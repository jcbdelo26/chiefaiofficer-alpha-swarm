#!/usr/bin/env python3
"""
Segmentor Agent - Lead Classification & ICP Scoring
===================================================
Classifies leads by source, calculates ICP scores, and assigns tiers.

Features:
- ICP scoring based on company size, title, industry, tech stack, intent signals
- Tier assignment: tier_1 (>=80), tier_2 (>=60), tier_3 (>=40), tier_4 (<40)
- Campaign routing by tier + source_type
- Self-annealing integration for threshold learning
- Batch processing with progress tracking

Usage:
    python execution/segmentor_classify.py --input leads.json --output segmented.json
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.progress import Progress

import platform
import os
# Only replace stdout/stderr on Windows when not running in pytest
# This avoids breaking pytest's capture mechanism
if platform.system() == "Windows" and "PYTEST_CURRENT_TEST" not in os.environ:
    import sys
    import io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    from core.retry import retry, schedule_retry
except ImportError:
    def schedule_retry(*args, **kwargs): pass

try:
    from core.alerts import send_warning
except ImportError:
    def send_warning(*args, **kwargs): pass

try:
    from core.event_log import log_event, EventType
except ImportError:
    class EventType:
        LEAD_SEGMENTED = "lead_segmented"
    def log_event(*args, **kwargs): pass

try:
    from core.context import estimate_tokens, get_context_zone, ContextZone
except ImportError:
    class ContextZone:
        SMART = "smart"
        CAUTION = "caution"
        DUMB = "dumb"
        CRITICAL = "critical"
    def estimate_tokens(data): return len(json.dumps(data)) // 4
    def get_context_zone(tokens):
        if tokens < 50000: return ContextZone.SMART
        elif tokens < 100000: return ContextZone.CAUTION
        elif tokens < 150000: return ContextZone.DUMB
        return ContextZone.CRITICAL

try:
    from core.self_annealing import SelfAnnealingEngine, OutcomeType
    ANNEALING_AVAILABLE = True
except ImportError:
    ANNEALING_AVAILABLE = False
    SelfAnnealingEngine = None

console = Console()


class ICPTier(Enum):
    """ICP tier classification based on score thresholds."""
    TIER_1 = "tier_1"  # >= 80
    TIER_2 = "tier_2"  # >= 60
    TIER_3 = "tier_3"  # >= 40
    TIER_4 = "tier_4"  # < 40


class SourceType(Enum):
    """Lead source types for campaign routing."""
    COMPETITOR_FOLLOWER = "competitor_follower"
    EVENT_ATTENDEE = "event_attendee"
    GROUP_MEMBER = "group_member"
    POST_COMMENTER = "post_commenter"
    POST_LIKER = "post_liker"
    WEBSITE_VISITOR = "website_visitor"
    CONTENT_DOWNLOADER = "content_downloader"
    WEBINAR_REGISTRANT = "webinar_registrant"
    DEMO_REQUESTER = "demo_requester"


@dataclass
class SegmentedLead:
    """Lead with segmentation and scoring."""
    lead_id: str
    linkedin_url: str
    name: str
    title: str
    company: str
    
    # Scores
    icp_score: int
    icp_tier: str
    intent_score: int
    
    # Segmentation
    source_type: str
    source_name: str
    segment_tags: List[str] = field(default_factory=list)
    
    # ICP breakdown
    score_breakdown: Dict[str, int] = field(default_factory=dict)
    scoring_reasons: List[str] = field(default_factory=list)  # Human-readable "why this score"

    # Flags
    disqualification_reason: Optional[str] = None
    needs_review: bool = False
    
    # Enrichment data
    email: Optional[str] = None
    company_size: int = 0
    industry: str = ""
    
    # Campaign recommendation
    recommended_campaign: str = ""
    personalization_hooks: List[str] = field(default_factory=list)
    
    segmented_at: str = ""
    
    # Preserve original lead data for downstream personalization
    original_lead: Dict[str, Any] = field(default_factory=dict)


class LeadSegmentor:
    """
    Classify and score leads according to ICP criteria.
    
    Scoring breakdown (100 points max):
    - Company size: 20 points (51-500 employees = highest)
    - Title seniority: 25 points (VP/C-level = highest)
    - Industry fit: 20 points (B2B SaaS/Technology = highest)
    - Technology stack: 15 points (using CRM = positive signal)
    - Intent signals: 20 points (website visits, content downloads)
    
    Tier thresholds:
    - tier_1: ICP score >= 80
    - tier_2: ICP score >= 60
    - tier_3: ICP score >= 40
    - tier_4: ICP score < 40
    """
    
    # Title keywords for scoring (seniority tiers)
    C_LEVEL_TITLES = ['ceo', 'cfo', 'coo', 'cto', 'cmo', 'cro', 'chief', 'founder', 'co-founder']
    VP_TITLES = ['vp', 'vice president', 'svp', 'evp', 'head of']
    DIRECTOR_TITLES = ['director', 'sr director', 'senior director']
    MANAGER_TITLES = ['manager', 'lead', 'senior manager', 'principal']
    
    # Industry keywords (fit tiers)
    TIER1_INDUSTRIES = ['saas', 'software as a service', 'b2b software', 'enterprise software']
    TIER2_INDUSTRIES = ['technology', 'tech', 'information technology', 'it services']
    TIER3_INDUSTRIES = ['professional services', 'consulting', 'fintech', 'healthtech']
    
    # Technology stack signals (CRM/sales tools = positive)
    CRM_TECHNOLOGIES = ['salesforce', 'hubspot', 'pipedrive', 'zoho crm', 'dynamics 365', 'freshsales']
    SALES_TECH = ['gong', 'clari', 'chorus', 'outreach', 'salesloft', 'apollo', 'zoominfo']
    MARKETING_TECH = ['marketo', 'pardot', 'eloqua', 'mailchimp', 'klaviyo', 'intercom']
    
    # Tier thresholds (adjustable via self-annealing)
    DEFAULT_TIER_THRESHOLDS = {
        'tier_1': 80,
        'tier_2': 60,
        'tier_3': 40,
    }
    
    def __init__(self, use_annealing: bool = True):
        self.segmented: List[SegmentedLead] = []
        self.use_annealing = use_annealing and ANNEALING_AVAILABLE
        self.annealing_engine = None
        self.tier_thresholds = self.DEFAULT_TIER_THRESHOLDS.copy()
        
        if self.use_annealing:
            try:
                self.annealing_engine = SelfAnnealingEngine()
                self._load_learned_thresholds()
            except Exception as e:
                console.print(f"[yellow]Warning: Self-annealing unavailable: {e}[/yellow]")
                self.use_annealing = False
    
    def _load_learned_thresholds(self):
        """Load tier thresholds learned from self-annealing."""
        if not self.annealing_engine:
            return
        
        state = self.annealing_engine.get_annealing_status()
        q_table = getattr(self.annealing_engine, 'q_table', {})
        
        for tier in ['tier_1', 'tier_2', 'tier_3']:
            key = f"threshold_{tier}"
            if key in q_table and q_table[key]:
                best_threshold = max(q_table[key].items(), key=lambda x: x[1])
                try:
                    self.tier_thresholds[tier] = int(best_threshold[0])
                except (ValueError, TypeError):
                    pass
    
    def calculate_icp_score(self, lead: Dict[str, Any]) -> Tuple[int, Dict[str, int], Optional[str]]:
        """
        Calculate ICP score based on comprehensive criteria.
        
        Scoring breakdown (100 points max):
        - Company size: 20 points (51-500 employees = highest)
        - Title seniority: 25 points (VP/C-level = highest)
        - Industry fit: 20 points (B2B SaaS/Technology = highest)
        - Technology stack: 15 points (using CRM = positive signal)
        - Intent signals: 20 points (website visits, content downloads)
        
        Returns: (score, breakdown, disqualification_reason, scoring_reasons)
        """
        score = 0
        breakdown = {}
        reasons = []
        dq_reason = None

        # === COMPANY SIZE (20 points max) ===
        employee_count = lead.get("company", {}).get("employee_count") or 0
        if isinstance(employee_count, str):
            try:
                employee_count = int(employee_count.replace(',', '').replace('+', ''))
            except ValueError:
                employee_count = 0

        if employee_count < 10:
            dq_reason = "Company too small (<10 employees)"
            reasons.append(f"DISQUALIFIED: Company has <10 employees ({employee_count})")
        elif 51 <= employee_count <= 500:
            breakdown["company_size"] = 20
            score += 20
            reasons.append(f"+20: Company size {employee_count} employees (ideal 51-500 sweet spot)")
        elif 501 <= employee_count <= 1000:
            breakdown["company_size"] = 15
            score += 15
            reasons.append(f"+15: Company size {employee_count} employees (mid-market)")
        elif 20 <= employee_count <= 50:
            breakdown["company_size"] = 12
            score += 12
            reasons.append(f"+12: Company size {employee_count} employees (growth-stage)")
        elif 10 <= employee_count <= 19:
            breakdown["company_size"] = 5
            score += 5
            reasons.append(f"+5: Company size {employee_count} employees (early-stage)")
        elif employee_count > 1000:
            breakdown["company_size"] = 10
            score += 10
            reasons.append(f"+10: Company size {employee_count} employees (enterprise — slower sales cycle)")

        # === TITLE SENIORITY (25 points max) ===
        title = (lead.get("title") or "").lower()
        raw_title = lead.get("title") or "Unknown"
        if any(kw in title for kw in self.C_LEVEL_TITLES):
            breakdown["title_seniority"] = 25
            score += 25
            reasons.append(f"+25: C-Level/Founder title \"{raw_title}\" (budget owner)")
        elif any(kw in title for kw in self.VP_TITLES):
            breakdown["title_seniority"] = 22
            score += 22
            reasons.append(f"+22: VP-level title \"{raw_title}\" (budget influencer)")
        elif any(kw in title for kw in self.DIRECTOR_TITLES):
            breakdown["title_seniority"] = 15
            score += 15
            reasons.append(f"+15: Director-level title \"{raw_title}\" (tactical decision-maker)")
        elif any(kw in title for kw in self.MANAGER_TITLES):
            breakdown["title_seniority"] = 8
            score += 8
            reasons.append(f"+8: Manager-level title \"{raw_title}\" (operational)")
        else:
            breakdown["title_seniority"] = 0
            reasons.append(f"+0: Title \"{raw_title}\" does not match decision-maker patterns")

        # === INDUSTRY FIT (20 points max) ===
        industry = (lead.get("company", {}).get("industry") or "").lower()
        raw_industry = lead.get("company", {}).get("industry") or "Unknown"
        if any(kw in industry for kw in self.TIER1_INDUSTRIES):
            breakdown["industry_fit"] = 20
            score += 20
            reasons.append(f"+20: Industry \"{raw_industry}\" is core ICP (B2B SaaS/Software)")
        elif any(kw in industry for kw in self.TIER2_INDUSTRIES):
            breakdown["industry_fit"] = 15
            score += 15
            reasons.append(f"+15: Industry \"{raw_industry}\" is adjacent ICP (Tech/IT)")
        elif any(kw in industry for kw in self.TIER3_INDUSTRIES):
            breakdown["industry_fit"] = 10
            score += 10
            reasons.append(f"+10: Industry \"{raw_industry}\" is secondary ICP")
        else:
            breakdown["industry_fit"] = 0
            if raw_industry != "Unknown":
                reasons.append(f"+0: Industry \"{raw_industry}\" outside ICP target industries")
            else:
                reasons.append("+0: Industry unknown — no data from enrichment")
        
        # === TECHNOLOGY STACK (15 points max) ===
        technologies = lead.get("company", {}).get("technologies", [])
        if isinstance(technologies, str):
            technologies = [t.strip().lower() for t in technologies.split(',')]
        else:
            technologies = [str(t).lower() for t in technologies]
        
        tech_score = 0
        tech_signals = []
        
        for tech in technologies:
            if any(crm.lower() in tech for crm in self.CRM_TECHNOLOGIES):
                tech_score += 8
                tech_signals.append("crm_user")
            if any(st.lower() in tech for st in self.SALES_TECH):
                tech_score += 5
                tech_signals.append("sales_tech")
            if any(mt.lower() in tech for mt in self.MARKETING_TECH):
                tech_score += 3
                tech_signals.append("marketing_tech")
        
        breakdown["tech_stack"] = min(tech_score, 15)
        score += min(tech_score, 15)
        if tech_signals:
            breakdown["tech_signals"] = list(set(tech_signals))
            unique_signals = list(set(tech_signals))
            reasons.append(f"+{min(tech_score, 15)}: Tech stack signals — {', '.join(unique_signals)} (sales maturity indicator)")
        else:
            reasons.append("+0: No CRM/sales/marketing tech detected in stack")

        # === INTENT SIGNALS (20 points max) ===
        intent_data = lead.get("intent", {})
        intent_score = 0
        intent_signals = []
        intent_reasons = []

        website_visits = intent_data.get("website_visits", 0)
        if website_visits >= 5:
            intent_score += 8
            intent_signals.append("high_web_engagement")
            intent_reasons.append(f"{website_visits} website visits (high engagement)")
        elif website_visits >= 2:
            intent_score += 4
            intent_signals.append("web_engagement")
            intent_reasons.append(f"{website_visits} website visits")

        content_downloads = intent_data.get("content_downloads", 0)
        if content_downloads >= 3:
            intent_score += 8
            intent_signals.append("content_engaged")
            intent_reasons.append(f"{content_downloads} content downloads (highly engaged)")
        elif content_downloads >= 1:
            intent_score += 4
            intent_signals.append("content_downloaded")
            intent_reasons.append(f"{content_downloads} content download(s)")

        pricing_page = intent_data.get("pricing_page_visits", 0)
        if pricing_page >= 1:
            intent_score += 6
            intent_signals.append("pricing_interest")
            intent_reasons.append("visited pricing page (strong buy signal)")

        demo_request = intent_data.get("demo_requested", False)
        if demo_request:
            intent_score += 10
            intent_signals.append("demo_requested")
            intent_reasons.append("requested a demo (strongest buy signal)")

        source_type = lead.get("source_type", "")
        if source_type == "website_visitor":
            intent_score += 4
            intent_signals.append("website_source")
        elif source_type == "content_downloader":
            intent_score += 6
            intent_signals.append("content_source")
        elif source_type == "demo_requester":
            intent_score += 10
            intent_signals.append("demo_source")
        elif source_type == "webinar_registrant":
            intent_score += 5
            intent_signals.append("webinar_source")

        capped_intent = min(intent_score, 20)
        breakdown["intent_signals"] = capped_intent
        score += capped_intent
        if intent_signals:
            breakdown["intent_types"] = intent_signals
        if intent_reasons:
            reasons.append(f"+{capped_intent}: Intent signals — {'; '.join(intent_reasons)}")
        else:
            reasons.append("+0: No behavioral intent signals detected")
        
        # === SOURCE ENGAGEMENT BONUS (implicit in intent) ===
        if source_type == "post_commenter":
            score += 5
            breakdown["engagement_bonus"] = 5
            reasons.append("+5: Social engagement bonus (commented on post)")
        elif source_type == "event_attendee":
            score += 4
            breakdown["engagement_bonus"] = 4
            reasons.append("+4: Social engagement bonus (event attendee)")
        elif source_type == "competitor_follower":
            score += 3
            breakdown["engagement_bonus"] = 3
            reasons.append("+3: Social engagement bonus (competitor follower — displacement opportunity)")

        final_score = min(score, 100)
        reasons.append(f"= {final_score}/100 total ICP score")

        return final_score, breakdown, dq_reason, reasons
    
    def get_tier(self, score: int) -> str:
        """
        Get ICP tier from score using configurable thresholds.
        
        Default thresholds:
        - tier_1: >= 80
        - tier_2: >= 60
        - tier_3: >= 40
        - tier_4: < 40
        
        Thresholds can be adjusted via self-annealing based on conversion data.
        """
        if score >= self.tier_thresholds['tier_1']:
            return ICPTier.TIER_1.value
        elif score >= self.tier_thresholds['tier_2']:
            return ICPTier.TIER_2.value
        elif score >= self.tier_thresholds['tier_3']:
            return ICPTier.TIER_3.value
        else:
            return ICPTier.TIER_4.value
    
    def generate_segment_tags(self, lead: Dict[str, Any], tier: str) -> List[str]:
        """Generate segment tags for the lead."""
        tags = []
        
        # Tier tag
        tags.append(tier)
        
        # Source tag
        source_type = lead.get("source_type", "unknown")
        tags.append(source_type)
        
        # Competitor tag
        source_name = lead.get("source_name", "")
        if source_name:
            tags.append(f"from_{source_name.lower().replace(' ', '_')}")
        
        # Industry tag
        industry = lead.get("company", {}).get("industry", "")
        if industry:
            tags.append(f"industry_{industry.lower().replace(' ', '_')[:20]}")
        
        # Intent tag
        intent_score = lead.get("intent", {}).get("intent_score", 0)
        if intent_score >= 80:
            tags.append("hot_intent")
        elif intent_score >= 60:
            tags.append("warm_intent")
        elif intent_score >= 40:
            tags.append("cool_intent")
        
        # Email tag
        if lead.get("contact", {}).get("work_email"):
            tags.append("has_email")
        
        return tags
    
    def recommend_campaign(self, lead: Dict[str, Any], tier: str) -> str:
        """
        Recommend campaign type based on lead profile and tier.
        
        Campaign Routing Logic:
        - competitor_follower → competitor_displacement
        - event_attendee → event_followup
        - website_visitor → intent_based
        - content_downloader → content_nurture
        - demo_requester → sales_qualified (fast-track)
        - Default → nurture_sequence
        
        Tier modifies the campaign intensity:
        - tier_1: aggressive outreach
        - tier_2: standard sequences
        - tier_3/4: nurture/education focus
        """
        source_type = lead.get("source_type", "")
        source_name = lead.get("source_name", "").lower()
        intent_data = lead.get("intent", {})
        
        # === HIGH INTENT SOURCES (fast-track) ===
        if source_type == "demo_requester":
            return "sales_qualified_fasttrack"
        
        if intent_data.get("demo_requested"):
            return "sales_qualified_fasttrack"
        
        if intent_data.get("pricing_page_visits", 0) >= 2:
            return "high_intent_pricing"
        
        # === COMPETITOR DISPLACEMENT ===
        if source_type == "competitor_follower":
            if "gong" in source_name:
                return "gong_displacement"
            elif "clari" in source_name:
                return "clari_displacement"
            elif "chorus" in source_name:
                return "chorus_displacement"
            elif "outreach" in source_name:
                return "outreach_displacement"
            else:
                return "competitor_displacement"
        
        # === EVENT FOLLOW-UP ===
        if source_type == "event_attendee":
            return "event_followup"
        
        if source_type == "webinar_registrant":
            return "webinar_followup"
        
        # === INTENT-BASED (website visitors) ===
        if source_type == "website_visitor":
            if tier == ICPTier.TIER_1.value:
                return "intent_based_tier1"
            elif tier == ICPTier.TIER_2.value:
                return "intent_based_tier2"
            else:
                return "intent_based_nurture"
        
        # === CONTENT ENGAGEMENT ===
        if source_type == "content_downloader":
            if intent_data.get("content_downloads", 0) >= 3:
                return "content_engaged_sequence"
            return "content_nurture"
        
        # === SOCIAL ENGAGEMENT ===
        if source_type == "post_commenter":
            return "thought_leadership_response"
        
        if source_type == "group_member":
            return "community_outreach"
        
        if source_type == "post_liker":
            if tier in [ICPTier.TIER_1.value, ICPTier.TIER_2.value]:
                return "social_engagement_qualified"
            return "social_nurture"
        
        # === DEFAULT BY TIER ===
        if tier == ICPTier.TIER_1.value:
            return "tier1_priority_outreach"
        elif tier == ICPTier.TIER_2.value:
            return "tier2_standard_sequence"
        elif tier == ICPTier.TIER_3.value:
            return "nurture_sequence"
        else:
            return "nurture_sequence"
    
    def generate_personalization_hooks(self, lead: Dict[str, Any]) -> List[str]:
        """Generate personalization hooks for campaigns."""
        hooks = []
        
        # Source-based hooks
        source_type = lead.get("source_type", "")
        source_name = lead.get("source_name", "")
        
        if source_type == "post_commenter":
            hooks.append(f"Reference their comment on LinkedIn")
        elif source_type == "event_attendee":
            hooks.append(f"Mention {source_name} event they attended")
        elif source_type == "competitor_follower":
            hooks.append(f"Reference their interest in {source_name}")
        elif source_type == "group_member":
            hooks.append(f"Connect as fellow {source_name} member")
        
        # Company-based hooks
        company_data = lead.get("company", {})
        if company_data.get("technologies"):
            hooks.append("Reference their tech stack")
        if company_data.get("revenue_estimate", 0) > 10_000_000:
            hooks.append("Mention growth stage messaging")
        
        # Title-based hooks
        title = lead.get("title", "").lower()
        if "cro" in title or "chief" in title:
            hooks.append("Use executive-level messaging")
        elif "director" in title:
            hooks.append("Focus on operational value")
        
        return hooks
    
    def segment_lead(self, lead: Dict[str, Any]) -> SegmentedLead:
        """Segment and score a single lead."""
        
        # Calculate ICP score
        icp_score, breakdown, dq_reason, scoring_reasons = self.calculate_icp_score(lead)
        tier = self.get_tier(icp_score)
        
        # Get intent score from enrichment
        intent_score = lead.get("intent", {}).get("intent_score", 0)
        
        # Generate segment tags
        tags = self.generate_segment_tags(lead, tier)
        
        # Recommend campaign
        campaign = self.recommend_campaign(lead, tier)
        
        # Generate personalization hooks
        hooks = self.generate_personalization_hooks(lead)
        
        # Get original_lead from enriched data or create from current data
        original_lead = lead.get("original_lead", {})
        
        return SegmentedLead(
            lead_id=lead.get("lead_id", ""),
            linkedin_url=lead.get("linkedin_url", ""),
            name=original_lead.get("first_name", "") + " " + original_lead.get("last_name", "") if original_lead else lead.get("name", ""),
            title=original_lead.get("title", "") if original_lead else lead.get("title", ""),
            company=lead.get("company", {}).get("name", "") if isinstance(lead.get("company"), dict) else lead.get("company", ""),
            icp_score=icp_score,
            icp_tier=tier,
            intent_score=intent_score,
            source_type=lead.get("source_type", ""),
            source_name=lead.get("source_name", ""),
            segment_tags=tags,
            score_breakdown=breakdown,
            scoring_reasons=scoring_reasons,
            disqualification_reason=dq_reason,
            needs_review=icp_score >= 70 and icp_score <= 85,  # Review borderline Tier 1
            email=(lead.get("contact", {}).get("work_email")
                  or lead.get("contact", {}).get("verified_email")
                  or lead.get("email")),
            company_size=lead.get("company", {}).get("employee_count", 0),
            industry=lead.get("company", {}).get("industry", ""),
            recommended_campaign=campaign,
            personalization_hooks=hooks,
            segmented_at=datetime.now(timezone.utc).isoformat(),
            original_lead=original_lead
        )
    
    def segment_batch(self, leads_file: Path) -> List[SegmentedLead]:
        """
        Segment a batch of enriched leads.
        
        Includes context zone monitoring to warn when approaching Dumb Zone.
        """
        
        console.print(f"\n[bold blue]📊 SEGMENTOR: Classifying leads from {leads_file}[/bold blue]")
        
        with open(leads_file) as f:
            data = json.load(f)
        
        leads = data.get("leads", [])
        
        # === CONTEXT ZONE MONITORING ===
        tokens = estimate_tokens(leads)
        zone = get_context_zone(tokens)
        
        if zone == ContextZone.SMART:
            console.print(f"[dim]Context zone: SMART ({tokens:,} tokens) - optimal processing[/dim]")
        elif zone == ContextZone.CAUTION:
            console.print(f"[yellow]⚠️ Warning: Operating in CAUTION zone ({tokens:,} tokens)[/yellow]")
            console.print(f"[dim]   Performance may degrade. Consider smaller batches.[/dim]")
        elif zone == ContextZone.DUMB:
            console.print(f"[red]⚠️ Warning: Operating in DUMB zone ({tokens:,} tokens)[/red]")
            console.print(f"[yellow]   Expect degraded performance. Strongly recommend smaller batches.[/yellow]")
        elif zone == ContextZone.CRITICAL:
            console.print(f"[bold red]🚨 CRITICAL: Operating in CRITICAL zone ({tokens:,} tokens)[/bold red]")
            console.print(f"[red]   High risk of failures. Split this batch immediately.[/red]")
        
        segmented = []
        failed_count = 0
        batch_start = datetime.now(timezone.utc)
        
        with Progress() as progress:
            task = progress.add_task("Segmenting leads...", total=len(leads))
            
            for idx, lead in enumerate(leads):
                try:
                    result = self.segment_lead(lead)
                    segmented.append(result)
                    
                    log_event(EventType.LEAD_SEGMENTED, {
                        "lead_id": result.lead_id,
                        "icp_tier": result.icp_tier,
                        "icp_score": result.icp_score,
                        "recommended_campaign": result.recommended_campaign
                    })
                    
                    if self.annealing_engine:
                        self.annealing_engine.learn_from_outcome(
                            workflow=f"segmentation_{result.lead_id}",
                            outcome={
                                "action": "segment",
                                "state": {
                                    "icp_tier": result.icp_tier,
                                    "source_type": result.source_type,
                                    "icp_score": result.icp_score
                                },
                                "campaign": result.recommended_campaign
                            },
                            success=True,
                            details={"score_breakdown": result.score_breakdown}
                        )
                        
                except Exception as e:
                    failed_count += 1
                    schedule_retry(
                        operation_name="segmentation",
                        payload={"lead": lead, "leads_file": str(leads_file)},
                        error=e,
                        policy_name="default",
                        metadata={"lead_id": lead.get("lead_id")}
                    )
                    console.print(f"[yellow]Failed to segment lead {lead.get('lead_id')}: {e}[/yellow]")
                
                progress.update(task, advance=1)
        
        batch_duration = (datetime.now(timezone.utc) - batch_start).total_seconds()
        
        if failed_count > 0:
            send_warning(
                "Segmentation Partially Failed",
                f"{failed_count} leads failed to segment and have been queued for retry.",
                {"total": len(leads), "failed": failed_count, "success": len(segmented)}
            )
        
        if self.annealing_engine:
            self.annealing_engine.save_state()
        
        console.print(f"[dim]Processed {len(segmented)} leads in {batch_duration:.2f}s ({len(segmented)/batch_duration:.1f} leads/sec)[/dim]")
        
        self.segmented = segmented
        return segmented
    
    def print_summary(self, segmented: List[SegmentedLead]):
        """Print segmentation summary."""
        
        # Calculate tier distribution
        tiers = {}
        for lead in segmented:
            tier = lead.icp_tier
            tiers[tier] = tiers.get(tier, 0) + 1
        
        # Calculate campaign distribution
        campaigns = {}
        for lead in segmented:
            campaign = lead.recommended_campaign
            campaigns[campaign] = campaigns.get(campaign, 0) + 1
        
        # Print summary table
        console.print("\n[bold]📊 Segmentation Summary[/bold]")
        
        tier_table = Table(title="ICP Tier Distribution")
        tier_table.add_column("Tier", style="cyan")
        tier_table.add_column("Count", style="green")
        tier_table.add_column("Percentage", style="yellow")
        
        total = len(segmented)
        for tier in [ICPTier.TIER_1.value, ICPTier.TIER_2.value, ICPTier.TIER_3.value, 
                     ICPTier.TIER_4.value]:
            count = tiers.get(tier, 0)
            pct = (count / total * 100) if total > 0 else 0
            tier_table.add_row(tier.upper(), str(count), f"{pct:.1f}%")
        
        console.print(tier_table)
        
        # Campaign recommendations
        campaign_table = Table(title="Campaign Recommendations")
        campaign_table.add_column("Campaign", style="cyan")
        campaign_table.add_column("Count", style="green")
        
        for campaign, count in sorted(campaigns.items(), key=lambda x: -x[1]):
            campaign_table.add_row(campaign, str(count))
        
        console.print(campaign_table)
        
        # Highlight needs review
        needs_review = [l for l in segmented if l.needs_review]
        if needs_review:
            console.print(f"\n[yellow]⚠️ {len(needs_review)} leads need manual review (borderline Tier 1)[/yellow]")
    
    def save_segmented(
        self, 
        segmented: List[SegmentedLead], 
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Save segmented leads to JSON file.
        
        Args:
            segmented: List of segmented leads
            output_path: Optional specific output file path. If None, generates timestamped file.
        
        Returns:
            Path to the saved file
        """
        if output_path is None:
            output_dir = Path(__file__).parent.parent / ".hive-mind" / "segmented"
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"segmented_{timestamp}.json"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        segmented_data = [asdict(s) for s in segmented]
        
        tier_counts = {}
        campaign_counts = {}
        for s in segmented:
            tier_counts[s.icp_tier] = tier_counts.get(s.icp_tier, 0) + 1
            campaign_counts[s.recommended_campaign] = campaign_counts.get(s.recommended_campaign, 0) + 1
        
        output_data = {
            "segmented_at": datetime.now(timezone.utc).isoformat(),
            "lead_count": len(segmented),
            "tier_distribution": tier_counts,
            "campaign_distribution": campaign_counts,
            "avg_icp_score": sum(s.icp_score for s in segmented) / len(segmented) if segmented else 0,
            "tier_thresholds": self.tier_thresholds,
            "annealing_enabled": self.use_annealing,
            "leads": segmented_data
        }
        
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        
        console.print(f"[green]✅ Saved segmented leads to {output_path}[/green]")
        
        return output_path


def print_test_metrics(segmented: List[SegmentedLead]) -> None:
    """Print detailed verification metrics for test mode."""
    console.print("\n[bold cyan]═══ Test Mode Verification Metrics ═══[/bold cyan]\n")
    
    tier_counts = {"tier_1": 0, "tier_2": 0, "tier_3": 0, "tier_4": 0}
    source_counts = {}
    campaign_counts = {}
    scores = []
    
    for lead in segmented:
        tier_counts[lead.icp_tier] = tier_counts.get(lead.icp_tier, 0) + 1
        source_counts[lead.source_type] = source_counts.get(lead.source_type, 0) + 1
        campaign_counts[lead.recommended_campaign] = campaign_counts.get(lead.recommended_campaign, 0) + 1
        scores.append(lead.icp_score)
    
    total = len(segmented)
    avg_score = sum(scores) / total if total else 0
    min_score = min(scores) if scores else 0
    max_score = max(scores) if scores else 0
    
    table = Table(title="Segmentation Accuracy Metrics", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Percentage", style="yellow")
    
    table.add_row("Total Leads Processed", str(total), "100%")
    table.add_row("Average ICP Score", f"{avg_score:.1f}", "-")
    table.add_row("Score Range", f"{min_score:.0f} - {max_score:.0f}", "-")
    table.add_row("", "", "")
    
    for tier, count in sorted(tier_counts.items()):
        pct = (count / total * 100) if total else 0
        table.add_row(f"  {tier}", str(count), f"{pct:.1f}%")
    
    table.add_row("", "", "")
    table.add_row("[bold]Source Distribution[/bold]", "", "")
    for source, count in sorted(source_counts.items()):
        pct = (count / total * 100) if total else 0
        table.add_row(f"  {source}", str(count), f"{pct:.1f}%")
    
    table.add_row("", "", "")
    table.add_row("[bold]Campaign Distribution[/bold]", "", "")
    for campaign, count in sorted(campaign_counts.items()):
        pct = (count / total * 100) if total else 0
        table.add_row(f"  {campaign}", str(count), f"{pct:.1f}%")
    
    console.print(table)
    
    console.print("\n[bold]Quality Checks:[/bold]")
    all_have_tier = all(lead.icp_tier in tier_counts for lead in segmented)
    all_have_campaign = all(lead.recommended_campaign for lead in segmented)
    all_have_source = all(lead.source_type for lead in segmented)
    
    console.print(f"  ✅ All leads have valid tier: {all_have_tier}")
    console.print(f"  ✅ All leads have campaign assigned: {all_have_campaign}")
    console.print(f"  ✅ All leads have source type: {all_have_source}")
    
    high_value = sum(1 for s in scores if s >= 60)
    console.print(f"  📊 High-value leads (tier 1-2): {high_value} ({high_value/total*100:.1f}%)" if total else "")
    console.print("")


def main():
    parser = argparse.ArgumentParser(
        description="Segment and score leads using ICP criteria",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python execution/segmentor_classify.py --input leads.json --output segmented.json
    python execution/segmentor_classify.py --input .hive-mind/enriched/leads.json
    python execution/segmentor_classify.py --input leads.json --no-annealing
        """
    )
    parser.add_argument(
        "--input", "-i",
        type=Path, 
        required=True, 
        help="Input JSON file with enriched leads"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path, 
        help="Output JSON file path (default: auto-generated in .hive-mind/segmented/)"
    )
    parser.add_argument(
        "--no-annealing",
        action="store_true",
        help="Disable self-annealing integration"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress detailed output"
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Test mode: read from test leads, save to testing directory, show verification metrics"
    )
    
    args = parser.parse_args()
    
    input_path = args.input
    if args.test_mode:
        test_dir = PROJECT_ROOT / ".hive-mind" / "testing"
        enriched_test = test_dir / "enricher_test_results.json"
        test_leads = test_dir / "test-leads.json"
        if enriched_test.exists():
            input_path = enriched_test
            console.print(f"[cyan]🧪 Test mode: Using enriched test results from {enriched_test}[/cyan]")
        elif test_leads.exists():
            input_path = test_leads
            console.print(f"[cyan]🧪 Test mode: Using test leads from {test_leads}[/cyan]")
        elif not args.input.exists():
            console.print(f"[red]❌ Test mode: No test files found in {test_dir}[/red]")
            console.print("  Expected: enricher_test_results.json or test-leads.json")
            sys.exit(1)
        else:
            console.print(f"[cyan]🧪 Test mode: Using provided input {args.input}[/cyan]")
    
    if not input_path.exists():
        console.print(f"[red]❌ Input file not found: {input_path}[/red]")
        sys.exit(1)
    
    try:
        segmentor = LeadSegmentor(use_annealing=not args.no_annealing)
        
        if args.quiet:
            import io
            from contextlib import redirect_stdout
            with redirect_stdout(io.StringIO()):
                segmented = segmentor.segment_batch(input_path)
        else:
            segmented = segmentor.segment_batch(input_path)
        
        if segmented:
            if not args.quiet:
                segmentor.print_summary(segmented)
            
            if args.test_mode:
                test_output_dir = PROJECT_ROOT / ".hive-mind" / "testing"
                test_output_dir.mkdir(parents=True, exist_ok=True)
                output_path = test_output_dir / "segmentor_test_results.json"
            else:
                output_path = args.output
            
            output_path = segmentor.save_segmented(segmented, output_path)
            
            if args.test_mode:
                print_test_metrics(segmented)
            
            console.print(f"\n[bold green]✅ Segmentation complete![/bold green]")
            console.print(f"  Total leads: {len(segmented)}")
            console.print(f"  Output: {output_path}")
            if not args.test_mode:
                console.print(f"\nNext step: Generate campaigns with:")
                console.print(f"  python execution/crafter_campaign.py --input {output_path}")
        else:
            console.print("[yellow]No leads to segment[/yellow]")
            
    except json.JSONDecodeError as e:
        console.print(f"[red]❌ Invalid JSON in input file: {e}[/red]")
        sys.exit(1)
    except FileNotFoundError as e:
        console.print(f"[red]❌ File not found: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ Segmentation failed: {e}[/red]")
        import traceback
        if not args.quiet:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
