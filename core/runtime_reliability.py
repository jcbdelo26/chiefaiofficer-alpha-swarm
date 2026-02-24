#!/usr/bin/env python3
"""
Runtime reliability helpers for Redis, Inngest, and webhook signature policy.

This module provides:
- deterministic runtime dependency health checks
- env bootstrap defaults for Redis/Inngest/webhook reliability settings
- safe .env upsert helpers for automation scripts
"""

from __future__ import annotations

import importlib.util
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

try:
    import redis
except Exception:  # pragma: no cover - optional dependency in some test envs
    redis = None

_WEBHOOK_SECRET_ENV_BY_PROVIDER = {
    "instantly": "INSTANTLY_WEBHOOK_SECRET",
    "heyreach": "HEYREACH_WEBHOOK_SECRET",
    "rb2b": "RB2B_WEBHOOK_SECRET",
    "clay": "CLAY_WEBHOOK_SECRET",
}

# Providers that support custom HTTP headers (can use bearer token as fallback)
_BEARER_CAPABLE_PROVIDERS = {"instantly", "clay"}

# Providers that have NO auth mechanism (no HMAC, no custom headers)
_NO_AUTH_PROVIDERS = {"heyreach"}
_UNSIGNED_PROVIDER_ALLOWLIST_ENV = {
    "heyreach": "HEYREACH_UNSIGNED_ALLOWLIST",
}


def to_bool(value: Optional[str], default: bool = False) -> bool:
    """Parse a permissive bool string."""
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_mode(value: Optional[str]) -> str:
    mode = (value or "development").strip().lower()
    if mode not in {"development", "staging", "production"}:
        return "development"
    return mode


def get_runtime_env_defaults(mode: str) -> Dict[str, str]:
    """Return deterministic Redis/Inngest defaults for the target mode."""
    normalized_mode = normalize_mode(mode)
    required_default = "true" if normalized_mode in {"staging", "production"} else "false"
    trace_suffix = "" if normalized_mode == "production" else f"_{normalized_mode}"
    ttl_default = "7200" if normalized_mode == "production" else "3600"

    return {
        "ENVIRONMENT": normalized_mode,
        "REDIS_URL": "redis://localhost:6379/0",
        "REDIS_REQUIRED": required_default,
        "REDIS_MAX_CONNECTIONS": "50",
        "STATE_BACKEND": "redis" if normalized_mode in {"staging", "production"} else "file",
        "STATE_REDIS_PREFIX": "caio",
        "STATE_DUAL_READ_ENABLED": "true",
        "STATE_FILE_FALLBACK_WRITE": "true",
        "RATE_LIMIT_REDIS_NAMESPACE": f"caio:{normalized_mode}:ratelimit",
        "CONTEXT_REDIS_PREFIX": f"caio:{normalized_mode}:context",
        "CONTEXT_STATE_TTL_SECONDS": ttl_default,
        "INNGEST_SIGNING_KEY": "",
        "INNGEST_EVENT_KEY": "",
        "INNGEST_REQUIRED": required_default,
        "INNGEST_APP_ID": f"caio-alpha-swarm-{normalized_mode}",
        "INNGEST_APP_NAME": "CAIO Alpha Swarm",
        "INNGEST_WEBHOOK_URL": "http://localhost:8080/inngest",
        "WEBHOOK_SIGNATURE_REQUIRED": required_default,
        "INSTANTLY_WEBHOOK_SECRET": "",
        "HEYREACH_WEBHOOK_SECRET": "",
        "HEYREACH_UNSIGNED_ALLOWLIST": "false",
        "RB2B_WEBHOOK_SECRET": "",
        "CLAY_WEBHOOK_SECRET": "",
        "TRACE_ENVELOPE_FILE": f".hive-mind/traces/tool_trace_envelopes{trace_suffix}.jsonl",
        "TRACE_ENVELOPE_ENABLED": "true",
        "TRACE_RETENTION_DAYS": "30",
        "TRACE_CLEANUP_ENABLED": "true",
        "DASHBOARD_AUTH_TOKEN": "",
        "DASHBOARD_AUTH_STRICT": required_default,
        "DASHBOARD_AUTH_ALLOWLIST": "/api/health,/api/health/ready,/api/health/live",
        "CORS_ALLOWED_ORIGINS": "http://localhost:8080,http://127.0.0.1:8080",
    }


def _redis_health(*, check_connections: bool) -> Dict[str, Any]:
    required = to_bool(os.getenv("REDIS_REQUIRED"), default=False)
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    configured = bool(redis_url)

    result: Dict[str, Any] = {
        "name": "redis",
        "required": required,
        "configured": configured,
        "package_available": redis is not None,
        "connected": False,
        "latency_ms": None,
        "status": "not_configured" if not configured else "configured",
        "ready": True,
        "message": "",
    }

    if not configured:
        result["ready"] = not required
        if required:
            result["status"] = "unhealthy"
            result["message"] = "REDIS_REQUIRED=true but REDIS_URL is not set"
        else:
            result["message"] = "REDIS_URL not set; running without Redis"
        return result

    if redis is None:
        result["ready"] = not required
        result["status"] = "unhealthy" if required else "degraded"
        result["message"] = "redis package not installed"
        return result

    if not check_connections:
        result["status"] = "configured"
        result["message"] = "Redis configured (connection check skipped)"
        return result

    start = time.time()
    try:
        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        result["connected"] = True
        result["latency_ms"] = round((time.time() - start) * 1000, 2)
        result["status"] = "healthy"
        result["message"] = "Redis ping succeeded"
        return result
    except Exception as exc:
        result["ready"] = not required
        result["status"] = "unhealthy" if required else "degraded"
        result["message"] = f"Redis ping failed: {exc}"
        result["latency_ms"] = round((time.time() - start) * 1000, 2)
        return result


def _inngest_health(*, check_connections: bool, route_mounted: Optional[bool]) -> Dict[str, Any]:
    required = to_bool(os.getenv("INNGEST_REQUIRED"), default=False)
    signing_key = (os.getenv("INNGEST_SIGNING_KEY") or "").strip()
    event_key = (os.getenv("INNGEST_EVENT_KEY") or "").strip()
    keys_present = bool(signing_key and event_key)
    package_available = importlib.util.find_spec("inngest") is not None

    result: Dict[str, Any] = {
        "name": "inngest",
        "required": required,
        "configured": keys_present,
        "package_available": package_available,
        "keys_present": keys_present,
        "route_mounted": route_mounted,
        "app_id": (os.getenv("INNGEST_APP_ID") or "").strip(),
        "webhook_url": (os.getenv("INNGEST_WEBHOOK_URL") or "").strip(),
        "status": "not_configured" if not keys_present else "configured",
        "ready": True,
        "message": "",
    }

    if not keys_present:
        result["ready"] = not required
        if required:
            result["status"] = "unhealthy"
            result["message"] = "INNGEST_REQUIRED=true but signing/event keys are missing"
        else:
            result["message"] = "Inngest keys not configured"
        return result

    if not package_available:
        result["ready"] = not required
        result["status"] = "unhealthy" if required else "degraded"
        result["message"] = "inngest package not installed"
        return result

    if route_mounted is False:
        result["ready"] = not required
        result["status"] = "unhealthy" if required else "degraded"
        result["message"] = "Inngest route is not mounted at /inngest"
        return result

    if route_mounted is None:
        result["status"] = "configured_unverified"
        result["message"] = "Inngest configured; route mount not verified in this context"
        return result

    if not check_connections:
        result["status"] = "configured"
        result["message"] = "Inngest keys and route configured (connection check skipped)"
        return result

    result["status"] = "healthy"
    result["message"] = "Inngest keys present and route mounted"
    return result


def _webhook_signature_health() -> Dict[str, Any]:
    required_raw = (os.getenv("WEBHOOK_SIGNATURE_REQUIRED") or "").strip()
    if required_raw:
        required = to_bool(required_raw, default=False)
    else:
        environment = (os.getenv("ENVIRONMENT") or "").strip().lower()
        required = environment in {"staging", "production"}

    bearer_token_set = bool((os.getenv("WEBHOOK_BEARER_TOKEN") or "").strip())

    # A provider is "authed" if:
    # 1. Its HMAC secret is configured, OR
    # 2. It supports custom headers AND the bearer token is configured, OR
    # 3. It has no auth mechanism at all (e.g. HeyReach) — accepted as-is
    provider_auth = {}
    for provider, secret_env in _WEBHOOK_SECRET_ENV_BY_PROVIDER.items():
        has_secret = bool((os.getenv(secret_env) or "").strip())
        has_bearer = provider in _BEARER_CAPABLE_PROVIDERS and bearer_token_set
        no_auth_available = provider in _NO_AUTH_PROVIDERS
        unsigned_allowlist_env = _UNSIGNED_PROVIDER_ALLOWLIST_ENV.get(provider)
        unsigned_allowlisted = (
            no_auth_available
            and bool(unsigned_allowlist_env)
            and to_bool(os.getenv(unsigned_allowlist_env), default=False)
        )
        # Strict mode requires explicit allowlist for unsigned providers.
        unsigned_allowed = no_auth_available and (not required or unsigned_allowlisted)
        provider_auth[provider] = {
            "hmac": has_secret,
            "bearer": has_bearer,
            "no_auth_provider": no_auth_available,
            "unsigned_allowlist_env": unsigned_allowlist_env,
            "unsigned_allowlisted": unsigned_allowlisted,
            "authed": has_secret or has_bearer or unsigned_allowed,
        }

    unauthed = [p for p, info in provider_auth.items() if not info["authed"]]
    all_authed = not unauthed

    if all_authed:
        status = "healthy"
        message = "Webhook auth configured for all providers"
    elif required:
        status = "unhealthy"
        message = (
            "WEBHOOK_SIGNATURE_REQUIRED=true but no auth for: "
            + ", ".join(unauthed)
        )
    else:
        status = "not_configured"
        message = "Webhook auth is optional in current mode"

    return {
        "name": "webhooks",
        "required": required,
        "configured": all_authed,
        "ready": all_authed or not required,
        "status": status,
        "message": message,
        "provider_auth": provider_auth,
        "bearer_token_configured": bearer_token_set,
        "unauthed_providers": unauthed,
    }


def get_runtime_dependency_health(
    *,
    check_connections: bool = True,
    inngest_route_mounted: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Return Redis/Inngest/webhook runtime health with strict required-dependency semantics.
    """
    redis_result = _redis_health(check_connections=check_connections)
    inngest_result = _inngest_health(
        check_connections=check_connections,
        route_mounted=inngest_route_mounted,
    )
    webhook_result = _webhook_signature_health()

    failures = []
    if redis_result["required"] and not redis_result["ready"]:
        failures.append(f"redis: {redis_result['message']}")
    if inngest_result["required"] and not inngest_result["ready"]:
        failures.append(f"inngest: {inngest_result['message']}")
    if webhook_result["required"] and not webhook_result["ready"]:
        failures.append(f"webhooks: {webhook_result['message']}")

    ready = len(failures) == 0
    status = "ready" if ready else "not_ready"

    return {
        "status": status,
        "ready": ready,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "dependencies": {
            "redis": redis_result,
            "inngest": inngest_result,
            "webhooks": webhook_result,
        },
        "required_failures": failures,
    }


def merge_runtime_env_values(
    *,
    mode: str,
    existing: Optional[Mapping[str, str]] = None,
    overrides: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """
    Build env values for runtime reliability, preserving existing values unless overridden.
    """
    existing_values: Mapping[str, str] = existing or {}
    override_values: Mapping[str, str] = overrides or {}
    defaults = get_runtime_env_defaults(mode)

    merged: Dict[str, str] = {}
    for key, default_value in defaults.items():
        if key in override_values and override_values[key] is not None:
            merged[key] = str(override_values[key])
        elif key in existing_values and existing_values[key] not in (None, ""):
            merged[key] = str(existing_values[key])
        else:
            merged[key] = default_value
    return merged


def apply_env_updates(content: str, updates: Mapping[str, str]) -> Tuple[str, Dict[str, Any]]:
    """
    Apply KEY=VALUE updates to .env content and append missing keys as one block.
    """
    lines = content.splitlines(keepends=True)
    index_by_key: Dict[str, int] = {}

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates and key not in index_by_key:
            index_by_key[key] = idx

    updated_keys = []
    appended_keys = []

    for key, value in updates.items():
        new_line = f"{key}={value}\n"
        if key in index_by_key:
            lines[index_by_key[key]] = new_line
            updated_keys.append(key)
        else:
            appended_keys.append(key)

    if appended_keys:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append("\n# =============================================================================\n")
        lines.append("# RUNTIME RELIABILITY (Redis + Inngest)\n")
        lines.append("# =============================================================================\n")
        for key in appended_keys:
            lines.append(f"{key}={updates[key]}\n")

    return "".join(lines), {
        "updated_keys": sorted(updated_keys),
        "appended_keys": sorted(appended_keys),
        "total_keys": len(updates),
    }


def upsert_env_file(env_path: Path, updates: Mapping[str, str]) -> Dict[str, Any]:
    """
    Upsert reliability keys into an env file.
    """
    path = Path(env_path)
    original = ""
    if path.exists():
        original = path.read_text(encoding="utf-8")

    new_content, meta = apply_env_updates(original, updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_content, encoding="utf-8")
    return meta
