import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import requests


def post_event(base_url: str, evt: Dict[str, Any]) -> None:
    r = requests.post(f"{base_url}/v1/events", json=evt, timeout=10)
    r.raise_for_status()


def get_json(base_url: str, path: str) -> Dict[str, Any]:
    r = requests.get(f"{base_url}{path}", timeout=10)
    r.raise_for_status()
    return r.json()


def delete_session(base_url: str, session_id: str) -> None:
    r = requests.delete(f"{base_url}/v1/sessions/{session_id}", timeout=10)
    if r.status_code not in (200, 404):
        r.raise_for_status()


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(json.loads(line))
    return events

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--export-timeline", default="")
    ap.add_argument("--wipe", action="store_true")

    # NEW: expectation arguments
    ap.add_argument("--expect-score", type=int)
    ap.add_argument("--expect-severity")
    ap.add_argument("--expect-label", action="append")

    args = ap.parse_args()

    jsonl_path = Path(args.jsonl)
    if not jsonl_path.exists():
        print(f"File not found: {jsonl_path}", file=sys.stderr)
        return 2

    raw = read_jsonl(jsonl_path)

    if args.wipe:
        delete_session(args.base_url, args.session_id)

    # Normalize events
    events: List[Dict[str, Any]] = []
    for i, e in enumerate(raw, start=1):
        evt = dict(e)
        evt["session_id"] = args.session_id
        evt.setdefault("turn_id", i)

        if "role" not in evt or "content" not in evt:
            raise ValueError(f"Missing role/content in line {i}: {evt}")

        events.append(evt)

    # Ingest
    for evt in events:
        post_event(args.base_url, evt)

    # Fetch score
    result = get_json(args.base_url, f"/v1/score/{args.session_id}")

    print(json.dumps(result, indent=2))

    # -------------------------------------------------
    # Assertions (CI-style regression checks)
    # -------------------------------------------------
    failed = False

    if args.expect_score is not None:
        if result.get("score") != args.expect_score:
            print(f"\n❌ Expected score {args.expect_score}, got {result.get('score')}")
            failed = True

    if args.expect_severity is not None:
        if result.get("severity") != args.expect_severity:
            print(f"\n❌ Expected severity {args.expect_severity}, got {result.get('severity')}")
            failed = True

    if args.expect_label:
        labels = set(result.get("labels", []))
        for expected_label in args.expect_label:
            if expected_label not in labels:
                print(f"\n❌ Expected label '{expected_label}' not found in {labels}")
                failed = True

    if failed:
        print("\nReplay assertions FAILED")
        return 1

    # Timeline export
    if args.export_timeline:
        timeline = get_json(args.base_url, f"/v1/timeline/{args.session_id}")
        out = Path(args.export_timeline)
        out.write_text(json.dumps(timeline, indent=2), encoding="utf-8")
        print(f"\nWrote timeline to: {out}")

    print("\nReplay assertions PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
