from typing import Dict, Any, List
from app.scoring.engine import score_session

def build_timeline(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Builds a per-turn timeline and a simple risk progression.
    We score the session incrementally turn-by-turn.
    """
    # Group events by turn_id (already ordered in DB, but be safe)
    by_turn: Dict[int, List[Dict[str, Any]]] = {}
    for e in events:
        by_turn.setdefault(int(e["turn_id"]), []).append(e)

    turn_ids = sorted(by_turn.keys())

    # Build a flat, ordered event list up to each turn for incremental scoring
    ordered_events: List[Dict[str, Any]] = []
    risk_points: List[Dict[str, Any]] = []
    turns: List[Dict[str, Any]] = []

    for t in turn_ids:
        # Add this turn’s events to the running history
        for e in sorted(by_turn[t], key=lambda x: int(x["id"])):
            ordered_events.append(e)

        # Score up to this turn
        result = score_session(ordered_events)

        risk_points.append({
            "turn_id": t,
            "score": result["score"],
            "severity": result["severity"],
            "labels": result["labels"],
        })

        turns.append({
            "turn_id": t,
            "events": by_turn[t],
        })

    # Last score = current session score
    final = score_session(ordered_events) if ordered_events else {
        "score": 0, "severity": "NONE", "labels": [], "reasons": [], "evidence": {}
    }

    return {
        "final": final,
        "risk_points": risk_points,
        "turns": turns,
    }
