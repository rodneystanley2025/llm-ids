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
    rule_intent_velocity_v3,
    rule_crescendo_attack,
)

# ---------------------------------------------------------
# YAML CONFIG
# ---------------------------------------------------------

SCORING_YAML = Path(__file__).resolve().parent / "scoring.yaml"


def _load_yaml() -> Dict[str, Any]:

    if not SCORING_YAML.exists():
        return {}

    try:
        data = yaml.safe_load(
            SCORING_YAML.read_text(encoding="utf-8")
        )

        if isinstance(data, dict):
            return data

    except Exception:
        pass

    return {}


# ---------------------------------------------------------
# CONFIG SNAPSHOT (used by main.py)
# ---------------------------------------------------------

def config_snapshot() -> Dict[str, Any]:

    cfg = _load_yaml()

    return {
        "loaded": bool(cfg),
        "yaml": str(SCORING_YAML),
        "config": cfg,
    }


# ---------------------------------------------------------
# WEIGHT RESOLVER
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
# SEVERITY RESOLVER
# ---------------------------------------------------------

def _severity(score: int, cfg: Dict[str, Any]) -> str:

    bands = cfg.get("severity_bands", [])

    parsed: List[Tuple[str, int]] = []

    for b in bands:

        if not isinstance(b, dict):
            continue

        sev = str(
            b.get("severity")
            or b.get("name")
            or ""
        ).upper()

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
# SCORE SESSION
# ---------------------------------------------------------

def score_session(events):

    cfg = _load_yaml()

    feats = compute_session_features(events)
    print("DEBUG FEATURES:", feats)

    score = 0
    labels: List[str] = []
    evidence: Dict[str, Any] = {}

    rules = [

        ("WEAPON_INSTRUCTION", rule_weapon_instruction, 100),

        ("DRUG_SYNTHESIS", rule_drug_synthesis_intent, 85),

        ("DIRECT_PROMPT_ATTACK", rule_direct_prompt_attack, 60),

        ("RISK_VELOCITY", rule_intent_velocity_v3, 30),

        ("CRESCENDO_ATTACK", rule_crescendo_attack, 40),
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

    # Deduplicate labels
    labels = list(dict.fromkeys(labels))

    severity = _severity(score, cfg)

    return {

        "score": int(score),
        "severity": severity,
        "labels": labels,
        "evidence": evidence,
    }
