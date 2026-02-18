#!/usr/bin/env python3
"""
Deterministic integration coverage for scheduler traces and queue lifecycle.
"""

from __future__ import annotations

import json
import importlib.util
from types import SimpleNamespace
from pathlib import Path

import pytest
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
        approver="head_of_sales",
        auth=True,
    )
    assert reject_result["status"] == "rejected"

    rejected_payload = json.loads(reject_email_path.read_text(encoding="utf-8"))
    assert rejected_payload["status"] == "rejected"
    assert rejected_payload["rejected_by"] == "head_of_sales"

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
    assert payload["_shadow_queue_debug"]["merged_count"] == 2


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
                "timestamp": "2026-02-18T12:00:00+00:00",
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
                "timestamp": "2026-02-18T11:30:00+00:00",
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
                "timestamp": "2026-02-18T11:00:00+00:00",
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
                "timestamp": "2026-01-01T11:00:00+00:00",
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
