#!/usr/bin/env python3
"""
OPERATOR Agent — Unified Outbound Execution
=============================================
Single execution layer for all outbound channels:
  - Instantly (email campaigns, 25/day, 6 warmed domains)
  - HeyReach (LinkedIn automation, 5/day warmup → 20/day full)
  - GHL Revival (re-engage stale CRM contacts via warm domains)

Architecture:
    QUEEN (decides tier + channel) → GATEKEEPER (approves) → OPERATOR (executes)
        ├── dispatch_outbound()  → Instantly + HeyReach (new leads)
        ├── dispatch_revival()   → RevivalScanner + Instantly (stale GHL contacts)
        └── dispatch_all()       → both motions sequentially

Usage:
    python execution/operator_outbound.py --dry-run
    python execution/operator_outbound.py --live --motion outbound
    python execution/operator_outbound.py --status
"""

import os
import sys
import json
import uuid
import asyncio
import argparse
import platform
import logging
import hashlib
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, asdict, field

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from core.state_store import StateStore, normalize_email

_is_windows = platform.system() == "Windows"
console = Console(force_terminal=not _is_windows)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("operator_outbound")


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class WarmupSchedule:
    """Current daily limits based on warmup progression."""
    email_daily_limit: int
    linkedin_daily_limit: int
    linkedin_warmup_start: str
    linkedin_warmup_week: int
    is_linkedin_warmup: bool
    revival_daily_limit: int


@dataclass
class OperatorDailyState:
    """Tracks what OPERATOR has dispatched today. Resets daily."""
    date: str
    outbound_email_dispatched: int = 0
    outbound_linkedin_dispatched: int = 0
    revival_dispatched: int = 0
    cadence_dispatched: int = 0
    leads_dispatched: List[str] = field(default_factory=list)
    last_run_at: Optional[str] = None
    runs_today: int = 0


@dataclass
class OperatorReport:
    """Unified report from a dispatch run."""
    run_id: str
    started_at: str
    completed_at: str = ""
    dry_run: bool = True
    motion: str = "outbound"  # "outbound", "revival", "all"
    instantly_report: Optional[Dict] = None
    heyreach_report: Optional[Dict] = None
    revival_candidates_found: int = 0
    revival_dispatched: int = 0
    cadence_actions_due: int = 0
    cadence_dispatched: int = 0
    cadence_synced: Optional[Dict] = None
    cadence_auto_enrolled: int = 0
    warmup_schedule: Optional[Dict] = None
    errors: List[str] = field(default_factory=list)
    # Gatekeeper batch approval fields
    pending_approval: bool = False
    batch_id: Optional[str] = None


@dataclass
class DispatchBatch:
    """
    Gatekeeper approval batch — created when gatekeeper_required=true and
    OPERATOR is triggered in live mode. Must be approved before execution.
    """
    batch_id: str
    created_at: str
    motion: str               # "outbound", "cadence", "revival", "all"
    status: str = "pending"   # "pending", "approved", "rejected", "executed", "expired"
    warmup_schedule: Optional[Dict] = None
    leads_preview: List[Dict] = field(default_factory=list)
    total_email_leads: int = 0
    total_linkedin_leads: int = 0
    total_revival_candidates: int = 0
    total_cadence_due: int = 0
    tier_breakdown: Dict[str, int] = field(default_factory=dict)
    approved_shadow_email_ids: List[str] = field(default_factory=list)
    approved_linkedin_shadow_ids: List[str] = field(default_factory=list)
    approved_revival_emails: List[str] = field(default_factory=list)
    approved_cadence_actions: List[Dict[str, Any]] = field(default_factory=list)
    preview_hash: str = ""
    expires_at: Optional[str] = None
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    rejected_at: Optional[str] = None
    rejected_reason: Optional[str] = None
    executed_at: Optional[str] = None
    execution_report: Optional[Dict] = None


# =============================================================================
# OPERATOR AGENT
# =============================================================================

class OperatorOutbound:
    """
    Unified outbound execution agent.

    Orchestrates Instantly (email) + HeyReach (LinkedIn) + GHL Revival
    under warmup-aware volume limits with three-layer deduplication.

    Zero-args constructor required by UnifiedAgentRegistry.
    """

    def __init__(self):
        self._instantly = None
        self._heyreach = None
        self._signal_mgr = None
        self._timeline = None
        self._revival_scanner = None
        self._cadence_engine = None
        self._config: Dict = {}
        self._operator_config: Dict = {}
        self.hive_dir = PROJECT_ROOT / ".hive-mind"
        self._state_store = StateStore(hive_dir=self.hive_dir)
        self.state_file = self._state_store.operator_state_file
        self.dispatch_log = self.hive_dir / "operator_dispatch_log.jsonl"
        self.batch_dir = self._state_store.batch_dir
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.batch_dir.mkdir(parents=True, exist_ok=True)

        self._load_config()

    # -------------------------------------------------------------------------
    # Lazy initialization
    # -------------------------------------------------------------------------

    def _load_config(self):
        config_path = PROJECT_ROOT / "config" / "production.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
        self._operator_config = self._config.get("operator", {})

    def _get_instantly(self):
        if self._instantly is None:
            from execution.instantly_dispatcher import InstantlyDispatcher
            self._instantly = InstantlyDispatcher()
        return self._instantly

    def _get_heyreach(self):
        if self._heyreach is None:
            from execution.heyreach_dispatcher import HeyReachDispatcher
            self._heyreach = HeyReachDispatcher()
        return self._heyreach

    def _get_signal_manager(self):
        if self._signal_mgr is None:
            from core.lead_signals import LeadStatusManager
            self._signal_mgr = LeadStatusManager(hive_dir=PROJECT_ROOT / ".hive-mind")
        return self._signal_mgr

    def _get_timeline(self):
        if self._timeline is None:
            from core.activity_timeline import ActivityTimeline
            self._timeline = ActivityTimeline(hive_dir=PROJECT_ROOT / ".hive-mind")
        return self._timeline

    def _get_revival_scanner(self):
        if self._revival_scanner is None:
            from execution.operator_revival_scanner import RevivalScanner
            self._revival_scanner = RevivalScanner(hive_dir=PROJECT_ROOT / ".hive-mind")
        return self._revival_scanner

    def _get_cadence_engine(self):
        if self._cadence_engine is None:
            from execution.cadence_engine import CadenceEngine
            self._cadence_engine = CadenceEngine(hive_dir=PROJECT_ROOT / ".hive-mind")
        return self._cadence_engine

    # -------------------------------------------------------------------------
    # Ramp configuration (supervised go-live)
    # -------------------------------------------------------------------------

    @staticmethod
    def _report_live_dispatch_count(entry: Dict[str, Any]) -> int:
        """Best-effort dispatched volume extraction from an OperatorReport dict."""
        total = 0
        try:
            instantly = entry.get("instantly_report") or {}
            heyreach = entry.get("heyreach_report") or {}
            total += int(instantly.get("total_dispatched") or 0)
            total += int(heyreach.get("total_dispatched") or 0)
            total += int(entry.get("cadence_dispatched") or 0)
            total += int(entry.get("revival_dispatched") or 0)
        except Exception:
            return 0
        return total

    def _count_clean_supervised_days(
        self,
        *,
        required: int,
        lookback_days: int,
        min_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Count unique clean supervised live-send days from OPERATOR dispatch history.

        Clean day criteria:
        - report is live (`dry_run=False`)
        - report is not pending approval
        - report has no errors
        - report dispatched at least one action/email/message
        """
        clean_dates: Set[str] = set()
        today = date.today()
        cutoff = today - timedelta(days=max(0, lookback_days))

        for entry in self.get_dispatch_history(limit=2000):
            if not isinstance(entry, dict):
                continue
            if entry.get("dry_run", True):
                continue
            if entry.get("pending_approval"):
                continue
            if entry.get("errors"):
                continue
            if self._report_live_dispatch_count(entry) <= 0:
                continue

            stamp = entry.get("completed_at") or entry.get("started_at") or ""
            if not stamp:
                continue
            day_str = str(stamp)[:10]
            try:
                day_value = datetime.strptime(day_str, "%Y-%m-%d").date()
            except Exception:
                continue

            if day_value < cutoff:
                continue
            if min_date and day_value < min_date:
                continue

            clean_dates.add(day_str)
            if len(clean_dates) >= required:
                # No need to scan more once required threshold is reached.
                break

        ordered = sorted(clean_dates)
        return {
            "clean_days_completed": len(ordered),
            "clean_days_dates": ordered,
        }

    def _calendar_ramp_status(self, ramp_cfg: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """Backward-compatible date-window ramp behavior."""
        start_str = ramp_cfg.get("start_date", "")
        ramp_days = int(ramp_cfg.get("ramp_days", 3) or 3)

        if not start_str:
            return result

        try:
            start = datetime.strptime(start_str, "%Y-%m-%d").date()
            days_since = (date.today() - start).days

            if 0 <= days_since < ramp_days:
                result["active"] = True
                result["day"] = days_since + 1  # 1-indexed for display
                result["remaining_days"] = ramp_days - days_since
                result["email_limit_override"] = ramp_cfg.get("email_daily_limit_override", 5)
                result["tier_filter"] = ramp_cfg.get("tier_filter", "tier_1")
            elif days_since < 0:
                # Ramp hasn't started yet — still apply restrictions
                result["active"] = True
                result["day"] = 0
                result["remaining_days"] = ramp_days
                result["email_limit_override"] = ramp_cfg.get("email_daily_limit_override", 5)
                result["tier_filter"] = ramp_cfg.get("tier_filter", "tier_1")
        except ValueError:
            logger.warning("Invalid ramp start_date: %s", start_str)

        return result

    def _get_ramp_status(self) -> Dict[str, Any]:
        """
        Check if ramp mode is active.

        Ramp mode enforces reduced volume and tier restrictions during the
        first N supervised days of live sends (configured in production.json).

        Returns dict with: active (bool), day (int), remaining_days (int),
        email_limit_override (int), tier_filter (str).
        """
        ramp_cfg = self._operator_config.get("ramp", {})
        mode = str(ramp_cfg.get("mode") or "clean_days").strip().lower()
        result = {
            "enabled": ramp_cfg.get("enabled", False),
            "mode": mode,
            "active": False,
            "day": 0,
            "remaining_days": 0,
            "email_limit_override": None,
            "tier_filter": None,
            "clean_days_required": int(ramp_cfg.get("clean_days_required") or ramp_cfg.get("ramp_days") or 3),
            "clean_days_completed": 0,
            "clean_days_dates": [],
        }

        if not ramp_cfg.get("enabled", False):
            return result

        if mode in {"calendar", "date_window"}:
            return self._calendar_ramp_status(ramp_cfg, result)

        # Recommended mode: ramp remains active until N clean supervised LIVE days complete.
        required = max(1, int(ramp_cfg.get("clean_days_required") or ramp_cfg.get("ramp_days") or 3))
        lookback_days = max(1, int(ramp_cfg.get("clean_days_lookback_days") or 45))
        start_str = str(ramp_cfg.get("start_date") or "").strip()
        start_date: Optional[date] = None
        if start_str:
            try:
                start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            except ValueError:
                logger.warning("Invalid ramp start_date: %s", start_str)

        today = date.today()
        if start_date and today < start_date:
            # Not started yet: still enforce restrictive ramp limits.
            result["active"] = True
            result["day"] = 0
            result["remaining_days"] = required
            result["email_limit_override"] = ramp_cfg.get("email_daily_limit_override", 5)
            result["tier_filter"] = ramp_cfg.get("tier_filter", "tier_1")
            return result

        progress = self._count_clean_supervised_days(
            required=required,
            lookback_days=lookback_days,
            min_date=start_date,
        )
        completed = int(progress.get("clean_days_completed") or 0)
        result["clean_days_required"] = required
        result["clean_days_completed"] = completed
        result["clean_days_dates"] = progress.get("clean_days_dates") or []

        if completed < required:
            result["active"] = True
            result["day"] = completed + 1
            result["remaining_days"] = required - completed
            result["email_limit_override"] = ramp_cfg.get("email_daily_limit_override", 5)
            result["tier_filter"] = ramp_cfg.get("tier_filter", "tier_1")
        else:
            result["active"] = False
            result["day"] = required
            result["remaining_days"] = 0

        return result

    # -------------------------------------------------------------------------
    # Warmup schedule
    # -------------------------------------------------------------------------

    def get_warmup_schedule(self) -> WarmupSchedule:
        """Calculate current daily limits based on config warmup dates."""
        outbound_cfg = self._operator_config.get("outbound", {})
        revival_cfg = self._operator_config.get("revival", {})

        email_limit = outbound_cfg.get("email_daily_limit", 25)
        linkedin_warmup_start = outbound_cfg.get("linkedin_warmup_start", "")
        linkedin_warmup_limit = outbound_cfg.get("linkedin_warmup_daily_limit", 5)
        linkedin_full_limit = outbound_cfg.get("linkedin_full_daily_limit", 20)
        warmup_weeks = outbound_cfg.get("linkedin_warmup_weeks", 4)
        revival_limit = revival_cfg.get("daily_limit", 5)

        # Ramp override — reduce email limit during supervised go-live
        ramp = self._get_ramp_status()
        if ramp["active"] and ramp["email_limit_override"] is not None:
            email_limit = ramp["email_limit_override"]
            logger.info("Ramp active (day %d/%d): email limit overridden to %d/day",
                        ramp["day"], ramp["remaining_days"] + ramp["day"] - 1, email_limit)

        # Calculate LinkedIn warmup week
        is_warmup = True
        warmup_week = 0

        if linkedin_warmup_start:
            try:
                start = datetime.strptime(linkedin_warmup_start, "%Y-%m-%d").date()
                days_since = (date.today() - start).days
                warmup_week = max(0, days_since // 7)
                is_warmup = warmup_week < warmup_weeks
            except ValueError:
                logger.warning("Invalid linkedin_warmup_start date: %s", linkedin_warmup_start)

        linkedin_limit = linkedin_warmup_limit if is_warmup else linkedin_full_limit

        return WarmupSchedule(
            email_daily_limit=email_limit,
            linkedin_daily_limit=linkedin_limit,
            linkedin_warmup_start=linkedin_warmup_start,
            linkedin_warmup_week=warmup_week,
            is_linkedin_warmup=is_warmup,
            revival_daily_limit=revival_limit,
        )

    # -------------------------------------------------------------------------
    # Daily state
    # -------------------------------------------------------------------------

    def _load_daily_state(self) -> OperatorDailyState:
        """Load today's state, reset if date changed."""
        today = date.today().isoformat()
        data = self._state_store.get_operator_daily_state(today)
        if data:
            try:
                allowed = {
                    key: data.get(key)
                    for key in OperatorDailyState.__dataclass_fields__.keys()
                    if key in data
                }
                state = OperatorDailyState(**allowed)
                if self._migrate_legacy_dedup_entries(state):
                    self._save_daily_state(state)
                return state
            except TypeError:
                logger.warning("Invalid operator daily state payload found; resetting for %s", today)
        return OperatorDailyState(date=today)

    def _save_daily_state(self, state: OperatorDailyState):
        self._state_store.save_operator_daily_state(state.date, asdict(state))

    # -------------------------------------------------------------------------
    # Deduplication
    # -------------------------------------------------------------------------

    def _dedup_email_key(self, email: str) -> str:
        normalized = normalize_email(email)
        return f"email:{normalized}" if normalized else ""

    def _resolve_recipient_email_from_shadow_id(self, shadow_email_id: str) -> Optional[str]:
        shadow_id = (shadow_email_id or "").strip()
        if not shadow_id:
            return None
        shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
        if not shadow_dir.exists():
            return None

        direct_path = shadow_dir / f"{shadow_id}.json"
        if direct_path.exists():
            try:
                payload = json.loads(direct_path.read_text(encoding="utf-8"))
                return payload.get("to")
            except Exception:
                return None

        for path in shadow_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if payload.get("email_id") == shadow_id:
                return payload.get("to")
        return None

    def _migrate_legacy_dedup_entries(self, state: OperatorDailyState) -> bool:
        """Backfill canonical email dedup keys from legacy state entries."""
        changed = False
        existing_values = [str(v).strip() for v in (state.leads_dispatched or []) if str(v).strip()]
        dedup_set = {value.lower() for value in existing_values}
        to_add: Set[str] = set()

        for value in existing_values:
            lowered = value.lower()
            if lowered.startswith("email:"):
                continue
            if "@" in value:
                canonical = self._dedup_email_key(value)
                if canonical and canonical not in dedup_set:
                    to_add.add(canonical)
                continue

            resolved_email = self._resolve_recipient_email_from_shadow_id(value)
            canonical = self._dedup_email_key(resolved_email or "")
            if canonical and canonical not in dedup_set:
                to_add.add(canonical)

        if to_add:
            state.leads_dispatched.extend(sorted(to_add))
            changed = True
        return changed

    def _record_dispatched_email(self, state: OperatorDailyState, email: str):
        dedup_key = self._dedup_email_key(email)
        if not dedup_key:
            return
        existing = {str(v).strip().lower() for v in state.leads_dispatched if str(v).strip()}
        if dedup_key not in existing:
            state.leads_dispatched.append(dedup_key)

    def _is_lead_eligible(self, email: str, state: OperatorDailyState) -> bool:
        """Three-layer dedup check."""
        normalized_email = normalize_email(email)
        if not normalized_email:
            return False

        # Layer 1: Already dispatched today
        dedup_key = self._dedup_email_key(normalized_email)
        dispatched = {str(v).strip().lower() for v in state.leads_dispatched if str(v).strip()}
        if dedup_key in dispatched or normalized_email in dispatched:
            return False

        # Layer 2: Terminal or active status in signal loop
        mgr = self._get_signal_manager()
        status_record = mgr.get_lead_status(normalized_email)
        if status_record:
            status = status_record.get("status", "")
            terminal = {"bounced", "unsubscribed", "rejected", "disqualified"}
            if status in terminal:
                return False

        return True

    # -------------------------------------------------------------------------
    # Emergency stop
    # -------------------------------------------------------------------------

    def _check_emergency_stop(self) -> bool:
        return os.getenv("EMERGENCY_STOP", "false").lower().strip() in ("true", "1", "yes", "on")

    @property
    def gatekeeper_required(self) -> bool:
        return self._operator_config.get("gatekeeper_required", True)

    # -------------------------------------------------------------------------
    # GATEKEEPER batch approval
    # -------------------------------------------------------------------------

    def _batch_from_payload(self, data: Dict[str, Any]) -> DispatchBatch:
        return DispatchBatch(**{
            key: data.get(key)
            for key in DispatchBatch.__dataclass_fields__.keys()
            if key in data
        })

    def _get_batch_expiry_hours(self) -> int:
        return int(self._operator_config.get("batch_expiry_hours", 24) or 24)

    def _compute_batch_preview_hash(self, batch: DispatchBatch) -> str:
        scope_payload = {
            "motion": batch.motion,
            "approved_shadow_email_ids": sorted(batch.approved_shadow_email_ids),
            "approved_linkedin_shadow_ids": sorted(batch.approved_linkedin_shadow_ids),
            "approved_revival_emails": sorted(batch.approved_revival_emails),
            "approved_cadence_actions": sorted(
                [
                    {
                        "action_id": str(item.get("action_id", "")),
                        "email": normalize_email(item.get("email", "")),
                        "channel": str(item.get("channel", "")),
                        "step": int(item.get("step", 0) or 0),
                        "day": int(item.get("day", 0) or 0),
                    }
                    for item in (batch.approved_cadence_actions or [])
                ],
                key=lambda item: item["action_id"],
            ),
        }
        serialized = json.dumps(scope_payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _is_batch_expired(self, batch: DispatchBatch) -> bool:
        if not batch.expires_at:
            return False
        try:
            expires_at = datetime.fromisoformat(batch.expires_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > expires_at
        except ValueError:
            return False

    def _validate_batch_for_execution(self, batch: DispatchBatch, expected_motion: str) -> None:
        if batch.status != "approved":
            raise ValueError(f"Batch {batch.batch_id} is '{batch.status}', not approved")
        if not batch.preview_hash:
            raise ValueError(f"Batch {batch.batch_id} missing preview_hash")
        if not batch.expires_at:
            raise ValueError(f"Batch {batch.batch_id} missing expires_at")
        if batch.executed_at or (batch.execution_report and batch.execution_report.get("run_id")):
            raise ValueError(f"Batch {batch.batch_id} already executed")
        if self._is_batch_expired(batch):
            batch.status = "expired"
            self._state_store.save_batch(batch.batch_id, asdict(batch))
            raise ValueError(f"Batch {batch.batch_id} expired at {batch.expires_at}")
        if batch.motion not in {expected_motion, "all"}:
            raise ValueError(
                f"Batch {batch.batch_id} motion '{batch.motion}' incompatible with '{expected_motion}' execution"
            )
        expected_hash = self._compute_batch_preview_hash(batch)
        if batch.preview_hash and batch.preview_hash != expected_hash:
            raise ValueError(
                f"Batch {batch.batch_id} preview hash mismatch (expected={batch.preview_hash}, actual={expected_hash})"
            )

    def _load_shadow_candidates(self) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
        if not shadow_dir.exists():
            return candidates
        for path in sorted(shadow_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            email_id = payload.get("email_id") or path.stem
            payload["_shadow_email_id"] = str(email_id)
            payload["_shadow_file"] = str(path)
            candidates.append(payload)
        return candidates

    def _build_batch_preview(self, motion: str) -> DispatchBatch:
        """
        Build a preview of what OPERATOR would dispatch, for GATEKEEPER review.

        Scans approved shadow emails + cadence due actions + revival candidates
        without actually dispatching. Returns a DispatchBatch with lead previews.
        """
        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        batch = DispatchBatch(
            batch_id=batch_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            motion=motion,
            warmup_schedule=asdict(self.get_warmup_schedule()),
            expires_at=(
                datetime.now(timezone.utc) + timedelta(hours=self._get_batch_expiry_hours())
            ).isoformat(),
        )

        state = self._load_daily_state()
        schedule = self.get_warmup_schedule()
        routing = self._operator_config.get("outbound", {}).get("tier_channel_routing", {})

        # Ramp mode: auto-apply tier filter for batch preview
        ramp = self._get_ramp_status()
        ramp_tier_filter = ramp.get("tier_filter") if ramp["active"] else None

        # Preview outbound email leads (from approved shadow emails)
        if motion in ("outbound", "all"):
            tier_counts: Dict[str, int] = {}
            email_remaining = max(0, schedule.email_daily_limit - state.outbound_email_dispatched)
            linkedin_remaining = max(0, schedule.linkedin_daily_limit - state.outbound_linkedin_dispatched)

            email_scope: List[str] = []
            linkedin_scope: List[str] = []
            for data in self._load_shadow_candidates():
                status = data.get("status")
                if status != "approved":
                    continue
                if data.get("sent_via_ghl"):
                    continue
                # Canary / synthetic safety gate: never dispatch training emails
                if data.get("canary") or data.get("_do_not_dispatch") or data.get("synthetic"):
                    continue
                recipient_email = data.get("to", "")
                if not self._is_lead_eligible(recipient_email, state):
                    continue

                tier = data.get("tier", "tier_2")
                if ramp_tier_filter and tier != ramp_tier_filter:
                    continue

                shadow_email_id = str(data.get("_shadow_email_id") or "")
                recipient = data.get("recipient_data", {})
                tier_counts[tier] = tier_counts.get(tier, 0) + 1

                if len(email_scope) < email_remaining:
                    email_scope.append(shadow_email_id)
                    batch.leads_preview.append({
                        "email": recipient_email,
                        "name": recipient.get("name", ""),
                        "company": recipient.get("company", ""),
                        "tier": tier,
                        "channel": "email",
                        "shadow_email_id": shadow_email_id,
                    })

                if (
                    len(linkedin_scope) < linkedin_remaining
                    and "heyreach" in routing.get(tier, [])
                    and recipient.get("linkedin_url")
                ):
                    linkedin_scope.append(shadow_email_id)

            batch.approved_shadow_email_ids = email_scope
            batch.approved_linkedin_shadow_ids = linkedin_scope
            batch.total_email_leads = len(email_scope)
            batch.total_linkedin_leads = len(linkedin_scope)
            batch.tier_breakdown = tier_counts

        # Preview cadence actions due
        if motion in ("cadence", "all"):
            try:
                cadence = self._get_cadence_engine()
                due_actions = cadence.get_due_actions()
                action_scope: List[Dict[str, Any]] = []
                for action in due_actions:
                    if not self._is_lead_eligible(action.email, state):
                        continue
                    action_scope.append({
                        "action_id": (
                            f"{normalize_email(action.email)}|"
                            f"{action.step.channel}|s{action.step.step}|d{action.step.day}"
                        ),
                        "email": action.email,
                        "channel": action.step.channel,
                        "step": action.step.step,
                        "day": action.step.day,
                        "cadence_id": action.cadence_id,
                    })
                batch.approved_cadence_actions = action_scope
                batch.total_cadence_due = len(action_scope)
            except Exception as exc:
                logger.warning("Failed to build cadence batch preview: %s", exc)

        # Preview revival candidates
        if motion in ("revival", "all"):
            try:
                scanner = self._get_revival_scanner()
                candidates = scanner.scan(limit=schedule.revival_daily_limit)
                revival_scope: List[str] = []
                for candidate in candidates:
                    if not self._is_lead_eligible(candidate.email, state):
                        continue
                    revival_scope.append(normalize_email(candidate.email))
                batch.approved_revival_emails = revival_scope
                batch.total_revival_candidates = len(revival_scope)
            except Exception as exc:
                logger.warning("Failed to build revival batch preview: %s", exc)

        batch.preview_hash = self._compute_batch_preview_hash(batch)

        return batch

    def create_batch(self, motion: str = "all") -> DispatchBatch:
        """
        Create a dispatch batch for GATEKEEPER approval.

        Called when gatekeeper_required=true and live dispatch is requested.
        Saves batch to .hive-mind/operator_batches/ for dashboard review.
        """
        batch = self._build_batch_preview(motion)
        self._state_store.save_batch(batch.batch_id, asdict(batch))

        logger.info("Created dispatch batch %s for GATEKEEPER review (%d email, %d linkedin, %d revival, %d cadence)",
                     batch.batch_id, batch.total_email_leads, batch.total_linkedin_leads,
                     batch.total_revival_candidates, batch.total_cadence_due)

        # Slack alert
        try:
            from core.alerts import send_warning
            send_warning(
                f"OPERATOR batch ready for review: {batch.batch_id}\n"
                f"Email: {batch.total_email_leads}, LinkedIn: {batch.total_linkedin_leads}, "
                f"Revival: {batch.total_revival_candidates}, Cadence: {batch.total_cadence_due}\n"
                f"Approve via: POST /api/operator/approve-batch/{batch.batch_id}"
            )
        except Exception:
            pass

        return batch

    def approve_batch(self, batch_id: str, approved_by: str = "dashboard") -> DispatchBatch:
        """Mark a batch as approved for execution."""
        data = self._state_store.get_batch(batch_id)
        if not data:
            raise FileNotFoundError(f"Batch {batch_id} not found")

        if data["status"] != "pending":
            raise ValueError(f"Batch {batch_id} is '{data['status']}', not pending")

        data["status"] = "approved"
        data["approved_at"] = datetime.now(timezone.utc).isoformat()
        data["approved_by"] = approved_by
        self._state_store.save_batch(batch_id, data)

        logger.info("Batch %s approved by %s", batch_id, approved_by)
        return self._batch_from_payload(data)

    def reject_batch(self, batch_id: str, reason: str = "", rejected_by: str = "dashboard") -> DispatchBatch:
        """Reject a dispatch batch."""
        data = self._state_store.get_batch(batch_id)
        if not data:
            raise FileNotFoundError(f"Batch {batch_id} not found")

        data["status"] = "rejected"
        data["rejected_at"] = datetime.now(timezone.utc).isoformat()
        data["rejected_reason"] = reason or f"Rejected by {rejected_by}"
        self._state_store.save_batch(batch_id, data)

        logger.info("Batch %s rejected: %s", batch_id, reason)
        return self._batch_from_payload(data)

    def get_pending_batch(self) -> Optional[DispatchBatch]:
        """Get the most recent pending batch, if any."""
        batches = self._state_store.list_batches(status="pending")
        if not batches:
            return None
        return self._batch_from_payload(batches[0])

    def get_approved_batch(self) -> Optional[DispatchBatch]:
        """Get an approved batch waiting for execution."""
        batches = self._state_store.list_batches(status="approved")
        if not batches:
            return None
        return self._batch_from_payload(batches[0])

    def _mark_batch_executed(self, batch_id: str, report: OperatorReport):
        """Mark batch as executed after successful dispatch."""
        data = self._state_store.get_batch(batch_id)
        if not data:
            return
        if data.get("status") == "executed":
            logger.info("Batch %s already marked executed; skipping duplicate update", batch_id)
            return

        data["status"] = "executed"
        data["executed_at"] = datetime.now(timezone.utc).isoformat()
        data["execution_report"] = {
            "run_id": report.run_id,
            "motion": report.motion,
            "errors": report.errors,
        }
        self._state_store.save_batch(batch_id, data)

    def expire_stale_batches(self, max_age_hours: int = 24):
        """Expire pending batches using explicit expires_at (fallback to max_age_hours)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        for data in self._state_store.list_batches(status="pending"):
            batch_id = str(data.get("batch_id", "")).strip()
            if not batch_id:
                continue
            expired = False
            expires_at = data.get("expires_at")
            if expires_at:
                try:
                    expired = datetime.now(timezone.utc) > datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                except ValueError:
                    expired = False
            if not expired:
                try:
                    created = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
                    expired = created < cutoff
                except (ValueError, TypeError, KeyError):
                    expired = False
            if expired:
                data["status"] = "expired"
                data["expired_at"] = datetime.now(timezone.utc).isoformat()
                self._state_store.save_batch(batch_id, data)
                logger.info("Expired stale batch: %s", batch_id)

    # -------------------------------------------------------------------------
    # dispatch_outbound
    # -------------------------------------------------------------------------

    async def dispatch_outbound(
        self,
        tier_filter: Optional[str] = None,
        limit: Optional[int] = None,
        dry_run: bool = True,
        approved_batch: Optional[DispatchBatch] = None,
        skip_gatekeeper: bool = False,
        mark_batch_executed: bool = True,
    ) -> OperatorReport:
        """
        New outbound: approved shadow emails → Instantly + HeyReach.

        Sequential: Instantly first (email), then HeyReach (LinkedIn).
        Warmup-aware volume limits. Three-layer dedup.
        """
        run_id = f"op_out_{uuid.uuid4().hex[:8]}"
        report = OperatorReport(
            run_id=run_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            dry_run=dry_run,
            motion="outbound",
        )

        lock_token = None
        if not dry_run:
            lock_token = self._state_store.acquire_operator_lock("outbound", ttl_seconds=240)
            if not lock_token:
                report.errors.append("Another outbound dispatch is already running (distributed lock not acquired)")
                report.completed_at = datetime.now(timezone.utc).isoformat()
                return report

        # Safety
        try:
            if self._check_emergency_stop():
                report.errors.append("EMERGENCY_STOP active — all dispatch blocked")
                report.completed_at = datetime.now(timezone.utc).isoformat()
                return report

            if not self._operator_config.get("enabled", False) and not dry_run:
                report.errors.append("OPERATOR disabled in config/production.json")
                report.completed_at = datetime.now(timezone.utc).isoformat()
                return report

            # --- Ramp mode: enforce tier filter + reduced limits ---
            ramp = self._get_ramp_status()
            if ramp["active"]:
                if ramp["tier_filter"] and not tier_filter:
                    tier_filter = ramp["tier_filter"]
                    console.print(
                        f"[cyan]RAMP MODE[/cyan] Day {ramp['day']}: "
                        f"tier_filter={tier_filter}, email_limit={ramp['email_limit_override']}/day"
                    )

            # --- Gatekeeper batch approval gate ---
            effective_batch = approved_batch
            if not dry_run and self.gatekeeper_required and not skip_gatekeeper:
                if effective_batch is None:
                    effective_batch = self.get_approved_batch()
                if effective_batch and effective_batch.motion in ("outbound", "all"):
                    try:
                        self._validate_batch_for_execution(effective_batch, expected_motion="outbound")
                    except ValueError as exc:
                        report.errors.append(str(exc))
                        report.completed_at = datetime.now(timezone.utc).isoformat()
                        self._log_dispatch(report)
                        return report
                    logger.info("Executing approved batch: %s", effective_batch.batch_id)
                    report.batch_id = effective_batch.batch_id
                else:
                    # No approved batch -> create one for review
                    batch = self.create_batch(motion="outbound")
                    report.pending_approval = True
                    report.batch_id = batch.batch_id
                    report.errors.append(
                        f"GATEKEEPER: Batch {batch.batch_id} created for review. "
                        f"Approve via POST /api/operator/approve-batch/{batch.batch_id}"
                    )
                    console.print(
                        f"[yellow]GATEKEEPER GATE:[/yellow] Batch {batch.batch_id} requires approval.\n"
                        f"  Email leads: {batch.total_email_leads}, LinkedIn: {batch.total_linkedin_leads}\n"
                        f"  Approve: POST /api/operator/approve-batch/{batch.batch_id}"
                    )
                    report.completed_at = datetime.now(timezone.utc).isoformat()
                    self._log_dispatch(report)
                    return report
            elif effective_batch:
                try:
                    self._validate_batch_for_execution(effective_batch, expected_motion="outbound")
                except ValueError as exc:
                    report.errors.append(str(exc))
                    report.completed_at = datetime.now(timezone.utc).isoformat()
                    self._log_dispatch(report)
                    return report
                report.batch_id = effective_batch.batch_id

            schedule = self.get_warmup_schedule()
            report.warmup_schedule = asdict(schedule)
            state = self._load_daily_state()

            approved_shadow_email_ids: Optional[List[str]] = None
            approved_linkedin_shadow_ids: Optional[List[str]] = None
            if effective_batch:
                approved_shadow_email_ids = list(effective_batch.approved_shadow_email_ids or [])
                approved_linkedin_shadow_ids = list(effective_batch.approved_linkedin_shadow_ids or [])

            # --- Step 1: Instantly dispatch (email) ---
            try:
                instantly = self._get_instantly()
                email_remaining = max(0, schedule.email_daily_limit - state.outbound_email_dispatched)

                if email_remaining > 0:
                    instantly_report = await instantly.dispatch(
                        tier_filter=tier_filter,
                        limit=min(limit, email_remaining) if limit else email_remaining,
                        dry_run=dry_run,
                        approved_shadow_email_ids=approved_shadow_email_ids,
                    )
                    report.instantly_report = asdict(instantly_report)

                    # Track dispatched leads (skip in dry-run to avoid state pollution)
                    if not dry_run:
                        dispatched_count = instantly_report.total_dispatched
                        state.outbound_email_dispatched += dispatched_count

                        # Record dispatched lead recipient emails for dedup
                        for campaign in instantly_report.campaigns_created:
                            recipient_emails = list(getattr(campaign, "recipient_emails", []) or [])
                            if not recipient_emails:
                                for shadow_id in getattr(campaign, "shadow_email_ids", []):
                                    resolved = self._resolve_recipient_email_from_shadow_id(str(shadow_id))
                                    if resolved:
                                        recipient_emails.append(resolved)
                            for recipient_email in recipient_emails:
                                self._record_dispatched_email(state, recipient_email)
                else:
                    report.errors.append(
                        f"Email daily limit reached ({state.outbound_email_dispatched}/{schedule.email_daily_limit})"
                    )
            except Exception as e:
                report.errors.append(f"Instantly dispatch error: {e}")
                logger.error("Instantly dispatch error: %s", e)

            # --- Step 2: HeyReach dispatch (LinkedIn) ---
            try:
                # Check tier routing — only dispatch to HeyReach if tier is routed there
                routing = self._operator_config.get("outbound", {}).get("tier_channel_routing", {})
                heyreach_tiers = [t for t, channels in routing.items() if "heyreach" in channels]

                heyreach_filter = tier_filter
                if tier_filter and tier_filter not in heyreach_tiers:
                    logger.info("Tier %s not routed to HeyReach, skipping", tier_filter)
                else:
                    heyreach = self._get_heyreach()
                    linkedin_remaining = max(0, schedule.linkedin_daily_limit - state.outbound_linkedin_dispatched)

                    if linkedin_remaining > 0:
                        heyreach_report = await heyreach.dispatch(
                            tier_filter=heyreach_filter,
                            limit=min(limit, linkedin_remaining) if limit else linkedin_remaining,
                            dry_run=dry_run,
                            approved_shadow_email_ids=approved_linkedin_shadow_ids,
                        )
                        report.heyreach_report = asdict(heyreach_report)

                        if not dry_run:
                            dispatched_count = heyreach_report.total_dispatched
                            state.outbound_linkedin_dispatched += dispatched_count
                            for list_result in heyreach_report.lists_created:
                                recipient_emails = list(getattr(list_result, "recipient_emails", []) or [])
                                if not recipient_emails:
                                    for shadow_id in getattr(list_result, "shadow_email_ids", []):
                                        resolved = self._resolve_recipient_email_from_shadow_id(str(shadow_id))
                                        if resolved:
                                            recipient_emails.append(resolved)
                                for recipient_email in recipient_emails:
                                    self._record_dispatched_email(state, recipient_email)
                    else:
                        report.errors.append(
                            f"LinkedIn daily limit reached ({state.outbound_linkedin_dispatched}/{schedule.linkedin_daily_limit})"
                        )
            except Exception as e:
                report.errors.append(f"HeyReach dispatch error: {e}")
                logger.error("HeyReach dispatch error: %s", e)

            # --- XS-01: Partial dispatch detection ---
            if not dry_run:
                self._check_partial_dispatch(report)

            # --- Step 3: Auto-enroll dispatched leads into cadence ---
            if not dry_run:
                try:
                    enrolled = self._auto_enroll_to_cadence()
                    if enrolled > 0:
                        console.print(f"  [cyan]Cadence auto-enroll:[/cyan] {enrolled} leads enrolled")
                        report.cadence_auto_enrolled = enrolled
                except Exception as e:
                    report.errors.append(f"Cadence auto-enroll error: {e}")
                    logger.error("Cadence auto-enroll error: %s", e)

            # XS-04: Verify lock still held before saving state
            if lock_token and not self._state_store.verify_operator_lock("outbound", lock_token):
                report.errors.append(
                    "XS-04: Lock expired before state save — state NOT updated. "
                    "Dispatch may have succeeded but counts are stale."
                )
                logger.error("XS-04: Lock expired mid-dispatch for outbound run %s", report.run_id)
            else:
                # Update state only while lock is confirmed held
                state.last_run_at = datetime.now(timezone.utc).isoformat()
                state.runs_today += 1
                self._save_daily_state(state)

            report.completed_at = datetime.now(timezone.utc).isoformat()
            self._log_dispatch(report)

            # Mark batch as executed if we were processing an approved batch
            if mark_batch_executed and report.batch_id and not report.pending_approval:
                self._mark_batch_executed(report.batch_id, report)

            return report
        finally:
            if lock_token:
                self._state_store.release_operator_lock("outbound", lock_token)

    # -------------------------------------------------------------------------
    # XS-01: Partial dispatch detection
    # -------------------------------------------------------------------------

    @staticmethod
    def _check_partial_dispatch(report: "OperatorReport") -> bool:
        """
        Detect when one channel dispatched successfully while the other failed.
        Appends XS-01 error to report and sends Slack alert.
        Returns True if partial dispatch was detected.
        """
        instantly_dispatched = (report.instantly_report or {}).get("total_dispatched", 0)
        heyreach_dispatched = (report.heyreach_report or {}).get("total_dispatched", 0)
        instantly_failed = any("Instantly dispatch error:" in e for e in report.errors)
        heyreach_failed = any("HeyReach dispatch error:" in e for e in report.errors)

        if (instantly_dispatched > 0 and heyreach_failed) or \
           (heyreach_dispatched > 0 and instantly_failed):
            ok_channel = "Instantly" if instantly_dispatched > 0 else "HeyReach"
            failed_channel = "HeyReach" if instantly_dispatched > 0 else "Instantly"
            compensation_msg = (
                f"PARTIAL DISPATCH: {ok_channel} succeeded ({instantly_dispatched} email, "
                f"{heyreach_dispatched} linkedin) but {failed_channel} failed. "
                f"Affected leads may have incomplete cadence coverage."
            )
            report.errors.append(f"XS-01: {compensation_msg}")
            logger.warning("XS-01: %s", compensation_msg)

            try:
                from core.alerts import send_warning
                send_warning(
                    "Partial Dispatch Detected (XS-01)",
                    compensation_msg,
                    metadata={
                        "instantly_dispatched": instantly_dispatched,
                        "heyreach_dispatched": heyreach_dispatched,
                        "run_id": report.run_id,
                    },
                    source="operator_outbound",
                )
            except ImportError:
                pass
            return True
        return False

    # -------------------------------------------------------------------------
    # Auto-enroll dispatched leads into cadence
    # -------------------------------------------------------------------------

    def _auto_enroll_to_cadence(self) -> int:
        """
        Scan shadow emails for newly dispatched leads and enroll them in cadence.

        Called after dispatch_outbound(). Reads shadow email files that have
        been dispatched to outreach channels (Instantly/HeyReach) and
        enrolls them into the default 21-day cadence if not already enrolled.

        Returns count of newly enrolled leads.
        """
        shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
        if not shadow_dir.exists():
            return 0

        cadence = self._get_cadence_engine()
        enrolled_count = 0

        for email_file in shadow_dir.glob("*.json"):
            try:
                with open(email_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Only process emails dispatched to first-touch outreach channels
                if data.get("status") not in {"dispatched_to_instantly", "dispatched_to_heyreach"}:
                    continue

                # Skip if already enrolled flag set
                if data.get("cadence_enrolled"):
                    continue

                recipient_email = data.get("to", "")
                if not recipient_email:
                    continue

                tier = data.get("tier", "tier_2")
                recipient = data.get("recipient_data", {})
                linkedin_url = recipient.get("linkedin_url", "")
                context = data.get("context", {})

                lead_data = {
                    "first_name": recipient.get("name", "").split()[0] if recipient.get("name") else "",
                    "last_name": " ".join(recipient.get("name", "").split()[1:]) if recipient.get("name") else "",
                    "company": recipient.get("company", ""),
                    "title": recipient.get("title", ""),
                    "source_type": context.get("campaign_type", ""),
                    "icp_score": context.get("icp_score", 0),
                }

                # Enroll (idempotent — skips if already active)
                state = cadence.enroll(
                    email=recipient_email,
                    tier=tier,
                    linkedin_url=linkedin_url,
                    lead_data=lead_data,
                )

                if state.current_step == 1 and not state.steps_completed:
                    # Newly enrolled — mark shadow email to prevent re-processing
                    data["cadence_enrolled"] = True
                    data["cadence_enrolled_at"] = datetime.now(timezone.utc).isoformat()
                    with open(email_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    enrolled_count += 1

            except (json.JSONDecodeError, IOError, OSError) as e:
                logger.warning("Failed to process %s for cadence enrollment: %s", email_file.name, e)

        if enrolled_count > 0:
            logger.info("Auto-enrolled %d leads into cadence", enrolled_count)

        return enrolled_count

    # -------------------------------------------------------------------------
    # Save cadence follow-up email as shadow file
    # -------------------------------------------------------------------------

    def _save_cadence_email(self, action, followup_copy: Dict):
        """Save CRAFTER-generated cadence follow-up as a shadow email for review."""
        shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
        shadow_dir.mkdir(parents=True, exist_ok=True)

        email_id = f"cadence_s{action.step.step}_d{action.step.day}_{uuid.uuid4().hex[:6]}"
        filepath = shadow_dir / f"{email_id}.json"

        shadow_data = {
            "email_id": email_id,
            "to": action.email,
            "subject": followup_copy.get("subject", ""),
            "body": followup_copy.get("body", ""),
            "status": "pending_review",
            "source": "cadence_engine",
            "cadence_step": action.step.step,
            "cadence_day": action.step.day,
            "cadence_action": action.step.action,
            "cadence_id": action.cadence_id,
            "tier": action.tier,
            "recipient_data": action.lead_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(shadow_data, f, indent=2, ensure_ascii=False)
            logger.info("Saved cadence follow-up email: %s", filepath.name)
        except OSError as e:
            logger.error("Failed to save cadence email %s: %s", email_id, e)

    # -------------------------------------------------------------------------
    # dispatch_revival
    # -------------------------------------------------------------------------

    async def dispatch_revival(
        self,
        limit: Optional[int] = None,
        dry_run: bool = True,
        approved_revival_emails: Optional[List[str]] = None,
    ) -> OperatorReport:
        """
        GHL Revival: scan stale contacts → build context → dispatch re-engagement.

        Uses GHL cached contacts, scores by revival priority, dispatches
        via warm domains (chiefai.ai, NOT cold outreach domains).
        """
        run_id = f"op_rev_{uuid.uuid4().hex[:8]}"
        report = OperatorReport(
            run_id=run_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            dry_run=dry_run,
            motion="revival",
        )

        lock_token = None
        if not dry_run:
            lock_token = self._state_store.acquire_operator_lock("revival", ttl_seconds=180)
            if not lock_token:
                report.errors.append("Another revival dispatch is already running (distributed lock not acquired)")
                report.completed_at = datetime.now(timezone.utc).isoformat()
                return report

        try:
            if self._check_emergency_stop():
                report.errors.append("EMERGENCY_STOP active — revival blocked")
                report.completed_at = datetime.now(timezone.utc).isoformat()
                return report

            revival_cfg = self._operator_config.get("revival", {})
            if not revival_cfg.get("enabled", False) and not dry_run:
                report.errors.append("Revival disabled in config")
                report.completed_at = datetime.now(timezone.utc).isoformat()
                return report

            schedule = self.get_warmup_schedule()
            report.warmup_schedule = asdict(schedule)
            state = self._load_daily_state()

            revival_remaining = max(0, schedule.revival_daily_limit - state.revival_dispatched)
            scan_limit = min(limit or revival_remaining, revival_remaining)

            if scan_limit <= 0:
                report.errors.append(
                    f"Revival daily limit reached ({state.revival_dispatched}/{schedule.revival_daily_limit})"
                )
                report.completed_at = datetime.now(timezone.utc).isoformat()
                return report

            # Scan for candidates
            try:
                scanner = self._get_revival_scanner()
                candidates = scanner.scan(limit=scan_limit)
                allowed_revival = {
                    normalize_email(email) for email in (approved_revival_emails or []) if normalize_email(email)
                }
                if allowed_revival:
                    candidates = [
                        candidate for candidate in candidates
                        if normalize_email(candidate.email) in allowed_revival
                    ]
                report.revival_candidates_found = len(candidates)

                if not candidates:
                    logger.info("No revival candidates found")
                    report.completed_at = datetime.now(timezone.utc).isoformat()
                    return report

                console.print(f"[cyan]Revival scan:[/cyan] {len(candidates)} candidates found")

                # Filter through dedup
                eligible = [
                    c for c in candidates
                    if self._is_lead_eligible(c.email, state)
                ]

                if not eligible:
                    logger.info("All revival candidates filtered by dedup")
                    report.completed_at = datetime.now(timezone.utc).isoformat()
                    return report

                if dry_run:
                    for c in eligible:
                        console.print(
                            f"  [yellow][DRY RUN][/yellow] Would revive: {c.email} "
                            f"(score={c.revival_score:.2f}, reason={c.revival_reason}, "
                            f"inactive={c.days_inactive}d)"
                        )
                    report.revival_dispatched = len(eligible)
                else:
                    # Mark as revival_queued in signal loop
                    mgr = self._get_signal_manager()
                    dispatched = 0

                    for c in eligible:
                        try:
                            mgr.update_lead_status(
                                c.email, "revival_queued",
                                "operator:revival_scan",
                                {
                                    "revival_score": c.revival_score,
                                    "revival_reason": c.revival_reason,
                                    "days_inactive": c.days_inactive,
                                    "pipeline_stage": c.pipeline_stage,
                                },
                            )
                            self._record_dispatched_email(state, c.email)
                            dispatched += 1

                            console.print(
                                f"  [green]Queued revival:[/green] {c.email} "
                                f"(score={c.revival_score:.2f}, {c.revival_reason})"
                            )
                        except Exception as e:
                            report.errors.append(f"Revival queue error for {c.email}: {e}")
                            logger.error("Revival queue error: %s", e)

                    state.revival_dispatched += dispatched
                    report.revival_dispatched = dispatched

                    # Slack notification
                    try:
                        from core.alerts import send_info
                        send_info(
                            f"OPERATOR Revival: {dispatched} leads queued",
                            f"Scanned GHL cache, found {len(candidates)} candidates, "
                            f"queued {dispatched} for re-engagement.",
                            source="operator_outbound",
                        )
                    except ImportError:
                        pass

            except Exception as e:
                report.errors.append(f"Revival scan error: {e}")
                logger.error("Revival scan error: %s", e)

            # XS-04: Verify lock still held before saving state
            if lock_token and not self._state_store.verify_operator_lock("revival", lock_token):
                report.errors.append("XS-04: Lock expired before state save — revival state NOT updated.")
                logger.error("XS-04: Lock expired mid-dispatch for revival run %s", report.run_id)
            else:
                state.last_run_at = datetime.now(timezone.utc).isoformat()
                state.runs_today += 1
                self._save_daily_state(state)

            report.completed_at = datetime.now(timezone.utc).isoformat()
            self._log_dispatch(report)

            return report
        finally:
            if lock_token:
                self._state_store.release_operator_lock("revival", lock_token)

    # -------------------------------------------------------------------------
    # dispatch_cadence (follow-up steps for enrolled leads)
    # -------------------------------------------------------------------------

    async def dispatch_cadence(
        self,
        dry_run: bool = True,
        approved_cadence_actions: Optional[List[Dict[str, Any]]] = None,
    ) -> OperatorReport:
        """
        Process cadence follow-up actions for enrolled leads.

        1. Sync signals (auto-exit replied/bounced/unsubscribed leads)
        2. Get actions due today from cadence engine
        3. Dispatch email actions via Instantly
        4. Dispatch LinkedIn actions via HeyReach
        5. Mark steps done in cadence engine
        """
        run_id = f"op_cad_{uuid.uuid4().hex[:8]}"
        report = OperatorReport(
            run_id=run_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            dry_run=dry_run,
            motion="cadence",
        )

        lock_token = None
        if not dry_run:
            lock_token = self._state_store.acquire_operator_lock("cadence", ttl_seconds=180)
            if not lock_token:
                report.errors.append("Another cadence dispatch is already running (distributed lock not acquired)")
                report.completed_at = datetime.now(timezone.utc).isoformat()
                return report

        try:
            if self._check_emergency_stop():
                report.errors.append("EMERGENCY_STOP active — cadence blocked")
                report.completed_at = datetime.now(timezone.utc).isoformat()
                return report

            schedule = self.get_warmup_schedule()
            report.warmup_schedule = asdict(schedule)
            state = self._load_daily_state()

            cadence = self._get_cadence_engine()

            # Step 1: Sync signals (auto-exit on reply/bounce/unsub)
            try:
                sync_result = cadence.sync_signals()
                report.cadence_synced = sync_result
            except Exception as e:
                report.errors.append(f"Cadence signal sync error: {e}")
                logger.error("Cadence signal sync error: %s", e)

            # Step 2: Get actions due today
            try:
                due_actions = cadence.get_due_actions()
                allowed_action_ids = {
                    str(item.get("action_id", "")).strip()
                    for item in (approved_cadence_actions or [])
                    if str(item.get("action_id", "")).strip()
                }
                if allowed_action_ids:
                    due_actions = [
                        action for action in due_actions
                        if (
                            f"{normalize_email(action.email)}|"
                            f"{action.step.channel}|s{action.step.step}|d{action.step.day}"
                        ) in allowed_action_ids
                    ]
                report.cadence_actions_due = len(due_actions)

                if not due_actions:
                    logger.info("No cadence actions due today")
                    report.completed_at = datetime.now(timezone.utc).isoformat()
                    self._log_dispatch(report)
                    return report

                dispatched = 0

                for action in due_actions:
                    # Check daily limits
                    if action.step.channel == "email":
                        remaining = max(0, schedule.email_daily_limit - state.outbound_email_dispatched)
                        if remaining <= 0:
                            report.errors.append(f"Email limit reached, skipping cadence step for {action.email}")
                            continue
                    elif action.step.channel == "linkedin":
                        remaining = max(0, schedule.linkedin_daily_limit - state.outbound_linkedin_dispatched)
                        if remaining <= 0:
                            report.errors.append(f"LinkedIn limit reached, skipping cadence step for {action.email}")
                            continue

                    # Dedup check
                    if not self._is_lead_eligible(action.email, state):
                        continue

                    # Generate follow-up copy for email steps via CRAFTER
                    followup_copy = None
                    if action.step.channel == "email" and action.step.action != "intro":
                        try:
                            from execution.crafter_campaign import CampaignCrafter
                            crafter = CampaignCrafter()
                            followup_copy = crafter.craft_cadence_followup(
                                action_type=action.step.action,
                                lead_data=action.lead_data,
                                step_num=action.step.step,
                                day_num=action.step.day,
                            )
                        except Exception as e:
                            logger.warning("CRAFTER follow-up generation failed for %s: %s", action.email, e)

                    if dry_run:
                        label = f"  [yellow][DRY RUN][/yellow] Cadence Step {action.step.step} "
                        label += f"(Day {action.step.day}) [{action.step.channel}] -> {action.email}"
                        if followup_copy:
                            label += f' | subj: "{followup_copy["subject"][:50]}"'
                        else:
                            label += f" | {action.step.action}"
                        console.print(label)
                        dispatched += 1
                    else:
                        try:
                            if action.step.channel == "email":
                                state.outbound_email_dispatched += 1
                            elif action.step.channel == "linkedin":
                                state.outbound_linkedin_dispatched += 1

                            metadata = {}
                            if followup_copy:
                                # Save generated copy to shadow email dir for review
                                self._save_cadence_email(action, followup_copy)
                                metadata["followup_subject"] = followup_copy.get("subject", "")

                            cadence.mark_step_done(action.email, action.step.step, "dispatched",
                                                   metadata=metadata)
                            self._record_dispatched_email(state, action.email)
                            dispatched += 1

                            console.print(
                                f"  [green]Cadence[/green] Step {action.step.step} "
                                f"(Day {action.step.day}) [{action.step.channel}] -> {action.email}"
                            )
                        except Exception as e:
                            report.errors.append(f"Cadence dispatch error for {action.email}: {e}")

                if not dry_run:
                    state.cadence_dispatched += dispatched
                report.cadence_dispatched = dispatched

            except Exception as e:
                report.errors.append(f"Cadence engine error: {e}")
                logger.error("Cadence engine error: %s", e)

            if not dry_run:
                # XS-04: Verify lock still held before saving state
                if lock_token and not self._state_store.verify_operator_lock("cadence", lock_token):
                    report.errors.append("XS-04: Lock expired before state save — cadence state NOT updated.")
                    logger.error("XS-04: Lock expired mid-dispatch for cadence run %s", report.run_id)
                else:
                    state.last_run_at = datetime.now(timezone.utc).isoformat()
                    state.runs_today += 1
                    self._save_daily_state(state)

            report.completed_at = datetime.now(timezone.utc).isoformat()
            self._log_dispatch(report)

            return report
        finally:
            if lock_token:
                self._state_store.release_operator_lock("cadence", lock_token)

    # -------------------------------------------------------------------------
    # dispatch_all
    # -------------------------------------------------------------------------

    async def dispatch_all(self, dry_run: bool = True) -> OperatorReport:
        """Run all three motions: outbound → cadence → revival."""
        run_id = f"op_all_{uuid.uuid4().hex[:8]}"
        report = OperatorReport(
            run_id=run_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            dry_run=dry_run,
            motion="all",
        )

        lock_token = None
        if not dry_run:
            lock_token = self._state_store.acquire_operator_lock("all", ttl_seconds=300)
            if not lock_token:
                report.errors.append("Another all-motion dispatch is already running (distributed lock not acquired)")
                report.completed_at = datetime.now(timezone.utc).isoformat()
                return report

        try:
            approved_batch: Optional[DispatchBatch] = None

            # --- Gatekeeper batch approval gate (combined for all motions) ---
            if not dry_run and self.gatekeeper_required:
                approved_batch = self.get_approved_batch()
                if approved_batch and approved_batch.motion == "all":
                    try:
                        self._validate_batch_for_execution(approved_batch, expected_motion="all")
                    except ValueError as exc:
                        report.errors.append(str(exc))
                        report.completed_at = datetime.now(timezone.utc).isoformat()
                        self._log_dispatch(report)
                        return report
                    logger.info("Executing approved 'all' batch: %s", approved_batch.batch_id)
                    report.batch_id = approved_batch.batch_id
                else:
                    batch = self.create_batch(motion="all")
                    report.pending_approval = True
                    report.batch_id = batch.batch_id
                    report.errors.append(
                        f"GATEKEEPER: Batch {batch.batch_id} created for review. "
                        f"Approve via POST /api/operator/approve-batch/{batch.batch_id}"
                    )
                    console.print(
                        f"[yellow]GATEKEEPER GATE:[/yellow] Batch {batch.batch_id} requires approval.\n"
                        f"  Email: {batch.total_email_leads}, LinkedIn: {batch.total_linkedin_leads}\n"
                        f"  Cadence due: {batch.total_cadence_due}, Revival: {batch.total_revival_candidates}\n"
                        f"  Approve: POST /api/operator/approve-batch/{batch.batch_id}"
                    )
                    report.completed_at = datetime.now(timezone.utc).isoformat()
                    self._log_dispatch(report)
                    return report

            # 1. Outbound (new leads)
            outbound_report = await self.dispatch_outbound(
                dry_run=dry_run,
                approved_batch=approved_batch,
                skip_gatekeeper=True,
                mark_batch_executed=False,
            )
            report.instantly_report = outbound_report.instantly_report
            report.heyreach_report = outbound_report.heyreach_report
            report.errors.extend(outbound_report.errors)

            # 2. Cadence (follow-up steps for enrolled leads)
            cadence_report = await self.dispatch_cadence(
                dry_run=dry_run,
                approved_cadence_actions=(approved_batch.approved_cadence_actions if approved_batch else None),
            )
            report.cadence_actions_due = cadence_report.cadence_actions_due
            report.cadence_dispatched = cadence_report.cadence_dispatched
            report.cadence_synced = cadence_report.cadence_synced
            report.errors.extend(cadence_report.errors)

            # 3. Revival (stale GHL contacts)
            revival_report = await self.dispatch_revival(
                dry_run=dry_run,
                approved_revival_emails=(approved_batch.approved_revival_emails if approved_batch else None),
            )
            report.revival_candidates_found = revival_report.revival_candidates_found
            report.revival_dispatched = revival_report.revival_dispatched
            report.errors.extend(revival_report.errors)

            report.warmup_schedule = outbound_report.warmup_schedule
            report.completed_at = datetime.now(timezone.utc).isoformat()

            # Mark batch as executed if we were processing an approved batch
            if report.batch_id and not report.pending_approval:
                self._mark_batch_executed(report.batch_id, report)

            return report
        finally:
            if lock_token:
                self._state_store.release_operator_lock("all", lock_token)

    # -------------------------------------------------------------------------
    # Status (for dashboard)
    # -------------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return current OPERATOR status for dashboard display."""
        state = self._load_daily_state()
        schedule = self.get_warmup_schedule()

        # Cadence summary
        cadence_summary = {}
        try:
            cadence = self._get_cadence_engine()
            cadence_summary = cadence.get_cadence_summary()
        except Exception:
            pass

        ramp = self._get_ramp_status()

        return {
            "enabled": self._operator_config.get("enabled", False),
            "emergency_stop": self._check_emergency_stop(),
            "date": state.date,
            "warmup_schedule": asdict(schedule),
            "ramp": ramp,
            "today": {
                "outbound_email": state.outbound_email_dispatched,
                "outbound_linkedin": state.outbound_linkedin_dispatched,
                "revival": state.revival_dispatched,
                "cadence": state.cadence_dispatched,
                "total_leads": len(state.leads_dispatched),
                "runs": state.runs_today,
                "last_run": state.last_run_at,
            },
            "limits": {
                "email_remaining": max(0, schedule.email_daily_limit - state.outbound_email_dispatched),
                "linkedin_remaining": max(0, schedule.linkedin_daily_limit - state.outbound_linkedin_dispatched),
                "revival_remaining": max(0, schedule.revival_daily_limit - state.revival_dispatched),
            },
            "cadence": cadence_summary,
            "gatekeeper": {
                "required": self.gatekeeper_required,
                "pending_batch": asdict(pending) if (pending := self.get_pending_batch()) else None,
            },
            "config": {
                "tier_routing": self._operator_config.get("outbound", {}).get("tier_channel_routing", {}),
                "revival_enabled": self._operator_config.get("revival", {}).get("enabled", False),
                "revival_stages": self._operator_config.get("revival", {}).get("scan_pipeline_stages", []),
            },
        }

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------

    def _log_dispatch(self, report: OperatorReport):
        """Append dispatch report to JSONL log."""
        try:
            with open(self.dispatch_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(report), default=str) + "\n")
        except Exception as e:
            logger.error("Failed to write operator dispatch log: %s", e)

    def get_dispatch_history(self, limit: int = 50) -> List[Dict]:
        """Read recent dispatch reports from log."""
        history = []
        if not self.dispatch_log.exists():
            return history

        try:
            lines = self.dispatch_log.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines[-limit:]):
                if line.strip():
                    try:
                        history.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

        return history


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="OPERATOR Agent — Unified Outbound Execution")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Simulate without API calls (default)")
    parser.add_argument("--live", action="store_true",
                        help="Actually dispatch (overrides --dry-run)")
    parser.add_argument("--motion", choices=["outbound", "cadence", "revival", "all"], default="all",
                        help="Which motion to run (default: all)")
    parser.add_argument("--tier", type=str,
                        help="Filter by ICP tier (tier_1, tier_2, tier_3)")
    parser.add_argument("--limit", type=int,
                        help="Override daily limit")
    parser.add_argument("--status", action="store_true",
                        help="Show current OPERATOR status")
    parser.add_argument("--history", action="store_true",
                        help="Show dispatch history")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args()

    operator = OperatorOutbound()

    if args.status:
        status = operator.get_status()
        if args.json:
            print(json.dumps(status, indent=2, default=str))
        else:
            schedule = status["warmup_schedule"]
            today = status["today"]
            limits = status["limits"]

            console.print("\n[bold]OPERATOR Status[/bold]")
            console.print(f"  Enabled:        {status['enabled']}")
            console.print(f"  Emergency Stop: {status['emergency_stop']}")
            console.print(f"  Date:           {status['date']}")

            ramp = status.get("ramp", {})
            if ramp.get("active"):
                console.print(f"\n[bold yellow]RAMP MODE (Supervised Go-Live)[/bold yellow]")
                console.print(f"  Day:            {ramp['day']} of {ramp['day'] + ramp['remaining_days'] - 1}")
                console.print(f"  Email limit:    {ramp['email_limit_override']}/day (override)")
                console.print(f"  Tier filter:    {ramp['tier_filter']} only")
                console.print(f"  Remaining days: {ramp['remaining_days']}")
            elif ramp.get("enabled"):
                console.print(f"\n  Ramp:           configured but not active")

            console.print(f"\n[bold]Warmup Schedule[/bold]")
            console.print(f"  Email limit:    {schedule['email_daily_limit']}/day")
            console.print(f"  LinkedIn limit: {schedule['linkedin_daily_limit']}/day")
            warmup_label = f"Week {schedule['linkedin_warmup_week']}" if schedule["is_linkedin_warmup"] else "FULL"
            console.print(f"  LinkedIn phase: {warmup_label}")
            console.print(f"  Revival limit:  {schedule['revival_daily_limit']}/day")

            console.print(f"\n[bold]Today[/bold]")
            console.print(f"  Email dispatched:    {today['outbound_email']}")
            console.print(f"  LinkedIn dispatched: {today['outbound_linkedin']}")
            console.print(f"  Revival dispatched:  {today['revival']}")
            console.print(f"  Cadence dispatched:  {today.get('cadence', 0)}")
            console.print(f"  Total leads:         {today['total_leads']}")
            console.print(f"  Runs today:          {today['runs']}")

            console.print(f"\n[bold]Remaining[/bold]")
            console.print(f"  Email:    {limits['email_remaining']}")
            console.print(f"  LinkedIn: {limits['linkedin_remaining']}")
            console.print(f"  Revival:  {limits['revival_remaining']}")

            cad = status.get("cadence", {})
            if cad:
                console.print(f"\n[bold]Cadence[/bold]")
                console.print(f"  Enrolled:  {cad.get('total_enrolled', 0)}")
                bs = cad.get('by_status', {})
                console.print(f"  Active:    {bs.get('active', 0)}")
                console.print(f"  Completed: {bs.get('completed', 0)}")
                console.print(f"  Exited:    {bs.get('exited', 0)}")
                console.print(f"  Due today: {cad.get('actions_due_today', 0)}")
        return

    if args.history:
        history = operator.get_dispatch_history(limit=20)
        if args.json:
            print(json.dumps(history, indent=2, default=str))
        else:
            for entry in history:
                motion = entry.get("motion", "?")
                dry = "[DRY]" if entry.get("dry_run") else "[LIVE]"
                ts = entry.get("started_at", "")[:19]
                errors = len(entry.get("errors", []))
                console.print(f"  {ts}  {dry}  {motion}  errors={errors}")
        return

    dry_run = not args.live

    async def _run():
        if args.motion == "outbound":
            return await operator.dispatch_outbound(
                tier_filter=args.tier, limit=args.limit, dry_run=dry_run,
            )
        elif args.motion == "cadence":
            return await operator.dispatch_cadence(dry_run=dry_run)
        elif args.motion == "revival":
            return await operator.dispatch_revival(
                limit=args.limit, dry_run=dry_run,
            )
        else:
            return await operator.dispatch_all(dry_run=dry_run)

    report = asyncio.run(_run())

    if args.json:
        print(json.dumps(asdict(report), indent=2, default=str))
    else:
        mode = "[DRY RUN]" if dry_run else "[LIVE]"
        console.print(f"\n{mode} OPERATOR Report: {report.run_id} ({report.motion})")

        if report.instantly_report:
            ir = report.instantly_report
            console.print(f"  Instantly: {ir.get('total_dispatched', 0)} dispatched, "
                          f"{ir.get('total_errors', 0)} errors")

        if report.heyreach_report:
            hr = report.heyreach_report
            console.print(f"  HeyReach:  {hr.get('total_dispatched', 0)} dispatched, "
                          f"{hr.get('total_errors', 0)} errors")

        if report.motion in ("cadence", "all"):
            console.print(f"  Cadence:   {report.cadence_actions_due} due, "
                          f"{report.cadence_dispatched} dispatched")

        if report.motion in ("revival", "all"):
            console.print(f"  Revival:   {report.revival_candidates_found} found, "
                          f"{report.revival_dispatched} dispatched")

        if report.errors:
            for err in report.errors:
                console.print(f"  [red]ERROR: {err}[/red]")


if __name__ == "__main__":
    main()
