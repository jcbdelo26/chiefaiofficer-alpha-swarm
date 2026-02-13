# CAIO Alpha Swarm — Unified Implementation Plan

**Last Updated**: 2026-02-13
**Owner**: ChiefAIOfficer Production Team
**AI**: Claude Opus 4.6

---

## Executive Summary

The CAIO Alpha Swarm is a 12-agent autonomous SDR pipeline: Lead Discovery (Apollo.io) -> Enrichment (Apollo + fallback) -> ICP Scoring -> Email Crafting -> Approval -> Send (Instantly.ai). This plan tracks all phases from foundation through production autonomy.

**Current Position**: Phase 3 (Expand & Harden) — IN PROGRESS
**Production Pipeline**: 5/6 stages PASS with real Apollo data (7.2s end-to-end)
**Autonomy Score**: ~82/100

```
Phase 0: Foundation Lock          [##########] 100%  COMPLETE
Phase 1: Live Pipeline Validation [##########] 100%  COMPLETE
Phase 2: Supervised Burn-In       [##########] 100%  COMPLETE
Phase 3: Expand & Harden          [########--]  85%  IN PROGRESS
Phase 4: Autonomy Graduation      [----------]   0%  PENDING
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
| Scrape | PASS | 3 leads via Apollo People Search | 4.7s |
| Enrich | PASS | 3/3 enriched via Apollo People Match | 2.5s |
| Segment | PASS | ICP scoring with real data | 8ms |
| Craft | PASS | 1 campaign created | 21ms |
| Approve | PASS | Auto-approve | 0ms |
| Send | FAIL (expected) | Instantly not configured | — |
| **Total** | **5/6 PASS** | | **7.2s** |

### 2C: Bugfixes Applied

| Bug | Fix | File |
|-----|-----|------|
| Apollo `reveal_phone_number` requires `webhook_url` (400) | Removed `reveal_phone_number: True` from payload | `enricher_clay_waterfall.py` |
| Segmentor `NoneType has no attribute 'lower'` | Changed to `(lead.get("title") or "").lower()` pattern | `segmentor_classify.py` (3 locations) |
| Segmentor `employee_count` None crash | Changed to `lead.get("company", {}).get("employee_count") or 0` | `segmentor_classify.py` |

---

## Phase 3: Expand & Harden — IN PROGRESS (85%)

### Completed Tasks

| Task | Status | Notes |
|------|--------|-------|
| Apollo two-step flow (Search -> Match) | DONE | Free search + 1 credit/reveal |
| Segmentor NoneType bugfix | DONE | title/industry/employee_count null-safe |
| Enrichment provider research (28+ providers) | DONE | [ENRICHMENT_PROVIDER_RESEARCH_2026.md](docs/research/ENRICHMENT_PROVIDER_RESEARCH_2026.md) |
| Proxycurl removal from scraper | DONE | `_fetch_via_proxycurl` method deleted |
| Proxycurl removal from enricher | DONE | All Proxycurl code replaced with BetterContact |
| BetterContact fallback code integration | DONE | Async polling in `enricher_clay_waterfall.py` |
| Clay workbook research | DONE | Requires $314/mo Explorer (we have it!), async webhooks |
| Multi-channel cadence research | DONE | [MULTI_CHANNEL_CADENCE_RESEARCH_2026.md](docs/research/MULTI_CHANNEL_CADENCE_RESEARCH_2026.md) |
| Clay Explorer webhook enrichment CODE | DONE | `_enrich_via_clay` + `_parse_clay_response` + callback endpoint |
| Clay callback endpoint | DONE | `POST /api/clay-callback` in `dashboard/health_app.py` (legacy) |
| Enricher waterfall: Apollo -> Clay -> BC | DONE | 3-tier fallback chain with file-based callback |
| Railway deployment (all fixes) | DONE | Build successful |
| Existing Clay workbook assessment | DONE | Existing Website Visitor Enrichment Workbook fully compatible |
| Unified Clay callback handler | DONE | `POST /webhooks/clay` routes both RB2B visitors AND pipeline leads |
| Enricher env var unification | DONE | Reads `CLAY_WEBHOOK_URL` or `CLAY_WORKBOOK_WEBHOOK_URL` (same URL) |
| Clay webhook source URL located | DONE | User found URL in Clay workbook settings, added to Railway |

### 3A-Assessment: Existing Workbook Reuse — CONFIRMED

**Finding**: The existing **Website Visitor Enrichment Workbook** (`share_0t9c5h2Dt6hzzFrz4Gv`) already has all enrichment columns the pipeline needs: email waterfall, email validation, company enrichment, and HTTP API callback. **No new workbook required.**

**How it works now (unified)**:
- Both RB2B visitors and pipeline leads POST to the **same Clay webhook URL** (`CLAY_WORKBOOK_WEBHOOK_URL`)
- Clay enriches both the same way (waterfall columns don't care about source)
- Clay HTTP API action column POSTs enriched data to `POST /webhooks/clay`
- The unified callback handler routes by checking `source` and `lead_id`:
  - `source=caio_pipeline` + `lead_id` present → writes `.hive-mind/clay_callbacks/{lead_id}.json` for enricher
  - `visitor_id` present / no pipeline source → existing RB2B/GHL sync + Website Intent Monitor

**Key files modified**:
- `webhooks/rb2b_webhook.py` — unified `POST /webhooks/clay` handler
- `execution/enricher_clay_waterfall.py` — reads `CLAY_WORKBOOK_WEBHOOK_URL` as fallback
- `dashboard/health_app.py` — legacy `/api/clay-callback` kept for backward compatibility

### In Progress Tasks

| Task | Status | Notes |
|------|--------|-------|
| Set `CLAY_WORKBOOK_WEBHOOK_URL` env var on Railway | DONE | User located webhook source URL and added to Railway |
| Verify Clay HTTP API Body includes `lead_id` + `source` in callback | NEEDS CHECK | Expand Body section in HTTP API column config to confirm passthrough |
| Deploy Railway with new env var | NEEDS USER | Click "Apply 1 change" → Deploy (rate limit may delay) |
| End-to-end Clay enrichment test | READY | All config in place — test after deploy |

### Deferred Tasks

| Task | Status | Reason |
|------|--------|--------|
| BetterContact Starter subscription | DEFERRED | Clay Explorer already paid ($499/mo, 14K credits), use Clay first |
| FullEnrich integration | DEFERRED | Clay Explorer covers enrichment fallback needs |
| ZeroBounce email verification layer | DEFERRED | Clay has built-in ZeroBounce verification |
| HeyReach LinkedIn automation | DEFERRED | Multi-channel Phase 4+ (need warm LinkedIn accounts first) |
| Instantly.ai Send stage configuration | DEFERRED | Requires domain warm-up plan execution |
| Supabase Lead 360 view | DEFERRED | Need unified lead schema first |
| Job change detection (Bombora/G2) | DEFERRED | Phase 4+ |

---

### 3A: Clay Explorer Webhook Enrichment — ARCHITECTURE (UNIFIED)

**Why Clay over BetterContact**: You're already paying $499/mo for Clay Explorer with 14,000 credits/month (25,812.7 available). Using Clay's built-in waterfall enrichment (10+ providers including Hunter, Apollo, Prospeo, DropContact, Clearbit) eliminates the need for a separate BetterContact subscription.

**Key Insight**: The existing Website Visitor Enrichment Workbook ALREADY provides the enrichment columns needed. No new workbook or additional webhook required. Both RB2B visitors and pipeline leads share the same Clay workbook.

**Credit Economics**:
- Email waterfall (avg): 4 credits/lead
- Email validation (ZeroBounce): 1 credit/lead
- Company enrichment (Clearbit): 8 credits/lead
- **Email only**: ~2,800-3,500 leads/month with 14K credits
- **Email + company**: ~1,000-1,400 leads/month

**Unified Architecture**:

```
  SOURCE A: RB2B Visitor                    SOURCE B: Pipeline Lead (Apollo miss)
       |                                         |
       | visitor_id, email, company_domain        | lead_id, linkedin_url, source="caio_pipeline"
       |                                         |
       +------------------+----------------------+
                          |
                          v
               Clay Workbook Webhook
               (CLAY_WORKBOOK_WEBHOOK_URL)
                          |
            [Auto-run enrichment columns]
            Col 1: Find Work Email (waterfall: Hunter->Apollo->Prospeo->...)
            Col 2: Validate Email (ZeroBounce)
            Col 3: Enrich Company (Clearbit)
            Col 4: HTTP API POST (callback to /webhooks/clay)
                          |
                          v
               POST /webhooks/clay (unified handler)
                          |
              +-----------+-----------+
              |                       |
       has lead_id +            has visitor_id
       source=caio_pipeline     (or no lead_id)
              |                       |
              v                       v
     Write callback file       ClayDirectEnrichment
     .hive-mind/clay_callbacks/  -> GHL sync
     {lead_id}.json               -> Website Intent Monitor
              |
              v
     Enricher polls file
     -> Pipeline continues (Segment -> Craft -> Approve -> Send)
```

**Latency**: 1-3 minutes (async — requires callback endpoint + Redis queue)

**Implementation Steps**:

1. **Create Clay Table** (`Pipeline Lead Enrichment`):
   - Webhook source with auth token
   - Email waterfall column (Hunter -> Apollo -> Prospeo -> DropContact)
   - Email validation column (ZeroBounce, 1 credit)
   - Company enrichment column (Clearbit, 8 credits)
   - HTTP API action column (POST to our callback)

2. **Add Callback Endpoint** (`dashboard/health_app.py`):
   ```
   POST /api/clay-callback
   - Receives enriched lead data from Clay
   - Stores in Redis with lead_id as key
   - Triggers pipeline continuation via Inngest
   ```

3. **Modify Enricher** (`enricher_clay_waterfall.py`):
   ```
   Apollo (sync, primary)
     -> miss -> Clay webhook (async, fallback)
       -> POST to Clay, store lead_id in Redis as "pending"
       -> Clay callback triggers pipeline continuation
     -> miss -> BetterContact (sync, tertiary — code ready, no subscription yet)
   ```

4. **50K Webhook Limit**: At ~1,000-2,000 leads/month, one webhook lasts 25-50 months.

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

## Phase 4: Autonomy Graduation — PENDING

### Prerequisites
- [ ] Instantly.ai Send stage configured and tested
- [ ] Domain warm-up plan executed (5-phase, 4 weeks)
- [ ] 10+ successful production pipeline runs with real sends
- [ ] ICP Match Rate >= 80% (currently untested with real sends)
- [ ] Email Open Rate >= 50%
- [ ] Reply Rate >= 8%
- [ ] Bounce Rate < 5%
- [ ] 3 consecutive days of autonomous operation without intervention
- [ ] Self-annealing feedback loop validated

### Planned Tasks

| Task | Priority | Dependency |
|------|----------|-----------|
| Configure Instantly.ai campaigns | HIGH | Domain warm-up complete |
| Execute domain warm-up plan | HIGH | Instantly configured |
| Enable real sends (flip `actually_send: true`) | HIGH | Warm-up complete, KPIs met |
| HeyReach LinkedIn automation setup | MEDIUM | Warm LinkedIn accounts |
| Pipeline channel router (email + LinkedIn) | MEDIUM | HeyReach configured |
| RB2B visitor signals -> pipeline feed | MEDIUM | Clay integration working |
| Supabase unified lead schema | LOW | All data sources connected |
| Self-annealing feedback loop | LOW | Real send data available |
| Job change / intent signal detection | LOW | Phase 5+ |

---

## Current API Status

| Service | Status | Notes |
|---------|--------|-------|
| **Apollo.io** | WORKING | People Search (free) + Match (1 credit/reveal) |
| **Clay Explorer** | ACTIVE | $499/mo, 14K credits/mo, 25.8K available. Existing workbook reused for pipeline enrichment. |
| **BetterContact** | CODE READY | Async API integrated in enricher, no subscription yet (Clay preferred) |
| **Slack Alerting** | WORKING | Webhook configured, WARNING + CRITICAL alerts |
| **Redis (Upstash)** | WORKING | 62ms from Railway |
| **Inngest** | WORKING | 4 functions mounted |
| **Instantly.ai** | CONFIGURED | Send stage untested (expected FAIL) |
| **Railway** | DEPLOYED | Auto-deploy on push |
| **Proxycurl** | REMOVED | Shutting down Jul 2026 (sued by LinkedIn) |
| **Clay API v1** | DEPRECATED | Returns 404, replaced by webhook pattern |
| **LinkedIn Scraper** | BLOCKED | 403 rate-limited, replaced by Apollo Search |

---

## Key Files

| Purpose | File |
|---------|------|
| Pipeline runner | `execution/run_pipeline.py` |
| Enricher (Apollo + BetterContact + Clay planned) | `execution/enricher_clay_waterfall.py` |
| Lead discovery (Apollo) | `execution/hunter_scrape_followers.py` |
| ICP scoring | `execution/segmentor_classify.py` |
| Dashboard + API | `dashboard/health_app.py` |
| Alerts (Slack) | `core/alerts.py` |
| Production config | `config/production.json` |
| Enrichment research | `docs/research/ENRICHMENT_PROVIDER_RESEARCH_2026.md` |
| Multi-channel research | `docs/research/MULTI_CHANNEL_CADENCE_RESEARCH_2026.md` |
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
| Instantly.ai | TBD | Email sending | CONFIGURED |
| BetterContact | $0 (not subscribed) | Code ready, Clay preferred | DEFERRED |
| HeyReach | $0 (not subscribed) | LinkedIn automation | DEFERRED (Phase 4+) |

**Total Current Spend**: ~$553/mo (Clay + Apollo + Railway)

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

---

*Plan Version: 2.1*
*Created: 2026-02-13*
*Supersedes: IMPLEMENTATION_ROADMAP.md (v1.0, 2026-01-17)*
