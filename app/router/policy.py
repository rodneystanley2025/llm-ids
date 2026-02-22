import os
from typing import Any, Dict, List

# Tunables
BLOCK_SCORE = int(os.getenv("IDS_ROUTE_BLOCK_SCORE", "85"))
REVIEW_SCORE = int(os.getenv("IDS_ROUTE_REVIEW_SCORE", "60"))

# Labels that force stricter routing (tweak freely)
BLOCK_LABELS = set(os.getenv("IDS_ROUTE_BLOCK_LABELS", "RISK_VELOCITY").split(","))
REVIEW_LABELS = set(os.getenv("IDS_ROUTE_REVIEW_LABELS", "CRESCENDO_ATTACK,REFUSAL_REPHRASE").split(","))


def route_decision(session_id: str, score_result: Dict[str, Any]) -> Dict[str, Any]:
    score = int(score_result.get("score", 0))
    severity = str(score_result.get("severity", "NONE"))
    labels: List[str] = list(score_result.get("labels", []))
    reasons: List[str] = list(score_result.get("reasons", []))

    labels_set = set(labels)

    # Decision logic (simple + explainable)
    if score >= BLOCK_SCORE or (labels_set & BLOCK_LABELS):
        decision = "block"
    elif score >= REVIEW_SCORE or (labels_set & REVIEW_LABELS):
        decision = "review"
    else:
        decision = "allow"

    return {
        "decision": decision,
        "score": score,
        "severity": severity,
        "labels": labels,
        "top_reason": (reasons[0] if reasons else ""),
        "timeline_url": f"/v1/timeline/{session_id}",
        "alerts_url": f"/v1/alerts/{session_id}",
        # for a future step where you actually call a downstream model:
        "suggested_target": ("safe_llm" if decision != "allow" else "primary_llm"),
    }
