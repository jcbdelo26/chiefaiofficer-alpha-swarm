#!/usr/bin/env python3
"""
Instantly Campaign Dispatcher
==============================
Reads approved shadow emails and dispatches them to Instantly.ai campaigns.

This is a POST-APPROVAL step -- the pipeline send stage still writes shadow
emails, and the dashboard still handles approval. This dispatcher takes
approved emails and creates paused Instantly campaigns for human activation.

Usage:
    python execution/instantly_dispatcher.py --dry-run
    python execution/instantly_dispatcher.py --live --from-email chris@outreach.com
    python execution/instantly_dispatcher.py --tier tier_1 --limit 10
"""

import os
import sys
import json
import uuid
import asyncio
import argparse
import platform
import logging
from datetime import datetime, date, timezone
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
logger = logging.getLogger("instantly_dispatcher")


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class DispatchResult:
    """Result of a single campaign dispatch."""
    campaign_name: str
    campaign_id: Optional[str]
    leads_added: int
    shadow_email_ids: List[str]
    status: str  # "dispatched", "dry_run", "error"
    error: Optional[str] = None


@dataclass
class DispatchReport:
    """Summary of a dispatch run."""
    run_id: str
    started_at: str
    completed_at: str = ""
    dry_run: bool = True
    total_approved: int = 0
    total_dispatched: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    campaigns_created: List[DispatchResult] = field(default_factory=list)
    daily_limit_remaining: int = 0
    errors: List[str] = field(default_factory=list)


# =============================================================================
# DAILY CEILING TRACKER
# =============================================================================

class DailyCeilingTracker:
    """
    Tracks how many emails have been dispatched to Instantly today.
    Enforced independently of Instantly's own config -- defense in depth.

    State file: .hive-mind/instantly_dispatch_state.json
    """

    def __init__(self):
        self.state_file = PROJECT_ROOT / ".hive-mind" / "instantly_dispatch_state.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state: Dict[str, Any] = {}
        self._load()

    def _load(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._state = {}

        # Reset if date changed
        today_str = date.today().isoformat()
        if self._state.get("date") != today_str:
            self._state = {
                "date": today_str,
                "dispatched_count": 0,
                "dispatched_emails": [],
                "campaigns_created": [],
            }
            self._save()

    def _save(self):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2)

    def get_remaining(self, daily_limit: int) -> int:
        return max(0, daily_limit - self._state.get("dispatched_count", 0))

    def record_dispatch(self, count: int, email_ids: List[str], campaign_name: str):
        self._state["dispatched_count"] = self._state.get("dispatched_count", 0) + count
        self._state["dispatched_emails"].extend(email_ids)
        self._state["campaigns_created"].append({
            "name": campaign_name,
            "leads": count,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        self._save()

    def get_today_count(self) -> int:
        return self._state.get("dispatched_count", 0)


# =============================================================================
# MAIN DISPATCHER
# =============================================================================

class InstantlyDispatcher:
    """
    Dispatches approved shadow emails to Instantly.ai campaigns.

    Workflow:
    1. Scan .hive-mind/shadow_mode_emails/ for status="approved"
    2. Filter out already-dispatched emails (have "instantly_campaign_id")
    3. Check daily ceiling
    4. Check EMERGENCY_STOP
    5. Group by ICP tier + date -> campaign naming convention
    6. Create paused Instantly campaigns via AsyncInstantlyClient
    7. Add leads with custom_variables
    8. Record dispatch state in each shadow email file
    9. Log to .hive-mind/instantly_dispatch_log.jsonl
    """

    def __init__(self):
        self.shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
        self.dispatch_log = PROJECT_ROOT / ".hive-mind" / "instantly_dispatch_log.jsonl"
        self.ceiling = DailyCeilingTracker()
        self.config = self._load_config()
        self._client = None  # Lazy init

    def _load_config(self) -> Dict[str, Any]:
        config_path = PROJECT_ROOT / "config" / "production.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _is_instantly_enabled(self) -> bool:
        return self.config.get("external_apis", {}).get("instantly", {}).get("enabled", False)

    def _get_sending_accounts(self) -> List[str]:
        """Load sending accounts from config for multi-email rotation."""
        instantly_cfg = self.config.get("external_apis", {}).get("instantly", {})
        accounts_cfg = instantly_cfg.get("sending_accounts", {})
        return accounts_cfg.get("primary_from_emails", [])

    def _get_daily_limit(self) -> int:
        return self.config.get("guardrails", {}).get("email_limits", {}).get("daily_limit", 25)

    def _check_emergency_stop(self) -> bool:
        load_dotenv(override=True)
        return os.getenv("EMERGENCY_STOP", "false").lower().strip() in ("true", "1", "yes", "on")

    async def _get_client(self):
        """Lazy-initialize the Instantly client."""
        if self._client is None:
            sys.path.insert(0, str(PROJECT_ROOT / "mcp-servers" / "instantly-mcp"))
            from server import AsyncInstantlyClient
            self._client = AsyncInstantlyClient()
        return self._client

    # -------------------------------------------------------------------------
    # Shadow email loading
    # -------------------------------------------------------------------------

    def _load_approved_emails(self, tier_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load approved, not-yet-dispatched shadow emails."""
        approved: List[Dict[str, Any]] = []

        if not self.shadow_dir.exists():
            return approved

        for email_file in sorted(self.shadow_dir.glob("*.json")):
            try:
                with open(email_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Only approved, not yet dispatched, not synthetic
                if data.get("status") != "approved":
                    continue
                if data.get("instantly_campaign_id"):
                    continue
                if data.get("synthetic"):
                    continue

                # Tier filter
                if tier_filter and data.get("tier") != tier_filter:
                    continue

                data["_file_path"] = str(email_file)
                approved.append(data)
            except Exception as e:
                logger.warning("Failed to read %s: %s", email_file.name, e)

        return approved

    # -------------------------------------------------------------------------
    # Campaign naming
    # -------------------------------------------------------------------------

    def _generate_campaign_name(self, tier: str, source: str = "pipeline") -> str:
        """
        Generate campaign name per INSTANTLY.md convention:
        {tier}_{source}_{date}_{variant}

        Example: t1_pipeline_20260214_v1
        """
        tier_short = tier.replace("tier_", "t")
        date_str = date.today().strftime("%Y%m%d")

        # Increment variant based on today's dispatches
        existing = self.ceiling._state.get("campaigns_created", [])
        prefix = f"{tier_short}_{source}_{date_str}"
        same_prefix = [c for c in existing if c.get("name", "").startswith(prefix)]
        variant = f"v{len(same_prefix) + 1}"

        return f"{prefix}_{variant}"

    # -------------------------------------------------------------------------
    # Lead mapping
    # -------------------------------------------------------------------------

    def _group_by_tier(self, emails: List[Dict]) -> Dict[str, List[Dict]]:
        """Group emails by ICP tier for campaign creation."""
        groups: Dict[str, List[Dict]] = {}
        for email in emails:
            tier = email.get("tier", "tier_3")
            groups.setdefault(tier, []).append(email)
        return groups

    def _map_to_instantly_lead(self, shadow_email: Dict) -> Dict[str, Any]:
        """Map shadow email data to Instantly lead format per INSTANTLY.md spec."""
        recipient = shadow_email.get("recipient_data", {})
        context = shadow_email.get("context", {})

        name = recipient.get("name", "")
        name_parts = name.split(" ", 1) if name else ["", ""]
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        return {
            "email": shadow_email.get("to", ""),
            "first_name": first_name,
            "last_name": last_name,
            "company": recipient.get("company", ""),
            "custom_variables": {
                "title": recipient.get("title", ""),
                "linkedin_url": recipient.get("linkedin_url", ""),
                "icpScore": str(context.get("icp_score", "")),
                "icpTier": context.get("icp_tier", ""),
                "sourceType": "pipeline",
                "campaignType": context.get("campaign_type", ""),
                "ghl_contact_id": shadow_email.get("contact_id", ""),
                "shadow_email_id": shadow_email.get("email_id", ""),
                "pipeline_run_id": context.get("pipeline_run_id", ""),
            },
        }

    # -------------------------------------------------------------------------
    # State tracking
    # -------------------------------------------------------------------------

    def _mark_email_dispatched(self, shadow_email: Dict, campaign_id: str, campaign_name: str):
        """Update shadow email file with dispatch info."""
        file_path = shadow_email.get("_file_path")
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            data["instantly_campaign_id"] = campaign_id
            data["instantly_campaign_name"] = campaign_name
            data["instantly_dispatched_at"] = datetime.now(timezone.utc).isoformat()
            data["status"] = "dispatched_to_instantly"

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to mark email as dispatched: %s", e)

    def _log_dispatch(self, result: DispatchResult):
        """Append to dispatch log (JSONL)."""
        self.dispatch_log.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.dispatch_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(result), default=str) + "\n")
        except Exception as e:
            logger.error("Failed to write dispatch log: %s", e)

    # -------------------------------------------------------------------------
    # Main dispatch
    # -------------------------------------------------------------------------

    async def dispatch(
        self,
        tier_filter: Optional[str] = None,
        limit: Optional[int] = None,
        dry_run: bool = True,
        from_email: str = "",
    ) -> DispatchReport:
        """
        Main dispatch method.

        Args:
            tier_filter: Only dispatch emails for this tier (e.g., "tier_1")
            limit: Override daily limit
            dry_run: Simulate without API calls
            from_email: Sending email address (from Instantly account)
        """
        run_id = f"dispatch_{uuid.uuid4().hex[:8]}"
        report = DispatchReport(
            run_id=run_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            dry_run=dry_run,
        )

        # --- SAFETY CHECKS ---

        # 1. Emergency stop
        if self._check_emergency_stop():
            report.errors.append("EMERGENCY_STOP is active -- dispatch blocked")
            report.completed_at = datetime.now(timezone.utc).isoformat()

            if not dry_run:
                try:
                    client = await self._get_client()
                    pause_result = await client.bulk_pause_all()
                    report.errors.append(
                        f"Emergency bulk-pause: {pause_result.get('paused_count', 0)} campaigns paused"
                    )
                    try:
                        from core.alerts import send_critical
                        send_critical(
                            "EMERGENCY STOP - Instantly Bulk Pause",
                            f"All {pause_result.get('paused_count', 0)} active campaigns paused",
                            metadata=pause_result,
                            source="instantly_dispatcher",
                        )
                    except ImportError:
                        pass
                except Exception as e:
                    report.errors.append(f"Emergency bulk-pause failed: {e}")

            return report

        # 2. Check config enabled
        if not self._is_instantly_enabled() and not dry_run:
            report.errors.append("Instantly is disabled in config/production.json")
            report.completed_at = datetime.now(timezone.utc).isoformat()
            return report

        # 3. Daily ceiling
        daily_limit = limit or self._get_daily_limit()
        remaining = self.ceiling.get_remaining(daily_limit)
        report.daily_limit_remaining = remaining

        if remaining <= 0:
            report.errors.append(
                f"Daily limit reached ({self.ceiling.get_today_count()}/{daily_limit})"
            )
            report.completed_at = datetime.now(timezone.utc).isoformat()

            try:
                from core.alerts import send_warning
                send_warning(
                    "Instantly Daily Limit Reached",
                    f"Dispatched {self.ceiling.get_today_count()}/{daily_limit} today",
                    source="instantly_dispatcher",
                )
            except ImportError:
                pass

            return report

        # --- LOAD & GROUP ---

        approved_emails = self._load_approved_emails(tier_filter)
        report.total_approved = len(approved_emails)

        if not approved_emails:
            console.print("[dim]No approved emails to dispatch.[/dim]")
            report.completed_at = datetime.now(timezone.utc).isoformat()
            return report

        # Enforce remaining ceiling
        if len(approved_emails) > remaining:
            approved_emails = approved_emails[:remaining]
            report.total_skipped = report.total_approved - len(approved_emails)

        tier_groups = self._group_by_tier(approved_emails)

        # --- FROM EMAIL + SENDING ACCOUNTS ---
        sending_accounts = self._get_sending_accounts()

        if not from_email:
            from_email = os.getenv("INSTANTLY_FROM_EMAIL", "")
            if not from_email and sending_accounts:
                from_email = sending_accounts[0]
            if not from_email:
                report.errors.append("No from_email provided, INSTANTLY_FROM_EMAIL not set, and no sending_accounts in config")
                report.completed_at = datetime.now(timezone.utc).isoformat()
                return report

        # --- DISPATCH PER TIER ---

        try:
            from execution.fail_safe_manager import CircuitBreaker, CircuitOpenError
        except ImportError:
            CircuitBreaker = None
            CircuitOpenError = Exception

        if CircuitBreaker:
            breaker = CircuitBreaker("instantly_api", failure_threshold=5, recovery_timeout=120)
        else:
            breaker = None

        for tier, emails in tier_groups.items():
            campaign_name = self._generate_campaign_name(tier)

            # Use first email's subject/body as campaign template
            first = emails[0]
            subject = first.get("subject", "Personalized outreach")
            body = first.get("body", "")

            # Default schedule — NOTE: Instantly V2 rejects "America/New_York",
            # "America/Detroit" is the accepted Eastern Time equivalent.
            schedule = {
                "timezone": "America/Detroit",
                "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "startHour": 8,
                "endHour": 18,
            }

            dispatch_result = DispatchResult(
                campaign_name=campaign_name,
                campaign_id=None,
                leads_added=0,
                shadow_email_ids=[e.get("email_id", "") for e in emails],
                status="pending",
            )

            if dry_run:
                dispatch_result.status = "dry_run"
                dispatch_result.leads_added = len(emails)
                report.total_dispatched += len(emails)
                console.print(
                    f"[yellow][DRY RUN][/yellow] Would create campaign "
                    f"'{campaign_name}' with {len(emails)} leads ({tier})"
                )
            else:
                try:
                    client = await self._get_client()

                    # Create campaign (paused by default — V2 DRAFTED state)
                    campaign_result = await client.create_campaign(
                        name=campaign_name,
                        from_email=from_email,
                        subject=subject,
                        body=body,
                        schedule=schedule,
                        email_list=sending_accounts if sending_accounts else None,
                    )

                    if not campaign_result.get("success"):
                        raise Exception(
                            f"Campaign creation failed: {campaign_result.get('error')}"
                        )

                    campaign_id = campaign_result.get("data", {}).get("id")
                    if not campaign_id:
                        raise Exception("No campaign ID returned")

                    dispatch_result.campaign_id = campaign_id

                    # Add leads — CRITICAL: rollback campaign on failure
                    leads = [self._map_to_instantly_lead(e) for e in emails]
                    add_result = await client.add_leads(campaign_id, leads, skip_duplicates=True)

                    if not add_result.get("success"):
                        # Rollback: delete orphaned empty campaign
                        logger.error(
                            "Lead add failed for %s — deleting orphaned campaign %s",
                            campaign_name, campaign_id,
                        )
                        try:
                            await client.delete_campaign(campaign_id)
                        except Exception as del_err:
                            logger.error("Orphan cleanup also failed: %s", del_err)
                        raise Exception(
                            f"Lead add failed (campaign rolled back): {add_result.get('error')}"
                        )

                    dispatch_result.leads_added = len(leads)
                    dispatch_result.status = "dispatched"
                    report.total_dispatched += len(leads)

                    # Mark each shadow email
                    for email in emails:
                        self._mark_email_dispatched(email, campaign_id, campaign_name)

                    # Record in daily ceiling
                    self.ceiling.record_dispatch(
                        len(leads),
                        [e.get("email_id", "") for e in emails],
                        campaign_name,
                    )

                    console.print(
                        f"[green]Dispatched[/green] campaign '{campaign_name}' "
                        f"({campaign_id}) with {len(leads)} leads ({tier}) [PAUSED]"
                    )

                    # Slack notification
                    try:
                        from core.alerts import send_info
                        send_info(
                            f"Instantly Campaign Created: {campaign_name}",
                            f"{len(leads)} leads dispatched ({tier}). "
                            f"Campaign is PAUSED -- activate in dashboard.",
                            metadata={
                                "campaign_id": campaign_id,
                                "tier": tier,
                                "leads": len(leads),
                            },
                            source="instantly_dispatcher",
                        )
                    except ImportError:
                        pass

                except Exception as e:
                    dispatch_result.status = "error"
                    dispatch_result.error = str(e)
                    report.total_errors += 1
                    report.errors.append(str(e))
                    logger.error("Dispatch error for %s: %s", campaign_name, e)

                    try:
                        from core.alerts import send_warning
                        send_warning(
                            f"Instantly Dispatch Error: {campaign_name}",
                            str(e),
                            source="instantly_dispatcher",
                        )
                    except ImportError:
                        pass

            self._log_dispatch(dispatch_result)
            report.campaigns_created.append(dispatch_result)

        report.completed_at = datetime.now(timezone.utc).isoformat()
        report.daily_limit_remaining = self.ceiling.get_remaining(daily_limit)

        # Close client
        if self._client:
            await self._client.close()
            self._client = None

        return report


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Instantly Campaign Dispatcher")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Simulate without API calls (default)")
    parser.add_argument("--live", action="store_true",
                        help="Actually dispatch (overrides --dry-run)")
    parser.add_argument("--tier", type=str,
                        help="Filter by ICP tier (tier_1, tier_2, tier_3)")
    parser.add_argument("--limit", type=int,
                        help="Override daily limit")
    parser.add_argument("--from-email", type=str, default="",
                        help="Sending email address")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args()

    dry_run = not args.live

    dispatcher = InstantlyDispatcher()
    report = asyncio.run(
        dispatcher.dispatch(
            tier_filter=args.tier,
            limit=args.limit,
            dry_run=dry_run,
            from_email=args.from_email,
        )
    )

    if args.json:
        print(json.dumps(asdict(report), indent=2, default=str))
    else:
        mode = "[DRY RUN]" if dry_run else "[LIVE]"
        console.print(f"\n{mode} Dispatch Report: {report.run_id}")
        console.print(f"  Approved:  {report.total_approved}")
        console.print(f"  Dispatched: {report.total_dispatched}")
        console.print(f"  Skipped:   {report.total_skipped}")
        console.print(f"  Errors:    {report.total_errors}")
        console.print(f"  Daily remaining: {report.daily_limit_remaining}")
        for r in report.campaigns_created:
            color = (
                "green" if r.status == "dispatched"
                else "yellow" if r.status == "dry_run"
                else "red"
            )
            console.print(
                f"    [{color}]{r.campaign_name}[/{color}]: "
                f"{r.leads_added} leads ({r.status})"
            )
        if report.errors:
            for err in report.errors:
                console.print(f"    [red]ERROR: {err}[/red]")


if __name__ == "__main__":
    main()
