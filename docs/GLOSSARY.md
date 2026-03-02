---
title: CAIO Alpha Swarm Glossary
version: "1.0"
last_updated: 2026-03-02
audience: [all-agents, engineers, pto-gtm]
tags: [glossary, context-engineering, reference]
canonical_for: [domain-terminology]
---

# CAIO Alpha Swarm — Domain Glossary

Canonical definitions for all domain terms used across the codebase, documentation, and agent directives.

---

## Agents & Roles

| Term | Definition |
|------|-----------|
| **Alpha Swarm** | The 12-agent pipeline system (`chiefaiofficer-alpha-swarm`) for autonomous SDR outreach |
| **Queen Orchestrator** | Master coordinator agent (`execution/unified_queen_orchestrator.py`) that routes workflows across all agents |
| **Hunter** | Lead sourcing agent — scrapes LinkedIn, websites, and databases for prospects |
| **Enricher** | Data enrichment agent — runs the Apollo > BetterContact > Clay waterfall |
| **Segmentor** | ICP scoring agent — classifies leads into Tier 1/2/3 using scoring multipliers |
| **CRAFTER** | Email generation agent — writes personalized outreach using M.A.P. framework and templates |
| **Gatekeeper** | Approval gate agent — routes emails to HoS review queue before sending |
| **OPERATOR** | Unified dispatch agent (`execution/operator_outbound.py`) — handles Instantly + HeyReach sends, revival, cadence sync |
| **Scout** | Intent detection agent — monitors buying signals and engagement data |
| **Piper** | Visitor intelligence agent — processes RB2B webhook data for website visitors |
| **Coach** | Optimization agent — self-annealing and performance tracking (dormant) |
| **HoS** | Head of Sales — the human reviewer who approves/rejects pipeline-generated emails |
| **PTO/GTM** | Product/Technical Owner / Go-To-Market — business stakeholder providing inputs |

## Pipeline Stages

| Term | Definition |
|------|-----------|
| **6-Stage Pipeline** | Scrape > Enrich > Segment > Craft > Approve > Send — the end-to-end outreach flow |
| **Shadow Mode** | Safety mode where emails go to Redis queue + filesystem instead of real sends. Controlled by `shadow_mode: true` in `config/production.json` |
| **Ramp Mode** | Controlled scaling: starts at 5 sends/day, tier_1 only, 3 supervised days before auto-increase |
| **Dry Run** | Pipeline execution that validates all stages without side effects |
| **Live Fire** | Production pipeline execution with real API calls and actual sends |
| **Lane B / Canary** | Isolated test lane using synthetic leads (`scripts/canary_lane_b.py`) for safe HoS training |

## Lead Classification

| Term | Definition |
|------|-----------|
| **ICP** | Ideal Customer Profile — scoring criteria defined in `config/icp_config.py` |
| **Tier 1** | Highest-priority leads (multiplier 1.5x) — exact title + industry + company size match |
| **Tier 2** | Medium-priority leads (multiplier 1.2x) — partial match on 2+ criteria |
| **Tier 3** | Low-priority leads (multiplier 1.0x) — single criterion match or fallback |
| **Disqualifier** | Hard criteria that immediately reject a lead (e.g., competitor domain, role mismatch) |
| **Lead Signal** | Engagement or intent event tracked by `core/lead_signals.py` (21 statuses) |
| **Engagement Decay** | Time-based reduction of lead priority when no new signals arrive |

## Outreach Channels

| Term | Definition |
|------|-----------|
| **Instantly** | Cold email platform — V2 API, 6 warmed domains, sender `chris.d@` |
| **HeyReach** | LinkedIn automation platform — connection requests, messages, InMail |
| **GHL** | GoHighLevel CRM — contact sync, campaign management, meeting booking |
| **Multi-Channel Cadence** | 21-day 8-step sequence combining email + LinkedIn touchpoints (`execution/cadence_engine.py`) |

## Enrichment & APIs

| Term | Definition |
|------|-----------|
| **Waterfall** | Ordered fallback chain: Apollo (primary) > BetterContact (fallback) > Clay (position 3, feature-flagged) |
| **Apollo.io** | Primary enrichment API — `q_organization_name` does FUZZY matching (use exact names) |
| **BetterContact** | Secondary enrichment API — async polling model with status checks |
| **Clay** | Tertiary enrichment API — uses Redis LinkedIn URL correlation to bypass `lead_id` limitation. Gated by `CLAY_PIPELINE_ENABLED` |

## Safety & Guards

| Term | Definition |
|------|-----------|
| **EMERGENCY_STOP** | Env var that blocks ALL outbound sends when set |
| **Circuit Breaker** | Per-agent failure detector (`core/circuit_breaker.py`) — trips after 5 failures, exponential backoff, auto-reset after 5+ min |
| **Unified Guardrails** | 12-agent permission matrix (`core/unified_guardrails.py`, 1550 lines) — rate limiting, grounding evidence |
| **Quality Guard** | Deterministic content validator (`core/quality_guard.py`) — banned openers (10 regex), generic phrases (23), fingerprint dedup |
| **Deliverability Guard** | Pre-send email validator (`core/deliverability_guard.py`) — syntax, suppression, role/disposable checks |
| **Rejection Memory** | Per-lead rejection history (`core/rejection_memory.py`) — Redis primary + file fallback, 30-day TTL |
| **Multi-Layer Failsafe** | Input validation + Byzantine consensus for critical decisions (`core/multi_layer_failsafe.py`) |
| **Strict Auth** | Dashboard auth mode requiring `X-Dashboard-Token` header — query-token disabled in production/staging |

## Context Engineering

| Term | Definition |
|------|-----------|
| **Context Zone** | FIC methodology zones: SMART (<40%), CAUTION (40-70%), DUMB (>70%), CRITICAL (>90%) |
| **FIC** | Frequent Intentional Compaction — strategy to keep context window in SMART zone |
| **RPI** | Research > Plan > Implement — the standard agent workflow pattern |
| **Second Brain** | The `.hive-mind/knowledge/` directory containing company, customer, and messaging knowledge |
| **MEMORY.md** | Cross-session persistence file loaded into every Claude session (~5K tokens) |
| **CLAUDE.md** | Master session configuration — pitfalls, directives, mandatory read order |
| **Hot/Warm/Cold Tiers** | Persistence layers: Hot=Redis (real-time), Warm=`.hive-mind/` (per-run JSONL), Cold=Git (permanent) |

## Messaging & Templates

| Term | Definition |
|------|-----------|
| **M.A.P. Framework** | Messaging Architecture Pattern — structured approach to email personalization |
| **Blog-Triggered Email** | Outreach triggered by prospect visiting specific blog content (`.hive-mind/knowledge/templates/blog_triggered_emails.json`) |
| **Banned Opener** | Regex-matched first lines that get auto-rejected by Quality Guard (e.g., "I noticed...", "I saw...") |
| **Generic Phrase** | 23 overused phrases detected and flagged by Quality Guard |
| **Fingerprint Dedup** | Content hash comparison to prevent sending duplicate emails to same lead |

## Dashboard & Operations

| Term | Definition |
|------|-----------|
| **Seed Queue** | Dashboard-triggered synthetic email generator (`core/seed_queue.py`) — 15 personas, 11 templates |
| **Shadow Queue** | Redis bridge (`core/shadow_queue.py`) for local pipeline > Railway dashboard visibility |
| **Precision Scorecard** | Real-time KPI dashboard (`core/precision_scorecard.py`) — success rate, engagement, approval, send metrics |
| **Runtime Dependencies** | `/api/runtime/dependencies` endpoint exposing auth state, integration status, env config |

## Infrastructure

| Term | Definition |
|------|-----------|
| **Railway** | Production hosting platform — Linux container, port 8080 |
| **Upstash** | Managed Redis provider — used for shadow queue, state store, rejection memory |
| **CONTEXT_REDIS_PREFIX** | Canonical Redis key prefix (`caio:production:context`) — MUST use this for cross-env shared data |
| **STATE_REDIS_PREFIX** | Legacy prefix (differs local vs Railway) — do NOT use for shared data |
| **Hookdeck** | Webhook proxy/relay service for Instantly and HeyReach event routing |

## Testing

| Term | Definition |
|------|-----------|
| **Pre-commit Suite** | Curated 502-test gate (29 files, ~58s) in `.githooks/pre-commit` |
| **Curated Tests** | Handpicked test files covering Phase 4 critical paths — run on every commit |
| **Legacy Test Debt** | ~15 known failures in non-curated tests (Slack MCP, Calendar, PII, guardrails) |
| **Smoke Test** | Quick validation script for deployed instances (e.g., `scripts/deployed_full_smoke_checklist.py`) |
| **Strict-Auth Parity Smoke** | N1-N7 security validation on deployed instances (`scripts/strict_auth_parity_smoke.py`) |

## Learning Engines (Dormant)

| Term | Definition |
|------|-----------|
| **Dormant Engine** | Learning module that collects data but does NOT change behavior. See `docs/DORMANT_ENGINES.md` |
| **Feedback Loop** | Training tuple collector (`core/feedback_loop.py`) — PARTIALLY ACTIVE. Gated by `FEEDBACK_LOOP_POLICY_ENABLED` |
| **RL Engine** | Reinforcement learning infrastructure (`execution/rl_engine.py`) — DORMANT. Gated by `RL_ENGINE_ENABLED` |
| **Self-Annealing** | Template selection optimizer (`core/self_annealing_engine.py`) — DORMANT. Gated by `SELF_ANNEALING_ENGINE_ENABLED` |
| **A/B Test Engine** | Experiment harness (`core/ab_test_engine.py`) — DORMANT. Gated by `AB_TEST_ENGINE_ENABLED` |
| **Self-Learning ICP** | Adaptive ICP scorer (`core/self_learning_icp.py`) — DORMANT. Gated by `SELF_LEARNING_ICP_ENABLED` |
| **Feature Flag** | Env var that gates dormant engine activation — default `false`, requires Phase 5 |

## Compliance

| Term | Definition |
|------|-----------|
| **CAN-SPAM** | US email marketing law — requires unsubscribe, physical address, honest subject lines |
| **GDPR** | EU data protection regulation — consent, right to erasure, data minimization |
| **LinkedIn ToS** | LinkedIn Terms of Service — rate limits, content restrictions for automated outreach |
| **Brand Safety** | Content rules preventing reputational risk in outreach messaging |

---

*Maintained by the engineering team. Update this glossary when introducing new domain terms.*
