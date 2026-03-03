---
title: Master Tracker & Autonomy Roadmap
version: "5.3"
last_updated: 2026-03-04
audience: [all-agents, engineers, pto-gtm]
tags: [tracker, sprints, autonomy, go-no-go]
canonical_for: [sprint-tracker, task-status]
---

# CAIO Alpha Swarm — Master Tracker & Autonomy Roadmap

**Last Updated**: 2026-03-04
**Last Commit**: `38562b0` (Agentic Engineering Audit sprints A-D + post-audit housekeeping)
**Plan Version**: v5.3
**Test Suite**: 576 tests passing (34-file pre-commit suite, ~102s)

> **This file is the single source of truth for all current and future work.**
> **Canonical status rule (2026-03-03)**: update live status ONLY in this file; other trackers are historical context unless explicitly regenerated from this file.
> For historical roadmap: `CAIO_IMPLEMENTATION_PLAN.md` (v4.8). For deployment context: `CLAUDE.md`.
> **Operational mode (2026-03-04)**: dev-progress only. Live sends, ramp graduation, and go-live sign-off are paused until N3/N6 closure and post-fix rerun gates are green.

---

## 1. Phase Progress

```
Phase 0: Foundation Lock          [##########] 100%  COMPLETE
Phase 1: Live Pipeline Validation [##########] 100%  COMPLETE  (33+ runs, 10 consecutive 6/6)
Phase 2: Supervised Burn-In       [##########] 100%  COMPLETE
Phase 3: Expand & Harden          [##########] 100%  COMPLETE
Phase 4: Autonomy Graduation      [#########.]  98%  IN PROGRESS (DEV-PROGRESS HOLD) ← YOU ARE HERE
Phase 5: Intelligence & Optimize  [..........]   0%  WAITING (trigger: 2 weeks live send data)
Phase 6: Full Autonomy            [..........]   0%  WAITING (trigger: 30 days live send data)
```

### Phase 4 Sub-Task Breakdown

| Sub-Phase | Status | Notes |
|-----------|--------|-------|
| 4A Instantly Go-Live | COMPLETE | 6 domains, V2 API, 100% warmup health |
| 4B HeyReach LinkedIn | 95% | Infra done, 9/10 bugs resolved. Blocked: HR-05 payload validation + warmup ~Mar 16 |
| 4C OPERATOR Agent | COMPLETE | Unified dispatch (outbound + cadence + revival) |
| 4D Cadence Engine | COMPLETE | 21-day, 8-step Email+LinkedIn sequence |
| 4E Supervised Live Sends | ON HOLD | Dev-progress mode active until N3/N6 closure + rerun gates |
| 4F Monaco Signal Loop | COMPLETE | 21 statuses, webhook-driven |
| 4G Proof & Feedback | COMPLETE | GHLSendProofEngine, webhook + poll fallback |
| 4H Task Routing | 95% | Committed, needs production validation |
| 4I Runtime Reliability | COMPLETE | Circuit breakers, fallbacks, retry |
| 4J TDD Testing | COMPLETE | 576 curated tests (34 pre-commit files) |
| 4K Clay Fallback | COMPLETE | Redis LinkedIn URL correlation |
| 4L Agentic Engineering Audit | COMPLETE | 21 gaps → 4 sprints (A-D), N1-N7 security, feedback loop wired, 576 tests |

### Engineering Sprint History

| Sprint | Scope | Tests | Status |
|--------|-------|-------|--------|
| 1-3 | Core pipeline, enrichment, HeyReach/Instantly | 202 | COMPLETE |
| 4 | HeyReach hardening (12/14 HR findings resolved) | +47 | COMPLETE |
| 5 | Cross-system hardening (XS-01–06, HR-12) | +46 | COMPLETE |
| 6 | Observability, legacy test debt, dev-team skill | +144 | COMPLETE |
| 7 | HeyReach B6+B7, cadence follow-up, reply classification | +63 | COMPLETE |
| 8 (A) | Agentic audit: security hardening + Sprint A quick wins | +30 | COMPLETE |
| 8 (B) | Agentic audit: structural improvements (knowledge index, CLI, smoke, cross-env test, UI validation, doc freshness) | +12 | COMPLETE |
| 8 (C) | Agentic audit: compound engineering (MCP catalog, ADRs, lessons learned, compound skills, diagnosis CLI) | +0 | COMPLETE |
| 8 (D) | Agentic audit: deep integration (gateway registry, compound metrics, 33 legacy test fixes, feedback loop activation) | +32 | COMPLETE |

---

## 2. Critical Path to Full Autonomy

### Post-Audit Execution Window (2026-03-04)

| Phase | Status | Evidence / Remaining Blocker |
|-------|--------|------------------------------|
| Phase 0: Canonicalization | DONE | `task.md` enforced as sole live tracker; `docs/CAIO_TASK_TRACKER.md` + `CAIO_IMPLEMENTATION_PLAN.md` treated as historical/roadmap |
| Phase 1: Runtime/Auth Gate | PARTIAL | Staging+production matrices executed; remaining parity blockers are N3 + N6 and must be closed before live operations |
| Phase 2: PTO Inputs Closure | IN_PROGRESS (DEV ONLY) | Runtime env mapping and isolation verified; complete `SESSION_SECRET_KEY` explicit detection + docs-disable verification + rerun evidence |
| Phase 3: Supervised Proof + 3-Day Ramp | ON HOLD | Blocked until Phase 1 and Phase 2 are green (no N3/N6 failures) |
| Phase 4: LinkedIn Readiness | BLOCKED | HR-05 still requires real HeyReach webhook payload capture/validation (`python scripts/inspect_heyreach_payloads.py --print-sample`) |
| Phase 5: Doc Drift Cleanup | IN_PROGRESS | Numeric/status drift reconciliation started across 4 source docs |

### Phase 1 Validation Snapshot (Production, 2026-03-03)

- `strict_auth_parity_smoke.py`: **FAIL (8/12)**  
  - PASS: N1, N2, N4, N5  
  - FAIL: N3 (`auth.session_secret_explicit=false`), N6 (`/docs`, `/redoc`, `/openapi.json` return 200)
- `strict_auth_parity_smoke.py` (staging): **FAIL (8/12)** with the same N3/N6 failures
- `webhook_strict_smoke.py --require-heyreach-hard-auth`: **PASS**
- `endpoint_auth_smoke.py --expect-query-token-enabled false`: **PASS**
- `webhook_strict_smoke_matrix.py --require-heyreach-hard-auth`: **PASS** (staging + production)
- `deployed_full_smoke_matrix.py --expect-query-token-enabled false --require-heyreach-hard-auth`: **PASS** (staging + production)
- `deployed_full_smoke_checklist.py --expect-query-token-enabled false --require-heyreach-hard-auth`: **FAIL**
  - Legacy result before checker update; matrix now passes with login-gated `/sales` handling
- Full evidence log: `docs/POST_AUDIT_EXECUTION_LOG.md`
- Latest manual verification (2026-03-04): `session_secret_explicit=false` in staging+production; `/docs`, `/redoc`, `/openapi.json` returned `302` in staging+production (still failing N3/N6 until redeploy + env correction).

### Overview

```
TODAY        Day 1-3        Day 3         ~Mar 10        ~Mar 16+
  |            |              |              |              |
  v            v              v              v              v
HoS Review → Ramp Supervision → Graduate → HR Hardening → LinkedIn Live
(YOU)        (YOU + System)    (Config)    (AI)           (Operations)
  |                                         |
  |   Unlocks email autonomy (25/day)       |   Unlocks multi-channel
  |   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~          |   ~~~~~~~~~~~~~~~~~~~~~
```

### Step 1: Runtime/Auth Closure — USER + ENGINEERING (NOW)

**This is the current gate blocking live operations.**

1. Re-enter `SESSION_SECRET_KEY` in staging and production as plain single-line values.
2. Force redeploy staging then production.
3. Validate `/api/runtime/dependencies` shows:
   - `auth.environment=staging|production` correctly
   - `auth.session_secret_explicit=true`
   - `auth.session_secret_source=SESSION_SECRET_KEY`

**What to check on each email:**
- Subject line: Not deceptive, personalized to recipient
- Body: Has unsubscribe footer (`Reply STOP`), physical address, clear CTA
- Recipient: Not a competitor, not an existing customer, valid email format
- Tier: Must be tier_1 (VP+/C-suite decision makers)

**Reference**: `docs/HOS_EMAIL_REVIEW_GUIDE.md`

### Step 2: Docs Exposure Closure + Full Reruns — USER + ENGINEERING

1. Deploy/verify production-like docs disable logic.
2. Confirm `/docs`, `/redoc`, `/openapi.json` return `404` on staging and production.
3. Run gate reruns:
   - `scripts/endpoint_auth_smoke.py`
   - `scripts/strict_auth_parity_smoke.py`
   - `scripts/webhook_strict_smoke_matrix.py`
   - `scripts/deployed_full_smoke_matrix.py`
4. Keep live sends paused until all reruns are green.

**Graduation criteria (all must pass):**
- [ ] 3 consecutive clean supervised days (no gate failures, no unresolved sends)
- [ ] Bounce rate < 5% across all ramp days
- [ ] No EMERGENCY_STOP activations during ramp
- [ ] HoS quality metrics stable (rejection ratio trending down)

### Step 3: Ramp Graduation — CONFIG CHANGE (Day 3)

Once criteria met, update `config/production.json`:
```json
"operator.ramp.enabled": false
```
This unlocks: 25 emails/day, all tiers, cadence auto-run, revival scanner.

**Recommendation**: Keep `gatekeeper_required: true` for 2 more weeks post-graduation.

### Step 4: HeyReach Hardening — ENGINEERING (Before Mar 16)

See Section 5 (Sprint 7) for full task breakdown. Must complete before LinkedIn warmup finishes.

### Step 5: LinkedIn Go-Live — OPERATIONS (~Mar 16+)

After HeyReach hardening AND LinkedIn warmup complete:
1. Activate HeyReach campaigns in UI (currently DRAFT status)
2. LinkedIn ramp: 5/day warmup → 20/day full capacity
3. Multi-channel cadence fully operational (email + LinkedIn, 21-day sequence)

---

## 3. Module Readiness Assessment

| Module | File | Status | Blockers |
|--------|------|--------|----------|
| Dashboard & HoS Review | `dashboard/health_app.py` (~3150 lines) | READY | Login gate deployed (`5023f6b`) |
| OPERATOR Dispatch | `execution/operator_outbound.py` (1936 lines) | READY | 3 clean ramp days |
| Cadence Engine | `execution/cadence_engine.py` (682 lines) | READY | None — auto-runs daily |
| Shadow Queue (Redis) | `core/shadow_queue.py` (263 lines) | READY | None |
| GHL Proof Engine | `core/ghl_send_proof.py` | READY | None — auto-triggers on approve |
| Lead Signal State Machine | `core/lead_signals.py` (21 statuses) | READY | None — webhook-driven |
| Instantly Dispatcher | `execution/instantly_dispatcher.py` | READY | None — 6 domains warmed |
| HeyReach Dispatcher | `execution/heyreach_dispatcher.py` (900+ lines) | 95% READY | 1 remaining bug (HR-05 — needs real payload) |
| Enrichment Waterfall | `execution/enricher_waterfall.py` | READY | None — Apollo + BC + Clay |
| Queue Seed System | `core/seed_queue.py` + `/api/admin/seed_queue` | READY | 15 personas, 11 templates, dashboard UI (`7397f27`) |
| Segmentor/ICP Scoring | `execution/segmentor_classify.py` | READY | None |

---

## 4. Required Inputs From You

### Immediate (This Week)

| Input | Why | How |
|-------|-----|-----|
| **Review 5+ shadow emails** | Unblocks first live dispatch | Dashboard Email Queue tab |
| **Confirm daily supervision schedule** | Need 3 supervised days for ramp graduation | 15:00 EST recommended |
| **Provide staging dashboard + webhook bearer tokens for matrix gate** | Required to complete staging+production same-window auth closure | Secure handoff to engineering runbook |

### Before LinkedIn Ramp (~Mar 10)

| Input | Why | How |
|-------|-----|-----|
| **Confirm `HEYREACH_BEARER_TOKEN` in staging and production** | Hard-auth parity must be green in both envs | Railway dashboard → env vars |
| **Confirm HeyReach webhook schema** | HR-05: requires real payload evidence | Trigger a real HeyReach event, then run `python scripts/inspect_heyreach_payloads.py --print-sample` |
| **Verify campaign IDs still valid** | 334314 / 334364 / 334381 in config | HeyReach UI |
| **Confirm LinkedIn warmup progress** | Determines hardening deadline | HeyReach dashboard |

### Decisions Needed

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Keep GATEKEEPER after ramp? | (A) Remove after 3 days (B) Keep 2 more weeks | **B** — safety net while scaling |
| HeyReach hardening timing | (A) Start now (B) Wait until Mar 10 | **A** — less time pressure |
| Compliance documentation | (A) Create formal doc (B) Inline checks sufficient | **A** — needed before scaling past 25/day |
| KPI alerting | (A) Build now (B) Manual monitoring during ramp | **B** now, **A** before Phase 5 |

---

## 5. Sprint 7: HeyReach Hardening + Autonomy Prep

**Goal**: Fix 7 critical HeyReach bugs before LinkedIn ramp (~Mar 16). Parallel: docs refresh.

### Track A: Operational (YOU)

| # | Task | When | Effort |
|---|------|------|--------|
| A1 | HoS email review (5+ emails) | Day 0 | 15-30 min |
| A2 | Daily supervision ritual | Days 1-3 | 10 min/day |
| A3 | Set `operator.ramp.enabled: false` after graduation | Day 3 | Config change |
| A4 | Set `HEYREACH_BEARER_TOKEN` on Railway | Before Mar 10 | 5 min |
| A5 | Capture real HeyReach webhook payload (for HR-05) | Before Mar 10 | 15 min |

### Track B: Engineering (AI) — 3 remaining (7 resolved in prior sprints)

| # | Task | IDs | Files | Est. | Status |
|---|------|-----|-------|------|--------|
| ~~B1~~ | ~~Retry + circuit breaker + error discrimination~~ | HR-04, HR-08, HR-10 | `heyreach_dispatcher.py` | — | DONE (exponential backoff, CB registered, handlers split) |
| ~~B2~~ | ~~URL-encode query params~~ | HR-01 | `heyreach_dispatcher.py` | — | DONE (`url_quote` on all params) |
| ~~B3~~ | ~~Distributed LinkedIn ceiling~~ | HR-03 | `heyreach_dispatcher.py` | — | DONE (`LinkedInDailyCeiling` Redis class) |
| ~~B4~~ | ~~Shadow file write race fix~~ | HR-02 | `heyreach_dispatcher.py` | — | DONE (`_atomic_json_write`) |
| B5 | Webhook payload schema validation | HR-05 | `heyreach_webhook.py` | 1h | **BLOCKED** — needs real payload (user task A5) |
| ~~B6~~ | ~~Follow-up flag consumer (cadence integration)~~ | HR-07 | `cadence_engine.py` | — | DONE (`9606327`) — `process_linkedin_followups()` reads flags, accelerates next_step_due |
| ~~B7~~ | ~~Reply classification routing~~ | HR-06 | `heyreach_webhook.py` | — | DONE (`9606327`) — keyword classifier, Slack HOT LEAD alert, unsubscribe routing |
| ~~B8~~ | ~~Partial success detection~~ | HR-09 | `heyreach_dispatcher.py` | — | DONE (3 field variants checked) |
| ~~B9~~ | ~~LinkedIn URL format validation~~ | HR-16 | `heyreach_dispatcher.py` | — | DONE (regex `_LINKEDIN_PROFILE_RE`) |
| ~~B10~~ | ~~Verify unsigned allowlist~~ | HR-11 | Railway env | — | DONE |

### Track C: Documentation (AI)

| # | Task | Files | Est. |
|---|------|-------|------|
| ~~C1~~ | ~~CLAUDE.md refresh (deploy hash, audit results, Sprint 8)~~ | `CLAUDE.md` | DONE (v4.8) |
| ~~C2~~ | ~~Create compliance doc (CAN-SPAM, GDPR, LinkedIn ToS)~~ | `docs/COMPLIANCE.md` | DONE |
| ~~C3~~ | ~~Create incident response playbook~~ | `docs/INCIDENT_RESPONSE.md` | DONE |

### Track D: Autonomy Prep + Nice-to-Have

| # | Task | Priority | Trigger |
|---|------|----------|---------|
| D1 | KPI alerting system (`/api/alerts` endpoint + `core/kpi_monitor.py`) | HIGH | Before Phase 5 |
| D2 | EMERGENCY_STOP dashboard toggle (GET status, POST activate) | MEDIUM | Before removing GATEKEEPER |
| D3 | Railway deployment playbook (`docs/DEPLOYMENT_RAILWAY.md`) | MEDIUM | Before next deploy |
| D4 | Replace `datetime.utcnow()` → timezone-aware UTC (partial) | LOW | Ongoing cleanup |
| D5 | Remove stale `PROXYCURL_API_KEY` references | LOW | Cleanup |
| D6 | **Wire feedback loops for full autonomy** | **CRITICAL** | Before Phase 5 |

#### D6: Feedback Loop Wiring (PARTIALLY WIRED — Sprint D-4)

**Status**: `feedback_loop.py` → `quality_guard.py` integration COMPLETE (Sprint D-4). Remaining 5 engines deferred to Phase 5.

**What's wired** (gated behind `FEEDBACK_LOOP_POLICY_ENABLED`, default: false):
- GUARD-001 boost: leads approved 3+ times bypass rejection block
- GUARD-004 extension: dynamically bans openers from feedback-derived policy deltas (count >= 2)
- Tests: `tests/test_feedback_integration.py` (12 tests)

**Remaining engines** (deferred to Phase 5 — need 2+ weeks of live send data):

| Engine | File | What's Missing |
|--------|------|----------------|
| CRAFTER | `execution/crafter_campaign.py` | Template selection based on feedback |
| Self-Annealing | `core/self_annealing_engine.py` | Event triggers for RETRIEVE-JUDGE-DISTILL |
| RL Engine | `execution/rl_engine.py` | Reward signals from send/open/reply webhooks |
| A/B Testing | `core/ab_test_engine.py` | Auto-trigger on reply rate drops |
| Self-Learning ICP | `core/self_learning_icp.py` | GHL deal outcome webhook hookup |

**To close remaining loops (Phase 5)**:
1. Wire send/open/reply/bounce webhook events → RL engine `update()` calls
2. Apply policy deltas → CRAFTER template selection (avoid rejected angles)
3. Auto-create A/B tests when reply rate drops below threshold
4. GHL deal outcome webhook → ICP weight recalibration

---

## 6. Completed Sprints (Archive)

### Sprint 5: Cross-System Hardening — COMPLETE (7/7)

| Task | IDs | Status |
|------|-----|--------|
| ~~OPERATOR partial dispatch detection~~ | XS-01 | DONE — `_check_partial_dispatch()`, 11 tests |
| ~~Instantly webhook signature verification~~ | XS-02 | DONE — already enforced on all 4 endpoints |
| ~~Instantly ceiling to Redis~~ | XS-03 | DONE — INCRBY + atomic writes, 12 tests |
| ~~Cadence step idempotency keys~~ | XS-05 | DONE — duplicate check, 7 tests |
| ~~Dashboard GHL send transaction~~ | XS-06 | DONE — atomic write + immediate persist, 8 tests |
| ~~OPERATOR locking improvements~~ | XS-04 | DONE — `verify_operator_lock` + atomic file writes, 13 tests |
| ~~Email validation before signal loop~~ | HR-12 | DONE — warning on empty email, 2 tests |

### Sprint 6: Observability + Quality — COMPLETE (6/7)

| Task | IDs | Status |
|------|-----|--------|
| ~~Config schema validation~~ | HR-18 | DONE — `_validate_config()`, 4 tests |
| ~~Enricher timeout enforcement~~ | XS-14 | DONE — `_run_with_timeout()`, 7 tests |
| ~~Dispatch log atomic writes~~ | HR-17 | DONE — JSONL atomic append, 3 tests |
| ~~Legacy test debt cleanup~~ | — | DONE — 439 tests, fixed 7 files, emoji purge |
| ~~Dev team sub-agent skill~~ | — | DONE — 3 agents (FDE, PM, PTO) + `/dev-team` command |
| ~~Slack alert for unknown events~~ | HR-21 | DONE in Sprint 4 |
| Mock HeyReach integration tests | — | DEFERRED — existing coverage sufficient |

**Legacy test cleanup details:**
- Triaged all 57 non-pre-commit test files (~1500 tests)
- Fixed: `test_operator_dedup_and_send_path.py` (status assertion), `test_unified_integration.py` (4-value unpack), `test_unified_guardrails.py` (agent count), `test_day3_4_framework.py` (emojis)
- Fixed production code: `gatekeeper_queue.py` (24 emojis → ASCII, Windows cp1252 crash)
- Promoted 6 files to pre-commit: dedup, ramp, webhook sig, state store, health monitor, gatekeeper
- Remaining ~15 failures: Slack MCP API (9), Calendar mock mode (7), PII risk scoring (2), guardrails API evolution (6)

---

## 7. Open Audit Findings (Unresolved)

### HeyReach — 1 Remaining (HR-05 PARTIAL — blocked on user)

| ID | Severity | Issue | Sprint 7 Task | Status |
|----|----------|-------|---------------|--------|
| HR-05 | CRITICAL | Webhook payload fields unvalidated | B5 | PARTIAL — discovery harness built, needs real payload from user |
| ~~HR-06~~ | ~~CRITICAL~~ | ~~Reply classification TODO~~ | B7 | RESOLVED (`9606327`) — keyword classifier + Slack alerts + signal loop routing |
| ~~HR-07~~ | ~~CRITICAL~~ | ~~Follow-up flags unread~~ | B6 | RESOLVED (`9606327`) — `process_linkedin_followups()` in cadence engine |

**Resolved (19/22):** HR-01 (url_quote on all params), HR-02 (atomic_json_write), HR-03 (Redis LinkedInDailyCeiling), HR-04 (exponential backoff + retryable status codes), HR-08 (split into TimeoutError/ClientError/Exception handlers), HR-09 (partial success detection with 3 field variants), HR-10 (circuit breaker registered in __init__), HR-11 (auth enforced), HR-12 (email validation), HR-13 (timeout), HR-14 (JSON fallback), HR-15, HR-16 (LinkedIn URL regex), HR-17 (atomic log), HR-18 (config validation), HR-19, HR-20, HR-21 (Slack alert), HR-22.

### Cross-System — 6 Remaining (0 CRITICAL, 0 HIGH, 6 MEDIUM/LOW)

| ID | Severity | Issue | Status |
|----|----------|-------|--------|
| XS-07 | MEDIUM | Instantly no retry/timeout | Mitigated by ramp mode |
| XS-08 | MEDIUM | Instantly state file race | Mitigated by Redis cutover |
| XS-09 | MEDIUM | Batch expiry not enforced | LOW risk during ramp |
| XS-10 | MEDIUM | Cadence auto-enroll silent failure | Monitoring catches this |
| XS-11 | MEDIUM | Exit condition race | Edge case, low frequency |
| XS-12 | MEDIUM | Double-approve race | Single HoS reviewer mitigates |

---

## 8. Security & Production Risk Register

### P0 (Blockers before full autonomy)

- [x] **Webhook strict enforcement** — `WEBHOOK_SIGNATURE_REQUIRED=true` validated
- [ ] **HeyReach auth** — `HEYREACH_UNSIGNED_ALLOWLIST` must be `false`, `HEYREACH_BEARER_TOKEN` must be set on Railway
- [x] **Dashboard auth** — Login page gate with signed cookie sessions (commit `5023f6b`). Token never in URL.

### P1 (Before scaling past 25/day)

- [x] **State-store cutover** — `STATE_BACKEND=redis`, file fallback disabled
- [x] **CORS policy** — Explicit methods/headers, smoke-validated
- [x] **Compliance documentation** — `docs/COMPLIANCE.md` created (CAN-SPAM, GDPR, LinkedIn ToS)
- [ ] **KPI monitoring** — No automated alerting for bounce%, reply%, unsub% thresholds

### P2 (Maintenance)

- [x] FastAPI lifespan migration (from deprecated `on_event`)
- [ ] Replace `datetime.utcnow()` with timezone-aware UTC (partial)
- [ ] Remove stale `PROXYCURL_API_KEY` references
- [x] CLAUDE.md deployed hash updated to `4226583` (v4.8, audit complete)

### Emergency Controls

**EMERGENCY_STOP** is integrated into ALL dispatch paths:
- `execution/operator_outbound.py` (outbound, cadence, revival)
- `execution/instantly_dispatcher.py`
- `execution/heyreach_dispatcher.py`
- `dashboard/health_app.py` (approval processing)
- `core/ghl_execution_gateway.py`

**Activation**: Set `EMERGENCY_STOP=true` on Railway env vars. No dashboard UI yet (Sprint 7 D2).

---

## 9. Phase 5-6 Roadmap (Post-Graduation)

### Phase 5: Intelligence & Optimization

| Task | Description | Trigger | Dependencies |
|------|-------------|---------|-------------|
| 5A: ICP Recalibration | Tune scoring model with reply/meeting data | 50+ replies collected | Live send data |
| 5B: A/B Testing | Subject line + body variants, performance tracking | 100+ sends/day | Stable KPIs |
| 5C: Infrastructure Scale | Scale to 500+ emails/day, domain rotation | Approaching 250/day | Domain health data |

### Phase 6: Full Autonomy

| Task | Description | Trigger | Dependencies |
|------|-------------|---------|-------------|
| 6A: Unsupervised Sends | Remove GATEKEEPER gate entirely | Stable KPIs for 2 weeks | Phase 5A complete |
| 6B: Closed-Loop Feedback | Reply classification → pipeline signal (hot/warm/cold) | Reply data available | Phase 5A complete |
| 6C: Advanced Targeting | Job change detection, account-based personalization | ICP model stabilized | Phase 5B complete |

---

## 10. Graduation Checklist

All must be TRUE before declaring full email autonomy:

- [ ] **HoS has reviewed and approved 5+ emails** (Step 1)
- [ ] **3 consecutive clean ramp days completed** (Step 2)
- [ ] **Bounce rate < 5% across all ramp days**
- [ ] **No EMERGENCY_STOP activations during ramp**
- [ ] **`operator.ramp.enabled` set to `false`** (config change)
- [ ] **CLAUDE.md updated with current deploy hash**
- [x] Webhook strict mode enabled (`WEBHOOK_SIGNATURE_REQUIRED=true`)
- [x] Login page + cookie session auth (token never in URL)
- [x] Redis-only state cutover complete
- [x] 576 pre-commit tests passing (34 files)
- [x] Engineering Sprints 1-8(D) complete (Agentic Engineering Audit fully remediated)

All must be TRUE before declaring multi-channel (email + LinkedIn) autonomy:

- [ ] All email autonomy items above
- [x] **HeyReach HR-06, HR-07 bugs fixed** (Sprint 7 B6+B7 — `9606327`)
- [ ] **HeyReach HR-05 schema validation** (blocked — needs real webhook payload)
- [ ] **LinkedIn warmup complete** (~Mar 16)
- [ ] **`HEYREACH_BEARER_TOKEN` set on Railway**
- [ ] **`HEYREACH_UNSIGNED_ALLOWLIST=false` on Railway**
- [ ] **HeyReach campaigns activated in UI** (currently DRAFT)
- [ ] **Multi-channel cadence validated** (connection → warm email trigger)

---

## 11. Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| HeyReach bugs hit during LinkedIn ramp | LOW | 1 remaining (HR-05), 9 resolved | Sprint 7 Track B before Mar 16 |
| Bounce rate > 5% during ramp | MEDIUM | Ramp days reset, domain reputation at risk | 4-layer deliverability guards, 3/domain/batch |
| No HoS review this week | LOW | Entire pipeline stalled | Email queue + Slack reminder |
| Railway env var mismatch | LOW | Shadow emails invisible on dashboard | Pre-flight checklist enforces |
| LinkedIn warmup slower than expected | MEDIUM | Delays multi-channel go-live | Email-only autonomy unaffected |

---

## 12. Configuration Quick-Reference

### Current Production Settings (`config/production.json`)

| Setting | Current Value | After Graduation |
|---------|--------------|-----------------|
| `shadow_mode` | `true` | `true` (emails still logged) |
| `gatekeeper_required` | `true` | `true` (keep 2 weeks, then `false`) |
| `operator.ramp.enabled` | `true` | **`false`** |
| `operator.ramp.email_daily_limit_override` | `5` | N/A (ramp disabled) |
| `operator.outbound.email_daily_limit` | `25` | `25` (active once ramp off) |
| `operator.outbound.linkedin_warmup_daily_limit` | `5` | `5` → `20` (after warmup) |
| `WEBHOOK_SIGNATURE_REQUIRED` | `true` | `true` |
| `STATE_BACKEND` | `redis` | `redis` |
| `EMERGENCY_STOP` | `false` | `false` |

### Instantly Cold Outreach (6 Domains)

```
chris.d@chiefaiofficerai.com
chris.d@chiefaiofficerconsulting.com
chris.d@chiefaiofficerguide.com
chris.d@chiefaiofficerlabs.com
chris.d@chiefaiofficerresources.com
chris.d@chiefaiofficersolutions.com
```
Rotation: round-robin | Warmup: complete | Health: 100%

### HeyReach Campaigns (DRAFT — Awaiting Activation)

| Campaign | ID | Tier | Sequence |
|----------|----|------|----------|
| CAIO Tier 1 — VP+ Decision Makers | 334314 | tier_1 | Connect → Msg (1d) → Follow-up (7d) |
| CAIO Tier 2 — Directors & Managers | 334364 | tier_2 | Connect → Msg (1d) → End |
| CAIO Tier 3 — Connection Only | 334381 | tier_3 | Connect → End |

---

## 13. Operational Ritual (Daily Supervised Window)

**Schedule:** 15:00 EST

### Pre-flight (must pass)
```powershell
python scripts/deployed_full_smoke_checklist.py --base-url https://caio-swarm-dashboard-production.up.railway.app --token <DASHBOARD_AUTH_TOKEN>
python scripts/trace_outbound_ghl_queue.py --base-url https://caio-swarm-dashboard-production.up.railway.app --token <DASHBOARD_AUTH_TOKEN>
```

### Supervised generation
```powershell
echo yes | python execution/run_pipeline.py --mode production --source "wpromote" --limit 2
```

### HoS review
- Review only fresh Tier_1 in `/sales`
- Reject requires structured tag + reason
- Approve exactly one card for verification when needed

### Post-approval proof
- API response must be: `Email sent via GHL`
- Verify the message in GHL conversation thread for that contact

---

## 14. Key Files Reference

| Purpose | File | Notes |
|---------|------|-------|
| Dashboard API | `dashboard/health_app.py` | 2820 lines, 50+ endpoints |
| OPERATOR Agent | `execution/operator_outbound.py` | 1936 lines, 3 dispatch motions |
| HeyReach Dispatcher | `execution/heyreach_dispatcher.py` | 900+ lines, 1 bug remaining (HR-05) |
| HeyReach Webhooks | `webhooks/heyreach_webhook.py` | 388 lines |
| Instantly Dispatcher | `execution/instantly_dispatcher.py` | V2 API, 6 domains |
| Cadence Engine | `execution/cadence_engine.py` | 682 lines, 21-day 8-step |
| Shadow Queue | `core/shadow_queue.py` | 263 lines, Redis bridge |
| Lead Signals | `core/lead_signals.py` | 21-status state machine |
| Proof Engine | `core/ghl_send_proof.py` | Webhook + poll fallback |
| Circuit Breaker | `core/circuit_breaker.py` | Per-service registry |
| State Store | `core/state_store.py` | Redis backend, atomic writes |
| Alerts | `core/alerts.py` | Slack webhook, 3 severity levels |
| Compliance | `core/compliance.py` | CAN-SPAM enforcement |
| Production Config | `config/production.json` | All feature flags + limits |
| Pre-commit Hook | `.githooks/pre-commit` | 34 files, 576 tests, ~102s |
| Implementation Plan | `CAIO_IMPLEMENTATION_PLAN.md` | v4.8, full historical roadmap |
| HoS Review Guide | `docs/HOS_EMAIL_REVIEW_GUIDE.md` | Email approval criteria |
| Dev Team Skill | `.claude/commands/dev-team.md` | 3-pass code review |

---

## 15. What NOT To Do

1. **No Phase 5 optimization** — requires 2+ weeks of live send data. No ICP recalibration, A/B testing, or analytics.
2. **No safety setting changes** — `shadow_mode`, `gatekeeper_required`, and ramp stay until explicit graduation.
3. **No new agents** — 6 consolidated agents. The 12→6 consolidation was intentional.
4. **No CRM rebuild** — GHL works. Decisioned out in implementation plan.
5. **No enrichment provider changes** — Apollo + BetterContact + Clay waterfall is stable.
6. **No LinkedIn dispatch** — until HR-01–07 are fixed AND warmup completes (~Mar 16).

---

## 16. Change Log

| Commit | Date | Description |
|--------|------|-------------|
| `38562b0` | 2026-03-03 | Agentic audit Sprints A-D + post-audit housekeeping merged. Post-audit execution started: production hard-auth smoke run, canonical tracker enforcement, cross-doc drift cleanup initiated. |
| `9606327` | 2026-03-02 | Sprint 7 B6+B7: cadence follow-up consumer (HR-07, 9 tests) + reply classification routing (HR-06, 15 tests). task.md + CLAUDE.md refreshed. 498 tests, 29 files. Deployed to Railway. |
| `7397f27` | 2026-03-02 | Queue Seed System: dashboard-triggered training email generation, OPERATOR synthetic guard, 14 new tests. 475 tests, 28 files. Deployed to Railway. |
| `5023f6b` | 2026-03-01 | Dashboard login gate (cookie sessions) + Sprint 4-6 engineering hardening. 461 tests, 27 files. Deployed to Railway. |
| `8176c27` | 2026-02-27 | Phase 4 bulk commit: 7 modules, 14 test files, 5 agents, pre-commit hook. Deployed to Railway. |
| `4992d69` | 2026-02-27 | FastAPI lifespan migration, timezone-aware UTC, smoke matrix hard-auth. |
| `21993cd` | 2026-02-26 | CORS hardening: explicit methods/headers; staging + production validated. |
| `f1cb70a` | 2026-02-26 | Smoke hardening: header-token runtime auth path. |
| `d9b8c63` | 2026-02-25 | Tier_1 personalization normalization. |
| `00bb12e` | 2026-02-24 | Query-token gate + header-priority auth. |
| `5eaffac` | 2026-02-23 | HeyReach strict auth hardening + regression tests. |
| `d9ade64` | 2026-02-22 | Structured rejection tags + clean-day ramp gating. |

**All Sprint 5-6 work committed in `5023f6b`** — XS-01–06 fixes, HR-12/17/18 fixes, XS-14, legacy test cleanup, emoji purge, dev-team skill, login gate.

---

*Last updated: 2026-03-03 | Next review: After staging+production auth matrix closure and first supervised proof cycle*
