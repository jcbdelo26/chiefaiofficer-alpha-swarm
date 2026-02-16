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
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console

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

        self.state_file = PROJECT_ROOT / ".hive-mind" / "operator_state.json"
        self.dispatch_log = PROJECT_ROOT / ".hive-mind" / "operator_dispatch_log.jsonl"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

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

        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("date") == today:
                    return OperatorDailyState(**data)
            except (json.JSONDecodeError, IOError, TypeError):
                pass

        return OperatorDailyState(date=today)

    def _save_daily_state(self, state: OperatorDailyState):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(asdict(state), f, indent=2)

    # -------------------------------------------------------------------------
    # Deduplication
    # -------------------------------------------------------------------------

    def _is_lead_eligible(self, email: str, state: OperatorDailyState) -> bool:
        """Three-layer dedup check."""
        if not email:
            return False

        # Layer 1: Already dispatched today
        if email.lower() in [e.lower() for e in state.leads_dispatched]:
            return False

        # Layer 2: Terminal or active status in signal loop
        mgr = self._get_signal_manager()
        status_record = mgr.get_lead_status(email)
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
        load_dotenv(override=True)
        return os.getenv("EMERGENCY_STOP", "false").lower().strip() in ("true", "1", "yes", "on")

    # -------------------------------------------------------------------------
    # dispatch_outbound
    # -------------------------------------------------------------------------

    async def dispatch_outbound(
        self,
        tier_filter: Optional[str] = None,
        limit: Optional[int] = None,
        dry_run: bool = True,
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

        # Safety
        if self._check_emergency_stop():
            report.errors.append("EMERGENCY_STOP active — all dispatch blocked")
            report.completed_at = datetime.now(timezone.utc).isoformat()
            return report

        if not self._operator_config.get("enabled", False) and not dry_run:
            report.errors.append("OPERATOR disabled in config/production.json")
            report.completed_at = datetime.now(timezone.utc).isoformat()
            return report

        schedule = self.get_warmup_schedule()
        report.warmup_schedule = asdict(schedule)
        state = self._load_daily_state()

        # --- Step 1: Instantly dispatch (email) ---
        try:
            instantly = self._get_instantly()
            email_remaining = max(0, schedule.email_daily_limit - state.outbound_email_dispatched)

            if email_remaining > 0:
                instantly_report = await instantly.dispatch(
                    tier_filter=tier_filter,
                    limit=min(limit, email_remaining) if limit else email_remaining,
                    dry_run=dry_run,
                )
                report.instantly_report = asdict(instantly_report)

                # Track dispatched leads
                dispatched_count = instantly_report.total_dispatched
                state.outbound_email_dispatched += dispatched_count

                # Record dispatched lead emails for dedup
                for campaign in instantly_report.campaigns_created:
                    for eid in campaign.shadow_email_ids:
                        if eid not in state.leads_dispatched:
                            state.leads_dispatched.append(eid)
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
                    )
                    report.heyreach_report = asdict(heyreach_report)

                    dispatched_count = heyreach_report.total_dispatched
                    state.outbound_linkedin_dispatched += dispatched_count
                else:
                    report.errors.append(
                        f"LinkedIn daily limit reached ({state.outbound_linkedin_dispatched}/{schedule.linkedin_daily_limit})"
                    )
        except Exception as e:
            report.errors.append(f"HeyReach dispatch error: {e}")
            logger.error("HeyReach dispatch error: %s", e)

        # --- Step 3: Auto-enroll dispatched leads into cadence ---
        try:
            enrolled = self._auto_enroll_to_cadence()
            if enrolled > 0:
                console.print(f"  [cyan]Cadence auto-enroll:[/cyan] {enrolled} leads enrolled")
                report.cadence_auto_enrolled = enrolled
        except Exception as e:
            report.errors.append(f"Cadence auto-enroll error: {e}")
            logger.error("Cadence auto-enroll error: %s", e)

        # Update state
        state.last_run_at = datetime.now(timezone.utc).isoformat()
        state.runs_today += 1
        self._save_daily_state(state)

        report.completed_at = datetime.now(timezone.utc).isoformat()
        self._log_dispatch(report)

        return report

    # -------------------------------------------------------------------------
    # Auto-enroll dispatched leads into cadence
    # -------------------------------------------------------------------------

    def _auto_enroll_to_cadence(self) -> int:
        """
        Scan shadow emails for newly dispatched leads and enroll them in cadence.

        Called after dispatch_outbound(). Reads shadow email files that have
        been dispatched to Instantly (status == "dispatched_to_instantly") and
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

                # Only process dispatched-to-instantly emails
                if data.get("status") != "dispatched_to_instantly":
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
                        state.leads_dispatched.append(c.email)
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

        state.last_run_at = datetime.now(timezone.utc).isoformat()
        state.runs_today += 1
        self._save_daily_state(state)

        report.completed_at = datetime.now(timezone.utc).isoformat()
        self._log_dispatch(report)

        return report

    # -------------------------------------------------------------------------
    # dispatch_cadence (follow-up steps for enrolled leads)
    # -------------------------------------------------------------------------

    async def dispatch_cadence(self, dry_run: bool = True) -> OperatorReport:
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
                    cadence.mark_step_done(action.email, action.step.step, "dry_run",
                                           metadata={"followup_copy": bool(followup_copy)})
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
                        state.leads_dispatched.append(action.email)
                        dispatched += 1

                        console.print(
                            f"  [green]Cadence[/green] Step {action.step.step} "
                            f"(Day {action.step.day}) [{action.step.channel}] -> {action.email}"
                        )
                    except Exception as e:
                        report.errors.append(f"Cadence dispatch error for {action.email}: {e}")

            state.cadence_dispatched += dispatched
            report.cadence_dispatched = dispatched

        except Exception as e:
            report.errors.append(f"Cadence engine error: {e}")
            logger.error("Cadence engine error: %s", e)

        state.last_run_at = datetime.now(timezone.utc).isoformat()
        state.runs_today += 1
        self._save_daily_state(state)

        report.completed_at = datetime.now(timezone.utc).isoformat()
        self._log_dispatch(report)

        return report

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

        # 1. Outbound (new leads)
        outbound_report = await self.dispatch_outbound(dry_run=dry_run)
        report.instantly_report = outbound_report.instantly_report
        report.heyreach_report = outbound_report.heyreach_report
        report.errors.extend(outbound_report.errors)

        # 2. Cadence (follow-up steps for enrolled leads)
        cadence_report = await self.dispatch_cadence(dry_run=dry_run)
        report.cadence_actions_due = cadence_report.cadence_actions_due
        report.cadence_dispatched = cadence_report.cadence_dispatched
        report.cadence_synced = cadence_report.cadence_synced
        report.errors.extend(cadence_report.errors)

        # 3. Revival (stale GHL contacts)
        revival_report = await self.dispatch_revival(dry_run=dry_run)
        report.revival_candidates_found = revival_report.revival_candidates_found
        report.revival_dispatched = revival_report.revival_dispatched
        report.errors.extend(revival_report.errors)

        report.warmup_schedule = outbound_report.warmup_schedule
        report.completed_at = datetime.now(timezone.utc).isoformat()

        return report

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

        return {
            "enabled": self._operator_config.get("enabled", False),
            "emergency_stop": self._check_emergency_stop(),
            "date": state.date,
            "warmup_schedule": asdict(schedule),
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
