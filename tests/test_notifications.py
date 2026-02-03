
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from core.notifications import NotificationManager, get_notification_manager

@dataclass
class MockReviewItem:
    review_id: str = "rev_123"
    campaign_name: str = "Test Campaign"
    campaign_type: str = "outbound"
    lead_count: int = 100
    avg_icp_score: float = 85.5
    urgency: str = "normal"
    tier: str = "tier1"
    email_preview: Dict[str, str] = field(default_factory=lambda: {"subject_a": "Hello"})
    description: str = "A test review item"

@dataclass
class MockApprovalRequest:
    request_id: str = "req_456"
    requester_agent: str = "CRAFTER"
    action_type: str = "campaign_launch"
    payload: Dict[str, Any] = field(default_factory=lambda: {
        "campaign_name": "Approval Campaign",
        "lead_count": 50
    })
    risk_score: float = 0.2
    description: str = "Request description"
    # urgency might be missing, forcing default
    
@pytest.mark.asyncio
async def test_slack_notification_review_item():
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_post.return_value.__aenter__.return_value = mock_response
        
        manager = NotificationManager()
        manager.slack_webhook = "http://fake.url"
        
        item = MockReviewItem()
        result = await manager.send_slack_notification(item)
        
        assert result is True
        assert manager.notification_stats["slack_sent"] == 1
        
        # Verify payload structure
        call_args = mock_post.call_args
        assert call_args is not None
        payload = call_args.kwargs['json']
        assert payload['text'] == "Approval required: Test Campaign"
        # Check blocks
        header_block = payload['blocks'][0]
        assert "Approval Required" in header_block['text']['text']

@pytest.mark.asyncio
async def test_slack_notification_approval_request():
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_post.return_value.__aenter__.return_value = mock_response
        
        manager = NotificationManager()
        manager.slack_webhook = "http://fake.url"
        
        req = MockApprovalRequest()
        result = await manager.send_slack_notification(req)
        
        assert result is True
        
        # Verify payload fallback
        call_args = mock_post.call_args
        payload = call_args.kwargs['json']
        # Should fallback to payload['campaign_name']
        assert "Approval Campaign" in payload['text'] 
        
@pytest.mark.asyncio
async def test_escalation_logic():
    manager = NotificationManager()
    manager.slack_webhook = "http://fake.url"
    
    # Mock contacts
    manager.escalation_contacts = {
        "level2": [{"phone": "+15550000000"}],
        "level3": [{"email": "boss@example.com"}]
    }
    
    # Mock sending methods to avoid actual calls
    manager.send_slack_notification = AsyncMock(return_value=True)
    manager.send_sms_alert = AsyncMock(return_value=True)
    manager.send_email_fallback = AsyncMock(return_value=True)
    
    item = MockReviewItem()
    
    # Level 1
    await manager.escalate(item, level=1)
    manager.send_slack_notification.assert_called_once()
    manager.send_sms_alert.assert_not_called()
    
    # Reset
    manager.send_slack_notification.reset_mock()
    
    # Level 2
    await manager.escalate(item, level=2)
    manager.send_slack_notification.assert_called_once()
    manager.send_sms_alert.assert_called() 
    
    # Level 3
    await manager.escalate(item, level=3)
    manager.send_email_fallback.assert_called()

def test_singleton():
    m1 = get_notification_manager()
    m2 = get_notification_manager()
    assert m1 is m2
