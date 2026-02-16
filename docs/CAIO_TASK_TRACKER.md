# CAIO Alpha Swarm — Unified Task Tracker

**Last Updated**: 2026-02-16
**Source**: Merged from `CAIO_IMPLEMENTATION_PLAN.md` (v3.6) + `docs/MONACO_SIGNAL_LOOP_GUIDE.md`
**Quick Nav**: [Phase 0](#phase-0-foundation-lock--complete) | [Phase 1](#phase-1-live-pipeline-validation--complete) | [Phase 2](#phase-2-supervised-burn-in--complete) | [Phase 3](#phase-3-expand--harden--complete) | **[Phase 4 (YOU ARE HERE)](#phase-4-autonomy-graduation--in-progress)** | [Phase 5](#phase-5-optimize--scale-post-autonomy)

---

## Progress Overview

```
Phase 0: Foundation Lock          [##########] 100%  COMPLETE
Phase 1: Live Pipeline Validation [##########] 100%  COMPLETE
Phase 2: Supervised Burn-In       [##########] 100%  COMPLETE
Phase 3: Expand & Harden          [##########] 100%  COMPLETE
Phase 4: Autonomy Graduation      [#######---]  65%  ◄◄◄ YOU ARE HERE
Phase 5: Optimize & Scale         [----------]   0%  FUTURE
```

**Autonomy Score**: ~90/100
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

**Overall Phase 4 Progress**: 65% — 4A complete, 4B code built (awaiting subscription), 4F signal loop built

```
4A: Domain & Instantly Go-Live      [##########] 100%  COMPLETE
4B: HeyReach LinkedIn Integration   [######----]  60%  CODE BUILT, AWAITING USER ACTIONS
4C: OPERATOR Agent Activation       [----------]   0%  TODO (deferred — premature with 1 active channel)
4D: Multi-Channel Cadence           [----------]   0%  TODO (requires 4B + 4C)
4E: Supervised Live Sends           [----------]   0%  TODO (THE GOAL — actually_send: true)
4F: Monaco Signal Loop              [########--]  80%  CODE BUILT, WIRING REMAINING
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

### 4B: HeyReach LinkedIn Integration — CODE BUILT, AWAITING USER ACTIONS

**What's built**: Dispatcher, webhooks, registration script — all deployed to Railway.
**What's blocking**: 7 user actions requiring HeyReach subscription + LinkedIn account setup.

#### Code Tasks (DONE)
- [x] `execution/heyreach_dispatcher.py` — API client + lead-list-first safety, 20/day ceiling, CLI
- [x] `webhooks/heyreach_webhook.py` — 11 event handlers, JSONL logging, follow-up flags, Slack alerts
- [x] Mount HeyReach webhook in `dashboard/health_app.py`
- [x] `scripts/register_heyreach_webhooks.py` — CRUD: --list, --delete-all, --check-auth
- [x] Wire CONNECTION_REQUEST_ACCEPTED → Instantly warm follow-up flag

#### User Actions Required (TODO)

> **Note**: These are deferred until you have approval to use your LinkedIn account for testing.

| # | Action | Time | How |
|---|--------|------|-----|
| 1 | Subscribe to HeyReach Growth ($79/mo) | 5 min | [heyreach.io/pricing](https://heyreach.io/pricing) → Growth plan |
| 2 | Connect LinkedIn account + start warm-up | 10 min | HeyReach → Accounts → Add LinkedIn → warm 4 weeks |
| 3 | Build 3 campaign templates in HeyReach UI | 30 min | Create tier_1, tier_2, tier_3 sequences (connection → message → follow-up) |
| 4 | Set `HEYREACH_API_KEY` in Railway | 2 min | HeyReach Settings → API → copy key → Railway Variables → paste |
| 5 | Register webhooks (run script) | 2 min | `python scripts/register_heyreach_webhooks.py` |
| 6 | Configure native HeyReach ↔ Instantly sync | 5 min | Paste API keys in both dashboards (Settings → Integrations) |
| 7 | Shadow test with 5 internal LinkedIn profiles | 15 min | Add 5 test profiles → verify events flow to dashboard |

---

### 4F: Monaco-Inspired Intelligence Layer — CODE BUILT, WIRING REMAINING

**What it is**: Feedback loop architecture inspired by [Monaco.com](https://www.monaco.com) ($35M AI-native revenue engine). Transforms our linear pipeline (scrape → send → done) into a signal loop (scrape → send → engagement signals → re-score → next action).

#### Built (DONE)

- [x] **Signal Loop Engine** — `core/lead_signals.py`
  - LeadStatusManager with 18 lead statuses
  - Signal handlers for email (open/reply/bounce/unsub) and LinkedIn (connect/reply)
  - Engagement decay detection (72h ghost, 7d stall, 2+ opens no reply)
  - Bootstrap from existing shadow emails

- [x] **Unified Activity Timeline** — `core/activity_timeline.py`
  - Aggregates events from ALL sources per lead
  - Shadow emails, Instantly dispatch, HeyReach events, pipeline events, status signals

- [x] **"Why This Score" Explainability** — `execution/segmentor_classify.py`
  - Human-readable scoring reasons per lead
  - Example: `+22: VP-level title "VP of Sales" (budget influencer)`

- [x] **Leads Dashboard** — `dashboard/leads_dashboard.html` (served at `/leads`)
  - 5-stage pipeline flow visualization
  - Filterable lead card list (All, Replied, Opened, Ghosted, Stalled, Tier 1/2)
  - Click-to-expand timeline modal with "Why This Score" + activity events

- [x] **API Endpoints** (6 new routes in `dashboard/health_app.py`)
  - `GET /api/leads` — all leads with status
  - `GET /api/leads/funnel` — pipeline funnel counts
  - `GET /api/leads/status-summary` — count by status
  - `GET /api/leads/{email}/timeline` — per-lead timeline
  - `POST /api/leads/detect-decay` — ghosting/stall scan
  - `POST /api/leads/bootstrap` — seed from shadow emails

#### Lead Status State Machine

```
PIPELINE                    OUTREACH                 ENGAGEMENT
pending ──► approved ──► dispatched ──► sent ──► opened ──► replied ──► meeting_booked
   │                                      │          │
   ▼                                      ▼          ▼
 rejected                              ghosted    stalled
                                       (72h)      (7 days)
                                                     │
                                                     ▼
                                              engaged_not_replied
                                              (2+ opens, 0 replies)

TERMINAL: bounced | unsubscribed | disqualified

LINKEDIN: linkedin_sent → linkedin_connected → linkedin_replied
                                                    │
                                              linkedin_exhausted
```

#### Remaining Tasks (TODO)

- [ ] **Wire signal loop INTO Instantly webhooks** — add `LeadStatusManager.handle_*()` calls to `webhooks/instantly_webhook.py`
  - When to do: Before Phase 4E (Supervised Live Sends). No value until real emails are sent.
  - What: Import `LeadStatusManager`, call `handle_email_opened()` / `handle_email_replied()` / `handle_email_bounced()` / `handle_email_unsubscribed()` in each event handler.

- [ ] **Wire signal loop INTO HeyReach webhooks** — same pattern for `webhooks/heyreach_webhook.py`
  - When to do: After HeyReach subscription is active.

- [ ] **Bootstrap lead data** — visit `/leads` dashboard → click "Bootstrap Leads"
  - When to do: Anytime after Railway deploy (available now).

- [ ] **Schedule decay detection** — add `detect_engagement_decay()` to Inngest as daily cron
  - When to do: After live sends begin (Phase 4E).

---

### 4C: OPERATOR Agent Activation — TODO (DEFERRED)

> **Why deferred**: Building a unified dispatch abstraction over 1 active channel (Instantly) is premature engineering. Activate when HeyReach goes live and there are 2+ channels to unify.

- [ ] Create `execution/operator_outbound.py` — unified dispatch interface
- [ ] Move `instantly_dispatcher.py` under OPERATOR interface
- [ ] Add `heyreach_dispatcher.py` under OPERATOR interface
- [x] Update agent registry (module_path, description) — already points to `execution.operator_outbound`
- [x] Update agent permissions (Instantly + HeyReach actions) — 17 new actions
- [ ] QUEEN routing logic: ICP tier → channel selection
- [ ] GATEKEEPER approval gate for both channels

**Trigger to start**: When HeyReach 4B user actions are complete and LinkedIn is warmed.

---

### 4D: Multi-Channel Cadence (21-day) — TODO

Requires 4B (HeyReach live) + 4C (OPERATOR routing).

| Day | Channel | Action | Platform |
|-----|---------|--------|----------|
| 1 | Email | Personalized intro | Instantly |
| 2 | LinkedIn | Connection request | HeyReach |
| 3 | Phone | Call attempt #1 | GHL |
| 5 | Email | Value/case study | Instantly |
| 7 | LinkedIn | Message (if connected) | HeyReach |
| 10 | Email | Social proof | Instantly |
| 14 | LinkedIn | Voice message | HeyReach |
| 17 | Email | Break-up | Instantly |
| 21 | Email | Graceful close | Instantly |

---

### 4E: Supervised Live Sends — TODO (THE ACTUAL GOAL)

This is where `actually_send` flips to `true` and real outreach begins.

#### Prerequisites
- [x] 6 cold outreach domains DNS verified + warm-up complete
- [x] Internal test campaign sent via Instantly
- [ ] Wire signal loop into Instantly webhooks (4F remaining task)
- [ ] LinkedIn account warm-up complete (4 weeks) — requires 4B
- [ ] Shadow test via HeyReach completed (5 profiles) — requires 4B
- [ ] OPERATOR agent operational — requires 4C

#### Go-Live Checklist
- [ ] Enable `actually_send: true` for tier_1 only in `config/production.json`
- [ ] 3 days supervised operation (5 emails/day)
- [ ] Monitor KPIs: open rate ≥50%, reply rate ≥8%, bounce <5%
- [ ] Graduate to 25/day email ceiling
- [ ] Enable HeyReach LinkedIn sends (10 connections/day)

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

Based on current state (Phase 4, 65% complete), here's the critical path to live sends:

### Can Do RIGHT NOW (No Dependencies)

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 1 | **Wire signal loop into Instantly webhooks** | 30 min (code change) | Engagement data flows the moment live sends start |
| 2 | **Bootstrap lead data** from `/leads` dashboard | 2 min (click button) | Seed existing shadow email leads into signal loop |
| 3 | **Deploy + verify** `/leads` dashboard on Railway | 5 min | Confirm Monaco dashboard works in production |

### Requires Decision Before Proceeding

| # | Task | Decision Needed | Impact |
|---|------|----------------|--------|
| 4 | **Flip `actually_send: true`** for tier_1 | Are you ready for real emails to go out? Start with 5/day ceiling. | THE milestone — everything else is preparation for this |
| 5 | **Subscribe to HeyReach** | Approve $79/mo + use of personal LinkedIn account | Unblocks all of 4B, 4C, 4D |
| 6 | **Activate BetterContact** | Approve $15/mo for enrichment fallback | Improves data quality on Apollo misses |

### Future (Phase 5 Triggers)

| Task | Trigger |
|------|---------|
| Self-learning ICP calibration | 2 weeks of live send data |
| Multi-source intent fusion (RB2B + email + LinkedIn) | 30 days of send data |
| A/B testing infrastructure | 30 days of send data |
| Enrichment result caching (Supabase) | Apollo credits running low |
| CRO Copilot ("Ask" chat) | Lead volume exceeds 500+ |

---

## Key Decisions & Questions Per Phase

### Before Starting Phase 4E (Live Sends)

> These must be answered before `actually_send: true`:

1. **Daily send volume**: Start at 5/day for 3 days, then ramp to 25/day? Or different ramp?
2. **Tier restriction**: Start with tier_1 only (highest ICP fit)? Or include tier_2?
3. **Approval workflow**: Keep Gatekeeper manual approval for first 3 days? Or auto-approve tier_1?
4. **Bounce handling**: Auto-suppress bounced emails from future campaigns? (Currently appends to `.hive-mind/unsubscribes.jsonl`)
5. **Reply routing**: Where do replies go? Currently logged via Instantly webhook → classified by RESPONDER. Do you want Slack notifications per reply?

### Before Starting Phase 4B (HeyReach Activation)

1. **LinkedIn account**: Personal or company account? Personal has warmer connections but risks personal reputation.
2. **Campaign templates**: What messaging tone for LinkedIn? Same as email or more casual?
3. **Daily LinkedIn limit**: Start at 10 connections/day (conservative) or 20 (standard)?
4. **Instantly ↔ HeyReach sync**: Enable native bidirectional sync from day 1? Or keep channels independent initially?

### Before Starting Phase 4C (OPERATOR Unification)

1. **Channel routing logic**: tier_1 gets email + LinkedIn, tier_2 gets email only, tier_3 gets email only? Or different?
2. **GHL inclusion**: Route nurture/follow-up through GHL as third channel? Or keep GHL manual?

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
*For full implementation details, see `CAIO_IMPLEMENTATION_PLAN.md` (v3.6).*
*For signal loop activation steps, see `docs/MONACO_SIGNAL_LOOP_GUIDE.md`.*
