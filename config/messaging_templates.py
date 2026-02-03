#!/usr/bin/env python3
"""
Messaging Templates - Chief AI Officer Alpha Swarm
===================================================

Email and LinkedIn message templates based on:
- Outbound Proposal & Example Strategy
- AI SDR Playbook methodology
- LinkedIn BDR Campaign templates

Angles:
- Angle A: "AI Noise" (Direct/Relatable)
- Angle B: "Efficiency Gap" (Analytical)
- Angle C: "Fractional Advantage" (Authority)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class Channel(Enum):
    EMAIL = "email"
    LINKEDIN = "linkedin"
    SMS = "sms"


class SequenceType(Enum):
    COLD_OUTBOUND = "cold_outbound"
    WARM_NURTURE = "warm_nurture"
    HOT_FAST_TRACK = "hot_fast_track"
    RE_ENGAGEMENT = "re_engagement"


# =============================================================================
# EMAIL TEMPLATES - COLD OUTBOUND (INSTANTLY)
# =============================================================================

COLD_EMAIL_SEQUENCES = {
    # Angle A: The "AI Noise" (Direct/Relatable)
    "ai_noise": {
        "description": "For leads showing AI overwhelm signals",
        "emails": [
            {
                "step": 1,
                "delay_days": 0,
                "subject": "{first_name}, your AI strategy",
                "body": """Hi {first_name},

Every {title} I talk to is overwhelmed by AI, but lacks a practical way to implement it.

"You need ChatGPT!"
"Automate everything!"
"Your competitors are using AI!"

But nobody's actually showing you WHERE to start or HOW to implement it without burning 6 months and $50k.

I work with {industry} companies like {company_name} to identify the 2-3 specific areas where automation will save 10+ hours/week immediately.

Worth a 5-minute chat to see where you're leaking time?

{signature}

P.S. No pitch, just a quick audit of your current ops to see if there's low-hanging fruit.""",
            },
            {
                "step": 2,
                "delay_days": 3,
                "subject": "Re: {first_name}, your AI strategy",
                "body": """Hi {first_name},

Quick follow-up - I know your inbox is probably flooded.

Last week I helped a {similar_company_type} cut their lead response time from 4 hours to 4 minutes with a simple automation.

No fancy AI. No expensive consultants. Just a smart workflow.

If you're curious, I can share exactly what we did in a 10-min call.

{signature}""",
            },
            {
                "step": 3,
                "delay_days": 4,
                "subject": "Quick question about {company_name}",
                "body": """Hi {first_name},

Genuine question - is AI even on your radar right now?

I ask because some {title}s I talk to are all-in on automation, while others have bigger fish to fry.

If it's not a priority, just let me know and I'll stop reaching out.

But if you ARE thinking about it, I'd love to share a 2-page roadmap I put together for {industry} companies.

Which is it for you?

{signature}""",
            },
            {
                "step": 4,
                "delay_days": 5,
                "subject": "Closing the loop",
                "body": """Hi {first_name},

I'll keep this short since I haven't heard back.

I'm going to assume the timing isn't right. Totally understand.

When you ARE ready to explore AI for {company_name}, here's what I'd suggest:
1. Start with ONE workflow that's eating 5+ hours/week
2. Automate that before touching anything else
3. Measure the ROI before expanding

Happy to help when the time is right. My inbox is always open.

{signature}""",
            },
        ],
    },
    
    # Angle B: The "Efficiency Gap" (Analytical)
    "efficiency_gap": {
        "description": "For leads with visible manual process pain",
        "emails": [
            {
                "step": 1,
                "delay_days": 0,
                "subject": "Observation: {company_name} manual processes",
                "body": """Hi {first_name},

I've been researching {industry} companies and noticed something interesting about {company_name}.

Most companies your size have what I call an "Efficiency Gap" - the difference between current operational costs and what they'd be with proper automation.

For {industry}, that gap is typically 15-25% of OpEx.

I put together a 2-page roadmap showing exactly where those savings come from. Want me to send it over?

{signature}""",
            },
            {
                "step": 2,
                "delay_days": 3,
                "subject": "The 15% question",
                "body": """Hi {first_name},

Quick thought experiment:

What would you do with an extra 15% operational budget?

That's what the average {industry} company saves when they automate:
- Lead qualification and routing
- Client onboarding workflows
- Reporting and data entry

I help {title}s identify their specific gap in about 30 minutes.

Open to a quick conversation?

{signature}""",
            },
            {
                "step": 3,
                "delay_days": 4,
                "subject": "Case study: {similar_company_type}",
                "body": """Hi {first_name},

Thought you might find this relevant.

Just finished working with a {similar_company_type} - similar size to {company_name}.

Before:
- 3 people on data entry (40 hours/week)
- Average lead response: 4 hours
- Manual reporting taking 2 days/month

After:
- 0 people on data entry
- Lead response under 5 minutes
- Reports generated automatically

The kicker? Took 6 weeks to implement, not 6 months.

Worth 15 minutes to see if we can replicate this for you?

{signature}""",
            },
            {
                "step": 4,
                "delay_days": 5,
                "subject": "Last note",
                "body": """Hi {first_name},

I'm guessing this either:
a) Landed at the wrong time
b) Isn't a priority right now
c) Got buried

Either way, I'll stop here.

When efficiency becomes top of mind for {company_name}, feel free to reach out. I've helped dozens of {industry} {title}s close their efficiency gap.

Best,
{signature}""",
            },
        ],
    },
    
    # Angle C: The "Fractional Advantage" (Authority)
    "fractional_advantage": {
        "description": "For leads who need strategic AI leadership",
        "emails": [
            {
                "step": 1,
                "delay_days": 0,
                "subject": "Chief AI Officer for {company_name}?",
                "body": """Hi {first_name},

Here's the reality most {title}s face:

You KNOW you need an AI strategy.
You CAN'T justify a $200k+ full-time hire.
You DON'T have time to figure it out yourself.

That's exactly why I created the Fractional Chief AI Officer model.

I work with 4-5 {industry} companies at a time, handling:
- AI tool selection and implementation
- Team training and change management
- Custom GPT and automation builds

All for a fraction of what you'd pay a full-time AI executive.

Reply "AI" and I'll send a quick video showing how this works in practice.

{signature}""",
            },
            {
                "step": 2,
                "delay_days": 3,
                "subject": "Re: Chief AI Officer for {company_name}?",
                "body": """Hi {first_name},

Following up on my last note about Fractional AI leadership.

Most {title}s I work with have the same 3 concerns:
1. "We've tried AI tools before and they didn't stick"
2. "My team doesn't have time for another initiative"
3. "How do we know what to prioritize?"

That's exactly what I solve. I'm not selling you software - I'm becoming your AI strategy partner.

15 minutes - I'll show you the exact roadmap I use with companies like yours.

{signature}""",
            },
            {
                "step": 3,
                "delay_days": 4,
                "subject": "The $200k alternative",
                "body": """Hi {first_name},

Quick math:

Full-time Chief AI Officer: $200-350k/year
Junior AI hire who doesn't know your industry: $80k + 6 months ramp time
"Figure it out yourself": 20+ hours/week of YOUR time

Fractional CAIO: Strategic AI leadership for a fraction of the above.

You get the executive guidance without the executive salary.

Worth a conversation?

{signature}""",
            },
            {
                "step": 4,
                "delay_days": 5,
                "subject": "Closing the loop",
                "body": """Hi {first_name},

Last note from me on this.

If AI isn't on the roadmap for {company_name} right now, I totally get it. Priorities shift.

But when you ARE ready to get serious about it, having a strategic partner who knows {industry} inside and out will save you months of trial and error.

My calendar's always open. Best of luck with everything.

{signature}""",
            },
        ],
    },
}


# =============================================================================
# LINKEDIN TEMPLATES
# =============================================================================

LINKEDIN_SEQUENCES = {
    "connection_request": {
        "templates": [
            {
                "variant": "general",
                "message": """Hi {first_name}, I came across your profile while researching leaders in the {industry} space. Your background in {role_focus} is impressive. Would love to connect and keep up with your work at {company_name}!""",
            },
            {
                "variant": "tech_specific",
                "message": """Hi {first_name}, saw your experience leading {company_name}. I'm currently helping {industry} companies streamline their operations with AI - thought we might have some good conversations to share. Would love to connect!""",
            },
            {
                "variant": "mutual_connection",
                "message": """Hi {first_name}, noticed we both know {mutual_connection}. I work with {industry} leaders on AI strategy and automation. Would love to add you to my network!""",
            },
        ],
    },
    "follow_up_sequence": [
        {
            "step": 1,
            "delay_days": 3,
            "trigger": "connection_accepted",
            "message": """Thanks for connecting, {first_name}!

I'm reaching out because I help {industry} {title}s automate their operations without the usual 6-month implementation nightmare.

Quick question: Is AI/automation even on your radar for {company_name} right now, or are there bigger fish to fry?""",
        },
        {
            "step": 2,
            "delay_days": 7,
            "trigger": "no_response",
            "message": """Wanted to bubble this up, {first_name}.

Just helped a {similar_company_type} cut their manual data entry by 80% in 4 weeks.

If you're curious what that would look like for {company_name}, happy to share the playbook over a quick call.

No pitch, just practical stuff you can use.""",
        },
        {
            "step": 3,
            "delay_days": 14,
            "trigger": "no_response",
            "message": """Hi {first_name}, I assume you're busy scaling {company_name}. Totally get it.

I'll stop reaching out so I don't clutter your inbox. If AI/automation ever becomes a priority, feel free to ping me.

Best of luck with everything!""",
        },
    ],
}


# =============================================================================
# WARM SEQUENCES (GOHIGHLEVEL)
# =============================================================================

WARM_NURTURE_SEQUENCES = {
    "email_reply_received": {
        "description": "When lead replies to cold email",
        "steps": [
            {
                "step": 1,
                "channel": "email",
                "delay_minutes": 5,
                "template": "reply_acknowledgment",
                "message": """Hi {first_name},

Thanks for getting back to me!

{personalized_response_to_their_reply}

I'd love to schedule a quick 15-minute call to discuss further. Here's my calendar: {calendar_link}

Or if you prefer, just reply with a couple times that work for you this week.

Looking forward to it,
{signature}""",
            },
            {
                "step": 2,
                "channel": "sms",
                "delay_hours": 2,
                "condition": "no_calendar_booking",
                "message": """Hi {first_name}, this is {sender_name} from Chief AI Officer. Just following up on your email about AI automation. Here's a quick link to grab time: {calendar_link}""",
            },
        ],
    },
    "meeting_booked": {
        "description": "When lead books a meeting",
        "steps": [
            {
                "step": 1,
                "channel": "email",
                "delay_minutes": 0,
                "template": "meeting_confirmation",
                "message": """Hi {first_name},

Great, you're all set for {meeting_date} at {meeting_time}!

Before we chat, it would help if you could think about:
1. The biggest manual task eating your team's time
2. Any AI tools you've tried (even if they didn't work)
3. Your #1 goal for the next 6 months

Looking forward to our conversation!

{signature}""",
            },
            {
                "step": 2,
                "channel": "sms",
                "delay_hours": 24,
                "condition": "meeting_tomorrow",
                "message": """Hi {first_name}! Quick reminder about our call tomorrow at {meeting_time}. Looking forward to discussing AI automation for {company_name}. - {sender_name}""",
            },
            {
                "step": 3,
                "channel": "sms",
                "delay_minutes": 15,
                "condition": "meeting_in_15_min",
                "message": """Hi {first_name}, we're on in 15 min! Here's the Zoom link: {zoom_link} - {sender_name}""",
            },
        ],
    },
}


# =============================================================================
# TEMPLATE PERSONALIZATION
# =============================================================================

@dataclass
class TemplateVariables:
    """Variables available for template personalization."""
    first_name: str
    last_name: str
    title: str
    company_name: str
    industry: str
    employee_count: Optional[int] = None
    pain_points: List[str] = field(default_factory=list)
    similar_company_type: Optional[str] = None
    mutual_connection: Optional[str] = None
    role_focus: Optional[str] = None
    signature: str = "Chris Daigle\nFractional Chief AI Officer\nchiefaiofficer.com"
    sender_name: str = "Chris"
    calendar_link: str = "https://calendly.com/chiefaiofficer"
    
    def to_dict(self) -> Dict:
        return {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "title": self.title,
            "company_name": self.company_name,
            "industry": self.industry,
            "employee_count": self.employee_count,
            "pain_points": self.pain_points,
            "similar_company_type": self.similar_company_type or f"similar {self.industry} company",
            "mutual_connection": self.mutual_connection or "",
            "role_focus": self.role_focus or self.title.lower(),
            "signature": self.signature,
            "sender_name": self.sender_name,
            "calendar_link": self.calendar_link,
        }


def render_template(template: str, variables: TemplateVariables) -> str:
    """Render a template with variables."""
    var_dict = variables.to_dict()
    
    result = template
    for key, value in var_dict.items():
        placeholder = "{" + key + "}"
        if placeholder in result:
            result = result.replace(placeholder, str(value) if value else "")
    
    return result


# =============================================================================
# SEQUENCE SELECTOR
# =============================================================================

def get_recommended_sequence(
    icp_tier: str,
    engagement_level: str,
    pain_points: Optional[List[str]] = None,
) -> Dict:
    """
    Get recommended messaging sequence based on lead profile.
    
    Args:
        icp_tier: A, B, C, D, or DISQUALIFIED
        engagement_level: cold, lukewarm, warm, hot
        pain_points: List of identified pain points
    
    Returns:
        Dict with sequence configuration
    """
    # Hot leads go to GHL immediately
    if engagement_level == "hot":
        return {
            "platform": "gohighlevel",
            "sequence_type": "hot_fast_track",
            "sequence_name": "meeting_booked" if "meeting" in str(pain_points).lower() else "email_reply_received",
            "priority": 1,
        }
    
    # Warm leads get nurture sequence
    if engagement_level == "warm":
        return {
            "platform": "gohighlevel",
            "sequence_type": "warm_nurture",
            "sequence_name": "email_reply_received",
            "priority": 2,
        }
    
    # Cold/Lukewarm go to Instantly
    if icp_tier == "A":
        angle = "ai_noise"
    elif icp_tier == "B":
        # Check for specific pain points
        if pain_points and any("manual" in pp.lower() or "process" in pp.lower() for pp in pain_points):
            angle = "efficiency_gap"
        else:
            angle = "ai_noise"
    else:
        angle = "fractional_advantage"
    
    return {
        "platform": "instantly",
        "sequence_type": "cold_outbound",
        "sequence_name": angle,
        "priority": 3 if icp_tier in ["A", "B"] else 4,
    }


# =============================================================================
# DEMO
# =============================================================================

def demo():
    """Demonstrate template rendering."""
    print("=" * 60)
    print("Messaging Template Demo")
    print("=" * 60)
    
    # Sample lead
    variables = TemplateVariables(
        first_name="Sarah",
        last_name="Chen",
        title="CEO",
        company_name="Bright Marketing Agency",
        industry="Marketing Agency",
        employee_count=85,
        pain_points=["manual data entry", "slow lead response"],
        similar_company_type="digital marketing agency",
    )
    
    # Get recommended sequence
    sequence_config = get_recommended_sequence(
        icp_tier="A",
        engagement_level="cold",
        pain_points=variables.pain_points,
    )
    
    print(f"\nRecommended Sequence: {sequence_config}")
    
    # Render first email
    sequence = COLD_EMAIL_SEQUENCES[sequence_config["sequence_name"]]
    first_email = sequence["emails"][0]
    
    print(f"\nSubject: {render_template(first_email['subject'], variables)}")
    print(f"\n{render_template(first_email['body'], variables)}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    demo()
