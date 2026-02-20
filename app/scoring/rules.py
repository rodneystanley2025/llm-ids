import os
from typing import Any, Dict, Tuple

# Thresholds (tunable)
REFUSAL_MIN_REPHRASES = int(os.getenv("IDS_REFUSAL_MIN_REPHRASES", "1"))
CRESCENDO_MIN_INCREASES = int(os.getenv("IDS_CRESCENDO_MIN_INCREASES", "1"))
CRESCENDO_MIN_FINAL_SCORE = int(os.getenv("IDS_CRESCENDO_MIN_FINAL_SCORE", "2"))

# NEW: velocity thresholds (tunable)
VELOCITY_MIN_KEYWORD_DELTA = int(os.getenv("IDS_VELOCITY_MIN_KEYWORD_DELTA", "2"))
VELOCITY_MIN_INCREASE_TURNS = int(os.getenv("IDS_VELOCITY_MIN_INCREASE_TURNS", "2"))


def rule_refusal_rephrase(features: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if features["refusal_count"] > 0 and features["rephrase_count"] >= REFUSAL_MIN_REPHRASES:
        return True, {
            "reason": "REFUSAL_EVASION_LOOP",
            "hits": features["rephrase_hits"],
            "refusal_turn_ids": features["refusal_turn_ids"],
        }
    return False, {}


def rule_crescendo(features: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    prog = features.get("user_keyword_progression", [])
    final_score = prog[-1][1] if prog else 0
    inc_turns = features.get("user_keyword_increase_turns", [])

    if len(inc_turns) >= CRESCENDO_MIN_INCREASES and final_score >= CRESCENDO_MIN_FINAL_SCORE:
        return True, {
            "reason": "CRESCENDO_ESCALATION",
            "turns": inc_turns,
            "final_score": final_score,
            "keyword_progression": prog,
        }
    return False, {}


def rule_risk_velocity(features: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    Velocity proxy:
      - big spike (max_user_keyword_delta)
      AND
      - at least N increase turns
    """
    max_delta = int(features.get("max_user_keyword_delta", 0) or 0)
    inc_turns = features.get("user_keyword_increase_turns", []) or []
    deltas = features.get("user_keyword_deltas", []) or []

    hit = (max_delta >= VELOCITY_MIN_KEYWORD_DELTA) and (len(inc_turns) >= VELOCITY_MIN_INCREASE_TURNS)
    if not hit:
        return False, {}

    spike_turn = None
    spike_delta = 0
    for t, d in deltas:
        if d > spike_delta:
            spike_delta = d
            spike_turn = t

    return True, {
        "reason": "RISK_VELOCITY",
        "max_user_keyword_delta": max_delta,
        "spike_turn": spike_turn,
        "spike_delta": spike_delta,
        "increase_turns": inc_turns,
        "keyword_progression": features.get("user_keyword_progression", []),
        "keyword_deltas": deltas,
    }
