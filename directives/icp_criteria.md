# 🎯 ICP Criteria - Chiefaiofficer.com
# Ideal Customer Profile Definition

---

## Executive Summary

This directive defines the Ideal Customer Profile (ICP) for Chiefaiofficer.com's Alpha Swarm lead generation system. All leads MUST be scored against these criteria before campaign inclusion.

---

## Primary ICP Characteristics

### Company Attributes

| Attribute | Target | Score Weight |
|-----------|--------|--------------|
| **Employee Count** | 51-500 | 20% |
| **Industry** | B2B SaaS, Technology, Professional Services | 20% |
| **Annual Revenue** | $5M - $100M ARR | 15% |
| **Growth Stage** | Series A - Series C | 10% |
| **Geography** | USA, Canada, UK, Australia | 5% |

### Decision Maker Titles

**Tier 1 (Primary Buyers)** - Weight: 25%
- Chief Revenue Officer (CRO)
- VP of Revenue
- VP of Sales
- VP of Revenue Operations
- Director of Revenue Operations

**Tier 2 (Influencers)** - Weight: 15%
- Director of Sales Operations
- Head of SDR/BDR
- Director of Sales Enablement
- Sales Operations Manager

**Tier 3 (Researchers)** - Weight: 5%
- Revenue Operations Analyst
- Sales Operations Analyst
- GTM Operations

### Technology Stack Indicators

**Positive Signals** (Likely to buy):
- Using Salesforce or HubSpot CRM
- Outreach or SalesLoft for engagement
- Gong, Chorus, or Clari for intelligence
- Looking to implement AI solutions
- Manual forecasting processes

**Negative Signals** (Less likely to buy):
- Very early stage (Airtable as CRM)
- Already using AI RevOps solution
- In-house built solution

---

## ICP Scoring Algorithm

### Score Calculation (0-100)

```python
def calculate_icp_score(lead: dict) -> int:
    score = 0
    
    # Company Size (20 points max)
    employees = lead.get('company_size', 0)
    if 51 <= employees <= 200:
        score += 20
    elif 201 <= employees <= 500:
        score += 15
    elif 20 <= employees <= 50:
        score += 10
    elif 501 <= employees <= 1000:
        score += 10
    
    # Industry (20 points max)
    industry = lead.get('industry', '').lower()
    if 'saas' in industry or 'software' in industry:
        score += 20
    elif 'technology' in industry:
        score += 15
    elif 'professional services' in industry:
        score += 10
    
    # Title (25 points max)
    title = lead.get('title', '').lower()
    tier1_keywords = ['cro', 'chief revenue', 'vp revenue', 'vp sales', 'vp rev ops']
    tier2_keywords = ['director sales', 'director revenue', 'head of sdr', 'head of bdr']
    tier3_keywords = ['revenue operations', 'sales operations', 'gtm']
    
    if any(kw in title for kw in tier1_keywords):
        score += 25
    elif any(kw in title for kw in tier2_keywords):
        score += 15
    elif any(kw in title for kw in tier3_keywords):
        score += 5
    
    # Revenue (15 points max)
    revenue = lead.get('estimated_revenue', 0)
    if 10_000_000 <= revenue <= 50_000_000:
        score += 15
    elif 5_000_000 <= revenue <= 10_000_000:
        score += 12
    elif 50_000_000 <= revenue <= 100_000_000:
        score += 10
    
    # Engagement Source (20 points max)
    source = lead.get('source_type', '')
    if source == 'post_commenter':
        score += 20
    elif source == 'event_attendee':
        score += 18
    elif source == 'group_member':
        score += 12
    elif source == 'competitor_follower':
        score += 10
    elif source == 'post_liker':
        score += 8
    
    return min(score, 100)
```

### Tier Classification

| ICP Tier | Score Range | Priority | Campaign Treatment |
|----------|-------------|----------|--------------------|
| **Tier 1** | 85-100 | 🔴 Critical | Personalized 1:1, AE direct |
| **Tier 2** | 70-84 | 🟠 High | Personalized sequence |
| **Tier 3** | 50-69 | 🟡 Medium | Semi-personalized batch |
| **Tier 4** | 30-49 | 🔵 Low | Nurture sequence |
| **Disqualified** | 0-29 | ⚫ None | Do not contact |

---

## Disqualification Criteria

### Hard Disqualifiers (Automatic DQ)

1. **Company Size**: < 20 employees
2. **Industry**: 
   - Staffing/Recruiting agencies
   - Marketing agencies (unless 100+ employees)
   - Non-profit organizations
   - Government entities
3. **Already Customer**: In GHL as active customer
4. **Unsubscribed**: Previously opted out
5. **Competitor Employee**: Works for direct competitor
6. **Personal Email Only**: No work email found

### Soft Disqualifiers (Review Required)

1. **Freelancer/Consultant**: Individual contributor
2. **Intern/Student**: Junior level role
3. **Recently Contacted**: Within last 90 days
4. **Bounced Previously**: Email delivery failed

---

## Source Quality Weighting

### LinkedIn Source Types

| Source | Base Score | Rationale |
|--------|------------|-----------|
| **Post Commenter** | +20 | Active engagement, expressed opinion |
| **Event Attendee** | +18 | High intent, topically aligned |
| **Group Member (Active)** | +14 | Community participant |
| **Group Member (Passive)** | +10 | Interest signal |
| **Competitor Follower** | +10 | Awareness of space |
| **Post Liker** | +8 | Passive engagement |

### Competitor Source Priority

| Competitor | Priority | Displacement Messaging |
|------------|----------|----------------------|
| Gong | P0 | "Beyond conversation intelligence" |
| Clari | P0 | "Unified revenue intelligence" |
| Chorus | P1 | "Next-gen call analytics" |
| People.ai | P1 | "Activity data + AI insight" |
| InsightSquared | P2 | "Real-time revenue visibility" |
| Aviso | P2 | "AI-native forecasting" |

---

## Intent Signal Boosters

### Additional Score Modifiers

| Signal | Score Boost | Detection Method |
|--------|-------------|------------------|
| **Hiring RevOps** | +10 | LinkedIn Jobs |
| **Recent Funding** | +8 | News/Crunchbase |
| **New VP Sales** | +7 | LinkedIn Changes |
| **Product Launch** | +5 | News |
| **Website Visitor** | +5 | RB2B Match |
| **Multiple Touches** | +3 per | Our system |

---

## Implementation Notes

### For SEGMENTOR Agent
1. Apply this scoring algorithm to every lead
2. Store score breakdown with lead record
3. Flag any leads needing manual review
4. Generate segment reports daily

### For GATEKEEPER Agent
1. Display ICP score prominently in review
2. Highlight any disqualification flags
3. Allow manual override with reason
4. Track override patterns for learning

### For CRAFTER Agent
1. Use tier to select template intensity
2. Reference competitor in displacement messaging
3. Adjust CTA urgency by tier
4. Personalization depth increases with tier

---

## Update History

| Date | Change | By |
|------|--------|-----|
| 2026-01-12 | Initial creation | Alpha Swarm |

---

*Directive Version: 1.0*
*Review Frequency: Monthly*
