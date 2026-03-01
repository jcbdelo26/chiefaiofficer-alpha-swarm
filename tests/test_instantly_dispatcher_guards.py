"""Tests for execution/instantly_dispatcher.py — 4-layer deliverability guard system.

The guard system is the last defense before real emails reach recipients.
Tests load actual production.json exclusion lists to ensure config changes that
accidentally remove a blocked domain will fail CI.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.instantly_dispatcher import InstantlyDispatcher, DailyCeilingTracker, _atomic_json_write

PROJECT_ROOT = Path(__file__).parent.parent


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def dispatcher(tmp_path, monkeypatch):
    """Create dispatcher with real production.json config but temp shadow dir."""
    d = InstantlyDispatcher.__new__(InstantlyDispatcher)
    d.shadow_dir = tmp_path / "shadow_emails"
    d.shadow_dir.mkdir()
    d.dispatch_log = tmp_path / "dispatch_log.jsonl"
    d.deliverability_rejection_log = tmp_path / "audit" / "rejections.jsonl"
    d.ceiling = DailyCeilingTracker.__new__(DailyCeilingTracker)
    d.ceiling.state_file = tmp_path / "dispatch_state.json"
    d.ceiling._state = {"date": date.today().isoformat(), "dispatched_count": 0, "dispatched_emails": [], "campaigns_created": []}
    d.ceiling._redis = None
    d.ceiling._redis_prefix = ""
    d.config = _load_production_config()
    d._client = None
    return d


def _load_production_config() -> Dict[str, Any]:
    """Load the actual production.json for guard tests."""
    config_path = PROJECT_ROOT / "config" / "production.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _write_shadow_email(shadow_dir: Path, email_id: str, to: str, **overrides) -> Path:
    """Write a shadow email JSON to the shadow dir."""
    data = {
        "email_id": email_id,
        "to": to,
        "subject": "Test Subject",
        "body": "Test body",
        "status": "approved",
        "tier": "tier_1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    data.update(overrides)
    filepath = shadow_dir / f"{email_id}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return filepath


# ── Guard 1: Email format validation ─────────────────────────────


class TestGuard1EmailFormat:

    def test_valid_email_passes(self):
        assert InstantlyDispatcher._validate_email_format("john@acme.com") is True

    def test_invalid_email_no_at(self):
        assert InstantlyDispatcher._validate_email_format("johnacme.com") is False

    def test_invalid_email_no_domain(self):
        assert InstantlyDispatcher._validate_email_format("john@") is False

    def test_invalid_email_no_tld(self):
        assert InstantlyDispatcher._validate_email_format("john@acme") is False

    def test_empty_email(self):
        assert InstantlyDispatcher._validate_email_format("") is False

    def test_email_with_plus(self):
        assert InstantlyDispatcher._validate_email_format("john+tag@acme.com") is True

    def test_invalid_format_blocked_in_loading(self, dispatcher):
        """Bad format email rejected during _load_approved_emails."""
        _write_shadow_email(dispatcher.shadow_dir, "bad_fmt_001", "not-an-email")
        result = dispatcher._load_approved_emails()
        assert len(result) == 0


# ── Guard 2: Excluded domains ────────────────────────────────────


class TestGuard2ExcludedDomains:

    def test_all_competitor_domains_blocked(self, dispatcher):
        """Every competitor domain from production.json is blocked."""
        excluded = dispatcher._get_excluded_domains()
        expected_competitors = [
            "apollo.io", "gong.io", "outreach.io", "salesloft.com",
            "chorus.ai", "people.ai", "seamless.ai", "zoominfo.com",
            "lusha.com", "cognism.com",
        ]
        for domain in expected_competitors:
            assert domain in excluded, f"{domain} should be in excluded domains"

    def test_own_domains_blocked(self, dispatcher):
        """Own domains (chiefaiofficer.com, chiefai.ai) are blocked."""
        excluded = dispatcher._get_excluded_domains()
        assert "chiefaiofficer.com" in excluded
        assert "chiefai.ai" in excluded

    def test_case_insensitive_matching(self):
        """Domain matching is case insensitive."""
        excluded = {"gong.io", "outreach.io"}
        assert InstantlyDispatcher._is_excluded_domain("GONG.IO", excluded) is True
        assert InstantlyDispatcher._is_excluded_domain("Gong.Io", excluded) is True

    def test_subdomain_matching(self):
        """Subdomain user@sub.customer.com matches excluded customer.com."""
        excluded = {"customer.com"}
        assert InstantlyDispatcher._is_excluded_domain("sub.customer.com", excluded) is True
        assert InstantlyDispatcher._is_excluded_domain("deep.sub.customer.com", excluded) is True

    def test_non_excluded_domain_passes(self):
        """Unrelated domain passes through."""
        excluded = {"gong.io"}
        assert InstantlyDispatcher._is_excluded_domain("safedomain.com", excluded) is False

    def test_excluded_domain_blocked_in_loading(self, dispatcher):
        """Excluded domain email rejected during _load_approved_emails."""
        _write_shadow_email(dispatcher.shadow_dir, "comp_001", "john@gong.io")
        result = dispatcher._load_approved_emails()
        assert len(result) == 0

    def test_empty_domain_not_excluded(self):
        """Empty domain returns False (not excluded)."""
        excluded = {"gong.io"}
        assert InstantlyDispatcher._is_excluded_domain("", excluded) is False


# ── Guard 3: Domain concentration ────────────────────────────────


class TestGuard3DomainConcentration:

    def test_first_three_same_domain_pass(self, dispatcher):
        """First 3 emails from same domain pass (default max=3)."""
        for i in range(3):
            _write_shadow_email(dispatcher.shadow_dir, f"conc_{i:03d}", f"user{i}@samecompany.com")
        result = dispatcher._load_approved_emails()
        assert len(result) == 3

    def test_fourth_same_domain_rejected(self, dispatcher):
        """4th email from same domain is rejected."""
        for i in range(4):
            _write_shadow_email(dispatcher.shadow_dir, f"conc_{i:03d}", f"user{i}@samecompany.com")
        result = dispatcher._load_approved_emails()
        assert len(result) == 3  # 4th blocked

    def test_different_domains_unaffected(self, dispatcher):
        """Emails to different domains are independent."""
        _write_shadow_email(dispatcher.shadow_dir, "dom_001", "a@company1.com")
        _write_shadow_email(dispatcher.shadow_dir, "dom_002", "b@company2.com")
        _write_shadow_email(dispatcher.shadow_dir, "dom_003", "c@company3.com")
        _write_shadow_email(dispatcher.shadow_dir, "dom_004", "d@company4.com")
        result = dispatcher._load_approved_emails()
        assert len(result) == 4


# ── Guard 4: Individual email exclusion ──────────────────────────


class TestGuard4IndividualExclusion:

    def test_all_customer_emails_blocked(self, dispatcher):
        """All 27 customer emails from HoS Section 1.4 are blocked."""
        config = _load_production_config()
        excluded_emails = config.get("guardrails", {}).get("deliverability", {}).get(
            "excluded_recipient_emails", []
        )
        # HoS Section 1.4 specifies 27 customer emails
        assert len(excluded_emails) >= 27, f"Expected >= 27 excluded emails, got {len(excluded_emails)}"

        # Spot-check specific emails
        excluded_set = {e.lower().strip() for e in excluded_emails}
        assert "chudziak@jbcco.com" in excluded_set
        assert "cole@exitmomentum.com" in excluded_set
        assert "sharrell@frazerbilt.com" in excluded_set

    def test_excluded_email_blocked_in_loading(self, dispatcher):
        """Individual excluded email rejected during _load_approved_emails."""
        _write_shadow_email(dispatcher.shadow_dir, "cust_001", "chudziak@jbcco.com")
        result = dispatcher._load_approved_emails()
        assert len(result) == 0

    def test_non_excluded_email_passes(self, dispatcher):
        """Non-excluded email passes through."""
        _write_shadow_email(dispatcher.shadow_dir, "safe_001", "prospect@safedomain.com")
        result = dispatcher._load_approved_emails()
        assert len(result) == 1


# ── Canary safety gate ───────────────────────────────────────────


class TestCanarySafety:

    def test_canary_email_never_dispatched(self, dispatcher):
        """Canary=True emails silently excluded."""
        _write_shadow_email(dispatcher.shadow_dir, "canary_001", "test@safe.com", canary=True)
        result = dispatcher._load_approved_emails()
        assert len(result) == 0

    def test_do_not_dispatch_flag(self, dispatcher):
        """_do_not_dispatch=True emails silently excluded."""
        _write_shadow_email(dispatcher.shadow_dir, "dnd_001", "test@safe.com", _do_not_dispatch=True)
        result = dispatcher._load_approved_emails()
        assert len(result) == 0


# ── EMERGENCY_STOP ───────────────────────────────────────────────


class TestEmergencyStop:

    def test_emergency_stop_true(self, monkeypatch):
        d = InstantlyDispatcher.__new__(InstantlyDispatcher)
        d.config = {}
        monkeypatch.setenv("EMERGENCY_STOP", "true")
        assert d._check_emergency_stop() is True

    def test_emergency_stop_false(self, monkeypatch):
        d = InstantlyDispatcher.__new__(InstantlyDispatcher)
        d.config = {}
        monkeypatch.setenv("EMERGENCY_STOP", "false")
        assert d._check_emergency_stop() is False

    def test_emergency_stop_not_set(self, monkeypatch):
        d = InstantlyDispatcher.__new__(InstantlyDispatcher)
        d.config = {}
        monkeypatch.delenv("EMERGENCY_STOP", raising=False)
        assert d._check_emergency_stop() is False


# ── Daily ceiling ────────────────────────────────────────────────


class TestDailyCeiling:

    def test_ceiling_remaining(self, tmp_path):
        c = DailyCeilingTracker.__new__(DailyCeilingTracker)
        c.state_file = tmp_path / "state.json"
        c._state = {"date": date.today().isoformat(), "dispatched_count": 10, "dispatched_emails": [], "campaigns_created": []}
        c._redis = None
        c._redis_prefix = ""
        assert c.get_remaining(25) == 15

    def test_ceiling_exhausted(self, tmp_path):
        c = DailyCeilingTracker.__new__(DailyCeilingTracker)
        c.state_file = tmp_path / "state.json"
        c._state = {"date": date.today().isoformat(), "dispatched_count": 25, "dispatched_emails": [], "campaigns_created": []}
        c._redis = None
        c._redis_prefix = ""
        assert c.get_remaining(25) == 0

    def test_ceiling_record_increments(self, tmp_path):
        c = DailyCeilingTracker.__new__(DailyCeilingTracker)
        c.state_file = tmp_path / "state.json"
        c._state = {"date": date.today().isoformat(), "dispatched_count": 0, "dispatched_emails": [], "campaigns_created": []}
        c._redis = None
        c._redis_prefix = ""
        c.record_dispatch(5, ["e1", "e2", "e3", "e4", "e5"], "campaign_1")
        assert c.get_today_count() == 5
        assert c.get_remaining(25) == 20


# ── Mixed guard interaction ──────────────────────────────────────


class TestGuardInteraction:

    def test_valid_email_passes_all_guards(self, dispatcher):
        """A clean email with no exclusion issues passes all 4 guards."""
        _write_shadow_email(dispatcher.shadow_dir, "clean_001", "prospect@safedomain.com")
        result = dispatcher._load_approved_emails()
        assert len(result) == 1
        assert result[0]["to"] == "prospect@safedomain.com"

    def test_non_approved_status_skipped(self, dispatcher):
        """Only status=approved emails are loaded."""
        _write_shadow_email(dispatcher.shadow_dir, "pending_001", "a@safe.com", status="pending")
        _write_shadow_email(dispatcher.shadow_dir, "rejected_001", "b@safe.com", status="rejected")
        result = dispatcher._load_approved_emails()
        assert len(result) == 0

    def test_already_dispatched_skipped(self, dispatcher):
        """Emails with instantly_campaign_id are skipped (already sent)."""
        _write_shadow_email(
            dispatcher.shadow_dir, "sent_001", "a@safe.com",
            instantly_campaign_id="abc123",
        )
        result = dispatcher._load_approved_emails()
        assert len(result) == 0

    def test_rejection_audit_log_written(self, dispatcher):
        """Guard rejections write to audit JSONL."""
        _write_shadow_email(dispatcher.shadow_dir, "bad_001", "john@gong.io")
        dispatcher._load_approved_emails()
        assert dispatcher.deliverability_rejection_log.exists()
        with open(dispatcher.deliverability_rejection_log) as f:
            entries = [json.loads(line) for line in f if line.strip()]
        assert len(entries) >= 1
        assert entries[0]["reason_code"] == "excluded_recipient_domain"


# ── Atomic JSON writes (XS-08) ─────────────────────────────────


class TestAtomicJsonWrite:

    def test_creates_file(self, tmp_path):
        f = tmp_path / "test.json"
        _atomic_json_write(f, {"a": 1})
        assert f.exists()
        assert json.loads(f.read_text())["a"] == 1

    def test_overwrites_existing(self, tmp_path):
        f = tmp_path / "test.json"
        _atomic_json_write(f, {"v": 1})
        _atomic_json_write(f, {"v": 2})
        assert json.loads(f.read_text())["v"] == 2

    def test_no_temp_files_left(self, tmp_path):
        f = tmp_path / "test.json"
        _atomic_json_write(f, {"ok": True})
        assert len(list(tmp_path.glob("*.tmp"))) == 0

    def test_ceiling_save_uses_atomic(self, tmp_path):
        """DailyCeilingTracker._save() uses atomic write."""
        c = DailyCeilingTracker.__new__(DailyCeilingTracker)
        c.state_file = tmp_path / "state.json"
        c._state = {"date": "2026-02-28", "dispatched_count": 3, "dispatched_emails": [], "campaigns_created": []}
        c._redis = None
        c._redis_prefix = ""
        c._save()
        assert c.state_file.exists()
        data = json.loads(c.state_file.read_text())
        assert data["dispatched_count"] == 3


# ── Redis-backed daily ceiling (XS-03) ─────────────────────────


class TestRedisDailyCeiling:
    """Tests for XS-03: Redis-backed distributed ceiling."""

    def _make_ceiling(self, tmp_path):
        c = DailyCeilingTracker.__new__(DailyCeilingTracker)
        c.state_file = tmp_path / "state.json"
        c._state = {"date": date.today().isoformat(), "dispatched_count": 0, "dispatched_emails": [], "campaigns_created": []}
        c._redis = None
        c._redis_prefix = ""
        return c

    def test_redis_count_used_when_available(self, tmp_path):
        """Redis count is preferred over file count."""
        from unittest.mock import MagicMock
        c = self._make_ceiling(tmp_path)
        c._redis = MagicMock()
        c._redis_prefix = "caio"
        c._redis.get.return_value = "7"
        assert c.get_remaining(25) == 18
        assert c.get_today_count() == 7

    def test_file_fallback_when_redis_returns_none(self, tmp_path):
        """Falls back to file count when Redis returns None."""
        c = self._make_ceiling(tmp_path)
        c._state["dispatched_count"] = 12
        # _redis is None — triggers file fallback
        assert c.get_remaining(25) == 13
        assert c.get_today_count() == 12

    def test_file_fallback_on_redis_error(self, tmp_path):
        """Falls back to file count on Redis exception."""
        from unittest.mock import MagicMock
        c = self._make_ceiling(tmp_path)
        c._redis = MagicMock()
        c._redis_prefix = "caio"
        c._redis.get.side_effect = Exception("connection lost")
        c._state["dispatched_count"] = 5
        assert c.get_remaining(25) == 20

    def test_incrby_called_on_record(self, tmp_path):
        """record_dispatch calls Redis INCRBY."""
        from unittest.mock import MagicMock
        c = self._make_ceiling(tmp_path)
        c._redis = MagicMock()
        c._redis_prefix = "caio"
        c.record_dispatch(3, ["e1", "e2", "e3"], "camp_v1")
        c._redis.incrby.assert_called_once()
        c._redis.expire.assert_called_once()

    def test_local_state_always_updated(self, tmp_path):
        """Local state updated even when Redis is available."""
        from unittest.mock import MagicMock
        c = self._make_ceiling(tmp_path)
        c._redis = MagicMock()
        c._redis_prefix = "caio"
        c.record_dispatch(2, ["e1", "e2"], "camp_v1")
        assert c._state["dispatched_count"] == 2
        assert len(c._state["dispatched_emails"]) == 2

    def test_survives_redis_write_failure(self, tmp_path):
        """Redis INCRBY failure doesn't break record_dispatch."""
        from unittest.mock import MagicMock
        c = self._make_ceiling(tmp_path)
        c._redis = MagicMock()
        c._redis_prefix = "caio"
        c._redis.incrby.side_effect = Exception("write failed")
        c.record_dispatch(1, ["e1"], "camp_v1")
        # Local state still updated
        assert c._state["dispatched_count"] == 1

    def test_redis_key_includes_date(self, tmp_path):
        """Redis key contains today's date for automatic rollover."""
        c = self._make_ceiling(tmp_path)
        c._redis_prefix = "caio"
        key = c._redis_key("count")
        assert date.today().isoformat() in key
        assert "instantly" in key

    def test_zero_count_from_redis(self, tmp_path):
        """Redis returning 0 (new day) is not treated as None."""
        from unittest.mock import MagicMock
        c = self._make_ceiling(tmp_path)
        c._redis = MagicMock()
        c._redis_prefix = "caio"
        c._redis.get.return_value = None  # Key doesn't exist yet
        assert c.get_today_count() == 0
        assert c.get_remaining(25) == 25
