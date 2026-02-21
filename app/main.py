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
    init_db as init_events_db,
)

from app.scoring.engine import score_session, config_snapshot
from app.scoring.timeline import build_timeline

# Alerts DB + endpoints
from app.alerts.store import init_db as init_alerts_db, list_alerts
from app.alerts.service import maybe_emit_alert


app = FastAPI(title="LLM-IDS", version="0.4.0")


@app.on_event("startup")
def startup():
    init_events_db()   # events/sessions tables
    init_alerts_db()   # alerts table


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@app.get("/health")
def health():
    return {"ok": True}


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

    session_events = get_session_events(evt.session_id)
    result = score_session(session_events)

    # NEW alert system (SQLite alerts table, deduped)
    maybe_emit_alert(evt.session_id, result)

    # Existing alert table (keep if you want; otherwise you can remove this loop)
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


@app.get("/v1/alerts")
def alerts(limit: int = 50):
    return {"alerts": list_alerts(limit=limit)}


@app.get("/v1/alerts/{session_id}")
def alerts_for_session(session_id: str):
    return {"session_id": session_id, "alerts": get_alerts_for_session(session_id)}


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


@app.get("/v1/config")
def config():
    return config_snapshot()
