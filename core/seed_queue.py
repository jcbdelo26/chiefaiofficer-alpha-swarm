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
    },
    {
        "first_name": "David", "last_name": "Chen",
        "title": "Founder & COO", "company": "Summit Consulting Group",
        "industry": "Management Consulting", "employees": 250,
        "location": "Chicago, IL", "tier": "tier_1",
    },
    {
        "first_name": "Rachel", "last_name": "Torres",
        "title": "Managing Partner", "company": "Caliber Legal Advisors",
        "industry": "Law Firm", "employees": 95,
        "location": "Denver, CO", "tier": "tier_1",
    },
    {
        "first_name": "James", "last_name": "Nakamura",
        "title": "President", "company": "Meridian Staffing Solutions",
        "industry": "Staffing & Recruiting", "employees": 320,
        "location": "Seattle, WA", "tier": "tier_1",
    },
    {
        "first_name": "Lauren", "last_name": "Bishop",
        "title": "Owner", "company": "Ironclad Construction Group",
        "industry": "Construction", "employees": 150,
        "location": "Nashville, TN", "tier": "tier_1",
    },
    {
        "first_name": "Marcus", "last_name": "Reeves",
        "title": "CEO", "company": "Trident Media Agency",
        "industry": "Advertising Agency", "employees": 210,
        "location": "New York, NY", "tier": "tier_1",
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
        "subject": "Quick question about AI strategy at {company}",
        "body": (
            "Hi {first_name},\n\n"
            "Most {industry} firms your size are asking the same question right now: "
            "where is our AI strategy actually going?\n\n"
            "The challenge is not tools or vendors -- it is the lack of a dedicated "
            "AI executive who can set the roadmap and hold the team accountable. "
            "That is exactly what our Fractional CAIO service provides.\n\n"
            "We embed into your leadership team, run a 90-day M.A.P. cycle "
            "(Measure, Automate, Prove), and deliver measurable ROI -- or you do "
            "not pay the next phase.\n\n"
            "Would a 15-minute call next week make sense to see if this fits "
            "{company}'s priorities?"
        ),
    },
    "t1_b_industry_specific": {
        "tier": "tier_1",
        "angle": "Industry-Specific",
        "subject": "{first_name} -- 300+ hours saved in back-office at a firm like {company}",
        "body": (
            "Hi {first_name},\n\n"
            "I have been working with {industry} firms similar to {company} and "
            "one theme keeps coming up: back-office operations are eating 30-40%% "
            "of leadership bandwidth.\n\n"
            "One of our recent engagements freed up over 300 hours in the first 30 "
            "days by automating intake, reporting, and internal routing -- all "
            "without disrupting the team's existing workflows.\n\n"
            "If you are seeing similar bottlenecks at {company}, I would love to "
            "share what worked.\n\n"
            "Open to a quick chat this week?"
        ),
    },
    "t1_c_hiring_trigger": {
        "tier": "tier_1",
        "angle": "Hiring Trigger",
        "subject": "Bridging the AI gap at {company} before your next hire starts",
        "body": (
            "Hi {first_name},\n\n"
            "I noticed {company} has been growing its team -- and in my experience, "
            "that is exactly when AI strategy either accelerates or stalls.\n\n"
            "Before your next AI or data hire ramps up, there is a window to set "
            "the roadmap so they are executing from day one instead of spending "
            "3 months figuring out priorities.\n\n"
            "Our Fractional CAIO service bridges that gap: we set the strategy, "
            "build the playbook, and hand it off to your permanent hire.\n\n"
            "Worth a 15-minute call to see if the timing makes sense?"
        ),
    },
    "t1_d_value_first": {
        "tier": "tier_1",
        "angle": "Value-First",
        "subject": "Free AI readiness audit for {company}",
        "body": (
            "Hi {first_name},\n\n"
            "I put together a 2-minute AI Readiness audit that has helped "
            "{industry} leaders like yourself identify their 3 biggest automation "
            "wins -- no strings attached.\n\n"
            "It takes about 2 minutes, and you will get a personalized report "
            "showing exactly where AI can save your team time right now.\n\n"
            "Mind if I send the link over?"
        ),
    },
    # Tier 2 angles
    "t2_a_tech_stack": {
        "tier": "tier_2",
        "angle": "Tech Stack Integration",
        "subject": "AI integration playbook for {company}'s stack",
        "body": (
            "Hi {first_name},\n\n"
            "I have been mapping out AI integration playbooks for {industry} "
            "teams and wanted to share one tailored to companies like {company}.\n\n"
            "Most teams I talk to have the same 3 pain points: lead enrichment "
            "takes too long, document processing is manual, and support triage "
            "is a bottleneck. AI can address all three without ripping out your "
            "existing stack.\n\n"
            "Would it be helpful if I shared the playbook specific to your "
            "tech environment?"
        ),
    },
    "t2_b_operations_efficiency": {
        "tier": "tier_2",
        "angle": "Operations Efficiency",
        "subject": "40-60%% time savings on ops at firms like {company}",
        "body": (
            "Hi {first_name},\n\n"
            "Teams like yours at {company} are typically spending 40-60%% of "
            "their operational bandwidth on tasks that AI can handle in minutes.\n\n"
            "Our M.A.P. framework (Measure, Automate, Prove) identifies the "
            "highest-ROI automations in your first 90 days and delivers "
            "measurable results your leadership team can see.\n\n"
            "Open to a brief sync to see where {company} stands?"
        ),
    },
    "t2_c_innovation_champion": {
        "tier": "tier_2",
        "angle": "Innovation Champion",
        "subject": "Why 75%% of AI pilots stall (and how {company} can avoid it)",
        "body": (
            "Hi {first_name},\n\n"
            "75%% of AI pilots never make it past the proof-of-concept stage. "
            "The reason is almost never the technology -- it is the lack of an "
            "internal AI Council driving adoption across the org.\n\n"
            "We help companies like {company} stand up that council: a 90-day "
            "bootcamp to co-pilot phase, then a clean handoff so your team "
            "owns it long-term.\n\n"
            "If you have been thinking about how to scale AI at {company}, "
            "I would love to compare notes."
        ),
    },
    # Tier 3 angles
    "t3_a_quick_win": {
        "tier": "tier_3",
        "angle": "Quick Win",
        "subject": "One workflow to automate at {company} this month",
        "body": (
            "Hi {first_name},\n\n"
            "What if you could pick one workflow at {company} and automate it "
            "this month -- getting 8 hours back every week?\n\n"
            "That is exactly what we help {industry} teams do. No massive "
            "overhaul, no 6-month project. Just one quick win that proves "
            "the value.\n\n"
            "Reply 'yes' and I will send over the top 3 candidates for "
            "{company}."
        ),
    },
    "t3_b_time_savings": {
        "tier": "tier_3",
        "angle": "Time Savings",
        "subject": "10 hrs/week back for your {industry} team",
        "body": (
            "Hi {first_name},\n\n"
            "Most {industry} teams I work with are losing 10+ hours a week "
            "to tasks that AI agents (not chatbots) can handle automatically.\n\n"
            "I am talking about real workflow automation: intake processing, "
            "reporting, data entry, internal routing -- the stuff that eats "
            "your team's time but does not need a human brain.\n\n"
            "Want me to send a quick video showing how this works for "
            "teams like yours at {company}?"
        ),
    },
    "t3_c_competitor_fomo": {
        "tier": "tier_3",
        "angle": "Competitor FOMO",
        "subject": "Your {industry} competitors are already automating",
        "body": (
            "Hi {first_name},\n\n"
            "Just a heads up: several {industry} companies your size are "
            "already using AI to automate 40-60%% of their operational "
            "workflows.\n\n"
            "The gap between early adopters and everyone else is widening "
            "fast. The good news: catching up does not take a massive budget "
            "or a 12-month timeline.\n\n"
            "Reply 'show me' and I will share what is working right now for "
            "teams like {company}."
        ),
    },
    "t3_d_diy_resource": {
        "tier": "tier_3",
        "angle": "DIY Resource",
        "subject": "Free AI automation checklist for {company}",
        "body": (
            "Hi {first_name},\n\n"
            "I put together a 1-page checklist of the top AI tools (all under "
            "$100/mo) that {industry} teams are using to automate repetitive "
            "work.\n\n"
            "No pitch, no call required -- just practical tools you can start "
            "using this week.\n\n"
            "Want me to send it over?"
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
        }
        subject = template["subject"].format(**fmt)
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
