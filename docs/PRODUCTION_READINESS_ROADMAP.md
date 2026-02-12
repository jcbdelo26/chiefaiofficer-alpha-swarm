# CAIO Alpha Swarm: Production Readiness Roadmap

**Date:** February 10, 2026
**For:** GTM Engineer / Product Technical Officer
**Status:** Configuration & Implementation Guide

---

## Executive Summary

This document provides the complete roadmap to move CAIO Alpha Swarm from staging to production-ready state. It includes:
- **Production values** for Redis and Inngest configuration
- **Optimal trace retention** recommendations
- **Release scorecard ownership** structure
- **Simulation boundary** decisions (what stays simulated vs goes live)

**Timeline:** 2-3 weeks to full production readiness

---

## Section 1: Production Configuration Values

### 1.1 Redis Configuration (Production Values)

**Purpose:** Atomic rate limiting, session state management, circuit breaker coordination

**Recommended Production Setup:**

| Environment | Redis URL | REDIS_REQUIRED | Notes |
|-------------|-----------|----------------|-------|
| **Production** | `redis://<prod-host>:6379/0` | `true` | Fail-fast if unavailable |
| **Staging** | `redis://<staging-host>:6379/1` | `true` | Mirror production behavior |
| **Development** | `redis://localhost:6379/2` | `false` | Fallback to in-memory |

**Production `.env` Values:**

```bash
# Redis Configuration (PRODUCTION)
REDIS_URL=redis://your-production-redis.com:6379/0
REDIS_REQUIRED=true
REDIS_MAX_CONNECTIONS=50
REDIS_SOCKET_TIMEOUT=5
REDIS_SOCKET_CONNECT_TIMEOUT=5

# Namespaces for isolation
RATE_LIMIT_REDIS_NAMESPACE=caio:prod:ratelimit
CONTEXT_REDIS_PREFIX=caio:prod:context
CIRCUIT_BREAKER_REDIS_PREFIX=caio:prod:circuit

# TTL Configuration
CONTEXT_STATE_TTL_SECONDS=7200  # 2 hours (recommended for session persistence)
RATE_LIMIT_TTL_SECONDS=3600     # 1 hour
CIRCUIT_BREAKER_TTL_SECONDS=300  # 5 minutes
```

**Redis Provider Recommendations:**

| Provider | Use Case | Monthly Cost (est.) |
|----------|----------|---------------------|
| **AWS ElastiCache** | Enterprise, auto-failover | $50-150 |
| **Redis Cloud** | Managed, global | $7-100 |
| **Upstash** | Serverless, per-request | $10-50 |
| **Render** | Simple, affordable | $7-25 |

**Recommended:** Start with **Redis Cloud** or **Upstash** for reliability and ease of setup.

---

### 1.2 Inngest Configuration (Production Values)

**Purpose:** Scheduled orchestration, async workflows, webhook processing

**Recommended Production Setup:**

```bash
# Inngest Configuration (PRODUCTION)
INNGEST_SIGNING_KEY=signkey-prod-[your-key-here]
INNGEST_EVENT_KEY=eventkey-prod-[your-key-here]
INNGEST_REQUIRED=true

# App configuration
INNGEST_APP_ID=caio-alpha-swarm-prod
INNGEST_APP_NAME="CAIO Alpha Swarm"

# Environment URLs
INNGEST_WEBHOOK_URL=https://your-app.com/inngest
INNGEST_DEV_SERVER_URL=http://127.0.0.1:8288  # Only for local dev
```

**Key Setup Steps:**

1. **Create Inngest Account:** https://www.inngest.com
2. **Create Production Environment** in Inngest dashboard
3. **Copy Keys:**
   - Signing Key: Found in Settings > Keys > Signing Keys
   - Event Key: Found in Settings > Keys > Event Keys
4. **Configure Webhook:** Point Inngest to `https://your-domain.com/inngest`

**Monthly Cost:** Free tier covers up to 50k function runs/month (sufficient for most GTM operations)

---

### 1.3 Trace Configuration (Production Values)

**Purpose:** Debugging, audit trail, performance analysis, quality regression detection

**Recommended Production Setup:**

```bash
# Trace Envelope Configuration (PRODUCTION)
TRACE_ENVELOPE_FILE=.hive-mind/traces/tool_trace_envelopes.jsonl
TRACE_ENVELOPE_ENABLED=true
TRACE_REDACT_SENSITIVE=true

# Retention Policy (see Section 2)
TRACE_RETENTION_DAYS=30
TRACE_BACKUP_ENABLED=true
TRACE_BACKUP_INTERVAL_HOURS=24
TRACE_BACKUP_PATH=.hive-mind/traces/backups/
```

---

## Section 2: Optimal Trace Retention Windows

### 2.1 Analysis & Recommendation

**Question:** How long should we keep trace envelopes?

**Options Evaluated:**

| Window | Storage (GB/month)* | Use Cases | Recommendation |
|--------|---------------------|-----------|----------------|
| **14 days** | ~2-5 GB | Real-time debugging, hot-fix analysis | ❌ Too short for pattern detection |
| **30 days** | ~5-10 GB | Monthly regression analysis, trend detection | ✅ **RECOMMENDED** |
| **90 days** | ~15-30 GB | Quarterly reviews, long-term pattern analysis | ⚠️ Only if storage permits |

*Assumes 500-1000 trace entries/day at ~10KB each

### 2.2 Recommended Configuration

**Production Default: 30 Days**

**Rationale:**
1. **Monthly scorecard cycle** aligns with 30-day retention
2. **Sufficient for regression detection** - can compare current week to 3 weeks ago
3. **Cost-effective** - balances storage cost vs debugging value
4. **Compliance-friendly** - short enough for PII concerns

**Implementation:**

```bash
# In .env (Production)
TRACE_RETENTION_DAYS=30
TRACE_CLEANUP_ENABLED=true
TRACE_CLEANUP_CRON="0 2 * * *"  # Daily at 2 AM
```

**Automated Cleanup Script:**

Add to cron or Inngest schedule:
```python
# scripts/cleanup_traces.py
python scripts/cleanup_traces.py --retention-days 30 --dry-run false
```

### 2.3 Backup Strategy

**Archive to Cold Storage:**
- After 30 days, compress and move to S3/Azure Blob
- Keep 90-day archive for compliance/audit needs
- Cost: ~$1-3/month for compressed archives

---

## Section 3: Release Scorecard Owner & Sign-Off Cadence

### 3.1 Recommended Ownership Structure

**Primary Owner: Product Technical Officer (You)**

**Responsibilities:**
1. **Weekly Scorecard Review** (30 min)
   - Replay pass rate (must be ≥95%)
   - Critical evaluation failures
   - Groundedness failures
   - Negative constraint violations

2. **Release Sign-Off** (Per deployment)
   - Run `python scripts/replay_harness.py --min-pass-rate 0.95`
   - Verify all critical evaluations pass
   - Approve or block deployment

3. **Monthly Quality Review** (1 hour)
   - Analyze trends in scorecard metrics
   - Update Golden Set with new failure scenarios
   - Adjust thresholds if needed

**Backup Owner: GTM Engineer**
- Can execute scorecard runs
- Escalates to PTO for final sign-off

---

### 3.2 Recommended Sign-Off Cadence

**Weekly Rhythm:**

| Day | Activity | Owner | Duration |
|-----|----------|-------|----------|
| **Monday** | Run replay harness, publish pass rate snapshot | GTM Eng | 15 min |
| **Wednesday** | Review rejects/edits with HoS, map to taxonomy | PTO + HoS | 30 min |
| **Friday** | Release readiness check (scorecard + health) | PTO | 30 min |

**Pre-Release Gate:**
- ✅ Replay pass rate ≥ 95%
- ✅ No critical evaluation failures in last 7 days
- ✅ Redis + Inngest connection checks pass
- ✅ Queue aging within SLA (<2 hours)
- ✅ HoS approval on messaging quality

**Sign-Off Document:**
```markdown
# Release [Version] Sign-Off
Date: [Date]
Release Branch: [Branch]

✅ Replay Pass Rate: 97% (threshold: 95%)
✅ Critical Failures: 0
✅ Groundedness Score: 98%
✅ Negative Constraints: 0 violations
✅ Infrastructure Health: All systems operational
✅ HoS Approval: Approved (messaging quality: 92%)

Signed: [Product Technical Officer]
```

---

## Section 4: Simulation Boundary (Production-Real vs Simulated)

### 4.1 Current State Analysis

**What is Currently Simulated:**
1. **Email Sending** - Uses test mode or logs instead of actual SMTP
2. **Calendar Events** - May use mock Google Calendar API responses
3. **GHL Contact Creation** - May use sandbox mode
4. **Webhook Processing** - May skip actual external webhook calls
5. **Inngest Workflows** - May use dev server instead of production Inngest

### 4.2 Recommended Production Boundary

**MUST Be Production-Real (No Simulation):**

| Component | Production-Real Behavior | Risk Mitigation |
|-----------|-------------------------|-----------------|
| **Redis** | Live Redis instance | Circuit breakers handle failure |
| **Inngest** | Production Inngest cloud | Retry logic + error tracking |
| **Audit Trail** | SQLite writes to `.hive-mind/audit.db` | Daily backups to S3 |
| **Trace Logging** | Real JSONL writes | Async + buffered writes |
| **Rate Limiting** | Redis-backed atomic counters | Prevents API overuse |
| **Circuit Breakers** | Redis-backed state tracking | Protects integrations |

**CAN Remain Simulated (Safe for Staging):**

| Component | Simulated Behavior | When to Make Real |
|-----------|-------------------|-------------------|
| **Email Sending** | Log-only mode (no SMTP) | After HoS approves messaging quality |
| **Calendar Creation** | Mock API responses | After meeting prep quality threshold |
| **External Webhooks** | Skip or log only | After webhook reliability proven |
| **GHL Contact Write** | Sandbox mode | After data quality validation |

### 4.3 Phased Production Rollout Plan

**Phase 1: Infrastructure-Only (Week 1)**
- ✅ Redis: Production
- ✅ Inngest: Production
- ✅ Audit Trail: Production
- ✅ Trace Logging: Production
- ⚠️ Email: Simulated (log-only)
- ⚠️ Calendar: Simulated (mock)
- ⚠️ GHL Writes: Sandbox

**Phase 2: Read-Only Integrations (Week 2)**
- ✅ All Phase 1 items
- ✅ GHL Reads: Production
- ✅ Google Calendar Reads: Production
- ⚠️ Email: Simulated (log-only)
- ⚠️ Calendar Writes: Simulated (mock)
- ⚠️ GHL Writes: Sandbox

**Phase 3: Write Integrations (Week 3)**
- ✅ All Phase 2 items
- ✅ Calendar Writes: Production (with HoS approval)
- ✅ GHL Contact Updates: Production (with guardrails)
- ⚠️ Email: Limited production (whitelist only)

**Phase 4: Full Production (Week 4+)**
- ✅ All components production-real
- ✅ Email: Full production (with daily limits)
- ✅ Monitoring: Full observability

### 4.4 Production-Readiness Checklist

**Infrastructure:**
- [ ] Redis production instance provisioned and connected
- [ ] Inngest production environment configured
- [ ] Trace retention policy configured (30 days)
- [ ] Audit DB daily backups to S3/Azure
- [ ] Circuit breakers tested with Redis

**Safety Guardrails:**
- [ ] Daily email limit: 150 (GHL)
- [ ] Hourly email limit: 20
- [ ] Per-domain-per-hour limit: 5
- [ ] Working hours enforcement: 9am-6pm ET
- [ ] HoS approval required for HIGH/CRITICAL risk actions
- [ ] Grounding evidence validation (timestamp <1 hour)

**Monitoring:**
- [ ] Replay harness runs weekly (Monday)
- [ ] Scorecard review scheduled (Friday)
- [ ] HoS feedback loop scheduled (Wednesday)
- [ ] Alert on pass rate <95%
- [ ] Alert on Redis/Inngest unavailability
- [ ] Queue aging alert (<2 hours)

---

## Section 5: Next 2 Weeks - Action Plan

### Week 1: Infrastructure Setup

**Monday-Tuesday:**
- [ ] Provision production Redis instance
- [ ] Configure Inngest production environment
- [ ] Update `.env` with production values
- [ ] Run `python scripts/validate_runtime_env.py --mode production`

**Wednesday-Thursday:**
- [ ] Deploy to staging with production-like config
- [ ] Run replay harness: `python scripts/replay_harness.py --min-pass-rate 0.95`
- [ ] Validate all endpoints with production Redis/Inngest

**Friday:**
- [ ] Release readiness check
- [ ] Document any blockers
- [ ] Get PTO sign-off on infrastructure changes

---

### Week 2: Integration Testing & HoS Alignment

**Monday-Tuesday:**
- [ ] Complete router split of `dashboard/health_app.py`
- [ ] Add endpoint parity tests
- [ ] Verify trace envelope logging

**Wednesday:**
- [ ] **HoS Session:** Review messaging quality requirements (see HoS doc)
- [ ] Define approval rubric
- [ ] Establish rejection taxonomy

**Thursday-Friday:**
- [ ] Update Golden Set with real production scenarios
- [ ] Run final replay harness
- [ ] Prepare production deployment plan

---

## Section 6: Escalation Triggers

**Immediate Escalation (Same Day):**

1. ❌ Replay pass rate drops below 95%
2. ❌ Any groundedness hard-fail cases
3. ❌ Redis connection unavailable when `REDIS_REQUIRED=true`
4. ❌ Inngest keys missing when `INNGEST_REQUIRED=true`
5. ❌ Queue aging exceeds 2 hours without HoS approval
6. ❌ Daily email limit exceeded (>150 emails)

**Escalation Path:**
1. **GTM Engineer** → Immediately notify PTO + HoS
2. **PTO** → Review logs, determine root cause
3. **Emergency Fix:** Roll back to last known good state
4. **Post-Mortem:** Within 24 hours, document and fix

---

## Section 7: Success Metrics

**Production-Ready Definition:**

| Metric | Threshold | Current | Target |
|--------|-----------|---------|--------|
| Replay Pass Rate | ≥95% | TBD | 97%+ |
| Critical Failures | 0 per week | TBD | 0 |
| Groundedness Score | ≥90% | TBD | 95%+ |
| Negative Constraints | 0 violations | TBD | 0 |
| Redis Uptime | ≥99.9% | N/A | 99.9% |
| Inngest Success Rate | ≥99% | N/A | 99.5% |
| HoS Approval Rate | ≥80% | TBD | 85%+ |
| Queue Aging (p95) | <2 hours | TBD | <1 hour |

**Monthly Review:**
- Compare current month vs previous month
- Identify trends (improving, stable, degrading)
- Update thresholds if consistently exceeding targets

---

## Appendix A: Cost Estimates

| Service | Tier | Monthly Cost | Notes |
|---------|------|--------------|-------|
| **Redis Cloud** | Essentials | $7-25 | 256MB-1GB, good for GTM workload |
| **Inngest** | Free | $0 | Up to 50k runs/month |
| **S3 (Trace Backups)** | Standard | $1-3 | Compressed 90-day archive |
| **Monitoring** | Included | $0 | Use built-in health dashboard |
| **Total** | - | **$8-28/mo** | Infrastructure baseline |

---

## Appendix B: Quick Reference Commands

**Validate Environment:**
```bash
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections
```

**Run Replay Harness:**
```bash
python scripts/replay_harness.py --min-pass-rate 0.95
```

**Check Health:**
```bash
curl http://localhost:8080/api/health
```

**View Traces:**
```bash
tail -f .hive-mind/traces/tool_trace_envelopes.jsonl
```

**Cleanup Old Traces:**
```bash
python scripts/cleanup_traces.py --retention-days 30 --dry-run false
```

---

## Document Version

**Version:** 1.0
**Last Updated:** February 10, 2026
**Next Review:** February 17, 2026 (Post Week 1)
**Owner:** Product Technical Officer
