"""Tests for core.rejection_memory — per-lead rejection history store."""

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from core.rejection_memory import (
    RejectionMemory,
    compute_draft_fingerprint,
    _normalize_email,
    _email_hash,
)


@pytest.fixture
def memory(tmp_path):
    """RejectionMemory with no Redis, filesystem only."""
    with patch.dict("os.environ", {"REDIS_URL": ""}, clear=False):
        mem = RejectionMemory(storage_dir=tmp_path / "rejection_memory")
        mem._redis = None  # force file-only
        yield mem


# ── compute_draft_fingerprint ──────────────────────────────────────


def test_fingerprint_deterministic():
    fp1 = compute_draft_fingerprint("Subject A", "Body content here")
    fp2 = compute_draft_fingerprint("Subject A", "Body content here")
    assert fp1 == fp2
    assert len(fp1) == 32


def test_fingerprint_differs_for_different_content():
    fp1 = compute_draft_fingerprint("Subject A", "Body content here")
    fp2 = compute_draft_fingerprint("Subject B", "Totally different body")
    assert fp1 != fp2


def test_fingerprint_normalizes_whitespace():
    fp1 = compute_draft_fingerprint("  Subject  A  ", "Body   content   here")
    fp2 = compute_draft_fingerprint("Subject A", "Body content here")
    assert fp1 == fp2


def test_fingerprint_uses_first_500_chars():
    long_body = "x" * 1000
    fp1 = compute_draft_fingerprint("Subj", long_body)
    fp2 = compute_draft_fingerprint("Subj", long_body[:500])
    assert fp1 == fp2


# ── record_rejection ──────────────────────────────────────────────


def test_record_rejection_stores_and_retrieves(memory):
    result = memory.record_rejection(
        lead_email="andrew.mahr@wpromote.com",
        rejection_tag="personalization_mismatch",
        subject="AI roadmap for Wpromote",
        body="Given your role as CRO at Wpromote, quick context...",
        feedback_text="Too generic, no specific company initiative",
    )
    assert result["rejection_count"] == 1
    assert result["lead_email"] == "andrew.mahr@wpromote.com"
    assert "personalization_mismatch" in result["rejection_tags"]

    history = memory.get_rejection_history("andrew.mahr@wpromote.com")
    assert history is not None
    assert history["rejection_count"] == 1
    assert len(history["rejected_body_hashes"]) == 1
    assert len(history["feedback_texts"]) == 1


def test_record_rejection_increments_count(memory):
    memory.record_rejection("celia@wpromote.com", "personalization_mismatch")
    memory.record_rejection("celia@wpromote.com", "tone_style_issue", feedback_text="Too formal")
    history = memory.get_rejection_history("celia@wpromote.com")
    assert history["rejection_count"] == 2
    assert len(history["rejection_tags"]) == 2


def test_record_rejection_empty_email_returns_empty(memory):
    result = memory.record_rejection("", "personalization_mismatch")
    assert result == {}


def test_record_rejection_stores_template_id(memory):
    memory.record_rejection(
        "test@example.com", "weak_subject",
        template_id="t1_executive_buyin",
    )
    history = memory.get_rejection_history("test@example.com")
    assert "t1_executive_buyin" in history["rejected_template_ids"]


def test_record_rejection_deduplicates_subjects(memory):
    memory.record_rejection("a@b.com", "other", subject="Same subject")
    memory.record_rejection("a@b.com", "other", subject="Same subject")
    history = memory.get_rejection_history("a@b.com")
    assert history["rejected_subjects"].count("Same subject") == 1


# ── get_rejection_history ──────────────────────────────────────────


def test_no_history_returns_none(memory):
    assert memory.get_rejection_history("unknown@example.com") is None


def test_email_normalization(memory):
    memory.record_rejection("Andrew.Mahr@Wpromote.COM", "other")
    history = memory.get_rejection_history("andrew.mahr@wpromote.com")
    assert history is not None
    assert history["rejection_count"] == 1


# ── TTL ────────────────────────────────────────────────────────────


def test_ttl_expired_returns_none(memory):
    memory.record_rejection("old@example.com", "other")
    # Backdate last_rejected_at to 31 days ago
    history = memory.get_rejection_history("old@example.com")
    history["last_rejected_at"] = (
        datetime.now(timezone.utc) - timedelta(days=31)
    ).isoformat()
    memory._persist("old@example.com", history)

    assert memory.get_rejection_history("old@example.com") is None


def test_ttl_not_expired_returns_record(memory):
    memory.record_rejection("recent@example.com", "other")
    history = memory.get_rejection_history("recent@example.com")
    history["last_rejected_at"] = (
        datetime.now(timezone.utc) - timedelta(days=29)
    ).isoformat()
    memory._persist("recent@example.com", history)

    assert memory.get_rejection_history("recent@example.com") is not None


# ── is_repeat_draft ────────────────────────────────────────────────


def test_repeat_draft_detected(memory):
    memory.record_rejection(
        "test@co.com", "other",
        subject="AI roadmap", body="Given your role as CRO...",
    )
    assert memory.is_repeat_draft("test@co.com", "AI roadmap", "Given your role as CRO...") is True


def test_different_draft_not_flagged(memory):
    memory.record_rejection(
        "test@co.com", "other",
        subject="AI roadmap", body="Given your role as CRO...",
    )
    assert memory.is_repeat_draft("test@co.com", "New subject", "Completely different content") is False


def test_no_history_not_repeat(memory):
    assert memory.is_repeat_draft("new@co.com", "Subject", "Body") is False


# ── should_block_lead ──────────────────────────────────────────────


def test_should_not_block_first_rejection(memory):
    memory.record_rejection("first@co.com", "personalization_mismatch")
    blocked, reason = memory.should_block_lead("first@co.com")
    assert blocked is False


def test_should_block_after_two_rejections(memory):
    memory.record_rejection("blocked@co.com", "personalization_mismatch")
    memory.record_rejection("blocked@co.com", "tone_style_issue")
    blocked, reason = memory.should_block_lead("blocked@co.com")
    assert blocked is True
    assert "2 prior rejections" in reason


def test_should_not_block_with_new_evidence(memory):
    memory.record_rejection("evidence@co.com", "personalization_mismatch")
    memory.record_rejection("evidence@co.com", "tone_style_issue")
    blocked, reason = memory.should_block_lead("evidence@co.com", has_new_evidence=True)
    assert blocked is False


def test_should_not_block_unknown_lead(memory):
    blocked, reason = memory.should_block_lead("unknown@co.com")
    assert blocked is False
    assert reason == ""


# ── get_rejected_template_ids ──────────────────────────────────────


def test_rejected_template_ids(memory):
    memory.record_rejection("tmpl@co.com", "other", template_id="t1_executive_buyin")
    memory.record_rejection("tmpl@co.com", "other", template_id="t1_value_first")
    ids = memory.get_rejected_template_ids("tmpl@co.com")
    assert "t1_executive_buyin" in ids
    assert "t1_value_first" in ids


def test_rejected_template_ids_empty_for_unknown(memory):
    assert memory.get_rejected_template_ids("nope@co.com") == []


# ── get_feedback_context ───────────────────────────────────────────


def test_feedback_context_shape(memory):
    memory.record_rejection(
        "ctx@co.com", "personalization_mismatch",
        feedback_text="Too generic opener",
        template_id="t1_executive_buyin",
    )
    ctx = memory.get_feedback_context("ctx@co.com")
    assert ctx["rejection_count"] == 1
    assert "personalization_mismatch" in ctx["rejection_tags"]
    assert "Too generic opener" in ctx["feedback_texts"]
    assert "t1_executive_buyin" in ctx["rejected_template_ids"]


def test_feedback_context_empty_for_unknown(memory):
    assert memory.get_feedback_context("nope@co.com") == {}


# ── Andrew/Celia replay test ──────────────────────────────────────


def test_andrew_celia_replay_blocked(memory):
    """Simulate the exact failure mode: 2 rejections for Andrew → 3rd blocked."""
    # Rejection 1
    memory.record_rejection(
        lead_email="andrew.mahr@wpromote.com",
        rejection_tag="personalization_mismatch",
        subject="AI roadmap for Wpromote",
        body="Given your role as CRO at Wpromote, quick context: Most teams...",
        feedback_text="AI-identifiable generic opener, no company initiative proof",
    )
    # Rejection 2
    memory.record_rejection(
        lead_email="andrew.mahr@wpromote.com",
        rejection_tag="personalization_mismatch",
        subject="Wpromote: practical AI roadmap",
        body="As a fellow revenue leader at Wpromote, I noticed teams...",
        feedback_text="Still generic, no specific Wpromote initiative",
    )

    # 3rd attempt should be blocked
    blocked, reason = memory.should_block_lead("andrew.mahr@wpromote.com")
    assert blocked is True
    assert "personalization_mismatch" in reason

    # Repeat draft detection
    assert memory.is_repeat_draft(
        "andrew.mahr@wpromote.com",
        "AI roadmap for Wpromote",
        "Given your role as CRO at Wpromote, quick context: Most teams...",
    ) is True

    # Different draft not flagged as repeat
    assert memory.is_repeat_draft(
        "andrew.mahr@wpromote.com",
        "Completely new angle",
        "Noticed Wpromote's recent Q4 hiring push in AI ops...",
    ) is False


# ── filesystem persistence ─────────────────────────────────────────


def test_filesystem_persistence_across_instances(tmp_path):
    """Records survive across RejectionMemory instances (filesystem)."""
    storage = tmp_path / "rm"
    with patch.dict("os.environ", {"REDIS_URL": ""}, clear=False):
        mem1 = RejectionMemory(storage_dir=storage)
        mem1._redis = None
        mem1.record_rejection("persist@co.com", "other", subject="Test")

    with patch.dict("os.environ", {"REDIS_URL": ""}, clear=False):
        mem2 = RejectionMemory(storage_dir=storage)
        mem2._redis = None
        history = mem2.get_rejection_history("persist@co.com")
        assert history is not None
        assert history["rejection_count"] == 1
