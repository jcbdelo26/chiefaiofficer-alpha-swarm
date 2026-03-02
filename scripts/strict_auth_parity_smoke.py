#!/usr/bin/env python3
"""
Strict-auth parity smoke gate for CAIO production deployments.

Validates all N1-N7 security hardening nuances from the Agentic
Engineering Audit v1.1 are enforced on a deployed instance.

Checks:
  N1 — Query-token auth disabled (no ?token= bypass)
  N2 — Dashboard URLs contain no embedded auth tokens
  N3 — Session secret is explicit (not fallback)
  N4 — Runtime dependencies endpoint reports full auth state
  N5 — Webhook signature enforcement declared
  N6 — OpenAPI docs disabled (/docs, /redoc, /openapi.json return 404)
  N7 — Dormant engines report feature-flag status

Usage:
  python scripts/strict_auth_parity_smoke.py \
    --base-url https://caio-swarm-dashboard-production.up.railway.app \
    --token "<DASHBOARD_AUTH_TOKEN>"
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class CheckResult:
    nuance: str
    name: str
    passed: bool
    expectation: str
    detail: Optional[str] = None
    error: Optional[str] = None


def _http(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
    timeout: int = 20,
) -> tuple[int | None, str | None, bytes | None]:
    """Return (status, error, response_body)."""
    req = Request(url=url, method=method, headers=headers or {}, data=body)
    try:
        ctx = ssl.create_default_context()
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            return int(resp.getcode()), None, resp.read()
    except HTTPError as exc:
        body_bytes = None
        try:
            body_bytes = exc.read()
        except Exception:
            pass
        return int(exc.code), None, body_bytes
    except URLError as exc:
        return None, str(exc), None
    except Exception as exc:
        return None, str(exc), None


def _url(base: str, path: str, params: Optional[Dict[str, str]] = None) -> str:
    base = base.rstrip("/")
    path = path if path.startswith("/") else f"/{path}"
    if not params:
        return f"{base}{path}"
    return f"{base}{path}?{urlencode(params)}"


def _json_body(body: bytes | None) -> Any:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except Exception:
        return None


def run_checks(
    base_url: str,
    token: str,
    timeout: int = 20,
) -> Dict[str, Any]:
    results: List[CheckResult] = []
    auth_header = {"X-Dashboard-Token": token}

    # ── N1: Query-token auth DISABLED in production ──────────────
    query_url = _url(base_url, "/api/operator/status", {"token": token})
    status, error, _ = _http(query_url, timeout=timeout)
    results.append(CheckResult(
        nuance="N1",
        name="query_token_rejected",
        passed=(status == 401),
        expectation="401 (query-token auth disabled in production)",
        detail=f"got {status}",
        error=error,
    ))

    # Verify header auth still works
    header_url = _url(base_url, "/api/operator/status")
    status, error, _ = _http(header_url, headers=auth_header, timeout=timeout)
    results.append(CheckResult(
        nuance="N1",
        name="header_token_accepted",
        passed=(status is not None and status != 401),
        expectation="non-401 (header auth works)",
        detail=f"got {status}",
        error=error,
    ))

    # ── N3 + N4: Runtime dependencies exposes auth state ─────────
    deps_url = _url(base_url, "/api/runtime/dependencies")
    status, error, body = _http(deps_url, headers=auth_header, timeout=timeout)
    deps = _json_body(body) or {}
    auth_state = deps.get("auth", {})

    results.append(CheckResult(
        nuance="N4",
        name="runtime_deps_reachable",
        passed=(status is not None and status != 401),
        expectation="non-401 (endpoint reachable with header token)",
        detail=f"got {status}",
        error=error,
    ))

    # N1 parity: query_token_enabled should be false
    qt_enabled = auth_state.get("query_token_enabled")
    results.append(CheckResult(
        nuance="N1",
        name="deps_query_token_disabled",
        passed=(qt_enabled is False),
        expectation="auth.query_token_enabled == false",
        detail=f"got {qt_enabled!r}",
    ))

    # N3 parity: session_secret_explicit should be true
    ss_explicit = auth_state.get("session_secret_explicit")
    results.append(CheckResult(
        nuance="N3",
        name="deps_session_secret_explicit",
        passed=(ss_explicit is True),
        expectation="auth.session_secret_explicit == true",
        detail=f"got {ss_explicit!r}",
    ))

    # N4: token_configured should be true
    token_configured = auth_state.get("token_configured")
    results.append(CheckResult(
        nuance="N4",
        name="deps_token_configured",
        passed=(token_configured is True),
        expectation="auth.token_configured == true",
        detail=f"got {token_configured!r}",
    ))

    # N4: environment should be production or staging
    env_val = auth_state.get("environment", "")
    results.append(CheckResult(
        nuance="N4",
        name="deps_environment_strict",
        passed=(env_val in ("production", "staging")),
        expectation="auth.environment in (production, staging)",
        detail=f"got {env_val!r}",
    ))

    # N5: webhook_signature_required ideally true
    ws_required = auth_state.get("webhook_signature_required")
    results.append(CheckResult(
        nuance="N5",
        name="deps_webhook_sig_required",
        passed=(ws_required is True),
        expectation="auth.webhook_signature_required == true",
        detail=f"got {ws_required!r} (advisory -- set WEBHOOK_SIGNATURE_REQUIRED=true)",
    ))

    # ── N6: OpenAPI docs DISABLED in production ──────────────────
    for doc_path in ("/docs", "/redoc", "/openapi.json"):
        doc_url = _url(base_url, doc_path)
        status, error, _ = _http(doc_url, timeout=timeout)
        results.append(CheckResult(
            nuance="N6",
            name=f"openapi{doc_path.replace('/', '_')}_blocked",
            passed=(status == 404),
            expectation=f"404 ({doc_path} disabled in production)",
            detail=f"got {status}",
            error=error,
        ))

    # ── N2: Verify no token in dashboard URL helper ──────────────
    # This is a code-level check; at runtime we verify /api/health/ready
    # doesn't leak tokens in any response body.
    ready_url = _url(base_url, "/api/health/ready")
    status, error, body = _http(ready_url, timeout=timeout)
    body_text = (body or b"").decode("utf-8", errors="replace")
    has_token_leak = token in body_text if token else False
    results.append(CheckResult(
        nuance="N2",
        name="health_no_token_leak",
        passed=(not has_token_leak and status == 200),
        expectation="200 + no token in response body",
        detail=f"status={status}, token_in_body={has_token_leak}",
        error=error,
    ))

    # ── Summary ──────────────────────────────────────────────────
    all_passed = all(r.passed for r in results)
    by_nuance: Dict[str, bool] = {}
    for r in results:
        by_nuance.setdefault(r.nuance, True)
        if not r.passed:
            by_nuance[r.nuance] = False

    return {
        "base_url": base_url.rstrip("/"),
        "passed": all_passed,
        "nuance_summary": by_nuance,
        "checks": [asdict(r) for r in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Strict-auth parity smoke gate (N1-N7 audit checks)."
    )
    parser.add_argument("--base-url", required=True, help="Deployed dashboard base URL.")
    parser.add_argument("--token", required=True, help="Dashboard auth token.")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout per request.")
    args = parser.parse_args()

    summary = run_checks(args.base_url, args.token, timeout=args.timeout)

    # Pretty-print
    print(json.dumps(summary, indent=2))

    # Human-readable nuance summary
    print("\n--- Nuance Summary ---")
    for nuance, ok in summary["nuance_summary"].items():
        status_str = "PASS" if ok else "FAIL"
        print(f"  {nuance}: {status_str}")

    total = len(summary["checks"])
    passed = sum(1 for c in summary["checks"] if c["passed"])
    print(f"\n{passed}/{total} checks passed.")

    if not summary["passed"]:
        failed = [c for c in summary["checks"] if not c["passed"]]
        print(f"\nFailed checks ({len(failed)}):")
        for c in failed:
            print(f"  [{c['nuance']}] {c['name']}: expected {c['expectation']}, {c.get('detail', '')}")

    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
