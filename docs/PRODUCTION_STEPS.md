# 📋 Production Readiness Step-by-Step Guide

> Complete walkthrough from zero to bulletproof daily operations

**Updated**: 2026-01-15 | **Version**: 2.0 (with Async HTTP, Idempotency, Webhooks)

---

## Table of Contents

1. [Phase 1: Prerequisites & APIs](#phase-1-prerequisites--apis)
2. [Phase 2: MCP Server Setup](#phase-2-mcp-server-setup)
3. [Phase 3: Webhook Configuration](#phase-3-webhook-configuration)
4. [Phase 4: Data Ingestion](#phase-4-data-ingestion)
5. [Phase 5: AE Validation & ICP Calibration](#phase-5-ae-validation--icp-calibration)
6. [Phase 6: Staging Environment Testing](#phase-6-staging-environment-testing)
7. [Phase 7: Scheduler Setup](#phase-7-scheduler-setup)
8. [Phase 8: Dashboard Launch](#phase-8-dashboard-launch)
9. [Phase 9: Pilot Mode](#phase-9-pilot-mode)
10. [Phase 10: Full Production](#phase-10-full-production)

---

## Phase 1: Prerequisites & APIs

### Step 1.1: Install Dependencies

```powershell
cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
.\.venv\Scripts\Activate.ps1

# Install production dependencies
pip install aiohttp flask pymupdf paddleocr pyyaml mcp rich
```

### Step 1.2: Configure Environment

Open your `.env` file and fill in all required values:

```bash
# Required APIs
INSTANTLY_API_KEY=your_key_here
GHL_API_KEY=your_key_here
GHL_LOCATION_ID=your_location_here
CLAY_API_KEY=your_key_here
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx

# Webhook Secrets (generate strong random strings)
GHL_WEBHOOK_SECRET=your_random_secret_here
INSTANTLY_WEBHOOK_SECRET=your_random_secret_here

# AI Models
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
```

### Step 1.3: Test Connections

```powershell
python execution\test_connections.py
```

**Expected Output:**
```
✅ Instantly API: Connected
✅ GoHighLevel API: Connected  
✅ Anthropic API: Connected
✅ Slack Webhook: Configured
```

---

## Phase 2: MCP Server Setup

### Step 2.1: Verify MCP Servers

```powershell
# Test GHL MCP (async + idempotent)
python mcp-servers/ghl-mcp/server.py --help

# Test Instantly MCP (complete lifecycle)
python mcp-servers/instantly-mcp/server.py --help

# Test Document MCP
python mcp-servers/document-mcp/server.py --help
```

### Step 2.2: Start MCP Servers (Development)

```powershell
# In separate terminals:
python mcp-servers/ghl-mcp/server.py
python mcp-servers/instantly-mcp/server.py
python mcp-servers/document-mcp/server.py
```

### Step 2.3: Test Idempotency

```powershell
# The idempotency system stores keys in:
dir .hive-mind/idempotency/
```

**Key Features Activated:**
| MCP Server | Async HTTP | Idempotency | Rate Limiting |
|------------|------------|-------------|---------------|
| ghl-mcp | ✅ aiohttp | ✅ 24h expiry | ✅ 60/min |
| instantly-mcp | ✅ aiohttp | ✅ 24h expiry | ✅ Auto |
| document-mcp | N/A | N/A | N/A |

---

## Phase 3: Webhook Configuration

### Step 3.1: Start Webhook Server

```powershell
# Start webhook server
python webhooks/webhook_server.py --port 8080
```

**Endpoints Created:**
| Endpoint | Source | Purpose |
|----------|--------|---------|
| `POST /webhook/ghl` | GoHighLevel | Contact/opportunity events |
| `POST /webhook/instantly` | Instantly | Email opens, clicks, replies |
| `POST /webhook/rb2b` | RB2B | Visitor identification |
| `GET /webhook/events` | Debug | View recent events |
| `GET /health` | Monitoring | Health check |

### Step 3.2: Configure GoHighLevel Webhooks

1. Login to GoHighLevel
2. Go to Settings → Integrations → Webhooks
3. Add webhook URL: `https://your-domain.com/webhook/ghl`
4. Select events:
   - ContactCreate
   - OpportunityCreate
   - OpportunityStageUpdate
   - InboundMessage
5. Copy the webhook secret to `.env` as `GHL_WEBHOOK_SECRET`

### Step 3.3: Configure Instantly Webhooks

1. Login to Instantly
2. Go to Settings → Webhooks
3. Add webhook URL: `https://your-domain.com/webhook/instantly`
4. Select events:
   - email_replied
   - email_bounced
   - email_unsubscribed

### Step 3.4: Configure RB2B Webhooks

1. Login to RB2B
2. Go to Settings → Integrations
3. Add webhook URL: `https://your-domain.com/webhook/rb2b`

### Step 3.5: Test Webhooks Locally (ngrok)

```powershell
# Install ngrok if needed
choco install ngrok

# Expose local webhook server
ngrok http 8080

# Use the ngrok URL for testing webhook configuration
```

---

## Phase 4: Data Ingestion

### Step 4.1: View the Guide

```powershell
python execution\run_full_ingestion.py --guide
```

### Step 4.2: Run Full Ingestion

```powershell
python execution\run_full_ingestion.py --full
```

This will:
1. Import campaign analytics from Instantly (last 90 days)
2. Import email templates and voice patterns
3. Import deals from GoHighLevel (last 180 days)
4. Calculate baseline metrics
5. Generate AE validation template

### Step 4.3: Verify Ingestion

```powershell
# Check what was imported
dir .hive-mind\knowledge\campaigns
dir .hive-mind\knowledge\templates
dir .hive-mind\knowledge\deals

# View baseline metrics
Get-Content .hive-mind\knowledge\campaigns\_baselines.json | ConvertFrom-Json | Format-List
```

---

## Phase 5: AE Validation & ICP Calibration

### Step 5.1: Generate Validation Template

```powershell
python execution\icp_calibrate.py --generate-template --num-leads 50
```

This creates: `.tmp\ae_validation_template.json`

### Step 5.2: AE Reviews 50 Leads

Have your AE review each lead in the template file:

```json
{
    "lead_id": "example_1",
    "name": "John Doe",
    "title": "VP of Sales",
    "company": "Example Corp",
    "system_score": 82,
    "system_tier": "tier2_high",
    "ae_agrees": false,
    "ae_tier": "tier1_vip",
    "reason": "Fortune 500 company, should be VIP",
    "override_direction": "upgrade"
}
```

### Step 5.3: Run Calibration

```powershell
python execution\icp_calibrate.py --calibrate --feedback .tmp\ae_validation_template.json
```

---

## Phase 6: Staging Environment Testing

### Step 6.1: Create Staging Environment

```powershell
# Copy staging template
copy .env.staging.example .env.staging

# Edit with staging API keys (separate test accounts)
notepad .env.staging
```

### Step 6.2: Run Integration Tests

```powershell
# Run all tests in staging mode
python tests/integration_tests.py --env staging

# Run specific test suites
python tests/integration_tests.py --suite mcp
python tests/integration_tests.py --suite webhooks
python tests/integration_tests.py --suite pipeline
```

**Expected Output:**
```
┌─────────────────────────┐
│ Test Results            │
├─────────────────────────┤
│ Tests Run: 25           │
│ Passed: 25              │
│ Failed: 0               │
│ Errors: 0               │
└─────────────────────────┘
✓ All tests passed!
```

### Step 6.3: Test RPI Workflow

```powershell
python tests/test_rpi_workflow.py
```

### Step 6.4: Test Document Extraction

```powershell
# Parse a sample document
python core/document_parser.py -i sample_docs/test_company.pdf --schema lead
```

---

## Phase 7: Scheduler Setup

### Step 7.1: View Scheduler Help

```powershell
.\scripts\setup_scheduler.ps1 -Help
```

### Step 7.2: Install Scheduled Tasks

**⚠️ Run PowerShell as Administrator:**

```powershell
cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
.\scripts\setup_scheduler.ps1 -Install
```

**Scheduled Tasks Created:**
| Task | Time | Purpose |
|------|------|---------|
| DailyScrape | 9:00 PM PHT | LinkedIn scraping |
| DailyEnrich | 11:00 PM PHT | Lead enrichment |
| DailyDocEnrich | 11:30 PM PHT | Document enrichment |
| DailyCampaign | 12:00 AM PHT | Campaign generation (RPI) |
| DailyAnneal | 8:00 AM PHT | Self-annealing |
| WebhookServer | Always | Webhook handler |

### Step 7.3: Verify Tasks

```powershell
.\scripts\setup_scheduler.ps1 -Status
```

---

## Phase 8: Dashboard Launch

### Step 8.1: Start GATEKEEPER Dashboard

```powershell
python execution\gatekeeper_queue.py --serve
```

### Step 8.2: Access Dashboard

Open in browser: **http://localhost:5000**

### Step 8.3: Dashboard Features

| Page | Purpose |
|------|---------|
| `/` | Dashboard home with stats + semantic anchors |
| `/campaigns` | All pending campaigns |
| `/campaign/<id>` | Campaign detail view + approval |
| `/analytics` | Rejection patterns for self-annealing |

**New Features in v2.0:**
- Semantic anchors displayed for each campaign
- Visual grounding (document source references)
- RPI workflow indicator

---

## Phase 9: Pilot Mode

### Step 9.1: Enable Shadow Mode

For the first 2-3 days, run in shadow mode (no actual sends):

```powershell
$env:SHADOW_MODE = "true"
```

### Step 9.2: Manual Test Run

```powershell
# Run RPI workflow
python execution/rpi_research.py --input .hive-mind/segmented/latest.json
python execution/rpi_plan.py --research .hive-mind/research/research_*.json
python execution/rpi_implement.py --plan .hive-mind/plans/plan_*.json

# Queue for review
python execution/gatekeeper_queue.py --input .hive-mind/campaigns/campaigns_rpi_*.json
```

### Step 9.3: Test Webhook Flow

```powershell
# Verify webhook events are being received
curl http://localhost:8080/webhook/events
```

### Step 9.4: Check Health

```powershell
python execution\health_check.py
```

---

## Phase 10: Full Production

### Step 10.1: Disable Shadow Mode

```powershell
$env:SHADOW_MODE = "false"
```

### Step 10.2: Daily Operations Checklist

**Morning (8:00 AM):**
- [ ] Check Slack for overnight alerts
- [ ] Run `python execution\health_check.py`
- [ ] Check webhook server: `curl http://localhost:8080/health`
- [ ] Open GATEKEEPER dashboard
- [ ] Review semantic anchors + approve campaigns

**Midday (12:00 PM):**
- [ ] Check for inbound replies: `dir .hive-mind/replies/`
- [ ] Process hot leads from RB2B: `dir .hive-mind/hot_leads/`

**End of Day (6:00 PM):**
- [ ] Run `python execution\generate_daily_report.py --print`
- [ ] Log any issues or learnings

**Weekly (Friday):**
- [ ] Run integration tests: `python tests/integration_tests.py`
- [ ] Review rejection patterns in Analytics
- [ ] Run self-annealing cycle
- [ ] Update ICP calibration if needed

---

## Troubleshooting

### Async HTTP Issues

```powershell
# Verify aiohttp is installed
pip show aiohttp

# Test async client
python -c "import aiohttp; print('aiohttp OK')"
```

### Idempotency Issues

```powershell
# Clear idempotency cache (use with caution)
Remove-Item .hive-mind/idempotency/*.json

# Check idempotency log
dir .hive-mind/idempotency/
```

### Webhook Not Receiving Events

1. Check webhook server is running: `curl http://localhost:8080/health`
2. Check ngrok (if using): `ngrok status`
3. Verify webhook URL in GHL/Instantly settings
4. Check event log: `curl http://localhost:8080/webhook/events`

### MCP Server Errors

```powershell
# Test MCP imports
python -c "from mcp.server import Server; print('MCP OK')"

# Check server logs
$env:LOG_LEVEL = "DEBUG"
python mcp-servers/ghl-mcp/server.py
```

---

## Commands Quick Reference

```powershell
# MCP Servers
python mcp-servers/ghl-mcp/server.py
python mcp-servers/instantly-mcp/server.py
python mcp-servers/document-mcp/server.py

# Webhook Server
python webhooks/webhook_server.py --port 8080

# Integration Tests
python tests/integration_tests.py --env staging
python tests/integration_tests.py --suite mcp

# RPI Workflow
python execution/rpi_research.py --input FILE
python execution/rpi_plan.py --research FILE
python execution/rpi_implement.py --plan FILE

# Document Extraction
python core/document_parser.py -i FILE --schema lead
python execution/enricher_document_ai.py --batch FILE --documents DIR

# Health & Reports
python execution\health_check.py
python execution\generate_daily_report.py --print
```

---

## Key Files (v2.0)

| File | Purpose |
|------|---------|
| `.env` | Production API credentials |
| `.env.staging.example` | Staging template |
| `.hive-mind/idempotency/` | Idempotency key cache |
| `.hive-mind/webhook_events/` | Webhook event log |
| `.hive-mind/replies/` | Inbound email replies |
| `.hive-mind/hot_leads/` | RB2B visitor data |
| `.hive-mind/unsubscribes.json` | Compliance list |
| `webhooks/webhook_server.py` | Webhook handler |
| `tests/integration_tests.py` | Integration tests |

---

*Last Updated: 2026-01-15*
*Version: 2.0 (Async HTTP, Idempotency, Webhooks, Integration Tests)*
