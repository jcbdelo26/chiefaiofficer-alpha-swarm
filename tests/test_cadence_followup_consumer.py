"""Tests for cadence engine LinkedIn follow-up flag consumer (HR-07).

Validates:
 - Flag files read from .hive-mind/heyreach_followups/
 - Cadence state updated (linkedin_connected, next_step_due accelerated)
 - Processed flags not re-read
 - Leads without active cadence gracefully skipped
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict
from unittest.mock import patch, MagicMock

import pytest

import sys
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_hive(tmp_path):
    """Create a temporary hive-mind directory with cadence_state and heyreach_followups."""
    hive = tmp_path / ".hive-mind"
    (hive / "cadence_state").mkdir(parents=True)
    (hive / "heyreach_followups").mkdir(parents=True)
    return hive


def _write_cadence_state(hive: Path, email: str, **overrides):
    """Write a minimal cadence state file."""
    state = {
        "email": email,
        "cadence_id": "default_21day",
        "tier": "tier_1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "current_step": 3,
        "status": "active",
        "exit_reason": "",
        "linkedin_url": "https://linkedin.com/in/test",
        "linkedin_connected": False,
        "lead_data": {},
        "steps_completed": [],
        "last_step_at": "",
        "next_step_due": (date.today() + timedelta(days=5)).isoformat(),
        "paused_at": "",
    }
    state.update(overrides)
    filename = email.replace("@", "_at_").replace(".", "_") + ".json"
    (hive / "cadence_state" / filename).write_text(
        json.dumps(state, indent=2), encoding="utf-8"
    )
    return state


def _write_followup_flag(hive: Path, email: str, reason: str = "connection_accepted", processed: bool = False):
    """Write a follow-up flag file."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{reason}_{ts}_{email.split('@')[0]}.json"
    flag = {
        "reason": reason,
        "lead": {
            "email": email,
            "first_name": "Test",
            "last_name": "User",
            "linkedin_url": "https://linkedin.com/in/test",
        },
        "flagged_at": datetime.now(timezone.utc).isoformat(),
        "processed": processed,
    }
    path = hive / "heyreach_followups" / filename
    path.write_text(json.dumps(flag, indent=2), encoding="utf-8")
    return path


def _make_engine(hive: Path):
    """Create a CadenceEngine pointed at the temp hive dir with file-only backend."""
    from execution.cadence_engine import CadenceEngine
    with patch.dict("os.environ", {"STATE_BACKEND": "file"}):
        engine = CadenceEngine(hive_dir=hive)
    return engine


class TestCadenceFollowupConsumer:
    """Test process_linkedin_followups() method."""

    def test_no_flags_returns_empty(self, tmp_hive):
        engine = _make_engine(tmp_hive)
        result = engine.process_linkedin_followups()
        assert result == []

    def test_no_followup_dir_returns_empty(self, tmp_path):
        """If heyreach_followups dir doesn't exist, return empty."""
        hive = tmp_path / ".hive-mind"
        (hive / "cadence_state").mkdir(parents=True)
        engine = _make_engine(hive)
        result = engine.process_linkedin_followups()
        assert result == []

    def test_processes_flag_and_accelerates(self, tmp_hive):
        email = "alice@example.com"
        future_date = (date.today() + timedelta(days=7)).isoformat()
        _write_cadence_state(tmp_hive, email, next_step_due=future_date)
        flag_path = _write_followup_flag(tmp_hive, email)

        engine = _make_engine(tmp_hive)
        result = engine.process_linkedin_followups()

        assert email in result
        # Verify cadence state was updated
        state = engine._load_lead_state(email)
        assert state.linkedin_connected is True
        assert state.next_step_due == date.today().isoformat()

    def test_marks_flag_as_processed(self, tmp_hive):
        email = "bob@example.com"
        _write_cadence_state(tmp_hive, email)
        flag_path = _write_followup_flag(tmp_hive, email)

        engine = _make_engine(tmp_hive)
        engine.process_linkedin_followups()

        flag_data = json.loads(flag_path.read_text(encoding="utf-8"))
        assert flag_data["processed"] is True
        assert "processed_at" in flag_data

    def test_skips_already_processed(self, tmp_hive):
        email = "charlie@example.com"
        _write_cadence_state(tmp_hive, email)
        _write_followup_flag(tmp_hive, email, processed=True)

        engine = _make_engine(tmp_hive)
        result = engine.process_linkedin_followups()
        assert result == []

    def test_skips_no_active_cadence(self, tmp_hive):
        email = "dave@example.com"
        _write_cadence_state(tmp_hive, email, status="exited")
        flag_path = _write_followup_flag(tmp_hive, email)

        engine = _make_engine(tmp_hive)
        result = engine.process_linkedin_followups()
        assert result == []

        # Flag should be marked processed with skip reason
        flag_data = json.loads(flag_path.read_text(encoding="utf-8"))
        assert flag_data["processed"] is True
        assert flag_data["skip_reason"] == "no_active_cadence"

    def test_skips_no_email_in_flag(self, tmp_hive):
        """Flag with no email in lead data should be skipped."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        flag_path = tmp_hive / "heyreach_followups" / f"connection_accepted_{ts}_noemail.json"
        flag_path.write_text(json.dumps({
            "reason": "connection_accepted",
            "lead": {"first_name": "No", "last_name": "Email"},
            "flagged_at": datetime.now(timezone.utc).isoformat(),
            "processed": False,
        }, indent=2), encoding="utf-8")

        engine = _make_engine(tmp_hive)
        result = engine.process_linkedin_followups()
        assert result == []

        flag_data = json.loads(flag_path.read_text(encoding="utf-8"))
        assert flag_data["processed"] is True
        assert flag_data["skip_reason"] == "no_email"

    def test_already_connected_only_accelerates(self, tmp_hive):
        """If linkedin_connected already True, only accelerate date."""
        email = "eve@example.com"
        future = (date.today() + timedelta(days=10)).isoformat()
        _write_cadence_state(tmp_hive, email, linkedin_connected=True, next_step_due=future)
        _write_followup_flag(tmp_hive, email)

        engine = _make_engine(tmp_hive)
        result = engine.process_linkedin_followups()

        assert email in result
        state = engine._load_lead_state(email)
        assert state.next_step_due == date.today().isoformat()

    def test_step_due_today_not_double_accelerated(self, tmp_hive):
        """If next_step_due is already today or past, don't change it."""
        email = "frank@example.com"
        today = date.today().isoformat()
        _write_cadence_state(tmp_hive, email, next_step_due=today, linkedin_connected=True)
        _write_followup_flag(tmp_hive, email)

        engine = _make_engine(tmp_hive)
        result = engine.process_linkedin_followups()

        # Nothing changed (linkedin_connected already True, date already today)
        assert result == []
