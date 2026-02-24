#!/usr/bin/env python3
"""
Webhook strict-mode smoke checker for deployed CAIO environments.

This validates that non-API webhook endpoints enforce auth when strict mode is
enabled and that runtime dependency health reflects the expected webhook policy.

Usage:
  python scripts/webhook_strict_smoke.py \
    --base-url "https://<staging-domain>" \
    --dashboard-token "<DASHBOARD_AUTH_TOKEN>" \
    --expect-webhook-required true \
    --webhook-bearer-token "<WEBHOOK_BEARER_TOKEN>"
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from dataclasses import asdict, dataclass
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
    details: Optional[Dict[str, object]] = None
    error: Optional[str] = None


def _parse_bool(value: str) -> bool:
    v = (value or "").strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid bool value: {value}")


def _build_url(base_url: str, path: str, params: Optional[Dict[str, str]] = None) -> str:
    base = base_url.rstrip("/")
    clean_path = path if path.startswith("/") else f"/{path}"
    if not params:
        return f"{base}{clean_path}"
    return f"{base}{clean_path}?{urlencode(params)}"


def _http_request(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
    timeout_seconds: int = 20,
) -> tuple[Optional[int], Optional[str], Optional[bytes]]:
    req = Request(url=url, method=method, headers=headers or {}, data=body)
    try:
        with urlopen(req, timeout=timeout_seconds, context=ssl.create_default_context()) as resp:
            return int(resp.getcode()), None, resp.read()
    except HTTPError as exc:
        payload = None
        try:
            payload = exc.read()
        except Exception:
            payload = None
        return int(exc.code), None, payload
    except URLError as exc:
        return None, str(exc), None
    except Exception as exc:  # pragma: no cover
        return None, str(exc), None


def _decode_json(data: Optional[bytes]) -> Optional[Dict[str, object]]:
    if not data:
        return None
    try:
        raw = data.decode("utf-8", errors="replace")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    except Exception:
        return None


def run_webhook_strict_smoke(
    *,
    base_url: str,
    dashboard_token: str,
    expect_webhook_required: bool,
    webhook_bearer_token: Optional[str] = None,
    require_heyreach_hard_auth: bool = False,
    timeout_seconds: int = 20,
) -> Dict[str, object]:
    checks: list[CheckResult] = []

    runtime_url = _build_url(base_url, "/api/runtime/dependencies", {"token": dashboard_token})
    runtime_status, runtime_error, runtime_body = _http_request(
        runtime_url,
        timeout_seconds=timeout_seconds,
    )
    runtime_json = _decode_json(runtime_body) or {}
    deps = runtime_json.get("dependencies", {}) if isinstance(runtime_json, dict) else {}
    webhook_dep = deps.get("webhooks", {}) if isinstance(deps, dict) else {}
    provider_auth = webhook_dep.get("provider_auth", {}) if isinstance(webhook_dep, dict) else {}
    heyreach_auth = provider_auth.get("heyreach", {}) if isinstance(provider_auth, dict) else {}

    runtime_required_actual = bool(webhook_dep.get("required")) if isinstance(webhook_dep, dict) else None
    runtime_ready_actual = bool(webhook_dep.get("ready")) if isinstance(webhook_dep, dict) else None

    checks.append(
        CheckResult(
            name="runtime_webhook_required_matches_expectation",
            method="GET",
            url=runtime_url,
            status=runtime_status,
            passed=(runtime_status == 200 and runtime_required_actual == expect_webhook_required),
            expectation=f"runtime.dependencies.webhooks.required == {expect_webhook_required}",
            details={
                "actual_required": runtime_required_actual,
                "actual_ready": runtime_ready_actual,
                "provider_auth": provider_auth,
            },
            error=runtime_error,
        )
    )

    if expect_webhook_required:
        checks.append(
            CheckResult(
                name="runtime_webhook_ready_when_required",
                method="GET",
                url=runtime_url,
                status=runtime_status,
                passed=(runtime_status == 200 and runtime_ready_actual is True),
                expectation="runtime.dependencies.webhooks.ready == true",
                details={
                    "actual_ready": runtime_ready_actual,
                },
                error=runtime_error,
            )
        )

    # unauthenticated webhook calls should be blocked in strict mode
    webhook_payload = json.dumps({"eventType": "UNKNOWN", "data": {"lead_email": "lead@example.com"}}).encode("utf-8")
    no_auth_headers = {"Content-Type": "application/json"}

    for name, path in [
        ("instantly_no_auth_blocked", "/webhooks/instantly/open"),
        ("clay_no_auth_blocked", "/webhooks/clay"),
        ("rb2b_no_auth_blocked", "/webhooks/rb2b"),
    ]:
        status, error, _ = _http_request(
            _build_url(base_url, path),
            method="POST",
            headers=no_auth_headers,
            body=webhook_payload,
            timeout_seconds=timeout_seconds,
        )
        expected = "status in {401,503} when strict=true" if expect_webhook_required else "informational (strict=false allowed)"
        passed = (
            (status in {401, 503}) if expect_webhook_required else (status is not None)
        )
        checks.append(
            CheckResult(
                name=name,
                method="POST",
                url=_build_url(base_url, path),
                status=status,
                passed=passed,
                expectation=expected,
                error=error,
            )
        )

    # HeyReach has special treatment currently. Keep explicit visibility.
    heyreach_status, heyreach_error, _ = _http_request(
        _build_url(base_url, "/webhooks/heyreach"),
        method="POST",
        headers=no_auth_headers,
        body=webhook_payload,
        timeout_seconds=timeout_seconds,
    )
    heyreach_expected = (
        "status in {401,503} (hard-auth required)"
        if require_heyreach_hard_auth
        else "informational (provider may be unsigned)"
    )
    heyreach_passed = (
        (heyreach_status in {401, 503})
        if require_heyreach_hard_auth
        else (heyreach_status is not None)
    )
    checks.append(
        CheckResult(
            name="heyreach_auth_behavior",
            method="POST",
            url=_build_url(base_url, "/webhooks/heyreach"),
            status=heyreach_status,
            passed=heyreach_passed,
            expectation=heyreach_expected,
            details={
                "provider_auth_heyreach": heyreach_auth,
            },
            error=heyreach_error,
        )
    )

    # Positive-path validation via bearer token when supplied.
    if webhook_bearer_token:
        bearer_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {webhook_bearer_token}",
        }
        for name, path in [
            ("instantly_bearer_allows_request", "/webhooks/instantly/open"),
            ("clay_bearer_allows_request", "/webhooks/clay"),
        ]:
            status, error, _ = _http_request(
                _build_url(base_url, path),
                method="POST",
                headers=bearer_headers,
                body=webhook_payload,
                timeout_seconds=timeout_seconds,
            )
            checks.append(
                CheckResult(
                    name=name,
                    method="POST",
                    url=_build_url(base_url, path),
                    status=status,
                    passed=(status is not None and status not in {401, 503}),
                    expectation="request accepted when bearer token is valid",
                    error=error,
                )
            )

    passed = all(c.passed for c in checks)
    return {
        "base_url": base_url.rstrip("/"),
        "expect_webhook_required": expect_webhook_required,
        "require_heyreach_hard_auth": require_heyreach_hard_auth,
        "passed": passed,
        "checks": [asdict(c) for c in checks],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run webhook strict-mode smoke checks for a deployed environment."
    )
    parser.add_argument("--base-url", required=True, help="Deployed dashboard base URL.")
    parser.add_argument("--dashboard-token", required=True, help="Dashboard auth token.")
    parser.add_argument(
        "--expect-webhook-required",
        default="true",
        help="Expected value for runtime.dependencies.webhooks.required (true/false).",
    )
    parser.add_argument(
        "--webhook-bearer-token",
        default="",
        help="Optional webhook bearer token to validate positive auth path.",
    )
    parser.add_argument(
        "--require-heyreach-hard-auth",
        action="store_true",
        help="Fail if HeyReach accepts unsigned requests.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=20,
        help="HTTP timeout per request.",
    )
    args = parser.parse_args()

    try:
        expect_required = _parse_bool(args.expect_webhook_required)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    summary = run_webhook_strict_smoke(
        base_url=args.base_url,
        dashboard_token=args.dashboard_token,
        expect_webhook_required=expect_required,
        webhook_bearer_token=(args.webhook_bearer_token or "").strip() or None,
        require_heyreach_hard_auth=bool(args.require_heyreach_hard_auth),
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())

