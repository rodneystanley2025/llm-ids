from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException

from app.schemas import Event
from app.storage.db import (
    init_db,
    get_conn,
    list_sessions,
    get_session_events,
    insert_alert,
    list_alerts,
    get_alerts_for_session,
)
from app.scoring.engine import score_session, config_snapshot
from app.scoring.timeline import build_timeline

app = FastAPI(title="LLM-IDS", version="0.4.0")
from app.storage.db import delete_session  # add to imports


# ---------------------------------------------------------
# Utilities
# ---------------------------------------------------------
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
# Startup
# ---------------------------------------------------------

# ---------------------------------------------------------
# Startup
# ---------------------------------------------------------
@app.on_event("startup")
def startup():
    init_db()


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------

@app.get("/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------
# Event ingest (core IDS entrypoint)
# ---------------------------------------------------------

@app.post("/v1/events")
def ingest_event(evt: Event):
    ts = evt.ts or utc_now_iso()

    # Upsert event
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO events (session_id, turn_id, role, content, ts, model)
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

    # Score session
    session_events = get_session_events(evt.session_id)
    result = score_session(session_events)

    # Insert alerts (deduped by DB unique index + INSERT OR IGNORE)
    # Get full session
    session_events = get_session_events(evt.session_id)

    # Run centralized scoring engine
    result = score_session(session_events)

    # Insert alerts (deduped automatically by DB unique index)
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

    # Return scoring result inline
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

    return {
        "session_id": session_id,
        "events": events,
    }


# ---------------------------------------------------------
# Alert endpoints
# ---------------------------------------------------------

@app.get("/v1/alerts")
def alerts(limit: int = 50):
    return {"alerts": list_alerts(limit=limit)}


@app.get("/v1/alerts/{session_id}")
def alerts_for_session(session_id: str):
    return {
        "session_id": session_id,
        "alerts": get_alerts_for_session(session_id),
    }


# ---------------------------------------------------------
# Scoring endpoint (on-demand scoring)
# ---------------------------------------------------------

@app.get("/v1/score/{session_id}")
def score(session_id: str):
    events = get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="session_id not found")
    result = score_session(events)
    return {"session_id": session_id, **result}

# ---------------------------------------------------------
# Alert endpoints
# ---------------------------------------------------------
@app.get("/v1/alerts")
def alerts(limit: int = 50):
    return {"alerts": list_alerts(limit=limit)}


@app.get("/v1/alerts/{session_id}")
def alerts_for_session(session_id: str):
    return {"session_id": session_id, "alerts": get_alerts_for_session(session_id)}


# ---------------------------------------------------------
# Scoring endpoint (on-demand scoring)
# ---------------------------------------------------------
@app.get("/v1/score/{session_id}")
def score(session_id: str):
    events = get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="session_id not found")
    return {"session_id": session_id, **score_session(events)}


# ---------------------------------------------------------
# Timeline endpoint (per-turn risk progression)
# ---------------------------------------------------------
@app.get("/v1/timeline/{session_id}")
def timeline(session_id: str):
    events = get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="session_id not found")
    return {"session_id": session_id, **build_timeline(events)}


# ---------------------------------------------------------
# Config endpoint (shows runtime IDS settings)
# ---------------------------------------------------------
@app.get("/v1/config")
def config():
    return config_snapshot()

@app.delete("/v1/sessions/{session_id}")
def delete_session_endpoint(session_id: str):
    deleted = delete_session(session_id)
    return {"session_id": session_id, "deleted": deleted}
