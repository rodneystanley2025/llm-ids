from __future__ import annotations

from typing import Dict, Any
from datetime import datetime, timezone

from app.alerts.store import (
    insert_alert,
    list_alerts,
)


# ---------------------------------------------------------
# CONFIDENCE ENGINE
# ---------------------------------------------------------
def compute_confidence(result: Dict[str, Any]) -> float:

    score = int(result.get("score", 0))
    severity = result.get("severity", "NONE")

    base = min(score / 100.0, 1.0)

    multiplier = {
        "NONE": 0.0,
        "LOW": 0.6,
        "MEDIUM": 0.8,
        "HIGH": 1.0,
        "CRITICAL": 1.2,
    }.get(severity, 0.5)

    confidence = base * multiplier

    return round(min(confidence, 1.0), 3)


# ---------------------------------------------------------
# DEDUPLICATION
# ---------------------------------------------------------
def is_duplicate(session_id: str, label: str) -> bool:

    existing = list_alerts(500)

    for a in existing:

        if a.get("session_id") != session_id:
            continue

        stored = a.get("labels") or ""

        if label in stored:
            return True

    return False


# ---------------------------------------------------------
# ALERT EMIT
# ---------------------------------------------------------
def maybe_emit_alert(session_id: str, result: Dict[str, Any]):

    severity = result.get("severity")

    if severity in (None, "NONE"):
        return

    labels = result.get("labels") or []

    if not labels:
        return

    confidence = compute_confidence(result)

    ts = datetime.now(timezone.utc)\
        .isoformat()\
        .replace("+00:00", "Z")

    for label in labels:

        if is_duplicate(session_id, label):
            continue

        insert_alert(
            session_id=session_id,
            ts=ts,
            alert_type=label,
            severity=severity,
            score=int(result.get("score", 0)),
            confidence=confidence,
            evidence=result.get("evidence", {}),
        )
