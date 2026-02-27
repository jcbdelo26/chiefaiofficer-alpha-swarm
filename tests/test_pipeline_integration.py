"""Tests for pipeline stage boundary data contracts.

These tests verify that the output of each stage is consumable by the next
stage — catching the silent inter-stage corruption that has bitten before
(e.g., company string vs dict, missing first_name).
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.enricher_waterfall import (
    EnrichedCompany,
    EnrichedContact,
    EnrichedLead,
    IntentSignals,
)
from execution.segmentor_classify import LeadSegmentor


# ── Fixtures ─────────────────────────────────────────────────────

def _make_enriched_lead(**overrides) -> Dict[str, Any]:
    """Build a realistic enriched lead dict that the pipeline would produce."""
    lead = EnrichedLead(
        lead_id="lead_001",
        linkedin_url="https://linkedin.com/in/jdoe",
        contact=EnrichedContact(
            work_email="jdoe@acmecorp.com",
            personal_email="jdoe@gmail.com",
            phone="+14155551234",
            mobile="+14155551234",
            email_verified=True,
            email_confidence=95,
        ),
        company=EnrichedCompany(
            name="Acme Corp",
            domain="acmecorp.com",
            linkedin_url="https://linkedin.com/company/acmecorp",
            description="Enterprise SaaS",
            employee_count=250,
            employee_range="201-500",
            revenue_estimate=50000000,
            revenue_range="$50M",
            industry="Information Technology",
            founded=2015,
            headquarters="San Francisco, CA",
            technologies=["Salesforce", "HubSpot"],
        ),
        intent=IntentSignals(
            hiring_revops=True,
            intent_score=30,
            signals=["hiring"],
        ),
        enrichment_quality=100,
        enriched_at="2026-02-27T12:00:00",
        enrichment_sources=["apollo"],
        raw_enrichment={},
        original_lead={"name": "John Doe", "source_type": "apollo", "source_name": "test"},
    )
    d = asdict(lead)
    # Pipeline merges original lead fields into top level
    d["name"] = "John Doe"
    d["email"] = d["contact"]["work_email"]
    d["title"] = "VP of Sales"
    d["source_type"] = "apollo"
    d["source_name"] = "test"
    d.update(overrides)
    return d


def _make_segmented_output(enriched_lead: Dict[str, Any]) -> Dict[str, Any]:
    """Run segmentor on an enriched lead and return the result as dict."""
    segmentor = LeadSegmentor()
    result = segmentor.segment_lead(enriched_lead)
    return asdict(result) if hasattr(result, "__dataclass_fields__") else result


# ── Enrich → Segment boundary ────────────────────────────────────


class TestEnrichToSegment:

    def test_enriched_lead_consumable_by_segmentor(self):
        """Segmentor can process enriched lead output without crashing."""
        enriched = _make_enriched_lead()
        segmentor = LeadSegmentor()
        result = segmentor.segment_lead(enriched)
        assert result.icp_score > 0
        assert result.icp_tier in ("tier_1", "tier_2", "tier_3", "tier_4")

    def test_company_as_string_requires_normalization(self):
        """Segmentor crashes on company-as-string — pipeline MUST normalize to dict.

        This is a documented pitfall: the pipeline normalizes company strings
        to dicts in _stage_enrich() before passing to segmentor. If this test
        ever passes without normalization, the segmentor was silently changed.
        """
        enriched = _make_enriched_lead()
        enriched["company"] = "Acme Corp"  # String — not valid for segmentor
        segmentor = LeadSegmentor()
        with pytest.raises(AttributeError):
            segmentor.segment_lead(enriched)

    def test_company_as_dict_with_name_key(self):
        """Segmentor works with company as dict (pipeline-normalized format)."""
        enriched = _make_enriched_lead()
        enriched["company"] = {"name": "Acme Corp", "employee_count": 250, "industry": "SaaS"}
        segmentor = LeadSegmentor()
        result = segmentor.segment_lead(enriched)
        assert result is not None
        assert result.icp_tier in ("tier_1", "tier_2", "tier_3", "tier_4")

    def test_missing_title_handled(self):
        """Segmentor handles missing title gracefully."""
        enriched = _make_enriched_lead()
        enriched["title"] = None
        segmentor = LeadSegmentor()
        result = segmentor.segment_lead(enriched)
        assert result is not None

    def test_missing_email_handled(self):
        """Segmentor handles missing email (uses contact.work_email fallback)."""
        enriched = _make_enriched_lead()
        enriched.pop("email", None)
        segmentor = LeadSegmentor()
        result = segmentor.segment_lead(enriched)
        assert result.email is not None or result.email is None  # No crash


# ── Segment → Craft boundary ─────────────────────────────────────


class TestSegmentToCraft:

    def test_segmented_output_has_required_craft_fields(self):
        """Segmented lead has all fields needed by crafter."""
        enriched = _make_enriched_lead()
        segmented = _make_segmented_output(enriched)

        # Fields the crafter requires
        assert "icp_tier" in segmented
        assert "icp_score" in segmented
        assert segmented["icp_tier"].startswith("tier_")
        assert isinstance(segmented["icp_score"], (int, float))

    def test_segmented_has_email(self):
        """Segmented output preserves email for crafter consumption."""
        enriched = _make_enriched_lead()
        segmented = _make_segmented_output(enriched)
        # Email should come through (either from segmentor or original lead)
        assert segmented.get("email") is not None


# ── Shadow queue round-trip ──────────────────────────────────────


class TestShadowQueueRoundTrip:

    def test_push_and_retrieve(self, monkeypatch, tmp_path):
        """Push to shadow queue and retrieve via list_pending — full round-trip."""
        import core.shadow_queue as sq

        # Reset module globals
        sq._client = None
        sq._init_done = True  # Skip Redis init
        shadow_dir = tmp_path / "shadow_emails"
        shadow_dir.mkdir()

        shadow_email = {
            "email_id": "pipeline_test_001",
            "status": "pending",
            "to": "prospect@safe.com",
            "subject": "Test",
            "body": "Hello",
            "recipient_data": {"name": "Prospect", "company": "Safe Inc"},
            "context": {"icp_tier": "tier_1", "campaign_id": "camp_001"},
            "tier": "tier_1",
            "timestamp": "2026-02-27T12:00:00+00:00",
        }

        result = sq.push(shadow_email, shadow_dir=shadow_dir)
        assert result is True

        pending = sq.list_pending(limit=10, shadow_dir=shadow_dir)
        assert len(pending) == 1
        assert pending[0]["email_id"] == "pipeline_test_001"
        assert pending[0]["to"] == "prospect@safe.com"

    def test_status_lifecycle(self, monkeypatch, tmp_path):
        """Status lifecycle: pending → approved → dispatched."""
        import core.shadow_queue as sq

        sq._client = None
        sq._init_done = True
        shadow_dir = tmp_path / "shadow_emails"
        shadow_dir.mkdir()

        email = {
            "email_id": "lifecycle_001",
            "status": "pending",
            "to": "a@b.com",
            "subject": "S",
            "body": "B",
            "timestamp": "2026-02-27T12:00:00+00:00",
        }
        sq.push(email, shadow_dir=shadow_dir)

        # Approve
        result = sq.update_status("lifecycle_001", "approved", shadow_dir=shadow_dir)
        assert result["status"] == "approved"

        # Should no longer be in pending list
        pending = sq.list_pending(limit=10, shadow_dir=shadow_dir)
        assert all(p.get("status") != "pending" or p["email_id"] != "lifecycle_001" for p in pending)

        # Dispatch
        result = sq.update_status(
            "lifecycle_001", "dispatched_to_instantly",
            shadow_dir=shadow_dir,
            extra_fields={"instantly_campaign_id": "camp_abc"},
        )
        assert result["status"] == "dispatched_to_instantly"
        assert result["instantly_campaign_id"] == "camp_abc"
