# CAIO Alpha Swarm — Unified Implementation Plan

**Last Updated**: 2026-02-27 (v4.6 — Sprint 3: Clay fallback re-enabled, TDD testing complete, HeyReach tests, pre-commit hook)
**Owner**: ChiefAIOfficer Production Team
**AI**: Claude Opus 4.6

---

## Executive Summary

The CAIO Alpha Swarm is a 12-agent autonomous SDR pipeline: Lead Discovery (Apollo.io) -> Enrichment (Apollo + fallback) -> ICP Scoring -> Email Crafting -> Approval -> Send (Instantly.ai). This plan tracks all phases from foundation through production autonomy.

**Current Position**: Phase 4 (Autonomy Graduation) — IN PROGRESS
**Production Pipeline**: 6/6 stages PASS with real Apollo data (8-68s end-to-end)
**Autonomy Score**: ~98/100
**Total Production Runs**: 33+ (22 fully clean, last 10 consecutive 6/6 PASS)

```
Phase 0: Foundation Lock          [##########] 100%  COMPLETE
Phase 1: Live Pipeline Validation [##########] 100%  COMPLETE
Phase 2: Supervised Burn-In       [##########] 100%  COMPLETE
Phase 3: Expand & Harden          [##########] 100%  COMPLETE
Phase 4: Autonomy Graduation      [#########.]  98%  IN PROGRESS (4A+4C+4D+4F+4G+4I+4J+4K COMPLETE, 4B infra done, 4E ramp active, 4H in progress)
```

---

## Phase 0: Foundation Lock — COMPLETE

All core infrastructure deployed and validated.

| Task | Status | Notes |
|------|--------|-------|
| 12-agent architecture (Queen + 11 agents) | DONE | All agents instantiated |
| 6-stage pipeline (scrape/enrich/segment/craft/approve/send) | DONE | `execution/run_pipeline.py` |
| FastAPI dashboard on port 8080 | DONE | `dashboard/health_app.py` |
| Redis (Upstash) integration | DONE | 62ms from Railway, 1392ms local |
| Inngest event-driven functions | DONE | 5 functions mounted (incl. daily_decay_detection cron) |
| Railway deployment | DONE | Auto-deploy on git push |
| Safety controls (shadow mode, EMERGENCY_STOP) | DONE | `config/production.json` |
| Gatekeeper approve/reject/edit flows | DONE | Full audit trail in `.hive-mind/audit/` |
| Circuit breaker system | DONE | `core/circuit_breaker.py` |
| Context zone monitoring (SMART/CAUTION/DUMB/CRITICAL) | DONE | `core/context.py` |

---

## Phase 1: Live Pipeline Validation — COMPLETE

Sandbox pipeline validated end-to-end (3 consecutive clean runs, 0 errors).

| Run | Source | Leads | Stages | Duration |
|-----|--------|-------|--------|----------|
| `run_20260213_043832_928cf2` | competitor_gong | 5 | 6/6 PASS | 7ms |
| `run_20260213_043838_a09487` | event_saastr | 5 | 6/6 PASS | 7ms |
| `run_20260213_043845_b01cdf` | default | 10 | 6/6 PASS | 9ms |

---

## Phase 2: Supervised Burn-In — COMPLETE

Production pipeline validated with real Apollo data. All critical blockers resolved.

### 2A: Blocker Resolution

| Blocker | Resolution | Date |
|---------|-----------|------|
| LinkedIn Scraper 403 (cookie blocked) | Replaced with Apollo.io People Search (free) + People Match (1 credit/reveal) | 2026-02-13 |
| Clay API v1 deprecated (404) | Replaced with direct Apollo.io enrichment | 2026-02-13 |
| Slack alerting not configured | Webhook configured, WARNING + CRITICAL alerts working | 2026-02-13 |

### 2B: Production Pipeline Results (Real Data)

| Stage | Status | Detail | Duration |
|-------|--------|--------|----------|
| Scrape | PASS | 5 leads via Apollo People Search | 7.3s |
| Enrich | PASS | 5/5 enriched via Apollo People Match | 4.7s |
| Segment | PASS | ICP scoring with real data | 9ms |
| Craft | PASS | 1 campaign created | 56ms |
| Approve | PASS | Auto-approve | 0ms |
| Send | PASS | 5 emails queued to shadow_mode_emails | 2ms |
| **Total** | **6/6 PASS** | | **12.1s** |

### 2C: Bugfixes Applied

| Bug | Fix | File |
|-----|-----|------|
| Apollo `reveal_phone_number` requires `webhook_url` (400) | Removed `reveal_phone_number: True` from payload | `enricher_waterfall.py` (formerly `enricher_clay_waterfall.py`) |
| Segmentor `NoneType has no attribute 'lower'` | Changed to `(lead.get("title") or "").lower()` pattern | `segmentor_classify.py` (3 locations) |
| Segmentor `employee_count` None crash | Changed to `lead.get("company", {}).get("employee_count") or 0` | `segmentor_classify.py` |
| Segmentor email only checking `work_email` | Added fallback chain: `work_email` OR `verified_email` OR top-level `email` | `segmentor_classify.py` |
| Send stage broken Instantly import | Rewrote to queue shadow emails for HoS dashboard approval | `run_pipeline.py` |
| CampaignCrafter requires `first_name` but pipeline has `name` | Added name normalization in `_stage_craft()`: splits `name` → `first_name`/`last_name` | `run_pipeline.py` |
| Circuit breaker state transitions silent | Wired OPEN/recovery alerts to Slack via `core/alerts.py` | `circuit_breaker.py` |
| Pipeline stage failures not alerted | Added `send_warning` on stage failure, `send_critical` on exception | `run_pipeline.py` |

---

## Phase 3: Expand & Harden — COMPLETE

### Completed Tasks

| Task | Status | Notes |
|------|--------|-------|
| Apollo two-step flow (Search -> Match) | DONE | Free search + 1 credit/reveal |
| Segmentor NoneType bugfix | DONE | title/industry/employee_count null-safe |
| Enrichment provider research (28+ providers) | DONE | [ENRICHMENT_PROVIDER_RESEARCH_2026.md](docs/research/ENRICHMENT_PROVIDER_RESEARCH_2026.md) |
| Proxycurl removal from scraper | DONE | `_fetch_via_proxycurl` method deleted |
| Proxycurl removal from enricher | DONE | All Proxycurl code replaced with BetterContact |
| BetterContact fallback code integration | DONE | Async polling in `enricher_waterfall.py` (formerly `enricher_clay_waterfall.py`) |
| Clay workbook research | DONE | Explorer plan active, async webhooks |
| Multi-channel cadence research | DONE | [MULTI_CHANNEL_CADENCE_RESEARCH_2026.md](docs/research/MULTI_CHANNEL_CADENCE_RESEARCH_2026.md) |
| Clay pipeline fallback — REMOVED | DONE | `lead_id` not accessible in Clay HTTP callback → 3-min guaranteed timeouts. Clay kept for RB2B visitor enrichment ONLY |
| `/webhooks/clay` handler simplified | DONE | RB2B visitor path only (pipeline lead path removed) |
| Pipeline waterfall: Apollo -> BC -> mock | DONE | No Clay in pipeline enrichment |
| Railway deployment (all fixes) | DONE | Build successful |
| Send stage rewrite | DONE | Shadow mode email queue for HoS dashboard approval (Instantly import removed) |
| Pipeline alerts → Slack | DONE | Stage failures → WARNING, exceptions → CRITICAL |
| Circuit breaker alerts → Slack | DONE | OPEN/recovery transitions alerted |
| Segmentor email resolution fix | DONE | Fallback chain: work_email → verified_email → top-level email |
| first_name normalization | DONE | Pipeline splits `name` → `first_name`/`last_name` before craft |
| 3 consecutive clean production runs | DONE | 6/6 PASS x3, 0 errors each |
| 20-lead scale test | DONE | 19 enriched, 2 campaigns, 68.4s, 0 errors |
| Dashboard API E2E test | DONE | approve/reject/pending flows verified with real data |
| Google Calendar setup guide | DONE | `docs/GOOGLE_CALENDAR_SETUP_GUIDE.md` + `scripts/setup_google_calendar.py` |
| GHL Calendar integration | DONE | Replaced Google Calendar with GHL Calendar API in scheduler agent. Zero new dependencies. |

### 3A-Assessment: Clay in Pipeline — RE-ENABLED (Phase 4K)

**Original finding**: Clay HTTP API callback does NOT include the `lead_id` field, causing guaranteed 3-minute timeouts. Clay was removed from pipeline in Phase 3.

**Resolution (Phase 4K, commit `a0d91b4`)**: Bypassed `lead_id` limitation using Redis LinkedIn URL correlation. Before sending to Clay, pipeline stores `linkedin_hash → {lead_id, request_id}` in Redis. Railway callback handler extracts LinkedIn URL from Clay response, looks up correlation, stores result for pipeline polling.

**Pipeline enrichment waterfall (current)**:
1. Apollo.io People Match (primary, synchronous, 1 credit/reveal)
2. BetterContact (fallback, async polling — code ready, subscription pending)
3. Clay Explorer (fallback, async callback + Redis correlation — feature-flagged `CLAY_PIPELINE_ENABLED`)
4. Graceful skip (lead continues without enrichment)

**Clay usage**:
- **Pipeline leads**: Waterfall position 3, Redis LinkedIn URL correlation, `/api/clay-callback` handler
- **RB2B visitors**: Clay workbook webhook → enrichment columns → HTTP callback to `/webhooks/clay`

### Completed (Final)

| Task | Status | Notes |
|------|--------|-------|
| Deploy GHL calendar + latest fixes to Railway | DONE | Deployed 2026-02-14 (commit 348ad84) |
| Hit 10+ clean production runs | DONE | 10 consecutive 6/6 PASS achieved |
| Instantly V2 API migration | DONE | server.py rewrite, dispatcher orphan fix, webhook suppression JSONL |

### Deferred Tasks

| Task | Status | Reason |
|------|--------|--------|
| BetterContact Starter subscription | DEFERRED | Code ready, activate when Apollo miss rate justifies $15/mo |
| FullEnrich integration | DEFERRED | BetterContact preferred as first fallback |
| ZeroBounce email verification layer | DEFERRED | Add when real sends begin (pre-send verification) |
| Supabase Lead 360 view | DEFERRED | Need unified lead schema first |
| Job change detection (Bombora/G2) | DEFERRED | Phase 5+ |
| Clay pipeline enrichment fallback | RE-ENABLED | Redis LinkedIn URL correlation bypasses `lead_id` limitation (Phase 4K) |

---

### 3A: Enrichment Architecture — CURRENT

**Pipeline Enrichment Waterfall**:
```
Apollo.io People Match (primary, sync, 1 credit/reveal)
  -> miss -> BetterContact async poll (fallback, code ready)
    -> miss -> Clay Explorer async callback (fallback, Redis LinkedIn correlation)
      -> miss -> graceful skip (lead continues without enrichment)
```

**Clay Explorer** ($499/mo, 14K credits/mo): Used for **RB2B visitor enrichment only**.
```
RB2B Visitor webhook
  -> Clay Workbook (waterfall: Hunter->Apollo->Prospeo->DropContact)
  -> HTTP API callback -> POST /webhooks/clay
  -> GHL sync + Website Intent Monitor
```

**Why Clay was removed from pipeline**: Clay HTTP API callback does not pass through the `lead_id` field, making it impossible to correlate enriched data back to the pipeline lead. This caused a guaranteed 3-minute timeout on every lead. Apollo synchronous enrichment is faster (2-5s) and more reliable.

### 3C: Production Stability Results

| Run | Mode | Leads | Stages | Duration | Errors |
|-----|------|-------|--------|----------|--------|
| `232408_bd1c74` | production | 5 | 6/6 PASS | 12.1s | 0 |
| `233340_89c546` | production | 5 | 6/6 PASS | 15.0s | 0 |
| `233407_aaa29c` | production | 5 | 6/6 PASS | 19.8s | 0 |
| `233523_3b4913` | production | 19 | 6/6 PASS | 68.4s | 0 |

**Dashboard API E2E**: Approve/reject/pending flows verified with real pipeline data.

---

### 3B: Multi-Channel Cadence — ARCHITECTURE PLAN

**Recommendation**: HeyReach ($79/mo/sender) + Instantly.ai (existing) with native bidirectional sync.

**Research Summary** (full report: [MULTI_CHANNEL_CADENCE_RESEARCH_2026.md](docs/research/MULTI_CHANNEL_CADENCE_RESEARCH_2026.md)):

| Tool | Type | Price | API | Instantly Native |
|------|------|-------|-----|-----------------|
| **HeyReach** (recommended) | LinkedIn automation | $79/mo/sender | Full REST + webhooks | Yes (bidirectional) |
| Lemlist | Multi-channel (replaces Instantly) | $99/user/mo | Full REST | No |
| La Growth Machine | Multi-channel + Twitter | EUR 120/mo | Partial | No |

**Cadence Template (21-day)**:
```
Day 1:  Email #1 (personalized intro)
Day 2:  LinkedIn connection request
Day 3:  Phone call attempt #1
Day 5:  Email #2 (value/case study)
Day 7:  LinkedIn message (if connected)
Day 10: Email #3 (social proof)
Day 14: LinkedIn voice message
Day 17: Email #4 (break-up)
Day 21: Email #5 (graceful close)
```

**LinkedIn Safety**:
- Max 20-25 connection requests/day
- 4-week warm-up mandatory for new accounts
- Cloud-based tools only (no browser extensions)
- Sender rotation across multiple accounts

**Implementation**: Phase 4+ (requires warm LinkedIn accounts, HeyReach subscription, pipeline channel router)

---

## Phase 4: Autonomy Graduation — IN PROGRESS

### 4A: Domain & Instantly Go-Live — COMPLETE

**Domain Strategy**: 6 dedicated cold outreach domains + isolated nurture domain.

| Channel | Domains | Platform | Purpose |
|---------|---------|----------|---------|
| Cold outreach | `chiefaiofficerai.com`, `chiefaiofficerconsulting.com`, `chiefaiofficerguide.com`, `chiefaiofficerlabs.com`, `chiefaiofficerresources.com`, `chiefaiofficersolutions.com` | Instantly V2 | Cold emails, 6 accounts rotating |
| Nurture/inbound | `chiefai.ai` | GHL (LC Email) | Warm leads, follow-ups, booking confirmations (Stage 1 warmup, 8%) |

| Task | Status | Notes |
|------|--------|-------|
| Instantly V2 API migration (server.py, dispatcher, webhooks) | DONE | Bearer auth, cursor pagination, CRITICAL fixes C1-C4 |
| Fix `email_list` bug in `create_campaign()` | DONE | V2 sending accounts were silently ignored — now passed in API payload |
| Multi-account rotation config in production.json | DONE | `sending_accounts.primary_from_emails` — 6 accounts, round-robin |
| Webhook handler V2 cleanup | DONE | `activate_campaign()` replaces `pause_campaign("resume")` |
| CLAUDE.md dual-platform strategy update | DONE | Instantly re-added, domain isolation table, OPERATOR role |
| INSTANTLY.md V2 documentation rewrite | DONE | 445 lines — endpoints, payloads, domains, agents, dispatcher |
| Domain strategy config in production.json | DONE | `sending_accounts`, `domain_strategy`, `dedicated_domains` blocks |
| All code files verified (AST + JSON parse) | DONE | server.py, dispatcher.py, webhook.py, health_app.py, production.json, permissions.json |
| Generate Instantly V2 API key | DONE | V2 key working — `/api/instantly/campaigns` returns data |
| Set `INSTANTLY_API_KEY` (V2) in Railway | DONE | Confirmed: endpoint returns `{"campaigns":[],"count":0}` |
| Deploy V2 code to Railway | DONE | Commit `53ab1c1` — Instantly routes, dispatcher, webhooks all live |
| 6 cold outreach domains DNS (SPF, DKIM, DMARC) | DONE | All 6 accounts verified green (100% health) in Instantly dashboard |
| Instantly warm-up complete | DONE | 10 warmup emails/account, 100% health score across all 6 accounts |
| Fix production.json domain mismatch | DONE | Updated from old placeholder domains to actual 6 chris.d@ accounts |
| Set `INSTANTLY_FROM_EMAIL` in Railway | DONE | `chris.d@chiefaiofficerai.com` — Apply 1 change + Deploy pending |
| GHL dedicated domain (`chiefai.ai`) | DONE | Stage 1 warmup (8%), Shared IP, SSL Issued (added 02/08/2026) |
| Send 1 internal test campaign through Instantly | DONE | `test_internal_v2_20260215` — Active, 1 lead (josh@chiefaiofficer.com), sending via schedule |
| Register Instantly webhooks | DONE | 4/4 registered: reply, bounce, open, unsubscribe → Railway dashboard |

### 4B: HeyReach LinkedIn Integration

**Status**: API verified, 4 webhooks registered, signal loop wired, 3 campaign templates created (Drafted). Awaiting: LinkedIn warm-up + bidirectional sync for live sends.

| Task | Status | Notes |
|------|--------|-------|
| Subscribe to HeyReach Growth ($79/mo, 1 sender) | DONE | API key generated, 19 existing campaigns visible |
| Connect LinkedIn account + warm-up (4 weeks) | TODO | 20-25 connections/day ramp — USER ACTION |
| Build 3 campaign templates in HeyReach UI | DONE | Tier 1 (334314): Connection→Message(1d)→Follow-up(7d). Tier 2 (334364): Connection→Message(1d)→End. Tier 3 (334381): Connection only→End. All saved as Draft. |
| Set `HEYREACH_API_KEY` in Railway + .env | DONE | Verified via `CheckApiKey` (HTTP 200). Health endpoint confirms `api_key_configured: true` |
| Create `execution/heyreach_dispatcher.py` | DONE | API client + lead-list-first safety, daily ceiling (20/day), CLI with --dry-run |
| Create `webhooks/heyreach_webhook.py` | DONE | 11 event handlers, JSONL logging, follow-up flags, Slack alerts |
| Mount HeyReach webhook in dashboard | DONE | `dashboard/health_app.py` — router included after Instantly |
| Create `scripts/register_heyreach_webhooks.py` | DONE | Rewritten to utility: --check-auth, --list-campaigns, --list-accounts, --print-guide (webhook CRUD is UI-only) |
| Register HeyReach webhooks → `/webhooks/heyreach` | DONE | 4 webhooks created in HeyReach UI: Connection Sent, Connection Accepted, Reply Received, Campaign Completed |
| Wire signal loop into HeyReach webhook handlers | DONE | `LeadStatusManager` calls in connection_sent, connection_accepted, reply, campaign_completed handlers |
| Configure native HeyReach ↔ Instantly bidirectional sync | DONE | Instantly API key in HeyReach + HeyReach connected in Instantly ("My Connection", 2/16/2026) |
| Wire CONNECTION_REQUEST_ACCEPTED → Instantly warm follow-up | DONE | Webhook handler writes flag file, dispatcher reads it |
| Map campaign IDs to `config/production.json` | DONE | tier_1: 334314, tier_2: 334364, tier_3: 334381 — mapped in config with sequence descriptions |
| Shadow test with 5 internal LinkedIn profiles | TODO | Validate before real outreach — USER ACTION |

**HeyReach API Discoveries**:
- Webhook CRUD is **UI-only** — no API endpoints exist (all paths return 404)
- `/linkedinaccount/GetAll` returns 404 — not available on all plans
- `aiohttp` requires `content_type=None` on all `.json()` calls (HeyReach omits Content-Type header)
- 19 existing campaigns visible, including "HeyReach to GHL CAIO ABM High ICP" (ID: 291587)

**HeyReach API Reference**:
- Base URL: `https://api.heyreach.io/api/public`
- Auth: `X-API-KEY` header
- Rate limit: 300 req/min
- CRITICAL: Adding leads to paused campaign auto-reactivates it → use lead-list-first pattern

### 4C: OPERATOR Agent Activation — BUILT

**Design**: OPERATOR is the unified outbound execution layer + GHL revival engine.

```
QUEEN (orchestrator)
  → GATEKEEPER (approve)
    → OPERATOR (execute)
       ├── dispatch_outbound()
       │   ├── InstantlyDispatcher (email: 25/day, 6 warmed domains)
       │   └── HeyReachDispatcher (LinkedIn: 5/day warmup → 20/day full)
       ├── dispatch_revival()
       │   ├── RevivalScanner (GHL cache → stale contacts)
       │   └── InstantlyDispatcher (warm domains, re-engagement)
       └── dispatch_all() → both motions sequentially
```

| Task | Status | Notes |
|------|--------|-------|
| Create `execution/operator_outbound.py` | DONE | OperatorOutbound: dispatch_outbound, dispatch_revival, dispatch_all, get_status, WarmupSchedule, CLI |
| Create `execution/operator_revival_scanner.py` | DONE | RevivalScanner: scan, score, context builder. Reads GHL cache, uses ActivityTimeline |
| Wire InstantlyDispatcher under OPERATOR | DONE | Sequential: Instantly first, then HeyReach |
| Wire HeyReachDispatcher under OPERATOR | DONE | Warmup-aware: 5/day weeks 1-4, 20/day weeks 5+ |
| Update agent registry (module_path, description) | DONE | Points to `execution.operator_outbound` |
| Update agent permissions (Instantly + HeyReach actions) | DONE | 17 new allowed actions for OPERATOR |
| Tier → channel routing config | DONE | tier_1: email+LinkedIn, tier_2: email+LinkedIn, tier_3: email only |
| Add 3 revival statuses to lead_signals.py | DONE | revival_candidate, revival_queued, revival_sent + is_revivable() |
| Add get_revival_context() to activity_timeline.py | DONE | Context builder for CRAFTER re-engagement copy |
| Add GHL cache search methods to ghl_local_sync.py | DONE | search_by_tags, search_by_pipeline_stage, get_stale_contacts |
| Add operator config to production.json | DONE | Warmup dates, tier routing, revival config (30-120 day window) |
| Add /api/operator/* dashboard endpoints | DONE | status, revival-candidates, trigger, history |
| Three-layer deduplication | DONE | OperatorDailyState + LeadStatusManager + shadow email flags |
| GATEKEEPER approval gate for both channels | DONE | Batch approval flow: create_batch → approve/reject → execute. 3 dashboard endpoints. Slack alert on creation. |

### 4D: Multi-Channel Cadence — COMPLETE (Engine + CRAFTER + Auto-Enroll)

**Status**: Full cadence system operational. Phone/GHL calls deferred per user directive.

| Task | Status | Notes |
|------|--------|-------|
| `execution/cadence_engine.py` — CadenceEngine class | DONE | enroll/due/mark_done/sync/pause/resume/exit |
| Cadence config in `production.json` | DONE | 8-step sequence, exit/pause conditions |
| `dispatch_cadence()` in OPERATOR | DONE | Processes follow-up steps for enrolled leads |
| 4 `/api/cadence/*` dashboard endpoints | DONE | summary, due, leads, sync |
| OPERATOR `--motion cadence` CLI | DONE | Full dry-run tested |
| CRAFTER follow-up templates for Steps 3/5/7/8 | DONE | 4 templates: value_followup, social_proof, breakup, close |
| Auto-enroll leads on first OPERATOR dispatch | DONE | `_auto_enroll_to_cadence()` in OPERATOR, `cadence_enrolled` flag |
| Phone/GHL calls (Day 3) | DEFERRED | Add when complexity budget allows |

**Simplified Sequence (Email + LinkedIn only, warmup-safe):**

| Step | Day | Channel | Action | Condition |
|------|-----|---------|--------|-----------|
| 1 | 1 | Email | Personalized intro | Always |
| 2 | 2 | LinkedIn | Connection request | has_linkedin_url |
| 3 | 5 | Email | Value/case study | not_replied |
| 4 | 7 | LinkedIn | Direct message | linkedin_connected |
| 5 | 10 | Email | Social proof | not_replied |
| 6 | 14 | LinkedIn | Follow-up message | linkedin_connected |
| 7 | 17 | Email | Break-up | not_replied |
| 8 | 21 | Email | Graceful close | not_replied |

### 4E: Supervised Live Sends — RAMP MODE ACTIVE

### Prerequisites
- [x] 6 cold outreach domains DNS verified + warm-up complete (all 100% health)
- [x] Internal test campaign sent successfully via Instantly (`test_internal_v2_20260215`)
- [x] Signal loop wired into Instantly + HeyReach webhooks
- [x] OPERATOR agent operational (unified dispatch + revival + cadence)
- [x] Cadence engine built and tested
- [ ] LinkedIn account warm-up complete (4 weeks) — requires 4B
- [ ] Shadow test via HeyReach completed (5 profiles) — requires 4B
- [x] GATEKEEPER approval gate for OPERATOR dispatch — batch approval + 3 endpoints (commit `bcd3815`)

### Deployed (commit `87225fa`)

| Task | Status | Notes |
|------|--------|-------|
| Fix Instantly V2 timezone bug | DONE | `America/New_York` → `America/Detroit` (API whitelist quirk) |
| Fix cadence engine encoding bug | DONE | Unicode `→` → ASCII `->` (Windows cp1252) |
| Ramp configuration | DONE | `operator.ramp`: 5/day, tier_1, 3 supervised days |
| Wire ramp into OPERATOR | DONE | Limit override + tier filter + batch preview + status display |
| `actually_send` semantics clarified | DONE | Governs dashboard direct GHL send behavior only; OPERATOR path is controlled by `--live` + Gatekeeper + OPERATOR config |
| Deploy to Railway | DONE | Ramp active, verified via `/api/operator/status` |

### HoS Requirements Integration (2026-02-18)

| Task | Status | Notes |
|------|--------|-------|
| Ingest HoS requirements document | DONE | `docs/google_drive_docs/HEAD_OF_SALES_REQUIREMENTS 01.26.2026 (1).docx` — full text extracted |
| Update CLAUDE.md with HoS Email Crafting Reference | DONE | 11 angles, ICP tiers, follow-ups, objections, signature, exclusions |
| Rewrite CRAFTER templates (11 HoS angles) | DONE | `crafter_campaign.py` — Fractional CAIO positioning, M.A.P.™ Framework, CAN-SPAM footer |
| Update segmentor ICP scoring | DONE | HoS title/industry lists, multipliers (1.5x/1.2x), threshold 80 |
| Add customer exclusion lists | DONE | 7 domains + 27 emails from HoS Section 1.4 in `production.json` |
| Add dispatcher Guard 4 | DONE | Individual email exclusion in `instantly_dispatcher.py` |
| Update TARGET_COMPANIES | DONE | HoS Tier 1 ICP: agencies, staffing, consulting, e-commerce |
| Update ramp config | DONE | tier_filter: tier_1, start_date: 2026-02-18 |
| Update sender info | DONE | Dani Apgar, Chief AI Officer, caio.cx booking link |

### Remaining (Operational — User Action Required)

| Task | Status | Notes |
|------|--------|-------|
| Run pipeline with HoS Tier 1 targets | TODO | Agency/consulting/staffing companies (51-500 employees) |
| Approve tier_1 leads in HoS dashboard | TODO | `/sales` → review + approve |
| First live dispatch via OPERATOR | TODO | `--motion outbound --live` → GATEKEEPER → approve → dispatch |
| 3 days supervised operation (5 emails/day) | TODO | Monitor delivery, opens, bounces |
| Monitor: open rate ≥50%, reply rate ≥8%, bounce <5% | TODO | Dashboard KPI tracking |
| Graduate: `ramp.enabled: false` → 25/day + all tiers | TODO | After 3 clean days |
| Enable HeyReach LinkedIn sends (5 connections/day) | TODO | After LinkedIn warm-up complete |

### HoS Deep Review Validation (commit `10cc82c` handoff verification)

**Review context**: `docs/CODEX_HANDOFF_HOS_REVIEW.md` is dated 2026-02-18. Local code verification + fixes were executed on 2026-02-17 against the current working tree.

#### Verified and Fixed (pre-live)

| Item | Status | Outcome | Files |
|------|--------|---------|-------|
| B1 follow-up A/B subjects duplicated | FIXED | HoS follow-up templates now have distinct `subject_a` / `subject_b` variants; rendering uses fallback-safe key resolution | `execution/crafter_campaign.py` |
| B5 intent+engagement score inflation | FIXED | Social engagement bonus now stays inside the 20-point intent cap (`intent_signals`) | `execution/segmentor_classify.py` |
| B11 subdomain exclusion gap | FIXED | Recipient domain guard now matches apex + subdomains (e.g., `sub.domain.com` matches `domain.com`) | `execution/instantly_dispatcher.py` |
| B22 cadence dry-run mutating state | FIXED | Dry-run cadence no longer marks steps done or saves daily state side effects | `execution/operator_outbound.py` |
| B23 cadence auto-enroll channel gap | FIXED | Auto-enroll now supports first-touch status from Instantly and HeyReach | `execution/operator_outbound.py` |

#### Verified as Not Reproducible / Already Covered

| Item | Status | Notes |
|------|--------|-------|
| B10 `bulk_pause_all()` missing | NOT REPRODUCED | `AsyncInstantlyClient.bulk_pause_all()` exists in `mcp-servers/instantly-mcp/server.py` and is callable from dispatcher emergency-stop path |

#### Residual Risk to Address Before Full-Autonomy (non-blocking for supervised ramp if monitored)

| Risk | Severity | Recommended Action |
|------|----------|--------------------|
| `/sales` and `/leads` HTML routes are publicly reachable (API data still token-protected) | LOW-MEDIUM | Decide policy: keep internal-open + API-protected, or enforce token on page routes |

#### HoS Regression Gate (added)

| Gate | Command | Result |
|------|---------|--------|
| HoS regression tests | `python -m pytest -q tests/test_hos_integration_regressions.py` | **PASS** |
| Webhook + edge-case hardening tests | `python -m pytest -q tests/test_webhook_signature_enforcement.py tests/test_hos_integration_regressions.py` | **PASS** |
| Expanded critical pack (incl. HoS + auth + webhook hardening) | `python -m pytest -q tests/test_gatekeeper_integration.py tests/test_runtime_reliability.py tests/test_runtime_determinism_flows.py tests/test_trace_envelope_and_hardening.py tests/test_replay_harness_assets.py tests/test_operator_batch_snapshot_integrity.py tests/test_operator_dedup_and_send_path.py tests/test_state_store_redis_cutover.py tests/test_hos_integration_regressions.py tests/test_webhook_signature_enforcement.py tests/test_instantly_webhook_auth.py` | **PASS** (77 passed) |
| Replay Gate | `python scripts/replay_harness.py --min-pass-rate 0.95` | **PASS** (50/50, `pass_rate=1.0`, `block_build=false`) |

#### Pre-Live Evaluation + Edge-Case Matrix (must keep running before real live testing)

| Edge Case | Status | Automated Coverage |
|-----------|--------|--------------------|
| `EMERGENCY_STOP` during live dispatch | COVERED | `tests/test_hos_integration_regressions.py::test_emergency_stop_blocks_live_dispatch_before_channel_calls` |
| Subdomain exclusions (`user@sub.customer.com`) | COVERED | `tests/test_hos_integration_regressions.py::test_excluded_domain_guard_blocks_subdomains` |
| Individual excluded email rejection | COVERED | `tests/test_hos_integration_regressions.py::test_excluded_email_guard_logs_structured_rejection` |
| Cadence dry-run must not mutate state | COVERED | `tests/test_hos_integration_regressions.py::test_dispatch_cadence_dry_run_has_no_state_side_effects` |
| Gatekeeper queue drift after approval | COVERED | `tests/test_operator_batch_snapshot_integrity.py::test_approved_batch_executes_only_frozen_scope` |
| Re-run executed batch must not resend | COVERED | `tests/test_operator_batch_snapshot_integrity.py::test_approved_batch_executes_only_frozen_scope` |
| `sent_via_ghl` excluded from Instantly/HeyReach | COVERED | `tests/test_operator_dedup_and_send_path.py::test_instantly_loader_excludes_sent_via_ghl`, `tests/test_hos_integration_regressions.py::test_heyreach_loader_excludes_sent_via_ghl` |
| Query-token and header-token auth parity | COVERED | `tests/test_runtime_reliability.py::test_protected_api_endpoints_require_dashboard_token`, `tests/test_instantly_webhook_auth.py::test_instantly_control_endpoints_require_token_when_configured` |
| CORS preflight (`OPTIONS`) on protected APIs | COVERED | `tests/test_runtime_reliability.py::test_protected_api_endpoints_require_dashboard_token` |
| Redis lock contention on concurrent live motions | COVERED | `tests/test_state_store_redis_cutover.py::test_operator_lock_disallows_concurrent_live_runs` |
| Intent-heavy + social-source score cap behavior | COVERED | `tests/test_hos_integration_regressions.py::test_intent_plus_engagement_respects_20_point_cap` |
| Follow-up A/B subject variation rendering | COVERED | `tests/test_hos_integration_regressions.py::test_followup_subject_variants_are_distinct` |

### KPI Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| ICP Match Rate | ≥ 80% | Enriched leads matching ICP criteria |
| Email Open Rate | ≥ 50% | Instantly analytics |
| Reply Rate | ≥ 8% | Instantly + HeyReach combined |
| Bounce Rate | < 5% | Instantly analytics |
| LinkedIn Accept Rate | ≥ 30% | HeyReach stats |
| Autonomous Days | 3 consecutive | No manual intervention needed |

### 4F: Monaco-Inspired Intelligence Layer

**Inspiration**: [Monaco.com](https://www.monaco.com) — AI-native revenue engine ($35M Series A, Feb 2026). Key lesson: pipelines should be feedback LOOPS, not lines. Leads generate engagement signals that feed back into scoring and next-action decisions.

**Status**: COMPLETE. Dashboard live at `/leads`. Daily decay cron running via Inngest.

| Task | Status | Notes |
|------|--------|-------|
| **Signal Loop**: Webhook events update lead status | DONE | `core/lead_signals.py` — LeadStatusManager with 21 statuses (incl. revival) |
| **Ghosting Detection**: 72h no open → "ghosted" | DONE | `detect_engagement_decay()` — time-based rules |
| **Stall Detection**: 7d opened, no reply → "stalled" | DONE | On demand via `POST /api/leads/detect-decay` + daily Inngest cron (10 AM UTC) |
| **Engaged-Not-Replied**: 2+ opens, 0 replies → "hesitant" | DONE | Automatic pattern detection |
| **"Why This Score" Explainability** | DONE | `scoring_reasons` field in segmentor output (human-readable) |
| **Unified Activity Timeline** | DONE | `core/activity_timeline.py` — aggregates all channels per lead |
| **Pipeline Funnel Visualization** | DONE | 5-stage flow on `/leads` dashboard (Pipeline→Outreach→Engaged→At Risk→Terminal) |
| **Lead Dashboard** | DONE | `dashboard/leads_dashboard.html` — filterable lead list + click-to-expand timeline |
| **API Endpoints** | DONE | `/api/leads`, `/api/leads/funnel`, `/api/leads/{email}/timeline`, `/api/leads/detect-decay` |
| Wire signal loop INTO Instantly webhook handlers | DONE | reply→`handle_email_replied`, bounce→`handle_email_bounced`, open→`handle_email_opened`, unsub→`handle_email_unsubscribed` |
| Wire signal loop INTO HeyReach webhook handlers | DONE | connection_sent/accepted→`handle_linkedin_*`, reply→`handle_linkedin_reply`, campaign_completed→`linkedin_exhausted` |
| CRO Copilot ("Ask" chat interface) | DEFERRED | Low priority at current volume (<100 leads) |
| Meeting Intelligence (auto note-taking) | DEFERRED | Phone outreach not live yet (Phase 4D) |

**Monaco Concepts Adopted**:
- Signal-based pipeline progression (engagement drives status, not rep hygiene)
- Self-maintaining lead records (webhooks auto-update, no manual data entry)
- Explainable scoring ("why this account" reasoning per lead)
- Unified activity capture (email + LinkedIn + pipeline events in one timeline)
- Human-guided agents (Gatekeeper approval gate = Monaco's human review layer)

**Monaco Concepts Rejected**:
- Proprietary prospect database (we rent Apollo — correct at our scale)
- CRO Copilot (unnecessary at <100 leads)
- Replace CRM (GHL works, "Rent the Pipes")

### 4G: Production Hardening Patch Train (P0) — COMPLETE (v4.4)

**Objective**: close P0 reliability/security gaps before autonomy progression and Golden Set replay at scale.

#### Completed Patch Table (P0-A through P0-E)

| Patch | Status | Outcome | Primary Files |
|------|--------|---------|---------------|
| **P0-A: API Auth Hardening (strict)** | DONE | Protected `/api/*` endpoints now require token via query (`token`) or header (`X-Dashboard-Token`); health allowlist remains unauthenticated; legacy token bypass removed (including Instantly control router) | `dashboard/health_app.py`, `dashboard/hos_dashboard.html`, `dashboard/leads_dashboard.html`, `webhooks/instantly_webhook.py` |
| **P0-B: Gatekeeper Snapshot Integrity** | DONE | `DispatchBatch` now carries immutable approved scope (`approved_*`), `preview_hash`, `expires_at`; execution validates scope/hash/expiry and is one-time idempotent | `execution/operator_outbound.py`, `execution/instantly_dispatcher.py`, `execution/heyreach_dispatcher.py` |
| **P0-C: Duplicate-Send + Dedup Corrections** | DONE | Dashboard GHL send success now writes terminal `status=sent_via_ghl`; Instantly/HeyReach loaders exclude GHL-sent leads; OPERATOR dedup migrated to canonical email keys with legacy compatibility | `dashboard/health_app.py`, `execution/operator_outbound.py`, `execution/instantly_dispatcher.py`, `execution/heyreach_dispatcher.py` |
| **P0-D: Redis State Source-of-Truth (dual-read cutover)** | DONE | New Redis-backed state layer introduced for operator daily state, batches, cadence lead state; dual-read backfill from files; distributed locks added for live dispatch paths | `core/state_store.py`, `execution/operator_outbound.py`, `execution/cadence_engine.py`, `scripts/migrate_file_state_to_redis.py` |
| **P0-E: Escalation Regression Fix** | DONE | Escalation chain aligned to deterministic rubric: Level 1 Slack, Level 2 Slack+SMS, Level 3 Slack+SMS+Email | `core/notifications.py` |

#### Safety Controls (v4.4)

| Control | Behavior | Verification |
|---------|----------|--------------|
| Strict API auth model | All protected `/api/*` endpoints reject unauthenticated calls with `401`; only health allowlist is unauthenticated | `tests/test_runtime_reliability.py::test_protected_api_endpoints_require_dashboard_token` |
| Immutable Gatekeeper execution scope | Approved batch executes frozen IDs/actions only; queue drift cannot alter execution scope | `tests/test_operator_batch_snapshot_integrity.py` |
| One-time batch execution | Executed batch cannot be replayed; subsequent live call creates new pending batch instead of re-sending prior approved scope | `tests/test_operator_batch_snapshot_integrity.py` |
| Canonical dedup keys | Daily dedup key is normalized recipient email (`email:<normalized>`); legacy `email_id` entries are migrated/compatible | `tests/test_operator_dedup_and_send_path.py` |
| Redis state + locking | Operator/cadence/batch state uses Redis-backed interface with dual-read fallback and live-motion distributed locks | `tests/test_state_store_redis_cutover.py` |

#### Strict Release Gate (Executed)

| Gate | Command | Threshold | Result |
|------|---------|-----------|--------|
| Replay Gate | `python scripts/replay_harness.py --min-pass-rate 0.95` | `pass_rate >= 0.95` | **PASS** (`1.0`, 50/50, `block_build=false`) |
| Critical Pytest Pack | `python -m pytest -q tests/test_gatekeeper_integration.py tests/test_runtime_reliability.py tests/test_runtime_determinism_flows.py tests/test_trace_envelope_and_hardening.py tests/test_replay_harness_assets.py tests/test_operator_batch_snapshot_integrity.py tests/test_operator_dedup_and_send_path.py tests/test_state_store_redis_cutover.py` | Zero failures | **PASS** (60 passed) |
| Operator Dry-Run Safety | `python -m execution.operator_outbound --motion outbound --dry-run --json` + `python -m execution.operator_outbound --motion all --dry-run --json` | No unexpected errors | **PASS** |
| Endpoint Auth No-Go Gate (local deterministic) | `tests/test_runtime_reliability.py::test_protected_api_endpoints_require_dashboard_token` | Protected routes unauth=`401`; token auth accepted | **PASS** |

#### Contradiction Cleanup (v4.4)

- **Inngest function count**: canonical count is **5** functions (includes `daily-decay-detection`).
- **`actually_send` semantics**: this flag applies to dashboard approval path (direct GHL send behavior). OPERATOR execution path is governed by `--live`, Gatekeeper approval, and OPERATOR config/ramp controls.

#### Post-P0 Cutover Steps — REVALIDATION REQUIRED (post deep review)

- [x] Add deterministic deployed auth smoke gate utility:
  - `python scripts/endpoint_auth_smoke.py --base-url "https://<env-domain>" --token "<DASHBOARD_AUTH_TOKEN>"`
- [x] Add staging+production auth smoke matrix runner:
  - `python scripts/endpoint_auth_smoke_matrix.py --staging-url "https://<staging-domain>" --staging-token "<staging-token>" --production-url "https://<prod-domain>" --production-token "<prod-token>"`
- [x] Set production/staging `CORS_ALLOWED_ORIGINS` explicit allowlist (Railway domains only, wildcard removed).
- [ ] Rotate staging+production `DASHBOARD_AUTH_TOKEN` (prior token appeared in docs history) and redeploy.
- [ ] Re-run deployed endpoint auth smoke with rotated tokens:
  - `python scripts/endpoint_auth_smoke.py --base-url "https://<prod-domain>" --token "<new-token>"`
- [x] Run one-time state migration in deployed environment — **ok: true** (2 items migrated):
  - `python scripts/migrate_file_state_to_redis.py --hive-dir .hive-mind`
- [x] Replay harness — **50/50 PASS** (100%, avg score 4.54/5, `block_build: false`)
- [ ] Keep conservative ramp policy active until 3 clean supervised live days are completed.

### 4H: Deep Review Hardening Follow-Up (v4.5) — IN PROGRESS

**Objective**: Validate cutover claims against code, close residual security hardening gaps, and lock final PTO inputs before rigorous autonomy testing.

#### Implemented in this follow-up

| Item | Status | Outcome | Files |
|------|--------|---------|-------|
| Constant-time token validation | DONE | Replaced string `==` token comparison with `hmac.compare_digest` in dashboard and Instantly control auth paths | `dashboard/health_app.py`, `webhooks/instantly_webhook.py` |
| CORS preflight auth behavior | DONE | `OPTIONS` requests now bypass API auth middleware, preventing false 401s on browser preflight | `dashboard/health_app.py`, `tests/test_runtime_reliability.py` |
| Instantly control auth regression tests | DONE | Added strict auth tests: query/header token success, strict fail-closed without token, legacy bypass rejection | `tests/test_instantly_webhook_auth.py` |
| Non-API webhook signature enforcement | DONE | Added uniform strict-mode HMAC checks for `/webhooks/instantly/*`, `/webhooks/heyreach`, `/webhooks/rb2b`, and `/webhooks/clay`; fail-closed in strict mode when secrets missing | `core/webhook_security.py`, `webhooks/instantly_webhook.py`, `webhooks/heyreach_webhook.py`, `webhooks/rb2b_webhook.py` |
| Deliverability rejection structured audit logs | DONE | Deliverability guard rejections now emit structured JSONL audit events with reason codes and lead identifiers | `execution/instantly_dispatcher.py` |
| Runtime readiness webhook secret hard-fail | DONE | Runtime dependency health now includes webhook signature dependency and fails readiness in strict mode when required webhook secrets are missing | `core/runtime_reliability.py`, `tests/test_runtime_reliability.py` |
| Edge-case regression coverage expansion | DONE | Added explicit tests for EMERGENCY_STOP live block, excluded individual email rejection audit, and HeyReach exclusion for `sent_via_ghl` | `tests/test_hos_integration_regressions.py`, `tests/test_webhook_signature_enforcement.py` |
| Secret leakage cleanup in handoff docs | DONE | Redacted exposed dashboard token values and replaced with placeholders | `docs/CODEX_HANDOFF.md` |

#### Deep review findings requiring PTO action before rigorous testing

| Finding | Severity | Required Input/Action |
|---------|----------|-----------------------|
| Dashboard token appeared in docs history | HIGH | Rotate staging+production `DASHBOARD_AUTH_TOKEN` immediately and redeploy |
| Deployed auth smoke must be re-run after token rotation | HIGH | Provide final deployed URLs + new tokens for deterministic auth smoke gate rerun |
| Ramp to first supervised live dispatch still pending | HIGH | Execute first live dispatch ritual and hold 3 clean supervised days before autonomy graduation |

#### Go/No-Go Inputs Needed (PTO)

- [ ] New staging `DASHBOARD_AUTH_TOKEN` rotated and deployed
- [ ] New production `DASHBOARD_AUTH_TOKEN` rotated and deployed
- [ ] Re-run: `python scripts/endpoint_auth_smoke.py --base-url "https://<staging-domain>" --token "<new-staging-token>"`
- [ ] Re-run: `python scripts/endpoint_auth_smoke.py --base-url "https://<prod-domain>" --token "<new-prod-token>"`
- [ ] (Recommended) Run one-shot matrix smoke:
  - `python scripts/endpoint_auth_smoke_matrix.py --staging-url "https://<staging-domain>" --staging-token "<new-staging-token>" --production-url "https://<prod-domain>" --production-token "<new-prod-token>"`
- [ ] Confirm strict runtime flags remain enforced (`DASHBOARD_AUTH_STRICT=true`, `REDIS_REQUIRED=true`, `INNGEST_REQUIRED=true`, `WEBHOOK_SIGNATURE_REQUIRED=true`)
- [ ] Set production/staging webhook secrets:
  - `INSTANTLY_WEBHOOK_SECRET`, `HEYREACH_WEBHOOK_SECRET`, `RB2B_WEBHOOK_SECRET`, `CLAY_WEBHOOK_SECRET`

#### Remaining Recommended Engineering Next Steps (v4.5)

- [x] Add strict webhook authentication policy for non-API webhook routes (`/webhooks/heyreach`, `/webhooks/clay`, `/webhooks/rb2b`) with provider-supported signatures or shared-secret headers.
- [x] Add readiness hard-fail when required webhook secrets are missing in strict production mode.
- [ ] After 1 week stable Redis operations, disable file fallback (`STATE_DUAL_READ_ENABLED=false`) and remove file-write fallback in production.

### 4I: Rejection Loop Hardening — COMPLETE

**Objective**: Prevent the Andrew/Celia repeat-rejection pattern by adding per-lead rejection memory, pre-queue quality guards, and sub-agent enrichment to extract deeper personalization signals.

**Root Cause**: CRAFTER used deterministic template selection (`hash(email) % len(templates)`) with no per-lead rejection history. Rejected drafts for the same lead were regenerated with the same template, same opener pattern, and no awareness of prior feedback.

| Task | Status | Files |
|------|--------|-------|
| Per-lead rejection memory store (Redis + filesystem, 30-day TTL) | DONE | `core/rejection_memory.py` |
| Pre-queue quality guard (5 deterministic rules, soft mode) | DONE | `core/quality_guard.py` |
| Sub-agent enrichment (5 specialist pure-function signal extractors) | DONE | `core/enrichment_sub_agents.py` |
| CRAFTER template rotation away from rejected templates | DONE | `execution/crafter_campaign.py` |
| CRAFTER rejection context in template variables | DONE | `execution/crafter_campaign.py` |
| Dashboard reject → rejection memory recording | DONE | `dashboard/health_app.py` |
| Quality guard gate before `shadow_queue.push()` | DONE | `execution/run_pipeline.py` |
| Rejection memory tests (26 tests) | DONE | `tests/test_rejection_memory.py` |
| Quality guard tests (16 tests) | DONE | `tests/test_quality_guard.py` |
| CRAFTER hardening + sub-agent tests (8 tests) | DONE | `tests/test_crafter_rejection_hardening.py` |

**Quality Guard Rules**:
- GUARD-001: Per-lead rejection count exceeds threshold → block (unless new evidence)
- GUARD-002: Draft fingerprint (SHA-256) matches previously rejected draft → block
- GUARD-003: Insufficient personalization evidence → sub-agent enrichment fallback → block if still insufficient
- GUARD-004: Banned opener patterns (10 patterns) → block
- GUARD-005: Generic AI phrase density > 40% of sentences → block

**Env Vars**: `QUALITY_GUARD_ENABLED` (default: true), `QUALITY_GUARD_MODE` (soft = log-only), `REJECTION_MEMORY_TTL_DAYS` (default: 30), `REJECTION_MEMORY_MAX_REJECTIONS` (default: 3)

**Test Gate**: 50/50 passing in 0.67s

### 4J: TDD Critical Path Testing — COMPLETE

**Objective**: Close the 6 critical testing gaps identified in the TDD assessment before Phase 5 graduation. Shadow queue (3 production incidents, 0 tests), enricher parsers (0 tests), dispatcher guards (0 test coverage), pipeline integration (no inter-stage tests), feedback loop (module exists, 0 dedicated tests), coverage tracking (not configured).

**Result**: 187 tests across 9 test files, all passing. Pre-commit hook enforces test gate on every commit.

**Sprint 1 — Critical Path Tests (COMPLETE)**:

| Task | Status | Target | Files |
|------|--------|--------|-------|
| Shadow queue tests (dual-write, prefix regression) | DONE | 22 tests | `tests/test_shadow_queue.py` |
| Enricher parser tests (Apollo + BetterContact) | DONE | 27 tests | `tests/test_enricher_waterfall.py` |
| Dispatcher guard tests (4-layer deliverability) | DONE | 32 tests | `tests/test_instantly_dispatcher_guards.py` |
| Coverage config + CI gate (40% threshold) | DONE | `.coveragerc` | `.coveragerc`, `.github/workflows/replay-harness.yml` |

**Sprint 2 — Integration + Wiring (COMPLETE)**:

| Task | Status | Target | Files |
|------|--------|--------|-------|
| Pipeline integration tests (stage boundaries) | DONE | 9 tests | `tests/test_pipeline_integration.py` |
| Feedback loop tests (module exists, tests missing) | DONE | 15 tests | `tests/test_feedback_loop.py` |
| Wire VerificationHooks into `_stage_send()` | DONE | ~15 lines | `execution/run_pipeline.py` |
| Wire CircuitBreaker pre-check (ENRICH) | DONE | ~10 lines | `execution/run_pipeline.py` |

**Sprint 3 — Hardening (COMPLETE)**:

| Task | Status | Target | Files |
|------|--------|--------|-------|
| Pre-commit hook for critical tests | DONE | ~10s run | `.githooks/pre-commit` |
| HeyReach dispatcher tests | DONE | 18 tests | `tests/test_heyreach_dispatcher.py` |

### Phase 4K: Clay Pipeline Enrichment Fallback — COMPLETE

**Problem**: Clay was removed from pipeline waterfall because HTTP API callback doesn't pass `lead_id`, causing 3-min guaranteed timeouts.

**Solution**: Redis LinkedIn URL correlation. Before sending to Clay, store `linkedin_hash → {lead_id, request_id}` in Redis. On callback, Railway dashboard extracts LinkedIn URL, looks up correlation, stores result for pipeline polling.

**Waterfall position**: Apollo (sync, ~2s) → BetterContact (async, ~2min) → Clay (async, ~2min) → null

**Feature flag**: `CLAY_PIPELINE_ENABLED=true` (disabled by default)

**Files modified**:
- `execution/enricher_waterfall.py` — Clay provider + parser + waterfall chain (~130 lines)
- `dashboard/health_app.py` — Pipeline Clay callback handler with Redis correlation (~100 lines)
- `tests/test_enricher_waterfall.py` — 14 Clay-specific tests (parser, normalization, integration)

**Env vars**: `CLAY_API_KEY`, `CLAY_WORKBOOK_WEBHOOK_URL` (existing), `CLAY_PIPELINE_ENABLED` (new, default false)

---

## Phase 5: Optimize & Scale (Post-Autonomy)

**Principle**: Only optimize what you have production data for. Don't build infrastructure for hypothetical problems.

**Strategy**: "Own the Brain, Rent the Pipes" — intelligence layer (ICP scoring, message strategy, agent orchestration, approval gates) is the moat. Email sending, CRM, enrichment APIs are rented infrastructure.

### 5A: Data Optimization (Trigger: 2 weeks of live sends)

| Task | Status | Notes |
|------|--------|-------|
| Enrichment result caching (Supabase) | TODO | Saves Apollo credits on re-encounters |
| Self-learning ICP calibration | TODO | Feed real deal outcomes back to scoring model |
| Enrichment quality feedback loop | TODO | Track which provider gives best data per segment |
| Document adapter contracts in CLAUDE.md | TODO | Low effort, high clarity |

### 5B: Intelligence Layer (Trigger: 30 days of send data)

| Task | Status | Notes |
|------|--------|-------|
| Multi-source intent fusion | TODO | RB2B visitors + email opens + LinkedIn engagement → unified intent score |
| A/B testing infrastructure | TODO | Email subject/body variants — needs real send data first |
| Campaign performance analytics dashboard | TODO | Aggregate Instantly + HeyReach metrics |

### 5C: Infrastructure Migration (Trigger: Volume exceeds 500 emails/day)

| Task | Status | Notes |
|------|--------|-------|
| Evaluate Resend.com as secondary email backend | TODO | $20/mo for 50K — only if Instantly fails or limits hit |
| Evaluate AWS SES for cold sending | TODO | ~$0.10/1000 — only at scale |
| DNS health monitoring dashboard | TODO | Only if deliverability drops |

### Decisioned Out (Explicitly NOT doing)

| Item | Source | Why Not |
|------|--------|---------|
| Rebuild CRM (replace GHL) | Modernization Roadmap | CRMs are commodity infrastructure. GHL works. 2-year project, zero competitive advantage. |
| Custom warmup at current volume | Modernization Roadmap | 6 accounts x 25/day = 150 emails. Instantly handles warmup. Building custom is absurd at this scale. |
| Replace RB2B with custom pixel | Modernization Roadmap | IP-to-identity is proprietary tech. RB2B works. |
| Exa.ai as third enrichment provider | Modernization Roadmap | Apollo + BetterContact covers needs. Third provider adds complexity without clear ROI. Revisit if miss rate >20%. |
| Full email migration from Instantly | Modernization Roadmap | EmailSendingAdapter exists for future swap. Only migrate when volume justifies custom SMTP infrastructure. |

---

## Current API Status

| Service | Status | Notes |
|---------|--------|-------|
| **Apollo.io** | WORKING | People Search (free) + Match (1 credit/reveal) |
| **Clay Explorer** | ACTIVE | $499/mo, 14K credits/mo. RB2B visitor enrichment + pipeline fallback (position 3, feature-flagged `CLAY_PIPELINE_ENABLED`). |
| **BetterContact** | CODE READY | Async API integrated in enricher, no subscription yet (Clay preferred) |
| **Slack Alerting** | WORKING | Webhook configured, WARNING + CRITICAL alerts |
| **Redis (Upstash)** | WORKING | 62ms from Railway |
| **Inngest** | WORKING | 5 functions mounted |
| **Instantly.ai** | V2 LIVE | Bearer auth, DRAFTED-by-default, 6 domains warmed (100% health), 4/4 webhooks registered, test campaign sent. Phase 4A COMPLETE. |
| **HeyReach** | ACTIVE | API key verified, 4 webhooks registered (UI), signal loop wired. 19 campaigns exist. Webhook CRUD is UI-only. |
| **Railway** | DEPLOYED | Auto-deploy on push |
| **Proxycurl** | REMOVED | Shutting down Jul 2026 (sued by LinkedIn) |
| **Clay API v1** | DEPRECATED | Returns 404, replaced by webhook pattern |
| **LinkedIn Scraper** | BLOCKED | 403 rate-limited, replaced by Apollo Search |

---

## Key Files

| Purpose | File |
|---------|------|
| Pipeline runner | `execution/run_pipeline.py` |
| Enricher (Apollo + BetterContact + Clay fallback) | `execution/enricher_waterfall.py` |
| Lead discovery (Apollo) | `execution/hunter_scrape_followers.py` |
| ICP scoring | `execution/segmentor_classify.py` |
| Dashboard + API | `dashboard/health_app.py` |
| Alerts (Slack) | `core/alerts.py` |
| Production config | `config/production.json` |
| Enrichment research | `docs/research/ENRICHMENT_PROVIDER_RESEARCH_2026.md` |
| Multi-channel research | `docs/research/MULTI_CHANNEL_CADENCE_RESEARCH_2026.md` |
| GHL Calendar client (adapter) | `mcp-servers/ghl-mcp/calendar_client.py` |
| GHL MCP server (CRM + Calendar) | `mcp-servers/ghl-mcp/server.py` |
| Calendar guardrails (shared) | `mcp-servers/google-calendar-mcp/guardrails.py` |
| Instantly dispatcher | `execution/instantly_dispatcher.py` |
| Instantly webhooks | `webhooks/instantly_webhook.py` |
| Instantly MCP server (V2) | `mcp-servers/instantly-mcp/server.py` |
| Instantly webhook registration | `scripts/register_instantly_webhooks.py` |
| Instantly integration spec (V2) | `docs/integrations/INSTANTLY.md` |
| HeyReach dispatcher | `execution/heyreach_dispatcher.py` |
| HeyReach webhooks | `webhooks/heyreach_webhook.py` |
| HeyReach webhook registration | `scripts/register_heyreach_webhooks.py` |
| **OPERATOR agent (unified dispatch)** | `execution/operator_outbound.py` |
| **Revival scanner (GHL contact mining)** | `execution/operator_revival_scanner.py` |
| Lead Signal Loop (engagement tracking) | `core/lead_signals.py` |
| Activity Timeline (per-lead aggregation) | `core/activity_timeline.py` |
| GHL Local Sync (contact cache) | `core/ghl_local_sync.py` |
| Leads Dashboard (pipeline visualization) | `dashboard/leads_dashboard.html` |
| Agent permissions | `core/agent_action_permissions.json` |
| Agent registry | `execution/unified_agent_registry.py` |
| **Rejection memory (per-lead history)** | `core/rejection_memory.py` |
| **Quality guard (pre-queue validator)** | `core/quality_guard.py` |
| **Enrichment sub-agents (signal extraction)** | `core/enrichment_sub_agents.py` |
| **Feedback loop (outcome → learning bridge)** | `core/feedback_loop.py` |
| Rejection hardening design doc | `docs/REJECTION_LOOP_HARDENING_PLAN.md` |
| **Pre-commit hook (test gate)** | `.githooks/pre-commit` |
| **HeyReach dispatcher tests (18 tests)** | `tests/test_heyreach_dispatcher.py` |
| **Enricher waterfall tests (41 tests)** | `tests/test_enricher_waterfall.py` |
| This plan | `CAIO_IMPLEMENTATION_PLAN.md` |

---

## Safety Controls (Active)

| Control | Setting | Location |
|---------|---------|----------|
| `actually_send` | dashboard-path toggle (not OPERATOR master switch) | `config/production.json` |
| `shadow_mode` | `true` | `config/production.json` |
| `max_daily_sends` | `0` | `config/production.json` |
| `EMERGENCY_STOP` | env var | Blocks all outbound |
| Shadow emails | `.hive-mind/shadow_mode_emails/` | Review before enabling real sends |
| Audit trail | `.hive-mind/audit/` | All approvals/rejections logged |

---

## Cost Summary

| Service | Monthly Cost | Credits/Capacity | Status |
|---------|-------------|-----------------|--------|
| Clay Explorer | $499/mo | 14,000 credits/mo | ACTIVE (enrichment planned) |
| Apollo.io | ~$49/mo | 900 credits/mo (estimated) | ACTIVE (primary enrichment) |
| Railway | ~$5/mo | Dashboard hosting | ACTIVE |
| Upstash Redis | Free tier | 10K commands/day | ACTIVE |
| Inngest | Free tier | 25K events/mo | ACTIVE |
| Instantly.ai | ~$30/mo | Email sending (Growth plan) | V2 MIGRATED |
| HeyReach | $79/mo | LinkedIn automation (1 sender, 19 campaigns) | ACTIVE |
| BetterContact | $0 (not subscribed) | Code ready | DEFERRED |

**Total Current Spend**: ~$662/mo (Clay + Apollo + Railway + Instantly + HeyReach)

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-13 | Cancel PDL integration | 10x more expensive ($0.28/lead), stale data, single source |
| 2026-02-13 | Choose BetterContact over FullEnrich | Cheaper Starter ($15/mo vs $29/mo), pay-only-for-verified |
| 2026-02-13 | Defer BetterContact, use Clay Explorer | Already paying $499/mo with 14K credits. Clay waterfall has 10+ providers built-in. No extra subscription needed. |
| 2026-02-13 | Remove all Proxycurl code | Shutting down Jul 2026, sued by LinkedIn |
| 2026-02-13 | Replace LinkedIn scraper with Apollo Search | LinkedIn 403 blocked, Apollo covers 275M+ contacts |
| 2026-02-13 | Replace Clay API v1 with Apollo enrichment | Clay v1 deprecated (404), Apollo sync API simpler |
| 2026-02-13 | Recommend HeyReach for LinkedIn automation | Native Instantly.ai bidirectional sync, full API, cloud-based safety |
| 2026-02-13 | Clay webhook pattern for enrichment fallback | Already on Explorer plan, 25.8K credits available, 10+ waterfall providers |
| 2026-02-13 | Reuse existing Clay workbook (not new table) | Website Visitor Enrichment Workbook already has all columns needed. Same webhook serves both RB2B and pipeline. Saves 50K-row webhook slot. |
| 2026-02-13 | Unified `/webhooks/clay` callback handler | Single endpoint routes by `source`/`lead_id` for pipeline vs `visitor_id` for RB2B. Eliminates duplicate endpoints. |
| 2026-02-14 | Remove Clay from pipeline enrichment | `lead_id` not passed through Clay HTTP callback → 3-min guaranteed timeouts. Apollo sync is faster and reliable. |
| 2026-02-14 | Rewrite Send stage to shadow queue | Replaced broken Instantly import with shadow email queue in `.hive-mind/shadow_mode_emails/` for HoS dashboard review |
| 2026-02-14 | Wire pipeline + circuit breaker alerts to Slack | Stage failures → WARNING, exceptions/OPEN transitions → CRITICAL |
| 2026-02-14 | Google Calendar setup guide created | Non-technical guide for HoS + OAuth setup script (`scripts/setup_google_calendar.py`) |
| 2026-02-14 | Replace Google Calendar with GHL Calendar | Zero setup (GHL API keys already on Railway), CRM-native (appointments link to contacts), no OAuth flow needed. GHLCalendarClient is a drop-in adapter matching GoogleCalendarMCP interface. |
| 2026-02-14 | Migrate Instantly V1 → V2 API | V1 deprecated Jan 19, 2026. Full rewrite: Bearer auth, cursor pagination, webhook CRUD, CampaignStatus enum. Fixed 4 CRITICAL failure modes (orphaned campaigns, pagination gap, suppression race condition). |
| 2026-02-14 | Domain reputation isolation | Dedicated cold outreach domains (6 domains, see 2026-02-15 entry) for Instantly, `chiefai.ai` for GHL nurture. Reputation isolation — cold spam reports don't poison nurture deliverability. |
| 2026-02-14 | HeyReach for LinkedIn automation | API compatible ($79/mo Growth). Cannot create campaigns via API (UI only). Native Instantly bidirectional sync. 11 webhook events. Lead-list-first pattern avoids campaign auto-reactivation. |
| 2026-02-14 | OPERATOR as unified outbound agent | Consolidates Instantly email + HeyReach LinkedIn + GHL nurture under single execution layer. GATEKEEPER remains approval gate. QUEEN routes by ICP tier. |
| 2026-02-15 | Dual-platform email strategy (GHL + Instantly) | CLAUDE.md updated from "GHL exclusive" to dual-platform. GHL handles nurture on `chiefai.ai`, Instantly handles cold outreach on 5 isolated domains. Domain reputation isolation is non-negotiable. |
| 2026-02-15 | Multi-account rotation via `email_list` | Fixed silent V2 bug where sending accounts were never included in campaign payload. Added `sending_accounts` config block with 6 primary from-emails for round-robin rotation. |
| 2026-02-15 | 6 dedicated cold outreach domains (NOT outbound.chiefai.ai) | User already has 6 warmed domains in Instantly: chiefaiofficerai.com, chiefaiofficerconsulting.com, chiefaiofficerguide.com, chiefaiofficerlabs.com, chiefaiofficerresources.com, chiefaiofficersolutions.com. This is BETTER than a single subdomain — more rotation diversity, better deliverability. Replaced placeholder domains in production.json. |
| 2026-02-15 | Deploy Instantly routes to Railway | Commit `53ab1c1` deployed. Routes were local-only (never committed from previous session). Verified: `/api/instantly/campaigns`, `/webhooks/instantly/health`, `/api/instantly/dispatch-status` all responding. |
| 2026-02-16 | HeyReach webhook CRUD is UI-only | Discovered via API probing (9 endpoint variations, all 404). Rewrote `register_heyreach_webhooks.py` to utility script. 4 webhooks created manually in HeyReach UI. |
| 2026-02-16 | Wire Monaco signal loop into both webhook handlers | `LeadStatusManager` calls added to Instantly (reply/bounce/open/unsubscribe) and HeyReach (connection_sent/accepted, reply, campaign_completed). Engagement-driven lead status now flows from real webhook events. |
| 2026-02-16 | HeyReach enabled in production.json | API key verified (HTTP 200), health endpoint confirms `api_key_configured: true`. 4/4 webhooks registered. `enabled: true` in config. |
| 2026-02-17 | Apply HoS critical pre-live fixes + add regression gate | Fixed follow-up subject A/B bug, intent+engagement cap inflation, subdomain exclusion gap, cadence dry-run side effects, and cadence auto-enroll channel gap. Added `tests/test_hos_integration_regressions.py`; replay and expanded pytest gates passed. |
| 2026-02-17 | Enforce strict non-API webhook signatures + readiness webhook dependency checks | Added shared webhook signature policy helper; enforced signed webhooks on Instantly/HeyReach/RB2B/Clay endpoints; runtime readiness now hard-fails in strict mode if required webhook secrets are missing. Added `tests/test_webhook_signature_enforcement.py` and expanded runtime reliability tests. |
| 2026-02-18 | HoS Requirements Integration | Complete email system rewrite: 11 HoS-approved angles (4 T1, 3 T2, 4 T3), Fractional CAIO positioning, M.A.P.™ Framework, CAN-SPAM footer (5700 Harper Dr, Albuquerque), sender=Dani Apgar/Chief AI Officer, booking=caio.cx, ICP scoring multipliers (1.5x/1.2x), customer exclusion (7 domains + 27 emails), Guard 4 in dispatcher, Tier 1 target companies (agencies/consulting/staffing). |

---

*Plan Version: 4.6*
*Created: 2026-02-13*
*Latest Release: 2026-02-27 (commit `a0d91b4` — Sprint 3: Clay fallback re-enabled via Redis LinkedIn URL correlation, HeyReach dispatcher tests (18), pre-commit hook, TDD 4J COMPLETE with 187 tests)*
*Previous Release: 2026-02-17 (P0-A..P0-E complete, v4.5 deep-review + HoS fixes + strict webhook signature hardening)*
*Supersedes: v3.7, v3.6, Modernization Roadmap (implementation_plan.md.resolved), Original Path to Full Autonomy (f34646b2/task.md.resolved)*
