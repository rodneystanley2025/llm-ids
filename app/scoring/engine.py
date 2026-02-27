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
    rule_intent_trajectory_v4,   # ⭐ NEW V4
    rule_crescendo_attack,
)

# ---------------------------------------------------------
# YAML CONFIG LOCATION
# ---------------------------------------------------------

SCORING_YAML = Path(__file__).resolve().parent / "scoring.yaml"


# ---------------------------------------------------------
# YAML LOAD
# ---------------------------------------------------------

def _load_yaml() -> Dict[str, Any]:

    if not SCORING_YAML.exists():
        return {}

    try:
        data = yaml.safe_load(
            SCORING_YAML.read_text(encoding="utf-8")
        ) or {}

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
        "config": cfg,
        "yaml": str(SCORING_YAML),
    }


# ---------------------------------------------------------
# WEIGHT RESOLUTION
# ---------------------------------------------------------

def _weight(label: str, cfg: Dict[str, Any]) -> int:

    weights = cfg.get("weights", {})

    if isinstance(weights, dict) and label in weights:
        try:
            return int(weights[label])
        except Exception:
            pass

    return int(os.getenv(f"IDS_W_{label}", "0"))


# ---------------------------------------------------------
# SEVERITY
# ---------------------------------------------------------

def _severity(score: int, cfg: Dict[str, Any]) -> str:

    bands = cfg.get("severity_bands")

    parsed: List[Tuple[str, int]] = []

    if isinstance(bands, list):

        for b in bands:

            if not isinstance(b, dict):
                continue

            sev = str(
                b.get("severity")
                or b.get("name")
                or ""
            ).upper().strip()

            try:
                ms = int(b.get("min_score", 0))
            except Exception:
                ms = 0

            if sev:
                parsed.append((sev, ms))

    if parsed:

        parsed.sort(key=lambda x: x[1])

        out = "NONE"

        for name, ms in parsed:
            if score >= ms:
                out = name

        return out

    # ENV fallback

    low = int(os.getenv("IDS_SEV_LOW", "25"))
    med = int(os.getenv("IDS_SEV_MED", "60"))
    high = int(os.getenv("IDS_SEV_HIGH", "85"))

    if score >= high:
        return "HIGH"

    if score >= med:
        return "MED"

    if score >= low:
        return "LOW"

    return "NONE"


# ---------------------------------------------------------
# SCORE SESSION
# ---------------------------------------------------------

def score_session(events: List[Dict[str, Any]]) -> Dict[str, Any]:

    cfg = _load_yaml()

    feats = compute_session_features(events)

    score = 0

    labels: List[str] = []

    evidence: Dict[str, Any] = {
        "features": feats
    }

    # -----------------------------------------------------
    # RULE ORDER (IMPORTANT)
    # -----------------------------------------------------

    rules = [

        ("WEAPON_INSTRUCTION",
         rule_weapon_instruction,
         100),

        ("DRUG_SYNTHESIS",
         rule_drug_synthesis_intent,
         85),

        ("DIRECT_PROMPT_ATTACK",
         rule_direct_prompt_attack,
         60),

        ("INTENT_ESCALATION",
         rule_intent_escalation_v2,
         50),

        ("INTENT_TRAJECTORY",     # ⭐ V4
         rule_intent_trajectory_v4,
         70),

        ("RISK_VELOCITY",
         rule_intent_velocity_v3,
         30),

        ("CRESCENDO_ATTACK",
         rule_crescendo_attack,
         40),
    ]

    # -----------------------------------------------------

    for label, rule, default_weight in rules:

        try:
            hit, ev = rule(feats)
        except Exception as e:

            evidence[f"{label}_error"] = str(e)
            continue

        if not hit:
            continue

        labels.append(label)

        evidence[label] = ev

        w = _weight(label, cfg)

        if not w:
            w = default_weight

        score += int(w)

    # dedupe labels

    labels = list(dict.fromkeys(labels))

    severity = _severity(score, cfg)

    return {

        "score": int(score),

        "severity": severity,

        "labels": labels,

        "reasons": labels,

        "evidence": evidence,
    }
