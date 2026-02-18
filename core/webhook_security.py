#!/usr/bin/env python3
"""
Shared webhook signature enforcement helpers.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Dict, Optional

from fastapi import HTTPException


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def is_webhook_signature_strict_mode() -> bool:
    """
    Determine whether webhook endpoints must fail-closed without signatures.

    Priority:
    1) WEBHOOK_SIGNATURE_REQUIRED explicit boolean
    2) ENVIRONMENT in {staging, production}
    """
    explicit = (os.getenv("WEBHOOK_SIGNATURE_REQUIRED") or "").strip().lower()
    if explicit in _TRUE_VALUES:
        return True
    if explicit in _FALSE_VALUES:
        return False

    environment = (os.getenv("ENVIRONMENT") or "").strip().lower()
    return environment in {"staging", "production"}


def get_webhook_signature_status(
    secret_env: str, bearer_env: str = "WEBHOOK_BEARER_TOKEN"
) -> Dict[str, bool]:
    """Return strict/secret/bearer state for health endpoints."""
    return {
        "strict_mode": is_webhook_signature_strict_mode(),
        "secret_configured": bool((os.getenv(secret_env) or "").strip()),
        "bearer_configured": bool((os.getenv(bearer_env) or "").strip()),
    }


def _normalize_signature(signature: Optional[str]) -> str:
    value = (signature or "").strip()
    if not value:
        return ""

    lower = value.lower()
    for prefix in ("sha256=", "hmac-sha256="):
        if lower.startswith(prefix):
            return value[len(prefix):].strip()
    return value


def verify_hmac_sha256(raw_body: bytes, signature: Optional[str], secret: str) -> bool:
    """Verify HMAC-SHA256 signature against raw request body."""
    if not secret:
        return False

    normalized_signature = _normalize_signature(signature)
    if not normalized_signature:
        return False

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, normalized_signature)


def require_hmac_sha256_signature(
    *,
    raw_body: bytes,
    signature: Optional[str],
    provider: str,
    secret_env: str,
    header_name: str,
) -> None:
    """
    Enforce webhook signature checks with deterministic fail-closed behavior.

    - If secret missing:
      - strict mode -> 503 (misconfigured service)
      - non-strict  -> allow (development compatibility)
    - If secret configured:
      - missing/invalid signature -> 401
    """
    secret = (os.getenv(secret_env) or "").strip()
    strict_mode = is_webhook_signature_strict_mode()

    if not secret:
        if strict_mode:
            raise HTTPException(
                status_code=503,
                detail=f"{provider} webhook secret not configured ({secret_env})",
            )
        return

    if not _normalize_signature(signature):
        raise HTTPException(status_code=401, detail=f"Missing {header_name} header")

    if not verify_hmac_sha256(raw_body, signature, secret):
        raise HTTPException(status_code=401, detail="Invalid signature")


def require_webhook_auth(
    *,
    request,
    raw_body: bytes,
    provider: str,
    secret_env: str,
    signature_header: str,
    bearer_env: str = "WEBHOOK_BEARER_TOKEN",
) -> None:
    """
    Two-layer webhook auth: HMAC signature first, bearer token fallback.

    Priority:
    1. HMAC secret configured (secret_env) -> verify signature header
    2. Bearer token configured (bearer_env) -> verify Authorization header
    3. Neither configured + strict -> 503
    4. Neither configured + non-strict -> allow (dev compatibility)

    Use this instead of require_hmac_sha256_signature() for providers that
    don't support HMAC signing but do support custom headers (e.g. Instantly,
    Clay). Providers with no header support (HeyReach) fall through to
    layer 3/4.
    """
    hmac_secret = (os.getenv(secret_env) or "").strip()
    bearer_token = (os.getenv(bearer_env) or "").strip()
    strict = is_webhook_signature_strict_mode()

    # Layer 1: HMAC (if provider secret configured — e.g. RB2B)
    if hmac_secret:
        sig = _normalize_signature(request.headers.get(signature_header))
        if not sig:
            raise HTTPException(
                status_code=401, detail=f"Missing {signature_header} header"
            )
        if not verify_hmac_sha256(raw_body, request.headers.get(signature_header), hmac_secret):
            raise HTTPException(status_code=401, detail="Invalid signature")
        return

    # Layer 2: Bearer token (if configured — for Instantly, Clay)
    if bearer_token:
        auth = (request.headers.get("Authorization") or "").strip()
        if not auth.lower().startswith("bearer "):
            raise HTTPException(
                status_code=401,
                detail=f"Missing Authorization header for {provider} webhook",
            )
        token = auth[7:].strip()
        if not hmac.compare_digest(token, bearer_token):
            raise HTTPException(status_code=401, detail="Invalid bearer token")
        return

    # Layer 3: Nothing configured
    if strict:
        raise HTTPException(
            status_code=503,
            detail=f"{provider} webhook auth not configured ({secret_env} / {bearer_env})",
        )
    # Non-strict: allow through (dev mode)
