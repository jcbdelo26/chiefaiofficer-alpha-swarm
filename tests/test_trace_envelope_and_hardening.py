#!/usr/bin/env python3
"""
Focused tests for deterministic tracing and runtime hardening changes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.context_manager import ContextManager, Priority
from core.trace_envelope import emit_tool_trace
from core.unified_guardrails import ActionResult, HookSystem, UnifiedRateLimiter


def test_emit_tool_trace_envelope_required_fields(tmp_path: Path, monkeypatch):
    trace_file = tmp_path / "tool_traces.jsonl"
    monkeypatch.setenv("TRACE_ENVELOPE_FILE", str(trace_file))

    envelope = emit_tool_trace(
        correlation_id="corr-123",
        case_id="case-001",
        agent="GATEKEEPER",
        tool_name="UnifiedIntegrationGateway.execute:ghl.send_email",
        tool_input={"api_key": "secret", "subject": "Hello"},
        tool_output={"success": True},
        retrieved_context_refs=["lead_123"],
        status="success",
        duration_ms=12.34,
    )

    assert trace_file.exists()
    lines = trace_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    payload = json.loads(lines[0])
    required = {
        "correlation_id",
        "case_id",
        "agent",
        "tool_name",
        "tool_input_summary",
        "tool_output_summary",
        "retrieved_context_refs",
        "status",
        "duration_ms",
        "error_code",
        "error_message",
    }
    assert required.issubset(payload.keys())
    assert payload["correlation_id"] == "corr-123"
    assert payload["case_id"] == "case-001"
    assert "***REDACTED***" in payload["tool_input_summary"]
    assert envelope["tool_name"] == payload["tool_name"]


@pytest.mark.asyncio
async def test_hook_system_captures_post_hook_errors():
    hooks = HookSystem()
    context = {}

    def failing_post_hook(_context, _result):
        raise RuntimeError("post-hook failed")

    hooks.register_post_hook("failing", failing_post_hook)
    result = ActionResult(success=True, action_type="read_contact", agent="ENRICHER")

    await hooks.run_post_hooks(context, result)

    assert "hook_errors" in context
    assert any("failing" in msg for msg in context["hook_errors"])


def test_context_manager_save_restore_round_trip(tmp_path: Path):
    save_path = tmp_path / "context_state.json"

    manager = ContextManager(session_id="session-1", redis_url="")
    manager.add_context(
        content="important context",
        priority=Priority.HIGH,
        source="test",
        item_id="ctx_1",
    )
    manager.save_state(save_path)

    restored = ContextManager(session_id="session-2", redis_url="")
    assert restored.restore_state(save_path) is True
    assert restored.get_item("ctx_1") is not None


def test_rate_limiter_file_fallback_handles_corrupt_state(tmp_path: Path):
    storage_path = tmp_path / "rate_limits.json"
    storage_path.write_text("{invalid json", encoding="utf-8")

    limiter = UnifiedRateLimiter(storage_path=storage_path, redis_url="")
    allowed, reason = limiter.check_limit("agent_test")
    assert allowed is True
    assert reason is None

    limiter.record_action("agent_test")
    usage = limiter.get_usage("agent_test")
    assert usage["minute"]["used"] == 1
