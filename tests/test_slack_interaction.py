
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from core.slack_handler import SlackInteractionHandler

@pytest.mark.asyncio
async def test_handle_approve_action():
    with patch("core.slack_handler.get_approval_engine") as mock_get:
        mock_engine = MagicMock()
        mock_get.return_value = mock_engine
        
        handler = SlackInteractionHandler()
        
        payload = {
            "user": {"username": "tester", "id": "U123"},
            "actions": [{"action_id": "approve_req_123"}],
            "message": {
                "blocks": [
                    {"type": "header", "text": {"text": "Header"}},
                    {"type": "actions", "elements": []} 
                ]
            }
        }
        
        result = await handler.handle_payload(payload)
        
        # Verify engine call
        mock_engine.approve_request.assert_called_once_with(
            "req_123", "tester (U123)", "Approved via Slack"
        )
        
        # Verify result
        assert result["replace_original"] is True
        # The actions block should be gone
        assert len(result["blocks"]) == 2 # Header + Context
        assert result["blocks"][1]["type"] == "context"
        assert "Approved" in result["blocks"][1]["elements"][0]["text"]

@pytest.mark.asyncio
async def test_handle_reject_action():
    with patch("core.slack_handler.get_approval_engine") as mock_get:
        mock_engine = MagicMock()
        mock_get.return_value = mock_engine
        
        handler = SlackInteractionHandler()
        
        payload = {
            "user": {"username": "tester", "id": "U123"},
            "actions": [{"action_id": "reject_req_456"}],
            "message": {"blocks": []}
        }
        
        result = await handler.handle_payload(payload)
        
        mock_engine.reject_request.assert_called_once_with(
            "req_456", "tester (U123)", "Rejected via Slack"
        )
        
        assert "Rejected" in result["blocks"][0]["elements"][0]["text"]

@pytest.mark.asyncio
async def test_handle_unknown_action():
    with patch("core.slack_handler.get_approval_engine") as mock_get:
        mock_engine = MagicMock()
        mock_get.return_value = mock_engine
        
        handler = SlackInteractionHandler()
        payload = {"actions": [{"action_id": "dance_req_789"}]}
        
        result = await handler.handle_payload(payload)
        
        # Should log warning and return empty, meaning no update
        assert result == {}
        mock_engine.approve_request.assert_not_called()
