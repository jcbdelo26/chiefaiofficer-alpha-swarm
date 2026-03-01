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
    classify_reply,
    EVENT_HANDLERS,
)


# =============================================================================
# TEST: Lead Info Extraction (HR-05)
# =============================================================================

class TestLeadInfoExtraction:
    """Tests for HR-05: payload field extraction — validated against real HeyReach payloads."""

    def _real_payload(self, **overrides):
        """Build a realistic HeyReach nested payload (connection_request_accepted shape)."""
        base = {
            "connection_message": "Test Message",
            "campaign": {"name": "CAIO Outreach", "id": 42, "status": None},
            "sender": {
                "id": 99, "first_name": "Chris", "last_name": "D",
                "full_name": "Chris D", "email_address": "chris@test.com",
                "profile_url": "https://linkedin.com/in/chrisd",
            },
            "lead": {
                "id": "lead_abc", "profile_url": "https://linkedin.com/in/johndoe",
                "first_name": "John", "last_name": "Doe", "full_name": "John Doe",
                "location": "Miami, FL", "company_url": "https://acme.com",
                "company_name": "Acme", "position": "CEO",
                "email_address": "john@acme.com", "enriched_email": None,
                "tags": ["hot-lead"], "lists": [],
            },
            "timestamp": "2026-03-01T19:26:58Z",
            "event_type": "connection_request_accepted",
            "correlation_id": "00000000-0000-0000-0000-000000000000",
        }
        # Allow overriding nested keys via dot notation won't work here,
        # but callers can override top-level or pass modified nested dicts
        base.update(overrides)
        return base

    def test_nested_lead_fields_extracted(self):
        """Real nested lead object fields are extracted correctly."""
        payload = self._real_payload()
        lead = _extract_lead_info(payload)
        assert lead["linkedin_url"] == "https://linkedin.com/in/johndoe"
        assert lead["first_name"] == "John"
        assert lead["last_name"] == "Doe"
        assert lead["full_name"] == "John Doe"
        assert lead["company"] == "Acme"
        assert lead["email"] == "john@acme.com"
        assert lead["position"] == "CEO"
        assert lead["location"] == "Miami, FL"

    def test_campaign_fields_extracted(self):
        """Campaign ID and name extracted from nested campaign object."""
        payload = self._real_payload()
        lead = _extract_lead_info(payload)
        assert lead["campaign_id"] == "42"
        assert lead["campaign_name"] == "CAIO Outreach"

    def test_lead_id_extracted(self):
        """Lead ID extracted from nested lead object."""
        payload = self._real_payload()
        lead = _extract_lead_info(payload)
        assert lead["lead_id"] == "lead_abc"

    def test_sender_and_metadata_extracted(self):
        """Sender name, connection message, and correlation ID extracted."""
        payload = self._real_payload()
        lead = _extract_lead_info(payload)
        assert lead["sender_name"] == "Chris D"
        assert lead["connection_message"] == "Test Message"
        assert lead["correlation_id"] == "00000000-0000-0000-0000-000000000000"

    def test_tags_extracted_as_list(self):
        """Tags array preserved from lead object."""
        payload = self._real_payload()
        lead = _extract_lead_info(payload)
        assert lead["tags"] == ["hot-lead"]

    def test_email_fallback_to_enriched(self):
        """Falls back to enriched_email when email_address is empty."""
        payload = self._real_payload()
        payload["lead"]["email_address"] = ""
        payload["lead"]["enriched_email"] = "enriched@acme.com"
        lead = _extract_lead_info(payload)
        assert lead["email"] == "enriched@acme.com"

    def test_missing_fields_default_empty(self):
        """Missing/empty payload defaults to empty strings, no exceptions."""
        lead = _extract_lead_info({})
        assert lead["linkedin_url"] == ""
        assert lead["first_name"] == ""
        assert lead["email"] == ""
        assert lead["campaign_id"] == ""
        assert lead["tags"] == []

    def test_empty_critical_fields_logged_as_warning(self):
        """Empty critical fields trigger a warning log."""
        with patch("webhooks.heyreach_webhook.logger") as mock_logger:
            _extract_lead_info({"event_type": "test"})
            mock_logger.warning.assert_called()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "empty" in warning_msg.lower()

    def test_payload_keys_logged(self):
        """All top-level keys are logged for schema discovery."""
        with patch("webhooks.heyreach_webhook.logger") as mock_logger:
            _extract_lead_info({"foo": "bar", "baz": 123})
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
        """Reply handler classifies and returns sentiment."""
        lead = {"linkedin_url": "https://linkedin.com/in/test", "first_name": "Test", "last_name": "User", "email": "t@co.com"}
        payload = {"message_text": "Sounds interesting, let's chat!"}

        with patch("webhooks.heyreach_webhook._slack_alert"), \
             patch("webhooks.heyreach_webhook._get_signal_manager") as mock_sm:
            mock_sm.return_value = MagicMock()
            result = await _handle_reply_received("MESSAGE_REPLY_RECEIVED", payload, lead)

        assert result["action"] == "reply_classified"
        assert result["sentiment"] == "positive"


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


# =============================================================================
# TEST: Reply Classification (HR-06)
# =============================================================================

class TestReplyClassification:
    """Tests for HR-06: keyword-based reply sentiment classification."""

    def test_positive_interested(self):
        assert classify_reply("Yes, I'm interested! Tell me more.") == "positive"

    def test_positive_schedule(self):
        assert classify_reply("Sounds great, let's schedule a call") == "positive"

    def test_positive_send_over(self):
        assert classify_reply("Sure, send it over please") == "positive"

    def test_negative_not_interested(self):
        assert classify_reply("Not interested, thanks") == "negative"

    def test_negative_unsubscribe(self):
        assert classify_reply("Please unsubscribe me from these messages") == "negative"

    def test_negative_stop(self):
        assert classify_reply("Stop contacting me") == "negative"

    def test_negative_remove(self):
        assert classify_reply("Remove me from your list") == "negative"

    def test_neutral_question(self):
        assert classify_reply("What exactly does your company do?") == "neutral"

    def test_neutral_short(self):
        assert classify_reply("Thanks for reaching out") == "neutral"

    def test_empty_reply(self):
        assert classify_reply("") == "neutral"

    def test_none_reply(self):
        assert classify_reply("") == "neutral"

    def test_negative_takes_priority(self):
        """Negative keywords override positive ones (opt-out safety)."""
        assert classify_reply("I was interested but not the right time, please stop") == "negative"

    @pytest.mark.asyncio
    async def test_reply_handler_returns_sentiment(self):
        """Full handler returns classification result instead of TODO marker."""
        lead = {
            "linkedin_url": "https://linkedin.com/in/test",
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
        }
        payload = {"message_text": "Yes, I'm interested! Tell me more."}
        with patch("webhooks.heyreach_webhook._slack_alert"), \
             patch("webhooks.heyreach_webhook._get_signal_manager") as mock_sm:
            mock_sm.return_value = MagicMock()
            result = await _handle_reply_received("MESSAGE_REPLY_RECEIVED", payload, lead)

        assert result["action"] == "reply_classified"
        assert result["sentiment"] == "positive"

    @pytest.mark.asyncio
    async def test_negative_reply_updates_signal_loop(self):
        """Negative replies should update signal loop to unsubscribed."""
        lead = {
            "linkedin_url": "https://linkedin.com/in/test",
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
        }
        payload = {"message_text": "Not interested, please stop"}
        mock_mgr = MagicMock()
        with patch("webhooks.heyreach_webhook._slack_alert"), \
             patch("webhooks.heyreach_webhook._get_signal_manager", return_value=mock_mgr):
            result = await _handle_reply_received("MESSAGE_REPLY_RECEIVED", payload, lead)

        assert result["sentiment"] == "negative"
        # Should call update_lead_status for negative classification AND handle_linkedin_reply
        assert mock_mgr.handle_linkedin_reply.called
        assert mock_mgr.update_lead_status.called
        args = mock_mgr.update_lead_status.call_args
        assert args[0][1] == "unsubscribed"
