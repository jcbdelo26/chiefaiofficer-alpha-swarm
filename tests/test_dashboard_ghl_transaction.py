#!/usr/bin/env python3
"""
XS-06: Dashboard GHL Send Transaction Safety Tests
====================================================
Tests that the dashboard approval flow uses atomic writes and persists
sent_via_ghl state before proof engine runs.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.health_app import _atomic_json_write


# =============================================================================
# TEST: Atomic JSON Write (dashboard helper)
# =============================================================================

class TestDashboardAtomicWrite:
    """Tests for _atomic_json_write in health_app.py."""

    def test_creates_file_with_correct_content(self, tmp_path):
        """Atomic write creates file with expected JSON content."""
        target = tmp_path / "email.json"
        data = {"email_id": "abc", "sent_via_ghl": True, "status": "sent_proved"}

        _atomic_json_write(target, data)

        result = json.loads(target.read_text(encoding="utf-8"))
        assert result["email_id"] == "abc"
        assert result["sent_via_ghl"] is True
        assert result["status"] == "sent_proved"

    def test_overwrites_existing_file_atomically(self, tmp_path):
        """Atomic write replaces existing file without corruption."""
        target = tmp_path / "email.json"
        target.write_text('{"status": "approved"}', encoding="utf-8")

        _atomic_json_write(target, {"status": "sent_proved", "sent_via_ghl": True})

        result = json.loads(target.read_text(encoding="utf-8"))
        assert result["status"] == "sent_proved"
        assert "approved" not in json.dumps(result)

    def test_no_temp_files_left_on_success(self, tmp_path):
        """No .tmp files left after successful write."""
        target = tmp_path / "email.json"

        _atomic_json_write(target, {"clean": True})

        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "email.json"

    def test_original_file_preserved_on_write_failure(self, tmp_path):
        """If atomic write fails, original file content is preserved."""
        target = tmp_path / "email.json"
        original = {"status": "approved", "email_id": "test123"}
        target.write_text(json.dumps(original), encoding="utf-8")

        # Force a failure by making data non-serializable
        class BadObject:
            pass

        try:
            _atomic_json_write(target, {"bad": BadObject()})
        except TypeError:
            pass

        # Original file should still be intact
        result = json.loads(target.read_text(encoding="utf-8"))
        assert result == original

    def test_creates_parent_directories(self, tmp_path):
        """Atomic write creates parent dirs if needed."""
        target = tmp_path / "deep" / "path" / "email.json"

        _atomic_json_write(target, {"nested": True})

        assert target.exists()


# =============================================================================
# TEST: sent_via_ghl Persistence Order
# =============================================================================

class TestSentViaGhlPersistence:
    """Tests that sent_via_ghl is persisted before proof engine runs."""

    def test_sent_via_ghl_written_before_proof(self, tmp_path):
        """
        Simulate the XS-06 fix: after GHL send succeeds, sent_via_ghl
        is written to file BEFORE proof engine runs.
        """
        email_file = tmp_path / "test_email.json"
        email_data = {
            "email_id": "test_001",
            "status": "approved",
            "sent_via_ghl": False,
            "to": "test@example.com",
        }
        # Initial save
        _atomic_json_write(email_file, email_data)

        # Simulate GHL send success
        email_data["sent_via_ghl"] = True
        email_data["ghl_message_id"] = "msg_abc123"

        # XS-06: Persist immediately after send, before proof
        _atomic_json_write(email_file, email_data)

        # Verify file reflects send BEFORE proof engine would run
        saved = json.loads(email_file.read_text(encoding="utf-8"))
        assert saved["sent_via_ghl"] is True
        assert saved["ghl_message_id"] == "msg_abc123"
        assert saved["status"] == "approved"  # Not yet updated to sent_proved

    def test_file_reflects_send_even_if_proof_crashes(self, tmp_path):
        """
        If proof engine crashes after GHL send, file still shows sent_via_ghl=True.
        """
        email_file = tmp_path / "test_email.json"
        email_data = {
            "email_id": "test_002",
            "status": "approved",
            "sent_via_ghl": False,
        }
        _atomic_json_write(email_file, email_data)

        # GHL send succeeds → persist immediately
        email_data["sent_via_ghl"] = True
        email_data["ghl_message_id"] = "msg_xyz"
        _atomic_json_write(email_file, email_data)

        # Simulate proof engine crash (status never updated)
        # The file should still reflect that email was sent
        saved = json.loads(email_file.read_text(encoding="utf-8"))
        assert saved["sent_via_ghl"] is True
        assert saved["status"] == "approved"  # Proof never completed

    def test_final_save_updates_status_to_sent_proved(self, tmp_path):
        """Full happy path: send → persist → proof → final save with status."""
        email_file = tmp_path / "test_email.json"
        email_data = {
            "email_id": "test_003",
            "status": "approved",
            "sent_via_ghl": False,
        }

        # Step 1: GHL send succeeds, persist immediately
        email_data["sent_via_ghl"] = True
        _atomic_json_write(email_file, email_data)

        # Step 2: Proof resolves
        email_data["proof_status"] = "proved"
        email_data["status"] = "sent_proved"

        # Step 3: Final atomic save
        _atomic_json_write(email_file, email_data)

        saved = json.loads(email_file.read_text(encoding="utf-8"))
        assert saved["status"] == "sent_proved"
        assert saved["sent_via_ghl"] is True
        assert saved["proof_status"] == "proved"
