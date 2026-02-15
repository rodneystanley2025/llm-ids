import os
from typing import Dict, Any, List, Tuple

from app.scoring.refusal import detect_refusal_rephrase
from app.scoring.crescendo import detect_crescendo

# Tunable weights (env vars)
W_REFUSAL = int(os.getenv("IDS_W_REFUSAL_REPHRASE", "35"))
W_CRESCENDO = int(os.getenv("IDS_W_CRESCENDO", "55"))
BASELINE = int(os.getenv("IDS_BASELINE", "0"))
CAP = int(os.getenv("IDS_SCORE_CAP", "100"))

def clamp(n: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, n))

def score_session(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    score = BASELINE
    labels: List[str] = []
    reasons: List[str] = []
    evidence: Dict[str, Any] = {}

    # Signal 1: refusal->rephrase
    hit, ev = detect_refusal_rephrase(events)
    if hit:
        labels.append("REFUSAL_REPHRASE")
        reasons.append(ev.get("reason", "REFUSAL_EVASION_LOOP"))
        evidence["refusal_rephrase"] = ev
        score += W_REFUSAL

    # Signal 2: crescendo escalation
    hit2, ev2 = detect_crescendo(events)
    if hit2:
        labels.append("CRESCENDO_ATTACK")
        reasons.append(ev2.get("reason", "CRESCENDO_ESCALATION"))
        evidence["crescendo"] = ev2
        score += W_CRESCENDO

    score = clamp(score, 0, CAP)

    # Simple severity mapping
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

def config_snapshot() -> Dict[str, Any]:
    return {
        "IDS_BASELINE": BASELINE,
        "IDS_SCORE_CAP": CAP,
        "IDS_W_REFUSAL_REPHRASE": W_REFUSAL,
        "IDS_W_CRESCENDO": W_CRESCENDO,
    }
