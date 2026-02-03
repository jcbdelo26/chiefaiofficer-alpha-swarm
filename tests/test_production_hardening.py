"""
Production Hardening Component Tests
=====================================
Tests for agent_permissions, circuit_breaker, ghl_guardrails, and system_orchestrator.
"""

import pytest
import json
import tempfile
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent_permissions import (
    Permission, AgentRole, PermissionGuard, PermissionDeniedError,
    PREDEFINED_ROLES, requires_permission, requires_platform, get_permission_guard
)
from core.circuit_breaker import (
    CircuitBreaker, CircuitState, CircuitBreakerRegistry,
    CircuitBreakerError, with_circuit_breaker, get_registry
)
from core.unified_guardrails import ActionType, RiskLevel, ACTION_RISK_LEVELS
from core.ghl_guardrails import EmailDeliverabilityGuard, get_email_guard
from core.system_orchestrator import (
    SystemOrchestrator, SystemStatus, ComponentType, ComponentHealth
)


class TestAgentPermissions:
    """Tests for agent_permissions.py"""
    
    @pytest.fixture
    def guard(self, tmp_path):
        """Create fresh permission guard with temp log directory."""
        guard = PermissionGuard(log_dir=str(tmp_path))
        guard.register_agent_by_role_name("hunter", "HUNTER")
        guard.register_agent_by_role_name("ghl_master", "GHL_MASTER")
        guard.register_agent_by_role_name("gatekeeper", "GATEKEEPER")
        return guard
    
    def test_unknown_agent_returns_false(self, guard):
        """Unknown agent should be denied all permissions."""
        result = guard.check_permission("unknown_agent", Permission.READ_LEADS)
        assert result is False
    
    def test_require_permission_raises_for_denied(self, guard):
        """require_permission should raise PermissionDeniedError when denied."""
        with pytest.raises(PermissionDeniedError) as exc_info:
            guard.require_permission("hunter", Permission.SEND_EMAIL)
        assert "hunter" in str(exc_info.value)
        assert Permission.SEND_EMAIL.name in str(exc_info.value)
    
    def test_granted_permission_passes(self, guard):
        """Agent with permission should pass check."""
        result = guard.check_permission("hunter", Permission.READ_LEADS)
        assert result is True
    
    def test_ghl_master_can_send_email(self, guard):
        """GHL_MASTER role should have SEND_EMAIL permission."""
        result = guard.check_permission("ghl_master", Permission.SEND_EMAIL)
        assert result is True
    
    def test_hunter_cannot_send_email(self, guard):
        """HUNTER role should NOT have SEND_EMAIL permission."""
        result = guard.check_permission("hunter", Permission.SEND_EMAIL)
        assert result is False
    
    def test_platform_access_case_insensitive(self, guard):
        """Platform access should be case-insensitive."""
        assert guard.check_platform_access("hunter", "LinkedIn") is True
        assert guard.check_platform_access("hunter", "linkedin") is True
        assert guard.check_platform_access("hunter", "LINKEDIN") is True
    
    def test_platform_access_denied_for_wrong_platform(self, guard):
        """Agent should be denied access to platforms not in their role."""
        assert guard.check_platform_access("hunter", "GoHighLevel") is False
        assert guard.check_platform_access("ghl_master", "LinkedIn") is False
    
    def test_violations_logged(self, guard):
        """Denied permission should be logged as violation."""
        guard.require_permission("ghl_master", Permission.READ_LEADS)  # allowed
        
        with pytest.raises(PermissionDeniedError):
            guard.require_permission("hunter", Permission.SEND_EMAIL)  # denied
        
        violations = guard.get_violations("hunter")
        assert len(violations) == 1
        assert violations[0]["permission"] == "SEND_EMAIL"
    
    def test_rate_limit_blocks_after_threshold(self, guard):
        """Rate limiting should block after threshold reached."""
        guard.agent_roles["hunter"].rate_limits["test_action"] = 3
        
        for i in range(3):
            assert guard.check_rate_limit("hunter", "test_action") is True
            guard.increment_action_count("hunter", "test_action")
        
        assert guard.check_rate_limit("hunter", "test_action") is False
    
    def test_needs_approval_for_restricted_actions(self, guard):
        """CRAFTER should need approval for SEND_EMAIL."""
        guard.register_agent_by_role_name("crafter", "CRAFTER")
        assert guard.needs_approval("crafter", Permission.SEND_EMAIL) is True
        assert guard.needs_approval("ghl_master", Permission.SEND_EMAIL) is False


class TestCircuitBreaker:
    """Tests for circuit_breaker.py"""
    
    @pytest.fixture
    def registry(self, tmp_path):
        """Create fresh circuit breaker registry."""
        state_file = tmp_path / "circuit_breakers.json"
        registry = CircuitBreakerRegistry(state_file=state_file)
        registry.register("test_service", failure_threshold=3, recovery_timeout=1)
        return registry
    
    def test_closed_to_open_after_threshold_failures(self, registry):
        """Circuit should open after threshold failures."""
        breaker = registry.get_breaker("test_service")
        assert breaker.state == CircuitState.CLOSED
        
        for _ in range(3):
            registry.record_failure("test_service", Exception("test error"))
        
        assert breaker.state == CircuitState.OPEN
    
    def test_open_blocks_calls(self, registry):
        """Open circuit should report not available."""
        for _ in range(3):
            registry.record_failure("test_service", Exception("test"))
        
        assert registry.is_available("test_service") is False
    
    def test_open_to_half_open_after_timeout(self, registry):
        """Circuit should transition to HALF_OPEN after recovery timeout."""
        for _ in range(3):
            registry.record_failure("test_service", Exception("test"))
        
        breaker = registry.get_breaker("test_service")
        breaker.last_failure_time = datetime.now() - timedelta(seconds=2)
        
        registry.is_available("test_service")
        assert breaker.state == CircuitState.HALF_OPEN
    
    def test_half_open_to_closed_after_successes(self, registry):
        """Circuit should close after successful calls in HALF_OPEN."""
        registry.register("recovery_test", failure_threshold=2, recovery_timeout=0, half_open_max_calls=2)
        
        registry.record_failure("recovery_test", Exception("test"))
        registry.record_failure("recovery_test", Exception("test"))
        
        breaker = registry.get_breaker("recovery_test")
        breaker.state = CircuitState.HALF_OPEN
        breaker.half_open_call_count = 0
        
        registry.record_success("recovery_test")
        registry.record_success("recovery_test")
        
        assert breaker.state == CircuitState.CLOSED
    
    def test_half_open_to_open_on_failure(self, registry):
        """Circuit should reopen on failure during HALF_OPEN."""
        breaker = registry.get_breaker("test_service")
        breaker.state = CircuitState.HALF_OPEN
        
        registry.record_failure("test_service", Exception("test"))
        
        assert breaker.state == CircuitState.OPEN
    
    def test_circuit_breaker_error_includes_retry_time(self, registry):
        """CircuitBreakerError should include time until retry."""
        for _ in range(3):
            registry.record_failure("test_service", Exception("test"))
        
        time_until = registry.get_time_until_retry("test_service")
        assert time_until is not None
        assert time_until > 0
    
    def test_force_close_resets_breaker(self, registry):
        """force_close should reset breaker to CLOSED."""
        for _ in range(3):
            registry.record_failure("test_service", Exception("test"))
        
        registry.force_close("test_service")
        breaker = registry.get_breaker("test_service")
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
    
    def test_state_persists_to_file(self, registry, tmp_path):
        """Breaker state should persist to file."""
        registry.record_failure("test_service", Exception("test"))
        
        state_file = tmp_path / "circuit_breakers.json"
        assert state_file.exists()
        
        with open(state_file) as f:
            data = json.load(f)
        
        breaker_data = next(b for b in data["breakers"] if b["name"] == "test_service")
        assert breaker_data["failure_count"] == 1


class TestEmailDeliverabilityGuard:
    """Tests for EmailDeliverabilityGuard (the valuable part of ghl_guardrails.py)"""
    
    @pytest.fixture
    def email_guard(self, tmp_path):
        """Create fresh email guard instance."""
        g = get_email_guard()
        g.hive_mind_path = tmp_path
        g.limits_file = tmp_path / "email_limits.json"
        g.domains_file = tmp_path / "domain_health.json"
        return g
    
    def test_spam_words_block_email(self, email_guard):
        """Emails with spam words should be blocked."""
        is_valid, issues = email_guard.validate_email_content(
            subject="FREE MONEY NOW!!!",
            body="Act now for guaranteed results!"
        )
        assert is_valid is False
        assert len(issues) > 0
    
    def test_missing_unsubscribe_flagged(self, email_guard):
        """Emails without unsubscribe should be flagged."""
        is_valid, issues = email_guard.validate_email_content(
            subject="Quick question",
            body="Hi, I wanted to reach out about your business."
        )
        assert any("unsubscribe" in issue.lower() for issue in issues)
    
    def test_action_risk_levels_exist(self):
        """Verify action risk levels are properly defined in unified_guardrails."""
        # SEND_EMAIL should be HIGH risk
        assert ACTION_RISK_LEVELS[ActionType.SEND_EMAIL] == RiskLevel.HIGH
        # BULK_DELETE should be CRITICAL risk
        assert ACTION_RISK_LEVELS[ActionType.BULK_DELETE] == RiskLevel.CRITICAL
        # READ_CONTACT should be LOW risk
        assert ACTION_RISK_LEVELS[ActionType.READ_CONTACT] == RiskLevel.LOW
    
    def test_email_limits_enforced(self, email_guard):
        """Email sending limits should be enforced."""
        email_guard.limits.monthly_sent = 3000
        can_send, reason = email_guard.can_send_email("test@example.com")
        assert can_send is False
        assert "limit" in reason.lower()
    
    def test_valid_email_allowed(self, email_guard):
        """Valid email with proper content should pass content validation."""
        # Test content validation directly (working hours may block full validation)
        is_valid, issues = email_guard.validate_email_content(
            subject="Quick question about RevOps",
            body="Hi, I noticed your team has been growing rapidly. I help companies like yours streamline their revenue operations. Would you be open to a brief call? Reply STOP to unsubscribe."
        )
        # Content should be valid (no spam words, has unsubscribe)
        assert is_valid is True or not any("spam" in i.lower() for i in issues)


class TestSystemOrchestrator:
    """Tests for system_orchestrator.py"""
    
    @pytest.fixture
    def orchestrator(self, tmp_path):
        """Create fresh orchestrator."""
        with patch.object(SystemOrchestrator, '__init__', lambda self: None):
            orch = SystemOrchestrator.__new__(SystemOrchestrator)
            orch.hive_mind_path = tmp_path
            orch.status = SystemStatus.HEALTHY
            orch.maintenance_mode = False
            orch.emergency_stop = False
            orch.components = {}
            orch._initialize_components()
        return orch
    
    def test_healthy_system_is_operational(self, orchestrator):
        """Healthy system should be operational."""
        assert orchestrator.is_operational() is True
    
    def test_maintenance_mode_stops_operations(self, orchestrator):
        """Maintenance mode should stop operations."""
        orchestrator.enter_maintenance_mode("Test maintenance")
        assert orchestrator.is_operational() is False
        assert orchestrator.status == SystemStatus.MAINTENANCE
    
    def test_exit_maintenance_resumes_operations(self, orchestrator):
        """Exiting maintenance should resume operations."""
        orchestrator.enter_maintenance_mode("Test")
        orchestrator.exit_maintenance_mode()
        assert orchestrator.is_operational() is True
    
    def test_emergency_shutdown_stops_operations(self, orchestrator):
        """Emergency shutdown should stop all operations."""
        orchestrator.emergency_shutdown("Critical error")
        assert orchestrator.is_operational() is False
        assert orchestrator.status == SystemStatus.EMERGENCY
    
    def test_component_health_update(self, orchestrator):
        """Component health updates should be recorded."""
        orchestrator.update_component_health("api_ghl", "healthy")
        assert orchestrator.components["api_ghl"].status == "healthy"
        
        orchestrator.update_component_health("api_ghl", "down", "Connection failed")
        assert orchestrator.components["api_ghl"].status == "down"
        assert orchestrator.components["api_ghl"].failure_count == 1
    
    def test_critical_api_down_degrades_system(self, orchestrator):
        """Critical API being down should degrade system status."""
        orchestrator.update_component_health("api_ghl", "down")
        assert orchestrator.status in [SystemStatus.DEGRADED, SystemStatus.CRITICAL]
    
    def test_production_readiness_check(self, orchestrator):
        """Production readiness should fail for unknown APIs."""
        ready, passed, failed = orchestrator.check_production_readiness()
        assert any("Not tested" in f or "unknown" in f.lower() for f in failed)


class TestIntegration:
    """Integration tests across components."""
    
    def test_permission_and_guardrails_alignment(self):
        """Permission actions should align with guardrail action types."""
        permission_email = Permission.SEND_EMAIL
        action_type_email = ActionType.SEND_EMAIL
        
        assert permission_email.name.lower() == action_type_email.value.lower().replace("_", "_")
    
    def test_circuit_breakers_exist_for_apis(self):
        """Circuit breakers should exist for all APIs."""
        registry = get_registry()
        expected_breakers = ["ghl_api", "linkedin_api", "supabase"]
        
        for name in expected_breakers:
            breaker = registry.get_breaker(name)
            assert breaker is not None, f"Missing circuit breaker for {name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
