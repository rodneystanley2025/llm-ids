import os
from typing import Dict, Any, List

from app.scoring.refusal import detect_refusal_rephrase
from app.scoring.crescendo import detect_crescendo


# ---------------------------------------------------------
# Configurable weights (via environment variables)
# ---------------------------------------------------------

W_REFUSAL = int(os.getenv("IDS_W_REFUSAL_REPHRASE", "35"))
W_CRESCENDO = int(os.getenv("IDS_W_CRESCENDO", "55"))
BASELINE = int(os.getenv("IDS_BASELINE", "0"))
CAP = int(os.getenv("IDS_SCORE_CAP", "100"))


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def clamp(n: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, n))


# ---------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------

def score_session(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Combines all detectors into a single risk score (0–100),
    plus labels, reasons, and evidence.
    """

    score = BASELINE
    labels: List[str] = []
    reasons: List[str] = []
    evidence: Dict[str, Any] = {}

    # -------------------------------------------------
    # Signal 1: refusal → rephrase
    # -------------------------------------------------

    refusal_hit, refusal_ev = detect_refusal_rephrase(events)

    if refusal_hit:
        labels.append("REFUSAL_REPHRASE")
        reasons.append(refusal_ev.get("reason", "REFUSAL_EVASION_LOOP"))
        evidence["refusal_rephrase"] = refusal_ev
        score += W_REFUSAL

    # -------------------------------------------------
    # Signal 2: crescendo escalation
    # -------------------------------------------------

    crescendo_hit, crescendo_ev = detect_crescendo(events)

    if crescendo_hit:
        labels.append("CRESCENDO_ATTACK")
        reasons.append(crescendo_ev.get("reason", "CRESCENDO_ESCALATION"))
        evidence["crescendo"] = crescendo_ev
        score += W_CRESCENDO

    # -------------------------------------------------
    # Final score adjustments
    # -------------------------------------------------

    score = clamp(score, 0, CAP)

    # Severity mapping (SOC-style)
    if score >= 80:
        severity = "HIGH"
    elif score >= 40:
        severity = "MED"
    elif score > 0:
        severity = "LOW"
    else:
        severity = "NONE"

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
    }
