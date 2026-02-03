#!/usr/bin/env python3
"""
Unit tests for Slack MCP Server.
Tests approval workflows, alerts, and message handling.
"""

import os
import sys
import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch
import importlib.util

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# Load modules with hyphens in path using importlib
def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Load slack modules
slack_server = load_module(
    "slack_server",
    PROJECT_ROOT / "mcp-servers" / "slack-mcp" / "server.py"
)
slack_config = load_module(
    "slack_config", 
    PROJECT_ROOT / "mcp-servers" / "slack-mcp" / "config.py"
)


class TestSlackMCP:
    """Test Slack MCP functionality."""
    
    @pytest.mark.asyncio
    async def test_send_approval_request(self):
        """Test sending approval request."""
        result = await slack_server.send_approval_request(
            workflow_id="W-test-001",
            action_type="send_email",
            title="Test Approval",
            description="Test description for approval",
            context={"contact": "John Doe", "company": "Test Corp"},
            requester="TEST_AGENT",
            risk_level="medium"
        )
        
        assert "approval_id" in result
        assert result["approval_id"].startswith("APR-")
        assert result["status"] == "pending"
    
    @pytest.mark.asyncio
    async def test_send_alert(self):
        """Test sending alert notification."""
        result = await slack_server.send_alert(
            title="Test Alert",
            message="This is a test alert message",
            level="warning",
            details={"key": "value"}
        )
        
        assert result["ok"] is True
        assert "message_ts" in result
    
    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test sending simple message."""
        result = await slack_server.send_message(
            text="Test message content"
        )
        
        assert result["ok"] is True
    
    @pytest.mark.asyncio
    async def test_get_approval_status(self):
        """Test getting approval status."""
        # Create an approval first
        approval = await slack_server.send_approval_request(
            workflow_id="W-test-002",
            action_type="create_event",
            title="Test Status Check",
            description="Testing status retrieval",
            context={}
        )
        
        # Get its status
        status = await slack_server.get_approval_status(approval["approval_id"])
        
        assert status["found"] is True
        assert status["status"] == "pending"
        assert status["workflow_id"] == "W-test-002"
    
    @pytest.mark.asyncio
    async def test_get_approval_status_not_found(self):
        """Test getting status for non-existent approval."""
        status = await slack_server.get_approval_status("APR-nonexistent")
        
        assert status["found"] is False
        assert "error" in status
    
    @pytest.mark.asyncio
    async def test_process_approval(self):
        """Test processing an approval action."""
        # Create an approval
        approval = await slack_server.send_approval_request(
            workflow_id="W-test-003",
            action_type="send_email",
            title="Test Approval Processing",
            description="Testing approval flow",
            context={}
        )
        
        # Approve it
        result = await slack_server.process_interaction(
            approval_id=approval["approval_id"],
            action="approve",
            user_id="U12345",
            user_name="Test User"
        )
        
        assert result["ok"] is True
        assert result["action"] == "approve"
        assert result["status"] == "approved"
    
    @pytest.mark.asyncio
    async def test_process_rejection(self):
        """Test rejecting an approval."""
        approval = await slack_server.send_approval_request(
            workflow_id="W-test-004",
            action_type="bulk_send",
            title="Test Rejection",
            description="Testing rejection flow",
            context={},
            risk_level="high"
        )
        
        result = await slack_server.process_interaction(
            approval_id=approval["approval_id"],
            action="reject",
            user_id="U12345",
            user_name="Reviewer"
        )
        
        assert result["ok"] is True
        assert result["action"] == "reject"
        assert result["status"] == "rejected"
    
    @pytest.mark.asyncio
    async def test_list_pending_approvals(self):
        """Test listing pending approvals."""
        # Clear existing
        slack_server.slack_client.pending_approvals.clear()
        
        # Create a few approvals
        await slack_server.send_approval_request(
            workflow_id="W-list-001",
            action_type="send_email",
            title="Pending 1",
            description="First pending",
            context={}
        )
        
        await slack_server.send_approval_request(
            workflow_id="W-list-002",
            action_type="create_event",
            title="Pending 2",
            description="Second pending",
            context={}
        )
        
        pending = await slack_server.list_pending_approvals()
        
        assert pending["count"] >= 2
        assert len(pending["approvals"]) >= 2
    
    @pytest.mark.asyncio
    async def test_approval_idempotency(self):
        """Test that approvals get unique IDs."""
        approval1 = await slack_server.send_approval_request(
            workflow_id="W-idem-001",
            action_type="send_email",
            title="Idem Test 1",
            description="Test 1",
            context={}
        )
        
        approval2 = await slack_server.send_approval_request(
            workflow_id="W-idem-001",
            action_type="send_email",
            title="Idem Test 2",
            description="Test 2",
            context={}
        )
        
        # Same workflow but different approvals should have different IDs
        assert approval1["approval_id"] != approval2["approval_id"]
    
    @pytest.mark.asyncio
    async def test_double_action_prevention(self):
        """Test that an approval can't be acted on twice."""
        approval = await slack_server.send_approval_request(
            workflow_id="W-double-001",
            action_type="send_email",
            title="Double Action Test",
            description="Testing double action prevention",
            context={}
        )
        
        # First approval
        result1 = await slack_server.process_interaction(
            approval_id=approval["approval_id"],
            action="approve",
            user_id="U12345",
            user_name="User 1"
        )
        
        # Second attempt should fail
        result2 = await slack_server.process_interaction(
            approval_id=approval["approval_id"],
            action="reject",
            user_id="U67890",
            user_name="User 2"
        )
        
        assert result1["ok"] is True
        assert result2["ok"] is False
        assert "already" in result2["error"].lower()


class TestBlockKitBuilders:
    """Test Block Kit building functions."""
    
    def test_build_approval_blocks(self):
        """Test approval block generation."""
        blocks = slack_server.build_approval_blocks(
            approval_id="APR-test123",
            title="Test Approval",
            description="Test description",
            context={"key": "value"},
            requester="TEST_AGENT",
            risk_level="high"
        )
        
        # Should have header, section, context, divider, fields, actions
        assert len(blocks) >= 5
        
        # First block should be header
        assert blocks[0]["type"] == "header"
        
        # Should have action buttons
        action_block = [b for b in blocks if b["type"] == "actions"][0]
        assert len(action_block["elements"]) == 3  # Approve, Reject, Edit
    
    def test_build_alert_blocks(self):
        """Test alert block generation."""
        blocks = slack_server.build_alert_blocks(
            title="Test Alert",
            message="Test message",
            level="critical",
            details={"metric": "100%"}
        )
        
        # Should have header, section, details, context
        assert len(blocks) >= 3
        
        # First block should be header with emoji
        assert blocks[0]["type"] == "header"


class TestSlackConfig:
    """Test Slack configuration."""
    
    def test_config_from_env(self):
        """Test loading config from environment."""
        with patch.dict(os.environ, {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "SLACK_SIGNING_SECRET": "test-secret",
            "SLACK_DEFAULT_CHANNEL": "#test-alerts"
        }):
            config = slack_config.SlackConfig.from_env()
            
            assert config.bot_token == "xoxb-test-token"
            assert config.signing_secret == "test-secret"
            assert config.default_channel == "#test-alerts"
            assert config.is_configured is True
    
    def test_config_validation(self):
        """Test configuration validation."""
        config = slack_config.SlackConfig(bot_token="", signing_secret="")
        issues = config.validate()
        
        assert len(issues) >= 2
        assert any("SLACK_BOT_TOKEN" in issue for issue in issues)
    
    def test_config_not_configured(self):
        """Test is_configured when token missing."""
        config = slack_config.SlackConfig()
        assert config.is_configured is False


class TestSlackIntegration:
    """Integration tests for Slack MCP with other components."""
    
    @pytest.mark.asyncio
    async def test_approval_workflow_integration(self):
        """Test approval workflow with guardrails integration."""
        # Simulate a GATEKEEPER approval request
        approval = await slack_server.send_approval_request(
            workflow_id="W-gate-001",
            action_type="send_email",
            title="Cold Outreach to Enterprise Lead",
            description="GATEKEEPER requests approval for cold email",
            context={
                "contact_id": "C-12345",
                "contact_name": "Jane Smith",
                "company": "Enterprise Corp",
                "template": "thought_leadership_v2",
                "risk_score": 0.7
            },
            requester="GATEKEEPER",
            risk_level="high",
            timeout_minutes=30
        )
        
        # Verify pending
        status = await slack_server.get_approval_status(approval["approval_id"])
        assert status["status"] == "pending"
        
        # Approve
        result = await slack_server.process_interaction(
            approval_id=approval["approval_id"],
            action="approve",
            user_id="U-AE-001",
            user_name="Account Executive"
        )
        
        # Verify approved
        final_status = await slack_server.get_approval_status(approval["approval_id"])
        assert final_status["status"] == "approved"
        assert final_status["approved_by"] == "Account Executive"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
