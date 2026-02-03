# 🚀 Chief AI Officer Beta Swarm - Production Roadmap

> **Version**: 2.0 | **Created**: 2026-01-23 | **Status**: Shadow Mode Active

---

## Executive Assessment

### Current State: **75% Production-Ready**

| Component | Status | Readiness |
|-----------|--------|-----------|
| Core Architecture | ✅ Solid | 90% |
| Security (AIDefence) | ✅ Implemented | 85% |
| Approval Engine | ✅ Implemented | 85% |
| Audit Trail | ✅ Implemented | 90% |
| Health Monitor | ✅ Implemented | 80% |
| Hot Lead Detection | ✅ Implemented | 80% |
| Production Config | ✅ Created | 100% |
| Webhook Integration | 🟡 Configured, needs GHL setup | 60% |
| API Credentials | 🔴 Missing production keys | 30% |
| Business Data Ingestion | 🟡 Partial | 50% |

---

## ⚠️ CRITICAL: Simplification Required Before Production

### Overengineering Issues Identified

The Oracle review identified **significant redundancy** that increases complexity, debugging time, and failure surface area:

#### 1. Triple Guardrails Problem
Currently 3 overlapping enforcement layers:
- `unified_guardrails.py` - permissions + rate limits + circuit breakers + audit
- `ghl_guardrails.py` - action validation + deliverability + approval + audit  
- `ghl_execution_gateway.py` - permissions + circuit breakers + orchestrator + audit

**DECISION: Keep 2 layers only**
- ✅ `GHLExecutionGateway` - Single entry point for all GHL actions
- ✅ `UnifiedGuardrails` - Policy engine (calls ApprovalEngine + AuditTrail)
- ❌ `ghl_guardrails.py` - Demote to library (keep only EmailDeliverabilityGuard)

#### 2. Triple Audit Problem
Currently 4 separate audit systems:
- `audit_trail.py` → SQLite + backups ✅ **KEEP**
- `unified_guardrails.py` → `guardrails_audit.json`
- `ghl_guardrails.py` → `action_audit_log.json`
- `ghl_execution_gateway.py` → `gateway_audit.json`

**DECISION: Single audit sink**
- ✅ Keep `audit_trail.py` (SQLite) as authoritative
- ❌ Remove JSON audit writers after shadow mode parity confirmed

#### 3. Duplicate ActionType/RiskLevel Enums
Both `unified_guardrails.py` and `ghl_guardrails.py` define `ActionType` and `RiskLevel` with different values.

**DECISION: Single source of truth**
- ✅ Keep `unified_guardrails.ActionType` + `RiskLevel`
- ❌ Remove from `ghl_guardrails.py`

#### 4. 12 Agents → 6 Core Agents
For initial production, 12 agents is overkill. Consolidate to 6 functional roles:

| Keep Active | Role | Merges |
|-------------|------|--------|
| UNIFIED_QUEEN | Orchestrator | - |
| HUNTER | Research + Sourcing | + RESEARCHER |
| ENRICHER | Data Enrichment | - |
| SEGMENTOR | ICP + Scoring | - |
| CRAFTER | Messaging | + COACH (personalization) |
| OPERATOR | Execution | + GATEKEEPER approval, SCHEDULER, PIPER, SCOUT |

**Inactive until proven necessary:** SCOUT, COACH, PIPER, SCHEDULER, RESEARCHER, GATEKEEPER (approval moves to OPERATOR)

---

## Phase 1: Simplification Sprint (Before Production)

### 1.1 Consolidate Guardrails (Effort: L, 1-2 days)

```
Before:
  Gateway → checks permissions → calls GHLGuardrails → calls UnifiedGuardrails → audit log x3

After:
  Gateway → calls UnifiedGuardrails.execute_with_guardrails() → AuditTrail.log_event()
```

**Tasks:**
- [ ] Remove `ActionType`, `RiskLevel`, `ActionValidator` from `ghl_guardrails.py`
- [ ] Extract `EmailDeliverabilityGuard` as standalone library
- [ ] Update `GHLExecutionGateway.execute()` to call `UnifiedGuardrails` directly
- [ ] Remove approval logic from `ghl_guardrails.py` (use `ApprovalEngine` only)
- [ ] Remove JSON audit writes from all files except shadow mode logging

### 1.2 Consolidate PII Redaction (Effort: M, 1-3 hours)

**Current:** 3 implementations
- `aidefence.py` → PII detector
- `audit_trail.py` → PIIRedactor  
- `unified_guardrails.py` → `redact_pii()`

**Decision:**
- [ ] Keep `audit_trail.PIIRedactor` as single implementation
- [ ] `AIDefence` returns detection signals only (no redaction)
- [ ] Remove `UnifiedGuardrails.redact_pii()` - let AuditTrail handle

### 1.3 Agent Reduction (Effort: M, 1-3 hours)

- [ ] Update `config/production.json` to disable 6 agents
- [ ] Merge GATEKEEPER approval into OPERATOR workflow
- [ ] Update permission matrix to 6 active agents
- [ ] Update tests to reflect 6-agent model

---

## Phase 2: Environment Variables

### Required (.env) - BLOCKING PRODUCTION

```bash
# =============================================================================
# GOHIGHLEVEL (REQUIRED) - Primary CRM & Email Platform
# =============================================================================
GHL_PROD_API_KEY=           # Get from GHL → Settings → API Keys
GHL_LOCATION_ID=            # Get from GHL → Settings → Business Info
GHL_BASE_URL=https://services.leadconnectorhq.com

# =============================================================================
# SUPABASE (REQUIRED) - Data Persistence
# =============================================================================
SUPABASE_URL=               # Get from Supabase → Project Settings → API
SUPABASE_KEY=               # Anon public key (not service role for prod!)

# =============================================================================
# ENRICHMENT (REQUIRED) - Lead Data Enhancement
# =============================================================================
CLAY_API_KEY=               # Get from Clay → Settings → API
PROXYCURL_API_KEY=          # Get from Proxycurl dashboard

# =============================================================================
# RB2B (REQUIRED) - Website Visitor Identification
# =============================================================================
RB2B_API_KEY=               # Get from RB2B → Settings → API
RB2B_WEBHOOK_SECRET=        # Generate secure random string

# =============================================================================
# NOTIFICATIONS (REQUIRED) - Alerts & Approvals
# =============================================================================
SLACK_WEBHOOK_URL=          # Create at api.slack.com → Your Apps → Webhooks
SLACK_BOT_TOKEN=            # Optional: for interactive approvals
```

### Optional (.env) - Enhanced Functionality

```bash
# =============================================================================
# TWILIO (OPTIONAL) - SMS Escalation for Hot Leads
# =============================================================================
TWILIO_ACCOUNT_SID=         # From Twilio Console
TWILIO_AUTH_TOKEN=          # From Twilio Console
TWILIO_FROM_NUMBER=         # Your Twilio phone number

# =============================================================================
# ESCALATION CONTACTS
# =============================================================================
ESCALATION_PHONE_L2=        # AE phone for hot lead alerts
ESCALATION_PHONE_L3=        # VP/CRO phone for critical escalations
ESCALATION_EMAIL_L2=        # AE email
ESCALATION_EMAIL_L3=        # VP email

# =============================================================================
# GOOGLE (OPTIONAL) - Calendar Integration
# =============================================================================
GOOGLE_CREDENTIALS_PATH=./credentials/google_credentials.json
GOOGLE_TOKEN_PATH=./credentials/google_token.json

# =============================================================================
# ZOOM (OPTIONAL) - Meeting Links
# =============================================================================
ZOOM_API_KEY=
ZOOM_API_SECRET=

# =============================================================================
# SMTP (OPTIONAL) - Direct Email Fallback
# =============================================================================
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=

# =============================================================================
# SYSTEM CONFIGURATION
# =============================================================================
LOG_LEVEL=INFO
DASHBOARD_PORT=8080
HEALTH_CHECK_INTERVAL=30
WORKING_HOURS_START=9
WORKING_HOURS_END=18
DEFAULT_TIMEZONE=America/New_York
```

---

## Phase 3: Webhook Setup

### 3.1 GHL Webhook Configuration

**GHL Admin Panel → Settings → Webhooks**

| Webhook | URL | Events |
|---------|-----|--------|
| Lead Events | `https://your-domain.com/webhooks/ghl` | `contact.create`, `contact.update`, `opportunity.status_change` |
| Email Events | `https://your-domain.com/webhooks/ghl` | `email.open`, `email.click`, `email.reply`, `email.bounce` |
| Call Events | `https://your-domain.com/webhooks/ghl` | `call.completed`, `voicemail.received` |
| Form Events | `https://your-domain.com/webhooks/ghl` | `form.submission` |

**Webhook Security:**
```json
{
  "signature_header": "X-GHL-Signature",
  "signature_secret_env": "GHL_WEBHOOK_SECRET"
}
```

### 3.2 RB2B Webhook Configuration

**RB2B Dashboard → Webhooks**

| Webhook | URL | Events |
|---------|-----|--------|
| Visitor Identified | `https://your-domain.com/webhooks/rb2b` | `visitor.identified` |

### 3.3 Deploy Webhook Server

```powershell
# Option A: Local (for testing)
cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
.\.venv\Scripts\Activate.ps1
uvicorn webhooks.webhook_server:app --host 0.0.0.0 --port 8000

# Option B: Production (ngrok tunnel for webhook receipt)
ngrok http 8000

# Option C: Cloud Deployment (recommended)
# Deploy to Cloud Run, Railway, or Fly.io
```

---

## Phase 4: API Integration Checklist

### GHL Integration
- [ ] Generate Production API Key (Settings → API Keys)
- [ ] Note Location ID (Settings → Business Info)
- [ ] Enable required OAuth scopes:
  - `contacts.readonly`, `contacts.write`
  - `opportunities.readonly`, `opportunities.write`
  - `campaigns.readonly`
  - `calendars.readonly`, `calendars.write`
- [ ] Configure webhooks per Section 3.1
- [ ] Test connection: `python execution/test_connections.py --ghl`

### Supabase Integration
- [ ] Create production project (if not exists)
- [ ] Run SQL migrations: `sql/*.sql`
- [ ] Configure RLS policies for swarm service role
- [ ] Note URL and anon key
- [ ] Test connection: `python execution/test_connections.py --supabase`

### Clay Integration
- [ ] Generate API key (Settings → API)
- [ ] Configure enrichment tables
- [ ] Set up waterfall rules
- [ ] Test connection: `python execution/test_connections.py --clay`

### Slack Integration
- [ ] Create Slack App (api.slack.com)
- [ ] Add Incoming Webhook
- [ ] Configure channels:
  - `#swarm-alerts` - System alerts
  - `#hot-leads` - Hot lead notifications
  - `#approvals` - Approval requests
- [ ] Test connection: `python execution/send_alert.py --test`

---

## Phase 5: Revenue Operations Data Files

### Required Files (Create/Update)

| File | Location | Purpose |
|------|----------|---------|
| `icp_criteria.json` | `.hive-mind/knowledge/` | ICP scoring rules |
| `email_templates.json` | `.hive-mind/knowledge/` | Approved email templates |
| `product_offerings.json` | `.hive-mind/knowledge/company/` | Product catalog (exists) |
| `voice_samples.md` | `.hive-mind/knowledge/` | Chris's writing voice |
| `competitor_intel.json` | `.hive-mind/knowledge/company/` | Competitor positioning |
| `objection_library.json` | `.hive-mind/knowledge/` | Objection handling |

### Data Ingestion Priority

**Week 1 (Critical):**
- [ ] Export 50 successful email templates from GHL/Instantly
- [ ] Document ICP validation from last 20 closed deals
- [ ] Capture Chris's writing voice (10 samples)
- [ ] Export win/loss reasons from CRM

**Week 2 (Important):**
- [ ] Historical campaign analytics
- [ ] AE rejection patterns
- [ ] Competitor positioning matrix
- [ ] Objection response library

---

## Phase 6: Rollout Phases

### Shadow Mode (Current) - Week 1-2
```json
{
  "email_behavior.actually_send": false,
  "rollout_phase.current": "shadow",
  "guardrails.block_production_writes": false,
  "logging.capture_all_failures": true
}
```

**Validation Criteria:**
- [ ] 100 leads processed without error
- [ ] All emails logged to `.hive-mind/shadow_mode_emails/`
- [ ] AE reviews 50 sample emails, approves 80%+
- [ ] No PII leaks in logs
- [ ] Hot lead detection triggers correctly

### Parallel Mode - Week 2-3
```json
{
  "email_behavior.actually_send": false,
  "rollout_phase.current": "parallel",
  "comparison_mode": true
}
```

**Validation Criteria:**
- [ ] AI recommendations compared to human decisions
- [ ] Agreement rate > 70%
- [ ] False positive rate < 10%
- [ ] Performance metrics baselined

### Assisted Mode - Week 3-4
```json
{
  "email_behavior.actually_send": true,
  "rollout_phase.current": "assisted",
  "max_auto_approved_per_day": 10
}
```

**Validation Criteria:**
- [ ] First 10 emails sent successfully
- [ ] Open rate > 40%
- [ ] No spam complaints
- [ ] Reply handling works

### Full Operations - Week 5+
```json
{
  "email_behavior.actually_send": true,
  "rollout_phase.current": "full",
  "auto_approve_low_risk": true
}
```

---

## Phase 7: Pre-Flight Checklist

### Before Shadow → Parallel

- [ ] All required env vars populated
- [ ] GHL webhooks configured and receiving
- [ ] Supabase migrations applied
- [ ] Slack alerts working
- [ ] Health dashboard accessible
- [ ] 100 leads processed in shadow mode
- [ ] AE approved 80%+ of sample emails
- [ ] No critical errors in 48 hours

### Before Parallel → Assisted

- [ ] AI vs Human agreement > 70%
- [ ] False positive rate < 10%
- [ ] Domain health score > 70
- [ ] Unsubscribe mechanism tested
- [ ] CAN-SPAM compliance verified
- [ ] Approval workflow tested end-to-end

### Before Assisted → Full

- [ ] 50+ emails sent without issues
- [ ] Open rate > 40%
- [ ] Reply rate > 5%
- [ ] Zero spam complaints
- [ ] Hot lead → AE handoff working
- [ ] Self-annealing patterns captured
- [ ] Weekly report validated

---

## Quick Commands Reference

```powershell
# Health Check
python execution/health_check.py

# Test Connections
python execution/test_connections.py

# Test Alert
python execution/send_alert.py --test

# Run Webhook Server
uvicorn webhooks.webhook_server:app --host 0.0.0.0 --port 8000

# Run Health Dashboard
uvicorn dashboard.health_app:app --host 0.0.0.0 --port 8080

# Daily Workflows
.\scripts\daily_scrape.ps1
.\scripts\daily_enrich.ps1
.\scripts\daily_campaign.ps1
.\scripts\daily_anneal.ps1

# Generate Report
python execution/generate_daily_report.py --print
```

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| API Key Leaks | Low | Critical | PII redaction, .env not in git |
| LinkedIn Blocks | Medium | High | Rate limiting, session rotation |
| Email Spam Reports | Medium | Critical | Human approval, deliverability guards |
| GHL Rate Limits | Low | Medium | Circuit breakers, backoff |
| Data Loss | Low | High | Supabase backups, audit trail |
| Agent Hallucination | Medium | High | Grounding evidence, human approval |

---

## Success Metrics (Target by Week 4)

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Leads Processed/Day | 100+ | < 50 |
| Enrichment Success | ≥ 85% | < 80% |
| ICP Match Rate | ≥ 80% | < 70% |
| AE Approval Rate | ≥ 70% | < 50% |
| Email Open Rate | ≥ 50% | < 40% |
| Reply Rate | ≥ 8% | < 5% |
| Hot Lead Response Time | < 5 min | > 15 min |

---

## Next Steps (Immediate Actions)

1. **TODAY**: Populate required environment variables
2. **TODAY**: Run simplification sprint (consolidate guardrails)
3. **THIS WEEK**: Configure GHL webhooks
4. **THIS WEEK**: Ingest business data (templates, voice, ICP)
5. **NEXT WEEK**: Exit Shadow Mode, enter Parallel Mode

---

*Roadmap Version: 2.0*
*Last Updated: 2026-01-23*
*Owner: Beta Swarm Production Team*
