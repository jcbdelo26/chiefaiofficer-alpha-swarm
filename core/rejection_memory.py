#!/usr/bin/env python3
"""
Per-lead rejection memory store.

Tracks rejection history per lead email so the pipeline can:
- Block re-queuing leads that exceeded the rejection threshold
- Detect repeat drafts via content fingerprinting
- Provide per-lead rejection context to the CRAFTER

Storage: Redis (primary, shared across local + Railway) + filesystem (fallback).
Redis key: {CONTEXT_REDIS_PREFIX}:rejection_memory:{email_hash}
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("rejection_memory")

try:
    import redis as _redis_mod
except Exception:
    _redis_mod = None

PROJECT_ROOT = Path(__file__).parent.parent

# Defaults (overridable via env vars)
DEFAULT_TTL_DAYS = 30
DEFAULT_MAX_REJECTIONS = 2
DEFAULT_SUPPRESSION_WINDOW_DAYS = 7
DEFAULT_MAX_FEEDBACK_STORED = 5
DEFAULT_MAX_HASHES_STORED = 10


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _redis_prefix() -> str:
    return (os.getenv("CONTEXT_REDIS_PREFIX") or "caio").strip() or "caio"


def _get_ttl_days() -> int:
    try:
        return int(os.getenv("REJECTION_MEMORY_TTL_DAYS", str(DEFAULT_TTL_DAYS)))
    except (ValueError, TypeError):
        return DEFAULT_TTL_DAYS


def _get_max_rejections() -> int:
    try:
        return int(os.getenv("REJECTION_MEMORY_MAX_REJECTIONS", str(DEFAULT_MAX_REJECTIONS)))
    except (ValueError, TypeError):
        return DEFAULT_MAX_REJECTIONS


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _email_hash(email: str) -> str:
    return hashlib.sha256(_normalize_email(email).encode()).hexdigest()[:16]


def compute_draft_fingerprint(subject: str, body: str) -> str:
    """SHA-256 fingerprint of normalized draft content (first 500 chars of body)."""
    norm_body = re.sub(r"\s+", " ", (body or "")[:500]).strip().lower()
    norm_subject = re.sub(r"\s+", " ", (subject or "")).strip().lower()
    content = f"{norm_subject}||{norm_body}"
    return hashlib.sha256(content.encode()).hexdigest()[:32]


class RejectionMemory:
    """Per-lead rejection history with Redis primary + filesystem fallback."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or (PROJECT_ROOT / ".hive-mind" / "rejection_memory")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._redis = self._build_redis()

    def _build_redis(self):
        if _redis_mod is None:
            return None
        url = (os.getenv("REDIS_URL") or "").strip()
        if not url:
            return None
        try:
            client = _redis_mod.Redis.from_url(url, decode_responses=True, socket_timeout=3)
            client.ping()
            return client
        except Exception as exc:
            logger.warning("RejectionMemory Redis connect failed: %s", exc)
            return None

    def _redis_key(self, lead_email: str) -> str:
        return f"{_redis_prefix()}:rejection_memory:{_email_hash(lead_email)}"

    def _file_path(self, lead_email: str) -> Path:
        return self.storage_dir / f"{_email_hash(lead_email)}.json"

    # ── Write ──────────────────────────────────────────────────────

    def record_rejection(
        self,
        lead_email: str,
        rejection_tag: str,
        subject: str = "",
        body: str = "",
        feedback_text: str = "",
        template_id: str = "",
    ) -> Dict[str, Any]:
        """Record a rejection event for a lead. Returns the updated record."""
        lead_email = _normalize_email(lead_email)
        if not lead_email:
            return {}

        record = self.get_rejection_history(lead_email) or self._empty_record(lead_email)

        record["rejection_count"] += 1
        record["last_rejected_at"] = _utc_now().isoformat()

        # Append rejection tag (keep all within TTL window)
        if rejection_tag:
            record["rejection_tags"].append(rejection_tag)

        # Append rejected subject
        if subject and subject not in record["rejected_subjects"]:
            record["rejected_subjects"].append(subject)
            record["rejected_subjects"] = record["rejected_subjects"][-DEFAULT_MAX_HASHES_STORED:]

        # Append body fingerprint
        if body:
            fp = compute_draft_fingerprint(subject, body)
            if fp not in record["rejected_body_hashes"]:
                record["rejected_body_hashes"].append(fp)
                record["rejected_body_hashes"] = record["rejected_body_hashes"][-DEFAULT_MAX_HASHES_STORED:]

        # Append feedback text
        if feedback_text:
            record["feedback_texts"].append(feedback_text)
            record["feedback_texts"] = record["feedback_texts"][-DEFAULT_MAX_FEEDBACK_STORED:]

        # Track rejected template IDs
        if template_id:
            if template_id not in record.get("rejected_template_ids", []):
                record.setdefault("rejected_template_ids", []).append(template_id)

        record["updated_at"] = _utc_now().isoformat()

        self._persist(lead_email, record)
        return record

    def _persist(self, lead_email: str, record: Dict[str, Any]) -> None:
        """Write record to Redis + filesystem."""
        payload = json.dumps(record, ensure_ascii=False)
        ttl_seconds = _get_ttl_days() * 86400

        if self._redis:
            try:
                key = self._redis_key(lead_email)
                self._redis.set(key, payload, ex=ttl_seconds)
            except Exception as exc:
                logger.warning("RejectionMemory Redis write failed for %s: %s", lead_email, exc)

        try:
            fp = self._file_path(lead_email)
            fp.write_text(payload, encoding="utf-8")
        except Exception as exc:
            logger.warning("RejectionMemory file write failed for %s: %s", lead_email, exc)

    # ── Read ───────────────────────────────────────────────────────

    def get_rejection_history(self, lead_email: str) -> Optional[Dict[str, Any]]:
        """Retrieve rejection history for a lead. Returns None if no history."""
        lead_email = _normalize_email(lead_email)
        if not lead_email:
            return None

        record = None

        # Try Redis first
        if self._redis:
            try:
                raw = self._redis.get(self._redis_key(lead_email))
                if raw:
                    record = json.loads(raw)
            except Exception:
                pass

        # Filesystem fallback
        if record is None:
            fp = self._file_path(lead_email)
            if fp.exists():
                try:
                    record = json.loads(fp.read_text(encoding="utf-8"))
                except Exception:
                    pass

        if record is None:
            return None

        # Check TTL — discard stale records
        last_rejected = record.get("last_rejected_at", "")
        if last_rejected:
            try:
                last_dt = datetime.fromisoformat(last_rejected.replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                if _utc_now() - last_dt > timedelta(days=_get_ttl_days()):
                    return None
            except Exception:
                pass

        return record

    # ── Query helpers ──────────────────────────────────────────────

    def is_repeat_draft(self, lead_email: str, subject: str, body: str) -> bool:
        """Check if a draft's fingerprint matches any prior rejected draft."""
        record = self.get_rejection_history(lead_email)
        if not record:
            return False
        fp = compute_draft_fingerprint(subject, body)
        return fp in record.get("rejected_body_hashes", [])

    def should_block_lead(
        self,
        lead_email: str,
        has_new_evidence: bool = False,
    ) -> Tuple[bool, str]:
        """
        Determine if a lead should be blocked from re-queuing.

        Returns (should_block, reason).

        Rules:
        - >= max_rejections AND no new evidence → BLOCK
        - >= max_rejections BUT has new evidence → ALLOW (one more chance)
        - < max_rejections → ALLOW
        """
        record = self.get_rejection_history(lead_email)
        if not record:
            return False, ""

        max_rej = _get_max_rejections()
        count = record.get("rejection_count", 0)

        if count >= max_rej:
            if has_new_evidence:
                return False, ""
            return True, (
                f"Lead has {count} prior rejections (max {max_rej}). "
                f"Tags: {', '.join(record.get('rejection_tags', [])[-3:])}. "
                f"Blocked without new enrichment evidence."
            )

        return False, ""

    def get_rejected_template_ids(self, lead_email: str) -> List[str]:
        """Return template IDs previously rejected for this lead."""
        record = self.get_rejection_history(lead_email)
        if not record:
            return []
        return record.get("rejected_template_ids", [])

    def get_banned_subjects(self, lead_email: str) -> List[str]:
        """Return subjects previously rejected for this lead."""
        record = self.get_rejection_history(lead_email)
        if not record:
            return []
        return record.get("rejected_subjects", [])

    def get_feedback_context(self, lead_email: str) -> Dict[str, Any]:
        """Return a context dict suitable for injecting into CRAFTER template vars."""
        record = self.get_rejection_history(lead_email)
        if not record:
            return {}
        return {
            "rejection_count": record.get("rejection_count", 0),
            "rejection_tags": record.get("rejection_tags", []),
            "feedback_texts": record.get("feedback_texts", []),
            "rejected_subjects": record.get("rejected_subjects", []),
            "rejected_template_ids": record.get("rejected_template_ids", []),
        }

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _empty_record(lead_email: str) -> Dict[str, Any]:
        return {
            "lead_email": _normalize_email(lead_email),
            "rejection_count": 0,
            "last_rejected_at": "",
            "rejection_tags": [],
            "rejected_subjects": [],
            "rejected_body_hashes": [],
            "feedback_texts": [],
            "rejected_template_ids": [],
            "updated_at": "",
        }


# ── Module-level convenience functions ────────────────────────────

_default_instance: Optional[RejectionMemory] = None


def _get_default() -> RejectionMemory:
    global _default_instance
    if _default_instance is None:
        _default_instance = RejectionMemory()
    return _default_instance


def record_rejection(
    lead_email: str,
    rejection_tag: str,
    subject: str = "",
    body: str = "",
    feedback_text: str = "",
    template_id: str = "",
) -> Dict[str, Any]:
    return _get_default().record_rejection(
        lead_email, rejection_tag, subject, body, feedback_text, template_id,
    )


def get_rejection_history(lead_email: str) -> Optional[Dict[str, Any]]:
    return _get_default().get_rejection_history(lead_email)


def should_block_lead(lead_email: str, has_new_evidence: bool = False) -> Tuple[bool, str]:
    return _get_default().should_block_lead(lead_email, has_new_evidence)


def is_repeat_draft(lead_email: str, subject: str, body: str) -> bool:
    return _get_default().is_repeat_draft(lead_email, subject, body)
