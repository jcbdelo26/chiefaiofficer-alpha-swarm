#!/usr/bin/env python3
"""
Response Escalation Handler
============================

Routes and escalates email responses that require human attention:
- Vague responses with hints of interest
- Doubts or questions needing clarity
- Objections that need human touch
- High-value opportunities

All escalations route to Dani Apgar (HoS) via Slack and Email.
"""

import os
import json
import asyncio
import logging
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List

from core.sentiment_analyzer import SentimentAnalyzer, Sentiment, BuyingSignal
from core.notifications import get_notification_manager

logger = logging.getLogger("response_escalation")


class EscalationType(Enum):
    """Types of responses that need escalation."""
    VAGUE_INTEREST = "vague_interest"       # "Maybe", "Possibly", hints at interest
    DOUBT_QUESTIONS = "doubt_questions"     # Has questions, wants clarity
    OBJECTION_SOFT = "objection_soft"       # Timing, budget, but not hard no
    HIGH_VALUE = "high_value"               # Clear interest from Tier 1 lead
    MEETING_REQUEST = "meeting_request"     # Wants to schedule a call
    COMPETITOR_MENTION = "competitor_mention"  # Mentions a competitor


@dataclass
class EscalationTicket:
    """Ticket for HoS review."""
    ticket_id: str
    escalation_type: str
    contact_email: str
    contact_name: str
    company_name: str
    original_email_subject: str
    reply_content: str
    recommended_actions: List[str]
    urgency: str  # low, medium, high, critical
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "pending"
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Keywords that indicate vague interest (needs HoS review)
VAGUE_INTEREST_SIGNALS = [
    "maybe", "possibly", "might be interested", "not sure",
    "could be", "let me think", "need to consider", "interesting",
    "sounds interesting", "tell me more first", "depends",
    "what exactly", "how does it work", "can you explain",
    "i'm curious but", "need more info", "not opposed",
    "open to learning", "possibly in the future"
]

# Keywords that indicate questions/doubts needing clarity
DOUBT_QUESTION_SIGNALS = [
    "how much", "what's the cost", "pricing", "roi",
    "how long", "timeline", "what's involved", "process",
    "who else", "case studies", "examples", "references",
    "guarantee", "what if", "concerns about", "worried about",
    "not sure if", "how do you", "what makes you different",
    "why should", "compared to", "skeptical"
]

# Keywords that indicate soft objections (salvageable)
SOFT_OBJECTION_SIGNALS = [
    "not right now", "maybe later", "next quarter",
    "budget constraints", "need approval", "check with",
    "already looking at", "in the middle of", "recently signed",
    "too busy", "bad timing", "revisit in", "circle back",
    "on my radar", "keep me posted"
]


class ResponseEscalationHandler:
    """
    Handles escalation of email responses to HoS.
    
    Routes to Dani Apgar via:
    - Slack DM/channel with approve/reject actions
    - Email fallback
    """
    
    def __init__(self):
        self.notification_manager = get_notification_manager()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.tickets_dir = Path(".hive-mind/escalation_tickets")
        self.tickets_dir.mkdir(parents=True, exist_ok=True)
        
        # Dani's contact info (from env or default)
        self.hos_slack_id = os.getenv("SLACK_DANI_USER_ID", "U0123456789")
        self.hos_email = os.getenv("HOS_EMAIL", "dani@chiefaiofficer.com")
        self.hos_slack_channel = os.getenv("HOS_SLACK_CHANNEL", "#approvals")
    
    def analyze_response(self, reply_content: str) -> Dict[str, Any]:
        """
        Analyze a response to determine if escalation is needed.
        
        Returns:
            Dict with escalation_needed, type, urgency, and recommended_actions
        """
        reply_lower = reply_content.lower()
        
        # Check for vague interest
        vague_matches = [s for s in VAGUE_INTEREST_SIGNALS if s in reply_lower]
        
        # Check for doubt/questions
        doubt_matches = [s for s in DOUBT_QUESTION_SIGNALS if s in reply_lower]
        
        # Check for soft objections
        objection_matches = [s for s in SOFT_OBJECTION_SIGNALS if s in reply_lower]
        
        # Use sentiment analyzer for additional context
        sentiment_result = self.sentiment_analyzer.analyze(reply_content)
        
        # Determine escalation type and urgency
        escalation_needed = False
        escalation_type = None
        urgency = "medium"
        recommended_actions = []
        
        # High buying signal = high priority
        if sentiment_result.buying_signal in [BuyingSignal.HIGH_INTENT, BuyingSignal.MEDIUM_INTENT]:
            escalation_needed = True
            escalation_type = EscalationType.HIGH_VALUE
            urgency = "high"
            recommended_actions = [
                "Respond within 30 minutes",
                "Personalize response based on their specific interest",
                "Offer a specific meeting time"
            ]
        
        # Meeting request = critical
        elif any(kw in reply_lower for kw in ["schedule", "call", "meeting", "chat", "book time", "calendar"]):
            escalation_needed = True
            escalation_type = EscalationType.MEETING_REQUEST
            urgency = "critical"
            recommended_actions = [
                "Send calendar link immediately",
                "Confirm availability within 15 minutes",
                "Prepare personalized agenda"
            ]
        
        # Vague interest = needs nurturing
        elif vague_matches:
            escalation_needed = True
            escalation_type = EscalationType.VAGUE_INTEREST
            urgency = "medium"
            recommended_actions = [
                f"Address their uncertainty: detected '{vague_matches[0]}'",
                "Send value-first content (case study or quick win)",
                "Ask a clarifying question to understand their situation"
            ]
        
        # Doubt/questions = needs clarity
        elif doubt_matches:
            escalation_needed = True
            escalation_type = EscalationType.DOUBT_QUESTIONS
            urgency = "medium"
            recommended_actions = [
                f"Answer their question about: '{doubt_matches[0]}'",
                "Provide specific proof points or case study",
                "Offer a brief call to address concerns"
            ]
        
        # Soft objections = salvageable
        elif objection_matches:
            escalation_needed = True
            escalation_type = EscalationType.OBJECTION_SOFT
            urgency = "low"
            recommended_actions = [
                f"Handle objection: '{objection_matches[0]}'",
                "Acknowledge their situation",
                "Suggest a future touchpoint or nurture sequence"
            ]
        
        return {
            "escalation_needed": escalation_needed,
            "escalation_type": escalation_type.value if escalation_type else None,
            "urgency": urgency,
            "recommended_actions": recommended_actions,
            "sentiment": sentiment_result.sentiment.value,
            "buying_signal": sentiment_result.buying_signal.value,
            "vague_signals": vague_matches,
            "doubt_signals": doubt_matches,
            "objection_signals": objection_matches
        }
    
    async def create_escalation_ticket(
        self,
        contact_email: str,
        contact_name: str,
        company_name: str,
        original_subject: str,
        reply_content: str
    ) -> Optional[EscalationTicket]:
        """
        Create an escalation ticket if the response warrants it.
        
        Returns:
            EscalationTicket if escalation needed, None otherwise
        """
        analysis = self.analyze_response(reply_content)
        
        if not analysis["escalation_needed"]:
            logger.info(f"No escalation needed for response from {contact_email}")
            return None
        
        # Generate ticket ID
        ticket_id = f"ESC-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{contact_email.split('@')[0][:8]}"
        
        ticket = EscalationTicket(
            ticket_id=ticket_id,
            escalation_type=analysis["escalation_type"],
            contact_email=contact_email,
            contact_name=contact_name,
            company_name=company_name,
            original_email_subject=original_subject,
            reply_content=reply_content[:1000],  # Truncate long replies
            recommended_actions=analysis["recommended_actions"],
            urgency=analysis["urgency"]
        )
        
        # Save ticket
        ticket_file = self.tickets_dir / f"{ticket_id}.json"
        ticket_file.write_text(json.dumps(ticket.to_dict(), indent=2))
        
        # Send notification to Dani
        await self._notify_hos(ticket, analysis)
        
        logger.info(f"Created escalation ticket {ticket_id} ({analysis['escalation_type']})")
        return ticket
    
    async def _notify_hos(self, ticket: EscalationTicket, analysis: Dict[str, Any]):
        """Send Slack notification to Dani with approve/reject actions."""
        
        urgency_emoji = {
            "critical": "🚨",
            "high": "🔥",
            "medium": "⚠️",
            "low": "📋"
        }
        
        type_labels = {
            "vague_interest": "Vague Interest - Needs Nurturing",
            "doubt_questions": "Questions - Needs Clarity",
            "objection_soft": "Soft Objection - Salvageable",
            "high_value": "High Value - Priority Response",
            "meeting_request": "Meeting Request - Respond NOW",
            "competitor_mention": "Competitor Mention - Handle Carefully"
        }
        
        emoji = urgency_emoji.get(ticket.urgency, "📋")
        type_label = type_labels.get(ticket.escalation_type, ticket.escalation_type)
        
        # Build Slack Block Kit message with actions
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Response Escalation: {type_label}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Contact:*\n{ticket.contact_name}"},
                    {"type": "mrkdwn", "text": f"*Company:*\n{ticket.company_name}"},
                    {"type": "mrkdwn", "text": f"*Email:*\n{ticket.contact_email}"},
                    {"type": "mrkdwn", "text": f"*Urgency:*\n{ticket.urgency.upper()}"}
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Their Reply:*\n```{ticket.reply_content[:500]}```"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Recommended Actions:*\n" + "\n".join(f"• {a}" for a in ticket.recommended_actions)
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "📞 Call Now"},
                        "style": "primary",
                        "action_id": f"call_{ticket.ticket_id}",
                        "url": f"tel:{ticket.contact_email}"  # Would be phone if available
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✉️ Draft Response"},
                        "action_id": f"draft_{ticket.ticket_id}"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "⏰ Snooze 2hrs"},
                        "action_id": f"snooze_{ticket.ticket_id}"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Mark Handled"},
                        "style": "primary",
                        "action_id": f"handled_{ticket.ticket_id}"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Ticket: {ticket.ticket_id} | <@{self.hos_slack_id}>"}
                ]
            }
        ]
        
        # Send to Slack
        if self.notification_manager.slack_webhook:
            try:
                import aiohttp
                session = await self.notification_manager._get_session()
                payload = {
                    "channel": self.hos_slack_channel,
                    "blocks": blocks,
                    "text": f"Response escalation: {ticket.contact_name} from {ticket.company_name}"
                }
                async with session.post(self.notification_manager.slack_webhook, json=payload) as resp:
                    if resp.status == 200:
                        logger.info(f"Sent Slack escalation for {ticket.ticket_id}")
            except Exception as e:
                logger.error(f"Failed to send Slack escalation: {e}")
        
        # Also send email for critical/high urgency
        if ticket.urgency in ["critical", "high"]:
            await self.notification_manager.send_email_fallback(
                email=self.hos_email,
                item=ticket,
                subject=f"[{ticket.urgency.upper()}] Response Escalation: {ticket.company_name}"
            )
    
    async def resolve_ticket(
        self,
        ticket_id: str,
        resolved_by: str = "dani",
        notes: str = ""
    ) -> bool:
        """Mark a ticket as resolved."""
        ticket_file = self.tickets_dir / f"{ticket_id}.json"
        
        if not ticket_file.exists():
            logger.warning(f"Ticket {ticket_id} not found")
            return False
        
        ticket_data = json.loads(ticket_file.read_text())
        ticket_data["status"] = "resolved"
        ticket_data["resolved_at"] = datetime.now(timezone.utc).isoformat()
        ticket_data["resolved_by"] = resolved_by
        ticket_data["resolution_notes"] = notes
        
        ticket_file.write_text(json.dumps(ticket_data, indent=2))
        logger.info(f"Resolved ticket {ticket_id}")
        return True
    
    def get_pending_tickets(self) -> List[EscalationTicket]:
        """Get all pending escalation tickets."""
        pending = []
        for ticket_file in self.tickets_dir.glob("ESC-*.json"):
            try:
                data = json.loads(ticket_file.read_text())
                if data.get("status") == "pending":
                    pending.append(EscalationTicket(**data))
            except Exception:
                continue
        return sorted(pending, key=lambda t: t.created_at, reverse=True)


# Singleton
_escalation_handler = None

def get_escalation_handler() -> ResponseEscalationHandler:
    """Get singleton instance of ResponseEscalationHandler."""
    global _escalation_handler
    if _escalation_handler is None:
        _escalation_handler = ResponseEscalationHandler()
    return _escalation_handler
