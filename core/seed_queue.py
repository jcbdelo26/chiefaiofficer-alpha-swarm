"""
Dashboard-triggered queue seeding for HoS email review training.

Generates pre-built training emails using synthetic personas and the
11 canonical HoS email angles. No LLM calls, no external APIs.

All seeded emails use @seed-training.internal (non-routable) and are
marked synthetic=True + canary=True for safety.

Usage (API):
    POST /api/admin/seed_queue?count=5&tier=tier_1

Usage (code):
    from core.seed_queue import generate_seed_emails
    emails = generate_seed_emails(count=5, tier_filter="tier_1")
"""

from __future__ import annotations

import os
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Seed personas — 15 synthetic ICP contacts across 3 tiers
# ---------------------------------------------------------------------------

SEED_PERSONAS: List[Dict[str, Any]] = [
    # --- Tier 1: C-Suite at agencies, consulting, staffing, law ---
    {
        "first_name": "Sarah", "last_name": "Mitchell",
        "title": "CEO", "company": "Apex Digital Partners",
        "industry": "Digital Marketing Agency", "employees": 180,
        "location": "Austin, TX", "tier": "tier_1",
        "pain_hook": "managing creative teams while keeping client delivery on track",
        "company_context": "180-person digital marketing agency",
    },
    {
        "first_name": "David", "last_name": "Chen",
        "title": "Founder & COO", "company": "Summit Consulting Group",
        "industry": "Management Consulting", "employees": 250,
        "location": "Chicago, IL", "tier": "tier_1",
        "pain_hook": "scaling advisory engagements without burning out your senior consultants",
        "company_context": "boutique consulting firm in growth mode",
    },
    {
        "first_name": "Rachel", "last_name": "Torres",
        "title": "Managing Partner", "company": "Caliber Legal Advisors",
        "industry": "Law Firm", "employees": 95,
        "location": "Denver, CO", "tier": "tier_1",
        "pain_hook": "running a law practice where billable hours compete with administrative overhead",
        "company_context": "mid-size legal practice balancing growth and efficiency",
    },
    {
        "first_name": "James", "last_name": "Nakamura",
        "title": "President", "company": "Meridian Staffing Solutions",
        "industry": "Staffing & Recruiting", "employees": 320,
        "location": "Seattle, WA", "tier": "tier_1",
        "pain_hook": "filling roles fast while your own back-office runs on spreadsheets",
        "company_context": "staffing firm placing hundreds of candidates a month",
    },
    {
        "first_name": "Lauren", "last_name": "Bishop",
        "title": "Owner", "company": "Ironclad Construction Group",
        "industry": "Construction", "employees": 150,
        "location": "Nashville, TN", "tier": "tier_1",
        "pain_hook": "coordinating 150 crew members across job sites while keeping margins tight",
        "company_context": "mid-size commercial construction firm scaling past the coordination ceiling",
    },
    {
        "first_name": "Marcus", "last_name": "Reeves",
        "title": "CEO", "company": "Trident Media Agency",
        "industry": "Advertising Agency", "employees": 210,
        "location": "New York, NY", "tier": "tier_1",
        "pain_hook": "juggling campaign execution for multiple clients with a lean internal team",
        "company_context": "full-service ad agency competing against bigger shops",
    },
    # --- Tier 2: CTO, CIO, VP Ops at SaaS, IT, healthcare ---
    {
        "first_name": "Priya", "last_name": "Sharma",
        "title": "CTO", "company": "Velox SaaS Platform",
        "industry": "B2B SaaS", "employees": 175,
        "location": "San Francisco, CA", "tier": "tier_2",
    },
    {
        "first_name": "Brian", "last_name": "O'Sullivan",
        "title": "VP of Operations", "company": "NovaCare Health Systems",
        "industry": "Healthcare IT", "employees": 400,
        "location": "Boston, MA", "tier": "tier_2",
    },
    {
        "first_name": "Angela", "last_name": "Kim",
        "title": "CIO", "company": "Bridgepoint IT Services",
        "industry": "IT Services", "employees": 290,
        "location": "Atlanta, GA", "tier": "tier_2",
    },
    {
        "first_name": "Thomas", "last_name": "Erikson",
        "title": "VP of Strategy", "company": "Pinnacle Financial Group",
        "industry": "Financial Services", "employees": 220,
        "location": "Dallas, TX", "tier": "tier_2",
    },
    {
        "first_name": "Natasha", "last_name": "Volkov",
        "title": "Head of Innovation", "company": "Clearview Analytics",
        "industry": "Data Analytics", "employees": 130,
        "location": "Portland, OR", "tier": "tier_2",
    },
    # --- Tier 3: Directors, managers at manufacturing, logistics ---
    {
        "first_name": "Kevin", "last_name": "Morales",
        "title": "Director of Operations", "company": "Titan Manufacturing Co",
        "industry": "Manufacturing", "employees": 500,
        "location": "Detroit, MI", "tier": "tier_3",
    },
    {
        "first_name": "Emily", "last_name": "Hartwell",
        "title": "Director of IT", "company": "Redline Logistics",
        "industry": "Logistics & Supply Chain", "employees": 350,
        "location": "Memphis, TN", "tier": "tier_3",
    },
    {
        "first_name": "Derek", "last_name": "Patel",
        "title": "VP of Engineering", "company": "GreenBuild Home Services",
        "industry": "Home Services", "employees": 85,
        "location": "Phoenix, AZ", "tier": "tier_3",
    },
    {
        "first_name": "Olivia", "last_name": "Chang",
        "title": "Head of Data", "company": "Pacific Coast E-Commerce",
        "industry": "E-Commerce", "employees": 200,
        "location": "Los Angeles, CA", "tier": "tier_3",
    },
]

# ---------------------------------------------------------------------------
# Seed templates — 11 canonical HoS email angles
# ---------------------------------------------------------------------------

SEED_TEMPLATES: Dict[str, Dict[str, Any]] = {
    # Tier 1 angles
    "t1_a_executive_buyin": {
        "tier": "tier_1",
        "angle": "Executive Buy-In",
        "subjects": [
            "AI Roadmap for {company}",
            "Quick question regarding {company}'s AI strategy",
            "Fractional AI leadership for {company}",
        ],
        "body": (
            "Hi {first_name},\n\n"
            "Seeing a lot of {industry} firms stuck in \"AI research mode\" "
            "without moving to implementation.\n\n"
            "Usually, it's because the CTO is buried in legacy tech and "
            "there's no dedicated AI lead to drive the strategy forward.\n\n"
            "We act as your Fractional Chief AI Officer to move {company} "
            "from curiosity to ROI -- typically in 90 days.\n\n"
            "What that looks like:\n"
            "- Day 1: One-day M.A.P. Bootcamp (your team leaves with an "
            "AI-ready action plan)\n"
            "- Days 2-90: We embed with your team, build the workflows, "
            "and measure results\n"
            "- Guarantee: Measurable ROI, or you don't pay the next phase\n\n"
            "Worth a brief chat on how we're doing this for similar "
            "{industry} companies?"
        ),
    },
    "t1_b_industry_specific": {
        "tier": "tier_1",
        "angle": "Industry-Specific",
        "subjects": [
            "AI in {industry} / {company}",
            "Automating {company}'s back-office?",
            "{first_name} -- operational efficiency at {company}",
        ],
        "body": (
            "Hi {first_name},\n\n"
            "Many {industry} CEOs I speak with are frustrated by thin margins "
            "and operational inefficiency.\n\n"
            "The fix we're seeing work: AI automating the back-office \"drudge "
            "work\" -- project estimation, invoicing, scheduling, reporting -- "
            "so your team can focus on revenue.\n\n"
            "Example: A 150-person {industry} firm saved 300+ hours in 30 days "
            "and saw a 27% productivity boost after our 90-day AI pilot.\n\n"
            "Are you open to seeing a quick breakdown of the workflow we built "
            "for them?"
        ),
    },
    "t1_c_hiring_trigger": {
        "tier": "tier_1",
        "angle": "Hiring Trigger",
        "subjects": [
            "Re: {company}'s AI hiring",
            "{first_name} - about your AI team",
            "Bridge strategy for {company}",
        ],
        "body": (
            "Hi {first_name},\n\n"
            "Noticed you're hiring for a {title} at {company}. Great move.\n\n"
            "But here's what we usually see: it takes 4-6 months to get that "
            "person productive -- finding the right hire, onboarding, learning "
            "your systems.\n\n"
            "We provide the fractional AI leadership to set the strategy now "
            "so your new hire hits the ground running on Day 1.\n\n"
            "What we do in 90 days:\n"
            "- Define your AI roadmap before the hire starts\n"
            "- Train your current team on AI fundamentals\n"
            "- Build your first automated workflows\n"
            "- Hand off a documented playbook to your new AI lead\n\n"
            "Open to a \"bridge strategy\" call? Just 15 minutes."
        ),
    },
    "t1_d_value_first": {
        "tier": "tier_1",
        "angle": "Value-First",
        "subjects": [
            "2-minute AI readiness check for {company}",
            "{first_name} - quick resource for {industry} leaders",
            "AI quick wins for {industry}",
        ],
        "body": (
            "Hi {first_name},\n\n"
            "I put together a 2-minute \"AI Readiness\" audit for "
            "{industry} leaders.\n\n"
            "It covers the 3 biggest low-hanging fruit automation wins "
            "we're seeing right now -- ones that typically save 10-20 hours "
            "per week per team member.\n\n"
            "Mind if I send the link over?\n\n"
            "(No pitch, no 30-minute demo request -- just a quick "
            "self-assessment.)"
        ),
    },
    # Tier 2 angles (aligned to HoS doc source of truth)
    "t2_a_tech_stack": {
        "tier": "tier_2",
        "angle": "Tech Stack Integration",
        "subjects": [
            "{first_name} - AI for {company}'s tech stack",
            "AI integration for {industry} teams",
            "AI playbook for teams like {company}",
        ],
        "body": (
            "Hi {first_name},\n\n"
            "I noticed {company} is in {industry} -- we actually have a "
            "specific AI integration playbook for that space.\n\n"
            "Most {title} roles I talk to are seeing two blockers:\n"
            "1. The CTO is buried in legacy tech maintenance\n"
            "2. No dedicated AI strategy lead to drive implementation\n\n"
            "We bridge that gap as your Fractional Chief AI Officer -- "
            "moving from \"AI pilot\" to production workflows in 90 days.\n\n"
            "What teams like yours are automating:\n"
            "- Lead enrichment & qualification (from raw data to booked meetings)\n"
            "- Document processing & extraction (invoices, contracts, reports)\n"
            "- Customer support triage (route, respond, escalate)\n\n"
            "Would it be helpful if I shared the AI playbook we're seeing "
            "work best for {industry}?"
        ),
    },
    "t2_b_operations_efficiency": {
        "tier": "tier_2",
        "angle": "Operations Efficiency",
        "subjects": [
            "{company}'s operational efficiency",
            "{first_name} - cutting {company}'s overhead",
            "AI for operations teams at {company}",
        ],
        "body": (
            "Hi {first_name},\n\n"
            "The teams we work with are seeing 40-60% time savings on "
            "operational tasks using AI automation.\n\n"
            "Specifically:\n"
            "- One 150-person firm saved 300+ hours in 30 days on "
            "administrative work\n"
            "- A 7-person pilot team saw 27% productivity boost in the "
            "first month\n"
            "- AI now handles the work of 20+ staff in Operations at one "
            "of our travel clients\n\n"
            "The pattern: start with high-volume, low-complexity tasks "
            "(data entry, scheduling, reporting), prove ROI in 30 days, "
            "then expand.\n\n"
            "We call it the M.A.P. framework: Measure, Automate, Prove.\n\n"
            "Open to a brief sync, or should I just send over a one-pager "
            "for now?"
        ),
    },
    "t2_c_innovation_champion": {
        "tier": "tier_2",
        "angle": "Innovation Champion",
        "subjects": [
            "AI transformation at {company}",
            "{first_name} - building the AI Council",
            "Accelerating {company}'s AI roadmap",
        ],
        "body": (
            "Hi {first_name},\n\n"
            "75%+ of AI pilots stall before ROI is proven.\n\n"
            "The root cause we see: insufficient governance and process "
            "integration. CFOs see spend but not savings. Teams focus on "
            "\"AI chatbots\" instead of operational transformation.\n\n"
            "We fix this by building an AI Council inside your company -- "
            "internal champions from every department who drive adoption "
            "from within.\n\n"
            "Our 90-day approach:\n"
            "1. Day 1: Executive bootcamp (your team leaves AI-ready)\n"
            "2. Weeks 2-8: We co-pilot with your AI Council, build the "
            "workflows\n"
            "3. Weeks 9-12: Measure ROI, hand off the playbook\n\n"
            "If the M.A.P. cycle doesn't deliver tangible savings, you "
            "don't pay the next phase.\n\n"
            "Mind if I send over a 2-minute video on how we do this?"
        ),
    },
    # Tier 3 angles (aligned to HoS doc source of truth)
    "t3_a_quick_win": {
        "tier": "tier_3",
        "angle": "Quick Win",
        "subjects": [
            "Quick idea for {company}",
            "{first_name} - one workflow to automate",
            "Save 5 hours/week at {company}",
        ],
        "body": (
            "Hi {first_name},\n\n"
            "Most {industry} teams I talk to have one workflow that eats up "
            "way too much time -- usually something like data entry, reporting, "
            "or lead research.\n\n"
            "We help companies like {company} automate that one thing first. "
            "No 6-month project. Just pick the biggest time-waster and fix it.\n\n"
            "Example: A 25-person {industry} company automated their weekly "
            "reporting and got 8 hours back per person, per month.\n\n"
            "Worth a quick look?\n\n"
            "Reply \"yes\" and I'll send a 2-minute breakdown of how we do it."
        ),
    },
    "t3_b_time_savings": {
        "tier": "tier_3",
        "angle": "Time Savings",
        "subjects": [
            "{first_name} - 10 hours back per week",
            "What if {company}'s admin work did itself?",
            "AI for the boring stuff at {company}",
        ],
        "body": (
            "Hi {first_name},\n\n"
            "The teams I work with typically waste 10-15 hours per week on "
            "tasks that should be automated: data entry, status updates, "
            "scheduling, and reporting.\n\n"
            "We use AI agents to handle that -- not a \"chatbot\" but actual "
            "workflow automation that runs 24/7.\n\n"
            "Quick wins we see for {industry} teams:\n"
            "- Auto-updating spreadsheets and dashboards\n"
            "- Lead research done overnight (you wake up to qualified lists)\n"
            "- Follow-up emails sent at the right time, automatically\n\n"
            "No huge IT project. Start with one workflow, prove it works, "
            "expand from there.\n\n"
            "Should I send over a quick video showing how this works for "
            "teams your size?"
        ),
    },
    "t3_c_competitor_fomo": {
        "tier": "tier_3",
        "angle": "Competitor FOMO",
        "subjects": [
            "What {industry} teams are automating",
            "{first_name} - how competitors are scaling",
            "AI adoption in {industry}",
        ],
        "body": (
            "Hi {first_name},\n\n"
            "I've been working with a few {industry} companies lately, and "
            "there's a pattern:\n\n"
            "The ones pulling ahead are automating the \"invisible work\" -- "
            "the research, the data entry, the follow-ups that eat up 40-60% "
            "of everyone's week.\n\n"
            "What they're automating:\n"
            "- Lead research and scoring (AI does it overnight)\n"
            "- Proposal drafts and first-pass content\n"
            "- Client onboarding workflows\n"
            "- Reporting and status updates\n\n"
            "Not asking you to rip out your tech stack. Just add a layer of "
            "AI that handles the repetitive stuff.\n\n"
            "Curious if {company} has looked into this yet?\n\n"
            "Just reply \"show me\" -- I'll send a quick breakdown of what "
            "we're seeing work."
        ),
    },
    "t3_d_diy_resource": {
        "tier": "tier_3",
        "angle": "DIY Resource",
        "subjects": [
            "Free AI checklist for {industry}",
            "{first_name} - quick resource for small teams",
            "AI quick wins (no sales pitch)",
        ],
        "body": (
            "Hi {first_name},\n\n"
            "I put together a 1-page checklist of the 5 \"quick win\" AI "
            "automations that work best for {industry} teams under 50 people.\n\n"
            "No fluff, no 30-minute demo required -- just actionable stuff "
            "you can implement yourself or hand to your ops person.\n\n"
            "Includes:\n"
            "- Top 5 workflows to automate first (and why)\n"
            "- Tools that work for small budgets (under $100/month)\n"
            "- Common mistakes to avoid\n\n"
            "Mind if I send it over?\n\n"
            "(No strings attached -- it's genuinely useful even if we "
            "never talk.)"
        ),
    },
}

# Tier → priority mapping (matches pipeline convention)
_TIER_PRIORITY = {"tier_1": "high", "tier_2": "medium", "tier_3": "normal"}

# Safe email domain (non-routable TLD, prevents accidental delivery)
_SEED_DOMAIN = "seed-training.internal"


def generate_seed_emails(
    count: int = 5,
    tier_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Generate pre-built training emails and push to the shadow queue.

    No LLM calls, no external API calls. Instant generation.

    Args:
        count: Number of emails to generate (capped at 20).
        tier_filter: Optional tier constraint ("tier_1", "tier_2", "tier_3").

    Returns:
        List of generated email payloads (already pushed to shadow queue).
    """
    count = max(1, min(count, 20))

    # Filter personas by tier if requested
    pool = SEED_PERSONAS
    if tier_filter:
        pool = [p for p in SEED_PERSONAS if p["tier"] == tier_filter]
        if not pool:
            pool = SEED_PERSONAS  # fallback to all if filter matches nothing

    # Filter templates by tier
    all_templates = list(SEED_TEMPLATES.values())

    # Import signature enforcement
    try:
        from core.email_signature import enforce_text_signature
    except ImportError:
        def enforce_text_signature(body: str) -> str:  # type: ignore[misc]
            return body

    # Import shadow queue push
    try:
        from core.shadow_queue import push as shadow_push
    except ImportError:
        shadow_push = None  # type: ignore[assignment]

    now = datetime.now(timezone.utc)
    ts_str = now.strftime("%Y%m%d_%H%M%S")
    generated: List[Dict[str, Any]] = []
    used_keys: set = set()

    for i in range(count):
        # Pick a persona (cycle through pool, avoid repeats where possible)
        persona = pool[i % len(pool)] if count <= len(pool) else random.choice(pool)

        # Dedupe key: avoid same recipient in one batch
        dedupe_key = f"{persona['first_name']}_{persona['last_name']}"
        attempt = 0
        while dedupe_key in used_keys and attempt < 10:
            persona = random.choice(pool)
            dedupe_key = f"{persona['first_name']}_{persona['last_name']}"
            attempt += 1
        used_keys.add(dedupe_key)

        # Pick a tier-matched template
        tier = persona["tier"]
        tier_templates = [t for t in all_templates if t["tier"] == tier]
        if not tier_templates:
            tier_templates = all_templates
        template = random.choice(tier_templates)

        # Render placeholders
        fmt = {
            "first_name": persona["first_name"],
            "last_name": persona["last_name"],
            "company": persona["company"],
            "title": persona["title"],
            "industry": persona["industry"],
            "pain_hook": persona.get("pain_hook", "growing efficiently"),
            "company_context": persona.get("company_context", persona["industry"] + " firm"),
        }
        # Support both "subject" (string) and "subjects" (list for rotation)
        subject_raw = template.get("subject") or random.choice(template["subjects"])
        subject = subject_raw.format(**fmt)
        raw_body = template["body"].format(**fmt)
        body = enforce_text_signature(raw_body)

        # Build email address
        email_local = "{}.{}".format(
            persona["first_name"].lower(),
            persona["last_name"].lower(),
        )
        to_addr = "{}@{}".format(email_local, _SEED_DOMAIN)

        # Build email_id
        short_uuid = uuid.uuid4().hex[:8]
        slug = "{}_{}".format(
            persona["first_name"].lower(),
            persona["last_name"].lower(),
        )
        email_id = "seed_{}_{}_{}".format(ts_str, slug, short_uuid)

        email_data: Dict[str, Any] = {
            "email_id": email_id,
            "status": "pending",
            "to": to_addr,
            "subject": subject,
            "body": body,
            "source": "dashboard_seed",
            "direction": "outbound",
            "delivery_platform": "training",
            "delivery_path": "seed_training",
            "timestamp": now.isoformat(),
            "created_at": now.isoformat(),
            "recipient_data": {
                "name": "{} {}".format(persona["first_name"], persona["last_name"]),
                "company": persona["company"],
                "title": persona["title"],
                "location": persona.get("location", ""),
                "industry": persona["industry"],
                "employees": persona.get("employees", 0),
            },
            "context": {
                "source": "dashboard_seed",
                "source_type": "seed_training",
                "campaign_type": "seed_training",
                "campaign_id": "seed_training",
                "intent_score": round(random.uniform(0.75, 0.95), 2),
                "icp_tier": tier,
                "icp_score": round(random.uniform(65, 98), 1),
            },
            "tier": tier,
            "angle": template.get("angle", ""),
            "priority": _TIER_PRIORITY.get(tier, "normal"),
            "synthetic": True,
            "canary": True,
            # Deliberately NOT setting _do_not_dispatch or canary_training
            # so the email appears in the default pending queue.
            # Safety: OPERATOR checks synthetic before dispatch.
        }

        # Push to shadow queue (Redis + filesystem)
        if shadow_push is not None:
            try:
                shadow_dir_env = os.getenv("SHADOW_EMAIL_DIR")
                shadow_push(email_data, shadow_dir=shadow_dir_env)
            except Exception:
                pass  # Graceful degradation; email still in returned list

        generated.append(email_data)

    return generated
