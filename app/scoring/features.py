import os
import re
from typing import Any, Dict, List, Tuple, Optional

def normalize_text(text: str) -> str:
    t = (text or "").lower()
    # normalize curly quotes/apostrophes/dashes → ascii
    return (
        t.replace("\u2019", "'")
         .replace("\u2018", "'")
         .replace("\u201c", '"')
         .replace("\u201d", '"')
         .replace("\u2014", "-")
         .replace("\u2013", "-")
    )

# -----------------------------
# Tunables (env vars)
# -----------------------------
REFUSAL_PATTERNS = [
    r"\bi can'?t\b",
    r"\bi cannot\b",
    r"\bi'?m sorry\b",
    r"\bi won'?t\b",
    r"\bcan'?t help\b",
    r"\bnot able to\b",
    r"\bcan'?t do that\b",
]

DEFAULT_SENSITIVE_KEYWORDS = [
    "system prompt",
    "hidden prompt",
    "bypass",
    "exploit",
    "jailbreak",
    "override",
    "ignore instructions",
    "reveal instructions",
]

KEYWORDS = os.getenv("IDS_CRESCENDO_KEYWORDS")
SENSITIVE_KEYWORDS = (
    [k.strip().lower() for k in KEYWORDS.split(",")] if KEYWORDS else DEFAULT_SENSITIVE_KEYWORDS
)

REPHRASE_SIM_THRESHOLD = float(os.getenv("REFUSAL_SIM_THRESHOLD", "0.35"))
REPHRASE_WINDOW_TURNS = int(os.getenv("REFUSAL_WINDOW_TURNS", "2"))


# -----------------------------
# Text helpers
# -----------------------------
def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9']+", normalize_text(text))


def jaccard(a: str, b: str) -> float:
    wa = set(_tokens(a))
    wb = set(_tokens(b))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def keyword_count(text: str) -> int:
    t = normalize_text(text)
    return sum(1 for k in SENSITIVE_KEYWORDS if k in t)


def is_refusal(text: str) -> bool:
    t = normalize_text(text)
    return any(re.search(p, t) for p in REFUSAL_PATTERNS)


# -----------------------------
# Event grouping
# -----------------------------
def group_by_turn(events: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    by_turn: Dict[int, List[Dict[str, Any]]] = {}
    for e in events:
        by_turn.setdefault(int(e["turn_id"]), []).append(e)
    # Ensure stable ordering inside each turn
    for t in by_turn:
        by_turn[t] = sorted(by_turn[t], key=lambda x: int(x.get("id", 0)))
    return by_turn


def _last_user_before(by_turn: Dict[int, List[Dict[str, Any]]], turn_id: int) -> Optional[Tuple[int, str]]:
    for t in sorted([k for k in by_turn.keys() if k < turn_id], reverse=True):
        umsgs = [e for e in by_turn[t] if e.get("role") == "user"]
        if umsgs:
            return t, umsgs[-1].get("content", "")
    return None


def _next_user_after(by_turn: Dict[int, List[Dict[str, Any]]], turn_id: int) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for t in sorted([k for k in by_turn.keys() if k > turn_id]):
        umsgs = [e for e in by_turn[t] if e.get("role") == "user"]
        if umsgs:
            out.append((t, umsgs[-1].get("content", "")))
    return out


# -----------------------------
# Feature extraction
# -----------------------------
def compute_session_features(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Returns explainable, deterministic features for the whole session.
    """
    by_turn = group_by_turn(events)
    turn_ids = sorted(by_turn.keys())

    user_turns = 0
    assistant_turns = 0
    user_msgs = 0
    assistant_msgs = 0

    refusal_turn_ids: List[int] = []
    total_sensitive_kw = 0

    # Basic counts + refusal turns + keyword totals
    for t in turn_ids:
        for e in by_turn[t]:
            role = e.get("role")
            if role == "user":
                user_msgs += 1
            elif role == "assistant":
                assistant_msgs += 1

            total_sensitive_kw += keyword_count(e.get("content", ""))

        if any(e.get("role") == "user" for e in by_turn[t]):
            user_turns += 1
        if any(e.get("role") == "assistant" for e in by_turn[t]):
            assistant_turns += 1

        # refusal if any assistant msg in this turn looks like a refusal
        if any(e.get("role") == "assistant" and is_refusal(e.get("content", "")) for e in by_turn[t]):
            refusal_turn_ids.append(t)

    # Rephrase-after-refusal detection (feature-level)
    rephrase_hits: List[Dict[str, Any]] = []
    for refusal_turn in refusal_turn_ids:
        prev_user = _last_user_before(by_turn, refusal_turn)
        if not prev_user:
            continue
        prev_user_turn, prev_user_text = prev_user

        checked = 0
        for next_turn, next_user_text in _next_user_after(by_turn, refusal_turn):
            sim = jaccard(prev_user_text, next_user_text)
            checked += 1
            if sim >= REPHRASE_SIM_THRESHOLD:
                rephrase_hits.append({
                    "original_turn": prev_user_turn,
                    "refusal_turn": refusal_turn,
                    "rephrase_turn": next_turn,
                    "similarity": round(sim, 3),
                })
                break
            if checked >= REPHRASE_WINDOW_TURNS:
                break

    # Crescendo-like “growth”: keyword_count per user turn and monotonic increases
    user_progression: List[Tuple[int, int]] = []
    for t in turn_ids:
        umsgs = [e for e in by_turn[t] if e.get("role") == "user"]
        if not umsgs:
            continue
        # score this turn by last user msg (simple, deterministic)
        user_progression.append((t, keyword_count(umsgs[-1].get("content", ""))))

    increases: List[int] = []
    if user_progression:
        prev = user_progression[0][1]
        for t, s in user_progression[1:]:
            if s > prev:
                increases.append(t)
            prev = s

    return {
        "turn_count": len(turn_ids),
        "user_turn_count": user_turns,
        "assistant_turn_count": assistant_turns,
        "user_message_count": user_msgs,
        "assistant_message_count": assistant_msgs,
        "refusal_count": len(refusal_turn_ids),
        "refusal_turn_ids": refusal_turn_ids,
        "rephrase_count": len(rephrase_hits),
        "rephrase_hits": rephrase_hits,  # evidence-ready
        "sensitive_keyword_total": total_sensitive_kw,
        "user_keyword_progression": user_progression,
        "user_keyword_increase_turns": increases,
    }


def compute_turn_features(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Returns per-turn features to support timeline explainability.
    """
    by_turn = group_by_turn(events)
    out: List[Dict[str, Any]] = []

    for t in sorted(by_turn.keys()):
        turn_events = by_turn[t]
        user_texts = [e.get("content", "") for e in turn_events if e.get("role") == "user"]
        assistant_texts = [e.get("content", "") for e in turn_events if e.get("role") == "assistant"]

        out.append({
            "turn_id": t,
            "has_user": bool(user_texts),
            "has_assistant": bool(assistant_texts),
            "user_sensitive_kw": keyword_count(user_texts[-1]) if user_texts else 0,
            "assistant_refusal": any(is_refusal(x) for x in assistant_texts),
            "events": turn_events,
        })

    return out
