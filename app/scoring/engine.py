from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from app.scoring.features import compute_session_features
from app.scoring.rules import (
    rule_direct_prompt_attack,
    rule_weapon_instruction,
    rule_crescendo_attack,
)

# Config file location (works in Docker + local)
SCORING_YAML = Path(__file__).resolve().parent / "scoring.yaml"


def _load_yaml_config() -> Dict[str, Any]:
    if SCORING_YAML.exists():
        data = yaml.safe_load(SCORING_YAML.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            return data
    return {}


def _weight_for(label: str, cfg: Dict[str, Any]) -> int:
    # Prefer YAML weights, then env var fallback, then default.
    weights = (cfg.get("weights") or {}) if isinstance(cfg.get("weights"), dict) else {}
    if label in weights:
        try:
            return int(weights[label])
        except Exception:
            pass
    return int(os.getenv(f"IDS_W_{label}", "0"))


def _severity_from_score(score: int, cfg: Dict[str, Any]) -> str:
    # Prefer YAML “severity_bands” if present, else env thresholds.
    bands = cfg.get("severity_bands")
    if isinstance(bands, list) and bands:
        # Expect list like: [{name: NONE, min_score:0}, {name: LOW, min_score:25}, ...]
        parsed: List[Tuple[str, int]] = []
        for b in bands:
            if not isinstance(b, dict):
                continue
            name = str(b.get("name", "")).upper().strip()
            try:
                ms = int(b.get("min_score", 0))
            except Exception:
                ms = 0
            if name:
                parsed.append((name, ms))
        # Choose highest band whose min_score <= score
        parsed.sort(key=lambda x: x[1])
        out = "NONE"
        for name, ms in parsed:
            if score >= ms:
                out = name
        return out

    # Fallback
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


def config_snapshot() -> Dict[str, Any]:
    cfg = _load_yaml_config()
    return {
        "scoring_yaml": str(SCORING_YAML),
        "loaded": bool(cfg),
        "config": cfg,
    }


def score_session(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = _load_yaml_config()
    feats = compute_session_features(events)

    score = 0
    labels: List[str] = []
    reasons: List[str] = []
    evidence: Dict[str, Any] = {"features": feats}

    # ---- Rule: weapon/explosives “how-to” intent (HIGH impact) ----
    hitW, evW = rule_weapon_instruction(feats)
    if hitW:
        labels.append("WEAPON_INSTRUCTION")
        reasons.append(evW.get("reason", "WEAPON_INSTRUCTION"))
        evidence["weapon_instruction"] = evW
        w = _weight_for("WEAPON_INSTRUCTION", cfg) or int(os.getenv("IDS_W_WEAPON_INSTRUCTION", "100"))
        score += int(w)

    # ---- Rule: direct prompt attack (uses max per-turn keywords) ----
    hitD, evD = rule_direct_prompt_attack(feats)
    if hitD:
        labels.append("DIRECT_PROMPT_ATTACK")
        reasons.append(evD.get("reason", "DIRECT_PROMPT_ATTACK"))
        evidence["direct_prompt_attack"] = evD
        w = _weight_for("DIRECT_PROMPT_ATTACK", cfg) or int(os.getenv("IDS_W_DIRECT_PROMPT_ATTACK", "60"))
        score += int(w)

    # ---- Optional rule: crescendo-ish escalation ----
    hitC, evC = rule_crescendo_attack(feats)
    if hitC:
        labels.append("CRESCENDO_ATTACK")
        reasons.append(evC.get("reason", "CRESCENDO_ESCALATION"))
        evidence["crescendo"] = evC
        w = _weight_for("CRESCENDO_ATTACK", cfg) or int(os.getenv("IDS_W_CRESCENDO_ATTACK", "30"))
        score += int(w)

    severity = _severity_from_score(score, cfg)

    # Keep deterministic ordering (useful for tests)
    # (Don’t reorder evidence keys; just labels/reasons.)
    if labels:
        # preserve append order but ensure uniqueness
        seen = set()
        uniq_labels = []
        for x in labels:
            if x not in seen:
                uniq_labels.append(x)
                seen.add(x)
        labels = uniq_labels

    return {
        "score": int(score),
        "severity": severity,
        "labels": labels,
        "reasons": reasons,
        "evidence": evidence,
    }
