from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from app.scoring.engine import score_session
from app.scoring.features import compute_turn_features


def _safe_int(x: Any) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None


def build_timeline(
    events: List[Dict[str, Any]],
    *,
    include_events: bool = True,
    truncate: int = 240,
) -> Dict[str, Any]:
    final = score_session(events)
    turns = compute_turn_features(events)

    evidence = final.get("evidence", {}) or {}
    feats = evidence.get("features", {}) or {}

    refusal_turns: Set[int] = set(
        _safe_int(t) for t in (feats.get("refusal_turn_ids") or []) if _safe_int(t) is not None
    )

    rr = evidence.get("refusal_rephrase", {}) or {}
    rephrase_turns: Set[int] = set()
    rephrase_meta: Dict[int, Any] = {}
    for hit in rr.get("hits", []) or []:
        t = _safe_int(hit.get("rephrase_turn"))
        if t is not None:
            rephrase_turns.add(t)
            rephrase_meta[t] = hit

    cresc = evidence.get("crescendo", {}) or {}
    crescendo_turns: Set[int] = set(
        _safe_int(t) for t in (cresc.get("turns", []) or []) if _safe_int(t) is not None
    )

    vel = evidence.get("risk_velocity", {}) or {}
    spike_turn = _safe_int(vel.get("spike_turn"))

    dpa = evidence.get("direct_prompt_attack", {}) or {}

    # annotate turns
    for t in turns:
        tid = int(t["turn_id"])
        highlights: List[Dict[str, Any]] = []

        if tid in refusal_turns:
            highlights.append({"type": "refusal", "title": "Assistant refusal detected"})

        if tid in rephrase_turns:
            sim = (rephrase_meta.get(tid) or {}).get("similarity")
            highlights.append(
                {
                    "type": "rephrase",
                    "title": "User rephrased after refusal",
                    "detail": f"similarity={sim}" if sim is not None else None,
                }
            )

        if tid in crescendo_turns:
            highlights.append({"type": "crescendo", "title": "Escalation across turns"})

        if spike_turn is not None and tid == spike_turn:
            highlights.append(
                {"type": "velocity", "title": "Velocity spike", "detail": f"delta={vel.get('spike_delta')}"}
            )

        kw = int(t.get("user_sensitive_kw", 0) or 0)
        if kw > 0:
            highlights.append({"type": "keywords", "title": "Sensitive keywords", "detail": f"count={kw}"})

        t["highlights"] = [h for h in highlights if h.get("detail") is not None or "detail" not in h]

        if include_events:
            for e in t.get("events", []) or []:
                c = e.get("content", "") or ""
                if truncate and len(c) > truncate:
                    e["content"] = c[:truncate] + "…"
        else:
            t.pop("events", None)

    # "wow" summary
    labels = final.get("labels", []) or []
    score = int(final.get("score", 0) or 0)
    severity = final.get("severity", "NONE")

    top_signals: List[str] = []
    if "REFUSAL_REPHRASE" in labels:
        top_signals.append(f"Refusal+rephrase loop (hits={rr.get('hit_count')}).")
    if "CRESCENDO_ATTACK" in labels:
        top_signals.append(f"Crescendo escalation (final_score={cresc.get('final_score')}).")
    if "RISK_VELOCITY" in labels:
        top_signals.append(f"Velocity spike (max_delta={vel.get('max_user_keyword_delta')}).")
    if "DIRECT_PROMPT_ATTACK" in labels:
        top_signals.append(f"Direct prompt attack patterns matched (hits={len(dpa.get('hits', []) or [])}).")

    recommended_action = "allow"
    if severity == "MED":
        recommended_action = "review"
    if severity == "HIGH":
        recommended_action = "block"

    explanation = f"Scored {score} ({severity})."
    if labels:
        explanation += f" Triggered: {', '.join(labels)}."

    return {
        "final": final,
        "recommended_action": recommended_action,
        "explanation": explanation,
        "top_signals": top_signals[:3],
        "turns": turns,
    }
