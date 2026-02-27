#!/usr/bin/env python3
"""
Auth checks for Instantly dashboard control endpoints.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_client():
    from webhooks.instantly_webhook import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_instantly_control_endpoints_require_token_when_configured(monkeypatch):
    monkeypatch.setenv("DASHBOARD_AUTH_STRICT", "true")
    monkeypatch.setenv("DASHBOARD_AUTH_TOKEN", "webhook-test-token")

    client = _build_client()

    unauth = client.get("/api/instantly/dispatch-status")
    query_auth = client.get("/api/instantly/dispatch-status?token=webhook-test-token")
    header_auth = client.get(
        "/api/instantly/dispatch-status",
        headers={"X-Dashboard-Token": "webhook-test-token"},
    )

    assert unauth.status_code == 401
    assert query_auth.status_code == 200
    assert header_auth.status_code == 200


def test_instantly_control_endpoints_fail_closed_in_strict_without_configured_token(monkeypatch):
    monkeypatch.setenv("DASHBOARD_AUTH_STRICT", "true")
    monkeypatch.delenv("DASHBOARD_AUTH_TOKEN", raising=False)

    client = _build_client()
    response = client.get("/api/instantly/dispatch-status")

    assert response.status_code == 401


def test_instantly_legacy_token_bypass_removed(monkeypatch):
    monkeypatch.setenv("DASHBOARD_AUTH_STRICT", "true")
    monkeypatch.setenv("DASHBOARD_AUTH_TOKEN", "webhook-test-token")

    client = _build_client()
    legacy = client.get("/api/instantly/dispatch-status?token=caio-swarm-secret-2026")

    assert legacy.status_code == 401
