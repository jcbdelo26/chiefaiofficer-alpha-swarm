"""
Tests for feedback loop -> quality guard integration (Sprint D-4).

Validates:
  1. FeedbackLoop.get_lead_approval_count() returns correct counts
  2. FeedbackLoop.get_latest_policy_delta() reads the most recent delta
  3. QualityGuard GUARD-001 boost: leads approved 3+ times bypass rejection block
  4. QualityGuard GUARD-004 extension: dynamic banned openers from policy deltas
  5. Feature flag gating: all feedback behaviour OFF when flag is disabled
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from core.feedback_loop import FeedbackLoop
from core.rejection_memory import RejectionMemory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def feedback_dir(tmp_path):
    """Provide a temporary feedback loop storage directory."""
    d = tmp_path / "feedback_loop"
    d.mkdir()
    (d / "policy_deltas").mkdir()
    return d


@pytest.fixture
def feedback_loop(feedback_dir):
    """FeedbackLoop with temp storage, no Redis."""
    loop = FeedbackLoop(storage_dir=feedback_dir)
    loop.redis_client = None
    return loop


@pytest.fixture
def rejection_mem(tmp_path):
    """RejectionMemory with temp storage, no Redis."""
    mem = RejectionMemory(storage_dir=tmp_path / "rejection_memory")
    mem._redis = None
    mem._use_redis = False
    return mem


def _write_tuples(feedback_dir: Path, tuples: list[dict]) -> None:
    """Write training tuples to the JSONL file."""
    with open(feedback_dir / "training_tuples.jsonl", "w", encoding="utf-8") as f:
        for t in tuples:
            f.write(json.dumps(t) + "\n")


def _write_policy_delta(feedback_dir: Path, delta: dict, name: str = "policy_delta_20260302_120000.json") -> None:
    """Write a policy delta file."""
    with open(feedback_dir / "policy_deltas" / name, "w", encoding="utf-8") as f:
        json.dump(delta, f)


# ---------------------------------------------------------------------------
# FeedbackLoop helper tests
# ---------------------------------------------------------------------------

class TestGetLeadApprovalCount:

    def test_no_tuples_returns_zero(self, feedback_loop):
        assert feedback_loop.get_lead_approval_count("nobody@test.com") == 0

    def test_counts_approved_outcomes(self, feedback_loop, feedback_dir):
        _write_tuples(feedback_dir, [
            {"lead_features": {"lead_email": "alice@co.com"}, "outcome": "approved"},
            {"lead_features": {"lead_email": "alice@co.com"}, "outcome": "approved"},
            {"lead_features": {"lead_email": "alice@co.com"}, "outcome": "sent_proved"},
            {"lead_features": {"lead_email": "alice@co.com"}, "outcome": "rejected"},
            {"lead_features": {"lead_email": "bob@co.com"}, "outcome": "approved"},
        ])
        assert feedback_loop.get_lead_approval_count("alice@co.com") == 3
        assert feedback_loop.get_lead_approval_count("bob@co.com") == 1

    def test_case_insensitive(self, feedback_loop, feedback_dir):
        _write_tuples(feedback_dir, [
            {"lead_features": {"lead_email": "alice@co.com"}, "outcome": "approved"},
        ])
        assert feedback_loop.get_lead_approval_count("Alice@CO.com") == 1


class TestGetLatestPolicyDelta:

    def test_no_deltas_returns_none(self, feedback_loop):
        assert feedback_loop.get_latest_policy_delta() is None

    def test_reads_most_recent(self, feedback_loop, feedback_dir):
        _write_policy_delta(feedback_dir, {"version": "old"}, "policy_delta_20260301_100000.json")
        _write_policy_delta(feedback_dir, {"version": "new"}, "policy_delta_20260302_120000.json")
        delta = feedback_loop.get_latest_policy_delta()
        assert delta["version"] == "new"


class TestBuildPolicyDeltas:

    def test_generates_delta_from_tuples(self, feedback_loop, feedback_dir):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        _write_tuples(feedback_dir, [
            {
                "timestamp": now,
                "outcome": "rejected",
                "evidence": {"feedback": "too generic opener", "rejection_tag": "tone_mismatch"},
                "lead_features": {"lead_domain": ""},
            },
            {
                "timestamp": now,
                "outcome": "rejected",
                "evidence": {"feedback": "too generic opener", "rejection_tag": "tone_mismatch"},
                "lead_features": {"lead_domain": ""},
            },
            {
                "timestamp": now,
                "outcome": "blocked_deliverability",
                "evidence": {"feedback": "", "rejection_tag": ""},
                "lead_features": {"lead_domain": "baddomain.com"},
            },
        ])
        delta = feedback_loop.build_policy_deltas(window_days=7)
        assert len(delta["opener_pattern_suppressions"]) >= 1
        assert delta["opener_pattern_suppressions"][0]["pattern"] == "too generic opener"
        assert delta["opener_pattern_suppressions"][0]["count"] == 2
        assert len(delta["domain_risk_updates"]) >= 1
        assert delta["domain_risk_updates"][0]["domain"] == "baddomain.com"


# ---------------------------------------------------------------------------
# QualityGuard integration tests (feature flag ON)
# ---------------------------------------------------------------------------

class TestGuard001ApprovalBoost:

    def test_boost_bypasses_rejection_block(self, rejection_mem, feedback_dir):
        """Lead with 3+ approvals passes GUARD-001 despite rejection history."""
        # Record 3 rejections (would normally block)
        rejection_mem.record_rejection("alice@co.com", "tone_mismatch")
        rejection_mem.record_rejection("alice@co.com", "too_generic")

        # Write 3 approvals to feedback tuples
        _write_tuples(feedback_dir, [
            {"lead_features": {"lead_email": "alice@co.com"}, "outcome": "approved"},
            {"lead_features": {"lead_email": "alice@co.com"}, "outcome": "approved"},
            {"lead_features": {"lead_email": "alice@co.com"}, "outcome": "sent_proved"},
        ])

        with patch.dict(os.environ, {"FEEDBACK_LOOP_POLICY_ENABLED": "true"}):
            # Reimport to pick up the flag
            import importlib
            import core.quality_guard as qg_mod
            importlib.reload(qg_mod)
            try:
                guard = qg_mod.QualityGuard(rejection_memory=rejection_mem)
                guard._feedback_loop = FeedbackLoop(storage_dir=feedback_dir)
                guard._feedback_loop.redis_client = None

                result = guard.check({
                    "to": "alice@co.com",
                    "subject": "Quick sync on your pipeline strategy",
                    "body": "Hi Alice,\nYour team at Acme Corp is scaling fast. As someone leading revenue operations, the shift in pipeline efficiency matters.\nWould a 15-min call make sense?",
                    "recipient_data": {"company": "Acme Corp", "title": "VP Revenue Operations"},
                })
                # GUARD-001 should be bypassed due to approval boost
                guard001_failures = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-001"]
                assert len(guard001_failures) == 0, f"GUARD-001 should be bypassed but got: {guard001_failures}"
            finally:
                # Restore module state
                importlib.reload(qg_mod)

    def test_no_boost_without_enough_approvals(self, rejection_mem, feedback_dir):
        """Lead with < 3 approvals is still blocked by GUARD-001."""
        rejection_mem.record_rejection("bob@co.com", "tone_mismatch")
        rejection_mem.record_rejection("bob@co.com", "too_generic")

        _write_tuples(feedback_dir, [
            {"lead_features": {"lead_email": "bob@co.com"}, "outcome": "approved"},
        ])

        with patch.dict(os.environ, {"FEEDBACK_LOOP_POLICY_ENABLED": "true"}):
            import importlib
            import core.quality_guard as qg_mod
            importlib.reload(qg_mod)
            try:
                guard = qg_mod.QualityGuard(rejection_memory=rejection_mem)
                guard._feedback_loop = FeedbackLoop(storage_dir=feedback_dir)
                guard._feedback_loop.redis_client = None

                result = guard.check({
                    "to": "bob@co.com",
                    "subject": "Quick sync",
                    "body": "Hi Bob,\nYour team at Acme Corp is scaling. Revenue growth matters.\n",
                    "recipient_data": {"company": "Acme Corp", "title": "VP Sales"},
                })
                guard001_failures = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-001"]
                assert len(guard001_failures) == 1, "GUARD-001 should still block"
            finally:
                importlib.reload(qg_mod)


class TestGuard004DynamicOpeners:

    def test_dynamic_openers_block_feedback_patterns(self, rejection_mem, feedback_dir):
        """Policy-derived opener patterns are enforced in GUARD-004."""
        _write_policy_delta(feedback_dir, {
            "opener_pattern_suppressions": [
                {"pattern": "Let me be blunt", "count": 5},
            ],
            "domain_risk_updates": [],
            "rejection_tag_constraints": [],
        })

        with patch.dict(os.environ, {"FEEDBACK_LOOP_POLICY_ENABLED": "true"}):
            import importlib
            import core.quality_guard as qg_mod
            importlib.reload(qg_mod)
            try:
                guard = qg_mod.QualityGuard(rejection_memory=rejection_mem)
                guard._feedback_loop = FeedbackLoop(storage_dir=feedback_dir)
                guard._feedback_loop.redis_client = None
                # Manually reload policy since we injected after init
                guard._load_feedback_policy()

                result = guard.check({
                    "to": "newlead@co.com",
                    "subject": "Partnership opportunity",
                    "body": "Hi Chris,\nLet me be blunt about what we see at Acme Corp. Revenue pipeline efficiency has dropped.\n",
                    "recipient_data": {"company": "Acme Corp", "title": "CRO"},
                })
                guard004_failures = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-004"]
                assert len(guard004_failures) == 1, "Dynamic opener should be blocked"
            finally:
                importlib.reload(qg_mod)

    def test_low_count_patterns_ignored(self, rejection_mem, feedback_dir):
        """Opener patterns with count < 2 are not added to banned list."""
        _write_policy_delta(feedback_dir, {
            "opener_pattern_suppressions": [
                {"pattern": "One-off bad opener", "count": 1},
            ],
            "domain_risk_updates": [],
            "rejection_tag_constraints": [],
        })

        with patch.dict(os.environ, {"FEEDBACK_LOOP_POLICY_ENABLED": "true"}):
            import importlib
            import core.quality_guard as qg_mod
            importlib.reload(qg_mod)
            try:
                guard = qg_mod.QualityGuard(rejection_memory=rejection_mem)
                guard._feedback_loop = FeedbackLoop(storage_dir=feedback_dir)
                guard._feedback_loop.redis_client = None
                guard._load_feedback_policy()

                assert len(guard._dynamic_banned_openers) == 0
            finally:
                importlib.reload(qg_mod)


# ---------------------------------------------------------------------------
# Feature flag OFF — no feedback behaviour
# ---------------------------------------------------------------------------

class TestFeatureFlagGating:

    def test_guard001_no_boost_when_flag_off(self, rejection_mem, feedback_dir):
        """Without FEEDBACK_LOOP_POLICY_ENABLED, no approval boost."""
        rejection_mem.record_rejection("alice@co.com", "tone_mismatch")
        rejection_mem.record_rejection("alice@co.com", "too_generic")

        _write_tuples(feedback_dir, [
            {"lead_features": {"lead_email": "alice@co.com"}, "outcome": "approved"},
            {"lead_features": {"lead_email": "alice@co.com"}, "outcome": "approved"},
            {"lead_features": {"lead_email": "alice@co.com"}, "outcome": "sent_proved"},
        ])

        # Flag is OFF (default)
        with patch.dict(os.environ, {"FEEDBACK_LOOP_POLICY_ENABLED": "false"}):
            import importlib
            import core.quality_guard as qg_mod
            importlib.reload(qg_mod)
            try:
                guard = qg_mod.QualityGuard(rejection_memory=rejection_mem)
                result = guard.check({
                    "to": "alice@co.com",
                    "subject": "Quick sync on strategy",
                    "body": "Hi Alice,\nYour team at Acme Corp is growing. Revenue operations efficiency matters.\n",
                    "recipient_data": {"company": "Acme Corp", "title": "VP Revenue Ops"},
                })
                guard001_failures = [f for f in result["rule_failures"] if f["rule_id"] == "GUARD-001"]
                assert len(guard001_failures) == 1, "Should still block without flag"
            finally:
                importlib.reload(qg_mod)

    def test_no_dynamic_openers_when_flag_off(self, rejection_mem, feedback_dir):
        """Without flag, dynamic openers are not loaded."""
        _write_policy_delta(feedback_dir, {
            "opener_pattern_suppressions": [
                {"pattern": "Bad opener from feedback", "count": 10},
            ],
            "domain_risk_updates": [],
            "rejection_tag_constraints": [],
        })

        with patch.dict(os.environ, {"FEEDBACK_LOOP_POLICY_ENABLED": "false"}):
            import importlib
            import core.quality_guard as qg_mod
            importlib.reload(qg_mod)
            try:
                guard = qg_mod.QualityGuard(rejection_memory=rejection_mem)
                assert len(guard._dynamic_banned_openers) == 0
            finally:
                importlib.reload(qg_mod)
