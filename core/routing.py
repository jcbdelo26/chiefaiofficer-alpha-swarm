"""
Escalation Routing System for SDR Automation
=============================================
Evaluates leads and replies to determine when human escalation is needed.

Based on sdr_rules.yaml escalation triggers:
- Immediate (5 min): Enterprise, C-level, existing customer, competitor, negative, pricing, security
- Standard (1 hour): Buying signals, meeting request, technical, integration, demo
- Deferred (daily): ICP 95+, multiple touchpoints, engagement change, persona mismatch
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from core.config import get_escalation_triggers


class HandoffDestination(Enum):
    """Where to route the handoff."""
    AE = "ae"
    ENTERPRISE_AE = "enterprise_ae"
    SENIOR_AE = "senior_ae"
    AE_CALENDAR = "ae_calendar"
    AE_AND_SE = "ae_and_se"
    AE_REVIEW = "ae_review"
    SE = "se"
    CSM = "csm"
    SKIP = "skip"
    VIP_CAMPAIGN = "vip_campaign"
    NURTURE_UPGRADE = "nurture_upgrade"
    OUTREACH_ADJUSTMENT = "outreach_adjustment"
    RE_QUALIFICATION = "re_qualification"


class HandoffPriority(Enum):
    """Urgency of the handoff."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BLOCK = "block"


@dataclass
class HandoffTicket:
    """Ticket representing a lead handoff to human team member."""
    handoff_id: str
    lead_id: str
    campaign_id: str
    trigger: str
    destination: str
    priority: str
    sla_due_at: str
    created_at: str
    status: str = "pending"
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None
    closed_at: Optional[str] = None
    closed_by: Optional[str] = None
    notes: Optional[str] = None
    lead_name: Optional[str] = None
    lead_email: Optional[str] = None
    lead_company: Optional[str] = None
    lead_title: Optional[str] = None
    reply_snippet: Optional[str] = None


C_LEVEL_PATTERNS = [
    r'\b(CEO|CFO|CTO|COO|CMO|CIO|CISO|CRO|CPO)\b',
    r'\bChief\s+\w+\s+Officer\b',
    r'\bFounder\b',
    r'\bCo-Founder\b',
    r'\bPresident\b',
    r'\bOwner\b',
]

PRICING_KEYWORDS = [
    'price', 'pricing', 'cost', 'budget', 'quote', 'discount',
    'how much', 'what does it cost', 'roi', 'investment'
]

SECURITY_KEYWORDS = [
    'security', 'soc2', 'soc 2', 'gdpr', 'hipaa', 'compliance',
    'encryption', 'encrypted', 'audit', 'penetration test', 'vulnerability',
    'data protection', 'privacy', 'iso 27001'
]

BUYING_SIGNAL_KEYWORDS = [
    'interested', 'tell me more', 'sounds good', 'like to learn',
    'looking for', 'need a solution', 'evaluating', 'comparing',
    'timeline', 'decision maker', 'stakeholders', 'next steps'
]

MEETING_REQUEST_KEYWORDS = [
    'meet', 'call', 'schedule', 'calendar', 'availability',
    'time to chat', 'hop on a call', '15 minutes', '30 minutes'
]

TECHNICAL_KEYWORDS = [
    'api', 'integration', 'webhook', 'sdk', 'documentation',
    'architecture', 'infrastructure', 'deployment', 'scalability',
    'performance', 'latency', 'throughput', 'uptime', 'sla'
]

INTEGRATION_KEYWORDS = [
    'integrate', 'integration', 'connect', 'salesforce', 'hubspot',
    'zapier', 'webhook', 'crm', 'erp', 'sync', 'import', 'export'
]

DEMO_KEYWORDS = [
    'demo', 'demonstration', 'show me', 'walkthrough', 'trial',
    'see it in action', 'how does it work'
]

NEGATIVE_PATTERNS = [
    r'\b(not interested|no thanks|stop|unsubscribe|remove me)\b',
    r'\b(never contact|do not contact|leave me alone)\b',
    r'\b(this is spam|reported as spam)\b',
    r'\b(terrible|awful|worst)\b'
]


def _matches_c_level(title: str) -> bool:
    """Check if title indicates C-level executive."""
    if not title:
        return False
    title_upper = title.upper()
    for pattern in C_LEVEL_PATTERNS:
        if re.search(pattern, title_upper, re.IGNORECASE):
            return True
    return False


def _contains_keywords(text: str, keywords: List[str]) -> bool:
    """Check if text contains any of the keywords."""
    if not text:
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _matches_negative_patterns(text: str) -> bool:
    """Check if text matches negative sentiment patterns."""
    if not text:
        return False
    text_lower = text.lower()
    for pattern in NEGATIVE_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False


def _calculate_sla_due(priority: str, created_at: datetime) -> datetime:
    """Calculate SLA due time based on priority."""
    if priority == HandoffPriority.CRITICAL.value:
        return created_at + timedelta(minutes=5)
    elif priority == HandoffPriority.HIGH.value:
        return created_at + timedelta(minutes=15)
    elif priority == HandoffPriority.MEDIUM.value:
        return created_at + timedelta(hours=1)
    elif priority == HandoffPriority.LOW.value:
        return created_at + timedelta(hours=24)
    elif priority == HandoffPriority.BLOCK.value:
        return created_at + timedelta(minutes=5)
    else:
        return created_at + timedelta(hours=4)


def evaluate_escalation_triggers(
    lead: Dict[str, Any],
    reply: Optional[Dict[str, Any]] = None,
    decision: Optional[Dict[str, Any]] = None,
    rules: Optional[Dict[str, Any]] = None
) -> List[HandoffTicket]:
    """
    Evaluate a lead/reply against escalation triggers.
    
    Args:
        lead: Lead data with fields like employee_count, title, company, is_customer
        reply: Optional reply data with body, sentiment, classification
        decision: Optional decision data from responder
        rules: Optional custom rules (defaults to sdr_rules.yaml)
    
    Returns:
        List of HandoffTicket objects for triggered escalations
    """
    if rules is None:
        rules = get_escalation_triggers()
    
    tickets = []
    created_at = datetime.now(timezone.utc)
    lead_id = lead.get("lead_id", lead.get("id", str(uuid.uuid4())))
    campaign_id = lead.get("campaign_id", "")
    reply_text = reply.get("body", "") if reply else ""
    
    def create_ticket(trigger: str, destination: str, priority: str) -> HandoffTicket:
        sla_due = _calculate_sla_due(priority, created_at)
        return HandoffTicket(
            handoff_id=str(uuid.uuid4()),
            lead_id=lead_id,
            campaign_id=campaign_id,
            trigger=trigger,
            destination=destination,
            priority=priority,
            sla_due_at=sla_due.isoformat(),
            created_at=created_at.isoformat(),
            status="pending",
            lead_name=lead.get("name", lead.get("full_name")),
            lead_email=lead.get("email"),
            lead_company=lead.get("company", lead.get("company_name")),
            lead_title=lead.get("title", lead.get("job_title")),
            reply_snippet=reply_text[:200] if reply_text else None
        )
    
    # === IMMEDIATE TRIGGERS (5 min) ===
    
    # Enterprise account >1000 employees
    employee_count = lead.get("employee_count", lead.get("employees", 0))
    if isinstance(employee_count, str):
        employee_count = int(employee_count.replace(",", "").replace("+", "")) if employee_count.isdigit() else 0
    if employee_count > 1000:
        tickets.append(create_ticket(
            "enterprise_account",
            HandoffDestination.ENTERPRISE_AE.value,
            HandoffPriority.CRITICAL.value
        ))
    
    # C-level engagement
    title = lead.get("title", lead.get("job_title", ""))
    if _matches_c_level(title):
        tickets.append(create_ticket(
            "c_level_engagement",
            HandoffDestination.SENIOR_AE.value,
            HandoffPriority.CRITICAL.value
        ))
    
    # Existing customer
    if lead.get("is_existing_customer") or lead.get("is_customer"):
        tickets.append(create_ticket(
            "existing_customer",
            HandoffDestination.CSM.value,
            HandoffPriority.CRITICAL.value
        ))
    
    # Competitor employee
    if lead.get("is_competitor"):
        tickets.append(create_ticket(
            "competitor_employee",
            HandoffDestination.SKIP.value,
            HandoffPriority.BLOCK.value
        ))
    
    # Reply-based immediate triggers
    if reply:
        sentiment = reply.get("sentiment", decision.get("sentiment", "") if decision else "")
        
        # Negative reply
        if sentiment == "negative" or _matches_negative_patterns(reply_text):
            tickets.append(create_ticket(
                "negative_reply",
                HandoffDestination.AE_REVIEW.value,
                HandoffPriority.HIGH.value
            ))
        
        # Pricing mentioned
        if _contains_keywords(reply_text, PRICING_KEYWORDS):
            tickets.append(create_ticket(
                "pricing_mentioned",
                HandoffDestination.AE.value,
                HandoffPriority.HIGH.value
            ))
        
        # Security question
        if _contains_keywords(reply_text, SECURITY_KEYWORDS):
            tickets.append(create_ticket(
                "security_question",
                HandoffDestination.SE.value,
                HandoffPriority.HIGH.value
            ))
    
    # === STANDARD TRIGGERS (1 hour) ===
    
    if reply:
        # Buying signals
        if _contains_keywords(reply_text, BUYING_SIGNAL_KEYWORDS):
            tickets.append(create_ticket(
                "buying_signals",
                HandoffDestination.AE.value,
                HandoffPriority.MEDIUM.value
            ))
        
        # Meeting request
        if _contains_keywords(reply_text, MEETING_REQUEST_KEYWORDS):
            tickets.append(create_ticket(
                "meeting_request_manual",
                HandoffDestination.AE_CALENDAR.value,
                HandoffPriority.MEDIUM.value
            ))
        
        # Technical deep-dive
        if _contains_keywords(reply_text, TECHNICAL_KEYWORDS):
            tickets.append(create_ticket(
                "technical_deepdive",
                HandoffDestination.SE.value,
                HandoffPriority.MEDIUM.value
            ))
        
        # Integration requirements
        if _contains_keywords(reply_text, INTEGRATION_KEYWORDS):
            tickets.append(create_ticket(
                "integration_requirements",
                HandoffDestination.SE.value,
                HandoffPriority.MEDIUM.value
            ))
        
        # Demo request
        if _contains_keywords(reply_text, DEMO_KEYWORDS):
            tickets.append(create_ticket(
                "demo_request",
                HandoffDestination.AE_AND_SE.value,
                HandoffPriority.MEDIUM.value
            ))
    
    # === DEFERRED TRIGGERS (daily) ===
    
    # ICP score >= 95
    icp_score = lead.get("icp_score", lead.get("score", 0))
    if icp_score >= 95:
        tickets.append(create_ticket(
            "icp_score_95_plus",
            HandoffDestination.VIP_CAMPAIGN.value,
            HandoffPriority.LOW.value
        ))
    
    # Multiple touchpoints
    touchpoints = lead.get("touchpoint_count", lead.get("touchpoints", 0))
    if touchpoints >= 5:
        tickets.append(create_ticket(
            "multiple_touchpoints",
            HandoffDestination.NURTURE_UPGRADE.value,
            HandoffPriority.LOW.value
        ))
    
    # Engagement pattern change
    if lead.get("engagement_changed") or lead.get("engagement_spike"):
        tickets.append(create_ticket(
            "engagement_pattern_change",
            HandoffDestination.OUTREACH_ADJUSTMENT.value,
            HandoffPriority.LOW.value
        ))
    
    # Persona mismatch
    if lead.get("persona_mismatch") or lead.get("segment_mismatch"):
        tickets.append(create_ticket(
            "persona_mismatch",
            HandoffDestination.RE_QUALIFICATION.value,
            HandoffPriority.LOW.value
        ))
    
    return tickets
