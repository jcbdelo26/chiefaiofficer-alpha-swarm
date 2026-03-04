> **DEPRECATED (2026-02-27)**: Merged into `task.md`.
> **ARCHIVE MODE (2026-03-03)**: This file is historical context only. Live status must be updated in `task.md` only.

# CAIO Alpha Swarm — Historical Task Tracker (Read-Only Context)

**Last Updated (UTC):** 2026-03-03 11:00
**Primary Objective:** Safe progression from supervised Tier_1 live sends to full autonomy without security regressions.
**Owner:** PTO/GTM (operational), Engineering (controls), HoS (message quality)

---

**Canonical status source**: `task.md` (root).  
**Usage rule**: Do not use this file as a live go/no-go board.

---

## 1) Current Assessed State (Validated)

### 1.1 Deployment + Runtime
- Production app: `https://caio-swarm-dashboard-production.up.railway.app`
- Historical deployed-commit snapshot (not live): `f1cb70a` (webhook/header-token smoke compatibility), latest functional patch at snapshot time: `d9b8c63` (Tier_1 personalization normalization)
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

## P0-v1.1 (Agentic Engineering Audit — Security Hardening, 2026-03-02)

- [x] **N1: Query-token auth default hardened**
  - `_is_query_token_enabled()` now defaults to DISABLED in production/staging.
  - Header-only auth (`X-Dashboard-Token`) is the canonical path.
  - Override: `DASHBOARD_QUERY_TOKEN_ENABLED=true`.
  - File: `dashboard/health_app.py`

- [x] **N2: Tokenized dashboard URLs removed from Slack notifier**
  - `core/approval_notifier.py` no longer embeds `?token=` in dashboard URLs.
  - Added `_dashboard_url()` helper returning token-free URLs.
  - File: `core/approval_notifier.py`

- [x] **N3: Session secret strict enforcement**
  - Production/staging requires explicit `SESSION_SECRET_KEY` env var.
  - Falls back to `DASHBOARD_AUTH_TOKEN` with warning; raises `RuntimeError` if neither set.
  - File: `dashboard/health_app.py`

- [x] **N4: Runtime dependencies auth state enriched**
  - `/api/runtime/dependencies` now reports: `token_configured`, `session_secret_explicit`, `webhook_signature_required`, `environment`, `query_token_enabled`, `strict_mode`, `token_header`.
  - File: `dashboard/health_app.py`

- [x] **N6: OpenAPI docs disabled in production/staging**
  - `/docs`, `/redoc`, `/openapi.json` return 404 in production/staging.
  - Local dev retains Swagger/ReDoc for development convenience.
  - File: `dashboard/health_app.py`

- [x] **N7: Dormant learning engines gated behind feature flags**
  - 5 engine files annotated with `STATUS: DORMANT` headers + feature flag references.
  - Catalog: `docs/DORMANT_ENGINES.md` (activation criteria, data thresholds, rollback procedures).
  - Flags: `FEEDBACK_LOOP_POLICY_ENABLED`, `AB_TEST_ENGINE_ENABLED`, `SELF_ANNEALING_ENGINE_ENABLED`, `RL_ENGINE_ENABLED`, `SELF_LEARNING_ICP_ENABLED`.
  - Files: `core/feedback_loop.py`, `core/ab_test_engine.py`, `core/self_annealing_engine.py`, `execution/rl_engine.py`, `core/self_learning_icp.py`

- [x] **Strict-auth parity smoke script created**
  - `scripts/strict_auth_parity_smoke.py` validates N1-N7 on deployed instances.
  - Usage: `python scripts/strict_auth_parity_smoke.py --base-url <URL> --token <TOKEN>`

- [x] **Security hardening tests written**
  - `tests/test_security_hardening_v11.py` — 26 tests covering all N1-N7 nuances.
  - All passing alongside existing 96 tests (dashboard login, health monitor, feedback loop).

- Validation:
  - `python -m pytest tests/test_security_hardening_v11.py -x -q --tb=short -s` -> 26 passed
  - `python -m pytest tests/test_dashboard_login.py tests/test_health_monitor.py tests/test_feedback_loop.py -x -q --tb=short -s` -> 96 passed (no regressions)

- Railway env vars needed before deploy:
  - `SESSION_SECRET_KEY` (new, dedicated session signing secret — recommended)
  - `WEBHOOK_SIGNATURE_REQUIRED=true` (advisory, for N5 parity)

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

## 2B) Agentic Engineering Audit — 5-Pillar Assessment (2026-03-02)

**Source**: `docs/AGENTIC_ENGINEERING_AUDIT_HANDOFF.md` (v1.1)
**Framework**: 5 Pillars of Agentic AI Engineering (Context, Validation, Tooling, Codebases, Compound)

| Pillar | Score | Verdict | Primary Gap |
|--------|------:|---------|-------------|
| Context Engineering | 9.0 | Strong | No indexed freshness automation |
| Agentic Validation | 8.8 | Strong | Learning loops mostly observational |
| Agentic Tooling | 8.4 | Strong | Tool orchestration/discovery fragmentation |
| Agentic Codebases | 7.8 | Good (weakest) | Dormant systems + auth nuance drift |
| Compound Engineering | 8.1 | Strong | Feedback not consistently policy-closing |
| **Overall** | **8.4** | **Production-capable** | **Strict auth + dormant engine gating** |

### Gap Remediation Roadmap (4 Sprints)

**Sprint A — Quick Wins (COMPLETE)**:
| # | Gap | Action | Status |
|---|-----|--------|--------|
| 1 | G4.1 | Add DORMANT headers + feature flags to 5 engine files | DONE |
| 2 | G4.1 | Create `docs/DORMANT_ENGINES.md` catalog | DONE |
| 3 | N1-N7 | Security hardening (query-token, session secret, OpenAPI, token URLs) | DONE |
| 4 | N7 | Strict-auth parity smoke script | DONE |
| 5 | G1.5 | Create `docs/GLOSSARY.md` (80+ terms, 14 categories) | DONE |
| 6 | G4.5 | Clean up 16 TODO stubs in `core/agent_manager.py` + dormant header + emoji purge | DONE |
| 7 | G1.2 | Add YAML frontmatter to 8 critical docs | DONE |
| 8 | G4.4 | Create `scripts/check_ascii.py` + add to `.githooks/pre-commit` (staged-only mode) | DONE |

**Sprint B — Structural Improvements (COMPLETE)**:
| # | Gap | Action | Status |
|---|-----|--------|--------|
| 9 | G1.1 | Create `docs/KNOWLEDGE_INDEX.md` (master doc index, 55 active + 15 archived) | DONE |
| 10 | G3.1 | Create unified `cli.py` entry point (12 subcommands) | DONE |
| 11 | G3.3 | Create `scripts/smoke_all.py` orchestrator (3 scripts: smoke + auth + UI) | DONE |
| 12 | G2.4 | Create `tests/test_cross_environment_bridge.py` (12 tests, 4 scenarios) | DONE |
| 13 | G2.2 | Create `scripts/validate_dashboard_ui.py` (6 endpoint checks) | DONE |
| 14 | G1.3 | Create `scripts/check_doc_freshness.py` (critical 7d + standard 30d thresholds) | DONE |

**Sprint C — Compound Engineering Enhancements (COMPLETE)**:
| # | Gap | Action | Status |
|---|-----|--------|--------|
| 15 | G3.2 | Create `docs/MCP_SERVER_CATALOG.md` (15 servers, ~98 tools) | DONE |
| 16 | G1.4 | Create `docs/adr/` with 5 backfilled ADRs (001-005) | DONE |
| 17 | G5.3 | Create `scripts/capture_lesson.py` + `docs/LESSONS_LEARNED.md` (6 initial lessons) | DONE |
| 18 | G5.4 | Create `.claude/commands/skills/` (deploy-and-validate, sprint-close, diagnose-failure) | DONE |
| 19 | G3.4 | Create `scripts/diagnose.py` (case_id/correlation_id trace, breakers, health, errors) | DONE |

**Sprint D — Deep Integration (Strategic)**:
| # | Gap | Action | Status |
|---|-----|--------|--------|
| 20 | G4.3 | Create `core/gateway_registry.py` + wire 3 gateways | DONE |
| 21 | G5.2 | Add compound metrics endpoint + dashboard tab | DONE |
| 22 | G2.3 | Fix remaining ~15 legacy test failures (33 total: 295 pass, 57 skip, 0 fail) | DONE |
| 23 | G2.1 | Activate feedback loops: quality_guard <-> feedback_loop integration, feature-flagged | DONE |

### Codex Handoff Candidates (for agent manager review, tests, validation)
See Section 9 below for full handoff specification.

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

## 8) Go/No-Go — v1.1 Audit Additions

In addition to the existing full-autonomy gates, the v1.1 audit adds:
- [x] Query-token auth disabled in production (N1 — code change done, deploy pending).
- [x] Session secret explicit in production (N3 — code change done, `SESSION_SECRET_KEY` env var needed on Railway).
- [x] OpenAPI docs disabled in production (N6 — code change done, deploy pending).
- [x] Dormant engines gated behind feature flags (N7 — all 5 files annotated).
- [ ] Run `scripts/strict_auth_parity_smoke.py` against production after deploy — all N1-N7 checks must pass.
- [ ] Set `SESSION_SECRET_KEY` env var on Railway (production + staging).
- [ ] Set `WEBHOOK_SIGNATURE_REQUIRED=true` on Railway if not already set.

---

## 9) Codex Handoff — Areas for Agent Manager Review, Tests & Validation

The following areas are suitable for handoff to Codex (agent manager) for independent review, test writing, and validation. Each area is self-contained with clear acceptance criteria.

### Handoff A: Sprint A Remaining Quick Wins (Low Risk, High Impact)

**Scope**: Complete the remaining Sprint A items from the agentic engineering audit.

| Task | Description | Files | Acceptance |
|------|-------------|-------|------------|
| Glossary | Create `docs/GLOSSARY.md` with all domain terms | New file | Covers Tier_1/2/3, shadow_mode, ramp, GATEKEEPER, OPERATOR, cadence, ICP, etc. |
| agent_manager.py cleanup | Strip 16 TODO stubs from `core/agent_manager.py` | 1 file | No active Phase 4 imports broken; unused stubs removed |
| YAML frontmatter | Add frontmatter to 8 critical docs | 8 files | `title`, `version`, `last_updated`, `audience`, `tags` |
| ASCII enforcement | Create `scripts/check_ascii.py` + add to `.githooks/pre-commit` | 2 files | Scans `.py` for non-ASCII in production code paths |

**Validation**: Pre-commit suite still passes (502+ tests). No import errors: `python -c "import core; import execution; import dashboard"`.

### Handoff B: Sprint B Structural Improvements (Medium Effort)

**Scope**: Structural tooling and test improvements.

| Task | Description | Files | Acceptance |
|------|-------------|-------|------------|
| Knowledge Index | Create `docs/KNOWLEDGE_INDEX.md` — master index of all 96+ docs | New file | Organized by phase, role, status |
| Unified CLI | Create `cli.py` at project root — subcommands delegating to existing scripts | New file | `deploy`, `validate`, `health`, `canary`, `seed-queue`, `approve`, `smoke-test` |
| Smoke orchestrator | Create `scripts/smoke_all.py` — runs all smoke scripts in sequence | New file | Collects pass/fail from 3+ smoke scripts, outputs JSON summary |
| Cross-env bridge test | Create `tests/test_cross_environment_bridge.py` | New file | Tests `shadow_queue.push()` → `shadow_queue.get_pending()` with correct Redis prefix |
| Dashboard UI validation | Create `scripts/validate_dashboard_ui.py` | New file | HTTP 200 checks, expected HTML elements, API JSON shape validation |
| Doc freshness checker | Create `scripts/check_doc_freshness.py` | New file | Parses frontmatter `last_updated`, warns if stale |

**Validation**: All new scripts executable via `--help`. New tests pass. Pre-commit suite green.

### Handoff C: Sprint C Compound Engineering (Documentation-Heavy)

**Scope**: Documentation, ADRs, compound skills.

| Task | Description | Files | Acceptance |
|------|-------------|-------|------------|
| MCP Server Catalog | Create `docs/MCP_SERVER_CATALOG.md` — catalog all 14 MCP servers | New file | Name, purpose, exposed functions, health check, dependencies |
| ADR backfill | Create `docs/adr/` with 5 ADRs | 6 files | 001-redis, 002-six-stage, 003-tier-scoring, 004-shadow-mode, 005-context-prefix |
| Lesson capture CLI | Create `scripts/capture_lesson.py` + `docs/LESSONS_LEARNED.md` | 2 files | CLI appends dated entries to lessons file |
| Compound skills | Create `.claude/commands/skills/` with 3 compound workflows | 3 files | deploy-and-validate, sprint-close, diagnose-failure |
| Trace diagnosis CLI | Create `scripts/diagnose.py` — takes case_id, aggregates traces + errors | New file | Structured JSON output with trace events, circuit breaker states |

**Validation**: Docs render correctly in markdown. Scripts have `--help`. No broken links.

### Handoff D: Sprint D Deep Integration (Strategic, Higher Risk)

**Scope**: Code-level integration work. Requires deeper codebase understanding.

| Task | Description | Files | Acceptance |
|------|-------------|-------|------------|
| Gateway registry | Create `core/gateway_registry.py` — aggregates 3 gateway health checks | 4 files | `get_all_gateway_health()` returns combined status from LLM, Integration, GHL gateways |
| Compound metrics | Add `/api/compound-metrics` endpoint + dashboard tab | 2 files | Returns test count trend, approval rate, template rankings |
| Legacy test fixes | Fix ~15 remaining legacy test failures | Multiple | Slack MCP (9), Calendar mock (7), PII scoring (2), guardrails API (6) |
| Feedback loop activation | Wire `feedback_loop.py` outcomes into `quality_guard.py` | 5+ files | Phase 5 gate — biggest ROI. Behind `FEEDBACK_LOOP_POLICY_ENABLED` flag. |

**Validation**: Pre-commit suite green. `/api/health` returns 200. No import errors.

### Handoff Priority Recommendation

| Priority | Handoff | Risk | Codex Suitability |
|----------|---------|------|-------------------|
| 1st | **A** (Quick Wins) | Low | Excellent — self-contained, clear specs, easy validation |
| 2nd | **B** (Structural) | Low-Med | Good — new files only, no existing code changes |
| 3rd | **C** (Compound) | Low | Excellent — documentation-heavy, minimal code |
| 4th | **D** (Deep Integration) | Medium | Moderate — requires understanding existing architecture |

---

## 10) Change Log (Most Recent)

- `UNRELEASED` — Sprint D complete: deep integration (2026-03-02):
  - New: `core/gateway_registry.py` — unified health aggregation for 3 API gateways (LLM, Integration, GHL)
  - New: `tests/test_gateway_registry.py` — 15 tests (structure, status computation, graceful failure)
  - New: `tests/test_compound_metrics.py` — 5 tests (pre-commit count, endpoint structure, metrics)
  - New: `tests/test_feedback_integration.py` — 12 tests (approval boost, dynamic openers, feature flag gating)
  - Changed: `dashboard/health_app.py` — `/api/compound-metrics` endpoint + gateway health in `/api/health`
  - Changed: `core/quality_guard.py` — feedback loop integration: GUARD-001 approval boost + GUARD-004 dynamic openers (behind `FEEDBACK_LOOP_POLICY_ENABLED` flag)
  - Changed: `core/feedback_loop.py` — added `get_lead_approval_count()` and `get_latest_policy_delta()` helpers
  - Fixed: 33 legacy test failures across 17 files (calendar dates, guardrails API, PII thresholds, Redis state leakage, Slack mocking, Windows SQLite locks)
- `UNRELEASED` — Sprint B complete: structural improvements (2026-03-02):
  - New: `docs/KNOWLEDGE_INDEX.md` — master doc index (55 active + 15 archived across 12 categories)
  - New: `cli.py` — unified CLI entry point with 12 subcommands delegating to existing scripts
  - New: `scripts/smoke_all.py` — smoke test orchestrator (3 scripts in sequence)
  - New: `scripts/validate_dashboard_ui.py` — dashboard UI endpoint validation (6 checks: login, sales, scorecard, health, ready, runtime deps)
  - New: `scripts/check_doc_freshness.py` — YAML frontmatter staleness detection (7d critical, 30d standard)
  - New: `tests/test_cross_environment_bridge.py` — 12 tests covering cross-env data flow (prefix consistency, fallback, status transitions)
  - Changed: `scripts/smoke_all.py` now includes validate_dashboard_ui.py as 3rd smoke script
  - Changed: `cli.py` now includes `validate-ui` subcommand
- `UNRELEASED` — Sprint C complete: compound engineering enhancements (2026-03-02):
  - New: `docs/MCP_SERVER_CATALOG.md` — full catalog of 15 MCP servers (~98 tools, dependencies, data flow)
  - New: `docs/adr/001-005` — 5 Architecture Decision Records (Redis, pipeline, tiers, shadow mode, prefix)
  - New: `scripts/capture_lesson.py` — CLI for appending lessons to `docs/LESSONS_LEARNED.md`
  - New: `docs/LESSONS_LEARNED.md` — compound knowledge base with 6 initial lessons
  - New: `.claude/commands/skills/` — 3 compound skills (deploy-and-validate, sprint-close, diagnose-failure)
  - New: `scripts/diagnose.py` — trace diagnosis CLI (case_id, correlation_id, breakers, health, errors)
  - Changed: `cli.py` — added `lesson` and `diagnose` subcommands (now 13 total)
- `UNRELEASED` — Sprint A complete: agentic engineering remediation quick wins (2026-03-02):
  - New: `docs/GLOSSARY.md` — 80+ domain terms across 14 categories
  - New: `scripts/check_ascii.py` — ASCII enforcement for production code (staged-only pre-commit)
  - New: `docs/CODEX_HANDOFF_SPRINTS_B_C.md` — full handoff spec for 11 Sprint B+C tasks
  - Changed: `core/agent_manager.py` — 16 TODO stubs removed, dormant header added, emojis purged
  - Changed: YAML frontmatter added to 8 critical docs (CLAUDE.md, task.md, CAIO_IMPLEMENTATION_PLAN.md, CAIO_CLAUDE_MEMORY.md, HOS_EMAIL_REVIEW_GUIDE.md, CONTEXT_HANDOFF.md, DEPLOYMENT_CHECKLIST.md, DEPLOYMENT_GUIDE.md)
  - Changed: `.githooks/pre-commit` — ASCII check step added before test suite
- `UNRELEASED` — Agentic Engineering Audit v1.1 security hardening (2026-03-02):
  - N1: Query-token auth default disabled in production/staging (`dashboard/health_app.py`)
  - N2: Token-free dashboard URLs in Slack notifier (`core/approval_notifier.py`)
  - N3: Session secret strict enforcement in production (`dashboard/health_app.py`)
  - N4: Runtime dependencies auth state enriched (`dashboard/health_app.py`)
  - N6: OpenAPI docs disabled in production/staging (`dashboard/health_app.py`)
  - N7: 5 dormant engine files annotated with STATUS + feature flags
  - New: `docs/DORMANT_ENGINES.md` (dormant engine catalog)
  - New: `scripts/strict_auth_parity_smoke.py` (N1-N7 deployed validation)
  - New: `tests/test_security_hardening_v11.py` (26 tests, all passing)
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
