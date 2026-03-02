#!/usr/bin/env python3
"""
Dashboard UI validation script for CAIO Alpha Swarm.

Performs DOM-assertion validation against key dashboard endpoints,
checking HTTP status codes, expected HTML elements, and API response
shapes on a deployed instance.

Checks:
  1. /login — HTTP 200, contains token input field
  2. /sales (authenticated) — HTTP 200, contains email table or "no pending"
  3. /scorecard (authenticated) — HTTP 200, contains KPI elements
  4. /api/health — HTTP 200, JSON with "status" field
  5. /api/health/ready — HTTP 200
  6. /api/runtime/dependencies (authenticated) — HTTP 200, JSON with "auth" field

Usage:
  python scripts/validate_dashboard_ui.py \\
    --base-url https://caio-swarm-dashboard-production.up.railway.app \\
    --token "<DASHBOARD_AUTH_TOKEN>"
  python scripts/validate_dashboard_ui.py --base-url <URL> --token <TOKEN> --json
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
from dataclasses import asdict, dataclass
from http.cookiejar import CookieJar
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    Request,
    build_opener,
)


@dataclass
class CheckResult:
    name: str
    endpoint: str
    passed: bool
    expectation: str
    status_code: Optional[int] = None
    detail: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only — no requests/httpx)
# ---------------------------------------------------------------------------

_SSL_CTX = ssl.create_default_context()


class _NoRedirectHandler(HTTPRedirectHandler):
    """Capture redirects instead of following them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _url(base: str, path: str, params: Optional[Dict[str, str]] = None) -> str:
    base = base.rstrip("/")
    path = path if path.startswith("/") else f"/{path}"
    if not params:
        return f"{base}{path}"
    return f"{base}{path}?{urlencode(params)}"


def _http(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
    timeout: int = 20,
    cookie_jar: Optional[CookieJar] = None,
    follow_redirects: bool = True,
) -> tuple[Optional[int], Optional[str], Optional[str]]:
    """Return (status_code, response_body, error)."""
    req = Request(url=url, method=method, headers=headers or {}, data=body)
    handlers = []
    if cookie_jar is not None:
        handlers.append(HTTPCookieProcessor(cookie_jar))
    if not follow_redirects:
        handlers.append(_NoRedirectHandler())
    opener = build_opener(*handlers)
    try:
        resp = opener.open(req, timeout=timeout)
        payload = resp.read().decode("utf-8", errors="replace")
        return int(resp.getcode()), payload, None
    except HTTPError as exc:
        payload = ""
        try:
            payload = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return int(exc.code), payload, None
    except URLError as exc:
        return None, None, str(exc)
    except Exception as exc:
        return None, None, str(exc)


def _safe_json(payload: Optional[str]) -> Dict[str, Any]:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# Session helper — login via POST /login to get session cookie
# ---------------------------------------------------------------------------

def _create_session(base_url: str, token: str, timeout: int) -> Optional[CookieJar]:
    """Authenticate via POST /login and return a CookieJar with session cookie."""
    jar = CookieJar()
    login_url = _url(base_url, "/login")
    form_data = urlencode({"token": token}).encode("utf-8")
    status, body, err = _http(
        login_url,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=form_data,
        timeout=timeout,
        cookie_jar=jar,
        follow_redirects=True,
    )
    if err:
        return None
    # After login, the session cookie should be in the jar.
    # A successful login redirects (302/303) then serves the target page.
    # We check if we got a valid page (200) or a redirect was followed.
    if status is not None and status < 400:
        return jar
    return None


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_login_page(base_url: str, timeout: int) -> CheckResult:
    """Check /login returns 200 and contains a token input field."""
    url = _url(base_url, "/login")
    status, body, err = _http(url, timeout=timeout)
    if err:
        return CheckResult(
            name="login_page", endpoint="/login", passed=False,
            expectation='HTTP 200 with name="token" input',
            error=err,
        )
    if status != 200:
        return CheckResult(
            name="login_page", endpoint="/login", passed=False,
            expectation='HTTP 200 with name="token" input',
            status_code=status,
            detail=f"Expected 200, got {status}",
        )
    has_token_input = bool(
        body and re.search(r'name\s*=\s*["\']token["\']', body, re.IGNORECASE)
    )
    return CheckResult(
        name="login_page", endpoint="/login",
        passed=has_token_input,
        expectation='HTTP 200 with name="token" input',
        status_code=status,
        detail="token input found" if has_token_input else "token input NOT found in HTML",
    )


def check_sales_page(
    base_url: str, jar: CookieJar, timeout: int
) -> CheckResult:
    """/sales should contain email table or 'no pending' indicator."""
    url = _url(base_url, "/sales")
    status, body, err = _http(url, timeout=timeout, cookie_jar=jar)
    if err:
        return CheckResult(
            name="sales_dashboard", endpoint="/sales", passed=False,
            expectation="HTTP 200 with email table or no-pending indicator",
            error=err,
        )
    if status != 200:
        return CheckResult(
            name="sales_dashboard", endpoint="/sales", passed=False,
            expectation="HTTP 200 with email table or no-pending indicator",
            status_code=status,
            detail=f"Expected 200, got {status}",
        )
    # Look for key HoS dashboard elements
    checks = [
        bool(body and re.search(r'id\s*=\s*["\']emailList["\']', body)),
        bool(body and re.search(r'showTab', body)),
        bool(body and re.search(r'tab-overview|tab-emails|tab-campaigns|tab-settings', body)),
    ]
    passed = any(checks)
    detail_parts = []
    if checks[0]:
        detail_parts.append("emailList element found")
    if checks[1]:
        detail_parts.append("showTab() function found")
    if checks[2]:
        detail_parts.append("tab containers found")
    return CheckResult(
        name="sales_dashboard", endpoint="/sales",
        passed=passed,
        expectation="HTTP 200 with email table or no-pending indicator",
        status_code=status,
        detail=", ".join(detail_parts) if detail_parts else "Expected UI elements NOT found",
    )


def check_scorecard_page(
    base_url: str, jar: CookieJar, timeout: int
) -> CheckResult:
    """/scorecard should contain KPI elements."""
    url = _url(base_url, "/scorecard")
    status, body, err = _http(url, timeout=timeout, cookie_jar=jar)
    if err:
        return CheckResult(
            name="scorecard_dashboard", endpoint="/scorecard", passed=False,
            expectation="HTTP 200 with KPI elements",
            error=err,
        )
    if status != 200:
        return CheckResult(
            name="scorecard_dashboard", endpoint="/scorecard", passed=False,
            expectation="HTTP 200 with KPI elements",
            status_code=status,
            detail=f"Expected 200, got {status}",
        )
    # Look for scorecard-specific elements
    has_kpi = bool(body and re.search(
        r'scorecard|metric|kpi|precision|constraint', body, re.IGNORECASE
    ))
    return CheckResult(
        name="scorecard_dashboard", endpoint="/scorecard",
        passed=has_kpi,
        expectation="HTTP 200 with KPI elements",
        status_code=status,
        detail="KPI elements found" if has_kpi else "KPI elements NOT found",
    )


def check_health_api(base_url: str, timeout: int) -> CheckResult:
    """/api/health should return JSON with 'status' field."""
    url = _url(base_url, "/api/health")
    status, body, err = _http(url, timeout=timeout)
    if err:
        return CheckResult(
            name="health_api", endpoint="/api/health", passed=False,
            expectation='HTTP 200, JSON with "status" field',
            error=err,
        )
    if status != 200:
        return CheckResult(
            name="health_api", endpoint="/api/health", passed=False,
            expectation='HTTP 200, JSON with "status" field',
            status_code=status,
            detail=f"Expected 200, got {status}",
        )
    data = _safe_json(body)
    has_status = "status" in data
    return CheckResult(
        name="health_api", endpoint="/api/health",
        passed=has_status,
        expectation='HTTP 200, JSON with "status" field',
        status_code=status,
        detail=f"status={data.get('status')}" if has_status else '"status" field missing from JSON',
    )


def check_health_ready(base_url: str, timeout: int) -> CheckResult:
    """/api/health/ready should return HTTP 200."""
    url = _url(base_url, "/api/health/ready")
    status, body, err = _http(url, timeout=timeout)
    if err:
        return CheckResult(
            name="health_ready", endpoint="/api/health/ready", passed=False,
            expectation="HTTP 200",
            error=err,
        )
    passed = status == 200
    return CheckResult(
        name="health_ready", endpoint="/api/health/ready",
        passed=passed,
        expectation="HTTP 200",
        status_code=status,
        detail="OK" if passed else f"Expected 200, got {status}",
    )


def check_runtime_deps(
    base_url: str, token: str, timeout: int
) -> CheckResult:
    """/api/runtime/dependencies should return JSON with 'auth' field."""
    url = _url(base_url, "/api/runtime/dependencies")
    headers = {"X-Dashboard-Token": token}
    status, body, err = _http(url, headers=headers, timeout=timeout)
    if err:
        return CheckResult(
            name="runtime_dependencies", endpoint="/api/runtime/dependencies",
            passed=False,
            expectation='HTTP 200, JSON with "auth" field',
            error=err,
        )
    if status != 200:
        return CheckResult(
            name="runtime_dependencies", endpoint="/api/runtime/dependencies",
            passed=False,
            expectation='HTTP 200, JSON with "auth" field',
            status_code=status,
            detail=f"Expected 200, got {status}",
        )
    data = _safe_json(body)
    has_auth = "auth" in data
    return CheckResult(
        name="runtime_dependencies", endpoint="/api/runtime/dependencies",
        passed=has_auth,
        expectation='HTTP 200, JSON with "auth" field',
        status_code=status,
        detail=f"auth present" if has_auth else '"auth" field missing from JSON',
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate CAIO dashboard UI endpoints on a deployed instance."
    )
    parser.add_argument("--base-url", required=True, help="Deployed dashboard base URL.")
    parser.add_argument("--token", required=True, help="Dashboard auth token.")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout per request (seconds).")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable.")
    args = parser.parse_args()

    results: List[CheckResult] = []

    # --- Unauthenticated checks ---
    print("--- Unauthenticated checks ---")

    result = check_login_page(args.base_url, args.timeout)
    results.append(result)
    print(f"  [{('PASS' if result.passed else 'FAIL')}] {result.name}: {result.detail or result.error}")

    result = check_health_api(args.base_url, args.timeout)
    results.append(result)
    print(f"  [{('PASS' if result.passed else 'FAIL')}] {result.name}: {result.detail or result.error}")

    result = check_health_ready(args.base_url, args.timeout)
    results.append(result)
    print(f"  [{('PASS' if result.passed else 'FAIL')}] {result.name}: {result.detail or result.error}")

    # --- Token-authenticated API check ---
    print("\n--- Token-authenticated checks ---")

    result = check_runtime_deps(args.base_url, args.token, args.timeout)
    results.append(result)
    print(f"  [{('PASS' if result.passed else 'FAIL')}] {result.name}: {result.detail or result.error}")

    # --- Session-authenticated checks ---
    print("\n--- Session-authenticated checks ---")

    jar = _create_session(args.base_url, args.token, args.timeout)
    if jar is None:
        print("  [FAIL] Session creation failed - cannot run authenticated UI checks")
        results.append(CheckResult(
            name="session_login", endpoint="/login (POST)",
            passed=False, expectation="Session cookie acquired",
            error="POST /login did not return a valid session",
        ))
    else:
        print("  [OK]   Session created successfully")

        result = check_sales_page(args.base_url, jar, args.timeout)
        results.append(result)
        print(f"  [{('PASS' if result.passed else 'FAIL')}] {result.name}: {result.detail or result.error}")

        result = check_scorecard_page(args.base_url, jar, args.timeout)
        results.append(result)
        print(f"  [{('PASS' if result.passed else 'FAIL')}] {result.name}: {result.detail or result.error}")

    # --- Summary ---
    passed_count = sum(1 for r in results if r.passed)
    total = len(results)
    all_passed = passed_count == total

    summary = {
        "base_url": args.base_url.rstrip("/"),
        "all_passed": all_passed,
        "passed": passed_count,
        "total": total,
        "results": [asdict(r) for r in results],
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print()
        print("=" * 50)
        print(f"DASHBOARD UI VALIDATION: {passed_count}/{total} passed")
        print("=" * 50)
        for r in results:
            icon = "PASS" if r.passed else "FAIL"
            print(f"  [{icon}] {r.name} ({r.endpoint})")
        print()
        if all_passed:
            print("All dashboard UI checks PASSED.")
        else:
            failed = [r for r in results if not r.passed]
            print(f"{len(failed)} check(s) FAILED. Review output above.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
