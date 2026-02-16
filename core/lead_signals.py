#!/usr/bin/env python3
"""
Lead Signal Loop & Engagement Monitor
=========================================
Monaco-inspired engagement-driven lead status management.

Transforms the linear pipeline (scrape→send→done) into a feedback loop
where webhook engagement signals update lead status and trigger next actions.

Status Progression:
    pending → approved → dispatched → sent → opened → replied → meeting_booked

Divergent States:
    bounced, unsubscribed, ghosted, stalled, engaged_not_replied

Signal Sources:
    - Instantly webhooks: open, reply, bounce, unsubscribe
    - HeyReach webhooks: connection_accepted, message_reply, campaign_completed
    - RB2B webhooks: visitor identification (website intent)
    - Time-based rules: ghosting (72h no open), stalling (7d no reply)
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger("caio.lead_signals")

# ─── Lead Status Definitions ───────────────────────────────────────────────

LEAD_STATUSES = {
    # Pipeline progression
    "pending": "Email crafted, awaiting approval",
    "approved": "Approved by Gatekeeper, awaiting dispatch",
    "dispatched": "Sent to Instantly/HeyReach campaign",
    "sent": "Email delivered to recipient inbox",
    # Engagement signals
    "opened": "Recipient opened the email",
    "replied": "Recipient replied (positive, negative, or neutral)",
    "meeting_booked": "Meeting scheduled from this lead",
    # Engagement decay
    "ghosted": "No open after 72h since send",
    "stalled": "Opened but no reply after 7 days",
    "engaged_not_replied": "Multiple opens, no reply (interested but hesitant)",
    # Terminal states
    "bounced": "Email bounced (bad address)",
    "unsubscribed": "Recipient opted out",
    "rejected": "Rejected by Gatekeeper",
    "disqualified": "Failed ICP criteria",
    # LinkedIn states
    "linkedin_sent": "Connection request sent via HeyReach",
    "linkedin_connected": "Connection accepted — warm follow-up eligible",
    "linkedin_replied": "Replied to LinkedIn message",
    "linkedin_exhausted": "HeyReach campaign completed, no response",
    # Revival states
    "revival_candidate": "Flagged by revival scanner for re-engagement",
    "revival_queued": "Approved for re-engagement, awaiting dispatch",
    "revival_sent": "Re-engagement email dispatched via warm domain",
}

# Time thresholds for engagement decay
GHOST_THRESHOLD_HOURS = 72
STALL_THRESHOLD_DAYS = 7
ENGAGED_NOT_REPLIED_OPENS = 2


class LeadStatusManager:
    """
    Manages lead engagement status based on multi-channel signals.

    Reads/writes status to individual lead files in .hive-mind/lead_status/.
    Each file is keyed by lead email (sanitized filename).
    """

    def __init__(self, hive_dir: Path = None):
        self.hive_dir = hive_dir or Path(".hive-mind")
        self.status_dir = self.hive_dir / "lead_status"
        self.status_dir.mkdir(parents=True, exist_ok=True)
        self.shadow_dir = self.hive_dir / "shadow_mode_emails"

    def _email_to_filename(self, email: str) -> str:
        """Convert email to safe filename."""
        return email.lower().replace("@", "_at_").replace(".", "_") + ".json"

    def get_lead_status(self, email: str) -> Optional[Dict[str, Any]]:
        """Get current status record for a lead."""
        filepath = self.status_dir / self._email_to_filename(email)
        if filepath.exists():
            try:
                return json.loads(filepath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def update_lead_status(
        self,
        email: str,
        new_status: str,
        signal_source: str,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Update lead status based on an engagement signal.

        Args:
            email: Lead's email address (primary key)
            new_status: New status from LEAD_STATUSES
            signal_source: What triggered this update (e.g., "instantly_webhook:reply")
            metadata: Additional signal data (reply text, bounce reason, etc.)

        Returns:
            Updated lead status record
        """
        existing = self.get_lead_status(email) or {
            "email": email,
            "status": "unknown",
            "status_history": [],
            "signals": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "open_count": 0,
            "reply_count": 0,
            "linkedin_status": None,
        }

        old_status = existing["status"]
        now = datetime.now(timezone.utc).isoformat()

        # Record status transition
        if old_status != new_status:
            existing["status_history"].append({
                "from": old_status,
                "to": new_status,
                "at": now,
                "source": signal_source,
            })

        existing["status"] = new_status
        existing["updated_at"] = now

        # Record the signal
        signal_record = {
            "type": signal_source,
            "status": new_status,
            "at": now,
        }
        if metadata:
            signal_record["data"] = metadata
        existing["signals"].append(signal_record)

        # Track open/reply counts
        if new_status == "opened":
            existing["open_count"] = existing.get("open_count", 0) + 1
        elif new_status in ("replied", "linkedin_replied"):
            existing["reply_count"] = existing.get("reply_count", 0) + 1

        # Write to file
        filepath = self.status_dir / self._email_to_filename(email)
        filepath.write_text(json.dumps(existing, indent=2), encoding="utf-8")

        logger.info(
            "Lead %s: %s → %s (source: %s)",
            email, old_status, new_status, signal_source,
        )

        return existing

    # ─── Signal Handlers (called from webhook handlers) ─────────────────

    def handle_email_opened(self, email: str, campaign_id: str = "") -> Dict:
        """Instantly webhook: email opened."""
        current = self.get_lead_status(email)
        open_count = (current.get("open_count", 0) + 1) if current else 1

        # Multiple opens without reply = engaged but hesitant
        if current and current["status"] in ("opened", "engaged_not_replied"):
            if open_count >= ENGAGED_NOT_REPLIED_OPENS:
                return self.update_lead_status(
                    email, "engaged_not_replied", "instantly_webhook:open",
                    {"campaign_id": campaign_id, "open_count": open_count},
                )

        return self.update_lead_status(
            email, "opened", "instantly_webhook:open",
            {"campaign_id": campaign_id},
        )

    def handle_email_replied(self, email: str, reply_text: str = "", campaign_id: str = "") -> Dict:
        """Instantly webhook: email reply received."""
        return self.update_lead_status(
            email, "replied", "instantly_webhook:reply",
            {"campaign_id": campaign_id, "reply_preview": reply_text[:200]},
        )

    def handle_email_bounced(self, email: str, bounce_type: str = "") -> Dict:
        """Instantly webhook: email bounced."""
        return self.update_lead_status(
            email, "bounced", "instantly_webhook:bounce",
            {"bounce_type": bounce_type},
        )

    def handle_email_unsubscribed(self, email: str) -> Dict:
        """Instantly webhook: recipient unsubscribed."""
        return self.update_lead_status(
            email, "unsubscribed", "instantly_webhook:unsubscribe",
        )

    def handle_linkedin_connection_sent(self, linkedin_url: str, email: str = "") -> Dict:
        """HeyReach webhook: connection request sent."""
        if not email:
            return {}
        return self.update_lead_status(
            email, "linkedin_sent", "heyreach_webhook:connection_sent",
            {"linkedin_url": linkedin_url},
        )

    def handle_linkedin_connection_accepted(self, linkedin_url: str, email: str = "") -> Dict:
        """HeyReach webhook: connection accepted — warm follow-up eligible."""
        if not email:
            return {}
        record = self.update_lead_status(
            email, "linkedin_connected", "heyreach_webhook:connection_accepted",
            {"linkedin_url": linkedin_url},
        )
        record["linkedin_status"] = "connected"
        # Re-save with linkedin_status
        filepath = self.status_dir / self._email_to_filename(email)
        filepath.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return record

    def handle_linkedin_reply(self, linkedin_url: str, message_text: str = "", email: str = "") -> Dict:
        """HeyReach webhook: LinkedIn message reply."""
        if not email:
            return {}
        return self.update_lead_status(
            email, "linkedin_replied", "heyreach_webhook:message_reply",
            {"linkedin_url": linkedin_url, "message_preview": message_text[:200]},
        )

    # ─── Revival Eligibility ─────────────────────────────────────────────

    def is_revivable(self, email: str) -> bool:
        """
        Check if a lead can be revived (not terminal, not in active outbound).

        A lead is revivable if:
          - No status record exists (unknown GHL contact = potentially revivable)
          - Status is NOT terminal (bounced, unsubscribed, rejected, disqualified)
          - Status is NOT actively in pipeline (pending, approved, dispatched, etc.)
        """
        status = self.get_lead_status(email)
        if not status:
            return True
        terminal = {"bounced", "unsubscribed", "rejected", "disqualified"}
        active = {
            "pending", "approved", "dispatched", "sent", "opened",
            "linkedin_sent", "linkedin_connected",
            "revival_queued", "revival_sent",
        }
        return status.get("status") not in (terminal | active)

    # ─── Engagement Decay Detection (Ghosting / Stalling) ──────────────

    def detect_engagement_decay(self) -> Dict[str, List[Dict]]:
        """
        Scan all leads for ghosting and stalling patterns.

        Returns:
            {
                "ghosted": [leads that went ghost],
                "stalled": [leads that stalled],
                "engaged_not_replied": [leads opening but not replying],
            }
        """
        now = datetime.now(timezone.utc)
        ghost_cutoff = now - timedelta(hours=GHOST_THRESHOLD_HOURS)
        stall_cutoff = now - timedelta(days=STALL_THRESHOLD_DAYS)

        results = {"ghosted": [], "stalled": [], "engaged_not_replied": []}

        for filepath in self.status_dir.glob("*.json"):
            try:
                record = json.loads(filepath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            status = record.get("status", "")
            email = record.get("email", "")
            updated_at_str = record.get("updated_at", "")

            if not updated_at_str:
                continue

            try:
                updated_at = datetime.fromisoformat(updated_at_str)
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            # Ghost detection: dispatched/sent but never opened after 72h
            if status in ("dispatched", "sent") and updated_at < ghost_cutoff:
                self.update_lead_status(
                    email, "ghosted", "engagement_monitor:ghost_detection",
                    {"hours_since_send": (now - updated_at).total_seconds() / 3600},
                )
                results["ghosted"].append({"email": email, "since": updated_at_str})

            # Stall detection: opened but no reply after 7 days
            elif status == "opened" and updated_at < stall_cutoff:
                self.update_lead_status(
                    email, "stalled", "engagement_monitor:stall_detection",
                    {"days_since_open": (now - updated_at).days},
                )
                results["stalled"].append({"email": email, "since": updated_at_str})

            # Engaged but not replied: 2+ opens, still no reply
            elif status == "opened" and record.get("open_count", 0) >= ENGAGED_NOT_REPLIED_OPENS:
                self.update_lead_status(
                    email, "engaged_not_replied",
                    "engagement_monitor:engagement_pattern",
                    {"open_count": record["open_count"]},
                )
                results["engaged_not_replied"].append({
                    "email": email,
                    "open_count": record["open_count"],
                })

        logger.info(
            "Engagement decay scan: %d ghosted, %d stalled, %d engaged_not_replied",
            len(results["ghosted"]),
            len(results["stalled"]),
            len(results["engaged_not_replied"]),
        )
        return results

    # ─── Aggregation ───────────────────────────────────────────────────

    def get_all_lead_statuses(self) -> List[Dict[str, Any]]:
        """Get all lead status records for dashboard display."""
        leads = []
        for filepath in sorted(self.status_dir.glob("*.json")):
            try:
                record = json.loads(filepath.read_text(encoding="utf-8"))
                leads.append(record)
            except (json.JSONDecodeError, OSError):
                continue
        return leads

    def get_status_summary(self) -> Dict[str, int]:
        """Get count of leads by status for dashboard KPIs."""
        counts: Dict[str, int] = {}
        for filepath in self.status_dir.glob("*.json"):
            try:
                record = json.loads(filepath.read_text(encoding="utf-8"))
                status = record.get("status", "unknown")
                counts[status] = counts.get(status, 0) + 1
            except (json.JSONDecodeError, OSError):
                continue
        return counts

    # ─── Bootstrap: Seed from existing shadow emails ───────────────────

    def bootstrap_from_shadow_emails(self) -> int:
        """
        Seed lead status records from existing shadow email files.
        Only creates records for leads that don't already have status files.
        Returns count of new records created.
        """
        created = 0
        if not self.shadow_dir.exists():
            return created

        for filepath in self.shadow_dir.glob("*.json"):
            try:
                email_data = json.loads(filepath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            email = email_data.get("to", "")
            if not email:
                continue

            # Skip if already tracked
            if self.get_lead_status(email):
                continue

            status = email_data.get("status", "pending")
            context = email_data.get("context", {})
            recipient = email_data.get("recipient_data", {})

            record = {
                "email": email,
                "status": status,
                "status_history": [{"from": "new", "to": status, "at": email_data.get("timestamp", ""), "source": "bootstrap"}],
                "signals": [],
                "created_at": email_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                "updated_at": email_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                "open_count": 0,
                "reply_count": 0,
                "linkedin_status": None,
                "name": recipient.get("name", ""),
                "company": recipient.get("company", ""),
                "title": recipient.get("title", ""),
                "linkedin_url": recipient.get("linkedin_url", ""),
                "icp_tier": context.get("icp_tier", ""),
                "icp_score": context.get("icp_score", 0),
                "campaign_id": context.get("campaign_id", ""),
                "email_id": email_data.get("email_id", ""),
            }

            status_file = self.status_dir / self._email_to_filename(email)
            status_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
            created += 1

        logger.info("Bootstrap: created %d lead status records from shadow emails", created)
        return created
