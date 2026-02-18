#!/usr/bin/env python3
"""
Run full deployed smoke checklist across staging + production.

Usage:
  python scripts/deployed_full_smoke_matrix.py \
    --staging-url "https://<staging-domain>" \
    --staging-token "<STAGING_DASHBOARD_AUTH_TOKEN>" \
    --production-url "https://<production-domain>" \
    --production-token "<PRODUCTION_DASHBOARD_AUTH_TOKEN>"
"""

from __future__ import annotations

import argparse
import json

from deployed_full_smoke_checklist import run_full_smoke


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run full deployed smoke checklist for staging and production."
    )
    parser.add_argument("--staging-url", required=True, help="Staging dashboard base URL.")
    parser.add_argument("--staging-token", required=True, help="Staging dashboard auth token.")
    parser.add_argument("--production-url", required=True, help="Production dashboard base URL.")
    parser.add_argument("--production-token", required=True, help="Production dashboard auth token.")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=20,
        help="HTTP timeout per request.",
    )
    parser.add_argument(
        "--refresh-wait-seconds",
        type=int,
        default=3,
        help="Wait between pending-emails polls.",
    )
    args = parser.parse_args()

    staging = run_full_smoke(
        args.staging_url,
        args.staging_token,
        timeout_seconds=args.timeout_seconds,
        refresh_wait_seconds=args.refresh_wait_seconds,
    )
    production = run_full_smoke(
        args.production_url,
        args.production_token,
        timeout_seconds=args.timeout_seconds,
        refresh_wait_seconds=args.refresh_wait_seconds,
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
