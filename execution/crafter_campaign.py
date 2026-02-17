#!/usr/bin/env python3
"""
Crafter Agent - Campaign Generator
==================================
Generates hyper-personalized email campaigns from segmented leads.

Usage:
    python execution/crafter_campaign.py --input .hive-mind/segmented/leads.json
    python execution/crafter_campaign.py --segment tier1_gong --template t1_executive_buyin
"""

import os
import sys
import json
import uuid
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from jinja2 import Template, Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from core.compliance import validate_campaign, ValidationResult
from core.event_log import log_event, EventType
from core.retry import retry, schedule_retry
from core.alerts import send_warning, send_critical
from core.context import (
    compact_lead_batch,
    get_context_zone,
    ContextZone,
    estimate_tokens
)

console = Console()

# Dumb Zone protection settings
SMART_ZONE_BATCH_SIZE = 25  # Process leads in batches to stay in Smart Zone
CONTEXT_WARNING_THRESHOLD = 0.4  # Warn when approaching Dumb Zone


@dataclass
class EmailStep:
    """Single email in a sequence."""
    step: int
    delay_days: int
    channel: str  # email, linkedin
    subject_a: str
    subject_b: str
    body_a: str
    body_b: str
    personalization_level: int  # 1-3


@dataclass
class Campaign:
    """Complete campaign with leads and sequence."""
    campaign_id: str
    name: str
    segment: str
    campaign_type: str
    leads: List[Dict[str, Any]]
    lead_count: int
    sequence: List[EmailStep]
    status: str  # draft, pending_review, approved, active, paused
    created_at: str
    avg_icp_score: float
    avg_intent_score: float
    personalization_hooks: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class CampaignCrafter:
    """Generates hyper-personalized email campaigns."""

    # =========================================================================
    # 11 HoS-Approved Email Angles (Fractional Chief AI Officer + M.A.P. Framework)
    # =========================================================================
    TEMPLATES = {
        "t1_executive_buyin": {
            "subject_a": "AI Roadmap for {{lead.company}}",
            "subject_b": "Quick question regarding {{lead.company}}'s AI strategy",
            "body": """Hi {{lead.first_name}},

Seeing a lot of {{lead.industry}} firms stuck in "AI research mode" without moving to implementation.

Usually, it's because the CTO is buried in legacy tech and there's no dedicated AI lead to drive the strategy forward.

We act as your Fractional Chief AI Officer to move {{lead.company}} from curiosity to ROI—typically in 90 days.

What that looks like:
- Day 1: One-day M.A.P. Bootcamp (your team leaves with an AI-ready action plan)
- Days 2-90: We embed with your team, build the workflows, and measure results
- Guarantee: Measurable ROI, or you don't pay the next phase

Worth a brief chat on how we're doing this for similar {{lead.industry}} companies?

Best,
{{sender.name}}
{{sender.title}}
{{sender.calendar_link}}

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        "t1_industry_specific": {
            "subject_a": "AI in {{lead.industry}} / {{lead.company}}",
            "subject_b": "Automating {{lead.company}}'s back-office?",
            "body": """Hi {{lead.first_name}},

Many {{lead.industry}} CEOs I speak with are frustrated by thin margins and operational inefficiency.

The fix we're seeing work: AI automating the back-office "drudge work"—project estimation, invoicing, scheduling, reporting—so your team can focus on revenue.

Example: A 150-person {{lead.industry}} firm saved 300+ hours in 30 days and saw a 27% productivity boost after our 90-day AI pilot.

Are you open to seeing a quick breakdown of the workflow we built for them?

Best,
{{sender.name}}
{{sender.title}}
{{sender.calendar_link}}

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        "t1_hiring_trigger": {
            "subject_a": "Re: {{lead.company}}'s AI hiring",
            "subject_b": "Bridge strategy for {{lead.company}}",
            "body": """Hi {{lead.first_name}},

Noticed you're hiring for AI/data roles at {{lead.company}}. Great move.

But here's what we usually see: it takes 4-6 months to get that person productive—finding the right hire, onboarding, learning your systems.

We provide the fractional AI leadership to set the strategy *now* so your new hire hits the ground running on Day 1.

What we do in 90 days:
- Define your AI roadmap before the hire starts
- Train your current team on AI fundamentals
- Build your first automated workflows
- Hand off a documented playbook to your new AI lead

Open to a "bridge strategy" call? Just 15 minutes.

Best,
{{sender.name}}
{{sender.title}}
{{sender.calendar_link}}

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        "t1_value_first": {
            "subject_a": "2-minute AI readiness check for {{lead.company}}",
            "subject_b": "{{lead.first_name}} - quick resource for {{lead.industry}} leaders",
            "body": """Hi {{lead.first_name}},

I put together a 2-minute "AI Readiness" audit for {{lead.industry}} leaders.

It covers the 3 biggest low-hanging fruit automation wins we're seeing right now—ones that typically save 10-20 hours per week per team member.

Mind if I send the link over?

(No pitch, no 30-minute demo request—just a quick self-assessment.)

Best,
{{sender.name}}
{{sender.title}}
ChiefAIOfficer.com

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        "t2_tech_stack": {
            "subject_a": "{{lead.first_name}} - AI for {{lead.company}}'s tech stack",
            "subject_b": "AI integration for {{lead.industry}} teams",
            "body": """Hi {{lead.first_name}},

I noticed {{lead.company}} is in the {{lead.industry}} space—we actually have a specific AI integration playbook for that stack.

Most {{lead.title}} roles I talk to are seeing two blockers:
1. The CTO is buried in legacy tech maintenance
2. No dedicated AI strategy lead to drive implementation

We bridge that gap as your Fractional Chief AI Officer—moving from "AI pilot" to production workflows in 90 days.

What teams like yours are automating:
- Lead enrichment and qualification (from raw data to booked meetings)
- Document processing and extraction (invoices, contracts, reports)
- Customer support triage (route, respond, escalate)

Would it be helpful if I shared the AI playbook we're seeing work best for {{lead.industry}}?

Cheers,
{{sender.name}}
{{sender.title}}
{{sender.calendar_link}}

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        "t2_ops_efficiency": {
            "subject_a": "{{lead.company}}'s operational efficiency",
            "subject_b": "{{lead.first_name}} - cutting {{lead.company}}'s overhead",
            "body": """Hi {{lead.first_name}},

The teams we work with are seeing 40-60% time savings on operational tasks using AI automation.

Specifically:
- One 150-person firm saved 300+ hours in 30 days on administrative work
- A 7-person pilot team saw 27% productivity boost in the first month
- AI now handles the work of 20+ staff in Operations at one of our clients

The pattern: start with high-volume, low-complexity tasks (data entry, scheduling, reporting), prove ROI in 30 days, then expand.

We call it the M.A.P. framework: Measure, Automate, Prove.

Open to a brief sync, or should I just send over a one-pager for now?

Cheers,
{{sender.name}}
{{sender.title}}
{{sender.calendar_link}}

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        "t2_innovation_champion": {
            "subject_a": "AI transformation at {{lead.company}}",
            "subject_b": "{{lead.first_name}} - building the AI Council",
            "body": """Hi {{lead.first_name}},

75%+ of AI pilots stall before ROI is proven.

The root cause we see: insufficient governance and process integration. CFOs see spend but not savings. Teams focus on "AI chatbots" instead of operational transformation.

We fix this by building an AI Council inside your company—internal champions from every department who drive adoption from within.

Our 90-day approach:
1. Day 1: Executive bootcamp (your team leaves AI-ready)
2. Weeks 2-8: We co-pilot with your AI Council, build the workflows
3. Weeks 9-12: Measure ROI, hand off the playbook

If the M.A.P. cycle doesn't deliver tangible savings, you don't pay the next phase.

Mind if I send over a 2-minute video on how we do this?

Cheers,
{{sender.name}}
{{sender.title}}
ChiefAIOfficer.com

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        "t3_quick_win": {
            "subject_a": "Quick idea for {{lead.company}}",
            "subject_b": "{{lead.first_name}} - one workflow to automate",
            "body": """Hi {{lead.first_name}},

Most {{lead.industry}} teams I talk to have one workflow that eats up way too much time—usually something like data entry, reporting, or lead research.

We help companies like {{lead.company}} automate that one thing first. No 6-month project. Just pick the biggest time-waster and fix it.

Example: A 25-person {{lead.industry}} company automated their weekly reporting and got 8 hours back per person, per month.

Worth a quick look?

Reply "yes" and I'll send a 2-minute breakdown of how we do it.

Best,
{{sender.name}}
{{sender.title}}
ChiefAIOfficer.com

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        "t3_time_savings": {
            "subject_a": "{{lead.first_name}} - 10 hours back per week",
            "subject_b": "What if {{lead.company}}'s admin work did itself?",
            "body": """Hi {{lead.first_name}},

The teams I work with typically waste 10-15 hours per week on tasks that should be automated: data entry, status updates, scheduling, and reporting.

We use AI agents to handle that—not a "chatbot" but actual workflow automation that runs 24/7.

Quick wins we see for {{lead.industry}} teams:
- Auto-updating spreadsheets and dashboards
- Lead research done overnight (you wake up to qualified lists)
- Follow-up emails sent at the right time, automatically

No huge IT project. Start with one workflow, prove it works, expand from there.

Should I send over a quick video showing how this works for teams your size?

Best,
{{sender.name}}
{{sender.title}}
ChiefAIOfficer.com

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        "t3_competitor_fomo": {
            "subject_a": "What {{lead.industry}} teams are automating",
            "subject_b": "{{lead.first_name}} - how competitors are scaling",
            "body": """Hi {{lead.first_name}},

I've been working with a few {{lead.industry}} companies lately, and there's a pattern:

The ones pulling ahead are automating the "invisible work"—the research, the data entry, the follow-ups that eat up 40-60% of everyone's week.

What they're automating:
- Lead research and scoring (AI does it overnight)
- Proposal drafts and first-pass content
- Client onboarding workflows
- Reporting and status updates

Not asking you to rip out your tech stack. Just add a layer of AI that handles the repetitive stuff.

Curious if {{lead.company}} has looked into this yet?

Just reply "show me"—I'll send a quick breakdown of what we're seeing work.

Best,
{{sender.name}}
{{sender.title}}
ChiefAIOfficer.com

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        "t3_diy_resource": {
            "subject_a": "Free AI checklist for {{lead.industry}}",
            "subject_b": "{{lead.first_name}} - quick resource for small teams",
            "body": """Hi {{lead.first_name}},

I put together a 1-page checklist of the 5 "quick win" AI automations that work best for {{lead.industry}} teams under 50 people.

No fluff, no 30-minute demo required—just actionable stuff you can implement yourself or hand to your ops person.

Includes:
- Top 5 workflows to automate first (and why)
- Tools that work for small budgets (under $100/month)
- Common mistakes to avoid

Mind if I send it over?

(No strings attached—it's genuinely useful even if we never talk.)

Best,
{{sender.name}}
{{sender.title}}
ChiefAIOfficer.com

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        }
    }

    # =========================================================================
    # HoS-Approved Follow-Up Sequence (2 steps: value-first + breakup)
    # =========================================================================
    FOLLOWUP_TEMPLATES = [
        {
            "delay_days": 3,
            "subject": "Re: {{original_subject}}",
            "body": """Hi {{lead.first_name}},

Following up on my note from earlier this week.

I put together a 2-minute "AI Readiness" audit specifically for {{lead.industry}} leaders.

It covers the 3 biggest low-hanging fruit automation wins we're seeing right now—ones that typically save 10-20 hours per week per team member.

Mind if I send the link over?

(No pitch, no 30-minute demo request—just a quick self-assessment you can complete in under 3 minutes.)

Best,
{{sender.name}}
{{sender.title}}
ChiefAIOfficer.com

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        {
            "delay_days": 7,
            "subject": "Closing the loop / {{lead.company}}",
            "body": """Hi {{lead.first_name}},

I haven't heard back, so I'm assuming AI implementation isn't a top-three priority for {{lead.company}} this quarter.

I'll take this off my follow-up list.

If things change down the road—whether it's a new budget cycle, a strategic shift, or just curiosity—you know where to find me.

Wishing you and the {{lead.company}} team continued success.

Best,
{{sender.name}}
{{sender.title}}
ChiefAIOfficer.com

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        }
    ]

    # =========================================================================
    # HoS-Aligned Cadence Templates (keyed by cadence action type)
    # Used by dispatch_cadence() in OPERATOR agent for Steps 3/5/7/8
    # =========================================================================
    CADENCE_TEMPLATES = {
        "value_followup": {
            "subject": "{{lead.first_name}} - quick resource",
            "body": """Hi {{lead.first_name}},

Following up on my note from earlier this week.

I put together a 2-minute "AI Readiness" audit specifically for {{lead.industry}} leaders.

It covers the 3 biggest low-hanging fruit automation wins we're seeing right now—ones that typically save 10-20 hours per week per team member.

Mind if I send the link over?

(No pitch, no 30-minute demo request—just a quick self-assessment you can complete in under 3 minutes.)

Best,
{{sender.name}}
{{sender.title}}
ChiefAIOfficer.com

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        "social_proof": {
            "subject": "Case study for {{lead.company}}",
            "body": """Hi {{lead.first_name}},

Following up—I thought you'd like to see how we helped a similar {{lead.industry}} company.

Quick stats:
- 27% productivity boost in 30 days
- 300+ hours saved from a 7-person pilot team
- Now expanding AI-powered workflows company-wide

The playbook we used might be directly applicable to {{lead.company}}.

Want me to share the one-pager?

Best,
{{sender.name}}
{{sender.title}}
{{sender.calendar_link}}

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        "breakup": {
            "subject": "Closing the loop / {{lead.company}}",
            "body": """Hi {{lead.first_name}},

I haven't heard back, so I'm assuming AI implementation isn't a top-three priority for {{lead.company}} this quarter.

I'll take this off my follow-up list.

If things change down the road—whether it's a new budget cycle, a strategic shift, or just curiosity—you know where to find me.

Wishing you and the {{lead.company}} team continued success.

Best,
{{sender.name}}
{{sender.title}}
ChiefAIOfficer.com

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
        "close": {
            "subject": "Last note from me, {{lead.first_name}}",
            "body": """Hi {{lead.first_name}},

I've reached out a couple of times about AI automation for {{lead.company}}.

Not trying to be a pest—just want to know where you stand:

- Yes: Let's talk—reply and I'll send a calendar link
- No: Not a fit—I'll remove you from my list
- Not yet: Bad timing—tell me when to check back

One word is all I need.

Best,
{{sender.name}}
{{sender.title}}

---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"""
        },
    }

    def __init__(self):
        self.sender_info = {
            "name": "Dani Apgar",
            "title": "Chief AI Officer",
            "company": "ChiefAIOfficer.com",
            "calendar_link": "https://caio.cx/ai-exec-briefing-call"
        }

    def _select_template(self, lead: Dict[str, Any]) -> str:
        """Select appropriate template based on lead ICP tier and source."""
        source_type = lead.get("source_type", "")
        recommended = lead.get("recommended_campaign", "")

        # Use recommended campaign if it matches a valid template
        if recommended and recommended in self.TEMPLATES:
            return recommended

        # Website visitors keep their template
        if source_type == "website_visitor":
            return "t1_value_first"

        # Hiring trigger detection
        if lead.get("hiring_signal"):
            return "t1_hiring_trigger"

        # Route by ICP tier
        tier = lead.get("icp_tier", "tier_3")
        TIER_TEMPLATES = {
            "tier_1": ["t1_executive_buyin", "t1_industry_specific", "t1_value_first"],
            "tier_2": ["t2_tech_stack", "t2_ops_efficiency", "t2_innovation_champion"],
            "tier_3": ["t3_quick_win", "t3_time_savings", "t3_competitor_fomo", "t3_diy_resource"],
        }
        templates = TIER_TEMPLATES.get(tier, TIER_TEMPLATES["tier_3"])
        idx = hash(lead.get("email", "")) % len(templates)
        return templates[idx]

    def _render_template(self, template_str: str, variables: Dict[str, Any]) -> str:
        """Render a Jinja2 template with variables."""
        try:
            template = Template(template_str)
            return template.render(**variables)
        except Exception as e:
            console.print(f"[yellow]Template rendering warning: {e}[/yellow]")
            return template_str

    def _build_template_variables(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Build template variables from lead data."""
        return {
            "lead": {
                "first_name": lead.get("first_name", lead.get("name", "").split()[0] if lead.get("name") else "there"),
                "last_name": lead.get("last_name", ""),
                "name": lead.get("name", ""),
                "title": lead.get("title", ""),
                "company": lead.get("company", "your company"),
                "location": lead.get("location", ""),
                "industry": lead.get("industry", lead.get("company", {}).get("industry", "") if isinstance(lead.get("company"), dict) else ""),
            },
            "source": {
                "type": lead.get("source_type", ""),
                "name": lead.get("source_name", ""),
                "url": lead.get("source_url", "")
            },
            "engagement": {
                "action": lead.get("engagement_action", ""),
                "content": lead.get("engagement_content", ""),
                "timestamp": lead.get("engagement_timestamp", "")
            },
            "context": {
                "competitor": lead.get("source_name", "competitors"),
                "topics": lead.get("personalization_hooks", []),
                "pain_points": [],
                "angle": lead.get("recommended_campaign", ""),
                "original_subject": lead.get("original_subject", "my earlier note"),
            },
            "original_subject": lead.get("original_subject", "my earlier note"),
            "company": {
                "size": lead.get("company_size", 0),
                "industry": lead.get("industry", ""),
                "tech_stack": []
            },
            "sender": self.sender_info
        }

    def craft_cadence_followup(
        self,
        action_type: str,
        lead_data: Dict[str, Any],
        step_num: int = 0,
        day_num: int = 0,
    ) -> Optional[Dict[str, str]]:
        """
        Generate follow-up email for a cadence step.

        Args:
            action_type: Cadence action (value_followup, social_proof, breakup, close)
            lead_data: Lead info (first_name, last_name, company, title, email, etc.)
            step_num: Cadence step number (for logging)
            day_num: Cadence day number (for logging)

        Returns:
            Dict with "subject" and "body" keys, or None if template not found.
        """
        template = self.CADENCE_TEMPLATES.get(action_type)
        if not template:
            return None

        variables = self._build_template_variables(lead_data)

        subject = self._render_template(template["subject"], variables)
        body = self._render_template(template["body"], variables)

        return {
            "subject": subject,
            "body": body,
            "action_type": action_type,
            "step": step_num,
            "day": day_num,
        }

    def generate_email(self, lead: Dict[str, Any], template_name: str = None) -> Dict[str, Any]:
        """Generate a personalized email for a single lead."""

        if not template_name:
            template_name = self._select_template(lead)

        template = self.TEMPLATES.get(template_name, self.TEMPLATES["t1_executive_buyin"])
        variables = self._build_template_variables(lead)

        # Render both A/B variants
        subject_a = self._render_template(template["subject_a"], variables)
        subject_b = self._render_template(template["subject_b"], variables)
        body = self._render_template(template["body"], variables)

        return {
            "lead_id": lead.get("lead_id", ""),
            "email": lead.get("email", ""),
            "template": template_name,
            "subject_a": subject_a,
            "subject_b": subject_b,
            "body": body,
            "personalization_level": 3 if lead.get("icp_tier") == "tier_1" else 2
        }

    def generate_sequence(self, lead: Dict[str, Any], template_name: str = None) -> List[EmailStep]:
        """Generate a full email sequence for a lead."""

        if not template_name:
            template_name = self._select_template(lead)

        template = self.TEMPLATES.get(template_name, self.TEMPLATES["t1_executive_buyin"])
        variables = self._build_template_variables(lead)

        sequence = []

        # Step 1: Initial email
        sequence.append(EmailStep(
            step=1,
            delay_days=0,
            channel="email",
            subject_a=self._render_template(template["subject_a"], variables),
            subject_b=self._render_template(template["subject_b"], variables),
            body_a=self._render_template(template["body"], variables),
            body_b=self._render_template(template["body"], variables),
            personalization_level=3
        ))

        # Follow-up steps
        for i, followup in enumerate(self.FOLLOWUP_TEMPLATES, start=2):
            sequence.append(EmailStep(
                step=i,
                delay_days=followup["delay_days"],
                channel="email",
                subject_a=self._render_template(followup["subject"], variables),
                subject_b=self._render_template(followup["subject"], variables),
                body_a=self._render_template(followup["body"], variables),
                body_b=self._render_template(followup["body"], variables),
                personalization_level=2
            ))

        return sequence

    def create_campaign(
        self,
        leads: List[Dict[str, Any]],
        segment: str,
        campaign_type: str = None
    ) -> Campaign:
        """Create a full campaign from a list of leads."""
        if not leads:
            return None

        # Calculate campaign metadata
        avg_icp_score = sum(l.get("icp_score", 0) for l in leads) / len(leads)
        avg_intent_score = sum(l.get("intent", {}).get("score", 0) for l in leads) / len(leads)

        # Determine campaign type if not provided
        if not campaign_type:
            campaign_type = "t1_executive_buyin"

        print(f"Creating {campaign_type} campaign for {len(leads)} leads (Segment: {segment})")

        processed_leads = []
        skipped_leads = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Generating emails...", total=len(leads))

            for lead in leads:
                # Validation: Check critical fields
                critical_missing = []
                if not lead.get("email"): critical_missing.append("email")
                if not lead.get("first_name"): critical_missing.append("first_name")
                if not lead.get("company_name") and not lead.get("company"): critical_missing.append("company")

                if critical_missing:
                    reason = f"Missing critical fields: {', '.join(critical_missing)}"
                    skipped_leads.append({"email": lead.get("email", "unknown"), "reason": reason})
                    progress.advance(task)
                    continue

                # Generate sequence
                sequence = self.generate_sequence(lead, campaign_type)
                if sequence:
                    lead["sequence"] = sequence
                    processed_leads.append(lead)

                progress.advance(task)

        if skipped_leads:
            print(f"Skipped {len(skipped_leads)} leads due to missing data.")

        return Campaign(
            campaign_id=f"camp_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name=f"{segment.title()} Campaign - {datetime.now().strftime('%B %d')}",
            segment=segment,
            campaign_type=campaign_type,
            leads=processed_leads,
            lead_count=len(processed_leads),
            sequence=[], # Sequence is now per-lead
            status="draft",
            created_at=datetime.now().isoformat(),
            avg_icp_score=avg_icp_score,
            avg_intent_score=avg_intent_score,
            metadata={
                "skipped_count": len(skipped_leads),
                "skipped_reasons": skipped_leads
            }
        )

    def process_segmented_file(self, input_file: Path, segment_filter: str = None) -> List[Campaign]:
        """
        Process a segmented leads file and create campaigns.

        Implements Dumb Zone protection via Frequent Intentional Compaction (FIC).
        Large batches are automatically processed in chunks to keep context <40%.
        """

        console.print(f"\n[bold blue]CRAFTER: Generating campaigns[/bold blue]")

        with open(input_file) as f:
            data = json.load(f)

        leads = data.get("leads", [])

        if segment_filter:
            leads = [l for l in leads if segment_filter in l.get("segment_tags", [])]

        # === DUMB ZONE PROTECTION ===
        # Check context zone before processing
        token_estimate = estimate_tokens(leads)
        context_zone = get_context_zone(token_estimate)

        if context_zone == ContextZone.SMART:
            console.print(f"[dim]Context zone: SMART ({token_estimate:,} tokens) - optimal processing[/dim]")
        elif context_zone == ContextZone.CAUTION:
            console.print(f"[yellow]Context zone: CAUTION ({token_estimate:,} tokens) - enabling batch mode[/yellow]")
        elif context_zone in [ContextZone.DUMB, ContextZone.CRITICAL]:
            console.print(f"[red]Context zone: {context_zone.value.upper()} ({token_estimate:,} tokens)[/red]")
            console.print(f"[yellow]   Large batch detected. Compacting and batching to stay in Smart Zone.[/yellow]")

            # Compact the lead batch for overview
            compacted = compact_lead_batch(leads, max_leads=20)
            if compacted['compacted']:
                console.print(f"[dim]   Compacted {compacted['total_count']} leads to {compacted['sample_count']} for analysis[/dim]")
                console.print(f"[dim]   Tier distribution: {compacted['tier_distribution']}[/dim]")

        # Group leads by tier and campaign type
        groups = {}
        for lead in leads:
            tier = lead.get("icp_tier", "tier_4")
            campaign_type = lead.get("recommended_campaign", "t1_executive_buyin")
            key = f"{tier}_{campaign_type}"

            if key not in groups:
                groups[key] = []
            groups[key].append(lead)

        campaigns = []
        failed_segments = []

        with Progress() as progress:
            task = progress.add_task("Creating campaigns...", total=len(groups))

            for segment, segment_leads in groups.items():
                if "disqualified" in segment:
                    progress.update(task, advance=1)
                    continue

                try:
                    campaign_type = segment.split("_", 1)[1] if "_" in segment else "t1_executive_buyin"

                    # === BATCH PROCESSING FOR DUMB ZONE PROTECTION ===
                    # If segment is large, process in batches to stay in Smart Zone
                    if len(segment_leads) > SMART_ZONE_BATCH_SIZE:
                        console.print(f"[dim]   Batching {len(segment_leads)} leads in {segment} (batch size: {SMART_ZONE_BATCH_SIZE})[/dim]")

                        for batch_idx in range(0, len(segment_leads), SMART_ZONE_BATCH_SIZE):
                            batch = segment_leads[batch_idx:batch_idx + SMART_ZONE_BATCH_SIZE]
                            batch_num = batch_idx // SMART_ZONE_BATCH_SIZE + 1
                            batch_segment = f"{segment}_batch{batch_num}"

                            campaign = self.create_campaign(batch, batch_segment, campaign_type)
                            campaigns.append(campaign)

                            log_event(EventType.CAMPAIGN_CREATED, {
                                "campaign_id": campaign.campaign_id,
                                "campaign_name": campaign.name,
                                "lead_count": campaign.lead_count,
                                "segment": batch_segment,
                                "campaign_type": campaign_type,
                                "batch_processing": True,
                                "batch_number": batch_num
                            })
                    else:
                        # Normal processing for smaller segments
                        campaign = self.create_campaign(segment_leads, segment, campaign_type)
                        campaigns.append(campaign)

                        log_event(EventType.CAMPAIGN_CREATED, {
                            "campaign_id": campaign.campaign_id,
                            "campaign_name": campaign.name,
                            "lead_count": campaign.lead_count,
                            "segment": segment,
                            "campaign_type": campaign_type
                        })

                except Exception as e:
                    failed_segments.append(segment)
                    schedule_retry(
                        operation_name="campaign_creation",
                        payload={
                            "segment": segment,
                            "lead_count": len(segment_leads),
                            "input_file": str(input_file)
                        },
                        error=e,
                        policy_name="campaign_delivery_failure",
                        metadata={"segment": segment}
                    )
                    console.print(f"[yellow]Failed to create campaign for {segment}: {e}[/yellow]")

                progress.update(task, advance=1)

        if failed_segments:
            send_warning(
                "Campaign Creation Partially Failed",
                f"{len(failed_segments)} campaign segments failed and have been queued for retry.",
                {"failed_segments": failed_segments, "success_count": len(campaigns)}
            )

        console.print(f"[green]Created {len(campaigns)} campaigns[/green]")

        return campaigns

    def save_campaigns(self, campaigns: List[Campaign], output_dir: Optional[Path] = None) -> Path:
        """Save campaigns to JSON file."""

        if output_dir is None:
            output_dir = Path(__file__).parent.parent / ".hive-mind" / "campaigns"

        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"campaigns_{timestamp}.json"
        output_path = output_dir / filename

        campaigns_data = [asdict(c) for c in campaigns]

        # Calculate totals
        total_leads = sum(c.lead_count for c in campaigns)

        with open(output_path, "w") as f:
            json.dump({
                "created_at": datetime.now(timezone.utc).isoformat(),
                "campaign_count": len(campaigns),
                "total_leads": total_leads,
                "status": "pending_review",
                "campaigns": campaigns_data
            }, f, indent=2)

        console.print(f"[green]Saved campaigns to {output_path}[/green]")

        return output_path

    def print_summary(self, campaigns: List[Campaign]):
        """Print campaign summary."""

        table = Table(title="Campaign Summary")
        table.add_column("Campaign", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Leads", style="yellow")
        table.add_column("Avg ICP", style="magenta")
        table.add_column("Status", style="blue")

        for campaign in campaigns:
            table.add_row(
                campaign.name[:40],
                campaign.campaign_type[:20],
                str(campaign.lead_count),
                f"{campaign.avg_icp_score:.0f}",
                campaign.status
            )

        console.print(table)

        total_leads = sum(c.lead_count for c in campaigns)
        console.print(f"\n[bold]Total: {len(campaigns)} campaigns, {total_leads} leads[/bold]")


def main():
    parser = argparse.ArgumentParser(description="Generate email campaigns from segmented leads")
    parser.add_argument("--input", type=Path, help="Input segmented leads JSON file")
    parser.add_argument("--segment", help="Filter by segment tag")
    parser.add_argument("--template", choices=list(CampaignCrafter.TEMPLATES.keys()),
                        help="Force specific template")

    args = parser.parse_args()

    if not args.input:
        # Find latest segmented file
        segmented_dir = Path(__file__).parent.parent / ".hive-mind" / "segmented"
        if segmented_dir.exists():
            files = sorted(segmented_dir.glob("*.json"), reverse=True)
            if files:
                args.input = files[0]

    if not args.input or not args.input.exists():
        console.print("[red]No input file specified and no segmented files found.[/red]")
        console.print("Run: python execution/segmentor_classify.py first")
        sys.exit(1)

    try:
        crafter = CampaignCrafter()
        campaigns = crafter.process_segmented_file(args.input, args.segment)

        if campaigns:
            crafter.print_summary(campaigns)
            output_path = crafter.save_campaigns(campaigns)

            console.print(f"\n[bold green]Campaign generation complete![/bold green]")
            console.print(f"Campaigns are [yellow]pending_review[/yellow]")
            console.print(f"\nNext step: Submit for AE review via GATEKEEPER")
            console.print(f"  python execution/gatekeeper_queue.py --input {output_path}")

    except Exception as e:
        console.print(f"[red]Campaign generation failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
