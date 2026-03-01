#!/usr/bin/env python3
"""
Tests for the dashboard login/session gate.

Verifies:
- Login page served correctly
- Login flow (success / failure / rate limiting)
- Logout clears session
- HTML pages redirect to /login without session
- API routes accept session cookie OR X-Dashboard-Token header
- Health endpoints remain public
- Static files remain accessible
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    """Set up env vars for consistent test behavior."""
    monkeypatch.setenv("DASHBOARD_AUTH_TOKEN", "test-secret-token-abc")
    monkeypatch.setenv("DASHBOARD_AUTH_STRICT", "true")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-xyz")
    monkeypatch.setenv("ENVIRONMENT", "testing")


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from dashboard.health_app import app
    return TestClient(app)


@pytest.fixture()
def authed_client(client):
    """Client with an active session (logged in)."""
    resp = client.post(
        "/login",
        data={"token": "test-secret-token-abc", "next": "/sales"},
        follow_redirects=False,
    )
    assert resp.status_code == 303, f"Login failed: {resp.status_code}"
    return client


# =====================================================================
# LOGIN PAGE
# =====================================================================


class TestLoginPage:
    def test_login_page_returns_200(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "Login" in resp.text
        assert 'name="token"' in resp.text

    def test_login_page_with_valid_session_redirects(self, authed_client):
        resp = authed_client.get("/login", follow_redirects=False)
        assert resp.status_code == 302
        assert "/sales" in resp.headers["location"]

    def test_login_page_preserves_next_param(self, client):
        resp = client.get("/login?next=/scorecard")
        assert resp.status_code == 200
        assert "/scorecard" in resp.text


# =====================================================================
# LOGIN SUBMIT
# =====================================================================


class TestLoginSubmit:
    def test_login_success_sets_session_and_redirects(self, client):
        resp = client.post(
            "/login",
            data={"token": "test-secret-token-abc", "next": "/sales"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/sales"
        # Session cookie should be set
        assert "caio_session" in resp.headers.get("set-cookie", "")

    def test_login_success_redirects_to_custom_next(self, client):
        resp = client.post(
            "/login",
            data={"token": "test-secret-token-abc", "next": "/scorecard"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/scorecard"

    def test_login_failure_shows_error(self, client):
        resp = client.post(
            "/login",
            data={"token": "wrong-token", "next": "/sales"},
        )
        assert resp.status_code == 200
        assert "Invalid token" in resp.text

    def test_login_sanitizes_next_url(self, client):
        resp = client.post(
            "/login",
            data={"token": "test-secret-token-abc", "next": "https://evil.com"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        # Should not redirect to external URL
        assert resp.headers["location"] == "/sales"

    def test_login_rate_limiting(self, client):
        from dashboard import health_app
        # Reset rate limiter
        health_app._LOGIN_FAIL_TRACKER.clear()

        # Make 5 failed attempts
        for _ in range(5):
            client.post("/login", data={"token": "wrong"})

        # 6th attempt should be rate-limited
        resp = client.post("/login", data={"token": "wrong"})
        assert resp.status_code == 429

        # Cleanup
        health_app._LOGIN_FAIL_TRACKER.clear()


# =====================================================================
# LOGOUT
# =====================================================================


class TestLogout:
    def test_logout_clears_session(self, authed_client):
        resp = authed_client.get("/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["location"]

        # After logout, dashboard pages should redirect to login
        resp2 = authed_client.get("/sales", follow_redirects=False)
        assert resp2.status_code == 302
        assert "/login" in resp2.headers["location"]


# =====================================================================
# HTML PAGE GATING
# =====================================================================


class TestHtmlPageGating:
    def test_sales_redirects_to_login_without_session(self, client):
        resp = client.get("/sales", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["location"]
        assert "next=" in resp.headers["location"]

    def test_scorecard_redirects_to_login_without_session(self, client):
        resp = client.get("/scorecard", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["location"]

    def test_leads_redirects_to_login_without_session(self, client):
        resp = client.get("/leads", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["location"]

    def test_root_redirects_to_login_without_session(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["location"]

    def test_sales_accessible_with_session(self, authed_client):
        resp = authed_client.get("/sales", follow_redirects=False)
        # Should serve the page (200) or redirect within the app, not to /login
        assert resp.status_code == 200 or (
            resp.status_code in (302, 307) and "/login" not in resp.headers.get("location", "")
        )

    def test_legacy_route_redirects_through_login(self, client):
        resp = client.get("/ChiefAIOfficer", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["location"]


# =====================================================================
# API ROUTE AUTH (DUAL: session cookie OR header token)
# =====================================================================


class TestApiAuth:
    def test_api_health_public_without_auth(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_api_health_ready_public(self, client):
        resp = client.get("/api/health/ready")
        assert resp.status_code == 200

    def test_api_protected_with_header_token(self, client):
        resp = client.get(
            "/api/pending-emails",
            headers={"X-Dashboard-Token": "test-secret-token-abc"},
        )
        # Should not be 401 (may be 200 or other status depending on data)
        assert resp.status_code != 401

    def test_api_protected_with_session_cookie(self, authed_client):
        resp = authed_client.get("/api/pending-emails")
        assert resp.status_code != 401

    def test_api_protected_without_auth_returns_401(self, client):
        resp = client.get("/api/pending-emails")
        assert resp.status_code == 401


# =====================================================================
# EXEMPT PATHS
# =====================================================================


class TestExemptPaths:
    def test_login_page_accessible_without_session(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_webhooks_accessible_without_session(self, client):
        # Webhook routes have their own auth (signature verification)
        resp = client.post(
            "/webhooks/rb2b",
            json={"test": True},
            follow_redirects=False,
        )
        # Should not redirect to login (may return 400/422/500 depending on payload)
        assert resp.status_code != 302 or "/login" not in resp.headers.get("location", "")
