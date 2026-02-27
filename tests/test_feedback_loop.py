"""Tests for core/feedback_loop.py — deterministic feedback loop storage.

This module bridges email outcomes (approve/reject/bounce/meeting) into
training tuples consumed by the self-annealing engine. These tests verify
the record/read/aggregate contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.feedback_loop import FeedbackLoop, REWARD_BY_OUTCOME


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def feedback(tmp_path):
    """Create FeedbackLoop with temp storage and no Redis."""
    with patch.object(FeedbackLoop, "_build_redis_client", return_value=None):
        fl = FeedbackLoop(storage_dir=tmp_path / "feedback_loop")
    return fl


def _sample_email(**overrides) -> Dict[str, Any]:
    base = {
        "to": "prospect@acmecorp.com",
        "subject": "AI-driven growth for Acme Corp",
        "body": "Hi John...",
        "tier": "tier_1",
        "angle": "executive_buyin",
        "template_version": "t1_v3",
        "recipient_data": {"company": "Acme Corp", "title": "VP of Sales"},
    }
    base.update(overrides)
    return base


# ── record_email_outcome tests ───────────────────────────────────


class TestRecordOutcome:

    def test_records_approved_outcome(self, feedback):
        """record_email_outcome stores an approved event with correct reward."""
        result = feedback.record_email_outcome(
            email_data=_sample_email(),
            outcome="approved",
            action="gatekeeper_approve",
        )
        assert result["outcome"] == "approved"
        assert result["reward"] == REWARD_BY_OUTCOME["approved"]
        assert result["action"] == "gatekeeper_approve"
        assert result["id"]  # UUID present

    def test_records_rejected_outcome(self, feedback):
        """Rejected outcome gets negative reward."""
        result = feedback.record_email_outcome(
            email_data=_sample_email(rejection_tag="too_generic", feedback="opener too vague"),
            outcome="rejected",
            action="gatekeeper_reject",
        )
        assert result["reward"] == -0.6
        assert result["evidence"]["rejection_tag"] == "too_generic"
        assert result["evidence"]["feedback"] == "opener too vague"

    def test_records_sent_proved_outcome(self, feedback):
        """Sent+proved (meeting booked) gets highest reward."""
        result = feedback.record_email_outcome(
            email_data=_sample_email(proof_status="meeting_booked", proof_source="instantly_webhook"),
            outcome="sent_proved",
            action="instantly_send",
        )
        assert result["reward"] == 1.0
        assert result["evidence"]["proof_status"] == "meeting_booked"

    def test_records_blocked_deliverability(self, feedback):
        """Deliverability block gets negative reward."""
        result = feedback.record_email_outcome(
            email_data=_sample_email(deliverability_risk="high", deliverability_reasons=["bounce_risk"]),
            outcome="blocked_deliverability",
            action="guard_block",
        )
        assert result["reward"] == -0.5
        assert result["evidence"]["deliverability_risk"] == "high"

    def test_unknown_outcome_zero_reward(self, feedback):
        """Unknown outcome type gets 0.0 reward."""
        result = feedback.record_email_outcome(
            email_data=_sample_email(),
            outcome="some_new_outcome",
            action="test",
        )
        assert result["reward"] == 0.0

    def test_lead_features_extracted(self, feedback):
        """Lead features (email, domain, tier, company, title) extracted correctly."""
        result = feedback.record_email_outcome(
            email_data=_sample_email(),
            outcome="approved",
            action="test",
        )
        lf = result["lead_features"]
        assert lf["lead_email"] == "prospect@acmecorp.com"
        assert lf["lead_domain"] == "acmecorp.com"
        assert lf["tier"] == "tier_1"
        assert lf["company"] == "Acme Corp"
        assert lf["title"] == "VP of Sales"

    def test_persists_to_jsonl(self, feedback):
        """Events are appended to training_tuples.jsonl."""
        feedback.record_email_outcome(_sample_email(), "approved", "test")
        feedback.record_email_outcome(_sample_email(to="b@co.com"), "rejected", "test")

        assert feedback.tuples_file.exists()
        with open(feedback.tuples_file) as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) == 2
        assert lines[0]["outcome"] == "approved"
        assert lines[1]["outcome"] == "rejected"

    def test_metadata_passed_through(self, feedback):
        """Custom metadata is stored on the event."""
        result = feedback.record_email_outcome(
            email_data=_sample_email(),
            outcome="approved",
            action="test",
            metadata={"reviewer": "hos", "batch_id": "batch_001"},
        )
        assert result["metadata"]["reviewer"] == "hos"
        assert result["metadata"]["batch_id"] == "batch_001"


# ── build_policy_deltas tests ────────────────────────────────────


class TestPolicyDeltas:

    def test_empty_history_empty_delta(self, feedback):
        """No events → empty policy delta."""
        delta = feedback.build_policy_deltas(window_days=7)
        assert delta["opener_pattern_suppressions"] == []
        assert delta["domain_risk_updates"] == []
        assert delta["rejection_tag_constraints"] == []

    def test_rejected_feedback_creates_opener_suppression(self, feedback):
        """Rejected emails with feedback text create opener suppressions."""
        for _ in range(3):
            feedback.record_email_outcome(
                email_data=_sample_email(
                    rejection_tag="too_generic",
                    feedback="opener too vague and impersonal",
                ),
                outcome="rejected",
                action="gatekeeper_reject",
            )
        delta = feedback.build_policy_deltas(window_days=7)
        suppressions = delta["opener_pattern_suppressions"]
        assert len(suppressions) >= 1
        assert suppressions[0]["count"] == 3

    def test_blocked_deliverability_creates_domain_risk(self, feedback):
        """Deliverability blocks create domain risk updates."""
        for _ in range(5):
            feedback.record_email_outcome(
                email_data=_sample_email(to="user@risky-domain.com"),
                outcome="blocked_deliverability",
                action="guard_block",
            )
        delta = feedback.build_policy_deltas(window_days=7)
        domain_risks = delta["domain_risk_updates"]
        assert len(domain_risks) >= 1
        assert domain_risks[0]["domain"] == "risky-domain.com"
        assert domain_risks[0]["blocked_count"] == 5

    def test_rejection_tags_aggregated(self, feedback):
        """Rejection tags are counted across events."""
        for tag in ["too_generic", "too_generic", "wrong_angle", "too_generic"]:
            feedback.record_email_outcome(
                email_data=_sample_email(rejection_tag=tag),
                outcome="rejected",
                action="reject",
            )
        delta = feedback.build_policy_deltas(window_days=7)
        tags = delta["rejection_tag_constraints"]
        tag_map = {t["tag"]: t["count"] for t in tags}
        assert tag_map.get("too_generic") == 3
        assert tag_map.get("wrong_angle") == 1

    def test_delta_saved_to_file(self, feedback):
        """Policy delta is persisted to policy_deltas/ directory."""
        feedback.record_email_outcome(_sample_email(), "rejected", "test")
        feedback.build_policy_deltas(window_days=7)

        delta_files = list(feedback.policy_dir.glob("policy_delta_*.json"))
        assert len(delta_files) >= 1


# ── Reward mapping tests ─────────────────────────────────────────


class TestRewardMapping:

    def test_all_known_outcomes_have_rewards(self):
        """All documented outcomes have reward values."""
        expected = ["sent_proved", "sent_unresolved", "blocked_deliverability", "approved", "rejected"]
        for outcome in expected:
            assert outcome in REWARD_BY_OUTCOME, f"Missing reward for {outcome}"

    def test_reward_ordering(self):
        """Rewards are ordered: sent_proved > approved > sent_unresolved > blocked > rejected."""
        assert REWARD_BY_OUTCOME["sent_proved"] > REWARD_BY_OUTCOME["approved"]
        assert REWARD_BY_OUTCOME["approved"] > REWARD_BY_OUTCOME["sent_unresolved"]
        assert REWARD_BY_OUTCOME["sent_unresolved"] > REWARD_BY_OUTCOME["blocked_deliverability"]
        assert REWARD_BY_OUTCOME["blocked_deliverability"] > REWARD_BY_OUTCOME["rejected"]
