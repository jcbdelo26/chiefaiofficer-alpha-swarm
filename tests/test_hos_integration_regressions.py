#!/usr/bin/env python3
"""
Regression tests for HoS integration hardening fixes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest


def test_followup_subject_variants_are_distinct():
    from execution.crafter_campaign import CampaignCrafter

    crafter = CampaignCrafter()
    lead = {
        "first_name": "Jane",
        "name": "Jane Doe",
        "email": "jane@example.com",
        "title": "CEO",
        "company": "Acme Corp",
        "industry": "marketing",
        "icp_tier": "tier_1",
    }

    sequence = crafter.generate_sequence(lead, "t1_executive_buyin")
    assert len(sequence) >= 3
    assert sequence[1].subject_a != sequence[1].subject_b
    assert sequence[2].subject_a != sequence[2].subject_b


def test_intent_plus_engagement_respects_20_point_cap():
    from execution.segmentor_classify import LeadSegmentor

    segmentor = LeadSegmentor()
    base_lead = {
        "title": "Director of Operations",
        "source_name": "test_source",
        "company": {
            "employee_count": 150,
            "industry": "manufacturing",
            "technologies": [],
        },
        "intent": {
            "website_visits": 12,
            "content_downloads": 5,
            "pricing_page_visits": 2,
            "demo_requested": True,
        },
    }

    high_intent_web = dict(base_lead, source_type="website_visitor")
    high_intent_social = dict(base_lead, source_type="post_commenter")

    score_web, breakdown_web, _, _ = segmentor.calculate_icp_score(high_intent_web)
    score_social, breakdown_social, _, _ = segmentor.calculate_icp_score(high_intent_social)

    assert breakdown_web["intent_signals"] <= 20
    assert breakdown_social["intent_signals"] <= 20
    # When intent already maxes the 20-point bucket, social engagement should not inflate score.
    assert score_web == score_social


def test_excluded_domain_guard_blocks_subdomains(monkeypatch, tmp_path: Path):
    from execution import instantly_dispatcher

    project_root = tmp_path
    config_dir = project_root / "config"
    shadow_dir = project_root / ".hive-mind" / "shadow_mode_emails"
    config_dir.mkdir(parents=True, exist_ok=True)
    shadow_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "guardrails": {
            "email_limits": {"daily_limit": 25},
            "deliverability": {
                "excluded_recipient_domains": ["jbcco.com"],
                "excluded_recipient_emails": [],
                "max_leads_per_domain_per_batch": 3,
            },
        },
        "external_apis": {"instantly": {"enabled": False}},
    }
    (config_dir / "production.json").write_text(json.dumps(config), encoding="utf-8")

    payload = {
        "email_id": "subdomain_case",
        "status": "approved",
        "to": "exec@sub.jbcco.com",
        "tier": "tier_1",
        "subject": "Test",
        "body": "Test",
    }
    (shadow_dir / "subdomain_case.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(instantly_dispatcher, "PROJECT_ROOT", project_root)
    dispatcher = instantly_dispatcher.InstantlyDispatcher()

    approved = dispatcher._load_approved_emails()
    assert approved == []


@dataclass
class _FakeCadenceStep:
    step: int
    day: int
    channel: str
    action: str


@dataclass
class _FakeCadenceAction:
    email: str
    step: _FakeCadenceStep
    lead_data: dict = field(default_factory=dict)


class _FakeCadenceEngine:
    def __init__(self):
        self.marked: list[tuple] = []

    def sync_signals(self):
        return {"exited": [], "paused": [], "connected": []}

    def get_due_actions(self):
        return [
            _FakeCadenceAction(
                email="dryrun@example.com",
                step=_FakeCadenceStep(step=1, day=1, channel="email", action="intro"),
                lead_data={},
            )
        ]

    def mark_step_done(self, email: str, step: int, status: str, metadata=None):
        self.marked.append((email, step, status, metadata or {}))


@pytest.mark.asyncio
async def test_dispatch_cadence_dry_run_has_no_state_side_effects(monkeypatch, tmp_path: Path):
    from execution import operator_outbound

    project_root = tmp_path
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "production.json").write_text(
        json.dumps(
            {
                "operator": {
                    "enabled": True,
                    "outbound": {
                        "email_daily_limit": 25,
                        "linkedin_warmup_start": date.today().isoformat(),
                        "linkedin_warmup_daily_limit": 5,
                        "linkedin_full_daily_limit": 20,
                        "linkedin_warmup_weeks": 4,
                    },
                    "revival": {"daily_limit": 5},
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(operator_outbound, "PROJECT_ROOT", project_root)
    monkeypatch.setenv("STATE_BACKEND", "file")

    operator = operator_outbound.OperatorOutbound()
    fake_cadence = _FakeCadenceEngine()
    state = operator_outbound.OperatorDailyState(date=date.today().isoformat())

    save_called = {"value": False}

    monkeypatch.setattr(operator, "_get_cadence_engine", lambda: fake_cadence)
    monkeypatch.setattr(operator, "_load_daily_state", lambda: state)
    monkeypatch.setattr(operator, "_save_daily_state", lambda _: save_called.__setitem__("value", True))

    report = await operator.dispatch_cadence(dry_run=True)

    assert report.cadence_dispatched == 1
    assert fake_cadence.marked == []
    assert save_called["value"] is False


@dataclass
class _TrackingInstantlyReport:
    run_id: str = "fake_instantly"
    started_at: str = "2026-02-18T00:00:00+00:00"
    completed_at: str = "2026-02-18T00:00:00+00:00"
    dry_run: bool = False
    total_approved: int = 0
    total_dispatched: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    campaigns_created: list = field(default_factory=list)
    daily_limit_remaining: int = 25
    errors: list[str] = field(default_factory=list)


class _TrackingInstantlyDispatcher:
    def __init__(self):
        self.called = False

    async def dispatch(self, **kwargs):
        self.called = True
        return _TrackingInstantlyReport(dry_run=kwargs.get("dry_run", False))


@dataclass
class _TrackingHeyReachReport:
    run_id: str = "fake_heyreach"
    started_at: str = "2026-02-18T00:00:00+00:00"
    completed_at: str = "2026-02-18T00:00:00+00:00"
    dry_run: bool = False
    total_approved: int = 0
    total_dispatched: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    lists_created: list = field(default_factory=list)
    daily_limit_remaining: int = 20
    errors: list[str] = field(default_factory=list)


class _TrackingHeyReachDispatcher:
    def __init__(self):
        self.called = False

    async def dispatch(self, **kwargs):
        self.called = True
        return _TrackingHeyReachReport(dry_run=kwargs.get("dry_run", False))


@pytest.mark.asyncio
async def test_emergency_stop_blocks_live_dispatch_before_channel_calls(monkeypatch, tmp_path: Path):
    from execution import operator_outbound

    project_root = tmp_path
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "production.json").write_text(
        json.dumps(
            {
                "operator": {
                    "enabled": True,
                    "gatekeeper_required": False,
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
                    "revival": {"daily_limit": 5, "enabled": True},
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(operator_outbound, "PROJECT_ROOT", project_root)
    monkeypatch.setenv("STATE_BACKEND", "file")
    monkeypatch.setenv("EMERGENCY_STOP", "true")

    operator = operator_outbound.OperatorOutbound()
    fake_instantly = _TrackingInstantlyDispatcher()
    fake_heyreach = _TrackingHeyReachDispatcher()
    monkeypatch.setattr(operator, "_get_instantly", lambda: fake_instantly)
    monkeypatch.setattr(operator, "_get_heyreach", lambda: fake_heyreach)

    report = await operator.dispatch_outbound(dry_run=False)

    assert any("EMERGENCY_STOP active" in err for err in report.errors)
    assert fake_instantly.called is False
    assert fake_heyreach.called is False


def test_excluded_email_guard_logs_structured_rejection(monkeypatch, tmp_path: Path):
    from execution import instantly_dispatcher

    project_root = tmp_path
    config_dir = project_root / "config"
    shadow_dir = project_root / ".hive-mind" / "shadow_mode_emails"
    config_dir.mkdir(parents=True, exist_ok=True)
    shadow_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "guardrails": {
            "email_limits": {"daily_limit": 25},
            "deliverability": {
                "excluded_recipient_domains": [],
                "excluded_recipient_emails": ["user@sub.customer.com"],
                "max_leads_per_domain_per_batch": 3,
                "require_valid_email_format": True,
            },
        },
        "external_apis": {"instantly": {"enabled": False}},
    }
    (config_dir / "production.json").write_text(json.dumps(config), encoding="utf-8")
    (shadow_dir / "excluded_email_case.json").write_text(
        json.dumps(
            {
                "email_id": "excluded_email_case",
                "status": "approved",
                "to": "user@sub.customer.com",
                "tier": "tier_1",
                "subject": "Test",
                "body": "Test",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(instantly_dispatcher, "PROJECT_ROOT", project_root)
    dispatcher = instantly_dispatcher.InstantlyDispatcher()

    approved = dispatcher._load_approved_emails()
    assert approved == []

    audit_log = project_root / ".hive-mind" / "audit" / "deliverability_guard_rejections.jsonl"
    assert audit_log.exists()
    entries = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(
        entry.get("reason_code") == "excluded_recipient_email"
        and entry.get("to_email") == "user@sub.customer.com"
        for entry in entries
    )


def test_heyreach_loader_excludes_sent_via_ghl(monkeypatch, tmp_path: Path):
    from execution import heyreach_dispatcher

    project_root = tmp_path
    config_dir = project_root / "config"
    shadow_dir = project_root / ".hive-mind" / "shadow_mode_emails"
    config_dir.mkdir(parents=True, exist_ok=True)
    shadow_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "production.json").write_text(
        json.dumps({"external_apis": {"heyreach": {"enabled": False}}}),
        encoding="utf-8",
    )

    (shadow_dir / "sent_via_ghl_case.json").write_text(
        json.dumps(
            {
                "email_id": "sent_via_ghl_case",
                "status": "dispatched_to_instantly",
                "sent_via_ghl": True,
                "to": "lead@example.com",
                "tier": "tier_1",
                "recipient_data": {
                    "name": "Lead Example",
                    "company": "Acme",
                    "linkedin_url": "https://linkedin.com/in/lead-example",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(heyreach_dispatcher, "PROJECT_ROOT", project_root)
    dispatcher = heyreach_dispatcher.HeyReachDispatcher()

    assert dispatcher._load_linkedin_eligible() == []
