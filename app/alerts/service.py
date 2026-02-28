import hashlib
import time

from app.storage.db import insert_alert

ALERT_COOLDOWN_SECONDS = 60
_last_alert_cache = {}

def maybe_emit_alert(session_id: str, result: dict):

    if not result.get("labels"):
        return

    fingerprint = hashlib.sha256(
        (session_id + str(result.get("labels"))).encode()
    ).hexdigest()

    now = time.time()
    last = _last_alert_cache.get(fingerprint)

    if last and now - last < ALERT_COOLDOWN_SECONDS:
        return  # suppress duplicate

    _last_alert_cache[fingerprint] = now

    insert_alert(
        session_id=session_id,
        ts=result.get("score"),
        alert_type="RULE_TRIGGER",
        severity=result.get("severity"),
        confidence=result.get("confidence"),
        reasons=result.get("labels"),
        evidence=result.get("evidence"),
    )
