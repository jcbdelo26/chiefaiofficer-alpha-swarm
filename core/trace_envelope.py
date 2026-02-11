#!/usr/bin/env python3
"""
Structured trace envelope utilities for replay and diagnostics.

This module centralizes runtime traces with a normalized schema so
record/replay and deterministic evaluation can consume a single format.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
TRACE_DIR = PROJECT_ROOT / ".hive-mind" / "traces"
DEFAULT_TRACE_FILE = TRACE_DIR / "tool_trace_envelopes.jsonl"

_WRITE_LOCK = threading.Lock()
_correlation_id_var: ContextVar[Optional[str]] = ContextVar("trace_correlation_id", default=None)
_case_id_var: ContextVar[Optional[str]] = ContextVar("trace_case_id", default=None)

_SENSITIVE_KEY_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "cookie",
)


def _resolve_trace_file() -> Path:
    configured = os.getenv("TRACE_ENVELOPE_FILE")
    if configured:
        return Path(configured)
    return DEFAULT_TRACE_FILE


def set_current_correlation_id(correlation_id: str) -> Token:
    """Set request correlation id in async context."""
    return _correlation_id_var.set(correlation_id)


def reset_current_correlation_id(token: Token) -> None:
    """Reset request correlation id in async context."""
    _correlation_id_var.reset(token)


def get_current_correlation_id() -> Optional[str]:
    """Get request correlation id from async context."""
    return _correlation_id_var.get()


def set_current_case_id(case_id: str) -> Token:
    """Set replay case id in async context."""
    return _case_id_var.set(case_id)


def reset_current_case_id(token: Token) -> None:
    """Reset replay case id in async context."""
    _case_id_var.reset(token)


def get_current_case_id() -> Optional[str]:
    """Get replay case id from async context."""
    return _case_id_var.get()


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if any(fragment in key_lower for fragment in _SENSITIVE_KEY_FRAGMENTS):
                sanitized[str(key)] = "***REDACTED***"
            else:
                sanitized[str(key)] = _sanitize_payload(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_payload(v) for v in value[:50]]
    if isinstance(value, tuple):
        return [_sanitize_payload(v) for v in value[:50]]
    return value


def summarize_payload(payload: Any, max_chars: int = 500) -> str:
    """Create a sanitized compact payload summary."""
    try:
        sanitized = _sanitize_payload(payload)
        text = json.dumps(sanitized, ensure_ascii=False, default=str)
    except Exception:
        text = str(payload)

    if len(text) > max_chars:
        return f"{text[:max_chars]}...(truncated)"
    return text


def emit_tool_trace(
    *,
    agent: str,
    tool_name: str,
    tool_input: Any = None,
    tool_output: Any = None,
    retrieved_context_refs: Optional[List[Any]] = None,
    status: str,
    duration_ms: float,
    correlation_id: Optional[str] = None,
    case_id: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Emit a single normalized trace envelope.

    Required schema fields:
    - correlation_id
    - case_id
    - agent
    - tool_name
    - tool_input_summary
    - tool_output_summary
    - retrieved_context_refs
    - status
    - duration_ms
    - error_code
    - error_message
    """
    envelope = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id or get_current_correlation_id() or str(uuid4()),
        "case_id": case_id or get_current_case_id(),
        "agent": agent,
        "tool_name": tool_name,
        "tool_input_summary": summarize_payload(tool_input),
        "tool_output_summary": summarize_payload(tool_output),
        "retrieved_context_refs": [str(v) for v in (retrieved_context_refs or [])][:100],
        "status": status,
        "duration_ms": round(float(duration_ms), 3),
        "error_code": error_code,
        "error_message": error_message,
    }

    trace_file = _resolve_trace_file()
    trace_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with _WRITE_LOCK:
            with open(trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Failed to emit trace envelope to %s: %s", trace_file, exc)

    return envelope
