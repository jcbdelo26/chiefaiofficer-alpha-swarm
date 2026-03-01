#!/usr/bin/env python3
"""
XS-01: Partial Dispatch Detection Tests
=========================================
Tests that the OPERATOR correctly detects when one channel dispatched
successfully while the other failed, and produces the right alerts.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from execution.operator_outbound import OperatorOutbound, OperatorReport


# =============================================================================
# HELPERS
# =============================================================================

def _make_report(**overrides) -> OperatorReport:
    """Create a minimal OperatorReport for testing."""
    defaults = {
        "run_id": "test-run-001",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": False,
        "motion": "outbound",
        "instantly_report": None,
        "heyreach_report": None,
        "errors": [],
    }
    defaults.update(overrides)
    return OperatorReport(**defaults)


# =============================================================================
# TEST: XS-01 Partial Dispatch Detection
# =============================================================================

class TestPartialDispatchDetection:
    """Tests for XS-01: detect when one channel succeeds and the other fails."""

    def test_instantly_ok_heyreach_failed(self):
        """Instantly dispatched emails but HeyReach errored → partial detected."""
        report = _make_report(
            instantly_report={"total_dispatched": 3},
            heyreach_report={"total_dispatched": 0},
            errors=["HeyReach dispatch error: API timeout"],
        )
        result = OperatorOutbound._check_partial_dispatch(report)

        assert result is True
        xs01_errors = [e for e in report.errors if e.startswith("XS-01:")]
        assert len(xs01_errors) == 1
        assert "Instantly succeeded" in xs01_errors[0]
        assert "HeyReach failed" in xs01_errors[0]

    def test_heyreach_ok_instantly_failed(self):
        """HeyReach dispatched but Instantly errored → partial detected."""
        report = _make_report(
            instantly_report={"total_dispatched": 0},
            heyreach_report={"total_dispatched": 2},
            errors=["Instantly dispatch error: rate limit exceeded"],
        )
        result = OperatorOutbound._check_partial_dispatch(report)

        assert result is True
        xs01_errors = [e for e in report.errors if e.startswith("XS-01:")]
        assert len(xs01_errors) == 1
        assert "HeyReach succeeded" in xs01_errors[0]
        assert "Instantly failed" in xs01_errors[0]

    def test_both_succeed_no_detection(self):
        """Both channels dispatched successfully → no partial dispatch."""
        report = _make_report(
            instantly_report={"total_dispatched": 5},
            heyreach_report={"total_dispatched": 3},
            errors=[],
        )
        result = OperatorOutbound._check_partial_dispatch(report)

        assert result is False
        assert not any(e.startswith("XS-01:") for e in report.errors)

    def test_both_fail_no_detection(self):
        """Both channels failed → not partial, it's total failure. No XS-01."""
        report = _make_report(
            instantly_report={"total_dispatched": 0},
            heyreach_report={"total_dispatched": 0},
            errors=[
                "Instantly dispatch error: connection refused",
                "HeyReach dispatch error: API timeout",
            ],
        )
        result = OperatorOutbound._check_partial_dispatch(report)

        assert result is False
        assert not any(e.startswith("XS-01:") for e in report.errors)

    def test_neither_dispatched_no_errors(self):
        """No dispatches and no errors (e.g. no leads) → no detection."""
        report = _make_report(
            instantly_report={"total_dispatched": 0},
            heyreach_report={"total_dispatched": 0},
            errors=[],
        )
        result = OperatorOutbound._check_partial_dispatch(report)

        assert result is False

    def test_null_reports_handled(self):
        """None reports (channels not attempted) → no detection."""
        report = _make_report(
            instantly_report=None,
            heyreach_report=None,
            errors=[],
        )
        result = OperatorOutbound._check_partial_dispatch(report)

        assert result is False

    def test_instantly_ok_heyreach_null_no_error(self):
        """Instantly dispatched, HeyReach report is None but no error → not partial."""
        report = _make_report(
            instantly_report={"total_dispatched": 3},
            heyreach_report=None,
            errors=[],
        )
        result = OperatorOutbound._check_partial_dispatch(report)

        assert result is False

    def test_slack_alert_sent(self):
        """When partial dispatch detected, send_warning is called."""
        report = _make_report(
            instantly_report={"total_dispatched": 3},
            heyreach_report={"total_dispatched": 0},
            errors=["HeyReach dispatch error: API timeout"],
        )
        with patch("execution.operator_outbound.send_warning", create=True) as mock_warn:
            # The import is inside the method, so we mock at the module level
            with patch.dict("sys.modules", {"core.alerts": type(sys)("core.alerts")}):
                import sys as _sys
                _sys.modules["core.alerts"].send_warning = mock_warn
                OperatorOutbound._check_partial_dispatch(report)

        mock_warn.assert_called_once()
        call_args = mock_warn.call_args
        assert "Partial Dispatch" in call_args[0][0]
        assert call_args[1]["metadata"]["instantly_dispatched"] == 3

    def test_error_message_includes_counts(self):
        """XS-01 error message includes dispatch counts for debugging."""
        report = _make_report(
            instantly_report={"total_dispatched": 5},
            heyreach_report={"total_dispatched": 0},
            errors=["HeyReach dispatch error: 503"],
        )
        OperatorOutbound._check_partial_dispatch(report)

        xs01_msg = [e for e in report.errors if e.startswith("XS-01:")][0]
        assert "5 email" in xs01_msg
        assert "0 linkedin" in xs01_msg

    def test_unrelated_errors_not_matched(self):
        """Errors that don't match dispatch error patterns don't trigger detection."""
        report = _make_report(
            instantly_report={"total_dispatched": 3},
            heyreach_report={"total_dispatched": 0},
            errors=["Cadence auto-enroll error: timeout"],  # Not a dispatch error
        )
        result = OperatorOutbound._check_partial_dispatch(report)

        assert result is False

    def test_preserves_existing_errors(self):
        """XS-01 error is appended, not replacing existing errors."""
        report = _make_report(
            instantly_report={"total_dispatched": 3},
            heyreach_report={"total_dispatched": 0},
            errors=["HeyReach dispatch error: 503", "Some other warning"],
        )
        OperatorOutbound._check_partial_dispatch(report)

        assert len(report.errors) == 3  # original 2 + XS-01
        assert report.errors[0] == "HeyReach dispatch error: 503"
        assert report.errors[1] == "Some other warning"
        assert report.errors[2].startswith("XS-01:")
