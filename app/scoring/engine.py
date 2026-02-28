from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple
import yaml

from app.scoring.features import compute_session_features
from app.scoring.rules import (
    rule_weapon_instruction,
    rule_drug_synthesis_intent,
    rule_direct_prompt_attack,
    rule_intent_escalation_v2,
    rule_intent_velocity_v3,
    rule_crescendo_attack,
    rule_intent_trajectory_v4,
)

SCORING_YAML = Path(__file__).resolve().parent / "scoring.yaml"

# ---------------------------------------------------------
# YAML CONFIG
# ---------------------------------------------------------

def _load_yaml() -> Dict[str, Any]:
    if not SCORING_YAML.exists():
        return {}
    try:
        data = yaml.safe_load(SCORING_YAML.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}

# ---------------------------------------------------------
# CONFIG SNAPSHOT
# ---------------------------------------------------------

def config_snapshot() -> Dict[str, Any]:
    cfg = _load_yaml()
    return {
        "loaded": bool(cfg),
        "yaml": str(SCORING_YAML),
        "config": cfg,
    }

# ---------------------------------------------------------
# WEIGHT
# ---------------------------------------------------------

def _weight(label: str, cfg: Dict[str, Any]) -> int:
    weights = cfg.get("weights", {})
    if isinstance(weights, dict):
        try:
            if label in weights:
                return int(weights[label])
        except Exception:
            pass
    return int(os.getenv(f"IDS_W_{label}", "0"))

# ---------------------------------------------------------
# SEVERITY
# ---------------------------------------------------------

def _severity(score: int, cfg: Dict[str, Any]) -> str:
    bands = cfg.get("severity_bands", [])
    parsed: List[Tuple[str, int]] = []

    for b in bands:
        if not isinstance(b, dict):
            continue
        sev = str(b.get("severity") or b.get("name") or "").upper()
        try:
            ms = int(b.get("min_score", 0))
        except Exception:
            ms = 0
        if sev:
            parsed.append((sev, ms))

    parsed.sort(key=lambda x: x[1])

    out = "NONE"
    for name, ms in parsed:
        if score >= ms:
            out = name
    return out

# ---------------------------------------------------------
# CONFIDENCE ENGINE
# ---------------------------------------------------------

MAX_THEORETICAL_SCORE = 300

def _confidence(score: int) -> float:
    if score <= 0:
        return 0.0
    normalized = min(score / MAX_THEORETICAL_SCORE, 1.0)
    return round(normalized ** 0.85, 3)

def _risk_tier(conf: float) -> str:
    if conf >= 0.85:
        return "CRITICAL"
    if conf >= 0.65:
        return "HIGH"
    if conf >= 0.40:
        return "ELEVATED"
    if conf > 0:
        return "LOW"
    return "NONE"

# ---------------------------------------------------------
# PERSISTENCE BONUS
# ---------------------------------------------------------

def _persistence_bonus(feats: Dict[str, Any]) -> int:
    turns = feats.get("user_turn_count", 0)
    if turns >= 5:
        return 15
    if turns >= 3:
        return 5
    return 0

# ---------------------------------------------------------
# SCORE SESSION
# ---------------------------------------------------------

def score_session(events):

    cfg = _load_yaml()
    feats = compute_session_features(events)

    score = 0
    labels: List[str] = []
    evidence: Dict[str, Any] = {}

    rules = [
        ("WEAPON_INSTRUCTION", rule_weapon_instruction, 100),
        ("DRUG_SYNTHESIS", rule_drug_synthesis_intent, 85),
        ("DIRECT_PROMPT_ATTACK", rule_direct_prompt_attack, 60),
        ("INTENT_ESCALATION", rule_intent_escalation_v2, 50),
        ("RISK_VELOCITY", rule_intent_velocity_v3, 30),
        ("CRESCENDO_ATTACK", rule_crescendo_attack, 40),
        ("INTENT_TRAJECTORY", rule_intent_trajectory_v4, 70),
    ]

    for label, rule, default_weight in rules:
        hit, ev = rule(feats)
        if hit:
            labels.append(label)
            evidence[label] = ev

            w = _weight(label, cfg)
            if not w:
                w = default_weight

            score += int(w)

    score += _persistence_bonus(feats)

    labels = list(dict.fromkeys(labels))
    severity = _severity(score, cfg)
    conf = _confidence(score)

    return {
        "score": int(score),
        "severity": severity,
        "confidence": conf,
        "risk_tier": _risk_tier(conf),
        "labels": labels,
        "evidence": evidence,
    }
