#!/usr/bin/env python3
"""
Deterministic feedback loop storage for supervised learning tuples.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Optional
from uuid import uuid4

from core.trace_envelope import emit_tool_trace

try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None


PROJECT_ROOT = Path(__file__).parent.parent

REWARD_BY_OUTCOME = {
    "sent_proved": 1.0,
    "sent_unresolved": 0.2,
    "blocked_deliverability": -0.5,
    "approved": 0.3,
    "rejected": -0.6,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_parse_iso(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return _utc_now()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return _utc_now()


class FeedbackLoop:
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or (PROJECT_ROOT / ".hive-mind" / "feedback_loop")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.tuples_file = self.storage_dir / "training_tuples.jsonl"
        self.policy_dir = self.storage_dir / "policy_deltas"
        self.policy_dir.mkdir(parents=True, exist_ok=True)
        self.redis_prefix = (os.getenv("STATE_REDIS_PREFIX") or "caio").strip() or "caio"
        self.redis_client = self._build_redis_client()

    def _build_redis_client(self):
        if redis is None:
            return None
        redis_url = (os.getenv("REDIS_URL") or "").strip()
        if not redis_url:
            return None
        try:
            client = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=5)
            client.ping()
            return client
        except Exception:
            return None

    def record_email_outcome(
        self,
        email_data: Dict[str, Any],
        outcome: str,
        action: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        started = perf_counter()
        lead_email = str(email_data.get("to") or "").strip().lower()
        domain = lead_email.split("@", 1)[1] if "@" in lead_email else ""
        event = {
            "id": str(uuid4()),
            "timestamp": _utc_now().isoformat(),
            "action": action,
            "outcome": outcome,
            "reward": REWARD_BY_OUTCOME.get(outcome, 0.0),
            "lead_features": {
                "lead_email": lead_email,
                "lead_domain": domain,
                "tier": email_data.get("tier"),
                "angle": email_data.get("angle"),
                "company": (email_data.get("recipient_data") or {}).get("company"),
                "title": (email_data.get("recipient_data") or {}).get("title"),
            },
            "copy_features": {
                "subject": email_data.get("subject"),
                "template_version": email_data.get("template_version", "unknown"),
                "campaign_id": email_data.get("campaign_ref", {}).get("internal_id")
                if isinstance(email_data.get("campaign_ref"), dict)
                else None,
            },
            "routing": {
                "model_route": email_data.get("model_route"),
                "classifier": email_data.get("classifier"),
            },
            "evidence": {
                "proof_status": email_data.get("proof_status"),
                "proof_source": email_data.get("proof_source"),
                "proof_timestamp": email_data.get("proof_timestamp"),
                "proof_evidence_id": email_data.get("proof_evidence_id"),
                "deliverability_risk": email_data.get("deliverability_risk"),
                "deliverability_reasons": email_data.get("deliverability_reasons"),
                "rejection_tag": email_data.get("rejection_tag"),
                "feedback": email_data.get("feedback"),
            },
            "metadata": metadata or {},
        }
        try:
            self._append_event(event)
        except Exception as exc:
            self._emit_trace(
                status="failure",
                duration_ms=(perf_counter() - started) * 1000.0,
                tool_input={
                    "action": action,
                    "outcome": outcome,
                    "metadata": metadata or {},
                    "lead_email": lead_email,
                },
                tool_output={"error": str(exc)},
                error_code="FEEDBACK_RECORD_FAILED",
                error_message=str(exc),
            )
            raise

        self._emit_trace(
            status="success",
            duration_ms=(perf_counter() - started) * 1000.0,
            tool_input={
                "action": action,
                "outcome": outcome,
                "metadata": metadata or {},
                "lead_email": lead_email,
            },
            tool_output={
                "event_id": event["id"],
                "outcome": event["outcome"],
                "reward": event["reward"],
            },
        )
        return event

    def _append_event(self, event: Dict[str, Any]) -> None:
        with open(self.tuples_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

        if self.redis_client is None:
            return
        try:
            day_key = _utc_now().strftime("%Y-%m-%d")
            redis_key = f"{self.redis_prefix}:feedback:tuples:{day_key}"
            self.redis_client.rpush(redis_key, json.dumps(event, ensure_ascii=False))
            self.redis_client.expire(redis_key, 60 * 60 * 24 * 30)
        except Exception:
            return

    def build_policy_deltas(self, window_days: int = 7) -> Dict[str, Any]:
        cutoff = _utc_now() - timedelta(days=max(1, window_days))
        opener_rejections: Dict[str, int] = defaultdict(int)
        domain_blocks: Dict[str, int] = defaultdict(int)
        rejection_tags: Dict[str, int] = defaultdict(int)

        if self.tuples_file.exists():
            with open(self.tuples_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except Exception:
                        continue
                    ts = _safe_parse_iso(item.get("timestamp"))
                    if ts < cutoff:
                        continue

                    outcome = str(item.get("outcome") or "")
                    evidence = item.get("evidence") or {}
                    feedback = str(evidence.get("feedback") or "").strip().lower()
                    domain = str((item.get("lead_features") or {}).get("lead_domain") or "").strip().lower()
                    tag = str(evidence.get("rejection_tag") or "").strip().lower()

                    if outcome == "rejected" and feedback:
                        opener_rejections[feedback[:160]] += 1
                    if outcome == "blocked_deliverability" and domain:
                        domain_blocks[domain] += 1
                    if tag:
                        rejection_tags[tag] += 1

        delta = {
            "generated_at": _utc_now().isoformat(),
            "window_days": window_days,
            "opener_pattern_suppressions": sorted(
                [{"pattern": k, "count": v} for k, v in opener_rejections.items()],
                key=lambda x: x["count"],
                reverse=True,
            )[:20],
            "domain_risk_updates": sorted(
                [{"domain": k, "blocked_count": v} for k, v in domain_blocks.items()],
                key=lambda x: x["blocked_count"],
                reverse=True,
            )[:50],
            "rejection_tag_constraints": sorted(
                [{"tag": k, "count": v} for k, v in rejection_tags.items()],
                key=lambda x: x["count"],
                reverse=True,
            )[:50],
        }

        output_file = self.policy_dir / f"policy_delta_{_utc_now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(delta, f, indent=2, ensure_ascii=False)
        return delta

    def _emit_trace(
        self,
        *,
        status: str,
        duration_ms: float,
        tool_input: Dict[str, Any],
        tool_output: Dict[str, Any],
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        emit_tool_trace(
            agent="feedback_loop",
            tool_name="record_email_outcome",
            tool_input=tool_input,
            tool_output=tool_output,
            retrieved_context_refs=[],
            status=status,
            duration_ms=duration_ms,
            error_code=error_code,
            error_message=error_message,
        )
