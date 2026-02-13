# CAIO Alpha Swarm: LinkedIn Sustainability & Phase 3 Prerequisites Plan

**Date**: 2026-02-13
**Status**: AWAITING APPROVAL
**Author**: Claude Code (Opus 4.6) + Research Agents

---

## Executive Summary

The cookie-based LinkedIn scraper is permanently unsustainable. The industry has moved to API-first data providers. Our research across 15+ agentic SDR platforms (11x, Artisan, Clay, Apollo, Instantly, Regie, Amplemarket, Qualified/Piper) confirms one universal pattern: **waterfall enrichment via B2B data APIs, zero LinkedIn scraping**.

This plan covers the minimum viable changes to make CAIO Alpha Swarm production-sustainable before Phase 3 (Expand & Harden). Complex features (multi-channel cadences, inbound visitor identification, third-party intent data) are deferred to Phase 4+.

---

## Current State (Post Phase 2 Fixes)

| Component | Status | Provider |
|-----------|--------|----------|
| Lead Discovery (HUNTER) | Cookie blocked, API fallback scaffold | Apollo search (endpoint fixed) |
| Enrichment (ENRICHER) | Working with Apollo key | Apollo People Match (LIVE) |
| Segmentor | Working | ICP scoring + tier assignment |
| Crafter | Working | Email campaign generation |
| Approver | Working | Dashboard HITL flow |
| Sender | Scaffold only | Instantly API (configured, untested) |
| Alerts | Working | Slack webhook (WARNING + CRITICAL) |
| Dashboard | Working | FastAPI on Railway |

**Environment Variables**:
- `APOLLO_API_KEY`: SET (validated - enrichment returns real data)
- `PROXYCURL_API_KEY`: NOT SET (Proxycurl shutting down Jul 2026 - deprioritized)
- `LINKEDIN_COOKIE`: SET (blocked/403 - dead credential)
- `SLACK_WEBHOOK_URL`: SET (working)
- `INSTANTLY_API_KEY`: SET (untested)
- `SUPABASE_URL`: SET (untested in pipeline)
- `OPENAI_API_KEY`: SET
- `REDIS_URL`: SET

---

## Research Findings Summary

### How the Industry Replaced LinkedIn Scraping

Every production-grade SDR tool uses the same architecture:

1. **Lead Discovery**: Apollo People Search API (free, no credits) or built-in B2B databases
2. **Enrichment**: Waterfall across 2-4 API providers (Apollo -> PDL -> RocketReach -> email pattern)
3. **Intent Signals**: Firmographic scoring + job change detection + optional 3rd-party (Bombora)
4. **Outreach**: Email-first, LinkedIn as optional engagement channel (not data source)

Key finding: **LinkedIn is treated as an outreach channel, NOT a data source**. Discovery and enrichment happen entirely through B2B data APIs.

### Qualified/Piper Insights

Piper's core pattern is the **Visitor 360 profile** — merging firmographic data, behavioral signals, intent data, and CRM records into a single composite record. The applicable concept for CAIO is: build a unified lead record that all agents read from and write to (currently `.hive-mind/` files; target: Supabase).

Piper's LinkedIn identification is company-level (reverse IP via Clearbit Reveal), not person-level. Person-level identification requires either: (a) the person interacts (form fill, chat), or (b) third-party deanonymization tools (RB2B at $119/mo). This is a Phase 4+ consideration.

### Critical Warning: Proxycurl Shutting Down

Proxycurl (our fallback enrichment provider) was sued by LinkedIn and is shutting down July 4, 2026. We should NOT invest in Proxycurl integration. People Data Labs (PDL) is the recommended replacement if a second provider is needed.

---

## Plan: Minimum Viable Fixes for Phase 3 Readiness

### Fix 1: Replace HUNTER LinkedIn Scraping with Apollo People Search
**Files**: `execution/hunter_scrape_followers.py`
**Effort**: Small (endpoint already scaffolded, needs response parsing fix)

**What changed**: Apollo's free People Search (`/api/v1/mixed_people/api_search`) returns anonymized results — titles and companies match, but names/emails/LinkedIn URLs are not revealed without credits. The correct approach for lead discovery is:

1. Use Apollo People Search to find ICP-matching contacts at target companies (free)
2. The search returns `id` fields for each matched person
3. Use Apollo People Match to reveal contact details only for ICP-matched leads (1 credit each)

**Changes needed**:
- Update `_fetch_via_apollo()` to use the two-step flow: search (free) -> match (credit per reveal)
- Handle the case where People Search returns anonymized records
- Add `organization_domains` filter as primary (more reliable than `organization_name`)

**Why this matters**: Replaces the blocked LinkedIn cookie with a sustainable, rate-limited API. Apollo's database covers 275M+ contacts — broader than LinkedIn scraping ever reached.

### Fix 2: Validate Apollo Enrichment in Production Pipeline
**Files**: `execution/enricher_clay_waterfall.py`, `execution/run_pipeline.py`
**Effort**: Small (enricher already routes to Apollo, just needs live validation)

**What changed**: The Apollo API key is now set and validated. The enricher correctly routes to Apollo People Match when `APOLLO_API_KEY` is configured. This needs an end-to-end production pipeline run with real enrichment (not mock).

**Changes needed**:
- Run production pipeline with Apollo enrichment active
- Verify `EnrichedLead` data quality from real Apollo responses
- Confirm segmentor handles real company data (nested dicts with actual values)
- Monitor credit usage (each enrichment costs 1+ credits)

### Fix 3: Remove Proxycurl References (Pre-Sunset Cleanup)
**Files**: `execution/enricher_clay_waterfall.py`, `execution/hunter_scrape_followers.py`
**Effort**: Minimal

**What**: Proxycurl is shutting down July 2026. Rather than keeping dead code, downgrade Proxycurl to a deprecated-but-present fallback. No new development on Proxycurl integration.

**Changes needed**:
- Add deprecation warning when `PROXYCURL_API_KEY` is detected
- Keep existing code functional (it works if key is set) but don't invest in fixes
- Document People Data Labs (PDL) as future Provider 2 replacement (Phase 4)

### Fix 4: Enrich-Then-Score Flow (Currently Scores Before Real Enrichment)
**Files**: `execution/run_pipeline.py`, `execution/segmentor_classify.py`
**Effort**: Small

**Problem**: The segmentor's ICP scoring (`calculate_icp_score`) reads `lead.get("company", {}).get("employee_count")`, `lead.get("company", {}).get("industry")`, etc. With real Apollo enrichment, these nested dicts are populated with actual data. But the scoring weights were tuned against mock data (random employee counts, generic industries).

**Changes needed**:
- Run segmentor against Apollo-enriched leads and verify score distribution
- Adjust scoring weights if distribution is heavily skewed (all tier_4 or all tier_1)
- No structural code changes — just validation and potential threshold tuning

### Fix 5: Slack Alert on Real API Errors
**Files**: `core/alerts.py` (already done), `execution/enricher_clay_waterfall.py`
**Effort**: Already complete

**Status**: The enricher already sends `send_critical()` on Apollo credit exhaustion (402) and `send_warning()` on enrichment failures. Slack webhook delivers WARNING + CRITICAL alerts. This is working.

---

## What Is NOT In This Plan (Deferred to Phase 4+)

| Feature | Why Deferred | Phase |
|---------|-------------|-------|
| People Data Labs as Provider 2 | Not needed until Proxycurl sunsets (Jul 2026) or Apollo alone isn't sufficient | Phase 4 |
| Multi-channel cadences (email + LinkedIn outreach) | Requires LinkedIn automation partner (not available via API) | Phase 4+ |
| Inbound visitor identification (RB2B / Clearbit Reveal) | Requires landing pages and website traffic | Phase 4+ |
| Third-party intent data (Bombora / G2) | Enterprise pricing, not justified at current scale | Phase 5 |
| Lead 360 composite record in Supabase | Requires schema design and migration from file-based storage | Phase 4 |
| Email pattern matching + verification (ZeroBounce) | Only needed when Apollo match rate proves insufficient | Phase 4 |
| Parallel waterfall enrichment | Sequential is fine at current volume (<100 leads/day) | Phase 4 |
| Job change detection (UserGems-style) | Requires periodic re-enrichment infrastructure | Phase 5 |

---

## Implementation Order

```
Fix 1: Apollo People Search two-step flow     [~30 min]
Fix 2: Live Apollo enrichment pipeline run     [~15 min]
Fix 4: Validate segmentor with real data       [~15 min]
Fix 3: Proxycurl deprecation warning           [~5 min]
                                               ─────────
                                Total:         ~65 min
```

Fix 5 (Slack alerts) is already complete.

---

## Expected Outcome After Fixes

| Metric | Before | After |
|--------|--------|-------|
| Lead discovery | 0 (blocked) | 25-50 per search (Apollo API) |
| Enrichment match rate | 0% (Clay deprecated) | 60-70% (Apollo People Match) |
| Pipeline completion | Sandbox only | Production with real data |
| Cost per enriched lead | $0 (non-functional) | ~$0.07-0.13 (Apollo credits) |
| Hang time per lead | ~3.5 min (Clay retry) | <2s (Apollo API) |
| LinkedIn dependency | 100% (cookie) | 0% (API-only) |

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Apollo API key rate-limited | Low | 2-retry policy with 5s backoff already in place |
| Apollo credits exhausted | Medium | `send_critical()` alert on 402; monitor via dashboard |
| Apollo search returns 0 results for niche companies | Medium | Pipeline gracefully falls to test data; real data improves with broader title filters |
| Proxycurl sunset before PDL integration | Low (5 months away) | Not currently used; deprecation warning added |

---

## Decision Points for Review

1. **Approve this plan as-is** — Execute Fixes 1-4 in order (~65 min)
2. **Add PDL integration now** — Adds ~2 hours but provides a second enrichment provider immediately
3. **Skip Fix 1 (Apollo search)** — Keep using test data for discovery, only use Apollo for enrichment of manually-provided leads
4. **Other direction** — Specify what to change
