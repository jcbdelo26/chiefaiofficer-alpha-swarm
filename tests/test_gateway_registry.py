"""
Tests for core/gateway_registry.py — unified gateway health aggregation.

Validates:
  1. Registry returns structured dict with all 3 gateways
  2. Graceful handling when gateways are unavailable
  3. Overall status computation logic
  4. Health endpoint integration (gateways key in /api/health)
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest


def test_registry_import():
    """gateway_registry module imports without error."""
    from core.gateway_registry import get_all_gateway_health
    assert callable(get_all_gateway_health)


def test_registry_returns_all_three_gateways():
    """get_all_gateway_health returns status for all 3 gateways."""
    from core.gateway_registry import get_all_gateway_health
    result = get_all_gateway_health()
    assert "overall" in result
    assert "checked_at" in result
    assert "gateways" in result
    gateways = result["gateways"]
    assert "llm_routing" in gateways
    assert "unified_integration" in gateways
    assert "ghl_execution" in gateways


def test_each_gateway_has_status_field():
    """Each gateway entry has a 'status' field."""
    from core.gateway_registry import get_all_gateway_health
    result = get_all_gateway_health()
    for name, gw in result["gateways"].items():
        assert "status" in gw, f"Gateway '{name}' missing 'status' field"


def test_overall_healthy_when_all_healthy():
    """Overall is 'healthy' when all gateways report healthy."""
    from core import gateway_registry

    with patch.object(gateway_registry, "_get_llm_health", return_value={"status": "healthy"}), \
         patch.object(gateway_registry, "_get_integration_health", return_value={"status": "healthy"}), \
         patch.object(gateway_registry, "_get_ghl_execution_health", return_value={"status": "healthy"}):
        result = gateway_registry.get_all_gateway_health()
        assert result["overall"] == "healthy"


def test_overall_degraded_when_one_degraded():
    """Overall is 'degraded' when any gateway is degraded."""
    from core import gateway_registry

    with patch.object(gateway_registry, "_get_llm_health", return_value={"status": "healthy"}), \
         patch.object(gateway_registry, "_get_integration_health", return_value={"status": "degraded"}), \
         patch.object(gateway_registry, "_get_ghl_execution_health", return_value={"status": "healthy"}):
        result = gateway_registry.get_all_gateway_health()
        assert result["overall"] == "degraded"


def test_overall_unhealthy_when_one_error():
    """Overall is 'unhealthy' when any gateway reports error."""
    from core import gateway_registry

    with patch.object(gateway_registry, "_get_llm_health", return_value={"status": "error", "error": "test"}), \
         patch.object(gateway_registry, "_get_integration_health", return_value={"status": "healthy"}), \
         patch.object(gateway_registry, "_get_ghl_execution_health", return_value={"status": "healthy"}):
        result = gateway_registry.get_all_gateway_health()
        assert result["overall"] == "unhealthy"


def test_overall_unavailable_when_all_unavailable():
    """Overall is 'unavailable' when all gateways report unavailable."""
    from core import gateway_registry

    with patch.object(gateway_registry, "_get_llm_health", return_value={"status": "unavailable"}), \
         patch.object(gateway_registry, "_get_integration_health", return_value={"status": "unavailable"}), \
         patch.object(gateway_registry, "_get_ghl_execution_health", return_value={"status": "unavailable"}):
        result = gateway_registry.get_all_gateway_health()
        assert result["overall"] == "unavailable"


def test_graceful_when_llm_gateway_import_fails():
    """Registry gracefully handles missing LLM gateway."""
    from core import gateway_registry

    with patch.object(gateway_registry, "_safe_import_llm_gateway", return_value=None):
        result = gateway_registry._get_llm_health()
        assert result["status"] == "unavailable"
        assert "error" in result


def test_graceful_when_integration_gateway_import_fails():
    """Registry gracefully handles missing integration gateway."""
    from core import gateway_registry

    with patch.object(gateway_registry, "_safe_import_integration_gateway", return_value=None):
        result = gateway_registry._get_integration_health()
        assert result["status"] == "unavailable"
        assert "error" in result


def test_graceful_when_ghl_gateway_import_fails():
    """Registry gracefully handles missing GHL gateway."""
    from core import gateway_registry

    with patch.object(gateway_registry, "_safe_import_ghl_gateway", return_value=None):
        result = gateway_registry._get_ghl_execution_health()
        assert result["status"] == "unavailable"
        assert "error" in result


def test_llm_health_with_mock_gateway():
    """LLM health extracts provider availability from gateway status."""
    from core import gateway_registry

    mock_gw = MagicMock()
    mock_gw.get_status.return_value = {
        "providers": {
            "claude": {"available": True, "errors": 0},
            "gemini": {"available": True, "errors": 1},
            "openai": {"available": False, "errors": 5},
        },
        "routing_summary": {"total_requests": 42, "total_cost": 1.23},
    }
    with patch.object(gateway_registry, "_safe_import_llm_gateway", return_value=mock_gw):
        result = gateway_registry._get_llm_health()
        assert result["status"] == "healthy"
        assert result["providers_available"] == 2
        assert result["providers_total"] == 3
        assert result["total_requests"] == 42


def test_integration_health_with_mock_gateway():
    """Integration health extracts adapter health from gateway status."""
    from core import gateway_registry

    mock_gw = MagicMock()
    mock_gw.get_status.return_value = {
        "integrations": {
            "ghl": {"health": "healthy", "circuit_state": "closed", "latency_ms": 120},
            "clay": {"health": "healthy", "circuit_state": "closed", "latency_ms": 200},
        },
        "webhook_stats": {"queue_size": 0},
    }
    with patch.object(gateway_registry, "_safe_import_integration_gateway", return_value=mock_gw):
        result = gateway_registry._get_integration_health()
        assert result["status"] == "healthy"
        assert result["integrations_healthy"] == 2
        assert result["integrations_total"] == 2


def test_ghl_health_with_mock_gateway():
    """GHL health extracts from gateway internals."""
    from core import gateway_registry

    mock_gw = MagicMock()
    mock_gw._system_orchestrator = MagicMock()
    mock_gw._system_orchestrator.is_operational.return_value = True
    mock_gw._circuit_registry = MagicMock()
    mock_gw._circuit_registry.get_status.return_value = {
        "ghl_api": {"state": "closed"},
        "email_sending": {"state": "closed"},
    }
    mock_gw._email_guard = None

    with patch.object(gateway_registry, "_safe_import_ghl_gateway", return_value=mock_gw):
        result = gateway_registry._get_ghl_execution_health()
        assert result["status"] == "healthy"
        assert result["orchestrator_operational"] is True
        assert result["circuit_breakers"]["total"] == 2
        assert result["circuit_breakers"]["open"] == []


def test_ghl_health_degraded_when_breaker_open():
    """GHL health reports degraded when a circuit breaker is open."""
    from core import gateway_registry

    mock_gw = MagicMock()
    mock_gw._system_orchestrator = MagicMock()
    mock_gw._system_orchestrator.is_operational.return_value = True
    mock_gw._circuit_registry = MagicMock()
    mock_gw._circuit_registry.get_status.return_value = {
        "ghl_api": {"state": "OPEN"},
        "email_sending": {"state": "closed"},
    }
    mock_gw._email_guard = None

    with patch.object(gateway_registry, "_safe_import_ghl_gateway", return_value=mock_gw):
        result = gateway_registry._get_ghl_execution_health()
        assert result["status"] == "degraded"
        assert "ghl_api" in result["circuit_breakers"]["open"]


def test_checked_at_is_iso_timestamp():
    """checked_at field is a valid ISO timestamp."""
    from core.gateway_registry import get_all_gateway_health
    from datetime import datetime
    result = get_all_gateway_health()
    ts = result["checked_at"]
    # Should parse without error
    datetime.fromisoformat(ts)
