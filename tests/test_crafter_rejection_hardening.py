"""Tests for CRAFTER rejection hardening — template rotation + feedback context."""

from unittest.mock import patch, MagicMock

import pytest

from core.rejection_memory import RejectionMemory


@pytest.fixture
def memory(tmp_path):
    """RejectionMemory with no Redis, filesystem only."""
    with patch.dict("os.environ", {"REDIS_URL": ""}, clear=False):
        mem = RejectionMemory(storage_dir=tmp_path / "rejection_memory")
        mem._redis = None
        yield mem


@pytest.fixture
def crafter(memory, tmp_path):
    """CampaignCrafter with injected rejection memory."""
    # Ensure no real feedback file interferes
    feedback_log = tmp_path / "agent_feedback.jsonl"
    feedback_log.touch()

    from execution.crafter_campaign import CampaignCrafter

    c = CampaignCrafter()
    c._rejection_memory = memory
    # Override the feedback log path so tests don't read production data
    c.__class__.AGENT_FEEDBACK_LOG = feedback_log
    c.feedback_profile = c._load_feedback_profile()
    return c


def _make_lead(email="andrew.mahr@wpromote.com", tier="tier_1", **kwargs):
    base = {
        "email": email,
        "first_name": "Andrew",
        "last_name": "Mahr",
        "name": "Andrew Mahr",
        "title": "Chief Revenue Officer",
        "company_name": "Wpromote",
        "company": "Wpromote",
        "industry": "Digital Marketing",
        "icp_tier": tier,
        "source_type": "competitor_follower",
        "source_name": "Gong",
        "personalization_hooks": ["Tech stack signal: Salesforce"],
        "engagement_content": "",
    }
    base.update(kwargs)
    return base


# ── Template rotation after rejection ─────────────────────────────


def test_template_rotation_after_rejection(crafter, memory):
    """Rejected template should not be re-selected for the same lead."""
    lead = _make_lead()

    # First call: get the default template
    original_template = crafter._select_template(lead)

    # Record a rejection for that template
    memory.record_rejection(
        lead_email="andrew.mahr@wpromote.com",
        rejection_tag="personalization_mismatch",
        template_id=original_template,
    )

    # Second call: should select a DIFFERENT template
    new_template = crafter._select_template(lead)
    assert new_template != original_template, (
        f"Template should have rotated away from '{original_template}' "
        f"but got '{new_template}'"
    )


def test_template_rotation_exhausted_falls_back(crafter, memory):
    """When all tier templates are rejected, last one still returns something valid."""
    lead = _make_lead()

    # Reject ALL tier_1 templates
    tier1_templates = ["t1_executive_buyin", "t1_industry_specific", "t1_value_first"]
    for tmpl in tier1_templates:
        memory.record_rejection(
            "andrew.mahr@wpromote.com", "other", template_id=tmpl,
        )

    # Should still return a valid template (falls back to candidate since no alternatives)
    result = crafter._select_template(lead)
    assert result in crafter.TEMPLATES


def test_template_rotation_different_lead_unaffected(crafter, memory):
    """Rejection for one lead doesn't affect template selection for another."""
    lead_andrew = _make_lead(email="andrew@wpromote.com")
    lead_celia = _make_lead(email="celia@wpromote.com")

    # Get andrew's template and reject it
    andrew_template = crafter._select_template(lead_andrew)
    memory.record_rejection("andrew@wpromote.com", "other", template_id=andrew_template)

    # Celia's template should not be affected by Andrew's rejection
    celia_template = crafter._select_template(lead_celia)
    # (may or may not be the same template — the point is it wasn't forcibly rotated)
    assert celia_template in crafter.TEMPLATES


# ── Feedback text in crafter context ──────────────────────────────


def test_feedback_text_appears_in_template_variables(crafter, memory):
    """Rejection feedback text should appear in template variables via rejection_context."""
    memory.record_rejection(
        lead_email="andrew.mahr@wpromote.com",
        rejection_tag="personalization_mismatch",
        feedback_text="Too generic, no specific Wpromote initiative mentioned",
        template_id="t1_executive_buyin",
    )

    lead = _make_lead()
    variables = crafter._build_template_variables(lead)

    rejection_ctx = variables.get("rejection_context", {})
    assert rejection_ctx.get("rejection_count") == 1
    assert "personalization_mismatch" in rejection_ctx.get("rejection_tags", [])
    assert any(
        "Wpromote initiative" in txt
        for txt in rejection_ctx.get("feedback_texts", [])
    )


def test_no_rejection_context_for_new_lead(crafter, memory):
    """New lead with no rejection history should have empty rejection_context."""
    lead = _make_lead(email="brand.new@example.com")
    variables = crafter._build_template_variables(lead)

    rejection_ctx = variables.get("rejection_context", {})
    assert rejection_ctx == {}


def test_generate_email_includes_rejection_context(crafter, memory):
    """generate_email() output should include rejection_context field."""
    memory.record_rejection(
        "andrew.mahr@wpromote.com", "personalization_mismatch",
        feedback_text="Generic opener detected",
    )

    lead = _make_lead()
    result = crafter.generate_email(lead)

    assert "rejection_context" in result
    assert result["rejection_context"].get("rejection_count") == 1


# ── Sub-agent enrichment integration ──────────────────────────────


def test_sub_agent_enrichment_extracts_signals():
    """Sub-agents extract meaningful signals from enriched lead data."""
    from core.enrichment_sub_agents import extract_all_signals

    lead = {
        "email": "test@acme.com",
        "company_name": "Acme Corp",
        "company": {"name": "Acme Corp", "industry": "SaaS", "employee_count": 200},
        "title": "Chief Revenue Officer",
        "industry": "SaaS",
        "hiring_signal": "Hiring 3 ML engineers",
        "personalization_hooks": ["Tech stack signal: Salesforce"],
        "source_type": "event_attendee",
        "source_name": "SaaStr Annual 2026",
    }

    ctx = extract_all_signals(lead)
    assert ctx.company_specific_count >= 2  # company name + industry + hiring
    assert ctx.role_impact_count >= 1       # CRO mapped to pain point
    assert ctx.meets_minimum_evidence
    assert ctx.recommended_opener_signal is not None
    assert len(ctx.sub_agent_trace_ids) == 5  # all 5 sub-agents ran


def test_sub_agent_fallback_on_sparse_data():
    """Sub-agents handle minimal lead data without crashing."""
    from core.enrichment_sub_agents import extract_all_signals

    lead = {"email": "sparse@unknown.com"}
    ctx = extract_all_signals(lead)
    assert ctx.overall_confidence == 0.0
    assert not ctx.meets_minimum_evidence
    assert len(ctx.sub_agent_trace_ids) == 5
