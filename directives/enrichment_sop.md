# 💎 Enrichment SOP
# Standard Operating Procedure for ENRICHER Agent

---

## Overview

This directive governs lead enrichment activities. The goal is to transform raw LinkedIn profiles into deeply contextualized, sales-ready lead records with verified contact data.

---

## Enrichment Pipeline

### Pipeline Stages

```
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│ Stage 1        │    │ Stage 2        │    │ Stage 3        │
│ CONTACT DATA   │ →  │ COMPANY INTEL  │ →  │ INTENT SIGNALS │
│ (Clay/RB2B)    │    │ (Exa/Web)      │    │ (Analysis)     │
└────────────────┘    └────────────────┘    └────────────────┘
         ↓                    ↓                    ↓
┌────────────────────────────────────────────────────────────┐
│                   Stage 4: CONTEXT BUILD                   │
│               Combine all data into rich profile           │
└────────────────────────────────────────────────────────────┘
```

---

## Stage 1: Contact Data Enrichment

### Primary: Clay Waterfall

**Script**: `execution/enricher_clay_waterfall.py`

Clay runs a waterfall of providers to find contact information:
1. Apollo
2. ZoomInfo
3. Clearbit
4. Hunter.io
5. Lusha

**Request Schema**:
```json
{
  "linkedin_url": "https://linkedin.com/in/johndoe",
  "name": "John Doe",
  "company": "Acme Inc",
  "company_domain": "acme.com"
}
```

**Response Schema**:
```json
{
  "email": {
    "work_email": "john.doe@acme.com",
    "personal_email": "johndoe@gmail.com",
    "confidence": 95,
    "verified": true
  },
  "phone": {
    "work_phone": "+1-555-123-4567",
    "mobile": "+1-555-987-6543",
    "verified": false
  },
  "social": {
    "twitter": "@johndoe",
    "github": "johndoe"
  }
}
```

### Secondary: RB2B Cross-Reference

**Script**: `execution/enricher_rb2b_match.py`

Match scraped leads against RB2B website visitor data:
```python
def match_rb2b_visitor(lead: dict) -> dict | None:
    """
    Search RB2B for matching visitors
    Match on: LinkedIn URL, email, or name+company
    """
    # Returns visitor data with:
    # - Pages visited
    # - Visit timestamps
    # - Session duration
    # - Referral source
    pass
```

### Fallback: Direct Lookup

If Clay fails to find email:
1. Try company email pattern ({first}.{last}@domain.com)
2. Check LinkedIn for published email
3. Flag for manual research

---

## Stage 2: Company Intelligence

### Company Enrichment Sources

**Script**: `execution/enricher_company_intel.py`

| Data Point | Primary Source | Fallback |
|------------|----------------|----------|
| Employee Count | LinkedIn | Clay |
| Revenue | ZoomInfo | Estimated |
| Industry | LinkedIn | Clay |
| Tech Stack | BuiltWith | Clay |
| Funding | Crunchbase | News |
| News | Exa Search | Google |

### Output Schema

```json
{
  "company": {
    "name": "Acme Inc",
    "domain": "acme.com",
    "linkedin_url": "https://linkedin.com/company/acme",
    "description": "B2B SaaS platform for...",
    "founded": 2018,
    "headquarters": "San Francisco, CA"
  },
  "firmographics": {
    "employee_count": 150,
    "employee_range": "101-250",
    "revenue_estimate": 25000000,
    "revenue_range": "$10M-$50M",
    "growth_rate": 45
  },
  "industry": {
    "primary": "Software",
    "secondary": "B2B SaaS",
    "vertical": "Revenue Operations"
  },
  "technology": {
    "crm": "Salesforce",
    "engagement": ["Outreach", "Gong"],
    "marketing": ["HubSpot", "Marketo"],
    "analytics": ["Tableau", "Looker"]
  },
  "funding": {
    "total_raised": 50000000,
    "last_round": "Series B",
    "last_round_date": "2025-06-15",
    "investors": ["a16z", "Sequoia"]
  },
  "news": [
    {
      "title": "Acme Raises $30M Series B",
      "date": "2025-06-15",
      "url": "https://...",
      "sentiment": "positive"
    }
  ]
}
```

---

## Stage 3: Intent Signals

### Intent Signal Detection

**Script**: `execution/enricher_intent_signals.py`

| Signal | Points | How We Detect |
|--------|--------|---------------|
| Hiring RevOps/Sales | 30 | LinkedIn Jobs API |
| Recent Funding (90 days) | 25 | Crunchbase + News |
| New CRO/VP Sales | 20 | LinkedIn profile changes |
| Competitor Usage | 15 | Tech stack detection |
| Website Visitor | 10 | RB2B match |
| Multiple Engagements | 5/each | Our scraping data |
| Event Attendance | 8 | Our event scrapes |
| Content Downloads | 7 | RB2B + GHL |

### Intent Score Calculation

```python
def calculate_intent_score(signals: dict) -> int:
    """
    Calculate intent score from 0-100
    Higher = more likely to buy now
    """
    score = 0
    
    if signals.get('hiring_revops'):
        score += 30
    if signals.get('recent_funding'):
        score += 25
    if signals.get('new_leadership'):
        score += 20
    if signals.get('competitor_user'):
        score += 15
    if signals.get('website_visitor'):
        score += 10
    
    # Cap at 100
    return min(score, 100)
```

### Intent to Tier Mapping

| Intent Score | Priority | Response Time |
|--------------|----------|---------------|
| 80-100 | 🔴 Hot | < 24 hours |
| 60-79 | 🟠 Warm | < 3 days |
| 40-59 | 🟡 Cool | < 1 week |
| 0-39 | 🔵 Nurture | Drip sequence |

---

## Stage 4: Context Building

### Engagement Context Analysis

**Script**: `execution/enricher_context_build.py`

For each lead, compile:

1. **Why We Found Them**
   - Source type and specific source
   - Engagement action and content
   - Relationship to our ICPxs

2. **What They Care About**
   - Topic of post/event/group they engaged with
   - Inferred pain points from comment analysis
   - Technology interests from tech stack

3. **Their Competitive Landscape**
   - Current tools they use
   - Competitors they follow
   - Displacement opportunity

4. **Best Approach Angle**
   - Recommended messaging angle
   - Personalization hooks
   - Timing considerations

### Context Output Schema

```json
{
  "lead_id": "uuid",
  "context": {
    "discovery_story": "Found via Gong LinkedIn page - they commented on a post about AI forecasting asking 'how does this compare to manual methods?'",
    "inferred_pain_points": [
      "manual forecasting processes",
      "rep productivity tracking",
      "pipeline visibility"
    ],
    "topic_affinity": [
      "AI in sales",
      "forecasting automation",
      "RevOps efficiency"
    ],
    "competitor_awareness": {
      "following": ["Gong", "Clari"],
      "likely_using": ["Gong"],
      "displacement_angle": "Beyond conversation intelligence"
    },
    "personalization_hooks": [
      "Reference their comment about manual methods",
      "Mention their title as VP RevOps",
      "Connect to their company's recent funding"
    ],
    "recommended_approach": {
      "angle": "competitor_displacement",
      "template": "gong_to_caio",
      "urgency": "high",
      "channel": "email_then_linkedin"
    }
  }
}
```

---

## Rate Limits & Quotas

### API Rate Limits

| Service | Limit | Handling |
|---------|-------|----------|
| Clay | 1000/day | Batch requests |
| RB2B | Unlimited | Real-time |
| Exa | 10,000/month | Cache results |
| LinkedIn | See scraping SOP | Careful |

### Batch Processing

```python
# Process leads in batches of 50
BATCH_SIZE = 50

# Maximum enrichment attempts per lead
MAX_RETRY = 3

# Delay between batches (seconds)
BATCH_DELAY = 60
```

---

## Enrichment Quality Scores

### Completeness Score (0-100)

| Field | Weight | Required |
|-------|--------|----------|
| Work Email | 30 | ✅ Yes |
| Company Name | 15 | ✅ Yes |
| Title | 15 | ✅ Yes |
| Phone | 10 | ❌ No |
| Company Size | 10 | ❌ No |
| Tech Stack | 10 | ❌ No |
| Intent Score | 10 | ❌ No |

### Quality Tiers

| Score | Status | Action |
|-------|--------|--------|
| 90-100 | ✅ Ready | Push to campaign |
| 70-89 | ⚠️ Partial | Campaign with gaps noted |
| 50-69 | ⚡ Minimal | Nurture only |
| 0-49 | ❌ Incomplete | Skip or manual research |

---

## Error Handling

### Common Enrichment Errors

| Error | Cause | Response |
|-------|-------|----------|
| No email found | Poor match | Try fallback patterns |
| Domain mismatch | Job change? | Flag for review |
| API timeout | Overload | Retry with backoff |
| Invalid LinkedIn | Bad URL | Log and skip |
| Rate limited | Quota hit | Wait and resume |

### Logging

All enrichment attempts logged to `.hive-mind/enriched/logs/{date}.json`:
```json
{
  "lead_id": "uuid",
  "stage": "contact_data",
  "provider": "clay",
  "success": true,
  "data_found": ["email", "phone"],
  "duration_ms": 1500,
  "timestamp": "2026-01-12T16:00:00Z"
}
```

---

## Storage

### Enriched Lead Storage

Location: `.hive-mind/enriched/`

```
enriched/
├── 2026/
│   └── 01/
│       └── 12/
│           ├── batch_001.json
│           ├── batch_002.json
│           └── summary.json
└── index.json  # Quick lookup index
```

### GHL Sync

After enrichment, sync to GoHighLevel:
```python
def sync_to_ghl(enriched_lead: dict) -> str:
    """
    Create/update contact in GHL
    Returns: GHL contact ID
    """
    pass
```

---

*Directive Version: 1.0*
*Last Updated: 2026-01-12*
*Owner: ENRICHER Agent*
