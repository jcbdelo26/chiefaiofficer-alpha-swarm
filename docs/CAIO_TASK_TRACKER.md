# CAIO Alpha Swarm — Unified Task Tracker

**Last Updated**: 2026-02-23
**Source**: `CAIO_IMPLEMENTATION_PLAN.md` (v4.5) + Production Cutover Results
**Quick Nav**: **[Weekly Focus (YOU ARE HERE)](#weekly-focus-week-of-2026-02-23-pto-gtm-execution)** | [Phase 0](#phase-0-foundation-lock--complete) | [Phase 1](#phase-1-live-pipeline-validation--complete) | [Phase 2](#phase-2-supervised-burn-in--complete) | [Phase 3](#phase-3-expand--harden--complete) | [Phase 4](#phase-4-autonomy-graduation--in-progress) | [Phase 5](#phase-5-optimize--scale-post-autonomy)

---

## Weekly Focus (Week of 2026-02-23): PTO/GTM Execution

This section is the operating tracker for this week and aligns with the supervised go-live model.
Primary runbook: `docs/PTO_GTM_SAFE_TRAINING_EVAL_REGIMEN.md`.

### Patch + Code Status (this week)

- [x] Structured rejection taxonomy implemented in backend (`/api/emails/{id}/reject` requires `rejection_tag`).
- [x] Structured rejection UI implemented (`/sales` reject flow requires selecting a rejection tag).
- [x] Rejection taxonomy API added (`GET /api/rejection-tags`) and UI now loads tags from backend to prevent drift.
- [x] Ramp logic upgraded to clean-days mode in OPERATOR (`mode: clean_days`, `clean_days_required: 3`).
- [x] Deterministic stale-card filtering active in pending queue (`stale_gt_72h` exclusion path).
- [x] Targeted regression tests pass locally:
  - `tests/test_runtime_determinism_flows.py`
  - `tests/test_operator_ramp_logic.py`
- [ ] Deploy current patch set to Railway.
- [ ] Run post-deploy smoke matrix on staging + production.
- [ ] Run supervised live cycle and capture HoS approval/rejection tags.

### Ramp Logic (recommended and now coded)

- Mode: `clean_days`
- Graduation rule: ramp remains active until **3 clean supervised LIVE days** are recorded.
- Clean day definition: live run, no pending-approval hold, no errors, and at least one actual dispatch.
- Until graduation: keep `tier_1` filter and conservative daily cap.

### Approval SLA (operational suggestion for PTO/GTM + HoS)

- New pending card first review SLA: **within 30 minutes** during active send windows.
- Final decision SLA (approve/reject with tag): **within 2 hours**.
- If SLA breached: card remains pending but is included in queue diagnostics and should be reviewed before next live cycle.

### Operational Ownership (confirmed)

- Daily supervised review window: **15:00 EST**.
- Daily HoS approver owner: **PTO (you)**.
- SLA owner for unresolved pending cards: **PTO (you)**.
- Escalation channel for smoke/gate failures: **Slack**.

### Stale Card Policy (best-fit default)

- Cards older than `PENDING_QUEUE_MAX_AGE_HOURS` (default 72h) are auto-excluded from actionable queue.
- Use structured rejection tag `queue_hygiene_non_actionable` when cleaning non-actionable queue items.
- Run hygiene cleanup once before each supervised live cycle when drift/noise appears.

### PTO/GTM Role Clarity

- You are the go/no-go owner for supervised live cycles.
- HoS is quality approver for messaging.
- Engineering/Codex owns deterministic controls, tests, and regression gates.

---

## Progress Overview

```
Phase 0: Foundation Lock          [##########] 100%  COMPLETE
Phase 1: Live Pipeline Validation [##########] 100%  COMPLETE
Phase 2: Supervised Burn-In       [##########] 100%  COMPLETE
Phase 3: Expand & Harden          [##########] 100%  COMPLETE
Phase 4: Autonomy Graduation      [#########.]  98%  <<< YOU ARE HERE
Phase 5: Optimize & Scale         [----------]   0%  FUTURE
```

**Autonomy Score**: ~98/100
**Production Runs**: 33+ (22 fully clean, last 10 consecutive 6/6 PASS)
**Monthly Spend**: ~$662/mo (Clay $499 + Apollo $49 + Railway $5 + Instantly $30 + HeyReach $79)
**Latest Deployed Commit**: `0f0e0a9` (2026-02-19) — Compliance footer fix + Dashboard v3.0 + P0 checks

---

## Phase 0: Foundation Lock — COMPLETE

All core infrastructure deployed and validated. Nothing to do here.

<details>
<summary>Click to expand completed tasks</summary>

- [x] 12-agent architecture (Queen + 11 agents) — all instantiated
- [x] 6-stage pipeline (scrape/enrich/segment/craft/approve/send) — `execution/run_pipeline.py`
- [x] FastAPI dashboard on port 8080 — `dashboard/health_app.py`
- [x] Redis (Upstash) integration — 62ms from Railway
- [x] Inngest event-driven functions — 5 functions mounted (incl. daily_decay_detection)
- [x] Railway deployment — auto-deploy on git push
- [x] Safety controls (shadow mode, EMERGENCY_STOP) — `config/production.json`
- [x] Gatekeeper approve/reject/edit flows — full audit trail in `.hive-mind/audit/`
- [x] Circuit breaker system — `core/circuit_breaker.py`
- [x] Context zone monitoring (SMART/CAUTION/DUMB/CRITICAL)

</details>

---

## Phase 1: Live Pipeline Validation — COMPLETE

Sandbox pipeline validated end-to-end (3 consecutive clean runs, 0 errors).

<details>
<summary>Click to expand completed tasks</summary>

- [x] Pipeline run: `competitor_gong` — 5 leads, 6/6 PASS, 7ms
- [x] Pipeline run: `event_saastr` — 5 leads, 6/6 PASS, 7ms
- [x] Pipeline run: `default` — 10 leads, 6/6 PASS, 9ms

</details>

---

## Phase 2: Supervised Burn-In — COMPLETE

Production pipeline validated with real Apollo data. All critical blockers resolved.

<details>
<summary>Click to expand completed tasks</summary>

### Blockers Resolved
- [x] LinkedIn Scraper 403 -> replaced with Apollo.io People Search + Match
- [x] Clay API v1 deprecated -> replaced with direct Apollo.io enrichment
- [x] Slack alerting -> webhook configured, WARNING + CRITICAL alerts working

### Production Results (Real Data)
- [x] Scrape: 5 leads via Apollo People Search (7.3s)
- [x] Enrich: 5/5 via Apollo People Match (4.7s)
- [x] Segment: ICP scoring with real data (9ms)
- [x] Craft: 1 campaign created (56ms)
- [x] Approve: Auto-approve (0ms)
- [x] Send: 5 emails queued to shadow_mode_emails (2ms)
- [x] **Total: 6/6 PASS in 12.1s**

### Bugfixes
- [x] Apollo `reveal_phone_number` requires `webhook_url` — removed from payload
- [x] Segmentor `NoneType.lower()` crash — null-safe `(x or "").lower()` pattern
- [x] Segmentor `employee_count` None crash — safe dict access
- [x] Segmentor email resolution — fallback chain: work_email -> verified_email -> top-level
- [x] Send stage broken Instantly import — rewrote to shadow queue
- [x] CampaignCrafter `first_name` missing — name normalization added
- [x] Circuit breaker silent state changes — wired to Slack alerts
- [x] Pipeline stage failures silent — wired to Slack WARNING/CRITICAL

</details>

---

## Phase 3: Expand & Harden — COMPLETE

<details>
<summary>Click to expand completed tasks</summary>

### Enrichment & Pipeline
- [x] Apollo two-step flow (Search -> Match) — free search + 1 credit/reveal
- [x] Enrichment provider research (28+ providers)
- [x] Proxycurl removal (scraper + enricher) — shutting down Jul 2026
- [x] BetterContact fallback code — async polling in `enricher_clay_waterfall.py`
- [x] Clay removed from pipeline enrichment — `lead_id` not accessible in callback
- [x] `/webhooks/clay` simplified — RB2B visitor path only
- [x] Pipeline waterfall: Apollo -> BetterContact -> mock/skip

### Stability
- [x] Send stage rewrite — shadow mode queue for HoS dashboard
- [x] Pipeline alerts -> Slack — stage failures WARNING, exceptions CRITICAL
- [x] Circuit breaker alerts -> Slack — OPEN/recovery transitions
- [x] 3 consecutive clean production runs — 6/6 PASS x 3
- [x] 20-lead scale test — 19 enriched, 2 campaigns, 68.4s, 0 errors
- [x] Dashboard API E2E test — approve/reject/pending flows verified
- [x] 10+ consecutive clean production runs — ACHIEVED

### Integrations
- [x] Google Calendar setup guide
- [x] GHL Calendar integration — replaced Google Calendar, zero new dependencies
- [x] Instantly V2 API migration — server.py, dispatcher, webhooks, MCP server
- [x] Multi-channel cadence research

### Deferred from Phase 3
- [ ] BetterContact subscription — activate when Apollo miss rate justifies $15/mo
- [ ] ZeroBounce email verification — add when real sends begin (Phase 4E)

</details>

---

## Phase 4: Autonomy Graduation — IN PROGRESS

### <<< YOU ARE HERE <<<

**Overall Phase 4 Progress**: 98% — All code built + production cutover complete. Only operational steps remain.

```
4A: Domain & Instantly Go-Live      [##########] 100%  COMPLETE
4B: HeyReach LinkedIn Integration   [########--]  80%  CODE DONE, WEBHOOKS REGISTERED, AWAITING WARMUP
4C: OPERATOR Agent Activation       [##########] 100%  COMPLETE
4D: Multi-Channel Cadence           [##########] 100%  COMPLETE
4E: Supervised Live Sends           [#########-]  90%  RAMP DAY 2, COMPLIANCE PASS, AWAITING HoS SEND
4F: Monaco Signal Loop              [##########] 100%  COMPLETE
4G: Production Hardening (P0)       [##########] 100%  COMPLETE (commit 746d347)
```

---

### 4A: Domain & Instantly Go-Live — COMPLETE

<details>
<summary>Click to expand (15 tasks done)</summary>

- [x] Instantly V2 API migration (server.py, dispatcher, webhooks)
- [x] Fix `email_list` bug in `create_campaign()` — sending accounts passed in payload
- [x] Multi-account rotation config — 6 accounts, round-robin
- [x] Domain strategy config in `production.json`
- [x] Generate Instantly V2 API key — working
- [x] Set `INSTANTLY_API_KEY` (V2) in Railway — confirmed
- [x] Deploy V2 code to Railway — commit `53ab1c1`
- [x] 6 cold outreach domains DNS verified — all 100% health
- [x] Instantly warm-up complete — 100% health across all 6 accounts
- [x] Fix production.json domain mismatch — actual chris.d@ accounts
- [x] GHL dedicated domain (`chiefai.ai`) — Stage 1 warmup (8%)
- [x] Send 1 internal test campaign — `test_internal_v2_20260215` active
- [x] Register Instantly webhooks — 4/4 (reply, bounce, open, unsubscribe)

**Domains**: chiefaiofficerai.com, chiefaiofficerconsulting.com, chiefaiofficerguide.com, chiefaiofficerlabs.com, chiefaiofficerresources.com, chiefaiofficersolutions.com — all chris.d@, all 100% health.

</details>

---

### 4B: HeyReach LinkedIn Integration — AWAITING WARMUP

**Code + infra done**. Remaining: LinkedIn warm-up (4 weeks) + shadow test (5 profiles).

<details>
<summary>Click to expand completed tasks</summary>

#### Code (DONE)
- [x] `execution/heyreach_dispatcher.py` — API client + lead-list-first safety, 20/day ceiling, CLI
- [x] `webhooks/heyreach_webhook.py` — 11 event handlers, JSONL logging, follow-up flags, Slack alerts
- [x] Mount HeyReach webhook in `dashboard/health_app.py`
- [x] `scripts/register_heyreach_webhooks.py` — CRUD utility

#### Infrastructure (DONE)
- [x] `HEYREACH_API_KEY` set in Railway — verified working (19 campaigns visible)
- [x] 3 CAIO campaign templates created (tier_1: 334314, tier_2: 334364, tier_3: 334381)
- [x] 4 webhooks registered via HeyReach UI
- [x] Bidirectional HeyReach <-> Instantly sync configured
- [x] Campaign IDs mapped in `config/production.json`
- [x] Signal loop wired into HeyReach webhook handlers

</details>

#### Remaining (USER ACTION)

| # | Action | Time | How |
|---|--------|------|-----|
| 1 | Connect LinkedIn account + start warm-up | 10 min | HeyReach -> Accounts -> Add LinkedIn -> warm 4 weeks |
| 2 | Shadow test with 5 internal LinkedIn profiles | 15 min | Add 5 test profiles -> verify events flow to dashboard |

---

### 4C: OPERATOR Agent Activation — COMPLETE

<details>
<summary>Click to expand (13 tasks done)</summary>

- [x] `execution/operator_outbound.py` — OperatorOutbound class with CLI
- [x] `execution/operator_revival_scanner.py` — RevivalScanner
- [x] Wire InstantlyDispatcher + HeyReachDispatcher under OPERATOR
- [x] Three-layer dedup: daily state + signal loop + shadow flags
- [x] 3 revival statuses added to `core/lead_signals.py` (21 total)
- [x] Operator config in `config/production.json`
- [x] ICP tier -> channel routing (tier_1/2: email+LinkedIn, tier_3: email only)
- [x] 4 `/api/operator/*` dashboard endpoints
- [x] GATEKEEPER approval gate — batch approval before live dispatch
- [x] Update agent registry + permissions

</details>

---

### 4D: Multi-Channel Cadence — COMPLETE

<details>
<summary>Click to expand (9 tasks done)</summary>

- [x] `execution/cadence_engine.py` — CadenceEngine (8-step, 21-day)
- [x] Cadence config in `production.json`
- [x] `dispatch_cadence()` motion in OPERATOR
- [x] 4 `/api/cadence/*` dashboard endpoints
- [x] CRAFTER follow-up templates (value_followup, social_proof, breakup, close)
- [x] Auto-enroll from pipeline dispatch
- [ ] Phone/GHL calls — deferred

</details>

---

### 4E: Supervised Live Sends — RAMP DAY 2, COMPLIANCE PASS

**All code deployed. 2 real emails compliance-PASS, awaiting HoS review and send.**

#### Infrastructure (ALL DONE)
- [x] Instantly V2 timezone fix (`America/Detroit`)
- [x] Cadence engine encoding fix (Unicode -> ASCII)
- [x] Ramp configuration (5/day, tier_1, 3 days)
- [x] Ramp wired into OPERATOR agent
- [x] Pipeline body extraction fix (per-lead sequences)
- [x] Mid-market scrape targets (apollo.io default)
- [x] HoS Dashboard v3.0 with 4-tab UI (Overview, Email Queue, Campaigns, Settings)
- [x] Backend compliance checks (Reply STOP, signature, CTA, footer) on every pending email
- [x] "Reply STOP to unsubscribe." added to canonical text + HTML footer (commit `0f0e0a9`)
- [x] Refresh heartbeat + compliance indicators in approval modal
- [x] Deployed to Railway (`0f0e0a9`, 2026-02-19)

#### Go-Live Checklist (Operational — User Action Required)

| # | Step | Command / Action | Status |
|---|------|-----------------|--------|
| 1 | Run pipeline (mid-market) | `echo yes \| python execution/run_pipeline.py --mode production` | READY |
| 2 | Review leads in HoS dashboard | Open `/sales` -> review tier_1 leads | READY |
| 3 | Approve tier_1 leads | Click "Approve & Send" per lead | WAITING for Step 1 |
| 4 | First live dispatch | `python -m execution.operator_outbound --motion outbound --live` | WAITING for Step 3 |
| 5 | Approve GATEKEEPER batch | `/api/operator/approve-batch/{id}` | WAITING for Step 4 |
| 6 | Activate DRAFTED campaigns | Instantly dashboard -> Activate | WAITING for Step 5 |
| 7 | 3 supervised days | Monitor 5 emails/day, check KPIs daily | WAITING for Step 6 |
| 8 | Graduate to full autonomy | Set `ramp.enabled: false` -> 25/day + all tiers | WAITING for Step 7 |

#### KPI Targets

| Metric | Target | Red Flag | Source |
|--------|--------|----------|--------|
| ICP Match Rate | >= 80% | < 60% | Pipeline segmentation |
| Email Open Rate | >= 50% | < 30% | Instantly analytics |
| Reply Rate | >= 8% | 0 after 15 sends | Instantly + HeyReach |
| Bounce Rate | < 5% | > 10% | Instantly analytics |
| Unsubscribe Rate | < 2% | > 5% | Instantly webhooks |

---

### 4F: Monaco Signal Loop — COMPLETE

<details>
<summary>Click to expand (10 tasks done)</summary>

- [x] Signal Loop Engine — `core/lead_signals.py` (21 statuses)
- [x] Unified Activity Timeline — `core/activity_timeline.py`
- [x] "Why This Score" Explainability in segmentor
- [x] Leads Dashboard at `/leads`
- [x] 6 leads API endpoints + 4 cadence API endpoints
- [x] Instantly webhooks wired to signal loop (4 handlers)
- [x] HeyReach webhooks wired to signal loop (4 handlers)
- [x] Bootstrap lead data (15 leads from shadow emails)
- [x] Daily decay detection cron (Inngest, 10 AM UTC)

</details>

---

### 4G: Production Hardening (P0) — COMPLETE

**Deployed**: Commit `746d347` — 22 files, 3,064 insertions, 592 deletions.

| Patch | What | Key Files |
|-------|------|-----------|
| P0-A | API auth middleware (strict token auth on all `/api/*` routes) | `dashboard/health_app.py` |
| P0-B | Gatekeeper snapshot integrity (immutable batch scope) | `execution/operator_outbound.py` |
| P0-C | Dedup corrections (canonical email keys, GHL-sent exclusion) | `operator_outbound.py`, `instantly_dispatcher.py`, `heyreach_dispatcher.py` |
| P0-D | Redis state store (dual-read cutover, distributed locks) | `core/state_store.py`, `scripts/migrate_file_state_to_redis.py` |
| P0-E | Escalation regression fix (deterministic Level 1/2/3) | `core/notifications.py` |

#### Production Gates — ALL PASS

| Gate | Result |
|------|--------|
| Runtime env validation (staging + production) | PASS |
| Endpoint auth smoke (6/6 checks) | PASS |
| Redis state migration | ok: true (2 items) |
| Replay harness (50 golden set cases) | 100% pass (avg 4.54/5) |
| Critical pytest pack (60 tests) | 0 failures |

#### Post-P0 Cutover Steps — REVALIDATION REQUIRED
- [x] CORS_ALLOWED_ORIGINS set (Railway domain only)
- [ ] Rotate staging+production `DASHBOARD_AUTH_TOKEN` (previous value appeared in documentation history)
- [x] DASHBOARD_AUTH_STRICT=true in Railway
- [ ] Re-run auth smoke on staging+production URLs using newly rotated tokens
- [x] Redis migration executed successfully
- [x] Replay harness gate passed

---

## Recommended Next Steps (Priority Order)

### IMMEDIATE: First Live Dispatch (Steps 1-5 can happen TODAY)

| # | Task | How | Time |
|---|------|-----|------|
| 1 | **Rotate dashboard tokens** | Update Railway staging+production `DASHBOARD_AUTH_TOKEN`, redeploy both | 5 min |
| 2 | **Re-run endpoint auth smoke** | `python scripts/endpoint_auth_smoke.py --base-url "https://<env-domain>" --token "<new-token>"` | 2 min |
| 3 | **Run fresh pipeline** | `echo yes \| python execution/run_pipeline.py --mode production` | 30-60s |
| 4 | **Approve tier_1 leads** | HoS dashboard at `/sales` -> review -> Approve | 5 min |
| 5 | **First live dispatch** | `python -m execution.operator_outbound --motion outbound --live` | 1 min |
| 6 | **Approve GATEKEEPER batch** | `/api/operator/approve-batch/{id}` (Slack notifies) | 1 min |
| 7 | **Activate Instantly campaign** | Instantly dashboard -> find DRAFTED campaign -> Activate | 1 min |

### SHORT-TERM: 3-Day Supervised Ramp (Days 1-3)

| # | Task | When |
|---|------|------|
| 8 | Monitor Day 1 KPIs (opens, replies, bounces) | Day 1 EOD |
| 9 | Repeat pipeline -> dispatch -> approve cycle | Days 2-3 |
| 10 | Graduate: `ramp.enabled: false` in production.json | Day 3 EOD (if KPIs pass) |

### PARALLEL: LinkedIn Warmup (Can start NOW, runs 4 weeks)

| # | Task | When |
|---|------|------|
| 11 | Connect LinkedIn in HeyReach | NOW |
| 12 | Start LinkedIn warmup (5/day, 4 weeks) | NOW |
| 13 | Shadow test with 5 internal profiles | After warmup starts |
| 14 | Enable LinkedIn in cadence steps 2/4/6 | After 4 weeks |

### POST-GRADUATION: Full Autonomy Config

```json
// After 3 clean supervised days:
"operator.ramp.enabled": false           // Unlocks 25/day + all tiers
"operator.gatekeeper_required": false    // Optional: skip batch approval

// After LinkedIn warmup (4 weeks):
// HeyReach sends active in cadence steps 2/4/6
```

### OPTIONAL: Quality Improvements

| # | Task | Impact |
|---|------|--------|
| 15 | Activate BetterContact ($15/mo) | Better email quality on Apollo misses |
| 16 | Add ZeroBounce verification | Reduces bounce rate |
| 17 | Custom scrape targets per ICP vertical | Higher lead quality |
| 18 | Remove file-based state fallback | Cleaner Redis-only state (after 1 week stability) |
| 19 | Enforce webhook signature/secret checks on non-API webhooks | Prevents forged webhook events |

### Phase 5 Triggers (FUTURE)

| Task | Trigger |
|------|---------|
| Self-learning ICP calibration | 2 weeks of live send data |
| Multi-source intent fusion | 30 days of send data |
| A/B testing infrastructure | 30 days of send data |
| Enrichment result caching | Apollo credits running low |
| CRO Copilot | Lead volume > 500 |

---

## Architecture Overview

```
                    +----------------------------------+
                    |   6-STAGE PIPELINE               |
                    | Scrape -> Enrich -> Segment ->    |
                    | Craft -> Approve -> Send          |
                    +----------------+-----------------+
                                     |
                    +----------------v-----------------+
                    |   SHADOW QUEUE (.hive-mind/)      |
                    |   Shadow emails + dispatch logs   |
                    +----------------+-----------------+
                                     |
            +------------------------+------------------------+
            |                        |                        |
    +-------v-------+       +-------v-------+       +--------v------+
    |   Instantly    |       |   HeyReach    |       |    GHL        |
    |   (Email)      |       |  (LinkedIn)   |       |   (Nurture)   |
    |   V2 LIVE      |       |  CODE BUILT   |       |   ACTIVE      |
    +-------+-------+       +-------+-------+       +---------------+
            |                        |
    +-------v-------+       +-------v-------+
    |   Webhooks     |       |   Webhooks    |
    | open/reply/    |       | connect/reply/|
    | bounce/unsub   |       | campaign done |
    +-------+-------+       +-------+-------+
            |                        |
            +------------+-----------+
                         |
         +---------------v-----------------+  <-- Phase 4F (DONE)
         |   LEAD SIGNAL LOOP              |
         |   core/lead_signals.py          |
         |   21 statuses, decay scan       |
         +---------------+-----------------+
                         |
         +---------------v-----------------+  <-- Phase 4F (DONE)
         |   ACTIVITY TIMELINE             |
         |   core/activity_timeline.py     |
         |   All channels -> 1 timeline    |
         +---------------+-----------------+
                         |
         +---------------v-----------------+  <-- Phase 4F (DONE)
         |   LEADS DASHBOARD (/leads)      |
         |   Pipeline flow + timeline      |
         |   + "Why This Score"            |
         +----------------------------------+
```

---

## Safety Controls (Active — 8 Layers)

| Layer | Control | Status | What It Does |
|-------|---------|--------|-------------|
| 1 | `EMERGENCY_STOP` env var | `false` | Kills ALL outbound instantly |
| 2 | API auth middleware | **ACTIVE** (P0-A) | 401 on unauthenticated `/api/*` calls |
| 3 | CORS lockdown | **ACTIVE** (P0-A) | Only Railway domain accepted |
| 4 | GATEKEEPER gate | **ACTIVE** | Live dispatch requires batch approval |
| 5 | Ramp mode | **ACTIVE** | 5/day, tier_1 only, 3 days |
| 6 | `--dry-run` default | **ACTIVE** | OPERATOR requires `--live` flag |
| 7 | Campaigns DRAFTED | Built-in | Instantly V2 creates as status=0 |
| 8 | Shadow mode | **ACTIVE** | Emails -> `.hive-mind/shadow_mode_emails/` |

---

## Key Files Quick Reference

| Category | File | Purpose |
|----------|------|---------|
| **Pipeline** | `execution/run_pipeline.py` | 6-stage pipeline runner |
| | `execution/hunter_scrape_followers.py` | Apollo lead discovery |
| | `execution/enricher_clay_waterfall.py` | Apollo + BetterContact enrichment |
| | `execution/segmentor_classify.py` | ICP scoring + "Why This Score" |
| **OPERATOR** | `execution/operator_outbound.py` | Unified dispatch: outbound + cadence + revival |
| | `execution/operator_revival_scanner.py` | GHL contact mining for re-engagement |
| | `execution/cadence_engine.py` | 21-day Email + LinkedIn cadence scheduler |
| **Dispatch** | `execution/instantly_dispatcher.py` | Shadow -> Instantly campaigns |
| | `execution/heyreach_dispatcher.py` | Lead-list-first LinkedIn dispatch |
| **Webhooks** | `webhooks/instantly_webhook.py` | Email open/reply/bounce/unsub |
| | `webhooks/heyreach_webhook.py` | 11 LinkedIn events |
| **Signal Loop** | `core/lead_signals.py` | Lead status engine + decay detection |
| | `core/activity_timeline.py` | Per-lead event aggregation |
| **Security** | `dashboard/health_app.py` | FastAPI + auth middleware + all routes |
| | `core/state_store.py` | Redis state backend (NEW in 4G) |
| **Config** | `config/production.json` | Safety controls, ramp, cadence, domains |
| **Scripts** | `scripts/endpoint_auth_smoke.py` | Auth smoke test (6 checks) |
| | `scripts/migrate_file_state_to_redis.py` | File -> Redis migration |
| | `scripts/validate_runtime_env.py` | Runtime env validator |
| **Docs** | `CAIO_IMPLEMENTATION_PLAN.md` | Full implementation plan (v4.5) |
| | `docs/CODEX_HANDOFF.md` | Codex review handoff |

---

## Dashboards Quick Reference

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| System Health | `/` | Agent status, circuit breakers, context zones |
| Scorecard | `/scorecard` | Pipeline run history, stage pass/fail |
| Head of Sales | `/sales` | Email approval queue (approve/reject/edit) |
| Leads Signal Loop | `/leads` | Pipeline funnel, lead list, timeline, decay scan |

---

*This tracker is the single source of truth for CAIO Alpha Swarm development status.*
*For full implementation details, see `CAIO_IMPLEMENTATION_PLAN.md` (v4.5).*
*For Codex review, see `docs/CODEX_HANDOFF.md`.*
*For signal loop activation, see `docs/MONACO_SIGNAL_LOOP_GUIDE.md`.*
