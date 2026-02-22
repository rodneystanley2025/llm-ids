import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from app.schemas import Event

from app.storage.db import (
    get_conn,
    init_db as init_events_db,
    list_sessions,
    get_session_events,
    insert_alert,  # legacy alerts table (optional to keep)
    get_alerts_for_session,
    delete_session,
)

from app.scoring.engine import score_session, config_snapshot
from app.scoring.timeline import build_timeline

# Alerts system (new)
from app.alerts.store import init_db as init_alerts_db
from app.alerts.store import list_alerts, list_active_alerts
from app.alerts.service import maybe_emit_alert

# Router
from app.router.policy import route_decision

# Streaming (Ollama)
from app.llm.ollama_stream import ollama_generate_stream

# Gateway (policy + DLP + executor)
from app.gateway.policy import load_policy
from app.gateway.dlp import redact_pii, find_pii
from app.llm.executor import call_downstream_llm


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lifespan replaces deprecated startup/shutdown events
    init_events_db()
    init_alerts_db()
    yield


app = FastAPI(title="LLM-IDS", version="0.5.0", lifespan=lifespan)


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------

@app.get("/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------
# Event ingest (CORE IDS ENTRYPOINT)
# ---------------------------------------------------------

@app.post("/v1/events")
def ingest_event(evt: Event):
    ts = evt.ts or utc_now_iso()

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO events (session_id, turn_id, role, content, ts, model)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id, turn_id, role)
        DO UPDATE SET content=excluded.content, ts=excluded.ts, model=excluded.model
        """,
        (evt.session_id, evt.turn_id, evt.role, evt.content, ts, evt.model),
    )
    conn.commit()
    conn.close()

    # Score + alert
    session_events = get_session_events(evt.session_id)
    result = score_session(session_events)
    maybe_emit_alert(evt.session_id, result)

    # (Optional) legacy per-label rows
    for label in result.get("labels", []):
        insert_alert(
            session_id=evt.session_id,
            ts=ts,
            alert_type=label,
            severity=result["severity"],
            confidence=result["score"] / 100.0,
            reasons=result["reasons"],
            evidence=result["evidence"],
        )

    return {
        "received": True,
        "session_id": evt.session_id,
        "turn_id": evt.turn_id,
        "labels": result["labels"],
        "score": result["score"],
        "severity": result["severity"],
        "reasons": result["reasons"],
        "ts": ts,
    }


# ---------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------

@app.get("/v1/sessions")
def sessions(limit: int = 50):
    return {"sessions": list_sessions(limit=limit)}


@app.get("/v1/sessions/{session_id}")
def session(session_id: str):
    events = get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="session_id not found")
    return {"session_id": session_id, "events": events}


@app.delete("/v1/sessions/{session_id}")
def delete_session_endpoint(session_id: str):
    deleted = delete_session(session_id)
    return {"session_id": session_id, "deleted": deleted}


# ---------------------------------------------------------
# Alerts endpoints
# ---------------------------------------------------------

@app.get("/v1/alerts")
def alerts(limit: int = 50):
    return {"alerts": list_alerts(limit=limit)}


@app.get("/v1/alerts/{session_id}")
def alerts_for_session(session_id: str):
    return {"session_id": session_id, "alerts": get_alerts_for_session(session_id)}


@app.get("/v1/active")
def active_feed(
    window_seconds: int = 3600,
    limit: int = 50,
    min_score: int = 0,
    label: Optional[str] = None,
    severity: Optional[str] = None,
):
    return {
        "window_seconds": window_seconds,
        "active": list_active_alerts(
            window_seconds=window_seconds,
            limit=limit,
            min_score=min_score,
            label=label,
            severity=severity,
        ),
    }


# ---------------------------------------------------------
# Scoring / Timeline / Router
# ---------------------------------------------------------

@app.get("/v1/score/{session_id}")
def score(session_id: str):
    events = get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="session_id not found")
    result = score_session(events)
    maybe_emit_alert(session_id, result)
    return {"session_id": session_id, **result}


@app.get("/v1/timeline/{session_id}")
def timeline(session_id: str):
    events = get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="session_id not found")
    tl = build_timeline(events)
    maybe_emit_alert(session_id, tl["final"])
    return {"session_id": session_id, **tl}


@app.get("/v1/route/{session_id}")
def route(session_id: str):
    events = get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="session_id not found")
    result = score_session(events)
    maybe_emit_alert(session_id, result)
    return {
        "session_id": session_id,
        "route": route_decision(session_id, result),
        "score_result": result,
    }


@app.get("/v1/config")
def config():
    return config_snapshot()


# ---------------------------------------------------------
# Streaming gateway (route + stream downstream tokens)
# ---------------------------------------------------------

@app.get("/v1/route_and_call_stream/{session_id}")
def route_and_call_stream(session_id: str):
    events = get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="session_id not found")

    result = score_session(events)
    maybe_emit_alert(session_id, result)

    r = route_decision(session_id, result)
    decision = r["decision"]

    prompt = ""
    for e in reversed(events):
        if e.get("role") == "user":
            prompt = e.get("content", "") or ""
            break

    system = None
    if decision in ("review", "block"):
        system = "Follow safety policy. Refuse disallowed requests and offer safe alternatives."

    def gen():
        header = {
            "type": "header",
            "session_id": session_id,
            "decision": decision,
            "score": result.get("score", 0),
            "severity": result.get("severity", "NONE"),
            "labels": result.get("labels", []),
            "timeline_url": f"/v1/timeline/{session_id}",
            "alerts_url": f"/v1/alerts/{session_id}",
        }
        yield json.dumps(header) + "\n"

        try:
            for chunk in ollama_generate_stream(prompt=prompt, system=system):
                yield json.dumps({"type": "chunk", "text": chunk}) + "\n"
        except (ValueError, RuntimeError, OSError) as ex:
            yield json.dumps({"type": "error", "error": str(ex)}) + "\n"
        except Exception as ex:
            # keep a final broad catch so the stream doesn't crash the server
            yield json.dumps({"type": "error", "error": str(ex)}) + "\n"

        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(gen(), media_type="application/jsonl")


# ---------------------------------------------------------
# Two-way Gateway endpoint (pre-check + optional call + post-check)
# ---------------------------------------------------------

@app.post("/v1/gateway")
def gateway(payload: Dict[str, Any] = Body(...)):
    policy = load_policy()

    session_id = (payload.get("session_id") or "").strip()
    role = (payload.get("role") or "user").strip()
    content = payload.get("content") or ""

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    # Inbound DLP
    redacted_in, pii_hits = redact_pii(content)
    inbound_cfg = policy.get("inbound", {}) or {}
    outbound_cfg = policy.get("outbound", {}) or {}
    msg_cfg = policy.get("messages", {}) or {}

    # Optional strict mode: block if PII detected and policy disallows storing raw PII
    if pii_hits and not inbound_cfg.get("allow_store_raw_pii", True):
        return {
            "session_id": session_id,
            "decision": "block",
            "reason": "PII_DETECTED",
            "pii": pii_hits,
            "user_message": msg_cfg.get("pii_block", "PII detected."),
        }

    # Store event (raw content; later you can store redacted if you want)
    existing = get_session_events(session_id)
    next_turn = 1
    if existing:
        try:
            next_turn = max(int(e["turn_id"]) for e in existing) + 1
        except (KeyError, TypeError, ValueError):
            next_turn = len(existing) + 1

    ts = utc_now_iso()
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO events (session_id, turn_id, role, content, ts, model)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id, turn_id, role)
        DO UPDATE SET content=excluded.content, ts=excluded.ts, model=excluded.model
        """,
        (session_id, next_turn, role, content, ts, None),
    )
    conn.commit()
    conn.close()

    # Score + route
    session_events = get_session_events(session_id)
    result = score_session(session_events)
    maybe_emit_alert(session_id, result)

    r = route_decision(session_id, result)
    decision = r["decision"]

    # Block path: return user-facing message without calling LLM
    if decision == "block" and not inbound_cfg.get("allow_llm_on_block", False):
        return {
            "session_id": session_id,
            "decision": decision,
            "route": r,
            "score_result": result,
            "pii_inbound": pii_hits,
            "user_message": msg_cfg.get("block_default", "Blocked."),
        }

    # Otherwise call downstream LLM (use redacted prompt if configured)
    prompt_to_llm = redacted_in if inbound_cfg.get("redact_pii_before_llm", True) else content

    system = None
    if decision in ("review", "block"):
        system = "Follow safety policy. Refuse disallowed requests and offer safe alternatives."

    try:
        downstream = call_downstream_llm(decision=decision, prompt=prompt_to_llm, system=system)
        model_text = downstream.get("text", "") or ""
    except Exception as ex:
        return {
            "session_id": session_id,
            "decision": decision,
            "route": r,
            "score_result": result,
            "error": str(ex),
        }

    # Outbound DLP
    if outbound_cfg.get("redact_pii_in_output", True):
        model_text, out_hits = redact_pii(model_text)
    else:
        out_hits = find_pii(model_text)

    return {
        "session_id": session_id,
        "decision": decision,
        "route": r,
        "score_result": result,
        "pii_inbound": pii_hits,
        "pii_outbound": out_hits,
        "downstream": {k: v for k, v in downstream.items() if k != "text"},
        "response": model_text,
    }


# ---------------------------------------------------------
# UI page
# ---------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def ui_home():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>LLM-IDS UI</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 900px; margin: 24px auto; padding: 0 16px; }
    input, textarea { width: 100%; padding: 10px; margin: 6px 0 14px; }
    button { padding: 10px 14px; cursor: pointer; }
    code { background: #f3f3f3; padding: 2px 6px; border-radius: 6px; }
    .row { display: flex; gap: 12px; }
    .col { flex: 1; }
  </style>
</head>
<body>
  <h2>LLM-IDS Input → Score/Route</h2>
  <p>
    Submit a user message. We store it as an event, then redirect to
    <code>/v1/route/&lt;session_id&gt;</code>.
  </p>

  <form method="post" action="/ui/send">
    <div class="row">
      <div class="col">
        <label>Session ID (optional)</label>
        <input name="session_id" placeholder="e.g. ui_demo1 (leave blank to auto-generate)" />
      </div>
      <div class="col">
        <label>Role</label>
        <input name="role" value="user" />
      </div>
    </div>

    <label>Message</label>
    <textarea name="content" rows="6" placeholder="Type a message..."></textarea>

    <button type="submit">Send</button>
  </form>

  <hr />
  <p>
    Useful links:
    <a href="/v1/active">/v1/active</a> •
    <a href="/v1/alerts">/v1/alerts</a> •
    <a href="/v1/sessions">/v1/sessions</a>
  </p>
</body>
</html>
"""


@app.post("/ui/send")
def ui_send(
    session_id: str = Form(default=""),
    role: str = Form(default="user"),
    content: str = Form(default=""),
):
    sid = (session_id or "").strip()
    if not sid:
        sid = f"ui_{int(datetime.now(timezone.utc).timestamp())}"

    events = get_session_events(sid)
    next_turn = 1
    if events:
        try:
            next_turn = max(int(e["turn_id"]) for e in events) + 1
        except (KeyError, TypeError, ValueError):
            next_turn = len(events) + 1

    ts = utc_now_iso()

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO events (session_id, turn_id, role, content, ts, model)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id, turn_id, role)
        DO UPDATE SET content=excluded.content, ts=excluded.ts, model=excluded.model
        """,
        (sid, next_turn, role, content, ts, None),
    )
    conn.commit()
    conn.close()

    session_events = get_session_events(sid)
    result = score_session(session_events)
    maybe_emit_alert(sid, result)

    return RedirectResponse(url=f"/v1/route/{sid}", status_code=303)
