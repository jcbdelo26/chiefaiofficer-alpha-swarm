#!/usr/bin/env python3
"""
Pre-send deliverability guard.

Fail-closed for high-risk recipients when DELIVERABILITY_FAIL_CLOSED=true.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,63}$", re.IGNORECASE)

ROLE_LOCAL_PARTS = {
    "admin",
    "billing",
    "compliance",
    "contact",
    "finance",
    "hello",
    "hr",
    "info",
    "legal",
    "marketing",
    "noreply",
    "no-reply",
    "ops",
    "sales",
    "support",
    "team",
}

DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "guerrillamail.com",
    "10minutemail.com",
    "yopmail.com",
    "tempmail.com",
}


def _normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 365) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(minimum, min(maximum, value))


def _parse_utc(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class DeliverabilityGuard:
    def __init__(
        self,
        suppression_path: Optional[Path] = None,
        fail_closed: Optional[bool] = None,
    ):
        self.fail_closed = _env_bool("DELIVERABILITY_FAIL_CLOSED", True) if fail_closed is None else bool(fail_closed)
        default_path = Path(
            os.getenv("DELIVERABILITY_SUPPRESSION_FILE", ".hive-mind/suppressions.json")
        )
        default_bounce_file = Path(
            os.getenv("DELIVERABILITY_BOUNCE_FILE", ".hive-mind/ghl_webhook_events.jsonl")
        )
        self.suppression_path = Path(suppression_path) if suppression_path else default_path
        self.bounce_events_path = default_bounce_file
        self.bounce_lookback_days = _env_int("DELIVERABILITY_BOUNCE_LOOKBACK_DAYS", 30)
        self._suppressed = self._load_suppressed()

    def evaluate(self, email: str) -> Dict[str, Any]:
        recipient = _normalize_email(email)
        reasons: List[str] = []
        risk_level = "low"
        recent_hard_bounces = self._load_recent_hard_bounces()

        if not recipient or not EMAIL_RE.match(recipient):
            reasons.append("invalid_email_syntax")
            risk_level = "high"
            return self._build_verdict(recipient, risk_level, reasons)

        local, _, domain = recipient.partition("@")

        if recipient in self._suppressed:
            reasons.append("suppressed_recipient")
            risk_level = "high"

        if recipient in recent_hard_bounces:
            reasons.append("recent_hard_bounce")
            risk_level = "high"

        if local in ROLE_LOCAL_PARTS:
            reasons.append("role_mailbox")
            if risk_level != "high":
                risk_level = "medium"

        if domain in DISPOSABLE_DOMAINS:
            reasons.append("disposable_domain")
            risk_level = "high"

        if "." not in domain or domain.endswith(".local"):
            reasons.append("domain_format_suspicious")
            if risk_level == "low":
                risk_level = "medium"

        return self._build_verdict(recipient, risk_level, reasons)

    def _build_verdict(self, email: str, risk_level: str, reasons: List[str]) -> Dict[str, Any]:
        allow_send = not (self.fail_closed and risk_level == "high")
        recommended_tag = self._recommended_tag(reasons)
        return {
            "email": email,
            "risk_level": risk_level,
            "allow_send": allow_send,
            "reasons": reasons,
            "recommended_tag": recommended_tag,
        }

    def _recommended_tag(self, reasons: List[str]) -> str:
        if not reasons:
            return "other"
        if "suppressed_recipient" in reasons:
            return "compliance_issue"
        if "invalid_email_syntax" in reasons:
            return "placeholder_or_rendering_issue"
        if "role_mailbox" in reasons:
            return "icp_mismatch"
        if "disposable_domain" in reasons:
            return "compliance_issue"
        if "recent_hard_bounce" in reasons:
            return "compliance_issue"
        return "other"

    def _load_suppressed(self) -> Set[str]:
        suppressed: Set[str] = set()
        if not self.suppression_path.exists():
            return suppressed

        try:
            with open(self.suppression_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return suppressed

        values = payload.get("suppressed_emails") if isinstance(payload, dict) else None
        if isinstance(values, list):
            for value in values:
                normalized = _normalize_email(value)
                if normalized:
                    suppressed.add(normalized)
        return suppressed

    def _load_recent_hard_bounces(self) -> Set[str]:
        bounced: Set[str] = set()
        if not self.bounce_events_path.exists():
            return bounced

        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(days=self.bounce_lookback_days)
        try:
            with open(self.bounce_events_path, "r", encoding="utf-8") as f:
                for line in f:
                    row = line.strip()
                    if not row:
                        continue
                    try:
                        event = json.loads(row)
                    except Exception:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if not self._is_hard_bounce_event(event):
                        continue

                    ts = _parse_utc(
                        event.get("timestamp")
                        or event.get("created_at")
                        or event.get("event_timestamp")
                    )
                    if ts is not None and ts < cutoff:
                        continue

                    event_email = _normalize_email(
                        event.get("email")
                        or event.get("lead_email")
                        or event.get("recipient_email")
                        or event.get("to")
                    )
                    if event_email:
                        bounced.add(event_email)
        except Exception:
            return bounced
        return bounced

    @staticmethod
    def _is_hard_bounce_event(event: Dict[str, Any]) -> bool:
        event_type = str(
            event.get("event_type")
            or event.get("type")
            or event.get("event")
            or ""
        ).strip().lower()
        if "bounce" in event_type:
            return True

        bounce_type = str(event.get("bounce_type") or "").strip().lower()
        if bounce_type in {"hard", "hard_bounce", "permanent"}:
            return True
        return bool(event.get("is_bounced"))
