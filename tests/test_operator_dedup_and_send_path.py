#!/usr/bin/env python3
"""
Dedup and send-path safety tests for OPERATOR + dashboard approval flow.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest


def _write_operator_config(project_root: Path) -> None:
    config = {
        "operator": {
            "enabled": True,
            "gatekeeper_required": True,
            "outbound": {
                "email_daily_limit": 25,
                "linkedin_warmup_start": date.today().isoformat(),
                "linkedin_warmup_daily_limit": 5,
                "linkedin_full_daily_limit": 20,
                "linkedin_warmup_weeks": 4,
                "tier_channel_routing": {"tier_1": ["instantly", "heyreach"]},
            },
            "revival": {"enabled": True, "daily_limit": 5},
        },
        "external_apis": {
            "instantly": {"enabled": True}
        },
        "cadence": {"default_21day": {"steps": [], "exit_on": [], "pause_on": []}},
        "email_behavior": {"actually_send": True},
        "guardrails": {"email_limits": {"daily_limit": 25, "monthly_limit": 3000, "min_delay_seconds": 60}},
    }
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "production.json").write_text(json.dumps(config), encoding="utf-8")


def _write_shadow_file(shadow_dir: Path, name: str, payload: dict) -> Path:
    shadow_dir.mkdir(parents=True, exist_ok=True)
    path = shadow_dir / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_instantly_loader_excludes_sent_via_ghl(monkeypatch, tmp_path: Path):
    from execution import instantly_dispatcher

    project_root = tmp_path
    _write_operator_config(project_root)
    shadow_dir = project_root / ".hive-mind" / "shadow_mode_emails"

    _write_shadow_file(
        shadow_dir,
        "approved_ok",
        {
            "email_id": "approved_ok",
            "status": "approved",
            "to": "ok@example.com",
            "tier": "tier_1",
            "subject": "OK",
            "body": "OK",
        },
    )
    _write_shadow_file(
        shadow_dir,
        "approved_but_ghl_sent",
        {
            "email_id": "approved_but_ghl_sent",
            "status": "approved",
            "sent_via_ghl": True,
            "to": "skip1@example.com",
            "tier": "tier_1",
            "subject": "Skip",
            "body": "Skip",
        },
    )
    _write_shadow_file(
        shadow_dir,
        "terminal_ghl_status",
        {
            "email_id": "terminal_ghl_status",
            "status": "sent_via_ghl",
            "sent_via_ghl": True,
            "to": "skip2@example.com",
            "tier": "tier_1",
            "subject": "Skip2",
            "body": "Skip2",
        },
    )

    monkeypatch.setattr(instantly_dispatcher, "PROJECT_ROOT", project_root)
    dispatcher = instantly_dispatcher.InstantlyDispatcher()
    approved = dispatcher._load_approved_emails()

    approved_ids = {item.get("email_id") for item in approved}
    assert approved_ids == {"approved_ok"}


def test_legacy_email_id_dedup_backfills_canonical_email(monkeypatch, tmp_path: Path):
    from execution import operator_outbound

    project_root = tmp_path
    hive_dir = project_root / ".hive-mind"
    shadow_dir = hive_dir / "shadow_mode_emails"
    _write_operator_config(project_root)

    _write_shadow_file(
        shadow_dir,
        "legacy_shadow",
        {
            "email_id": "legacy_shadow",
            "status": "approved",
            "to": "repeat@example.com",
            "tier": "tier_1",
            "subject": "Subject",
            "body": "Body",
        },
    )

    state_payload = {
        "date": date.today().isoformat(),
        "outbound_email_dispatched": 1,
        "outbound_linkedin_dispatched": 0,
        "revival_dispatched": 0,
        "cadence_dispatched": 0,
        "leads_dispatched": ["legacy_shadow"],  # legacy email_id-only entry
        "last_run_at": "",
        "runs_today": 1,
    }
    (hive_dir / "operator_state.json").parent.mkdir(parents=True, exist_ok=True)
    (hive_dir / "operator_state.json").write_text(json.dumps(state_payload), encoding="utf-8")

    monkeypatch.setenv("STATE_BACKEND", "file")
    monkeypatch.setattr(operator_outbound, "PROJECT_ROOT", project_root)
    operator = operator_outbound.OperatorOutbound()

    state = operator._load_daily_state()
    assert "email:repeat@example.com" in [entry.lower() for entry in state.leads_dispatched]
    assert operator._is_lead_eligible("repeat@example.com", state) is False


@pytest.mark.asyncio
async def test_dashboard_approval_marks_sent_via_ghl_terminal_status(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    project_root = tmp_path
    _write_operator_config(project_root)
    shadow_dir = project_root / ".hive-mind" / "shadow_mode_emails"
    email_path = _write_shadow_file(
        shadow_dir,
        "ghl_send_case",
        {
            "email_id": "ghl_send_case",
            "status": "pending",
            "to": "buyer@example.com",
            "subject": "Subject",
            "body": "Body",
            "tier": "tier_1",
            "angle": "ROI",
            "contact_id": "real_contact_123",
        },
    )

    class _FakeGHLClient:
        def __init__(self, api_key, location_id, config=None):
            self.api_key = api_key
            self.location_id = location_id

        async def send_email(self, contact_id, template):
            return {"success": True, "message_id": "ghl-msg-1"}

        async def close(self):
            return None

    monkeypatch.setattr(health_app, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(health_app, "GHLOutreachClient", _FakeGHLClient)
    monkeypatch.setenv("GHL_API_KEY", "test-key")
    monkeypatch.setenv("GHL_LOCATION_ID", "test-location")

    result = await health_app.approve_email(
        email_id="ghl_send_case",
        approver="test_approver",
        auth=True,
        edited_body=None,
        feedback="approved",
    )

    assert result["status"] == "approved"
    stored = json.loads(email_path.read_text(encoding="utf-8"))
    assert stored["sent_via_ghl"] is True
    assert stored["status"] == "sent_via_ghl"
