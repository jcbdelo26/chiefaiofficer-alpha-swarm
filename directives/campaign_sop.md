# ✍️ Campaign SOP
# Standard Operating Procedure for CRAFTER Agent

---

## Overview

This directive governs campaign creation for the Alpha Swarm. CRAFTER generates hyper-personalized email campaigns based on deep lead context, then queues them for AE approval via GATEKEEPER.

---

## Campaign Types

### 1. Competitor Displacement
**Trigger**: Lead follows/engages with competitor
**Angle**: Show what they're missing

### 2. Event Follow-Up
**Trigger**: Attended relevant event
**Angle**: Continue the conversation

### 3. Thought Leadership Response
**Trigger**: Commented on industry post
**Angle**: Respond to their viewpoint

### 4. Community Outreach
**Trigger**: Member of relevant group
**Angle**: Peer-to-peer connection

### 5. Website Visitor
**Trigger**: RB2B identified visitor
**Angle**: Address what they explored

---

## Template Library

### Template Structure

```
templates/
├── competitor_displacement/
│   ├── gong_users.jinja2
│   ├── clari_users.jinja2
│   └── generic.jinja2
├── event_followup/
│   ├── webinar.jinja2
│   ├── conference.jinja2
│   └── workshop.jinja2
├── thought_leadership/
│   ├── commenter.jinja2
│   └── liker.jinja2
├── community/
│   ├── group_member.jinja2
│   └── shared_connection.jinja2
└── website_visitor/
    ├── pricing_page.jinja2
    └── product_page.jinja2
```

### Template Variables

**Lead Variables**:
```
{{lead.first_name}}        - First name
{{lead.last_name}}         - Last name
{{lead.full_name}}         - Full name
{{lead.title}}             - Job title
{{lead.company}}           - Company name
{{lead.location}}          - Location
```

**Source Variables**:
```
{{source.type}}            - competitor_follower, event_attendee, etc.
{{source.name}}            - Competitor/Event/Group name
{{source.url}}             - Source URL
```

**Engagement Variables**:
```
{{engagement.action}}      - commented, liked, registered, etc.
{{engagement.content}}     - Their actual comment
{{engagement.timestamp}}   - When they engaged
```

**Context Variables**:
```
{{context.pain_points}}    - List of inferred pain points
{{context.topics}}         - Topics they care about
{{context.competitor}}     - Competitor they use/follow
{{context.angle}}          - Recommended approach
```

**Company Variables**:
```
{{company.size}}           - Employee count
{{company.industry}}       - Industry
{{company.tech_stack}}     - Technologies used
{{company.funding}}        - Last funding round
{{company.news}}           - Recent news headlines
```

**Chris/Sender Variables**:
```
{{sender.name}}            - Chris Daigle
{{sender.title}}           - CEO
{{sender.company}}         - Chiefaiofficer.com
{{sender.calendar_link}}   - Booking link
```

---

## Sample Templates

### Competitor Displacement (Gong Users)

```jinja2
Subject: {{lead.first_name}}, what Gong isn't showing you

Hi {{lead.first_name}},

I noticed you follow Gong's updates on LinkedIn - smart move staying current on conversation intelligence.

Here's what I've been hearing from RevOps leaders like yourself at {{company.size | company_tier}}-sized {{company.industry}} companies:

"Gong shows us what happened on calls... but we still can't predict what's going to happen next quarter."

At Chiefaiofficer.com, we're building the layer ABOVE conversation intelligence - connecting call insights to pipeline predictions to rep coaching in one AI-native system.

{% if context.competitor %}
Given you're already thinking about {{context.topics[0]}}, this might resonate.
{% endif %}

Worth a 15-min look? {{sender.calendar_link}}

Best,
{{sender.name}}
{{sender.title}}, {{sender.company}}

P.S. - No generic demo. I'll show you exactly how this would work for {{lead.company}}.
```

### Event Follow-Up (Webinar)

```jinja2
Subject: Quick follow-up from {{source.name}}

Hi {{lead.first_name}},

I saw you attended {{source.name}} - great session on {{context.topics[0]}}.

{% if engagement.content %}
Your question about "{{engagement.content | truncate(50)}}" particularly stood out. We're actually solving that exact problem for RevOps teams.
{% else %}
The discussion around {{context.topics[0]}} is exactly where we focus at Chiefaiofficer.com.
{% endif %}

Would love to share how {{lead.company}} could apply some of these concepts to {{context.pain_points[0] | lower}}.

15 minutes this week? {{sender.calendar_link}}

{{sender.name}}
```

### Thought Leadership (Commenter)

```jinja2
Subject: Your take on {{context.topics[0] | truncate(30)}}

{{lead.first_name}},

I came across your comment on LinkedIn about {{context.topics[0]}}:

"{{engagement.content | truncate(100)}}"

Couldn't agree more. {% if context.pain_points %}The {{context.pain_points[0]}} challenge is real for most RevOps teams.{% endif %}

We're working with {{company.size | similar_companies}} companies addressing exactly this. Curious if you'd find our approach interesting?

Quick 15-min chat? {{sender.calendar_link}}

{{sender.name}}
P.S. - Would love to compare notes on your experience at {{lead.company}}.
```

---

## Sequence Structure

### Standard 4-Touch Sequence

**Email 1 - Day 0**: Initial outreach
- Personalized hook + context
- Clear value prop
- Soft CTA

**Email 2 - Day 3**: Value add
- Share relevant content
- Reference their situation
- Remind of CTA

**Email 3 - Day 7**: Social proof
- Case study or quote
- Results metrics
- Medium CTA

**Email 4 - Day 14**: Break-up
- Acknowledge busy
- Offer future value
- Last CTA

### Aggressive 7-Touch (Tier 1 Only)

Additional touches:
- LinkedIn connection request (Day 1)
- LinkedIn voice note (Day 5)
- LinkedIn InMail (Day 10)

---

## Personalization Levels

### Level 1: Basic (All leads)
- First name
- Company name
- Title

### Level 2: Contextual (Tier 2+)
- Source type
- Engagement action
- Industry-specific

### Level 3: Deep (Tier 1)
- Comment reference
- Company news
- Tech stack specific
- Competitor displacement

---

## Subject Line Library

### Competitor Displacement
- "{{lead.first_name}}, what {{context.competitor}} isn't showing you"
- "Beyond {{context.competitor}} for {{lead.company}}"
- "{{lead.first_name}}, quick question about your {{context.competitor}} setup"

### Event Follow-Up
- "Quick follow-up from {{source.name}}"
- "{{lead.first_name}}, loved your question at {{source.name}}"
- "{{source.name}} → next step for {{lead.company}}?"

### Thought Leadership
- "Your take on {{context.topics[0] | truncate(20)}}"
- "{{lead.first_name}}, re: your comment on LinkedIn"
- "Saw your thoughts on {{context.topics[0] | truncate(15)}}..."

### Website Visitor
- "You were on our site earlier"
- "{{lead.first_name}}, following up on your visit"
- "Quick question about what you explored"

---

## A/B Testing

### Standard A/B Template

For each campaign, generate 2 variants:
- **Variant A**: More formal, benefit-focused
- **Variant B**: More casual, curiosity-driven

### Subject Line A/B
Always test:
- Question vs Statement
- Short vs Medium length
- Name included vs not

### Track Metrics
- Open rate
- Reply rate
- Positive reply rate
- Meeting booked rate

---

## Tone Guidelines

### Voice
- Confident but not arrogant
- Helpful not pushy
- Peer-to-peer not salesy
- Data-informed not vague

### Avoid
- "Just checking in"
- "I wanted to reach out"
- "Hope you're doing well"
- Generic value propositions
- Excessive exclamation marks

### Embrace
- Specific references
- Genuine curiosity
- Clear asks
- Relevant stats

---

## Campaign Output Schema

```json
{
  "campaign_id": "uuid",
  "segment": "tier1_gong_users",
  "campaign_type": "competitor_displacement",
  "created_at": "2026-01-12T16:00:00Z",
  "leads": [
    {
      "lead_id": "uuid",
      "email": "john@company.com"
    }
  ],
  "lead_count": 50,
  "sequence": [
    {
      "step": 1,
      "delay_days": 0,
      "channel": "email",
      "subject_a": "...",
      "subject_b": "...",
      "body_a": "...",
      "body_b": "...",
      "personalization_level": 3
    }
  ],
  "status": "pending_review",
  "assigned_ae": null,
  "metrics": {
    "avg_icp_score": 87,
    "avg_intent_score": 72
  }
}
```

---

## GATEKEEPER Handoff

### Queue for Review

```python
def queue_for_review(campaign: dict) -> str:
    """
    Submit campaign to GATEKEEPER for AE review
    Returns: review_queue_id
    """
    queue_entry = {
        "campaign_id": campaign["campaign_id"],
        "segment": campaign["segment"],
        "lead_count": campaign["lead_count"],
        "priority": calculate_priority(campaign),
        "preview_url": generate_preview(campaign),
        "status": "pending_review",
        "queued_at": datetime.utcnow().isoformat()
    }
    return add_to_queue(queue_entry)
```

### Priority Calculation

| Segment Tier | Base Priority |
|--------------|---------------|
| Tier 1 | P0 (review within 4 hours) |
| Tier 2 | P1 (review within 24 hours) |
| Tier 3 | P2 (review within 48 hours) |

---

*Directive Version: 1.0*
*Last Updated: 2026-01-12*
*Owner: CRAFTER Agent*
