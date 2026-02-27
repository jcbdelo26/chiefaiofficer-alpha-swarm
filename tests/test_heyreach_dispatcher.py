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
import pytest
from pathlib import Path
from datetime import date
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from execution.heyreach_dispatcher import (
    LinkedInDailyCeiling,
    HeyReachDispatcher,
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
    """LinkedInDailyCeiling with temp state file."""
    with patch.object(LinkedInDailyCeiling, "__init__", lambda self: None):
        c = LinkedInDailyCeiling.__new__(LinkedInDailyCeiling)
        c.state_file = tmp_state_file
        c.state_file.parent.mkdir(parents=True, exist_ok=True)
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
