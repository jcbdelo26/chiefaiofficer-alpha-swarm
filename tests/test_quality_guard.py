"""Tests for core.quality_guard — pre-queue deterministic validator."""

from unittest.mock import patch, MagicMock

import pytest

from core.quality_guard import QualityGuard, BANNED_OPENERS, GENERIC_PHRASES
from core.rejection_memory import RejectionMemory, compute_draft_fingerprint


@pytest.fixture
def memory(tmp_path):
    """RejectionMemory with no Redis, filesystem only."""
    with patch.dict("os.environ", {"REDIS_URL": ""}, clear=False):
        mem = RejectionMemory(storage_dir=tmp_path / "rejection_memory")
        mem._redis = None
        yield mem


@pytest.fixture
def guard(memory):
    """QualityGuard with filesystem-only rejection memory."""
    with patch.dict("os.environ", {"QUALITY_GUARD_ENABLED": "true", "QUALITY_GUARD_MODE": ""}, clear=False):
        yield QualityGuard(rejection_memory=memory)


def _make_email(
    to="test@company.com",
    subject="AI roadmap for Acme Corp",
    body="Noticed Acme Corp's recent AI hiring push. As a CRO driving revenue execution, this practical framework helps teams move from pilots to measurable outcomes.",
    company="Acme Corp",
    title="Chief Revenue Officer",
):
    return {
        "to": to,
        "subject": subject,
        "body": body,
        "recipient_data": {"company": company, "title": title},
        "tier": "tier_1",
    }


# ── GUARD-001: Rejection memory block ─────────────────────────────


def test_guard_blocks_after_two_rejections(guard, memory):
    """GUARD-001: Lead with 2+ rejections and no new evidence → blocked."""
    memory.record_rejection("blocked@co.com", "personalization_mismatch")
    memory.record_rejection("blocked@co.com", "tone_style_issue")

    email = _make_email(to="blocked@co.com")
    result = guard.check(email)

    assert result["passed"] is False
    assert result["rejection_memory_hit"] is True
    assert any(f["rule_id"] == "GUARD-001" for f in result["rule_failures"])


def test_guard_passes_first_rejection(guard, memory):
    """Lead with 1 rejection should still pass (below threshold)."""
    memory.record_rejection("once@co.com", "personalization_mismatch")
    email = _make_email(to="once@co.com")
    result = guard.check(email)
    # May fail on other rules, but not GUARD-001
    guard001_failures = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-001"]
    assert len(guard001_failures) == 0


# ── GUARD-002: Repeat draft detection ─────────────────────────────


def test_guard_blocks_repeat_draft(guard, memory):
    """GUARD-002: Same fingerprint as rejected draft → blocked."""
    subject = "AI roadmap for Acme Corp"
    body = "Given your role as CRO at Acme Corp, quick context..."
    memory.record_rejection(
        "repeat@co.com", "personalization_mismatch",
        subject=subject, body=body,
    )

    email = _make_email(to="repeat@co.com", subject=subject, body=body)
    result = guard.check(email)

    assert result["rejection_memory_hit"] is True
    assert any(f["rule_id"] == "GUARD-002" for f in result["rule_failures"])


def test_guard_passes_different_draft(guard, memory):
    """Different content for same lead → no GUARD-002 failure."""
    memory.record_rejection(
        "diff@co.com", "personalization_mismatch",
        subject="Old subject", body="Old body content...",
    )

    email = _make_email(to="diff@co.com", subject="Completely new", body="Entirely different approach for Acme Corp revenue execution strategy.")
    result = guard.check(email)

    guard002_failures = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-002"]
    assert len(guard002_failures) == 0


# ── GUARD-003: Minimum personalization evidence ───────────────────


def test_guard_blocks_no_company_evidence(guard):
    """GUARD-003: Draft with generic 'your company' → blocked."""
    email = _make_email(
        body="I wanted to share one practical idea for your company.",
        company="your company",
    )
    result = guard.check(email)

    guard003_failures = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-003"]
    assert len(guard003_failures) > 0


def test_guard_passes_evidence_backed_draft(guard):
    """Draft with company initiative + role impact references → passes GUARD-003."""
    email = _make_email(
        body=(
            "Noticed Acme Corp's recent AI hiring push in the engineering org. "
            "As CRO, the execution cadence for revenue-driving workflows can "
            "often be the bottleneck between pilot and production."
        ),
        company="Acme Corp",
        title="CRO",
    )
    result = guard.check(email)

    guard003_failures = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-003"]
    assert len(guard003_failures) == 0


# ── GUARD-004: Banned opener patterns ─────────────────────────────


def test_guard_blocks_banned_opener_given_your_role(guard):
    """GUARD-004: 'Given your role as...' opener → blocked."""
    email = _make_email(
        body="Hi Chris,\nGiven your role as CRO at Acme Corp, quick context about AI execution.",
    )
    result = guard.check(email)

    guard004_failures = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-004"]
    assert len(guard004_failures) > 0


def test_guard_blocks_hope_this_finds_you(guard):
    """GUARD-004: 'I hope this finds you' opener → blocked."""
    email = _make_email(
        body="Hi there,\nI hope this email finds you well. I wanted to discuss AI strategy.",
    )
    result = guard.check(email)

    guard004_failures = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-004"]
    assert len(guard004_failures) > 0


def test_guard_passes_signal_based_opener(guard):
    """Signal-based opener (not banned) → passes GUARD-004."""
    email = _make_email(
        body=(
            "Hi Chris,\n"
            "Noticed Acme Corp's recent AI hiring push in the engineering team. "
            "Most teams at this stage need an operating cadence for execution."
        ),
    )
    result = guard.check(email)

    guard004_failures = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-004"]
    assert len(guard004_failures) == 0


# ── GUARD-005: Generic phrase density ─────────────────────────────


def test_guard_blocks_high_generic_density(guard):
    """GUARD-005: >40% generic phrases → blocked."""
    # Build body with many generic phrases
    body = (
        "In today's fast-paced business environment, we help you leverage cutting-edge AI. "
        "Revolutionize your workflows and unlock the power of automation. "
        "Transform your business with our best-in-class solution."
    )
    email = _make_email(body=body)
    result = guard.check(email)

    guard005_failures = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-005"]
    assert len(guard005_failures) > 0


def test_guard_passes_low_generic_density(guard):
    """Specific, non-generic content → passes GUARD-005."""
    email = _make_email(
        body=(
            "Noticed Acme Corp added 3 ML engineers last quarter. "
            "Teams at that stage often need an operating cadence to "
            "move pilots into production before momentum stalls."
        ),
    )
    result = guard.check(email)

    guard005_failures = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-005"]
    assert len(guard005_failures) == 0


# ── Soft mode ─────────────────────────────────────────────────────


def test_soft_mode_logs_but_passes(guard, memory):
    """QUALITY_GUARD_MODE=soft logs failures but returns passed=True."""
    memory.record_rejection("soft@co.com", "personalization_mismatch")
    memory.record_rejection("soft@co.com", "tone_style_issue")

    email = _make_email(to="soft@co.com")
    with patch.dict("os.environ", {"QUALITY_GUARD_MODE": "soft"}, clear=False):
        result = guard.check(email)

    # Soft mode: still marks as passed despite failures
    assert result["passed"] is True
    # But rule_failures are still populated
    assert len(result["rule_failures"]) > 0


# ── Disabled guard ────────────────────────────────────────────────


def test_disabled_guard_passes_everything(memory):
    """QUALITY_GUARD_ENABLED=false → always passes."""
    with patch.dict("os.environ", {"QUALITY_GUARD_ENABLED": "false"}, clear=False):
        guard = QualityGuard(rejection_memory=memory)
        email = _make_email(body="Terrible generic body with no personalization")
        result = guard.check(email)
        assert result["passed"] is True
        assert result["rule_failures"] == []


# ── Result shape ──────────────────────────────────────────────────


def test_result_contains_all_fields(guard):
    email = _make_email()
    result = guard.check(email)

    assert "passed" in result
    assert "blocked_reason" in result
    assert "rule_failures" in result
    assert "draft_fingerprint" in result
    assert "personalization_evidence" in result
    assert "rejection_memory_hit" in result
    assert isinstance(result["draft_fingerprint"], str)
    assert len(result["draft_fingerprint"]) == 32


# ── Andrew/Celia integration scenario ─────────────────────────────


def test_andrew_replay_blocked_by_guard(guard, memory):
    """Full Andrew scenario: 2 rejections → 3rd attempt blocked by guard."""
    # Rejection 1
    memory.record_rejection(
        "andrew.mahr@wpromote.com", "personalization_mismatch",
        subject="AI roadmap for Wpromote",
        body="Given your role as CRO at Wpromote, quick context...",
        feedback_text="AI-identifiable generic opener",
    )
    # Rejection 2
    memory.record_rejection(
        "andrew.mahr@wpromote.com", "personalization_mismatch",
        subject="Wpromote: practical AI roadmap",
        body="As a fellow revenue leader at Wpromote...",
        feedback_text="Still generic, no Wpromote initiative",
    )

    # 3rd attempt — same lead, similar content
    email = _make_email(
        to="andrew.mahr@wpromote.com",
        subject="AI execution plan for Wpromote",
        body="Given your role as CRO at Wpromote, quick context: Most teams run AI experiments...",
        company="Wpromote",
        title="CRO",
    )
    result = guard.check(email)
    assert result["passed"] is False
    assert result["rejection_memory_hit"] is True


def test_celia_different_content_still_blocked_on_count(guard, memory):
    """Celia with 2 rejections: even new content blocked without new evidence."""
    memory.record_rejection(
        "celia.kettering@wpromote.com", "personalization_mismatch",
        subject="Subject 1", body="Body 1",
    )
    memory.record_rejection(
        "celia.kettering@wpromote.com", "weak_subject",
        subject="Subject 2", body="Body 2",
    )

    # New content but no new enrichment evidence
    email = _make_email(
        to="celia.kettering@wpromote.com",
        subject="Fresh angle for Wpromote AI strategy",
        body="Noticed Wpromote's Q4 revenue growth. As VP Ops driving execution cadence, practical AI frameworks help teams scale.",
        company="Wpromote",
        title="VP Operations",
    )
    result = guard.check(email)
    # Should be blocked on GUARD-001 (rejection count threshold)
    guard001 = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-001"]
    assert len(guard001) > 0
