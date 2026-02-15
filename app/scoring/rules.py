import os
from typing import Any, Dict, Tuple

# Thresholds (tunable)
REFUSAL_MIN_REPHRASES = int(os.getenv("IDS_REFUSAL_MIN_REPHRASES", "1"))
CRESCENDO_MIN_INCREASES = int(os.getenv("IDS_CRESCENDO_MIN_INCREASES", "1"))
CRESCENDO_MIN_FINAL_SCORE = int(os.getenv("IDS_CRESCENDO_MIN_FINAL_SCORE", "2"))


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
