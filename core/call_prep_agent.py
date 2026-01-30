#!/usr/bin/env python3
"""
Call Prep Agent (PREPPER)
=========================
Enriches GHL contact custom fields with call-ready context before Dani's calls.
Sends ICP research brief to dani@chiefaiofficer.com the night before scheduled calls.

TRIGGER CONDITIONS (Guardrails):
=================================
The PREPPER agent activates when ANY of these conditions are met:

1. CALENDAR TRIGGER (Highest Priority)
   - A meeting is scheduled in GHL/Google Calendar with a contact
   - Prep runs at 8 PM the night before the call
   - Email sent to Dani with full research brief

2. APPROVAL TRIGGER (High Priority)
   - When Dani approves an email in the queue (status changes to "approved")
   - Indicates she's about to engage - prep the context

3. HOT LEAD TRIGGER (Medium Priority)
   - When a lead is classified as HOT (intent_score >= 75)
   - AND has warm connections to our team
   - Prep runs immediately upon detection

4. MANUAL TRIGGER (On-Demand)
   - API call or CLI command
   - Used when Dani knows she has a call coming up

Custom Fields Populated:
- call_prep_summary: One-paragraph briefing
- pain_points: Detected pain points from signals
- warm_connections: Any connections to our team
- recent_activity: Last 7 days of engagement
- recommended_approach: Suggested conversation angle
- company_context: Company news, funding, growth signals
- objection_prep: Likely objections and responses

Usage:
    from core.call_prep_agent import CallPrepAgent
    
    prepper = CallPrepAgent()
    await prepper.prepare_contact_for_call(contact_id="abc123")
    
    # Check for upcoming calls and prep
    await prepper.prep_upcoming_calls()
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
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
logger = logging.getLogger('call_prep_agent')


# =============================================================================
# SDR RESEARCH PROMPT (World-Class SDR Assistant)
# =============================================================================

SDR_RESEARCH_PROMPT = """You are a world-class SDR research assistant. Your job is to analyze leads and produce clear, tactical, and trustworthy sales briefs.

ADAPTIVE INSTRUCTIONS:

Process leads with available data and gracefully handle missing fields. If a required field is blank or missing, note it as "Not provided" and continue the analysis using available information. Never stop the analysis due to missing data.

LEAD PROFILE (All fields optional - use what's available):

- Name: {name} (if available)
- Title: {title} (if available; note role authority from this)
- Company: {company} (if available; if blank, reference the URL domain from website if available)
- Website: {website} (if available)
- Industry: {industry} (if available; if blank, infer from website/company context)
- Employee Count: {employee_count} (if available)
- LinkedIn: {linkedin} (if available)

ADDITIONAL CONTEXT:
- Pages Viewed on Our Website: {pages_viewed}
- Warm Connections to Our Team: {warm_connections}
- Intent Signals Detected: {intent_signals}

RESEARCH INSTRUCTIONS:

1. LEAD SNAPSHOT: Create a 30-word professional summary. If data is missing, use available firmographics (role, company clues, website content). Example: "Director at an operations firm, likely 50-100 employees, focused on supply chain optimization based on website presence."

2. COMPANY CONTEXT: Share business focus and growth signals. If Industry or Company details are blank, infer from: website content, domain type (.com vs vertical-specific), LinkedIn profile hints, or role context.

3. SALES ANGLES: Provide 3 specific talking points for outreach. Adapt based on available data:
   - If you have Role + Industry: "Your background in [Industry] suggests expertise in [operational area]..."
   - If Industry is missing: "Based on your role as [Title], you likely deal with..."
   - Always include practical next steps relevant to available information

4. RISKS & GAPS: Note any missing data that would strengthen qualification. Example: "No company size identified; would benefit from LinkedIn company search" or "Funding stage not available but role suggests growth-stage opportunity."

5. NEXT STEPS: Recommended outreach approach tailored to data confidence level. If missing key info, suggest discovery-focused first message.

IMPORTANT ADAPTIVE LOGIC:
- If Company and Industry are blank: Leverage role title and website to infer business type and value proposition fit
- If LinkedIn is blank: Focus on other signals and information sources
- If Employee Count is blank: Use role title level to estimate company scale (Founder/CEO = typically smaller; VP/Director = likely larger)
- Always maintain professional quality - missing data is normal, not a reason to deprioritize analysis

OUTPUT FORMAT:

# Lead Snapshot
[30-word summary using available data]

# Company Context
[Key business focus - can be inferred from role or website hints if direct data missing]

# Sales Angles
1. [Angle 1 - tailored to available data]
2. [Angle 2 - tailored to available data]
3. [Angle 3 - tailored to available data]

# Risks & Gaps
- [Gap 1: What's missing and why it matters]
- [Gap 2: What's missing and why it matters]

# Next Steps
[Recommended approach]

IMPORTANT: Keep total response under 150 words. Focus on unique, timely insights.

If Name, Title, Company, Industry, or Employee Count is blank, continue creating an SDR Insight with the available information.
"""

# Dani's email for receiving prep briefs
DANI_EMAIL = "dani@chiefaiofficer.com"

# Trigger thresholds
HOT_LEAD_INTENT_THRESHOLD = 75
PREP_HOUR = 20  # 8 PM - when to send night-before briefs


# =============================================================================
# TRIGGER CONDITIONS (Guardrails)
# =============================================================================

class PrepTrigger(Enum):
    """Reasons why prep was triggered."""
    CALENDAR = "calendar"           # Meeting scheduled for tomorrow
    APPROVAL = "approval"           # Dani approved email in queue
    HOT_LEAD = "hot_lead"           # High intent + warm connections
    MANUAL = "manual"               # API/CLI trigger
    BATCH = "batch"                 # Part of batch processing


@dataclass
class TriggerCondition:
    """Defines when PREPPER should activate."""
    trigger_type: PrepTrigger
    contact_id: str
    reason: str
    priority: int  # 1 = highest
    meeting_time: Optional[str] = None
    
    def should_send_email(self) -> bool:
        """Determine if this trigger warrants an email to Dani."""
        # Calendar triggers always send email (night before call)
        if self.trigger_type == PrepTrigger.CALENDAR:
            return True
        # Hot leads with warm connections send email
        if self.trigger_type == PrepTrigger.HOT_LEAD:
            return True
        # Approvals send email (she's about to engage)
        if self.trigger_type == PrepTrigger.APPROVAL:
            return True
        return False


# =============================================================================
# CUSTOM FIELD DEFINITIONS
# =============================================================================

class CallPrepField(Enum):
    """GHL custom fields for call preparation."""
    CALL_PREP_SUMMARY = "call_prep_summary"
    PAIN_POINTS = "pain_points"
    WARM_CONNECTIONS = "warm_connections"
    RECENT_ACTIVITY = "recent_activity"
    RECOMMENDED_APPROACH = "recommended_approach"
    COMPANY_CONTEXT = "company_context"
    OBJECTION_PREP = "objection_prep"
    LAST_PREP_DATE = "last_prep_date"
    PREP_CONFIDENCE = "prep_confidence"


@dataclass
class CallPrepResult:
    """Result of call preparation enrichment."""
    contact_id: str
    contact_name: str
    company_name: str
    
    # Enriched fields
    summary: str = ""
    pain_points: List[str] = field(default_factory=list)
    warm_connections: List[Dict[str, str]] = field(default_factory=list)
    recent_activity: List[Dict[str, Any]] = field(default_factory=list)
    recommended_approach: str = ""
    company_context: str = ""
    objection_prep: List[Dict[str, str]] = field(default_factory=list)
    
    # Metadata
    confidence_score: float = 0.0
    prep_timestamp: str = ""
    sources_used: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.prep_timestamp:
            self.prep_timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_ghl_custom_fields(self) -> List[Dict[str, str]]:
        """Convert to GHL custom fields format."""
        return [
            {"key": CallPrepField.CALL_PREP_SUMMARY.value, "value": self.summary[:500]},
            {"key": CallPrepField.PAIN_POINTS.value, "value": " | ".join(self.pain_points[:5])},
            {"key": CallPrepField.WARM_CONNECTIONS.value, "value": self._format_connections()},
            {"key": CallPrepField.RECENT_ACTIVITY.value, "value": self._format_activity()},
            {"key": CallPrepField.RECOMMENDED_APPROACH.value, "value": self.recommended_approach[:300]},
            {"key": CallPrepField.COMPANY_CONTEXT.value, "value": self.company_context[:500]},
            {"key": CallPrepField.OBJECTION_PREP.value, "value": self._format_objections()},
            {"key": CallPrepField.LAST_PREP_DATE.value, "value": self.prep_timestamp},
            {"key": CallPrepField.PREP_CONFIDENCE.value, "value": f"{self.confidence_score:.0%}"},
        ]
    
    def _format_connections(self) -> str:
        if not self.warm_connections:
            return "No warm connections found"
        parts = []
        for conn in self.warm_connections[:3]:
            parts.append(f"{conn.get('team_member', 'Team')}: {conn.get('shared', 'Unknown')}")
        return " | ".join(parts)
    
    def _format_activity(self) -> str:
        if not self.recent_activity:
            return "No recent activity"
        parts = []
        for act in self.recent_activity[:5]:
            parts.append(f"{act.get('type', 'Activity')}: {act.get('date', '')}")
        return " | ".join(parts)
    
    def _format_objections(self) -> str:
        if not self.objection_prep:
            return "No objections predicted"
        parts = []
        for obj in self.objection_prep[:3]:
            parts.append(f"If '{obj.get('objection', '')}' → {obj.get('response', '')[:50]}")
        return " | ".join(parts)


# =============================================================================
# CALL PREP AGENT
# =============================================================================

class CallPrepAgent:
    """
    Agent that enriches GHL contacts with call-ready context.
    
    Integrates with:
    - GHL API for contact data and updates
    - Website Intent Monitor for page views and signals
    - Clay enrichment for company context
    - LLM for summary generation
    """
    
    def __init__(self):
        self.ghl_api_key = os.getenv("GHL_PROD_API_KEY", "")
        self.ghl_location_id = os.getenv("GHL_LOCATION_ID", "")
        self.storage_dir = PROJECT_ROOT / ".hive-mind" / "call_prep"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Import dependencies lazily
        self._llm_router = None
        self._website_monitor = None
        
        logger.info("CallPrepAgent initialized")
    
    @property
    def llm_router(self):
        """Lazy load LLM router."""
        if self._llm_router is None:
            try:
                from core.llm_routing_gateway import get_llm_router
                self._llm_router = get_llm_router()
            except ImportError:
                logger.warning("LLM router not available")
        return self._llm_router
    
    @property
    def website_monitor(self):
        """Lazy load website intent monitor."""
        if self._website_monitor is None:
            try:
                from core.website_intent_monitor import get_website_monitor
                self._website_monitor = get_website_monitor()
            except ImportError:
                logger.warning("Website monitor not available")
        return self._website_monitor
    
    async def prepare_contact_for_call(
        self,
        contact_id: str,
        update_ghl: bool = True
    ) -> CallPrepResult:
        """
        Main entry point: Prepare a contact for an upcoming call.
        
        Args:
            contact_id: GHL contact ID
            update_ghl: Whether to update custom fields in GHL
            
        Returns:
            CallPrepResult with all enriched data
        """
        logger.info(f"Preparing call context for contact: {contact_id}")
        
        # 1. Fetch contact from GHL
        contact = await self._fetch_ghl_contact(contact_id)
        if not contact:
            logger.error(f"Contact not found: {contact_id}")
            return CallPrepResult(
                contact_id=contact_id,
                contact_name="Unknown",
                company_name="Unknown",
                summary="ERROR: Contact not found in GHL"
            )
        
        contact_name = f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip()
        company_name = contact.get('companyName', 'Unknown Company')
        
        # 2. Gather context from multiple sources
        context = await self._gather_context(contact)
        
        # 3. Generate call prep using LLM
        result = await self._generate_call_prep(contact, context)
        
        # 4. Update GHL custom fields
        if update_ghl and self.ghl_api_key:
            await self._update_ghl_custom_fields(contact_id, result)
        
        # 5. Save to local storage
        self._save_prep_result(result)
        
        logger.info(f"Call prep complete for {contact_name} @ {company_name}")
        return result
    
    async def _fetch_ghl_contact(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Fetch contact data from GHL."""
        if not self.ghl_api_key:
            logger.warning("GHL API key not configured")
            return None
        
        import httpx
        
        url = f"https://services.leadconnectorhq.com/contacts/{contact_id}"
        headers = {
            "Authorization": f"Bearer {self.ghl_api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.json().get("contact", {})
                else:
                    logger.error(f"GHL fetch failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"GHL fetch error: {e}")
            return None
    
    async def _gather_context(self, contact: Dict[str, Any]) -> Dict[str, Any]:
        """Gather context from multiple sources."""
        context = {
            "contact": contact,
            "page_views": [],
            "warm_connections": [],
            "enrichment_data": {},
            "email_history": [],
            "signals": []
        }
        
        email = contact.get("email", "")
        linkedin_url = contact.get("customFields", {}).get("linkedin_url", "")
        company_domain = contact.get("website", "") or contact.get("customFields", {}).get("company_domain", "")
        
        # Get page views from website monitor
        if self.website_monitor:
            try:
                # Check for any stored intent data
                intent_dir = PROJECT_ROOT / ".hive-mind" / "website_intent"
                if intent_dir.exists():
                    for f in intent_dir.glob("*.json"):
                        try:
                            with open(f) as fp:
                                data = json.load(fp)
                                if data.get("email") == email or data.get("linkedin_url") == linkedin_url:
                                    context["page_views"].extend(data.get("pages_viewed", []))
                                    context["signals"].extend(data.get("triggers", []))
                        except:
                            pass
            except Exception as e:
                logger.warning(f"Failed to get page views: {e}")
        
        # Get warm connections
        if self.website_monitor:
            try:
                work_history = contact.get("customFields", {}).get("work_history", [])
                if isinstance(work_history, str):
                    try:
                        work_history = json.loads(work_history)
                    except:
                        work_history = []
                
                for member_id, member_data in self.website_monitor.team_network.items():
                    for prev_company in member_data.get("previous_companies", []):
                        for hist in work_history:
                            if hist.get("company_domain") == prev_company.get("domain"):
                                context["warm_connections"].append({
                                    "team_member": member_data.get("name"),
                                    "shared": prev_company.get("name"),
                                    "type": "same_previous_company"
                                })
            except Exception as e:
                logger.warning(f"Failed to get warm connections: {e}")
        
        # Get enrichment data if available
        enrichment_dir = PROJECT_ROOT / ".hive-mind" / "enriched"
        if enrichment_dir.exists():
            for f in enrichment_dir.glob("*.json"):
                try:
                    with open(f) as fp:
                        data = json.load(fp)
                        if data.get("email") == email:
                            context["enrichment_data"] = data
                            break
                except:
                    pass
        
        return context
    
    async def _generate_call_prep(
        self,
        contact: Dict[str, Any],
        context: Dict[str, Any]
    ) -> CallPrepResult:
        """Generate call prep using LLM."""
        contact_name = f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip()
        company_name = contact.get('companyName', 'Unknown')
        job_title = contact.get('customFields', {}).get('job_title', '') or contact.get('title', '')
        
        # Build prompt for LLM
        prompt = self._build_prep_prompt(contact, context)
        
        # Use LLM to generate prep
        if self.llm_router:
            try:
                from core.llm_routing_gateway import TaskType
                response = await self.llm_router.complete(
                    messages=[{"role": "user", "content": prompt}],
                    task_type=TaskType.ANALYSIS,
                    agent_name="PREPPER"
                )
                prep_text = response.get("content", "")
                return self._parse_llm_response(
                    contact.get("id", ""),
                    contact_name,
                    company_name,
                    prep_text,
                    context
                )
            except Exception as e:
                logger.warning(f"LLM generation failed: {e}")
        
        # Fallback: Generate basic prep without LLM
        return self._generate_basic_prep(contact, context)
    
    def _build_prep_prompt(self, contact: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Build the SDR research prompt for LLM call prep generation."""
        contact_name = f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip()
        company_name = contact.get('companyName', '')
        job_title = contact.get('customFields', {}).get('job_title', '') or contact.get('title', '')
        website = contact.get('website', '') or contact.get('customFields', {}).get('company_domain', '')
        linkedin = contact.get('customFields', {}).get('linkedin_url', '')
        
        # Get enrichment data
        enrich = context.get("enrichment_data", {})
        industry = enrich.get('industry', '')
        employee_count = enrich.get('company_size', '') or enrich.get('employee_count', '')
        
        # Format warm connections
        warm_conn_str = "None detected"
        if context.get("warm_connections"):
            parts = []
            for conn in context["warm_connections"]:
                parts.append(f"{conn.get('team_member', 'Team member')}: Both worked at {conn.get('shared', 'Unknown')}")
            warm_conn_str = "; ".join(parts)
        
        # Format page views
        pages_str = "None recorded"
        if context.get("page_views"):
            pages_str = ", ".join(context["page_views"][:5])
        
        # Format intent signals
        signals_str = "None detected"
        if context.get("signals"):
            signals_str = ", ".join(context["signals"][:5])
        
        # Use the SDR Research Prompt
        prompt = SDR_RESEARCH_PROMPT.format(
            name=contact_name or "Not provided",
            title=job_title or "Not provided",
            company=company_name or "Not provided",
            website=website or "Not provided",
            industry=industry or "Not provided",
            employee_count=employee_count or "Not provided",
            linkedin=linkedin or "Not provided",
            pages_viewed=pages_str,
            warm_connections=warm_conn_str,
            intent_signals=signals_str
        )
        
        return prompt
    
    def _parse_llm_response(
        self,
        contact_id: str,
        contact_name: str,
        company_name: str,
        response_text: str,
        context: Dict[str, Any]
    ) -> CallPrepResult:
        """Parse LLM response into structured result."""
        result = CallPrepResult(
            contact_id=contact_id,
            contact_name=contact_name,
            company_name=company_name,
            warm_connections=context.get("warm_connections", []),
            sources_used=["ghl", "website_intent", "llm"]
        )
        
        # Parse sections from response
        sections = response_text.split("##")
        for section in sections:
            section = section.strip()
            if section.lower().startswith("summary"):
                result.summary = section.split("\n", 1)[-1].strip()[:500]
            elif section.lower().startswith("pain points"):
                lines = section.split("\n")[1:]
                result.pain_points = [l.strip("- ").strip() for l in lines if l.strip()][:5]
            elif section.lower().startswith("recommended approach"):
                result.recommended_approach = section.split("\n", 1)[-1].strip()[:300]
            elif section.lower().startswith("likely objections"):
                lines = section.split("\n")[1:]
                for line in lines:
                    if ":" in line or "→" in line:
                        parts = line.replace("→", ":").split(":", 1)
                        if len(parts) == 2:
                            result.objection_prep.append({
                                "objection": parts[0].strip("- ").strip(),
                                "response": parts[1].strip()
                            })
            elif section.lower().startswith("conversation starters"):
                # Add to company context as conversation starters
                result.company_context = section.split("\n", 1)[-1].strip()[:500]
        
        # Calculate confidence
        confidence = 0.3  # Base
        if result.summary:
            confidence += 0.2
        if result.pain_points:
            confidence += 0.15
        if context.get("warm_connections"):
            confidence += 0.2
        if context.get("page_views"):
            confidence += 0.15
        result.confidence_score = min(confidence, 1.0)
        
        return result
    
    def _generate_basic_prep(
        self,
        contact: Dict[str, Any],
        context: Dict[str, Any]
    ) -> CallPrepResult:
        """Generate basic prep without LLM."""
        contact_id = contact.get("id", "")
        contact_name = f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip()
        company_name = contact.get('companyName', 'Unknown')
        job_title = contact.get('customFields', {}).get('job_title', '') or contact.get('title', '')
        
        # Build basic summary
        summary_parts = [f"{contact_name} is {job_title} at {company_name}."]
        
        if context.get("warm_connections"):
            conn = context["warm_connections"][0]
            summary_parts.append(
                f"Warm connection: {conn.get('team_member')} also worked at {conn.get('shared')}."
            )
        
        if context.get("page_views"):
            summary_parts.append(
                f"Recently viewed: {', '.join(context['page_views'][:2])}."
            )
        
        # Default pain points based on role
        pain_points = []
        if "sales" in job_title.lower() or "revenue" in job_title.lower():
            pain_points = [
                "Pipeline visibility and forecasting accuracy",
                "Rep productivity and time spent on admin tasks",
                "Cross-team alignment between sales and product"
            ]
        elif "operations" in job_title.lower() or "ops" in job_title.lower():
            pain_points = [
                "Manual processes slowing down execution",
                "Data silos across systems",
                "Scaling operations without adding headcount"
            ]
        else:
            pain_points = [
                "Operational efficiency and cost reduction",
                "Competitive pressure to adopt AI",
                "Measuring ROI on technology investments"
            ]
        
        # Default objections
        objection_prep = [
            {"objection": "We're not ready for AI", "response": "Our AI Readiness Assessment takes 5 min and shows exactly where to start"},
            {"objection": "Too expensive", "response": "We guarantee measured ROI or you don't pay the next phase"},
            {"objection": "Already have tools", "response": "We integrate with existing stack - this is about orchestration, not replacement"}
        ]
        
        return CallPrepResult(
            contact_id=contact_id,
            contact_name=contact_name,
            company_name=company_name,
            summary=" ".join(summary_parts),
            pain_points=pain_points,
            warm_connections=context.get("warm_connections", []),
            recommended_approach=f"Lead with the warm connection if available, otherwise focus on {context.get('signals', ['general AI efficiency'])[0] if context.get('signals') else 'efficiency gains'}.",
            objection_prep=objection_prep,
            confidence_score=0.5,
            sources_used=["ghl", "defaults"]
        )
    
    async def _update_ghl_custom_fields(
        self,
        contact_id: str,
        result: CallPrepResult
    ) -> bool:
        """Update GHL contact with call prep custom fields."""
        import httpx
        
        url = f"https://services.leadconnectorhq.com/contacts/{contact_id}"
        headers = {
            "Authorization": f"Bearer {self.ghl_api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        
        payload = {
            "customFields": result.to_ghl_custom_fields()
        }
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.put(url, json=payload, headers=headers)
                if response.status_code in [200, 201]:
                    logger.info(f"Updated GHL custom fields for {contact_id}")
                    return True
                else:
                    logger.error(f"GHL update failed: {response.status_code} - {response.text}")
                    return False
        except Exception as e:
            logger.error(f"GHL update error: {e}")
            return False
    
    def _save_prep_result(self, result: CallPrepResult):
        """Save prep result to local storage."""
        filename = f"{result.contact_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.storage_dir / filename
        
        try:
            with open(filepath, "w") as f:
                json.dump(asdict(result), f, indent=2)
            logger.info(f"Saved call prep to {filepath}")
        except Exception as e:
            logger.warning(f"Failed to save prep result: {e}")
    
    async def prepare_hot_leads_batch(self, limit: int = 10) -> List[CallPrepResult]:
        """Prepare all hot leads in the queue for calls."""
        results = []
        
        # Get hot leads from shadow_mode_emails
        shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
        if not shadow_dir.exists():
            return results
        
        for f in list(shadow_dir.glob("*.json"))[:limit]:
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    if data.get("priority") == "high" and data.get("status") == "pending":
                        contact_id = data.get("contact_id")
                        if contact_id:
                            result = await self.prepare_contact_for_call(contact_id)
                            results.append(result)
            except Exception as e:
                logger.warning(f"Failed to process {f}: {e}")
        
        return results
    
    # =========================================================================
    # TRIGGER DETECTION & EMAIL SENDING
    # =========================================================================
    
    async def check_triggers(self) -> List[TriggerCondition]:
        """
        Check all trigger conditions and return list of contacts needing prep.
        
        Guardrails for when to activate:
        1. Calendar: Meetings scheduled for tomorrow
        2. Approval: Recently approved emails (last hour)
        3. Hot Lead: High intent + warm connections
        """
        triggers = []
        
        # 1. Check calendar for tomorrow's meetings
        tomorrow_meetings = await self._get_tomorrow_meetings()
        for meeting in tomorrow_meetings:
            contact_id = meeting.get("contact_id")
            if contact_id:
                triggers.append(TriggerCondition(
                    trigger_type=PrepTrigger.CALENDAR,
                    contact_id=contact_id,
                    reason=f"Meeting scheduled: {meeting.get('title', 'Call')}",
                    priority=1,
                    meeting_time=meeting.get("start_time")
                ))
        
        # 2. Check recently approved emails
        approved = await self._get_recently_approved()
        for email in approved:
            contact_id = email.get("contact_id")
            if contact_id:
                triggers.append(TriggerCondition(
                    trigger_type=PrepTrigger.APPROVAL,
                    contact_id=contact_id,
                    reason=f"Email approved: {email.get('subject', 'Outreach')}",
                    priority=2
                ))
        
        # 3. Check hot leads with warm connections
        hot_leads = await self._get_hot_leads_with_connections()
        for lead in hot_leads:
            triggers.append(TriggerCondition(
                trigger_type=PrepTrigger.HOT_LEAD,
                contact_id=lead.get("contact_id"),
                reason=f"Hot lead ({lead.get('intent_score', 0)} intent) with warm connection",
                priority=3
            ))
        
        # Sort by priority
        triggers.sort(key=lambda t: t.priority)
        
        logger.info(f"Found {len(triggers)} prep triggers")
        return triggers
    
    async def _get_tomorrow_meetings(self) -> List[Dict[str, Any]]:
        """Get meetings scheduled for tomorrow from GHL/calendar."""
        meetings = []
        
        # Check meetings directory
        meetings_dir = PROJECT_ROOT / ".hive-mind" / "meetings"
        if meetings_dir.exists():
            tomorrow = (datetime.now() + timedelta(days=1)).date()
            for f in meetings_dir.glob("*.json"):
                try:
                    with open(f) as fp:
                        data = json.load(fp)
                        meeting_date = data.get("date", "")
                        if meeting_date and tomorrow.isoformat() in meeting_date:
                            meetings.append(data)
                except:
                    pass
        
        return meetings
    
    async def _get_recently_approved(self) -> List[Dict[str, Any]]:
        """Get emails approved in the last hour."""
        approved = []
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        
        shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
        if shadow_dir.exists():
            for f in shadow_dir.glob("*.json"):
                try:
                    with open(f) as fp:
                        data = json.load(fp)
                        if data.get("status") == "approved":
                            approved_at = data.get("approved_at", "")
                            if approved_at:
                                try:
                                    dt = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
                                    if dt > one_hour_ago:
                                        approved.append(data)
                                except:
                                    pass
                except:
                    pass
        
        return approved
    
    async def _get_hot_leads_with_connections(self) -> List[Dict[str, Any]]:
        """Get hot leads that have warm connections."""
        hot_leads = []
        
        shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
        if shadow_dir.exists():
            for f in shadow_dir.glob("*.json"):
                try:
                    with open(f) as fp:
                        data = json.load(fp)
                        context = data.get("context", {})
                        intent_score = context.get("intent_score", 0)
                        warm_connections = context.get("warm_connections", [])
                        
                        # Hot lead threshold + has warm connections
                        if intent_score >= HOT_LEAD_INTENT_THRESHOLD and warm_connections:
                            # Check if not already prepped
                            if not data.get("prepped"):
                                hot_leads.append({
                                    "contact_id": data.get("contact_id"),
                                    "intent_score": intent_score,
                                    "warm_connections": warm_connections,
                                    "email_file": str(f)
                                })
                except:
                    pass
        
        return hot_leads
    
    async def send_prep_email_to_dani(
        self,
        result: CallPrepResult,
        trigger: TriggerCondition
    ) -> bool:
        """
        Send ICP research brief email to Dani.
        Sent the night before a call for review.
        """
        import httpx
        
        # Format the email body
        meeting_info = ""
        if trigger.meeting_time:
            meeting_info = f"\n📅 **Meeting Time:** {trigger.meeting_time}\n"
        
        email_body = f"""Hi Dani,

Here's your call prep brief for tomorrow's conversation.

{meeting_info}
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**

# Lead Snapshot
{result.summary}

# Company Context
{result.company_context or 'Inferred from available signals - see Sales Angles'}

# Sales Angles
"""
        for i, angle in enumerate(result.pain_points[:3], 1):
            email_body += f"{i}. {angle}\n"
        
        email_body += f"""
# Warm Connections
"""
        if result.warm_connections:
            for conn in result.warm_connections:
                email_body += f"• {conn.get('team_member', 'Team')}: Both worked at {conn.get('shared', 'Unknown')}\n"
        else:
            email_body += "• No warm connections detected\n"
        
        email_body += f"""
# Recommended Approach
{result.recommended_approach}

# Likely Objections
"""
        for obj in result.objection_prep[:3]:
            email_body += f"• If \"{obj.get('objection', '')}\" → {obj.get('response', '')}\n"
        
        email_body += f"""
**━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━**

**Confidence Score:** {result.confidence_score:.0%}
**Prep Trigger:** {trigger.reason}

— PREPPER Agent
Chief AI Officer Swarm
"""
        
        subject = f"📋 Call Prep: {result.contact_name} @ {result.company_name}"
        
        # Save email to outbox for GHL sending
        outbox_dir = PROJECT_ROOT / ".hive-mind" / "outbox"
        outbox_dir.mkdir(parents=True, exist_ok=True)
        
        email_data = {
            "to": DANI_EMAIL,
            "subject": subject,
            "body": email_body,
            "type": "call_prep",
            "contact_id": result.contact_id,
            "contact_name": result.contact_name,
            "company_name": result.company_name,
            "trigger": trigger.trigger_type.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending_send"
        }
        
        filename = f"prep_{result.contact_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = outbox_dir / filename
        
        with open(filepath, "w") as f:
            json.dump(email_data, f, indent=2)
        
        logger.info(f"📧 Prep email queued for Dani: {subject}")
        
        # Try to send via GHL if configured
        if self.ghl_api_key:
            try:
                # Use GHL to send internal email
                url = "https://services.leadconnectorhq.com/conversations/messages"
                headers = {
                    "Authorization": f"Bearer {self.ghl_api_key}",
                    "Content-Type": "application/json",
                    "Version": "2021-07-28"
                }
                
                payload = {
                    "type": "Email",
                    "locationId": self.ghl_location_id,
                    "email": DANI_EMAIL,
                    "subject": subject,
                    "html": email_body.replace("\n", "<br>"),
                    "emailFrom": "swarm@chiefaiofficer.com"
                }
                
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code in [200, 201]:
                        logger.info(f"✅ Prep email sent to Dani via GHL")
                        email_data["status"] = "sent"
                        with open(filepath, "w") as f:
                            json.dump(email_data, f, indent=2)
                        return True
                    else:
                        logger.warning(f"GHL email send returned {response.status_code}")
            except Exception as e:
                logger.warning(f"GHL email send failed: {e}")
        
        return True  # Email is queued even if not sent immediately
    
    async def prep_upcoming_calls(self) -> List[CallPrepResult]:
        """
        Main scheduled method: Check triggers and prep all upcoming calls.
        Run this at 8 PM daily to prep for tomorrow's calls.
        """
        logger.info("🔍 Checking for upcoming calls to prep...")
        
        triggers = await self.check_triggers()
        results = []
        
        for trigger in triggers:
            try:
                # Prepare the contact
                result = await self.prepare_contact_for_call(
                    contact_id=trigger.contact_id,
                    update_ghl=True
                )
                
                # Send email if trigger warrants it
                if trigger.should_send_email():
                    await self.send_prep_email_to_dani(result, trigger)
                
                results.append(result)
                
            except Exception as e:
                logger.error(f"Failed to prep {trigger.contact_id}: {e}")
        
        logger.info(f"✅ Prepped {len(results)} contacts for upcoming calls")
        return results
    
    async def on_email_approved(self, email_data: Dict[str, Any]):
        """
        Hook called when an email is approved in the queue.
        Triggers immediate prep since Dani is about to engage.
        """
        contact_id = email_data.get("contact_id")
        if not contact_id:
            return
        
        trigger = TriggerCondition(
            trigger_type=PrepTrigger.APPROVAL,
            contact_id=contact_id,
            reason=f"Email approved: {email_data.get('subject', 'Outreach')}",
            priority=2
        )
        
        result = await self.prepare_contact_for_call(contact_id, update_ghl=True)
        await self.send_prep_email_to_dani(result, trigger)
        
        return result


# =============================================================================
# SINGLETON & CLI
# =============================================================================

_agent: Optional[CallPrepAgent] = None


def get_call_prep_agent() -> CallPrepAgent:
    """Get or create the global call prep agent."""
    global _agent
    if _agent is None:
        _agent = CallPrepAgent()
    return _agent


async def main():
    """CLI for testing call prep agent."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Call Prep Agent (PREPPER)")
    parser.add_argument("--contact-id", type=str, help="GHL contact ID to prepare")
    parser.add_argument("--batch", action="store_true", help="Prepare all hot leads")
    parser.add_argument("--upcoming", action="store_true", help="Prep all upcoming calls (check triggers)")
    parser.add_argument("--check-triggers", action="store_true", help="Check triggers without prepping")
    parser.add_argument("--limit", type=int, default=10, help="Max leads to prepare in batch")
    parser.add_argument("--dry-run", action="store_true", help="Don't update GHL or send emails")
    parser.add_argument("--send-email", action="store_true", help="Send prep email to Dani")
    
    args = parser.parse_args()
    
    agent = get_call_prep_agent()
    
    if args.check_triggers:
        print("\n🔍 Checking prep triggers...")
        triggers = await agent.check_triggers()
        print(f"\nFound {len(triggers)} triggers:\n")
        for t in triggers:
            emoji = {"calendar": "📅", "approval": "✅", "hot_lead": "🔥", "manual": "👆"}.get(t.trigger_type.value, "•")
            print(f"  {emoji} [{t.trigger_type.value.upper()}] Contact: {t.contact_id}")
            print(f"     Reason: {t.reason}")
            print(f"     Send Email: {'Yes' if t.should_send_email() else 'No'}")
            print()
    
    elif args.upcoming:
        print("\n🔍 Prepping upcoming calls...")
        results = await agent.prep_upcoming_calls()
        print(f"\n✅ Prepped {len(results)} contacts")
        for r in results:
            print(f"  📋 {r.contact_name} @ {r.company_name} ({r.confidence_score:.0%})")
    
    elif args.contact_id:
        result = await agent.prepare_contact_for_call(
            args.contact_id,
            update_ghl=not args.dry_run
        )
        print("\n" + "=" * 60)
        print(f"  CALL PREP: {result.contact_name} @ {result.company_name}")
        print("=" * 60)
        print(f"\n📋 SUMMARY:\n{result.summary}")
        print(f"\n🎯 SALES ANGLES / PAIN POINTS:")
        for pp in result.pain_points:
            print(f"  • {pp}")
        print(f"\n🤝 WARM CONNECTIONS:")
        if result.warm_connections:
            for conn in result.warm_connections:
                print(f"  • {conn.get('team_member')}: {conn.get('shared')}")
        else:
            print("  • No warm connections detected")
        print(f"\n💡 RECOMMENDED APPROACH:\n{result.recommended_approach}")
        print(f"\n⚡ OBJECTION PREP:")
        for obj in result.objection_prep:
            print(f"  • If '{obj.get('objection', '')}' → {obj.get('response', '')}")
        print(f"\n🔍 Confidence: {result.confidence_score:.0%}")
        print("=" * 60)
        
        if args.send_email and not args.dry_run:
            trigger = TriggerCondition(
                trigger_type=PrepTrigger.MANUAL,
                contact_id=args.contact_id,
                reason="Manual CLI trigger",
                priority=4
            )
            await agent.send_prep_email_to_dani(result, trigger)
            print(f"\n📧 Prep email sent to {DANI_EMAIL}")
    
    elif args.batch:
        results = await agent.prepare_hot_leads_batch(args.limit)
        print(f"\nPrepared {len(results)} hot leads for calls")
        for r in results:
            print(f"  ✓ {r.contact_name} @ {r.company_name} ({r.confidence_score:.0%})")
    
    else:
        parser.print_help()
        print("\n📋 PREPPER Agent Trigger Conditions:")
        print("  1. CALENDAR: Meeting scheduled for tomorrow → Email sent at 8 PM")
        print("  2. APPROVAL: Dani approves email in queue → Immediate prep + email")
        print("  3. HOT_LEAD: Intent ≥75 + warm connections → Prep + email")
        print("  4. MANUAL: API/CLI trigger → Prep (email optional)")
        print(f"\n  Emails sent to: {DANI_EMAIL}")


if __name__ == "__main__":
    asyncio.run(main())
