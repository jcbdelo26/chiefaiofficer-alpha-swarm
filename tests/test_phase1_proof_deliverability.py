#!/usr/bin/env python3
"""
Phase-1 hardening tests:
- deterministic GHL send proof (webhook primary, poll fallback)
- deliverability guard fail-closed behavior
- dashboard approval status contract for proved sends
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_send_proof_resolves_from_webhook_evidence(tmp_path: Path):
    from core.ghl_send_proof import GHLSendProofEngine

    evidence_file = tmp_path / "ghl_webhook_events.jsonl"
    evidence_file.write_text(
        json.dumps(
            {
                "message_id": "msg-webhook-123",
                "contact_id": "contact_123",
                "to": "lead@example.com",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    engine = GHLSendProofEngine(
        proof_sla_seconds=30,
        poll_fallback_enabled=True,
        evidence_file=evidence_file,
    )

    class _FakeClient:
        async def get_email_stats(self, contact_id: str):
            return {"success": True, "message_count": 0, "emails": []}

    proof = await engine.resolve_proof(
        client=_FakeClient(),
        shadow_email_id="shadow_1",
        recipient_email="lead@example.com",
        contact_id="contact_123",
        send_result={"success": True, "message_id": "msg-webhook-123"},
    )

    assert proof["proof_status"] == "proved"
    assert proof["proof_source"] == "webhook"
    assert proof["proof_evidence_id"] == "msg-webhook-123"


@pytest.mark.asyncio
async def test_send_proof_falls_back_to_poll_when_webhook_missing(tmp_path: Path):
    from core.ghl_send_proof import GHLSendProofEngine

    engine = GHLSendProofEngine(
        proof_sla_seconds=10,
        poll_fallback_enabled=True,
        evidence_file=tmp_path / "missing.jsonl",
    )

    class _FakeClient:
        async def get_email_stats(self, contact_id: str):
            return {
                "success": True,
                "message_count": 1,
                "emails": [
                    {
                        "id": "poll_msg_1",
                        "to": "lead@example.com",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ],
            }

    proof = await engine.resolve_proof(
        client=_FakeClient(),
        shadow_email_id="shadow_2",
        recipient_email="lead@example.com",
        contact_id="contact_999",
        send_result={"success": True, "message_id": "msg-unknown"},
    )

    assert proof["proof_status"] == "proved"
    assert proof["proof_source"] == "poll"
    assert proof["proof_evidence_id"] == "poll_msg_1"


def test_deliverability_guard_blocks_suppressed_email(tmp_path: Path):
    from core.deliverability_guard import DeliverabilityGuard

    suppression_path = tmp_path / "suppressions.json"
    suppression_path.write_text(
        json.dumps({"suppressed_emails": ["blocked@example.com"]}),
        encoding="utf-8",
    )

    guard = DeliverabilityGuard(
        suppression_path=suppression_path,
        fail_closed=True,
    )
    verdict = guard.evaluate("blocked@example.com")

    assert verdict["allow_send"] is False
    assert verdict["risk_level"] == "high"
    assert "suppressed_recipient" in verdict["reasons"]
    assert verdict["recommended_tag"]


def test_deliverability_guard_blocks_recent_hard_bounce(tmp_path: Path, monkeypatch):
    from core.deliverability_guard import DeliverabilityGuard

    bounce_file = tmp_path / "ghl_webhook_events.jsonl"
    bounce_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_type": "email_bounced",
                        "email": "bounced@example.com",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
                json.dumps(
                    {
                        "event_type": "message_reply_received",
                        "email": "not-bounce@example.com",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DELIVERABILITY_BOUNCE_FILE", str(bounce_file))
    monkeypatch.setenv("DELIVERABILITY_BOUNCE_LOOKBACK_DAYS", "30")

    guard = DeliverabilityGuard(fail_closed=True)
    verdict = guard.evaluate("bounced@example.com")

    assert verdict["allow_send"] is False
    assert verdict["risk_level"] == "high"
    assert "recent_hard_bounce" in verdict["reasons"]


@pytest.mark.asyncio
async def test_dashboard_approval_sets_sent_proved_when_poll_finds_evidence(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("GHL_API_KEY", "test_key")
    monkeypatch.setenv("GHL_LOCATION_ID", "test_location")
    monkeypatch.setenv("DELIVERABILITY_FAIL_CLOSED", "true")
    monkeypatch.setenv("PROOF_POLL_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("PROOF_SLA_SECONDS", "20")

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "production.json").write_text(
        json.dumps(
            {
                "email_behavior": {"actually_send": True},
                "guardrails": {
                    "email_limits": {
                        "monthly_limit": 3000,
                        "daily_limit": 150,
                        "min_delay_seconds": 60,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    email_path = shadow_dir / "phase1_send.json"
    email_path.write_text(
        json.dumps(
            {
                "email_id": "phase1_send",
                "status": "pending",
                "to": "lead@example.com",
                "subject": "Subject",
                "body": "Body",
                "tier": "tier_1",
                "contact_id": "contact_123",
                "recipient_data": {"name": "Lead Example", "company": "Acme"},
            }
        ),
        encoding="utf-8",
    )

    class _FakeGHLClient:
        def __init__(self, api_key, location_id, config=None):
            self.api_key = api_key
            self.location_id = location_id

        async def send_email(self, contact_id, template):
            assert contact_id == "contact_123"
            return {"success": True, "message_id": "msg-proof-1"}

        async def get_email_stats(self, contact_id: str):
            return {
                "success": True,
                "message_count": 1,
                "emails": [
                    {
                        "id": "poll-evidence-1",
                        "to": "lead@example.com",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ],
            }

        async def close(self):
            return None

    monkeypatch.setattr(health_app, "GHLOutreachClient", _FakeGHLClient)

    result = await health_app.approve_email(
        email_id="phase1_send",
        approver="hos",
        auth=True,
        edited_body=None,
        feedback="approved",
    )

    assert result["status"] == "approved"
    assert "proved" in result["message"].lower()

    updated = json.loads(email_path.read_text(encoding="utf-8"))
    assert updated["sent_via_ghl"] is True
    assert updated["status"] == "sent_proved"
    assert updated["proof_status"] == "proved"
    assert updated["proof_source"] in {"webhook", "poll"}
