
import pytest
import re
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any

from core.unified_guardrails import UnifiedGuardrails, ActionType, RiskLevel
from execution.unified_queen_orchestrator import UnifiedQueen, Task, TaskPriority
from core.context_manager import ContextManager

# ============================================================================
# PII REDACTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_pii_redaction_in_logs():
    """
    Guardrail Test 1: PII Redaction
    Verify that sensitive information (emails, SSN, credit cards) is redacted from logs.
    """
    guardrails = UnifiedGuardrails()
    
    # Test data with various PII types
    sensitive_text = """
    Contact john.doe@example.com for details.
    SSN: 123-45-6789
    Credit Card: 4532-1234-5678-9010
    Phone: (555) 123-4567
    """
    
    redacted = guardrails.redact_pii(sensitive_text)
    
    # Verify email is redacted
    assert "john.doe@example.com" not in redacted
    assert "[EMAIL_REDACTED]" in redacted or "[REDACTED]" in redacted
    
    # Verify SSN is redacted
    assert "123-45-6789" not in redacted
    assert "[SSN_REDACTED]" in redacted or "[REDACTED]" in redacted
    
    # Verify credit card is redacted
    assert "4532-1234-5678-9010" not in redacted
    
    # Verify phone is redacted
    assert "(555) 123-4567" not in redacted
    
    print(f"\n[PII Redaction]\nOriginal:\n{sensitive_text}\n\nRedacted:\n{redacted}")


@pytest.mark.asyncio
async def test_pii_redaction_preserves_structure():
    """
    Guardrail Test 2: PII Redaction Structure
    Verify redaction preserves text structure for debugging.
    """
    guardrails = UnifiedGuardrails()
    
    text = "Email me at alice@company.com or call 555-0100"
    redacted = guardrails.redact_pii(text)
    
    # Should preserve sentence structure
    assert "Email me at" in redacted
    assert "or call" in redacted
    
    # But sensitive data should be gone
    assert "alice@company.com" not in redacted
    assert "555-0100" not in redacted


# ============================================================================
# CONTEXT BUDGET TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_context_budget_enforcement():
    """
    Guardrail Test 3: Context Budget
    Verify system enters "Dumb Zone" when context budget exceeds 40%.
    """
    context_mgr = ContextManager(max_tokens=10000)
    
    # Simulate context growth
    large_context = "x" * 4500  # 45% of budget (assuming ~1 char = 1 token for simplicity)
    context_mgr.add_context("task_1", large_context)
    
    usage = context_mgr.get_usage()
    assert usage["percentage"] > 40.0
    assert usage["in_dumb_zone"] is True
    
    print(f"\n[Context Budget] Usage: {usage['percentage']:.1f}% (Dumb Zone: {usage['in_dumb_zone']})")


@pytest.mark.asyncio
async def test_dumb_zone_triggers_cleanup():
    """
    Guardrail Test 4: Dumb Zone Auto-Cleanup
    Verify entering Dumb Zone triggers context cleanup.
    """
    context_mgr = ContextManager(max_tokens=10000)
    
    # Add multiple contexts
    context_mgr.add_context("task_1", "x" * 2000, priority="low")
    context_mgr.add_context("task_2", "y" * 2000, priority="low")
    context_mgr.add_context("task_3", "z" * 500, priority="high")
    
    initial_usage = context_mgr.get_usage()["percentage"]
    
    # Trigger cleanup
    if initial_usage > 40.0:
        context_mgr.cleanup_low_priority()
    
    final_usage = context_mgr.get_usage()["percentage"]
    assert final_usage < initial_usage
    
    # High priority should be preserved
    assert context_mgr.has_context("task_3")
    
    print(f"\n[Cleanup] Before: {initial_usage:.1f}% → After: {final_usage:.1f}%")


# ============================================================================
# TOOL AUTHORIZATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_high_risk_action_requires_approval():
    """
    Guardrail Test 5: High-Risk Actions
    Verify high-risk actions (delete, external API calls) require Gatekeeper approval.
    """
    guardrails = UnifiedGuardrails()
    
    # High-risk action: Database deletion
    action = {
        "type": ActionType.DATABASE_WRITE,
        "operation": "DELETE",
        "target": "ghl_contacts"
    }
    
    risk_assessment = guardrails.assess_risk(action)
    
    assert risk_assessment["level"] in [RiskLevel.HIGH, RiskLevel.CRITICAL]
    assert risk_assessment["requires_approval"] is True
    
    print(f"\n[High-Risk Action] {action['operation']} → Risk: {risk_assessment['level'].value}")


@pytest.mark.asyncio
async def test_low_risk_action_auto_approved():
    """
    Guardrail Test 6: Low-Risk Actions
    Verify low-risk actions (read operations) are auto-approved.
    """
    guardrails = UnifiedGuardrails()
    
    # Low-risk action: Database read
    action = {
        "type": ActionType.DATABASE_READ,
        "operation": "SELECT",
        "target": "ghl_contacts"
    }
    
    risk_assessment = guardrails.assess_risk(action)
    
    assert risk_assessment["level"] in [RiskLevel.LOW, RiskLevel.MEDIUM]
    assert risk_assessment["requires_approval"] is False
    
    print(f"\n[Low-Risk Action] {action['operation']} → Risk: {risk_assessment['level'].value} (Auto-approved)")


@pytest.mark.asyncio
async def test_gatekeeper_blocks_unauthorized_tools():
    """
    Guardrail Test 7: Tool Authorization
    Verify Gatekeeper blocks unauthorized tool usage by agents.
    """
    from execution.gatekeeper_queue import EnhancedGatekeeperQueue
    from core.approval_engine import ApprovalRequest
    
    gatekeeper = EnhancedGatekeeperQueue(test_mode=True)
    
    # Mock approval engine to reject this request
    gatekeeper.approval_engine.submit_request = MagicMock(return_value=ApprovalRequest(
        request_id="req_reject_1",
        status="rejected",
        requester_agent="hunter",
        action_type="external_api_call",
        payload={"tool": "unauthorized_scraper"},
        risk_score=0.9,
        created_at="",
        updated_at=""
    ))
    
    # Attempt unauthorized action
    result = gatekeeper.submit_for_review(
        campaign_id="test_unauth",
        agent_name="hunter",
        action_type="external_api_call",
        payload={"tool": "unauthorized_scraper"},
        metadata={}
    )
    
    # Should be blocked or pending (not auto-approved)
    assert result["status"] != "approved"
    
    print(f"\n[Tool Authorization] Unauthorized tool blocked: {result['status']}")


# ============================================================================
# RATE LIMITING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_rate_limiting_enforcement():
    """
    Guardrail Test 8: Rate Limiting
    Verify external API rate limits are enforced.
    """
    guardrails = UnifiedGuardrails()
    
    # Simulate rapid API calls
    api_name = "linkedin_scraper"
    
    for i in range(150):  # 150 calls (LinkedIn limit is 100/hour)
        allowed = guardrails.check_rate_limit(api_name, limit=100, window=3600)
        
        if i < 100:
            assert allowed is True
        else:
            assert allowed is False  # Should be blocked after 100 calls
    
    print(f"\n[Rate Limiting] Blocked calls after hitting 100/hour limit for {api_name}")
