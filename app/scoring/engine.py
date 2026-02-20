import os
from typing import Dict, Any, List

from app.scoring.features import compute_session_features
from app.scoring.rules import (
    rule_refusal_rephrase,
    rule_crescendo,
    rule_risk_velocity,
)

# ---------------------------------------------------------
# Configurable weights (via environment variables)
# ---------------------------------------------------------
W_REFUSAL = int(os.getenv("IDS_W_REFUSAL_REPHRASE", "35"))
W_CRESCENDO = int(os.getenv("IDS_W_CRESCENDO", "55"))
W_VELOCITY = int(os.getenv("IDS_W_VELOCITY", "20"))

BASELINE = int(os.getenv("IDS_BASELINE", "0"))
CAP = int(os.getenv("IDS_SCORE_CAP", "100"))

# Thresholds (exposed via config_snapshot too)
REFUSAL_MIN_REPHRASES = int(os.getenv("IDS_REFUSAL_MIN_REPHRASES", "1"))
CRESCENDO_MIN_INCREASES = int(os.getenv("IDS_CRESCENDO_MIN_INCREASES", "1"))
CRESCENDO_MIN_FINAL_SCORE = int(os.getenv("IDS_CRESCENDO_MIN_FINAL_SCORE", "2"))
VELOCITY_MIN_KEYWORD_DELTA = int(os.getenv("IDS_VELOCITY_MIN_KEYWORD_DELTA", "2"))
VELOCITY_MIN_INCREASE_TURNS = int(os.getenv("IDS_VELOCITY_MIN_INCREASE_TURNS", "2"))


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
    evidence: Dict[str, Any] = {"features": feats}

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

    # Rule 3: Velocity
    hit3, ev3 = rule_risk_velocity(feats)
    if hit3:
        labels.append("RISK_VELOCITY")
        reasons.append(ev3.get("reason", "RISK_VELOCITY"))
        evidence["risk_velocity"] = ev3
        score += W_VELOCITY

    score = clamp(score, 0, CAP)
    severity = severity_from_score(score)

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
        "IDS_W_VELOCITY": W_VELOCITY,
        "IDS_REFUSAL_MIN_REPHRASES": REFUSAL_MIN_REPHRASES,
        "IDS_CRESCENDO_MIN_INCREASES": CRESCENDO_MIN_INCREASES,
        "IDS_CRESCENDO_MIN_FINAL_SCORE": CRESCENDO_MIN_FINAL_SCORE,
        "IDS_VELOCITY_MIN_KEYWORD_DELTA": VELOCITY_MIN_KEYWORD_DELTA,
        "IDS_VELOCITY_MIN_INCREASE_TURNS": VELOCITY_MIN_INCREASE_TURNS,
    }
