#!/usr/bin/env python3
"""
Cross-environment bridge regression tests.

Validates the LOCAL <-> RAILWAY data flow that caused 3 production incidents
(documented in CLAUDE.md pitfall #1). Tests the full lifecycle:
  push (local) -> list_pending (Railway) -> approve -> verify state change

All tests use FakeRedis to simulate the shared Upstash Redis instance
and verify that both environments use consistent key patterns.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest


# ── FakeRedis (reused from test_shadow_queue.py pattern) ─────────


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
    """Redis client that raises on every operation — simulates Redis outage."""

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
def shared_redis():
    """Simulates the shared Upstash Redis instance used by both envs."""
    return FakeRedis()


@pytest.fixture
def local_shadow_dir(tmp_path):
    """Local dev filesystem shadow directory (not visible on Railway)."""
    d = tmp_path / "local_shadow_emails"
    d.mkdir()
    return d


@pytest.fixture
def railway_shadow_dir(tmp_path):
    """Railway container filesystem (separate from local)."""
    d = tmp_path / "railway_shadow_emails"
    d.mkdir()
    return d


def _inject_redis(redis_client):
    """Inject a Redis client into the shadow_queue module."""
    import core.shadow_queue as sq
    sq._client = redis_client
    sq._init_done = True


def _sample_email(email_id: str = "bridge_001", **overrides) -> Dict[str, Any]:
    base = {
        "email_id": email_id,
        "to": "prospect@example.com",
        "from": "chris.d@chiefaiofficerai.com",
        "subject": "Quick question about AI strategy",
        "body": "Hi there, wanted to reach out about...",
        "status": "pending",
        "tier": "tier_1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


# =====================================================================
# SCENARIO 1: Normal cross-env round-trip (THE critical path)
# =====================================================================


class TestCrossEnvRoundTrip:
    """The full lifecycle: local push -> Railway read -> approve -> verify."""

    def test_local_push_visible_on_railway_via_redis(self, monkeypatch, shared_redis, local_shadow_dir):
        """LOCAL push is visible to Railway dashboard via shared Redis."""
        import core.shadow_queue as sq
        _inject_redis(shared_redis)
        monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:production:context")

        # Step 1: Local pipeline pushes email (writes to Redis + local disk)
        email = _sample_email()
        result = sq.push(email, shadow_dir=local_shadow_dir)
        assert result is True

        # Step 2: Railway dashboard reads from same Redis (no local disk)
        pending = sq.list_pending(limit=20)
        assert len(pending) == 1
        assert pending[0]["email_id"] == "bridge_001"
        assert pending[0]["to"] == "prospect@example.com"

    def test_full_approve_lifecycle(self, monkeypatch, shared_redis, local_shadow_dir):
        """Push -> list -> approve -> verify no longer pending."""
        import core.shadow_queue as sq
        _inject_redis(shared_redis)
        monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:production:context")

        # Local push
        email = _sample_email()
        sq.push(email, shadow_dir=local_shadow_dir)

        # Railway reads pending
        pending = sq.list_pending(limit=20)
        assert len(pending) == 1

        # Railway approves (updates status in Redis)
        updated = sq.update_status("bridge_001", "approved", extra_fields={
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": "hos",
        })
        assert updated is not None
        assert updated["status"] == "approved"

        # Verify no longer in pending list
        pending_after = sq.list_pending(limit=20)
        assert len(pending_after) == 0

        # Verify approved data is retrievable
        retrieved = sq.get_email("bridge_001")
        assert retrieved["status"] == "approved"
        assert retrieved["approved_by"] == "hos"

    def test_multi_email_batch_round_trip(self, monkeypatch, shared_redis):
        """Multiple emails pushed locally are all visible on Railway."""
        import core.shadow_queue as sq
        _inject_redis(shared_redis)
        monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:production:context")

        # Local pushes 5 emails
        for i in range(5):
            email = _sample_email(email_id=f"batch_{i}", tier=f"tier_{(i % 3) + 1}")
            sq.push(email)
            time.sleep(0.01)

        # Railway reads all 5
        pending = sq.list_pending(limit=20)
        assert len(pending) == 5
        ids = {e["email_id"] for e in pending}
        assert ids == {"batch_0", "batch_1", "batch_2", "batch_3", "batch_4"}


# =====================================================================
# SCENARIO 2: Prefix consistency (ROOT CAUSE of 3 incidents)
# =====================================================================


class TestPrefixConsistency:
    """CONTEXT_REDIS_PREFIX must be used consistently across environments."""

    def test_context_prefix_is_canonical(self, monkeypatch, shared_redis):
        """Both envs must use CONTEXT_REDIS_PREFIX for key generation."""
        import core.shadow_queue as sq
        _inject_redis(shared_redis)
        monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:production:context")
        monkeypatch.setenv("STATE_REDIS_PREFIX", "different_value")

        email = _sample_email()
        sq.push(email)

        # Key MUST use CONTEXT_REDIS_PREFIX, not STATE_REDIS_PREFIX
        expected_key = "caio:production:context:shadow:email:bridge_001"
        assert shared_redis.get(expected_key) is not None

        wrong_key = "different_value:shadow:email:bridge_001"
        assert shared_redis.get(wrong_key) is None

    def test_state_prefix_mismatch_causes_empty_dashboard(self, monkeypatch, shared_redis):
        """Regression: if writer uses different prefix than reader, dashboard is empty."""
        import core.shadow_queue as sq
        _inject_redis(shared_redis)

        # Writer (local) uses prefix "local_prefix"
        monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "local_prefix")
        email = _sample_email()
        sq.push(email)

        # Reader (Railway) uses prefix "railway_prefix" — MISMATCH
        monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "railway_prefix")
        pending = sq.list_pending(limit=20)

        # Dashboard shows empty — this is the bug that caused 3 incidents
        assert len(pending) == 0

    def test_matching_prefix_works(self, monkeypatch, shared_redis):
        """When both envs use same CONTEXT_REDIS_PREFIX, data flows correctly."""
        import core.shadow_queue as sq
        _inject_redis(shared_redis)

        canonical = "caio:production:context"

        # Writer
        monkeypatch.setenv("CONTEXT_REDIS_PREFIX", canonical)
        email = _sample_email()
        sq.push(email)

        # Reader (same prefix)
        pending = sq.list_pending(limit=20)
        assert len(pending) == 1

    def test_index_key_also_uses_context_prefix(self, monkeypatch, shared_redis):
        """The sorted set index key must also use CONTEXT_REDIS_PREFIX."""
        import core.shadow_queue as sq
        _inject_redis(shared_redis)
        monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:production:context")

        email = _sample_email()
        sq.push(email)

        expected_index = "caio:production:context:shadow:pending_ids"
        assert expected_index in shared_redis._zsets
        assert "bridge_001" in shared_redis._zsets[expected_index]


# =====================================================================
# SCENARIO 3: Redis failure with filesystem fallback
# =====================================================================


class TestRedisFallback:
    """When Redis is down, filesystem fallback must work for local operations."""

    def test_push_falls_back_to_filesystem(self, monkeypatch, local_shadow_dir):
        """When Redis is down, push still works via filesystem."""
        import core.shadow_queue as sq
        _inject_redis(BrokenRedis())

        email = _sample_email()
        result = sq.push(email, shadow_dir=local_shadow_dir)

        assert result is True
        files = list(local_shadow_dir.glob("*.json"))
        assert len(files) == 1

    def test_filesystem_emails_not_visible_on_railway(self, monkeypatch, local_shadow_dir, railway_shadow_dir):
        """CRITICAL: filesystem writes on local are NOT visible on Railway.
        This test documents the architectural limitation that caused incidents."""
        import core.shadow_queue as sq
        _inject_redis(None)

        # Local writes to local filesystem
        email = _sample_email()
        sq.push(email, shadow_dir=local_shadow_dir)

        # Local can read its own files
        local_pending = sq.list_pending(limit=20, shadow_dir=local_shadow_dir)
        assert len(local_pending) == 1

        # Railway cannot see local files (different filesystem)
        railway_pending = sq.list_pending(limit=20, shadow_dir=railway_shadow_dir)
        assert len(railway_pending) == 0

    def test_redis_recovery_restores_cross_env_visibility(self, monkeypatch, shared_redis, local_shadow_dir):
        """After Redis recovers, new pushes are visible cross-env again."""
        import core.shadow_queue as sq
        monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:production:context")

        # Phase 1: Redis down — filesystem only
        _inject_redis(None)
        email1 = _sample_email(email_id="offline_001")
        sq.push(email1, shadow_dir=local_shadow_dir)

        # Phase 2: Redis recovers
        _inject_redis(shared_redis)
        email2 = _sample_email(email_id="online_001")
        sq.push(email2)

        # Only the post-recovery email is visible via Redis
        pending = sq.list_pending(limit=20)
        assert len(pending) == 1
        assert pending[0]["email_id"] == "online_001"


# =====================================================================
# SCENARIO 4: Status transitions across environments
# =====================================================================


class TestCrossEnvStatusTransitions:
    """Status changes on Railway must be visible from both environments."""

    def test_rejection_removes_from_pending(self, monkeypatch, shared_redis):
        """Railway rejection removes email from pending list."""
        import core.shadow_queue as sq
        _inject_redis(shared_redis)
        monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:production:context")

        email = _sample_email()
        sq.push(email)
        assert len(sq.list_pending(limit=20)) == 1

        sq.update_status("bridge_001", "rejected", extra_fields={
            "rejection_tags": ["too_generic", "weak_opener"],
            "rejection_reason": "Subject line needs personalization",
        })

        assert len(sq.list_pending(limit=20)) == 0
        rejected = sq.get_email("bridge_001")
        assert rejected["status"] == "rejected"
        assert "too_generic" in rejected["rejection_tags"]

    def test_approve_reject_mixed_batch(self, monkeypatch, shared_redis):
        """Mixed approvals and rejections in same batch work correctly."""
        import core.shadow_queue as sq
        _inject_redis(shared_redis)
        monkeypatch.setenv("CONTEXT_REDIS_PREFIX", "caio:production:context")

        # Push 4 emails
        for i in range(4):
            sq.push(_sample_email(email_id=f"mix_{i}"))
            time.sleep(0.01)

        assert len(sq.list_pending(limit=20)) == 4

        # Approve 2, reject 2
        sq.update_status("mix_0", "approved")
        sq.update_status("mix_1", "rejected")
        sq.update_status("mix_2", "approved")
        sq.update_status("mix_3", "rejected")

        # Nothing pending
        assert len(sq.list_pending(limit=20)) == 0

        # All retrievable with correct status
        assert sq.get_email("mix_0")["status"] == "approved"
        assert sq.get_email("mix_1")["status"] == "rejected"
        assert sq.get_email("mix_2")["status"] == "approved"
        assert sq.get_email("mix_3")["status"] == "rejected"
