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


def _parse_bool(value: str) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


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
    parser.add_argument(
        "--expect-query-token-enabled",
        default="true",
        help=(
            "Expected query-token auth behavior for protected endpoints "
            "(true/false). Use false when DASHBOARD_QUERY_TOKEN_ENABLED=false."
        ),
    )
    args = parser.parse_args()
    try:
        expect_query_token_enabled = _parse_bool(args.expect_query_token_enabled)
    except ValueError as exc:
        raise SystemExit(str(exc))

    staging = run_full_smoke(
        args.staging_url,
        args.staging_token,
        timeout_seconds=args.timeout_seconds,
        refresh_wait_seconds=args.refresh_wait_seconds,
        expect_query_token_enabled=expect_query_token_enabled,
    )
    production = run_full_smoke(
        args.production_url,
        args.production_token,
        timeout_seconds=args.timeout_seconds,
        refresh_wait_seconds=args.refresh_wait_seconds,
        expect_query_token_enabled=expect_query_token_enabled,
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
