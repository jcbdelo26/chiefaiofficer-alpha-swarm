#!/usr/bin/env python3
"""
Tests for Unified Integration Gateway
======================================
"""

import pytest
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)

from core.unified_integration_gateway import (
    UnifiedIntegrationGateway,
    IntegrationAdapter,
    GHLAdapter,
    GoogleCalendarAdapter,
    GmailAdapter,
    ClayAdapter,
    LinkedInAdapter,
    SupabaseAdapter,
    ZoomAdapter,
    WebhookIngress,
    WebhookEvent,
    IntegrationStatus,
    RateLimitConfig,
    ExecutionResult,
    get_gateway
)


class TestIntegrationAdapters:
    """Test individual adapters."""
    
    def test_ghl_adapter_initialization(self):
        adapter = GHLAdapter()
        assert adapter.name == "ghl"
        assert adapter.rate_limits.per_day == 3000
        assert "send_email" in adapter.get_actions()
    
    def test_google_calendar_adapter_initialization(self):
        adapter = GoogleCalendarAdapter()
        assert adapter.name == "google_calendar"
        assert "create_event" in adapter.get_actions()
        assert "get_availability" in adapter.get_actions()
    
    def test_gmail_adapter_initialization(self):
        adapter = GmailAdapter()
        assert adapter.name == "gmail"
        assert "parse_thread" in adapter.get_actions()
    
    def test_clay_adapter_initialization(self):
        adapter = ClayAdapter()
        assert adapter.name == "clay"
        assert "enrich_contact" in adapter.get_actions()
    
    def test_linkedin_adapter_initialization(self):
        adapter = LinkedInAdapter()
        assert adapter.name == "linkedin"
        assert adapter.rate_limits.per_minute == 10  # Strict limit
    
    def test_supabase_adapter_initialization(self):
        adapter = SupabaseAdapter()
        assert adapter.name == "supabase"
        assert "query" in adapter.get_actions()
    
    def test_zoom_adapter_initialization(self):
        adapter = ZoomAdapter()
        assert adapter.name == "zoom"
        assert "create_meeting" in adapter.get_actions()
    
    @pytest.mark.asyncio
    async def test_adapter_execute(self):
        adapter = GHLAdapter()
        result = await adapter.execute("read_contact", {"contact_id": "123"})
        assert result["action"] == "read_contact"
        assert result["status"] == "executed"
    
    @pytest.mark.asyncio
    async def test_adapter_health_check(self):
        adapter = GHLAdapter()
        health = await adapter.health_check()
        assert health.status == IntegrationStatus.HEALTHY
        assert health.last_check is not None


class TestWebhookIngress:
    """Test webhook handling."""
    
    def test_register_handler(self):
        ingress = WebhookIngress()
        handler = AsyncMock()
        ingress.register_handler("ghl", "contact.created", handler)
        
        stats = ingress.get_stats()
        assert "ghl" in stats["registered_handlers"]
        assert "contact.created" in stats["registered_handlers"]["ghl"]
    
    def test_set_secret(self):
        ingress = WebhookIngress()
        ingress.set_secret("ghl", "test_secret")
        assert ingress._secrets["ghl"] == "test_secret"
    
    def test_validate_signature_no_secret(self):
        ingress = WebhookIngress()
        # No secret set - should pass
        assert ingress.validate_signature("ghl", b"test", "any") is True
    
    @pytest.mark.asyncio
    async def test_process_webhook(self):
        ingress = WebhookIngress()
        handler = AsyncMock()
        ingress.register_handler("ghl", "contact.created", handler)
        
        event = WebhookEvent(
            source="ghl",
            event_type="contact.created",
            payload={"id": "123"}
        )
        
        result = await ingress.process(event)
        assert result is True
        handler.assert_called_once_with({"id": "123"})
    
    @pytest.mark.asyncio
    async def test_process_unknown_webhook(self):
        ingress = WebhookIngress()
        
        event = WebhookEvent(
            source="unknown",
            event_type="unknown.event",
            payload={}
        )
        
        result = await ingress.process(event)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_wildcard_handler(self):
        ingress = WebhookIngress()
        handler = AsyncMock()
        ingress.register_handler("ghl", "*", handler)
        
        event = WebhookEvent(
            source="ghl",
            event_type="any.event",
            payload={"test": True}
        )
        
        result = await ingress.process(event)
        assert result is True


class TestUnifiedIntegrationGateway:
    """Test unified gateway."""
    
    def test_gateway_initialization(self):
        gateway = UnifiedIntegrationGateway()
        
        # Should have default adapters registered
        assert gateway.get_adapter("ghl") is not None
        assert gateway.get_adapter("google_calendar") is not None
        assert gateway.get_adapter("gmail") is not None
        assert gateway.get_adapter("clay") is not None
        assert gateway.get_adapter("linkedin") is not None
        assert gateway.get_adapter("supabase") is not None
        assert gateway.get_adapter("zoom") is not None
    
    def test_register_unregister_adapter(self):
        gateway = UnifiedIntegrationGateway()
        
        # Unregister
        gateway.unregister_adapter("zoom")
        assert gateway.get_adapter("zoom") is None
        
        # Re-register
        gateway.register_adapter(ZoomAdapter())
        assert gateway.get_adapter("zoom") is not None
    
    @pytest.mark.asyncio
    async def test_execute_success(self):
        gateway = UnifiedIntegrationGateway()
        
        result = await gateway.execute(
            integration="ghl",
            action="read_contact",
            params={"contact_id": "123"},
            agent="HUNTER"
        )
        
        assert result.success is True
        assert result.integration == "ghl"
        assert result.action == "read_contact"
        assert result.agent == "HUNTER"
        assert result.latency_ms > 0
    
    @pytest.mark.asyncio
    async def test_execute_unknown_integration(self):
        gateway = UnifiedIntegrationGateway()
        
        result = await gateway.execute(
            integration="unknown_service",
            action="test",
            params={},
            agent="HUNTER"
        )
        
        assert result.success is False
        assert "Unknown integration" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_high_risk_without_grounding(self):
        gateway = UnifiedIntegrationGateway()
        
        result = await gateway.execute(
            integration="ghl",
            action="send_email",
            params={"contact_id": "123", "subject": "Test"},
            agent="GATEKEEPER"  # Has permission
        )
        
        # Should fail without grounding evidence
        assert result.success is False
        assert "Guardrails blocked" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_with_grounding(self):
        gateway = UnifiedIntegrationGateway()
        
        result = await gateway.execute(
            integration="ghl",
            action="send_email",
            params={"contact_id": "123", "subject": "Test"},
            agent="GATEKEEPER",
            grounding_evidence={
                "source": "supabase",
                "data_id": "lead_123",
                "verified_at": datetime.utcnow().isoformat()
            }
        )
        
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_health_check_all(self):
        gateway = UnifiedIntegrationGateway()
        
        health = await gateway.health_check_all()
        
        assert "ghl" in health
        assert "google_calendar" in health
        assert all(h.status == IntegrationStatus.HEALTHY for h in health.values())
    
    def test_get_status(self):
        gateway = UnifiedIntegrationGateway()
        
        status = gateway.get_status()
        
        assert "integrations" in status
        assert "webhook_stats" in status
        assert "updated_at" in status
        assert len(status["integrations"]) == 7  # 7 default adapters
    
    def test_webhook_ingress_access(self):
        gateway = UnifiedIntegrationGateway()
        
        ingress = gateway.webhook_ingress
        assert isinstance(ingress, WebhookIngress)


class TestSingletonGateway:
    """Test singleton pattern."""
    
    def test_get_gateway_singleton(self):
        # Clear singleton
        import core.unified_integration_gateway as module
        module._gateway = None
        
        gateway1 = get_gateway()
        gateway2 = get_gateway()
        
        assert gateway1 is gateway2


class TestRateLimiting:
    """Test rate limiting."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self):
        gateway = UnifiedIntegrationGateway()
        
        # Get adapter with tight limits
        adapter = gateway.get_adapter("linkedin")
        
        # Make many requests within the last minute (LinkedIn has 10/min limit)
        import time
        now = time.time()
        adapter._request_times = [now - i for i in range(15)]  # 15 requests in last 15 seconds
        
        # Should be rate limited now
        allowed, reason = gateway._check_rate_limit(adapter)
        assert allowed is False
        assert "Rate limit exceeded" in reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
