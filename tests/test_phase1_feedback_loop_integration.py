#!/usr/bin/env python3
"""
Phase-1 feedback loop integration tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


@pytest.mark.asyncio
async def test_approve_records_blocked_deliverability_feedback_tuple(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("GHL_API_KEY", "test_key")
    monkeypatch.setenv("GHL_LOCATION_ID", "test_location")
    monkeypatch.setenv("DELIVERABILITY_FAIL_CLOSED", "true")

    suppression_file = tmp_path / "suppressions.json"
    suppression_file.write_text(
        json.dumps({"suppressed_emails": ["blocked@example.com"]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DELIVERABILITY_SUPPRESSION_FILE", str(suppression_file))

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "production.json").write_text(
        json.dumps({"email_behavior": {"actually_send": True}}),
        encoding="utf-8",
    )

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    email_path = shadow_dir / "blocked_case.json"
    email_path.write_text(
        json.dumps(
            {
                "email_id": "blocked_case",
                "status": "pending",
                "to": "blocked@example.com",
                "subject": "Subject",
                "body": "Body",
                "tier": "tier_1",
                "angle": "t1_executive_buyin",
                "recipient_data": {"name": "Blocked Lead", "company": "Acme"},
            }
        ),
        encoding="utf-8",
    )

    class _FakeGHLClient:
        def __init__(self, api_key, location_id, config=None):
            self.api_key = api_key
            self.location_id = location_id

        async def close(self):
            return None

    monkeypatch.setattr(health_app, "GHLOutreachClient", _FakeGHLClient)

    result = await health_app.approve_email(
        email_id="blocked_case",
        approver="hos",
        auth=True,
        edited_body=None,
        feedback="bad recipient",
    )

    assert result["status"] == "approved"
    assert "blocked" in result["message"].lower()

    tuples_file = tmp_path / ".hive-mind" / "feedback_loop" / "training_tuples.jsonl"
    tuples = _read_jsonl(tuples_file)
    assert tuples, "expected at least one feedback tuple after approval"
    last = tuples[-1]
    assert last["outcome"] == "blocked_deliverability"
    assert last["evidence"]["deliverability_risk"] == "high"
    assert last["lead_features"]["lead_email"] == "blocked@example.com"

    updated = json.loads(email_path.read_text(encoding="utf-8"))
    assert updated["status"] == "blocked_deliverability"


@pytest.mark.asyncio
async def test_reject_records_rejected_feedback_tuple(monkeypatch, tmp_path: Path):
    from dashboard import health_app

    monkeypatch.setattr(health_app, "PROJECT_ROOT", tmp_path)

    shadow_dir = tmp_path / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    email_path = shadow_dir / "reject_case.json"
    email_path.write_text(
        json.dumps(
            {
                "email_id": "reject_case",
                "status": "pending",
                "to": "lead@example.com",
                "subject": "Subject",
                "body": "Body",
                "tier": "tier_1",
                "angle": "t1_executive_buyin",
                "recipient_data": {"name": "Lead", "company": "Acme"},
            }
        ),
        encoding="utf-8",
    )

    result = await health_app.reject_email(
        email_id="reject_case",
        reason="personalization too generic",
        rejection_tag="personalization_mismatch",
        approver="hos",
        auth=True,
    )

    assert result["status"] == "rejected"
    assert result["rejection_tag"] == "personalization_mismatch"

    tuples_file = tmp_path / ".hive-mind" / "feedback_loop" / "training_tuples.jsonl"
    tuples = _read_jsonl(tuples_file)
    assert tuples, "expected at least one feedback tuple after rejection"
    last = tuples[-1]
    assert last["outcome"] == "rejected"
    assert last["evidence"]["rejection_tag"] == "personalization_mismatch"
    assert last["evidence"]["feedback"] == "personalization too generic"

    updated = json.loads(email_path.read_text(encoding="utf-8"))
    assert updated["status"] == "rejected"

