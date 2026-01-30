#!/usr/bin/env python3
"""
Website Intent Monitor
======================
Monitors website visitors (RB2B) for high-intent blog page visits and
detects warm connections (colleagues from previous companies our team knows).

Key Features:
1. Blog page trigger rules - specific pages trigger specific outreach
2. Connection matching - find prior company overlap with sales team
3. Personalized email generation via CRAFTER using Gemini
4. Auto-queue to GATEKEEPER for approval

Trigger Logic:
    Visitor hits blog → Check ICP fit → Match connections → Generate email → Queue

Usage:
    from core.website_intent_monitor import get_website_monitor
    
    monitor = get_website_monitor()
    
    # Process RB2B webhook
    result = await monitor.process_visitor(visitor_data)
    
    # Manually check for warm connections
    connections = await monitor.find_warm_connections(visitor_linkedin_url)
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from enum import Enum

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env', override=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('website_intent')


class BlogCategory(Enum):
    """Categories of blog content for trigger matching."""
    AI_CASE_STUDY = "ai_case_study"
    ROI_METRICS = "roi_metrics"
    IMPLEMENTATION = "implementation"
    LEADERSHIP = "leadership"
    SALES_AI = "sales_ai"
    OPERATIONS = "operations"
    GENERAL = "general"


class ConnectionType(Enum):
    """Types of warm connections."""
    FORMER_COLLEAGUE = "former_colleague"
    SAME_PREVIOUS_COMPANY = "same_previous_company"
    MUTUAL_CONNECTION = "mutual_connection"
    SAME_SCHOOL = "same_school"
    SAME_INDUSTRY = "same_industry"


@dataclass
class BlogTrigger:
    """Configuration for a blog page trigger."""
    url_pattern: str
    category: BlogCategory
    intent_score_boost: int
    email_template_id: str
    subject_template: str
    opening_hook: str
    pain_points: List[str]


@dataclass
class WarmConnection:
    """A warm connection found between visitor and our team."""
    connection_type: ConnectionType
    shared_entity: str
    our_team_member: str
    team_member_title: str
    confidence: float
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VisitorIntent:
    """Processed visitor with intent signals."""
    visitor_id: str
    email: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    linkedin_url: Optional[str]
    company_name: Optional[str]
    company_domain: Optional[str]
    job_title: Optional[str]
    
    pages_viewed: List[str]
    blog_triggers_matched: List[BlogTrigger]
    warm_connections: List[WarmConnection]
    
    intent_score: int
    icp_tier: str
    recommended_action: str
    
    generated_email: Optional[Dict[str, str]] = None
    queued_for_approval: bool = False
    
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["blog_triggers_matched"] = [
            {"url_pattern": t.url_pattern, "category": t.category.value} 
            for t in self.blog_triggers_matched
        ]
        d["warm_connections"] = [asdict(c) for c in self.warm_connections]
        for c in d["warm_connections"]:
            c["connection_type"] = c["connection_type"].value if isinstance(c["connection_type"], ConnectionType) else c["connection_type"]
        return d


# Blog trigger configurations
BLOG_TRIGGERS: List[BlogTrigger] = [
    BlogTrigger(
        url_pattern=r"/blog.*(p&g|pg|procter.*gamble).*(product|development|ai|22)",
        category=BlogCategory.AI_CASE_STUDY,
        intent_score_boost=25,
        email_template_id="case_study_pg",
        subject_template="Quick thought on {company_name}'s development cycle",
        opening_hook="I saw you were reading our piece on how P&G cut product development time by 22% using AI.",
        pain_points=[
            "shorter cycles",
            "better decisions", 
            "less drag between teams",
            "without blowing up headcount or process"
        ]
    ),
    BlogTrigger(
        url_pattern=r"/blog.*roi|/blog.*cost.*reduction|/blog.*efficiency",
        category=BlogCategory.ROI_METRICS,
        intent_score_boost=20,
        email_template_id="roi_focused",
        subject_template="The efficiency numbers you were looking at",
        opening_hook="I noticed you were exploring our ROI content.",
        pain_points=[
            "operational cost reduction",
            "efficiency improvement",
            "measurable outcomes"
        ]
    ),
    BlogTrigger(
        url_pattern=r"/blog.*sales.*ai|/blog.*revenue.*intelligence|/blog.*crm.*ai",
        category=BlogCategory.SALES_AI,
        intent_score_boost=30,
        email_template_id="sales_ai",
        subject_template="AI for {company_name}'s sales org",
        opening_hook="I saw you checking out our sales AI frameworks.",
        pain_points=[
            "speed to execution",
            "cross-team alignment",
            "insight visibility"
        ]
    ),
    BlogTrigger(
        url_pattern=r"/blog.*implementation|/blog.*getting.*started|/blog.*deployment",
        category=BlogCategory.IMPLEMENTATION,
        intent_score_boost=35,
        email_template_id="implementation_ready",
        subject_template="Implementation path for {company_name}",
        opening_hook="You were looking at our implementation guides—that usually means timing is becoming real.",
        pain_points=[
            "deployment timeline",
            "change management",
            "quick wins vs long-term"
        ]
    ),
    BlogTrigger(
        url_pattern=r"/blog.*leadership|/blog.*executive|/blog.*cro|/blog.*vp.*sales",
        category=BlogCategory.LEADERSHIP,
        intent_score_boost=20,
        email_template_id="leadership",
        subject_template="For {first_name}'s consideration",
        opening_hook="I noticed you exploring our executive-level content.",
        pain_points=[
            "strategic visibility",
            "board-level metrics",
            "competitive positioning"
        ]
    ),
    # Catch-all for any blog visit with AI/automation content
    BlogTrigger(
        url_pattern=r"/blog.*(ai|automation|efficiency|transform|strategy)",
        category=BlogCategory.GENERAL,
        intent_score_boost=15,
        email_template_id="general_ai",
        subject_template="AI insights for {company_name}",
        opening_hook="I noticed you exploring our AI transformation content.",
        pain_points=[
            "operational efficiency",
            "competitive advantage",
            "measurable outcomes"
        ]
    ),
]

# Environment variable to enable fallback processing for visitors without trigger matches
FALLBACK_FOR_WARM_CONNECTIONS = os.getenv("INTENT_MONITOR_FALLBACK_WARM", "true").lower() == "true"

# Team network for connection matching (Dani's previous companies/connections)
TEAM_NETWORK: Dict[str, Dict[str, Any]] = {
    "dani_apgar": {
        "name": "Dani Apgar",
        "title": "Head of Partnerships & Revenue",
        "email": "dani@chiefaiofficer.com",
        "linkedin": "https://www.linkedin.com/in/daniapgar",
        "previous_companies": [
            {"name": "Gong", "domain": "gong.io", "years": "2020-2023"},
            {"name": "Outreach", "domain": "outreach.io", "years": "2018-2020"},
            {"name": "Salesforce", "domain": "salesforce.com", "years": "2015-2018"},
        ],
        "university": "UC Berkeley",
        "known_connections": [
            # Add LinkedIn URLs of known connections here
        ]
    },
    "chris_daigle": {
        "name": "Chris Daigle",
        "title": "Founder & CEO",
        "email": "chris@chiefaiofficer.com",
        "linkedin": "https://www.linkedin.com/in/doctordaigle",
        "previous_companies": [
            {"name": "Google", "domain": "google.com", "years": "2018-2022"},
            {"name": "McKinsey", "domain": "mckinsey.com", "years": "2015-2018"},
        ],
        "university": "Stanford",
        "known_connections": []
    }
}


class WebsiteIntentMonitor:
    """
    Monitors website visitors for high-intent blog visits and warm connections.
    """
    
    def __init__(self):
        self.storage_dir = PROJECT_ROOT / ".hive-mind" / "website_intent"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.blog_triggers = BLOG_TRIGGERS
        self.team_network = TEAM_NETWORK
        
        self._processed_visitors: Dict[str, VisitorIntent] = {}
        self._load_state()
        
        logger.info("Website Intent Monitor initialized")
    
    def _load_state(self):
        """Load processed visitors state."""
        state_file = self.storage_dir / "processed_visitors.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    data = json.load(f)
                    # Just load IDs for dedup, not full objects
                    self._processed_ids = set(data.get("processed_ids", []))
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
                self._processed_ids = set()
        else:
            self._processed_ids = set()
    
    def _save_state(self):
        """Save state to disk."""
        state_file = self.storage_dir / "processed_visitors.json"
        try:
            with open(state_file, "w") as f:
                json.dump({
                    "processed_ids": list(self._processed_ids)[-1000:],
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")
    
    def match_blog_triggers(self, pages_viewed: List[str]) -> List[BlogTrigger]:
        """Match viewed pages against blog triggers."""
        matched = []
        
        for page in pages_viewed:
            page_lower = page.lower()
            for trigger in self.blog_triggers:
                if re.search(trigger.url_pattern, page_lower, re.IGNORECASE):
                    if trigger not in matched:
                        matched.append(trigger)
        
        return matched
    
    def find_warm_connections(
        self,
        visitor_company: Optional[str] = None,
        visitor_domain: Optional[str] = None,
        visitor_linkedin: Optional[str] = None,
        visitor_work_history: Optional[List[Dict]] = None
    ) -> List[WarmConnection]:
        """
        Find warm connections between visitor and our team.
        
        Checks:
        1. Same current company as team's previous companies
        2. Shared previous company (both worked there)
        3. Known LinkedIn connections
        4. Same university
        """
        connections = []
        
        for member_id, member in self.team_network.items():
            # Check if visitor's current company is team member's previous company
            if visitor_domain:
                for prev_co in member.get("previous_companies", []):
                    if prev_co["domain"].lower() in visitor_domain.lower():
                        connections.append(WarmConnection(
                            connection_type=ConnectionType.SAME_PREVIOUS_COMPANY,
                            shared_entity=prev_co["name"],
                            our_team_member=member["name"],
                            team_member_title=member["title"],
                            confidence=0.9,
                            details={
                                "team_member_years": prev_co["years"],
                                "team_member_email": member["email"]
                            }
                        ))
            
            # Check visitor's work history against team's previous companies
            if visitor_work_history:
                for prev_job in visitor_work_history:
                    visitor_prev_domain = prev_job.get("company_domain", "")
                    visitor_prev_name = prev_job.get("company_name", "")
                    
                    for member_prev in member.get("previous_companies", []):
                        domain_match = (
                            visitor_prev_domain and 
                            member_prev["domain"].lower() in visitor_prev_domain.lower()
                        )
                        name_match = (
                            visitor_prev_name and 
                            member_prev["name"].lower() in visitor_prev_name.lower()
                        )
                        
                        if domain_match or name_match:
                            connections.append(WarmConnection(
                                connection_type=ConnectionType.FORMER_COLLEAGUE,
                                shared_entity=member_prev["name"],
                                our_team_member=member["name"],
                                team_member_title=member["title"],
                                confidence=0.85,
                                details={
                                    "visitor_years": prev_job.get("years", "unknown"),
                                    "team_member_years": member_prev["years"],
                                    "team_member_email": member["email"]
                                }
                            ))
            
            # Check known LinkedIn connections
            if visitor_linkedin:
                if visitor_linkedin in member.get("known_connections", []):
                    connections.append(WarmConnection(
                        connection_type=ConnectionType.MUTUAL_CONNECTION,
                        shared_entity="LinkedIn Network",
                        our_team_member=member["name"],
                        team_member_title=member["title"],
                        confidence=0.95,
                        details={"team_member_email": member["email"]}
                    ))
        
        return connections
    
    def calculate_intent_score(
        self,
        triggers: List[BlogTrigger],
        connections: List[WarmConnection],
        base_score: int = 30
    ) -> int:
        """Calculate overall intent score."""
        score = base_score
        
        # Add trigger boosts
        for trigger in triggers:
            score += trigger.intent_score_boost
        
        # Add connection boosts
        for conn in connections:
            if conn.connection_type == ConnectionType.FORMER_COLLEAGUE:
                score += 25
            elif conn.connection_type == ConnectionType.SAME_PREVIOUS_COMPANY:
                score += 20
            elif conn.connection_type == ConnectionType.MUTUAL_CONNECTION:
                score += 30
        
        return min(score, 100)
    
    def determine_icp_tier(self, intent_score: int, job_title: Optional[str]) -> str:
        """Determine ICP tier based on intent and title."""
        title_boost = 0
        if job_title:
            title_lower = job_title.lower()
            if any(t in title_lower for t in ["cro", "ceo", "coo", "chief"]):
                title_boost = 15
            elif any(t in title_lower for t in ["vp", "vice president", "director"]):
                title_boost = 10
            elif any(t in title_lower for t in ["head of", "senior"]):
                title_boost = 5
        
        adjusted_score = intent_score + title_boost
        
        if adjusted_score >= 75:
            return "tier_1"
        elif adjusted_score >= 50:
            return "tier_2"
        else:
            return "tier_3"
    
    async def generate_personalized_email(
        self,
        visitor: VisitorIntent
    ) -> Dict[str, str]:
        """
        Generate personalized email using CRAFTER via Gemini.
        
        Returns:
            Dict with 'subject', 'body', 'template_used'
        """
        try:
            from core.agent_llm_mixin import crafter_create
        except ImportError:
            logger.warning("LLM routing not available, using template fallback")
            return self._template_fallback_email(visitor)
        
        # Get primary trigger for template
        primary_trigger = visitor.blog_triggers_matched[0] if visitor.blog_triggers_matched else None
        
        # Build connection context
        connection_context = ""
        if visitor.warm_connections:
            best_conn = max(visitor.warm_connections, key=lambda c: c.confidence)
            if best_conn.connection_type == ConnectionType.FORMER_COLLEAGUE:
                connection_context = f"""
The visitor previously worked at {best_conn.shared_entity}, same as our {best_conn.our_team_member}.
Mention this shared background naturally - "I noticed we might have crossed paths at {best_conn.shared_entity}..."
"""
            elif best_conn.connection_type == ConnectionType.SAME_PREVIOUS_COMPANY:
                connection_context = f"""
The visitor currently works at a company where our {best_conn.our_team_member} previously worked ({best_conn.shared_entity}).
Mention this connection: "My colleague {best_conn.our_team_member} spent time at {best_conn.shared_entity}..."
"""
        
        prompt = f"""Generate a personalized cold email for this website visitor.

VISITOR INFO:
- Name: {visitor.first_name or 'Unknown'} {visitor.last_name or ''}
- Title: {visitor.job_title or 'Sales Leader'}
- Company: {visitor.company_name or 'their company'}
- Blog page viewed: {visitor.pages_viewed[0] if visitor.pages_viewed else 'our content'}

TRIGGER CONTEXT:
{primary_trigger.opening_hook if primary_trigger else "I saw you were reading our content."}

Pain points to address: {', '.join(primary_trigger.pain_points) if primary_trigger else "efficiency, speed, visibility"}

{connection_context}

EMAIL REQUIREMENTS:
1. Subject line: personalized, curiosity-driving, no spam triggers
2. Opening: Reference the specific content they viewed
3. Body: 
   - Connect their role to the pain points
   - Ask an engaging question about their friction points
   - Offer value (10-min AI framework walkthrough)
4. CTA: Soft close with "later today or tomorrow"
5. Signature: Dani Apgar, Head of Partnerships & Revenue, Chief AI Officer Inc.
   dani@chiefaiofficer.com | chiefaiofficer.com
   Book a 15-min intro: https://caio.cx/meet

TONE: Professional but conversational. No corporate jargon. Direct and helpful.

Return JSON format:
{{"subject": "...", "body": "..."}}
"""
        
        try:
            response = await crafter_create(prompt)
            
            # Parse JSON from response
            content = response.content
            json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if json_match:
                email_data = json.loads(json_match.group())
                email_data["template_used"] = primary_trigger.email_template_id if primary_trigger else "generic"
                email_data["generated_by"] = "gemini_crafter"
                return email_data
            else:
                logger.warning("Could not parse email JSON from LLM response")
                return self._template_fallback_email(visitor)
                
        except Exception as e:
            logger.error(f"LLM email generation failed: {e}")
            return self._template_fallback_email(visitor)
    
    def _template_fallback_email(self, visitor: VisitorIntent) -> Dict[str, str]:
        """Fallback template when LLM is unavailable."""
        trigger = visitor.blog_triggers_matched[0] if visitor.blog_triggers_matched else None
        
        first_name = visitor.first_name or "there"
        company = visitor.company_name or "your company"
        
        subject = trigger.subject_template.format(
            first_name=first_name,
            company_name=company
        ) if trigger else f"Quick thought for {first_name}"
        
        opening = trigger.opening_hook if trigger else "I saw you were reading our content."
        
        body = f"""Hi {first_name},

{opening}

When VPs of Sales look at that example, it's usually because they're under pressure to move faster—shorter cycles, better decisions, less drag between teams—without blowing up headcount or process.

Quick question: where are you seeing the most friction right now—speed to execution, cross-team alignment, or insight visibility?

If it's useful, I can show you how other sales orgs are applying similar AI frameworks in a tight 10 minutes.

Would later today or tomorrow work better?

Kind regards,

Dani Apgar
Head of Partnerships & Revenue, Chief AI Officer Inc.
dani@chiefaiofficer.com | chiefaiofficer.com
Book a 15-min intro: https://caio.cx/meet"""
        
        return {
            "subject": subject,
            "body": body,
            "template_used": trigger.email_template_id if trigger else "fallback",
            "generated_by": "template_fallback"
        }
    
    async def process_visitor(
        self,
        visitor_data: Dict[str, Any]
    ) -> Optional[VisitorIntent]:
        """
        Process an RB2B visitor webhook and determine action.
        
        Args:
            visitor_data: RB2B webhook payload with visitor info
        
        Returns:
            VisitorIntent if actionable, None if skipped
        """
        visitor_id = visitor_data.get("visitor_id") or visitor_data.get("id")
        if not visitor_id:
            visitor_id = hashlib.md5(
                json.dumps(visitor_data, sort_keys=True).encode()
            ).hexdigest()[:12]
        
        # Dedup check
        if visitor_id in self._processed_ids:
            logger.info(f"Visitor {visitor_id} already processed, skipping")
            return None
        
        # Extract visitor info
        pages_viewed = visitor_data.get("pages_viewed", [])
        if isinstance(pages_viewed, str):
            pages_viewed = [pages_viewed]
        
        # Match blog triggers
        triggers = self.match_blog_triggers(pages_viewed)
        
        # Extract work history if available (from Clay enrichment)
        work_history = visitor_data.get("work_history", [])
        
        # Find warm connections FIRST (before early return)
        connections = self.find_warm_connections(
            visitor_company=visitor_data.get("company_name"),
            visitor_domain=visitor_data.get("company_domain"),
            visitor_linkedin=visitor_data.get("linkedin_url"),
            visitor_work_history=work_history
        )
        
        # If no triggers matched, check if we should process anyway
        if not triggers:
            # Process warm connections even without triggers (if enabled)
            if FALLBACK_FOR_WARM_CONNECTIONS and connections:
                logger.info(f"No triggers but found {len(connections)} warm connections for {visitor_id}")
                # Create a synthetic trigger for warm connection processing
                triggers = [BlogTrigger(
                    url_pattern="warm_connection_fallback",
                    category=BlogCategory.GENERAL,
                    intent_score_boost=20,
                    email_template_id="warm_connection",
                    subject_template="Thought you might find this interesting, {first_name}",
                    opening_hook="I noticed you're exploring AI transformation for your organization.",
                    pain_points=["operational efficiency", "competitive advantage", "measurable outcomes"]
                )]
            else:
                logger.debug(f"No blog triggers matched for visitor {visitor_id}")
                # Still track but don't process
                self._processed_ids.add(visitor_id)
                self._save_state()
                return None
        
        # Calculate intent score (connections already found above)
        intent_score = self.calculate_intent_score(triggers, connections)
        
        # Determine ICP tier
        icp_tier = self.determine_icp_tier(
            intent_score, 
            visitor_data.get("job_title")
        )
        
        # Build visitor intent object
        visitor_intent = VisitorIntent(
            visitor_id=visitor_id,
            email=visitor_data.get("email"),
            first_name=visitor_data.get("first_name"),
            last_name=visitor_data.get("last_name"),
            linkedin_url=visitor_data.get("linkedin_url"),
            company_name=visitor_data.get("company_name"),
            company_domain=visitor_data.get("company_domain"),
            job_title=visitor_data.get("job_title"),
            pages_viewed=pages_viewed,
            blog_triggers_matched=triggers,
            warm_connections=connections,
            intent_score=intent_score,
            icp_tier=icp_tier,
            recommended_action=self._determine_action(intent_score, icp_tier, connections)
        )
        
        # Generate personalized email if high intent
        if intent_score >= 40 or connections:
            email = await self.generate_personalized_email(visitor_intent)
            visitor_intent.generated_email = email
            
            # Queue for GATEKEEPER approval
            if visitor_intent.email:
                await self._queue_for_approval(visitor_intent)
                visitor_intent.queued_for_approval = True
        
        # Save result
        self._processed_ids.add(visitor_id)
        self._save_visitor_intent(visitor_intent)
        self._save_state()
        
        logger.info(
            f"Processed visitor {visitor_id}: score={intent_score}, "
            f"tier={icp_tier}, triggers={len(triggers)}, connections={len(connections)}"
        )
        
        return visitor_intent
    
    def _determine_action(
        self,
        intent_score: int,
        icp_tier: str,
        connections: List[WarmConnection]
    ) -> str:
        """Determine recommended action."""
        if connections and intent_score >= 50:
            return "immediate_warm_outreach"
        elif icp_tier == "tier_1" and intent_score >= 60:
            return "priority_outreach"
        elif intent_score >= 40:
            return "standard_outreach"
        else:
            return "nurture_sequence"
    
    def _save_visitor_intent(self, visitor: VisitorIntent):
        """Save visitor intent to disk."""
        output_file = self.storage_dir / f"visitor_{visitor.visitor_id}.json"
        try:
            with open(output_file, "w") as f:
                json.dump(visitor.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save visitor intent: {e}")
    
    def _check_daily_limit(self) -> bool:
        """Check if daily email limit has been reached (25/day in Live Mode)."""
        metrics_dir = PROJECT_ROOT / ".hive-mind" / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        
        counter_file = metrics_dir / "daily_email_counts.json"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        counts = {"date": today, "queued": 0, "sent": 0}
        
        if counter_file.exists():
            try:
                with open(counter_file) as f:
                    data = json.load(f)
                    if data.get("date") == today:
                        counts = data
                    # Reset if new day
            except Exception:
                pass
        
        daily_limit = 25  # Live Mode limit
        return counts.get("queued", 0) < daily_limit
    
    def _increment_daily_count(self):
        """Increment daily email queue count."""
        metrics_dir = PROJECT_ROOT / ".hive-mind" / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        
        counter_file = metrics_dir / "daily_email_counts.json"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        counts = {"date": today, "queued": 0, "sent": 0}
        
        if counter_file.exists():
            try:
                with open(counter_file) as f:
                    data = json.load(f)
                    if data.get("date") == today:
                        counts = data
            except Exception:
                pass
        
        counts["queued"] = counts.get("queued", 0) + 1
        counts["last_queued_at"] = datetime.now(timezone.utc).isoformat()
        
        with open(counter_file, "w") as f:
            json.dump(counts, f, indent=2)
    
    async def _queue_for_approval(self, visitor: VisitorIntent):
        """
        Queue email for GATEKEEPER approval.
        
        Writes to BOTH:
        1. shadow_mode_emails (dashboard-compatible format for approval UI)
        2. gatekeeper_queue (original format for audit/backup)
        """
        if not visitor.generated_email or not visitor.email:
            return
        
        # Check daily limit (25/day in Live Mode)
        if not self._check_daily_limit():
            logger.warning(f"Daily email limit reached, skipping queue for {visitor.email}")
            return
        
        email_id = f"blog_intent_{visitor.visitor_id}"
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Context for both formats
        context = {
            "intent_score": visitor.intent_score,
            "icp_tier": visitor.icp_tier,
            "triggers": [t.category.value for t in visitor.blog_triggers_matched],
            "warm_connections": [
                {
                    "type": c.connection_type.value,
                    "shared": c.shared_entity,
                    "team_member": c.our_team_member
                }
                for c in visitor.warm_connections
            ],
            "pages_viewed": visitor.pages_viewed
        }
        
        # =================================================================
        # 1. DASHBOARD-COMPATIBLE FORMAT (shadow_mode_emails)
        # This is what the sales dashboard reads for pending approvals
        # =================================================================
        shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
        shadow_dir.mkdir(parents=True, exist_ok=True)
        
        recipient_name = f"{visitor.first_name or ''} {visitor.last_name or ''}".strip()
        
        dashboard_email = {
            "email_id": email_id,
            "status": "pending",
            "to": visitor.email,
            "subject": visitor.generated_email.get("subject", ""),
            "body": visitor.generated_email.get("body", ""),
            "source": "website_intent_monitor",
            "timestamp": timestamp,
            "created_at": timestamp,
            "recipient_data": {
                "name": recipient_name,
                "company": visitor.company_name,
                "title": visitor.job_title,
                "linkedin_url": visitor.linkedin_url
            },
            "context": context,
            "priority": "high" if visitor.warm_connections else "medium",
            "synthetic": False,
            "contact_id": None  # Will be set if GHL contact exists
        }
        
        shadow_file = shadow_dir / f"{email_id}.json"
        with open(shadow_file, "w") as f:
            json.dump(dashboard_email, f, indent=2)
        
        logger.info(f"✅ Queued pending email to dashboard: {email_id}")
        
        # =================================================================
        # 2. ORIGINAL FORMAT (gatekeeper_queue) - for backup/audit
        # =================================================================
        approval_queue_dir = PROJECT_ROOT / ".hive-mind" / "gatekeeper_queue"
        approval_queue_dir.mkdir(parents=True, exist_ok=True)
        
        queue_item = {
            "queue_id": email_id,
            "type": "blog_triggered_email",
            "priority": "high" if visitor.warm_connections else "medium",
            "visitor": {
                "id": visitor.visitor_id,
                "email": visitor.email,
                "name": recipient_name,
                "company": visitor.company_name,
                "title": visitor.job_title
            },
            "email": visitor.generated_email,
            "context": context,
            "created_at": timestamp
        }
        
        queue_file = approval_queue_dir / f"{email_id}.json"
        with open(queue_file, "w") as f:
            json.dump(queue_item, f, indent=2)
        
        # Increment daily counter
        self._increment_daily_count()
        
        # Log to event stream for monitoring
        self._log_queue_event(email_id, visitor)
        
        logger.info(f"Queued email for GATEKEEPER approval: {email_id}")
    
    def _log_queue_event(self, email_id: str, visitor: VisitorIntent):
        """Log queue event for monitoring."""
        logs_dir = PROJECT_ROOT / ".hive-mind" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = logs_dir / "intent_queue.jsonl"
        
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "email_queued",
            "email_id": email_id,
            "visitor_email": visitor.email,
            "company": visitor.company_name,
            "intent_score": visitor.intent_score,
            "triggers": len(visitor.blog_triggers_matched),
            "warm_connections": len(visitor.warm_connections)
        }
        
        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.warning(f"Failed to log queue event: {e}")
    
    def add_team_member_connection(
        self,
        member_id: str,
        company_name: str,
        company_domain: str,
        years: str
    ):
        """Add a previous company to a team member's network."""
        if member_id not in self.team_network:
            logger.warning(f"Team member {member_id} not found")
            return
        
        self.team_network[member_id]["previous_companies"].append({
            "name": company_name,
            "domain": company_domain,
            "years": years
        })
        
        logger.info(f"Added {company_name} to {member_id}'s network")
    
    def add_known_linkedin_connection(self, member_id: str, linkedin_url: str):
        """Add a known LinkedIn connection for a team member."""
        if member_id not in self.team_network:
            logger.warning(f"Team member {member_id} not found")
            return
        
        if linkedin_url not in self.team_network[member_id]["known_connections"]:
            self.team_network[member_id]["known_connections"].append(linkedin_url)
            logger.info(f"Added LinkedIn connection for {member_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get monitor statistics."""
        return {
            "processed_visitors": len(self._processed_ids),
            "blog_triggers_configured": len(self.blog_triggers),
            "team_members_tracked": len(self.team_network),
            "storage_dir": str(self.storage_dir)
        }


# Singleton instance
_monitor: Optional[WebsiteIntentMonitor] = None


def get_website_monitor() -> WebsiteIntentMonitor:
    """Get or create the global website intent monitor."""
    global _monitor
    if _monitor is None:
        _monitor = WebsiteIntentMonitor()
    return _monitor


async def demo():
    """Demonstrate website intent monitoring."""
    print("\n" + "=" * 60)
    print("WEBSITE INTENT MONITOR - Demo")
    print("=" * 60)
    
    monitor = get_website_monitor()
    
    # Simulate a visitor who read the P&G case study
    # and previously worked at Gong (where Dani worked)
    test_visitor = {
        "visitor_id": "demo_visitor_001",
        "email": "todd@acmecorp.com",
        "first_name": "Todd",
        "last_name": "Smith",
        "linkedin_url": "https://linkedin.com/in/toddsmith",
        "company_name": "Acme Corp",
        "company_domain": "acmecorp.com",
        "job_title": "VP of Sales",
        "pages_viewed": [
            "/blog/how-pg-cut-product-development-time-22-percent-using-ai"
        ],
        "work_history": [
            {"company_name": "Gong", "company_domain": "gong.io", "years": "2019-2022"},
            {"company_name": "Oracle", "company_domain": "oracle.com", "years": "2015-2019"}
        ]
    }
    
    print("\n[Processing test visitor...]")
    print(f"  Name: {test_visitor['first_name']} {test_visitor['last_name']}")
    print(f"  Company: {test_visitor['company_name']}")
    print(f"  Title: {test_visitor['job_title']}")
    print(f"  Page viewed: {test_visitor['pages_viewed'][0]}")
    print(f"  Work history: Gong (2019-2022), Oracle (2015-2019)")
    
    result = await monitor.process_visitor(test_visitor)
    
    if result:
        print("\n[Results]")
        print(f"  Intent Score: {result.intent_score}/100")
        print(f"  ICP Tier: {result.icp_tier}")
        print(f"  Recommended Action: {result.recommended_action}")
        print(f"  Triggers Matched: {[t.category.value for t in result.blog_triggers_matched]}")
        
        if result.warm_connections:
            print("\n  [Warm Connections Found!]")
            for conn in result.warm_connections:
                print(f"    - {conn.connection_type.value}: {conn.shared_entity}")
                print(f"      Team member: {conn.our_team_member} ({conn.team_member_title})")
        
        if result.generated_email:
            print("\n  [Generated Email]")
            print(f"    Subject: {result.generated_email.get('subject', 'N/A')}")
            print(f"    Template: {result.generated_email.get('template_used', 'N/A')}")
            print(f"    Generated by: {result.generated_email.get('generated_by', 'N/A')}")
        
        if result.queued_for_approval:
            print("\n  ✅ Email queued for GATEKEEPER approval")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
