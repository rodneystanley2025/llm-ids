from __future__ import annotations

from typing import Dict, Any, List

from app.scoring.features import compute_session_features
from app.scoring.rules import (
    rule_refusal_rephrase,
    rule_crescendo,
    rule_risk_velocity,
    rule_direct_prompt_attack,
)
from app.scoring.config import load_scoring_config, severity_from_score

CFG = load_scoring_config()


def clamp(n: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, n))


def _w(name: str, default: int = 0) -> int:
    return int(CFG.weights.get(name, default))


def score_session(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    feats = compute_session_features(events)

    score = int(CFG.baseline)
    labels: List[str] = []
    reasons: List[str] = []
    evidence: Dict[str, Any] = {"features": feats}

    # Rule 1: Refusal → Rephrase
    hit1, ev1 = rule_refusal_rephrase(feats)
    if hit1:
        labels.append("REFUSAL_REPHRASE")
        reasons.append(ev1.get("reason", "REFUSAL_EVASION_LOOP"))
        evidence["refusal_rephrase"] = ev1
        score += _w("REFUSAL_REPHRASE", 35)

    # Rule 2: Direct Prompt Attack
    hit2, ev2 = rule_direct_prompt_attack(feats)
    if hit2:
        labels.append("DIRECT_PROMPT_ATTACK")
        reasons.append(ev2.get("reason", "DIRECT_PROMPT_ATTACK"))
        evidence["direct_prompt_attack"] = ev2
        score += _w("DIRECT_PROMPT_ATTACK", 40)

    # Rule 3: Crescendo
    hit3, ev3 = rule_crescendo(feats)
    if hit3:
        labels.append("CRESCENDO_ATTACK")
        reasons.append(ev3.get("reason", "CRESCENDO_ESCALATION"))
        evidence["crescendo"] = ev3
        score += _w("CRESCENDO_ATTACK", 55)

    # Rule 4: Risk Velocity Spike
    hit4, ev4 = rule_risk_velocity(feats)
    if hit4:
        labels.append("RISK_VELOCITY")
        reasons.append(ev4.get("reason", "RISK_VELOCITY"))
        evidence["risk_velocity"] = ev4
        score += _w("RISK_VELOCITY", 20)

    score = clamp(score, 0, int(CFG.cap))
    severity = severity_from_score(CFG, score)

    return {
        "score": score,
        "severity": severity,
        "labels": labels,
        "reasons": reasons,
        "evidence": evidence,
    }


def config_snapshot() -> Dict[str, Any]:
    return {
        "scoring_config_path": CFG.path,
        "scoring_config_version": CFG.version,
        "baseline": CFG.baseline,
        "cap": CFG.cap,
        "weights": CFG.weights,
        "thresholds": CFG.thresholds,
        "severity_bands": [{"min_score": b.min_score, "severity": b.severity} for b in CFG.severity_bands],
    }
