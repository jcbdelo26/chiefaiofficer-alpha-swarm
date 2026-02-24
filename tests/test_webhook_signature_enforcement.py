#!/usr/bin/env python3
"""
Webhook signature enforcement tests for non-API webhook endpoints.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _build_client(router) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_instantly_webhook_requires_valid_signature_in_strict_mode(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    monkeypatch.setenv("INSTANTLY_WEBHOOK_SECRET", "instantly-secret")
    monkeypatch.delenv("WEBHOOK_BEARER_TOKEN", raising=False)

    from webhooks.instantly_webhook import router

    client = _build_client(router)
    body = json.dumps(
        {"data": {"lead_email": "lead@example.com", "campaign_id": "camp_1"}}
    ).encode("utf-8")

    missing_sig = client.post(
        "/webhooks/instantly/open",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    invalid_sig = client.post(
        "/webhooks/instantly/open",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Instantly-Signature": "sha256=invalid",
        },
    )
    valid_sig = client.post(
        "/webhooks/instantly/open",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Instantly-Signature": _sign("instantly-secret", body),
        },
    )

    assert missing_sig.status_code == 401
    assert invalid_sig.status_code == 401
    assert valid_sig.status_code == 200


def test_heyreach_webhook_requires_valid_signature_in_strict_mode(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    monkeypatch.setenv("HEYREACH_WEBHOOK_SECRET", "heyreach-secret")

    from webhooks.heyreach_webhook import router

    client = _build_client(router)
    body = json.dumps({"eventType": "UNKNOWN", "email": "lead@example.com"}).encode("utf-8")

    missing_sig = client.post(
        "/webhooks/heyreach",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    valid_sig = client.post(
        "/webhooks/heyreach",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-HeyReach-Signature": _sign("heyreach-secret", body),
        },
    )

    assert missing_sig.status_code == 401
    assert valid_sig.status_code == 200


def test_heyreach_webhook_allows_unsigned_payload_when_non_strict(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "false")
    monkeypatch.delenv("HEYREACH_WEBHOOK_SECRET", raising=False)

    from webhooks.heyreach_webhook import router

    client = _build_client(router)
    response = client.post("/webhooks/heyreach", json={"eventType": "UNKNOWN"})
    assert response.status_code == 200


def test_heyreach_webhook_strict_rejects_unsigned_without_allowlist(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    monkeypatch.delenv("HEYREACH_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("HEYREACH_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("HEYREACH_UNSIGNED_ALLOWLIST", raising=False)

    from webhooks.heyreach_webhook import router

    client = _build_client(router)
    response = client.post("/webhooks/heyreach", json={"eventType": "UNKNOWN"})
    assert response.status_code == 503


def test_heyreach_webhook_strict_allows_unsigned_with_allowlist(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    monkeypatch.delenv("HEYREACH_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("HEYREACH_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("HEYREACH_UNSIGNED_ALLOWLIST", "true")

    from webhooks.heyreach_webhook import router

    client = _build_client(router)
    response = client.post("/webhooks/heyreach", json={"eventType": "UNKNOWN"})
    assert response.status_code == 200


def test_heyreach_webhook_strict_accepts_bearer_token(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    monkeypatch.delenv("HEYREACH_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("HEYREACH_UNSIGNED_ALLOWLIST", raising=False)
    monkeypatch.setenv("HEYREACH_BEARER_TOKEN", "heyreach-bearer-token")

    from webhooks.heyreach_webhook import router

    client = _build_client(router)
    body = json.dumps({"eventType": "UNKNOWN", "email": "lead@example.com"}).encode("utf-8")

    no_auth = client.post(
        "/webhooks/heyreach",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    good_bearer = client.post(
        "/webhooks/heyreach",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer heyreach-bearer-token",
        },
    )

    assert no_auth.status_code == 401
    assert good_bearer.status_code == 200


def test_rb2b_and_clay_fail_closed_when_strict_without_secret(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")

    from webhooks.rb2b_webhook import router
    monkeypatch.setenv("RB2B_WEBHOOK_SECRET", "")
    monkeypatch.setenv("CLAY_WEBHOOK_SECRET", "")
    monkeypatch.delenv("WEBHOOK_BEARER_TOKEN", raising=False)

    client = _build_client(router)
    rb2b_resp = client.post("/webhooks/rb2b", json={"visitor_id": "v_1"})
    clay_resp = client.post("/webhooks/clay", json={"visitor_id": "v_1"})

    assert rb2b_resp.status_code == 503
    assert clay_resp.status_code == 503


def test_rb2b_health_reports_signature_policy(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    monkeypatch.setenv("RB2B_WEBHOOK_SECRET", "rb2b-secret")

    from webhooks.rb2b_webhook import router

    client = _build_client(router)
    response = client.get("/webhooks/rb2b/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["secret_configured"] is True
    assert payload["signature_strict_mode"] is True


def test_instantly_webhook_accepts_bearer_token_when_no_hmac(monkeypatch):
    """Bearer token fallback: no HMAC secret, but bearer token configured."""
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    monkeypatch.delenv("INSTANTLY_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("WEBHOOK_BEARER_TOKEN", "test-bearer-token-48chars-placeholder-value-ok")

    from webhooks.instantly_webhook import router

    client = _build_client(router)
    body = json.dumps(
        {"data": {"lead_email": "lead@example.com", "campaign_id": "camp_1"}}
    ).encode("utf-8")

    # No auth header → 401
    no_auth = client.post(
        "/webhooks/instantly/open",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    # Wrong bearer token → 401
    bad_bearer = client.post(
        "/webhooks/instantly/open",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer wrong-token",
        },
    )
    # Correct bearer token → 200
    good_bearer = client.post(
        "/webhooks/instantly/open",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer test-bearer-token-48chars-placeholder-value-ok",
        },
    )

    assert no_auth.status_code == 401
    assert bad_bearer.status_code == 401
    assert good_bearer.status_code == 200


def test_clay_webhook_accepts_bearer_token_when_no_hmac(monkeypatch):
    """Bearer token fallback for Clay webhook."""
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "true")
    monkeypatch.delenv("CLAY_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("WEBHOOK_BEARER_TOKEN", "test-bearer-token-48chars-placeholder-value-ok")

    from webhooks.rb2b_webhook import router

    client = _build_client(router)

    # No auth → 401
    no_auth = client.post("/webhooks/clay", json={"visitor_id": "v_1"})
    # Good bearer → 200
    good_bearer = client.post(
        "/webhooks/clay",
        json={"visitor_id": "v_1"},
        headers={"Authorization": "Bearer test-bearer-token-48chars-placeholder-value-ok"},
    )

    assert no_auth.status_code == 401
    assert good_bearer.status_code == 200


def test_heyreach_webhook_allows_through_non_strict_no_bearer(monkeypatch):
    """HeyReach has no custom header support — falls through in non-strict."""
    monkeypatch.setenv("WEBHOOK_SIGNATURE_REQUIRED", "false")
    monkeypatch.delenv("HEYREACH_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("WEBHOOK_BEARER_TOKEN", raising=False)

    from webhooks.heyreach_webhook import router

    client = _build_client(router)
    response = client.post("/webhooks/heyreach", json={"eventType": "UNKNOWN"})
    assert response.status_code == 200
