# Instantly.ai Integration Specification (API V2)

> Complete configuration guide for Instantly email outreach integration with Alpha Swarm
> **API Version**: V2 (migrated from V1 on 2026-02-14, V1 deprecated Jan 19, 2026)
> **Last Updated**: 2026-02-15

---

## Overview

Instantly.ai handles all **cold email outreach** operations including campaign management, lead sequencing, multi-mailbox rotation, and delivery optimization. GHL handles nurture/warm email separately.

### Domain Isolation Strategy

| Channel | Platform | Domain(s) | Purpose |
|---------|----------|-----------|---------|
| Cold outreach | Instantly | b2b.chiefaiofficer.com, business.chiefaiofficer.com, chiefaiofficer.com, getchiefai.com, chiefaitrends.com | New prospect cold emails |
| Nurture/warm | GHL (LC Email) | chiefai.ai | Warm leads, follow-ups, booking confirmations |

> **NEVER use chiefai.ai for Instantly cold outreach. Reputation isolation is non-negotiable.**

---

## API V2 Authentication

### Key Differences from V1

| Property | V1 (Deprecated) | V2 (Current) |
|----------|-----------------|--------------|
| Auth method | `?api_key=` query param | `Authorization: Bearer <key>` header |
| Base URL | `https://api.instantly.ai/api/v1` | `https://api.instantly.ai/api/v2` |
| API keys | V1 keys | V2 keys (must generate new) |
| Campaign status | String | Integer (0=DRAFTED, 1=ACTIVE, 2=PAUSED, 3=COMPLETED) |
| Pagination | `skip`/`offset` | Cursor-based (`starting_after`) |
| Lead add | `POST /lead/add` | `POST /leads/bulk` |
| Lead list | `GET /lead/list` | `POST /leads/list` |
| Lead delete | `POST /lead/delete` | `DELETE /leads` |

### Environment Configuration

```env
INSTANTLY_API_KEY=<V2 Bearer token>
INSTANTLY_WORKSPACE_ID=<workspace UUID>
```

### Generate V2 API Key

1. Log into Instantly dashboard
2. Navigate to **Settings > Integrations > API**
3. Click **Generate API Key** (generates V2 key)
4. Copy and store — set as `INSTANTLY_API_KEY` in Railway

---

## V2 API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/campaigns` | POST | Create campaign (starts as DRAFTED) |
| `/campaigns/{id}` | PATCH | Update campaign settings |
| `/campaigns/{id}` | DELETE | Delete campaign |
| `/campaigns` | GET | List campaigns (cursor pagination) |
| `/campaigns/{id}/pause` | POST | Pause active campaign |
| `/campaigns/{id}/activate` | POST | Activate drafted/paused campaign |
| `/campaigns/analytics` | GET | Campaign metrics |
| `/leads/bulk` | POST | Add leads to campaign (bulk) |
| `/leads/list` | POST | List/search leads |
| `/leads` | DELETE | Remove lead from campaign |
| `/webhooks` | POST | Register webhook |
| `/webhooks` | GET | List webhooks |
| `/webhooks/{id}` | DELETE | Delete webhook |
| `/webhooks/{id}/test` | POST | Test webhook |

---

## Campaign Setup

### V2 Safety: DRAFTED by Default

Campaigns created via V2 API start in **DRAFTED** state (status=0). They **cannot send** until explicitly activated via `POST /campaigns/{id}/activate`. This is the natural paused-by-default behavior — no safety hack needed.

### Campaign Naming Convention

```
{tier}_{source}_{date}_{variant}

Examples:
- t1_pipeline_20260215_v1
- t2_event-attendees_20260215_v1
- t3_group-members_20260215_a-test
```

### Campaign Structure (V2 Format)

```json
{
  "name": "t1_pipeline_20260215_v1",
  "email_list": [
    "chris@b2b.chiefaiofficer.com",
    "chris@business.chiefaiofficer.com",
    "chris@chiefaiofficer.com"
  ],
  "campaign_schedule": {
    "schedules": [{
      "name": "Default",
      "timezone": "America/New_York",
      "days": {
        "monday": true,
        "tuesday": true,
        "wednesday": true,
        "thursday": true,
        "friday": true,
        "saturday": false,
        "sunday": false
      },
      "timing": {
        "from": "08:00",
        "to": "18:00"
      }
    }]
  },
  "sequences": [{
    "steps": [{
      "type": "email",
      "delay": 0,
      "variants": [{
        "subject": "{{firstName}}, quick question about {{companyName}}",
        "body": "Personalized email body..."
      }]
    }]
  }],
  "stop_on_reply": true,
  "daily_limit": 50,
  "email_gap": 90
}
```

### Required Campaign Settings

| Setting | Value | Reason |
|---------|-------|--------|
| Daily sending limit | 50 per mailbox | Deliverability |
| Email gap | 90 seconds | Natural cadence |
| Working hours | 8am-6pm recipient TZ | Open rates |
| Weekend sending | Disabled | B2B best practice |
| Reply detection | stop_on_reply: true | Auto-pause |
| Warmup | Enabled in dashboard | New mailboxes |

### Multi-Step Sequence (V2 Format)

V2 sequences are inline on campaign create/update — no separate endpoint.

| Step | Delay (days) | Purpose |
|------|-------------|---------|
| 1 | 0 | Personalized opener |
| 2 | 2 | Reply bump |
| 3 | 5 | Value add / case study |
| 4 | 9 | Social proof |
| 5 | 14 | Soft breakup |

```json
{
  "sequences": [{
    "steps": [
      {"type": "email", "delay": 0, "variants": [{"subject": "...", "body": "..."}]},
      {"type": "email", "delay": 2, "variants": [{"subject": "...", "body": "..."}]},
      {"type": "email", "delay": 5, "variants": [{"subject": "...", "body": "..."}]},
      {"type": "email", "delay": 9, "variants": [{"subject": "...", "body": "..."}]},
      {"type": "email", "delay": 14, "variants": [{"subject": "...", "body": "..."}]}
    ]
  }]
}
```

A/B variant support: add multiple objects in the `variants` array per step.

---

## Lead Variable Mapping

### Standard Variables

| Variable | Description | Source |
|----------|-------------|--------|
| `{{firstName}}` | First name | Apollo enrichment |
| `{{lastName}}` | Last name | Apollo enrichment |
| `{{email}}` | Email address | Apollo enrichment |
| `{{companyName}}` | Company name | Apollo enrichment |
| `{{title}}` | Job title | Apollo enrichment |

### Custom Variables (Alpha Swarm Specific)

| Variable | Description | Source |
|----------|-------------|--------|
| `{{sourceType}}` | How we found them | Pipeline |
| `{{painPoint}}` | Primary pain point | Enrichment |
| `{{icpScore}}` | ICP score | Segmentor |
| `{{icpTier}}` | ICP tier | Segmentor |
| `{{campaignType}}` | Campaign type | Crafter |
| `{{ghl_contact_id}}` | GHL contact ID | Pipeline sync |
| `{{shadow_email_id}}` | Shadow email ID | Dispatcher |
| `{{pipeline_run_id}}` | Pipeline run ID | Pipeline |

### Lead Payload (V2 Bulk Format)

```json
{
  "campaign": "campaign-uuid-here",
  "leads": [
    {
      "email": "john@company.com",
      "first_name": "John",
      "last_name": "Doe",
      "company_name": "Acme Inc",
      "custom_variables": {
        "title": "VP of Revenue Operations",
        "icpScore": "87",
        "icpTier": "tier_1",
        "sourceType": "pipeline",
        "ghl_contact_id": "contact_xyz789",
        "shadow_email_id": "se_abc123",
        "pipeline_run_id": "run_001"
      }
    }
  ],
  "skip_if_in_workspace": true,
  "skip_if_in_campaign": true
}
```

> **V2 Note**: `custom_variables` values must be scalar (string/number/boolean/null). No nested objects.

---

## Sending Accounts

### Multi-Mailbox Rotation

20+ email accounts warming up since Feb 12, 2026 across 5 isolated cold domains:

| Domain | Purpose | Warmup Status |
|--------|---------|---------------|
| b2b.chiefaiofficer.com | Cold outreach (primary) | Stage 3 (most warmed) |
| business.chiefaiofficer.com | Cold outreach | Stage 1 |
| chiefaiofficer.com | Cold outreach (original) | Warming |
| getchiefai.com | Cold outreach | Warming |
| chiefaitrends.com | Cold outreach | Warming |

### Warmup Ramp Schedule

| Week | Daily Emails/Mailbox | Total Capacity (20 accounts) |
|------|---------------------|------------------------------|
| Week 1 (Feb 12-18) | 5 | ~100/day |
| Week 2 (Feb 19-25) | 10 | ~200/day |
| Week 3 (Feb 26-Mar 4) | 15 | ~300/day |
| Week 4+ (Mar 5+) | 25 | ~500/day |

### Accounts Per Campaign

Config: `sending_accounts.accounts_per_campaign: 3`
Rotation: `round_robin`

---

## Webhook Configuration

### V2 Programmatic Webhook CRUD

V2 provides full webhook API — no manual Instantly dashboard config needed.

```python
# Register all webhooks programmatically
result = await client.setup_webhooks(
    "https://caio-swarm-dashboard-production.up.railway.app"
)
```

### Webhook Events

| Event | Webhook URL | Handler |
|-------|-------------|---------|
| reply_received | `/webhooks/instantly/reply` | Route to RESPONDER, update GHL tag |
| email_bounced | `/webhooks/instantly/bounce` | Remove from list, update GHL |
| email_opened | `/webhooks/instantly/open` | Track engagement |
| lead_unsubscribed | `/webhooks/instantly/unsubscribe` | Add to suppression JSONL, update GHL |

### Webhook Handler Location

**File**: `webhooks/instantly_webhook.py`

Handlers registered in `dashboard/health_app.py` via FastAPI router.

---

## Suppression List

### Append-Only JSONL Format

**File**: `.hive-mind/unsubscribes.jsonl`

```jsonl
{"email": "john@example.com", "at": "2026-02-15T10:00:00+00:00"}
{"email": "jane@example.com", "at": "2026-02-15T11:30:00+00:00"}
```

- Append-only (no read-modify-write race condition)
- Checked before lead dispatch via `_is_suppressed()`
- Fed by: unsubscribe webhooks, bounce webhooks, GHL sync

---

## Dispatcher

### File: `execution/instantly_dispatcher.py`

**Workflow**:
1. Scan `.hive-mind/shadow_mode_emails/` for `status="approved"`
2. Filter out already-dispatched (have `instantly_campaign_id`)
3. Check daily ceiling (defense in depth)
4. Check EMERGENCY_STOP
5. Group by ICP tier → campaign naming convention
6. Create DRAFTED Instantly campaigns via V2 API
7. Add leads with custom_variables + sending accounts (email_list)
8. Record dispatch state in each shadow email file
9. Log to `.hive-mind/instantly_dispatch_log.jsonl`

**Safety**: If `add_leads` fails, orphaned campaign is auto-deleted (rollback).

### CLI Usage

```bash
# Dry run (default)
python execution/instantly_dispatcher.py --dry-run

# Live dispatch with specific from-email
python execution/instantly_dispatcher.py --live --from-email chris@b2b.chiefaiofficer.com

# Filter by tier, override limit
python execution/instantly_dispatcher.py --live --tier tier_1 --limit 10

# JSON output
python execution/instantly_dispatcher.py --dry-run --json
```

---

## MCP Server

### File: `mcp-servers/instantly-mcp/server.py`

### Available Tools

| Tool | Description |
|------|-------------|
| `instantly_create_campaign` | Create campaign (idempotent, starts DRAFTED) |
| `instantly_update_campaign` | Update campaign settings |
| `instantly_add_leads` | Add leads to campaign (bulk, dedup) |
| `instantly_get_analytics` | Campaign metrics |
| `instantly_pause_campaign` | Pause/resume campaign |
| `instantly_activate_campaign` | Activate DRAFTED campaign (only way to go live) |
| `instantly_list_campaigns` | List all campaigns (cursor pagination) |
| `instantly_delete_campaign` | Delete campaign permanently |
| `instantly_create_sequence` | Multi-step sequence with A/B variants |
| `instantly_get_lead_status` | Check lead email status |
| `instantly_export_replies` | Export interested leads |
| `instantly_setup_webhooks` | Register all webhook subscriptions |

---

## Rate Limits

### API Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| Lead operations | 1000/hour | Per API key |
| Campaign operations | 100/hour | Per API key |
| Analytics | 500/hour | Per API key |
| Bulk operations | 10/minute | Per API key |

### Daily Ceiling (Defense in Depth)

**Config**: `guardrails.email_limits.daily_limit: 25`
**State file**: `.hive-mind/instantly_dispatch_state.json`

The dispatcher enforces its own daily ceiling independently of Instantly's campaign limits.

---

## Error Handling

### V2 API Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 401 | Invalid/expired V2 API key | Regenerate V2 key in Instantly dashboard |
| 400 | Invalid request | Check V2 payload format |
| 404 | Campaign/lead not found | Skip or recreate |
| 429 | Rate limited | Exponential backoff (built into client) |
| 500 | Server error | Retry with backoff (3 attempts) |

### V2 Gotchas

- V1 keys do NOT work with V2 — must generate new key
- Campaign status is integer: 0=DRAFTED, 1=ACTIVE, 2=PAUSED, 3=COMPLETED
- Leads bulk uses `campaign` key at top level (not `campaign_id`)
- Lead list is POST (not GET), lead delete is DELETE (not POST)
- Pagination is cursor-based (`starting_after`, not `skip`)

---

## Campaign-GHL Sync

### Lead Status Mapping

| Instantly Status | GHL Tag | GHL Pipeline Stage |
|------------------|---------|-------------------|
| DRAFTED | `status-in-sequence` | In Sequence |
| ACTIVE | `status-in-sequence` | In Sequence |
| PAUSED | `status-in-sequence` | In Sequence |
| Replied | `status-replied` | Replied |
| COMPLETED | `status-sequence-completed` | Nurture |
| Bounced | `status-bounced` | Disqualified |
| Unsubscribed | `status-unsubscribed` | Disqualified |

---

## Agent Ownership

| Responsibility | Agent |
|----------------|-------|
| Campaign dispatch | OPERATOR |
| Lead management | OPERATOR |
| Campaign lifecycle | OPERATOR |
| Reply/webhook processing | RESPONDER |
| Channel routing (email vs LinkedIn) | QUEEN |
| Approval gate | GATEKEEPER |
| Analytics/reporting | COACH |

---

*Document Version: 2.0 (V2 API)*
*Last Updated: 2026-02-15*
*Owner: Alpha Swarm Integration Team*
