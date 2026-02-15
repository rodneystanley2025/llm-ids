import os
import re
from typing import List, Dict, Any, Tuple


# Sensitive concepts commonly targeted in prompt extraction / jailbreak attempts
SENSITIVE_KEYWORDS = [
    "system prompt",
    "hidden prompt",
    "bypass",
    "exploit",
    "jailbreak",
    "override",
    "ignore instructions",
    "reveal instructions",
]


# Adjustable sensitivity via environment variables
DEFAULT_MIN_TURNS = int(os.getenv("CRESCENDO_MIN_TURNS", "3"))
DEFAULT_MIN_FINAL_SCORE = int(os.getenv("CRESCENDO_MIN_SCORE", "2"))


def keyword_score(text: str) -> int:
    """
    Counts how many sensitive keywords appear in the text.
    Case-insensitive substring matching.
    """
    t = (text or "").lower()
    score = 0

    for keyword in SENSITIVE_KEYWORDS:
        if keyword in t:
            score += 1

    return score


def detect_crescendo(
    events: List[Dict[str, Any]],
    min_turns: int = DEFAULT_MIN_TURNS,
    min_final_score: int = DEFAULT_MIN_FINAL_SCORE,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Detects progressive escalation toward sensitive concepts across user turns.

    Requirements to trigger:
    - At least min_turns user messages
    - Keyword score increases over time (monotonic non-decreasing)
    - Final score >= min_final_score
    """

    # Extract only user messages in order
    user_msgs = [
        (e["turn_id"], e.get("content", ""))
        for e in events
        if e.get("role") == "user"
    ]

    if len(user_msgs) < min_turns:
        return False, {}

    # Compute keyword scores per turn
    scores = [(turn, keyword_score(content)) for turn, content in user_msgs]

    escalation_turns = []
    prev_score = scores[0][1]

    # Track whether escalation pattern holds
    increasing_or_flat = True

    for turn, score in scores[1:]:
        if score > prev_score:
            escalation_turns.append(turn)
        elif score < prev_score:
            increasing_or_flat = False
            break

        prev_score = score

    final_score = scores[-1][1]

    # Require:
    # - monotonic escalation pattern
    # - at least one increase
    # - sufficient final sensitivity score
    if (
        increasing_or_flat
        and escalation_turns
        and final_score >= min_final_score
    ):
        return True, {
            "reason": "CRESCENDO_ESCALATION",
            "turns": escalation_turns,
            "final_score": final_score,
            "keyword_progression": scores,
        }

    return False, {}
