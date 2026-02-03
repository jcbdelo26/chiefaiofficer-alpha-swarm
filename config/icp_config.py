#!/usr/bin/env python3
"""
ICP Configuration - Chief AI Officer Alpha Swarm
=================================================

Ideal Customer Profile (ICP) scoring and classification based on
buyer persona research and outbound strategy documentation.

Target: Fractional Chief AI Officer Services
Offer: AI Opportunity Audit / AI Implementation Roadmap
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class PersonaTier(Enum):
    """Buyer persona priority tiers."""
    TIER_1 = "tier_1"  # Primary decision-makers
    TIER_2 = "tier_2"  # Influencers/Champions
    TIER_3 = "tier_3"  # Secondary contacts


class IndustryFit(Enum):
    """Industry fit classification."""
    IDEAL = "ideal"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    DISQUALIFIED = "disqualified"


# =============================================================================
# TARGET PERSONAS
# =============================================================================

TARGET_TITLES = {
    PersonaTier.TIER_1: [
        # Primary Decision Makers (highest conversion)
        "CEO", "Chief Executive Officer",
        "Founder", "Co-Founder",
        "President",
        "Managing Partner",  # PE/VC
        "COO", "Chief Operating Officer",
        "Owner",
    ],
    PersonaTier.TIER_2: [
        # Strategic Influencers
        "CTO", "Chief Technology Officer",
        "CIO", "Chief Information Officer",
        "CSO", "Chief Strategy Officer",
        "Chief of Staff",
        "VP of Operations",
        "VP of Strategy",
        "Head of Innovation",
        "Head of Transformation",
        "Head of Digital",
        "Managing Director",
    ],
    PersonaTier.TIER_3: [
        # Secondary Contacts
        "Director of Operations",
        "Director of IT",
        "Director of Strategy",
        "VP Engineering",
        "VP of Technology",
        "Head of AI",
        "Head of Data",
    ],
}


# =============================================================================
# TARGET INDUSTRIES
# =============================================================================

TARGET_INDUSTRIES = {
    IndustryFit.IDEAL: [
        # Professional Services (highest operational overhead)
        "Marketing Agency",
        "Advertising Agency",
        "Digital Marketing",
        "Recruitment",
        "Staffing",
        "Consulting",
        "Management Consulting",
        "Law Firm",
        "Legal Services",
        "Accounting",
        "CPA Firm",
        
        # Real Estate (high admin overhead)
        "Real Estate Brokerage",
        "Property Management",
        "Commercial Real Estate",
        
        # E-commerce/DTC (scalable operations)
        "E-commerce",
        "Direct-to-Consumer",
        "DTC",
        "Retail",
    ],
    IndustryFit.GOOD: [
        # Tech/SaaS (AI-aware)
        "B2B SaaS",
        "Software",
        "Technology",
        "IT Services",
        "Managed Services",
        
        # Healthcare Services
        "Healthcare",
        "Medical Practice",
        "Dental",
        "Physical Therapy",
        
        # Financial Services
        "Financial Services",
        "Insurance",
        "Wealth Management",
    ],
    IndustryFit.ACCEPTABLE: [
        # Manufacturing/Logistics (operational focus)
        "Manufacturing",
        "Logistics",
        "Supply Chain",
        "Distribution",
        "Warehousing",
        
        # Construction
        "Construction",
        "General Contractor",
        "Home Services",
    ],
    IndustryFit.DISQUALIFIED: [
        # Avoid these
        "Government",
        "Non-profit",
        "Education",
        "Academic",
        "Research",
    ],
}


# =============================================================================
# COMPANY SIZE CRITERIA
# =============================================================================

@dataclass
class CompanySizeRange:
    min_employees: int
    max_employees: int
    score_multiplier: float
    label: str


COMPANY_SIZE_TIERS = [
    CompanySizeRange(10, 50, 1.0, "Small SMB"),
    CompanySizeRange(51, 100, 1.2, "Growth SMB"),
    CompanySizeRange(101, 250, 1.5, "Mid-Market Sweet Spot"),  # PRIMARY TARGET
    CompanySizeRange(251, 500, 1.3, "Upper Mid-Market"),
    CompanySizeRange(501, 1000, 1.0, "Lower Enterprise"),
]

# Disqualify if below or above these
MIN_EMPLOYEES = 10
MAX_EMPLOYEES = 1000


# =============================================================================
# REVENUE CRITERIA
# =============================================================================

@dataclass  
class RevenueRange:
    min_revenue: int  # in millions
    max_revenue: int
    score_multiplier: float
    label: str


REVENUE_TIERS = [
    RevenueRange(1, 5, 0.8, "Early Stage"),
    RevenueRange(5, 10, 1.0, "Growth Stage"),
    RevenueRange(10, 25, 1.3, "Scaling"),
    RevenueRange(25, 50, 1.5, "Scale-Up Sweet Spot"),  # PRIMARY TARGET
    RevenueRange(50, 100, 1.3, "Mid-Market"),
    RevenueRange(100, 250, 1.0, "Upper Mid-Market"),
]

MIN_REVENUE_M = 1  # $1M minimum
MAX_REVENUE_M = 250  # $250M maximum


# =============================================================================
# PAIN POINT SIGNALS
# =============================================================================

PAIN_POINT_SIGNALS = {
    # High intent signals (50+ points)
    "ai_overwhelm": {
        "score": 60,
        "keywords": [
            "AI strategy", "AI roadmap", "AI implementation",
            "don't know where to start with AI", "AI consultant",
            "fractional AI", "AI advisor"
        ],
        "description": "Knows they need AI but lacks roadmap"
    },
    "manual_processes": {
        "score": 55,
        "keywords": [
            "manual data entry", "spreadsheet", "copy paste",
            "time consuming", "repetitive tasks", "administrative burden"
        ],
        "description": "High operational costs from manual work"
    },
    "founder_bottleneck": {
        "score": 50,
        "keywords": [
            "wearing too many hats", "can't scale", "founder-led sales",
            "no time", "burned out", "need to delegate"
        ],
        "description": "Founder is the bottleneck"
    },
    
    # Medium intent signals (30-49 points)
    "tech_adoption": {
        "score": 40,
        "keywords": [
            "digital transformation", "modernization", "automation",
            "optimize", "streamline", "efficiency"
        ],
        "description": "Actively seeking tech solutions"
    },
    "hiring_challenges": {
        "score": 35,
        "keywords": [
            "can't find talent", "hiring freeze", "high turnover",
            "training costs", "remote team"
        ],
        "description": "Hiring/retention challenges"
    },
    
    # Lower intent signals (10-29 points)
    "growth_focus": {
        "score": 25,
        "keywords": [
            "scale", "growth", "expand", "new markets",
            "increase revenue"
        ],
        "description": "Growth-focused messaging"
    },
}


# =============================================================================
# DISQUALIFICATION CRITERIA
# =============================================================================

DISQUALIFICATION_CRITERIA = [
    "less_than_10_employees",
    "non_profit",
    "government",
    "already_customer",
    "competitor",
    "agency_under_20_employees",
    "no_email",
    "generic_email",  # gmail, yahoo, etc for business leads
]


# =============================================================================
# TECH STACK SIGNALS
# =============================================================================

POSITIVE_TECH_SIGNALS = {
    # CRM (indicates sales maturity)
    "salesforce": 20,
    "hubspot": 20,
    "pipedrive": 15,
    "zoho crm": 10,
    
    # AI-adjacent tools (indicates AI awareness)
    "zapier": 15,
    "make.com": 15,
    "notion": 10,
    "airtable": 12,
    
    # Communication tools (indicates remote/modern)
    "slack": 10,
    "teams": 10,
}

NEGATIVE_TECH_SIGNALS = {
    # Indicates already has AI capability (harder sell)
    "in-house ai team": -30,
    "data science team": -20,
    "ml engineers": -20,
}


# =============================================================================
# ICP SCORING FUNCTION
# =============================================================================

@dataclass
class ICPScore:
    """ICP scoring result."""
    total_score: float
    title_score: float
    industry_score: float
    size_score: float
    revenue_score: float
    pain_point_score: float
    tech_stack_score: float
    tier: str  # "A", "B", "C", "D", or "DISQUALIFIED"
    persona_tier: Optional[PersonaTier] = None
    industry_fit: Optional[IndustryFit] = None
    reasoning: List[str] = field(default_factory=list)
    disqualification_reasons: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "total_score": self.total_score,
            "title_score": self.title_score,
            "industry_score": self.industry_score,
            "size_score": self.size_score,
            "revenue_score": self.revenue_score,
            "pain_point_score": self.pain_point_score,
            "tech_stack_score": self.tech_stack_score,
            "tier": self.tier,
            "persona_tier": self.persona_tier.value if self.persona_tier else None,
            "industry_fit": self.industry_fit.value if self.industry_fit else None,
            "reasoning": self.reasoning,
            "disqualification_reasons": self.disqualification_reasons,
        }


def score_lead(
    title: str,
    industry: str,
    employee_count: int,
    revenue_m: Optional[float] = None,
    pain_points: Optional[List[str]] = None,
    tech_stack: Optional[List[str]] = None,
) -> ICPScore:
    """
    Score a lead against ICP criteria.
    
    Returns ICPScore with tier classification:
    - A: Score >= 80 (Hot lead, prioritize)
    - B: Score 60-79 (Good fit, standard outreach)
    - C: Score 40-59 (Acceptable, lower priority)
    - D: Score 20-39 (Poor fit, deprioritize)
    - DISQUALIFIED: Score < 20 or fails criteria
    """
    title_score = 0.0
    industry_score = 0.0
    size_score = 0.0
    revenue_score = 0.0
    pain_point_score = 0.0
    tech_stack_score = 0.0
    reasoning = []
    disqualification_reasons = []
    persona_tier = None
    industry_fit = None
    
    # Title scoring
    title_lower = title.lower()
    for tier, titles in TARGET_TITLES.items():
        for t in titles:
            if t.lower() in title_lower:
                persona_tier = tier
                if tier == PersonaTier.TIER_1:
                    title_score = 30
                    reasoning.append(f"Tier 1 title: {t}")
                elif tier == PersonaTier.TIER_2:
                    title_score = 20
                    reasoning.append(f"Tier 2 title: {t}")
                else:
                    title_score = 10
                    reasoning.append(f"Tier 3 title: {t}")
                break
        if persona_tier:
            break
    
    # Industry scoring
    industry_lower = industry.lower()
    for fit, industries in TARGET_INDUSTRIES.items():
        for ind in industries:
            if ind.lower() in industry_lower:
                industry_fit = fit
                if fit == IndustryFit.IDEAL:
                    industry_score = 25
                    reasoning.append(f"Ideal industry: {ind}")
                elif fit == IndustryFit.GOOD:
                    industry_score = 18
                    reasoning.append(f"Good industry: {ind}")
                elif fit == IndustryFit.ACCEPTABLE:
                    industry_score = 10
                    reasoning.append(f"Acceptable industry: {ind}")
                else:
                    industry_score = -50
                    disqualification_reasons.append(f"Disqualified industry: {ind}")
                break
        if industry_fit:
            break
    
    # Company size scoring
    if employee_count < MIN_EMPLOYEES:
        disqualification_reasons.append(f"Too small: {employee_count} employees")
        size_score = -20
    elif employee_count > MAX_EMPLOYEES:
        disqualification_reasons.append(f"Too large: {employee_count} employees")
        size_score = -10
    else:
        for tier in COMPANY_SIZE_TIERS:
            if tier.min_employees <= employee_count <= tier.max_employees:
                size_score = 15 * tier.score_multiplier
                reasoning.append(f"Size fit: {tier.label} ({employee_count} emp)")
                break
    
    # Revenue scoring
    if revenue_m:
        if revenue_m < MIN_REVENUE_M:
            disqualification_reasons.append(f"Revenue too low: ${revenue_m}M")
            revenue_score = -10
        elif revenue_m > MAX_REVENUE_M:
            reasoning.append(f"Large revenue: ${revenue_m}M (may need enterprise approach)")
            revenue_score = 5
        else:
            for tier in REVENUE_TIERS:
                if tier.min_revenue <= revenue_m <= tier.max_revenue:
                    revenue_score = 10 * tier.score_multiplier
                    reasoning.append(f"Revenue fit: {tier.label} (${revenue_m}M)")
                    break
    
    # Pain point scoring
    if pain_points:
        for pp in pain_points:
            pp_lower = pp.lower()
            for signal_key, signal_data in PAIN_POINT_SIGNALS.items():
                for keyword in signal_data["keywords"]:
                    if keyword.lower() in pp_lower:
                        pain_point_score += signal_data["score"]
                        reasoning.append(f"Pain point: {signal_data['description']}")
                        break
    
    # Tech stack scoring
    if tech_stack:
        for tech in tech_stack:
            tech_lower = tech.lower()
            for tech_signal, score in POSITIVE_TECH_SIGNALS.items():
                if tech_signal in tech_lower:
                    tech_stack_score += score
                    reasoning.append(f"Positive tech signal: {tech_signal}")
            for tech_signal, score in NEGATIVE_TECH_SIGNALS.items():
                if tech_signal in tech_lower:
                    tech_stack_score += score
                    reasoning.append(f"Negative tech signal: {tech_signal}")
    
    # Calculate total
    total_score = (
        title_score + 
        industry_score + 
        size_score + 
        revenue_score + 
        pain_point_score + 
        tech_stack_score
    )
    
    # Determine tier
    if disqualification_reasons or total_score < 20:
        tier = "DISQUALIFIED"
    elif total_score >= 80:
        tier = "A"
    elif total_score >= 60:
        tier = "B"
    elif total_score >= 40:
        tier = "C"
    else:
        tier = "D"
    
    return ICPScore(
        total_score=round(total_score, 2),
        title_score=title_score,
        industry_score=industry_score,
        size_score=size_score,
        revenue_score=revenue_score,
        pain_point_score=pain_point_score,
        tech_stack_score=tech_stack_score,
        tier=tier,
        persona_tier=persona_tier,
        industry_fit=industry_fit,
        reasoning=reasoning,
        disqualification_reasons=disqualification_reasons,
    )


# =============================================================================
# MESSAGING TEMPLATES BY TIER
# =============================================================================

MESSAGING_ANGLES = {
    "A": {
        "primary_angle": "ai_noise",
        "subject": "{first_name}, your AI strategy",
        "hook": "Every business owner is overwhelmed by AI, but lacks a practical way to implement it.",
        "cta": "Worth a 5-minute chat to see where you're leaking time?",
        "sequence": "hot_lead_fast_track",
    },
    "B": {
        "primary_angle": "efficiency_gap",
        "subject": "Observation: {company_name} manual processes",
        "hook": "The Efficiency Gap - difference between current OpEx and what it would be with automated workflows.",
        "cta": "I put together a 2-page roadmap for companies in {industry}. Want me to send the PDF?",
        "sequence": "warm_lead_nurture",
    },
    "C": {
        "primary_angle": "fractional_advantage",
        "subject": "Chief AI Officer for {company_name}?",
        "hook": "Most companies need an AI strategy but can't justify a $20k/month executive.",
        "cta": "Reply 'AI' and I'll send a video showing how we did this for a similar company.",
        "sequence": "cold_lead_standard",
    },
}


# =============================================================================
# DEMO
# =============================================================================

def demo():
    """Demonstrate ICP scoring."""
    print("=" * 60)
    print("ICP Scoring Demo")
    print("=" * 60)
    
    # Example leads
    leads = [
        {
            "name": "Sarah Chen - CEO of Marketing Agency",
            "title": "CEO",
            "industry": "Marketing Agency",
            "employee_count": 85,
            "revenue_m": 12,
            "pain_points": ["manual data entry", "can't scale operations"],
            "tech_stack": ["hubspot", "slack"],
        },
        {
            "name": "Mike Johnson - CTO at E-commerce",
            "title": "CTO",
            "industry": "E-commerce",
            "employee_count": 150,
            "revenue_m": 35,
            "pain_points": ["digital transformation"],
            "tech_stack": ["salesforce", "zapier"],
        },
        {
            "name": "Jane Smith - Director at Non-profit",
            "title": "Director of Operations",
            "industry": "Non-profit",
            "employee_count": 25,
            "revenue_m": 2,
            "pain_points": [],
            "tech_stack": [],
        },
    ]
    
    for lead in leads:
        print(f"\n{lead['name']}")
        print("-" * 40)
        
        score = score_lead(
            title=lead["title"],
            industry=lead["industry"],
            employee_count=lead["employee_count"],
            revenue_m=lead.get("revenue_m"),
            pain_points=lead.get("pain_points"),
            tech_stack=lead.get("tech_stack"),
        )
        
        print(f"  Total Score: {score.total_score}")
        print(f"  Tier: {score.tier}")
        print(f"  Persona: {score.persona_tier.value if score.persona_tier else 'Unknown'}")
        print(f"  Industry Fit: {score.industry_fit.value if score.industry_fit else 'Unknown'}")
        print(f"  Reasoning: {score.reasoning[:3]}")
        
        if score.disqualification_reasons:
            print(f"  DISQUALIFIED: {score.disqualification_reasons}")
        
        if score.tier in MESSAGING_ANGLES:
            print(f"  Recommended Angle: {MESSAGING_ANGLES[score.tier]['primary_angle']}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    demo()
