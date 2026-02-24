#!/usr/bin/env python3
"""
Run webhook strict-mode smoke checks across staging + production.

Usage:
  python scripts/webhook_strict_smoke_matrix.py \
    --staging-url "https://<staging-domain>" \
    --staging-dashboard-token "<STAGING_DASHBOARD_AUTH_TOKEN>" \
    --staging-webhook-required true \
    --production-url "https://<production-domain>" \
    --production-dashboard-token "<PRODUCTION_DASHBOARD_AUTH_TOKEN>" \
    --production-webhook-required false
"""

from __future__ import annotations

import argparse
import json

from webhook_strict_smoke import run_webhook_strict_smoke


def _to_bool(value: str) -> bool:
    v = (value or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run webhook strict-mode smoke checks for staging and production."
    )
    parser.add_argument("--staging-url", required=True, help="Staging dashboard base URL.")
    parser.add_argument("--staging-dashboard-token", required=True, help="Staging dashboard auth token.")
    parser.add_argument(
        "--staging-webhook-required",
        default="true",
        help="Expected staging runtime.dependencies.webhooks.required value (true/false).",
    )
    parser.add_argument(
        "--staging-webhook-bearer-token",
        default="",
        help="Optional staging webhook bearer token.",
    )

    parser.add_argument("--production-url", required=True, help="Production dashboard base URL.")
    parser.add_argument("--production-dashboard-token", required=True, help="Production dashboard auth token.")
    parser.add_argument(
        "--production-webhook-required",
        default="true",
        help="Expected production runtime.dependencies.webhooks.required value (true/false).",
    )
    parser.add_argument(
        "--production-webhook-bearer-token",
        default="",
        help="Optional production webhook bearer token.",
    )

    parser.add_argument(
        "--require-heyreach-hard-auth",
        action="store_true",
        help="Fail if HeyReach accepts unsigned requests.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=20, help="HTTP timeout per request.")
    args = parser.parse_args()

    staging = run_webhook_strict_smoke(
        base_url=args.staging_url,
        dashboard_token=args.staging_dashboard_token,
        expect_webhook_required=_to_bool(args.staging_webhook_required),
        webhook_bearer_token=(args.staging_webhook_bearer_token or "").strip() or None,
        require_heyreach_hard_auth=bool(args.require_heyreach_hard_auth),
        timeout_seconds=args.timeout_seconds,
    )
    production = run_webhook_strict_smoke(
        base_url=args.production_url,
        dashboard_token=args.production_dashboard_token,
        expect_webhook_required=_to_bool(args.production_webhook_required),
        webhook_bearer_token=(args.production_webhook_bearer_token or "").strip() or None,
        require_heyreach_hard_auth=bool(args.require_heyreach_hard_auth),
        timeout_seconds=args.timeout_seconds,
    )

    summary = {
        "passed": bool(staging.get("passed")) and bool(production.get("passed")),
        "environments": {
            "staging": staging,
            "production": production,
        },
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

