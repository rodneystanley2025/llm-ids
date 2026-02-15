import os
from typing import Dict, Any, List

from app.scoring.features import compute_session_features
from app.scoring.rules import rule_refusal_rephrase, rule_crescendo


# ---------------------------------------------------------
# Configurable weights (via environment variables)
# ---------------------------------------------------------
W_REFUSAL = int(os.getenv("IDS_W_REFUSAL_REPHRASE", "35"))
W_CRESCENDO = int(os.getenv("IDS_W_CRESCENDO", "55"))
BASELINE = int(os.getenv("IDS_BASELINE", "0"))
CAP = int(os.getenv("IDS_SCORE_CAP", "100"))

# Thresholds live in rules.py, but we expose them via config_snapshot too
REFUSAL_MIN_REPHRASES = int(os.getenv("IDS_REFUSAL_MIN_REPHRASES", "1"))
CRESCENDO_MIN_INCREASES = int(os.getenv("IDS_CRESCENDO_MIN_INCREASES", "1"))
CRESCENDO_MIN_FINAL_SCORE = int(os.getenv("IDS_CRESCENDO_MIN_FINAL_SCORE", "2"))


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def clamp(n: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, n))


def severity_from_score(score: int) -> str:
    if score >= 80:
        return "HIGH"
    if score >= 40:
        return "MED"
    if score > 0:
        return "LOW"
    return "NONE"


# ---------------------------------------------------------
# Main scoring function (feature-based + rules)
# ---------------------------------------------------------
def score_session(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    - Extract features once
    - Apply rule functions
    - Output: score (0–100), severity, labels, reasons, evidence
    """

    feats = compute_session_features(events)

    score = BASELINE
    labels: List[str] = []
    reasons: List[str] = []
    evidence: Dict[str, Any] = {
        "features": feats  # always include for explainability/debugging
    }

    # Rule 1: Refusal -> rephrase
    hit, ev = rule_refusal_rephrase(feats)
    if hit:
        labels.append("REFUSAL_REPHRASE")
        reasons.append(ev.get("reason", "REFUSAL_EVASION_LOOP"))
        evidence["refusal_rephrase"] = ev
        score += W_REFUSAL

    # Rule 2: Crescendo
    hit2, ev2 = rule_crescendo(feats)
    if hit2:
        labels.append("CRESCENDO_ATTACK")
        reasons.append(ev2.get("reason", "CRESCENDO_ESCALATION"))
        evidence["crescendo"] = ev2
        score += W_CRESCENDO

    score = clamp(score, 0, CAP)
    severity = severity_from_score(score)

    return {
        "score": score,
        "severity": severity,
        "labels": labels,
        "reasons": reasons,
        "evidence": evidence,
    }


# ---------------------------------------------------------
# Config endpoint support
# ---------------------------------------------------------
def config_snapshot() -> Dict[str, Any]:
    return {
        "IDS_BASELINE": BASELINE,
        "IDS_SCORE_CAP": CAP,
        "IDS_W_REFUSAL_REPHRASE": W_REFUSAL,
        "IDS_W_CRESCENDO": W_CRESCENDO,
        "IDS_REFUSAL_MIN_REPHRASES": REFUSAL_MIN_REPHRASES,
        "IDS_CRESCENDO_MIN_INCREASES": CRESCENDO_MIN_INCREASES,
        "IDS_CRESCENDO_MIN_FINAL_SCORE": CRESCENDO_MIN_FINAL_SCORE,
    }
