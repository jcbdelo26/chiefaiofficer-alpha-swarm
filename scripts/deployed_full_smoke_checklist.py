#!/usr/bin/env python3
"""
Full deployed smoke checklist for CAIO dashboard runtime + refresh reliability.

Checks include:
1. Protected API auth behavior.
2. Health/readiness/runtime dependency endpoints.
3. /sales page includes auto-refresh wiring.
4. /api/pending-emails refreshes over time (no manual page reload dependency).

Usage:
  python scripts/deployed_full_smoke_checklist.py \
    --base-url "https://<env-domain>" \
    --token "<DASHBOARD_AUTH_TOKEN>"
"""

from __future__ import annotations

import argparse
import json
import ssl
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from endpoint_auth_smoke import run_smoke as run_auth_smoke


@dataclass
class CheckResult:
    name: str
    method: str
    url: str
    status: Optional[int]
    passed: bool
    expectation: str
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


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
) -> tuple[Optional[int], Optional[str], Optional[str]]:
    req = Request(url=url, method=method, headers=headers or {}, data=body)
    try:
        with urlopen(req, timeout=timeout_seconds, context=ssl.create_default_context()) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
            return int(resp.getcode()), payload, None
    except HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), payload, None
    except URLError as exc:
        return None, None, str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return None, None, str(exc)


def _safe_json(payload: Optional[str]) -> Dict[str, Any]:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            return parsed
        return {"_raw": parsed}
    except Exception:
        return {}


def _record(
    checks: list[CheckResult],
    *,
    name: str,
    method: str,
    url: str,
    status: Optional[int],
    passed: bool,
    expectation: str,
    details: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    checks.append(
        CheckResult(
            name=name,
            method=method,
            url=url,
            status=status,
            passed=passed,
            expectation=expectation,
            details=details,
            error=error,
        )
    )


def run_full_smoke(
    base_url: str,
    token: str,
    *,
    timeout_seconds: int = 20,
    refresh_wait_seconds: int = 3,
    expect_query_token_enabled: bool = True,
    require_heyreach_hard_auth: bool = False,
) -> Dict[str, Any]:
    checks: list[CheckResult] = []

    # Baseline auth checks (existing no-go gate)
    auth_summary = run_auth_smoke(
        base_url,
        token,
        timeout_seconds=timeout_seconds,
        expect_query_token_enabled=expect_query_token_enabled,
    )
    for item in auth_summary.get("checks", []):
        checks.append(
            CheckResult(
                name=f"auth::{item.get('name')}",
                method=str(item.get("method") or "GET"),
                url=str(item.get("url") or ""),
                status=item.get("status"),
                passed=bool(item.get("passed")),
                expectation=str(item.get("expectation") or ""),
                error=item.get("error"),
            )
        )

    # Pending emails unauthenticated must be blocked
    pending_unauth = _build_url(base_url, "/api/pending-emails")
    status, _, error = _http_request(
        pending_unauth,
        method="GET",
        headers={"Accept": "application/json"},
        timeout_seconds=timeout_seconds,
    )
    _record(
        checks,
        name="pending_emails_unauth_blocked",
        method="GET",
        url=pending_unauth,
        status=status,
        passed=(status == 401),
        expectation="401 unauthorized",
        error=error,
    )

    # Runtime dependencies should be callable and ideally ready=true
    runtime_url = _build_url(base_url, "/api/runtime/dependencies")
    status, payload, error = _http_request(
        runtime_url,
        headers={"X-Dashboard-Token": token},
        timeout_seconds=timeout_seconds,
    )
    runtime_json = _safe_json(payload)
    runtime_ready = bool(runtime_json.get("ready"))
    _record(
        checks,
        name="runtime_dependencies_ready",
        method="GET",
        url=runtime_url,
        status=status,
        passed=(status == 200 and runtime_ready),
        expectation="200 with ready=true",
        details={"ready": runtime_ready},
        error=error,
    )

    # Optional no-go: fail unless HeyReach is authenticated without unsigned allowlist.
    provider_auth = (
        runtime_json.get("dependencies", {})
        .get("webhooks", {})
        .get("provider_auth", {})
    )
    heyreach_auth = provider_auth.get("heyreach") if isinstance(provider_auth, dict) else {}
    heyreach_hmac = bool((heyreach_auth or {}).get("hmac"))
    heyreach_bearer = bool((heyreach_auth or {}).get("bearer"))
    heyreach_unsigned_allowlisted = bool((heyreach_auth or {}).get("unsigned_allowlisted"))
    heyreach_authed = bool((heyreach_auth or {}).get("authed"))
    heyreach_hard_auth_ok = (
        bool(status == 200)
        and heyreach_authed
        and (heyreach_hmac or heyreach_bearer)
        and not heyreach_unsigned_allowlisted
    )
    _record(
        checks,
        name="runtime_heyreach_hard_auth",
        method="GET",
        url=runtime_url,
        status=status,
        passed=(heyreach_hard_auth_ok if require_heyreach_hard_auth else True),
        expectation=(
            "HeyReach uses explicit auth (hmac/bearer) and unsigned allowlist is disabled"
            if require_heyreach_hard_auth
            else "check skipped (require_heyreach_hard_auth=false)"
        ),
        details={
            "required": require_heyreach_hard_auth,
            "heyreach_authed": heyreach_authed,
            "heyreach_hmac": heyreach_hmac,
            "heyreach_bearer": heyreach_bearer,
            "heyreach_unsigned_allowlisted": heyreach_unsigned_allowlisted,
            "bearer_env": (heyreach_auth or {}).get("bearer_env"),
            "unsigned_allowlist_env": (heyreach_auth or {}).get("unsigned_allowlist_env"),
        },
        error=error,
    )

    # Readiness probe should pass in deployed environment
    ready_url = _build_url(base_url, "/api/health/ready")
    status, payload, error = _http_request(ready_url, timeout_seconds=timeout_seconds)
    ready_json = _safe_json(payload)
    ready_status = str(ready_json.get("status") or "").lower()
    _record(
        checks,
        name="health_ready_status",
        method="GET",
        url=ready_url,
        status=status,
        passed=(status == 200 and ready_status in {"ready", "ok", "healthy"}),
        expectation="200 with status indicating readiness",
        details={"status": ready_json.get("status")},
        error=error,
    )

    # CORS preflight should not be blocked by auth middleware
    preflight_url = _build_url(base_url, "/api/operator/status")
    status, _, error = _http_request(
        preflight_url,
        method="OPTIONS",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Dashboard-Token",
        },
        timeout_seconds=timeout_seconds,
    )
    _record(
        checks,
        name="cors_preflight_not_unauthorized",
        method="OPTIONS",
        url=preflight_url,
        status=status,
        passed=(status is not None and status != 401),
        expectation="OPTIONS is not blocked with 401",
        error=error,
    )

    # Sales page should include auto-refresh wiring for pending queue
    sales_url = _build_url(base_url, "/sales")
    status, payload, error = _http_request(sales_url, timeout_seconds=timeout_seconds)
    html = payload or ""
    has_interval = "setInterval" in html
    has_visibility_refresh = "visibilitychange" in html
    has_pending_fetch = "/api/pending-emails" in html and "fetchPendingEmails" in html
    _record(
        checks,
        name="sales_page_auto_refresh_wiring",
        method="GET",
        url=sales_url,
        status=status,
        passed=(status == 200 and has_interval and has_visibility_refresh and has_pending_fetch),
        expectation="/sales includes polling + visibility refresh wiring",
        details={
            "has_setInterval": has_interval,
            "has_visibilitychange": has_visibility_refresh,
            "has_pending_fetch": has_pending_fetch,
        },
        error=error,
    )

    # Legacy sales bookmark should not be a dead endpoint
    legacy_sales_url = _build_url(base_url, "/ChiefAIOfficer")
    status, _, error = _http_request(legacy_sales_url, timeout_seconds=timeout_seconds)
    _record(
        checks,
        name="legacy_sales_bookmark_not_dead",
        method="GET",
        url=legacy_sales_url,
        status=status,
        passed=(status is not None and status != 404),
        expectation="/ChiefAIOfficer redirects/serves dashboard (not 404)",
        error=error,
    )

    # Pending endpoint should refresh its timestamp across polls
    pending_url = _build_url(base_url, "/api/pending-emails", {"_ts": str(int(time.time() * 1000))})
    status1, payload1, error1 = _http_request(
        pending_url,
        headers={"X-Dashboard-Token": token, "Accept": "application/json"},
        timeout_seconds=timeout_seconds,
    )
    data1 = _safe_json(payload1)
    refreshed_at_1 = str(data1.get("refreshed_at") or "")
    count1 = data1.get("count")

    if refresh_wait_seconds > 0:
        time.sleep(refresh_wait_seconds)

    pending_url_2 = _build_url(
        base_url,
        "/api/pending-emails",
        {"_ts": str(int(time.time() * 1000))},
    )
    status2, payload2, error2 = _http_request(
        pending_url_2,
        headers={"X-Dashboard-Token": token, "Accept": "application/json"},
        timeout_seconds=timeout_seconds,
    )
    data2 = _safe_json(payload2)
    refreshed_at_2 = str(data2.get("refreshed_at") or "")
    count2 = data2.get("count")
    refreshed_changed = bool(refreshed_at_1 and refreshed_at_2 and refreshed_at_1 != refreshed_at_2)

    _record(
        checks,
        name="pending_emails_refresh_timestamp_changes",
        method="GET",
        url=pending_url_2,
        status=status2,
        passed=(status1 == 200 and status2 == 200 and refreshed_changed),
        expectation="two polls return 200 and refreshed_at changes",
        details={
            "first_status": status1,
            "second_status": status2,
            "first_count": count1,
            "second_count": count2,
            "first_refreshed_at": refreshed_at_1,
            "second_refreshed_at": refreshed_at_2,
            "debug_second": data2.get("_shadow_queue_debug"),
        },
        error=error1 or error2,
    )

    # Pending payload should expose classifier + campaign mapping contract for UI traceability
    pending_items = data2.get("pending_emails") if isinstance(data2, dict) else None
    first_item = pending_items[0] if isinstance(pending_items, list) and pending_items else {}
    classifier = first_item.get("classifier") if isinstance(first_item, dict) else None
    campaign_ref = first_item.get("campaign_ref") if isinstance(first_item, dict) else None
    classifier_contract_ok = (
        status2 == 200
        and (
            not isinstance(pending_items, list)
            or len(pending_items) == 0
            or (
                isinstance(classifier, dict)
                and isinstance(campaign_ref, dict)
                and "target_platform" in classifier
                and "queue_origin" in classifier
                and "internal_id" in campaign_ref
            )
        )
    )

    _record(
        checks,
        name="pending_emails_classifier_contract",
        method="GET",
        url=pending_url_2,
        status=status2,
        passed=classifier_contract_ok,
        expectation="pending emails expose classifier + campaign_ref metadata",
        details={
            "count": len(pending_items) if isinstance(pending_items, list) else None,
            "first_item_classifier": classifier if isinstance(classifier, dict) else None,
            "first_item_campaign_ref": campaign_ref if isinstance(campaign_ref, dict) else None,
        },
        error=error2,
    )

    passed = all(c.passed for c in checks)
    return {
        "base_url": base_url.rstrip("/"),
        "passed": passed,
        "refresh_wait_seconds": refresh_wait_seconds,
        "expect_query_token_enabled": expect_query_token_enabled,
        "require_heyreach_hard_auth": require_heyreach_hard_auth,
        "checks": [asdict(c) for c in checks],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full deployed smoke checklist.")
    parser.add_argument("--base-url", required=True, help="Deployed dashboard base URL.")
    parser.add_argument("--token", required=True, help="Dashboard auth token.")
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
        help="Wait between two pending-emails polls.",
    )
    parser.add_argument(
        "--expect-query-token-enabled",
        default="true",
        help="Expected query-token auth state (true/false).",
    )
    parser.add_argument(
        "--require-heyreach-hard-auth",
        action="store_true",
        help="Fail unless HeyReach has explicit auth (hmac/bearer) with allowlist disabled.",
    )
    args = parser.parse_args()

    normalized = (args.expect_query_token_enabled or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        expect_query_enabled = True
    elif normalized in {"0", "false", "no", "off"}:
        expect_query_enabled = False
    else:
        raise SystemExit(f"Invalid --expect-query-token-enabled value: {args.expect_query_token_enabled!r}")

    summary = run_full_smoke(
        args.base_url,
        args.token,
        timeout_seconds=args.timeout_seconds,
        refresh_wait_seconds=args.refresh_wait_seconds,
        expect_query_token_enabled=expect_query_enabled,
        require_heyreach_hard_auth=bool(args.require_heyreach_hard_auth),
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
