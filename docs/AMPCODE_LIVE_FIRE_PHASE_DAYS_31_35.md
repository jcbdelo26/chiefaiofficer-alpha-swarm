# 🔥 Ampcode Live Fire Phase - Days 31-35

> **Transition from Shadow Mode to Production Operations**

**Prerequisites**: Sessions 1-5 complete (Days 1-30), Production config created, Shadow Mode active

---

## Phase Overview

| Day | Focus | Goal |
|-----|-------|------|
| 31 | Simplification Sprint | Eliminate overengineering before live fire |
| 32 | Environment & Webhook Setup | Production credentials + webhooks live |
| 33 | Shadow Mode Validation | 100 leads processed, AE approval >80% |
| 34 | Parallel Mode | AI vs Human comparison, exit criteria validation |
| 35 | Assisted Mode Launch | First real emails sent, hot lead flow tested |

---

## Day 31: Simplification Sprint 🧹 ✅ COMPLETE

**Goal**: Reduce complexity before production. Fix overengineering identified in code review.

**STATUS**: ✅ COMPLETED January 23, 2026

**Changes Made**:
1. ✅ **ghl_guardrails.py** refactored from 1030 → 574 lines (~44% reduction)
   - Removed duplicate ActionType, RiskLevel, ActionValidator, GHLGuardrails, ghl_protected
   - Kept EmailDeliverabilityGuard as core value
   - Added get_email_guard() convenience function

2. ✅ **ghl_execution_gateway.py** updated to use UnifiedGuardrails
   - Now imports from unified_guardrails.py
   - Uses EmailDeliverabilityGuard for email-specific checks
   - Audit logs to AuditTrail (SQLite) instead of JSON

3. ✅ **unified_guardrails.py** updated to use AuditTrail
   - Removed JSON audit file writes
   - Single audit sink via audit_trail.py

4. ✅ **config/production.json** reduced to 6 active agents
   - Active: UNIFIED_QUEEN, HUNTER, ENRICHER, SEGMENTOR, CRAFTER, OPERATOR
   - Disabled: GATEKEEPER, SCOUT, COACH, PIPER, SCHEDULER, RESEARCHER

5. ✅ **tests/test_production_hardening.py** updated for new structure
   - TestGHLGuardrails → TestEmailDeliverabilityGuard
   - All 136 tests passing

### Prompt 31.1: Consolidate Guardrails (CRITICAL)

```
TASK: Consolidate the triple-guardrails problem

Currently we have 3 overlapping enforcement layers:
1. core/ghl_execution_gateway.py - permissions + circuit breakers + audit
2. core/ghl_guardrails.py - action validation + approval + audit
3. core/unified_guardrails.py - permissions + rate limits + circuit breakers + audit

CONSOLIDATION PLAN:
1. Keep GHLExecutionGateway as single entry point for GHL actions
2. Keep UnifiedGuardrails as the policy engine (permissions, rate limits, grounding)
3. Demote ghl_guardrails.py to library - extract ONLY EmailDeliverabilityGuard

FILES TO MODIFY:
- core/ghl_execution_gateway.py: Call UnifiedGuardrails instead of duplicating checks
- core/ghl_guardrails.py: Remove ActionType, RiskLevel, ActionValidator, approval logic
- core/unified_guardrails.py: Ensure it integrates with ApprovalEngine and AuditTrail

REMOVE FROM ghl_guardrails.py:
- ActionType enum (use unified_guardrails.ActionType)
- RiskLevel enum (use unified_guardrails.RiskLevel)
- ActionValidator class (use UnifiedGuardrails)
- pending_approvals dict (use ApprovalEngine)
- approve_action/deny_action methods (use ApprovalEngine)
- JSON audit writes (use AuditTrail)

KEEP IN ghl_guardrails.py (as library):
- EmailDeliverabilityGuard class (domain health, warmup, working hours)
- SENDING_LIMITS constant

Test after: python -m pytest tests/test_unified_guardrails.py tests/test_ghl_guardrails.py -v
```

### Prompt 31.2: Single Audit Sink

```
TASK: Consolidate to single audit system

Currently 4 audit outputs:
1. core/audit_trail.py → SQLite (KEEP - authoritative)
2. unified_guardrails.py → guardrails_audit.json (REMOVE)
3. ghl_guardrails.py → action_audit_log.json (REMOVE)
4. ghl_execution_gateway.py → gateway_audit.json (REMOVE)

CHANGES:
1. In unified_guardrails.py:
   - Remove _audit_log list and JSON persistence
   - Add: from core.audit_trail import AuditTrail
   - Call AuditTrail().log_event() instead of self._audit_log.append()

2. In ghl_execution_gateway.py:
   - Remove JSON audit write
   - Call AuditTrail().log_event() for all gateway actions

3. In ghl_guardrails.py:
   - Remove action_audit_log.json write
   - (Already removed most logic in 31.1)

Test after: python -m pytest tests/test_audit_trail.py -v
Verify: Only .hive-mind/audit.db exists (no JSON audit files created)
```

### Prompt 31.3: Reduce to 6 Active Agents

```
TASK: Update config/production.json to reduce 12 agents to 6 active

ACTIVE AGENTS (keep enabled):
1. UNIFIED_QUEEN - Orchestrator
2. HUNTER - Research + Sourcing (absorbs RESEARCHER role)
3. ENRICHER - Data Enrichment
4. SEGMENTOR - ICP + Scoring
5. CRAFTER - Messaging (absorbs COACH personalization)
6. OPERATOR - Execution (absorbs GATEKEEPER approval, SCHEDULER, PIPER, SCOUT)

DISABLED AGENTS (set alert_on_critical: false, enabled: false):
- SCOUT (merged into OPERATOR)
- COACH (merged into CRAFTER)
- PIPER (merged into OPERATOR)
- SCHEDULER (merged into OPERATOR)
- RESEARCHER (merged into HUNTER)
- GATEKEEPER (approval moves to OPERATOR via ApprovalEngine)

Update failure_tracker.agents in config/production.json accordingly.
```

---

## Day 32: Environment & Webhook Setup 🔌 ✅ SCRIPTS CREATED

**Goal**: All production credentials configured, webhooks receiving events.

**STATUS**: ✅ SCRIPTS CREATED January 23, 2026 (Awaiting credential population)

**Scripts Created**:
1. ✅ `execution/verify_production_env.py` - Checks all required env vars and API connections
2. ✅ `webhooks/webhook_server.py` - Already exists with hot lead detection

**Current Credential Status** (from verify_production_env.py):
- ✅ GHL_LOCATION_ID: Set
- ❌ GHL_PROD_API_KEY: Not set
- ✅ SUPABASE_URL: Set
- ✅ SUPABASE_KEY: Set
- ✅ CLAY_API_KEY: Set
- ✅ SLACK_WEBHOOK_URL: Set
- ❌ RB2B_API_KEY: Not set
- ✅ RB2B_WEBHOOK_SECRET: Set

### Prompt 32.1: Verify Environment Variables

```
TASK: Create execution/verify_production_env.py

Script should:
1. Load config/production.json
2. Check each required env var exists and is non-empty
3. Test each API connection (with timeout)
4. Report status with clear pass/fail

REQUIRED VARS (from production.json.environment_variables_required):
- GHL_PROD_API_KEY
- GHL_LOCATION_ID
- RB2B_WEBHOOK_SECRET
- RB2B_API_KEY
- CLAY_API_KEY
- SUPABASE_URL
- SUPABASE_KEY
- SLACK_WEBHOOK_URL

For each API:
- GHL: GET /locations/{location_id} should return 200
- Supabase: Query system health
- Slack: POST test message (delete after)
- Clay: GET /v1/tables (list tables)

Output format:
✅ GHL_PROD_API_KEY: Set, Connected
✅ SUPABASE_URL: Set, Connected
❌ SLACK_WEBHOOK_URL: Set, NOT Connected (403 Forbidden)

Exit code 1 if any critical var fails.
```

### Prompt 32.2: Start Webhook Server

```
TASK: Deploy and test webhook server

1. Start webhook server:
   python webhooks/webhook_server.py --port 8000

2. Verify endpoints respond:
   - GET /health → 200
   - GET /webhooks/events → 200 (empty list)
   - POST /webhooks/ghl → 200 (with valid payload)
   - POST /webhooks/rb2b → 200 (with valid payload)

3. If using ngrok for testing:
   ngrok http 8000
   
4. Configure GHL webhooks (user action):
   - URL: https://{ngrok-url}/webhooks/ghl
   - Events: contact.create, contact.update, opportunity.status_change,
             email.open, email.click, email.reply, email.bounce

5. Configure RB2B webhooks (user action):
   - URL: https://{ngrok-url}/webhooks/rb2b
   - Events: visitor.identified

Test: Trigger a test event from GHL, verify it appears in /webhooks/events
```

### Prompt 32.3: Test Hot Lead Detection Flow

```
TASK: End-to-end test of hot lead detection

1. Simulate a GHL webhook event with high engagement:
   curl -X POST http://localhost:8000/webhooks/ghl \
     -H "Content-Type: application/json" \
     -d '{
       "type": "email.reply",
       "contact_id": "test_123",
       "email": "test@example.com",
       "message": "Yes, I am very interested in learning more about AI"
     }'

2. Verify hot_lead_detector.py:
   - Sentiment score >= 0.8 triggers HOT alert
   - Slack notification sent
   - Event logged to audit trail

3. Check logs:
   - .hive-mind/hot_leads/ has entry
   - AuditTrail has "hot_lead_detected" event
```

---

## Day 33: Shadow Mode Validation ✅ SCRIPTS CREATED

**Goal**: Process 100 leads, achieve 80%+ AE approval rate on sample emails.

**STATUS**: ✅ SCRIPTS CREATED January 23, 2026

**Scripts Created**:
1. ✅ `execution/validate_shadow_exit.py` - Checks all shadow mode exit criteria

### Prompt 33.1: Run Shadow Mode Pipeline

```
TASK: Execute full pipeline in shadow mode

1. Verify shadow mode active:
   python -c "from config.production_config import get_production_config; c = get_production_config(); print('Shadow Mode:', c['email_behavior']['shadow_mode'])"

2. Run daily scrape (or use test data):
   .\scripts\daily_scrape.ps1
   # OR for testing: python execution/segmentor_classify.py --input .hive-mind/test_leads.json

3. Run enrichment:
   .\scripts\daily_enrich.ps1

4. Run campaign generation:
   .\scripts\daily_campaign.ps1

5. Verify shadow emails logged:
   dir .hive-mind/shadow_mode_emails/
   
6. Count: Should have 100+ leads processed
```

### Prompt 33.2: AE Sample Review

```
TASK: Generate AE review sample

1. Extract 50 shadow emails for AE review:
   python execution/generate_ae_review_sample.py \
     --source .hive-mind/shadow_mode_emails/ \
     --output .tmp/ae_review_sample.json \
     --count 50

2. Sample format for AE:
   {
     "id": "email_001",
     "to": "prospect@company.com",
     "subject": "AI opportunity for Company",
     "body": "...",
     "icp_score": 82,
     "tier": "tier2_high",
     "personalization_fields": ["company_name", "pain_point"],
     "ae_approved": null,
     "ae_notes": ""
   }

3. AE reviews and fills ae_approved (true/false) + ae_notes

4. Calculate approval rate:
   python execution/calculate_approval_rate.py --input .tmp/ae_review_sample.json
   
   Target: >= 80% approval rate
```

### Prompt 33.3: Validate Exit Criteria

```
TASK: Check Shadow Mode exit criteria

Create execution/validate_shadow_exit.py that checks:

1. ✅ 100+ leads processed without errors
2. ✅ All emails logged to shadow_mode_emails/
3. ✅ AE approval rate >= 80% on sample
4. ✅ No PII detected in logs (run AIDefence scan)
5. ✅ Hot lead detection triggered correctly (at least 1 test)
6. ✅ Webhook server running and receiving events
7. ✅ Health dashboard accessible

Output:
```
Shadow Mode Exit Criteria
=========================
✅ Leads processed: 127
✅ Shadow emails logged: 127
✅ AE approval rate: 84% (42/50)
✅ PII in logs: 0 detected
✅ Hot lead test: PASSED
✅ Webhooks: Receiving events
✅ Dashboard: Accessible

RESULT: READY FOR PARALLEL MODE
```

Exit code 0 if all pass, 1 otherwise.
```

---

## Day 34: Parallel Mode 🔄 SCRIPTS CREATED

**Goal**: Compare AI decisions to human decisions, validate agreement rate.

**STATUS**: ✅ SCRIPTS CREATED January 23, 2026

**Scripts Created**:
1. ✅ `execution/compare_parallel_decisions.py` - Compares AI vs AE decisions

### Prompt 34.1: Enable Parallel Mode

```
TASK: Switch from Shadow to Parallel mode

1. Update config/production.json:
   - rollout_phase.current: "parallel"
   - email_behavior.actually_send: false (still no sends)
   - comparison_mode: true

2. In Parallel Mode:
   - AI generates email recommendation
   - Human (AE) makes independent decision
   - System compares and logs agreement/disagreement
   
3. Modify execution/gatekeeper_queue.py to:
   - Show AI recommendation alongside lead data
   - Hide AI recommendation initially (blind review)
   - After AE decision, reveal AI recommendation
   - Log agreement/disagreement to .hive-mind/parallel_mode/
```

### Prompt 34.2: Run Parallel Comparison

```
TASK: Process 50 leads in parallel mode

1. Generate 50 campaign recommendations (AI):
   python execution/crafter_campaign.py --input .hive-mind/enriched/latest.json --parallel-mode

2. Queue for blind AE review:
   python execution/gatekeeper_queue.py --serve --blind-mode

3. AE reviews each lead independently:
   - Approves/rejects based on their judgment
   - Does NOT see AI recommendation yet

4. After AE completes review:
   python execution/compare_parallel_decisions.py \
     --ai-decisions .hive-mind/campaigns/ai_recommendations.json \
     --ae-decisions .hive-mind/gatekeeper/ae_decisions.json

5. Output:
   ```
   Parallel Mode Comparison
   ========================
   Total leads: 50
   AI approved: 42
   AE approved: 38
   Agreement: 44 (88%)
   Disagreement: 6 (12%)
   
   Disagreement breakdown:
   - AI approved, AE rejected: 4 (false positives)
   - AI rejected, AE approved: 2 (false negatives)
   ```
```

### Prompt 34.3: Validate Parallel Exit Criteria

```
TASK: Check Parallel Mode exit criteria

Create execution/validate_parallel_exit.py:

1. ✅ Agreement rate >= 70%
2. ✅ False positive rate < 15% (AI approves, AE rejects)
3. ✅ False negative rate < 10% (AI rejects, AE approves)
4. ✅ No critical misses (Tier 1 VIP leads correctly identified)
5. ✅ Performance metrics baselined

Output:
```
Parallel Mode Exit Criteria
===========================
✅ Agreement rate: 88%
✅ False positive rate: 8%
✅ False negative rate: 4%
✅ Tier 1 accuracy: 100%
✅ Baseline metrics captured

RESULT: READY FOR ASSISTED MODE
```
```

---

## Day 35: Assisted Mode Launch 🚀 SCRIPTS CREATED

**Goal**: First real emails sent, hot lead to AE handoff working.

**STATUS**: ✅ SCRIPTS CREATED January 23, 2026

**Scripts Created**:
1. ✅ `execution/send_approved_emails.py` - Sends emails with safety checks

### Prompt 35.1: Enable Assisted Mode

```
TASK: Switch from Parallel to Assisted mode

1. Update config/production.json:
   - rollout_phase.current: "assisted"
   - email_behavior.actually_send: true
   - max_auto_approved_per_day: 10
   - human_approval_required: true

2. Assisted Mode rules:
   - All emails require human approval
   - System can auto-approve up to 10 LOW-RISK emails/day
   - HIGH/CRITICAL risk always require human approval
   - Hot leads trigger immediate Slack + SMS alert

3. Verify email limits:
   - Daily limit: 10 (assisted mode cap)
   - Will scale to 150 in Full mode
```

### Prompt 35.2: Send First Production Emails

```
TASK: Send first 10 production emails

1. Select 10 AE-approved, LOW-RISK emails from queue
2. Pre-flight checklist (automated):
   - [ ] Unsubscribe link present
   - [ ] No PII in logs
   - [ ] Domain health > 70
   - [ ] Within working hours
   - [ ] Not on suppression list

3. Send via GHL:
   python execution/send_approved_emails.py \
     --source .hive-mind/gatekeeper/approved/ \
     --limit 10 \
     --dry-run false

4. Monitor delivery:
   - Check GHL for send status
   - Watch for bounces (should be 0)
   - Log results to .hive-mind/sent_emails/

5. Verify audit trail:
   python -c "from core.audit_trail import AuditTrail; at = AuditTrail(); print(at.query_by_action('email_sent', limit=10))"
```

### Prompt 35.3: Test Hot Lead to AE Handoff

```
TASK: End-to-end hot lead test with real escalation

1. Wait for or trigger a hot lead event:
   - Email reply with positive sentiment
   - Form submission from high-ICP lead
   - RB2B visitor from target account

2. Verify escalation chain:
   a. HotLeadDetector scores lead >= 0.8
   b. Slack alert sent to #hot-leads channel
   c. SMS sent to ESCALATION_PHONE_L2 (if configured)
   d. Lead tagged in GHL as "hot_lead"
   e. AE receives notification within 5 minutes

3. Measure response time:
   - Event received → Alert sent: < 30 seconds
   - Alert sent → AE acknowledged: < 5 minutes (target)

4. Log to .hive-mind/hot_leads/escalation_log.json
```

### Prompt 35.4: Day 35 Checkpoint

```
TASK: Validate Assisted Mode and create Week 1 Report

1. Assisted Mode validation:
   ✅ 10 emails sent successfully
   ✅ 0 bounces
   ✅ 0 spam complaints
   ✅ Hot lead escalation working
   ✅ AE handoff under 5 minutes

2. Generate Week 1 Report:
   python execution/generate_weekly_report.py --week 1

   Include:
   - Leads processed: X
   - Emails sent: X
   - Open rate: X% (if available)
   - Reply rate: X%
   - Hot leads detected: X
   - AE response time: Xm avg
   - Errors: X
   - Approval rate: X%

3. Decision point:
   - All green → Plan Full Operations (Week 2)
   - Issues → Extend Assisted Mode, fix issues
```

---

## Summary: Day 31-35 Checklist

| Day | Task | Exit Criteria | Status |
|-----|------|---------------|--------|
| 31 | Simplification Sprint | Guardrails consolidated, single audit, 6 agents | ✅ COMPLETE |
| 32 | Environment Setup | All APIs connected, webhooks live | ✅ SCRIPTS CREATED (needs credentials) |
| 33 | Shadow Validation | 100 leads, 80%+ AE approval | ✅ SCRIPTS CREATED |
| 34 | Parallel Mode | 70%+ agreement rate, metrics baselined | ✅ SCRIPTS CREATED |
| 35 | Assisted Launch | 10 emails sent, hot lead flow working | ✅ SCRIPTS CREATED |

### Scripts Created in This Session

| Script | Purpose |
|--------|---------|
| `execution/verify_production_env.py` | Verify all env vars and test API connections |
| `execution/validate_shadow_exit.py` | Check shadow mode exit criteria |
| `execution/compare_parallel_decisions.py` | Compare AI vs AE decisions |
| `execution/send_approved_emails.py` | Send approved emails with safety checks |

---

## Commands Quick Reference

```powershell
# Day 31
python -m pytest tests/test_unified_guardrails.py -v

# Day 32
python execution/verify_production_env.py
python webhooks/webhook_server.py --port 8000

# Day 33
python execution/validate_shadow_exit.py

# Day 34
python execution/compare_parallel_decisions.py

# Day 35
python execution/send_approved_emails.py --limit 10
python execution/generate_weekly_report.py --week 1
```

---

*Created: 2026-01-23*
*Version: 1.0 - Live Fire Phase*
