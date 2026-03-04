#!/usr/bin/env python3
"""
Inspect captured HeyReach webhook payloads to validate HR-05 schema evidence.

Usage:
  python scripts/inspect_heyreach_payloads.py
  python scripts/inspect_heyreach_payloads.py --path .hive-mind/heyreach_events.jsonl --print-sample
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _is_real_schema_payload(payload: Dict[str, Any]) -> bool:
    """Heuristic for real HeyReach webhook shape (vs synthetic UNKNOWN probes)."""
    if not isinstance(payload, dict):
        return False
    has_event = bool(payload.get("event_type") or payload.get("eventType"))
    has_lead = isinstance(payload.get("lead"), dict)
    has_campaign = isinstance(payload.get("campaign"), dict)
    has_sender = isinstance(payload.get("sender"), dict)
    return has_event and (has_lead or has_campaign or has_sender)


def analyze_events(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    normalized: List[Dict[str, Any]] = [e for e in events if isinstance(e, dict)]
    total = len(normalized)
    real_schema_events = 0
    event_type_counts: Counter[str] = Counter()
    top_level_keys: Counter[str] = Counter()

    for record in normalized:
        event_type = str(record.get("event_type") or "UNKNOWN")
        event_type_counts[event_type] += 1
        payload = record.get("payload") or {}
        if isinstance(payload, dict):
            top_level_keys.update(payload.keys())
            if _is_real_schema_payload(payload):
                real_schema_events += 1

    unknown_only_events = total - real_schema_events
    return {
        "total_events": total,
        "real_schema_events": real_schema_events,
        "unknown_only_events": unknown_only_events,
        "has_real_schema_payloads": real_schema_events > 0,
        "event_type_counts": dict(event_type_counts),
        "top_payload_keys": dict(top_level_keys),
    }


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    parsed: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            parsed.append(item)
    return parsed


def _first_real_payload(events: Iterable[Dict[str, Any]]) -> Dict[str, Any] | None:
    for record in events:
        payload = record.get("payload") if isinstance(record, dict) else None
        if isinstance(payload, dict) and _is_real_schema_payload(payload):
            return payload
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect captured HeyReach payload schema evidence.")
    parser.add_argument(
        "--path",
        default=".hive-mind/heyreach_events.jsonl",
        help="Path to HeyReach JSONL event log.",
    )
    parser.add_argument(
        "--print-sample",
        action="store_true",
        help="Print one captured real-schema payload sample when available.",
    )
    args = parser.parse_args()

    path = Path(args.path)
    events = _load_jsonl(path)
    summary = analyze_events(events)

    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.print_sample:
        sample = _first_real_payload(events)
        if sample is None:
            print("sample_payload: NONE")
        else:
            print("sample_payload:")
            print(json.dumps(sample, indent=2, sort_keys=True))

    return 0 if summary["has_real_schema_payloads"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

