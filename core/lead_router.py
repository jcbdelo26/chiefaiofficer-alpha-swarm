#!/usr/bin/env python3
"""
Lead Router - Context-Aware Outreach Platform Routing
======================================================

Routes leads to GoHighLevel based on engagement level:
- COLD: Cold outbound sequences
- LUKEWARM: Warm nurture sequences
- WARM: Engaged followup sequences
- HOT: Priority immediate queue

All outreach flows through GHL with different sequence types.

Engagement Signals Analyzed:
- Prior email opens/clicks/replies
- LinkedIn connections/messages
- Website visits (RB2B)
- Form submissions
- Meeting history
- CRM activity
"""

import os
import json
import logging
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lead-router")


class OutreachPlatform(Enum):
    """Target platform for outreach - all routes to GoHighLevel."""
    GOHIGHLEVEL_COLD = "gohighlevel_cold"  # Cold outbound sequences
    GOHIGHLEVEL_WARM = "gohighlevel_warm"  # Warm nurture sequences
    GOHIGHLEVEL_HOT = "gohighlevel_hot"    # Hot lead priority queue


class EngagementLevel(Enum):
    """Lead engagement classification."""
    COLD = "cold"                # No prior interaction
    LUKEWARM = "lukewarm"        # Some passive signals (website visit, profile view)
    WARM = "warm"                # Active engagement (opened email, clicked)
    HOT = "hot"                  # High intent (replied, booked meeting, inbound)


@dataclass
class EngagementSignals:
    """Aggregated engagement signals for a lead."""
    # Email signals
    emails_sent: int = 0
    emails_opened: int = 0
    emails_clicked: int = 0
    emails_replied: int = 0
    last_email_open: Optional[datetime] = None
    last_email_reply: Optional[datetime] = None
    
    # LinkedIn signals
    linkedin_connected: bool = False
    linkedin_messages_sent: int = 0
    linkedin_messages_received: int = 0
    linkedin_profile_viewed: bool = False
    last_linkedin_activity: Optional[datetime] = None
    
    # Website/Intent signals
    website_visits: int = 0
    pages_viewed: List[str] = field(default_factory=list)
    rb2b_identified: bool = False
    last_website_visit: Optional[datetime] = None
    
    # CRM signals
    in_crm: bool = False
    crm_stage: Optional[str] = None
    meetings_booked: int = 0
    meetings_completed: int = 0
    forms_submitted: int = 0
    last_crm_activity: Optional[datetime] = None
    
    # Inbound signals
    inbound_source: Optional[str] = None  # referral, organic, paid, etc.
    requested_contact: bool = False
    downloaded_content: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "emails_sent": self.emails_sent,
            "emails_opened": self.emails_opened,
            "emails_clicked": self.emails_clicked,
            "emails_replied": self.emails_replied,
            "last_email_open": self.last_email_open.isoformat() if self.last_email_open else None,
            "last_email_reply": self.last_email_reply.isoformat() if self.last_email_reply else None,
            "linkedin_connected": self.linkedin_connected,
            "linkedin_messages_sent": self.linkedin_messages_sent,
            "linkedin_messages_received": self.linkedin_messages_received,
            "linkedin_profile_viewed": self.linkedin_profile_viewed,
            "last_linkedin_activity": self.last_linkedin_activity.isoformat() if self.last_linkedin_activity else None,
            "website_visits": self.website_visits,
            "pages_viewed": self.pages_viewed,
            "rb2b_identified": self.rb2b_identified,
            "last_website_visit": self.last_website_visit.isoformat() if self.last_website_visit else None,
            "in_crm": self.in_crm,
            "crm_stage": self.crm_stage,
            "meetings_booked": self.meetings_booked,
            "meetings_completed": self.meetings_completed,
            "forms_submitted": self.forms_submitted,
            "last_crm_activity": self.last_crm_activity.isoformat() if self.last_crm_activity else None,
            "inbound_source": self.inbound_source,
            "requested_contact": self.requested_contact,
            "downloaded_content": self.downloaded_content,
        }


@dataclass
class RoutingDecision:
    """Routing decision with reasoning."""
    platform: OutreachPlatform
    engagement_level: EngagementLevel
    confidence: float  # 0-1
    reasoning: List[str]
    signals_summary: Dict[str, Any]
    recommended_sequence: Optional[str] = None
    priority: int = 5  # 1-10, higher = more urgent
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform.value,
            "engagement_level": self.engagement_level.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "signals_summary": self.signals_summary,
            "recommended_sequence": self.recommended_sequence,
            "priority": self.priority,
        }


class LeadRouter:
    """
    Context-aware lead routing engine.
    
    Routes all leads to GoHighLevel with different sequence types
    based on engagement signals and behavioral analysis.
    """
    
    # Scoring weights for engagement signals
    WEIGHTS = {
        "email_reply": 50,
        "email_click": 20,
        "email_open": 10,
        "linkedin_connected": 40,
        "linkedin_message_received": 45,
        "linkedin_message_sent": 5,
        "meeting_booked": 60,
        "meeting_completed": 80,
        "form_submitted": 55,
        "website_visit": 8,
        "rb2b_identified": 15,
        "requested_contact": 70,
        "downloaded_content": 25,
        "in_crm": 10,
    }
    
    # Thresholds for engagement levels
    THRESHOLDS = {
        "cold": 0,
        "lukewarm": 15,
        "warm": 40,
        "hot": 70,
    }
    
    # Time decay - signals older than this are weighted less
    RECENCY_WINDOW_DAYS = 30
    
    def __init__(self, supabase_client=None, ghl_client=None):
        self.supabase = supabase_client
        self.ghl = ghl_client
    
    def calculate_engagement_score(self, signals: EngagementSignals) -> float:
        """Calculate weighted engagement score from signals."""
        score = 0.0
        now = datetime.utcnow()
        
        # Email engagement
        if signals.emails_replied > 0:
            recency_factor = self._recency_factor(signals.last_email_reply, now)
            score += self.WEIGHTS["email_reply"] * min(signals.emails_replied, 3) * recency_factor
        
        if signals.emails_clicked > 0:
            recency_factor = self._recency_factor(signals.last_email_open, now)
            score += self.WEIGHTS["email_click"] * min(signals.emails_clicked, 5) * recency_factor
        
        if signals.emails_opened > 0:
            recency_factor = self._recency_factor(signals.last_email_open, now)
            score += self.WEIGHTS["email_open"] * min(signals.emails_opened, 5) * recency_factor
        
        # LinkedIn engagement
        if signals.linkedin_connected:
            score += self.WEIGHTS["linkedin_connected"]
        
        if signals.linkedin_messages_received > 0:
            recency_factor = self._recency_factor(signals.last_linkedin_activity, now)
            score += self.WEIGHTS["linkedin_message_received"] * recency_factor
        
        # Meeting signals (highest intent)
        if signals.meetings_completed > 0:
            score += self.WEIGHTS["meeting_completed"]
        elif signals.meetings_booked > 0:
            score += self.WEIGHTS["meeting_booked"]
        
        # Form/content signals
        if signals.forms_submitted > 0:
            score += self.WEIGHTS["form_submitted"]
        
        if signals.downloaded_content:
            score += self.WEIGHTS["downloaded_content"]
        
        if signals.requested_contact:
            score += self.WEIGHTS["requested_contact"]
        
        # Website/intent signals
        if signals.website_visits > 0:
            recency_factor = self._recency_factor(signals.last_website_visit, now)
            score += self.WEIGHTS["website_visit"] * min(signals.website_visits, 5) * recency_factor
        
        if signals.rb2b_identified:
            recency_factor = self._recency_factor(signals.last_website_visit, now)
            score += self.WEIGHTS["rb2b_identified"] * recency_factor
        
        # CRM presence
        if signals.in_crm:
            score += self.WEIGHTS["in_crm"]
        
        return score
    
    def _recency_factor(self, timestamp: Optional[datetime], now: datetime) -> float:
        """Calculate recency decay factor (1.0 = recent, 0.3 = old)."""
        if timestamp is None:
            return 0.5
        
        days_ago = (now - timestamp).days
        if days_ago <= 7:
            return 1.0
        elif days_ago <= 14:
            return 0.8
        elif days_ago <= 30:
            return 0.6
        elif days_ago <= 60:
            return 0.4
        else:
            return 0.3
    
    def classify_engagement(self, score: float) -> EngagementLevel:
        """Classify engagement level based on score."""
        if score >= self.THRESHOLDS["hot"]:
            return EngagementLevel.HOT
        elif score >= self.THRESHOLDS["warm"]:
            return EngagementLevel.WARM
        elif score >= self.THRESHOLDS["lukewarm"]:
            return EngagementLevel.LUKEWARM
        else:
            return EngagementLevel.COLD
    
    def route_lead(self, signals: EngagementSignals) -> RoutingDecision:
        """
        Determine optimal platform for lead outreach.
        
        Returns routing decision with platform, reasoning, and recommendations.
        """
        score = self.calculate_engagement_score(signals)
        engagement_level = self.classify_engagement(score)
        reasoning = []
        
        # Determine GHL sequence based on engagement level
        if engagement_level == EngagementLevel.HOT:
            platform = OutreachPlatform.GOHIGHLEVEL_HOT
            reasoning.append("High engagement detected - GHL hot_lead_immediate (priority queue)")
            
            if signals.meetings_booked > 0:
                reasoning.append(f"Has {signals.meetings_booked} meeting(s) booked")
            if signals.emails_replied > 0:
                reasoning.append(f"Replied to {signals.emails_replied} email(s)")
            if signals.requested_contact:
                reasoning.append("Requested contact - inbound lead")
            
            recommended_sequence = "hot_lead_immediate"
            priority = 9
            
        elif engagement_level == EngagementLevel.WARM:
            platform = OutreachPlatform.GOHIGHLEVEL_WARM
            reasoning.append("Warm engagement - GHL engaged_followup_sequence")
            
            if signals.linkedin_connected:
                reasoning.append("LinkedIn connection established")
            if signals.emails_clicked > 0:
                reasoning.append(f"Clicked {signals.emails_clicked} email link(s)")
            if signals.forms_submitted > 0:
                reasoning.append("Submitted form - known interest")
            
            recommended_sequence = "engaged_followup_sequence"
            priority = 7
            
        elif engagement_level == EngagementLevel.LUKEWARM:
            platform = OutreachPlatform.GOHIGHLEVEL_WARM
            reasoning.append("Passive signals detected - GHL warm_nurture_sequence")
            
            if signals.rb2b_identified:
                reasoning.append("RB2B identified visitor - has shown website interest")
            if signals.website_visits > 0:
                reasoning.append(f"Visited website {signals.website_visits} time(s)")
            if signals.linkedin_profile_viewed:
                reasoning.append("Viewed LinkedIn profile")
            
            recommended_sequence = "warm_nurture_sequence"
            priority = 5
            
        else:  # COLD
            platform = OutreachPlatform.GOHIGHLEVEL_COLD
            reasoning.append("No prior engagement - GHL cold_outbound_sequence")
            reasoning.append("Will escalate sequence upon engagement signal")
            
            recommended_sequence = "cold_outbound_sequence"
            priority = 3
        
        # Build signals summary
        signals_summary = {
            "engagement_score": round(score, 2),
            "has_email_engagement": signals.emails_opened > 0 or signals.emails_replied > 0,
            "has_linkedin_engagement": signals.linkedin_connected or signals.linkedin_messages_received > 0,
            "has_website_activity": signals.website_visits > 0,
            "has_direct_response": signals.emails_replied > 0 or signals.requested_contact,
            "in_crm": signals.in_crm,
            "days_since_last_activity": self._days_since_last_activity(signals),
        }
        
        # Calculate confidence based on signal density
        signal_count = sum([
            signals.emails_sent > 0,
            signals.emails_opened > 0,
            signals.linkedin_connected,
            signals.website_visits > 0,
            signals.in_crm,
        ])
        confidence = min(0.5 + (signal_count * 0.1), 0.95)
        
        return RoutingDecision(
            platform=platform,
            engagement_level=engagement_level,
            confidence=confidence,
            reasoning=reasoning,
            signals_summary=signals_summary,
            recommended_sequence=recommended_sequence,
            priority=priority,
        )
    
    def _days_since_last_activity(self, signals: EngagementSignals) -> Optional[int]:
        """Calculate days since most recent activity."""
        dates = [
            signals.last_email_open,
            signals.last_email_reply,
            signals.last_linkedin_activity,
            signals.last_website_visit,
            signals.last_crm_activity,
        ]
        valid_dates = [d for d in dates if d is not None]
        
        if not valid_dates:
            return None
        
        most_recent = max(valid_dates)
        return (datetime.utcnow() - most_recent).days
    
    async def fetch_signals_from_sources(self, email: str, linkedin_url: Optional[str] = None) -> EngagementSignals:
        """
        Aggregate engagement signals from all sources.
        
        Sources:
        - Supabase (leads table, outcomes table)
        - GoHighLevel (contact activity, campaign stats)
        """
        signals = EngagementSignals()
        
        # Fetch from Supabase
        if self.supabase:
            try:
                # Get lead record
                lead_result = self.supabase.table("leads").select("*").eq("email", email).execute()
                if lead_result.data:
                    lead = lead_result.data[0]
                    signals.in_crm = True
                    signals.crm_stage = lead.get("status")
                    
                    # Check enrichment data for signals
                    enrichment = lead.get("enrichment_data", {})
                    if enrichment.get("website_visits"):
                        signals.website_visits = enrichment["website_visits"]
                    if enrichment.get("rb2b_identified"):
                        signals.rb2b_identified = True
                
                # Get outcomes (email engagement)
                outcomes_result = self.supabase.table("outcomes").select("*").eq(
                    "lead_id", lead_result.data[0]["id"] if lead_result.data else ""
                ).execute()
                
                for outcome in outcomes_result.data:
                    if outcome.get("channel") == "email":
                        signals.emails_sent += 1
                        if outcome.get("open_rate", 0) > 0:
                            signals.emails_opened += 1
                        if outcome.get("click_rate", 0) > 0:
                            signals.emails_clicked += 1
                        if outcome.get("reply_rate", 0) > 0:
                            signals.emails_replied += 1
                            
            except Exception as e:
                logger.warning(f"Failed to fetch Supabase signals: {e}")
        
        # Fetch from GoHighLevel
        if self.ghl:
            try:
                # GHL contact lookup and activity would go here
                pass
            except Exception as e:
                logger.warning(f"Failed to fetch GHL signals: {e}")
        
        return signals
    
    def should_escalate_sequence(self, signals: EngagementSignals) -> bool:
        """
        Check if a lead should be escalated to a higher-priority GHL sequence.
        
        Escalation triggers:
        - Email reply received
        - Meeting booked
        - Form submitted
        - Requested contact
        - 3+ email opens in last 7 days
        """
        if signals.emails_replied > 0:
            return True
        if signals.meetings_booked > 0:
            return True
        if signals.forms_submitted > 0:
            return True
        if signals.requested_contact:
            return True
        
        # Check for high open engagement
        if signals.emails_opened >= 3 and signals.last_email_open:
            days_since_open = (datetime.utcnow() - signals.last_email_open).days
            if days_since_open <= 7:
                return True
        
        return False


def demo():
    """Demonstrate GHL-only routing logic with sample leads."""
    router = LeadRouter()
    
    print("=" * 70)
    print("Lead Router Demo - GHL-Only Outreach Routing")
    print("=" * 70)
    
    # Cold lead - no signals
    cold_signals = EngagementSignals()
    cold_decision = router.route_lead(cold_signals)
    print(f"\n[COLD LEAD] -> GHL cold_outbound_sequence")
    print(f"  Platform: {cold_decision.platform.value}")
    print(f"  Sequence: {cold_decision.recommended_sequence}")
    print(f"  Reasoning: {cold_decision.reasoning}")
    
    # Lukewarm lead - website visitor
    lukewarm_signals = EngagementSignals(
        website_visits=3,
        rb2b_identified=True,
        last_website_visit=datetime.utcnow() - timedelta(days=2),
    )
    lukewarm_decision = router.route_lead(lukewarm_signals)
    print(f"\n[LUKEWARM LEAD - RB2B Visitor] -> GHL warm_nurture_sequence")
    print(f"  Platform: {lukewarm_decision.platform.value}")
    print(f"  Sequence: {lukewarm_decision.recommended_sequence}")
    print(f"  Reasoning: {lukewarm_decision.reasoning}")
    
    # Warm lead - email engagement
    warm_signals = EngagementSignals(
        emails_sent=5,
        emails_opened=3,
        emails_clicked=1,
        linkedin_connected=True,
        last_email_open=datetime.utcnow() - timedelta(days=3),
        in_crm=True,
    )
    warm_decision = router.route_lead(warm_signals)
    print(f"\n[WARM LEAD - Email Engagement] -> GHL engaged_followup_sequence")
    print(f"  Platform: {warm_decision.platform.value}")
    print(f"  Sequence: {warm_decision.recommended_sequence}")
    print(f"  Reasoning: {warm_decision.reasoning}")
    
    # Hot lead - replied + meeting
    hot_signals = EngagementSignals(
        emails_sent=3,
        emails_opened=3,
        emails_replied=1,
        meetings_booked=1,
        last_email_reply=datetime.utcnow() - timedelta(days=1),
        in_crm=True,
        crm_stage="qualified",
    )
    hot_decision = router.route_lead(hot_signals)
    print(f"\n[HOT LEAD - Replied + Meeting] -> GHL hot_lead_immediate (priority)")
    print(f"  Platform: {hot_decision.platform.value}")
    print(f"  Sequence: {hot_decision.recommended_sequence}")
    print(f"  Priority: {hot_decision.priority}/10")
    print(f"  Reasoning: {hot_decision.reasoning}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    demo()
