import os
from typing import Any, Dict, Optional

from app.alerts.store import create_alert_if_needed

ALERT_THRESHOLD = int(os.getenv("IDS_ALERT_THRESHOLD", "80"))


def maybe_emit_alert(session_id: str, score_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    score_result should be the dict returned by score_session() OR the timeline's "final".
    """
    return create_alert_if_needed(
        session_id=session_id,
        final_score=int(score_result.get("score", 0)),
        final_severity=str(score_result.get("severity", "NONE")),
        labels=list(score_result.get("labels", [])),
        reasons=list(score_result.get("reasons", [])),
        threshold=ALERT_THRESHOLD,
        evidence=dict(score_result.get("evidence", {}) or {}),
        timeline_url=f"/v1/timeline/{session_id}",
    )
