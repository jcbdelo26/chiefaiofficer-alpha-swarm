> **DEPRECATED (2026-02-27)**: This file has been merged into `task.md` (project root).
> All future updates go to `task.md` only. This file is kept for historical reference.

# CAIO Alpha Swarm — Source of Truth Task Tracker

**Last Updated (UTC):** 2026-02-26 19:25
**Primary Objective:** Safe progression from supervised Tier_1 live sends to full autonomy without security regressions.
**Owner:** PTO/GTM (operational), Engineering (controls), HoS (message quality)

---

## 1) Current Assessed State (Validated)

### 1.1 Deployment + Runtime
- Production app: `https://caio-swarm-dashboard-production.up.railway.app`
- Latest deployed commit: `f1cb70a` (webhook/header-token smoke compatibility), latest functional patch: `d9b8c63` (Tier_1 personalization normalization)
- Runtime health: `ready=true`
- Redis required and healthy: `REDIS_REQUIRED=true`
- Inngest required and healthy: `INNGEST_REQUIRED=true`
- Dashboard auth strict: `DASHBOARD_AUTH_STRICT=true`
- Supervised send-window override: `SUPERVISED_SEND_WINDOW_OVERRIDE=false`

### 1.2 Quality + Reliability Gates (Latest Local/Deployed Checks)
- Replay harness: `50/50 pass`, `pass_rate=1.0` (`scripts/replay_harness.py --min-pass-rate 0.95`)
- Smoke checklist (production): `passed=true`
- Deployed full-smoke matrix (staging + production, header-only mode): `passed=true` with `--expect-query-token-enabled false`
- Deployed full-smoke matrix with HeyReach hard-auth required: `passed=false` (expected while `HEYREACH_UNSIGNED_ALLOWLIST=true`)
- Post-push verification (2026-02-24 UTC):
  - `deployed_full_smoke_matrix.py --expect-query-token-enabled false` -> `passed=true`
  - `deployed_full_smoke_matrix.py --expect-query-token-enabled false --require-heyreach-hard-auth` -> `passed=false`
    - blocker in both envs: `runtime_heyreach_hard_auth` reports `heyreach_unsigned_allowlisted=true`
- Targeted pytest packs run and passing:
  - `tests/test_instantly_webhook_auth.py`
  - `tests/test_runtime_determinism_flows.py`
  - `tests/test_webhook_signature_enforcement.py`
  - `tests/test_operator_batch_snapshot_integrity.py`
  - `tests/test_operator_dedup_and_send_path.py`
- Combined result in latest session: `32 tests passed`
- Phase-1 hardening TDD pack (latest local):
  - `tests/test_phase1_proof_deliverability.py`
  - `tests/test_phase1_feedback_loop_integration.py`
  - `tests/test_task_routing_policy.py`
  - `tests/test_runtime_reliability.py`
  - combined result: `25 passed`
- Phase-1 feedback + deliverability focused regression (latest local):
  - `tests/test_phase1_proof_deliverability.py`
  - `tests/test_phase1_feedback_loop_integration.py`
  - `tests/test_feedback_loop_trace.py`
  - combined result: `8 passed`

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
- [x] **Webhook strict enforcement enabled in staging + production**
  - Current: `WEBHOOK_SIGNATURE_REQUIRED=true` in staging and production.
  - Validation:
    - `python scripts/webhook_strict_smoke.py --base-url <env_url> --dashboard-token <token> --expect-webhook-required true --webhook-bearer-token <bearer>`
    - `python scripts/deployed_full_smoke_checklist.py --base-url <env_url> --token <token>`
  - Notes:
    - rollback commands were prepared before production flip and saved to local ops temp (`caio_prod_webhook_rollback.ps1`).

- [ ] **HeyReach auth model is not cryptographically enforced**
  - Current deployed env still uses temporary unsigned allowlist mode (`HEYREACH_UNSIGNED_ALLOWLIST=true`).
  - Risk: spoofable webhook events unless protected by trusted ingress controls.
  - Owner: Engineering
  - Progress:
    1. [x] Added strict policy in code: unsigned HeyReach is `unhealthy` in strict mode unless explicitly allowlisted via `HEYREACH_UNSIGNED_ALLOWLIST=true`.
    2. [x] Added enforcement path in webhook auth helper (`require_webhook_auth`) with explicit unsigned-provider allowlist gate.
    3. [x] Added/updated tests:
       - `tests/test_runtime_reliability.py`
       - `tests/test_webhook_signature_enforcement.py`
       - local result: `22 passed`.
    4. [x] Added HeyReach bearer-auth strict path (`HEYREACH_BEARER_TOKEN`) in runtime health and webhook tests.
       - allows strict-mode auth without unsigned allowlist when trusted ingress can inject `Authorization: Bearer ...`.
       - local verification: `25 passed` for runtime/webhook auth pack.
    5. [x] Added deployed smoke hard-auth gate:
       - `scripts/deployed_full_smoke_checklist.py --require-heyreach-hard-auth`
       - `scripts/deployed_full_smoke_matrix.py --require-heyreach-hard-auth`
       - runtime output now reports explicit blocker details (`heyreach_unsigned_allowlisted=true`) in each environment.
  - Remaining action:
    - configure and validate final strategy:
      - secure ingress + set `HEYREACH_BEARER_TOKEN` + set `HEYREACH_UNSIGNED_ALLOWLIST=false`, then validate with strict smoke **and** full smoke hard-auth gate:
        - `python scripts/webhook_strict_smoke_matrix.py ... --require-heyreach-hard-auth`
        - `python scripts/deployed_full_smoke_matrix.py ... --require-heyreach-hard-auth`
      - after this gate is green in staging + production, mark this item DONE.
      - keep temporary controlled audit mode with `HEYREACH_UNSIGNED_ALLOWLIST=true` until ingress path is ready.
  - Tracker note:
    - Temporary HeyReach allowlist mode active until March 10, 2026. Owner: PTO.

- [x] **Dashboard query token deprecation completed**
  - Current: header token auth is enforced for protected API routes; query-token auth is disabled in staging and production.
  - Risk: token leakage via browser history, logs, and copied URLs.
  - Owner: Engineering + PTO
  - Progress:
    1. [x] Added env gate `DASHBOARD_QUERY_TOKEN_ENABLED` (default `true`).
    2. [x] Header token now has extraction priority over query token.
    3. [x] Added smoke-script support for header-only mode:
       - `scripts/endpoint_auth_smoke.py --expect-query-token-enabled <true|false>`
       - `scripts/deployed_full_smoke_checklist.py --expect-query-token-enabled <true|false>`
  - Rollout actions:
    1. [x] Set `DASHBOARD_QUERY_TOKEN_ENABLED=false` in staging.
    2. [x] Ran full smoke in header-only mode and validated `/sales` API wiring.
    3. [x] Set `DASHBOARD_QUERY_TOKEN_ENABLED=false` in production and validated:
       - `python scripts/deployed_full_smoke_checklist.py --base-url https://caio-swarm-dashboard-production.up.railway.app --token <PROD_DASHBOARD_AUTH_TOKEN> --expect-query-token-enabled false`
       - `python scripts/webhook_strict_smoke.py --base-url https://caio-swarm-dashboard-production.up.railway.app --dashboard-token <PROD_DASHBOARD_AUTH_TOKEN> --expect-webhook-required true --webhook-bearer-token <PROD_WEBHOOK_BEARER_TOKEN>`

## P1 (High-priority hardening)
- [x] **State-store cutover env flags finalized in production**
  - Current production env:
    - `STATE_BACKEND=redis`
    - `STATE_DUAL_READ_ENABLED=false`
    - `STATE_FILE_FALLBACK_WRITE=false`
  - Verification:
    - deployed smoke (production) passed
    - webhook strict smoke (production) passed

- [x] **CORS method/header policy tightened**
  - Current:
    - `allow_methods` is explicit via `CORS_ALLOWED_METHODS` (default `GET,POST,OPTIONS`)
    - `allow_headers` is explicit via `CORS_ALLOWED_HEADERS` (default `Content-Type,X-Dashboard-Token`)
    - `allow_credentials=True` retained for authenticated dashboard browser flows
  - Owner: Engineering
  - Verification:
    - targeted regression tests passed (`40 passed`)
    - staging deployed smoke passed (`--expect-query-token-enabled false`)
    - production deployed smoke passed (`--expect-query-token-enabled false`)
    - webhook strict smoke matrix passed (staging + production)

## P2 (Stability/maintenance)
- [x] Migrate deprecated FastAPI `on_event` to lifespan handlers.
  - `dashboard/health_app.py` now uses FastAPI `lifespan` startup/shutdown management.
- [ ] Replace `datetime.utcnow()` usage with timezone-aware UTC.
  - Incremental progress:
    - `execution/run_pipeline.py` updated to timezone-aware UTC timestamps.
    - `execution/rl_engine.py` updated to timezone-aware UTC timestamps.
- [ ] Remove stale references in docs/env templates (`PROXYCURL_API_KEY` in `.env.example` no longer part of primary path).

---

## 3) This Week Execution Board (PTO/GTM + Engineering)

| Priority | Task | Owner | Status | Exit Criteria |
|---|---|---|---|---|
| P0 | Enable strict webhook policy in staging + production | PTO + Eng | DONE | `WEBHOOK_SIGNATURE_REQUIRED=true` in both envs; strict smoke + full smoke pass |
| P0 | Implement HeyReach strict auth strategy | Eng | IN_PROGRESS | strict mode rejects unsigned unless explicit allowlist strategy active |
| P0 | Query-token deprecation plan + header-only test | PTO + Eng | DONE | staging + production header-only validation passing (`expect-query-token-enabled false`) |
| P1 | Explicit Redis-only state env cutover | PTO + Eng | DONE | prod env has `STATE_DUAL_READ_ENABLED=false`, `STATE_FILE_FALLBACK_WRITE=false`; deployed smoke passing |
| P1 | CORS method/header tightening | Eng | DONE | explicit methods/headers deployed; smoke/auth checks passing in staging + production |
| P1 | Run supervised approval verification (real send proof) | PTO | IN_PROGRESS | approve 1 Tier_1 -> response `Email sent via GHL` + message visible in GHL conversation |
| P1 | Phase-1 deterministic proof + deliverability + feedback-loop closure | Eng | IN_PROGRESS | approvals terminate as `sent_proved/sent_unresolved/blocked_deliverability`; feedback tuples persisted and visible in `/api/pending-emails` payload |
| P1 | Rejection-tag learning loop review | HoS + PTO | TODO | top reject tags reviewed; crafter tuning PR merged |
| P2 | Lifespan + utcnow cleanup | Eng | IN_PROGRESS | no `@app.on_event` usage and utcnow deprecation warnings reduced in critical runtime paths |

### 3.1 Webhook Strict Rollout Package (Implemented)
- Added strict webhook rollout runbook: `docs/STAGING_WEBHOOK_STRICT_MODE_ROLLOUT.md`
- Added strict webhook validation script (single env): `scripts/webhook_strict_smoke.py`
- Added strict webhook validation script (staging + production): `scripts/webhook_strict_smoke_matrix.py`

Staging validation command:
```powershell
python scripts/webhook_strict_smoke.py --base-url <STAGING_URL> --dashboard-token <STAGING_DASHBOARD_AUTH_TOKEN> --expect-webhook-required true --webhook-bearer-token <WEBHOOK_BEARER_TOKEN>
```

### 3.2 Staging + Production Strict Rollout Execution (2026-02-24)
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
- [x] Production strict rollout executed:
  - baseline prod `webhook_strict_smoke --expect-webhook-required false` -> pass
  - baseline prod `deployed_full_smoke_checklist` -> pass
  - prod env updated:
    - `WEBHOOK_SIGNATURE_REQUIRED=true`
    - `WEBHOOK_BEARER_TOKEN` preserved
  - post-change prod strict validation:
    - `webhook_strict_smoke --expect-webhook-required true --webhook-bearer-token <...>` -> pass
    - unauthenticated Instantly/Clay/RB2B webhook probes blocked
    - bearer-authenticated Instantly/Clay webhook probes accepted
    - `deployed_full_smoke_checklist` -> pass
- [x] Follow-up hardening nuance validated post-deploy:
  - runtime + webhook auth logic enforce `HEYREACH_UNSIGNED_ALLOWLIST` consistently.
  - post-deploy strict smoke confirms `provider_auth.heyreach.unsigned_allowlisted=true` and readiness remains healthy.
- [x] Transitional rollout guardrail applied:
  - `HEYREACH_UNSIGNED_ALLOWLIST=true` set in staging + production (no redeploy triggered via `--skip-deploys`).
  - next deploy will preserve runtime readiness while keeping HeyReach unsigned path explicitly controlled.
- [x] Post-deploy verification on commit `00bb12e`:
  - staging strict smoke: pass
  - production strict smoke: pass
  - staging full smoke (`--expect-query-token-enabled true`): pass
  - production full smoke (`--expect-query-token-enabled true`): pass
- [x] Staging header-only auth validation (query-token disabled):
  - env: `DASHBOARD_QUERY_TOKEN_ENABLED=false` (staging)
  - `python scripts/deployed_full_smoke_checklist.py --base-url https://caio-swarm-dashboard-staging.up.railway.app --token <STAGING_DASHBOARD_AUTH_TOKEN> --expect-query-token-enabled false` -> pass
  - `python scripts/webhook_strict_smoke.py --base-url https://caio-swarm-dashboard-staging.up.railway.app --dashboard-token <STAGING_DASHBOARD_AUTH_TOKEN> --expect-webhook-required true --webhook-bearer-token <STAGING_WEBHOOK_BEARER_TOKEN>` -> pass
- [x] Production header-only auth validation (query-token disabled):
  - env: `DASHBOARD_QUERY_TOKEN_ENABLED=false` (production)
  - `python scripts/deployed_full_smoke_checklist.py --base-url https://caio-swarm-dashboard-production.up.railway.app --token <PROD_DASHBOARD_AUTH_TOKEN> --expect-query-token-enabled false` -> pass
  - `python scripts/webhook_strict_smoke.py --base-url https://caio-swarm-dashboard-production.up.railway.app --dashboard-token <PROD_DASHBOARD_AUTH_TOKEN> --expect-webhook-required true --webhook-bearer-token <PROD_WEBHOOK_BEARER_TOKEN>` -> pass

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

- [x] Webhook strict rollout completed in staging + production.
- [x] Query-token mode disabled in production after header-token verification.
- [x] State-store final cutover values confirmed in production:
  - `STATE_DUAL_READ_ENABLED=false`
  - `STATE_FILE_FALLBACK_WRITE=false`
- [x] Input 1: HoS/PTO confirmation in GHL UI that approved Andrew message is visible in contact conversation (final supervised proof).
- [ ] Input 2: Decision on remaining pending cards in `/sales` (approve/reject using required structured rejection tags).
- [ ] Input 3: Final token-rotation date/time for `DASHBOARD_AUTH_TOKEN` (staging + production).
- [x] Input 4: `scripts/trace_outbound_ghl_queue.py` updated for strict header-token auth (`X-Dashboard-Token`) and verified by test (`tests/test_trace_outbound_ghl_queue.py`).

---

## 7) Full-Autonomy Go/No-Go Criteria

All must be true for go-live autonomy:
- [ ] 3 clean supervised live days in a row (no gate failures, no unresolved sends).
- [ ] Webhook strict mode enabled with no unsigned-provider blind spots.
- [x] Header-only auth model validated; query-token disabled in production.
- [x] Redis-only state cutover complete; no file-fallback writes.
- [ ] Replay gate >= 0.95 and critical pytest pack green on release branch.
- [ ] HoS quality metrics stable (rejection ratio and personalization quality trending positive).

---

## 8) Change Log (Most Recent)

- `UNRELEASED` — Phase-1 feedback/deliverability patch:
  - `core/deliverability_guard.py`: added deterministic recent hard-bounce memory gate from `DELIVERABILITY_BOUNCE_FILE` + `DELIVERABILITY_BOUNCE_LOOKBACK_DAYS`; high-risk bounce recipients now fail closed as `recent_hard_bounce`.
  - `core/feedback_loop.py`: added trace-envelope emission for `record_email_outcome` (success/failure) for replay diagnostics.
  - tests: `tests/test_phase1_proof_deliverability.py::test_deliverability_guard_blocks_recent_hard_bounce` and `tests/test_feedback_loop_trace.py::test_feedback_loop_emits_trace_envelope`.
- `UNRELEASED` — Added PTO/GTM input completion runbook: `docs/PTO_GTM_INPUT_COMPLETION_RUNBOOK.md` (non-technical step-by-step for Inputs 1-4).
- `UNRELEASED` — Fixed strict-auth queue trace client: `scripts/trace_outbound_ghl_queue.py` now sends `X-Dashboard-Token` header (no query-token auth); regression test passing in `tests/test_trace_outbound_ghl_queue.py`.
- `4992d69` — hardening patch pushed: FastAPI lifespan migration (`dashboard/health_app.py`), timezone-aware UTC updates in critical runtime paths (`execution/run_pipeline.py`, `execution/rl_engine.py`), and smoke matrix hard-auth enforcement option.
- `UNRELEASED` — P2 reliability cleanup: migrated `dashboard/health_app.py` from deprecated `@app.on_event` hooks to FastAPI lifespan; moved critical pipeline timestamps (`execution/run_pipeline.py`, `execution/rl_engine.py`) to timezone-aware UTC.
- `UNRELEASED` — smoke gate hardening: `deployed_full_smoke_checklist.py` and `deployed_full_smoke_matrix.py` now support `--require-heyreach-hard-auth` to fail when unsigned HeyReach allowlist is still active.
- `21993cd` — CORS hardening: explicit `CORS_ALLOWED_METHODS` / `CORS_ALLOWED_HEADERS` defaults; deployed and smoke-validated on staging + production.
- `f1cb70a` — smoke hardening: `webhook_strict_smoke.py` uses header-token runtime auth path (query-token-independent).
- `d9b8c63` — personalization: normalized Tier_1 hooks + human-readable opener text.
- `42f829a` — strengthened Tier_1 opener and signal hooks.
- `3bf089d` — GHL contact lookup fixed to `/contacts?locationId+query`; supervised send-window override support.
- `d9ade64` — structured rejection tags + clean-day ramp gating.
- `5eaffac` — deployed HeyReach strict auth hardening (`HEYREACH_UNSIGNED_ALLOWLIST` gate) + regression tests; staging/prod strict smoke passed.
- `00bb12e` — deployed query-token gate (`DASHBOARD_QUERY_TOKEN_ENABLED`) + header-priority auth + smoke flags for header-only validation.

