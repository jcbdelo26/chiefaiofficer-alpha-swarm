# GoHighLevel Integration Specification

> Complete configuration guide for GHL CRM integration with Alpha Swarm

---

## Overview

GoHighLevel (GHL) serves as the central CRM for lead management, pipeline tracking, and workflow automation. This document defines the required configuration for seamless integration with the Alpha Swarm system.

---

## API Authentication Setup

### 1. Create API Key

1. Navigate to **Settings → Integrations → API Keys**
2. Click **Create New API Key**
3. Name: `alpha-swarm-production`
4. Permissions required:
   - Contacts: Read, Write, Delete
   - Opportunities: Read, Write
   - Pipelines: Read
   - Custom Fields: Read, Write
   - Tags: Read, Write
   - Workflows: Read, Execute

### 2. Environment Configuration

```env
# .env configuration
GHL_API_KEY=your_api_key_here
GHL_LOCATION_ID=your_location_id_here
GHL_API_BASE_URL=https://rest.gohighlevel.com/v1
```

### 3. API Rate Limits

| Endpoint Category | Rate Limit | Retry Strategy |
|-------------------|------------|----------------|
| Contacts | 100/min | Exponential backoff |
| Opportunities | 100/min | Exponential backoff |
| Custom Fields | 50/min | Queue and batch |
| Webhooks | Unlimited | N/A |

---

## Required Custom Fields

### Contact Custom Fields

| Field Name | Field ID | Type | Required | Description |
|------------|----------|------|----------|-------------|
| `linkedin_url` | `cf_linkedin_url` | Text | Yes | LinkedIn profile URL |
| `source_type` | `cf_source_type` | Dropdown | Yes | Lead acquisition source |
| `source_name` | `cf_source_name` | Text | Yes | Specific source (competitor, event, group) |
| `source_url` | `cf_source_url` | Text | No | Original source URL |
| `icp_score` | `cf_icp_score` | Number | Yes | ICP score (0-100) |
| `icp_tier` | `cf_icp_tier` | Dropdown | Yes | Tier 1, 2, or 3 |
| `intent_score` | `cf_intent_score` | Number | No | Intent signal score |
| `engagement_action` | `cf_engagement_action` | Dropdown | No | How they engaged |
| `engagement_content` | `cf_engagement_content` | Large Text | No | Comment text if applicable |
| `enrichment_date` | `cf_enrichment_date` | Date | Yes | When lead was enriched |
| `clay_record_id` | `cf_clay_record_id` | Text | No | Clay table record ID |
| `instantly_lead_id` | `cf_instantly_lead_id` | Text | No | Instantly lead ID |
| `data_provenance` | `cf_data_provenance` | Large Text | Yes | GDPR: Data source tracking |
| `consent_basis` | `cf_consent_basis` | Dropdown | Yes | Legitimate interest, etc. |
| `tech_stack` | `cf_tech_stack` | Large Text | No | JSON array of technologies |
| `pain_points` | `cf_pain_points` | Large Text | No | Inferred pain points |
| `competitor_current` | `cf_competitor_current` | Text | No | Current competitor tool |
| `employee_count` | `cf_employee_count` | Number | No | Company employee count |
| `industry` | `cf_industry` | Dropdown | No | Industry classification |
| `funding_stage` | `cf_funding_stage` | Dropdown | No | Funding stage |
| `last_scraped_at` | `cf_last_scraped_at` | Date | Yes | When data was scraped |

### Field Creation Script

```python
# execution/ghl_setup_fields.py
import requests

CUSTOM_FIELDS = [
    {"name": "linkedin_url", "field_key": "cf_linkedin_url", "dataType": "TEXT"},
    {"name": "source_type", "field_key": "cf_source_type", "dataType": "SINGLE_OPTIONS",
     "options": ["competitor_follower", "event_attendee", "group_member", "post_commenter", "post_liker", "rb2b_visitor"]},
    {"name": "icp_tier", "field_key": "cf_icp_tier", "dataType": "SINGLE_OPTIONS",
     "options": ["Tier 1", "Tier 2", "Tier 3", "Disqualified"]},
    {"name": "consent_basis", "field_key": "cf_consent_basis", "dataType": "SINGLE_OPTIONS",
     "options": ["legitimate_interest", "explicit_consent", "contract_performance"]},
    # ... add remaining fields
]

def create_custom_fields(api_key: str, location_id: str):
    for field in CUSTOM_FIELDS:
        requests.post(
            f"https://rest.gohighlevel.com/v1/locations/{location_id}/customFields",
            headers={"Authorization": f"Bearer {api_key}"},
            json=field
        )
```

---

## Tag Taxonomy

### ICP Tier Tags

| Tag | Color | Meaning |
|-----|-------|---------|
| `tier-1` | Green | High-value ICP match (score 80+) |
| `tier-2` | Yellow | Medium-value ICP match (score 50-79) |
| `tier-3` | Gray | Low-value or nurture (score <50) |
| `tier-disqualified` | Red | Does not match ICP |

### Source Tags

| Tag | Description |
|-----|-------------|
| `src-competitor-follower` | Follows a competitor |
| `src-event-attendee` | Attended/registered for event |
| `src-group-member` | Member of relevant LinkedIn group |
| `src-post-commenter` | Commented on relevant post |
| `src-post-liker` | Liked relevant post |
| `src-rb2b-visitor` | RB2B website visitor |
| `src-{competitor-name}` | Dynamic: e.g., `src-gong`, `src-clari` |

### Status Tags

| Tag | Description |
|-----|-------------|
| `status-new` | Newly scraped, not yet enriched |
| `status-enriched` | Enriched with contact data |
| `status-qualified` | Passed ICP qualification |
| `status-in-sequence` | Active in email sequence |
| `status-replied` | Received reply |
| `status-replied-positive` | Positive reply received |
| `status-replied-negative` | Negative/objection reply |
| `status-meeting-booked` | Meeting scheduled |
| `status-meeting-completed` | Meeting occurred |
| `status-unsubscribed` | Opted out |
| `status-bounced` | Email bounced |

### Campaign Tags

| Tag | Description |
|-----|-------------|
| `campaign-{name}` | Active campaign name |
| `seq-step-{n}` | Current sequence step |
| `ae-approved` | AE approved for outreach |
| `ae-rejected` | AE rejected campaign |

---

## Pipeline and Stage Configuration

### Lead Pipeline: `alpha-swarm-pipeline`

| Stage Name | Stage ID | Order | Actions |
|------------|----------|-------|---------|
| New Lead | `stage_new` | 1 | Auto-assign, trigger enrichment |
| Enriched | `stage_enriched` | 2 | ICP scoring |
| Qualified | `stage_qualified` | 3 | Campaign generation |
| AE Review | `stage_ae_review` | 4 | Human approval gate |
| In Sequence | `stage_in_sequence` | 5 | Active outreach |
| Replied | `stage_replied` | 6 | Response handling |
| Meeting Booked | `stage_meeting_booked` | 7 | Calendar integration |
| Won | `stage_won` | 8 | Closed won |
| Lost | `stage_lost` | 9 | Closed lost |
| Nurture | `stage_nurture` | 10 | Long-term nurture |

### Pipeline Creation

```json
{
  "name": "Alpha Swarm Pipeline",
  "stages": [
    {"name": "New Lead", "order": 1},
    {"name": "Enriched", "order": 2},
    {"name": "Qualified", "order": 3},
    {"name": "AE Review", "order": 4},
    {"name": "In Sequence", "order": 5},
    {"name": "Replied", "order": 6},
    {"name": "Meeting Booked", "order": 7},
    {"name": "Won", "order": 8},
    {"name": "Lost", "order": 9},
    {"name": "Nurture", "order": 10}
  ]
}
```

---

## Webhook Setup

### Inbound Webhooks (GHL → Alpha Swarm)

| Event | Webhook URL | Purpose |
|-------|-------------|---------|
| Contact Created | `{BASE_URL}/webhooks/ghl/contact-created` | Trigger enrichment |
| Contact Updated | `{BASE_URL}/webhooks/ghl/contact-updated` | Sync changes |
| Tag Added | `{BASE_URL}/webhooks/ghl/tag-added` | Status updates |
| Opportunity Stage Changed | `{BASE_URL}/webhooks/ghl/opportunity-stage` | Pipeline sync |
| Note Created | `{BASE_URL}/webhooks/ghl/note-created` | AE feedback capture |

### Webhook Configuration

1. Navigate to **Settings → Webhooks**
2. Create webhook for each event type
3. Set authentication header: `X-Webhook-Secret: {your_secret}`
4. Enable retry on failure

### Webhook Payload Example (Contact Created)

```json
{
  "event": "contact.created",
  "timestamp": "2026-01-15T10:30:00Z",
  "data": {
    "id": "contact_abc123",
    "email": "john@company.com",
    "firstName": "John",
    "lastName": "Doe",
    "phone": "+1234567890",
    "customFields": {
      "cf_linkedin_url": "https://linkedin.com/in/johndoe",
      "cf_source_type": "competitor_follower",
      "cf_source_name": "Gong.io"
    },
    "tags": ["tier-1", "src-competitor-follower"]
  }
}
```

### Outbound Webhooks (Alpha Swarm → GHL)

Use GHL REST API for all outbound operations:

```python
# Example: Create contact with enrichment data
def create_ghl_contact(lead_data: dict):
    payload = {
        "email": lead_data["email"],
        "firstName": lead_data["first_name"],
        "lastName": lead_data["last_name"],
        "phone": lead_data.get("phone"),
        "companyName": lead_data.get("company"),
        "customField": {
            "cf_linkedin_url": lead_data["linkedin_url"],
            "cf_source_type": lead_data["source"]["type"],
            "cf_source_name": lead_data["source"]["name"],
            "cf_icp_score": lead_data["icp_score"],
            "cf_icp_tier": lead_data["icp_tier"],
            "cf_data_provenance": json.dumps(lead_data["provenance"]),
            "cf_consent_basis": "legitimate_interest"
        },
        "tags": build_tags(lead_data)
    }
    return ghl_api.contacts.create(payload)
```

---

## Field Mapping Table

### Lead Fields → GHL Fields

| Source Field | GHL Field | Transform |
|--------------|-----------|-----------|
| `lead.linkedin_url` | `customField.cf_linkedin_url` | Direct |
| `lead.first_name` | `firstName` | Direct |
| `lead.last_name` | `lastName` | Direct |
| `lead.email` | `email` | Lowercase, validate |
| `lead.phone` | `phone` | E.164 format |
| `lead.company` | `companyName` | Direct |
| `lead.title` | `customField.cf_job_title` | Direct |
| `source.type` | `customField.cf_source_type` | Enum mapping |
| `source.name` | `customField.cf_source_name` | Direct |
| `source.url` | `customField.cf_source_url` | Direct |
| `enrichment.icp_score` | `customField.cf_icp_score` | Integer 0-100 |
| `enrichment.icp_tier` | `customField.cf_icp_tier` | Tier 1/2/3 |
| `enrichment.intent_score` | `customField.cf_intent_score` | Integer 0-100 |
| `engagement.action` | `customField.cf_engagement_action` | Enum |
| `engagement.content` | `customField.cf_engagement_content` | Truncate 5000 chars |
| `enrichment.tech_stack[]` | `customField.cf_tech_stack` | JSON string |
| `enrichment.pain_points[]` | `customField.cf_pain_points` | JSON string |
| `company.employee_count` | `customField.cf_employee_count` | Integer |
| `company.industry` | `customField.cf_industry` | Enum mapping |
| `company.funding_stage` | `customField.cf_funding_stage` | Enum |
| `provenance` | `customField.cf_data_provenance` | JSON string |
| `captured_at` | `customField.cf_last_scraped_at` | ISO 8601 date |

### Tag Generation Rules

```python
def build_tags(lead: dict) -> list:
    tags = []
    
    # ICP tier tag
    tier = lead.get("icp_tier", "Tier 3")
    tags.append(f"tier-{tier.lower().replace(' ', '-')}")
    
    # Source type tag
    source_type = lead["source"]["type"]
    tags.append(f"src-{source_type.replace('_', '-')}")
    
    # Competitor-specific tag
    if source_type == "competitor_follower":
        competitor = lead["source"]["name"].lower().replace(" ", "-")
        tags.append(f"src-{competitor}")
    
    # Status tag
    tags.append("status-new")
    
    return tags
```

---

## GHL Workflows Integration

### Workflow: Lead Enrichment Trigger

```
Trigger: Contact Created with tag "status-new"
Actions:
  1. Wait 1 minute
  2. HTTP Webhook → Alpha Swarm enrichment endpoint
  3. If webhook fails → Add tag "enrichment-failed"
```

### Workflow: AE Notification

```
Trigger: Pipeline stage = "AE Review"
Actions:
  1. Send SMS to AE
  2. Send Slack notification
  3. Create task in GHL
  4. Set reminder for 4 hours
```

### Workflow: Reply Handling

```
Trigger: Tag added "status-replied"
Actions:
  1. Remove from Instantly sequence (via API)
  2. Move to "Replied" stage
  3. If positive → Notify AE immediately
  4. If negative → Queue for soft breakup
```

---

## Error Handling

### API Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 401 | Unauthorized | Check API key, refresh if expired |
| 404 | Contact not found | Skip or create new |
| 409 | Duplicate | Merge with existing record |
| 422 | Validation error | Log and fix data |
| 429 | Rate limited | Exponential backoff |
| 500 | Server error | Retry with backoff |

### Duplicate Detection

```python
def find_or_create_contact(lead: dict):
    # Check by email first
    existing = ghl_api.contacts.search(email=lead["email"])
    if existing:
        return update_contact(existing.id, lead)
    
    # Check by LinkedIn URL
    existing = ghl_api.contacts.search(
        customField={"cf_linkedin_url": lead["linkedin_url"]}
    )
    if existing:
        return update_contact(existing.id, lead)
    
    # Create new
    return create_contact(lead)
```

---

## GDPR Compliance

### Data Provenance Fields

Every contact must have `cf_data_provenance` populated:

```json
{
  "sources": [
    {
      "type": "linkedin_scrape",
      "url": "https://linkedin.com/company/gong/followers",
      "captured_at": "2026-01-15T10:00:00Z",
      "tool": "hunter-mcp"
    },
    {
      "type": "clay_enrichment",
      "table_id": "tbl_abc123",
      "enriched_at": "2026-01-15T10:15:00Z"
    }
  ],
  "consent_basis": "legitimate_interest",
  "retention_until": "2028-01-15"
}
```

### Deletion Request Handling

```python
def handle_gdpr_deletion(contact_id: str):
    # 1. Delete from GHL
    ghl_api.contacts.delete(contact_id)
    
    # 2. Remove from Instantly
    instantly_api.leads.delete(email=contact.email)
    
    # 3. Remove from Clay
    clay_api.records.delete(contact.clay_record_id)
    
    # 4. Log deletion for audit
    log_deletion_request(contact_id, timestamp=now())
```

---

*Document Version: 1.0*
*Last Updated: 2026-01-15*
*Owner: Alpha Swarm Integration Team*
