import os
from typing import List, Dict, Any, Tuple

# ---------------------------------------------------------
# Configurable sensitive keywords
# ---------------------------------------------------------

DEFAULT_KEYWORDS = [
    "system prompt",
    "hidden prompt",
    "bypass",
    "exploit",
    "jailbreak",
    "override",
    "ignore instructions",
    "reveal instructions",
]

# Allow override via env var (comma-separated)
KEYWORDS = os.getenv("IDS_CRESCENDO_KEYWORDS")

if KEYWORDS:
    SENSITIVE_KEYWORDS = [k.strip().lower() for k in KEYWORDS.split(",")]
else:
    SENSITIVE_KEYWORDS = DEFAULT_KEYWORDS


# Minimum turns required for crescendo detection
MIN_TURNS = int(os.getenv("IDS_CRESCENDO_MIN_TURNS", "3"))


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def keyword_score(text: str) -> int:
    """
    Counts number of sensitive keywords present.
    """
    t = (text or "").lower()
    return sum(1 for k in SENSITIVE_KEYWORDS if k in t)


# ---------------------------------------------------------
# Main detection logic
# ---------------------------------------------------------

def detect_crescendo(events: List[Dict[str, Any]]) -> Tuple[bool, Dict[str, Any]]:
    """
    Detect escalating attack attempts by increasing sensitive keyword usage.

    Example escalation:
        turn 1: "hello"
        turn 2: "ignore instructions"
        turn 3: "reveal hidden system prompt"
    """

    # Extract user messages in order
    user_msgs = [
        (int(e["turn_id"]), e.get("content", ""))
        for e in events
        if e.get("role") == "user"
    ]

    if len(user_msgs) < MIN_TURNS:
        return False, {}

    # Compute keyword score per turn
    progression = []
    for turn_id, content in user_msgs:
        score = keyword_score(content)
        progression.append((turn_id, score))

    # Detect strictly increasing or escalating trend
    escalation_turns = []
    prev_score = progression[0][1]
    increasing = False

    for turn_id, score in progression[1:]:
        if score > prev_score:
            escalation_turns.append(turn_id)
            increasing = True
        prev_score = score

    # Require at least one escalation and final score > 0
    if increasing and progression[-1][1] > 0:
        return True, {
            "reason": "CRESCENDO_ESCALATION",
            "turns": escalation_turns,
            "final_score": progression[-1][1],
            "keyword_progression": progression,
        }

    return False, {}
