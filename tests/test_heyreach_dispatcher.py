#!/usr/bin/env python3
"""
HeyReach Dispatcher Tests
===========================
Tests for LinkedInDailyCeiling, lead mapping, list naming,
dispatch guards, and lead eligibility filtering.

All tests use mocking — no real API calls.
"""

import json
import os
import sys
import asyncio
import pytest
import aiohttp
from pathlib import Path
from datetime import date
from unittest.mock import patch, AsyncMock, MagicMock, PropertyMock

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from execution.heyreach_dispatcher import (
    LinkedInDailyCeiling,
    HeyReachDispatcher,
    HeyReachClient,
    _atomic_json_write,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def tmp_state_file(tmp_path):
    """Provide a temp state file for LinkedInDailyCeiling."""
    return tmp_path / "heyreach_dispatch_state.json"


@pytest.fixture
def ceiling(tmp_state_file):
    """LinkedInDailyCeiling with temp state file (no Redis)."""
    with patch.object(LinkedInDailyCeiling, "__init__", lambda self: None):
        c = LinkedInDailyCeiling.__new__(LinkedInDailyCeiling)
        c.state_file = tmp_state_file
        c.state_file.parent.mkdir(parents=True, exist_ok=True)
        c._redis = None
        c._redis_prefix = ""
        c._state = {
            "date": date.today().isoformat(),
            "dispatched_count": 0,
            "dispatched_leads": [],
            "lists_created": [],
        }
        return c


@pytest.fixture
def dispatcher(tmp_path):
    """HeyReachDispatcher with temp directories."""
    with patch.object(HeyReachDispatcher, "__init__", lambda self: None):
        d = HeyReachDispatcher.__new__(HeyReachDispatcher)
        d.shadow_dir = tmp_path / "shadow_mode_emails"
        d.shadow_dir.mkdir(parents=True, exist_ok=True)
        d.dispatch_log = tmp_path / "dispatch_log.jsonl"
        d.ceiling = LinkedInDailyCeiling.__new__(LinkedInDailyCeiling)
        d.ceiling.state_file = tmp_path / "state.json"
        d.ceiling.state_file.parent.mkdir(parents=True, exist_ok=True)
        d.ceiling._redis = None
        d.ceiling._redis_prefix = ""
        d.ceiling._state = {
            "date": date.today().isoformat(),
            "dispatched_count": 0,
            "dispatched_leads": [],
            "lists_created": [],
        }
        d.config = {
            "external_apis": {
                "heyreach": {
                    "enabled": True,
                    "campaign_templates": {
                        "tier_1": {"campaign_id": "camp_001"},
                        "tier_2": {"campaign_id": "camp_002"},
                        "tier_3": {"campaign_id": "camp_003"},
                    },
                    "safety": {"add_to_list_first": True},
                }
            }
        }
        d._client = None
        return d


def _make_shadow_email(
    email_id="test_001",
    status="approved",
    tier="tier_1",
    linkedin_url="https://www.linkedin.com/in/johndoe",
    name="John Doe",
    company="Acme Corp",
    title="VP Sales",
    synthetic=False,
    heyreach_list_id=None,
    to="john@acme.com",
):
    """Build a shadow email dict."""
    data = {
        "email_id": email_id,
        "status": status,
        "tier": tier,
        "to": to,
        "synthetic": synthetic,
        "recipient_data": {
            "name": name,
            "linkedin_url": linkedin_url,
            "company": company,
            "title": title,
        },
        "context": {
            "icp_score": 85,
            "icp_tier": tier,
        },
    }
    if heyreach_list_id:
        data["heyreach_list_id"] = heyreach_list_id
    return data


def _write_shadow_email(shadow_dir, data):
    """Write a shadow email JSON to the shadow dir."""
    email_id = data.get("email_id", "unknown")
    path = shadow_dir / f"{email_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


# =============================================================================
# TEST: LinkedInDailyCeiling
# =============================================================================

class TestLinkedInDailyCeiling:

    def test_initial_state_zero(self, ceiling):
        """Fresh ceiling starts at 0 dispatched."""
        assert ceiling.get_today_count() == 0
        assert ceiling.get_remaining(20) == 20

    def test_increment_and_check(self, ceiling):
        """Count increments correctly, ceiling enforced."""
        ceiling.record_dispatch(5, ["a", "b", "c", "d", "e"], "test_list_v1")
        assert ceiling.get_today_count() == 5
        assert ceiling.get_remaining(20) == 15

        ceiling.record_dispatch(15, [f"lead_{i}" for i in range(15)], "test_list_v2")
        assert ceiling.get_today_count() == 20
        assert ceiling.get_remaining(20) == 0

    def test_date_rollover_resets(self, ceiling):
        """Next day resets the count to 0."""
        ceiling.record_dispatch(10, ["a"] * 10, "list_v1")
        assert ceiling.get_today_count() == 10

        # Simulate date rollover: write stale date to file, then reload
        ceiling._state["date"] = "2020-01-01"
        ceiling._save()
        ceiling._load()
        assert ceiling.get_today_count() == 0
        assert ceiling.get_remaining(20) == 20

    def test_remaining_capacity(self, ceiling):
        """get_remaining returns correct value at various levels."""
        assert ceiling.get_remaining(20) == 20
        ceiling.record_dispatch(7, ["x"] * 7, "list")
        assert ceiling.get_remaining(20) == 13
        assert ceiling.get_remaining(5) == 0  # over limit with custom cap


# =============================================================================
# TEST: Lead Mapping
# =============================================================================

class TestLeadMapping:

    def test_shadow_email_to_heyreach_format(self, dispatcher):
        """Maps all fields correctly to HeyReach lead format."""
        shadow = _make_shadow_email(
            name="Jane Smith",
            linkedin_url="https://linkedin.com/in/janesmith",
            company="BigCorp",
            title="CTO",
        )
        result = dispatcher._map_to_heyreach_lead(shadow)

        assert result["linkedInUrl"] == "https://linkedin.com/in/janesmith"
        assert result["firstName"] == "Jane"
        assert result["lastName"] == "Smith"
        assert result["companyName"] == "BigCorp"

    def test_custom_user_fields_populated(self, dispatcher):
        """All 6 customUserFields are present."""
        shadow = _make_shadow_email()
        result = dispatcher._map_to_heyreach_lead(shadow)

        fields = {f["name"]: f["value"] for f in result["customUserFields"]}
        assert "title" in fields
        assert "icpScore" in fields
        assert "icpTier" in fields
        assert "email" in fields
        assert "shadowEmailId" in fields
        assert "source" in fields
        assert fields["source"] == "caio_pipeline"
        assert len(result["customUserFields"]) == 6

    def test_missing_optional_fields_handled(self, dispatcher):
        """Graceful handling of missing company/title."""
        shadow = _make_shadow_email(name="Solo", company="", title="")
        result = dispatcher._map_to_heyreach_lead(shadow)

        assert result["firstName"] == "Solo"
        assert result["lastName"] == ""
        assert result["companyName"] == ""


# =============================================================================
# TEST: List Naming
# =============================================================================

class TestListNaming:

    def test_list_name_format(self, dispatcher):
        """List name matches pattern caio_{tier}_{date}_{variant}."""
        name = dispatcher._generate_list_name("tier_1")
        today = date.today().strftime("%Y%m%d")
        assert name == f"caio_t1_{today}_v1"

    def test_tier_abbreviations(self, dispatcher):
        """tier_1→t1, tier_2→t2, tier_3→t3."""
        assert dispatcher._generate_list_name("tier_1").startswith("caio_t1_")
        assert dispatcher._generate_list_name("tier_2").startswith("caio_t2_")
        assert dispatcher._generate_list_name("tier_3").startswith("caio_t3_")

    def test_variant_increments(self, dispatcher):
        """Multiple lists same day get v1, v2, v3."""
        today = date.today().strftime("%Y%m%d")
        name1 = dispatcher._generate_list_name("tier_1")
        assert name1.endswith("_v1")

        # Simulate first list already created
        dispatcher.ceiling._state["lists_created"].append(
            {"name": f"caio_t1_{today}_v1", "leads": 5}
        )
        name2 = dispatcher._generate_list_name("tier_1")
        assert name2.endswith("_v2")

        dispatcher.ceiling._state["lists_created"].append(
            {"name": f"caio_t1_{today}_v2", "leads": 3}
        )
        name3 = dispatcher._generate_list_name("tier_1")
        assert name3.endswith("_v3")


# =============================================================================
# TEST: Dispatch Guards
# =============================================================================

class TestDispatchGuards:

    @pytest.mark.asyncio
    async def test_emergency_stop_blocks_all(self, dispatcher):
        """EMERGENCY_STOP=true blocks dispatch."""
        with patch.dict(os.environ, {"EMERGENCY_STOP": "true"}):
            report = await dispatcher.dispatch(dry_run=False)
            assert len(report.errors) > 0
            assert "EMERGENCY_STOP" in report.errors[0]
            assert report.total_dispatched == 0

    @pytest.mark.asyncio
    async def test_no_api_key_blocks(self, dispatcher):
        """Missing HEYREACH_API_KEY blocks live dispatch."""
        with patch.dict(os.environ, {"EMERGENCY_STOP": "false", "HEYREACH_API_KEY": ""}):
            report = await dispatcher.dispatch(dry_run=False)
            assert len(report.errors) > 0
            assert "HEYREACH_API_KEY" in report.errors[0]

    @pytest.mark.asyncio
    async def test_ceiling_exceeded_blocks(self, dispatcher):
        """At 20/20 ceiling, dispatch is blocked."""
        dispatcher.ceiling._state["dispatched_count"] = 20
        with patch.dict(os.environ, {"EMERGENCY_STOP": "false", "HEYREACH_API_KEY": "test_key"}):
            report = await dispatcher.dispatch(dry_run=False)
            assert len(report.errors) > 0
            assert "daily limit" in report.errors[0].lower()


# =============================================================================
# TEST: Lead Eligibility
# =============================================================================

class TestLeadEligibility:

    def test_approved_lead_eligible(self, dispatcher):
        """Approved lead with LinkedIn URL is eligible."""
        data = _make_shadow_email(status="approved", linkedin_url="https://linkedin.com/in/test")
        _write_shadow_email(dispatcher.shadow_dir, data)

        eligible = dispatcher._load_linkedin_eligible()
        assert len(eligible) == 1
        assert eligible[0]["email_id"] == "test_001"

    def test_synthetic_lead_rejected(self, dispatcher):
        """Synthetic leads are filtered out."""
        data = _make_shadow_email(email_id="synth_001", synthetic=True)
        _write_shadow_email(dispatcher.shadow_dir, data)

        eligible = dispatcher._load_linkedin_eligible()
        assert len(eligible) == 0

    def test_already_dispatched_rejected(self, dispatcher):
        """Leads already sent to HeyReach are filtered out."""
        data = _make_shadow_email(email_id="dispatched_001", heyreach_list_id="list_abc")
        _write_shadow_email(dispatcher.shadow_dir, data)

        eligible = dispatcher._load_linkedin_eligible()
        assert len(eligible) == 0

    def test_no_linkedin_url_rejected(self, dispatcher):
        """Leads without LinkedIn URL are filtered out."""
        data = _make_shadow_email(email_id="no_li_001", linkedin_url="")
        _write_shadow_email(dispatcher.shadow_dir, data)

        eligible = dispatcher._load_linkedin_eligible()
        assert len(eligible) == 0

    def test_tier_filter_respected(self, dispatcher):
        """Tier filter only returns matching tier."""
        t1 = _make_shadow_email(email_id="t1_lead", tier="tier_1")
        t2 = _make_shadow_email(email_id="t2_lead", tier="tier_2")
        _write_shadow_email(dispatcher.shadow_dir, t1)
        _write_shadow_email(dispatcher.shadow_dir, t2)

        eligible = dispatcher._load_linkedin_eligible(tier_filter="tier_1")
        assert len(eligible) == 1
        assert eligible[0]["email_id"] == "t1_lead"


# =============================================================================
# HELPERS: Mock aiohttp response
# =============================================================================

def _mock_response(status=200, json_data=None, text_data=None, headers=None):
    """Build a mock aiohttp response as an async context manager."""
    resp = AsyncMock()
    resp.status = status
    resp.headers = headers or {}

    if json_data is not None:
        resp.json = AsyncMock(return_value=json_data)
    elif text_data is not None:
        resp.json = AsyncMock(side_effect=aiohttp.ContentTypeError(
            MagicMock(), MagicMock(), message="not json"))
        resp.text = AsyncMock(return_value=text_data)
    else:
        resp.json = AsyncMock(return_value={})

    # Make it work as async context manager
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_client(cb_registry=None) -> HeyReachClient:
    """Build a HeyReachClient with mocked session (no real HTTP)."""
    client = HeyReachClient.__new__(HeyReachClient)
    client.api_key = "test_key"
    client._session = None
    client._max_retries = 2
    client._cb_registry = cb_registry
    return client


# =============================================================================
# TEST: _request() Retry, Error Discrimination, Circuit Breaker
# =============================================================================

class TestRequestRetry:
    """Tests for HR-04 (retry), HR-08 (error types), HR-10 (circuit breaker),
    HR-13 (timeouts), HR-14 (JSON fallback)."""

    @pytest.mark.asyncio
    async def test_retry_on_503(self):
        """503 triggers retry, succeeds on third attempt."""
        client = _make_client()
        mock_session = AsyncMock()
        mock_session.request = MagicMock(side_effect=[
            _mock_response(status=503, json_data={"message": "Service Unavailable"}),
            _mock_response(status=503, json_data={"message": "Service Unavailable"}),
            _mock_response(status=200, json_data={"id": "list_123"}),
        ])
        client._session = mock_session

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._request("POST", "/list/CreateEmptyList", json={"name": "test"})

        assert result["success"] is True
        assert result["data"]["id"] == "list_123"
        assert mock_session.request.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_429_with_retry_after(self):
        """429 respects Retry-After header."""
        client = _make_client()
        mock_session = AsyncMock()
        mock_session.request = MagicMock(side_effect=[
            _mock_response(status=429, json_data={"message": "Rate limited"}, headers={"Retry-After": "5"}),
            _mock_response(status=200, json_data={"ok": True}),
        ])
        client._session = mock_session

        sleep_calls = []
        async def mock_sleep(seconds):
            sleep_calls.append(seconds)
        with patch("asyncio.sleep", side_effect=mock_sleep):
            result = await client._request("GET", "/auth/CheckApiKey")

        assert result["success"] is True
        assert len(sleep_calls) == 1
        assert sleep_calls[0] == 5  # Retry-After: 5

    @pytest.mark.asyncio
    async def test_no_retry_on_401(self):
        """401 (auth failure) returns immediately, no retry."""
        client = _make_client()
        mock_session = AsyncMock()
        mock_session.request = MagicMock(side_effect=[
            _mock_response(status=401, json_data={"message": "Unauthorized"}),
        ])
        client._session = mock_session

        result = await client._request("GET", "/auth/CheckApiKey")

        assert result["success"] is False
        assert result["status"] == 401
        assert "Unauthorized" in result["error"]
        assert result.get("retryable") is False
        assert mock_session.request.call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self):
        """400 (bad request) returns immediately, no retry."""
        client = _make_client()
        mock_session = AsyncMock()
        mock_session.request = MagicMock(side_effect=[
            _mock_response(status=400, json_data={"message": "Bad Request"}),
        ])
        client._session = mock_session

        result = await client._request("POST", "/list/CreateEmptyList", json={"name": ""})

        assert result["success"] is False
        assert result["status"] == 400
        assert mock_session.request.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self):
        """asyncio.TimeoutError triggers retry."""
        client = _make_client()
        mock_session = AsyncMock()

        timeout_ctx = AsyncMock()
        timeout_ctx.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
        timeout_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session.request = MagicMock(side_effect=[
            timeout_ctx,
            _mock_response(status=200, json_data={"recovered": True}),
        ])
        client._session = mock_session

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._request("GET", "/auth/CheckApiKey")

        assert result["success"] is True
        assert mock_session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self):
        """aiohttp.ClientError triggers retry."""
        client = _make_client()
        mock_session = AsyncMock()

        error_ctx = AsyncMock()
        error_ctx.__aenter__ = AsyncMock(side_effect=aiohttp.ClientConnectionError("Connection refused"))
        error_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session.request = MagicMock(side_effect=[
            error_ctx,
            _mock_response(status=200, json_data={"ok": True}),
        ])
        client._session = mock_session

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._request("POST", "/campaign/GetAll", json={})

        assert result["success"] is True
        assert mock_session.request.call_count == 2

    @pytest.mark.asyncio
    async def test_json_parse_fallback(self):
        """Non-JSON response falls back to text (HR-14)."""
        client = _make_client()
        mock_session = AsyncMock()
        mock_session.request = MagicMock(side_effect=[
            _mock_response(status=200, text_data="<html>OK</html>"),
        ])
        client._session = mock_session

        result = await client._request("GET", "/auth/CheckApiKey")

        assert result["success"] is True
        assert result["data"]["raw_response"] == "<html>OK</html>"

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_when_open(self):
        """Open circuit breaker returns immediately without making HTTP call."""
        mock_registry = MagicMock()
        mock_registry.is_available.return_value = False

        client = _make_client(cb_registry=mock_registry)
        mock_session = AsyncMock()
        client._session = mock_session

        result = await client._request("GET", "/auth/CheckApiKey")

        assert result["success"] is False
        assert "Circuit breaker OPEN" in result["error"]
        assert result["retryable"] is False
        mock_session.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_breaker_records_failure_after_exhausted_retries(self):
        """CB failure recorded only after all retries are exhausted."""
        mock_registry = MagicMock()
        mock_registry.is_available.return_value = True

        client = _make_client(cb_registry=mock_registry)
        mock_session = AsyncMock()
        mock_session.request = MagicMock(side_effect=[
            _mock_response(status=503, json_data={"message": "down"}),
            _mock_response(status=503, json_data={"message": "down"}),
            _mock_response(status=503, json_data={"message": "still down"}),
        ])
        client._session = mock_session

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._request("POST", "/list/CreateEmptyList", json={"name": "x"})

        assert result["success"] is False
        assert result["retryable"] is True
        # CB failure recorded once (after exhausting retries), not per-attempt
        mock_registry.record_failure.assert_called_once()
        mock_registry.record_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_records_circuit_breaker_success(self):
        """Successful response records CB success."""
        mock_registry = MagicMock()
        mock_registry.is_available.return_value = True

        client = _make_client(cb_registry=mock_registry)
        mock_session = AsyncMock()
        mock_session.request = MagicMock(side_effect=[
            _mock_response(status=200, json_data={"ok": True}),
        ])
        client._session = mock_session

        result = await client._request("GET", "/auth/CheckApiKey")

        assert result["success"] is True
        mock_registry.record_success.assert_called_once_with("heyreach_api")
        mock_registry.record_failure.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_retries_from_config(self):
        """Client respects _max_retries setting."""
        client = _make_client()
        client._max_retries = 1  # Only 1 retry (2 total attempts)
        mock_session = AsyncMock()
        mock_session.request = MagicMock(side_effect=[
            _mock_response(status=503, json_data={"message": "down"}),
            _mock_response(status=503, json_data={"message": "still down"}),
        ])
        client._session = mock_session

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._request("POST", "/list/CreateEmptyList", json={"name": "x"})

        assert result["success"] is False
        assert mock_session.request.call_count == 2  # 1 initial + 1 retry


# =============================================================================
# TEST: URL Encoding (HR-01)
# =============================================================================

class TestUrlEncoding:
    """Tests for HR-01: query params must be URL-encoded."""

    @pytest.mark.asyncio
    async def test_campaign_id_with_special_chars(self):
        """Campaign ID with special chars is URL-encoded in query string."""
        client = _make_client()
        mock_session = AsyncMock()
        mock_session.request = MagicMock(side_effect=[
            _mock_response(status=200, json_data={"id": "camp_001"}),
        ])
        client._session = mock_session

        await client.get_campaign("camp/001&x=y")

        call_args = mock_session.request.call_args
        url = call_args[0][1]  # positional arg: URL
        assert "camp%2F001%26x%3Dy" in url
        assert "camp/001&x=y" not in url

    @pytest.mark.asyncio
    async def test_pause_campaign_url_encoded(self):
        """Pause campaign URL-encodes the campaign ID."""
        client = _make_client()
        mock_session = AsyncMock()
        mock_session.request = MagicMock(side_effect=[
            _mock_response(status=200, json_data={"ok": True}),
        ])
        client._session = mock_session

        await client.pause_campaign("id with spaces")

        url = mock_session.request.call_args[0][1]
        assert "id%20with%20spaces" in url
        assert "id with spaces" not in url

    @pytest.mark.asyncio
    async def test_resume_campaign_url_encoded(self):
        """Resume campaign URL-encodes the campaign ID."""
        client = _make_client()
        mock_session = AsyncMock()
        mock_session.request = MagicMock(side_effect=[
            _mock_response(status=200, json_data={"ok": True}),
        ])
        client._session = mock_session

        await client.resume_campaign("camp+123")

        url = mock_session.request.call_args[0][1]
        assert "camp%2B123" in url

    @pytest.mark.asyncio
    async def test_normal_campaign_id_unchanged(self):
        """Normal alphanumeric campaign ID passes through unchanged."""
        client = _make_client()
        mock_session = AsyncMock()
        mock_session.request = MagicMock(side_effect=[
            _mock_response(status=200, json_data={"id": "abc123"}),
        ])
        client._session = mock_session

        await client.get_campaign("abc123")

        url = mock_session.request.call_args[0][1]
        assert "campaignId=abc123" in url


# =============================================================================
# TEST: LinkedIn URL Validation (HR-16)
# =============================================================================

class TestLinkedInUrlValidation:
    """Tests for HR-16: LinkedIn URL format validation."""

    def test_valid_profile_url_accepted(self, dispatcher):
        """Standard LinkedIn profile URL is accepted."""
        data = _make_shadow_email(linkedin_url="https://www.linkedin.com/in/johndoe")
        _write_shadow_email(dispatcher.shadow_dir, data)
        assert len(dispatcher._load_linkedin_eligible()) == 1

    def test_valid_profile_url_no_www(self, dispatcher):
        """LinkedIn URL without www is accepted."""
        data = _make_shadow_email(linkedin_url="https://linkedin.com/in/johndoe")
        _write_shadow_email(dispatcher.shadow_dir, data)
        assert len(dispatcher._load_linkedin_eligible()) == 1

    def test_valid_profile_url_trailing_slash(self, dispatcher):
        """LinkedIn URL with trailing slash is accepted."""
        data = _make_shadow_email(linkedin_url="https://www.linkedin.com/in/jane-smith/")
        _write_shadow_email(dispatcher.shadow_dir, data)
        assert len(dispatcher._load_linkedin_eligible()) == 1

    def test_company_url_rejected(self, dispatcher):
        """LinkedIn company page URL is rejected."""
        data = _make_shadow_email(linkedin_url="https://www.linkedin.com/company/acme-corp")
        _write_shadow_email(dispatcher.shadow_dir, data)
        assert len(dispatcher._load_linkedin_eligible()) == 0

    def test_school_url_rejected(self, dispatcher):
        """LinkedIn school URL is rejected."""
        data = _make_shadow_email(linkedin_url="https://www.linkedin.com/school/mit")
        _write_shadow_email(dispatcher.shadow_dir, data)
        assert len(dispatcher._load_linkedin_eligible()) == 0

    def test_malformed_url_rejected(self, dispatcher):
        """Non-LinkedIn URL is rejected."""
        data = _make_shadow_email(linkedin_url="https://example.com/in/johndoe")
        _write_shadow_email(dispatcher.shadow_dir, data)
        assert len(dispatcher._load_linkedin_eligible()) == 0

    def test_empty_url_rejected(self, dispatcher):
        """Empty URL is rejected (existing behavior preserved)."""
        data = _make_shadow_email(linkedin_url="")
        _write_shadow_email(dispatcher.shadow_dir, data)
        assert len(dispatcher._load_linkedin_eligible()) == 0

    def test_profile_url_with_hyphens_and_numbers(self, dispatcher):
        """LinkedIn profile with hyphens and numbers is accepted."""
        data = _make_shadow_email(linkedin_url="https://www.linkedin.com/in/john-doe-123abc")
        _write_shadow_email(dispatcher.shadow_dir, data)
        assert len(dispatcher._load_linkedin_eligible()) == 1


# =============================================================================
# TEST: Partial Lead Add Validation (HR-09)
# =============================================================================

class TestPartialLeadValidation:
    """Tests for HR-09: detect when not all leads were added to list."""

    @pytest.mark.asyncio
    async def test_partial_success_logged(self, dispatcher):
        """When HeyReach returns addedCount < requested, report shows warning."""
        # Write 3 eligible leads
        for i in range(3):
            data = _make_shadow_email(
                email_id=f"lead_{i}",
                linkedin_url=f"https://linkedin.com/in/lead{i}",
            )
            _write_shadow_email(dispatcher.shadow_dir, data)

        mock_client = AsyncMock()
        mock_client.create_lead_list = AsyncMock(return_value={
            "success": True, "data": {"id": "list_abc"}
        })
        # Only 2 of 3 were added
        mock_client.add_leads_to_list = AsyncMock(return_value={
            "success": True, "data": {"addedCount": 2}
        })
        mock_client.close = AsyncMock()
        dispatcher._client = mock_client

        with patch.dict(os.environ, {"EMERGENCY_STOP": "false", "HEYREACH_API_KEY": "test"}):
            report = await dispatcher.dispatch(dry_run=False)

        assert report.total_dispatched == 2  # Not 3
        assert any("Partial add" in e for e in report.errors)

    @pytest.mark.asyncio
    async def test_full_success_no_warning(self, dispatcher):
        """When all leads added, no partial warning."""
        data = _make_shadow_email(email_id="lead_full", linkedin_url="https://linkedin.com/in/full")
        _write_shadow_email(dispatcher.shadow_dir, data)

        mock_client = AsyncMock()
        mock_client.create_lead_list = AsyncMock(return_value={
            "success": True, "data": {"id": "list_xyz"}
        })
        mock_client.add_leads_to_list = AsyncMock(return_value={
            "success": True, "data": {"addedCount": 1}
        })
        mock_client.close = AsyncMock()
        dispatcher._client = mock_client

        with patch.dict(os.environ, {"EMERGENCY_STOP": "false", "HEYREACH_API_KEY": "test"}):
            report = await dispatcher.dispatch(dry_run=False)

        assert report.total_dispatched == 1
        assert not any("Partial" in e for e in report.errors)

    @pytest.mark.asyncio
    async def test_missing_count_field_assumes_all(self, dispatcher):
        """When API doesn't return a count field, assume all added."""
        data = _make_shadow_email(email_id="lead_nocount", linkedin_url="https://linkedin.com/in/nocount")
        _write_shadow_email(dispatcher.shadow_dir, data)

        mock_client = AsyncMock()
        mock_client.create_lead_list = AsyncMock(return_value={
            "success": True, "data": {"id": "list_nc"}
        })
        mock_client.add_leads_to_list = AsyncMock(return_value={
            "success": True, "data": {"status": "ok"}  # No count field
        })
        mock_client.close = AsyncMock()
        dispatcher._client = mock_client

        with patch.dict(os.environ, {"EMERGENCY_STOP": "false", "HEYREACH_API_KEY": "test"}):
            report = await dispatcher.dispatch(dry_run=False)

        assert report.total_dispatched == 1
        assert not any("Partial" in e for e in report.errors)


# =============================================================================
# TEST: Atomic JSON Write (HR-02)
# =============================================================================

class TestAtomicJsonWrite:
    """Tests for HR-02: atomic file writes prevent corruption."""

    def test_atomic_write_creates_file(self, tmp_path):
        """Atomic write creates a valid JSON file."""
        target = tmp_path / "test.json"
        _atomic_json_write(target, {"key": "value"})
        assert target.exists()
        with open(target, "r", encoding="utf-8") as f:
            assert json.load(f) == {"key": "value"}

    def test_atomic_write_overwrites_existing(self, tmp_path):
        """Atomic write replaces existing file content."""
        target = tmp_path / "test.json"
        target.write_text('{"old": true}', encoding="utf-8")
        _atomic_json_write(target, {"new": True})
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data == {"new": True}
        assert "old" not in data

    def test_atomic_write_no_temp_file_left(self, tmp_path):
        """No .tmp files left after successful write."""
        target = tmp_path / "test.json"
        _atomic_json_write(target, {"clean": True})
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_atomic_write_preserves_original_on_error(self, tmp_path):
        """If serialization fails, original file is untouched."""
        target = tmp_path / "test.json"
        target.write_text('{"original": true}', encoding="utf-8")

        # Non-serializable value will raise TypeError
        try:
            _atomic_json_write(target, {"bad": object()})
        except TypeError:
            pass

        with open(target, "r", encoding="utf-8") as f:
            assert json.load(f) == {"original": True}

    def test_ceiling_save_uses_atomic_write(self, ceiling):
        """LinkedInDailyCeiling._save() produces a valid file."""
        ceiling.record_dispatch(3, ["a", "b", "c"], "test_list")
        assert ceiling.state_file.exists()
        with open(ceiling.state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["dispatched_count"] == 3

    def test_mark_lead_dispatched_atomic(self, dispatcher):
        """_mark_lead_dispatched writes atomically (no temp files left)."""
        data = _make_shadow_email(email_id="atomic_test")
        path = _write_shadow_email(dispatcher.shadow_dir, data)

        shadow = data.copy()
        shadow["_file_path"] = str(path)
        dispatcher._mark_lead_dispatched(shadow, "list_99", "test_list")

        # Verify the file was updated
        with open(path, "r", encoding="utf-8") as f:
            updated = json.load(f)
        assert updated["heyreach_list_id"] == "list_99"
        assert updated["heyreach_list_name"] == "test_list"
        assert "heyreach_dispatched_at" in updated

        # No temp files left
        tmp_files = list(dispatcher.shadow_dir.glob("*.tmp"))
        assert len(tmp_files) == 0


# =============================================================================
# TEST: Redis-Backed Daily Ceiling (HR-03)
# =============================================================================

class TestRedisDailyCeiling:
    """Tests for HR-03: distributed ceiling via Redis with file fallback."""

    def _make_ceiling_with_redis(self, tmp_path, mock_redis):
        """Build a LinkedInDailyCeiling with mocked Redis."""
        with patch.object(LinkedInDailyCeiling, "__init__", lambda self: None):
            c = LinkedInDailyCeiling.__new__(LinkedInDailyCeiling)
            c.state_file = tmp_path / "heyreach_state.json"
            c.state_file.parent.mkdir(parents=True, exist_ok=True)
            c._redis = mock_redis
            c._redis_prefix = "caio:production:context"
            c._state = {
                "date": date.today().isoformat(),
                "dispatched_count": 0,
                "dispatched_leads": [],
                "lists_created": [],
            }
            return c

    def test_redis_count_used_when_available(self, tmp_path):
        """get_today_count reads from Redis when connected."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "7"
        c = self._make_ceiling_with_redis(tmp_path, mock_redis)

        assert c.get_today_count() == 7
        assert c.get_remaining(20) == 13

    def test_file_fallback_when_redis_none(self, tmp_path):
        """get_today_count falls back to file when Redis is None."""
        c = self._make_ceiling_with_redis(tmp_path, None)
        c._state["dispatched_count"] = 5

        assert c.get_today_count() == 5
        assert c.get_remaining(20) == 15

    def test_file_fallback_when_redis_error(self, tmp_path):
        """get_today_count falls back to file on Redis exception."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("connection lost")
        c = self._make_ceiling_with_redis(tmp_path, mock_redis)
        c._state["dispatched_count"] = 3

        assert c.get_today_count() == 3

    def test_record_dispatch_increments_redis(self, tmp_path):
        """record_dispatch calls INCRBY on Redis."""
        mock_redis = MagicMock()
        c = self._make_ceiling_with_redis(tmp_path, mock_redis)

        c.record_dispatch(5, ["a", "b", "c", "d", "e"], "test_list_v1")

        # Redis INCRBY called with count
        mock_redis.incrby.assert_called_once()
        args = mock_redis.incrby.call_args
        assert args[0][1] == 5  # count
        assert "ceiling:heyreach:" in args[0][0]  # key contains pattern
        # Expire also set
        mock_redis.expire.assert_called_once()

    def test_record_dispatch_updates_local_state(self, tmp_path):
        """record_dispatch always updates local state (for list naming)."""
        mock_redis = MagicMock()
        c = self._make_ceiling_with_redis(tmp_path, mock_redis)

        c.record_dispatch(3, ["x", "y", "z"], "caio_t1_20260228_v1")

        assert c._state["dispatched_count"] == 3
        assert len(c._state["lists_created"]) == 1
        assert c._state["lists_created"][0]["name"] == "caio_t1_20260228_v1"

    def test_record_dispatch_survives_redis_failure(self, tmp_path):
        """record_dispatch still updates file when Redis INCRBY fails."""
        mock_redis = MagicMock()
        mock_redis.incrby.side_effect = Exception("write failed")
        c = self._make_ceiling_with_redis(tmp_path, mock_redis)

        c.record_dispatch(2, ["a", "b"], "test_list")

        # File state still updated despite Redis failure
        assert c._state["dispatched_count"] == 2
        assert c.state_file.exists()

    def test_redis_key_includes_date(self, tmp_path):
        """Redis key contains today's date for automatic rollover."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "0"
        c = self._make_ceiling_with_redis(tmp_path, mock_redis)

        c.get_today_count()

        key_used = mock_redis.get.call_args[0][0]
        assert date.today().isoformat() in key_used
        assert "ceiling:heyreach:" in key_used

    def test_redis_zero_count_returns_zero_not_none(self, tmp_path):
        """Redis returning None (key doesn't exist) means 0 dispatched."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # Key not set yet (new day)
        c = self._make_ceiling_with_redis(tmp_path, mock_redis)

        assert c.get_today_count() == 0
        assert c.get_remaining(20) == 20


# =============================================================================
# TEST: HR-18 Config Schema Validation
# =============================================================================

class TestConfigValidation:
    """Tests for HR-18: config schema validation at startup."""

    def test_valid_config_no_warnings(self, tmp_path, caplog):
        """Valid config produces no HR-18 warnings."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config = {
            "external_apis": {
                "heyreach": {
                    "enabled": True,
                    "retry_attempts": 2,
                    "timeout_seconds": 20,
                }
            }
        }
        (config_dir / "production.json").write_text(json.dumps(config), encoding="utf-8")

        d = HeyReachDispatcher.__new__(HeyReachDispatcher)
        d._validate_config(config)

        hr18_warnings = [r for r in caplog.records if "HR-18" in r.message and r.levelname == "WARNING"]
        assert len(hr18_warnings) == 0

    def test_missing_required_key_warns(self, tmp_path, caplog):
        """Missing required key produces HR-18 warning."""
        import logging
        with caplog.at_level(logging.WARNING):
            d = HeyReachDispatcher.__new__(HeyReachDispatcher)
            d._validate_config({})  # Empty config

        hr18_warnings = [r for r in caplog.records if "HR-18" in r.message and "Required" in r.message]
        assert len(hr18_warnings) >= 1

    def test_wrong_type_warns(self, tmp_path, caplog):
        """Config key with wrong type produces HR-18 warning."""
        import logging
        with caplog.at_level(logging.WARNING):
            config = {"external_apis": {"heyreach": {"enabled": "yes"}}}  # str, not bool
            d = HeyReachDispatcher.__new__(HeyReachDispatcher)
            d._validate_config(config)

        hr18_warnings = [r for r in caplog.records if "HR-18" in r.message and "wrong type" in r.message]
        assert len(hr18_warnings) >= 1

    def test_missing_recommended_keys_info(self, tmp_path, caplog):
        """Missing recommended keys produce info-level messages."""
        import logging
        with caplog.at_level(logging.INFO):
            config = {"external_apis": {"heyreach": {"enabled": True}}}
            d = HeyReachDispatcher.__new__(HeyReachDispatcher)
            d._validate_config(config)

        hr18_info = [r for r in caplog.records if "HR-18" in r.message and "Recommended" in r.message]
        assert len(hr18_info) >= 1


# =============================================================================
# TEST: HR-17 Dispatch Log Atomic Writes
# =============================================================================

class TestDispatchLogAtomicWrite:
    """Tests for HR-17: dispatch log JSONL append is atomic."""

    def test_log_creates_file_and_appends(self, tmp_path):
        """Dispatch log is created and contains valid JSONL."""
        from execution.heyreach_dispatcher import HeyReachDispatchResult
        from dataclasses import asdict

        d = HeyReachDispatcher.__new__(HeyReachDispatcher)
        d.dispatch_log = tmp_path / "dispatch_log.jsonl"

        result = HeyReachDispatchResult(
            list_name="test_list",
            list_id="list_123",
            leads_added=3,
            tier="tier_1",
            shadow_email_ids=["a", "b", "c"],
            status="dispatched",
        )
        d._log_dispatch(result)

        assert d.dispatch_log.exists()
        lines = d.dispatch_log.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["list_name"] == "test_list"
        assert data["leads_added"] == 3

    def test_log_appends_multiple_entries(self, tmp_path):
        """Multiple dispatches append to same JSONL file."""
        from execution.heyreach_dispatcher import HeyReachDispatchResult

        d = HeyReachDispatcher.__new__(HeyReachDispatcher)
        d.dispatch_log = tmp_path / "dispatch_log.jsonl"

        for i in range(3):
            result = HeyReachDispatchResult(
                list_name=f"list_{i}", list_id=f"id_{i}",
                leads_added=i + 1, tier="tier_1",
                shadow_email_ids=[], status="dispatched",
            )
            d._log_dispatch(result)

        lines = d.dispatch_log.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3
        assert json.loads(lines[2])["list_name"] == "list_2"

    def test_log_no_temp_files_left(self, tmp_path):
        """No .tmplog files left after successful write."""
        from execution.heyreach_dispatcher import HeyReachDispatchResult

        d = HeyReachDispatcher.__new__(HeyReachDispatcher)
        d.dispatch_log = tmp_path / "dispatch_log.jsonl"

        result = HeyReachDispatchResult(
            list_name="test", list_id="id", leads_added=1,
            tier="tier_1", shadow_email_ids=[], status="dispatched",
        )
        d._log_dispatch(result)

        tmp_files = list(tmp_path.glob("*.tmplog"))
        assert len(tmp_files) == 0
