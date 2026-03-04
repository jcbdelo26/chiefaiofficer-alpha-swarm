"""
Queue Watcher -- Self-validation loop for email queue auto-repopulation.

Ensures the HoS pending email queue never appears empty by monitoring
the Redis sorted set cardinality and auto-seeding when count drops
below a configurable low-water mark.

Two complementary mechanisms:
  1. check_and_seed() -- called synchronously from /api/pending-emails
  2. queue_watcher_loop() -- async background task as safety net

Configuration via env vars (override) or config/production.json (fallback).
Kill switch: QUEUE_AUTO_SEED_ENABLED=false
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("queue_watcher")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_config_cache: Optional[Dict[str, Any]] = None


def _load_config() -> Dict[str, Any]:
    """Load queue_watcher config from production.json (cached)."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    try:
        cfg_path = Path(__file__).parent.parent / "config" / "production.json"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                full = json.load(f)
            _config_cache = full.get("queue_watcher", {})
        else:
            _config_cache = {}
    except Exception:
        _config_cache = {}
    return _config_cache


def _cfg(key: str, default: Any) -> Any:
    """Read config: env var first, then production.json, then default."""
    env_map = {
        "enabled": "QUEUE_AUTO_SEED_ENABLED",
        "low_water_mark": "QUEUE_LOW_WATER_MARK",
        "target_count": "QUEUE_TARGET_COUNT",
        "cooldown_seconds": "QUEUE_AUTO_SEED_COOLDOWN",
        "check_interval_seconds": "QUEUE_CHECK_INTERVAL_SECONDS",
        "max_daily_auto_seeds": "QUEUE_AUTO_SEED_MAX_DAILY",
    }
    env_var = env_map.get(key)
    if env_var:
        val = os.getenv(env_var, "").strip()
        if val:
            if isinstance(default, bool):
                return val.lower() in ("true", "1", "yes")
            if isinstance(default, int):
                try:
                    return int(val)
                except ValueError:
                    pass
            return val
    file_cfg = _load_config()
    return file_cfg.get(key, default)


def get_config() -> Dict[str, Any]:
    """Return full resolved configuration."""
    return {
        "enabled": _cfg("enabled", True),
        "low_water_mark": _cfg("low_water_mark", 3),
        "target_count": _cfg("target_count", 5),
        "cooldown_seconds": _cfg("cooldown_seconds", 60),
        "check_interval_seconds": _cfg("check_interval_seconds", 30),
        "max_daily_auto_seeds": _cfg("max_daily_auto_seeds", 50),
    }


# ---------------------------------------------------------------------------
# Redis helpers (reuse shadow_queue internals)
# ---------------------------------------------------------------------------

def _watcher_key(suffix: str) -> str:
    from core.shadow_queue import _prefix
    return f"{_prefix()}:shadow:queue_watcher:{suffix}"


def _get_redis():
    from core.shadow_queue import _get_redis as sq_redis
    return sq_redis()


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class QueueWatcherResult:
    seeded_count: int
    previous_count: int
    reason: str  # "low_water_mark", "force", "cooldown_active", "above_threshold", "disabled", "daily_cap"
    timestamp: str


# ---------------------------------------------------------------------------
# Core: check_and_seed
# ---------------------------------------------------------------------------

def check_and_seed(force: bool = False) -> QueueWatcherResult:
    """
    Check pending queue depth and auto-seed if below low-water mark.

    Returns a QueueWatcherResult describing what happened.
    """
    now = datetime.now(timezone.utc)
    ts = now.isoformat()
    cfg = get_config()

    if not cfg["enabled"] and not force:
        return QueueWatcherResult(0, 0, "disabled", ts)

    from core.shadow_queue import pending_count as sq_pending_count
    current = sq_pending_count()

    if current >= cfg["low_water_mark"] and not force:
        return QueueWatcherResult(0, current, "above_threshold", ts)

    # Check cooldown
    r = _get_redis()
    if r:
        try:
            last_ts_raw = r.get(_watcher_key("last_seed_ts"))
            if last_ts_raw:
                last_dt = datetime.fromisoformat(last_ts_raw)
                elapsed = (now - last_dt).total_seconds()
                if elapsed < cfg["cooldown_seconds"]:
                    return QueueWatcherResult(0, current, "cooldown_active", ts)
        except Exception:
            pass

        # Check daily cap
        try:
            daily_key = _watcher_key(f"daily_count:{date.today().isoformat()}")
            daily_raw = r.get(daily_key)
            daily_count = int(daily_raw) if daily_raw else 0
            if daily_count >= cfg["max_daily_auto_seeds"]:
                return QueueWatcherResult(0, current, "daily_cap", ts)
        except Exception:
            pass

    # Calculate seed count
    seed_count = max(1, cfg["target_count"] - current)
    seed_count = min(seed_count, 20)  # hard cap per seed_queue

    # Seed
    try:
        from core.seed_queue import generate_seed_emails
        emails = generate_seed_emails(count=seed_count)
        seeded = len(emails)
    except Exception as exc:
        logger.warning("Queue watcher seed failed: %s", exc)
        return QueueWatcherResult(0, current, f"seed_error: {exc}", ts)

    # Update Redis metadata
    if r:
        try:
            r.set(_watcher_key("last_seed_ts"), ts)
            daily_key = _watcher_key(f"daily_count:{date.today().isoformat()}")
            r.incr(daily_key)
            r.expire(daily_key, 90000)  # 25h TTL
            r.incr(_watcher_key("total_seed_count"))
        except Exception as exc:
            logger.warning("Queue watcher metadata update failed: %s", exc)

    reason = "force" if force else "low_water_mark"
    logger.info(
        "Queue watcher auto-seeded %d emails (was %d, reason: %s)",
        seeded, current, reason,
    )
    return QueueWatcherResult(seeded, current, reason, ts)


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------

async def queue_watcher_loop():
    """Background safety net: periodically check and seed."""
    cfg = get_config()
    interval = cfg["check_interval_seconds"]
    logger.info("Queue watcher background loop started (interval=%ds)", interval)
    while True:
        await asyncio.sleep(interval)
        try:
            result = check_and_seed()
            if result.seeded_count > 0:
                logger.info(
                    "Queue watcher loop seeded %d emails (reason: %s)",
                    result.seeded_count, result.reason,
                )
        except Exception as exc:
            logger.warning("Queue watcher loop error: %s", exc)


# ---------------------------------------------------------------------------
# Metrics / observability
# ---------------------------------------------------------------------------

def get_watcher_metrics() -> Dict[str, Any]:
    """Return observable metrics for the queue watcher."""
    cfg = get_config()
    metrics: Dict[str, Any] = {
        "enabled": cfg["enabled"],
        "low_water_mark": cfg["low_water_mark"],
        "target_count": cfg["target_count"],
        "cooldown_seconds": cfg["cooldown_seconds"],
        "check_interval_seconds": cfg["check_interval_seconds"],
        "max_daily_auto_seeds": cfg["max_daily_auto_seeds"],
    }

    from core.shadow_queue import pending_count as sq_pending_count
    metrics["pending_count"] = sq_pending_count()

    r = _get_redis()
    if r:
        try:
            metrics["last_auto_seed_ts"] = r.get(_watcher_key("last_seed_ts")) or ""
            daily_key = _watcher_key(f"daily_count:{date.today().isoformat()}")
            raw = r.get(daily_key)
            metrics["daily_seed_count"] = int(raw) if raw else 0
            total_raw = r.get(_watcher_key("total_seed_count"))
            metrics["total_seed_count"] = int(total_raw) if total_raw else 0
        except Exception:
            metrics["redis_error"] = True
    else:
        metrics["redis_available"] = False

    return metrics
