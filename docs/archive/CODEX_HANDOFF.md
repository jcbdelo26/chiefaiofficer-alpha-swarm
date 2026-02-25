# CAIO Alpha Swarm — Codex Deep Review Handoff

**Date**: 2026-02-17
**Last deployed commit**: `746d347` (Railway: `caio-swarm-dashboard-production.up.railway.app`)
**Previous key commits**: `21297d8`, `b8dfc0f`, `87225fa`, `bcd3815`, `bcf7c02`
**Plan version**: v4.5
**Phase**: 4E — Supervised Live Sends (RAMP MODE ACTIVE) + 4G Production Hardening COMPLETE

---

## 1. What This System Does

CAIO Alpha Swarm is an autonomous B2B outbound sales pipeline that discovers leads, enriches them, scores ICP fit, generates personalized email copy, and dispatches via Instantly (email) + HeyReach (LinkedIn). It runs on Railway with a FastAPI dashboard.

**Architecture**: 12 agents + Queen orchestrator, 6-stage pipeline.

```
HUNTER (scrape) -> ENRICHER (enrich) -> SEGMENTOR (classify) -> CRAFTER (campaign) -> GATEKEEPER (approve) -> OUTBOX (send)
```

**Current state**: Production cutover code is complete (auth middleware, CORS lockdown, Redis migration), with post-review revalidation pending: rotate `DASHBOARD_AUTH_TOKEN` and rerun deployed auth smoke. System is in **ramp mode** — 5 emails/day, tier_1 leads only, 3 supervised days before graduating to full autonomy (25/day, all tiers).

---

## 2. Production Cutover Changes (Commit `746d347`)

**22 files changed, 3,064 insertions, 592 deletions**

This commit closes the P0 hardening patch train (P0-A through P0-E). Key areas:

### 2.1 API Auth Hardening (P0-A) — CRITICAL

**File**: `dashboard/health_app.py` (148 insertions, 24 deletions)

**What changed**:
- Added `APIAuthMiddleware` (Starlette BaseHTTPMiddleware) that enforces token auth on ALL `/api/*` routes
- Only health endpoints are exempt: `/api/health`, `/api/health/ready`, `/api/health/live`
- Token auth supports two modes: query param (`?token=...`) and header (`X-Dashboard-Token`)
- Strict mode (`DASHBOARD_AUTH_STRICT=true` env var) defaults to True in production/staging
- CORS changed from `allow_origins=["*"]` to `CORS_ALLOWED_ORIGINS` env var (Railway domain only)

**Key code to review**:
```python
_DEFAULT_UNAUTHENTICATED_API_ALLOWLIST: Set[str] = {
    "/api/health", "/api/health/ready", "/api/health/live",
}

class APIAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = _normalize_path(request.url.path)
        if path.startswith("/api/") and not _is_auth_exempt_path(path):
            token = _extract_dashboard_token(request)
            if not _token_is_valid(token):
                return JSONResponse(status_code=401, content={...})
        return await call_next(request)

def _token_is_valid(token):
    configured_token = (os.getenv("DASHBOARD_AUTH_TOKEN") or "").strip()
    if not configured_token:
        return not _is_token_strict_mode()  # No token configured = fail in strict mode
    return bool(token and token == configured_token)

def _get_cors_allowed_origins():
    raw = (os.getenv("CORS_ALLOWED_ORIGINS") or "").strip()
    if not raw:
        return ["http://localhost:8080", ...]  # Dev fallback
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
```

**Review questions**:
1. Is the middleware ordering correct? (`app.add_middleware(CORSMiddleware, ...)` then `app.add_middleware(APIAuthMiddleware)` — Starlette processes in reverse order, so auth runs FIRST)
2. Is the allowlist sufficient? Should webhook endpoints (`/webhooks/*`) also be exempt?
3. Does `_normalize_path()` handle trailing slashes and double slashes correctly?

### 2.2 Gatekeeper Snapshot Integrity (P0-B)

**File**: `execution/operator_outbound.py` (1,296 insertions/deletions — major refactor)

**What changed**:
- `DispatchBatch` now carries immutable approved scope: `approved_ids`, `approved_actions`, `preview_hash`, `expires_at`
- Execution validates scope/hash/expiry — batch can only be executed once
- Prevents queue drift from altering execution scope after approval

**Review questions**:
1. Can a batch be replayed? (Should be impossible — verify `executed_at` check)
2. Is `preview_hash` collision-resistant enough? (SHA-256 of sorted IDs + actions)
3. What happens when a batch expires? (Currently 24h, should log + alert)

### 2.3 Duplicate-Send Corrections (P0-C)

**Files**: `dashboard/health_app.py`, `execution/operator_outbound.py`, `execution/instantly_dispatcher.py`, `execution/heyreach_dispatcher.py`

**What changed**:
- Dashboard GHL send success writes terminal `status=sent_via_ghl` to prevent re-dispatch
- Instantly/HeyReach loaders exclude GHL-sent leads
- OPERATOR dedup migrated to canonical email keys (`email:<normalized>`) with legacy compatibility

**Review questions**:
1. Are there edge cases where a lead sent via GHL could still be picked up by OPERATOR?
2. Does the `sent_via_ghl` flag persist correctly in Redis vs file-based state?

### 2.4 Redis State Store (P0-D)

**File**: `core/state_store.py` (323 lines — NEW)

**What changed**:
- New `StateStore` class with Redis backend (Upstash)
- Covers: operator daily state, GATEKEEPER batches, cadence lead state
- Dual-read strategy: Redis primary, file fallback for migration period
- Distributed locks for live dispatch paths

**File**: `scripts/migrate_file_state_to_redis.py` (118 lines — NEW)

**What changed**:
- One-time migration from `.hive-mind/` file state to Redis
- Migrates: `operator_state.json`, `operator_batches/*.json`, `cadence_state/*.json`
- Reports `{"ok": true}` with counts on success
- **EXECUTED SUCCESSFULLY**: 1 operator state + 1 batch migrated, 0 errors

**Review questions**:
1. Is dual-read safe? Could stale file data override newer Redis data?
2. Are Redis keys namespaced correctly to prevent staging/production collision?
3. What's the TTL strategy for Redis keys? (Operator daily state expires, batches persist)

### 2.5 Escalation Regression Fix (P0-E)

**File**: `core/notifications.py` (48 insertions)

**What changed**:
- Escalation chain aligned to deterministic rubric: Level 1 Slack, Level 2 Slack+SMS, Level 3 Slack+SMS+Email
- Removed inconsistent behavior where some alerts skipped Slack

### 2.6 Dashboard Auth Propagation

**Files**: `dashboard/hos_dashboard.html` (63 insertions), `dashboard/leads_dashboard.html` (70 insertions)

**What changed**:
- Both dashboards now pass `DASHBOARD_AUTH_TOKEN` in API fetch calls
- Token stored in page-level variable, appended to all `/api/` requests
- Prevents dashboard breaking when strict auth is enabled

**Review questions**:
1. Is the token exposed in HTML source? (Yes — acceptable for internal dashboard)
2. Are there XSS vectors that could extract the token?

### 2.7 Supporting Scripts & Tests

**New files**:
| File | Lines | Purpose |
|------|-------|---------|
| `scripts/endpoint_auth_smoke.py` | 182 | 6-check deterministic auth smoke test (stdlib urllib, no deps) |
| `tests/test_operator_batch_snapshot_integrity.py` | 241 | Verifies immutable batch scope, one-time execution, hash validation |
| `tests/test_operator_dedup_and_send_path.py` | 195 | Canonical dedup keys, GHL-sent exclusion, legacy migration |
| `tests/test_state_store_redis_cutover.py` | 141 | Redis state store reads/writes, dual-read fallback, locks |

---

## 3. Production Cutover Gate Results (ALL PASS)

| Gate | Command | Result |
|------|---------|--------|
| Runtime Env (staging) | `python scripts/validate_runtime_env.py --mode staging --env-file .env.staging --check-connections` | **PASS** |
| Runtime Env (production) | `python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections` | **PASS** (Redis 36ms) |
| Auth Smoke (production) | `python scripts/endpoint_auth_smoke.py --base-url "https://caio-swarm-dashboard-production.up.railway.app" --token "<REDACTED>"` | **6/6 PASS** |
| Redis Migration | `python scripts/migrate_file_state_to_redis.py --hive-dir .hive-mind` | **ok: true** (2 items migrated) |
| Replay Harness | `python scripts/replay_harness.py --min-pass-rate 0.95` | **50/50 PASS** (100%, avg 4.54/5) |
| Critical Pytest Pack | 8 test files | **60 passed, 0 failures** |

---

## 4. Files Changed in Cutover (Priority Review Order)

### P0 — Security Critical
1. **`dashboard/health_app.py`** — Auth middleware, CORS lockdown, token validation
2. **`execution/operator_outbound.py`** — Gatekeeper snapshot integrity, dedup canonical keys, ramp enforcement
3. **`core/state_store.py`** — Redis state backend (NEW)

### P1 — Dispatch Safety
4. **`execution/instantly_dispatcher.py`** — GHL-sent exclusion, dedup keys
5. **`execution/heyreach_dispatcher.py`** — GHL-sent exclusion, dedup keys
6. **`webhooks/instantly_webhook.py`** — Legacy token bypass removed

### P2 — Dashboard & Observability
7. **`dashboard/hos_dashboard.html`** — Auth token propagation
8. **`dashboard/leads_dashboard.html`** — Auth token propagation
9. **`core/notifications.py`** — Escalation chain fix
10. **`core/runtime_reliability.py`** — Health check additions

### P3 — Tests & Scripts
11. **`scripts/endpoint_auth_smoke.py`** — Auth smoke test (NEW)
12. **`scripts/migrate_file_state_to_redis.py`** — State migration (NEW)
13. **`tests/test_operator_batch_snapshot_integrity.py`** — Batch integrity tests (NEW)
14. **`tests/test_operator_dedup_and_send_path.py`** — Dedup path tests (NEW)
15. **`tests/test_state_store_redis_cutover.py`** — Redis cutover tests (NEW)

---

## 5. Configuration State

### Railway Environment (69+ variables)
Key additions from cutover:
- `DASHBOARD_AUTH_TOKEN` = `<REDACTED>` (**ROTATE immediately if previously committed/shared**)
- `DASHBOARD_AUTH_STRICT` = `true`
- `CORS_ALLOWED_ORIGINS` = `https://caio-swarm-dashboard-production.up.railway.app`

### `config/production.json` — Safety Controls

```json
{
    "operator": {
        "enabled": true,
        "gatekeeper_required": true,
        "ramp": {
            "enabled": true,
            "email_daily_limit_override": 5,
            "tier_filter": "tier_1",
            "start_date": "2026-02-17",
            "ramp_days": 3
        }
    },
    "email_behavior": {
        "actually_send": true,
        "shadow_mode": true
    }
}
```

### Layered Safety Controls

| Layer | Control | Status | What Happens If Tripped |
|-------|---------|--------|-------------------------|
| 1 | `EMERGENCY_STOP` env var | `false` | Kills ALL outbound instantly |
| 2 | API auth middleware | ACTIVE | 401 on unauthenticated `/api/*` calls |
| 3 | CORS lockdown | ACTIVE | Only Railway domain accepted |
| 4 | GATEKEEPER gate | ACTIVE | Live dispatch requires batch approval |
| 5 | Ramp mode | ACTIVE | 5/day, tier_1 only |
| 6 | `--dry-run` default | ACTIVE | OPERATOR defaults to dry-run unless `--live` |
| 7 | Campaigns DRAFTED | Built-in | Instantly V2 creates campaigns as status=0 |
| 8 | Shadow mode | ACTIVE | Emails go to `.hive-mind/shadow_mode_emails/` |

---

## 6. Code Review Checklist for Codex

### Must Verify
- [ ] Auth middleware blocks unauthenticated calls to ALL protected endpoints
- [ ] Health endpoints remain public (no token needed for `/api/health/*`)
- [ ] CORS only allows configured origin (no wildcard)
- [ ] Token comparison is constant-time (timing attack resistance)
- [ ] Gatekeeper batch cannot be executed twice
- [ ] Gatekeeper batch expires after 24h
- [ ] Dedup keys are canonical (normalized email, case-insensitive)
- [ ] GHL-sent leads are excluded from Instantly/HeyReach dispatch
- [ ] Redis state writes are atomic (distributed locks for live dispatch)
- [ ] Dual-read does not override newer Redis data with stale file data
- [ ] Escalation levels 1/2/3 fire correct channels

### Should Verify
- [ ] Dashboard HTML passes auth token correctly to all fetch calls
- [ ] Webhook endpoints (`/webhooks/*`) are NOT blocked by auth middleware
- [ ] Smoke test catches real failures (false positive rate = 0)
- [ ] Migration script is idempotent (re-running doesn't corrupt state)
- [ ] Replay harness golden set covers auth-related scenarios

### Nice to Verify
- [ ] Windows cp1252 encoding issues fully resolved (no Unicode in console output)
- [ ] Rich console fallback works on Railway (Linux, no Windows quirks)
- [ ] Redis key namespace prevents cross-environment contamination

---

## 7. Known Issues & Tech Debt

| Issue | Severity | Notes |
|-------|----------|-------|
| Dashboard token exposure in documentation history | HIGH | Token value appeared in docs; rotate staging+production `DASHBOARD_AUTH_TOKEN` immediately and rerun auth smoke gates |
| Token in HTML source | LOW | Acceptable for internal dashboard; add CSP headers later |
| HeyReach webhook lacks signature validation | MEDIUM | `/webhooks/heyreach` currently trusts payload source; add shared-secret/signature validation path |
| File-based state still read as fallback | MEDIUM | Remove file fallback after confirming Redis stability over 1 week |
| Railway filesystem is ephemeral | INFO | File state persists only within deploy cycle; Redis is now primary |
| `CORS_ALLOWED_ORIGINS` doesn't include staging | INFO | Staging has its own variable; cross-env access not needed |

---

## 8. How to Run Verification

```bash
# Auth smoke test against production
python scripts/endpoint_auth_smoke.py \
  --base-url "https://caio-swarm-dashboard-production.up.railway.app" \
  --token "<DASHBOARD_AUTH_TOKEN>"

# Runtime env validation
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections

# Redis state migration (idempotent)
python scripts/migrate_file_state_to_redis.py --hive-dir .hive-mind

# Replay harness (golden set)
python scripts/replay_harness.py --min-pass-rate 0.95

# Critical test pack
python -m pytest -q tests/test_operator_batch_snapshot_integrity.py \
  tests/test_operator_dedup_and_send_path.py \
  tests/test_state_store_redis_cutover.py \
  tests/test_runtime_reliability.py

# Operator status (verify ramp active)
python -m execution.operator_outbound --status

# Pipeline dry-run
echo yes | python execution/run_pipeline.py --mode production

# Operator dry-run
python -m execution.operator_outbound --motion outbound --dry-run
```

---

## 9. Previous Commit History (Context)

| Commit | Description | Key Changes |
|--------|-------------|-------------|
| `746d347` | **Production cutover** | Auth middleware, CORS, Redis state store, smoke tests |
| `21297d8` | Task tracker audit | Verified 12/12 code claims, graduation roadmap |
| `b8dfc0f` | Pipeline body fix | Per-lead sequence extraction, mid-market targets, dashboard v2.4 |
| `87225fa` | Phase 4E ramp | Timezone fix, encoding fix, ramp config |
| `bcd3815` | GATEKEEPER gate | Batch approval, decay detection cron |
| `bcf7c02` | Phase 4C+4D | OPERATOR agent, cadence engine, CRAFTER, auto-enroll |

---

## 10. Questions for Codex Review

1. **Auth middleware ordering**: Is the Starlette middleware execution order correct? (CORS should process AFTER auth — verify middleware stack)
2. **Token timing attack**: Is `token == configured_token` vulnerable? Should we use `hmac.compare_digest()`?
3. **Batch replay prevention**: Is `executed_at` timestamp sufficient to prevent replay, or do we need a cryptographic nonce?
4. **Redis dual-read race**: If Redis write fails silently and file write succeeds, could a subsequent dual-read serve stale file data as if it were fresh?
5. **CORS preflight**: Does the middleware handle `OPTIONS` requests correctly for CORS preflight?
6. **Webhook auth gap**: Webhook endpoints (`/webhooks/instantly/*`, `/webhooks/heyreach/*`, `/webhooks/clay`, `/webhooks/rb2b`) are NOT protected by the auth middleware (they don't start with `/api/`). Should they have their own secret-based validation?
7. **State migration completeness**: Are all file-based state paths covered by the migration? What about `.hive-mind/lead_status/` and `.hive-mind/shadow_mode_emails/`?
