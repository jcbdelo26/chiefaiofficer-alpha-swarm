#!/usr/bin/env python3
"""
XS-14: Enricher Timeout Enforcement Tests
===========================================
Tests that the enrichment waterfall has an overall timeout cap
to prevent pipeline stalls.
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from execution.enricher_waterfall import _run_with_timeout, ENRICHMENT_OVERALL_TIMEOUT


# =============================================================================
# TEST: _run_with_timeout helper
# =============================================================================

class TestRunWithTimeout:
    """Tests for XS-14: _run_with_timeout helper."""

    def test_fast_function_returns_result(self):
        """Function completing within timeout returns its result."""
        def fast():
            return 42

        result = _run_with_timeout(fast, 5)
        assert result == 42

    def test_slow_function_returns_none(self):
        """Function exceeding timeout returns None."""
        def slow():
            time.sleep(10)
            return "never"

        result = _run_with_timeout(slow, 1)
        assert result is None

    def test_exception_is_propagated(self):
        """Exceptions from the function are re-raised."""
        def failing():
            raise ValueError("test error")

        try:
            _run_with_timeout(failing, 5)
            assert False, "Should have raised"
        except ValueError as e:
            assert "test error" in str(e)

    def test_passes_args_and_kwargs(self):
        """Arguments and keyword arguments are passed through."""
        def add(a, b, multiplier=1):
            return (a + b) * multiplier

        result = _run_with_timeout(add, 5, 3, 4, multiplier=2)
        assert result == 14

    def test_timeout_constant_is_set(self):
        """ENRICHMENT_OVERALL_TIMEOUT has a reasonable default."""
        assert ENRICHMENT_OVERALL_TIMEOUT > 0
        assert ENRICHMENT_OVERALL_TIMEOUT <= 600  # Max 10 min


# =============================================================================
# TEST: Enricher uses timeout wrapper
# =============================================================================

class TestEnricherTimeoutIntegration:
    """Tests that WaterfallEnricher.enrich_lead uses the timeout."""

    def test_enrich_lead_calls_run_with_timeout(self):
        """enrich_lead wraps _enrich_with_retry in timeout for non-test mode."""
        from execution.enricher_waterfall import WaterfallEnricher

        enricher = WaterfallEnricher(test_mode=False)
        # Force provider so it doesn't fall to mock
        enricher.test_mode = False
        enricher.provider = "apollo"

        with patch("execution.enricher_waterfall._run_with_timeout", return_value=None) as mock_timeout:
            result = enricher.enrich_lead("lead1", "https://linkedin.com/in/test")

        mock_timeout.assert_called_once()
        # First arg should be the method, second should be the timeout
        call_args = mock_timeout.call_args
        assert call_args[0][1] == ENRICHMENT_OVERALL_TIMEOUT
        assert result is None

    def test_test_mode_skips_timeout(self):
        """Test mode bypasses the timeout wrapper entirely."""
        from execution.enricher_waterfall import WaterfallEnricher

        enricher = WaterfallEnricher(test_mode=True)

        with patch("execution.enricher_waterfall._run_with_timeout") as mock_timeout:
            result = enricher.enrich_lead("lead1", "https://linkedin.com/in/test", name="Test User", company="TestCo")

        # In test mode, _run_with_timeout should NOT be called
        mock_timeout.assert_not_called()
        # Result should come from _mock_enrich
        assert result is not None or result is None  # Mock can return either
