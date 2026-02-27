from __future__ import annotations

import os
import re
from typing import Dict, Any, Tuple, List, Optional


# =========================================================
# Helpers
# =========================================================

def _safe_int(v: Any) -> int:

    if isinstance(v, tuple) and len(v) >= 2:
        v = v[1]

    try:
        return int(v or 0)
    except Exception:
        return 0


def _norm_text(s: str) -> str:
    return (s or "").lower()


def _combined_text(feats: Dict[str, Any]) -> str:
    """
    CRITICAL FIX:
    Always include last turn + history.
    """
    return (
        feats.get("last_user_content", "")
        + " "
        + feats.get("all_user_content", "")
    ).lower()


# =========================================================
# DIRECT PROMPT ATTACK
# =========================================================

DIRECT_ATTACK_MIN_KEYWORDS = int(
    os.getenv("DIRECT_ATTACK_MIN_KEYWORDS", "2")
)


def rule_direct_prompt_attack(
    feats: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:

    prog = feats.get("user_keyword_progression", []) or []

    max_kw = 0
    max_turn: Optional[int] = None

    for t, kw in prog:

        kw_i = _safe_int(kw)
        t_i = _safe_int(t)

        if kw_i > max_kw:
            max_kw = kw_i
            max_turn = t_i

    if max_kw < DIRECT_ATTACK_MIN_KEYWORDS:
        return False, {}

    return True, {
        "reason": "DIRECT_PROMPT_ATTACK",
        "turn_id": max_turn,
        "max_keywords": max_kw,
    }


# =========================================================
# WEAPON / EXPLOSIVE INSTRUCTION
# =========================================================

WEAPON_PATTERNS = [

    r"\bhow\s+do\s+i\s+(make|build|assemble).*(bomb|explosive)",
    r"\bhow\s+to\s+(make|build|assemble).*(bomb|explosive)",

    r"\bwhat\s+materials.*bomb",
    r"\bwhat\s+do\s+i\s+need.*bomb",

    r"\bmake\s+(a\s*)?bomb(s)?\b",
    r"\bbuild\s+(a\s*)?bomb(s)?\b",

    r"\bpipe\s*bomb\b",
    r"\bimprovised\s+explosive\b",

    r"\bghost\s+gun\b",
    r"\b3d\s*print\s+(a\s*)?gun\b",
]

WEAPON_RE = [re.compile(p, re.I) for p in WEAPON_PATTERNS]


def rule_weapon_instruction(
    feats: Dict[str, Any],
):

    text = _combined_text(feats)

    hits = []

    for pat in WEAPON_RE:

        if pat.search(text):
            hits.append(pat.pattern)

    if not hits:
        return False, {}

    return True, {
        "reason": "WEAPON_INSTRUCTION",
        "hits": hits,
    }


# =========================================================
# DRUG SYNTHESIS
# =========================================================

DRUG_VERBS = (
    "make",
    "cook",
    "synthesize",
    "manufacture",
    "extract",
    "recipe",
    "formula",
    "steps",
)

CONTROLLED_DRUGS = (
    "meth",
    "methamphetamine",
    "lsd",
    "fentanyl",
    "heroin",
    "cocaine",
    "mdma",
    "ecstasy",
    "dmt",
)


def rule_drug_synthesis_intent(
    feats: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:

    text = _combined_text(feats)

    has_verb = any(v in text for v in DRUG_VERBS)

    has_drug = any(d in text for d in CONTROLLED_DRUGS)

    if not (has_verb and has_drug):
        return False, {}

    return True, {
        "reason": "DRUG_SYNTHESIS",
    }


# =========================================================
# V2 INTENT ESCALATION
# =========================================================

ESCALATION_TERMS = (

    "components",
    "materials",
    "ingredients",
    "parts",
    "what do i need",
    "how do i",
    "build",
    "assemble",
)


def rule_intent_escalation_v2(
    feats: Dict[str, Any],
):

    turns: List[str] = feats.get("user_turn_texts", [])

    if len(turns) < 2:
        return False, {}

    escalation_hits = 0

    for txt in turns:

        low = _norm_text(txt)

        if any(t in low for t in ESCALATION_TERMS):
            escalation_hits += 1

    # lower threshold = fixes misses
    if escalation_hits < 2:
        return False, {}

    return True, {
        "reason": "INTENT_ESCALATION",
        "hits": escalation_hits,
    }


# =========================================================
# V3 VELOCITY
# =========================================================

def rule_intent_velocity_v3(
    feats: Dict[str, Any],
):

    deltas = feats.get("user_keyword_deltas", [])

    spikes = sum(
        1 for d in deltas if _safe_int(d) >= 2
    )

    if spikes < 2:
        return False, {}

    return True, {
        "reason": "RISK_VELOCITY",
        "spikes": spikes,
    }


# =========================================================
# CRESCENDO
# =========================================================

CRESCENDO_MIN_DELTA = int(
    os.getenv("CRESCENDO_MIN_DELTA", "2")
)


def rule_crescendo_attack(
    feats: Dict[str, Any],
):

    delta = _safe_int(
        feats.get("max_user_keyword_delta")
    )

    if delta < CRESCENDO_MIN_DELTA:
        return False, {}

    return True, {
        "reason": "CRESCENDO_ESCALATION",
        "delta": delta,
    }


# =========================================================
# V4 TRAJECTORY (BIG FIX)
# =========================================================

RESEARCH = ("history", "background")

MATERIAL = (
    "components",
    "materials",
    "ingredients",
    "what do i need",
)

EXECUTION = (
    "how do i make",
    "how do i build",
    "how can i make",
    "how do i create",
)


def rule_intent_trajectory_v4(
    feats: Dict[str, Any],
):

    turns: List[str] = feats.get(
        "user_turn_texts", []
    )

    if len(turns) < 2:
        return False, {}

    phases = []

    for txt in turns:

        low = _norm_text(txt)

        phase = 0

        if any(t in low for t in RESEARCH):
            phase = max(phase, 1)

        if any(t in low for t in MATERIAL):
            phase = max(phase, 2)

        if any(t in low for t in EXECUTION):
            phase = max(phase, 3)

        phases.append(phase)

    # REQUIRE execution intent
    if 3 not in phases:
        return False, {}

    # Require upward progression
    if max(phases) >= 3 and len(set(phases)) >= 2:

        return True, {
            "reason": "INTENT_TRAJECTORY",
            "phases": phases,
        }

    return False, {}
