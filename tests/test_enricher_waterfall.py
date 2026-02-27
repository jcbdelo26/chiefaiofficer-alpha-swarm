"""Tests for execution/enricher_waterfall.py — Apollo + BetterContact enrichment parsers.

Every pipeline run depends on correct parsing of provider responses. These are
pure function tests with dict fixtures — no HTTP mocking needed for parsers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.enricher_waterfall import (
    EnrichedCompany,
    EnrichedContact,
    EnrichedLead,
    IntentSignals,
    WaterfallEnricher,
)


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def enricher():
    """Create enricher in test mode (no API calls)."""
    return WaterfallEnricher(test_mode=True)


def _full_apollo_person() -> Dict[str, Any]:
    """Complete Apollo People Match response for a VP of Sales."""
    return {
        "email": "jsmith@acmecorp.com",
        "email_status": "verified",
        "personal_emails": ["john.personal@gmail.com"],
        "phone_numbers": [
            {"sanitized_number": "+14155551234", "type": "mobile"},
        ],
        "organization_phone": "+14155559000",
        "organization_name": "Acme Corp",
        "organization": {
            "name": "Acme Corp",
            "primary_domain": "acmecorp.com",
            "linkedin_url": "https://linkedin.com/company/acmecorp",
            "short_description": "Enterprise SaaS platform",
            "estimated_num_employees": 250,
            "employee_count_range": "201-500",
            "annual_revenue": 50000000,
            "annual_revenue_printed": "$50M",
            "industry": "Information Technology",
            "founded_year": 2015,
            "city": "San Francisco",
            "state": "CA",
            "current_technologies": ["Salesforce", "HubSpot", "Outreach"],
            "publicly_traded_symbol": None,
        },
    }


def _freelancer_apollo_person() -> Dict[str, Any]:
    """Apollo response for a freelancer with no organization."""
    return {
        "email": "freelancer@gmail.com",
        "email_status": "unverified",
        "personal_emails": [],
        "phone_numbers": [],
        "organization_name": "",
        "organization": None,  # Key difference — freelancers have no org
    }


def _bc_deliverable() -> Dict[str, Any]:
    """BetterContact response with deliverable email."""
    return {
        "contact_email_address": "jsmith@acmecorp.com",
        "contact_email_address_status": "deliverable",
        "contact_phone_number": "+14155551234",
        "contact_company": "Acme Corp",
        "contact_company_domain": "acmecorp.com",
    }


def _bc_catch_all_safe() -> Dict[str, Any]:
    """BetterContact response with catch-all safe email."""
    return {
        "contact_email_address": "info@catchall.com",
        "contact_email_address_status": "catch_all_safe",
        "contact_phone_number": None,
        "contact_company": "Catch-All Inc",
        "contact_company_domain": "catchall.com",
    }


def _bc_undeliverable() -> Dict[str, Any]:
    """BetterContact response with undeliverable email."""
    return {
        "contact_email_address": "gone@defunct.com",
        "contact_email_address_status": "undeliverable",
        "contact_phone_number": None,
        "contact_company": "Defunct Co",
        "contact_company_domain": "defunct.com",
    }


# ── Apollo parsing tests ─────────────────────────────────────────


class TestApolloParser:

    def test_complete_response_all_fields(self, enricher):
        """Complete Apollo response extracts all fields correctly."""
        result = enricher._parse_apollo_response("lead1", "https://linkedin.com/in/jsmith", _full_apollo_person())

        assert isinstance(result, EnrichedLead)
        assert result.lead_id == "lead1"
        assert result.contact.work_email == "jsmith@acmecorp.com"
        assert result.contact.email_verified is True
        assert result.contact.email_confidence == 95
        assert result.contact.personal_email == "john.personal@gmail.com"
        assert result.company.name == "Acme Corp"
        assert result.company.domain == "acmecorp.com"
        assert result.company.employee_count == 250
        assert result.company.industry == "Information Technology"
        assert result.company.revenue_estimate == 50000000
        assert "Salesforce" in result.company.technologies
        assert result.enrichment_sources == ["apollo"]

    def test_missing_organization_freelancer(self, enricher):
        """Missing organization key (freelancers) handled gracefully — no crash."""
        result = enricher._parse_apollo_response("lead2", "https://linkedin.com/in/free", _freelancer_apollo_person())

        assert isinstance(result, EnrichedLead)
        assert result.contact.work_email == "freelancer@gmail.com"
        assert result.contact.email_verified is False
        assert result.contact.email_confidence == 60  # unverified but email present
        assert result.company.name == ""  # No org
        assert result.company.employee_count == 0

    def test_verified_email_95_confidence(self, enricher):
        """Verified email → 95 confidence."""
        person = {"email": "test@co.com", "email_status": "verified"}
        result = enricher._parse_apollo_response("lead3", "url", person)
        assert result.contact.email_confidence == 95
        assert result.contact.email_verified is True

    def test_unverified_email_60_confidence(self, enricher):
        """Unverified email present → 60 confidence."""
        person = {"email": "test@co.com", "email_status": "unverified"}
        result = enricher._parse_apollo_response("lead4", "url", person)
        assert result.contact.email_confidence == 60
        assert result.contact.email_verified is False

    def test_no_email_zero_confidence(self, enricher):
        """No email → 0 confidence."""
        person = {"email": None, "email_status": None}
        result = enricher._parse_apollo_response("lead5", "url", person)
        assert result.contact.email_confidence == 0
        assert result.contact.work_email is None

    def test_personal_emails_empty(self, enricher):
        """Empty personal_emails array → None."""
        person = {"email": "test@co.com", "email_status": "verified", "personal_emails": []}
        result = enricher._parse_apollo_response("lead6", "url", person)
        assert result.contact.personal_email is None

    def test_personal_emails_none(self, enricher):
        """personal_emails is None → None (no crash)."""
        person = {"email": "test@co.com", "email_status": "verified", "personal_emails": None}
        result = enricher._parse_apollo_response("lead7", "url", person)
        assert result.contact.personal_email is None

    def test_phone_numbers_empty(self, enricher):
        """Empty phone_numbers → phone is None."""
        person = {"email": "test@co.com", "email_status": "verified", "phone_numbers": []}
        result = enricher._parse_apollo_response("lead8", "url", person)
        assert result.contact.phone is None
        assert result.contact.mobile is None

    def test_phone_numbers_none(self, enricher):
        """phone_numbers is None → no crash."""
        person = {"email": "test@co.com", "email_status": "verified", "phone_numbers": None}
        result = enricher._parse_apollo_response("lead9", "url", person)
        assert result.contact.phone is None

    def test_empty_fields_no_crash(self, enricher):
        """Completely empty person dict → no crash, empty fields."""
        result = enricher._parse_apollo_response("lead10", "url", {})
        assert isinstance(result, EnrichedLead)
        assert result.contact.work_email is None
        assert result.company.name == ""


# ── BetterContact parsing tests ──────────────────────────────────


class TestBetterContactParser:

    def test_deliverable_email(self, enricher):
        """Deliverable email → work_email populated, 95 confidence."""
        result = enricher._parse_bettercontact_response("lead1", "url", _bc_deliverable())
        assert result.contact.work_email == "jsmith@acmecorp.com"
        assert result.contact.email_verified is True
        assert result.contact.email_confidence == 95
        assert result.enrichment_sources == ["bettercontact"]

    def test_catch_all_safe_email(self, enricher):
        """catch_all_safe → work_email populated, 70 confidence (still usable)."""
        result = enricher._parse_bettercontact_response("lead2", "url", _bc_catch_all_safe())
        assert result.contact.work_email == "info@catchall.com"
        assert result.contact.email_verified is False
        assert result.contact.email_confidence == 70

    def test_undeliverable_email(self, enricher):
        """Undeliverable → work_email is None."""
        result = enricher._parse_bettercontact_response("lead3", "url", _bc_undeliverable())
        assert result.contact.work_email is None
        assert result.contact.email_confidence == 0

    def test_minimal_company_data(self, enricher):
        """BetterContact returns minimal company data — only name and domain."""
        result = enricher._parse_bettercontact_response("lead4", "url", _bc_deliverable())
        assert result.company.name == "Acme Corp"
        assert result.company.domain == "acmecorp.com"
        assert result.company.employee_count == 0  # Not provided by BC
        assert result.company.industry == ""  # Not provided by BC

    def test_catch_all_not_safe(self, enricher):
        """catch_all_not_safe → work_email is None (risky email excluded)."""
        data = {
            "contact_email_address": "risky@unknown.com",
            "contact_email_address_status": "catch_all_not_safe",
            "contact_phone_number": None,
            "contact_company": "",
            "contact_company_domain": "",
        }
        result = enricher._parse_bettercontact_response("lead5", "url", data)
        assert result.contact.work_email is None
        assert result.contact.email_confidence == 30


# ── Quality scoring tests ────────────────────────────────────────


class TestQualityScoring:

    def test_full_data_high_score(self, enricher):
        """Full data → high quality score (100)."""
        contact = EnrichedContact(
            work_email="test@co.com",
            email_verified=True,
            phone="+14155551234",
        )
        company = EnrichedCompany(
            name="Acme Corp",
            domain="acmecorp.com",
            employee_count=250,
            industry="SaaS",
            technologies=["Salesforce"],
            revenue_estimate=50000000,
        )
        score = enricher._calculate_quality(contact, company)
        assert score == 100

    def test_email_only_low_score(self, enricher):
        """Only email present → low score (20 for unverified email)."""
        contact = EnrichedContact(work_email="test@co.com", email_verified=False)
        company = EnrichedCompany()
        score = enricher._calculate_quality(contact, company)
        assert score == 20

    def test_verified_email_higher_than_unverified(self, enricher):
        """Verified email scores 30, unverified scores 20."""
        contact_verified = EnrichedContact(work_email="a@b.com", email_verified=True)
        contact_unverified = EnrichedContact(work_email="a@b.com", email_verified=False)
        company = EnrichedCompany()

        assert enricher._calculate_quality(contact_verified, company) == 30
        assert enricher._calculate_quality(contact_unverified, company) == 20

    def test_no_data_zero_score(self, enricher):
        """Empty contact and company → 0 score."""
        score = enricher._calculate_quality(EnrichedContact(), EnrichedCompany())
        assert score == 0

    def test_score_caps_at_100(self, enricher):
        """Score never exceeds 100."""
        contact = EnrichedContact(
            work_email="a@b.com",
            email_verified=True,
            phone="+1",
            mobile="+1",
        )
        company = EnrichedCompany(
            name="Co", domain="co.com", employee_count=100,
            industry="SaaS", technologies=["A", "B"], revenue_estimate=1000000,
        )
        score = enricher._calculate_quality(contact, company)
        assert score == 100


# ── Provider routing tests ───────────────────────────────────────


class TestProviderRouting:

    def test_apollo_key_selects_apollo(self, monkeypatch):
        """Apollo API key present → provider='apollo'."""
        monkeypatch.setenv("APOLLO_API_KEY", "test_apollo_key")
        monkeypatch.delenv("BETTERCONTACT_API_KEY", raising=False)
        e = WaterfallEnricher(test_mode=False)
        assert e.provider == "apollo"

    def test_no_apollo_bettercontact_fallback(self, monkeypatch):
        """No Apollo key, BetterContact present → provider='bettercontact'."""
        monkeypatch.delenv("APOLLO_API_KEY", raising=False)
        monkeypatch.setenv("BETTERCONTACT_API_KEY", "test_bc_key")
        e = WaterfallEnricher(test_mode=False)
        assert e.provider == "bettercontact"

    def test_no_keys_mock_mode(self, monkeypatch):
        """No API keys → auto-switches to mock mode."""
        monkeypatch.delenv("APOLLO_API_KEY", raising=False)
        monkeypatch.delenv("BETTERCONTACT_API_KEY", raising=False)
        e = WaterfallEnricher(test_mode=False)
        assert e.test_mode is True
        assert e.provider == "mock_fallback"

    def test_test_mode_explicit(self):
        """Explicit test_mode=True → provider='mock'."""
        e = WaterfallEnricher(test_mode=True)
        assert e.provider == "mock"
        assert e.test_mode is True


# ── Intent signal tests ──────────────────────────────────────────


class TestIntentSignals:

    def test_competitor_tech_detected(self, enricher):
        """Competitor tech in stack → competitor_user signal."""
        data = {"company": {"technologies": ["Salesforce", "Gong", "HubSpot"]}}
        result = enricher._detect_intent_signals(data)
        assert result.competitor_user is True
        assert "competitor_user" in result.signals

    def test_no_signals_zero_score(self, enricher):
        """No matching signals → 0 intent score."""
        result = enricher._detect_intent_signals({})
        assert result.intent_score == 0
        assert result.signals == []

    def test_hiring_signal(self, enricher):
        """Hiring signal detected."""
        data = {"hiring_signals": {"has_open_roles": True}}
        result = enricher._detect_intent_signals(data)
        assert result.hiring_revops is True
        assert result.intent_score == 30


# ── Clay fallback tests ─────────────────────────────────────────


def _clay_callback_data() -> Dict[str, Any]:
    """Realistic Clay callback payload with enriched person/company data."""
    return {
        "work_email": "jsmith@acmecorp.com",
        "email_verified": True,
        "phone": "+14155551234",
        "mobile_phone": "+14155559876",
        "linkedin_url": "https://linkedin.com/in/jsmith",
        "first_name": "John",
        "last_name": "Smith",
        "job_title": "VP of Sales",
        "company_name": "Acme Corp",
        "company_domain": "acmecorp.com",
        "industry": "Information Technology",
        "employee_count": 250,
        "revenue": "$50M",
        "company_linkedin_url": "https://linkedin.com/company/acmecorp",
        "icp_score": 0.85,
        "priority": "high",
        "sources": ["Apollo", "BetterContact"],
    }


class TestClayParser:

    def test_clay_response_all_fields(self, enricher):
        """Clay callback parses all fields into EnrichedLead."""
        result = enricher._parse_clay_pipeline_response(
            "lead1", "https://linkedin.com/in/jsmith", _clay_callback_data()
        )
        assert isinstance(result, EnrichedLead)
        assert result.lead_id == "lead1"
        assert result.contact.work_email == "jsmith@acmecorp.com"
        assert result.contact.email_verified is True
        assert result.contact.email_confidence == 90
        assert result.contact.phone == "+14155551234"
        assert result.contact.mobile == "+14155559876"
        assert result.company.name == "Acme Corp"
        assert result.company.domain == "acmecorp.com"
        assert result.company.industry == "Information Technology"
        assert result.company.employee_count == 250
        assert result.enrichment_sources == ["clay"]

    def test_clay_response_minimal_data(self, enricher):
        """Clay callback with only email — no crash."""
        data = {"email": "minimal@co.com"}
        result = enricher._parse_clay_pipeline_response("lead2", "url", data)
        assert result.contact.work_email == "minimal@co.com"
        assert result.contact.email_verified is False
        assert result.contact.email_confidence == 60
        assert result.company.name == ""

    def test_clay_response_empty(self, enricher):
        """Completely empty Clay response — no crash, empty fields."""
        result = enricher._parse_clay_pipeline_response("lead3", "url", {})
        assert isinstance(result, EnrichedLead)
        assert result.contact.work_email is None
        assert result.contact.email_confidence == 0
        assert result.company.name == ""

    def test_clay_employee_count_string(self, enricher):
        """Employee count as string (Clay returns varied types)."""
        data = {"employee_count": "500", "company_name": "BigCo"}
        result = enricher._parse_clay_pipeline_response("lead4", "url", data)
        assert result.company.employee_count == 500

    def test_clay_quality_score(self, enricher):
        """Clay response with email + company → reasonable quality score."""
        data = _clay_callback_data()
        result = enricher._parse_clay_pipeline_response("lead5", "url", data)
        # email verified (30) + company name (15) + phone (10) + domain (5)
        # + employee_count (10) + industry (10) = 80
        assert result.enrichment_quality >= 70


class TestClayLinkedInNormalization:

    def test_strips_protocol_and_trailing_slash(self, enricher):
        """Normalize strips https://, www, and trailing slash."""
        assert enricher._normalize_linkedin_url("https://www.linkedin.com/in/jdoe/") == "linkedin.com/in/jdoe"

    def test_case_insensitive(self, enricher):
        """Normalize lowercases the URL."""
        assert enricher._normalize_linkedin_url("HTTPS://LinkedIn.com/in/JDoe") == "linkedin.com/in/jdoe"

    def test_http_variant(self, enricher):
        """Normalize handles http:// variant."""
        assert enricher._normalize_linkedin_url("http://linkedin.com/in/jdoe") == "linkedin.com/in/jdoe"

    def test_already_normalized(self, enricher):
        """Already clean URL passes through."""
        assert enricher._normalize_linkedin_url("linkedin.com/in/jdoe") == "linkedin.com/in/jdoe"


class TestClayWaterfallIntegration:

    def test_clay_config_stored_on_enricher(self, monkeypatch):
        """Clay env vars are read and stored on the enricher instance."""
        monkeypatch.setenv("APOLLO_API_KEY", "apollo_key")
        monkeypatch.setenv("CLAY_API_KEY", "clay_key")
        monkeypatch.setenv("CLAY_WORKBOOK_WEBHOOK_URL", "https://api.clay.com/v3/sources/webhook/test")
        monkeypatch.setenv("CLAY_PIPELINE_ENABLED", "true")
        e = WaterfallEnricher(test_mode=False)
        assert e.clay_key == "clay_key"
        assert e.clay_webhook_url == "https://api.clay.com/v3/sources/webhook/test"
        assert e.clay_pipeline_enabled is True

    def test_clay_disabled_by_default(self, monkeypatch):
        """Clay pipeline is disabled by default (feature flag)."""
        monkeypatch.setenv("APOLLO_API_KEY", "apollo_key")
        monkeypatch.setenv("CLAY_API_KEY", "clay_key")
        monkeypatch.delenv("CLAY_PIPELINE_ENABLED", raising=False)
        e = WaterfallEnricher(test_mode=False)
        assert e.clay_pipeline_enabled is False

    def test_clay_skipped_when_no_key(self, monkeypatch):
        """Clay fallback skipped when CLAY_API_KEY not set."""
        monkeypatch.setenv("APOLLO_API_KEY", "apollo_key")
        monkeypatch.delenv("CLAY_API_KEY", raising=False)
        monkeypatch.setenv("CLAY_PIPELINE_ENABLED", "true")
        e = WaterfallEnricher(test_mode=False)
        assert e.clay_key == ""

    def test_clay_skipped_when_no_linkedin_url(self, monkeypatch):
        """_enrich_via_clay returns None when no LinkedIn URL provided."""
        monkeypatch.setenv("CLAY_API_KEY", "clay_key")
        monkeypatch.setenv("CLAY_WORKBOOK_WEBHOOK_URL", "https://webhook.test")
        monkeypatch.setenv("CLAY_PIPELINE_ENABLED", "true")
        e = WaterfallEnricher(test_mode=True)
        e.clay_pipeline_enabled = True
        e.clay_key = "clay_key"
        e.clay_webhook_url = "https://webhook.test"
        result = e._enrich_via_clay("lead1", "", "John Doe", "Acme")
        assert result is None

    def test_clay_skipped_when_no_redis(self, monkeypatch):
        """_enrich_via_clay returns None when Redis is unavailable."""
        monkeypatch.delenv("REDIS_URL", raising=False)
        e = WaterfallEnricher(test_mode=True)
        e.clay_pipeline_enabled = True
        e.clay_key = "clay_key"
        e.clay_webhook_url = "https://webhook.test"
        result = e._enrich_via_clay("lead1", "https://linkedin.com/in/jdoe", "John Doe", "Acme")
        assert result is None
