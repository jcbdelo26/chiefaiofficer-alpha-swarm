# 📦 Revenue Operations Context Loading Guide

> Step-by-step assets needed from Sales Operations to fully contextualize Alpha Swarm

**Purpose**: This document outlines exactly what information we need from your AE/Sales Ops team to train the AI to understand YOUR specific revenue operation — not generic outreach, but personalized to your ICP, voice, and sales process.

---

## 🎯 Overview: The Context Window

The AI needs to understand:
1. **WHO you sell to** (ICP)
2. **HOW you sell** (process & messaging)
3. **WHAT works** (historical wins)
4. **WHAT doesn't work** (failures & rules)
5. **WHO you already know** (existing relationships)

---

## Phase 1: Identity & Positioning (Week 1, Day 1-2)

### 1.1 Company Profile

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Company one-pager | PDF | AI understands what you sell | 🔴 Critical |
| Elevator pitch (30 seconds) | Text | Core value prop | 🔴 Critical |
| Founder/CEO LinkedIn bio | URL | Voice matching | 🔴 Critical |
| Press releases (last 6 months) | URLs/PDF | Recent positioning | 🟡 Important |
| Case studies (3-5 best) | PDF | Proof points | 🟡 Important |

**Deliverable from AE:**
```
📁 01_company_profile/
├── company_onepager.pdf
├── elevator_pitch.txt
├── founder_linkedin_url.txt
├── press_releases/
│   ├── pr_2026_01_funding.pdf
│   └── pr_2025_11_product_launch.pdf
└── case_studies/
    ├── case_study_techcorp.pdf
    ├── case_study_salesforce_customer.pdf
    └── case_study_enterprise_win.pdf
```

---

### 1.2 Product/Service Details

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Product overview | Doc/PDF | What you actually deliver | 🔴 Critical |
| Pricing structure | Doc | Tier/package understanding | 🔴 Critical |
| Feature list | CSV | What problems you solve | 🟡 Important |
| Integration list | List | Tech compatibility | 🟡 Important |
| Demo video link | URL | Visual understanding | 🟢 Nice to have |

**Deliverable:**
```
📁 02_product/
├── product_overview.pdf
├── pricing_tiers.md
├── features.csv
└── integrations.csv
```

---

## Phase 2: Ideal Customer Profile (Week 1, Day 2-3)

### 2.1 Target Company Definition

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| ICP document | YAML/Doc | Firmographic criteria | 🔴 Critical |
| Target industries list | CSV | Industry focus | 🔴 Critical |
| Company size ranges | Doc | Employee/revenue bands | 🔴 Critical |
| Geographic focus | List | Territory definition | 🔴 Critical |
| Tech stack signals | List | "They use X, we fit" | 🟡 Important |

**ICP Template (AE fills this out):**
```yaml
# 02_icp/icp_definition.yaml

company_criteria:
  size:
    min_employees: 51
    max_employees: 500
    preferred_range: "100-300"
  
  revenue:
    min_arr: "$5M"
    max_arr: "$100M"
    preferred: "$10M-50M"
  
  industries:
    tier1_priority:
      - "B2B SaaS"
      - "Technology"
      - "FinTech"
    tier2_acceptable:
      - "Professional Services"
      - "Healthcare Tech"
    excluded:
      - "Government"
      - "Non-profit"
      - "Education K-12"
  
  geography:
    primary: ["United States", "Canada"]
    secondary: ["UK", "Australia"]
    excluded: ["APAC except AU"]
  
  tech_signals:
    positive:
      - "Uses Salesforce"
      - "Uses HubSpot"
      - "Hiring for RevOps roles"
    negative:
      - "Using competitor X (already locked in)"
```

---

### 2.2 Target Persona Definition

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Target titles | List | Who to contact | 🔴 Critical |
| Persona descriptions | Doc | Motivations/pain points | 🔴 Critical |
| Seniority rules | Doc | Manager+, VP+, etc. | 🔴 Critical |
| Decision-maker vs influencer | Doc | Buying committee | 🟡 Important |

**Persona Template:**
```yaml
# 02_icp/personas.yaml

primary_buyer:
  titles:
    - "VP of Sales"
    - "VP of Revenue Operations"
    - "Chief Revenue Officer"
    - "Director of Sales Operations"
  
  pain_points:
    - "Forecasting is inaccurate"
    - "Pipeline velocity is slow"
    - "Rep productivity is declining"
    - "Tech stack is fragmented"
  
  goals:
    - "Hit revenue targets"
    - "Improve win rates"
    - "Reduce sales cycle"
  
  objections:
    - "We already have a solution"
    - "Budget is tight"
    - "Not a priority this quarter"

influencer:
  titles:
    - "Sales Manager"
    - "RevOps Manager"
    - "Sales Enablement Manager"
  
  how_to_use:
    - "Get intro to VP"
    - "Validate pain points"
```

---

### 2.3 Tier Definitions

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Tier 1 (VIP) criteria | Doc | Who gets white-glove | 🔴 Critical |
| Tier 2 (Target) criteria | Doc | Standard approach | 🔴 Critical |
| Tier 3 (Nurture) criteria | Doc | Long-term nurture | 🔴 Critical |

**Tier Template:**
```markdown
# 02_icp/tier_definitions.md

## Tier 1: VIP (White Glove)
- Fortune 500 companies
- Companies with 300+ employees
- $50M+ ARR
- Currently using competitor (displacement opportunity)
- Personal referral or warm intro
→ Approach: Highly personalized, exec-level, 1:1 emails

## Tier 2: Target (Standard)
- 100-300 employees
- $10M-50M ARR
- Clear ICP fit
- No existing relationship
→ Approach: Personalized sequences, value-first

## Tier 3: Nurture (Long-term)
- 50-100 employees
- Growing companies
- May not be ready today
→ Approach: Educational content, light touch
```

---

## Phase 3: Disqualification & Compliance (Week 1, Day 3-4)

### 3.1 Do Not Contact Lists

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Existing customers | CSV | Don't cold email customers | 🔴 Critical |
| Active opportunities | CSV | Don't overlap with live deals | 🔴 Critical |
| Unsubscribes | CSV | Legal compliance | 🔴 Critical |
| Competitors | CSV | Don't contact competitors | 🔴 Critical |
| Personal blocklist | CSV | Specific people to avoid | 🟡 Important |

**CSV Format:**
```csv
email,company,reason,added_date
john@acme.com,Acme Corp,Existing customer,2025-06-15
jane@competitor.com,Competitor Inc,Competitor employee,2025-01-01
bob@example.com,Example LLC,Requested removal,2025-12-01
```

---

### 3.2 Disqualification Rules

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Hard disqualifiers | List | Automatic exclusion | 🔴 Critical |
| Soft disqualifiers | List | Lower priority | 🟡 Important |

**Disqualification Template:**
```yaml
# 03_compliance/disqualifiers.yaml

hard_disqualify:
  - company_size_below: 20
  - company_type: "Agency"
  - company_type: "Consultancy"
  - industry: "Government"
  - existing_customer: true
  - unsubscribed: true
  - competitor_employee: true

soft_disqualify:
  - company_size_below: 50
  - no_linkedin_profile: true
  - generic_email_domain: true  # gmail, yahoo
```

---

## Phase 4: Messaging & Voice (Week 1, Day 4-5)

### 4.1 Winning Templates

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Best cold emails (5-10) | .txt files | Template training | 🔴 Critical |
| Subject lines that work | CSV | Subject optimization | 🔴 Critical |
| Follow-up sequences | .txt files | Multi-touch patterns | 🔴 Critical |
| Call scripts | Doc | If phone follow-up | 🟡 Important |

**Email Template Format:**
```
# 04_messaging/templates/tier1_competitor_displacement.txt

---
Template Name: Competitor Displacement
Tier: 1 (VIP)
Use When: Prospect uses Gong/Chorus
Historical Open Rate: 58%
Historical Reply Rate: 12%
---

SUBJECT: {firstName}, quick question about {competitor}

Hi {firstName},

Noticed {company} is using {competitor} for revenue intelligence. Out of curiosity — are you seeing the {specific_pain_point} issue that a lot of {industry} teams mention?

We just helped {similar_company} solve that and they saw {metric} improvement in {timeframe}.

Worth 15 minutes to see if we could do the same for {company}?

Best,
{sender_name}

---
FOLLOW UP (Day 3):

SUBJECT: Re: {firstName}, quick question about {competitor}

{firstName} — 

Wanted to bump this up. The {specific_pain_point} issue usually costs teams {cost_estimate}/month in missed opportunities.

Happy to share what we're seeing work. Worth a quick call?

{sender_name}
```

---

### 4.2 Brand Voice Guidelines

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Voice guidelines | Doc | Tone and style | 🔴 Critical |
| Words to avoid | List | Brand safety | 🔴 Critical |
| Words to use | List | Brand consistency | 🟡 Important |
| Signature template | HTML | Email signature | 🔴 Critical |

**Voice Template:**
```markdown
# 04_messaging/voice_guidelines.md

## Our Voice
- Confident but not arrogant
- Direct but not pushy
- Helpful, not salesy
- Peer-to-peer, not vendor-to-buyer

## Words We USE
- "you" (not "prospects")
- "help" (not "sell")
- "explore" (not "demo")
- "15 minutes" (not "a call")

## Words We AVOID
- "Just checking in"
- "I hope this email finds you well"
- "Touch base"
- "Pick your brain"
- "Low-hanging fruit"
- Any competitor disparagement

## Email Length
- Cold email: 50-100 words max
- Follow-up: 30-50 words max
- No long paragraphs
- Mobile-friendly formatting
```

---

### 4.3 Objection Handling

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Common objections | Doc | Reply templates | 🟡 Important |
| Rebuttal scripts | Doc | Conversation guides | 🟡 Important |

**Objection Template:**
```yaml
# 04_messaging/objections.yaml

objections:
  - trigger: "We already have a solution"
    response: |
      Totally get it — most of our customers did too before switching.
      What specifically is working well? I'm curious if we're solving 
      the same problems differently.
    
  - trigger: "Not a priority right now"
    response: |
      Makes sense. When would be a better time to revisit? 
      Happy to send some info to review when the timing is right.
    
  - trigger: "Send me information"
    response: |
      Absolutely. What specifically would be most useful — 
      case studies, pricing, or a product overview?
```

---

## Phase 5: Historical Data (Week 2, Day 1-2)

### 5.1 CRM Exports

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Won deals (180 days) | CSV | Pattern recognition | 🔴 Critical |
| Lost deals (180 days) | CSV | Failure patterns | 🔴 Critical |
| Open opportunities | CSV | Avoid overlap | 🔴 Critical |
| All contacts | CSV | Relationship mapping | 🟡 Important |

**Won Deals CSV Format:**
```csv
company,contact_name,contact_title,deal_value,close_date,source,days_to_close,industry,company_size
TechCorp,Jane Smith,VP Sales,$50000,2025-12-15,LinkedIn Outbound,45,B2B SaaS,150
SalesInc,Bob Jones,CRO,$75000,2025-11-20,Referral,30,Technology,280
```

---

### 5.2 Campaign Analytics

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Email campaigns (90 days) | CSV | What worked | 🔴 Critical |
| Open/reply rates by template | CSV | Template scoring | 🔴 Critical |
| Best performing sequences | Export | Sequence patterns | 🟡 Important |

**From Instantly:**
```
Export: Settings → Analytics → Export CSV
Timeframe: Last 90 days
Include: Campaign name, sends, opens, clicks, replies, unsubscribes
```

---

## Phase 6: Lead Sources (Week 2, Day 2-3)

### 6.1 LinkedIn Sources

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Competitor company URLs | CSV | Follower scraping | 🔴 Critical |
| Industry influencer URLs | CSV | Follower scraping | 🟡 Important |
| Target event URLs | CSV | Attendee scraping | 🟡 Important |
| LinkedIn Group URLs | CSV | Member scraping | 🟢 Nice to have |

**Sources CSV:**
```csv
source_type,name,url,priority,notes
competitor,Gong,https://linkedin.com/company/gong,high,Main competitor
competitor,Chorus,https://linkedin.com/company/chorus,high,Secondary competitor
influencer,Jason Lemkin,https://linkedin.com/in/jasonlemkin,medium,SaaStr
event,SaaStr Annual 2026,https://linkedin.com/events/123456,high,Key conference
```

---

## Phase 7: Documents for AI (Week 2, Day 3-4)

### 7.1 Competitor Intelligence

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Competitor one-pagers | PDF | Positioning | 🟡 Important |
| Competitor pricing pages | PDF/Screenshot | Comparison | 🟡 Important |
| Competitor weaknesses | Doc | Battle cards | 🟡 Important |

---

### 7.2 Target Account Research

| Asset | Format | Purpose | Priority |
|-------|--------|---------|----------|
| Named account list | CSV | ABM targets | 🟢 Nice to have |
| Account research docs | PDF | Pre-researched accounts | 🟢 Nice to have |

---

## 📋 Complete Asset Checklist

```markdown
## AE/Sales Ops Submission Checklist

### Phase 1: Identity (Day 1-2)
- [ ] Company one-pager (PDF)
- [ ] Elevator pitch (30-second text)
- [ ] Founder LinkedIn URL
- [ ] 3-5 case studies (PDF)
- [ ] Product overview
- [ ] Pricing structure

### Phase 2: ICP (Day 2-3)
- [ ] ICP definition (YAML or Doc)
- [ ] Target industries list
- [ ] Persona definitions
- [ ] Tier definitions (VIP/Target/Nurture)

### Phase 3: Compliance (Day 3-4)
- [ ] Existing customers list (CSV)
- [ ] Unsubscribe list (CSV)
- [ ] Competitor employee list (CSV)
- [ ] Hard disqualification rules

### Phase 4: Messaging (Day 4-5)
- [ ] 5-10 winning email templates
- [ ] Subject line performance data
- [ ] Follow-up sequences
- [ ] Voice guidelines
- [ ] Words to avoid
- [ ] Email signature (HTML)
- [ ] Objection handling scripts

### Phase 5: Historical Data (Week 2)
- [ ] Won deals export (180 days)
- [ ] Lost deals export (180 days)
- [ ] Open opportunities export
- [ ] Email campaign analytics (90 days)

### Phase 6: Lead Sources (Week 2)
- [ ] Competitor LinkedIn URLs
- [ ] Influencer LinkedIn URLs
- [ ] Event URLs (if applicable)

### Phase 7: Documents (Week 2)
- [ ] Competitor battle cards
- [ ] Named account list
```

---

## 📁 Final Folder Structure

```
ae_handoff/
├── 01_company_profile/
│   ├── company_onepager.pdf
│   ├── elevator_pitch.txt
│   ├── founder_linkedin.txt
│   ├── case_studies/
│   └── press_releases/
│
├── 02_icp/
│   ├── icp_definition.yaml
│   ├── personas.yaml
│   ├── tier_definitions.md
│   └── target_industries.csv
│
├── 03_compliance/
│   ├── existing_customers.csv
│   ├── unsubscribes.csv
│   ├── competitors.csv
│   └── disqualifiers.yaml
│
├── 04_messaging/
│   ├── templates/
│   │   ├── tier1_competitor_displacement.txt
│   │   ├── tier1_event_followup.txt
│   │   ├── tier2_cold_outreach.txt
│   │   └── tier3_nurture.txt
│   ├── subject_lines.csv
│   ├── voice_guidelines.md
│   ├── objections.yaml
│   └── signature.html
│
├── 05_historical/
│   ├── won_deals.csv
│   ├── lost_deals.csv
│   ├── open_opportunities.csv
│   └── campaign_analytics.csv
│
├── 06_sources/
│   ├── linkedin_sources.csv
│   └── named_accounts.csv
│
└── 07_documents/
    ├── competitor_collateral/
    └── account_research/
```

---

## ⏱️ Timeline Summary

| Day | Phase | Deliverables |
|-----|-------|-------------|
| Day 1-2 | Identity | Company profile, product info |
| Day 2-3 | ICP | Target criteria, personas, tiers |
| Day 3-4 | Compliance | DNC lists, disqualifiers |
| Day 4-5 | Messaging | Templates, voice, objections |
| Day 6-7 | Historical | CRM exports, campaign data |
| Day 8-9 | Sources | LinkedIn URLs |
| Day 10 | Documents | Competitor intel |

**Total time from AE: ~10-15 hours spread across 2 weeks**

---

*Once we have these assets, the AI will understand YOUR revenue operation — not generic outreach, but campaigns that sound like YOUR team wrote them.*
