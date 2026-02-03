# Clay Direct Enrichment Setup Guide

## Overview

This guide shows how to connect your Clay workbook directly to the swarm for automated enrichment.

**Current Flow (Manual):**
```
RB2B → Webhook → Clay Workbook (manual export) → GHL
```

**Optimized Flow (Automated):**
```
RB2B → Swarm Webhook → Clay Webhook → Enrichment → Callback → GHL Auto-Sync
```

---

## Step 1: Get Your Clay Workbook Webhook URL

Your Clay workbook: https://app.clay.com/shared-workbook/share_0t9c5h2Dt6hzzFrz4Gv

1. Open your Clay workbook
2. Click on the **Webhook** source at the top
3. Click **Settings** (gear icon)
4. Copy the **Webhook URL** (looks like: `https://app.clay.com/webhook/...`)
5. Add to your `.env` file:

```bash
CLAY_WORKBOOK_WEBHOOK_URL=https://app.clay.com/webhook/YOUR_WEBHOOK_ID
```

---

## Step 2: Configure Clay Callback Webhook

For Clay to send enriched data back to the swarm, add an HTTP API action to your workbook:

### In Clay Workbook:

1. Add a new column: **"Send to Swarm"** (HTTP API action)
2. Configure:
   - **Method**: POST
   - **URL**: `https://your-domain.com/webhooks/clay/callback`
   - **Headers**:
     ```json
     {
       "Content-Type": "application/json"
     }
     ```
   - **Body**:
     ```json
     {
       "request_id": "{{request_id}}",
       "email": "{{Work Email}}",
       "email_verified": {{Email Verified}},
       "phone": "{{Phone}}",
       "linkedin_url": "{{LinkedIn URL}}",
       "first_name": "{{First Name}}",
       "last_name": "{{Last Name}}",
       "job_title": "{{Job Title}}",
       "company_name": "{{Company Name}}",
       "company_domain": "{{Company Domain}}",
       "industry": "{{Industry}}",
       "employee_count": "{{Employee Count}}",
       "revenue": "{{Revenue}}",
       "icp_score": {{ICP Score}},
       "priority": "{{Priority Tier}}",
       "sources": ["clay"]
     }
     ```

3. Run this column automatically when enrichment completes

---

## Step 3: Start the Callback Webhook Server

```bash
cd chiefaiofficer-alpha-swarm
python core/clay_direct_enrichment.py --serve --port 8001
```

Or add to your main webhook server in `webhooks/webhook_server.py`.

---

## Step 4: Expose Webhook to Internet (Development)

For local development, use ngrok:

```bash
ngrok http 8001
```

Copy the ngrok URL and update your Clay HTTP API action URL.

---

## Step 5: Test the Flow

1. **Trigger a test enrichment**:
```bash
python core/clay_direct_enrichment.py --test
```

2. **Simulate RB2B webhook**:
```bash
curl -X POST http://localhost:8000/webhooks/rb2b \
  -H "Content-Type: application/json" \
  -d '{
    "visitor_id": "test_001",
    "company": {
      "name": "Test Company",
      "domain": "testcompany.com"
    }
  }'
```

3. **Check status**:
```bash
python core/clay_direct_enrichment.py --status
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    OPTIMIZED ENRICHMENT FLOW                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────┐     ┌─────────────┐     ┌─────────────┐               │
│  │  RB2B   │────>│   Swarm     │────>│    Clay     │               │
│  │ Webhook │     │  Webhook    │     │  Workbook   │               │
│  └─────────┘     └─────────────┘     └──────┬──────┘               │
│                                             │                       │
│                                             │ (Enrichment)          │
│                                             ▼                       │
│  ┌─────────┐     ┌─────────────┐     ┌─────────────┐               │
│  │   GHL   │<────│   Swarm     │<────│    Clay     │               │
│  │ Contact │     │  Callback   │     │  HTTP API   │               │
│  │ Created │     │  Webhook    │     │   Action    │               │
│  └─────────┘     └─────────────┘     └─────────────┘               │
│                                                                     │
│  Tags Applied: clay-enriched, priority-{tier}, rb2b-visitor         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Files Created

| File | Purpose |
|------|---------|
| `core/clay_direct_enrichment.py` | Direct Clay integration with webhook support |
| `webhooks/rb2b_webhook.py` | Updated to use Clay Direct Enrichment |

---

## Environment Variables

Add to your `.env`:

```bash
# Clay Direct Enrichment
CLAY_WORKBOOK_WEBHOOK_URL=https://app.clay.com/webhook/YOUR_ID
CLAY_API_KEY=your_clay_api_key  # Already set

# For callback (your exposed webhook URL)
CLAY_CALLBACK_URL=https://your-ngrok-url.ngrok.io/webhooks/clay/callback
```

---

## Monitoring

Check enrichment status:
```bash
python core/clay_direct_enrichment.py --status
```

View queued items:
```bash
dir .hive-mind\clay_enrichment\queue
```

View completed enrichments:
```bash
dir .hive-mind\clay_enrichment\results
```

---

## Fallback Behavior

If the Clay webhook is not configured, the system:
1. Queues enrichment requests to `.hive-mind/clay_enrichment/queue/`
2. You can manually import these into your Clay workbook
3. Export enriched data and place in `.hive-mind/clay_enrichment/results/`
4. System will sync to GHL automatically

---

## Cost Optimization

The Clay workbook uses waterfall enrichment which optimizes credit usage:
1. Try Apollo (cheapest) first
2. Fall back to ZoomInfo
3. Then Clearbit, Hunter.io, Lusha

Set daily spend limits in your Clay account to control costs.

---

*Created: 2026-01-24*
*Version: 1.0*
