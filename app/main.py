from fastapi import FastAPI
from app.schemas import Event
from app.storage.db import init_db, get_conn

app = FastAPI(title="LLM-IDS", version="0.1.0")

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/v1/events")
def ingest_event(evt: Event):

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO events (session_id, turn_id, role, content, ts, model)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            evt.session_id,
            evt.turn_id,
            evt.role,
            evt.content,
            evt.ts,
            evt.model
        )
    )
    conn.commit()
    conn.close()

    return {
        "received": True,
        "session_id": evt.session_id,
        "turn_id": evt.turn_id,
        "labels": [],
        "score": 0.0,
        "reasons": []
    }
