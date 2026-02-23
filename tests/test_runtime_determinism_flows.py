#!/usr/bin/env python3
"""
Deterministic integration coverage for scheduler traces and queue lifecycle.
"""

from __future__ import annotations

import json
import importlib.util
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.responses import Response


def _disable_shadow_queue_redis(monkeypatch) -> None:
    from core import shadow_queue

    monkeypatch.setattr(shadow_queue, "_get_redis", lambda: None)


@pytest.mark.asyncio
async def test_inngest_gateway_helper_emits_trace(monkeypatch, tmp_path: Path):
    if importlib.util.find_spec("inngest") is None:
        pytest.skip("inngest package not available in this environment")

    from core import inngest_scheduler

    trace_file = tmp_path / "scheduler_traces.jsonl"
    monkeypatch.setenv("TRACE_ENVELOPE_FILE", str(trace_file))

    class FakeGateway:
        async def execute(self, integration, action, params, agent):
            assert integration == "ghl"
            assert action == "read_pipeline"
            assert agent == "SCHEDULER"
            return SimpleNamespace(
                success=True,
                data={"leads": [{"id": "lead_1"}]},
                error=None,
            )

    monkeypatch.setattr("core.unified_integration_gateway.get_gateway", lambda: FakeGateway())

    records = await inngest_scheduler.check_stale_leads()
    assert len(records) == 1
    assert records[0]["id"] == "lead_1"

    assert trace_file.exists()
    lines = [json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(line.get("tool_name") == "Inngest.ghl.read_pipeline" for line in lines)
    assert any(line.get("status") == "success" for line in lines)


@pytest.mark.asyncio
async def test_queue_lifecycle_has_consistent_audit_logs(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    _disable_shadow_queue_redis(monkeypatch)
    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)

    pending_email_path = shadow_dir / "email_001.json"
    pending_email_path.write_text(
        json.dumps(
            {
                "email_id": "email_001",
                "status": "pending",
                "to": "buyer@example.com",
                "subject": "Initial Subject",
                "body": "Initial Body",
                "tier": "tier_1",
                "angle": "ROI",
            }
        ),
        encoding="utf-8",
    )

    response = Response()
    pending = await health_app.get_pending_emails(response=response, auth=True)
    assert pending["count"] == 1
    assert "Schedule a call with CAIO" in pending["pending_emails"][0]["body"]
    assert "Reply STOP to unsubscribe." in pending["pending_emails"][0]["body"]
    assert "support@chiefaiofficer.com" in pending["pending_emails"][0]["body"]
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"

    approve_result = await health_app.approve_email(
        email_id="email_001",
        approver="head_of_sales",
        auth=True,
        edited_body="Edited body for send",
        feedback="Looks good.",
    )
    assert approve_result["status"] == "approved"

    approved_payload = json.loads(pending_email_path.read_text(encoding="utf-8"))
    assert approved_payload["status"] == "approved"
    assert approved_payload["approved_by"] == "head_of_sales"
    assert approved_payload["was_edited"] is True
    assert "Schedule a call with CAIO" in approved_payload["body"]
    assert "Reply STOP to unsubscribe." in approved_payload["body"]

    reject_email_path = shadow_dir / "email_002.json"
    reject_email_path.write_text(
        json.dumps(
            {
                "email_id": "email_002",
                "status": "pending",
                "to": "second@example.com",
                "subject": "Second Subject",
                "body": "Second Body",
                "tier": "tier_2",
                "angle": "Urgency",
            }
        ),
        encoding="utf-8",
    )

    reject_result = await health_app.reject_email(
        email_id="email_002",
        reason="Tone is too aggressive.",
        rejection_tag="tone_style_issue",
        approver="head_of_sales",
        auth=True,
    )
    assert reject_result["status"] == "rejected"

    rejected_payload = json.loads(reject_email_path.read_text(encoding="utf-8"))
    assert rejected_payload["status"] == "rejected"
    assert rejected_payload["rejected_by"] == "head_of_sales"
    assert rejected_payload["rejection_tag"] == "tone_style_issue"

    approval_audit = tmp_path / ".hive-mind" / "audit" / "email_approvals.jsonl"
    feedback_audit = tmp_path / ".hive-mind" / "audit" / "agent_feedback.jsonl"

    assert approval_audit.exists()
    assert feedback_audit.exists()

    approval_lines = [json.loads(line) for line in approval_audit.read_text(encoding="utf-8").splitlines() if line.strip()]
    feedback_lines = [json.loads(line) for line in feedback_audit.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert any(line.get("email_id") == "email_001" and line.get("action") == "approved" for line in approval_lines)
    assert any(line.get("email_id") == "email_002" and line.get("action") == "rejected" for line in approval_lines)
    assert any(line.get("email_id") == "email_001" and "approved" in line.get("action", "") for line in feedback_lines)
    assert any(line.get("email_id") == "email_002" and line.get("action") == "rejected" for line in feedback_lines)


@pytest.mark.asyncio
async def test_reject_email_requires_structured_rejection_tag(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    _disable_shadow_queue_redis(monkeypatch)
    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    (shadow_dir / "email_003.json").write_text(
        json.dumps(
            {
                "email_id": "email_003",
                "status": "pending",
                "to": "missingtag@example.com",
                "subject": "Needs reject tag",
                "body": "Body",
                "tier": "tier_1",
                "angle": "General",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HTTPException) as exc:
        await health_app.reject_email(
            email_id="email_003",
            reason="No structured tag selected",
            approver="head_of_sales",
            auth=True,
        )
    assert exc.value.status_code == 422
    assert "rejection_tag is required" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_rejection_tags_endpoint_exposes_backend_taxonomy(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    _disable_shadow_queue_redis(monkeypatch)
    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)

    payload = await health_app.get_rejection_tags(auth=True)
    assert isinstance(payload.get("tags"), list)
    ids = {entry.get("id") for entry in payload["tags"]}
    assert "tone_style_issue" in ids
    assert "queue_hygiene_non_actionable" in ids


@pytest.mark.asyncio
async def test_approve_email_auto_resolves_contact_before_live_send(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    _disable_shadow_queue_redis(monkeypatch)
    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "production.json").write_text(
        json.dumps(
            {
                "email_behavior": {"actually_send": True},
                "guardrails": {"email_limits": {"monthly_limit": 3000, "daily_limit": 150, "min_delay_seconds": 60}},
            }
        ),
        encoding="utf-8",
    )

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    email_path = shadow_dir / "email_live_001.json"
    email_path.write_text(
        json.dumps(
            {
                "email_id": "email_live_001",
                "status": "pending",
                "to": "vp.sales@example.com",
                "subject": "AI Roadmap",
                "body": "Hi there",
                "tier": "tier_1",
                "recipient_data": {"name": "Taylor Prospect", "company": "Acme Corp"},
                "synthetic": False,
            }
        ),
        encoding="utf-8",
    )

    class _FakeGHLClient:
        def __init__(self, api_key, location_id, config=None):
            self.api_key = api_key
            self.location_id = location_id
            self.config = config
            self.closed = False

        async def resolve_or_create_contact_by_email(self, **kwargs):
            assert kwargs.get("email") == "vp.sales@example.com"
            return {"success": True, "created": True, "contact_id": "contact_123", "contact": {"id": "contact_123"}}

        async def send_email(self, contact_id, template, personalization=None):
            assert contact_id == "contact_123"
            assert template.subject == "AI Roadmap"
            return {"success": True, "message_id": "msg_abc"}

        async def close(self):
            self.closed = True

    monkeypatch.setattr(health_app, "GHLOutreachClient", _FakeGHLClient)
    monkeypatch.setenv("GHL_API_KEY", "test_key")
    monkeypatch.setenv("GHL_LOCATION_ID", "test_location")

    result = await health_app.approve_email(
        email_id="email_live_001",
        approver="head_of_sales",
        auth=True,
        edited_body=None,
        feedback="approved_live",
    )

    assert result["status"] == "approved"
    assert result["message"] == "Email sent via GHL"

    updated = json.loads(email_path.read_text(encoding="utf-8"))
    assert updated["status"] == "sent_via_ghl"
    assert updated["contact_id"] == "contact_123"
    assert updated["sent_via_ghl"] is True
    assert updated["ghl_message_id"] == "msg_abc"
    assert updated["contact_resolution"]["resolved"] is True
    assert updated["contact_resolution"]["created"] is True


@pytest.mark.asyncio
async def test_approve_email_skips_non_dispatchable_training_even_when_live(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    _disable_shadow_queue_redis(monkeypatch)
    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "production.json").write_text(
        json.dumps(
            {
                "email_behavior": {"actually_send": True},
                "guardrails": {"email_limits": {"monthly_limit": 3000, "daily_limit": 150, "min_delay_seconds": 60}},
            }
        ),
        encoding="utf-8",
    )

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    email_path = shadow_dir / "email_canary_001.json"
    email_path.write_text(
        json.dumps(
            {
                "email_id": "email_canary_001",
                "status": "pending",
                "to": "trainer@canary-training.internal",
                "subject": "Canary training",
                "body": "Training body",
                "tier": "tier_1",
                "recipient_data": {"name": "Canary Trainer", "company": "Canary Co"},
                "synthetic": False,
                "canary": True,
                "canary_training": True,
                "_do_not_dispatch": True,
            }
        ),
        encoding="utf-8",
    )

    class _FakeGHLClient:
        def __init__(self, api_key, location_id, config=None):
            self.api_key = api_key
            self.location_id = location_id
            self.config = config

        async def resolve_or_create_contact_by_email(self, **kwargs):
            raise AssertionError("resolve_or_create_contact_by_email must not be called for non-dispatchable training cards")

        async def send_email(self, contact_id, template, personalization=None):
            raise AssertionError("send_email must not be called for non-dispatchable training cards")

        async def close(self):
            return None

    monkeypatch.setattr(health_app, "GHLOutreachClient", _FakeGHLClient)
    monkeypatch.setenv("GHL_API_KEY", "test_key")
    monkeypatch.setenv("GHL_LOCATION_ID", "test_location")

    result = await health_app.approve_email(
        email_id="email_canary_001",
        approver="head_of_sales",
        auth=True,
        edited_body=None,
        feedback="training_skip",
    )

    assert result["status"] == "approved"
    assert result["message"] == "Email approved (Training/Non-dispatchable skipped)"

    updated = json.loads(email_path.read_text(encoding="utf-8"))
    assert updated["status"] == "approved"
    assert updated["send_skipped_reason"] == "non_dispatchable_training"
    assert updated["sent_via_ghl"] is False


@pytest.mark.asyncio
async def test_pending_emails_syncs_gatekeeper_queue(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    _disable_shadow_queue_redis(monkeypatch)
    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("PENDING_QUEUE_MAX_AGE_HOURS", "0")
    monkeypatch.setenv("PENDING_QUEUE_ENFORCE_RAMP_TIER", "false")

    gatekeeper_dir = tmp_path / ".hive-mind" / "gatekeeper_queue"
    gatekeeper_dir.mkdir(parents=True, exist_ok=True)
    queue_item = gatekeeper_dir / "queue_123.json"
    queue_item.write_text(
        json.dumps(
            {
                "queue_id": "queue_123",
                "priority": "high",
                "created_at": "2026-02-10T12:00:00Z",
                "visitor": {
                    "email": "prospect@example.com",
                    "name": "Taylor Prospect",
                    "company": "Acme Corp",
                    "title": "VP Sales",
                },
                "email": {
                    "subject": "Quick intro",
                    "body": "Hi Taylor, wanted to connect about pipeline velocity.",
                },
                "context": {
                    "icp_tier": "tier_1",
                    "triggers": ["hiring_signal"],
                },
            }
        ),
        encoding="utf-8",
    )

    response = Response()
    payload = await health_app.get_pending_emails(response=response, auth=True)

    assert payload["count"] == 1
    assert payload["synced_from_gatekeeper"] == 1
    assert payload["pending_emails"][0]["email_id"] == "queue_123"
    assert payload["pending_emails"][0]["to"] == "prospect@example.com"
    assert payload["pending_emails"][0]["tier"] == "tier_1"
    assert payload["pending_emails"][0]["classifier"]["queue_origin"] == "gatekeeper_queue_sync"
    assert payload["pending_emails"][0]["classifier"]["message_direction"] == "outbound"
    assert payload["pending_emails"][0]["classifier"]["target_platform"] == "ghl"
    assert payload["pending_emails"][0]["campaign_ref"]["internal_id"] == ""

    shadow_file = tmp_path / ".hive-mind" / "shadow_mode_emails" / "queue_123.json"
    assert shadow_file.exists()
    shadow_data = json.loads(shadow_file.read_text(encoding="utf-8"))
    assert shadow_data["source"] == "gatekeeper_queue_sync"


@pytest.mark.asyncio
async def test_pending_emails_merges_filesystem_sync_when_redis_is_partial(monkeypatch, tmp_path: Path):
    from dashboard import health_app
    from core import shadow_queue

    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("PENDING_QUEUE_MAX_AGE_HOURS", "0")
    monkeypatch.setenv("PENDING_QUEUE_ENFORCE_RAMP_TIER", "false")
    monkeypatch.setenv("PENDING_QUEUE_ALWAYS_MERGE_FILES", "true")

    gatekeeper_dir = tmp_path / ".hive-mind" / "gatekeeper_queue"
    gatekeeper_dir.mkdir(parents=True, exist_ok=True)
    (gatekeeper_dir / "queue_disk.json").write_text(
        json.dumps(
            {
                "queue_id": "queue_disk",
                "priority": "medium",
                "created_at": "2026-02-10T13:00:00Z",
                "visitor": {"email": "disk@example.com", "name": "Disk Lead"},
                "email": {"subject": "Disk pending", "body": "Disk body"},
                "context": {"icp_tier": "tier_2", "triggers": ["intent"]},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(shadow_queue, "_get_redis", lambda: object())
    monkeypatch.setattr(shadow_queue, "_prefix", lambda: "caio:test")
    monkeypatch.setattr(
        shadow_queue,
        "list_pending",
        lambda limit=20, shadow_dir=None: [
            {
                "email_id": "queue_redis",
                "status": "pending",
                "to": "redis@example.com",
                "subject": "Redis pending",
                "body": "Redis body",
                "tier": "tier_1",
                "angle": "roi",
                "timestamp": "2026-02-10T14:00:00Z",
            }
        ],
    )

    response = Response()
    payload = await health_app.get_pending_emails(response=response, auth=True)

    ids = {item["email_id"] for item in payload["pending_emails"]}
    assert payload["count"] == 2
    assert ids == {"queue_redis", "queue_disk"}
    assert payload["synced_from_gatekeeper"] == 1
    assert payload["_shadow_queue_debug"]["filesystem_pending"] >= 1
    assert payload["_shadow_queue_debug"]["filesystem_merge_enabled"] is True
    assert payload["_shadow_queue_debug"]["merged_count"] == 2


@pytest.mark.asyncio
async def test_pending_emails_redis_first_skips_filesystem_merge_by_default(monkeypatch, tmp_path: Path):
    from dashboard import health_app
    from core import shadow_queue

    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("PENDING_QUEUE_MAX_AGE_HOURS", "0")
    monkeypatch.setenv("PENDING_QUEUE_ENFORCE_RAMP_TIER", "false")
    monkeypatch.delenv("PENDING_QUEUE_ALWAYS_MERGE_FILES", raising=False)

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    (shadow_dir / "disk_only.json").write_text(
        json.dumps(
            {
                "email_id": "disk_only",
                "status": "pending",
                "to": "disk@example.com",
                "subject": "Disk pending",
                "body": "Disk body",
                "tier": "tier_1",
                "timestamp": "2026-02-10T13:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(shadow_queue, "_get_redis", lambda: object())
    monkeypatch.setattr(shadow_queue, "_prefix", lambda: "caio:test")
    monkeypatch.setattr(
        shadow_queue,
        "list_pending",
        lambda limit=20, shadow_dir=None: [
            {
                "email_id": "queue_redis",
                "status": "pending",
                "to": "redis@example.com",
                "subject": "Redis pending",
                "body": "Redis body",
                "tier": "tier_1",
                "angle": "roi",
                "timestamp": "2026-02-10T14:00:00Z",
            }
        ],
    )

    response = Response()
    payload = await health_app.get_pending_emails(response=response, auth=True)

    ids = {item["email_id"] for item in payload["pending_emails"]}
    assert payload["count"] == 1
    assert ids == {"queue_redis"}
    assert payload["_shadow_queue_debug"]["filesystem_merge_enabled"] is False
    assert payload["_shadow_queue_debug"]["filesystem_pending"] == 0
    assert payload["_shadow_queue_debug"]["merged_count"] == 1


@pytest.mark.asyncio
async def test_pending_email_classifier_exposes_campaign_mapping(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    _disable_shadow_queue_redis(monkeypatch)
    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("PENDING_QUEUE_MAX_AGE_HOURS", "0")
    monkeypatch.setenv("PENDING_QUEUE_ENFORCE_RAMP_TIER", "false")

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    (shadow_dir / "pipeline_1.json").write_text(
        json.dumps(
            {
                "email_id": "pipeline_1",
                "status": "pending",
                "to": "ceo@example.com",
                "subject": "Roadmap",
                "body": "Hi there",
                "tier": "tier_1",
                "source": "pipeline",
                "direction": "outbound",
                "delivery_platform": "ghl",
                "context": {
                    "campaign_id": "camp_t1_abc",
                    "campaign_type": "t1_executive_buyin",
                    "campaign_name": "Tier 1 Executive Buy-in",
                    "pipeline_run_id": "run_123",
                },
                "timestamp": "2026-02-18T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    response = Response()
    payload = await health_app.get_pending_emails(response=response, auth=True)
    assert payload["count"] == 1
    item = payload["pending_emails"][0]
    assert item["classifier"]["queue_origin"] == "pipeline"
    assert item["classifier"]["message_direction"] == "outbound"
    assert item["classifier"]["target_platform"] == "ghl"
    assert item["classifier"]["target_platform_reason"] == "explicit_metadata"
    assert item["campaign_ref"]["internal_id"] == "camp_t1_abc"
    assert item["campaign_ref"]["internal_type"] == "t1_executive_buyin"
    assert item["campaign_ref"]["internal_name"] == "Tier 1 Executive Buy-in"
    assert item["campaign_ref"]["pipeline_run_id"] == "run_123"


@pytest.mark.asyncio
async def test_pending_emails_filters_non_actionable_items(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    _disable_shadow_queue_redis(monkeypatch)
    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("PENDING_QUEUE_ENFORCE_RAMP_TIER", "false")
    monkeypatch.setenv("PENDING_QUEUE_MAX_AGE_HOURS", "72")
    now = datetime.now(timezone.utc)
    ts_keep = now.isoformat()
    ts_dup = (now - timedelta(minutes=30)).isoformat()
    ts_placeholder = (now - timedelta(hours=1)).isoformat()
    ts_stale = (now - timedelta(days=10)).isoformat()

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)

    # Actionable (kept)
    (shadow_dir / "email_keep.json").write_text(
        json.dumps(
            {
                "email_id": "email_keep",
                "status": "pending",
                "to": "buyer@example.com",
                "subject": "Roadmap intro",
                "body": "Valid personalized body",
                "tier": "tier_1",
                "timestamp": ts_keep,
            }
        ),
        encoding="utf-8",
    )

    # Duplicate recipient+subject (excluded)
    (shadow_dir / "email_dup.json").write_text(
        json.dumps(
            {
                "email_id": "email_dup",
                "status": "pending",
                "to": "buyer@example.com",
                "subject": "Roadmap intro",
                "body": "Older duplicate body",
                "tier": "tier_1",
                "timestamp": ts_dup,
            }
        ),
        encoding="utf-8",
    )

    # Placeholder body (excluded)
    (shadow_dir / "email_placeholder.json").write_text(
        json.dumps(
            {
                "email_id": "email_placeholder",
                "status": "pending",
                "to": "placeholder@example.com",
                "subject": "Placeholder draft",
                "body": "No Body Content",
                "tier": "tier_1",
                "timestamp": ts_placeholder,
            }
        ),
        encoding="utf-8",
    )

    # Stale (excluded)
    (shadow_dir / "email_stale.json").write_text(
        json.dumps(
            {
                "email_id": "email_stale",
                "status": "pending",
                "to": "stale@example.com",
                "subject": "Very old draft",
                "body": "Looks valid but is too old",
                "tier": "tier_1",
                "timestamp": ts_stale,
            }
        ),
        encoding="utf-8",
    )

    response = Response()
    payload = await health_app.get_pending_emails(response=response, auth=True)

    assert payload["count"] == 1
    assert payload["pending_emails"][0]["email_id"] == "email_keep"

    debug = payload["_shadow_queue_debug"]
    assert debug["excluded_non_actionable_count"] == 3
    assert debug["excluded_non_actionable_reasons"]["duplicate_recipient_subject"] >= 1
    assert debug["excluded_non_actionable_reasons"]["placeholder_body"] >= 1
    assert debug["excluded_non_actionable_reasons"]["stale_gt_72h"] >= 1


@pytest.mark.asyncio
async def test_pending_emails_respects_active_ramp_tier_filter(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    class _FakeOperator:
        def get_status(self):
            return {"ramp": {"active": True, "tier_filter": "tier_1"}}

    _disable_shadow_queue_redis(monkeypatch)
    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(health_app, "_operator", _FakeOperator())
    monkeypatch.setenv("PENDING_QUEUE_ENFORCE_RAMP_TIER", "true")
    monkeypatch.setenv("PENDING_QUEUE_MAX_AGE_HOURS", "0")

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)

    (shadow_dir / "email_t1.json").write_text(
        json.dumps(
            {
                "email_id": "email_t1",
                "status": "pending",
                "to": "tier1@example.com",
                "subject": "Tier 1 draft",
                "body": "Tier 1 body",
                "tier": "tier_1",
                "timestamp": "2026-02-18T10:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (shadow_dir / "email_t2.json").write_text(
        json.dumps(
            {
                "email_id": "email_t2",
                "status": "pending",
                "to": "tier2@example.com",
                "subject": "Tier 2 draft",
                "body": "Tier 2 body",
                "tier": "tier_2",
                "timestamp": "2026-02-18T10:01:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    response = Response()
    payload = await health_app.get_pending_emails(response=response, auth=True)

    assert payload["count"] == 1
    assert payload["pending_emails"][0]["email_id"] == "email_t1"
    assert payload["_shadow_queue_debug"]["queue_tier_filter"] == "tier_1"
    assert payload["_shadow_queue_debug"]["excluded_non_actionable_reasons"]["tier_mismatch:tier_2"] >= 1


@pytest.mark.asyncio
async def test_pending_emails_excludes_non_dispatchable_training_by_default(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    _disable_shadow_queue_redis(monkeypatch)
    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("PENDING_QUEUE_ENFORCE_RAMP_TIER", "false")
    monkeypatch.setenv("PENDING_QUEUE_MAX_AGE_HOURS", "0")
    monkeypatch.setenv("PENDING_QUEUE_INCLUDE_NON_DISPATCHABLE", "false")

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)

    (shadow_dir / "email_live.json").write_text(
        json.dumps(
            {
                "email_id": "email_live",
                "status": "pending",
                "to": "live@example.com",
                "subject": "Live draft",
                "body": "Live body",
                "tier": "tier_1",
            }
        ),
        encoding="utf-8",
    )
    (shadow_dir / "email_canary.json").write_text(
        json.dumps(
            {
                "email_id": "email_canary",
                "status": "pending",
                "to": "trainer@canary-training.internal",
                "subject": "Training draft",
                "body": "Training body",
                "tier": "tier_1",
                "canary": True,
                "canary_training": True,
                "_do_not_dispatch": True,
                "context": {"source": "canary_lane_b"},
            }
        ),
        encoding="utf-8",
    )

    response = Response()
    payload = await health_app.get_pending_emails(response=response, auth=True)

    assert payload["count"] == 1
    assert payload["pending_emails"][0]["email_id"] == "email_live"
    reasons = payload["_shadow_queue_debug"]["excluded_non_actionable_reasons"]
    assert reasons["non_dispatchable:_do_not_dispatch"] >= 1


@pytest.mark.asyncio
async def test_pending_emails_can_include_non_dispatchable_training_when_requested(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    _disable_shadow_queue_redis(monkeypatch)
    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("PENDING_QUEUE_ENFORCE_RAMP_TIER", "false")
    monkeypatch.setenv("PENDING_QUEUE_MAX_AGE_HOURS", "0")
    monkeypatch.setenv("PENDING_QUEUE_INCLUDE_NON_DISPATCHABLE", "false")

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)

    (shadow_dir / "email_canary.json").write_text(
        json.dumps(
            {
                "email_id": "email_canary",
                "status": "pending",
                "to": "trainer@canary-training.internal",
                "subject": "Training draft",
                "body": "Training body",
                "tier": "tier_1",
                "canary": True,
                "canary_training": True,
                "_do_not_dispatch": True,
                "context": {"source": "canary_lane_b"},
            }
        ),
        encoding="utf-8",
    )

    response = Response()
    payload = await health_app.get_pending_emails(
        response=response,
        include_non_dispatchable=True,
        auth=True,
    )

    assert payload["count"] == 1
    item = payload["pending_emails"][0]
    assert item["email_id"] == "email_canary"
    assert item["classifier"]["queue_origin"] == "canary_lane_b"
    assert item["classifier"]["target_platform"] == "training"
    assert item["classifier"]["sync_state"] == "non_dispatchable_training"
    assert item["campaign_ref"]["internal_id"] == "canary_training"
    assert item["campaign_ref"]["internal_type"] == "canary_lane_b"
    assert payload["_shadow_queue_debug"]["include_non_dispatchable"] is True


@pytest.mark.asyncio
async def test_gatekeeper_sync_does_not_reopen_terminal_shadow_status(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    _disable_shadow_queue_redis(monkeypatch)
    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)

    gatekeeper_dir = tmp_path / ".hive-mind" / "gatekeeper_queue"
    gatekeeper_dir.mkdir(parents=True, exist_ok=True)
    (gatekeeper_dir / "queue_approved.json").write_text(
        json.dumps(
            {
                "queue_id": "queue_approved",
                "priority": "high",
                "created_at": "2026-02-10T12:00:00Z",
                "visitor": {"email": "approved@example.com", "name": "Approved Lead"},
                "email": {"subject": "Should stay approved", "body": "Body"},
                "context": {"icp_tier": "tier_1", "triggers": ["hiring_signal"]},
            }
        ),
        encoding="utf-8",
    )

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    (shadow_dir / "queue_approved.json").write_text(
        json.dumps(
            {
                "email_id": "queue_approved",
                "status": "approved",
                "to": "approved@example.com",
                "subject": "Approved already",
                "body": "Approved body",
            }
        ),
        encoding="utf-8",
    )

    response = Response()
    payload = await health_app.get_pending_emails(response=response, auth=True)

    assert payload["count"] == 0
    assert payload["synced_from_gatekeeper"] == 0
