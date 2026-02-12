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

    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)

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

    shadow_file = tmp_path / ".hive-mind" / "shadow_mode_emails" / "queue_123.json"
    assert shadow_file.exists()
    shadow_data = json.loads(shadow_file.read_text(encoding="utf-8"))
    assert shadow_data["source"] == "gatekeeper_queue_sync"
