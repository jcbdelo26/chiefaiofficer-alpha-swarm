# CAIO Alpha Swarm — Handoff: Runtime Reliability & Backend Configuration

Date: February 11, 2026
Session: Redis + Inngest + Railway deployment configuration
Operator: PTO (non-technical GTM engineer)
AI: Claude Opus 4.6

---

## Executive Summary

Completed full backend runtime configuration for caio-alpha-swarm. Redis (Upstash) is connected and healthy in production. Inngest is code-ready with keys configured and route mounted. Railway deployment is live with all runtime variables set. Replay harness passed 50/50 (100%, avg score 4.54/5).

## Post-Handoff Update (Validated on February 11, 2026)

This section supersedes any earlier references to relaxed runtime policy in production.

- Production strict policy is now enforced in deployed Railway:
  - `REDIS_REQUIRED=true`
  - `INNGEST_REQUIRED=true`
- Live production health checks confirm strict-required dependencies are healthy:
  - `/api/health/ready` -> `200`
  - `/api/runtime/dependencies` -> `ready: true` with both Redis and Inngest required/healthy
  - `/inngest` -> `mode: cloud`, `function_count: 4`
- Replay gate re-run: `python scripts/replay_harness.py --min-pass-rate 0.95` -> `50/50`, pass rate `1.0`, `block_build=false`
- Determinism fix applied in validator:
  - `scripts/validate_runtime_env.py` now loads the target env file with `override=True` so shell env leakage cannot mask missing keys.
- Remaining blocker is staging Inngest hardening:
  - `.env.staging` still needs final `INNGEST_SIGNING_KEY` and `INNGEST_WEBHOOK_URL` before strict staging can be enforced.

---

## 1. What Was Accomplished

### 1.1 Redis Configuration (Upstash)

Two Redis instances provisioned on Upstash (free tier, AWS us-east-1):

| Environment | Instance | Endpoint |
|---|---|---|
| Staging | `caio-alpha-swarm-staging` | `moral-llama-53411.upstash.io:6379` |
| Production | `caio-alpha-swarm-production` | `welcomed-molly-53414.upstash.io:6379` |

Configuration applied to:
- `.env` (production, local)
- `.env.staging` (staging, local — created from `.env.staging.example`)
- Railway environment variables (production)

Redis variables set:
```
REDIS_URL=rediss://default:<token>@<host>:6379
REDIS_REQUIRED=false  (relaxed policy, ready to enforce)
REDIS_MAX_CONNECTIONS=50
RATE_LIMIT_REDIS_NAMESPACE=caio:<env>:ratelimit
CONTEXT_REDIS_PREFIX=caio:<env>:context
CONTEXT_STATE_TTL_SECONDS=7200 (production) / 3600 (staging)
```

Verified: Redis ping succeeds, 62ms latency from Railway.

### 1.2 Inngest Configuration

Inngest account created at inngest.com (ChiefAIOfficer / jcbdelo26).

Keys obtained and configured:
- `INNGEST_SIGNING_KEY` — from Inngest dashboard (Settings → Signing Key)
- `INNGEST_EVENT_KEY` — created as `caio-alpha-swarm` event key

Configuration applied to:
- `.env` (production, local)
- `.env.staging` (staging, local — signing key + webhook URL still empty for staging)
- Railway environment variables (production)

Inngest variables set:
```
INNGEST_SIGNING_KEY=signkey-prod-<redacted>
INNGEST_EVENT_KEY=BngE6rHc8DC<redacted>
INNGEST_REQUIRED=false  (relaxed policy)
INNGEST_APP_ID=caio-alpha-swarm-production
INNGEST_APP_NAME=CAIO Alpha Swarm
INNGEST_WEBHOOK_URL=https://caio-swarm-dashboard-production.up.railway.app/inngest
INNGEST_SERVE_ORIGIN=https://caio-swarm-dashboard-production.up.railway.app
```

Inngest endpoint verified:
```json
{
  "mode": "cloud",
  "function_count": 4,
  "has_event_key": true,
  "has_signing_key": true
}
```

### 1.3 Critical Bug Fix — Inngest serve() API

**Problem:** The `inngest` Python package updated to v0.5.15, which changed the `serve()` function signature. The old code used:
```python
# BROKEN — serve() no longer returns a mountable app
app.mount("/inngest", get_inngest_serve())
```

The v0.5+ API requires passing the FastAPI app directly:
```python
# FIXED — serve() modifies app in-place
serve(app, client=inngest_client, functions=[...], serve_path="/inngest")
```

**Files changed:**
- `core/inngest_scheduler.py:536-548` — `get_inngest_serve()` now accepts `app` parameter, passes `serve_origin` and `serve_path`
- `dashboard/health_app.py:1368-1375` — Changed from `app.mount("/inngest", get_inngest_serve())` to `get_inngest_serve(app)`

**Impact:** Without this fix, the `/inngest` route never mounted. Inngest Cloud could not reach the app. The fix enables Inngest function discovery and scheduled execution.

### 1.4 Railway Environment Fix

**Problem:** Railway had `ENVIRONMENT=development`, causing Inngest to report `"mode": "dev"`. Inngest Cloud (Production) refuses to sync with dev-mode apps.

**Fix:** Set `ENVIRONMENT=production` on Railway via CLI.

### 1.5 Railway Deployment Pipeline

Installed Railway CLI (`@railway/cli@4.29.0`) via npm. Linked to project:
- Project: `caio-swarm-dashboard`
- Service: `caio-swarm-dashboard`
- Environment: `production`

Deployed via `railway up` (CLI direct upload) and git push (auto-deploy from GitHub).

All runtime variables set on Railway via `railway variable set` (batch).

### 1.6 Trace Envelope Configuration

```
TRACE_ENVELOPE_FILE=.hive-mind/traces/tool_trace_envelopes_production.jsonl
TRACE_ENVELOPE_ENABLED=true
TRACE_RETENTION_DAYS=30
TRACE_CLEANUP_ENABLED=true
```

### 1.7 `.railwayignore` Fix

Added `nul` to `.railwayignore` to prevent Windows reserved device name from crashing Railway's upload indexer.

---

## 2. Files Changed (Committed)

Commit: `de637bb` — `fix: inngest serve() v0.5+ API + runtime reliability config`

```
 .env.example                             |  34 +++
 .env.staging.example                     |  35 +++
 .railwayignore                           |   3 +
 core/context_manager.py                  | 176 +++++++++---
 core/inngest_scheduler.py                | 322 +++++++++++++++++++++---
 core/runtime_reliability.py              | 297 ++++++++++++++++++++++  (NEW)
 core/trace_envelope.py                   | 166 +++++++++++++  (NEW)
 core/unified_guardrails.py               | 289 ++++++++++++++++++----
 core/unified_integration_gateway.py      | 135 ++++++++--
 dashboard/health_app.py                  | 206 +++++++++++++---
 dashboard/hos_dashboard.html             | 166 ++++++++-----
 scripts/bootstrap_runtime_reliability.py | 194 +++++++++++++++  (NEW)
 scripts/regression_test.py               | 126 +----------
 scripts/replay_harness.py                | 409 +++++++++++++++++++++++++++++++  (NEW)
 scripts/validate_runtime_env.py          | 226 +++++++++++++++++  (NEW)
```

**15 files changed, 2422 insertions, 362 deletions.**

---

## 3. Files Not Yet Committed (Untracked)

These exist locally but are not in git:

### Local-only environment files
- `.env.staging` — staging environment config (should not be committed)

### Documentation
- `docs/CAIO_ALPHA_DEEP_DIAGNOSTIC_2026-02-09.md`
- `docs/CAIO_ALPHA_GTM_OPERATOR_ROADMAP.md`
- `docs/CAIO_ALPHA_MAJOR_INPUTS_REQUIRED.md`
- `docs/CAIO_ALPHA_STATE_REVIEW_AND_EVALUATION_PLAN.md`
- `docs/CAIO_DASHBOARD_EMAIL_REFRESH_ROOT_CAUSE_AND_SUSTAINABLE_FIX.md`
- `docs/CAIO_PTO_INPUTS_NON_TECH_SETUP_GUIDE.md`
- `docs/CAIO_REDIS_INNGEST_HANDOFF_NON_TECH_2026-02-11.md`
- `docs/HOS_ACTION_ITEMS_GUIDE.md`
- `docs/PRODUCTION_QUICK_START.md`
- `docs/PRODUCTION_READINESS_ROADMAP.md`
- `docs/REPLAY_HARNESS.md`
- `docs/sme_architectural_review_prompt.md`

### Test infrastructure
- `tests/golden/caio_alpha_golden_set_v1.json` — 50-case golden set
- `tests/golden/sme_judge_output_schema.json`
- `tests/golden/sme_judge_system_prompt.md`
- `tests/test_replay_harness_assets.py`
- `tests/test_runtime_determinism_flows.py`
- `tests/test_runtime_reliability.py`
- `tests/test_trace_envelope_and_hardening.py`

### Scripts
- `scripts/swarm_replay_runner.py`

### CI/CD
- `.github/workflows/replay-harness.yml` — GitHub Actions workflow (not yet active)

---

## 4. New Modules Added

### `core/runtime_reliability.py`
Runtime dependency health model. Provides:
- `get_runtime_env_defaults(mode)` — mode-specific default configs
- `get_runtime_dependency_health()` — checks Redis connectivity, Inngest route mount, key presence
- `merge_runtime_env_values()` — safe env merging with overrides
- `upsert_env_file()` — atomic .env file updates

Used by `dashboard/health_app.py` at:
- `GET /api/runtime/dependencies` — reports dependency health
- `GET /api/health/ready` — blocks startup if required dependencies unhealthy

### `core/trace_envelope.py`
Structured trace emission for all tool/API calls. Provides:
- `emit_tool_trace(tool, action, status, duration_ms, ...)` — writes JSONL trace lines
- Used by inngest_scheduler, context_manager, guardrails, integration_gateway

### `scripts/validate_runtime_env.py`
CLI validator for environment configuration:
```powershell
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections
```
Checks required keys, recommended keys, Redis ping, Inngest package availability.

### `scripts/bootstrap_runtime_reliability.py`
CLI bootstrapper that generates/updates .env files with runtime reliability defaults:
```powershell
python scripts/bootstrap_runtime_reliability.py --mode production --env-file .env --redis-url "..." --validate
```

### `scripts/replay_harness.py`
Golden Set regression gate. Runs 50 test cases and enforces minimum pass rate:
```powershell
python scripts/replay_harness.py --min-pass-rate 0.95
```

---

## 5. Architecture: How Inngest Fits

### Two-Scheduler Design

The system has two independent schedulers:

**Fallback Scheduler** (`core/scheduler_service.py`) — always running via `start.sh`:
- Approval notifications (every 3 hours)
- Nurture queue processing (every 1 hour)
- Email queue processing (every 1 hour)
- No external dependencies, simple Python loop

**Inngest Scheduler** (`core/inngest_scheduler.py`) — 4 registered functions:
- `pipeline-scan` (every 15 min) — stale lead detection, ghost recovery, meeting prep triggers
- `daily-health-check` (daily 8 AM) — API connectivity, queue depths, error rates
- `weekly-icp-analysis` (Monday 9 AM) — won/lost deal analysis, ICP weight updates
- `meeting-prep-trigger` (daily 8 PM) — overnight meeting brief generation

**Without Inngest:** The system runs fine. Fallback scheduler handles essentials (email/nurture/approvals). You lose proactive pipeline scanning, self-learning ICP, and automated meeting prep.

**With Inngest:** Adds distributed execution, automatic retries, observability dashboard, and the 4 advanced automation functions above.

### Inngest Integration Path
```
Railway HTTP → FastAPI app → serve(app, ..., serve_path="/inngest")
                                    ↓
                            Inngest Cloud discovers 4 functions
                                    ↓
                            Inngest triggers functions on schedule
                                    ↓
                            Functions call GHL, Calendar, ICP APIs
```

---

## 6. Railway Production State

### Deployment
- Domain: `caio-swarm-dashboard-production.up.railway.app`
- Region: Asia Southeast (Singapore)
- Status: Online
- Latest deploy: `ba39a1a2` (SUCCESS, from git push)

### Key Endpoints Verified
| Endpoint | Status |
|---|---|
| `/api/health/ready` | 200 |
| `/api/runtime/dependencies` | `ready: true`, Redis healthy (62ms), Inngest healthy |
| `/inngest` | `mode: cloud`, 4 functions, all keys present |

### Railway Variables Set
All runtime reliability variables are set on Railway:
- `ENVIRONMENT=production`
- `REDIS_URL`, `REDIS_REQUIRED=false`, `REDIS_MAX_CONNECTIONS=50`
- `RATE_LIMIT_REDIS_NAMESPACE`, `CONTEXT_REDIS_PREFIX`, `CONTEXT_STATE_TTL_SECONDS`
- `INNGEST_SIGNING_KEY`, `INNGEST_EVENT_KEY`, `INNGEST_REQUIRED=false`
- `INNGEST_APP_ID`, `INNGEST_WEBHOOK_URL`, `INNGEST_SERVE_ORIGIN`
- `TRACE_ENVELOPE_*` variables
- Plus all existing API keys (GHL, Clay, Supabase, Anthropic, OpenAI, etc.)

---

## 7. Validation Results

### Local Validation
```
validate_runtime_env (production): PASS — 0 missing keys
validate_runtime_env (staging):    PASS — Redis healthy, Inngest skipped
```

### Replay Harness
```
Total cases:   50
Passed:        50
Failed:        0
Pass rate:     100% (required: 95%)
Avg score:     4.54 / 5.0
Block build:   false
```

---

## 8. Open Items / Next Steps

### Immediate (Low Effort)
1. **Inngest Cloud Sync** — The `/inngest` endpoint is live and the PUT handshake returns `ok: true`. The Inngest dashboard UI had trouble syncing. Try the "Curl command" tab or run `curl -X PUT https://caio-swarm-dashboard-production.up.railway.app/inngest` from terminal.

2. **Commit untracked docs and tests** — 12 docs, 4 test files, and the golden set are untracked. Consider committing to preserve them in git.

3. **Commit this handoff doc** — This file should be committed for future context.

### When Ready to Harden
4. **Enforce strict mode** — Set `REDIS_REQUIRED=true` and `INNGEST_REQUIRED=true` on Railway. This makes the app fail-fast if either dependency is unavailable. Only do this after confirming Inngest Cloud sync works end-to-end.

5. **Staging Inngest keys** — `.env.staging` has empty `INNGEST_SIGNING_KEY` and `INNGEST_WEBHOOK_URL`. If you deploy a staging environment, these need to be filled (create a separate Inngest app for staging or use dev mode).

6. **GitHub Actions CI** — `.github/workflows/replay-harness.yml` exists but is untracked. Committing it enables automatic replay harness on every push.

### Infrastructure
7. **Redis monitoring** — Upstash dashboard shows usage. Watch for bandwidth limits on free tier (200 GB/month).

8. **Inngest monitoring** — Once synced, Inngest dashboard (Runs, Metrics) shows function execution history, failures, and retries.

---

## 9. Key File Reference

| File | Purpose |
|---|---|
| `core/runtime_reliability.py` | Dependency health model, env merging |
| `core/trace_envelope.py` | Structured JSONL trace emission |
| `core/inngest_scheduler.py` | 4 Inngest scheduled functions |
| `core/scheduler_service.py` | Fallback scheduler (always running) |
| `dashboard/health_app.py` | FastAPI app, Inngest mount, health endpoints |
| `scripts/validate_runtime_env.py` | CLI env validator |
| `scripts/bootstrap_runtime_reliability.py` | CLI env bootstrapper |
| `scripts/replay_harness.py` | Golden Set regression gate |
| `.env` | Production env (local, gitignored) |
| `.env.staging` | Staging env (local, gitignored) |
| `.env.example` | Template with all keys documented |
| `.env.staging.example` | Staging template |
| `.railwayignore` | Railway upload exclusions |
| `execution/start.sh` | Railway entrypoint (scheduler + uvicorn) |
| `Procfile` | `web: sh execution/start.sh` |

---

## 10. Commands Cheat Sheet

```powershell
# Validate env
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections

# Bootstrap env (with real values)
python scripts/bootstrap_runtime_reliability.py --mode production --env-file .env --validate

# Replay harness
python scripts/replay_harness.py --min-pass-rate 0.95

# Railway deploy
npx @railway/cli up --detach -m "deploy message"

# Railway set variable
npx @railway/cli variable set "KEY=value"

# Railway logs
npx @railway/cli logs

# Railway deployment status
npx @railway/cli deployment list

# Check live endpoints
curl https://caio-swarm-dashboard-production.up.railway.app/api/health/ready
curl https://caio-swarm-dashboard-production.up.railway.app/api/runtime/dependencies?token=caio-swarm-secret-2026
curl https://caio-swarm-dashboard-production.up.railway.app/inngest
```
