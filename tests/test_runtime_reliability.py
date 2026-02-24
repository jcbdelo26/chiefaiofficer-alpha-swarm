#!/usr/bin/env python3
"""
Runtime reliability tests for Redis/Inngest bootstrap and health checks.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from core.runtime_reliability import (
    apply_env_updates,
    get_runtime_dependency_health,
    merge_runtime_env_values,
)


def _load_bootstrap_module():
    project_root = Path(__file__).resolve().parent.parent
    module_path = project_root / "scripts" / "bootstrap_runtime_reliability.py"
    spec = importlib.util.spec_from_file_location("bootstrap_runtime_reliability", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules["bootstrap_runtime_reliability"] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_dependency_health_optional_is_ready(monkeypatch):
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("INNGEST_REQUIRED", "false")
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "false")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("INNGEST_SIGNING_KEY", raising=False)
    monkeypatch.delenv("INNGEST_EVENT_KEY", raising=False)

    health = get_runtime_dependency_health(
        check_connections=False,
        inngest_route_mounted=False,
    )

    assert health["ready"] is True
    assert health["dependencies"]["redis"]["status"] == "not_configured"
    assert health["dependencies"]["inngest"]["status"] == "not_configured"


def test_runtime_dependency_health_required_missing_fails(monkeypatch):
    monkeypatch.setenv("REDIS_REQUIRED", "true")
    monkeypatch.setenv("INNGEST_REQUIRED", "true")
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "false")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("INNGEST_SIGNING_KEY", raising=False)
    monkeypatch.delenv("INNGEST_EVENT_KEY", raising=False)

    health = get_runtime_dependency_health(
        check_connections=False,
        inngest_route_mounted=False,
    )

    assert health["ready"] is False
    assert any(failure.startswith("redis:") for failure in health["required_failures"])
    assert any(failure.startswith("inngest:") for failure in health["required_failures"])


def test_runtime_dependency_health_webhooks_required_missing_fails(monkeypatch):
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("INNGEST_REQUIRED", "false")
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    monkeypatch.setenv("INSTANTLY_WEBHOOK_SECRET", "")
    monkeypatch.setenv("HEYREACH_WEBHOOK_SECRET", "")
    monkeypatch.setenv("RB2B_WEBHOOK_SECRET", "")
    monkeypatch.setenv("CLAY_WEBHOOK_SECRET", "")

    health = get_runtime_dependency_health(
        check_connections=False,
        inngest_route_mounted=False,
    )

    assert health["ready"] is False
    assert health["dependencies"]["webhooks"]["status"] == "unhealthy"
    assert any(failure.startswith("webhooks:") for failure in health["required_failures"])


def test_runtime_dependency_health_webhooks_required_with_secrets_passes(monkeypatch):
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("INNGEST_REQUIRED", "false")
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    monkeypatch.setenv("INSTANTLY_WEBHOOK_SECRET", "instantly-secret")
    monkeypatch.setenv("HEYREACH_WEBHOOK_SECRET", "heyreach-secret")
    monkeypatch.setenv("RB2B_WEBHOOK_SECRET", "rb2b-secret")
    monkeypatch.setenv("CLAY_WEBHOOK_SECRET", "clay-secret")

    health = get_runtime_dependency_health(
        check_connections=False,
        inngest_route_mounted=False,
    )

    assert health["ready"] is True
    assert health["dependencies"]["webhooks"]["status"] == "healthy"
    assert health["dependencies"]["webhooks"]["ready"] is True


def test_runtime_dependency_health_heyreach_unsigned_requires_explicit_allowlist(
    monkeypatch,
):
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("INNGEST_REQUIRED", "false")
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    monkeypatch.setenv("INSTANTLY_WEBHOOK_SECRET", "instantly-secret")
    monkeypatch.setenv("RB2B_WEBHOOK_SECRET", "rb2b-secret")
    monkeypatch.setenv("CLAY_WEBHOOK_SECRET", "clay-secret")
    monkeypatch.delenv("HEYREACH_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("HEYREACH_UNSIGNED_ALLOWLIST", raising=False)

    health = get_runtime_dependency_health(
        check_connections=False,
        inngest_route_mounted=False,
    )

    assert health["ready"] is False
    assert "heyreach" in health["dependencies"]["webhooks"]["unauthed_providers"]
    assert (
        health["dependencies"]["webhooks"]["provider_auth"]["heyreach"]["unsigned_allowlisted"]
        is False
    )

    monkeypatch.setenv("HEYREACH_UNSIGNED_ALLOWLIST", "true")
    allowlisted_health = get_runtime_dependency_health(
        check_connections=False,
        inngest_route_mounted=False,
    )

    assert allowlisted_health["ready"] is True
    assert (
        allowlisted_health["dependencies"]["webhooks"]["provider_auth"]["heyreach"][
            "unsigned_allowlisted"
        ]
        is True
    )


def test_runtime_dependency_health_heyreach_bearer_passes_without_allowlist(
    monkeypatch,
):
    monkeypatch.setenv("REDIS_REQUIRED", "false")
    monkeypatch.setenv("INNGEST_REQUIRED", "false")
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    monkeypatch.setenv("INSTANTLY_WEBHOOK_SECRET", "instantly-secret")
    monkeypatch.setenv("RB2B_WEBHOOK_SECRET", "rb2b-secret")
    monkeypatch.setenv("CLAY_WEBHOOK_SECRET", "clay-secret")
    monkeypatch.delenv("HEYREACH_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("HEYREACH_BEARER_TOKEN", "heyreach-bearer-token")
    monkeypatch.setenv("HEYREACH_UNSIGNED_ALLOWLIST", "false")

    health = get_runtime_dependency_health(
        check_connections=False,
        inngest_route_mounted=False,
    )

    assert health["ready"] is True
    heyreach = health["dependencies"]["webhooks"]["provider_auth"]["heyreach"]
    assert heyreach["hmac"] is False
    assert heyreach["bearer"] is True
    assert heyreach["bearer_env"] == "HEYREACH_BEARER_TOKEN"
    assert heyreach["unsigned_allowlisted"] is False
    assert heyreach["authed"] is True


def test_merge_runtime_env_values_respects_existing_and_overrides():
    merged = merge_runtime_env_values(
        mode="production",
        existing={
            "REDIS_URL": "redis://existing:6379/0",
            "CONTEXT_REDIS_PREFIX": "caio:custom:context",
        },
        overrides={
            "INNGEST_APP_ID": "custom-app-id",
        },
    )

    assert merged["REDIS_URL"] == "redis://existing:6379/0"
    assert merged["CONTEXT_REDIS_PREFIX"] == "caio:custom:context"
    assert merged["INNGEST_APP_ID"] == "custom-app-id"
    assert merged["REDIS_REQUIRED"] == "true"
    assert merged["INNGEST_REQUIRED"] == "true"


def test_apply_env_updates_replaces_and_appends():
    content = "ENVIRONMENT=development\nREDIS_REQUIRED=false\n"
    updated, meta = apply_env_updates(
        content,
        {
            "REDIS_REQUIRED": "true",
            "INNGEST_REQUIRED": "true",
        },
    )

    assert "REDIS_REQUIRED=true" in updated
    assert "INNGEST_REQUIRED=true" in updated
    assert "REDIS_REQUIRED" in meta["updated_keys"]
    assert "INNGEST_REQUIRED" in meta["appended_keys"]


def test_bootstrap_input_validation_blocks_placeholders():
    module = _load_bootstrap_module()

    errors = module._validate_bootstrap_inputs(
        {
            "REDIS_REQUIRED": "true",
            "REDIS_URL": "redis://localhost:6379/0",
            "INNGEST_REQUIRED": "true",
            "INNGEST_SIGNING_KEY": "your_key",
            "INNGEST_EVENT_KEY": "your_key",
        },
        allow_placeholders=False,
    )

    assert any("REDIS_URL points to localhost" in e for e in errors)
    assert any("placeholder values" in e for e in errors)


@pytest.mark.asyncio
async def test_readiness_probe_fails_when_runtime_required_missing(monkeypatch):
    from dashboard import health_app

    class DummyMonitor:
        def get_health_status(self):
            return {
                "integrations": {
                    "ghl": {"status": "healthy"},
                    "supabase": {"status": "healthy"},
                    "clay": {"status": "healthy"},
                }
            }

    monkeypatch.setattr(health_app, "get_health_monitor", lambda: DummyMonitor())
    monkeypatch.setattr(health_app, "INNGEST_ROUTE_MOUNTED", False)
    monkeypatch.setenv("REDIS_REQUIRED", "true")
    monkeypatch.setenv("INNGEST_REQUIRED", "true")
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "false")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("INNGEST_SIGNING_KEY", raising=False)
    monkeypatch.delenv("INNGEST_EVENT_KEY", raising=False)

    with pytest.raises(HTTPException) as exc:
        await health_app.readiness_probe()

    assert exc.value.status_code == 503
    assert "Runtime dependencies not ready" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_runtime_dependencies_endpoint_contract(monkeypatch):
    from dashboard import health_app

    monkeypatch.setattr(health_app, "INNGEST_ROUTE_MOUNTED", False)
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "false")
    payload = await health_app.get_runtime_dependencies(auth=True)

    assert "status" in payload
    assert "ready" in payload
    assert "dependencies" in payload
    assert "redis" in payload["dependencies"]
    assert "inngest" in payload["dependencies"]


def test_protected_api_endpoints_require_dashboard_token(monkeypatch):
    from dashboard import health_app

    monkeypatch.setenv("DASHBOARD_AUTH_TOKEN", "unit-test-token")
    monkeypatch.setenv("DASHBOARD_AUTH_STRICT", "true")
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "false")

    client = TestClient(health_app.app)

    unauth_status = client.get("/api/operator/status")
    unauth_trigger = client.post("/api/operator/trigger", json={"dry_run": True})
    health_ready = client.get("/api/health/ready")
    auth_status = client.get("/api/operator/status?token=unit-test-token")
    header_auth_status = client.get(
        "/api/operator/status",
        headers={"X-Dashboard-Token": "unit-test-token"},
    )
    preflight = client.options(
        "/api/operator/status",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert unauth_status.status_code == 401
    assert unauth_trigger.status_code == 401
    assert health_ready.status_code != 401
    assert auth_status.status_code != 401
    assert header_auth_status.status_code != 401
    assert preflight.status_code != 401


def test_query_token_can_be_disabled_while_header_token_remains_valid(monkeypatch):
    from dashboard import health_app

    monkeypatch.setenv("DASHBOARD_AUTH_TOKEN", "unit-test-token")
    monkeypatch.setenv("DASHBOARD_AUTH_STRICT", "true")
    monkeypatch.setenv("DASHBOARD_QUERY_TOKEN_ENABLED", "false")
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "false")

    client = TestClient(health_app.app)

    query_auth_status = client.get("/api/operator/status?token=unit-test-token")
    header_auth_status = client.get(
        "/api/operator/status",
        headers={"X-Dashboard-Token": "unit-test-token"},
    )
    runtime_deps_header = client.get(
        "/api/runtime/dependencies",
        headers={"X-Dashboard-Token": "unit-test-token"},
    )

    assert query_auth_status.status_code == 401
    assert header_auth_status.status_code != 401
    assert runtime_deps_header.status_code == 200
    payload = runtime_deps_header.json()
    assert payload.get("auth", {}).get("query_token_enabled") is False


def test_legacy_sales_routes_redirect_to_canonical_sales_dashboard():
    from dashboard import health_app

    client = TestClient(health_app.app)

    legacy_upper = client.get("/ChiefAIOfficer?token=abc123", follow_redirects=False)
    legacy_lower = client.get("/chiefaiofficer?token=abc123", follow_redirects=False)

    assert legacy_upper.status_code in {307, 308}
    assert legacy_lower.status_code in {307, 308}
    assert legacy_upper.headers.get("location") == "/sales?token=abc123"
    assert legacy_lower.headers.get("location") == "/sales?token=abc123"
