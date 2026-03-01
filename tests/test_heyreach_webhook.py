#!/usr/bin/env python3
"""
HeyReach Webhook Handler Tests
================================
Tests for webhook event routing, payload extraction, auth health check,
and unknown event alerting.

All tests use mocking — no real API calls or FastAPI server.
"""

import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from webhooks.heyreach_webhook import (
    _extract_lead_info,
    _flag_for_followup,
    _handle_unknown,
    _handle_connection_accepted,
    _handle_reply_received,
    _handle_campaign_completed,
    EVENT_HANDLERS,
)


# =============================================================================
# TEST: Lead Info Extraction (HR-05)
# =============================================================================

class TestLeadInfoExtraction:
    """Tests for HR-05: payload field extraction and schema discovery."""

    def test_camelcase_fields_extracted(self):
        """CamelCase field names (API convention) are extracted."""
        payload = {
            "linkedInUrl": "https://linkedin.com/in/johndoe",
            "firstName": "John",
            "lastName": "Doe",
            "companyName": "Acme",
            "email": "john@acme.com",
            "campaignId": "camp_001",
            "leadId": "lead_abc",
        }
        lead = _extract_lead_info(payload)
        assert lead["linkedin_url"] == "https://linkedin.com/in/johndoe"
        assert lead["first_name"] == "John"
        assert lead["last_name"] == "Doe"
        assert lead["company"] == "Acme"
        assert lead["email"] == "john@acme.com"
        assert lead["campaign_id"] == "camp_001"
        assert lead["lead_id"] == "lead_abc"

    def test_snake_case_fallback(self):
        """Snake_case field names (alternative) are extracted as fallback."""
        payload = {
            "linkedin_url": "https://linkedin.com/in/jane",
            "first_name": "Jane",
            "last_name": "Smith",
            "company": "BigCorp",
            "campaign_id": "camp_002",
            "lead_id": "lead_xyz",
        }
        lead = _extract_lead_info(payload)
        assert lead["linkedin_url"] == "https://linkedin.com/in/jane"
        assert lead["first_name"] == "Jane"
        assert lead["company"] == "BigCorp"

    def test_missing_fields_default_empty(self):
        """Missing fields default to empty string, no exceptions."""
        lead = _extract_lead_info({})
        assert lead["linkedin_url"] == ""
        assert lead["first_name"] == ""
        assert lead["email"] == ""
        assert lead["campaign_id"] == ""

    def test_empty_fields_logged_as_warning(self):
        """Empty fields trigger a warning log for schema discovery."""
        with patch("webhooks.heyreach_webhook.logger") as mock_logger:
            _extract_lead_info({"eventType": "TEST"})
            # Should warn about empty fields
            mock_logger.warning.assert_called()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "empty fields" in warning_msg

    def test_payload_keys_logged(self):
        """All top-level keys are logged for schema discovery."""
        with patch("webhooks.heyreach_webhook.logger") as mock_logger:
            _extract_lead_info({"foo": "bar", "baz": 123})
            # Should log the keys
            info_calls = [c for c in mock_logger.info.call_args_list
                          if "payload keys" in str(c).lower()]
            assert len(info_calls) >= 1


# =============================================================================
# TEST: Event Handler Routing
# =============================================================================

class TestEventHandlerRouting:
    """Tests for event type routing to correct handlers."""

    def test_all_11_events_registered(self):
        """All 11 documented event types have handlers."""
        expected_events = {
            "CONNECTION_REQUEST_SENT",
            "CONNECTION_REQUEST_ACCEPTED",
            "MESSAGE_SENT",
            "MESSAGE_REPLY_RECEIVED",
            "INMAIL_SENT",
            "INMAIL_REPLY_RECEIVED",
            "FOLLOW_SENT",
            "LIKED_POST",
            "VIEWED_PROFILE",
            "CAMPAIGN_COMPLETED",
            "LEAD_TAG_UPDATED",
        }
        assert set(EVENT_HANDLERS.keys()) == expected_events

    def test_unknown_event_falls_through_to_default(self):
        """Unknown event type is not in handler map."""
        assert "SOME_NEW_EVENT" not in EVENT_HANDLERS


# =============================================================================
# TEST: Unknown Event Alerting (HR-21)
# =============================================================================

class TestUnknownEventAlert:
    """Tests for HR-21: Slack alert on unknown events."""

    @pytest.mark.asyncio
    async def test_unknown_event_sends_slack_alert(self):
        """Unknown event triggers Slack warning alert."""
        with patch("webhooks.heyreach_webhook._slack_alert") as mock_alert:
            result = await _handle_unknown("NEW_EVENT_TYPE", {"key": "val"}, {})

            assert result["action"] == "unknown_event_logged"
            mock_alert.assert_called_once()
            call_args = mock_alert.call_args
            assert "NEW_EVENT_TYPE" in call_args[0][0]
            assert call_args[1]["level"] == "warning"

    @pytest.mark.asyncio
    async def test_unknown_event_includes_payload_keys(self):
        """Alert includes payload keys for debugging."""
        with patch("webhooks.heyreach_webhook._slack_alert") as mock_alert:
            await _handle_unknown("X", {"alpha": 1, "beta": 2}, {})

            message = mock_alert.call_args[0][1]
            assert "alpha" in message
            assert "beta" in message


# =============================================================================
# TEST: Connection Accepted Handler
# =============================================================================

class TestConnectionAccepted:

    @pytest.mark.asyncio
    async def test_flags_for_followup(self):
        """CONNECTION_REQUEST_ACCEPTED writes a follow-up flag file."""
        lead = {
            "linkedin_url": "https://linkedin.com/in/test",
            "first_name": "Test",
            "last_name": "User",
            "email": "test@co.com",
            "company": "TestCo",
        }
        with patch("webhooks.heyreach_webhook._flag_for_followup") as mock_flag, \
             patch("webhooks.heyreach_webhook._slack_alert"), \
             patch("webhooks.heyreach_webhook._get_signal_manager") as mock_sm:
            mock_sm.return_value = MagicMock()
            result = await _handle_connection_accepted("CONNECTION_REQUEST_ACCEPTED", {}, lead)

        assert result["action"] == "flagged_for_followup"
        mock_flag.assert_called_once_with(lead, "connection_accepted")


# =============================================================================
# TEST: Reply Handler
# =============================================================================

class TestReplyHandler:

    @pytest.mark.asyncio
    async def test_reply_logged_with_classification_flag(self):
        """Reply handler returns needs_classification=True."""
        lead = {"linkedin_url": "https://linkedin.com/in/test", "first_name": "Test", "last_name": "User", "email": "t@co.com"}
        payload = {"messageText": "Sounds interesting, let's chat!"}

        with patch("webhooks.heyreach_webhook._slack_alert"), \
             patch("webhooks.heyreach_webhook._get_signal_manager") as mock_sm:
            mock_sm.return_value = MagicMock()
            result = await _handle_reply_received("MESSAGE_REPLY_RECEIVED", payload, lead)

        assert result["action"] == "reply_logged"
        assert result["needs_classification"] is True


# =============================================================================
# TEST: Follow-up Flag Writer (HR-07 partial)
# =============================================================================

class TestFollowupFlag:

    def test_flag_file_created(self, tmp_path):
        """Follow-up flag creates a JSON file in followup dir."""
        lead = {"linkedin_url": "https://linkedin.com/in/flag-test", "email": "flag@test.com"}

        with patch("webhooks.heyreach_webhook.PROJECT_ROOT", tmp_path):
            _flag_for_followup(lead, "connection_accepted")

        followup_dir = tmp_path / ".hive-mind" / "heyreach_followups"
        files = list(followup_dir.glob("*.json"))
        assert len(files) == 1

        with open(files[0], "r") as f:
            data = json.load(f)
        assert data["reason"] == "connection_accepted"
        assert data["processed"] is False
        assert data["lead"]["email"] == "flag@test.com"


# =============================================================================
# TEST: Health Check (HR-11)
# =============================================================================

class TestWebhookHealthCheck:
    """Tests for HR-11: webhook auth warnings in health check."""

    @pytest.mark.asyncio
    async def test_health_warns_when_unsigned_allowed(self):
        """Health check warns when HEYREACH_UNSIGNED_ALLOWLIST is true."""
        with patch.dict(os.environ, {
            "HEYREACH_UNSIGNED_ALLOWLIST": "true",
            "HEYREACH_WEBHOOK_SECRET": "",
            "HEYREACH_API_KEY": "test",
        }):
            from webhooks.heyreach_webhook import heyreach_webhook_health
            result = await heyreach_webhook_health()

        assert result["unsigned_allowlisted"] is True
        assert any("UNSIGNED" in w.upper() for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_health_no_warning_when_secret_set(self):
        """No auth warning when webhook secret is configured."""
        with patch.dict(os.environ, {
            "HEYREACH_UNSIGNED_ALLOWLIST": "false",
            "HEYREACH_WEBHOOK_SECRET": "my-secret-key",
            "HEYREACH_API_KEY": "test",
        }):
            from webhooks.heyreach_webhook import heyreach_webhook_health
            result = await heyreach_webhook_health()

        assert result["unsigned_allowlisted"] is False
        assert result["secret_configured"] is True

    @pytest.mark.asyncio
    async def test_health_warns_no_auth_at_all(self):
        """Health check warns when no auth method is configured."""
        with patch.dict(os.environ, {
            "HEYREACH_UNSIGNED_ALLOWLIST": "false",
            "HEYREACH_WEBHOOK_SECRET": "",
            "WEBHOOK_BEARER_TOKEN": "",
            "HEYREACH_API_KEY": "test",
            "WEBHOOK_SIGNATURE_REQUIRED": "false",
        }):
            from webhooks.heyreach_webhook import heyreach_webhook_health
            result = await heyreach_webhook_health()

        assert result["unsigned_allowlisted"] is False
        assert any("No webhook auth" in w for w in result["warnings"])


# =============================================================================
# TEST: Email Validation in Signal Loop (HR-12)
# =============================================================================

class TestSignalLoopEmailValidation:
    """Tests for HR-12: warn when email is missing from webhook payload."""

    @pytest.mark.asyncio
    async def test_connection_accepted_warns_on_empty_email(self):
        """Connection accepted handler warns when email is empty."""
        lead = {"linkedin_url": "https://linkedin.com/in/test", "first_name": "Test", "email": ""}
        with patch("webhooks.heyreach_webhook.logger") as mock_logger, \
             patch("webhooks.heyreach_webhook._flag_for_followup"), \
             patch("webhooks.heyreach_webhook._slack_alert"), \
             patch("webhooks.heyreach_webhook._get_signal_manager") as mock_sm:
            mock_sm.return_value = MagicMock()
            await _handle_connection_accepted("CONNECTION_REQUEST_ACCEPTED", {}, lead)

        warning_calls = [c for c in mock_logger.warning.call_args_list if "HR-12" in str(c)]
        assert len(warning_calls) >= 1

    @pytest.mark.asyncio
    async def test_connection_accepted_no_warning_with_email(self):
        """No HR-12 warning when email is present."""
        lead = {"linkedin_url": "https://linkedin.com/in/test", "first_name": "Test", "email": "test@co.com"}
        with patch("webhooks.heyreach_webhook.logger") as mock_logger, \
             patch("webhooks.heyreach_webhook._flag_for_followup"), \
             patch("webhooks.heyreach_webhook._slack_alert"), \
             patch("webhooks.heyreach_webhook._get_signal_manager") as mock_sm:
            mock_sm.return_value = MagicMock()
            await _handle_connection_accepted("CONNECTION_REQUEST_ACCEPTED", {}, lead)

        warning_calls = [c for c in mock_logger.warning.call_args_list if "HR-12" in str(c)]
        assert len(warning_calls) == 0
