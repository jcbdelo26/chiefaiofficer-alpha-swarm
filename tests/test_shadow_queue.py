"""Tests for core/shadow_queue.py — dual-write Redis + filesystem shadow email queue.

This module has caused 3 production incidents (empty HoS dashboard due to
prefix mismatches and fallback failures). These tests codify the dual-write/
dual-read contract so regressions are caught before deploy.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from unittest.mock import patch

import pytest


# ── FakeRedis ────────────────────────────────────────────────────

class FakeRedis:
    """Dict-backed Redis stand-in for unit tests."""

    def __init__(self):
        self._store: Dict[str, str] = {}
        self._zsets: Dict[str, Dict[str, float]] = {}

    def ping(self):
        return True

    def get(self, key: str) -> Optional[str]:
        return self._store.get(key)

    def set(self, key: str, value: str):
        self._store[key] = value

    def zadd(self, key: str, mapping: Dict[str, float]):
        if key not in self._zsets:
            self._zsets[key] = {}
        self._zsets[key].update(mapping)

    def zrevrange(self, key: str, start: int, stop: int) -> List[str]:
        zs = self._zsets.get(key, {})
        sorted_members = sorted(zs.keys(), key=lambda m: zs[m], reverse=True)
        return sorted_members[start : stop + 1]

    def zrem(self, key: str, *members: str):
        zs = self._zsets.get(key, {})
        for m in members:
            zs.pop(m, None)

    def scan_iter(self, match: str = "*", count: int = 100):
        import fnmatch
        for key in list(self._store.keys()):
            if fnmatch.fnmatch(key, match):
                yield key

    def delete(self, *keys: str):
        for key in keys:
            self._store.pop(key, None)


class BrokenRedis:
    """Redis client that raises on every operation."""

    def ping(self):
        raise ConnectionError("Redis is down")

    def get(self, key: str):
        raise ConnectionError("Redis is down")

    def set(self, key: str, value: str):
        raise ConnectionError("Redis is down")

    def zadd(self, key: str, mapping: Dict):
        raise ConnectionError("Redis is down")

    def zrevrange(self, key: str, start: int, stop: int):
        raise ConnectionError("Redis is down")

    def zrem(self, key: str, *members: str):
        raise ConnectionError("Redis is down")

    def scan_iter(self, **kw):
        raise ConnectionError("Redis is down")


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_shadow_queue_globals():
    """Reset module-level globals before each test."""
    import core.shadow_queue as sq
    old_client = sq._client
    old_init = sq._init_done
    sq._client = None
    sq._init_done = False
    yield
    sq._client = old_client
    sq._init_done = old_init


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def shadow_dir(tmp_path):
    d = tmp_path / "shadow_emails"
    d.mkdir()
    return d


def _inject_redis(monkeypatch, redis_client):
    """Inject a fake Redis client into the shadow_queue module."""
    import core.shadow_queue as sq
    sq._client = redis_client
    sq._init_done = True


def _sample_email(email_id: str = "test_001", status: str = "pending", **overrides) -> Dict[str, Any]:
    base = {
        "email_id": email_id,
        "to": "andrew@example.com",
        "subject": "Test Subject",
        "body": "Test body content",
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


# ── push() tests ─────────────────────────────────────────────────


def test_push_writes_to_redis(monkeypatch, fake_redis):
    """push() writes to Redis when available."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    email = _sample_email()
    result = sq.push(email)

    assert result is True
    stored = fake_redis.get("caio:test:shadow:email:test_001")
    assert stored is not None
    assert json.loads(stored)["to"] == "andrew@example.com"


def test_push_writes_to_filesystem_when_no_redis(monkeypatch, shadow_dir):
    """push() writes to filesystem when Redis is unavailable."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, None)

    email = _sample_email()
    result = sq.push(email, shadow_dir=shadow_dir)

    assert result is True
    files = list(shadow_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["email_id"] == "test_001"


def test_push_dual_write(monkeypatch, fake_redis, shadow_dir):
    """push() writes to BOTH Redis and filesystem when both available."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    email = _sample_email()
    result = sq.push(email, shadow_dir=shadow_dir)

    assert result is True
    # Redis has it
    assert fake_redis.get("caio:test:shadow:email:test_001") is not None
    # File has it
    assert (shadow_dir / "test_001.json").exists()


def test_push_returns_false_when_both_fail(monkeypatch):
    """push() returns False when both Redis and filesystem fail."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, BrokenRedis())

    email = _sample_email()
    # No shadow_dir means no filesystem write, BrokenRedis means no Redis write
    result = sq.push(email)

    assert result is False


def test_push_pending_adds_to_sorted_set(monkeypatch, fake_redis):
    """push() with status=pending adds to sorted set index."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    email = _sample_email(status="pending")
    sq.push(email)

    index = fake_redis._zsets.get("caio:test:shadow:pending_ids", {})
    assert "test_001" in index


def test_push_non_pending_not_in_sorted_set(monkeypatch, fake_redis):
    """push() with status != pending does NOT add to sorted set index."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    email = _sample_email(status="approved")
    sq.push(email)

    index = fake_redis._zsets.get("caio:test:shadow:pending_ids", {})
    assert "test_001" not in index


# ── list_pending() tests ─────────────────────────────────────────


def test_list_pending_from_redis_sorted_set(monkeypatch, fake_redis):
    """list_pending() returns items from Redis sorted set (newest first)."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    # Push 3 emails with different timestamps
    for i in range(3):
        email = _sample_email(email_id=f"email_{i}", status="pending")
        sq.push(email)
        time.sleep(0.01)  # ensure distinct timestamps

    result = sq.list_pending(limit=10)
    assert len(result) == 3
    # Newest first
    assert result[0]["email_id"] == "email_2"


def test_list_pending_filesystem_fallback(monkeypatch, shadow_dir):
    """list_pending() falls back to filesystem when Redis unavailable."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, None)

    # Write emails directly to filesystem
    for i in range(3):
        email = _sample_email(email_id=f"email_{i}", status="pending")
        sq.push(email, shadow_dir=shadow_dir)

    result = sq.list_pending(limit=10, shadow_dir=shadow_dir)
    assert len(result) == 3


def test_list_pending_rebuilds_index_from_stray_keys(monkeypatch, fake_redis):
    """list_pending() rebuilds index when keys exist but index doesn't (migration)."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    # Directly insert keys WITHOUT index entries (simulates migration)
    email = _sample_email(email_id="stray_001", status="pending")
    fake_redis.set("caio:test:shadow:email:stray_001", json.dumps(email))
    # No zadd — simulates stray key

    result = sq.list_pending(limit=10)
    assert len(result) == 1
    assert result[0]["email_id"] == "stray_001"
    # Index should have been rebuilt
    assert "stray_001" in fake_redis._zsets.get("caio:test:shadow:pending_ids", {})


def test_list_pending_filters_non_pending_from_index(monkeypatch, fake_redis):
    """list_pending() removes non-pending entries from the index."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    # Push as pending, then change status directly in Redis
    email = _sample_email(email_id="changed_001", status="pending")
    sq.push(email)
    # Manually change status in Redis (simulates dashboard approval)
    email["status"] = "approved"
    fake_redis.set("caio:test:shadow:email:changed_001", json.dumps(email))

    result = sq.list_pending(limit=10)
    assert len(result) == 0
    # Should have been removed from index
    assert "changed_001" not in fake_redis._zsets.get("caio:test:shadow:pending_ids", {})


def test_list_pending_returns_empty_when_nothing(monkeypatch, fake_redis):
    """list_pending() returns empty list when no pending emails exist."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    result = sq.list_pending(limit=10)
    assert result == []


# ── update_status() tests ────────────────────────────────────────


def test_update_status_changes_redis_and_filesystem(monkeypatch, fake_redis, shadow_dir):
    """update_status() changes status in both Redis and filesystem."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    email = _sample_email(status="pending")
    sq.push(email, shadow_dir=shadow_dir)

    result = sq.update_status("test_001", "approved", shadow_dir=shadow_dir)
    assert result is not None
    assert result["status"] == "approved"

    # Verify Redis
    redis_data = json.loads(fake_redis.get("caio:test:shadow:email:test_001"))
    assert redis_data["status"] == "approved"

    # Verify filesystem
    file_data = json.loads((shadow_dir / "test_001.json").read_text())
    assert file_data["status"] == "approved"


def test_update_status_removes_from_pending_index(monkeypatch, fake_redis):
    """update_status() removes from pending index when status != pending."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    email = _sample_email(status="pending")
    sq.push(email)
    assert "test_001" in fake_redis._zsets.get("caio:test:shadow:pending_ids", {})

    sq.update_status("test_001", "approved")
    assert "test_001" not in fake_redis._zsets.get("caio:test:shadow:pending_ids", {})


def test_update_status_with_extra_fields(monkeypatch, fake_redis):
    """update_status() merges extra_fields into the email data."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    email = _sample_email(status="pending")
    sq.push(email)

    result = sq.update_status(
        "test_001", "rejected",
        extra_fields={"rejection_reason": "too generic", "rejected_at": "2026-02-27"},
    )
    assert result["rejection_reason"] == "too generic"
    assert result["rejected_at"] == "2026-02-27"


def test_update_status_returns_none_when_not_found(monkeypatch, fake_redis):
    """update_status() returns None when email_id doesn't exist."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    result = sq.update_status("nonexistent", "approved")
    assert result is None


# ── get_email() tests ────────────────────────────────────────────


def test_get_email_from_redis(monkeypatch, fake_redis):
    """get_email() retrieves from Redis first."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    email = _sample_email()
    sq.push(email)

    result = sq.get_email("test_001")
    assert result is not None
    assert result["to"] == "andrew@example.com"


def test_get_email_filesystem_fallback(monkeypatch, shadow_dir):
    """get_email() falls back to filesystem when Redis unavailable."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, None)

    email = _sample_email()
    sq.push(email, shadow_dir=shadow_dir)

    result = sq.get_email("test_001", shadow_dir=shadow_dir)
    assert result is not None
    assert result["email_id"] == "test_001"


def test_get_email_returns_none_when_not_found(monkeypatch, fake_redis):
    """get_email() returns None when email doesn't exist."""
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:test")

    result = sq.get_email("nonexistent")
    assert result is None


# ── _prefix() tests ──────────────────────────────────────────────


def test_prefix_uses_context_redis_prefix(monkeypatch):
    """_prefix() uses CONTEXT_REDIS_PREFIX first (architectural law)."""
    import core.shadow_queue as sq
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:production:context")
    monkeypatch.setenv("STATE_REDIS_PREFIX", "different_prefix")

    assert sq._prefix() == "caio:production:context"


def test_prefix_falls_back_to_state_redis_prefix(monkeypatch):
    """_prefix() falls back to STATE_REDIS_PREFIX when CONTEXT is not set."""
    import core.shadow_queue as sq
    monkeypatch.delenv("CONTEXT_REDIS_PREFIX", raising=False)
    monkeypatch.setenv("STATE_REDIS_PREFIX", "caio_state")

    assert sq._prefix() == "caio_state"


def test_prefix_falls_back_to_caio(monkeypatch):
    """_prefix() falls back to 'caio' when no env vars set."""
    import core.shadow_queue as sq
    monkeypatch.delenv("CONTEXT_REDIS_PREFIX", raising=False)
    monkeypatch.delenv("STATE_REDIS_PREFIX", raising=False)

    assert sq._prefix() == "caio"


# ── Regression: Railway dashboard key pattern ────────────────────


def test_railway_dashboard_key_pattern(monkeypatch, fake_redis):
    """
    Regression: prefix key pattern must match what the Railway dashboard reads.

    Railway sets CONTEXT_REDIS_PREFIX=caio:production:context. The dashboard
    API reads keys matching {prefix}:shadow:email:*. If the local pipeline
    uses a different prefix, the dashboard shows an empty queue.
    """
    import core.shadow_queue as sq
    _inject_redis(monkeypatch, fake_redis)
    monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:production:context")

    email = _sample_email()
    sq.push(email)

    # Verify the exact key pattern the dashboard expects
    expected_key = "caio:production:context:shadow:email:test_001"
    assert fake_redis.get(expected_key) is not None

    # Verify the pending index key
    expected_index = "caio:production:context:shadow:pending_ids"
    assert "test_001" in fake_redis._zsets.get(expected_index, {})
