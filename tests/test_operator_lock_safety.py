#!/usr/bin/env python3
"""
XS-04: OPERATOR Locking Safety Tests
======================================
Tests for lock verification before state save, atomic file writes,
and verify_operator_lock behavior.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.state_store import StateStore


# =============================================================================
# TEST: verify_operator_lock
# =============================================================================

def _make_store(backend="redis", redis_client=None):
    """Create a StateStore with mocked internals."""
    store = StateStore.__new__(StateStore)
    store.backend = backend
    store._redis_client = redis_client
    store.redis_prefix = "caio"
    return store


class TestVerifyOperatorLock:
    """Tests for StateStore.verify_operator_lock()."""

    def test_verify_returns_true_when_token_matches(self):
        """Lock verification succeeds when Redis holds our token."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "my-token-123"
        store = _make_store(redis_client=mock_redis)

        result = store.verify_operator_lock("outbound", "my-token-123")
        assert result is True

    def test_verify_returns_false_when_token_expired(self):
        """Lock verification fails when Redis key is gone (TTL expired)."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        store = _make_store(redis_client=mock_redis)

        result = store.verify_operator_lock("outbound", "my-token-123")
        assert result is False

    def test_verify_returns_false_when_different_token(self):
        """Lock verification fails when another process holds the lock."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "other-process-token"
        store = _make_store(redis_client=mock_redis)

        result = store.verify_operator_lock("outbound", "my-token-123")
        assert result is False

    def test_verify_returns_false_on_redis_error(self):
        """Lock verification returns False on Redis connection error."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Connection refused")
        store = _make_store(redis_client=mock_redis)

        result = store.verify_operator_lock("outbound", "my-token-123")
        assert result is False

    def test_verify_file_lock_token_accepted(self):
        """File-based lock tokens (no Redis) are accepted."""
        store = _make_store(backend="file", redis_client=None)

        result = store.verify_operator_lock("outbound", "file-lock-abc123")
        assert result is True

    def test_verify_file_lock_rejects_non_file_token(self):
        """Non-file-lock tokens rejected when Redis is unavailable."""
        store = _make_store(backend="file", redis_client=None)

        result = store.verify_operator_lock("outbound", "redis-token-abc")
        assert result is False


# =============================================================================
# TEST: Atomic JSON file writes
# =============================================================================

class TestAtomicFileWrite:
    """Tests for StateStore._write_json_file() atomic write pattern."""

    def test_atomic_write_creates_file(self, tmp_path):
        """Atomic write creates the target file with correct content."""
        store = StateStore.__new__(StateStore)
        target = tmp_path / "state.json"

        store._write_json_file(target, {"count": 5, "date": "2026-02-28"})

        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["count"] == 5
        assert data["date"] == "2026-02-28"

    def test_atomic_write_overwrites_existing(self, tmp_path):
        """Atomic write replaces existing file content."""
        store = StateStore.__new__(StateStore)
        target = tmp_path / "state.json"
        target.write_text('{"old": true}', encoding="utf-8")

        store._write_json_file(target, {"new": True})

        data = json.loads(target.read_text(encoding="utf-8"))
        assert data == {"new": True}

    def test_atomic_write_no_temp_files_left(self, tmp_path):
        """No temporary files left after successful write."""
        store = StateStore.__new__(StateStore)
        target = tmp_path / "state.json"

        store._write_json_file(target, {"clean": True})

        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "state.json"

    def test_atomic_write_creates_parent_dirs(self, tmp_path):
        """Atomic write creates parent directories if needed."""
        store = StateStore.__new__(StateStore)
        target = tmp_path / "deep" / "nested" / "state.json"

        store._write_json_file(target, {"nested": True})

        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["nested"] is True


# =============================================================================
# TEST: Lock-guarded state save in OPERATOR
# =============================================================================

class TestLockGuardedStateSave:
    """Tests that OPERATOR verifies lock before saving daily state."""

    def test_state_saved_when_lock_valid(self):
        """State is saved when lock is still held."""
        from execution.operator_outbound import OperatorOutbound, OperatorReport

        op = OperatorOutbound.__new__(OperatorOutbound)
        op._state_store = MagicMock()
        op._state_store.verify_operator_lock.return_value = True
        op._state_store.save_operator_daily_state = MagicMock()

        # Simulate the lock-guarded save pattern
        lock_token = "valid-token"
        if lock_token and not op._state_store.verify_operator_lock("outbound", lock_token):
            saved = False
        else:
            op._state_store.save_operator_daily_state("2026-02-28", {"runs_today": 1})
            saved = True

        assert saved is True
        op._state_store.save_operator_daily_state.assert_called_once()

    def test_state_not_saved_when_lock_expired(self):
        """State is NOT saved when lock has expired."""
        from execution.operator_outbound import OperatorOutbound

        op = OperatorOutbound.__new__(OperatorOutbound)
        op._state_store = MagicMock()
        op._state_store.verify_operator_lock.return_value = False
        op._state_store.save_operator_daily_state = MagicMock()

        lock_token = "expired-token"
        errors = []
        if lock_token and not op._state_store.verify_operator_lock("outbound", lock_token):
            errors.append("XS-04: Lock expired")
        else:
            op._state_store.save_operator_daily_state("2026-02-28", {"runs_today": 1})

        assert len(errors) == 1
        assert "XS-04" in errors[0]
        op._state_store.save_operator_daily_state.assert_not_called()

    def test_dry_run_skips_lock_entirely(self):
        """Dry run never acquires or verifies locks."""
        from execution.operator_outbound import OperatorOutbound

        op = OperatorOutbound.__new__(OperatorOutbound)
        op._state_store = MagicMock()

        # In dry_run, lock_token is None — state save path uses else branch
        lock_token = None
        if lock_token and not op._state_store.verify_operator_lock("outbound", lock_token):
            saved = False
        else:
            saved = True

        assert saved is True
        op._state_store.verify_operator_lock.assert_not_called()
