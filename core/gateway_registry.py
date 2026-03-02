"""
Gateway Registry - Aggregated health for all API gateways.

Provides a unified view across the 3 independent gateways:
  1. LLM Routing Gateway (Claude, Gemini, OpenAI)
  2. Unified Integration Gateway (GHL, Calendar, Gmail, Clay, LinkedIn, Supabase, Zoom)
  3. GHL Execution Gateway (GoHighLevel send path, guards, audit)

Usage:
  from core.gateway_registry import get_all_gateway_health
  status = get_all_gateway_health()

Author: Chris Daigle (Chiefaiofficer.com)
Version: 1.0.0
Date: 2026-03-02
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("caio.gateway_registry")


def _safe_import_llm_gateway() -> Optional[Any]:
    """Import LLM routing gateway without hard dependency."""
    try:
        from core.llm_routing_gateway import get_llm_router
        return get_llm_router()
    except Exception:
        return None


def _safe_import_integration_gateway() -> Optional[Any]:
    """Import unified integration gateway without hard dependency."""
    try:
        from core.unified_integration_gateway import get_gateway
        return get_gateway()
    except Exception:
        return None


def _safe_import_ghl_gateway() -> Optional[Any]:
    """Import GHL execution gateway without hard dependency."""
    try:
        from core.ghl_execution_gateway import get_gateway
        return get_gateway()
    except Exception:
        return None


def _get_llm_health() -> Dict[str, Any]:
    """Extract health from LLM routing gateway."""
    gw = _safe_import_llm_gateway()
    if gw is None:
        return {"status": "unavailable", "error": "Gateway not loaded"}
    try:
        raw = gw.get_status()
        providers = raw.get("providers", {})
        available = sum(1 for p in providers.values() if p.get("available"))
        total = len(providers)
        return {
            "status": "healthy" if available > 0 else "degraded",
            "providers_available": available,
            "providers_total": total,
            "total_requests": raw.get("routing_summary", {}).get("total_requests", 0),
            "total_cost": raw.get("routing_summary", {}).get("total_cost", 0),
            "providers": {
                name: {"available": info.get("available", False), "errors": info.get("errors", 0)}
                for name, info in providers.items()
            },
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _get_integration_health() -> Dict[str, Any]:
    """Extract health from unified integration gateway."""
    gw = _safe_import_integration_gateway()
    if gw is None:
        return {"status": "unavailable", "error": "Gateway not loaded"}
    try:
        raw = gw.get_status()
        integrations = raw.get("integrations", {})
        healthy = sum(
            1 for info in integrations.values()
            if info.get("health") in ("healthy", "ok", "green")
        )
        total = len(integrations)
        return {
            "status": "healthy" if healthy == total else ("degraded" if healthy > 0 else "unhealthy"),
            "integrations_healthy": healthy,
            "integrations_total": total,
            "webhook_stats": raw.get("webhook_stats", {}),
            "integrations": {
                name: {
                    "health": info.get("health", "unknown"),
                    "circuit_state": info.get("circuit_state", "unknown"),
                    "latency_ms": info.get("latency_ms"),
                }
                for name, info in integrations.items()
            },
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _get_ghl_execution_health() -> Dict[str, Any]:
    """Extract health from GHL execution gateway."""
    gw = _safe_import_ghl_gateway()
    if gw is None:
        return {"status": "unavailable", "error": "Gateway not loaded"}
    try:
        # GHL gateway lacks structured get_status(); extract from internals
        result: Dict[str, Any] = {"status": "healthy"}

        # Check system orchestrator if available
        if hasattr(gw, "_system_orchestrator") and gw._system_orchestrator:
            orch = gw._system_orchestrator
            if hasattr(orch, "is_operational"):
                operational = orch.is_operational()
                result["orchestrator_operational"] = operational
                if not operational:
                    result["status"] = "degraded"

        # Check circuit breakers if available
        if hasattr(gw, "_circuit_registry") and gw._circuit_registry:
            reg = gw._circuit_registry
            if hasattr(reg, "get_status"):
                breaker_status = reg.get_status()
                open_breakers = [
                    name for name, info in breaker_status.items()
                    if isinstance(info, dict) and info.get("state") in ("open", "OPEN")
                ]
                result["circuit_breakers"] = {
                    "total": len(breaker_status),
                    "open": open_breakers,
                }
                if open_breakers:
                    result["status"] = "degraded"

        # Check email guard if available
        if hasattr(gw, "_email_guard") and gw._email_guard:
            guard = gw._email_guard
            if hasattr(guard, "get_status"):
                result["email_guard"] = guard.get_status()

        return result
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def get_all_gateway_health() -> Dict[str, Any]:
    """
    Aggregate health status from all 3 API gateways.

    Returns:
        Dict with per-gateway status and overall verdict.
    """
    gateways = {
        "llm_routing": _get_llm_health(),
        "unified_integration": _get_integration_health(),
        "ghl_execution": _get_ghl_execution_health(),
    }

    # Compute overall status
    statuses = [g.get("status", "unknown") for g in gateways.values()]
    if all(s == "healthy" for s in statuses):
        overall = "healthy"
    elif any(s in ("error", "unhealthy") for s in statuses):
        overall = "unhealthy"
    elif any(s == "degraded" for s in statuses):
        overall = "degraded"
    elif all(s == "unavailable" for s in statuses):
        overall = "unavailable"
    else:
        overall = "unknown"

    return {
        "overall": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "gateways": gateways,
    }
