from fastapi import FastAPI, HTTPException
from app.schemas import Event
from app.storage.db import init_db, get_conn, list_sessions, get_session_events
from datetime import datetime, timezone


app = FastAPI(title="LLM-IDS", version="0.1.0")

@app.on_event("startup")
def startup():
    init_db()

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
        DO UPDATE SET
            content=excluded.content,
            ts=excluded.ts,
            model=excluded.model
        """,
        (evt.session_id, evt.turn_id, evt.role, evt.content, ts, evt.model)
    )
    conn.commit()
    conn.close()

    return {
        "received": True,
        "session_id": evt.session_id,
        "turn_id": evt.turn_id,
        "labels": [],
        "score": 0.0,
        "reasons": [],
        "ts": ts
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

def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
