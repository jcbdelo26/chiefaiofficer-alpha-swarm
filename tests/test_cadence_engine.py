#!/usr/bin/env python3
"""
Cadence Engine Tests
=====================
Tests for XS-05 (step idempotency) and core cadence state transitions.
"""

import sys
from datetime import datetime, date, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from execution.cadence_engine import CadenceEngine, CadenceStep, LeadCadenceState


# =============================================================================
# FIXTURES
# =============================================================================

def _make_engine():
    """Create CadenceEngine with mocked internals."""
    engine = CadenceEngine.__new__(CadenceEngine)
    engine.hive_dir = Path("/tmp/test-hive")
    engine._config = {}
    engine._cadence_configs = {}
    engine._signal_mgr = None
    engine._state_store = MagicMock()
    engine.state_dir = Path("/tmp/test-hive/cadence_state")
    return engine


def _make_steps():
    """Create a minimal 3-step cadence definition."""
    return [
        CadenceStep(step=1, day=1, channel="email", action="intro", description="Intro email", condition="always"),
        CadenceStep(step=2, day=5, channel="email", action="followup", description="Value follow-up", condition="not_replied"),
        CadenceStep(step=3, day=10, channel="email", action="proof", description="Social proof", condition="not_replied"),
    ]


def _make_active_state(email="test@example.com", current_step=1, steps_completed=None):
    """Create an active LeadCadenceState."""
    return LeadCadenceState(
        email=email,
        cadence_id="default_21day",
        tier="tier_1",
        started_at=datetime.now(timezone.utc).isoformat(),
        current_step=current_step,
        status="active",
        linkedin_url="",
        linkedin_connected=False,
        lead_data={},
        steps_completed=steps_completed or [],
        last_step_at="",
        next_step_due=date.today().isoformat(),
    )


# =============================================================================
# TEST: Step Idempotency (XS-05)
# =============================================================================

class TestStepIdempotency:
    """Tests for XS-05: mark_step_done is idempotent against webhook retries."""

    def test_duplicate_mark_step_done_is_noop(self):
        """Calling mark_step_done twice for same step+action is idempotent."""
        engine = _make_engine()
        steps = _make_steps()

        # State after step 1 already completed
        state = _make_active_state(
            current_step=2,
            steps_completed=[{"step": 1, "action": "dispatched", "at": "2026-02-28T12:00:00Z"}],
        )

        with patch.object(engine, "_load_lead_state", return_value=state), \
             patch.object(engine, "get_cadence_definition", return_value=({}, steps)), \
             patch.object(engine, "_save_lead_state") as mock_save:
            engine.mark_step_done("test@example.com", step_num=1, result="dispatched")

        # Should NOT save — duplicate detected
        mock_save.assert_not_called()

    def test_first_mark_step_done_proceeds(self):
        """First mark_step_done for a step advances the cadence."""
        engine = _make_engine()
        steps = _make_steps()
        state = _make_active_state(current_step=1, steps_completed=[])

        with patch.object(engine, "_load_lead_state", return_value=state), \
             patch.object(engine, "get_cadence_definition", return_value=({}, steps)), \
             patch.object(engine, "_save_lead_state") as mock_save:
            engine.mark_step_done("test@example.com", step_num=1, result="dispatched")

        # Should save — step recorded
        mock_save.assert_called_once()
        # State should advance to step 2
        assert state.current_step == 2

    def test_different_action_same_step_not_duplicate(self):
        """Same step with different action (e.g. 'skipped' vs 'dispatched') is not duplicate."""
        engine = _make_engine()
        steps = _make_steps()

        state = _make_active_state(
            current_step=2,
            steps_completed=[{"step": 1, "action": "skipped", "at": "2026-02-28T12:00:00Z"}],
        )

        with patch.object(engine, "_load_lead_state", return_value=state), \
             patch.object(engine, "get_cadence_definition", return_value=({}, steps)), \
             patch.object(engine, "_save_lead_state") as mock_save:
            engine.mark_step_done("test@example.com", step_num=1, result="dispatched")

        # Different action — should proceed
        mock_save.assert_called_once()

    def test_inactive_lead_ignored(self):
        """mark_step_done on non-active lead returns immediately."""
        engine = _make_engine()
        state = _make_active_state()
        state.status = "completed"

        with patch.object(engine, "_load_lead_state", return_value=state), \
             patch.object(engine, "_save_lead_state") as mock_save:
            engine.mark_step_done("test@example.com", step_num=1)

        mock_save.assert_not_called()

    def test_missing_lead_ignored(self):
        """mark_step_done on unknown lead returns immediately."""
        engine = _make_engine()

        with patch.object(engine, "_load_lead_state", return_value=None), \
             patch.object(engine, "_save_lead_state") as mock_save:
            engine.mark_step_done("unknown@example.com", step_num=1)

        mock_save.assert_not_called()


# =============================================================================
# TEST: Step Completion & Cadence Advance
# =============================================================================

class TestStepCompletion:
    """Tests for basic step completion flow."""

    def test_last_step_completes_cadence(self):
        """Completing the last step sets status=completed."""
        engine = _make_engine()
        steps = _make_steps()
        state = _make_active_state(
            current_step=3,
            steps_completed=[
                {"step": 1, "action": "dispatched", "at": "2026-02-26T12:00:00Z"},
                {"step": 2, "action": "dispatched", "at": "2026-02-27T12:00:00Z"},
            ],
        )

        with patch.object(engine, "_load_lead_state", return_value=state), \
             patch.object(engine, "get_cadence_definition", return_value=({}, steps)), \
             patch.object(engine, "_save_lead_state") as mock_save:
            engine.mark_step_done("test@example.com", step_num=3, result="dispatched")

        mock_save.assert_called_once()
        assert state.status == "completed"
        assert state.exit_reason == "all_steps_done"

    def test_middle_step_advances_to_next(self):
        """Completing step 2 advances current_step to 3."""
        engine = _make_engine()
        steps = _make_steps()
        state = _make_active_state(
            current_step=2,
            steps_completed=[
                {"step": 1, "action": "dispatched", "at": "2026-02-26T12:00:00Z"},
            ],
        )

        with patch.object(engine, "_load_lead_state", return_value=state), \
             patch.object(engine, "get_cadence_definition", return_value=({}, steps)), \
             patch.object(engine, "_save_lead_state"):
            engine.mark_step_done("test@example.com", step_num=2, result="dispatched")

        assert state.current_step == 3
        assert state.status == "active"
