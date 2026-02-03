#!/usr/bin/env python3
"""
Hot Lead Detector - Real-time Lead Escalation Service
======================================================

Bridges GHL webhooks to the escalation system. Monitors incoming
conversations/replies and immediately alerts AE/HoS for warm leads.

Architecture:
    GHL Webhook → WebhookQueue → HotLeadDetector → SentimentAnalyzer
                                                 → EscalationRouting
                                                 → NotificationManager → Slack/SMS/Email

Usage:
    # Start the detector service
    python -m core.hot_lead_detector
    
    # Or integrate into webhook processing
    from core.hot_lead_detector import HotLeadDetector
    detector = HotLeadDetector()
    await detector.process_webhook_event(payload)
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from core.sentiment_analyzer import SentimentAnalyzer, SentimentResult, Sentiment, BuyingSignal
from core.routing import evaluate_escalation_triggers, HandoffTicket, HandoffPriority
from core.notifications import get_notification_manager
from core.feedback_collector import FeedbackCollector

logger = logging.getLogger("hot_lead_detector")


class LeadTemperature(Enum):
    """Lead engagement temperature classification."""
    HOT = "hot"          # Ready to buy - immediate AE action
    WARM = "warm"        # High interest - prioritize follow-up
    COOL = "cool"        # Some interest - nurture sequence
    COLD = "cold"        # No interest - pause or remove


@dataclass
class HotLeadAlert:
    """Alert for a hot lead requiring immediate attention."""
    alert_id: str
    lead_id: str
    contact_email: str
    contact_name: str
    company_name: str
    temperature: str
    trigger_reason: str
    reply_snippet: str
    sentiment_score: float
    buying_signal: str
    recommended_action: str
    sla_minutes: int
    created_at: str
    handoff_tickets: List[Dict[str, Any]] = field(default_factory=list)
    notified_channels: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HotLeadDetector:
    """
    Real-time detector for warm/hot leads from GHL webhooks.
    
    Integrates:
    - SentimentAnalyzer for reply classification
    - EscalationRouting for handoff ticket creation
    - NotificationManager for AE/HoS alerts
    """
    
    # Temperature thresholds
    HOT_THRESHOLD = 0.8      # Immediate AE action
    WARM_THRESHOLD = 0.5     # Priority follow-up
    COOL_THRESHOLD = 0.2     # Nurture
    
    # Events that trigger analysis
    ANALYZABLE_EVENTS = {
        "email.replied",
        "contact.reply",
        "ContactReply",
        "InboundMessage",
        "sms.received",
        "conversation.message",
    }
    
    def __init__(self):
        self.sentiment_analyzer = SentimentAnalyzer()
        self.notification_manager = get_notification_manager()
        self.feedback_collector = FeedbackCollector()
        
        # Alert storage
        self.alerts_dir = Path(".hive-mind/hot_lead_alerts")
        self.alerts_dir.mkdir(parents=True, exist_ok=True)
        
        # Stats tracking
        self.stats = {
            "events_processed": 0,
            "hot_leads_detected": 0,
            "warm_leads_detected": 0,
            "alerts_sent": 0,
            "last_processed": None,
        }
    
    async def process_webhook_event(self, payload: Dict[str, Any]) -> Optional[HotLeadAlert]:
        """
        Process an incoming GHL webhook event and detect hot leads.
        
        Args:
            payload: Raw webhook payload from GHL
            
        Returns:
            HotLeadAlert if hot/warm lead detected, None otherwise
        """
        event_type = payload.get("type", payload.get("event", ""))
        
        if event_type not in self.ANALYZABLE_EVENTS:
            logger.debug(f"Skipping non-analyzable event: {event_type}")
            return None
        
        self.stats["events_processed"] += 1
        self.stats["last_processed"] = datetime.now(timezone.utc).isoformat()
        
        # Extract message content
        message_body = self._extract_message_body(payload)
        if not message_body or len(message_body) < 10:
            logger.debug("No substantial message body to analyze")
            return None
        
        # Analyze sentiment
        sentiment_result = self.sentiment_analyzer.analyze(message_body)
        
        # Calculate temperature score
        temperature, score = self._calculate_temperature(sentiment_result, payload)
        
        if temperature in (LeadTemperature.HOT, LeadTemperature.WARM):
            alert = await self._create_and_dispatch_alert(
                payload, sentiment_result, temperature, score
            )
            return alert
        
        return None
    
    def _extract_message_body(self, payload: Dict[str, Any]) -> str:
        """Extract the message body from various GHL payload formats."""
        # Try common GHL payload structures
        candidates = [
            payload.get("message", {}).get("body"),
            payload.get("body"),
            payload.get("text"),
            payload.get("content"),
            payload.get("reply", {}).get("body"),
            payload.get("data", {}).get("message"),
            payload.get("data", {}).get("body"),
        ]
        
        for candidate in candidates:
            if candidate and isinstance(candidate, str):
                return candidate.strip()
        
        return ""
    
    def _extract_contact_info(self, payload: Dict[str, Any]) -> Dict[str, str]:
        """Extract contact information from payload."""
        contact = payload.get("contact", {})
        return {
            "lead_id": payload.get("contactId", payload.get("contact_id", contact.get("id", "unknown"))),
            "email": contact.get("email", payload.get("email", "")),
            "name": contact.get("name", contact.get("firstName", "") + " " + contact.get("lastName", "")).strip(),
            "company": contact.get("companyName", payload.get("company", "")),
            "title": contact.get("title", contact.get("jobTitle", "")),
            "phone": contact.get("phone", ""),
        }
    
    def _calculate_temperature(
        self, 
        sentiment: SentimentResult, 
        payload: Dict[str, Any]
    ) -> tuple[LeadTemperature, float]:
        """
        Calculate lead temperature based on sentiment and context.
        
        Scoring factors:
        - Sentiment: very_positive (+0.4), positive (+0.2)
        - Buying signal: HIGH_INTENT (+0.4), MEDIUM_INTENT (+0.2)
        - Urgency: detected (+0.2)
        - Objection: competitor (-0.1), price (neutral - buying signal)
        """
        score = 0.0
        
        # Sentiment scoring
        if sentiment.sentiment == Sentiment.VERY_POSITIVE:
            score += 0.4
        elif sentiment.sentiment == Sentiment.POSITIVE:
            score += 0.2
        elif sentiment.sentiment == Sentiment.NEGATIVE:
            score -= 0.2
        elif sentiment.sentiment == Sentiment.VERY_NEGATIVE:
            score -= 0.4
        
        # Buying signal scoring
        if sentiment.buying_signal == BuyingSignal.HIGH_INTENT:
            score += 0.4
        elif sentiment.buying_signal == BuyingSignal.MEDIUM_INTENT:
            score += 0.2
        elif sentiment.buying_signal == BuyingSignal.LOW_INTENT:
            score += 0.1
        
        # Urgency bonus
        if sentiment.urgency_detected:
            score += 0.2
        
        # Clamp score
        score = max(0.0, min(1.0, score))
        
        # Determine temperature
        if score >= self.HOT_THRESHOLD:
            return LeadTemperature.HOT, score
        elif score >= self.WARM_THRESHOLD:
            return LeadTemperature.WARM, score
        elif score >= self.COOL_THRESHOLD:
            return LeadTemperature.COOL, score
        else:
            return LeadTemperature.COLD, score
    
    async def _create_and_dispatch_alert(
        self,
        payload: Dict[str, Any],
        sentiment: SentimentResult,
        temperature: LeadTemperature,
        score: float
    ) -> HotLeadAlert:
        """Create alert and dispatch to notification channels."""
        import uuid
        
        contact = self._extract_contact_info(payload)
        message_body = self._extract_message_body(payload)
        
        # Create handoff tickets via routing system
        lead_data = {
            "lead_id": contact["lead_id"],
            "email": contact["email"],
            "name": contact["name"],
            "company": contact["company"],
            "title": contact["title"],
        }
        
        reply_data = {
            "body": message_body,
            "sentiment": sentiment.sentiment.value,
        }
        
        handoff_tickets = evaluate_escalation_triggers(lead_data, reply_data)
        
        # Determine trigger reason
        trigger_reasons = []
        if sentiment.sentiment == Sentiment.VERY_POSITIVE:
            trigger_reasons.append("Very positive sentiment")
        if sentiment.buying_signal == BuyingSignal.HIGH_INTENT:
            trigger_reasons.append("High buying intent")
        if sentiment.urgency_detected:
            trigger_reasons.append("Urgency detected")
        if handoff_tickets:
            trigger_reasons.append(f"Escalation trigger: {handoff_tickets[0].trigger}")
        
        # SLA based on temperature
        sla_minutes = 5 if temperature == LeadTemperature.HOT else 30
        
        alert = HotLeadAlert(
            alert_id=f"hot_{uuid.uuid4().hex[:8]}",
            lead_id=contact["lead_id"],
            contact_email=contact["email"],
            contact_name=contact["name"],
            company_name=contact["company"],
            temperature=temperature.value,
            trigger_reason="; ".join(trigger_reasons) if trigger_reasons else "High engagement score",
            reply_snippet=message_body[:300] + "..." if len(message_body) > 300 else message_body,
            sentiment_score=score,
            buying_signal=sentiment.buying_signal.value,
            recommended_action=sentiment.recommended_action,
            sla_minutes=sla_minutes,
            created_at=datetime.now(timezone.utc).isoformat(),
            handoff_tickets=[asdict(t) for t in handoff_tickets],
        )
        
        # Update stats
        if temperature == LeadTemperature.HOT:
            self.stats["hot_leads_detected"] += 1
        else:
            self.stats["warm_leads_detected"] += 1
        
        # Dispatch notifications
        await self._dispatch_notifications(alert, temperature)
        
        # Persist alert
        self._save_alert(alert)
        
        logger.info(f"🔥 {temperature.value.upper()} LEAD: {contact['name']} ({contact['email']}) - {alert.trigger_reason}")
        
        return alert
    
    async def _dispatch_notifications(self, alert: HotLeadAlert, temperature: LeadTemperature):
        """Send notifications via appropriate channels."""
        notified = []
        
        # Create a notification-compatible object
        @dataclass
        class AlertNotification:
            review_id: str
            campaign_name: str
            campaign_type: str
            lead_count: int
            avg_icp_score: float
            urgency: str
            description: str
            email_preview: Dict[str, str]
        
        notification = AlertNotification(
            review_id=alert.alert_id,
            campaign_name=f"🔥 {temperature.value.upper()} LEAD: {alert.contact_name}",
            campaign_type="hot_lead_alert",
            lead_count=1,
            avg_icp_score=alert.sentiment_score * 100,
            urgency="critical" if temperature == LeadTemperature.HOT else "urgent",
            description=f"{alert.trigger_reason}\n\nReply: {alert.reply_snippet}",
            email_preview={"subject_a": alert.recommended_action},
        )
        
        # Determine escalation level
        level = 3 if temperature == LeadTemperature.HOT else 2
        
        try:
            result = await self.notification_manager.escalate(notification, level=level)
            
            if result.get("slack"):
                notified.append("slack")
            if result.get("sms"):
                notified.append("sms")
            if result.get("email"):
                notified.append("email")
            
            alert.notified_channels = notified
            self.stats["alerts_sent"] += 1
            
        except Exception as e:
            logger.error(f"Failed to dispatch notifications: {e}")
    
    def _save_alert(self, alert: HotLeadAlert):
        """Persist alert to disk."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        alerts_file = self.alerts_dir / f"alerts_{date_str}.json"
        
        # Load existing alerts
        existing = []
        if alerts_file.exists():
            try:
                with open(alerts_file, 'r') as f:
                    existing = json.load(f)
            except Exception:
                pass
        
        # Append new alert
        existing.append(alert.to_dict())
        
        # Save
        with open(alerts_file, 'w') as f:
            json.dump(existing, f, indent=2)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get detector statistics."""
        return self.stats.copy()
    
    def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent hot lead alerts."""
        all_alerts = []
        
        # Load last 7 days of alerts
        for days_ago in range(7):
            date = datetime.now(timezone.utc)
            if days_ago > 0:
                from datetime import timedelta
                date = date - timedelta(days=days_ago)
            
            alerts_file = self.alerts_dir / f"alerts_{date.strftime('%Y-%m-%d')}.json"
            if alerts_file.exists():
                try:
                    with open(alerts_file, 'r') as f:
                        all_alerts.extend(json.load(f))
                except Exception:
                    pass
        
        # Sort by created_at descending
        all_alerts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return all_alerts[:limit]


# =============================================================================
# WEBHOOK QUEUE PROCESSOR
# =============================================================================

class WebhookQueueProcessor:
    """
    Processes webhook events from the queue file.
    
    Runs as a background service, polling for new events
    and passing them through the HotLeadDetector.
    """
    
    def __init__(self, poll_interval: float = 2.0):
        self.detector = HotLeadDetector()
        self.poll_interval = poll_interval
        self.running = False
        self.queue_file = Path(".hive-mind/webhook_queue.json")
        self.processed_ids: set = set()
    
    async def start(self):
        """Start the queue processor."""
        self.running = True
        logger.info("🚀 Hot Lead Detector started - monitoring webhook queue")
        
        while self.running:
            try:
                await self._process_pending_events()
            except Exception as e:
                logger.error(f"Error processing queue: {e}")
            
            await asyncio.sleep(self.poll_interval)
    
    def stop(self):
        """Stop the queue processor."""
        self.running = False
        logger.info("Hot Lead Detector stopped")
    
    async def _process_pending_events(self):
        """Process pending events from the queue."""
        if not self.queue_file.exists():
            return
        
        try:
            with open(self.queue_file, 'r') as f:
                data = json.load(f)
        except Exception:
            return
        
        events = data.get("events", [])
        
        for event in events:
            event_id = event.get("event_id")
            
            # Skip already processed
            if event_id in self.processed_ids:
                continue
            
            # Skip already marked as processed in queue
            if event.get("processed"):
                self.processed_ids.add(event_id)
                continue
            
            # Process the event
            payload = event.get("payload", {})
            source = event.get("source", "")
            
            if source == "gohighlevel":
                alert = await self.detector.process_webhook_event(payload)
                if alert:
                    logger.info(f"Alert created: {alert.alert_id}")
            
            self.processed_ids.add(event_id)
            
            # Mark as processed in queue file
            event["processed"] = True
            event["processed_at"] = datetime.now(timezone.utc).isoformat()
        
        # Save updated queue
        with open(self.queue_file, 'w') as f:
            json.dump(data, f, indent=2)


# =============================================================================
# CLI / MAIN
# =============================================================================

async def main():
    """Run the hot lead detector service."""
    import signal
    
    processor = WebhookQueueProcessor()
    
    def handle_shutdown(sig, frame):
        logger.info("Shutting down...")
        processor.stop()
    
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    print("=" * 60)
    print("🔥 HOT LEAD DETECTOR SERVICE")
    print("=" * 60)
    print("Monitoring GHL webhooks for warm/hot leads...")
    print("Press Ctrl+C to stop\n")
    
    await processor.start()


if __name__ == "__main__":
    asyncio.run(main())
