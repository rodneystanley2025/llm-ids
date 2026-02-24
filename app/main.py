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

# UI layout helper
from app.ui.layout import page_html


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
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
def timeline(session_id: str, include_events: bool = True, truncate: int = 240):
    events = get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="session_id not found")
    tl = build_timeline(events, include_events=include_events, truncate=truncate)
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

    if pii_hits and not inbound_cfg.get("allow_store_raw_pii", True):
        return {
            "session_id": session_id,
            "decision": "block",
            "reason": "PII_DETECTED",
            "pii": pii_hits,
            "user_message": msg_cfg.get("pii_block", "PII detected."),
        }

    # Store event
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

    if decision == "block" and not inbound_cfg.get("allow_llm_on_block", False):
        return {
            "session_id": session_id,
            "decision": decision,
            "route": r,
            "score_result": result,
            "pii_inbound": pii_hits,
            "user_message": msg_cfg.get("block_default", "Blocked."),
        }

    # Call downstream LLM
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
# UI pages
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def ui_home():
    body = """
  <h2>LLM-IDS Input → Score/Route</h2>
  <p>
    Submit a user message. We store it as an event, then redirect to
    <code>/v1/route/&lt;session_id&gt;</code>.
  </p>

  <div class="card">
    <form method="post" action="/ui/send">
      <div style="display:flex; gap:12px; flex-wrap:wrap;">
        <div style="flex:1; min-width:260px;">
          <label>Session ID (optional)</label>
          <input name="session_id" placeholder="e.g. ui_demo1 (leave blank to auto-generate)" style="width:100%; padding:10px; margin-top:6px;" />
        </div>
        <div style="width:220px; min-width:180px;">
          <label>Role</label>
          <input name="role" value="user" style="width:100%; padding:10px; margin-top:6px;" />
        </div>
      </div>

      <div style="margin-top:12px;">
        <label>Message</label>
        <textarea name="content" rows="6" placeholder="Type a message..." style="width:100%; padding:10px; margin-top:6px;"></textarea>
      </div>

      <button type="submit" style="padding:10px 14px; cursor:pointer;">Send</button>
    </form>
  </div>

  <p class="muted">
    Tip: go to <a href="/ui/sessions">Sessions</a> and click Timeline.
  </p>
"""
    return page_html("LLM-IDS UI", body, active="home")


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


@app.get("/ui/timeline/{session_id}", response_class=HTMLResponse)
def ui_timeline(session_id: str):
    events = get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="session_id not found")

    tl = build_timeline(events, include_events=True, truncate=400)
    final = tl.get("final", {})
    turns = tl.get("turns", [])

    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    pill = {
        "NONE": "#6b7280",
        "LOW": "#0ea5e9",
        "MED": "#f59e0b",
        "HIGH": "#ef4444",
    }.get(final.get("severity", "NONE"), "#6b7280")

    labels = ", ".join(final.get("labels", []) or [])
    reasons = ", ".join(final.get("reasons", []) or [])
    top_signals = tl.get("top_signals", []) or []

    all_types = set()
    for t in turns:
        for h in (t.get("highlights", []) or []):
            all_types.add(h.get("type", ""))
    all_types = [x for x in sorted(all_types) if x]

    rows = []
    for t in turns:
        tid = int(t.get("turn_id"))
        hs = t.get("highlights", []) or []
        types = [h.get("type", "") for h in hs if h.get("type")]
        type_attr = " ".join(types)
        has_hl = "1" if types else "0"

        hs_html = "".join(
            f"<button class='tag' type='button' data-type='{esc(h.get('type',''))}'"
            f" onclick='toggleType(\"{esc(h.get('type',''))}\")'>{esc(h.get('type',''))}</button>"
            for h in hs
        )

        evs = t.get("events", []) or []
        parts = []
        for e in evs:
            role = e.get("role", "")
            content = esc(e.get("content", ""))
            cls = "user" if role == "user" else "assistant"
            parts.append(
                f"<div class='msg {cls}'>"
                f"<div class='role'>{esc(role)}</div>"
                f"<pre>{content}</pre>"
                f"</div>"
            )
        body = "".join(parts)

        rows.append(f"""
          <div class="turn" id="turn-{tid}" data-has-highlight="{has_hl}" data-types="{esc(type_attr)}">
            <div class="turnhdr">
              <div class="turnid">Turn {tid}</div>
              <div class="highlights">{hs_html}</div>
            </div>
            <div class="turnbody">{body}</div>
          </div>
        """)

    tags_toolbar = "".join(
        f"<button class='tag ghost' type='button' data-type='{esc(tp)}' onclick='toggleType(\"{esc(tp)}\")'>{esc(tp)}</button>"
        for tp in all_types
    )

    body = f"""
  <h2>Session Timeline: <code>{esc(session_id)}</code></h2>

  <div class="card">
    <div style="display:flex; gap:12px; flex-wrap:wrap; align-items:center;">
      <span class="pill">{esc(final.get("severity","NONE"))}</span>
      <div><b>Score:</b> {int(final.get("score",0) or 0)}</div>
      <div><b>Labels:</b> {esc(labels) or "—"}</div>
    </div>

    <div style="margin-top:10px;">
      <div><b>Reasons:</b> {esc(reasons) or "—"}</div>
      <div><b>Explanation:</b> {esc(tl.get("explanation",""))}</div>
      <div><b>Top signals:</b> {" • ".join(esc(x) for x in top_signals) if top_signals else "—"}</div>
    </div>

    <div class="toolbar">
      <button class="btn primary" type="button" onclick="toggleOnlyHighlighted()">Show highlighted only</button>
      <button class="btn warn" type="button" onclick="jumpHighlight(-1)">◀ Prev highlight</button>
      <button class="btn warn" type="button" onclick="jumpHighlight(1)">Next highlight ▶</button>
      <span class="hint">Filters:</span>
      {tags_toolbar}
    </div>

    <div style="margin-top:10px;">
      <a href="/v1/timeline/{esc(session_id)}">JSON</a> •
      <a href="/v1/score/{esc(session_id)}">Score</a> •
      <a href="/v1/alerts/{esc(session_id)}">Alerts</a>
    </div>
  </div>

  <div id="turns">
    {''.join(rows)}
  </div>

  <script>
    let onlyHighlighted = false;
    let activeTypes = new Set();
    let highlightIds = [];
    let highlightIdx = -1;

    function rebuildHighlightList() {{
      const turns = Array.from(document.querySelectorAll('.turn'));
      highlightIds = turns
        .filter(t => t.dataset.hasHighlight === "1" && !t.classList.contains('hidden'))
        .map(t => t.id);
      if (highlightIds.length === 0) highlightIdx = -1;
      else if (highlightIdx >= highlightIds.length) highlightIdx = highlightIds.length - 1;
    }}

    function applyFilters() {{
      const turns = Array.from(document.querySelectorAll('.turn'));
      turns.forEach(t => {{
        const hasHl = t.dataset.hasHighlight === "1";
        const types = (t.dataset.types || "").split(" ").filter(Boolean);

        let ok = true;
        if (onlyHighlighted && !hasHl) ok = false;

        if (activeTypes.size > 0) {{
          ok = ok && types.some(tp => activeTypes.has(tp));
        }}

        t.classList.toggle('hidden', !ok);
      }});
      rebuildHighlightList();
    }}

    function toggleOnlyHighlighted() {{
      onlyHighlighted = !onlyHighlighted;
      applyFilters();
    }}

    function toggleType(tp) {{
      if (!tp) return;
      if (activeTypes.has(tp)) activeTypes.delete(tp);
      else activeTypes.add(tp);

      document.querySelectorAll(`button[data-type="${{tp}}"]`).forEach(b => {{
        b.classList.toggle('active', activeTypes.has(tp));
      }});

      applyFilters();
    }}

    function jumpHighlight(dir) {{
      rebuildHighlightList();
      if (highlightIds.length === 0) return;

      highlightIdx = highlightIdx + dir;
      if (highlightIdx < 0) highlightIdx = 0;
      if (highlightIdx >= highlightIds.length) highlightIdx = highlightIds.length - 1;

      const id = highlightIds[highlightIdx];
      const el = document.getElementById(id);
      if (el) {{
        window.location.hash = id;
        el.scrollIntoView({{ behavior: "smooth", block: "start" }});
      }}
    }}

    applyFilters();
  </script>
"""

    extra_css = f"""
    .pill {{ background:{pill}; color:white; padding:4px 10px; border-radius:999px; font-weight:600; }}
    .toolbar {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-top:10px; }}
    .btn {{ border:1px solid #cbd5e1; background:#fff; padding:6px 10px; border-radius:10px; cursor:pointer; }}
    .btn:hover {{ background:#f8fafc; }}
    .btn.primary {{ border-color:#2563eb; color:#2563eb; }}
    .btn.warn {{ border-color:#f59e0b; color:#b45309; }}
    .tag {{
      display:inline-block; border:1px solid #cbd5e1; background:#fff;
      padding:2px 8px; border-radius:999px; margin-right:6px; font-size:12px; cursor:pointer;
    }}
    .tag.active {{ background:#0ea5e9; border-color:#0ea5e9; color:white; }}
    .tag.ghost {{ opacity:0.85; }}
    .turn {{ border:1px solid #e5e7eb; border-radius:12px; margin:12px 0; overflow:hidden; }}
    .turnhdr {{ background:#f8fafc; padding:10px 12px; display:flex; justify-content:space-between; gap:12px; }}
    .turnid {{ font-weight:700; }}
    .turnbody {{ padding:12px; display:grid; gap:10px; }}
    .msg {{ border:1px solid #e5e7eb; border-radius:10px; padding:10px; }}
    .msg.user {{ border-left:4px solid #0ea5e9; }}
    .msg.assistant {{ border-left:4px solid #a855f7; }}
    .role {{ font-size:12px; color:#64748b; margin-bottom:6px; font-weight:600; text-transform:uppercase; }}
    pre {{ margin:0; white-space:pre-wrap; word-break:break-word; }}
    .hidden {{ display:none !important; }}
    .hint {{ color:#64748b; font-size:12px; }}
"""
    return page_html(f"Timeline: {session_id}", body, active="sessions", extra_css=extra_css)


@app.get("/ui/sessions", response_class=HTMLResponse)
def ui_sessions(limit: int = 100, q: str = ""):
    items = list_sessions(limit=limit)
    qn = (q or "").strip().lower()
    if qn:
        items = [s for s in items if qn in (s.get("session_id", "") or "").lower()]

    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    rows = []
    for s in items:
        sid = s.get("session_id", "")
        first_ts = s.get("first_ts") or "—"
        last_ts = s.get("last_ts") or "—"
        cnt = int(s.get("event_count") or 0)

        rows.append(f"""
          <tr>
            <td><code>{esc(sid)}</code></td>
            <td>{esc(first_ts)}</td>
            <td>{esc(last_ts)}</td>
            <td style="text-align:right;">{cnt}</td>
            <td class="links">
              <a href="/ui/timeline/{esc(sid)}">Timeline</a>
              <a href="/v1/score/{esc(sid)}">Score</a>
              <a href="/v1/alerts/{esc(sid)}">Alerts</a>
              <a href="/v1/sessions/{esc(sid)}">Raw</a>
            </td>
          </tr>
        """)

    body = f"""
  <h2>Sessions</h2>

  <div class="card">
    <form class="row" method="get" action="/ui/sessions">
      <input name="q" value="{esc(q)}" placeholder="Filter by session_id (substring)..." />
      <input name="limit" value="{int(limit)}" style="width:110px;" />
      <button type="submit">Apply</button>
      <span class="muted">Tip: click Timeline for the “wow” view</span>
    </form>
  </div>

  <div class="card">
    <table>
      <thead>
        <tr>
          <th>Session</th>
          <th>First</th>
          <th>Last</th>
          <th style="text-align:right;">Events</th>
          <th>Links</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows) if rows else '<tr><td colspan="5" class="muted">No sessions found.</td></tr>'}
      </tbody>
    </table>
  </div>
"""

    extra_css = """
    input { padding:10px; width: 340px; max-width: 100%; }
    button { padding:10px 12px; cursor:pointer; }
    table { width:100%; border-collapse: collapse; }
    th, td { padding:10px; border-bottom:1px solid #e5e7eb; vertical-align: top; }
    th { text-align:left; color:#475569; font-size: 12px; text-transform: uppercase; letter-spacing: .03em; }
    .links a { margin-right:10px; }
    .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
"""
    return page_html("LLM-IDS Sessions", body, active="sessions", extra_css=extra_css)
