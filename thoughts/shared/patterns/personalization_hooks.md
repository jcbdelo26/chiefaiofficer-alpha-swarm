---
date: 2026-01-15
author: alpha_swarm
status: published
tags: [patterns, personalization, sdr, automation, icp]
related_docs:
  - directives/sdr_specifications.md
  - directives/icp_criteria.md
---

# Pattern: Personalization Hooks by Tier

> Effective personalization strategies aligned with ICP scoring

---

## Overview

This document defines personalization depth and strategies for each lead tier, based on the ICP scoring system defined in `directives/icp_criteria.md` and automation rules in `directives/sdr_specifications.md`.

**Core Principle:** Higher-scoring leads receive deeper, more researched personalization. Lower-scoring leads receive scalable template-based approaches.

---

## Tier Classification Reference

| Tier | Score Range | Priority | Personalization Depth |
|------|-------------|----------|----------------------|
| **Tier 1** | 85-100 | 🔴 Critical | Deep - AI + Human review |
| **Tier 2** | 70-84 | 🟠 High | Medium - AI with sampling |
| **Tier 3** | 50-69 | 🟡 Medium | Light - Template-based |
| **Tier 4** | 30-49 | 🔵 Low | Minimal - Standard template |

---

## Tier 1: VIP Personalization (Score 85-100)

### Required Elements

| Element | Example | Source |
|---------|---------|--------|
| First name | "Hi Sarah" | LinkedIn profile |
| Company name | "at Acme Corp" | LinkedIn profile |
| Specific engagement reference | "Your comment on AI forecasting..." | Source event |
| Recent company news/events | "Congrats on the Series B..." | News API/search |
| Inferred pain points (2-3) | "scaling RevOps without adding headcount" | Title + company stage |
| Mutual connections | "I see we both know John Smith" | LinkedIn |
| Industry-specific value prop | "B2B SaaS companies like yours..." | Industry data |
| Competitor displacement angle | "Moving beyond Gong's limitations..." | Tech stack intel |

### Optional Elements (When Available)

| Element | Example | Source |
|---------|---------|--------|
| Personal interests | "Fellow marathon runner here" | LinkedIn About |
| Recent content created | "Loved your post on pipeline management" | LinkedIn activity |
| Shared education/experience | "Go Bears! I'm also a Cal alum" | LinkedIn education |

### Generation Rules
```yaml
generation: AI with human review
approval: Required before send
review_checklist:
  - All placeholders resolved
  - Pain points accurate to company stage
  - News reference is recent (<30 days)
  - Tone matches prospect's style
```

### Example Hook Patterns

**Company News Hook:**
> "Saw the announcement about [specific news]. [Company] is clearly [insight from news]. Curious how you're thinking about [related challenge]..."

**Engagement Hook:**
> "Your comment on [topic] in [group/post] caught my attention - particularly your point about [specific insight]. It made me think about how [connection to our value]..."

**Competitor Evolution Hook:**
> "Many teams using [competitor] are finding they've outgrown [specific limitation]. We've helped [similar company] [specific outcome] by [differentiator]..."

---

## Tier 2: High-Priority Personalization (Score 70-84)

### Required Elements

| Element | Example | Source |
|---------|---------|--------|
| First name | "Hi Michael" | LinkedIn profile |
| Company name | "at TechFlow" | LinkedIn profile |
| Engagement reference | "Saw you liked the post about..." | Source event |
| Industry-specific hook | "In the SaaS space..." | Industry data |
| One pain point | "Forecasting accuracy" | Title inference |

### Optional Elements (When Available)

| Element | Example | Source |
|---------|---------|--------|
| Company news | "Growing team this year" | LinkedIn company page |
| Tech stack reference | "Noticed you're using Salesforce" | Enrichment data |

### Generation Rules
```yaml
generation: AI with sampling
approval: Recommended (10% review)
sampling_criteria:
  - First campaign from this source
  - New industry vertical
  - Score near threshold (70-75)
```

### Example Hook Patterns

**Source-Based Hook:**
> "Noticed you're part of [group/event] - great community for RevOps leaders. Quick question: how are you handling [common challenge]?"

**Industry Hook:**
> "Working with [industry] teams, we often see [common pain point]. Is that something on your radar at [Company]?"

**Role-Based Hook:**
> "As [their title], you're probably dealing with [role-specific challenge]. Wanted to share how [similar role at other company] addressed this..."

---

## Tier 3: Standard Personalization (Score 50-69)

### Required Elements

| Element | Example | Source |
|---------|---------|--------|
| First name | "Hi Jennifer" | LinkedIn profile |
| Company name | "at DataDriven Inc" | LinkedIn profile |
| Source-based hook | "Since you're interested in revenue ops..." | Source type |

### Optional Elements (When Available)

| Element | Example | Source |
|---------|---------|--------|
| Industry mention | "In the tech space" | LinkedIn company |

### Generation Rules
```yaml
generation: Template-based with merge fields
approval: Batch sampling only (10% of batch)
templates: Use standardized Tier 3 templates
```

### Example Hook Patterns

**Simple Source Hook:**
> "Hi [Name], reaching out since you [source action - liked/commented/attended]. Quick question about [topic]..."

**Industry Generic:**
> "Hi [Name], working with [industry] companies on [value prop]. Thought it might be relevant to [Company]..."

---

## Tier 4: Nurture Personalization (Score 30-49)

### Required Elements

| Element | Example | Source |
|---------|---------|--------|
| First name | "Hi Tom" | LinkedIn profile |

### Optional Elements

| Element | Example | Source |
|---------|---------|--------|
| Company name | "at StartupXYZ" | LinkedIn profile |

### Generation Rules
```yaml
generation: Standard template
approval: None required
cadence: Lower frequency (2-3 touches max)
```

### Example Hook Patterns

**Minimal Personal:**
> "Hi [Name], quick note about [general value prop]. Worth a 15-min chat?"

**Content-Led:**
> "Hi [Name], thought you might find this [resource type] useful: [link]. No strings attached."

---

## Source-Based Personalization Multipliers

Different lead sources warrant different personalization approaches:

### Post Commenter (Score +20)
**Best Hooks:**
- Reference their specific comment
- Quote or paraphrase their opinion
- Agree/build on their point

**Example:**
> "Your comment about [topic] really resonated - especially the point about [specific]. We've seen similar patterns at [customer type]..."

### Event Attendee (Score +18)
**Best Hooks:**
- Reference the event name
- Mention specific session if known
- Connect event topic to value prop

**Example:**
> "Hope you enjoyed [Event Name]! The session on [topic] aligned with what we're seeing in the market. Curious how you're applying those insights at [Company]..."

### Group Member - Active (Score +14)
**Best Hooks:**
- Reference group by name
- Mention community value
- Position as peer sharing

**Example:**
> "Fellow [Group Name] member here. Love the discussions in that community. Given your focus on [topic], thought you'd appreciate [value prop]..."

### Competitor Follower (Score +10)
**Best Hooks:**
- Acknowledge their current interest
- Position as complementary/evolution
- Avoid direct competitor criticism

**Example:**
> "Noticed you follow [Competitor] - they've done great work in [area]. We've been hearing from teams looking for [differentiated capability]. Worth comparing notes?"

---

## Personalization Quality Gates

From `directives/sdr_specifications.md`:

```yaml
Quality Checks:
  - No placeholder tokens in output ({{name}}, {company}, etc.)
  - Company name matches domain
  - Title capitalization correct
  - Grammar check passed
  - No lorem ipsum or test content
  - No duplicate content across leads
  
Fallback Rules:
  - If company news unavailable: Skip element
  - If no mutual connections: Use industry angle
  - If no comment content: Use source type
  - If low confidence on any data: Default to minimal
```

---

## ICP Criteria Quick Reference

Key scoring factors from `directives/icp_criteria.md`:

### Company Attributes (60 points max)
- **Employees 51-200:** 20 points
- **Industry (SaaS/Software):** 20 points
- **Revenue $10-50M:** 15 points

### Title Weight (25 points max)
- **Tier 1 (CRO, VP Revenue, VP Sales):** 25 points
- **Tier 2 (Director Sales Ops, Head of SDR):** 15 points
- **Tier 3 (RevOps Analyst):** 5 points

### Source (20 points max)
- **Post Commenter:** 20 points
- **Event Attendee:** 18 points
- **Group Member (Active):** 14 points

---

## Performance Tracking

### Metrics by Tier

| Tier | Target Open Rate | Target Reply Rate | Target Positive % |
|------|-----------------|-------------------|-------------------|
| Tier 1 | 60%+ | 15%+ | 60%+ |
| Tier 2 | 50%+ | 10%+ | 50%+ |
| Tier 3 | 45%+ | 6%+ | 45%+ |
| Tier 4 | 35%+ | 3%+ | 40%+ |

### A/B Testing Priorities

1. **Tier 1:** Test personalization depth vs. response rate
2. **Tier 2:** Test industry hooks vs. role hooks
3. **Tier 3:** Test source hooks vs. generic value prop
4. **Tier 4:** Test content-led vs. direct CTA

---

## Implementation Notes

### For CRAFTER Agent

1. Determine lead tier from ICP score
2. Select personalization depth from tier matrix
3. Gather required elements for that tier
4. Apply fallback rules if data missing
5. Run quality gates before output

### For SEGMENTOR Agent

1. Calculate ICP score per algorithm
2. Store score breakdown with lead
3. Flag tier-1 leads for priority processing
4. Track source for personalization context

### For GATEKEEPER Agent

1. Review Tier 1-2 personalization quality
2. Flag low-confidence personalization
3. Approve or request regeneration
4. Track approval patterns for learning

---

*Pattern last validated: 2026-01-15*
*Next review: 2026-04-15*
