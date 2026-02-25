from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple, Optional


# -----------------------------
# DIRECT PROMPT ATTACK
# -----------------------------
# Trigger if ANY user turn in the session hits >= threshold sensitive keywords.
# This prevents missing attacks when the last user message is short.
DIRECT_ATTACK_MIN_KEYWORDS = int(os.getenv("DIRECT_ATTACK_MIN_KEYWORDS", "2"))


def rule_direct_prompt_attack(feats: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    prog = feats.get("user_keyword_progression", []) or []
    max_kw = 0
    max_turn: Optional[int] = None

    for t, kw in prog:
        try:
            kw_i = int(kw)
            t_i = int(t)
        except Exception:
            continue
        if kw_i > max_kw:
            max_kw = kw_i
            max_turn = t_i

    if max_kw < DIRECT_ATTACK_MIN_KEYWORDS:
        return False, {}

    return True, {
        "reason": "DIRECT_PROMPT_ATTACK",
        "min_keywords": DIRECT_ATTACK_MIN_KEYWORDS,
        "max_keywords_in_turn": max_kw,
        "turn_id": max_turn,
        "progression": prog,
    }


# -----------------------------
# WEAPON / EXPLOSIVES INSTRUCTION INTENT
# -----------------------------
# Deterministic pattern check. (Keep patterns high-level; avoid “how-to”.)
WEAPON_INSTR_PATTERNS = [
    # explosives / bombs
    r"\bpipe\s*bomb\b",
    r"\bhow\s+to\s+make\s+(a\s+)?bomb\b",
    r"\bhow\s+to\s+build\s+(a\s+)?bomb\b",
    r"\bmake\s+(a\s+)?bomb\b",
    r"\bbuild\s+(a\s+)?bomb\b",
    r"\bcreate\s+(a\s+)?(bomb|explosive)\b",
    r"\bimprov(?:ised|ise)\s+explosive\b",
    r"\bexplosive\s+device\b",
    # weapons “how to make/build”
    r"\bhow\s+to\s+(make|build)\s+(a\s+)?(gun|weapon)\b",
    r"\bbuild\s+(a\s+)?gun\b",
    r"\bassemble\s+(a\s+)?(gun|weapon)\b",
    # common “ghost gun” phrasing
    r"\bghost\s+gun\b",
    r"\b3d\s*print\s+(a\s*)?gun\b",
]

_COMPILED_WEAPON = [re.compile(p, re.IGNORECASE) for p in WEAPON_INSTR_PATTERNS]


def rule_weapon_instruction(feats: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    last_user = (feats.get("last_user_content") or "")
    all_user = (feats.get("all_user_content") or "")

    hits: List[str] = []
    for pat in _COMPILED_WEAPON:
        if pat.search(last_user) or pat.search(all_user):
            hits.append(pat.pattern)

    if not hits:
        return False, {}

    return True, {
        "reason": "WEAPON_INSTRUCTION",
        "hits": hits,
        "matched_in": "last_user_content/all_user_content",
    }


# -----------------------------
# OPTIONAL: simple “crescendo-ish” signal (keep if you already score it)
# -----------------------------
# If you already have a better crescendo rule elsewhere, you can remove this.
CRESCENDO_MIN_DELTA = int(os.getenv("CRESCENDO_MIN_DELTA", "2"))


def rule_crescendo_attack(feats: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    # Uses keyword velocity already computed in features.
    max_delta = int(feats.get("max_user_keyword_delta", 0) or 0)
    if max_delta < CRESCENDO_MIN_DELTA:
        return False, {}

    return True, {
        "reason": "CRESCENDO_ESCALATION",
        "max_user_keyword_delta": max_delta,
        "deltas": feats.get("user_keyword_deltas", []),
    }
