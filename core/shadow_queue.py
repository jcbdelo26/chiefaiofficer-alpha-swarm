#!/usr/bin/env python3
"""
Shadow email queue backed by Redis (primary) + filesystem (fallback).

Solves the local-vs-Railway filesystem mismatch:
- Pipeline runs locally → writes to Redis + local disk
- Dashboard runs on Railway → reads from Redis (shared Upstash instance)

Key pattern: caio:shadow:email:{email_id}
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("shadow_queue")

try:
    import redis as _redis_mod
except Exception:
    _redis_mod = None

_client: Optional[Any] = None
_init_done = False


def _get_redis() -> Optional[Any]:
    """Lazy-init Redis client from REDIS_URL env var."""
    global _client, _init_done
    if _init_done:
        return _client
    _init_done = True

    if _redis_mod is None:
        logger.debug("redis package not available; shadow queue file-only mode.")
        return None

    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        logger.debug("REDIS_URL not set; shadow queue file-only mode.")
        return None

    try:
        _client = _redis_mod.Redis.from_url(
            url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3,
        )
        _client.ping()
        logger.info("Shadow queue connected to Redis.")
    except Exception as exc:
        logger.warning("Shadow queue Redis connect failed: %s", exc)
        _client = None
    return _client


def _prefix() -> str:
    return (os.getenv("STATE_REDIS_PREFIX") or os.getenv("CONTEXT_REDIS_PREFIX") or "caio").strip()


def _key(email_id: str) -> str:
    return f"{_prefix()}:shadow:email:{email_id}"


def _index_key() -> str:
    return f"{_prefix()}:shadow:pending_ids"


# ──────────────────────────────────────────────────────────────────
# Write
# ──────────────────────────────────────────────────────────────────

def push(email_data: Dict[str, Any], shadow_dir: Optional[Path] = None) -> bool:
    """
    Write a shadow email to Redis AND (optionally) local disk.

    Returns True if at least one write succeeded.
    """
    email_id = email_data.get("email_id", "")
    wrote_redis = False
    wrote_file = False

    # Redis write
    r = _get_redis()
    if r:
        try:
            r.set(_key(email_id), json.dumps(email_data, ensure_ascii=False))
            # Maintain a sorted set of pending IDs (score = timestamp for ordering)
            if email_data.get("status") == "pending":
                r.zadd(_index_key(), {email_id: datetime.now(timezone.utc).timestamp()})
            wrote_redis = True
        except Exception as exc:
            logger.warning("Shadow queue Redis write failed for %s: %s", email_id, exc)

    # Filesystem write (local dev + backup)
    if shadow_dir:
        try:
            shadow_dir.mkdir(parents=True, exist_ok=True)
            filepath = shadow_dir / f"{email_id}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(email_data, f, indent=2, ensure_ascii=False)
            wrote_file = True
        except Exception as exc:
            logger.warning("Shadow queue file write failed for %s: %s", email_id, exc)

    return wrote_redis or wrote_file


# ──────────────────────────────────────────────────────────────────
# Read
# ──────────────────────────────────────────────────────────────────

def list_pending(limit: int = 20, shadow_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Return pending shadow emails. Redis first, filesystem fallback.
    """
    # Try Redis
    r = _get_redis()
    if r:
        try:
            # Get pending IDs from sorted set (newest first)
            pending_ids = r.zrevrange(_index_key(), 0, limit - 1)
            if pending_ids:
                pending = []
                for eid in pending_ids:
                    raw = r.get(_key(eid))
                    if not raw:
                        # Stale index entry — remove
                        r.zrem(_index_key(), eid)
                        continue
                    data = json.loads(raw)
                    if data.get("status") == "pending":
                        pending.append(data)
                    else:
                        # Status changed — remove from pending index
                        r.zrem(_index_key(), eid)
                if pending:
                    return pending
            # If index is empty but we have Redis, check for stray keys
            # (migration scenario where keys exist but index doesn't)
            pattern = f"{_prefix()}:shadow:email:*"
            keys = list(r.scan_iter(match=pattern, count=100))
            if keys:
                pending = []
                for key in keys[:limit * 2]:
                    raw = r.get(key)
                    if not raw:
                        continue
                    data = json.loads(raw)
                    if data.get("status") == "pending":
                        pending.append(data)
                        # Rebuild index
                        eid = data.get("email_id", "")
                        if eid:
                            ts = data.get("timestamp", "")
                            try:
                                score = datetime.fromisoformat(ts.replace("+00:00", "+00:00")).timestamp()
                            except Exception:
                                score = datetime.now(timezone.utc).timestamp()
                            r.zadd(_index_key(), {eid: score})
                if pending:
                    pending.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
                    return pending[:limit]
        except Exception as exc:
            logger.warning("Shadow queue Redis read failed: %s", exc)

    # Filesystem fallback
    if shadow_dir and shadow_dir.exists():
        pending = []
        for email_file in sorted(shadow_dir.glob("*.json"), reverse=True)[:limit]:
            try:
                with open(email_file) as f:
                    data = json.load(f)
                if data.get("status", "pending") == "pending":
                    data["email_id"] = data.get("email_id") or email_file.stem
                    pending.append(data)
            except Exception as exc:
                logger.warning("Failed to read shadow email %s: %s", email_file, exc)
        return pending

    return []


# ──────────────────────────────────────────────────────────────────
# Update
# ──────────────────────────────────────────────────────────────────

def update_status(
    email_id: str,
    new_status: str,
    shadow_dir: Optional[Path] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update email status in Redis and filesystem. Returns updated data or None.
    """
    data = None

    # Redis update
    r = _get_redis()
    if r:
        try:
            raw = r.get(_key(email_id))
            if raw:
                data = json.loads(raw)
                data["status"] = new_status
                if extra_fields:
                    data.update(extra_fields)
                r.set(_key(email_id), json.dumps(data, ensure_ascii=False))
                # Remove from pending index if no longer pending
                if new_status != "pending":
                    r.zrem(_index_key(), email_id)
        except Exception as exc:
            logger.warning("Shadow queue Redis update failed for %s: %s", email_id, exc)

    # Filesystem update
    if shadow_dir and shadow_dir.exists():
        for f in shadow_dir.glob("*.json"):
            try:
                with open(f) as fp:
                    fdata = json.load(fp)
                if fdata.get("email_id") == email_id or f.stem == email_id:
                    fdata["status"] = new_status
                    if extra_fields:
                        fdata.update(extra_fields)
                    with open(f, "w", encoding="utf-8") as fp:
                        json.dump(fdata, fp, indent=2, ensure_ascii=False)
                    if data is None:
                        data = fdata
                    break
            except Exception:
                continue

    return data


def get_email(email_id: str, shadow_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Get a single email by ID from Redis or filesystem."""
    r = _get_redis()
    if r:
        try:
            raw = r.get(_key(email_id))
            if raw:
                return json.loads(raw)
        except Exception:
            pass

    if shadow_dir and shadow_dir.exists():
        for f in shadow_dir.glob("*.json"):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                if data.get("email_id") == email_id or f.stem == email_id:
                    return data
            except Exception:
                continue

    return None
