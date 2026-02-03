---
date: 2026-01-15
author: alpha_swarm
status: published
tags: [patterns, objections, sdr, automation]
related_docs:
  - directives/sdr_specifications.md
  - templates/objections/*.j2
---

# Pattern: Objection Handling Framework

> Proven response patterns for common SDR objections

---

## Overview

This document catalogs proven objection handling patterns for the SDR automation system. Each pattern references the corresponding Jinja2 template in `templates/objections/` and includes performance data when available.

**Canonical Reference:** `directives/sdr_specifications.md` Section 5.4 (Objection Escalation Matrix)

---

## Objection Categories

### Automated Responses (Full Automation)

| Objection | Template | Escalation | Key Principle |
|-----------|----------|------------|---------------|
| Not Interested | `soft_breakup.j2` | None | Graceful exit, leave door open |
| Bad Timing | `schedule_future.j2` | None | Capture future date, add to nurture |
| Need More Info | `send_resources.j2` | None | Provide value, no hard CTA |

### Supervised Responses (Partial Automation)

| Objection | Template | Escalation | Key Principle |
|-----------|----------|------------|---------------|
| Already Have Solution | `displacement_nurture.j2` | If Enterprise | Acknowledge, differentiate |
| Positive Interest | `book_meeting.j2` | If Tier 1 | Strike while hot, remove friction |

### Human-Only Responses (No Automation)

| Objection | Template | Escalation | Key Principle |
|-----------|----------|------------|---------------|
| Pricing Question | `value_framework.j2` | Always | Frame value before price |
| Technical Question | N/A | Always, route to SE | Accuracy critical |

---

## Pattern Details

### Pattern 1: Soft Breakup
**Template:** `templates/objections/soft_breakup.j2`
**Trigger:** Explicit "not interested" or similar

**Framework:**
1. Acknowledge their response respectfully
2. Express understanding (no pushback)
3. Leave door open for future
4. Remove from active sequence

**Do:**
- Keep it brief (2-3 sentences)
- Thank them for their time
- Offer easy re-engagement path

**Don't:**
- Ask why they're not interested
- Propose alternatives
- Send follow-ups after this

**Performance Data:**
| Metric | Value | Notes |
|--------|-------|-------|
| Re-engagement Rate | TBD | % who reply again within 6mo |
| Unsubscribe Rate | TBD | Should be near 0% |

---

### Pattern 2: Schedule Future
**Template:** `templates/objections/schedule_future.j2`
**Trigger:** "Not right now", "Maybe later", timing-related

**Framework:**
1. Acknowledge the timing constraint
2. Ask for specific future timeframe
3. Offer to reach back out
4. Add to timed nurture sequence

**Do:**
- Get a specific timeframe if possible
- Set calendar reminder
- Continue light-touch nurture

**Don't:**
- Push for immediate meeting anyway
- Add to aggressive sequence
- Forget to follow up

**Performance Data:**
| Metric | Value | Notes |
|--------|-------|-------|
| Future Conversion Rate | TBD | % who book after follow-up |
| Optimal Follow-up Window | TBD | Best delay before re-contact |

---

### Pattern 3: Displacement Nurture
**Template:** `templates/objections/displacement_nurture.j2`
**Trigger:** "We use [competitor]", "Already have a solution"

**Framework:**
1. Acknowledge current solution (validate their choice)
2. Position as complementary or evolution
3. Plant seed of differentiation
4. Add to displacement nurture track

**Competitor-Specific Angles:**
Reference `directives/icp_criteria.md` for displacement messaging:

| Current Solution | Angle |
|-----------------|-------|
| Gong | "Beyond conversation intelligence" |
| Clari | "Unified revenue intelligence" |
| Chorus | "Next-gen call analytics" |
| People.ai | "Activity data + AI insight" |

**Do:**
- Research their current tool usage
- Highlight unique differentiators
- Share relevant case study

**Don't:**
- Disparage their current solution
- Claim to "replace" everything
- Rush the displacement

**Performance Data:**
| Metric | Value | Notes |
|--------|-------|-------|
| Displacement Rate | TBD | % who switch within 12mo |
| Avg Nurture Duration | TBD | Time before conversion |

---

### Pattern 4: Send Resources
**Template:** `templates/objections/send_resources.j2`
**Trigger:** "Tell me more", "How does it work", information-seeking

**Framework:**
1. Thank them for their interest
2. Send relevant, valuable content
3. Soft CTA (not aggressive meeting push)
4. Queue follow-up in 2-3 days

**Resource Matching:**
| Interest Signal | Resource Type |
|----------------|---------------|
| General curiosity | Product overview |
| Technical question | Technical docs |
| ROI focus | Case study with metrics |
| Specific use case | Relevant demo video |

**Do:**
- Match resource to their specific question
- Personalize the resource selection
- Follow up to check if helpful

**Don't:**
- Send a wall of links
- Push for meeting in same email
- Send generic marketing materials

**Performance Data:**
| Metric | Value | Notes |
|--------|-------|-------|
| Resource Open Rate | TBD | % who engage with content |
| Progression Rate | TBD | % who advance to meeting |

---

### Pattern 5: Value Framework (Pricing)
**Template:** `templates/objections/value_framework.j2`
**Trigger:** "How much", "What's the cost", pricing questions

**Framework:**
1. Acknowledge the question positively
2. Frame pricing structure (without numbers)
3. Pivot to value and ROI
4. Propose meeting for tailored estimate

**Critical Rules:**
- **ALWAYS ESCALATE** - Pricing requires AE involvement
- Never provide specific pricing in automated responses
- Frame value before discussing investment

**Value Talking Points:**
- Rep productivity improvement
- Pipeline accuracy gains
- Time savings quantified
- ROI timeline (typically 90 days)

**Do:**
- Acknowledge pricing is a fair question
- Emphasize custom/tailored approach
- Connect to discovery call

**Don't:**
- Provide ballpark figures
- Use discounting language
- Promise specific outcomes

**Performance Data:**
| Metric | Value | Notes |
|--------|-------|-------|
| Meeting Book Rate | TBD | % who book after pricing Q |
| Deal Close Rate | TBD | Quality of pricing-triggered leads |

---

### Pattern 6: Book Meeting (Positive Interest)
**Template:** `templates/objections/book_meeting.j2`
**Trigger:** Positive buying signals, explicit interest

**Framework:**
1. Match their energy/enthusiasm
2. Provide frictionless booking (calendar link)
3. Offer alternative (manual scheduling)
4. Express genuine anticipation

**Automation Rules:**
- Tier 1 leads: Escalate to AE for personal outreach
- Tier 2-4: Automated response acceptable

**Do:**
- Respond quickly (SLA: 15 min for positive reply)
- Make booking dead simple
- Confirm receipt if they reply with times

**Don't:**
- Over-explain what the meeting covers
- Add unnecessary qualifiers
- Delay the response

**Performance Data:**
| Metric | Value | Notes |
|--------|-------|-------|
| Show Rate | TBD | % who attend booked meetings |
| Time-to-Book | TBD | Avg time from interest to confirmed |

---

## Performance Tracking

### Metrics to Capture

For each objection response:
1. **Response Time** - Time from objection to our reply
2. **Next Action Taken** - Did they reply, book, unsubscribe?
3. **Final Outcome** - Meeting booked, opportunity created, closed-won?
4. **Sentiment Shift** - Did response improve or worsen relationship?

### Quarterly Review

Schedule quarterly review of:
- Objection distribution (are patterns shifting?)
- Template effectiveness (A/B test variants)
- Escalation accuracy (were manual escalations correct?)
- New objection types emerging

---

## Template Locations

All templates are Jinja2 format in `templates/objections/`:

```
templates/objections/
├── book_meeting.j2         # Positive interest → meeting
├── displacement_nurture.j2 # Competitor user → nurture
├── schedule_future.j2      # Bad timing → future follow-up
├── send_resources.j2       # Info request → content
├── soft_breakup.j2         # Not interested → graceful exit
└── value_framework.j2      # Pricing → value conversation
```

---

*Pattern last validated: 2026-01-15*
*Next review: 2026-04-15*
