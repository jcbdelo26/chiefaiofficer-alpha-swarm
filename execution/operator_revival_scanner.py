#!/usr/bin/env python3
"""
Revival Scanner — GHL Contact Mining for Re-engagement
=========================================================
Scans GHL cached contacts for stale leads worth reviving.

Scoring:
  - Website revisit (RB2B signal):    0.9+
  - Previously replied (any channel): 0.7-0.9
  - Opened emails but no reply:       0.5-0.7
  - Never engaged:                    0.3-0.5
  - Recently unsubscribed:            0.0 (excluded)

Filters:
  - Inactive > N days (configurable, default 30)
  - Has email address
  - Not in active outbound pipeline
  - Not terminal (bounced, unsubscribed, rejected)
  - No excluded tags (do-not-contact, competitor)
  - Inactive < max days (default 120 — too old = archive)

Usage:
    python execution/operator_revival_scanner.py --scan --limit 10
    python execution/operator_revival_scanner.py --scan --json
"""

import sys
import json
import argparse
import platform
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console

_is_windows = platform.system() == "Windows"
console = Console(force_terminal=not _is_windows)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("revival_scanner")


# =============================================================================
# DATA MODEL
# =============================================================================

@dataclass
class RevivalCandidate:
    """A GHL contact scored for re-engagement."""
    email: str
    contact_id: str
    first_name: str
    last_name: str
    company: str
    title: str
    pipeline_stage: str
    last_activity_date: str
    days_inactive: int
    revival_score: float
    revival_reason: str
    context: Dict[str, Any]
    tags: List[str]


# =============================================================================
# SCANNER
# =============================================================================

class RevivalScanner:
    """
    Scans GHL contact cache for leads eligible for re-engagement.

    Reads from GHL local cache (instant, no API calls). Scores each
    contact by revival priority. Returns sorted candidates ready for
    OPERATOR dispatch.
    """

    def __init__(self, hive_dir: Path = None):
        self.hive_dir = hive_dir or (PROJECT_ROOT / ".hive-mind")

        # Lazy init
        self._ghl_sync = None
        self._signal_mgr = None
        self._timeline = None
        self._config: Dict = {}

        self._load_config()

    def _load_config(self):
        config_path = PROJECT_ROOT / "config" / "production.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)

    def _get_revival_config(self) -> Dict:
        return self._config.get("operator", {}).get("revival", {})

    def _get_ghl_sync(self):
        if self._ghl_sync is None:
            from core.ghl_local_sync import get_ghl_sync
            self._ghl_sync = get_ghl_sync()
        return self._ghl_sync

    def _get_signal_manager(self):
        if self._signal_mgr is None:
            from core.lead_signals import LeadStatusManager
            self._signal_mgr = LeadStatusManager(hive_dir=self.hive_dir)
        return self._signal_mgr

    def _get_timeline(self):
        if self._timeline is None:
            from core.activity_timeline import ActivityTimeline
            self._timeline = ActivityTimeline(hive_dir=self.hive_dir)
        return self._timeline

    # -------------------------------------------------------------------------
    # Main scan
    # -------------------------------------------------------------------------

    def scan(self, limit: int = 10) -> List[RevivalCandidate]:
        """
        Scan GHL cache for revival candidates.

        1. Get stale contacts from GHL cache
        2. Filter by config rules (stages, tags, inactive range)
        3. Check revivability via LeadStatusManager
        4. Score each candidate
        5. Build context from ActivityTimeline
        6. Return top N sorted by score DESC
        """
        cfg = self._get_revival_config()
        min_inactive = cfg.get("min_inactive_days", 30)
        max_inactive = cfg.get("max_inactive_days", 120)
        scan_stages = cfg.get("scan_pipeline_stages", ["Cold", "Lost", "Nurture"])
        exclude_tags = [t.lower() for t in cfg.get("exclude_tags", ["do-not-contact", "competitor", "unsubscribed"])]

        ghl = self._get_ghl_sync()
        mgr = self._get_signal_manager()

        # Get stale contacts
        stale_contacts = ghl.get_stale_contacts(inactive_days=min_inactive)
        logger.info("Revival scan: %d stale contacts (>%d days)", len(stale_contacts), min_inactive)

        candidates: List[RevivalCandidate] = []

        for contact in stale_contacts:
            email = (contact.get("email") or "").strip()
            if not email:
                continue

            # Calculate days inactive
            days_inactive = self._calc_days_inactive(contact)
            if days_inactive > max_inactive:
                continue  # Too old, skip

            # Exclude by tags
            contact_tags = [t.lower() for t in (contact.get("tags") or [])]
            if any(t in contact_tags for t in exclude_tags):
                continue

            # Check revivability (not terminal, not in active pipeline)
            if not mgr.is_revivable(email):
                continue

            # Score
            lead_status = mgr.get_lead_status(email)
            score, reason = self._score_candidate(contact, lead_status, days_inactive)
            if score <= 0:
                continue

            # Build context
            context = self._build_revival_context(email, contact)

            candidate = RevivalCandidate(
                email=email,
                contact_id=contact.get("id", ""),
                first_name=contact.get("firstName", ""),
                last_name=contact.get("lastName", ""),
                company=contact.get("companyName", contact.get("company", "")),
                title=self._extract_title(contact),
                pipeline_stage=self._extract_pipeline_stage(contact),
                last_activity_date=self._get_last_activity_date(contact),
                days_inactive=days_inactive,
                revival_score=score,
                revival_reason=reason,
                context=context,
                tags=contact.get("tags") or [],
            )
            candidates.append(candidate)

        # Sort by score DESC
        candidates.sort(key=lambda c: c.revival_score, reverse=True)

        result = candidates[:limit]
        logger.info("Revival scan: %d candidates after filtering (returning top %d)", len(candidates), len(result))
        return result

    # -------------------------------------------------------------------------
    # Scoring
    # -------------------------------------------------------------------------

    def _score_candidate(
        self,
        contact: Dict,
        lead_status: Optional[Dict],
        days_inactive: int,
    ) -> Tuple[float, str]:
        """
        Score revival priority. Returns (score, reason).

        Scoring bands:
          0.9+  Website revisit (RB2B signal within 30 days)
          0.7-0.9  Previously replied (any channel)
          0.5-0.7  Opened emails but no reply
          0.3-0.5  Never engaged
          0.0  Excluded (recently unsubscribed, bounced)
        """
        base_score = 0.3
        reason = "never_engaged"

        if not lead_status:
            # No engagement history — base score
            return base_score, reason

        status = lead_status.get("status", "")
        reply_count = lead_status.get("reply_count", 0)
        open_count = lead_status.get("open_count", 0)

        # Previously replied (any channel)
        if reply_count > 0 or status in ("replied", "linkedin_replied"):
            base_score = 0.8
            reason = "previously_replied"
        # Opened but no reply
        elif open_count > 0 or status in ("opened", "engaged_not_replied", "stalled"):
            base_score = 0.6
            reason = "opened_only"
        # Ghosted / exhausted
        elif status in ("ghosted", "linkedin_exhausted"):
            base_score = 0.35
            reason = "ghosted"

        # Boost: ICP tier_1
        icp_tier = lead_status.get("icp_tier", "")
        if icp_tier == "tier_1":
            base_score = min(1.0, base_score + 0.1)

        # Boost: LinkedIn connected (warm relationship)
        linkedin_status = lead_status.get("linkedin_status", "")
        if linkedin_status == "connected":
            base_score = min(1.0, base_score + 0.05)

        # Penalty: very stale contacts (60-120 days)
        if days_inactive > 90:
            base_score *= 0.8
        elif days_inactive > 60:
            base_score *= 0.9

        # Check for website revisit signal (RB2B)
        signals = lead_status.get("signals", [])
        for signal in reversed(signals):
            if "rb2b" in signal.get("type", "").lower() or "website" in signal.get("type", "").lower():
                try:
                    signal_date = datetime.fromisoformat(signal["at"].replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - signal_date).days < 30:
                        base_score = max(base_score, 0.92)
                        reason = "website_revisit"
                        break
                except (ValueError, TypeError, KeyError):
                    continue

        return round(base_score, 3), reason

    # -------------------------------------------------------------------------
    # Context building
    # -------------------------------------------------------------------------

    def _build_revival_context(self, email: str, contact: Dict) -> Dict[str, Any]:
        """Build context for CRAFTER to write re-engagement copy."""
        timeline = self._get_timeline()

        # Get timeline-based context
        ctx = timeline.get_revival_context(email)

        # Enrich with GHL contact data
        ctx["contact_id"] = contact.get("id", "")
        ctx["pipeline_stage"] = self._extract_pipeline_stage(contact)
        ctx["ghl_tags"] = contact.get("tags") or []

        # Custom fields that might be useful
        custom_fields = contact.get("customField") or contact.get("customFields") or {}
        if isinstance(custom_fields, dict):
            ctx["icp_tier"] = custom_fields.get("icp_tier", "")
            ctx["icp_score"] = custom_fields.get("icp_score", "")
        elif isinstance(custom_fields, list):
            for cf in custom_fields:
                key = (cf.get("key") or cf.get("name", "")).lower()
                if key in ("icp_tier", "icp_score"):
                    ctx[key] = cf.get("value", "")

        return ctx

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _calc_days_inactive(self, contact: Dict) -> int:
        """Calculate days since last activity."""
        last_str = (
            contact.get("dateLastActivity")
            or contact.get("lastActivity")
            or contact.get("dateUpdated")
            or contact.get("_synced_at")
        )
        if not last_str:
            return 999

        try:
            last = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - last).days
        except (ValueError, TypeError):
            return 999

    def _extract_title(self, contact: Dict) -> str:
        """Extract job title from contact."""
        title = contact.get("title") or ""
        if not title:
            custom = contact.get("customField") or contact.get("customFields") or {}
            if isinstance(custom, dict):
                title = custom.get("title", "")
            elif isinstance(custom, list):
                for cf in custom:
                    if (cf.get("key") or cf.get("name", "")).lower() == "title":
                        title = cf.get("value", "")
                        break
        return title

    def _extract_pipeline_stage(self, contact: Dict) -> str:
        """Extract pipeline stage from contact."""
        stage = contact.get("pipelineStage") or ""
        if not stage:
            custom = contact.get("customField") or contact.get("customFields") or {}
            if isinstance(custom, dict):
                stage = custom.get("pipeline_stage", "")
            elif isinstance(custom, list):
                for cf in custom:
                    if (cf.get("key") or cf.get("name", "")).lower() == "pipeline_stage":
                        stage = cf.get("value", "")
                        break

        # Check tags for stage-like values
        if not stage:
            known_stages = {"cold", "lost", "nurture", "warm", "hot", "new"}
            for tag in (contact.get("tags") or []):
                if tag.lower() in known_stages:
                    stage = tag
                    break

        return stage

    def _get_last_activity_date(self, contact: Dict) -> str:
        """Get last activity date as ISO string."""
        return (
            contact.get("dateLastActivity")
            or contact.get("lastActivity")
            or contact.get("dateUpdated")
            or ""
        )


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Revival Scanner — GHL Contact Mining")
    parser.add_argument("--scan", action="store_true", help="Run revival scan")
    parser.add_argument("--limit", type=int, default=10, help="Max candidates to return")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if not args.scan:
        parser.print_help()
        return

    scanner = RevivalScanner()
    candidates = scanner.scan(limit=args.limit)

    if args.json:
        print(json.dumps([asdict(c) for c in candidates], indent=2, default=str))
    else:
        console.print(f"\n[bold]Revival Scanner Results[/bold] ({len(candidates)} candidates)\n")

        if not candidates:
            console.print("[dim]No revival candidates found.[/dim]")
            return

        for i, c in enumerate(candidates, 1):
            color = "green" if c.revival_score >= 0.7 else "yellow" if c.revival_score >= 0.5 else "dim"
            console.print(
                f"  {i}. [{color}]{c.email}[/{color}] "
                f"score={c.revival_score:.2f} reason={c.revival_reason} "
                f"inactive={c.days_inactive}d stage={c.pipeline_stage or '?'}"
            )
            console.print(
                f"     {c.first_name} {c.last_name} | {c.title} @ {c.company}"
            )
            ctx = c.context
            console.print(
                f"     touches={ctx.get('total_touchpoints', 0)} "
                f"emails={ctx.get('emails_sent', 0)} "
                f"opens={ctx.get('emails_opened', 0)} "
                f"replies={ctx.get('replies_received', 0)} "
                f"linkedin={'connected' if ctx.get('linkedin_connected') else 'no'}"
            )


if __name__ == "__main__":
    main()
