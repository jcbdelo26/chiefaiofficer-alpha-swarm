#!/usr/bin/env python3
"""
Cleanup non-actionable pending approvals from deployed dashboard.

Rules:
  - Placeholder body ("No Body Content" / empty)
  - Older than max age hours (default 72h)
  - Tier mismatch during active ramp (tier_filter from /api/operator/status)

Usage:
  python scripts/cleanup_pending_queue.py \
    --base-url https://caio-swarm-dashboard-production.up.railway.app \
    --token <DASHBOARD_AUTH_TOKEN> \
    --apply
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _is_placeholder_body(value: Any) -> bool:
    body = str(value or "").strip().lower()
    return body in {"", "no body content"}


def _reasons_for_item(
    item: Dict[str, Any],
    *,
    now_utc: datetime,
    max_age_hours: float,
    ramp_tier: Optional[str],
) -> List[str]:
    reasons: List[str] = []
    body = item.get("body") or item.get("body_preview")
    if _is_placeholder_body(body):
        reasons.append("placeholder_body")

    ts = _parse_dt(item.get("timestamp") or item.get("created_at"))
    if ts and ts < (now_utc - timedelta(hours=max_age_hours)):
        reasons.append(f"stale_gt_{int(max_age_hours)}h")

    tier = str(item.get("tier") or "").strip().lower()
    if ramp_tier and tier and tier != ramp_tier:
        reasons.append(f"ramp_tier_mismatch:{tier}!={ramp_tier}")

    return reasons


def _api_get(base_url: str, path: str, token: str) -> Dict[str, Any]:
    resp = requests.get(
        f"{base_url.rstrip('/')}{path}",
        params={"token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup non-actionable pending queue items.")
    parser.add_argument("--base-url", required=True, help="Dashboard base URL.")
    parser.add_argument("--token", required=True, help="Dashboard auth token.")
    parser.add_argument("--max-age-hours", type=float, default=72.0, help="Max pending age before cleanup.")
    parser.add_argument("--apply", action="store_true", help="Apply cleanup (default is dry-run).")
    args = parser.parse_args()

    status = _api_get(args.base_url, "/api/operator/status", args.token)
    ramp = status.get("ramp", {})
    ramp_tier = str(ramp.get("tier_filter") or "").strip().lower() if ramp.get("active") else None

    payload = _api_get(args.base_url, "/api/pending-emails", args.token)
    pending = payload.get("pending_emails", [])

    now_utc = datetime.now(timezone.utc)
    candidates: List[Dict[str, Any]] = []
    for item in pending:
        reasons = _reasons_for_item(
            item,
            now_utc=now_utc,
            max_age_hours=args.max_age_hours,
            ramp_tier=ramp_tier,
        )
        if not reasons:
            continue
        candidates.append(
            {
                "email_id": item.get("email_id") or item.get("id"),
                "to": item.get("to"),
                "tier": item.get("tier"),
                "subject": item.get("subject"),
                "timestamp": item.get("timestamp") or item.get("created_at"),
                "reasons": reasons,
            }
        )

    print(f"ramp_tier={ramp_tier or 'none'}")
    print(f"visible_pending={len(pending)}")
    print(f"cleanup_candidates={len(candidates)}")

    for row in candidates:
        print(f"- {row['email_id']} [{row['tier']}] {row['to']} -> {', '.join(row['reasons'])}")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to reject candidates.")
        return 0

    rejected = 0
    for row in candidates:
        email_id = row["email_id"]
        reason = f"Auto-cleanup non-actionable pending item: {', '.join(row['reasons'])}"
        resp = requests.post(
            f"{args.base_url.rstrip('/')}/api/emails/{email_id}/reject",
            params={
                "token": args.token,
                "approver": "queue_hygiene_bot",
                "reason": reason,
                "rejection_tag": "queue_hygiene_non_actionable",
            },
            timeout=30,
        )
        if resp.status_code == 200:
            rejected += 1
            continue
        print(f"  ! reject failed for {email_id}: {resp.status_code} {resp.text[:200]}")

    print(f"\nrejected={rejected}/{len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
