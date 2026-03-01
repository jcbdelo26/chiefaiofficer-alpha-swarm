#!/usr/bin/env python3
"""
Tests for Unified Guardrails System
===================================
Tests covering circuit breakers, rate limiting, permission matrix,
grounding validation, and action execution.
"""

import pytest
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.unified_guardrails import (
    UnifiedGuardrails,
    ActionType,
    RiskLevel,
    AgentName,
    GroundingEvidence,
    UnifiedRateLimiter,
    RateLimitConfig,
    ExponentialBackoff,
    HookSystem,
    PermissionsConfigLoader,
    get_permissions_config,
    ACTION_RISK_LEVELS,
    AGENT_PERMISSIONS,
    BLOCKED_ACTIONS,
    require_grounding,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def guardrails(tmp_path):
    """Create a fresh guardrails instance with temp storage."""
    return UnifiedGuardrails(storage_path=tmp_path)


@pytest.fixture
def rate_limiter(tmp_path):
    """Create a fresh rate limiter with temp storage."""
    return UnifiedRateLimiter(tmp_path / "rate_limits.json")


@pytest.fixture
def valid_grounding():
    """Valid grounding evidence."""
    return {
        "source": "supabase",
        "data_id": "lead_123",
        "verified_at": datetime.now(timezone.utc).isoformat()
    }


@pytest.fixture
def stale_grounding():
    """Stale grounding evidence (>1 hour old)."""
    return {
        "source": "supabase",
        "data_id": "lead_123",
        "verified_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    }


# =============================================================================
# PERMISSION MATRIX TESTS
# =============================================================================

class TestPermissionMatrix:
    """Tests for agent permission system."""
    
    def test_queen_has_all_permissions(self, guardrails):
        """UNIFIED_QUEEN should have access to all actions except denied ones."""
        permissions = guardrails.get_agent_permissions("UNIFIED_QUEEN")
        # Queen has all actions except bulk_delete which is denied
        assert len(permissions) >= len(ActionType) - 1
        assert ActionType.READ_CONTACT in permissions
        assert ActionType.SEND_EMAIL in permissions
    
    def test_crafter_limited_permissions(self, guardrails):
        """CRAFTER should have limited permissions."""
        permissions = guardrails.get_agent_permissions("CRAFTER")
        assert ActionType.READ_CONTACT in permissions
        assert ActionType.GET_TEMPLATES in permissions
        assert ActionType.SEND_EMAIL not in permissions
        assert ActionType.BULK_DELETE not in permissions
    
    def test_gatekeeper_can_send_email(self, guardrails):
        """GATEKEEPER should be able to send emails."""
        permissions = guardrails.get_agent_permissions("GATEKEEPER")
        assert ActionType.SEND_EMAIL in permissions
        assert ActionType.BULK_SEND_EMAIL in permissions
    
    def test_scheduler_calendar_permissions(self, guardrails):
        """SCHEDULER should have calendar permissions."""
        permissions = guardrails.get_agent_permissions("SCHEDULER")
        assert ActionType.CREATE_CALENDAR_EVENT in permissions
        assert ActionType.UPDATE_CALENDAR_EVENT in permissions
        assert ActionType.DELETE_CALENDAR_EVENT in permissions
        assert ActionType.SEND_EMAIL not in permissions
    
    def test_unknown_agent_returns_empty(self, guardrails):
        """Unknown agent should return empty permissions."""
        permissions = guardrails.get_agent_permissions("UNKNOWN_AGENT")
        assert permissions == []
    
    def test_all_12_agents_defined(self):
        """All 12 agents should have permissions defined."""
        assert len(AgentName) == 12
        for agent in AgentName:
            assert agent in AGENT_PERMISSIONS


# =============================================================================
# ACTION VALIDATION TESTS
# =============================================================================

class TestActionValidation:
    """Tests for action validation logic."""
    
    def test_blocked_action_always_fails(self, guardrails):
        """Blocked actions should always be rejected."""
        valid, reason = guardrails.validate_action(
            "UNIFIED_QUEEN",
            ActionType.BULK_DELETE,
            {"source": "test", "data_id": "1", "verified_at": datetime.now(timezone.utc).isoformat()}
        )
        assert not valid
        assert "blocked" in reason.lower()
    
    def test_unauthorized_action_fails(self, guardrails):
        """Agent without permission should be rejected."""
        valid, reason = guardrails.validate_action(
            "CRAFTER",
            ActionType.SEND_EMAIL,
            None
        )
        assert not valid
        assert "not permitted" in reason.lower()
    
    def test_high_risk_without_grounding_fails(self, guardrails, valid_grounding):
        """High-risk action without grounding should fail."""
        valid, reason = guardrails.validate_action(
            "GATEKEEPER",
            ActionType.SEND_EMAIL,
            None  # No grounding
        )
        assert not valid
        assert "grounding evidence" in reason.lower()
    
    def test_high_risk_with_valid_grounding_passes(self, guardrails, valid_grounding):
        """High-risk action with valid grounding should pass."""
        valid, reason = guardrails.validate_action(
            "GATEKEEPER",
            ActionType.SEND_EMAIL,
            valid_grounding
        )
        assert valid
        assert reason is None
    
    def test_high_risk_with_stale_grounding_fails(self, guardrails, stale_grounding):
        """High-risk action with stale grounding should fail."""
        valid, reason = guardrails.validate_action(
            "GATEKEEPER",
            ActionType.SEND_EMAIL,
            stale_grounding
        )
        assert not valid
        assert "stale" in reason.lower()
    
    def test_low_risk_action_no_grounding_required(self, guardrails):
        """Low-risk actions should not require grounding."""
        valid, reason = guardrails.validate_action(
            "ENRICHER",
            ActionType.READ_CONTACT,
            None
        )
        assert valid


# =============================================================================
# GROUNDING EVIDENCE TESTS
# =============================================================================

class TestGroundingEvidence:
    """Tests for grounding evidence validation."""
    
    def test_valid_evidence(self, valid_grounding):
        """Valid evidence should pass validation."""
        evidence = GroundingEvidence.from_dict(valid_grounding)
        assert evidence.is_valid()
    
    def test_stale_evidence(self, stale_grounding):
        """Stale evidence should fail validation."""
        evidence = GroundingEvidence.from_dict(stale_grounding)
        assert not evidence.is_valid()
    
    def test_evidence_to_dict(self, valid_grounding):
        """Evidence should serialize correctly."""
        evidence = GroundingEvidence.from_dict(valid_grounding)
        d = evidence.to_dict()
        assert d["source"] == "supabase"
        assert d["data_id"] == "lead_123"
    
    def test_missing_fields_raises_error(self):
        """Missing required fields should raise ValueError (security fix)."""
        import pytest
        # SECURITY: Grounding evidence must have explicit verified_at to prevent forgery
        with pytest.raises(ValueError, match="verified_at"):
            GroundingEvidence.from_dict({})
        
        # Missing verified_at specifically
        with pytest.raises(ValueError, match="verified_at"):
            GroundingEvidence.from_dict({"source": "supabase", "data_id": "123"})
        
        # Invalid source should also raise
        with pytest.raises(ValueError, match="not in allowed list"):
            GroundingEvidence.from_dict({
                "source": "hacked_source",
                "data_id": "123",
                "verified_at": datetime.now(timezone.utc).isoformat()
            })


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================

class TestRateLimiting:
    """Tests for rate limiting functionality."""
    
    def test_under_limit_allowed(self, rate_limiter):
        """Actions under limit should be allowed."""
        allowed, reason = rate_limiter.check_limit("test_agent")
        assert allowed
        assert reason is None
    
    def test_minute_limit_enforced(self, rate_limiter):
        """Per-minute limit should be enforced."""
        limits = RateLimitConfig(per_minute=5, per_hour=100, per_day=1000)
        
        # Record 5 actions
        for _ in range(5):
            rate_limiter.record_action("test_agent")
        
        allowed, reason = rate_limiter.check_limit("test_agent", limits)
        assert not allowed
        assert "5/minute" in reason
    
    def test_hour_limit_enforced(self, rate_limiter):
        """Per-hour limit should be enforced."""
        limits = RateLimitConfig(per_minute=100, per_hour=5, per_day=1000)
        
        for _ in range(5):
            rate_limiter.record_action("test_agent")
        
        allowed, reason = rate_limiter.check_limit("test_agent", limits)
        assert not allowed
        assert "5/hour" in reason
    
    def test_get_usage_returns_counts(self, rate_limiter):
        """Usage should return correct counts."""
        rate_limiter.record_action("test_agent")
        rate_limiter.record_action("test_agent")
        
        usage = rate_limiter.get_usage("test_agent")
        assert usage["minute"]["used"] == 2
        assert usage["hour"]["used"] == 2
        assert usage["day"]["used"] == 2
    
    def test_guardrails_rate_limit_check(self, guardrails):
        """Guardrails should check rate limits correctly."""
        allowed, reason = guardrails.check_rate_limits("ENRICHER", ActionType.READ_CONTACT)
        assert allowed


# =============================================================================
# CIRCUIT BREAKER TESTS
# =============================================================================

class TestCircuitBreaker:
    """Tests for circuit breaker integration."""
    
    def test_circuit_starts_closed(self, guardrails):
        """Circuit should start in closed state."""
        status = guardrails.get_status()
        assert status["agents"]["ENRICHER"]["circuit_state"] in ["closed", "unknown"]
    
    def test_force_trip_opens_circuit(self, guardrails):
        """Force trip should open circuit."""
        guardrails.force_trip_circuit("ENRICHER")
        
        valid, reason = guardrails.validate_action(
            "ENRICHER",
            ActionType.READ_CONTACT,
            None
        )
        assert not valid
        assert "circuit breaker open" in reason.lower()
    
    def test_reset_closes_circuit(self, guardrails):
        """Reset should close circuit."""
        guardrails.force_trip_circuit("ENRICHER")
        guardrails.reset_circuit("ENRICHER")
        
        valid, reason = guardrails.validate_action(
            "ENRICHER",
            ActionType.READ_CONTACT,
            None
        )
        assert valid


# =============================================================================
# EXPONENTIAL BACKOFF TESTS
# =============================================================================

class TestExponentialBackoff:
    """Tests for exponential backoff."""
    
    def test_initial_delay_is_base(self):
        """First delay should be base delay."""
        backoff = ExponentialBackoff(base_delay=1.0, jitter=0)
        delay = backoff.get_delay("test")
        assert delay == 1.0
    
    def test_delay_increases_exponentially(self):
        """Delay should double with each attempt."""
        backoff = ExponentialBackoff(base_delay=1.0, multiplier=2.0, jitter=0)
        
        backoff.record_attempt("test")
        delay1 = backoff.get_delay("test")
        
        backoff.record_attempt("test")
        delay2 = backoff.get_delay("test")
        
        assert delay2 == delay1 * 2
    
    def test_delay_capped_at_max(self):
        """Delay should not exceed max."""
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=10.0, jitter=0)
        
        for _ in range(10):
            backoff.record_attempt("test")
        
        delay = backoff.get_delay("test")
        assert delay <= 10.0
    
    def test_reset_clears_attempts(self):
        """Reset should clear attempt count."""
        backoff = ExponentialBackoff()
        backoff.record_attempt("test")
        backoff.record_attempt("test")
        
        assert backoff.get_attempts("test") == 2
        
        backoff.reset("test")
        assert backoff.get_attempts("test") == 0


# =============================================================================
# HOOK SYSTEM TESTS
# =============================================================================

class TestHookSystem:
    """Tests for pre/post execution hooks."""
    
    def test_pre_hook_modifies_context(self):
        """Pre-hook should be able to modify context."""
        hooks = HookSystem()
        
        def add_timestamp(context):
            context["timestamp"] = "test_time"
            return context
        
        hooks.register_pre_hook("timestamp", add_timestamp)
        
        context = asyncio.run(hooks.run_pre_hooks({}))
        assert context["timestamp"] == "test_time"
    
    def test_hooks_run_in_priority_order(self):
        """Hooks should run in priority order (highest first)."""
        hooks = HookSystem()
        order = []
        
        def hook1(ctx):
            order.append(1)
            return ctx
        
        def hook2(ctx):
            order.append(2)
            return ctx
        
        hooks.register_pre_hook("low", hook1, priority=1)
        hooks.register_pre_hook("high", hook2, priority=10)
        
        asyncio.run(hooks.run_pre_hooks({}))
        assert order == [2, 1]  # Higher priority first


# =============================================================================
# EXECUTION TESTS
# =============================================================================

class TestExecution:
    """Tests for guarded action execution."""
    
    def test_successful_execution(self, guardrails):
        """Successful action should return success result."""
        async def mock_action(contact_id: str):
            return {"id": contact_id}
        
        async def run_test():
            return await guardrails.execute_with_guardrails(
                agent_name="ENRICHER",
                action_type=ActionType.READ_CONTACT,
                action_fn=mock_action,
                parameters={"contact_id": "123"}
            )
        
        result = asyncio.run(run_test())
        assert result.success
        assert result.result == {"id": "123"}
        assert result.execution_time_ms > 0
    
    def test_blocked_action_returns_failure(self, guardrails):
        """Blocked action should return failure."""
        async def mock_action():
            return {}
        
        async def run_test():
            return await guardrails.execute_with_guardrails(
                agent_name="CRAFTER",
                action_type=ActionType.SEND_EMAIL,  # CRAFTER can't send email
                action_fn=mock_action
            )
        
        result = asyncio.run(run_test())
        assert not result.success
        assert result.blocked_reason is not None
        assert "not permitted" in result.blocked_reason.lower()
    
    def test_exception_records_failure(self, guardrails):
        """Exception during action should record failure."""
        async def failing_action():
            raise ValueError("Test error")
        
        async def run_test():
            return await guardrails.execute_with_guardrails(
                agent_name="ENRICHER",
                action_type=ActionType.READ_CONTACT,
                action_fn=failing_action
            )
        
        result = asyncio.run(run_test())
        assert not result.success
        assert result.error == "Test error"
    
    def test_grounding_verified_flag(self, guardrails, valid_grounding):
        """Grounding verified should be set when evidence provided."""
        async def mock_action():
            return {}
        
        async def run_test():
            return await guardrails.execute_with_guardrails(
                agent_name="GATEKEEPER",
                action_type=ActionType.SEND_EMAIL,
                action_fn=mock_action,
                grounding_evidence=valid_grounding
            )
        
        result = asyncio.run(run_test())
        assert result.success
        assert result.grounding_verified


# =============================================================================
# DECORATOR TESTS
# =============================================================================

class TestDecorators:
    """Tests for guardrail decorators."""
    
    def test_require_grounding_decorator_without_evidence(self):
        """Decorator should reject calls without grounding."""
        @require_grounding(ActionType.SEND_EMAIL)
        async def protected_action():
            return "success"
        
        async def run_test():
            return await protected_action()
        
        with pytest.raises(ValueError) as exc_info:
            asyncio.run(run_test())
        
        assert "requires grounding evidence" in str(exc_info.value)
    
    def test_require_grounding_decorator_with_evidence(self, valid_grounding):
        """Decorator should allow calls with valid grounding."""
        @require_grounding(ActionType.SEND_EMAIL)
        async def protected_action(grounding_evidence=None):
            return "success"
        
        async def run_test():
            return await protected_action(grounding_evidence=valid_grounding)
        
        result = asyncio.run(run_test())
        assert result == "success"


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for complete workflows."""
    
    def test_full_workflow_with_hooks(self, guardrails):
        """Test complete workflow with hooks."""
        pre_hook_called = []
        post_hook_called = []
        
        def pre_hook(context):
            pre_hook_called.append(True)
            return context
        
        def post_hook(context, result):
            post_hook_called.append(True)
        
        guardrails.hook_system.register_pre_hook("test_pre", pre_hook)
        guardrails.hook_system.register_post_hook("test_post", post_hook)
        
        async def mock_action():
            return {"status": "ok"}
        
        async def run_test():
            return await guardrails.execute_with_guardrails(
                agent_name="ENRICHER",
                action_type=ActionType.READ_CONTACT,
                action_fn=mock_action
            )
        
        result = asyncio.run(run_test())
        assert result.success
        assert len(pre_hook_called) > 0
        assert len(post_hook_called) > 0
    
    def test_status_returns_all_agents(self, guardrails):
        """Status should include all 12 agents."""
        status = guardrails.get_status()
        assert len(status["agents"]) == 12
        for agent in AgentName:
            assert agent.value in status["agents"]


# =============================================================================
# RISK LEVEL TESTS
# =============================================================================

class TestRiskLevels:
    """Tests for action risk level assignments."""
    
    def test_read_actions_are_low_risk(self):
        """Read actions should be LOW risk."""
        assert ACTION_RISK_LEVELS[ActionType.READ_CONTACT] == RiskLevel.LOW
        assert ACTION_RISK_LEVELS[ActionType.READ_PIPELINE] == RiskLevel.LOW
        assert ACTION_RISK_LEVELS[ActionType.SEARCH_CONTACTS] == RiskLevel.LOW
    
    def test_outreach_actions_are_high_risk(self):
        """Outreach actions should be HIGH risk."""
        assert ACTION_RISK_LEVELS[ActionType.SEND_EMAIL] == RiskLevel.HIGH
        assert ACTION_RISK_LEVELS[ActionType.SEND_SMS] == RiskLevel.HIGH
        assert ACTION_RISK_LEVELS[ActionType.TRIGGER_WORKFLOW] == RiskLevel.HIGH
    
    def test_bulk_actions_are_critical(self):
        """Bulk actions should be CRITICAL risk."""
        assert ACTION_RISK_LEVELS[ActionType.BULK_CREATE_CONTACTS] == RiskLevel.CRITICAL
        assert ACTION_RISK_LEVELS[ActionType.BULK_SEND_EMAIL] == RiskLevel.CRITICAL


# =============================================================================
# JSON CONFIG TESTS
# =============================================================================

class TestPermissionsConfigLoader:
    """Tests for JSON permissions configuration loader."""
    
    def test_config_loads_successfully(self):
        """Config should load from JSON file."""
        config = get_permissions_config()
        assert config.config is not None
    
    def test_config_has_all_agents(self):
        """Config should define all known agents."""
        config = get_permissions_config()
        agents = config.get_all_agents()
        assert len(agents) >= 12  # At least 12, may grow as agents are added
        assert "UNIFIED_QUEEN" in agents
        assert "GATEKEEPER" in agents
        assert "SCHEDULER" in agents
    
    def test_agent_config_returns_data(self):
        """Agent config should return agent details."""
        config = get_permissions_config()
        queen_config = config.get_agent_config("UNIFIED_QUEEN")
        assert queen_config is not None
        assert queen_config.get("role") == "orchestrator"
        assert queen_config.get("can_approve") is True
    
    def test_queen_can_approve(self):
        """UNIFIED_QUEEN should have approval authority."""
        config = get_permissions_config()
        assert config.can_agent_approve("UNIFIED_QUEEN") is True
    
    def test_crafter_cannot_approve(self):
        """CRAFTER should NOT have approval authority."""
        config = get_permissions_config()
        assert config.can_agent_approve("CRAFTER") is False
    
    def test_queen_has_higher_approval_weight(self):
        """UNIFIED_QUEEN should have weight 3, others 1."""
        config = get_permissions_config()
        assert config.get_agent_approval_weight("UNIFIED_QUEEN") == 3
        assert config.get_agent_approval_weight("CRAFTER") == 1
    
    def test_action_definition_exists(self):
        """Action definitions should be loaded."""
        config = get_permissions_config()
        send_email_def = config.get_action_definition("send_email")
        assert send_email_def is not None
        assert send_email_def.get("risk_level") == "HIGH"
    
    def test_bulk_delete_is_blocked(self):
        """bulk_delete should be blocked."""
        config = get_permissions_config()
        blocked, reason = config.is_action_blocked("bulk_delete")
        assert blocked is True
        assert reason is not None
    
    def test_read_contact_not_blocked(self):
        """read_contact should NOT be blocked."""
        config = get_permissions_config()
        blocked, reason = config.is_action_blocked("read_contact")
        assert blocked is False
    
    def test_rate_limit_defaults(self):
        """Rate limit defaults should be loaded."""
        config = get_permissions_config()
        ghl_limits = config.get_rate_limit_defaults("ghl_email")
        assert ghl_limits.get("per_day") == 150
        assert ghl_limits.get("per_hour") == 20
    
    def test_config_validation(self):
        """Config should pass validation."""
        config = get_permissions_config()
        valid, errors = config.validate_config()
        assert valid is True
        assert len(errors) == 0


class TestGuardrailsWithJsonConfig:
    """Tests for guardrails using JSON config."""
    
    def test_guardrails_uses_json_config(self, guardrails):
        """Guardrails should use JSON config when enabled."""
        assert guardrails.use_json_config is True
        assert guardrails.permissions_config is not None
    
    def test_can_agent_approve_method(self, guardrails):
        """can_agent_approve should work with JSON config."""
        assert guardrails.can_agent_approve("UNIFIED_QUEEN") is True
        assert guardrails.can_agent_approve("GATEKEEPER") is True
        assert guardrails.can_agent_approve("CRAFTER") is False
    
    def test_approval_weight_method(self, guardrails):
        """get_agent_approval_weight should work with JSON config."""
        assert guardrails.get_agent_approval_weight("UNIFIED_QUEEN") == 3
        assert guardrails.get_agent_approval_weight("GATEKEEPER") == 2
        assert guardrails.get_agent_approval_weight("ENRICHER") == 1
    
    def test_get_agent_config_method(self, guardrails):
        """get_agent_config should return full agent configuration."""
        config = guardrails.get_agent_config("SCHEDULER")
        assert config.get("role") == "scheduling"
        assert "create_calendar_event" in config.get("allowed_actions", [])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
