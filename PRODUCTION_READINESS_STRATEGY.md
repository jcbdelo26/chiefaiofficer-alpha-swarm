# Unified Swarm Production Readiness Strategy

## Executive Summary

You have completed **Days 1-7** (core infrastructure) of the 30-day roadmap. The system has a strong "core spine" but is **not yet production-ready**. This document outlines the critical path, recommended MCP servers, sandbox testing strategy, and production deployment checklist.

---

## Current State Assessment

### ✅ Completed (Days 1-7)

| Day | Component | Status |
|-----|-----------|--------|
| 1-2 | Unified Guardrails (circuit breakers, rate limits, permission matrix) | ✅ Complete |
| 3 | Self-Annealing Engine (RETRIEVE-JUDGE-DISTILL-CONSOLIDATE) | ✅ Complete |
| 4 | Google Calendar MCP + Unified Integration Gateway | ✅ Complete |
| 5 | Email Threading MCP + Scheduling SOPs | ✅ Complete |
| 6-7 | Unified Queen Orchestrator (Q-learning, Byzantine consensus) | ✅ Complete |
| — | Product Context System (pitchdeck integration) | ✅ Complete |

### 🔴 Remaining (Days 8-30)

```
Week 2 (Jan 27-31)
├── Day 8: Swarm Coordination (heartbeats, auto-restart) ← CRITICAL
├── Day 9: Unified Workflows (YAML definitions) ← CRITICAL  
└── Day 10: Week 2 Integration Test

Week 3 (Feb 1-5)
├── Day 11-12: Scheduler Agent (calendar ops, GHL integration)
├── Day 13-14: Researcher Agent (company research, brief gen)
└── Day 15: Communicator Enhancements

Week 4 (Feb 6-10)
├── Day 16-17: Multi-Layer Failsafe ← CRITICAL
├── Day 18: Audit Trail ← CRITICAL
├── Day 19: Health Monitor Enhancements
└── Day 20: Week 4 Integration Test

Week 5 (Feb 11-15)
├── Day 21-22: AIDefence (threat detection, PII) ← CRITICAL
├── Day 23-24: Approval Engine ← CRITICAL
└── Day 25: Security Testing

Week 6 (Feb 16-20)
├── Day 26-27: Full Test Suite
├── Day 28: Deployment Scripts ← CRITICAL
├── Day 29: Staging Deploy
└── Day 30: Production Go-Live
```

---

## Critical Path Items (Blockers to Production)

These **MUST** be completed before production deployment:

### 1. Swarm Lifecycle Reliability (Day 8)
```
Priority: P0 (BLOCKER)
Without this, production will degrade into zombie agents and duplicate actions.
```
- Heartbeats (30s interval)
- Auto-restart on failure
- Worker concurrency scaling
- "Stuck task" detection
- Safe shutdown procedure

### 2. Deterministic Workflows (Day 9-10)
```
Priority: P0 (BLOCKER)
Q-learning routing needs "known paths" that are testable and auditable.
```
- Workflow contracts (YAML definitions)
- Lead-to-meeting flow
- Meeting prep flow
- Approval flow

### 3. Audit Trail + PII Redaction (Day 18)
```
Priority: P0 (BLOCKER)
Any system sending emails/modifying CRM needs immutable audit logs.
```
- Append-only audit database
- PII redaction in logs
- Query API for compliance
- 90-day retention

### 4. AIDefence Security Layer (Days 21-22)
```
Priority: P0 (BLOCKER)
Primary mitigation against prompt injection and data exfiltration.
```
- Prompt injection detection
- Jailbreak detection
- PII detection (block/sanitize/warn)
- Command injection prevention

### 5. Approval Engine (Days 23-24)
```
Priority: P0 (BLOCKER)
No emails sent without approval. No calendar changes without confirmation.
```
- Slack Block Kit approvals
- Escalation on timeout
- GATEKEEPER integration
- Audit logging

### 6. Staging Deploy + Rollback (Days 28-30)
```
Priority: P0 (BLOCKER)
Must prove: no double-bookings, no runaway emails, rate limits respected.
```
- Deployment scripts
- Rollback procedure
- Smoke tests
- Staging validation

---

## Recommended MCP Servers to Add

### High Priority (Add Now)

| MCP Server | Purpose | Justification |
|------------|---------|---------------|
| **slack-mcp** | Approval UI, alerts, notifications | Human override control plane; Block Kit for approvals |
| **webhook-ingress-mcp** | Event-driven triggers | Receive GHL events; prevents polling; testable replays |
| **exa-mcp** | Web research for Researcher agent | Company/person research with caching |

### Medium Priority (Add for Production)

| MCP Server | Purpose | Justification |
|------------|---------|---------------|
| **sms-mcp** (Twilio) | Critical alerts | Escalation for approval timeouts <30min |
| **zoom-mcp** | Meeting link creation | Automated Zoom link generation for bookings |
| **linkedin-mcp** | Profile enrichment | Direct LinkedIn scraping with rate limits |

### Low Priority (Add Later)

| MCP Server | Purpose | Justification |
|------------|---------|---------------|
| **secrets-config-mcp** | Centralized secrets | Multi-host deployment with env scoping |
| **analytics-mcp** | Performance metrics | Aggregate analytics across swarms |
| **backup-mcp** | Automated backups | Scheduled backups of .hive-mind/ |

---

## Sandbox Testing Strategy

### A. Create True Sandbox Environment

```
┌─────────────────────────────────────────────────────────────┐
│                    SANDBOX ENVIRONMENT                       │
├─────────────────────────────────────────────────────────────┤
│  GHL:        Separate sub-account/location                  │
│  Google:     Dedicated test calendar + test OAuth client    │
│  Email:      Test domain (e.g., test.yourdomain.com)        │
│  Supabase:   Separate project or staging schema             │
│  Slack:      Test workspace or #sandbox channel             │
└─────────────────────────────────────────────────────────────┘
```

### B. Implement 3 Execution Modes

```python
class ExecutionMode(Enum):
    DRY_RUN = "dry_run"           # Plan + route + draft + log, NO writes
    SANDBOX_WRITE = "sandbox"     # Writes only to sandbox resources
    PROD_WRITE = "production"     # Production writes (requires approval)
```

**Feature flag in config:**
```python
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "dry_run")
```

### C. Record/Replay Testing

```
┌─────────────────────────────────────────────────────────────┐
│                  RECORD/REPLAY SYSTEM                        │
├─────────────────────────────────────────────────────────────┤
│  1. Capture MCP request/response pairs                      │
│  2. PII redaction on capture                                │
│  3. Store in tests/fixtures/mcp_recordings/                 │
│  4. Replay in tests without hitting external APIs           │
└─────────────────────────────────────────────────────────────┘
```

### D. Canary Rollout Plan

```
Stage 1: 1 internal AE, 10 leads/day, meeting prep ONLY (read-only)
Stage 2: 1 internal AE, 10 leads/day, + scheduling (calendar writes)
Stage 3: 1 internal AE, 50 leads/day, + email follow-ups
Stage 4: All AEs, 150 leads/day, full production
```

---

## Security Hardening Checklist

### Dashboard & API Authentication
- [ ] Basic auth at reverse proxy (minimum)
- [ ] JWT sessions (recommended)
- [ ] IP allowlist for admin endpoints
- [ ] HTTPS enforced (Caddy auto-SSL)

### MCP Boundary Protections
- [ ] Outbound allowlist per agent
- [ ] Max payload sizes
- [ ] Strict JSON schema validation
- [ ] Input sanitization

### Secret Hygiene
- [ ] No credentials in repo
- [ ] No credentials in logs
- [ ] No credentials in .hive-mind/
- [ ] Rotate keys before production
- [ ] Least privilege OAuth scopes

### PII & Prompt Injection
- [ ] AIDefence on inbound emails
- [ ] AIDefence on scraped pages
- [ ] AIDefence on CRM user fields
- [ ] Log redaction for: email, phone, tokens, cookies

### Egress Control
- [ ] Domain allowlist for Researcher
- [ ] Firewall rules (if cloud deployed)
- [ ] Restrict outbound ports

---

## Integration Testing: Three Swarms Together

### Handoff Contract Schema

```json
{
  "task_id": "T-uuid",
  "workflow_id": "W-uuid",
  "lead_id": "L-123",
  "source_swarm": "alpha-swarm",
  "target_swarm": "revenue-swarm",
  "risk_level": "medium",
  "required_actions": ["create_contact", "add_tag"],
  "allowed_actions": ["create_contact", "add_tag", "update_contact"],
  "grounding_evidence": {
    "source": "supabase",
    "data_id": "lead_123",
    "verified_at": "2026-01-21T10:30:00Z"
  },
  "idempotency_key": "W-uuid_L-123_create_contact_v1"
}
```

### Three-Tier Test Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                    TIER 1: CONTRACT TESTS                    │
│  - Validate inputs/outputs match shared schema              │
│  - Validate permissions (no unauthorized actions)           │
│  - Fast, run on every commit                                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              TIER 2: WORKFLOW SIMULATION TESTS               │
│  - Synthetic leads + email threads                          │
│  - Alpha → Revenue → Scaling-up flow                        │
│  - Assert: audit entries, approvals, NO writes in DRY_RUN   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                TIER 3: CHAOS / FAILURE TESTS                 │
│  - Kill swarm mid-workflow → Queen requeues safely          │
│  - MCP failures → circuit breaker → fallback chain          │
│  - Approval timeout → escalation → no write                 │
└─────────────────────────────────────────────────────────────┘
```

### Idempotency (Make-or-Break)

```python
def generate_idempotency_key(workflow_id, lead_id, action_type, template_version):
    return f"{workflow_id}_{lead_id}_{action_type}_{template_version}"

# Before any write action:
if idempotency_key in completed_actions:
    return "already_done"  # Skip duplicate
else:
    execute_action()
    mark_completed(idempotency_key)
```

---

## Production Deployment Checklist

### Phase 0: Pre-Production Gates (Must Pass)

- [ ] Day 8-10 complete (swarm coordination + workflows + integration tests)
- [ ] Audit trail + approval engine + AIDefence implemented
- [ ] Deployment scripts + rollback procedure
- [ ] Passing tests:
  - [ ] 0 double-bookings in 100 scheduling simulations
  - [ ] 0 emails sent without approval
  - [ ] Stable heartbeats under load (12 workers, 30 minutes)

### Phase 1: Staging Environment Setup

```bash
# 1. Provision staging VM
# 2. Install runtime
python --version  # 3.11+
node --version    # 18+

# 3. Configure staging env
cp .env.example .env.staging
# Edit with sandbox API keys

# 4. Start services
docker-compose -f docker-compose.staging.yml up -d

# 5. Enable DRY_RUN mode
export EXECUTION_MODE=dry_run
```

### Phase 2: Staging Validation (Go/No-Go)

**Smoke Tests:**
- [ ] MCP connectivity (all 12+ servers respond)
- [ ] Guardrails sanity (circuit breakers reset)
- [ ] Q-table load/save
- [ ] Audit DB write/read

**E2E Workflows:**
- [ ] Lead-to-meeting (dry run)
- [ ] Approval flow (Slack interaction works)
- [ ] Meeting prep generation (Researcher)

**Failure Drills:**
- [ ] Force circuit breaker open → verify recovery
- [ ] Kill MCP process → verify Queen handles gracefully
- [ ] Simulate rate limit response → verify backoff

**Observability:**
- [ ] Dashboard shows real-time health
- [ ] Alerts trigger to Slack/email

### Phase 3: Production Preparation

- [ ] Rotate production secrets
- [ ] Enforce dashboard authentication + HTTPS
- [ ] Backup `.hive-mind/` and databases
- [ ] Freeze release tag (git tag)
- [ ] Configure canary group (small cohort)

### Phase 4: Production Go-Live (Canary)

```
Hour 0-1:   Deploy with all writes gated by approval
Hour 1-2:   Enable meeting prep (read-only)
Hour 2-4:   Enable scheduling (calendar writes) if stable
Day 2:      Enable email follow-ups if no issues
Day 3-7:    Expand canary (10 → 50 → 150 leads/day)
```

**Monitor for 60 minutes after each enablement:**
- [ ] Error rate < 5%
- [ ] Queue depth stable
- [ ] No circuit breakers open
- [ ] No duplicate prevention triggers
- [ ] All approvals processed

### Phase 5: Rollback Plan

**Rollback Triggers:**
- Any double-booking
- Any email sent without required approval
- Sustained error rate > 10%
- Approval system down

**Rollback Actions:**
```bash
# 1. Set to DRY_RUN immediately
export EXECUTION_MODE=dry_run

# 2. Stop Queen workers (keep dashboard)
docker-compose stop queen

# 3. Revert release version
git checkout <last-known-good-tag>

# 4. Restore backups if data corruption suspected
./scripts/restore_backup.sh <backup_id>
```

---

## Recommended Next Steps (Priority Order)

### This Week (Days 8-10)
1. **Day 8**: Implement swarm coordination (heartbeats, auto-restart)
2. **Day 9**: Create unified workflow YAML definitions
3. **Day 10**: Run integration tests for Queen + workflows

### Next Week (Days 11-15)
4. Implement Scheduler agent
5. Implement Researcher agent
6. Enhance Communicator

### Week 3 (Days 16-20)
7. **Day 16-17**: Multi-layer failsafe
8. **Day 18**: Audit trail (P0 BLOCKER)
9. **Day 19-20**: Health monitor enhancements

### Week 4 (Days 21-25)
10. **Day 21-22**: AIDefence (P0 BLOCKER)
11. **Day 23-24**: Approval engine (P0 BLOCKER)
12. **Day 25**: Security testing

### Week 5 (Days 26-30)
13. Full test suite
14. Deployment scripts
15. Staging deploy
16. Production go-live

---

## Quick Commands Reference

```bash
# Run all tests
python -m pytest tests/ -v

# Start local development
python scripts/start_mcp_servers.py
python execution/unified_queen_orchestrator.py

# Start health dashboard
uvicorn dashboard.health_app:app --port 8080

# Check system health
curl http://localhost:8080/api/health

# Deploy to staging
./scripts/deploy_unified_swarm.ps1 -Environment staging

# Rollback
./scripts/rollback.ps1 -Version <tag>
```

---

## Architecture Diagram (Target State)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          UNIFIED CAIO SWARM                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐     ┌──────────────────────────────────────────────────┐  │
│  │   CLIENTS   │     │              UNIFIED QUEEN                        │  │
│  │  (Slack/    │────▶│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │  │
│  │   GHL/Web)  │     │  │Q-Learn │ │Byzant. │ │Context │ │ Self-  │    │  │
│  └─────────────┘     │  │ Router │ │Consens.│ │ Budget │ │Anneal  │    │  │
│                      │  └────────┘ └────────┘ └────────┘ └────────┘    │  │
│                      └───────────────────┬──────────────────────────────┘  │
│                                          │                                  │
│  ┌───────────────────────────────────────┼───────────────────────────────┐ │
│  │                    AGENT SWARMS       ▼                                │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │ │
│  │  │                    ALPHA SWARM (Lead Gen)                        │  │ │
│  │  │  HUNTER → ENRICHER → SEGMENTOR → CRAFTER → GATEKEEPER           │  │ │
│  │  └─────────────────────────────────────────────────────────────────┘  │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │ │
│  │  │                   REVENUE SWARM (Pipeline)                       │  │ │
│  │  │  SCOUT → OPERATOR → COACH → PIPER                               │  │ │
│  │  └─────────────────────────────────────────────────────────────────┘  │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │ │
│  │  │                  SCALING SWARM (Scheduling)                      │  │ │
│  │  │  SCHEDULER → RESEARCHER → COMMUNICATOR                          │  │ │
│  │  └─────────────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                          │                                  │
│  ┌───────────────────────────────────────┼───────────────────────────────┐ │
│  │                    SAFETY LAYERS      ▼                                │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │ │
│  │  │Guardrails│ │AIDefence │ │ Approval │ │  Audit   │ │ Failsafe │   │ │
│  │  │ (Rate/CB)│ │(PII/Inj) │ │ (Slack)  │ │ (SQLite) │ │ (Layers) │   │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                          │                                  │
│  ┌───────────────────────────────────────┼───────────────────────────────┐ │
│  │                    MCP SERVERS        ▼                                │ │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐   │ │
│  │  │ GHL │ │GCal │ │Gmail│ │Slack│ │ Exa │ │Supa │ │Zoom │ │WebHk│   │ │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘   │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                          │                                  │
│  ┌───────────────────────────────────────┼───────────────────────────────┐ │
│  │               UNIFIED INTEGRATION GATEWAY                              │ │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐         │ │
│  │  │Rate Limits │ │Circuit Brkr│ │  Adapters  │ │ Health Mon │         │ │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘         │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*Last Updated: January 21, 2026*
*Status: Days 1-7 Complete, Production Target: February 20, 2026*
