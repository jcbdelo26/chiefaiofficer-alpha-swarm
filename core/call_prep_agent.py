#!/usr/bin/env python3
"""
Call Prep Agent (PREPPER)
=========================
Enriches GHL contact custom fields with call-ready context before Dani's calls.

This agent runs when:
1. A lead is marked as "hot" or "warm" in the queue
2. A meeting is scheduled in GHL calendar
3. Manually triggered before a call

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
        """Build the prompt for LLM call prep generation."""
        contact_name = f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip()
        company_name = contact.get('companyName', 'Unknown')
        job_title = contact.get('customFields', {}).get('job_title', '') or contact.get('title', '')
        
        prompt = f"""You are preparing Dani Apgar (Head of Partnerships at Chief AI Officer) for a sales call.

CONTACT INFORMATION:
- Name: {contact_name}
- Title: {job_title}
- Company: {company_name}
- Email: {contact.get('email', 'N/A')}

"""
        
        if context.get("page_views"):
            prompt += f"PAGES VIEWED ON OUR WEBSITE:\n"
            for page in context["page_views"][:5]:
                prompt += f"- {page}\n"
            prompt += "\n"
        
        if context.get("warm_connections"):
            prompt += f"WARM CONNECTIONS:\n"
            for conn in context["warm_connections"]:
                prompt += f"- {conn.get('team_member')}: Both worked at {conn.get('shared')}\n"
            prompt += "\n"
        
        if context.get("signals"):
            prompt += f"INTENT SIGNALS:\n"
            for signal in context["signals"]:
                prompt += f"- {signal}\n"
            prompt += "\n"
        
        if context.get("enrichment_data"):
            enrich = context["enrichment_data"]
            prompt += f"""COMPANY DATA:
- Industry: {enrich.get('industry', 'Unknown')}
- Size: {enrich.get('company_size', 'Unknown')}
- Revenue: {enrich.get('revenue', 'Unknown')}

"""
        
        prompt += """Please generate a call prep with the following sections (use these exact headers):

## SUMMARY
One paragraph briefing Dani can read 2 minutes before the call.

## PAIN POINTS
3-5 likely pain points based on their role, company, and behavior.

## RECOMMENDED APPROACH
The best angle to lead with based on signals and context.

## LIKELY OBJECTIONS
2-3 objections they might raise and brief responses.

## CONVERSATION STARTERS
2-3 specific things Dani can mention to build rapport (based on warm connections, pages viewed, etc.)
"""
        
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
    
    parser = argparse.ArgumentParser(description="Call Prep Agent")
    parser.add_argument("--contact-id", type=str, help="GHL contact ID to prepare")
    parser.add_argument("--batch", action="store_true", help="Prepare all hot leads")
    parser.add_argument("--limit", type=int, default=10, help="Max leads to prepare in batch")
    parser.add_argument("--dry-run", action="store_true", help="Don't update GHL")
    
    args = parser.parse_args()
    
    agent = get_call_prep_agent()
    
    if args.contact_id:
        result = await agent.prepare_contact_for_call(
            args.contact_id,
            update_ghl=not args.dry_run
        )
        print("\n" + "=" * 60)
        print(f"  CALL PREP: {result.contact_name} @ {result.company_name}")
        print("=" * 60)
        print(f"\n📋 SUMMARY:\n{result.summary}")
        print(f"\n🎯 PAIN POINTS:")
        for pp in result.pain_points:
            print(f"  • {pp}")
        print(f"\n🤝 WARM CONNECTIONS:")
        for conn in result.warm_connections:
            print(f"  • {conn.get('team_member')}: {conn.get('shared')}")
        print(f"\n💡 RECOMMENDED APPROACH:\n{result.recommended_approach}")
        print(f"\n⚡ OBJECTION PREP:")
        for obj in result.objection_prep:
            print(f"  • If '{obj['objection']}' → {obj['response']}")
        print(f"\n🔍 Confidence: {result.confidence_score:.0%}")
        print("=" * 60)
    
    elif args.batch:
        results = await agent.prepare_hot_leads_batch(args.limit)
        print(f"\nPrepared {len(results)} hot leads for calls")
        for r in results:
            print(f"  ✓ {r.contact_name} @ {r.company_name} ({r.confidence_score:.0%})")


if __name__ == "__main__":
    asyncio.run(main())
