from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.scoring.engine import score_session
from app.router.policy import route_decision


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl_events(path: Path, session_id: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        # Ensure the minimal event fields exist
        obj.setdefault("session_id", session_id)
        obj.setdefault("ts", None)
        obj.setdefault("model", None)
        events.append(obj)
    return events


def check_case(case: Dict[str, Any]) -> Tuple[bool, str]:
    name = case["name"]
    path = Path(case["path"])
    session_id = case.get("session_id", f"ci_{name}")

    events = load_jsonl_events(path, session_id=session_id)

    score_res = score_session(events)
    route_res = route_decision(session_id, score_res)

    exp = case.get("expect", {})
    problems: List[str] = []

    # Expectations (all optional)
    if "decision" in exp:
        if route_res.get("decision") != exp["decision"]:
            problems.append(f"decision={route_res.get('decision')} != {exp['decision']}")

    if "severity" in exp:
        if route_res.get("severity") != exp["severity"]:
            problems.append(f"severity={route_res.get('severity')} != {exp['severity']}")

    if "min_score" in exp:
        if int(route_res.get("score", 0)) < int(exp["min_score"]):
            problems.append(f"score={route_res.get('score')} < min_score={exp['min_score']}")

    if "labels_include" in exp:
        got = set(route_res.get("labels", []) or [])
        want = set(exp["labels_include"] or [])
        missing = sorted(list(want - got))
        if missing:
            problems.append(f"missing labels: {missing}")

    ok = len(problems) == 0
    summary = (
        f"{name}: ok (decision={route_res.get('decision')}, severity={route_res.get('severity')}, score={route_res.get('score')})"
        if ok
        else f"{name}: FAIL -> " + "; ".join(problems)
    )
    return ok, summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True, help="Path to regression cases JSON")
    args = ap.parse_args()

    cases_path = Path(args.cases)
    cases = load_json(cases_path)

    all_ok = True
    for case in cases["cases"]:
        ok, msg = check_case(case)
        print(msg)
        all_ok = all_ok and ok

    if not all_ok:
        print("\n❌ Safety regression suite failed.")
        return 1

    print("\n✅ Safety regression suite passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
