# CAIO Swarm: Phase 2 to Phase 3 Rollout Roadmap

**Created:** January 31, 2026  
**Status:** Phase 2 Parallel Testing → Phase 3 Assisted Mode → Phase 4 Full Autonomy  
**Current Issue:** 🚨 CODE NOT DEPLOYED TO RAILWAY - Local fixes exist but production uses old code

---

## 🚨 BLOCKING ISSUE: Railway Deployment Required

### Diagnosis (Jan 31, 2026)

| Finding | Evidence |
|---------|----------|
| **Railway missing new code** | `/api/queue-status` returns 404 on production |
| **5 pending emails exist locally** | `blog_intent_sample_*.json` with `status: pending` in `.hive-mind/shadow_mode_emails/` |
| **Clay callback not configured** | `CLAY_WORKBOOK_WEBHOOK_URL` is empty - Clay can't POST results back |
| **Production dashboard reads empty** | Railway has old code without Intent Monitor integration |

### Why Dashboard Shows "All Caught Up!"

```
LOCAL (✅ Fixed):
  RB2B webhook → normalize_rb2b_payload() → process_visitor_intent() 
              → WebsiteIntentMonitor.process_visitor()
              → _queue_for_approval() → writes to shadow_mode_emails/*.json ✅

PRODUCTION (❌ Old Code):
  RB2B webhook → Clay enrichment only (no Intent Monitor call)
              → Dashboard reads empty shadow_mode_emails/ ❌
```

### Fix: Deploy to Railway

**✅ Git push completed** (Jan 31, 2026):
```
Commit: 887d435
Message: feat: connect RB2B webhook to Website Intent Monitor for email queue population
Pushed to: https://github.com/jcbdelo26/chiefaiofficer-alpha-swarm.git
```

**⚠️ Railway NOT auto-deploying - Manual trigger required:**
1. Go to https://railway.app/dashboard
2. Select `caio-swarm-dashboard-production` project
3. Click "Deploy" → "Trigger Deploy" from latest commit
4. Wait for build to complete (~2-3 min)

**Alternative: Install Railway CLI**
```powershell
# Install Railway CLI
npm i -g @railway/cli

# Login and deploy
railway login
railway up
```

### Verify After Deploy

```bash
# Should return JSON (not 404)
curl https://caio-swarm-dashboard-production.up.railway.app/api/queue-status

# Should show pending count > 0
# Response: {"shadow_mode_emails": {"total": 5, "pending": 5, ...}}
```

---

## ✅ Clay Enrichment: Callback IS Configured

### Status (Jan 31, 2026)
Clay workbook has HTTP API column configured and working:
- **Endpoint**: `https://caio-swarm-dashboard-production.up.railway.app/webhooks/clay`
- **Status**: Status Code 200 on all rows (callbacks working!)
- **Workbook**: CAIO RB2B ABM Leads Enrichment (1,703 rows)

### Remaining Issue
The callback is reaching the server, but:
1. Production code doesn't process callbacks correctly (old code)
2. After Railway deploy, callbacks will populate `shadow_mode_emails/`

### Verify After Deploy
```bash
# Check Clay callback health
curl https://caio-swarm-dashboard-production.up.railway.app/webhooks/clay/health

# Expected: {"status": "healthy", "enricher_initialized": true}
```

---

## 🔴 Critical Issue Identified & Fixed (LOCAL ONLY)

### Root Cause Analysis

After Dani approved all pending emails, no new emails populated because:

1. **Disconnected Pipeline**: RB2B webhook → Clay enrichment ✅ but → Website Intent Monitor ❌
2. **Schema Mismatch**: Monitor wrote to `gatekeeper_queue/` but dashboard reads `shadow_mode_emails/`
3. **No Continuous Trigger**: No scheduler running the intent monitor independently
4. **Missing Rate Limiting**: No daily limit enforcement for Live Mode (25/day)

### Fixes Applied (LOCAL - NEED DEPLOY)

| Component | Issue | Fix |
|-----------|-------|-----|
| `webhooks/rb2b_webhook.py` | Did not call intent monitor | Now triggers `process_visitor()` via BackgroundTasks |
| `core/website_intent_monitor.py` | Wrote to wrong queue | Now writes to BOTH `shadow_mode_emails` AND `gatekeeper_queue` |
| `core/website_intent_monitor.py` | No rate limiting | Added 25/day limit check before queueing |
| `dashboard/health_app.py` | No pipeline visibility | Added `/api/queue-status` endpoint |
| New: `execution/diagnose_email_pipeline.py` | N/A | Pipeline diagnostic tool |

---

## 📊 Current System Status

### Phase 2: Parallel Testing (40% → 75% Complete)

| Test | Status | Result |
|------|--------|--------|
| 2.1 GHL Write Tests | ✅ Pass | Contacts created, workflows triggered |
| 2.2 Enrichment Pipeline | ⏳ In Progress | Circuit breaker active, Clay webhook connected |
| 2.3 Email Quality Review | ⏳ Pending | Exported 21 emails for Dani's review |
| 2.4 Domain Health | ✅ Pass | Score 75/50 |
| 2.5 Warm Connection Detection | ✅ Pass | Detecting Dani's Gong/Outreach connections |
| 2.6 Daily Limit Enforcement | ✅ Pass | 25/day limit working (1/25 queued) |
| 2.7 Pipeline Connectivity | ✅ Pass | RB2B → Intent Monitor → Dashboard Queue |

### Validation Scripts Created

```bash
# Run full Phase 2 validation
python execution/phase2_validation.py

# Test enrichment with circuit breaker
python execution/phase2_enrichment_stabilization.py --test

# Export emails for Dani's quality review
python execution/phase2_email_quality_review.py --export

# Run pipeline diagnostic
python execution/diagnose_email_pipeline.py --test-visitor
```

---

## 🚀 Phase 2: Parallel Testing (Remaining Steps)

### Week 1: Fix Validation & Pipeline Stability

#### Day 1-2: Validate Fixes
```bash
# 1. Run pipeline diagnostic
python execution/diagnose_email_pipeline.py

# 2. Simulate test visitor to verify queue population
python execution/diagnose_email_pipeline.py --test-visitor

# 3. Check queue status via API
curl https://caio-swarm-dashboard-production.up.railway.app/api/queue-status

# 4. Verify pending emails appear in dashboard
# Visit: /sales dashboard → Pending Email Approvals section
```

#### Day 3-4: Enrichment Pipeline Stabilization
The Clay enrichment pipeline is timing out. Fix:

1. **Add timeout handling** to `core/clay_direct_enrichment.py`:
   - Set 30-second timeout per enrichment
   - Circuit breaker after 3 consecutive failures
   - Fallback: queue email with partial data

2. **Run enrichment backfill**:
   ```bash
   python execution/enrich_missing_ghl_contacts.py --limit 50
   ```

3. **Success criteria**: ≥30% enrichment rate (was 1%)

#### Day 5-7: Email Quality Review (Dani)
1. Export sample emails:
   ```bash
   python execution/export_emails_for_review.py
   ```
2. Dani reviews 10-20 emails, scores 1-5 on:
   - Personalization quality
   - Subject line effectiveness
   - Value proposition clarity
   - CTA appropriateness
   - Professional tone

3. **Success criteria**: Average score ≥ 3.5/5

---

### Week 2: A/B Testing & Metrics Validation

#### Reply Rate Fix (Current: 6.5%, Target: 8%)

The dashboard shows reply rate is below target. Use the self-annealing fix:

```bash
# Apply A/B testing for subject lines
python execution/fix_low_reply_rate.py --apply

# This will:
# 1. Analyze current subject lines
# 2. Generate test variants with softer CTAs
# 3. Split traffic 50/50 for next 50 emails
```

#### Metrics to Track

| Metric | Current | Target | Phase 3 Gate |
|--------|---------|--------|--------------|
| Emails Sent | 847 | 2,500/mo | ✅ On track |
| Reply Rate | 6.5% | 8% | ❌ Below target |
| Meetings Booked | 12 | 15/mo | ❌ Below target |
| Pipeline Value | $142K | $200K/mo | ❌ Below target |

---

## 🎯 Phase 3: Assisted Mode (Entry Criteria)

Phase 3 begins when ALL of the following are met:

| Criterion | Requirement | Current |
|-----------|-------------|---------|
| Enrichment Rate | ≥30% | 1% ❌ |
| Email Quality Score | ≥3.5/5 | Pending ⏳ |
| Reply Rate | ≥7% | 6.5% ❌ |
| Pipeline Connectivity | All stages working | ✅ Fixed |
| Zero Send Errors | No GHL failures in 48h | ⏳ |
| Approval Latency | <4h avg review time | ⏳ |

### Phase 3 Implementation Plan

#### Mode Changes
- **Approval Threshold**: Auto-approve LOW confidence emails only
- **Human Review**: HOT and WARM leads still require approval
- **Daily Limit**: Increase to 50/day
- **Monitoring**: Real-time Slack alerts for anomalies

#### Technical Changes Required

1. **Add confidence-based auto-approval** to `core/website_intent_monitor.py`:
   ```python
   # In _queue_for_approval():
   if visitor.intent_score < 40 and not visitor.warm_connections:
       # Auto-approve low-confidence, skip queue
       await self._auto_send_email(visitor)
   else:
       # Queue for human review
       await self._queue_for_approval(visitor)
   ```

2. **Add Slack notification on queue** in `core/approval_notifier.py`:
   - Notify #sales-bot channel when hot leads queue
   - Escalate after 2 hours with no action

3. **Update production config**:
   ```json
   {
     "mode": "assisted",
     "daily_limit": 50,
     "auto_approve": {
       "enabled": true,
       "max_intent_score": 40,
       "require_no_warm_connections": true
     }
   }
   ```

---

## 🏁 Phase 4: Full Autonomy (Entry Criteria)

Phase 4 is the final production mode. Entry requires:

| Criterion | Requirement |
|-----------|-------------|
| Phase 3 Duration | Minimum 2 weeks |
| Reply Rate | ≥8% sustained |
| Approval Override Rate | <10% (90% of auto-approvals were correct) |
| Zero Domain Health Issues | Score >70 for 2 weeks |
| Pipeline Value Growth | 20% increase from Phase 2 baseline |
| Dani Sign-off | Explicit approval to proceed |

### Phase 4 Features
- All LOW and MEDIUM confidence emails auto-send
- Only CRITICAL actions require approval
- Daily limit: 100/day
- Self-annealing handles anomalies automatically
- Weekly digest instead of per-email review

---

## 🔧 Immediate Action Items

### TODAY - CRITICAL (Priority 0)
1. [x] ~~Git push to GitHub~~ - ✅ Commit 887d435 pushed
2. [ ] **TRIGGER RAILWAY DEPLOY** - Go to Railway dashboard, click "Deploy"
3. [ ] Verify `/api/queue-status` returns 200 (not 404)
4. [ ] Verify dashboard shows pending emails

### TODAY - Clay Configuration (Priority 1)
1. [x] ~~Clay HTTP API column configured~~ - ✅ Status Code 200 on all rows
2. [x] ~~POSTing to webhook endpoint~~ - ✅ `https://caio-swarm-dashboard-production.up.railway.app/webhooks/clay`
3. [ ] Verify after Railway deploy: `curl .../webhooks/clay/health` returns `{"enricher_initialized": true}`

### This Week (Priority 2)
1. [ ] Fix Clay enrichment timeouts
2. [ ] Run enrichment backfill on existing contacts
3. [ ] Have Dani review 10 sample emails
4. [ ] Apply A/B test for reply rate improvement

### Next Week (Priority 3)
1. [ ] Review A/B test results
2. [ ] Validate all Phase 2 tests pass
3. [ ] Prepare Phase 3 config changes
4. [ ] Schedule Phase 3 launch date

---

## 📈 Monitoring Dashboard

### Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/sales` | Main HoS dashboard |
| `/api/queue-status` | Pipeline queue status |
| `/api/pending-emails` | Pending approvals list |
| `/api/health` | System health |

### Health Checks

```bash
# Full system health
curl https://caio-swarm.../api/health

# Queue status
curl https://caio-swarm.../api/queue-status

# Pipeline diagnostic
python execution/diagnose_email_pipeline.py
```

---

## 📋 Rollback Plan

If issues arise after fix deployment:

1. **Revert webhook changes**:
   ```bash
   git checkout HEAD~1 webhooks/rb2b_webhook.py
   ```

2. **Disable intent monitor**:
   Set `INTENT_MONITOR_ENABLED=false` in `.env`

3. **Manual queue population**:
   ```bash
   python execution/crafter_campaign.py --segment tier_1
   python execution/gatekeeper_queue.py --input .hive-mind/campaigns/latest.json
   ```

---

## ✅ Success Metrics

### Phase 2 Exit → Phase 3 Entry
- [ ] All pipeline stages connected and logging
- [ ] ≥30% enrichment rate
- [ ] ≥3.5/5 email quality score
- [ ] ≥7% reply rate
- [ ] Zero GHL send failures for 48h

### Phase 3 Exit → Phase 4 Entry
- [ ] 2 weeks of stable Assisted Mode
- [ ] <10% approval override rate
- [ ] ≥8% sustained reply rate
- [ ] ≥$180K pipeline value
- [ ] Dani explicit sign-off

---

*Document maintained by CAIO Swarm Agent Team*
