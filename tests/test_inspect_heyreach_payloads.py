#!/usr/bin/env python3
"""Tests for scripts/inspect_heyreach_payloads.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from inspect_heyreach_payloads import analyze_events


def test_analyze_events_detects_real_schema_payload():
    events = [
        {"event_type": "UNKNOWN", "payload": {"eventType": "UNKNOWN"}},
        {
            "event_type": "MESSAGE_REPLY_RECEIVED",
            "payload": {
                "event_type": "message_reply_received",
                "lead": {"id": 123, "profile_url": "https://linkedin.com/in/test"},
                "campaign": {"id": 10, "name": "Test Campaign"},
                "sender": {"id": 7, "full_name": "Test Sender"},
                "message_text": "Interested",
            },
        },
    ]
    summary = analyze_events(events)
    assert summary["total_events"] == 2
    assert summary["real_schema_events"] == 1
    assert summary["unknown_only_events"] == 1
    assert summary["has_real_schema_payloads"] is True


def test_analyze_events_handles_empty_list():
    summary = analyze_events([])
    assert summary["total_events"] == 0
    assert summary["real_schema_events"] == 0
    assert summary["has_real_schema_payloads"] is False

