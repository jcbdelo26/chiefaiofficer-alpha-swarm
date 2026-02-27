#!/usr/bin/env python3
"""
Deterministic GHL send proof resolver.

Primary source:
- webhook evidence file (JSONL)

Fallback source:
- bounded poll via GHLOutreachClient.get_email_stats(...)
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_utc_iso(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return _utc_now_iso()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return _utc_now_iso()


def _normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


class GHLSendProofEngine:
    def __init__(
        self,
        proof_sla_seconds: int = 900,
        poll_fallback_enabled: bool = True,
        evidence_file: Optional[Path] = None,
    ):
        self.proof_sla_seconds = max(1, int(proof_sla_seconds))
        self.poll_fallback_enabled = bool(poll_fallback_enabled)
        default_file = Path(
            os.getenv("GHL_PROOF_EVIDENCE_FILE", ".hive-mind/ghl_webhook_events.jsonl")
        )
        self.evidence_file = Path(evidence_file) if evidence_file else default_file

    async def resolve_proof(
        self,
        client: Any,
        shadow_email_id: str,
        recipient_email: str,
        contact_id: str,
        send_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        recipient_email = _normalize_email(recipient_email)
        message_id = str((send_result or {}).get("message_id") or "").strip()

        webhook_proof = self._resolve_from_webhook(
            recipient_email=recipient_email,
            contact_id=contact_id,
            message_id=message_id,
        )
        if webhook_proof:
            return {
                "shadow_email_id": shadow_email_id,
                "proof_status": "proved",
                "proof_source": "webhook",
                "proof_timestamp": webhook_proof["proof_timestamp"],
                "proof_evidence_id": webhook_proof["proof_evidence_id"],
                "ghl_message_id": webhook_proof.get("ghl_message_id") or message_id or None,
            }

        if self.poll_fallback_enabled:
            poll_proof = await self._resolve_from_poll(
                client=client,
                recipient_email=recipient_email,
                contact_id=contact_id,
                message_id=message_id,
            )
            if poll_proof:
                return {
                    "shadow_email_id": shadow_email_id,
                    "proof_status": "proved",
                    "proof_source": "poll",
                    "proof_timestamp": poll_proof["proof_timestamp"],
                    "proof_evidence_id": poll_proof["proof_evidence_id"],
                    "ghl_message_id": poll_proof.get("ghl_message_id") or message_id or None,
                }

        return {
            "shadow_email_id": shadow_email_id,
            "proof_status": "unresolved",
            "proof_source": "none",
            "proof_timestamp": _utc_now_iso(),
            "proof_evidence_id": None,
            "ghl_message_id": message_id or None,
        }

    def _resolve_from_webhook(
        self,
        recipient_email: str,
        contact_id: str,
        message_id: str,
    ) -> Optional[Dict[str, str]]:
        for event in self._iter_webhook_events():
            event_message_id = str(event.get("message_id") or event.get("id") or "").strip()
            event_contact_id = str(event.get("contact_id") or "").strip()
            event_to = _normalize_email(event.get("to") or event.get("email"))

            by_message = bool(message_id and event_message_id and event_message_id == message_id)
            by_contact_and_recipient = bool(
                event_contact_id
                and contact_id
                and event_contact_id == contact_id
                and event_to
                and recipient_email
                and event_to == recipient_email
            )

            if not (by_message or by_contact_and_recipient):
                continue

            return {
                "proof_timestamp": _to_utc_iso(
                    event.get("timestamp") or event.get("created_at") or event.get("time")
                ),
                "proof_evidence_id": event_message_id or event.get("event_id") or event.get("id"),
                "ghl_message_id": event_message_id or None,
            }
        return None

    def _iter_webhook_events(self) -> Iterable[Dict[str, Any]]:
        if not self.evidence_file.exists():
            return []

        events: List[Dict[str, Any]] = []
        try:
            with open(self.evidence_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        parsed = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(parsed, dict):
                        events.append(parsed)
        except Exception:
            return []

        # Newest first improves match speed for recently sent messages.
        events.reverse()
        return events

    async def _resolve_from_poll(
        self,
        client: Any,
        recipient_email: str,
        contact_id: str,
        message_id: str,
    ) -> Optional[Dict[str, str]]:
        deadline = asyncio.get_running_loop().time() + min(self.proof_sla_seconds, 60)
        attempt = 0
        while asyncio.get_running_loop().time() < deadline:
            attempt += 1
            try:
                # Per-call timeout is capped to 30s by guardrail policy.
                stats = await asyncio.wait_for(
                    client.get_email_stats(contact_id),
                    timeout=30,
                )
            except Exception:
                stats = {}

            emails = self._extract_email_events(stats)
            for entry in emails:
                entry_to = _normalize_email(entry.get("to") or entry.get("email"))
                entry_id = str(
                    entry.get("id")
                    or entry.get("message_id")
                    or entry.get("task_id")
                    or ""
                ).strip()

                by_message = bool(message_id and entry_id and entry_id == message_id)
                by_recipient = bool(entry_to and recipient_email and entry_to == recipient_email)

                if by_message or by_recipient:
                    return {
                        "proof_timestamp": _to_utc_iso(
                            entry.get("timestamp")
                            or entry.get("created_at")
                            or entry.get("sent_at")
                        ),
                        "proof_evidence_id": entry_id or message_id or "poll_match",
                        "ghl_message_id": entry_id or None,
                    }

            # Keep fallback polling bounded and fast.
            if attempt >= 3:
                break
            await asyncio.sleep(1)

        return None

    def _extract_email_events(self, stats: Any) -> List[Dict[str, Any]]:
        if not isinstance(stats, dict):
            return []

        emails = stats.get("emails")
        if isinstance(emails, list):
            return [entry for entry in emails if isinstance(entry, dict)]

        messages = stats.get("messages")
        if isinstance(messages, list):
            normalized: List[Dict[str, Any]] = []
            for entry in messages:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("type") or "").lower() not in {"email", ""}:
                    continue
                normalized.append(entry)
            return normalized

        return []

