#!/usr/bin/env python3
"""
Unified Activity Timeline
============================
Monaco-inspired per-lead activity aggregation.

Aggregates events from ALL sources into a single chronological timeline:
  - Shadow emails (crafted/approved/rejected)
  - Pipeline runs (segmentation, campaign creation)
  - Instantly dispatch (campaign creation, lead addition)
  - Instantly webhooks (opens, replies, bounces, unsubscribes)
  - HeyReach webhooks (connection requests, replies, campaign events)
  - Lead status transitions (signal loop state changes)

Every lead gets a complete history: "What happened, when, and which channel."
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger("caio.activity_timeline")


class ActivityTimeline:
    """
    Aggregates all lead activity into a unified chronological timeline.

    Usage:
        timeline = ActivityTimeline()
        events = timeline.get_lead_timeline("john@acme.com")
        # Returns sorted list of events across all channels
    """

    def __init__(self, hive_dir: Path = None):
        self.hive_dir = hive_dir or Path(".hive-mind")
        self.shadow_dir = self.hive_dir / "shadow_mode_emails"
        self.status_dir = self.hive_dir / "lead_status"
        self.runs_dir = self.hive_dir / "pipeline_runs"
        self.events_file = self.hive_dir / "events.jsonl"
        self.instantly_log = self.hive_dir / "instantly_dispatch_log.jsonl"
        self.heyreach_log = self.hive_dir / "heyreach_events.jsonl"
        self.followups_dir = self.hive_dir / "heyreach_followups"

    def get_lead_timeline(self, email: str) -> List[Dict[str, Any]]:
        """
        Get unified timeline for a specific lead.

        Returns chronologically sorted list of events:
        [
            {"timestamp": "...", "type": "email_crafted", "channel": "pipeline", "summary": "...", "data": {...}},
            {"timestamp": "...", "type": "email_approved", "channel": "gatekeeper", ...},
            {"timestamp": "...", "type": "email_dispatched", "channel": "instantly", ...},
            {"timestamp": "...", "type": "email_opened", "channel": "instantly", ...},
        ]
        """
        events = []

        # 1. Shadow emails (crafted/approved/sent)
        events.extend(self._get_shadow_email_events(email))

        # 2. Lead status signals (engagement loop)
        events.extend(self._get_status_signal_events(email))

        # 3. Dispatch log (Instantly campaign events)
        events.extend(self._get_dispatch_events(email))

        # 4. HeyReach events (LinkedIn activity)
        events.extend(self._get_heyreach_events(email))

        # 5. Pipeline events (segmentation, etc.)
        events.extend(self._get_pipeline_events(email))

        # Sort chronologically
        events.sort(key=lambda e: e.get("timestamp", ""))

        return events

    def get_all_leads_summary(self) -> List[Dict[str, Any]]:
        """
        Get summary of all tracked leads with their latest activity.
        Used for dashboard lead list view.
        """
        leads = {}

        # Build from lead status files (primary source)
        if self.status_dir.exists():
            for filepath in self.status_dir.glob("*.json"):
                try:
                    record = json.loads(filepath.read_text(encoding="utf-8"))
                    email = record.get("email", "")
                    if email:
                        leads[email] = {
                            "email": email,
                            "name": record.get("name", ""),
                            "company": record.get("company", ""),
                            "title": record.get("title", ""),
                            "status": record.get("status", "unknown"),
                            "icp_tier": record.get("icp_tier", ""),
                            "icp_score": record.get("icp_score", 0),
                            "open_count": record.get("open_count", 0),
                            "reply_count": record.get("reply_count", 0),
                            "linkedin_status": record.get("linkedin_status"),
                            "updated_at": record.get("updated_at", ""),
                            "created_at": record.get("created_at", ""),
                            "signal_count": len(record.get("signals", [])),
                        }
                except (json.JSONDecodeError, OSError):
                    continue

        # Supplement from shadow emails for leads without status files
        if self.shadow_dir.exists():
            for filepath in self.shadow_dir.glob("*.json"):
                try:
                    data = json.loads(filepath.read_text(encoding="utf-8"))
                    email = data.get("to", "")
                    if email and email not in leads:
                        recipient = data.get("recipient_data", {})
                        context = data.get("context", {})
                        leads[email] = {
                            "email": email,
                            "name": recipient.get("name", ""),
                            "company": recipient.get("company", ""),
                            "title": recipient.get("title", ""),
                            "status": data.get("status", "pending"),
                            "icp_tier": context.get("icp_tier", ""),
                            "icp_score": context.get("icp_score", 0),
                            "open_count": 0,
                            "reply_count": 0,
                            "linkedin_status": None,
                            "updated_at": data.get("timestamp", ""),
                            "created_at": data.get("timestamp", ""),
                            "signal_count": 0,
                        }
                except (json.JSONDecodeError, OSError):
                    continue

        # Sort by most recently updated
        result = sorted(
            leads.values(),
            key=lambda l: l.get("updated_at", ""),
            reverse=True,
        )
        return result

    def get_funnel_summary(self) -> Dict[str, Any]:
        """
        Get pipeline funnel counts for dashboard visualization.

        Returns counts at each stage + engagement breakdown.
        """
        funnel = {
            "pipeline": {"pending": 0, "approved": 0, "rejected": 0},
            "outreach": {"dispatched": 0, "sent": 0},
            "engagement": {"opened": 0, "replied": 0, "meeting_booked": 0},
            "decay": {"ghosted": 0, "stalled": 0, "engaged_not_replied": 0},
            "terminal": {"bounced": 0, "unsubscribed": 0, "disqualified": 0},
            "linkedin": {"linkedin_sent": 0, "linkedin_connected": 0, "linkedin_replied": 0, "linkedin_exhausted": 0},
            "total_leads": 0,
        }

        if not self.status_dir.exists():
            return funnel

        for filepath in self.status_dir.glob("*.json"):
            try:
                record = json.loads(filepath.read_text(encoding="utf-8"))
                status = record.get("status", "unknown")
                funnel["total_leads"] += 1

                if status in funnel["pipeline"]:
                    funnel["pipeline"][status] += 1
                elif status in funnel["outreach"]:
                    funnel["outreach"][status] += 1
                elif status in funnel["engagement"]:
                    funnel["engagement"][status] += 1
                elif status in funnel["decay"]:
                    funnel["decay"][status] += 1
                elif status in funnel["terminal"]:
                    funnel["terminal"][status] += 1
                elif status in funnel["linkedin"]:
                    funnel["linkedin"][status] += 1
            except (json.JSONDecodeError, OSError):
                continue

        return funnel

    # ─── Private helpers ───────────────────────────────────────────────

    def _get_shadow_email_events(self, email: str) -> List[Dict]:
        """Get email crafting/approval events for a lead."""
        events = []
        if not self.shadow_dir.exists():
            return events

        for filepath in self.shadow_dir.glob("*.json"):
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                if data.get("to", "").lower() != email.lower():
                    continue

                context = data.get("context", {})
                recipient = data.get("recipient_data", {})

                events.append({
                    "timestamp": data.get("timestamp", data.get("created_at", "")),
                    "type": "email_crafted",
                    "channel": "pipeline",
                    "summary": f"Email crafted for {recipient.get('name', email)}",
                    "data": {
                        "email_id": data.get("email_id", ""),
                        "subject": data.get("subject", ""),
                        "status": data.get("status", ""),
                        "tier": context.get("icp_tier", ""),
                        "icp_score": context.get("icp_score", 0),
                        "campaign_type": context.get("campaign_type", ""),
                        "priority": data.get("priority", ""),
                    },
                })
            except (json.JSONDecodeError, OSError):
                continue

        return events

    def _get_status_signal_events(self, email: str) -> List[Dict]:
        """Get engagement signal events from lead status history."""
        events = []
        status_file = self.status_dir / self._email_to_filename(email)

        if not status_file.exists():
            return events

        try:
            record = json.loads(status_file.read_text(encoding="utf-8"))
            for signal in record.get("signals", []):
                source = signal.get("type", "")
                channel = source.split(":")[0] if ":" in source else "system"

                events.append({
                    "timestamp": signal.get("at", ""),
                    "type": signal.get("status", "signal"),
                    "channel": channel,
                    "summary": self._signal_to_summary(signal),
                    "data": signal.get("data", {}),
                })
        except (json.JSONDecodeError, OSError):
            pass

        return events

    def _get_dispatch_events(self, email: str) -> List[Dict]:
        """Get Instantly dispatch events mentioning this lead."""
        events = []
        if not self.instantly_log.exists():
            return events

        try:
            for line in self.instantly_log.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    # Check if any shadow_email_id contains parts of the email
                    shadow_ids = entry.get("shadow_email_ids", [])
                    email_part = email.split("@")[0].replace(".", "_")
                    if any(email_part in sid for sid in shadow_ids):
                        events.append({
                            "timestamp": entry.get("timestamp", entry.get("dispatched_at", "")),
                            "type": "email_dispatched",
                            "channel": "instantly",
                            "summary": f"Dispatched to Instantly campaign: {entry.get('campaign_name', '')}",
                            "data": {
                                "campaign_name": entry.get("campaign_name", ""),
                                "campaign_id": entry.get("campaign_id"),
                                "status": entry.get("status", ""),
                            },
                        })
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass

        return events

    def _get_heyreach_events(self, email: str) -> List[Dict]:
        """Get HeyReach LinkedIn events for this lead."""
        events = []
        if not self.heyreach_log.exists():
            return events

        try:
            for line in self.heyreach_log.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    payload = entry.get("payload", {})
                    # Match by email or linkedin_url
                    lead_email = payload.get("email", "")
                    if lead_email.lower() == email.lower():
                        event_type = entry.get("event_type", "")
                        events.append({
                            "timestamp": entry.get("received_at", entry.get("timestamp", "")),
                            "type": f"linkedin_{event_type.lower()}",
                            "channel": "heyreach",
                            "summary": self._heyreach_event_summary(event_type, payload),
                            "data": payload,
                        })
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass

        return events

    def _get_pipeline_events(self, email: str) -> List[Dict]:
        """Get pipeline events (segmentation, campaign creation) for this lead."""
        events = []
        if not self.events_file.exists():
            return events

        try:
            for line in self.events_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    payload = entry.get("payload", {})
                    lead_id = payload.get("lead_id", "")
                    # Match by lead_id containing email-like patterns
                    if lead_id and email.split("@")[0].replace(".", "") in lead_id.replace(".", ""):
                        events.append({
                            "timestamp": entry.get("timestamp", ""),
                            "type": entry.get("event_type", ""),
                            "channel": "pipeline",
                            "summary": self._pipeline_event_summary(entry),
                            "data": payload,
                        })
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass

        return events

    def _email_to_filename(self, email: str) -> str:
        return email.lower().replace("@", "_at_").replace(".", "_") + ".json"

    def _signal_to_summary(self, signal: Dict) -> str:
        """Convert a signal record to a human-readable summary."""
        status = signal.get("status", "")
        source = signal.get("type", "")
        data = signal.get("data", {})

        summaries = {
            "opened": "Email opened by recipient",
            "replied": f"Reply received: \"{data.get('reply_preview', '')[:60]}...\"" if data.get("reply_preview") else "Reply received",
            "bounced": f"Email bounced ({data.get('bounce_type', 'unknown')})",
            "unsubscribed": "Recipient unsubscribed",
            "ghosted": f"No engagement after {data.get('hours_since_send', 72):.0f}h",
            "stalled": f"Opened but no reply after {data.get('days_since_open', 7)} days",
            "engaged_not_replied": f"Opened {data.get('open_count', 2)}x but no reply",
            "linkedin_sent": "LinkedIn connection request sent",
            "linkedin_connected": "LinkedIn connection accepted",
            "linkedin_replied": "LinkedIn message reply received",
        }
        return summaries.get(status, f"Status changed to: {status}")

    def _heyreach_event_summary(self, event_type: str, payload: Dict) -> str:
        """Convert HeyReach event to human-readable summary."""
        name = payload.get("first_name", "Lead")
        summaries = {
            "CONNECTION_REQUEST_SENT": f"Connection request sent to {name}",
            "CONNECTION_REQUEST_ACCEPTED": f"{name} accepted LinkedIn connection",
            "MESSAGE_SENT": f"LinkedIn message sent to {name}",
            "MESSAGE_REPLY_RECEIVED": f"{name} replied on LinkedIn",
            "CAMPAIGN_COMPLETED": "LinkedIn campaign sequence completed",
        }
        return summaries.get(event_type, f"LinkedIn event: {event_type}")

    def _pipeline_event_summary(self, entry: Dict) -> str:
        """Convert pipeline event to human-readable summary."""
        event_type = entry.get("event_type", "")
        payload = entry.get("payload", {})

        summaries = {
            "lead_segmented": f"Lead scored and assigned to Tier {payload.get('tier', '?')}",
            "campaign_created": f"Campaign created: {payload.get('template', '')} ({payload.get('lead_count', 0)} leads)",
            "reply_classified": f"Reply classified as: {payload.get('objection_type', '')} → {payload.get('action', '')}",
            "research_completed": f"Research completed: {payload.get('segments_analyzed', 0)} segments analyzed",
        }
        return summaries.get(event_type, f"Pipeline event: {event_type}")
