# Instantly.ai Integration Specification

> Complete configuration guide for Instantly email outreach integration with Alpha Swarm

---

## Overview

Instantly.ai handles all email outreach operations including campaign management, lead sequencing, and delivery optimization. This document defines the required configuration for seamless integration with the Alpha Swarm system.

---

## API Authentication Setup

### 1. Generate API Key

1. Log into Instantly dashboard
2. Navigate to **Settings → Integrations → API**
3. Click **Generate API Key**
4. Copy and store securely

### 2. Environment Configuration

```env
# .env configuration
INSTANTLY_API_KEY=your_api_key_here
INSTANTLY_API_BASE_URL=https://api.instantly.ai/api/v1
INSTANTLY_WORKSPACE_ID=your_workspace_id
```

### 3. API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/lead/add` | POST | Add leads to campaigns |
| `/lead/delete` | POST | Remove leads |
| `/lead/list` | GET | List leads in campaign |
| `/campaign/list` | GET | List all campaigns |
| `/campaign/status` | GET | Get campaign status |
| `/campaign/analytics` | GET | Get campaign metrics |
| `/email/list` | GET | List sent emails |
| `/unibox/list` | GET | List replies |

---

## Campaign Setup Requirements

### Campaign Naming Convention

```
{tier}_{source}_{date}_{variant}

Examples:
- t1_gong-followers_20260115_v1
- t2_event-attendees_20260115_v1
- t3_group-members_20260115_a-test
```

### Required Campaign Settings

| Setting | Value | Reason |
|---------|-------|--------|
| Daily sending limit | 50-100 per mailbox | Deliverability |
| Time between emails | 60-120 seconds | Natural cadence |
| Working hours | 8am-6pm recipient TZ | Open rates |
| Weekend sending | Disabled | B2B best practice |
| Reply detection | Enabled | Auto-pause |
| Bounce handling | Auto-remove | List hygiene |
| Warmup | Enabled | New mailboxes |

### Campaign Structure

```json
{
  "name": "t1_competitor-followers_20260115_v1",
  "emailAccounts": ["chris@chiefaiofficer.com", "team@chiefaiofficer.com"],
  "schedule": {
    "timezone": "America/New_York",
    "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "startHour": 8,
    "endHour": 18
  },
  "settings": {
    "dailyLimit": 75,
    "waitBetweenEmails": 90,
    "stopOnReply": true,
    "stopOnBounce": true,
    "trackOpens": true,
    "trackClicks": true
  }
}
```

### Sequence Steps

| Step | Delay | Subject | Purpose |
|------|-------|---------|---------|
| 1 | Day 0 | Personalized opener | Initial touch |
| 2 | Day 2 | Reply bump | Short follow-up |
| 3 | Day 5 | Value add | Case study/resource |
| 4 | Day 9 | Social proof | Testimonial |
| 5 | Day 14 | Soft breakup | Final touch |

---

## Lead Variable Mapping

### Standard Variables

| Variable | Description | Source |
|----------|-------------|--------|
| `{{firstName}}` | First name | GHL contact |
| `{{lastName}}` | Last name | GHL contact |
| `{{email}}` | Email address | GHL contact |
| `{{companyName}}` | Company name | GHL contact |
| `{{title}}` | Job title | Enrichment |
| `{{phone}}` | Phone number | Enrichment |

### Custom Variables (Alpha Swarm Specific)

| Variable | Description | Source | Example |
|----------|-------------|--------|---------|
| `{{sourceType}}` | How we found them | Scraping | "competitor follower" |
| `{{sourceName}}` | Specific source | Scraping | "Gong.io" |
| `{{engagementAction}}` | What they did | Scraping | "commented on" |
| `{{engagementContent}}` | Comment text | Scraping | "Great insights..." |
| `{{painPoint}}` | Primary pain point | Enrichment | "manual forecasting" |
| `{{competitorCurrent}}` | Current tool | Enrichment | "Outreach" |
| `{{techStack}}` | Relevant tech | Enrichment | "Salesforce, HubSpot" |
| `{{mutualConnections}}` | Shared connections | Enrichment | "3 mutual connections" |
| `{{caseStudy}}` | Relevant case study | Matching | "Acme Corp success story" |
| `{{eventName}}` | Event attended | Scraping | "RevOps Summit 2026" |
| `{{groupName}}` | Group membership | Scraping | "Revenue Operations Pros" |
| `{{icpScore}}` | ICP score | Scoring | "87" |
| `{{icpTier}}` | ICP tier | Scoring | "Tier 1" |

### Lead Payload Structure

```json
{
  "campaign_id": "camp_abc123",
  "email": "john@company.com",
  "firstName": "John",
  "lastName": "Doe",
  "companyName": "Acme Inc",
  "personalization": {
    "title": "VP of Revenue Operations",
    "sourceType": "competitor follower",
    "sourceName": "Gong.io",
    "engagementAction": "follows",
    "painPoint": "manual forecasting taking 20+ hours per week",
    "competitorCurrent": "Outreach",
    "techStack": "Salesforce, Outreach, Gong",
    "caseStudy": "How Acme Corp reduced forecasting time by 80%",
    "icpScore": "87",
    "icpTier": "Tier 1"
  },
  "custom_variables": {
    "ghl_contact_id": "contact_xyz789",
    "clay_record_id": "rec_abc123",
    "sequence_version": "v1"
  }
}
```

---

## Webhook Endpoint Configuration

### Outbound Webhooks (Instantly → Alpha Swarm)

Configure in Instantly dashboard under **Settings → Webhooks**:

| Event | Webhook URL | Purpose |
|-------|-------------|---------|
| Reply Received | `{BASE_URL}/webhooks/instantly/reply` | Trigger response handling |
| Email Opened | `{BASE_URL}/webhooks/instantly/open` | Track engagement |
| Link Clicked | `{BASE_URL}/webhooks/instantly/click` | Track interest |
| Email Bounced | `{BASE_URL}/webhooks/instantly/bounce` | Update GHL status |
| Unsubscribe | `{BASE_URL}/webhooks/instantly/unsubscribe` | Compliance |
| Lead Completed | `{BASE_URL}/webhooks/instantly/completed` | Sequence finished |

### Webhook Payload Examples

**Reply Received:**
```json
{
  "event": "reply",
  "timestamp": "2026-01-15T14:30:00Z",
  "data": {
    "campaign_id": "camp_abc123",
    "lead_email": "john@company.com",
    "reply_text": "Thanks for reaching out. I'd love to learn more...",
    "sentiment": "positive",
    "sequence_step": 1,
    "email_account": "chris@chiefaiofficer.com"
  }
}
```

**Bounce:**
```json
{
  "event": "bounce",
  "timestamp": "2026-01-15T14:30:00Z",
  "data": {
    "campaign_id": "camp_abc123",
    "lead_email": "invalid@company.com",
    "bounce_type": "hard",
    "reason": "mailbox_not_found"
  }
}
```

### Webhook Handler Example

```python
# execution/instantly_webhooks.py

@app.post("/webhooks/instantly/reply")
async def handle_reply(payload: dict):
    lead_email = payload["data"]["lead_email"]
    reply_text = payload["data"]["reply_text"]
    sentiment = classify_sentiment(reply_text)
    
    # Update GHL
    contact = ghl_api.contacts.find(email=lead_email)
    ghl_api.contacts.update(contact.id, {
        "tags": ["status-replied", f"replied-{sentiment}"]
    })
    
    # Move pipeline stage
    ghl_api.opportunities.update_stage(
        contact.opportunity_id, 
        "stage_replied"
    )
    
    # Check escalation rules
    if should_escalate(sentiment, contact):
        trigger_ae_notification(contact, reply_text)
    
    return {"status": "processed"}
```

---

## Suppression List Management

### Global Suppression Lists

| List Type | Purpose | Update Frequency |
|-----------|---------|------------------|
| Unsubscribes | GDPR/CAN-SPAM compliance | Real-time |
| Bounces | Email hygiene | Real-time |
| Competitors | Never contact | Weekly |
| Existing Customers | Route to CSM | Daily |
| Blacklist Domains | spam traps, etc. | Monthly |

### Adding to Suppression

```python
def add_to_suppression(email: str, reason: str):
    instantly_api.suppression.add({
        "email": email,
        "reason": reason,
        "added_at": datetime.now().isoformat(),
        "added_by": "alpha-swarm"
    })
```

### Suppression Check Before Send

```python
def is_suppressed(email: str) -> bool:
    result = instantly_api.suppression.check(email)
    return result.get("suppressed", False)

def validate_lead_for_campaign(lead: dict) -> bool:
    if is_suppressed(lead["email"]):
        return False
    if is_competitor_domain(lead["email"]):
        return False
    if is_existing_customer(lead["email"]):
        return False
    return True
```

### Sync Suppression Lists

```python
# Run daily to sync GHL unsubscribes to Instantly
def sync_suppression_from_ghl():
    unsubscribed = ghl_api.contacts.list(
        tags=["status-unsubscribed"]
    )
    for contact in unsubscribed:
        instantly_api.suppression.add({
            "email": contact.email,
            "reason": "ghl_unsubscribe"
        })
```

---

## Rate Limits and Best Practices

### API Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| Lead operations | 1000/hour | Per API key |
| Campaign operations | 100/hour | Per API key |
| Analytics | 500/hour | Per API key |
| Bulk operations | 10/minute | Per API key |

### Sending Limits (Deliverability)

| Mailbox Age | Daily Limit | Warmup Required |
|-------------|-------------|-----------------|
| 0-2 weeks | 10-20 | Yes |
| 2-4 weeks | 20-40 | Yes |
| 1-2 months | 40-75 | Optional |
| 2+ months | 75-100 | No |

### Best Practices

1. **Domain Setup**
   - SPF, DKIM, DMARC configured
   - Custom tracking domain
   - Separate domain for cold outreach
   
2. **Mailbox Rotation**
   - 3-5 mailboxes per campaign
   - Rotate sending accounts
   - Monitor per-mailbox reputation

3. **Content Guidelines**
   - No spam trigger words
   - Plain text preferred over HTML
   - Max 2 links per email
   - No attachments
   - Personalization tokens ≥3 per email

4. **Timing**
   - Tuesday-Thursday best days
   - 9-11am and 2-4pm best times
   - Respect recipient timezone
   - No holiday sending

5. **List Hygiene**
   - Verify emails before adding
   - Remove bounces immediately
   - Re-verify aged leads (>30 days)
   - Segment by engagement

---

## Campaign-GHL Sync

### Lead Status Mapping

| Instantly Status | GHL Tag | GHL Pipeline Stage |
|------------------|---------|-------------------|
| Pending | `status-in-sequence` | In Sequence |
| Active | `status-in-sequence` | In Sequence |
| Paused | `status-in-sequence` | In Sequence |
| Replied | `status-replied` | Replied |
| Completed | `status-sequence-completed` | Nurture |
| Bounced | `status-bounced` | Disqualified |
| Unsubscribed | `status-unsubscribed` | Disqualified |

### Sync Script

```python
# execution/sync_instantly_ghl.py

def sync_campaign_status():
    campaigns = instantly_api.campaigns.list()
    
    for campaign in campaigns:
        leads = instantly_api.leads.list(campaign_id=campaign.id)
        
        for lead in leads:
            contact = ghl_api.contacts.find(email=lead.email)
            if not contact:
                continue
            
            new_tags = map_status_to_tags(lead.status)
            new_stage = map_status_to_stage(lead.status)
            
            ghl_api.contacts.update(contact.id, {
                "tags": new_tags
            })
            
            if new_stage:
                ghl_api.opportunities.update_stage(
                    contact.opportunity_id,
                    new_stage
                )
```

---

## Analytics Integration

### Metrics to Track

| Metric | Calculation | Alert Threshold |
|--------|-------------|-----------------|
| Delivery Rate | (Sent - Bounces) / Sent | <95% |
| Open Rate | Opens / Delivered | <40% |
| Reply Rate | Replies / Delivered | <5% |
| Positive Reply Rate | Positive / Total Replies | <40% |
| Unsubscribe Rate | Unsubscribes / Delivered | >1% |
| Spam Report Rate | Spam Reports / Delivered | >0.1% |

### Daily Analytics Pull

```python
def pull_daily_analytics():
    campaigns = instantly_api.campaigns.list(active=True)
    
    metrics = []
    for campaign in campaigns:
        stats = instantly_api.analytics.get(
            campaign_id=campaign.id,
            date_from=yesterday(),
            date_to=today()
        )
        
        metrics.append({
            "campaign": campaign.name,
            "sent": stats.sent,
            "delivered": stats.delivered,
            "opens": stats.opens,
            "replies": stats.replies,
            "bounces": stats.bounces,
            "unsubscribes": stats.unsubscribes
        })
    
    return metrics
```

---

## Error Handling

### API Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 401 | Invalid API key | Refresh credentials |
| 400 | Invalid request | Check payload format |
| 404 | Campaign/lead not found | Skip or recreate |
| 409 | Duplicate lead | Skip (already added) |
| 429 | Rate limited | Exponential backoff |
| 500 | Server error | Retry with backoff |

### Retry Strategy

```python
import time
from functools import wraps

def with_retry(max_retries=3, base_delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except RateLimitError:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                except ServerError:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(base_delay)
            return func(*args, **kwargs)
        return wrapper
    return decorator

@with_retry(max_retries=3)
def add_lead_to_campaign(campaign_id: str, lead: dict):
    return instantly_api.leads.add(campaign_id, lead)
```

---

## Campaign Templates

### Template: Competitor Follower

```
Subject: {{firstName}}, noticed you follow {{sourceName}}

Hi {{firstName}},

I saw you're following {{sourceName}} – sounds like {{painPoint}} might be on your radar.

We just helped {{caseStudy}} tackle this exact challenge.

Worth a quick chat to see if we could help {{companyName}}?

Best,
Chris

P.S. {{mutualConnections}} – small world!
```

### Template: Event Attendee

```
Subject: {{eventName}} follow-up

{{firstName}},

Great seeing {{companyName}} represented at {{eventName}}.

The session on {{engagementContent}} really resonated – it's exactly what we're solving for teams like yours.

Any chance you're exploring solutions in this space?

Chris
```

---

*Document Version: 1.0*
*Last Updated: 2026-01-15*
*Owner: Alpha Swarm Integration Team*
