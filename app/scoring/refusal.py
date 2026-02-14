import re
from typing import List, Dict, Any, Tuple

REFUSAL_PATTERNS = [
    r"\bi can'?t\b",
    r"\bi cannot\b",
    r"\bi'?m sorry\b",
    r"\bi won'?t\b",
    r"\bcan'?t help\b",
    r"\bnot able to\b",
    r"\bcan'?t do that\b",
]

def is_refusal(text: str) -> bool:
    t = (text or "").lower()
    return any(re.search(p, t) for p in REFUSAL_PATTERNS)

def token_jaccard(a: str, b: str) -> float:
    wa = set(re.findall(r"[a-z0-9']+", (a or "").lower()))
    wb = set(re.findall(r"[a-z0-9']+", (b or "").lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)

def detect_refusal_rephrase(
    events: List[Dict[str, Any]],
    window_turns: int = 2,
    sim_threshold: float = 0.35
) -> Tuple[bool, Dict[str, Any]]:

    by_turn = {}
    for e in events:
        by_turn.setdefault(e["turn_id"], []).append(e)

    turn_ids = sorted(by_turn.keys())
    for t in turn_ids:
        assistant_msgs = [e for e in by_turn[t] if e["role"] == "assistant"]
        if not assistant_msgs:
            continue
        if not any(is_refusal(m["content"]) for m in assistant_msgs):
            continue

        prev_user = None
        prev_user_turn = None
        for pt in reversed([x for x in turn_ids if x < t]):
            umsgs = [e for e in by_turn[pt] if e["role"] == "user"]
            if umsgs:
                prev_user = umsgs[-1]["content"]
                prev_user_turn = pt
                break
        if not prev_user:
            continue

        checked = 0
        for ft in [x for x in turn_ids if x > t]:
            umsgs = [e for e in by_turn[ft] if e["role"] == "user"]
            if not umsgs:
                continue
            checked += 1
            sim = token_jaccard(prev_user, umsgs[-1]["content"])
            if sim >= sim_threshold:
                return True, {
                    "reason": "REFUSAL_EVASION_LOOP",
                    "original_turn": prev_user_turn,
                    "refusal_turn": t,
                    "rephrase_turn": ft,
                    "similarity": round(sim, 3),
                }
            if checked >= window_turns:
                break

    return False, {}
