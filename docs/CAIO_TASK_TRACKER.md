# CAIO Alpha Swarm — Unified Task Tracker

**Last Updated**: 2026-02-17
**Source**: Merged from `CAIO_IMPLEMENTATION_PLAN.md` (v3.9) + `docs/MONACO_SIGNAL_LOOP_GUIDE.md`
**Quick Nav**: [Phase 0](#phase-0-foundation-lock--complete) | [Phase 1](#phase-1-live-pipeline-validation--complete) | [Phase 2](#phase-2-supervised-burn-in--complete) | [Phase 3](#phase-3-expand--harden--complete) | **[Phase 4 (YOU ARE HERE)](#phase-4-autonomy-graduation--in-progress)** | [Phase 5](#phase-5-optimize--scale-post-autonomy)

---

## Progress Overview

```
Phase 0: Foundation Lock          [##########] 100%  COMPLETE
Phase 1: Live Pipeline Validation [##########] 100%  COMPLETE
Phase 2: Supervised Burn-In       [##########] 100%  COMPLETE
Phase 3: Expand & Harden          [##########] 100%  COMPLETE
Phase 4: Autonomy Graduation      [#########.]  95%  ◄◄◄ YOU ARE HERE
Phase 5: Optimize & Scale         [----------]   0%  FUTURE
```

**Autonomy Score**: ~95/100
**Production Runs**: 33+ (22 fully clean, last 10 consecutive 6/6 PASS)
**Monthly Spend**: ~$583/mo (Clay $499 + Apollo $49 + Railway $5 + Instantly $30)

---

## Phase 0: Foundation Lock — COMPLETE

All core infrastructure deployed and validated. Nothing to do here.

<details>
<summary>Click to expand completed tasks</summary>

- [x] 12-agent architecture (Queen + 11 agents) — all instantiated
- [x] 6-stage pipeline (scrape/enrich/segment/craft/approve/send) — `execution/run_pipeline.py`
- [x] FastAPI dashboard on port 8080 — `dashboard/health_app.py`
- [x] Redis (Upstash) integration — 62ms from Railway
- [x] Inngest event-driven functions — 4 functions mounted
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
- [x] LinkedIn Scraper 403 → replaced with Apollo.io People Search + Match
- [x] Clay API v1 deprecated → replaced with direct Apollo.io enrichment
- [x] Slack alerting → webhook configured, WARNING + CRITICAL alerts working

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
- [x] Segmentor email resolution — fallback chain: work_email → verified_email → top-level
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
- [x] Apollo two-step flow (Search → Match) — free search + 1 credit/reveal
- [x] Enrichment provider research (28+ providers) — `docs/research/ENRICHMENT_PROVIDER_RESEARCH_2026.md`
- [x] Proxycurl removal (scraper + enricher) — shutting down Jul 2026
- [x] BetterContact fallback code — async polling in `enricher_clay_waterfall.py`
- [x] Clay removed from pipeline enrichment — `lead_id` not accessible in callback
- [x] `/webhooks/clay` simplified — RB2B visitor path only
- [x] Pipeline waterfall: Apollo → BetterContact → mock/skip

### Stability
- [x] Send stage rewrite — shadow mode queue for HoS dashboard
- [x] Pipeline alerts → Slack — stage failures WARNING, exceptions CRITICAL
- [x] Circuit breaker alerts → Slack — OPEN/recovery transitions
- [x] 3 consecutive clean production runs — 6/6 PASS × 3
- [x] 20-lead scale test — 19 enriched, 2 campaigns, 68.4s, 0 errors
- [x] Dashboard API E2E test — approve/reject/pending flows verified
- [x] 10+ consecutive clean production runs — ACHIEVED

### Integrations
- [x] Google Calendar setup guide — `docs/GOOGLE_CALENDAR_SETUP_GUIDE.md`
- [x] GHL Calendar integration — replaced Google Calendar, zero new dependencies
- [x] Instantly V2 API migration — server.py, dispatcher, webhooks, MCP server
- [x] Multi-channel cadence research — `docs/research/MULTI_CHANNEL_CADENCE_RESEARCH_2026.md`

### Deferred from Phase 3
- [ ] BetterContact subscription — activate when Apollo miss rate justifies $15/mo
- [ ] ZeroBounce email verification — add when real sends begin (Phase 4E)

</details>

---

## Phase 4: Autonomy Graduation — IN PROGRESS

### ◄◄◄ YOU ARE HERE ◄◄◄

**Overall Phase 4 Progress**: 95% — 4A+4C+4D+4F COMPLETE, 4B awaiting LinkedIn warmup, GATEKEEPER gate BUILT

```
4A: Domain & Instantly Go-Live      [##########] 100%  COMPLETE
4B: HeyReach LinkedIn Integration   [########--]  80%  API VERIFIED, CAMPAIGNS CREATED, WEBHOOKS REGISTERED
4C: OPERATOR Agent Activation       [##########] 100%  COMPLETE (unified dispatch + revival + GATEKEEPER gate)
4D: Multi-Channel Cadence           [##########] 100%  COMPLETE (Engine + CRAFTER + Auto-Enroll)
4E: Supervised Live Sends           [----------]   0%  TODO (THE GOAL — actually_send: true)
4F: Monaco Signal Loop              [##########] 100%  COMPLETE (signal loop + decay cron + bootstrap done)
```

---

### 4A: Domain & Instantly Go-Live — COMPLETE

All Instantly V2 infrastructure is live and verified.

<details>
<summary>Click to expand completed tasks</summary>

- [x] Instantly V2 API migration (server.py, dispatcher, webhooks)
- [x] Fix `email_list` bug in `create_campaign()` — sending accounts passed in payload
- [x] Multi-account rotation config — 6 accounts, round-robin
- [x] Webhook handler V2 cleanup — `activate_campaign()` replaces old pattern
- [x] Domain strategy config in `production.json`
- [x] All code verified (AST + JSON parse)
- [x] Generate Instantly V2 API key — working
- [x] Set `INSTANTLY_API_KEY` (V2) in Railway — confirmed
- [x] Deploy V2 code to Railway — commit `53ab1c1`
- [x] 6 cold outreach domains DNS verified — all 100% health
- [x] Instantly warm-up complete — 100% health across all 6 accounts
- [x] Fix production.json domain mismatch — actual chris.d@ accounts
- [x] Set `INSTANTLY_FROM_EMAIL` in Railway
- [x] GHL dedicated domain (`chiefai.ai`) — Stage 1 warmup (8%)
- [x] Send 1 internal test campaign — `test_internal_v2_20260215` active
- [x] Register Instantly webhooks — 4/4 (reply, bounce, open, unsubscribe)

**Domains (confirmed)**:
| Domain | Sender | Health |
|--------|--------|--------|
| chiefaiofficerai.com | chris.d@ | 100% |
| chiefaiofficerconsulting.com | chris.d@ | 100% |
| chiefaiofficerguide.com | chris.d@ | 100% |
| chiefaiofficerlabs.com | chris.d@ | 100% |
| chiefaiofficerresources.com | chris.d@ | 100% |
| chiefaiofficersolutions.com | chris.d@ | 100% |

</details>

---

### 4B: HeyReach LinkedIn Integration — API VERIFIED, CAMPAIGNS CREATED

**What's done**: API key verified, 3 CAIO campaigns created (tier 1/2/3), 4 webhooks registered in UI, bidirectional Instantly sync configured, dispatcher + webhook handlers deployed.
**What's remaining**: LinkedIn warm-up (4 weeks) + shadow test with 5 profiles.

#### Code Tasks (DONE)
- [x] `execution/heyreach_dispatcher.py` — API client + lead-list-first safety, 20/day ceiling, CLI
- [x] `webhooks/heyreach_webhook.py` — 11 event handlers, JSONL logging, follow-up flags, Slack alerts
- [x] Mount HeyReach webhook in `dashboard/health_app.py`
- [x] `scripts/register_heyreach_webhooks.py` — CRUD: --list, --delete-all, --check-auth
- [x] Wire CONNECTION_REQUEST_ACCEPTED → Instantly warm follow-up flag

#### Infrastructure (DONE)
- [x] `HEYREACH_API_KEY` set in Railway — verified working (19 campaigns visible)
- [x] 3 CAIO campaign templates created in HeyReach UI:
  - tier_1: 334314 ("CAIO Tier 1 — VP+ Decision Makers")
  - tier_2: 334364 ("CAIO Tier 2 — Directors & Managers")
  - tier_3: 334381 ("CAIO Tier 3 — Connection Only")
- [x] 4 webhooks registered via HeyReach UI (Settings → Integrations)
- [x] Bidirectional HeyReach ↔ Instantly sync configured (API key exchange)
- [x] Campaign IDs mapped in `config/production.json`

#### Remaining (TODO)

| # | Action | Time | How |
|---|--------|------|-----|
| 1 | Connect LinkedIn account + start warm-up | 10 min | HeyReach → Accounts → Add LinkedIn → warm 4 weeks |
| 2 | Shadow test with 5 internal LinkedIn profiles | 15 min | Add 5 test profiles → verify events flow to dashboard |

---

### 4F: Monaco-Inspired Intelligence Layer — COMPLETE

**What it is**: Feedback loop architecture inspired by Monaco.com. Transforms linear pipeline into a signal loop.

<details>
<summary>Click to expand completed tasks</summary>

#### Signal Loop + Timeline + Dashboard (DONE)

- [x] **Signal Loop Engine** — `core/lead_signals.py`
  - LeadStatusManager with 21 lead statuses (incl. 3 revival states)
  - Signal handlers for email (open/reply/bounce/unsub) and LinkedIn (connect/reply)
  - Engagement decay detection (72h ghost, 7d stall, 2+ opens no reply)
  - `is_revivable()` check for revival eligibility
  - Bootstrap from existing shadow emails

- [x] **Unified Activity Timeline** — `core/activity_timeline.py`
  - Aggregates events from ALL sources per lead
  - `get_revival_context()` for CRAFTER re-engagement copy

- [x] **"Why This Score" Explainability** — `execution/segmentor_classify.py`

- [x] **Leads Dashboard** — `dashboard/leads_dashboard.html` (served at `/leads`)

- [x] **API Endpoints** (6 leads routes + 4 cadence routes in `dashboard/health_app.py`)

#### Webhook Wiring (DONE)

- [x] **Instantly webhooks wired to signal loop** — all 4 handlers call `LeadStatusManager`:
  - `_process_reply` → `handle_email_replied()`
  - `_process_bounce` → `handle_email_bounced()`
  - `_process_unsubscribe` → `handle_email_unsubscribed()`
  - `handle_instantly_open` → `handle_email_opened()`

- [x] **HeyReach webhooks wired to signal loop** — all key handlers call `LeadStatusManager`:
  - `CONNECTION_REQUEST_SENT` → `handle_linkedin_connection_sent()`
  - `CONNECTION_REQUEST_ACCEPTED` → `handle_linkedin_connection_accepted()`
  - `MESSAGE_REPLY_RECEIVED` → `handle_linkedin_reply()`
  - `CAMPAIGN_COMPLETED` → `update_lead_status("linkedin_exhausted")`

#### Remaining (TODO)

- [x] **Bootstrap lead data** — 15 leads bootstrapped into signal loop from shadow emails
- [x] **Schedule decay detection** — `daily_decay_detection` Inngest cron (10 AM UTC): decay scan + batch expiry + cadence sync

</details>

---

### 4C: OPERATOR Agent Activation — COMPLETE

Unified dispatch layer orchestrating Instantly + HeyReach + GHL Revival under warmup-aware volume limits.

<details>
<summary>Click to expand completed tasks</summary>

- [x] `execution/operator_outbound.py` — OperatorOutbound class (zero-args constructor, registry-compatible)
  - `dispatch_outbound()` — Instantly email + HeyReach LinkedIn (sequential)
  - `dispatch_cadence()` — follow-up steps for enrolled leads
  - `dispatch_revival()` — GHL stale contact re-engagement
  - `dispatch_all()` — all three motions sequentially
  - `get_status()` — dashboard data with cadence summary
  - `get_warmup_schedule()` — date-based LinkedIn ceiling calculation
  - WarmupSchedule, OperatorDailyState, OperatorReport dataclasses
  - Three-layer dedup: daily state + signal loop + shadow email flags
  - Full CLI: `--status`, `--motion`, `--dry-run`, `--live`, `--history`, `--json`
- [x] `execution/operator_revival_scanner.py` — RevivalScanner + RevivalCandidate
  - Scores: website_revisit (0.9+) > previously_replied (0.7-0.9) > opened_only (0.5-0.7) > never_engaged (0.3)
  - Filters: 30-120 day inactivity window, exclude tags, revivability check
  - CLI: `--scan --limit N --json`
- [x] 3 revival statuses added to `core/lead_signals.py` (21 total)
- [x] `is_revivable()` method on LeadStatusManager
- [x] `get_revival_context()` on ActivityTimeline
- [x] `search_by_tags()`, `search_by_pipeline_stage()`, `get_stale_contacts()` on GHLLocalSync
- [x] 4 `/api/operator/*` endpoints in dashboard
- [x] Operator config in `config/production.json` (warmup schedule, tier routing, revival config)
- [x] ICP tier → channel routing logic (tier_1/2: email+LinkedIn, tier_3: email only)
- [x] Update agent registry + permissions
- [x] GATEKEEPER approval gate — batch approval before live dispatch (`create_batch` → `approve_batch` → execute). 3 new dashboard endpoints: `pending-batch`, `approve-batch`, `reject-batch`. Slack alert on batch creation.

</details>

---

### 4D: Multi-Channel Cadence — COMPLETE (Engine + CRAFTER + Auto-Enroll)

Simplified Email + LinkedIn 21-day sequence (no phone — deferred per user directive). Aligned to LinkedIn warmup period (4 weeks, 5/day).

#### Cadence Sequence (Email + LinkedIn Only)

| Step | Day | Channel | Action | Condition |
|------|-----|---------|--------|-----------|
| 1 | 1 | Email | Personalized intro | Always |
| 2 | 2 | LinkedIn | Connection request | Has linkedin_url |
| 3 | 5 | Email | Value/case study follow-up | Not replied |
| 4 | 7 | LinkedIn | Direct message | Connected only |
| 5 | 10 | Email | Social proof/testimonial | Not replied |
| 6 | 14 | LinkedIn | Follow-up message | Connected only |
| 7 | 17 | Email | Break-up | Not replied |
| 8 | 21 | Email | Graceful close | Not replied |

**Exit on**: replied, meeting_booked, bounced, unsubscribed, linkedin_replied
**Pause on**: engaged_not_replied (2+ opens, no reply — needs human review)

#### Built (DONE)
- [x] `execution/cadence_engine.py` — CadenceEngine class (~350 lines)
  - `enroll()` — start lead in cadence (idempotent)
  - `get_due_actions()` — scan all active leads, return actions due today
  - `mark_step_done()` — record completion, advance to next step
  - `sync_signals()` — auto-exit replied/bounced/unsubscribed leads
  - `pause_lead()` / `resume_lead()` / `exit_lead()` — manual controls
  - `get_cadence_summary()` — dashboard stats
  - Condition evaluation: `has_linkedin_url`, `not_replied`, `linkedin_connected`
  - Step skipping: if condition not met, auto-advance to next step
  - CLI: `--due`, `--status`, `--list`, `--enroll`, `--sync`, `--json`
- [x] Cadence config in `config/production.json` (8-step sequence, exit/pause conditions)
- [x] `dispatch_cadence()` motion in OPERATOR — processes follow-up steps
- [x] `dispatch_all()` updated: outbound → cadence → revival (3 motions)
- [x] 4 `/api/cadence/*` dashboard endpoints (summary, due, leads, sync)
- [x] OPERATOR `--motion cadence` CLI support
- [x] OPERATOR status includes cadence summary

- [x] **CRAFTER integration** — `craft_cadence_followup()` generates personalized email copy for Steps 3/5/7/8
  - 4 templates: `value_followup`, `social_proof`, `breakup`, `close`
  - Jinja2-rendered with lead data (first_name, company, title)
  - Follow-up emails saved as shadow files (`cadence_s{step}_d{day}_*.json`) for review
- [x] **Auto-enroll from pipeline** — `_auto_enroll_to_cadence()` in OPERATOR
  - Scans dispatched shadow emails, enrolls into default_21day cadence
  - Extracts tier, linkedin_url, lead_data from shadow email files
  - Idempotent: skips already-enrolled leads, marks `cadence_enrolled` flag on file

#### Remaining (TODO)
- [ ] **Phone/GHL calls** — deferred (add Day 3 call when complexity budget allows)

---

### 4E: Supervised Live Sends — TODO (THE ACTUAL GOAL)

This is where `actually_send` flips to `true` and real outreach begins.

#### Prerequisites
- [x] 6 cold outreach domains DNS verified + warm-up complete
- [x] Internal test campaign sent via Instantly
- [x] Signal loop wired into Instantly webhooks (4F)
- [x] Signal loop wired into HeyReach webhooks (4F)
- [x] OPERATOR agent operational (4C)
- [x] Cadence engine built (4D)
- [ ] LinkedIn account warm-up complete (4 weeks) — requires 4B
- [ ] Shadow test via HeyReach completed (5 profiles) — requires 4B
- [x] GATEKEEPER approval gate for OPERATOR dispatch (batch approval flow)

#### Go-Live Checklist
- [ ] Enable `actually_send: true` for tier_1 only in `config/production.json`
- [ ] 3 days supervised operation (5 emails/day)
- [ ] Monitor KPIs: open rate ≥50%, reply rate ≥8%, bounce <5%
- [ ] Graduate to 25/day email ceiling
- [ ] Enable HeyReach LinkedIn sends (5 connections/day during warmup)

#### KPI Targets

| Metric | Target | Source |
|--------|--------|--------|
| ICP Match Rate | ≥ 80% | Pipeline segmentation |
| Email Open Rate | ≥ 50% | Instantly analytics |
| Reply Rate | ≥ 8% | Instantly + HeyReach |
| Bounce Rate | < 5% | Instantly analytics |
| LinkedIn Accept Rate | ≥ 30% | HeyReach stats |
| Autonomous Days | 3 consecutive | No manual intervention |

---

## Recommended Next Steps (In Priority Order)

Based on current state (Phase 4, 95% complete), all code is built. Only user decisions remain.

### Recently Completed

| # | Task | Status |
|---|------|--------|
| ~~1~~ | Bootstrap lead data → signal loop | DONE — 15 leads bootstrapped |
| ~~2~~ | Deploy OPERATOR + cadence + CRAFTER to Railway | DONE — commit `bcf7c02` |
| ~~3~~ | GATEKEEPER approval gate | DONE — batch approval + 3 endpoints (commit `bcd3815`) |
| ~~4~~ | Daily decay detection cron | DONE — Inngest `daily_decay_detection` (10 AM UTC) |
| ~~5~~ | CRAFTER follow-up templates | DONE — 4 templates wired into `dispatch_cadence` |
| ~~6~~ | Auto-enroll pipeline leads | DONE — dispatched leads auto-enrolled into cadence |

### Requires Decision Before Proceeding

| # | Task | Decision Needed | Impact |
|---|------|----------------|--------|
| 5 | **Flip `actually_send: true`** for tier_1 | Are you ready for real emails to go out? Start with 5/day ceiling. | THE milestone — everything else is preparation for this |
| 6 | **LinkedIn warm-up start** | Connect LinkedIn account to HeyReach and begin 4-week warmup | Unblocks LinkedIn cadence steps |
| 7 | **Activate BetterContact** | Approve $15/mo for enrichment fallback | Improves data quality on Apollo misses |

### Future (Phase 5 Triggers)

| Task | Trigger |
|------|---------|
| Self-learning ICP calibration | 2 weeks of live send data |
| Multi-source intent fusion (RB2B + email + LinkedIn) | 30 days of send data |
| A/B testing infrastructure | 30 days of send data |
| Enrichment result caching (Supabase) | Apollo credits running low |
| CRO Copilot ("Ask" chat) | Lead volume exceeds 500+ |
| Phone/GHL calls in cadence | After email+LinkedIn prove ROI |

---

## Key Decisions & Questions Per Phase

### Before Starting Phase 4E (Live Sends)

> These must be answered before `actually_send: true`:

1. **Daily send volume**: Start at 5/day for 3 days, then ramp to 25/day? Or different ramp?
2. **Tier restriction**: Start with tier_1 only (highest ICP fit)? Or include tier_2?
3. **Approval workflow**: Keep Gatekeeper manual approval for first 3 days? Or auto-approve tier_1?
4. **Bounce handling**: Auto-suppress bounced emails from future campaigns? (Currently appends to `.hive-mind/unsubscribes.jsonl`)
5. **Reply routing**: Where do replies go? Currently logged via Instantly webhook + Slack notification. RESPONDER classification available.

---

## Architecture Overview

```
                    ┌─────────────────────────────────┐
                    │   6-STAGE PIPELINE (existing)     │
                    │ Scrape → Enrich → Segment →       │
                    │ Craft → Approve → Send             │
                    └────────────┬────────────────────┘
                                 │
                    ┌────────────▼────────────────────┐
                    │   SHADOW QUEUE (.hive-mind/)      │
                    │   Shadow emails + dispatch logs    │
                    └────────────┬────────────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                     │
    ┌───────▼───────┐   ┌───────▼───────┐   ┌────────▼──────┐
    │   Instantly     │   │   HeyReach    │   │    GHL         │
    │   (Email)       │   │  (LinkedIn)   │   │   (Nurture)    │
    │   V2 LIVE       │   │  CODE BUILT   │   │   ACTIVE       │
    └───────┬───────┘   └───────┬───────┘   └────────────────┘
            │                    │
    ┌───────▼───────┐   ┌───────▼───────┐
    │   Webhooks     │   │   Webhooks     │
    │ open/reply/    │   │ connect/reply/ │
    │ bounce/unsub   │   │ campaign done  │
    └───────┬───────┘   └───────┬───────┘
            │                    │
            └────────┬───────────┘
                     │
         ┌───────────▼────────────────┐  ◄── Phase 4F (BUILT)
         │   LEAD SIGNAL LOOP          │
         │   core/lead_signals.py      │
         │   18 statuses, decay scan   │
         └───────────┬────────────────┘
                     │
         ┌───────────▼────────────────┐  ◄── Phase 4F (BUILT)
         │   ACTIVITY TIMELINE         │
         │   core/activity_timeline.py │
         │   All channels → 1 timeline │
         └───────────┬────────────────┘
                     │
         ┌───────────▼────────────────┐  ◄── Phase 4F (BUILT)
         │   LEADS DASHBOARD           │
         │   /leads                    │
         │   Pipeline flow + timeline  │
         │   + "Why This Score"        │
         └────────────────────────────┘
```

---

## Dashboards Quick Reference

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| System Health | `/` | Agent status, circuit breakers, context zones |
| Scorecard | `/scorecard` | Pipeline run history, stage pass/fail |
| Head of Sales | `/sales` | Email approval queue (approve/reject/edit) |
| **Leads Signal Loop** | `/leads` | Pipeline funnel, lead list, timeline, decay scan |

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
| **Dispatch** | `execution/instantly_dispatcher.py` | Shadow → Instantly campaigns |
| | `execution/heyreach_dispatcher.py` | Lead-list-first LinkedIn dispatch |
| **Webhooks** | `webhooks/instantly_webhook.py` | Email open/reply/bounce/unsub |
| | `webhooks/heyreach_webhook.py` | 11 LinkedIn events |
| **Signal Loop** | `core/lead_signals.py` | Lead status engine + decay detection |
| | `core/activity_timeline.py` | Per-lead event aggregation |
| **Dashboard** | `dashboard/health_app.py` | FastAPI + all routes |
| | `dashboard/leads_dashboard.html` | Leads signal loop UI |
| **Config** | `config/production.json` | `actually_send`, `shadow_mode`, domains |
| **Scripts** | `scripts/register_instantly_webhooks.py` | Instantly webhook CRUD |
| | `scripts/register_heyreach_webhooks.py` | HeyReach webhook CRUD |
| **Docs** | `CAIO_IMPLEMENTATION_PLAN.md` | Full implementation plan (v3.6) |
| | `docs/MONACO_SIGNAL_LOOP_GUIDE.md` | Signal loop activation guide |

---

## Safety Controls (Active)

| Control | Setting | Location | What It Does |
|---------|---------|----------|-------------|
| `actually_send` | **false** | `config/production.json` | Blocks all real email sends |
| `shadow_mode` | **true** | `config/production.json` | Emails go to `.hive-mind/shadow_mode_emails/` |
| `max_daily_sends` | **0** | `config/production.json` | Daily ceiling (0 = unlimited in shadow) |
| `EMERGENCY_STOP` | env var | Railway | Kill switch — blocks ALL outbound |
| Shadow emails | `.hive-mind/shadow_mode_emails/` | Local/Railway | Review queue before enabling real sends |
| Audit trail | `.hive-mind/audit/` | Local/Railway | All Gatekeeper decisions logged |
| Lead status files | `.hive-mind/lead_status/` | Local/Railway | Signal loop state per lead |

---

## Metrics to Watch (Once Live)

| Metric | Target | What It Tells You | Where to See It |
|--------|--------|-------------------|-----------------|
| ICP Match Rate | ≥ 80% | Lead quality from Apollo | Pipeline segmentation output |
| Email Open Rate | ≥ 50% | Subject line + deliverability quality | Instantly analytics + `/leads` funnel |
| Reply Rate | ≥ 8% | Outreach copy effectiveness | Instantly + `/leads` → "Replied" filter |
| Bounce Rate | < 5% | Email data quality | Instantly analytics + `/leads` → "Bounced" |
| Ghost Rate | track | % emails never opened after 72h | `/leads` → "Ghosted" filter |
| Stall Rate | track | % opens that never reply after 7d | `/leads` → "Stalled" filter |
| Engaged-Not-Replied | track | Interested but hesitant leads | `/leads` → candidates for follow-up |
| LinkedIn Accept Rate | ≥ 30% | Profile + message quality | HeyReach stats |
| Open → Reply Conv | ≥ 15% | Outreach quality combined metric | `/leads` funnel numbers |
| Autonomous Days | 3 consecutive | Pipeline stability | No manual intervention needed |

---

*This tracker is the single source of truth for CAIO Alpha Swarm development status.*
*For full implementation details, see `CAIO_IMPLEMENTATION_PLAN.md` (v3.9).*
*For signal loop activation steps, see `docs/MONACO_SIGNAL_LOOP_GUIDE.md`.*
