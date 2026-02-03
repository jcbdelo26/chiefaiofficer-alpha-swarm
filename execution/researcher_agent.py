#!/usr/bin/env python3
"""
Researcher Agent - Beta Swarm (Day 13)
========================================
Pre-meeting research and meeting brief generation.

Capabilities:
1. Company research (website, LinkedIn, news)
2. Attendee research (profiles, GHL history, past interactions)
3. Tech stack detection
4. Objection prediction
5. Talking point generation
6. Meeting brief generation

Data Sources:
- Exa.ai for web research (via exa-mcp)
- GHL for contact history
- .hive-mind/knowledge for cached intel
- LinkedIn profiles (scraped data)

Output:
- Meeting briefs saved to .hive-mind/researcher/briefs/
- Structured JSON with research findings
- One-page summary for AE

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                    RESEARCHER AGENT                              │
    ├─────────────────────────────────────────────────────────────────┤
    │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
    │  │ Company         │  │ Attendee        │  │ Brief           │ │
    │  │ Research        │  │ Research        │  │ Generator       │ │
    │  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
    │           │                    │                    │          │
    │  ┌────────▼────────┐  ┌────────▼────────┐           │          │
    │  │ Exa.ai          │  │ GHL Contact     │           │          │
    │  │ Web Search      │  │ History         │           │          │
    │  └─────────────────┘  └─────────────────┘           │          │
    │                                    ┌────────────────▼────────┐ │
    │                                    │ .hive-mind/briefs/      │ │
    │                                    └─────────────────────────┘ │
    └─────────────────────────────────────────────────────────────────┘

Usage:
    from execution.researcher_agent import ResearcherAgent
    
    researcher = ResearcherAgent()
    
    # Research a company
    company_intel = await researcher.research_company(
        company_name="Acme Corp",
        company_website="https://acme.com"
    )
    
    # Research an attendee
    attendee_intel = await researcher.research_attendee(
        email="john@acme.com",
        name="John Smith",
        linkedin_url="https://linkedin.com/in/johnsmith"
    )
    
    # Generate full meeting brief
    brief = await researcher.generate_meeting_brief(
        meeting_id="MTG-001",
        company="Acme Corp",
        attendees=["john@acme.com"],
        meeting_type="discovery"
    )
"""

import os
import sys
import json
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("researcher_agent")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class ResearchType(Enum):
    """Types of research tasks."""
    COMPANY = "company"
    ATTENDEE = "attendee"
    TECH_STACK = "tech_stack"
    NEWS = "news"
    COMPETITORS = "competitors"
    OBJECTIONS = "objections"
    FULL_BRIEF = "full_brief"


class BriefStatus(Enum):
    """Status of a meeting brief."""
    PENDING = "pending"
    RESEARCHING = "researching"
    READY = "ready"
    DELIVERED = "delivered"
    EXPIRED = "expired"


# Research cache TTL
CACHE_TTL_DAYS = 7
MAX_NEWS_ARTICLES = 5
MAX_TALKING_POINTS = 5


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class CompanyIntel:
    """Company research data."""
    company_name: str
    website: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    headquarters: Optional[str] = None
    description: Optional[str] = None
    tech_stack: List[str] = field(default_factory=list)
    recent_news: List[Dict[str, str]] = field(default_factory=list)
    competitors: List[str] = field(default_factory=list)
    pain_points: List[str] = field(default_factory=list)
    linkedin_url: Optional[str] = None
    funding: Optional[str] = None
    employee_count: Optional[int] = None
    revenue_estimate: Optional[str] = None
    researched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confidence: float = 0.0


@dataclass
class AttendeeIntel:
    """Attendee research data."""
    email: str
    name: str
    title: Optional[str] = None
    linkedin_url: Optional[str] = None
    company: Optional[str] = None
    department: Optional[str] = None
    seniority: Optional[str] = None
    background: Optional[str] = None
    interests: List[str] = field(default_factory=list)
    past_interactions: List[Dict[str, Any]] = field(default_factory=list)
    communication_style: Optional[str] = None
    decision_maker: bool = False
    ghl_contact_id: Optional[str] = None
    ghl_tags: List[str] = field(default_factory=list)
    researched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confidence: float = 0.0


@dataclass
class ObjectionPrediction:
    """Predicted objection with response."""
    objection_type: str
    likelihood: float  # 0-1
    objection_text: str
    recommended_response: str
    evidence: Optional[str] = None


@dataclass
class TalkingPoint:
    """Suggested talking point for the meeting."""
    topic: str
    key_message: str
    supporting_evidence: str
    priority: int = 1  # 1=highest


@dataclass
class MeetingBrief:
    """Complete meeting brief for AE."""
    brief_id: str
    meeting_id: str
    meeting_time: str
    meeting_type: str
    status: BriefStatus = BriefStatus.PENDING
    
    # Company intel
    company: Optional[CompanyIntel] = None
    
    # Attendees
    attendees: List[AttendeeIntel] = field(default_factory=list)
    primary_contact: Optional[str] = None
    
    # Insights
    talking_points: List[TalkingPoint] = field(default_factory=list)
    objections: List[ObjectionPrediction] = field(default_factory=list)
    
    # Recommendations
    meeting_goal: Optional[str] = None
    next_step: Optional[str] = None
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = None
    quality_score: float = 0.0
    
    # One-liner summary
    summary: Optional[str] = None


# =============================================================================
# RESEARCHER AGENT
# =============================================================================

class ResearcherAgent:
    """
    Researcher Agent for the Beta Swarm.
    
    Generates meeting briefs with company and attendee research,
    objection prediction, and talking points.
    """
    
    def __init__(self):
        """Initialize the Researcher Agent."""
        # Hive-mind storage
        self.hive_mind = PROJECT_ROOT / ".hive-mind"
        self.researcher_dir = self.hive_mind / "researcher"
        self.briefs_dir = self.researcher_dir / "briefs"
        self.cache_dir = self.researcher_dir / "cache"
        self.queue_dir = self.researcher_dir / "queue"
        
        # Create directories
        for dir_path in [self.briefs_dir, self.cache_dir, self.queue_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # Load knowledge base
        self._knowledge = self._load_knowledge()
        
        # Industry patterns for objection prediction
        self._objection_patterns = self._load_objection_patterns()
        
        logger.info("Researcher Agent initialized")
    
    def _load_knowledge(self) -> Dict[str, Any]:
        """Load cached knowledge from hive-mind."""
        knowledge_file = self.hive_mind / "knowledge" / "company_intel.json"
        if knowledge_file.exists():
            try:
                return json.loads(knowledge_file.read_text())
            except Exception as e:
                logger.warning(f"Failed to load knowledge: {e}")
        return {}
    
    def _save_knowledge(self, company_name: str, intel: CompanyIntel):
        """Cache company intel."""
        knowledge_dir = self.hive_mind / "knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        
        key = company_name.lower().replace(" ", "_")
        self._knowledge[key] = asdict(intel)
        
        knowledge_file = knowledge_dir / "company_intel.json"
        knowledge_file.write_text(json.dumps(self._knowledge, indent=2))
    
    def _load_objection_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Load objection patterns for prediction."""
        return {
            "pricing": {
                "triggers": ["budget", "cost", "expensive", "price"],
                "response_template": "I understand budget is a concern. Let me show you the ROI our clients typically see...",
                "likelihood_boost": 0.2
            },
            "timing": {
                "triggers": ["busy", "later", "next quarter", "not now"],
                "response_template": "Timing is important. Many clients find that starting now actually saves time in the long run...",
                "likelihood_boost": 0.15
            },
            "competitor": {
                "triggers": ["using", "already have", "competitor", "alternative"],
                "response_template": "Great that you're already addressing this. Let me share how we're different...",
                "likelihood_boost": 0.25
            },
            "authority": {
                "triggers": ["discuss with", "check with", "manager", "approval"],
                "response_template": "Absolutely, involving the right stakeholders is crucial. Would it help if I provided materials for that conversation?",
                "likelihood_boost": 0.1
            },
            "skepticism": {
                "triggers": ["prove", "show me", "evidence", "case study"],
                "response_template": "I'd be happy to share specific examples. We have case studies from similar companies...",
                "likelihood_boost": 0.2
            }
        }
    
    def _generate_id(self, prefix: str = "RSR") -> str:
        """Generate a unique ID."""
        hash_input = f"{prefix}:{datetime.now().isoformat()}:{id(self)}"
        return f"{prefix}-{hashlib.md5(hash_input.encode()).hexdigest()[:8].upper()}"
    
    # =========================================================================
    # COMPANY RESEARCH
    # =========================================================================
    
    async def research_company(
        self,
        company_name: str,
        company_website: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        force_refresh: bool = False
    ) -> CompanyIntel:
        """
        Research a company and compile intelligence.
        
        Args:
            company_name: Company name
            company_website: Company website URL
            linkedin_url: Company LinkedIn URL
            force_refresh: Force fresh research (ignore cache)
        
        Returns:
            CompanyIntel with research findings
        """
        cache_key = company_name.lower().replace(" ", "_")
        
        # Check cache
        if not force_refresh:
            cached = self._get_cached_intel(cache_key, "company")
            if cached:
                logger.info(f"Using cached intel for {company_name}")
                return CompanyIntel(**cached)
        
        logger.info(f"Researching company: {company_name}")
        
        intel = CompanyIntel(
            company_name=company_name,
            website=company_website,
            linkedin_url=linkedin_url
        )
        
        # 1. Web search via Exa or mock
        web_results = await self._search_web(f"{company_name} company overview")
        if web_results:
            intel.description = web_results.get("summary", "")
            intel.industry = web_results.get("industry", "")
        
        # 2. Tech stack detection
        if company_website:
            tech_stack = await self._detect_tech_stack(company_website)
            intel.tech_stack = tech_stack
        
        # 3. Recent news
        news = await self._search_news(company_name)
        intel.recent_news = news[:MAX_NEWS_ARTICLES]
        
        # 4. Extract pain points from news/description
        intel.pain_points = self._extract_pain_points(intel)
        
        # 5. Estimate company size and revenue (mock)
        size_info = await self._estimate_company_size(company_name, intel.description)
        intel.company_size = size_info.get("size", "Unknown")
        intel.employee_count = size_info.get("employees")
        intel.revenue_estimate = size_info.get("revenue")
        
        # Calculate confidence
        intel.confidence = self._calculate_intel_confidence(intel)
        
        # Cache the results
        self._cache_intel(cache_key, "company", asdict(intel))
        self._save_knowledge(company_name, intel)
        
        logger.info(f"Company research complete for {company_name} (confidence: {intel.confidence:.0%})")
        
        return intel
    
    async def _search_web(self, query: str) -> Dict[str, Any]:
        """Search web using Exa or mock."""
        # Try to use Exa MCP if available
        try:
            sys.path.insert(0, str(PROJECT_ROOT / "mcp-servers" / "exa-mcp"))
            from server import ExaMCP
            
            exa = ExaMCP()
            results = await exa.search(query, num_results=5)
            return results
        except ImportError:
            logger.debug("Exa MCP not available - using mock")
        except Exception as e:
            logger.warning(f"Exa search failed: {e}")
        
        # Mock response
        return {
            "summary": f"Company information for query: {query}",
            "industry": "Technology",
            "results": []
        }
    
    async def _detect_tech_stack(self, website_url: str) -> List[str]:
        """Detect technology stack from website."""
        # In production, this would use tools like BuiltWith or Wappalyzer
        # For now, return common B2B SaaS tech
        
        common_tech = [
            "Salesforce", "HubSpot", "Slack", "Google Workspace",
            "Zoom", "Microsoft 365", "AWS", "React"
        ]
        
        # Mock: randomly select some technologies
        import random
        return random.sample(common_tech, min(4, len(common_tech)))
    
    async def _search_news(self, company_name: str) -> List[Dict[str, str]]:
        """Search for recent company news."""
        # Mock news results
        return [
            {
                "title": f"{company_name} Announces Q4 Growth",
                "source": "TechCrunch",
                "date": (datetime.now() - timedelta(days=5)).isoformat(),
                "summary": f"Strong performance reported by {company_name}.",
                "url": f"https://techcrunch.com/{company_name.lower().replace(' ', '-')}"
            },
            {
                "title": f"{company_name} Expands Team",
                "source": "LinkedIn",
                "date": (datetime.now() - timedelta(days=12)).isoformat(),
                "summary": f"{company_name} hiring for multiple positions.",
                "url": f"https://linkedin.com/company/{company_name.lower().replace(' ', '-')}"
            }
        ]
    
    def _extract_pain_points(self, intel: CompanyIntel) -> List[str]:
        """Extract potential pain points from company intel."""
        pain_points = []
        
        # Industry-based pain points
        industry_pains = {
            "technology": ["Scaling challenges", "Technical debt", "Talent acquisition"],
            "saas": ["Churn reduction", "Customer success", "Product-market fit"],
            "finance": ["Regulatory compliance", "Security concerns", "Digital transformation"],
            "healthcare": ["HIPAA compliance", "Patient experience", "Cost management"]
        }
        
        if intel.industry:
            industry_key = intel.industry.lower()
            for key, pains in industry_pains.items():
                if key in industry_key:
                    pain_points.extend(pains[:2])
                    break
        
        # News-based pain points
        if intel.recent_news:
            for news in intel.recent_news:
                if "growth" in news.get("title", "").lower():
                    pain_points.append("Scaling operations efficiently")
                if "hiring" in news.get("title", "").lower():
                    pain_points.append("Team productivity and onboarding")
        
        return list(set(pain_points))[:5]
    
    async def _estimate_company_size(
        self,
        company_name: str,
        description: Optional[str]
    ) -> Dict[str, Any]:
        """Estimate company size and revenue."""
        # Mock estimation
        return {
            "size": "51-200 employees",
            "employees": 100,
            "revenue": "$10M-$50M ARR"
        }
    
    def _calculate_intel_confidence(self, intel: CompanyIntel) -> float:
        """Calculate confidence score for intel."""
        score = 0.0
        
        if intel.website:
            score += 0.15
        if intel.industry:
            score += 0.15
        if intel.description:
            score += 0.2
        if intel.tech_stack:
            score += 0.15
        if intel.recent_news:
            score += 0.15
        if intel.pain_points:
            score += 0.1
        if intel.linkedin_url:
            score += 0.1
        
        return min(1.0, score)
    
    # =========================================================================
    # ATTENDEE RESEARCH
    # =========================================================================
    
    async def research_attendee(
        self,
        email: str,
        name: str,
        company: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        ghl_contact_id: Optional[str] = None,
        force_refresh: bool = False
    ) -> AttendeeIntel:
        """
        Research an attendee and compile intelligence.
        
        Args:
            email: Attendee email
            name: Attendee name
            company: Company name
            linkedin_url: LinkedIn profile URL
            ghl_contact_id: GHL contact ID for history
            force_refresh: Force fresh research
        
        Returns:
            AttendeeIntel with research findings
        """
        cache_key = email.lower().replace("@", "_at_").replace(".", "_")
        
        # Check cache
        if not force_refresh:
            cached = self._get_cached_intel(cache_key, "attendee")
            if cached:
                logger.info(f"Using cached intel for {email}")
                return AttendeeIntel(**cached)
        
        logger.info(f"Researching attendee: {name} ({email})")
        
        intel = AttendeeIntel(
            email=email,
            name=name,
            company=company,
            linkedin_url=linkedin_url,
            ghl_contact_id=ghl_contact_id
        )
        
        # 1. Infer title and seniority from name/email
        title_info = self._infer_title(email, name)
        intel.title = title_info.get("title")
        intel.seniority = title_info.get("seniority")
        intel.department = title_info.get("department")
        intel.decision_maker = title_info.get("decision_maker", False)
        
        # 2. Get GHL history if available
        if ghl_contact_id:
            ghl_history = await self._get_ghl_history(ghl_contact_id)
            intel.past_interactions = ghl_history.get("interactions", [])
            intel.ghl_tags = ghl_history.get("tags", [])
        
        # 3. LinkedIn research (mock)
        if linkedin_url:
            linkedin_data = await self._research_linkedin(linkedin_url)
            if linkedin_data:
                intel.background = linkedin_data.get("background")
                intel.interests = linkedin_data.get("interests", [])
        
        # 4. Determine communication style
        intel.communication_style = self._infer_communication_style(intel)
        
        # Calculate confidence
        intel.confidence = self._calculate_attendee_confidence(intel)
        
        # Cache results
        self._cache_intel(cache_key, "attendee", asdict(intel))
        
        logger.info(f"Attendee research complete for {name} (confidence: {intel.confidence:.0%})")
        
        return intel
    
    def _infer_title(self, email: str, name: str) -> Dict[str, Any]:
        """Infer title and seniority from email/name patterns."""
        email_lower = email.lower()
        name_lower = name.lower()
        
        # Title patterns
        c_suite = ["ceo", "cfo", "cto", "cmo", "coo", "cro", "chief"]
        vp_level = ["vp", "vice president", "svp", "evp"]
        director = ["director", "head of"]
        manager = ["manager", "lead", "sr", "senior"]
        
        title = None
        seniority = "unknown"
        department = None
        decision_maker = False
        
        combined = f"{email_lower} {name_lower}"
        
        for term in c_suite:
            if term in combined:
                seniority = "c-level"
                decision_maker = True
                title = f"Chief {term.upper()} Officer" if term != "chief" else "C-Suite Executive"
                break
        
        if not title:
            for term in vp_level:
                if term in combined:
                    seniority = "vp"
                    decision_maker = True
                    title = "VP"
                    break
        
        if not title:
            for term in director:
                if term in combined:
                    seniority = "director"
                    title = "Director"
                    break
        
        if not title:
            for term in manager:
                if term in combined:
                    seniority = "manager"
                    title = "Manager"
                    break
        
        # Department detection
        depts = {
            "sales": ["sales", "revenue", "account"],
            "marketing": ["marketing", "growth", "demand"],
            "engineering": ["eng", "tech", "dev", "software"],
            "operations": ["ops", "operations", "process"],
            "finance": ["finance", "accounting", "money"],
            "hr": ["hr", "people", "talent", "human"]
        }
        
        for dept, keywords in depts.items():
            if any(kw in combined for kw in keywords):
                department = dept.title()
                break
        
        return {
            "title": title,
            "seniority": seniority,
            "department": department,
            "decision_maker": decision_maker
        }
    
    async def _get_ghl_history(self, contact_id: str) -> Dict[str, Any]:
        """Get contact history from GHL."""
        try:
            sys.path.insert(0, str(PROJECT_ROOT / "mcp-servers" / "ghl-mcp"))
            from server import AsyncGHLClient
            
            client = AsyncGHLClient()
            contact = await client.get_contact(contact_id=contact_id)
            await client.close()
            
            return {
                "interactions": contact.get("notes", []),
                "tags": contact.get("tags", [])
            }
        except Exception as e:
            logger.warning(f"Failed to get GHL history: {e}")
        
        return {"interactions": [], "tags": []}
    
    async def _research_linkedin(self, linkedin_url: str) -> Dict[str, Any]:
        """Research LinkedIn profile (mock)."""
        # In production, this would use LinkedIn scraping or API
        return {
            "background": "Experienced professional with 10+ years in the industry.",
            "interests": ["AI/ML", "Sales Automation", "Revenue Operations"]
        }
    
    def _infer_communication_style(self, intel: AttendeeIntel) -> str:
        """Infer preferred communication style."""
        if intel.seniority in ["c-level", "vp"]:
            return "executive_summary"  # Concise, ROI-focused
        elif intel.department == "Engineering":
            return "technical_details"  # Data-driven, feature-focused
        elif intel.department in ["Sales", "Marketing"]:
            return "results_focused"  # Metrics, outcomes
        else:
            return "balanced"  # Mix of details and outcomes
    
    def _calculate_attendee_confidence(self, intel: AttendeeIntel) -> float:
        """Calculate confidence score for attendee intel."""
        score = 0.3  # Base for having name/email
        
        if intel.title:
            score += 0.15
        if intel.linkedin_url:
            score += 0.15
        if intel.past_interactions:
            score += 0.2
        if intel.background:
            score += 0.1
        if intel.seniority != "unknown":
            score += 0.1
        
        return min(1.0, score)
    
    # =========================================================================
    # OBJECTION PREDICTION
    # =========================================================================
    
    async def predict_objections(
        self,
        company: CompanyIntel,
        attendee: AttendeeIntel,
        meeting_type: str
    ) -> List[ObjectionPrediction]:
        """
        Predict likely objections based on company/attendee intel.
        """
        objections = []
        
        # Base objection likelihood by meeting type
        base_likelihood = {
            "discovery": 0.3,
            "demo": 0.4,
            "follow_up": 0.5,
            "negotiation": 0.6
        }.get(meeting_type.lower(), 0.4)
        
        # Check for pricing objection
        if company.company_size and "small" in company.company_size.lower():
            objections.append(ObjectionPrediction(
                objection_type="pricing",
                likelihood=base_likelihood + 0.2,
                objection_text="Your solution seems expensive for a company our size.",
                recommended_response=self._objection_patterns["pricing"]["response_template"],
                evidence="Small company size detected"
            ))
        
        # Check for competitor objection based on tech stack
        competitor_techs = ["Salesforce", "HubSpot", "Outreach", "SalesLoft"]
        if any(tech in (company.tech_stack or []) for tech in competitor_techs):
            objections.append(ObjectionPrediction(
                objection_type="competitor",
                likelihood=base_likelihood + 0.25,
                objection_text="We're already using [competitor] for this.",
                recommended_response=self._objection_patterns["competitor"]["response_template"],
                evidence=f"Tech stack includes: {', '.join(company.tech_stack[:3])}"
            ))
        
        # Check for authority objection
        if not attendee.decision_maker:
            objections.append(ObjectionPrediction(
                objection_type="authority",
                likelihood=base_likelihood + 0.15,
                objection_text="I'll need to check with my manager/team.",
                recommended_response=self._objection_patterns["authority"]["response_template"],
                evidence=f"Attendee seniority: {attendee.seniority}"
            ))
        
        # Check for timing based on recent news
        if company.recent_news:
            growth_news = any("growth" in n.get("title", "").lower() for n in company.recent_news)
            if growth_news:
                objections.append(ObjectionPrediction(
                    objection_type="timing",
                    likelihood=base_likelihood - 0.1,  # Lower if growing
                    objection_text="We're too busy growing right now.",
                    recommended_response="That growth is exactly why now is the right time. Let me show you how we can scale with you...",
                    evidence="Recent growth-related news found"
                ))
        
        # Sort by likelihood
        objections.sort(key=lambda x: x.likelihood, reverse=True)
        
        return objections[:4]  # Top 4 objections
    
    # =========================================================================
    # TALKING POINTS
    # =========================================================================
    
    async def generate_talking_points(
        self,
        company: CompanyIntel,
        attendee: AttendeeIntel,
        meeting_type: str
    ) -> List[TalkingPoint]:
        """
        Generate personalized talking points for the meeting.
        """
        talking_points = []
        priority = 1
        
        # 1. Opening hook based on recent news
        if company.recent_news:
            news = company.recent_news[0]
            talking_points.append(TalkingPoint(
                topic="Opening Hook",
                key_message=f"I saw {company.company_name} in the news recently regarding {news['title'].lower()}. Congratulations!",
                supporting_evidence=news.get("summary", ""),
                priority=priority
            ))
            priority += 1
        
        # 2. Pain point alignment
        if company.pain_points:
            pain = company.pain_points[0]
            talking_points.append(TalkingPoint(
                topic="Pain Point",
                key_message=f"Companies in your space often struggle with {pain.lower()}. Is that something you're experiencing?",
                supporting_evidence=f"Common industry challenge",
                priority=priority
            ))
            priority += 1
        
        # 3. Tech stack integration
        if company.tech_stack:
            talking_points.append(TalkingPoint(
                topic="Integration",
                key_message=f"I noticed you're using {company.tech_stack[0]}. We integrate seamlessly with that.",
                supporting_evidence=f"Detected tech: {', '.join(company.tech_stack[:3])}",
                priority=priority
            ))
            priority += 1
        
        # 4. Personalization based on attendee
        if attendee.seniority == "c-level":
            talking_points.append(TalkingPoint(
                topic="Executive ROI",
                key_message="At the executive level, you're probably most interested in the bottom-line impact. Our clients typically see 30% efficiency gains.",
                supporting_evidence="Tailored for executive audience",
                priority=priority
            ))
        elif attendee.department:
            talking_points.append(TalkingPoint(
                topic=f"{attendee.department} Focus",
                key_message=f"For your {attendee.department} function specifically, the key benefits are...",
                supporting_evidence=f"Department: {attendee.department}",
                priority=priority
            ))
        
        return talking_points[:MAX_TALKING_POINTS]
    
    # =========================================================================
    # MEETING BRIEF GENERATION
    # =========================================================================
    
    async def generate_meeting_brief(
        self,
        meeting_id: str,
        meeting_time: str,
        company_name: str,
        attendee_emails: List[str],
        attendee_names: Optional[List[str]] = None,
        meeting_type: str = "discovery",
        company_website: Optional[str] = None,
        ghl_contact_ids: Optional[List[str]] = None
    ) -> MeetingBrief:
        """
        Generate a complete meeting brief.
        
        Args:
            meeting_id: Unique meeting identifier
            meeting_time: Meeting start time (ISO)
            company_name: Company name
            attendee_emails: List of attendee emails
            attendee_names: List of attendee names (parallel to emails)
            meeting_type: Type of meeting (discovery, demo, etc.)
            company_website: Company website URL
            ghl_contact_ids: GHL contact IDs (parallel to emails)
        
        Returns:
            Complete MeetingBrief
        """
        brief_id = self._generate_id("BRF")
        logger.info(f"Generating meeting brief {brief_id} for {company_name}")
        
        # Initialize brief
        brief = MeetingBrief(
            brief_id=brief_id,
            meeting_id=meeting_id,
            meeting_time=meeting_time,
            meeting_type=meeting_type,
            status=BriefStatus.RESEARCHING
        )
        
        # 1. Research company
        company_intel = await self.research_company(
            company_name=company_name,
            company_website=company_website
        )
        brief.company = company_intel
        
        # 2. Research attendees
        attendee_names = attendee_names or [e.split("@")[0] for e in attendee_emails]
        ghl_contact_ids = ghl_contact_ids or [None] * len(attendee_emails)
        
        for email, name, ghl_id in zip(attendee_emails, attendee_names, ghl_contact_ids):
            attendee_intel = await self.research_attendee(
                email=email,
                name=name,
                company=company_name,
                ghl_contact_id=ghl_id
            )
            brief.attendees.append(attendee_intel)
            
            # Set primary contact (first decision maker or first attendee)
            if attendee_intel.decision_maker and not brief.primary_contact:
                brief.primary_contact = email
        
        if not brief.primary_contact and brief.attendees:
            brief.primary_contact = brief.attendees[0].email
        
        # 3. Predict objections (using first attendee)
        if brief.attendees:
            objections = await self.predict_objections(
                company=company_intel,
                attendee=brief.attendees[0],
                meeting_type=meeting_type
            )
            brief.objections = objections
        
        # 4. Generate talking points
        if brief.attendees:
            talking_points = await self.generate_talking_points(
                company=company_intel,
                attendee=brief.attendees[0],
                meeting_type=meeting_type
            )
            brief.talking_points = talking_points
        
        # 5. Set meeting goal and next step
        brief.meeting_goal = self._suggest_meeting_goal(meeting_type, company_intel)
        brief.next_step = self._suggest_next_step(meeting_type)
        
        # 6. Generate summary
        brief.summary = self._generate_summary(brief)
        
        # 7. Calculate quality score
        brief.quality_score = self._calculate_brief_quality(brief)
        
        # 8. Set expiry (24 hours after meeting)
        meeting_dt = datetime.fromisoformat(meeting_time.replace('Z', '+00:00'))
        brief.expires_at = (meeting_dt + timedelta(hours=24)).isoformat()
        
        # Mark as ready
        brief.status = BriefStatus.READY
        
        # Save brief
        self._save_brief(brief)
        
        logger.info(f"Meeting brief {brief_id} ready (quality: {brief.quality_score:.0%})")
        
        return brief
    
    def _suggest_meeting_goal(self, meeting_type: str, company: CompanyIntel) -> str:
        """Suggest meeting goal based on type and company."""
        goals = {
            "discovery": "Understand their current challenges and identify if there's a fit.",
            "demo": "Show how our solution addresses their specific pain points.",
            "follow_up": "Address questions and move toward a decision.",
            "negotiation": "Finalize terms and close the deal."
        }
        return goals.get(meeting_type.lower(), "Build relationship and understand needs.")
    
    def _suggest_next_step(self, meeting_type: str) -> str:
        """Suggest next step based on meeting type."""
        next_steps = {
            "discovery": "Schedule a demo with key stakeholders",
            "demo": "Send proposal and schedule follow-up",
            "follow_up": "Get verbal commitment or identify blockers",
            "negotiation": "Finalize contract and get signature"
        }
        return next_steps.get(meeting_type.lower(), "Schedule follow-up meeting")
    
    def _generate_summary(self, brief: MeetingBrief) -> str:
        """Generate one-liner summary."""
        company_name = brief.company.company_name if brief.company else "Unknown"
        attendee_count = len(brief.attendees)
        primary = brief.primary_contact or "unknown"
        
        return f"{brief.meeting_type.title()} with {company_name} ({attendee_count} attendee{'s' if attendee_count != 1 else ''}). Primary: {primary}. Goal: {brief.meeting_goal}"
    
    def _calculate_brief_quality(self, brief: MeetingBrief) -> float:
        """Calculate quality score for the brief."""
        score = 0.0
        
        if brief.company and brief.company.confidence > 0.5:
            score += 0.25
        if brief.attendees and any(a.confidence > 0.5 for a in brief.attendees):
            score += 0.25
        if brief.talking_points:
            score += 0.2
        if brief.objections:
            score += 0.15
        if brief.meeting_goal:
            score += 0.1
        if brief.next_step:
            score += 0.05
        
        return min(1.0, score)
    
    def _save_brief(self, brief: MeetingBrief):
        """Save brief to disk."""
        brief_file = self.briefs_dir / f"{brief.brief_id}.json"
        
        # Convert to dict (handle nested dataclasses)
        brief_dict = asdict(brief)
        brief_dict["status"] = brief.status.value
        if brief.company:
            brief_dict["company"] = asdict(brief.company)
        if brief.attendees:
            brief_dict["attendees"] = [asdict(a) for a in brief.attendees]
        if brief.talking_points:
            brief_dict["talking_points"] = [asdict(t) for t in brief.talking_points]
        if brief.objections:
            brief_dict["objections"] = [asdict(o) for o in brief.objections]
        
        brief_file.write_text(json.dumps(brief_dict, indent=2))
        logger.info(f"Brief saved: {brief_file}")
    
    def get_brief(self, brief_id: str) -> Optional[MeetingBrief]:
        """Load a brief by ID."""
        brief_file = self.briefs_dir / f"{brief_id}.json"
        if not brief_file.exists():
            return None
        
        try:
            data = json.loads(brief_file.read_text())
            # Reconstruct nested objects
            data["status"] = BriefStatus(data["status"])
            if data.get("company"):
                data["company"] = CompanyIntel(**data["company"])
            if data.get("attendees"):
                data["attendees"] = [AttendeeIntel(**a) for a in data["attendees"]]
            if data.get("talking_points"):
                data["talking_points"] = [TalkingPoint(**t) for t in data["talking_points"]]
            if data.get("objections"):
                data["objections"] = [ObjectionPrediction(**o) for o in data["objections"]]
            return MeetingBrief(**data)
        except Exception as e:
            logger.error(f"Failed to load brief {brief_id}: {e}")
            return None
    
    # =========================================================================
    # QUEUE PROCESSING
    # =========================================================================
    
    async def process_research_queue(self) -> List[str]:
        """
        Process pending research tasks from .hive-mind/researcher/queue/
        
        Returns list of processed task IDs.
        """
        processed = []
        
        for task_file in self.queue_dir.glob("*.json"):
            try:
                task = json.loads(task_file.read_text())
                
                if task.get("status") == "pending":
                    logger.info(f"Processing research task: {task['task_id']}")
                    
                    # Generate meeting brief
                    brief = await self.generate_meeting_brief(
                        meeting_id=task.get("task_id"),
                        meeting_time=task.get("meeting_time", datetime.now(timezone.utc).isoformat()),
                        company_name=task.get("prospect_company", "Unknown"),
                        attendee_emails=[task.get("prospect_email")],
                        attendee_names=[task.get("prospect_name")],
                        meeting_type=task.get("meeting_type", "discovery"),
                        ghl_contact_ids=[task.get("ghl_contact_id")]
                    )
                    
                    # Update task status
                    task["status"] = "completed"
                    task["brief_id"] = brief.brief_id
                    task["completed_at"] = datetime.now(timezone.utc).isoformat()
                    task_file.write_text(json.dumps(task, indent=2))
                    
                    processed.append(task["task_id"])
                    
            except Exception as e:
                logger.error(f"Failed to process task {task_file}: {e}")
        
        return processed
    
    # =========================================================================
    # CACHING
    # =========================================================================
    
    def _get_cached_intel(self, key: str, intel_type: str) -> Optional[Dict]:
        """Get cached intel if not expired."""
        cache_file = self.cache_dir / f"{intel_type}_{key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            data = json.loads(cache_file.read_text())
            cached_at = datetime.fromisoformat(data.get("researched_at", "2000-01-01"))
            
            # Check if expired
            if datetime.now(timezone.utc) - cached_at.replace(tzinfo=timezone.utc) > timedelta(days=CACHE_TTL_DAYS):
                cache_file.unlink()  # Delete expired cache
                return None
            
            return data
        except Exception:
            return None
    
    def _cache_intel(self, key: str, intel_type: str, data: Dict):
        """Cache intel for future use."""
        cache_file = self.cache_dir / f"{intel_type}_{key}.json"
        cache_file.write_text(json.dumps(data, indent=2))


# =============================================================================
# CLI INTERFACE
# =============================================================================

async def main():
    """Demo the Researcher Agent."""
    print("\n" + "=" * 60)
    print("RESEARCHER AGENT - Beta Swarm")
    print("=" * 60)
    
    researcher = ResearcherAgent()
    
    # Demo: Research company
    print("\n[1. Company Research]")
    company = await researcher.research_company(
        company_name="Acme Technology Corp",
        company_website="https://acmetech.com"
    )
    print(f"  Company: {company.company_name}")
    print(f"  Industry: {company.industry}")
    print(f"  Tech Stack: {', '.join(company.tech_stack[:3])}")
    print(f"  Confidence: {company.confidence:.0%}")
    
    # Demo: Research attendee
    print("\n[2. Attendee Research]")
    attendee = await researcher.research_attendee(
        email="john.smith@acmetech.com",
        name="John Smith",
        company="Acme Technology Corp"
    )
    print(f"  Name: {attendee.name}")
    print(f"  Title: {attendee.title or 'Unknown'}")
    print(f"  Seniority: {attendee.seniority}")
    print(f"  Decision Maker: {attendee.decision_maker}")
    
    # Demo: Generate meeting brief
    print("\n[3. Generating Meeting Brief]")
    brief = await researcher.generate_meeting_brief(
        meeting_id="MTG-001",
        meeting_time=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        company_name="Acme Technology Corp",
        attendee_emails=["john.smith@acmetech.com"],
        attendee_names=["John Smith"],
        meeting_type="discovery"
    )
    print(f"  Brief ID: {brief.brief_id}")
    print(f"  Status: {brief.status.value}")
    print(f"  Quality: {brief.quality_score:.0%}")
    print(f"  Summary: {brief.summary}")
    
    if brief.talking_points:
        print("\n  Talking Points:")
        for tp in brief.talking_points[:3]:
            print(f"    - {tp.topic}: {tp.key_message[:50]}...")
    
    if brief.objections:
        print("\n  Predicted Objections:")
        for obj in brief.objections[:2]:
            print(f"    - {obj.objection_type} ({obj.likelihood:.0%}): {obj.objection_text[:40]}...")
    
    print("\n" + "=" * 60)
    print("Demo complete!")


if __name__ == "__main__":
    asyncio.run(main())
