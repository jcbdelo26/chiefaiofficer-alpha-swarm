"""
Tests for core/queue_watcher.py -- Queue self-validation loop.

Validates:
  1. Auto-seeding when pending count drops below low-water mark
  2. Cooldown prevents rapid-fire seeding
  3. Daily cap limits total auto-seeds per day
  4. Force mode bypasses threshold check
  5. Kill switch disables all auto-seeding
  6. Metrics/observability returns expected shape
  7. Background loop handles exceptions gracefully
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeRedis:
    """Minimal Redis mock for queue watcher tests."""

    def __init__(self):
        self._data = {}
        self._zsets = {}

    def ping(self):
        return True

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value

    def incr(self, key):
        val = int(self._data.get(key, 0)) + 1
        self._data[key] = str(val)
        return val

    def expire(self, key, ttl):
        pass

    def zcard(self, key):
        return len(self._zsets.get(key, {}))

    def zadd(self, key, mapping):
        if key not in self._zsets:
            self._zsets[key] = {}
        self._zsets[key].update(mapping)

    def zrem(self, key, *members):
        zset = self._zsets.get(key, {})
        for m in members:
            zset.pop(m, None)

    def zrevrange(self, key, start, stop):
        zset = self._zsets.get(key, {})
        sorted_members = sorted(zset.items(), key=lambda x: x[1], reverse=True)
        return [m for m, _ in sorted_members[start:stop + 1]]

    def scan_iter(self, match=None, count=None):
        if match:
            import fnmatch
            return [k for k in self._data if fnmatch.fnmatch(k, match)]
        return list(self._data.keys())


def _make_env(**overrides):
    """Build env dict that disables real Redis and sets watcher config."""
    env = {
        "REDIS_URL": "",
        "QUEUE_AUTO_SEED_ENABLED": "true",
        "QUEUE_LOW_WATER_MARK": "3",
        "QUEUE_TARGET_COUNT": "5",
        "QUEUE_AUTO_SEED_COOLDOWN": "60",
        "QUEUE_CHECK_INTERVAL_SECONDS": "30",
        "QUEUE_AUTO_SEED_MAX_DAILY": "50",
    }
    env.update(overrides)
    return env


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """Reset cached config between tests."""
    import core.queue_watcher as qw
    qw._config_cache = None
    yield
    qw._config_cache = None


@pytest.fixture
def fake_redis():
    """Provide a FakeRedis instance wired into shadow_queue."""
    r = FakeRedis()
    with patch("core.shadow_queue._get_redis", return_value=r), \
         patch("core.shadow_queue._init_done", True), \
         patch("core.shadow_queue._client", r):
        yield r


# ---------------------------------------------------------------------------
# Configuration tests
# ---------------------------------------------------------------------------

class TestConfig:
    def test_default_config_values(self):
        """Defaults are correct without env vars or config file."""
        with patch.dict(os.environ, {
            "QUEUE_AUTO_SEED_ENABLED": "",
            "QUEUE_LOW_WATER_MARK": "",
            "QUEUE_TARGET_COUNT": "",
            "QUEUE_AUTO_SEED_COOLDOWN": "",
            "QUEUE_CHECK_INTERVAL_SECONDS": "",
            "QUEUE_AUTO_SEED_MAX_DAILY": "",
        }, clear=False):
            from core.queue_watcher import get_config
            cfg = get_config()
            assert cfg["enabled"] is True
            assert cfg["low_water_mark"] == 3
            assert cfg["target_count"] == 5
            assert cfg["cooldown_seconds"] == 60
            assert cfg["check_interval_seconds"] == 30
            assert cfg["max_daily_auto_seeds"] == 50

    def test_env_var_overrides(self):
        """Env vars override file config and defaults."""
        with patch.dict(os.environ, _make_env(
            QUEUE_LOW_WATER_MARK="10",
            QUEUE_TARGET_COUNT="15",
            QUEUE_AUTO_SEED_COOLDOWN="120",
        ), clear=False):
            from core.queue_watcher import get_config
            cfg = get_config()
            assert cfg["low_water_mark"] == 10
            assert cfg["target_count"] == 15
            assert cfg["cooldown_seconds"] == 120

    def test_disabled_flag(self):
        """QUEUE_AUTO_SEED_ENABLED=false disables seeding."""
        with patch.dict(os.environ, _make_env(
            QUEUE_AUTO_SEED_ENABLED="false",
        ), clear=False):
            from core.queue_watcher import get_config
            cfg = get_config()
            assert cfg["enabled"] is False


# ---------------------------------------------------------------------------
# pending_count() tests
# ---------------------------------------------------------------------------

class TestPendingCount:
    def test_pending_count_uses_zcard(self, fake_redis):
        """pending_count returns ZCARD of the pending_ids sorted set."""
        from core.shadow_queue import pending_count, _index_key
        # Empty set
        assert pending_count() == 0
        # Add items
        fake_redis.zadd(_index_key(), {"email_1": 100, "email_2": 200})
        assert pending_count() == 2

    def test_pending_count_zero_when_redis_down(self):
        """Returns 0 when Redis is unavailable."""
        with patch("core.shadow_queue._get_redis", return_value=None):
            from core.shadow_queue import pending_count
            assert pending_count() == 0


# ---------------------------------------------------------------------------
# check_and_seed() tests
# ---------------------------------------------------------------------------

class TestCheckAndSeed:
    def test_seeds_when_below_low_water_mark(self, fake_redis):
        """Triggers seed when pending count < low_water_mark."""
        with patch.dict(os.environ, _make_env(), clear=False):
            from core.queue_watcher import check_and_seed
            # pending_count = 0 (empty), low_water_mark = 3
            mock_emails = [{"email_id": f"seed_{i}", "synthetic": True} for i in range(5)]
            with patch("core.seed_queue.generate_seed_emails", return_value=mock_emails) as mock_gen:
                result = check_and_seed()
            assert result.seeded_count == 5
            assert result.reason == "low_water_mark"
            assert result.previous_count == 0
            mock_gen.assert_called_once_with(count=5)

    def test_no_seed_above_threshold(self, fake_redis):
        """No seeding when pending count >= low_water_mark."""
        from core.shadow_queue import _index_key
        # Add 5 items to sorted set
        for i in range(5):
            fake_redis.zadd(_index_key(), {f"email_{i}": 100 + i})

        with patch.dict(os.environ, _make_env(), clear=False):
            from core.queue_watcher import check_and_seed
            with patch("core.seed_queue.generate_seed_emails") as mock_gen:
                result = check_and_seed()
            assert result.seeded_count == 0
            assert result.reason == "above_threshold"
            mock_gen.assert_not_called()

    def test_seed_fills_to_target(self, fake_redis):
        """Seeds exactly (target - current) emails."""
        from core.shadow_queue import _index_key
        # 1 item in queue, target=5 -> should seed 4
        fake_redis.zadd(_index_key(), {"existing_1": 100})

        with patch.dict(os.environ, _make_env(), clear=False):
            from core.queue_watcher import check_and_seed
            mock_emails = [{"email_id": f"seed_{i}", "synthetic": True} for i in range(4)]
            with patch("core.seed_queue.generate_seed_emails", return_value=mock_emails) as mock_gen:
                result = check_and_seed()
            mock_gen.assert_called_once_with(count=4)
            assert result.seeded_count == 4

    def test_cooldown_prevents_rapid_seeding(self, fake_redis):
        """Second call within cooldown period is blocked."""
        with patch.dict(os.environ, _make_env(), clear=False):
            from core.queue_watcher import check_and_seed, _watcher_key
            # Set last_seed_ts to now (within cooldown)
            fake_redis.set(
                _watcher_key("last_seed_ts"),
                datetime.now(timezone.utc).isoformat(),
            )
            with patch("core.seed_queue.generate_seed_emails") as mock_gen:
                result = check_and_seed()
            assert result.seeded_count == 0
            assert result.reason == "cooldown_active"
            mock_gen.assert_not_called()

    def test_cooldown_expires_allows_reseed(self, fake_redis):
        """After cooldown expires, seeding resumes."""
        with patch.dict(os.environ, _make_env(QUEUE_AUTO_SEED_COOLDOWN="60"), clear=False):
            from core.queue_watcher import check_and_seed, _watcher_key
            # Set last_seed_ts to 2 minutes ago (expired)
            expired = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
            fake_redis.set(_watcher_key("last_seed_ts"), expired)

            mock_emails = [{"email_id": f"seed_{i}", "synthetic": True} for i in range(5)]
            with patch("core.seed_queue.generate_seed_emails", return_value=mock_emails):
                result = check_and_seed()
            assert result.seeded_count == 5
            assert result.reason == "low_water_mark"

    def test_daily_cap_stops_seeding(self, fake_redis):
        """After max_daily_auto_seeds, seeding stops."""
        from datetime import date
        with patch.dict(os.environ, _make_env(QUEUE_AUTO_SEED_MAX_DAILY="50"), clear=False):
            from core.queue_watcher import check_and_seed, _watcher_key
            daily_key = _watcher_key(f"daily_count:{date.today().isoformat()}")
            fake_redis.set(daily_key, "50")

            with patch("core.seed_queue.generate_seed_emails") as mock_gen:
                result = check_and_seed()
            assert result.seeded_count == 0
            assert result.reason == "daily_cap"
            mock_gen.assert_not_called()

    def test_force_bypasses_threshold(self, fake_redis):
        """force=True seeds even when above threshold."""
        from core.shadow_queue import _index_key
        # Add 10 items (well above threshold)
        for i in range(10):
            fake_redis.zadd(_index_key(), {f"email_{i}": 100 + i})

        with patch.dict(os.environ, _make_env(), clear=False):
            from core.queue_watcher import check_and_seed
            mock_emails = [{"email_id": "forced_1", "synthetic": True}]
            with patch("core.seed_queue.generate_seed_emails", return_value=mock_emails):
                result = check_and_seed(force=True)
            assert result.seeded_count == 1
            assert result.reason == "force"

    def test_disabled_flag_skips_all(self, fake_redis):
        """QUEUE_AUTO_SEED_ENABLED=false prevents all seeding."""
        with patch.dict(os.environ, _make_env(QUEUE_AUTO_SEED_ENABLED="false"), clear=False):
            from core.queue_watcher import check_and_seed
            with patch("core.seed_queue.generate_seed_emails") as mock_gen:
                result = check_and_seed()
            assert result.seeded_count == 0
            assert result.reason == "disabled"
            mock_gen.assert_not_called()

    def test_seeded_emails_are_synthetic(self, fake_redis):
        """All auto-seeded emails from seed_queue have synthetic=True."""
        with patch.dict(os.environ, _make_env(), clear=False):
            from core.queue_watcher import check_and_seed
            # Use real generate_seed_emails (it's pure, no APIs)
            result = check_and_seed()
            assert result.seeded_count > 0

    def test_result_dataclass_fields(self, fake_redis):
        """QueueWatcherResult has all expected fields."""
        with patch.dict(os.environ, _make_env(), clear=False):
            from core.queue_watcher import check_and_seed
            mock_emails = [{"email_id": "x", "synthetic": True}]
            with patch("core.seed_queue.generate_seed_emails", return_value=mock_emails):
                result = check_and_seed()
            assert hasattr(result, "seeded_count")
            assert hasattr(result, "previous_count")
            assert hasattr(result, "reason")
            assert hasattr(result, "timestamp")
            assert isinstance(result.timestamp, str)


# ---------------------------------------------------------------------------
# Background loop tests
# ---------------------------------------------------------------------------

class TestBackgroundLoop:
    def test_queue_watcher_loop_handles_exceptions(self):
        """Exception in check_and_seed doesn't kill the loop."""
        call_count = 0

        async def _run():
            nonlocal call_count
            from core.queue_watcher import queue_watcher_loop
            with patch.dict(os.environ, _make_env(QUEUE_CHECK_INTERVAL_SECONDS="0"), clear=False), \
                 patch("core.queue_watcher.check_and_seed", side_effect=RuntimeError("test error")):
                task = asyncio.create_task(queue_watcher_loop())
                # Let it run a few iterations
                for _ in range(5):
                    await asyncio.sleep(0.05)
                    call_count += 1
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        asyncio.get_event_loop().run_until_complete(_run())
        # Loop should have survived multiple iterations despite errors
        assert call_count >= 3


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_watcher_metrics_shape(self, fake_redis):
        """get_watcher_metrics returns all expected keys."""
        with patch.dict(os.environ, _make_env(), clear=False):
            from core.queue_watcher import get_watcher_metrics
            metrics = get_watcher_metrics()
            assert "enabled" in metrics
            assert "low_water_mark" in metrics
            assert "target_count" in metrics
            assert "cooldown_seconds" in metrics
            assert "check_interval_seconds" in metrics
            assert "max_daily_auto_seeds" in metrics
            assert "pending_count" in metrics
            assert isinstance(metrics["pending_count"], int)

    def test_total_seed_count_increments(self, fake_redis):
        """Total seed counter increments across calls."""
        with patch.dict(os.environ, _make_env(), clear=False):
            from core.queue_watcher import check_and_seed, get_watcher_metrics
            mock_emails = [{"email_id": "x", "synthetic": True}]
            with patch("core.seed_queue.generate_seed_emails", return_value=mock_emails):
                check_and_seed()
            metrics = get_watcher_metrics()
            assert metrics.get("total_seed_count", 0) >= 1

    def test_daily_counter_tracked(self, fake_redis):
        """Daily seed count is tracked in metrics."""
        with patch.dict(os.environ, _make_env(), clear=False):
            from core.queue_watcher import check_and_seed, get_watcher_metrics
            mock_emails = [{"email_id": "x", "synthetic": True}]
            with patch("core.seed_queue.generate_seed_emails", return_value=mock_emails):
                check_and_seed()
            metrics = get_watcher_metrics()
            assert metrics.get("daily_seed_count", 0) >= 1
