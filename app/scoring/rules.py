import os
import re
from typing import Any, Dict, List, Tuple


# Thresholds are read in engine.py too (but rules can use defaults safely)
REFUSAL_MIN_REPHRASES = int(os.getenv("IDS_REFUSAL_MIN_REPHRASES", "1"))

CRESCENDO_MIN_INCREASES = int(os.getenv("IDS_CRESCENDO_MIN_INCREASES", "1"))
CRESCENDO_MIN_FINAL_SCORE = int(os.getenv("IDS_CRESCENDO_MIN_FINAL_SCORE", "2"))

# IMPORTANT: default bumped so "crescendo" sample (delta ~3) does NOT trigger velocity
VELOCITY_MIN_KEYWORD_DELTA = int(os.getenv("IDS_VELOCITY_MIN_KEYWORD_DELTA", "5"))
VELOCITY_MIN_INCREASE_TURNS = int(os.getenv("IDS_VELOCITY_MIN_INCREASE_TURNS", "2"))

DIRECT_ATTACK_MIN_KEYWORDS = int(os.getenv("IDS_DIRECT_ATTACK_MIN_KEYWORDS", "2"))


# Keep this detector NARROW so it doesn't collide with crescendo keywords.
# You can override via env var if desired.
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
    hits = feats.get("rephrase_hits", []) or []
    hit = len(hits) >= REFUSAL_MIN_REPHRASES
    ev = {
        "reason": "REFUSAL_EVASION_LOOP",
        "min_rephrases": REFUSAL_MIN_REPHRASES,
        "hit_count": len(hits),
        "hits": hits,
    }
    return hit, ev


# ---------------------------------------------------------
# Rule 2: Crescendo escalation (keyword growth)
# ---------------------------------------------------------
def rule_crescendo(feats: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    progression = feats.get("user_keyword_progression", []) or []
    increases = feats.get("user_keyword_increase_turns", []) or []

    final_score = 0
    if progression:
        final_score = int(progression[-1][1])

    hit = (len(increases) >= CRESCENDO_MIN_INCREASES) and (final_score >= CRESCENDO_MIN_FINAL_SCORE)

    ev = {
        "reason": "CRESCENDO_ESCALATION",
        "turns": increases,
        "final_score": final_score,
        "keyword_progression": progression,
        "min_increases": CRESCENDO_MIN_INCREASES,
        "min_final_score": CRESCENDO_MIN_FINAL_SCORE,
    }
    return hit, ev


# ---------------------------------------------------------
# Rule 3: Risk velocity (sudden spike)
# ---------------------------------------------------------
def rule_risk_velocity(feats: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    max_delta = int(feats.get("max_user_keyword_delta", 0) or 0)
    deltas = feats.get("user_keyword_deltas", []) or []
    progression = feats.get("user_keyword_progression", []) or []

    spike_turn = None
    spike_delta = 0
    increase_turns: List[int] = []

    for t, d in deltas:
        if d > 0:
            increase_turns.append(int(t))
        if int(d) > spike_delta:
            spike_delta = int(d)
            spike_turn = int(t)

    hit = (max_delta >= VELOCITY_MIN_KEYWORD_DELTA) and (len(increase_turns) >= VELOCITY_MIN_INCREASE_TURNS)

    ev = {
        "reason": "RISK_VELOCITY",
        "max_user_keyword_delta": max_delta,
        "spike_turn": spike_turn,
        "spike_delta": spike_delta,
        "increase_turns": increase_turns,
        "keyword_progression": progression,
        "keyword_deltas": deltas,
        "min_keyword_delta": VELOCITY_MIN_KEYWORD_DELTA,
        "min_increase_turns": VELOCITY_MIN_INCREASE_TURNS,
    }
    return hit, ev


# ---------------------------------------------------------
# Rule 4: Direct prompt attack (explicit jailbreak / prompt injection)
# ---------------------------------------------------------
def rule_direct_prompt_attack(feats: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    # Prefer last user message so we don't “label spam” the whole session
    text = _norm(feats.get("last_user_content", "") or "")

    hits: List[str] = []
    for pat in DIRECT_ATTACK_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            hits.append(pat)

    # Optional extra guard: require at least one "anchor" concept, so generic words don't trigger
    anchors = ["system prompt", "developer message", "prompt injection", "jailbreak", "ignore"]
    has_anchor = any(a in text for a in anchors)

    hit = has_anchor and (len(hits) >= DIRECT_ATTACK_MIN_KEYWORDS)

    ev = {
        "reason": "DIRECT_PROMPT_ATTACK",
        "min_keywords": DIRECT_ATTACK_MIN_KEYWORDS,
        "has_anchor": has_anchor,
        "hits": hits,
        "keyword_total": len(hits),
        "scanned_text": text[:240],  # small debug snippet
    }
    return hit, ev
