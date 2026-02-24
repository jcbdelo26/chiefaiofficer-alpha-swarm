# CAIO Alpha Swarm — Source of Truth Task Tracker

**Last Updated (UTC):** 2026-02-24 09:15
**Primary Objective:** Safe progression from supervised Tier_1 live sends to full autonomy without security regressions.
**Owner:** PTO/GTM (operational), Engineering (controls), HoS (message quality)

---

## 1) Current Assessed State (Validated)

### 1.1 Deployment + Runtime
- Production app: `https://caio-swarm-dashboard-production.up.railway.app`
- Latest deployed commit: `165c753` (docs), latest functional patch: `d9b8c63` (Tier_1 personalization normalization)
- Runtime health: `ready=true`
- Redis required and healthy: `REDIS_REQUIRED=true`
- Inngest required and healthy: `INNGEST_REQUIRED=true`
- Dashboard auth strict: `DASHBOARD_AUTH_STRICT=true`
- Supervised send-window override: `SUPERVISED_SEND_WINDOW_OVERRIDE=false`

### 1.2 Quality + Reliability Gates (Latest Local/Deployed Checks)
- Replay harness: `50/50 pass`, `pass_rate=1.0` (`scripts/replay_harness.py --min-pass-rate 0.95`)
- Smoke checklist (production): `passed=true`
- Targeted pytest packs run and passing:
  - `tests/test_instantly_webhook_auth.py`
  - `tests/test_runtime_determinism_flows.py`
  - `tests/test_webhook_signature_enforcement.py`
  - `tests/test_operator_batch_snapshot_integrity.py`
  - `tests/test_operator_dedup_and_send_path.py`
- Combined result in latest session: `32 tests passed`

### 1.3 Live Queue + Supervised State
- Pending queue trace (production):
  - `total_pending=2`
  - `ghl_targeted=2`
  - `auto_resolve_on_approve=2`
  - `ready_for_live_send=0`
- Latest supervised generation run:
  - command: `echo yes | python execution/run_pipeline.py --mode production --source "wpromote" --limit 2`
  - run_id: `run_20260224_163335_c95a0d`
- Tier_1 opener fix verified on fresh cards:
  - weak opener phrase hits: `0`
  - raw dict literal hits: `0`
  - sample: `Noticed Wpromote already uses 6sense, Adobe, which usually makes implementation move faster.`

---

## 2) Security + Production Risk Register

## P0 (Blockers before full autonomy)
- [ ] **Webhook strict enforcement is disabled in production env**
  - Current: `WEBHOOK_SIGNATURE_REQUIRED=false`
  - Risk: webhook auth can fail open or be policy-inconsistent.
  - Owner: PTO + Engineering
  - Required action: set to `true` in production + staging after provider strategy is finalized.

- [ ] **HeyReach auth model is not cryptographically enforced**
  - Current code marks HeyReach as `no_auth_provider` and effectively treats it as authenticated in health checks.
  - Risk: spoofable webhook events unless protected by trusted ingress controls.
  - Owner: Engineering
  - Required action:
    1. Add strict policy: unsigned providers are `unhealthy` in strict mode unless explicitly allowed via dedicated override env.
    2. Implement one of:
       - trusted reverse-proxy verification + injected bearer header, or
       - ingress IP allowlist + explicit `HEYREACH_UNSIGNED_ALLOWLIST=true` audit mode.
    3. Add tests for strict-mode rejection path.

- [ ] **Dashboard query token compatibility still enabled**
  - Current: APIs accept `?token=` and header token.
  - Risk: token leakage via browser history, logs, and copied URLs.
  - Owner: Engineering + PTO
  - Required action:
    1. Add env gate `DASHBOARD_QUERY_TOKEN_ENABLED`.
    2. Set `false` in production after PTO confirms header-based flow works.
    3. Mask token from request logs if query support remains.

## P1 (High-priority hardening)
- [ ] **State-store cutover still has implicit fallback defaults**
  - Current defaults in code: `STATE_DUAL_READ_ENABLED=true`, `STATE_FILE_FALLBACK_WRITE=true` if env not set.
  - Risk: hidden drift between Redis and file state after restart/cutover.
  - Owner: Engineering
  - Required action:
    - set explicit production env:
      - `STATE_BACKEND=redis`
      - `STATE_DUAL_READ_ENABLED=false` (after one stable release)
      - `STATE_FILE_FALLBACK_WRITE=false`

- [ ] **CORS is origin-scoped but method/header policy is broad**
  - Current: `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=True`.
  - Risk: wider browser surface than needed.
  - Owner: Engineering
  - Required action: restrict to required methods/headers only (`GET,POST,OPTIONS`; `Content-Type,X-Dashboard-Token`).

## P2 (Stability/maintenance)
- [ ] Migrate deprecated FastAPI `on_event` to lifespan handlers.
- [ ] Replace `datetime.utcnow()` usage with timezone-aware UTC.
- [ ] Remove stale references in docs/env templates (`PROXYCURL_API_KEY` in `.env.example` no longer part of primary path).

---

## 3) This Week Execution Board (PTO/GTM + Engineering)

| Priority | Task | Owner | Status | Exit Criteria |
|---|---|---|---|---|
| P0 | Enable strict webhook policy in staging | PTO + Eng | TODO | `WEBHOOK_SIGNATURE_REQUIRED=true` in staging; webhook tests pass |
| P0 | Implement HeyReach strict auth strategy | Eng | TODO | strict mode rejects unsigned unless explicit allowlist strategy active |
| P0 | Query-token deprecation plan + header-only test | PTO + Eng | TODO | `/sales` + API works header-only; query-token disabled in staging |
| P1 | Explicit Redis-only state env cutover | PTO + Eng | TODO | prod env has `STATE_DUAL_READ_ENABLED=false`, `STATE_FILE_FALLBACK_WRITE=false` |
| P1 | CORS method/header tightening | Eng | TODO | smoke/auth tests pass with tightened policy |
| P1 | Run supervised approval verification (real send proof) | PTO | IN_PROGRESS | approve 1 Tier_1 -> response `Email sent via GHL` + message visible in GHL conversation |
| P1 | Rejection-tag learning loop review | HoS + PTO | TODO | top reject tags reviewed; crafter tuning PR merged |
| P2 | Lifespan + utcnow cleanup | Eng | TODO | warning class reduced in CI/test output |

### 3.1 Webhook Strict Rollout Package (Implemented)
- Added strict webhook rollout runbook: `docs/STAGING_WEBHOOK_STRICT_MODE_ROLLOUT.md`
- Added strict webhook validation script (single env): `scripts/webhook_strict_smoke.py`
- Added strict webhook validation script (staging + production): `scripts/webhook_strict_smoke_matrix.py`

Staging validation command:
```powershell
python scripts/webhook_strict_smoke.py --base-url <STAGING_URL> --dashboard-token <STAGING_DASHBOARD_AUTH_TOKEN> --expect-webhook-required true --webhook-bearer-token <WEBHOOK_BEARER_TOKEN>
```

### 3.2 Staging Strict Rollout Execution (2026-02-24)
- [x] Baseline staging checks passed before change:
  - `webhook_strict_smoke --expect-webhook-required false` -> pass
  - `deployed_full_smoke_checklist` -> pass
- [x] Staging env updated:
  - `WEBHOOK_SIGNATURE_REQUIRED=true`
  - `WEBHOOK_BEARER_TOKEN` set/rotated for staging
- [x] Post-change strict validation passed:
  - `webhook_strict_smoke --expect-webhook-required true --webhook-bearer-token <...>` -> pass
  - unauthenticated Instantly/Clay/RB2B webhook probes blocked
  - bearer-authenticated Instantly/Clay webhook probes accepted
  - `deployed_full_smoke_checklist` -> pass
- [ ] Follow-up hardening nuance:
  - runtime `provider_auth.heyreach` currently reports `authed=true` while strict HeyReach no-auth probe returns `503` (provider has no signature/header path).
  - engineering should align runtime health semantics with strict enforcement behavior before production strict-mode promotion.

---

## 4) Operational Ritual (Daily Supervised Window)

**Schedule:** 15:00 EST (PTO owner)

### Pre-flight (must pass)
```powershell
python scripts/deployed_full_smoke_checklist.py --base-url https://caio-swarm-dashboard-production.up.railway.app --token <DASHBOARD_AUTH_TOKEN>
python scripts/trace_outbound_ghl_queue.py --base-url https://caio-swarm-dashboard-production.up.railway.app --token <DASHBOARD_AUTH_TOKEN>
```

### Supervised generation
```powershell
echo yes | python execution/run_pipeline.py --mode production --source "wpromote" --limit 2
```

### HoS review and decision
- Review only fresh Tier_1 in `/sales`.
- Reject requires structured tag + reason.
- Approve exactly one card for verification when needed.

### Post-approval proof
- API response must be: `Email sent via GHL`
- Verify the message in GHL conversation thread for that contact.
- Record outcome in this tracker.

---

## 5) Safe Training + Evaluation Regimen (Until Autonomy)

## 5.1 Training lane policy
- Continue Tier_1 supervised only.
- Keep daily volume conservative (`<=5/day`) until clean-day threshold reached.
- Maintain 2-hour approval SLA for actionable pending cards.

## 5.2 Evaluation gates (required)
- Replay gate every release:
```powershell
python scripts/replay_harness.py --min-pass-rate 0.95
```
- Critical regression pack:
```powershell
python -m pytest -q \
  tests/test_gatekeeper_integration.py \
  tests/test_runtime_reliability.py \
  tests/test_runtime_determinism_flows.py \
  tests/test_trace_envelope_and_hardening.py \
  tests/test_replay_harness_assets.py \
  tests/test_operator_batch_snapshot_integrity.py \
  tests/test_operator_dedup_and_send_path.py \
  tests/test_state_store_redis_cutover.py \
  tests/test_webhook_signature_enforcement.py
```
- Deployment should be blocked if pass rate drops below threshold.

## 5.3 Edge-case set to keep running
- EMERGENCY_STOP during live dispatch.
- Re-run executed batch must not resend.
- Queue drift after approval must not alter execution scope.
- `sent_via_ghl` items must never route to Instantly/HeyReach.
- CORS preflight on protected APIs.
- Redis lock contention on concurrent live motion.
- Cadence dry-run must not mutate persistent state.
- Unmapped/unknown campaign cards should be auto-separated from dispatchable queue.

---

## 6) Inputs Needed From PTO (Current)

- [ ] Confirm webhook hardening rollout window for staging then production.
- [ ] Approve disabling query-token mode in production after header-token verification.
- [ ] Confirm state-store final cutover values:
  - `STATE_DUAL_READ_ENABLED=false`
  - `STATE_FILE_FALLBACK_WRITE=false`
- [ ] Confirm token rotation date for `DASHBOARD_AUTH_TOKEN` after rollout.

---

## 7) Full-Autonomy Go/No-Go Criteria

All must be true for go-live autonomy:
- [ ] 3 clean supervised live days in a row (no gate failures, no unresolved sends).
- [ ] Webhook strict mode enabled with no unsigned-provider blind spots.
- [ ] Header-only auth model validated; query-token disabled in production.
- [ ] Redis-only state cutover complete; no file-fallback writes.
- [ ] Replay gate >= 0.95 and critical pytest pack green on release branch.
- [ ] HoS quality metrics stable (rejection ratio and personalization quality trending positive).

---

## 8) Change Log (Most Recent)

- `d9b8c63` — personalization: normalized Tier_1 hooks + human-readable opener text.
- `42f829a` — strengthened Tier_1 opener and signal hooks.
- `3bf089d` — GHL contact lookup fixed to `/contacts?locationId+query`; supervised send-window override support.
- `d9ade64` — structured rejection tags + clean-day ramp gating.

