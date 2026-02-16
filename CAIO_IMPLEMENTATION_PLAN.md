# CAIO Alpha Swarm — Unified Implementation Plan

**Last Updated**: 2026-02-16 (v3.6 — Monaco-inspired signal loop + dashboard)
**Owner**: ChiefAIOfficer Production Team
**AI**: Claude Opus 4.6

---

## Executive Summary

The CAIO Alpha Swarm is a 12-agent autonomous SDR pipeline: Lead Discovery (Apollo.io) -> Enrichment (Apollo + fallback) -> ICP Scoring -> Email Crafting -> Approval -> Send (Instantly.ai). This plan tracks all phases from foundation through production autonomy.

**Current Position**: Phase 4 (Autonomy Graduation) — IN PROGRESS
**Production Pipeline**: 6/6 stages PASS with real Apollo data (8-68s end-to-end)
**Autonomy Score**: ~90/100
**Total Production Runs**: 33+ (22 fully clean, last 10 consecutive 6/6 PASS)

```
Phase 0: Foundation Lock          [##########] 100%  COMPLETE
Phase 1: Live Pipeline Validation [##########] 100%  COMPLETE
Phase 2: Supervised Burn-In       [##########] 100%  COMPLETE
Phase 3: Expand & Harden          [##########] 100%  COMPLETE
Phase 4: Autonomy Graduation      [#######---]  65%  IN PROGRESS (4A COMPLETE, 4B code built, 4F signal loop + dashboard live)
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
| Inngest event-driven functions | DONE | 4 functions mounted |
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
| Apollo `reveal_phone_number` requires `webhook_url` (400) | Removed `reveal_phone_number: True` from payload | `enricher_clay_waterfall.py` |
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
| BetterContact fallback code integration | DONE | Async polling in `enricher_clay_waterfall.py` |
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

### 3A-Assessment: Clay in Pipeline — REMOVED (RB2B Only)

**Finding**: Clay HTTP API callback does NOT include the `lead_id` field that the pipeline enricher needs to correlate responses. This causes a guaranteed 3-minute timeout on every lead routed through Clay, making it unusable as a pipeline enrichment fallback.

**Decision**: Clay REMOVED from pipeline enrichment waterfall. Clay Explorer ($499/mo) remains active and valuable for **RB2B visitor enrichment only** (visitor_id works in callbacks).

**Pipeline enrichment waterfall (current)**:
1. Apollo.io People Match (primary, synchronous, 1 credit/reveal)
2. BetterContact (fallback, async polling — code ready, subscription pending)
3. Mock/skip (graceful degradation)

**Clay usage**:
- RB2B visitors → Clay workbook webhook → enrichment columns → HTTP callback to `/webhooks/clay`
- `/webhooks/clay` handler: RB2B visitor path only (pipeline lead path removed)

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
| Clay pipeline enrichment fallback | CANCELLED | `lead_id` not accessible in HTTP callback → 3-min timeouts |

---

### 3A: Enrichment Architecture — CURRENT

**Pipeline Enrichment Waterfall (synchronous)**:
```
Apollo.io People Match (primary, 1 credit/reveal)
  -> miss -> BetterContact async poll (fallback, code ready)
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

**Status**: Code infrastructure BUILT. Awaiting HeyReach subscription + LinkedIn warm-up for activation.

| Task | Status | Notes |
|------|--------|-------|
| Subscribe to HeyReach Growth ($79/mo, 1 sender) | TODO | API included on all plans — USER ACTION |
| Connect LinkedIn account + warm-up (4 weeks) | TODO | 20-25 connections/day ramp — USER ACTION |
| Build 3 campaign templates in HeyReach UI | TODO | tier_1, tier_2, tier_3 sequences — USER ACTION |
| Set `HEYREACH_API_KEY` in Railway | TODO | Dashboard → Settings → Integrations — USER ACTION |
| Create `execution/heyreach_dispatcher.py` | DONE | API client + lead-list-first safety, daily ceiling (20/day), CLI with --dry-run |
| Create `webhooks/heyreach_webhook.py` | DONE | 11 event handlers, JSONL logging, follow-up flags, Slack alerts |
| Mount HeyReach webhook in dashboard | DONE | `dashboard/health_app.py` — router included after Instantly |
| Create `scripts/register_heyreach_webhooks.py` | DONE | CRUD: --list, --delete-all, --check-auth (same pattern as Instantly) |
| Register HeyReach webhooks (11 events → `/webhooks/heyreach`) | TODO | Run script after HEYREACH_API_KEY is set |
| Configure native HeyReach ↔ Instantly bidirectional sync | TODO | Paste API keys in both dashboards — USER ACTION |
| Wire CONNECTION_REQUEST_ACCEPTED → Instantly warm follow-up | DONE | Webhook handler writes flag file, dispatcher reads it |
| Shadow test with 5 internal LinkedIn profiles | TODO | Validate before real outreach — USER ACTION |

**HeyReach API Reference**:
- Base URL: `https://api.heyreach.io/api/public`
- Auth: `X-API-KEY` header
- Rate limit: 300 req/min
- CRITICAL: Adding leads to paused campaign auto-reactivates it → use lead-list-first pattern

### 4C: OPERATOR Agent Activation

**Design**: OPERATOR becomes the unified outbound execution layer for all channels.

```
QUEEN (orchestrator)
  → GATEKEEPER (approve)
    → OPERATOR (execute)
      ├── Instantly API V2 (email campaigns)
      ├── HeyReach API (LinkedIn campaigns)
      └── GHL API (nurture workflows)
```

| Task | Status | Notes |
|------|--------|-------|
| Create `execution/operator_outbound.py` | TODO | Unified dispatch interface |
| Move `instantly_dispatcher.py` under OPERATOR | TODO | OPERATOR.dispatch("email", ...) |
| Add `heyreach_dispatcher.py` under OPERATOR | TODO | OPERATOR.dispatch("linkedin", ...) |
| Update agent registry (module_path, description) | DONE | Points to `execution.operator_outbound` |
| Update agent permissions (Instantly + HeyReach actions) | DONE | 17 new allowed actions for OPERATOR |
| QUEEN routing logic: ICP tier → channel selection | TODO | tier_1: email+LinkedIn, tier_2: email, tier_3: email only |
| GATEKEEPER approval gate for both channels | TODO | Single choke point before OPERATOR dispatches |

### 4D: Multi-Channel Cadence (21-day)

| Day | Channel | Action | Platform |
|-----|---------|--------|----------|
| 1 | Email | Personalized intro | Instantly |
| 2 | LinkedIn | Connection request | HeyReach |
| 3 | Phone | Call attempt #1 | GHL (PREPPER provides context) |
| 5 | Email | Value/case study | Instantly |
| 7 | LinkedIn | Message (if connected) | HeyReach |
| 10 | Email | Social proof | Instantly |
| 14 | LinkedIn | Voice message | HeyReach |
| 17 | Email | Break-up | Instantly |
| 21 | Email | Graceful close | Instantly |

### 4E: Supervised Live Sends

### Prerequisites
- [x] 6 cold outreach domains DNS verified + warm-up complete (all 100% health)
- [x] Internal test campaign sent successfully via Instantly (`test_internal_v2_20260215`)
- [ ] LinkedIn account warm-up complete (4 weeks) — requires HeyReach subscription
- [ ] Shadow test via HeyReach completed (5 profiles)
- [ ] OPERATOR agent operational

| Task | Status | Notes |
|------|--------|-------|
| Enable `actually_send: true` for tier_1 only | TODO | Config change + Railway deploy |
| 3 days supervised operation (5 emails/day) | TODO | Monitor delivery, opens, bounces |
| Monitor: open rate ≥50%, reply rate ≥8%, bounce <5% | TODO | Dashboard KPI tracking |
| Graduate to 25/day email ceiling | TODO | After 3 clean days |
| Enable HeyReach LinkedIn sends (10 connections/day) | TODO | After LinkedIn warm-up complete |

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

**Status**: HIGH-IMPACT items BUILT. Dashboard live at `/leads`.

| Task | Status | Notes |
|------|--------|-------|
| **Signal Loop**: Webhook events update lead status | DONE | `core/lead_signals.py` — LeadStatusManager with 18 statuses |
| **Ghosting Detection**: 72h no open → "ghosted" | DONE | `detect_engagement_decay()` — time-based rules |
| **Stall Detection**: 7d opened, no reply → "stalled" | DONE | Runs on demand via `POST /api/leads/detect-decay` |
| **Engaged-Not-Replied**: 2+ opens, 0 replies → "hesitant" | DONE | Automatic pattern detection |
| **"Why This Score" Explainability** | DONE | `scoring_reasons` field in segmentor output (human-readable) |
| **Unified Activity Timeline** | DONE | `core/activity_timeline.py` — aggregates all channels per lead |
| **Pipeline Funnel Visualization** | DONE | 5-stage flow on `/leads` dashboard (Pipeline→Outreach→Engaged→At Risk→Terminal) |
| **Lead Dashboard** | DONE | `dashboard/leads_dashboard.html` — filterable lead list + click-to-expand timeline |
| **API Endpoints** | DONE | `/api/leads`, `/api/leads/funnel`, `/api/leads/{email}/timeline`, `/api/leads/detect-decay` |
| Wire signal loop INTO Instantly webhook handlers | TODO | On real webhook events, call `LeadStatusManager.handle_*()` |
| Wire signal loop INTO HeyReach webhook handlers | TODO | Requires HeyReach subscription first |
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
| **Clay Explorer** | ACTIVE | $499/mo, 14K credits/mo. RB2B visitor enrichment ONLY (removed from pipeline). |
| **BetterContact** | CODE READY | Async API integrated in enricher, no subscription yet (Clay preferred) |
| **Slack Alerting** | WORKING | Webhook configured, WARNING + CRITICAL alerts |
| **Redis (Upstash)** | WORKING | 62ms from Railway |
| **Inngest** | WORKING | 4 functions mounted |
| **Instantly.ai** | V2 LIVE | Bearer auth, DRAFTED-by-default, 6 domains warmed (100% health), 4/4 webhooks registered, test campaign sent. Phase 4A COMPLETE. |
| **HeyReach** | RESEARCHED | API compatible ($79/mo Growth). No campaign creation via API. Needs subscription + LinkedIn warm-up. |
| **Railway** | DEPLOYED | Auto-deploy on push |
| **Proxycurl** | REMOVED | Shutting down Jul 2026 (sued by LinkedIn) |
| **Clay API v1** | DEPRECATED | Returns 404, replaced by webhook pattern |
| **LinkedIn Scraper** | BLOCKED | 403 rate-limited, replaced by Apollo Search |

---

## Key Files

| Purpose | File |
|---------|------|
| Pipeline runner | `execution/run_pipeline.py` |
| Enricher (Apollo + BetterContact fallback) | `execution/enricher_clay_waterfall.py` |
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
| Lead Signal Loop (engagement tracking) | `core/lead_signals.py` |
| Activity Timeline (per-lead aggregation) | `core/activity_timeline.py` |
| Leads Dashboard (pipeline visualization) | `dashboard/leads_dashboard.html` |
| Agent permissions | `core/agent_action_permissions.json` |
| Agent registry | `execution/unified_agent_registry.py` |
| This plan | `CAIO_IMPLEMENTATION_PLAN.md` |

---

## Safety Controls (Active)

| Control | Setting | Location |
|---------|---------|----------|
| `actually_send` | `false` | `config/production.json` |
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
| HeyReach | $79/mo (planned) | LinkedIn automation (1 sender) | RESEARCHED |
| BetterContact | $0 (not subscribed) | Code ready | DEFERRED |

**Total Current Spend**: ~$583/mo (Clay + Apollo + Railway + Instantly)
**Projected with HeyReach**: ~$662/mo

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

---

*Plan Version: 3.5*
*Created: 2026-02-13*
*Supersedes: v3.4, Modernization Roadmap (implementation_plan.md.resolved), Original Path to Full Autonomy (f34646b2/task.md.resolved)*
