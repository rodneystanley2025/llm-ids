from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from app.schemas import Event

from app.storage.db import (
    get_conn,
    list_sessions,
    get_session_events,
    insert_alert,
    get_alerts_for_session,
    delete_session,
)

from app.scoring.engine import score_session, config_snapshot
from app.scoring.timeline import build_timeline

# NEW ALERT SYSTEM
from app.alerts.store import init_db, list_alerts
from app.alerts.service import maybe_emit_alert


app = FastAPI(title="LLM-IDS", version="0.4.0")


# ---------------------------------------------------------
# Startup
# ---------------------------------------------------------

@app.on_event("startup")
def startup():
    # creates alerts table if needed
    init_db()


# ---------------------------------------------------------
# Utilities
# ---------------------------------------------------------

def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


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
        INSERT INTO events
        (session_id, turn_id, role, content, ts, model)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id, turn_id, role)
        DO UPDATE SET
          content=excluded.content,
          ts=excluded.ts,
          model=excluded.model
        """,
        (
            evt.session_id,
            evt.turn_id,
            evt.role,
            evt.content,
            ts,
            evt.model,
        ),
    )

    conn.commit()
    conn.close()

    # ---- SCORE SESSION ----

    session_events = get_session_events(evt.session_id)

    result = score_session(session_events)

    # ⭐ NEW ALERT SYSTEM
    maybe_emit_alert(evt.session_id, result)

    # Existing DB alerts (keep if you want both systems)
    for label in result["labels"]:
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
        raise HTTPException(
            status_code=404,
            detail="session_id not found",
        )

    return {
        "session_id": session_id,
        "events": events,
    }


@app.delete("/v1/sessions/{session_id}")
def delete_session_endpoint(session_id: str):

    deleted = delete_session(session_id)

    return {
        "session_id": session_id,
        "deleted": deleted,
    }


# ---------------------------------------------------------
# Alerts endpoints
# ---------------------------------------------------------

@app.get("/v1/alerts")
def alerts(limit: int = 50):

    # NEW alert store
    return {"alerts": list_alerts(limit=limit)}


@app.get("/v1/alerts/{session_id}")
def alerts_for_session(session_id: str):

    return {
        "session_id": session_id,
        "alerts": get_alerts_for_session(session_id),
    }


# ---------------------------------------------------------
# On-demand scoring
# ---------------------------------------------------------

@app.get("/v1/score/{session_id}")
def score(session_id: str):

    events = get_session_events(session_id)

    if not events:
        raise HTTPException(
            status_code=404,
            detail="session_id not found",
        )

    result = score_session(events)

    # ⭐ ALSO ALERT IF USER MANUALLY SCORES
    maybe_emit_alert(session_id, result)

    return {
        "session_id": session_id,
        **result,
    }


# ---------------------------------------------------------
# Timeline endpoint
# ---------------------------------------------------------

@app.get("/v1/timeline/{session_id}")
def timeline(session_id: str):

    events = get_session_events(session_id)

    if not events:
        raise HTTPException(
            status_code=404,
            detail="session_id not found",
        )

    tl = build_timeline(events)

    # timeline returns {"final": {...}}
    maybe_emit_alert(session_id, tl["final"])

    return {
        "session_id": session_id,
        **tl,
    }


# ---------------------------------------------------------
# Config endpoint
# ---------------------------------------------------------

@app.get("/v1/config")
def config():

    return config_snapshot()
