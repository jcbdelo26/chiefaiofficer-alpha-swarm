#!/usr/bin/env python3
"""Regression tests for OPERATOR ramp graduation logic."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest


def _write_operator_config(project_root: Path, ramp: dict) -> None:
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "production.json").write_text(
        json.dumps(
            {
                "operator": {
                    "enabled": True,
                    "gatekeeper_required": True,
                    "outbound": {
                        "email_daily_limit": 25,
                        "linkedin_warmup_start": date.today().isoformat(),
                        "linkedin_warmup_daily_limit": 5,
                        "linkedin_full_daily_limit": 20,
                        "linkedin_warmup_weeks": 4,
                        "tier_channel_routing": {
                            "tier_1": ["instantly", "heyreach"],
                            "tier_2": ["instantly", "heyreach"],
                            "tier_3": ["instantly"],
                        },
                    },
                    "revival": {"daily_limit": 5, "enabled": True},
                    "ramp": ramp,
                }
            }
        ),
        encoding="utf-8",
    )


def _clean_live_entry(day_value: date, *, instantly: int = 0, cadence: int = 0, revival: int = 0) -> dict:
    return {
        "run_id": f"run_{day_value.isoformat()}",
        "started_at": f"{day_value.isoformat()}T10:00:00+00:00",
        "completed_at": f"{day_value.isoformat()}T10:01:00+00:00",
        "dry_run": False,
        "pending_approval": False,
        "errors": [],
        "instantly_report": {"total_dispatched": instantly},
        "cadence_dispatched": cadence,
        "revival_dispatched": revival,
    }


def test_ramp_clean_days_mode_stays_active_until_required(monkeypatch, tmp_path: Path):
    from execution import operator_outbound

    start_date = (date.today() - timedelta(days=7)).isoformat()
    _write_operator_config(
        tmp_path,
        ramp={
            "enabled": True,
            "mode": "clean_days",
            "start_date": start_date,
            "clean_days_required": 3,
            "clean_days_lookback_days": 45,
            "email_daily_limit_override": 5,
            "tier_filter": "tier_1",
        },
    )
    monkeypatch.setattr(operator_outbound, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("STATE_BACKEND", "file")
    operator = operator_outbound.OperatorOutbound()

    d1 = date.today() - timedelta(days=2)
    d2 = date.today() - timedelta(days=1)
    monkeypatch.setattr(
        operator,
        "get_dispatch_history",
        lambda limit=2000: [
            _clean_live_entry(d2, cadence=1),
            _clean_live_entry(d1, instantly=2),
        ],
    )

    ramp = operator._get_ramp_status()
    assert ramp["mode"] == "clean_days"
    assert ramp["clean_days_completed"] == 2
    assert ramp["clean_days_required"] == 3
    assert ramp["active"] is True
    assert ramp["day"] == 3
    assert ramp["remaining_days"] == 1
    assert ramp["email_limit_override"] == 5
    assert ramp["tier_filter"] == "tier_1"


def test_ramp_clean_days_mode_auto_deactivates_after_required(monkeypatch, tmp_path: Path):
    from execution import operator_outbound

    start_date = (date.today() - timedelta(days=10)).isoformat()
    _write_operator_config(
        tmp_path,
        ramp={
            "enabled": True,
            "mode": "clean_days",
            "start_date": start_date,
            "clean_days_required": 3,
            "email_daily_limit_override": 5,
            "tier_filter": "tier_1",
        },
    )
    monkeypatch.setattr(operator_outbound, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("STATE_BACKEND", "file")
    operator = operator_outbound.OperatorOutbound()

    d1 = date.today() - timedelta(days=3)
    d2 = date.today() - timedelta(days=2)
    d3 = date.today() - timedelta(days=1)
    monkeypatch.setattr(
        operator,
        "get_dispatch_history",
        lambda limit=2000: [
            _clean_live_entry(d3, instantly=1),
            _clean_live_entry(d2, revival=1),
            _clean_live_entry(d1, cadence=1),
        ],
    )

    ramp = operator._get_ramp_status()
    assert ramp["clean_days_completed"] == 3
    assert ramp["active"] is False
    assert ramp["day"] == 3
    assert ramp["remaining_days"] == 0
    assert ramp["email_limit_override"] is None
    assert ramp["tier_filter"] is None


def test_ramp_clean_days_ignores_unclean_live_reports(monkeypatch, tmp_path: Path):
    from execution import operator_outbound

    _write_operator_config(
        tmp_path,
        ramp={
            "enabled": True,
            "mode": "clean_days",
            "start_date": (date.today() - timedelta(days=5)).isoformat(),
            "clean_days_required": 3,
            "email_daily_limit_override": 5,
            "tier_filter": "tier_1",
        },
    )
    monkeypatch.setattr(operator_outbound, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("STATE_BACKEND", "file")
    operator = operator_outbound.OperatorOutbound()

    noisy_day = date.today() - timedelta(days=1)
    monkeypatch.setattr(
        operator,
        "get_dispatch_history",
        lambda limit=2000: [
            {
                "started_at": f"{noisy_day.isoformat()}T10:00:00+00:00",
                "completed_at": f"{noisy_day.isoformat()}T10:01:00+00:00",
                "dry_run": True,
                "errors": [],
                "pending_approval": False,
                "instantly_report": {"total_dispatched": 1},
            },
            {
                "started_at": f"{noisy_day.isoformat()}T11:00:00+00:00",
                "completed_at": f"{noisy_day.isoformat()}T11:01:00+00:00",
                "dry_run": False,
                "errors": ["gatekeeper pending"],
                "pending_approval": True,
                "instantly_report": {"total_dispatched": 1},
            },
            {
                "started_at": f"{noisy_day.isoformat()}T12:00:00+00:00",
                "completed_at": f"{noisy_day.isoformat()}T12:01:00+00:00",
                "dry_run": False,
                "errors": [],
                "pending_approval": False,
                "instantly_report": {"total_dispatched": 0},
                "cadence_dispatched": 0,
                "revival_dispatched": 0,
            },
        ],
    )

    ramp = operator._get_ramp_status()
    assert ramp["clean_days_completed"] == 0
    assert ramp["active"] is True
    assert ramp["day"] == 1
    assert ramp["remaining_days"] == 3


def test_ramp_calendar_mode_preserves_legacy_behavior(monkeypatch, tmp_path: Path):
    from execution import operator_outbound

    _write_operator_config(
        tmp_path,
        ramp={
            "enabled": True,
            "mode": "calendar",
            "start_date": (date.today() - timedelta(days=5)).isoformat(),
            "ramp_days": 3,
            "email_daily_limit_override": 5,
            "tier_filter": "tier_1",
        },
    )
    monkeypatch.setattr(operator_outbound, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("STATE_BACKEND", "file")
    operator = operator_outbound.OperatorOutbound()

    ramp = operator._get_ramp_status()
    assert ramp["mode"] == "calendar"
    assert ramp["active"] is False
    assert ramp["day"] == 0
    assert ramp["remaining_days"] == 0
