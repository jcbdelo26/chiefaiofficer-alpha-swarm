#!/usr/bin/env python3
"""
Trace pending approval cards routed to GHL and report live-send readiness.

This script clarifies that dashboard "Campaign: t1_xxx (camp_...)" fields are
internal pipeline identifiers, not native GHL campaign IDs.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

import requests


def _api_get(
    base_url: str,
    path: str,
    token: str,
    *,
    include_non_dispatchable: bool = False,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {"token": token}
    if include_non_dispatchable:
        params["include_non_dispatchable"] = "true"
    response = requests.get(
        f"{base_url.rstrip('/')}{path}",
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _sendability_reason(item: Dict[str, Any]) -> str:
    classifier = item.get("classifier", {}) if isinstance(item.get("classifier"), dict) else {}
    target_platform = str(classifier.get("target_platform") or "").strip().lower()
    if target_platform and target_platform != "ghl":
        return f"n/a_target_platform:{target_platform}"

    if bool(item.get("synthetic")):
        return "blocked_synthetic"

    contact_id = item.get("contact_id")
    if not contact_id:
        to_email = str(item.get("to") or "").strip()
        if to_email:
            return "auto_resolve_on_approve"
        return "blocked_missing_contact_id"

    return "ready_for_live_send"


def _compact_row(item: Dict[str, Any]) -> Dict[str, Any]:
    context = item.get("context", {}) if isinstance(item.get("context"), dict) else {}
    campaign_ref = item.get("campaign_ref", {}) if isinstance(item.get("campaign_ref"), dict) else {}
    classifier = item.get("classifier", {}) if isinstance(item.get("classifier"), dict) else {}

    return {
        "email_id": item.get("email_id"),
        "to": item.get("to"),
        "subject": item.get("subject"),
        "tier": item.get("tier"),
        "campaign_type": campaign_ref.get("internal_type") or context.get("campaign_type"),
        "campaign_id": campaign_ref.get("internal_id") or context.get("campaign_id"),
        "pipeline_run_id": campaign_ref.get("pipeline_run_id") or context.get("pipeline_run_id"),
        "queue_origin": classifier.get("queue_origin"),
        "target_platform": classifier.get("target_platform"),
        "sync_state": classifier.get("sync_state"),
        "contact_id": item.get("contact_id"),
        "synthetic": bool(item.get("synthetic")),
        "sendability": _sendability_reason(item),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Trace outbound GHL pending approvals.")
    parser.add_argument("--base-url", required=True, help="Dashboard base URL (https://...)")
    parser.add_argument("--token", required=True, help="Dashboard auth token")
    parser.add_argument("--limit", type=int, default=20, help="Max rows to print")
    parser.add_argument(
        "--include-non-dispatchable",
        action="store_true",
        help="Include canary/training cards marked as non-dispatchable.",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    payload = _api_get(
        args.base_url,
        "/api/pending-emails",
        args.token,
        include_non_dispatchable=args.include_non_dispatchable,
    )
    pending = payload.get("pending_emails", [])
    rows: List[Dict[str, Any]] = [_compact_row(item) for item in pending]

    summary = {
        "base_url": args.base_url.rstrip("/"),
        "total_pending": len(rows),
        "ghl_targeted": sum(1 for r in rows if r.get("target_platform") == "ghl"),
        "ready_for_live_send": sum(1 for r in rows if r.get("sendability") == "ready_for_live_send"),
        "auto_resolve_on_approve": sum(1 for r in rows if r.get("sendability") == "auto_resolve_on_approve"),
        "blocked_missing_contact_id": sum(1 for r in rows if r.get("sendability") == "blocked_missing_contact_id"),
        "blocked_synthetic": sum(1 for r in rows if r.get("sendability") == "blocked_synthetic"),
        "include_non_dispatchable": bool(args.include_non_dispatchable),
        "note": "campaign_id is internal CAIO pipeline grouping id; GHL send is direct message on approval (with auto contact upsert when needed).",
    }

    report = {
        "summary": summary,
        "rows": rows[: max(args.limit, 0)],
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("Outbound GHL Pending Trace")
    print("=" * 80)
    for key, value in summary.items():
        print(f"{key}: {value}")
    print("-" * 80)
    for row in report["rows"]:
        print(
            f"{row['email_id']} | {row['to']} | {row['campaign_type']} ({row['campaign_id']}) "
            f"| platform={row['target_platform']} | sendability={row['sendability']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
