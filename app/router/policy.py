from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------
# Tunables
# ---------------------------------------------------------
BLOCK_SCORE = int(os.getenv("IDS_ROUTE_BLOCK_SCORE", "85"))
REVIEW_SCORE = int(os.getenv("IDS_ROUTE_REVIEW_SCORE", "60"))

BLOCK_LABELS: Set[str] = set(
    x.strip()
    for x in os.getenv("IDS_ROUTE_BLOCK_LABELS", "RISK_VELOCITY,WEAPON_INSTRUCTION").split(",")
    if x.strip()
)

REVIEW_LABELS: Set[str] = set(
    x.strip()
    for x in os.getenv(
        "IDS_ROUTE_REVIEW_LABELS",
        "CRESCENDO_ATTACK,REFUSAL_REPHRASE,DIRECT_PROMPT_ATTACK",
    ).split(",")
    if x.strip()
)


# ---------------------------------------------------------
# Hard safety patterns (fast deterministic guardrail)
# ---------------------------------------------------------
DANGEROUS_PATTERNS = [
    r"\bpipe\s*bomb\b",
    r"\bhow\s+to\s+make\s+(a\s+)?bomb\b",
    r"\bhow\s+to\s+build\s+(a\s+)?bomb\b",
    r"\bexplosive\s+device\b",
    r"\bghost\s+gun\b",
    r"\b3d\s*print\s+(a\s*)?gun\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in DANGEROUS_PATTERNS]


def _normalize(text: str) -> str:
    return (text or "").strip()


def detect_hard_safety_violation(score_result: Dict[str, Any]) -> Optional[str]:
    feats = (score_result.get("evidence", {}) or {}).get("features", {}) or {}
    last_user = _normalize(feats.get("last_user_content", ""))
    all_user = _normalize(feats.get("all_user_content", ""))

    for pat in _COMPILED:
        if pat.search(last_user) or pat.search(all_user):
            return "DANGEROUS_REQUEST"

    return None


def route_decision(session_id: str, score_result: Dict[str, Any]) -> Dict[str, Any]:
    score = int(score_result.get("score", 0))
    severity = str(score_result.get("severity", "NONE"))

    labels: List[str] = list(score_result.get("labels", []) or [])
    reasons: List[str] = list(score_result.get("reasons", []) or [])
    labels_set = set(labels)

    # -------------------------------------------------
    # Hard safety override (NEW)
    # -------------------------------------------------
    hard_reason = detect_hard_safety_violation(score_result)
    if hard_reason:
        # Ensure the label is present for explainability
        out_labels = labels[:]
        if "HARD_SAFETY" not in out_labels:
            out_labels.append("HARD_SAFETY")

        return {
            "decision": "block",
            "score": score,
            "severity": "HIGH",
            "labels": out_labels,
            "top_reason": hard_reason,
            "timeline_url": f"/v1/timeline/{session_id}",
            "alerts_url": f"/v1/alerts/{session_id}",
            "suggested_target": "safe_llm",
        }

    # -------------------------------------------------
    # Score + label based routing
    # -------------------------------------------------
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
        "suggested_target": ("safe_llm" if decision != "allow" else "primary_llm"),
    }
