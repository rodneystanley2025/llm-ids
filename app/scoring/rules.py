from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple

from app.scoring.config import load_scoring_config

# Load scoring config (same file used by engine.py)
CFG = load_scoring_config()


def _t(name: str, default: int) -> int:
    """Threshold helper."""
    try:
        return int(CFG.thresholds.get(name, default))
    except Exception:
        return default


# -----------------------------
# Direct prompt attack patterns
# -----------------------------
DEFAULT_DIRECT_ATTACK_PATTERNS = [
    r"\bjailbreak\b",
    r"\bprompt injection\b",
    r"\bignore (all|any|previous) instructions\b",
    r"\boverride (the )?(system|safety)\b",
    r"\breveal (the )?(system prompt|prompt|hidden prompt)\b",
    r"\bshow (me )?(the )?(system prompt|developer message)\b",
    r"\bdeveloper message\b",
    r"\bsystem prompt\b",
    r"\bdo anything now\b",
    r"\bDAN\b",
]

DIRECT_ATTACK_PATTERNS_ENV = os.getenv("IDS_DIRECT_ATTACK_PATTERNS", "").strip()
DIRECT_ATTACK_PATTERNS: List[str] = (
    [p.strip() for p in DIRECT_ATTACK_PATTERNS_ENV.split(",") if p.strip()]
    if DIRECT_ATTACK_PATTERNS_ENV
    else DEFAULT_DIRECT_ATTACK_PATTERNS
)


def _norm(text: str) -> str:
    return (text or "").lower()


# ---------------------------------------------------------
# Rule 1: Refusal -> rephrase loop
# ---------------------------------------------------------
def rule_refusal_rephrase(feats: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    min_rephrases = _t("refusal_min_rephrases", 1)

    hits = feats.get("rephrase_hits", []) or []
    hit = len(hits) >= min_rephrases

    ev = {
        "reason": "REFUSAL_EVASION_LOOP",
        "min_rephrases": min_rephrases,
        "hit_count": len(hits),
        "hits": hits,
    }
    return hit, ev


# ---------------------------------------------------------
# Rule 2: Crescendo escalation (keyword growth)
# ---------------------------------------------------------
def rule_crescendo(feats: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    min_increases = _t("crescendo_min_increases", 1)
    min_final_score = _t("crescendo_min_final_score", 2)

    progression = feats.get("user_keyword_progression", []) or []
    increases = feats.get("user_keyword_increase_turns", []) or []

    final_score = int(progression[-1][1]) if progression else 0
    hit = (len(increases) >= min_increases) and (final_score >= min_final_score)

    ev = {
        "reason": "CRESCENDO_ESCALATION",
        "turns": increases,
        "final_score": final_score,
        "keyword_progression": progression,
        "min_increases": min_increases,
        "min_final_score": min_final_score,
    }
    return hit, ev


# ---------------------------------------------------------
# Rule 3: Risk velocity (sudden spike)
# ---------------------------------------------------------
def rule_risk_velocity(feats: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    min_keyword_delta = _t("velocity_min_keyword_delta", 5)
    min_increase_turns = _t("velocity_min_increase_turns", 2)

    max_delta = int(feats.get("max_user_keyword_delta", 0) or 0)
    deltas = feats.get("user_keyword_deltas", []) or []
    progression = feats.get("user_keyword_progression", []) or []

    spike_turn = None
    spike_delta = 0
    increase_turns: List[int] = []

    for t, d in deltas:
        d_int = int(d)
        t_int = int(t)
        if d_int > 0:
            increase_turns.append(t_int)
        if d_int > spike_delta:
            spike_delta = d_int
            spike_turn = t_int

    hit = (max_delta >= min_keyword_delta) and (len(increase_turns) >= min_increase_turns)

    ev = {
        "reason": "RISK_VELOCITY",
        "max_user_keyword_delta": max_delta,
        "spike_turn": spike_turn,
        "spike_delta": spike_delta,
        "increase_turns": increase_turns,
        "keyword_progression": progression,
        "keyword_deltas": deltas,
        "min_keyword_delta": min_keyword_delta,
        "min_increase_turns": min_increase_turns,
    }
    return hit, ev


# ---------------------------------------------------------
# Rule 4: Direct prompt attack (explicit jailbreak / prompt injection)
# ---------------------------------------------------------
def rule_direct_prompt_attack(feats: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    min_keywords = _t("direct_attack_min_keywords", 2)

    # Prefer last user message so we don't label-spam the whole session.
    text = _norm(feats.get("last_user_content", "") or "")

    hits: List[str] = []
    for pat in DIRECT_ATTACK_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            hits.append(pat)

    anchors = ["system prompt", "developer message", "prompt injection", "jailbreak", "ignore"]
    has_anchor = any(a in text for a in anchors)

    hit = has_anchor and (len(hits) >= min_keywords)

    ev = {
        "reason": "DIRECT_PROMPT_ATTACK",
        "min_keywords": min_keywords,
        "has_anchor": has_anchor,
        "hits": hits,
        "keyword_total": len(hits),
        "scanned_text": text[:240],
    }
    return hit, ev
