#!/usr/bin/env python3
"""
Gatekeeper snapshot integrity tests for OPERATOR batch execution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest


def _write_config(project_root: Path) -> None:
    config = {
        "operator": {
            "enabled": True,
            "gatekeeper_required": True,
            "batch_expiry_hours": 24,
            "outbound": {
                "email_daily_limit": 25,
                "linkedin_warmup_start": date.today().isoformat(),
                "linkedin_warmup_daily_limit": 5,
                "linkedin_full_daily_limit": 20,
                "linkedin_warmup_weeks": 4,
                "tier_channel_routing": {
                    "tier_1": ["instantly", "heyreach"],
                    "tier_2": ["instantly"],
                    "tier_3": ["instantly"],
                },
            },
            "revival": {"enabled": True, "daily_limit": 5},
        },
        "cadence": {
            "default_21day": {
                "steps": [],
                "exit_on": [],
                "pause_on": [],
            }
        },
    }
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "production.json").write_text(json.dumps(config), encoding="utf-8")


def _write_shadow_email(
    shadow_dir: Path,
    *,
    email_id: str,
    recipient_email: str,
    tier: str = "tier_1",
) -> None:
    payload = {
        "email_id": email_id,
        "status": "approved",
        "to": recipient_email,
        "tier": tier,
        "subject": f"Subject {email_id}",
        "body": f"Body {email_id}",
        "recipient_data": {
            "name": f"Lead {email_id}",
            "company": "Acme",
            "linkedin_url": f"https://linkedin.com/in/{email_id}",
        },
    }
    (shadow_dir / f"{email_id}.json").write_text(json.dumps(payload), encoding="utf-8")


@dataclass
class _FakeInstantlyCampaign:
    shadow_email_ids: list[str]
    recipient_emails: list[str]


@dataclass
class _FakeInstantlyReport:
    run_id: str
    started_at: str
    completed_at: str
    dry_run: bool
    total_approved: int
    total_dispatched: int
    total_skipped: int
    total_errors: int
    campaigns_created: list[_FakeInstantlyCampaign]
    daily_limit_remaining: int
    errors: list[str]


@dataclass
class _FakeHeyReachList:
    list_name: str
    list_id: str | None
    leads_added: int
    tier: str
    shadow_email_ids: list[str]
    status: str
    recipient_emails: list[str]
    error: str | None = None


@dataclass
class _FakeHeyReachReport:
    run_id: str
    started_at: str
    completed_at: str
    dry_run: bool
    total_approved: int
    total_dispatched: int
    total_skipped: int
    total_errors: int
    lists_created: list[_FakeHeyReachList]
    daily_limit_remaining: int
    errors: list[str]


class _FakeInstantlyDispatcher:
    def __init__(self):
        self.calls: list[list[str] | None] = []

    async def dispatch(self, **kwargs):
        approved_ids = kwargs.get("approved_shadow_email_ids")
        self.calls.append(list(approved_ids) if approved_ids is not None else None)
        scoped_ids = list(approved_ids or [])
        campaigns = [
            _FakeInstantlyCampaign(
                shadow_email_ids=[shadow_id],
                recipient_emails=[f"{shadow_id}@example.com"],
            )
            for shadow_id in scoped_ids
        ]
        return _FakeInstantlyReport(
            run_id="fake_instantly",
            started_at="2026-02-17T00:00:00+00:00",
            completed_at="2026-02-17T00:00:00+00:00",
            dry_run=kwargs.get("dry_run", True),
            total_approved=len(scoped_ids),
            total_dispatched=len(scoped_ids),
            total_skipped=0,
            total_errors=0,
            campaigns_created=campaigns,
            daily_limit_remaining=25,
            errors=[],
        )


class _FakeHeyReachDispatcher:
    def __init__(self):
        self.calls: list[list[str] | None] = []

    async def dispatch(self, **kwargs):
        approved_ids = kwargs.get("approved_shadow_email_ids")
        self.calls.append(list(approved_ids) if approved_ids is not None else None)
        scoped_ids = list(approved_ids or [])
        lists = [
            _FakeHeyReachList(
                list_name="fake_list",
                list_id="list_1",
                leads_added=len(scoped_ids),
                tier="tier_1",
                shadow_email_ids=scoped_ids,
                status="dispatched",
                recipient_emails=[f"{shadow_id}@example.com" for shadow_id in scoped_ids],
            )
        ] if scoped_ids else []
        return _FakeHeyReachReport(
            run_id="fake_heyreach",
            started_at="2026-02-17T00:00:00+00:00",
            completed_at="2026-02-17T00:00:00+00:00",
            dry_run=kwargs.get("dry_run", True),
            total_approved=len(scoped_ids),
            total_dispatched=len(scoped_ids),
            total_skipped=0,
            total_errors=0,
            lists_created=lists,
            daily_limit_remaining=20,
            errors=[],
        )


@pytest.mark.asyncio
async def test_approved_batch_executes_only_frozen_scope(monkeypatch, tmp_path: Path):
    from execution import operator_outbound

    project_root = tmp_path
    hive_dir = project_root / ".hive-mind"
    shadow_dir = hive_dir / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    _write_config(project_root)
    _write_shadow_email(shadow_dir, email_id="seed_1", recipient_email="seed1@example.com")
    _write_shadow_email(shadow_dir, email_id="seed_2", recipient_email="seed2@example.com")

    monkeypatch.setenv("STATE_BACKEND", "file")
    monkeypatch.setattr(operator_outbound, "PROJECT_ROOT", project_root)

    operator = operator_outbound.OperatorOutbound()
    fake_instantly = _FakeInstantlyDispatcher()
    fake_heyreach = _FakeHeyReachDispatcher()
    monkeypatch.setattr(operator, "_get_instantly", lambda: fake_instantly)
    monkeypatch.setattr(operator, "_get_heyreach", lambda: fake_heyreach)
    monkeypatch.setattr(operator, "_auto_enroll_to_cadence", lambda: 0)

    live_without_approval = await operator.dispatch_outbound(dry_run=False)
    assert live_without_approval.pending_approval is True
    assert live_without_approval.batch_id is not None
    assert fake_instantly.calls == []

    pending_batch = operator.get_pending_batch()
    assert pending_batch is not None
    frozen_email_ids = list(pending_batch.approved_shadow_email_ids)
    frozen_linkedin_ids = list(pending_batch.approved_linkedin_shadow_ids)
    assert frozen_email_ids == ["seed_1", "seed_2"]
    assert pending_batch.preview_hash
    assert pending_batch.expires_at

    approved_batch = operator.approve_batch(pending_batch.batch_id, approved_by="test")
    assert approved_batch.status == "approved"

    # Queue drift after approval: this new item must not be executed by the approved batch.
    _write_shadow_email(shadow_dir, email_id="drift_3", recipient_email="drift3@example.com")

    executed = await operator.dispatch_outbound(dry_run=False)
    assert executed.pending_approval is False
    assert executed.batch_id == pending_batch.batch_id
    assert fake_instantly.calls[-1] == frozen_email_ids
    assert fake_heyreach.calls[-1] == frozen_linkedin_ids
    assert executed.instantly_report["total_dispatched"] == len(frozen_email_ids)

    executed_payload = operator._state_store.get_batch(pending_batch.batch_id)
    assert executed_payload is not None
    assert executed_payload["status"] == "executed"
    assert executed_payload["execution_report"]["run_id"] == executed.run_id

    # Re-run cannot re-send the same approved batch; it creates a new pending review batch.
    second_live = await operator.dispatch_outbound(dry_run=False)
    assert second_live.pending_approval is True
    assert second_live.batch_id != pending_batch.batch_id
    assert len(fake_instantly.calls) == 1
