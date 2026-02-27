#!/usr/bin/env python3
"""
Feedback loop trace-envelope integration tests.
"""

from __future__ import annotations

import json
from pathlib import Path


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


def test_feedback_loop_emits_trace_envelope(monkeypatch, tmp_path: Path):
    from core.feedback_loop import FeedbackLoop

    monkeypatch.delenv("REDIS_URL", raising=False)
    trace_file = tmp_path / "traces" / "tool_trace_envelopes.jsonl"
    monkeypatch.setenv("TRACE_ENVELOPE_FILE", str(trace_file))

    loop = FeedbackLoop(storage_dir=tmp_path / "feedback_loop")
    event = loop.record_email_outcome(
        email_data={
            "to": "lead@example.com",
            "subject": "Subject",
            "proof_status": "proved",
            "proof_source": "poll",
            "deliverability_risk": "low",
            "deliverability_reasons": [],
            "tier": "tier_1",
            "angle": "t1_executive_buyin",
            "model_route": "sonnet-4.5",
        },
        outcome="sent_proved",
        action="approve_email",
        metadata={"email_id": "trace_case_1"},
    )

    assert event["outcome"] == "sent_proved"
    traces = _read_jsonl(trace_file)
    assert traces, "Expected feedback loop to emit at least one trace envelope"
    last = traces[-1]
    assert last["agent"] == "feedback_loop"
    assert last["tool_name"] == "record_email_outcome"
    assert last["status"] == "success"

