#!/usr/bin/env python3
"""
Runtime environment validator for CAIO Alpha Swarm.

Usage:
  python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.runtime_reliability import get_runtime_dependency_health, to_bool


@dataclass
class ValidationResult:
    mode: str
    missing_required: List[str]
    present_recommended: List[str]
    missing_recommended: List[str]
    connection_checks: Dict[str, str]

    @property
    def passed(self) -> bool:
        return len(self.missing_required) == 0 and not any(
            status.startswith("FAIL") for status in self.connection_checks.values()
        )


def _required_for_mode(mode: str) -> List[str]:
    base = [
        "ENVIRONMENT",
        "LOG_LEVEL",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
    ]
    if mode in {"staging", "production"}:
        base.extend(
            [
                "GHL_API_KEY",
                "GHL_LOCATION_ID",
                "SUPABASE_URL",
                "SUPABASE_KEY",
                "CLAY_API_KEY",
            ]
        )
    return base


def _recommended_keys() -> List[str]:
    return [
        "REDIS_URL",
        "REDIS_MAX_CONNECTIONS",
        "RATE_LIMIT_REDIS_NAMESPACE",
        "CONTEXT_REDIS_PREFIX",
        "CONTEXT_STATE_TTL_SECONDS",
        "INNGEST_SIGNING_KEY",
        "INNGEST_EVENT_KEY",
        "INNGEST_APP_ID",
        "INNGEST_WEBHOOK_URL",
        "INNGEST_REQUIRED",
        "REDIS_REQUIRED",
        "TRACE_ENVELOPE_FILE",
        "TRACE_ENVELOPE_ENABLED",
        "TRACE_RETENTION_DAYS",
        "TRACE_CLEANUP_ENABLED",
        "DASHBOARD_AUTH_TOKEN",
    ]


def _validate_required_keys(mode: str) -> Tuple[List[str], List[str]]:
    required = _required_for_mode(mode)
    missing = [k for k in required if not os.getenv(k)]

    if to_bool(os.getenv("REDIS_REQUIRED"), default=False) and not os.getenv("REDIS_URL"):
        missing.append("REDIS_URL (required because REDIS_REQUIRED=true)")

    if to_bool(os.getenv("INNGEST_REQUIRED"), default=False):
        if not os.getenv("INNGEST_SIGNING_KEY"):
            missing.append("INNGEST_SIGNING_KEY (required because INNGEST_REQUIRED=true)")
        if not os.getenv("INNGEST_EVENT_KEY"):
            missing.append("INNGEST_EVENT_KEY (required because INNGEST_REQUIRED=true)")

    return sorted(set(required)), sorted(set(missing))


def _validate_recommended_keys() -> Tuple[List[str], List[str]]:
    recommended = _recommended_keys()
    present = [k for k in recommended if os.getenv(k)]
    missing = [k for k in recommended if not os.getenv(k)]
    return present, missing


def _run_connection_checks(check_connections: bool, verify_inngest_route: bool) -> Dict[str, str]:
    status: Dict[str, str] = {}
    if not check_connections:
        return status

    route_mounted = None
    if verify_inngest_route:
        try:
            from dashboard import health_app

            route_mounted = bool(getattr(health_app, "INNGEST_ROUTE_MOUNTED", False))
        except Exception as exc:
            route_mounted = False
            status["inngest_route"] = f"FAIL: unable to verify /inngest route ({exc})"

    runtime = get_runtime_dependency_health(
        check_connections=True,
        inngest_route_mounted=route_mounted,
    )

    for dep_name in ("redis", "inngest"):
        dep = runtime["dependencies"][dep_name]
        dep_status = dep.get("status", "unknown")
        message = dep.get("message") or "no message"
        if dep_status == "not_configured" and not dep.get("required", False):
            prefix = "SKIP"
        elif dep.get("ready", False):
            prefix = "OK"
        else:
            prefix = "FAIL"
        status[dep_name] = (
            f"{prefix}: status={dep_status}; required={dep.get('required', False)}; {message}"
        )

    if verify_inngest_route and "inngest_route" not in status:
        inngest_dep = runtime["dependencies"]["inngest"]
        if inngest_dep.get("required") or inngest_dep.get("configured"):
            status["inngest_route"] = "OK" if route_mounted else "FAIL: /inngest route is not mounted"
        else:
            status["inngest_route"] = "SKIP: Inngest not required and not configured"

    status["runtime"] = "OK" if runtime.get("ready", False) else (
        "FAIL: " + "; ".join(runtime.get("required_failures", []))
    )

    return status


def validate(mode: str, check_connections: bool, verify_inngest_route: bool = False) -> ValidationResult:
    _required, missing_required = _validate_required_keys(mode)
    present_recommended, missing_recommended = _validate_recommended_keys()
    connection_checks = _run_connection_checks(check_connections, verify_inngest_route)
    return ValidationResult(
        mode=mode,
        missing_required=missing_required,
        present_recommended=present_recommended,
        missing_recommended=missing_recommended,
        connection_checks=connection_checks,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CAIO runtime environment variables.")
    parser.add_argument("--env-file", default=".env", help="Path to env file to load.")
    parser.add_argument(
        "--mode",
        choices=["development", "staging", "production"],
        default=os.getenv("ENVIRONMENT", "development"),
        help="Validation mode.",
    )
    parser.add_argument(
        "--check-connections",
        action="store_true",
        help="Attempt Redis connectivity check.",
    )
    parser.add_argument(
        "--verify-inngest-route",
        action="store_true",
        help="Import dashboard app and verify /inngest route mount state.",
    )
    args = parser.parse_args()

    if os.path.exists(args.env_file):
        load_dotenv(args.env_file, override=False)

    result = validate(
        mode=args.mode,
        check_connections=args.check_connections,
        verify_inngest_route=args.verify_inngest_route,
    )

    print("=" * 72)
    print(f"CAIO Runtime Env Validation | mode={result.mode}")
    print("=" * 72)

    if result.missing_required:
        print("Missing required keys:")
        for key in result.missing_required:
            print(f"  - {key}")
    else:
        print("Required keys: OK")

    print("\nRecommended keys present:")
    for key in sorted(result.present_recommended):
        print(f"  - {key}")

    print("\nRecommended keys missing:")
    for key in sorted(result.missing_recommended):
        print(f"  - {key}")

    if result.connection_checks:
        print("\nConnection checks:")
        for name, status in result.connection_checks.items():
            print(f"  - {name}: {status}")

    print("\nResult:", "PASS" if result.passed else "FAIL")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
