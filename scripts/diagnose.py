#!/usr/bin/env python3
"""
Trace diagnosis CLI for CAIO Alpha Swarm.

Aggregates trace events, circuit breaker states, event logs, and health
status for a given case_id or correlation_id. Outputs structured JSON
for debugging pipeline and deployment failures.

Usage:
  python scripts/diagnose.py --case-id <CASE_ID>
  python scripts/diagnose.py --correlation-id <CORR_ID>
  python scripts/diagnose.py --health
  python scripts/diagnose.py --breakers
  python scripts/diagnose.py --recent-errors --limit 20
  python scripts/diagnose.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HIVE_MIND = PROJECT_ROOT / ".hive-mind"

# Data source paths
EVENTS_FILE = HIVE_MIND / "events.jsonl"
TRACES_FILE = HIVE_MIND / "traces" / "tool_trace_envelopes.jsonl"
BREAKERS_FILE = HIVE_MIND / "circuit_breakers.json"
RETRY_QUEUE = HIVE_MIND / "retry_queue.jsonl"


def _read_jsonl(path: Path, limit: int = 500) -> List[Dict[str, Any]]:
    """Read JSONL file, returning last `limit` entries."""
    if not path.exists():
        return []
    entries = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []
    return entries[-limit:]


def _read_json(path: Path) -> Dict[str, Any]:
    """Read a JSON file."""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.loads(f.read())
    except Exception:
        return {}


def _filter_by_id(
    entries: List[Dict[str, Any]],
    key: str,
    value: str,
) -> List[Dict[str, Any]]:
    """Filter entries where entry[key] matches value."""
    return [e for e in entries if e.get(key) == value]


def diagnose_case(case_id: str) -> Dict[str, Any]:
    """Aggregate all data for a given case_id."""
    result: Dict[str, Any] = {
        "case_id": case_id,
        "diagnosed_at": datetime.now(timezone.utc).isoformat(),
        "traces": [],
        "events": [],
        "retry_queue_entries": [],
        "circuit_breakers": _read_json(BREAKERS_FILE),
    }

    # Search traces
    traces = _read_jsonl(TRACES_FILE)
    result["traces"] = _filter_by_id(traces, "case_id", case_id)

    # If we found traces, extract correlation_ids to search events
    corr_ids = {t.get("correlation_id") for t in result["traces"] if t.get("correlation_id")}

    # Search events
    events = _read_jsonl(EVENTS_FILE)
    for event in events:
        meta = event.get("metadata") or {}
        if meta.get("case_id") == case_id or meta.get("correlation_id") in corr_ids:
            result["events"].append(event)

    # Search retry queue
    retries = _read_jsonl(RETRY_QUEUE)
    for entry in retries:
        if entry.get("case_id") == case_id or entry.get("correlation_id") in corr_ids:
            result["retry_queue_entries"].append(entry)

    # Summary
    result["summary"] = {
        "trace_count": len(result["traces"]),
        "event_count": len(result["events"]),
        "retry_count": len(result["retry_queue_entries"]),
        "agents_involved": list({t.get("agent", "unknown") for t in result["traces"]}),
        "statuses": list({t.get("status", "unknown") for t in result["traces"]}),
        "errors": [
            {"agent": t.get("agent"), "error_code": t.get("error_code"), "error_message": t.get("error_message")}
            for t in result["traces"]
            if t.get("status") == "failure" or t.get("error_code")
        ],
    }

    return result


def diagnose_correlation(correlation_id: str) -> Dict[str, Any]:
    """Aggregate all data for a given correlation_id."""
    result: Dict[str, Any] = {
        "correlation_id": correlation_id,
        "diagnosed_at": datetime.now(timezone.utc).isoformat(),
        "traces": [],
        "events": [],
        "retry_queue_entries": [],
        "circuit_breakers": _read_json(BREAKERS_FILE),
    }

    traces = _read_jsonl(TRACES_FILE)
    result["traces"] = _filter_by_id(traces, "correlation_id", correlation_id)

    events = _read_jsonl(EVENTS_FILE)
    for event in events:
        meta = event.get("metadata") or {}
        if meta.get("correlation_id") == correlation_id:
            result["events"].append(event)

    retries = _read_jsonl(RETRY_QUEUE)
    result["retry_queue_entries"] = _filter_by_id(retries, "correlation_id", correlation_id)

    result["summary"] = {
        "trace_count": len(result["traces"]),
        "event_count": len(result["events"]),
        "retry_count": len(result["retry_queue_entries"]),
        "agents_involved": list({t.get("agent", "unknown") for t in result["traces"]}),
        "statuses": list({t.get("status", "unknown") for t in result["traces"]}),
        "errors": [
            {"agent": t.get("agent"), "error_code": t.get("error_code"), "error_message": t.get("error_message")}
            for t in result["traces"]
            if t.get("status") == "failure" or t.get("error_code")
        ],
    }

    return result


def get_breaker_status() -> Dict[str, Any]:
    """Get all circuit breaker states."""
    return {
        "diagnosed_at": datetime.now(timezone.utc).isoformat(),
        "circuit_breakers": _read_json(BREAKERS_FILE),
    }


def get_recent_errors(limit: int = 20) -> Dict[str, Any]:
    """Get recent errors from traces and events."""
    traces = _read_jsonl(TRACES_FILE)
    error_traces = [t for t in traces if t.get("status") == "failure" or t.get("error_code")]

    events = _read_jsonl(EVENTS_FILE)
    error_events = [e for e in events if e.get("event_type") in ("system_error", "compliance_failed", "enrichment_failed", "scrape_failed")]

    retries = _read_jsonl(RETRY_QUEUE, limit=limit)

    return {
        "diagnosed_at": datetime.now(timezone.utc).isoformat(),
        "recent_trace_errors": error_traces[-limit:],
        "recent_event_errors": error_events[-limit:],
        "retry_queue": retries[-limit:],
        "summary": {
            "trace_errors": len(error_traces),
            "event_errors": len(error_events),
            "retry_pending": len(retries),
        },
    }


def get_health_summary() -> Dict[str, Any]:
    """Get local health summary from available data."""
    breakers = _read_json(BREAKERS_FILE)
    events = _read_jsonl(EVENTS_FILE, limit=100)
    traces = _read_jsonl(TRACES_FILE, limit=100)

    # Count recent statuses
    trace_statuses: Dict[str, int] = {}
    for t in traces:
        s = t.get("status", "unknown")
        trace_statuses[s] = trace_statuses.get(s, 0) + 1

    event_types: Dict[str, int] = {}
    for e in events:
        et = e.get("event_type", "unknown")
        event_types[et] = event_types.get(et, 0) + 1

    # Check for open breakers
    open_breakers = [
        name for name, state in breakers.items()
        if isinstance(state, dict) and state.get("state") in ("open", "OPEN")
    ]

    return {
        "diagnosed_at": datetime.now(timezone.utc).isoformat(),
        "data_sources": {
            "events_file": str(EVENTS_FILE.relative_to(PROJECT_ROOT)),
            "events_exists": EVENTS_FILE.exists(),
            "traces_file": str(TRACES_FILE.relative_to(PROJECT_ROOT)),
            "traces_exists": TRACES_FILE.exists(),
            "breakers_file": str(BREAKERS_FILE.relative_to(PROJECT_ROOT)),
            "breakers_exists": BREAKERS_FILE.exists(),
        },
        "circuit_breakers": {
            "total": len(breakers),
            "open": open_breakers,
            "all_closed": len(open_breakers) == 0,
        },
        "recent_traces": {
            "count": len(traces),
            "statuses": trace_statuses,
        },
        "recent_events": {
            "count": len(events),
            "types": event_types,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose pipeline/deployment failures using trace correlation."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--case-id", help="Case ID to trace.")
    group.add_argument("--correlation-id", help="Correlation ID to trace.")
    group.add_argument("--health", action="store_true", help="Show local health summary.")
    group.add_argument("--breakers", action="store_true", help="Show circuit breaker states.")
    group.add_argument("--recent-errors", action="store_true", help="Show recent errors.")
    parser.add_argument("--limit", type=int, default=20, help="Max entries for recent-errors.")
    parser.add_argument("--json", action="store_true", help="Output raw JSON (default: formatted).")
    args = parser.parse_args()

    if args.case_id:
        result = diagnose_case(args.case_id)
    elif args.correlation_id:
        result = diagnose_correlation(args.correlation_id)
    elif args.breakers:
        result = get_breaker_status()
    elif args.recent_errors:
        result = get_recent_errors(limit=args.limit)
    else:
        result = get_health_summary()

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        # Human-readable output
        print(json.dumps(result, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
