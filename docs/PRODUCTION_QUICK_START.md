# CAIO Alpha Swarm: Production Quick Start Guide

**Date:** February 10, 2026
**Status:** Ready for Implementation

---

## TL;DR - What You Need Right Now

### For Product Technical Officer (You):

**This Week:**
1. ✅ Provision Redis (recommend: Redis Cloud - $7-25/mo)
2. ✅ Set up Inngest account (Free tier)
3. ✅ Update `.env` with production values (see below)
4. ✅ Run validation: `python scripts/validate_runtime_env.py --mode production`

**Next Week:**
1. Run replay harness weekly (Mondays)
2. Review scorecard (Fridays)
3. Meet with HoS (Wednesday) for quality alignment

---

### For Head of Sales:

**This Week (2 hours total):**
1. ✅ Provide 5 "good" email examples
2. ✅ Provide 5 "bad" email examples (with reasons why)
3. ✅ Define top 5 rejection categories
4. ✅ Set daily approval capacity (e.g., 30 emails/day)

**Result:** AI learns what you want, approval rate goes from 60% → 85%+

---

## Critical Decisions Made

| Decision | Value | Rationale |
|----------|-------|-----------|
| **Trace Retention** | 30 days | Balances storage cost vs debugging value |
| **Redis Required** | `true` (production) | Atomic rate limiting, fail-fast if unavailable |
| **Inngest Required** | `true` (production) | Scheduled workflows, async processing |
| **Replay Pass Rate** | ≥95% | Quality gate for deployments |
| **Scorecard Owner** | Product Technical Officer | Weekly review and release sign-off |
| **Sign-Off Cadence** | Weekly (Friday) | Pre-release quality check |

---

## Production Configuration (Copy-Paste Ready)

### Step 1: Get Your Credentials

**Redis (Recommended: Redis Cloud)**
1. Go to https://redis.com/try-free/
2. Create account → Create database
3. Copy connection URL: `redis://default:password@host:port/0`

**Inngest**
1. Go to https://www.inngest.com
2. Create account → Create app
3. Copy keys from Settings > Keys
   - Signing Key: `signkey-prod-xxx`
   - Event Key: `eventkey-prod-xxx`

---

### Step 2: Update Your `.env` File

**Add/Update these lines in `.env`:**

```bash
# =============================================================================
# PRODUCTION RUNTIME RELIABILITY
# =============================================================================

# Redis Configuration
REDIS_URL=redis://your-redis-cloud-url:6379/0
REDIS_REQUIRED=true
REDIS_MAX_CONNECTIONS=50
RATE_LIMIT_REDIS_NAMESPACE=caio:prod:ratelimit
CONTEXT_REDIS_PREFIX=caio:prod:context
CONTEXT_STATE_TTL_SECONDS=7200

# Inngest Configuration
INNGEST_SIGNING_KEY=signkey-prod-your-key-here
INNGEST_EVENT_KEY=eventkey-prod-your-key-here
INNGEST_REQUIRED=true
INNGEST_APP_ID=caio-alpha-swarm-prod

# Trace Configuration
TRACE_ENVELOPE_FILE=.hive-mind/traces/tool_trace_envelopes.jsonl
TRACE_ENVELOPE_ENABLED=true
TRACE_RETENTION_DAYS=30
TRACE_CLEANUP_ENABLED=true
```

Optional automation (recommended):

```bash
python scripts/bootstrap_runtime_reliability.py \
  --mode production \
  --env-file .env \
  --redis-url redis://your-redis-cloud-url:6379/0 \
  --inngest-signing-key signkey-prod-your-key-here \
  --inngest-event-key eventkey-prod-your-key-here \
  --validate --check-connections
```

---

### Step 3: Validate Configuration

```bash
# From repo root:
cd d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm

# Validate production config
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections

# Optional strict check (verifies /inngest mount by importing dashboard app)
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections --verify-inngest-route

# Expected output: "Result: PASS"
```

---

### Step 4: Run Quality Gate

```bash
# Run replay harness
python scripts/replay_harness.py --min-pass-rate 0.95

# Expected output:
# Pass rate: 97% (threshold: 95%)
# block_build: false
```

---

## Simulation Boundary (What's Real vs Fake)

### Phase 1: This Week (Infrastructure Only)

| Component | Production-Real | Notes |
|-----------|-----------------|-------|
| Redis | ✅ YES | Required for rate limiting |
| Inngest | ✅ YES | Required for workflows |
| Audit Trail | ✅ YES | SQLite writes |
| Trace Logging | ✅ YES | JSONL writes |
| **Email Sending** | ❌ NO (log-only) | Wait for HoS approval |
| **Calendar Writes** | ❌ NO (mock) | Wait for quality threshold |
| **GHL Writes** | ❌ NO (sandbox) | Wait for data validation |

**Why this approach?**
- Infrastructure goes live first (safe, no customer impact)
- Customer-facing actions wait for quality approval
- Reduces risk of bad emails/calendar spam

---

### Phase 2: Next Week (After HoS Alignment)

| Component | Production-Real | Gating Factor |
|-----------|-----------------|---------------|
| Email Sending | ✅ YES (whitelist only) | HoS approves messaging quality |
| Calendar Writes | ✅ YES (with approval) | Meeting prep quality ≥80% |
| GHL Writes | ✅ YES (limited) | Data quality validation passes |

**Rollout plan:** Start with 10 emails/day → increase based on approval rate

---

## Weekly Rhythm (Low Effort)

### Monday (15 min):
```bash
# Run replay harness
python scripts/replay_harness.py --min-pass-rate 0.95

# Share results in Slack/email
echo "Week of $(date): Pass rate X%, Status: PASS/FAIL"
```

### Wednesday (30 min):
- **Meeting with HoS:** Review rejected emails from past week
- Map rejections to taxonomy
- Update AI guidance if patterns emerge

### Friday (30 min):
- **Release Readiness Check:**
  - ✅ Replay pass rate ≥95%?
  - ✅ No critical failures this week?
  - ✅ Redis/Inngest healthy?
  - ✅ Queue aging <2 hours?
  - **Decision:** Approve or block deployment

---

## Escalation Rules (When to Panic)

**🚨 Immediate Escalation (Same Day):**

1. Replay pass rate drops below 95%
2. Any groundedness hard-fail cases
3. Redis unavailable when `REDIS_REQUIRED=true`
4. Inngest keys missing when `INNGEST_REQUIRED=true`
5. Queue aging >2 hours

**Escalation Path:**
- GTM Engineer → Email PTO + HoS immediately
- PTO → Review logs, rollback if needed
- Post-mortem within 24 hours

---

## Cost Breakdown

| Service | Monthly Cost | What It Does |
|---------|--------------|--------------|
| **Redis Cloud** | $7-25 | Rate limiting, session state |
| **Inngest** | $0 (free tier) | Scheduled workflows |
| **S3 (trace backups)** | $1-3 | Archive old traces |
| **Total** | **$8-28/mo** | Full infrastructure |

**No AI model costs here** - You're already paying for Anthropic/OpenAI API separately.

---

## Success Metrics (1 Month Target)

| Metric | Current | Target (1 Month) |
|--------|---------|------------------|
| **Replay Pass Rate** | TBD | 97%+ |
| **HoS Approval Rate** | ~60% | 85%+ |
| **Time Reviewing Emails** | 60 min/day | 30 min/day |
| **Queue Aging (p95)** | TBD | <1 hour |
| **Email Quality (HoS rating)** | TBD | 4/5 average |

---

## Quick Links

**Full Documentation:**
- [Production Readiness Roadmap](./PRODUCTION_READINESS_ROADMAP.md) - Technical implementation guide
- [HoS Action Items Guide](./HOS_ACTION_ITEMS_GUIDE.md) - Business quality standards
- [Original Handoff Doc](./CAIO_ALPHA_GTM_OPERATOR_ROADMAP.md) - Context and background

**Scripts:**
- Validate: `python scripts/validate_runtime_env.py`
- Bootstrap runtime env: `python scripts/bootstrap_runtime_reliability.py --mode production --env-file .env`
- Replay: `python scripts/replay_harness.py`
- Health: `curl http://localhost:8080/api/health`
- Runtime deps health: `curl http://localhost:8080/api/runtime/dependencies?token=YOUR_DASHBOARD_AUTH_TOKEN`

---

## Next 48 Hours - Action Checklist

### For Product Technical Officer:

**Today:**
- [ ] Read [Production Readiness Roadmap](./PRODUCTION_READINESS_ROADMAP.md) (15 min)
- [ ] Sign up for Redis Cloud account (10 min)
- [ ] Sign up for Inngest account (10 min)

**Tomorrow:**
- [ ] Update `.env` with Redis and Inngest credentials (15 min)
- [ ] Run `python scripts/validate_runtime_env.py --mode production` (5 min)
- [ ] Run `python scripts/replay_harness.py --min-pass-rate 0.95` (10 min)

**Total Time:** ~65 minutes to production-ready infrastructure

---

### For Head of Sales:

**Today:**
- [ ] Read [HoS Action Items Guide](./HOS_ACTION_ITEMS_GUIDE.md) (20 min)
- [ ] Pull 5 "good" email examples from past sends (10 min)
- [ ] Pull 5 "bad" email examples with notes on why (10 min)

**Tomorrow:**
- [ ] Write down top 5 reasons you reject AI emails (10 min)
- [ ] Set your daily approval capacity target (5 min)
- [ ] Schedule Wed/Fri alignment meetings with PTO (5 min)

**Total Time:** ~60 minutes to unblock AI quality improvements

---

## Questions?

**Technical:** Contact Product Technical Officer
**Business/Quality:** Contact Head of Sales
**Urgent/Blocker:** Escalate per rules above

---

## Document Version

**Version:** 1.0
**Last Updated:** February 10, 2026
**Owner:** Product Technical Officer
**Status:** Ready for implementation
