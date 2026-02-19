from typing import Dict, Any, List, Set

from app.scoring.engine import score_session
from app.scoring.features import group_by_turn


def build_timeline(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_turn = group_by_turn(events)
    turn_ids = sorted(by_turn.keys())

    ordered_events: List[Dict[str, Any]] = []
    risk_points: List[Dict[str, Any]] = []
    turns: List[Dict[str, Any]] = []

    prev_score = 0
    prev_labels: Set[str] = set()
    prev_reasons: Set[str] = set()

    for t in turn_ids:
        # Add this turn’s events to the running history
        for e in by_turn[t]:
            ordered_events.append(e)

        result = score_session(ordered_events)

        labels = result.get("labels", []) or []
        reasons = result.get("reasons", []) or []

        label_set = set(labels)
        reason_set = set(reasons)

        new_labels = sorted(list(label_set - prev_labels))
        new_reasons = sorted(list(reason_set - prev_reasons))

        score = int(result.get("score", 0) or 0)
        score_delta = score - prev_score

        # Very small “SOC-ish” summary
        top_reason = new_reasons[0] if new_reasons else (reasons[0] if reasons else "")

        risk_points.append({
            "turn_id": t,
            "score": score,
            "score_delta": score_delta,
            "severity": result.get("severity", "NONE"),
            "labels": labels,
            "new_labels": new_labels,
            "reasons": reasons,
            "new_reasons": new_reasons,
            "top_reason": top_reason,
        })

        turns.append({
            "turn_id": t,
            "events": by_turn[t],
        })

        prev_score = score
        prev_labels = label_set
        prev_reasons = reason_set

    final = score_session(ordered_events) if ordered_events else {
        "score": 0, "severity": "NONE", "labels": [], "reasons": [], "evidence": {}
    }

    return {
        "final": final,
        "risk_points": risk_points,
        "turns": turns,
    }
