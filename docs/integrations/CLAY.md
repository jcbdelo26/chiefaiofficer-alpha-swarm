# Clay Integration Specification

> Complete configuration guide for Clay enrichment platform integration with Alpha Swarm

---

## Overview

Clay serves as the primary enrichment engine for the Alpha Swarm system, providing waterfall enrichment across multiple data providers. This document defines the required configuration for seamless integration.

---

## API Authentication Setup

### 1. Generate API Key

1. Log into Clay dashboard
2. Navigate to **Settings → API**
3. Generate new API key
4. Store securely

### 2. Environment Configuration

```env
# .env configuration
CLAY_API_KEY=your_api_key_here
CLAY_API_BASE_URL=https://api.clay.com/v1
CLAY_WORKSPACE_ID=your_workspace_id
```

### 3. API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/tables` | GET, POST | List and create tables |
| `/tables/{id}/rows` | POST | Add rows to table |
| `/tables/{id}/rows/{rowId}` | GET, PATCH | Get/update row |
| `/tables/{id}/enrich` | POST | Trigger enrichment |
| `/tables/{id}/export` | POST | Export table data |
| `/webhooks` | POST | Configure webhooks |

---

## Enrichment Table Configuration

### Table: Lead Enrichment Pipeline

| Column Name | Column Type | Source | Description |
|-------------|-------------|--------|-------------|
| `linkedin_url` | URL | Input | LinkedIn profile URL |
| `first_name` | Text | Input | First name |
| `last_name` | Text | Input | Last name |
| `company_name` | Text | Input | Company name |
| `source_type` | Text | Input | Lead source type |
| `source_name` | Text | Input | Specific source |
| `scraped_at` | DateTime | Input | When scraped |
| `email_personal` | Email | Enriched | Personal email |
| `email_work` | Email | Enriched | Work email |
| `phone` | Phone | Enriched | Phone number |
| `title` | Text | Enriched | Job title |
| `company_domain` | URL | Enriched | Company website |
| `company_industry` | Text | Enriched | Industry |
| `company_size` | Number | Enriched | Employee count |
| `company_revenue` | Text | Enriched | Revenue range |
| `company_location` | Text | Enriched | HQ location |
| `tech_stack` | List | Enriched | Technologies used |
| `funding_stage` | Text | Enriched | Funding stage |
| `funding_amount` | Text | Enriched | Total funding |
| `linkedin_headline` | Text | Enriched | Profile headline |
| `linkedin_summary` | Text | Enriched | Profile summary |
| `linkedin_connections` | Number | Enriched | Connection count |
| `recent_posts` | List | Enriched | Recent activity |
| `mutual_connections` | Number | Enriched | Shared connections |
| `icp_score` | Number | Calculated | ICP score (0-100) |
| `icp_tier` | Text | Calculated | Tier 1/2/3 |
| `enrichment_status` | Text | System | Status tracking |
| `enriched_at` | DateTime | System | Enrichment timestamp |
| `provenance` | JSON | System | GDPR data trail |
| `ghl_contact_id` | Text | Output | GHL sync reference |
| `instantly_lead_id` | Text | Output | Instantly sync reference |

### Table Creation via API

```python
def create_enrichment_table():
    table_schema = {
        "name": "Alpha Swarm Lead Enrichment",
        "columns": [
            {"name": "linkedin_url", "type": "url", "required": True},
            {"name": "first_name", "type": "text"},
            {"name": "last_name", "type": "text"},
            {"name": "company_name", "type": "text"},
            {"name": "source_type", "type": "text"},
            {"name": "source_name", "type": "text"},
            {"name": "scraped_at", "type": "datetime"},
            {"name": "email_work", "type": "email", "enrichment": "waterfall"},
            {"name": "email_personal", "type": "email", "enrichment": "waterfall"},
            {"name": "phone", "type": "phone", "enrichment": "waterfall"},
            {"name": "title", "type": "text", "enrichment": "linkedin"},
            {"name": "company_domain", "type": "url", "enrichment": "clearbit"},
            {"name": "company_industry", "type": "text", "enrichment": "clearbit"},
            {"name": "company_size", "type": "number", "enrichment": "clearbit"},
            {"name": "tech_stack", "type": "list", "enrichment": "builtwith"},
            {"name": "funding_stage", "type": "text", "enrichment": "crunchbase"},
            {"name": "icp_score", "type": "number", "formula": "custom_icp_formula"},
            {"name": "icp_tier", "type": "text", "formula": "tier_formula"},
            {"name": "provenance", "type": "json"},
            {"name": "enriched_at", "type": "datetime"},
            {"name": "enrichment_status", "type": "text"}
        ]
    }
    
    return clay_api.tables.create(table_schema)
```

---

## Input/Output Field Specifications

### Input Fields (From Hunter Agent)

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `linkedin_url` | String | Yes | Valid LinkedIn URL pattern |
| `first_name` | String | No | Max 100 chars |
| `last_name` | String | No | Max 100 chars |
| `company_name` | String | No | Max 200 chars |
| `source_type` | Enum | Yes | One of: competitor_follower, event_attendee, group_member, post_commenter, post_liker |
| `source_name` | String | Yes | Max 200 chars |
| `source_url` | String | No | Valid URL |
| `engagement_action` | String | No | Action description |
| `engagement_content` | String | No | Comment text, max 5000 chars |
| `scraped_at` | ISO DateTime | Yes | UTC timestamp |

### Input Payload Example

```json
{
  "linkedin_url": "https://www.linkedin.com/in/johndoe",
  "first_name": "John",
  "last_name": "Doe",
  "company_name": "Acme Inc",
  "source_type": "competitor_follower",
  "source_name": "Gong.io",
  "source_url": "https://www.linkedin.com/company/gong-io/followers/",
  "scraped_at": "2026-01-15T10:00:00Z"
}
```

### Output Fields (To GHL/Instantly)

| Field | Type | Description |
|-------|------|-------------|
| `linkedin_url` | String | Original LinkedIn URL |
| `first_name` | String | Verified first name |
| `last_name` | String | Verified last name |
| `email` | String | Best available email (work preferred) |
| `email_personal` | String | Personal email if available |
| `phone` | String | Phone in E.164 format |
| `title` | String | Current job title |
| `company_name` | String | Current company |
| `company_domain` | String | Company website |
| `company_industry` | String | Industry classification |
| `company_size` | Number | Employee count |
| `company_revenue` | String | Revenue range |
| `company_location` | String | HQ location |
| `tech_stack` | Array | Technologies used |
| `funding_stage` | String | Current funding stage |
| `funding_amount` | String | Total raised |
| `icp_score` | Number | ICP score 0-100 |
| `icp_tier` | String | Tier 1, 2, or 3 |
| `source_type` | String | Original source type |
| `source_name` | String | Original source name |
| `source_url` | String | Original source URL |
| `engagement_action` | String | How they engaged |
| `engagement_content` | String | Engagement details |
| `provenance` | Object | GDPR data trail |
| `enriched_at` | DateTime | Enrichment timestamp |
| `clay_record_id` | String | Clay row reference |

### Output Payload Example

```json
{
  "linkedin_url": "https://www.linkedin.com/in/johndoe",
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@acme.com",
  "email_personal": "johnd@gmail.com",
  "phone": "+14155551234",
  "title": "VP of Revenue Operations",
  "company_name": "Acme Inc",
  "company_domain": "acme.com",
  "company_industry": "SaaS",
  "company_size": 250,
  "company_revenue": "$10M-$50M",
  "company_location": "San Francisco, CA",
  "tech_stack": ["Salesforce", "Outreach", "Gong", "HubSpot"],
  "funding_stage": "Series B",
  "funding_amount": "$35M",
  "icp_score": 87,
  "icp_tier": "Tier 1",
  "source_type": "competitor_follower",
  "source_name": "Gong.io",
  "source_url": "https://www.linkedin.com/company/gong-io/followers/",
  "engagement_action": "follows",
  "provenance": {
    "sources": [
      {"provider": "linkedin", "field": "name", "timestamp": "2026-01-15T10:05:00Z"},
      {"provider": "apollo", "field": "email", "timestamp": "2026-01-15T10:06:00Z"},
      {"provider": "clearbit", "field": "company", "timestamp": "2026-01-15T10:07:00Z"}
    ],
    "consent_basis": "legitimate_interest",
    "retention_until": "2028-01-15"
  },
  "enriched_at": "2026-01-15T10:10:00Z",
  "clay_record_id": "row_abc123xyz"
}
```

---

## Enrichment Waterfall Configuration

### Email Waterfall (Ordered by Accuracy)

| Priority | Provider | Cost | Accuracy | Fallback |
|----------|----------|------|----------|----------|
| 1 | Apollo | $0.03 | 95% | Next |
| 2 | Hunter.io | $0.02 | 92% | Next |
| 3 | Clearbit | $0.05 | 90% | Next |
| 4 | PDL | $0.04 | 88% | Next |
| 5 | Snov.io | $0.02 | 85% | Fail |

### Phone Waterfall

| Priority | Provider | Cost | Accuracy |
|----------|----------|------|----------|
| 1 | Cognism | $0.10 | 90% |
| 2 | Lusha | $0.08 | 85% |
| 3 | ZoomInfo | $0.12 | 88% |

### Company Data Waterfall

| Priority | Provider | Fields |
|----------|----------|--------|
| 1 | Clearbit | industry, size, revenue, location |
| 2 | LinkedIn | size, industry |
| 3 | Crunchbase | funding, investors |

### Tech Stack Enrichment

| Provider | Coverage |
|----------|----------|
| BuiltWith | Website technologies |
| HG Insights | Enterprise tech stack |
| Wappalyzer | Frontend technologies |

### Waterfall Configuration

```json
{
  "waterfall_email": {
    "providers": ["apollo", "hunter", "clearbit", "pdl", "snovio"],
    "stop_on_success": true,
    "verify_deliverability": true,
    "prefer_work_email": true
  },
  "waterfall_phone": {
    "providers": ["cognism", "lusha"],
    "format": "e164",
    "country_default": "US"
  },
  "waterfall_company": {
    "providers": ["clearbit", "crunchbase"],
    "merge_results": true
  },
  "waterfall_techstack": {
    "providers": ["builtwith", "wappalyzer"],
    "merge_results": true,
    "limit": 20
  }
}
```

---

## Rate Limits and Batching

### API Rate Limits

| Operation | Limit | Window | Strategy |
|-----------|-------|--------|----------|
| Row creation | 100/min | Per table | Queue + batch |
| Enrichment trigger | 50/min | Per workspace | Throttle |
| Row updates | 200/min | Per table | Batch |
| Table exports | 10/hour | Per workspace | Schedule |
| Webhooks | Unlimited | N/A | N/A |

### Provider Rate Limits (via Clay)

| Provider | Limit | Notes |
|----------|-------|-------|
| Apollo | 500/hour | Includes verification |
| Clearbit | 300/hour | Company + person |
| Hunter.io | 1000/hour | Email only |
| BuiltWith | 100/hour | Tech stack |
| Crunchbase | 200/hour | Company data |

### Batching Strategy

```python
import asyncio
from collections import deque

class ClayBatcher:
    def __init__(self, batch_size=50, flush_interval=60):
        self.queue = deque()
        self.batch_size = batch_size
        self.flush_interval = flush_interval
    
    async def add(self, lead: dict):
        self.queue.append(lead)
        if len(self.queue) >= self.batch_size:
            await self.flush()
    
    async def flush(self):
        if not self.queue:
            return
        
        batch = []
        while self.queue and len(batch) < self.batch_size:
            batch.append(self.queue.popleft())
        
        # Add rows in batch
        result = await clay_api.tables.add_rows(
            table_id=ENRICHMENT_TABLE_ID,
            rows=batch
        )
        
        # Trigger enrichment
        await clay_api.tables.enrich(
            table_id=ENRICHMENT_TABLE_ID,
            row_ids=[r["id"] for r in result["rows"]]
        )
        
        return result

# Usage
batcher = ClayBatcher(batch_size=50, flush_interval=60)

# In scraping loop
for lead in scraped_leads:
    await batcher.add(lead)

# Ensure remaining leads are processed
await batcher.flush()
```

### Optimal Batch Sizes

| Operation | Recommended Batch | Max Batch |
|-----------|-------------------|-----------|
| Row creation | 50 | 100 |
| Enrichment | 25 | 50 |
| Updates | 100 | 200 |
| Exports | 1000 | 5000 |

---

## Error Handling Patterns

### Error Types and Recovery

| Error Type | Code | Retry | Recovery Action |
|------------|------|-------|-----------------|
| Rate Limit | 429 | Yes | Exponential backoff |
| Provider Timeout | 504 | Yes | Retry next provider |
| Invalid Input | 400 | No | Log and skip |
| Authentication | 401 | No | Refresh API key |
| Provider Error | 502 | Yes | Retry with delay |
| Not Found | 404 | No | Mark as unenrichable |
| Quota Exceeded | 403 | No | Alert, pause until reset |

### Retry Logic

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60)
)
async def enrich_lead(row_id: str):
    try:
        result = await clay_api.tables.enrich(
            table_id=ENRICHMENT_TABLE_ID,
            row_ids=[row_id]
        )
        return result
    except RateLimitError:
        await asyncio.sleep(60)
        raise
    except ProviderError as e:
        log_provider_error(e)
        raise
```

### Enrichment Status Tracking

```python
class EnrichmentStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"  # Some fields enriched
    FAILED = "failed"
    UNENRICHABLE = "unenrichable"  # No data available

def update_enrichment_status(row_id: str, result: dict):
    if result.get("email") and result.get("company_size"):
        status = EnrichmentStatus.COMPLETED
    elif result.get("email") or result.get("phone"):
        status = EnrichmentStatus.PARTIAL
    elif result.get("error"):
        status = EnrichmentStatus.FAILED
    else:
        status = EnrichmentStatus.UNENRICHABLE
    
    clay_api.rows.update(row_id, {
        "enrichment_status": status,
        "enriched_at": datetime.now().isoformat()
    })
```

### Error Alerting

```python
def handle_enrichment_error(error: Exception, lead: dict):
    if isinstance(error, QuotaExceededError):
        send_alert(
            level="critical",
            message=f"Clay quota exceeded. Enrichment paused.",
            context={"remaining": error.quota_remaining}
        )
    elif isinstance(error, AuthenticationError):
        send_alert(
            level="critical",
            message="Clay API key invalid or expired",
            context={}
        )
    elif isinstance(error, ProviderError):
        log_error(f"Provider {error.provider} failed for {lead['linkedin_url']}")
```

---

## Provenance Field Requirements (GDPR)

### Purpose

The `provenance` field tracks the origin and processing history of personal data for GDPR compliance, including:
- Which providers supplied each data point
- When data was collected
- Legal basis for processing
- Retention period

### Provenance Schema

```json
{
  "provenance": {
    "collection": {
      "source": "linkedin_scrape",
      "source_url": "https://linkedin.com/company/gong-io/followers/",
      "collected_at": "2026-01-15T10:00:00Z",
      "collector": "hunter-mcp",
      "legal_basis": "legitimate_interest"
    },
    "enrichment": {
      "providers": [
        {
          "name": "apollo",
          "fields": ["email_work", "phone"],
          "timestamp": "2026-01-15T10:05:00Z"
        },
        {
          "name": "clearbit",
          "fields": ["company_size", "company_industry", "company_revenue"],
          "timestamp": "2026-01-15T10:06:00Z"
        },
        {
          "name": "builtwith",
          "fields": ["tech_stack"],
          "timestamp": "2026-01-15T10:07:00Z"
        }
      ],
      "completed_at": "2026-01-15T10:08:00Z"
    },
    "processing": {
      "purpose": "sales_outreach",
      "legal_basis": "legitimate_interest",
      "documented_interest": "B2B revenue operations solutions",
      "retention_days": 730,
      "retention_until": "2028-01-15T00:00:00Z"
    },
    "access_log": [
      {
        "system": "ghl_crm",
        "timestamp": "2026-01-15T10:10:00Z",
        "action": "create_contact"
      },
      {
        "system": "instantly",
        "timestamp": "2026-01-15T10:15:00Z",
        "action": "add_to_campaign"
      }
    ]
  }
}
```

### Building Provenance

```python
def build_provenance(lead: dict, enrichment_result: dict) -> dict:
    return {
        "collection": {
            "source": lead["source_type"],
            "source_url": lead.get("source_url"),
            "collected_at": lead["scraped_at"],
            "collector": "hunter-mcp",
            "legal_basis": "legitimate_interest"
        },
        "enrichment": {
            "providers": [
                {
                    "name": provider["name"],
                    "fields": provider["fields_enriched"],
                    "timestamp": provider["timestamp"]
                }
                for provider in enrichment_result.get("providers_used", [])
            ],
            "completed_at": datetime.now().isoformat()
        },
        "processing": {
            "purpose": "sales_outreach",
            "legal_basis": "legitimate_interest",
            "documented_interest": "B2B revenue operations solutions",
            "retention_days": 730,
            "retention_until": (datetime.now() + timedelta(days=730)).isoformat()
        },
        "access_log": []
    }
```

### GDPR Rights Handling

```python
def handle_right_to_access(email: str) -> dict:
    """Export all data for a subject (GDPR Art. 15)"""
    # Find in Clay
    rows = clay_api.tables.search(
        table_id=ENRICHMENT_TABLE_ID,
        query={"email_work": email}
    )
    
    # Include provenance
    return {
        "personal_data": rows,
        "provenance": [r.get("provenance") for r in rows],
        "generated_at": datetime.now().isoformat()
    }

def handle_right_to_erasure(email: str):
    """Delete all data for a subject (GDPR Art. 17)"""
    # Find in Clay
    rows = clay_api.tables.search(
        table_id=ENRICHMENT_TABLE_ID,
        query={"email_work": email}
    )
    
    # Delete from Clay
    for row in rows:
        clay_api.rows.delete(row["id"])
    
    # Also delete from GHL and Instantly
    # (handled by orchestrator)
    
    # Log deletion for audit
    log_deletion(email, "gdpr_erasure", datetime.now())

def handle_right_to_rectification(email: str, corrections: dict):
    """Update incorrect data (GDPR Art. 16)"""
    rows = clay_api.tables.search(
        table_id=ENRICHMENT_TABLE_ID,
        query={"email_work": email}
    )
    
    for row in rows:
        # Update with corrections
        clay_api.rows.update(row["id"], corrections)
        
        # Add to provenance
        row["provenance"]["access_log"].append({
            "action": "rectification",
            "timestamp": datetime.now().isoformat(),
            "fields_updated": list(corrections.keys())
        })
```

---

## Webhook Configuration

### Enrichment Complete Webhook

Configure Clay to notify Alpha Swarm when enrichment completes:

```json
{
  "webhook_url": "{BASE_URL}/webhooks/clay/enrichment-complete",
  "events": ["row.enriched", "row.enrichment_failed"],
  "headers": {
    "X-Webhook-Secret": "{your_secret}"
  }
}
```

### Webhook Payload

```json
{
  "event": "row.enriched",
  "timestamp": "2026-01-15T10:10:00Z",
  "table_id": "tbl_abc123",
  "row_id": "row_xyz789",
  "data": {
    "linkedin_url": "https://linkedin.com/in/johndoe",
    "email_work": "john@acme.com",
    "enrichment_status": "completed",
    "icp_score": 87,
    "icp_tier": "Tier 1"
  }
}
```

### Webhook Handler

```python
@app.post("/webhooks/clay/enrichment-complete")
async def handle_enrichment_complete(payload: dict):
    row_id = payload["row_id"]
    data = payload["data"]
    
    # Get full row data
    row = await clay_api.rows.get(row_id)
    
    # Sync to GHL
    ghl_contact = await sync_to_ghl(row)
    
    # Update Clay with GHL reference
    await clay_api.rows.update(row_id, {
        "ghl_contact_id": ghl_contact["id"]
    })
    
    # If Tier 1/2, add to campaign queue
    if row["icp_tier"] in ["Tier 1", "Tier 2"]:
        await queue_for_campaign(row, ghl_contact)
    
    return {"status": "processed"}
```

---

## ICP Scoring Formula

### Formula (Configured in Clay)

```javascript
// Clay formula for icp_score column
function calculateIcpScore(row) {
  let score = 0;
  
  // Company size (30 points max)
  const size = row.company_size || 0;
  if (size >= 200 && size <= 2000) score += 30;
  else if (size >= 100 && size < 200) score += 20;
  else if (size >= 50 && size < 100) score += 10;
  else if (size > 2000 && size <= 5000) score += 15;
  
  // Industry (20 points max)
  const targetIndustries = ["SaaS", "Technology", "Software", "B2B"];
  if (targetIndustries.includes(row.company_industry)) score += 20;
  
  // Title seniority (25 points max)
  const title = (row.title || "").toLowerCase();
  if (title.includes("chief") || title.includes("cro") || title.includes("ceo")) score += 25;
  else if (title.includes("vp") || title.includes("vice president")) score += 20;
  else if (title.includes("director")) score += 15;
  else if (title.includes("head of") || title.includes("senior")) score += 10;
  
  // Tech stack signals (15 points max)
  const techStack = row.tech_stack || [];
  const targetTech = ["salesforce", "hubspot", "outreach", "gong", "clari"];
  const matchCount = techStack.filter(t => 
    targetTech.some(target => t.toLowerCase().includes(target))
  ).length;
  score += Math.min(matchCount * 5, 15);
  
  // Funding (10 points max)
  const fundingStages = ["Series A", "Series B", "Series C"];
  if (fundingStages.includes(row.funding_stage)) score += 10;
  
  return Math.min(score, 100);
}

// Tier assignment
function assignTier(icpScore) {
  if (icpScore >= 80) return "Tier 1";
  if (icpScore >= 50) return "Tier 2";
  return "Tier 3";
}
```

---

*Document Version: 1.0*
*Last Updated: 2026-01-15*
*Owner: Alpha Swarm Integration Team*
