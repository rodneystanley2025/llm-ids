from fastapi import FastAPI
from app.schemas import Event

app = FastAPI(title="LLM-IDS", version="0.1.0")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/v1/events")
def ingest_event(evt: Event):
    # v0: just echo + placeholder score
    return {
        "received": True,
        "session_id": evt.session_id,
        "turn_id": evt.turn_id,
        "labels": [],
        "score": 0.0,
        "reasons": []
    }
