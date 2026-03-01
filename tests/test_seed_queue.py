"""Tests for core/seed_queue.py — dashboard-triggered queue seeding.

Validates:
 - Correct count, required fields, safety flags (synthetic, canary)
 - Non-routable @seed-training.internal domain
 - Tier filtering, persona diversity, template rendering
 - Shadow queue integration (push called)
 - Exclusion filter compatibility (seeded emails pass through)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helper: import exclusion filter from health_app for test_passes_exclusion_filter
# ---------------------------------------------------------------------------

def _stub_exclusion_reasons(
    email_data: Dict[str, Any],
    *,
    now_utc: Optional[datetime] = None,
    tier_filter: Optional[str] = None,
    max_age_hours: Optional[float] = None,
    include_non_dispatchable: bool = False,
) -> List[str]:
    """Minimal re-implementation of health_app._pending_email_exclusion_reasons
    for testing seed email compatibility without importing FastAPI deps."""
    reasons: List[str] = []
    status = str(email_data.get("status") or "pending").strip().lower()
    if status != "pending":
        reasons.append(f"status:{status}")
        return reasons
    if not include_non_dispatchable:
        if bool(email_data.get("_do_not_dispatch")):
            reasons.append("non_dispatchable:_do_not_dispatch")
            return reasons
        if bool(email_data.get("canary_training")):
            reasons.append("non_dispatchable:canary_training")
            return reasons
    return reasons


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSeedQueueGeneration:
    """Test generate_seed_emails() output shape and content."""

    def _generate(self, count: int = 5, tier_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Helper: generate seed emails with shadow_queue.push mocked out."""
        from core.seed_queue import generate_seed_emails
        with patch("core.shadow_queue.push", new=MagicMock()):
            return generate_seed_emails(count=count, tier_filter=tier_filter)

    def test_generate_returns_correct_count(self):
        for n in (1, 3, 5, 10):
            emails = self._generate(count=n)
            assert len(emails) == n, f"Expected {n} emails, got {len(emails)}"

    def test_all_have_required_fields(self):
        required = {
            "email_id", "to", "subject", "body", "status", "source",
            "tier", "recipient_data", "context", "priority", "direction",
        }
        emails = self._generate(count=5)
        for email in emails:
            missing = required - set(email.keys())
            assert not missing, f"Missing fields: {missing} in email {email.get('email_id')}"

    def test_all_synthetic(self):
        emails = self._generate(count=5)
        for email in emails:
            assert email.get("synthetic") is True, f"Email {email['email_id']} not synthetic"

    def test_all_canary(self):
        emails = self._generate(count=5)
        for email in emails:
            assert email.get("canary") is True, f"Email {email['email_id']} not canary"

    def test_no_do_not_dispatch(self):
        emails = self._generate(count=10)
        for email in emails:
            assert "_do_not_dispatch" not in email, (
                f"Email {email['email_id']} should NOT have _do_not_dispatch"
            )

    def test_no_canary_training(self):
        emails = self._generate(count=10)
        for email in emails:
            assert "canary_training" not in email, (
                f"Email {email['email_id']} should NOT have canary_training"
            )

    def test_safe_domain(self):
        emails = self._generate(count=10)
        for email in emails:
            to = email.get("to", "")
            assert to.endswith("@seed-training.internal"), (
                f"Unsafe domain: {to}"
            )

    def test_source_is_dashboard_seed(self):
        emails = self._generate(count=3)
        for email in emails:
            assert email["source"] == "dashboard_seed"

    def test_tier_filter(self):
        for tier in ("tier_1", "tier_2", "tier_3"):
            emails = self._generate(count=5, tier_filter=tier)
            for email in emails:
                assert email["tier"] == tier, (
                    f"Expected tier={tier}, got {email['tier']}"
                )

    def test_signature_present(self):
        emails = self._generate(count=3)
        for email in emails:
            body = email.get("body", "")
            assert "Dani Apgar" in body, f"Missing signature in email {email['email_id']}"
            assert "Reply STOP" in body, f"Missing CAN-SPAM footer in email {email['email_id']}"

    def test_diverse_personas(self):
        """A batch of 5 should have no duplicate recipients (15 personas > 5)."""
        emails = self._generate(count=5)
        recipients = [e["to"] for e in emails]
        assert len(set(recipients)) == 5, (
            f"Expected 5 unique recipients, got {len(set(recipients))}: {recipients}"
        )

    def test_pushes_to_shadow_queue(self):
        mock_push = MagicMock()
        with patch("core.shadow_queue.push", mock_push):
            from core.seed_queue import generate_seed_emails
            generate_seed_emails(count=4)

        assert mock_push.call_count == 4, (
            f"Expected shadow_queue.push called 4 times, got {mock_push.call_count}"
        )

    def test_max_count_capped(self):
        """Count > 20 should be capped to 20."""
        emails = self._generate(count=50)
        assert len(emails) == 20

    def test_passes_exclusion_filter(self):
        """Seeded emails should NOT be excluded by the default pending exclusion filter."""
        emails = self._generate(count=5)
        for email in emails:
            reasons = _stub_exclusion_reasons(
                email,
                now_utc=datetime.now(timezone.utc),
                include_non_dispatchable=False,
            )
            assert reasons == [], (
                f"Email {email['email_id']} excluded with reasons: {reasons}"
            )
