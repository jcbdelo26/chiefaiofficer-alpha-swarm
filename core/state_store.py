#!/usr/bin/env python3
"""
Unified state storage for OPERATOR and Cadence.

Supports:
- Redis source-of-truth with dual-read fallback from file state
- File backend fallback when Redis is unavailable
- Distributed locks for live dispatch paths
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import redis
except Exception:  # pragma: no cover - optional runtime dependency in some test envs
    redis = None


logger = logging.getLogger("state_store")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def cadence_email_hash(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


class StateStore:
    """
    Redis-backed state store with deterministic file fallback behavior.

    Key convention:
    - {prefix}:operator:state:{YYYY-MM-DD}
    - {prefix}:operator:batch:{batch_id}
    - {prefix}:cadence:lead:{email_hash}
    - {prefix}:locks:operator:{motion}
    """

    def __init__(self, hive_dir: Optional[Path] = None):
        self.hive_dir = Path(hive_dir) if hive_dir else (Path(__file__).resolve().parent.parent / ".hive-mind")
        self.hive_dir.mkdir(parents=True, exist_ok=True)

        self.backend = (os.getenv("STATE_BACKEND") or "redis").strip().lower()
        self.redis_prefix = (os.getenv("STATE_REDIS_PREFIX") or "caio").strip() or "caio"
        self.redis_url = (os.getenv("REDIS_URL") or "").strip()
        self._redis_client = None

        self._dual_read_enabled = (os.getenv("STATE_DUAL_READ_ENABLED") or "true").strip().lower() in {
            "1", "true", "yes", "on"
        }
        self._file_write_enabled = (os.getenv("STATE_FILE_FALLBACK_WRITE") or "true").strip().lower() in {
            "1", "true", "yes", "on"
        }

        self.operator_state_file = self.hive_dir / "operator_state.json"
        self.batch_dir = self.hive_dir / "operator_batches"
        self.cadence_state_dir = self.hive_dir / "cadence_state"
        self.batch_dir.mkdir(parents=True, exist_ok=True)
        self.cadence_state_dir.mkdir(parents=True, exist_ok=True)

        self._init_redis()

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    def _init_redis(self) -> None:
        if self.backend != "redis":
            return
        if redis is None:
            logger.warning("STATE_BACKEND=redis but redis package is not available; falling back to file backend.")
            return
        if not self.redis_url:
            logger.warning("STATE_BACKEND=redis but REDIS_URL is not set; falling back to file backend.")
            return
        try:
            self._redis_client = redis.Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._redis_client.ping()
            logger.info("StateStore connected to Redis backend.")
        except Exception as exc:
            logger.warning("StateStore Redis init failed; file fallback only. Error: %s", exc)
            self._redis_client = None

    def _redis_enabled(self) -> bool:
        return self.backend == "redis" and self._redis_client is not None

    def _key(self, *parts: str) -> str:
        pieces = [self.redis_prefix]
        pieces.extend([str(p).strip(":") for p in parts if p])
        return ":".join(pieces)

    def _redis_get_json(self, key: str) -> Optional[Dict[str, Any]]:
        if not self._redis_enabled():
            return None
        try:
            raw = self._redis_client.get(key)
            if not raw:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Redis read failed for key=%s: %s", key, exc)
            return None

    def _redis_set_json(self, key: str, payload: Dict[str, Any]) -> None:
        if not self._redis_enabled():
            return
        try:
            self._redis_client.set(key, json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            logger.warning("Redis write failed for key=%s: %s", key, exc)

    def _redis_scan_keys(self, pattern: str) -> List[str]:
        if not self._redis_enabled():
            return []
        try:
            return list(self._redis_client.scan_iter(match=pattern))
        except Exception as exc:
            logger.warning("Redis scan failed for pattern=%s: %s", pattern, exc)
            return []

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _read_json_file(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _write_json_file(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------------
    # Operator daily state
    # ------------------------------------------------------------------

    def get_operator_daily_state(self, state_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_date = state_date or date.today().isoformat()
        redis_key = self._key("operator", "state", target_date)

        data = self._redis_get_json(redis_key)
        if data:
            return data

        file_data = self._read_json_file(self.operator_state_file)
        if file_data and file_data.get("date") == target_date:
            if self._dual_read_enabled:
                self._redis_set_json(redis_key, file_data)
            return file_data
        return None

    def save_operator_daily_state(self, state_date: str, payload: Dict[str, Any]) -> None:
        redis_key = self._key("operator", "state", state_date)
        self._redis_set_json(redis_key, payload)
        if self._file_write_enabled:
            self._write_json_file(self.operator_state_file, payload)

    # ------------------------------------------------------------------
    # Operator batches
    # ------------------------------------------------------------------

    def _batch_file(self, batch_id: str) -> Path:
        return self.batch_dir / f"{batch_id}.json"

    def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        redis_key = self._key("operator", "batch", batch_id)
        data = self._redis_get_json(redis_key)
        if data:
            return data

        file_data = self._read_json_file(self._batch_file(batch_id))
        if file_data and self._dual_read_enabled:
            self._redis_set_json(redis_key, file_data)
        return file_data

    def save_batch(self, batch_id: str, payload: Dict[str, Any]) -> None:
        redis_key = self._key("operator", "batch", batch_id)
        self._redis_set_json(redis_key, payload)
        if self._file_write_enabled:
            self._write_json_file(self._batch_file(batch_id), payload)

    def list_batches(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        batches: List[Dict[str, Any]] = []

        redis_pattern = self._key("operator", "batch", "*")
        redis_keys = self._redis_scan_keys(redis_pattern)
        for key in redis_keys:
            data = self._redis_get_json(key)
            if not data:
                continue
            if status and data.get("status") != status:
                continue
            batches.append(data)

        if batches:
            batches.sort(key=lambda b: b.get("created_at", ""), reverse=True)
            return batches

        # fallback read from file batch dir
        for path in self.batch_dir.glob("batch_*.json"):
            data = self._read_json_file(path)
            if not data:
                continue
            if status and data.get("status") != status:
                continue
            batches.append(data)
            if self._dual_read_enabled and data.get("batch_id"):
                self._redis_set_json(self._key("operator", "batch", data["batch_id"]), data)

        batches.sort(key=lambda b: b.get("created_at", ""), reverse=True)
        return batches

    # ------------------------------------------------------------------
    # Cadence lead state
    # ------------------------------------------------------------------

    def _cadence_file_path(self, email: str) -> Path:
        filename = normalize_email(email).replace("@", "_at_").replace(".", "_") + ".json"
        return self.cadence_state_dir / filename

    def get_cadence_lead_state(self, email: str) -> Optional[Dict[str, Any]]:
        email_hash = cadence_email_hash(email)
        if not email_hash:
            return None
        redis_key = self._key("cadence", "lead", email_hash)
        data = self._redis_get_json(redis_key)
        if data:
            return data

        file_data = self._read_json_file(self._cadence_file_path(email))
        if file_data and self._dual_read_enabled:
            self._redis_set_json(redis_key, file_data)
        return file_data

    def save_cadence_lead_state(self, email: str, payload: Dict[str, Any]) -> None:
        email_hash = cadence_email_hash(email)
        if not email_hash:
            return
        redis_key = self._key("cadence", "lead", email_hash)
        self._redis_set_json(redis_key, payload)
        if self._file_write_enabled:
            self._write_json_file(self._cadence_file_path(email), payload)

    def list_cadence_lead_states(self) -> List[Dict[str, Any]]:
        states: List[Dict[str, Any]] = []
        redis_pattern = self._key("cadence", "lead", "*")
        redis_keys = self._redis_scan_keys(redis_pattern)
        for key in redis_keys:
            data = self._redis_get_json(key)
            if data:
                states.append(data)

        if states:
            return states

        for path in self.cadence_state_dir.glob("*.json"):
            data = self._read_json_file(path)
            if not data:
                continue
            states.append(data)
            if self._dual_read_enabled and data.get("email"):
                email_hash = cadence_email_hash(data["email"])
                if email_hash:
                    self._redis_set_json(self._key("cadence", "lead", email_hash), data)
        return states

    # ------------------------------------------------------------------
    # Distributed lock (Redis)
    # ------------------------------------------------------------------

    def acquire_operator_lock(self, motion: str, ttl_seconds: int = 120) -> Optional[str]:
        if not self._redis_enabled():
            return f"file-lock-{uuid.uuid4().hex[:8]}"

        key = self._key("locks", "operator", motion)
        token = uuid.uuid4().hex
        try:
            acquired = self._redis_client.set(key, token, nx=True, ex=max(10, ttl_seconds))
            if acquired:
                return token
            return None
        except Exception as exc:
            logger.warning("Failed to acquire operator lock (%s): %s", motion, exc)
            return None

    def release_operator_lock(self, motion: str, token: str) -> None:
        if not self._redis_enabled():
            return
        key = self._key("locks", "operator", motion)
        release_script = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""
        try:
            self._redis_client.eval(release_script, 1, key, token)
        except Exception as exc:
            logger.warning("Failed to release operator lock (%s): %s", motion, exc)
