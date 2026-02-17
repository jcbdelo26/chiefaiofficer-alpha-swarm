#!/usr/bin/env python3
"""
StateStore Redis cutover tests (dual-read + lock behavior).
"""

from __future__ import annotations

import fnmatch
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest


class _FakeRedisClient:
    def __init__(self):
        self._kv: dict[str, str] = {}

    @classmethod
    def from_url(cls, *args, **kwargs):
        return cls()

    def ping(self):
        return True

    def get(self, key: str):
        return self._kv.get(key)

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self._kv:
            return False
        self._kv[key] = value
        return True

    def scan_iter(self, match: str):
        for key in list(self._kv.keys()):
            if fnmatch.fnmatch(key, match):
                yield key

    def eval(self, script: str, numkeys: int, key: str, token: str):
        if self._kv.get(key) == token:
            del self._kv[key]
            return 1
        return 0


def _set_fake_redis(monkeypatch):
    from core import state_store
    monkeypatch.setattr(state_store, "redis", SimpleNamespace(Redis=_FakeRedisClient))
    return state_store


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_operator_state_dual_read_backfills_redis(monkeypatch, tmp_path: Path):
    state_store = _set_fake_redis(monkeypatch)
    today = date.today().isoformat()
    hive_dir = tmp_path / ".hive-mind"

    _write_json(
        hive_dir / "operator_state.json",
        {
            "date": today,
            "outbound_email_dispatched": 2,
            "outbound_linkedin_dispatched": 1,
            "revival_dispatched": 0,
            "cadence_dispatched": 0,
            "leads_dispatched": ["email:buyer@example.com"],
            "runs_today": 1,
        },
    )

    monkeypatch.setenv("STATE_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
    monkeypatch.setenv("STATE_DUAL_READ_ENABLED", "true")

    store = state_store.StateStore(hive_dir=hive_dir)
    payload = store.get_operator_daily_state(today)
    assert payload is not None
    assert payload["outbound_email_dispatched"] == 2

    redis_key = store._key("operator", "state", today)
    raw = store._redis_client.get(redis_key)
    assert raw is not None
    restored = json.loads(raw)
    assert restored["date"] == today


def test_cadence_state_dual_read_backfills_redis(monkeypatch, tmp_path: Path):
    state_store = _set_fake_redis(monkeypatch)
    hive_dir = tmp_path / ".hive-mind"
    email = "lead@example.com"
    cadence_payload = {
        "email": email,
        "cadence_id": "default_21day",
        "tier": "tier_1",
        "started_at": "2026-02-17T00:00:00+00:00",
        "current_step": 1,
        "status": "active",
        "next_step_due": date.today().isoformat(),
    }

    filename = email.lower().replace("@", "_at_").replace(".", "_") + ".json"
    _write_json(hive_dir / "cadence_state" / filename, cadence_payload)

    monkeypatch.setenv("STATE_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
    monkeypatch.setenv("STATE_DUAL_READ_ENABLED", "true")

    store = state_store.StateStore(hive_dir=hive_dir)
    loaded = store.get_cadence_lead_state(email)
    assert loaded is not None
    assert loaded["email"] == email

    email_hash = state_store.cadence_email_hash(email)
    redis_key = store._key("cadence", "lead", email_hash)
    assert store._redis_client.get(redis_key) is not None


def test_operator_lock_disallows_concurrent_live_runs(monkeypatch, tmp_path: Path):
    state_store = _set_fake_redis(monkeypatch)
    hive_dir = tmp_path / ".hive-mind"
    monkeypatch.setenv("STATE_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")

    store = state_store.StateStore(hive_dir=hive_dir)

    token1 = store.acquire_operator_lock("outbound", ttl_seconds=60)
    assert token1 is not None

    token2 = store.acquire_operator_lock("outbound", ttl_seconds=60)
    assert token2 is None

    store.release_operator_lock("outbound", token1)
    token3 = store.acquire_operator_lock("outbound", ttl_seconds=60)
    assert token3 is not None
