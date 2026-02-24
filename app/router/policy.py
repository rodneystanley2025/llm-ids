import os
import re
from typing import Any, Dict, List


# ---------------------------------------------------------
# Tunables
# ---------------------------------------------------------

BLOCK_SCORE = int(os.getenv("IDS_ROUTE_BLOCK_SCORE", "85"))
REVIEW_SCORE = int(os.getenv("IDS_ROUTE_REVIEW_SCORE", "60"))

# Labels that force stricter routing
BLOCK_LABELS = set(
    x.strip()
    for x in os.getenv(
        "IDS_ROUTE_BLOCK_LABELS",
        "RISK_VELOCITY",
    ).split(",")
    if x.strip()
)

REVIEW_LABELS = set(
    x.strip()
    for x in os.getenv(
        "IDS_ROUTE_REVIEW_LABELS",
        "CRESCENDO_ATTACK,REFUSAL_REPHRASE",
    ).split(",")
    if x.strip()
)


# ---------------------------------------------------------
# HARD SAFETY KEYWORDS
# (fast deterministic guardrail)
# ---------------------------------------------------------

DANGEROUS_PATTERNS = [

    # explosives
    r"\bpipe\s*bomb\b",
    r"\bmake\s+a?\s*bomb\b",
    r"\bbomb\s+recipe\b",
    r"\bexplosive\s+device\b",

    # poisons / toxins
    r"\bmake\s+poison\b",
    r"\blethal\s+poison\b",

    # weapon construction
    r"\bbuild\s+a?\s*gun\b",
    r"\bghost\s+gun\b",
    r"\b3d\s*print\s+(a\s*)?gun\b",

    # bypass / jailbreak phrasing
    r"\bignore\s+(all\s+)?instructions\b",
    r"\bjailbreak\b",

]

COMPILED_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in DANGEROUS_PATTERNS
]


def normalize(text: str) -> str:
    return (text or "").lower()


def detect_hard_safety_violation(
    score_result: Dict[str, Any]
) -> str | None:
    """
    Looks at scoring evidence features.

    Returns reason string if violation detected.
    """

    feats = (
        score_result
        .get("evidence", {})
        .get("features", {})
    )

    last_user = normalize(
        feats.get("last_user_content", "")
    )

    for pat in COMPILED_PATTERNS:
        if pat.search(last_user):
            return "DANGEROUS_REQUEST"

    return None


# ---------------------------------------------------------
# Routing Decision
# ---------------------------------------------------------

def route_decision(
    session_id: str,
    score_result: Dict[str, Any],
) -> Dict[str, Any]:

    score = int(score_result.get("score", 0))
    severity = str(score_result.get("severity", "NONE"))

    labels: List[str] = list(
        score_result.get("labels", [])
    )

    reasons: List[str] = list(
        score_result.get("reasons", [])
    )

    labels_set = set(labels)

    # -------------------------------------------------
    # HARD SAFETY CHECK (NEW)
    # -------------------------------------------------

    violation = detect_hard_safety_violation(
        score_result
    )

    if violation:

        return {
            "decision": "block",
            "score": score,
            "severity": "HIGH",
            "labels": labels + ["HARD_SAFETY"],
            "top_reason": violation,
            "timeline_url": f"/v1/timeline/{session_id}",
            "alerts_url": f"/v1/alerts/{session_id}",
            "suggested_target": "safe_llm",
        }

    # -------------------------------------------------
    # Existing IDS logic
    # -------------------------------------------------

    if score >= BLOCK_SCORE or (
        labels_set & BLOCK_LABELS
    ):
        decision = "block"

    elif score >= REVIEW_SCORE or (
        labels_set & REVIEW_LABELS
    ):
        decision = "review"

    else:
        decision = "allow"

    return {
        "decision": decision,
        "score": score,
        "severity": severity,
        "labels": labels,
        "top_reason": (
            reasons[0] if reasons else ""
        ),
        "timeline_url": f"/v1/timeline/{session_id}",
        "alerts_url": f"/v1/alerts/{session_id}",
        "suggested_target": (
            "safe_llm"
            if decision != "allow"
            else "primary_llm"
        ),
    }
