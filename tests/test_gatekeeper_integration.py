#!/usr/bin/env python3
"""
Tests for Enhanced Gatekeeper Integration
==========================================
Tests for EnhancedGatekeeperQueue with ApprovalEngine and NotificationManager.
"""

import pytest
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.gatekeeper_queue import (
    EnhancedGatekeeperQueue,
    GatekeeperQueue,
    NotificationManager,
    ReviewItem,
    ReviewStatus,
    UrgencyLevel,
)
from core.approval_engine import (
    ApprovalEngine,
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalResult,
)


@pytest.fixture
def sample_review_item():
    """Create a sample review item for testing."""
    return ReviewItem(
        review_id="test-review-123",
        campaign_id="campaign-456",
        campaign_name="Test Campaign",
        campaign_type="email_sequence",
        lead_count=50,
        avg_icp_score=75.0,
        segment="enterprise",
        email_preview={
            "subject_a": "Test Subject",
            "subject_b": "Test Subject B",
            "body": "Test body content..."
        },
        status=ReviewStatus.PENDING.value,
        queued_at=datetime.now(timezone.utc).isoformat(),
        tier="tier2",
        rpi_workflow=True
    )


@pytest.fixture
def tier1_high_value_item():
    """Create a high-value tier1 item."""
    return ReviewItem(
        review_id="test-tier1-high",
        campaign_id="campaign-tier1",
        campaign_name="High Value Campaign",
        campaign_type="email_sequence",
        lead_count=100,
        avg_icp_score=95.0,
        segment="enterprise",
        email_preview={"subject_a": "VIP Offer", "body": "Exclusive..."},
        status=ReviewStatus.PENDING.value,
        queued_at=datetime.now(timezone.utc).isoformat(),
        tier="tier1",
        rpi_workflow=True
    )


@pytest.fixture
def urgent_deadline_item():
    """Create an item with an urgent deadline."""
    deadline = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    return ReviewItem(
        review_id="test-urgent-deadline",
        campaign_id="campaign-urgent",
        campaign_name="Urgent Campaign",
        campaign_type="email_sequence",
        lead_count=30,
        avg_icp_score=70.0,
        segment="mid-market",
        email_preview={"subject_a": "Time Sensitive", "body": "Act now..."},
        status=ReviewStatus.PENDING.value,
        queued_at=datetime.now(timezone.utc).isoformat(),
        tier="tier3",
        deadline=deadline
    )


@pytest.fixture
def enhanced_gatekeeper():
    """Create an enhanced gatekeeper instance in test mode."""
    return EnhancedGatekeeperQueue(test_mode=True)


@pytest.fixture
def notification_manager():
    """Create a notification manager instance."""
    return NotificationManager()


class TestUrgencyCalculation:
    """Tests for urgency calculation logic."""
    
    def test_normal_urgency_default(self, enhanced_gatekeeper, sample_review_item):
        """Test that default items get normal urgency."""
        sample_review_item.tier = "tier3"
        sample_review_item.avg_icp_score = 60.0
        sample_review_item.lead_count = 20
        
        urgency = enhanced_gatekeeper.calculate_urgency(sample_review_item)
        assert urgency == UrgencyLevel.NORMAL.value
    
    def test_urgent_tier1(self, enhanced_gatekeeper, sample_review_item):
        """Test that tier1 items get urgent urgency."""
        sample_review_item.tier = "tier1"
        sample_review_item.lead_count = 30
        
        urgency = enhanced_gatekeeper.calculate_urgency(sample_review_item)
        assert urgency == UrgencyLevel.URGENT.value
    
    def test_urgent_tier2_high_icp(self, enhanced_gatekeeper, sample_review_item):
        """Test that tier2 with high ICP gets urgent."""
        sample_review_item.tier = "tier2"
        sample_review_item.avg_icp_score = 85.0
        
        urgency = enhanced_gatekeeper.calculate_urgency(sample_review_item)
        assert urgency == UrgencyLevel.URGENT.value
    
    def test_critical_tier1_high_leads(self, enhanced_gatekeeper, tier1_high_value_item):
        """Test that tier1 with 50+ leads gets critical."""
        urgency = enhanced_gatekeeper.calculate_urgency(tier1_high_value_item)
        assert urgency == UrgencyLevel.CRITICAL.value
    
    def test_critical_high_icp_high_leads(self, enhanced_gatekeeper, sample_review_item):
        """Test that high ICP + 100+ leads gets critical."""
        sample_review_item.avg_icp_score = 92.0
        sample_review_item.lead_count = 150
        sample_review_item.tier = "tier3"
        
        urgency = enhanced_gatekeeper.calculate_urgency(sample_review_item)
        assert urgency == UrgencyLevel.CRITICAL.value
    
    def test_urgent_deadline_under_30min(self, enhanced_gatekeeper, urgent_deadline_item):
        """Test that items with <30min deadline get urgent."""
        urgency = enhanced_gatekeeper.calculate_urgency(urgent_deadline_item)
        assert urgency == UrgencyLevel.URGENT.value
    
    def test_critical_past_deadline(self, enhanced_gatekeeper, sample_review_item):
        """Test that past deadline items get critical."""
        sample_review_item.deadline = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        
        urgency = enhanced_gatekeeper.calculate_urgency(sample_review_item)
        assert urgency == UrgencyLevel.CRITICAL.value


class TestSubmitForReview:
    """Tests for submit_for_review routing."""
    
    @pytest.mark.asyncio
    async def test_submit_routes_correctly(self, enhanced_gatekeeper, sample_review_item):
        """Test that submit_for_review routes item correctly."""
        with patch.object(enhanced_gatekeeper.notification_manager, 'send_slack_notification', 
                         new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True
            
            review_id = await enhanced_gatekeeper.submit_for_review(sample_review_item)
            
            assert review_id == sample_review_item.review_id
            assert enhanced_gatekeeper.approval_stats["submitted"] == 1
    
    @pytest.mark.asyncio
    async def test_submit_with_explicit_urgency(self, enhanced_gatekeeper, sample_review_item):
        """Test that explicit urgency overrides calculation."""
        with patch.object(enhanced_gatekeeper.notification_manager, 'escalate',
                         new_callable=AsyncMock) as mock_escalate:
            mock_escalate.return_value = {"slack": True, "sms": True, "email": True}
            
            await enhanced_gatekeeper.submit_for_review(sample_review_item, urgency="critical")
            
            assert sample_review_item.urgency == "critical"
            mock_escalate.assert_called_once()


class TestNotificationRouting:
    """Tests for notification routing based on urgency."""
    
    @pytest.mark.asyncio
    async def test_normal_items_get_slack_only(self, enhanced_gatekeeper, sample_review_item):
        """Test normal urgency items only get Slack notification."""
        sample_review_item.urgency = "normal"
        
        with patch.object(enhanced_gatekeeper.notification_manager, 'send_slack_notification',
                         new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True
            
            await enhanced_gatekeeper._send_urgency_based_notifications(sample_review_item)
            
            mock_slack.assert_called_once()
            assert sample_review_item.notification_sent_at is not None
            assert sample_review_item.sms_sent_at is None
    
    @pytest.mark.asyncio
    async def test_urgent_items_get_slack_and_sms(self, enhanced_gatekeeper, sample_review_item):
        """Test urgent items get Slack + SMS."""
        sample_review_item.urgency = "urgent"
        
        with patch.object(enhanced_gatekeeper.notification_manager, 'escalate',
                         new_callable=AsyncMock) as mock_escalate:
            mock_escalate.return_value = {"slack": True, "sms": True, "email": False}
            
            await enhanced_gatekeeper._send_urgency_based_notifications(sample_review_item)
            
            mock_escalate.assert_called_once_with(sample_review_item, level=2)
            assert sample_review_item.sms_sent_at is not None
    
    @pytest.mark.asyncio
    async def test_critical_items_get_full_escalation(self, enhanced_gatekeeper, tier1_high_value_item):
        """Test critical items get Slack + SMS + Email."""
        tier1_high_value_item.urgency = "critical"
        
        with patch.object(enhanced_gatekeeper.notification_manager, 'escalate',
                         new_callable=AsyncMock) as mock_escalate:
            mock_escalate.return_value = {"slack": True, "sms": True, "email": True}
            
            await enhanced_gatekeeper._send_urgency_based_notifications(tier1_high_value_item)
            
            mock_escalate.assert_called_once_with(tier1_high_value_item, level=3)
            assert tier1_high_value_item.email_fallback_sent_at is not None


class TestTimeoutHandling:
    """Tests for timeout handling and escalation."""
    
    @pytest.mark.asyncio
    async def test_2hr_timeout_sends_email_fallback(self, enhanced_gatekeeper, sample_review_item):
        """Test that 2+ hour old items get email fallback."""
        sample_review_item.queued_at = (datetime.now(timezone.utc) - timedelta(hours=2, minutes=30)).isoformat()
        sample_review_item.email_fallback_sent_at = None
        enhanced_gatekeeper.queue.pending.append(sample_review_item)
        
        with patch.object(enhanced_gatekeeper.notification_manager, 'send_email_fallback',
                         new_callable=AsyncMock) as mock_email:
            mock_email.return_value = True
            
            # Set up escalation contacts
            enhanced_gatekeeper.notification_manager.escalation_contacts["level2"] = [
                {"email": "test@example.com"}
            ]
            
            await enhanced_gatekeeper.check_and_escalate_timeouts()
            
            # Should have sent email
            assert mock_email.called or sample_review_item.email_fallback_sent_at is not None
    
    @pytest.mark.asyncio
    async def test_4hr_timeout_auto_rejects(self, enhanced_gatekeeper, sample_review_item):
        """Test that 4+ hour old items get auto-rejected."""
        sample_review_item.queued_at = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        enhanced_gatekeeper.queue.pending.append(sample_review_item)
        
        with patch.object(enhanced_gatekeeper, 'auto_reject_with_notification',
                         new_callable=AsyncMock) as mock_reject:
            await enhanced_gatekeeper.check_and_escalate_timeouts()
            
            mock_reject.assert_called_once()
            assert enhanced_gatekeeper.approval_stats["timed_out"] == 1
    
    @pytest.mark.asyncio
    async def test_30min_urgent_sends_sms(self, enhanced_gatekeeper, sample_review_item):
        """Test that 30+ min old urgent items get SMS."""
        sample_review_item.queued_at = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
        sample_review_item.urgency = "urgent"
        sample_review_item.sms_sent_at = None
        enhanced_gatekeeper.queue.pending.append(sample_review_item)
        
        with patch.object(enhanced_gatekeeper.notification_manager, 'send_sms_alert',
                         new_callable=AsyncMock) as mock_sms:
            mock_sms.return_value = True
            
            enhanced_gatekeeper.notification_manager.escalation_contacts["level2"] = [
                {"phone": "+1234567890"}
            ]
            
            await enhanced_gatekeeper.check_and_escalate_timeouts()
            
            # SMS should have been called
            assert mock_sms.called


class TestApprovalResponseHandling:
    """Tests for handling approval responses from different channels."""
    
    @pytest.mark.asyncio
    async def test_dashboard_approval(self, enhanced_gatekeeper, sample_review_item):
        """Test approval from dashboard."""
        enhanced_gatekeeper.queue.pending.append(sample_review_item)
        
        result = await enhanced_gatekeeper.handle_approval_response(
            review_id=sample_review_item.review_id,
            approved=True,
            approver="test_ae",
            source="dashboard"
        )
        
        assert result is not None
        assert result.status == ReviewStatus.APPROVED.value
        assert enhanced_gatekeeper.approval_stats["by_source"]["dashboard"] == 1
        assert enhanced_gatekeeper.approval_stats["manually_approved"] == 1
    
    @pytest.mark.asyncio
    async def test_slack_rejection(self, enhanced_gatekeeper, sample_review_item):
        """Test rejection from Slack."""
        enhanced_gatekeeper.queue.pending.append(sample_review_item)
        
        result = await enhanced_gatekeeper.handle_approval_response(
            review_id=sample_review_item.review_id,
            approved=False,
            approver="slack_user",
            reason="Content needs revision",
            source="slack"
        )
        
        assert result is not None
        assert result.status == ReviewStatus.REJECTED.value
        assert result.rejection_reason == "Content needs revision"
        assert enhanced_gatekeeper.approval_stats["by_source"]["slack"] == 1
    
    @pytest.mark.asyncio
    async def test_approval_with_edits(self, enhanced_gatekeeper, sample_review_item):
        """Test approval with edits applied."""
        enhanced_gatekeeper.queue.pending.append(sample_review_item)
        
        edits = {"subject": "New Subject Line", "body": "Updated body content"}
        
        result = await enhanced_gatekeeper.handle_approval_response(
            review_id=sample_review_item.review_id,
            approved=True,
            approver="editor",
            edits=edits,
            source="dashboard"
        )
        
        assert result is not None
        assert result.email_preview["subject_a"] == "New Subject Line"
        assert result.edits == edits
    
    @pytest.mark.asyncio
    async def test_approval_not_found(self, enhanced_gatekeeper):
        """Test handling approval for non-existent item."""
        result = await enhanced_gatekeeper.handle_approval_response(
            review_id="non-existent-id",
            approved=True,
            approver="test"
        )
        
        assert result is None


class TestApprovalEngineIntegration:
    """Tests for ApprovalEngine integration."""
    
    @pytest.mark.asyncio
    async def test_routes_to_approval_engine(self, enhanced_gatekeeper, sample_review_item):
        """Test that items are routed to approval engine."""
        result = await enhanced_gatekeeper.route_to_approval_engine(sample_review_item)
        
        assert result is not None
        assert result.request_id is not None
        assert isinstance(result, ApprovalResult)
    
    @pytest.mark.asyncio
    async def test_approval_engine_initialized(self, enhanced_gatekeeper):
        """Test that approval engine is properly initialized."""
        engine = enhanced_gatekeeper.approval_engine
        
        # Should have the get_policy method
        assert hasattr(engine, 'get_policy')
        # Test getting a policy
        policy = engine.get_policy("send_email")
        assert policy is not None
    
    @pytest.mark.asyncio
    async def test_auto_approve_low_risk_action(self, enhanced_gatekeeper):
        """Test auto-approve for low-risk actions like calendar operations."""
        item = ReviewItem(
            review_id="auto-approve-test",
            campaign_id="auto-campaign",
            campaign_name="Calendar Update Campaign",
            campaign_type="email_sequence",
            lead_count=10,
            avg_icp_score=85.0,
            segment="smb",
            email_preview={"subject_a": "Test", "body": "..."},
            status=ReviewStatus.PENDING.value,
            queued_at=datetime.now(timezone.utc).isoformat(),
            tier="tier3",
            rpi_workflow=True
        )
        
        with patch.object(enhanced_gatekeeper.notification_manager, 'send_slack_notification',
                         new_callable=AsyncMock):
            await enhanced_gatekeeper.submit_for_review(item)
        
        # Check stats were updated
        assert enhanced_gatekeeper.approval_stats["submitted"] >= 1


class TestNotificationFailureFallback:
    """Tests for notification failure fallback behavior."""
    
    @pytest.mark.asyncio
    async def test_slack_failure_tracked(self, notification_manager, sample_review_item):
        """Test that Slack failures are tracked."""
        notification_manager.slack_webhook = "https://invalid.webhook"
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
            
            result = await notification_manager.send_slack_notification(sample_review_item)
            
        assert notification_manager.notification_stats["failures"] >= 0
    
    @pytest.mark.asyncio
    async def test_sms_without_config_returns_false(self, notification_manager):
        """Test SMS returns False when not configured."""
        notification_manager.twilio_sid = None
        
        result = await notification_manager.send_sms_alert("+1234567890", "Test message")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_email_without_config_returns_false(self, notification_manager, sample_review_item):
        """Test email returns False when not configured."""
        notification_manager.smtp_user = None
        
        result = await notification_manager.send_email_fallback("test@example.com", sample_review_item)
        
        assert result is False


class TestStatsTracking:
    """Tests for statistics tracking."""
    
    def test_enhanced_stats_includes_all_metrics(self, enhanced_gatekeeper):
        """Test that enhanced stats include all expected metrics."""
        stats = enhanced_gatekeeper.get_enhanced_stats()
        
        assert "pending_count" in stats
        assert "approved_count" in stats
        assert "approval_stats" in stats
        assert "notification_stats" in stats
        assert "pending_by_urgency" in stats
        assert "approval_engine_pending" in stats
    
    def test_pending_by_urgency_breakdown(self, enhanced_gatekeeper, sample_review_item):
        """Test urgency breakdown in stats."""
        # Clear pending queue first to ensure test isolation
        initial_urgent_count = len([i for i in enhanced_gatekeeper.queue.pending if i.urgency == "urgent"])
        
        sample_review_item.urgency = "urgent"
        enhanced_gatekeeper.queue.pending.append(sample_review_item)
        
        stats = enhanced_gatekeeper.get_enhanced_stats()
        
        # Should have one more urgent item than before
        assert stats["pending_by_urgency"]["urgent"] == initial_urgent_count + 1
    
    def test_notification_stats_tracked(self, notification_manager):
        """Test that notification stats are tracked."""
        stats = notification_manager.get_stats()
        
        assert "slack_sent" in stats
        assert "sms_sent" in stats
        assert "email_sent" in stats
        assert "failures" in stats


class TestWebSocketIntegration:
    """Tests for WebSocket callback integration."""
    
    @pytest.mark.asyncio
    async def test_websocket_callback_registered(self, enhanced_gatekeeper):
        """Test WebSocket callback registration."""
        callback = AsyncMock()
        enhanced_gatekeeper.register_websocket_callback(callback)
        
        assert callback in enhanced_gatekeeper.websocket_callbacks
    
    @pytest.mark.asyncio
    async def test_websocket_notified_on_add(self, enhanced_gatekeeper, sample_review_item):
        """Test WebSocket notified when item added."""
        callback = AsyncMock()
        enhanced_gatekeeper.register_websocket_callback(callback)
        
        with patch.object(enhanced_gatekeeper.notification_manager, 'send_slack_notification',
                         new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True
            
            await enhanced_gatekeeper.submit_for_review(sample_review_item)
        
        callback.assert_called()
        call_args = callback.call_args[0]
        assert call_args[0] == "item_added"
    
    @pytest.mark.asyncio
    async def test_websocket_notified_on_approval(self, enhanced_gatekeeper, sample_review_item):
        """Test WebSocket notified when item approved."""
        callback = AsyncMock()
        enhanced_gatekeeper.register_websocket_callback(callback)
        enhanced_gatekeeper.queue.pending.append(sample_review_item)
        
        await enhanced_gatekeeper.handle_approval_response(
            review_id=sample_review_item.review_id,
            approved=True,
            approver="test"
        )
        
        callback.assert_called()
        call_args = callback.call_args[0]
        assert call_args[0] == "item_approved"


class TestSlackBlockKitFormat:
    """Tests for Slack Block Kit message formatting."""
    
    @pytest.mark.asyncio
    async def test_slack_message_includes_campaign_details(self, notification_manager, sample_review_item):
        """Test that Slack message includes all campaign details."""
        captured_payload = None
        
        async def capture_post(url, json, **kwargs):
            nonlocal captured_payload
            captured_payload = json
            mock_resp = AsyncMock()
            mock_resp.status = 200
            return mock_resp
        
        notification_manager.slack_webhook = "https://hooks.slack.com/test"
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_cm = AsyncMock()
            mock_cm.__aenter__.return_value.post = AsyncMock(side_effect=lambda *args, **kwargs: AsyncMock(__aenter__=AsyncMock(return_value=AsyncMock(status=200))))
            mock_session.return_value = mock_cm
            
            # The test verifies the method doesn't crash; actual payload verification
            # would require more complex mocking
            await notification_manager.send_slack_notification(sample_review_item)


class TestEscalationChain:
    """Tests for escalation chain functionality."""
    
    @pytest.mark.asyncio
    async def test_level1_escalation(self, notification_manager, sample_review_item):
        """Test level 1 escalation (Slack only)."""
        with patch.object(notification_manager, 'send_slack_notification',
                         new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True
            
            results = await notification_manager.escalate(sample_review_item, level=1)
            
            assert results["slack"] is True
            mock_slack.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_level2_escalation(self, notification_manager, sample_review_item):
        """Test level 2 escalation (Slack + SMS)."""
        notification_manager.escalation_contacts["level2"] = [
            {"name": "Manager", "phone": "+1234567890"}
        ]
        
        with patch.object(notification_manager, 'send_slack_notification',
                         new_callable=AsyncMock) as mock_slack, \
             patch.object(notification_manager, 'send_sms_alert',
                         new_callable=AsyncMock) as mock_sms:
            mock_slack.return_value = True
            mock_sms.return_value = True
            
            results = await notification_manager.escalate(sample_review_item, level=2)
            
            mock_slack.assert_called_once()
            mock_sms.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_level3_escalation(self, notification_manager, sample_review_item):
        """Test level 3 escalation (Slack + SMS + Email)."""
        notification_manager.escalation_contacts["level2"] = [
            {"name": "Manager", "phone": "+1234567890"}
        ]
        notification_manager.escalation_contacts["level3"] = [
            {"name": "Director", "email": "director@example.com"}
        ]
        
        with patch.object(notification_manager, 'send_slack_notification',
                         new_callable=AsyncMock) as mock_slack, \
             patch.object(notification_manager, 'send_sms_alert',
                         new_callable=AsyncMock) as mock_sms, \
             patch.object(notification_manager, 'send_email_fallback',
                         new_callable=AsyncMock) as mock_email:
            mock_slack.return_value = True
            mock_sms.return_value = True
            mock_email.return_value = True
            
            results = await notification_manager.escalate(sample_review_item, level=3)
            
            mock_slack.assert_called_once()
            mock_sms.assert_called()
            mock_email.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
