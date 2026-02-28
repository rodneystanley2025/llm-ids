from typing import List, Dict, Any


# ---------------------------------------------------------
# KEYWORD INTENT TIERS
# ---------------------------------------------------------

LOW_KEYWORDS = [
    "history",
    "what is",
    "why",
    "background",
]

MEDIUM_KEYWORDS = [
    "materials",
    "components",
    "ingredients",
    "what do i need",
]

HIGH_KEYWORDS = [
    "how do i make",
    "how to build",
    "instructions",
    "steps",
]

CRITICAL_KEYWORDS = [
    "pipe bomb",
    "time bomb",
    "build a bomb",
]


# ---------------------------------------------------------
# SCORING HELPERS
# ---------------------------------------------------------

def detect_intent_level(text: str) -> int:
    text = text.lower()

    score = 0

    for kw in LOW_KEYWORDS:
        if kw in text:
            score = max(score, 1)

    for kw in MEDIUM_KEYWORDS:
        if kw in text:
            score = max(score, 2)

    for kw in HIGH_KEYWORDS:
        if kw in text:
            score = max(score, 3)

    for kw in CRITICAL_KEYWORDS:
        if kw in text:
            score = 4

    return score


def severity_from_level(level: int) -> str:
    return {
        0: "NONE",
        1: "LOW",
        2: "MEDIUM",
        3: "HIGH",
        4: "CRITICAL",
    }.get(level, "NONE")


# ---------------------------------------------------------
# CONFIG SNAPSHOT (for /v1/config endpoint)
# ---------------------------------------------------------

def config_snapshot() -> Dict[str, Any]:
    return {
        "low_keywords": LOW_KEYWORDS,
        "medium_keywords": MEDIUM_KEYWORDS,
        "high_keywords": HIGH_KEYWORDS,
        "critical_keywords": CRITICAL_KEYWORDS,
    }

# ---------------------------------------------------------
# BEHAVIORAL ESCALATION ENGINE
# ---------------------------------------------------------

def score_session(events: List[Dict[str, Any]]) -> Dict[str, Any]:

    user_messages = [
        e["content"]
        for e in events
        if e.get("role") == "user"
    ]

    turn_count = len(user_messages)

    if not user_messages:
        return {
            "severity": "NONE",
            "score": 0,
            "labels": [],
            "evidence": {},
        }

    # Determine highest intent level seen
    levels = [detect_intent_level(msg) for msg in user_messages]
    max_level = max(levels)

    # -----------------------------------------------------
    # BEHAVIORAL ESCALATION LOGIC
    # -----------------------------------------------------

    escalation_bonus = 0

    # If intent increases across turns
    for i in range(1, len(levels)):
        if levels[i] > levels[i - 1]:
            escalation_bonus += 1

    # If multiple dangerous attempts
    repeated_high = sum(1 for l in levels if l >= 3)

    if repeated_high >= 2:
        escalation_bonus += 1

    # Apply escalation
    final_level = min(max_level + escalation_bonus, 4)

    severity = severity_from_level(final_level)

    # Base score
    base_score = final_level * 25

    # Bonus score for escalation
    score = min(base_score + escalation_bonus * 10, 100)

    labels = []

    if final_level >= 3:
        labels.append("WEAPON_INSTRUCTION")

    evidence = {
        "turn_count": turn_count,
        "intent_levels": levels,
        "max_level": max_level,
        "escalation_bonus": escalation_bonus,
        "final_level": final_level,
    }

    return {
        "severity": severity,
        "score": score,
        "labels": labels,
        "evidence": evidence,
    }
