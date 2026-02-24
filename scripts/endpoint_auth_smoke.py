#!/usr/bin/env python3
"""
Auth smoke gate for deployed CAIO dashboard endpoints.

Usage:
  python scripts/endpoint_auth_smoke.py \
    --base-url https://caio-swarm-dashboard-production.up.railway.app \
    --token "<DASHBOARD_AUTH_TOKEN>"
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from dataclasses import dataclass, asdict
from typing import Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class CheckResult:
    name: str
    method: str
    url: str
    status: Optional[int]
    passed: bool
    expectation: str
    error: Optional[str] = None


def _http_request(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
    timeout_seconds: int = 20,
) -> tuple[Optional[int], Optional[str]]:
    req = Request(url=url, method=method, headers=headers or {}, data=body)
    try:
        with urlopen(req, timeout=timeout_seconds, context=ssl.create_default_context()) as resp:
            return int(resp.getcode()), None
    except HTTPError as exc:
        return int(exc.code), None
    except URLError as exc:
        return None, str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return None, str(exc)


def _build_url(base_url: str, path: str, params: Optional[Dict[str, str]] = None) -> str:
    base = base_url.rstrip("/")
    clean_path = path if path.startswith("/") else f"/{path}"
    if not params:
        return f"{base}{clean_path}"
    return f"{base}{clean_path}?{urlencode(params)}"


def _parse_bool(value: str) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def run_smoke(
    base_url: str,
    token: str,
    timeout_seconds: int = 20,
    *,
    expect_query_token_enabled: bool = True,
) -> Dict[str, object]:
    checks: list[CheckResult] = []

    unauth_status_url = _build_url(base_url, "/api/operator/status")
    status_code, error = _http_request(unauth_status_url, timeout_seconds=timeout_seconds)
    checks.append(
        CheckResult(
            name="protected_status_unauth",
            method="GET",
            url=unauth_status_url,
            status=status_code,
            passed=(status_code == 401),
            expectation="401 unauthorized",
            error=error,
        )
    )

    unauth_trigger_url = _build_url(base_url, "/api/operator/trigger")
    trigger_body = json.dumps({"dry_run": True}).encode("utf-8")
    status_code, error = _http_request(
        unauth_trigger_url,
        method="POST",
        headers={"Content-Type": "application/json"},
        body=trigger_body,
        timeout_seconds=timeout_seconds,
    )
    checks.append(
        CheckResult(
            name="protected_trigger_unauth",
            method="POST",
            url=unauth_trigger_url,
            status=status_code,
            passed=(status_code == 401),
            expectation="401 unauthorized",
            error=error,
        )
    )

    ready_url = _build_url(base_url, "/api/health/ready")
    status_code, error = _http_request(ready_url, timeout_seconds=timeout_seconds)
    checks.append(
        CheckResult(
            name="health_ready_unauth",
            method="GET",
            url=ready_url,
            status=status_code,
            passed=(status_code == 200),
            expectation="200 ready",
            error=error,
        )
    )

    query_auth_url = _build_url(base_url, "/api/operator/status", {"token": token})
    status_code, error = _http_request(query_auth_url, timeout_seconds=timeout_seconds)
    query_expectation = (
        "non-401 with query token"
        if expect_query_token_enabled
        else "401 when query-token auth is disabled"
    )
    query_passed = (
        (status_code is not None and status_code != 401)
        if expect_query_token_enabled
        else (status_code == 401)
    )
    checks.append(
        CheckResult(
            name="protected_status_query_token",
            method="GET",
            url=query_auth_url,
            status=status_code,
            passed=query_passed,
            expectation=query_expectation,
            error=error,
        )
    )

    header_auth_url = _build_url(base_url, "/api/operator/status")
    status_code, error = _http_request(
        header_auth_url,
        headers={"X-Dashboard-Token": token},
        timeout_seconds=timeout_seconds,
    )
    checks.append(
        CheckResult(
            name="protected_status_header_token",
            method="GET",
            url=header_auth_url,
            status=status_code,
            passed=(status_code is not None and status_code != 401),
            expectation="non-401 with header token",
            error=error,
        )
    )

    runtime_deps_url = _build_url(base_url, "/api/runtime/dependencies")
    status_code, error = _http_request(
        runtime_deps_url,
        headers={"X-Dashboard-Token": token},
        timeout_seconds=timeout_seconds,
    )
    checks.append(
        CheckResult(
            name="runtime_dependencies_header_token",
            method="GET",
            url=runtime_deps_url,
            status=status_code,
            passed=(status_code is not None and status_code != 401),
            expectation="non-401 runtime dependencies with header token",
            error=error,
        )
    )

    passed = all(c.passed for c in checks)
    return {
        "base_url": base_url.rstrip("/"),
        "passed": passed,
        "checks": [asdict(c) for c in checks],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deployed endpoint auth smoke checks.")
    parser.add_argument("--base-url", required=True, help="Deployed dashboard base URL.")
    parser.add_argument("--token", required=True, help="Dashboard auth token.")
    parser.add_argument("--timeout-seconds", type=int, default=20, help="HTTP timeout per request.")
    parser.add_argument(
        "--expect-query-token-enabled",
        default="true",
        help="Expected query-token auth state (true/false).",
    )
    args = parser.parse_args()

    summary = run_smoke(
        args.base_url,
        args.token,
        timeout_seconds=args.timeout_seconds,
        expect_query_token_enabled=_parse_bool(args.expect_query_token_enabled),
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
