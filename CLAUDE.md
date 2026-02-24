# Chief AI Officer Alpha Swarm - Claude Configuration

## Project Context

**Project**: Chief AI Officer Alpha Swarm
**Purpose**: Autonomous SDR pipeline — lead discovery, enrichment, multi-channel outreach
**Founder**: Chris Daigle (https://www.linkedin.com/in/doctordaigle/)
**Company**: Chiefaiofficer.com
**Platform**: Railway (production) at `caio-swarm-dashboard-production.up.railway.app`
**Dashboard**: v3.0 full 4-tab UI (Overview/Email Queue/Campaigns/Settings) + live KPIs + compliance checks
**Latest successful production deploy**: commit `0f0e0a9` (2026-02-19) — Compliance footer fix (Reply STOP) + Dashboard v3.0 + P0 checks

### Mandatory Read Order (Every New Session)

1. `CLAUDE.md`
2. `docs/CAIO_CLAUDE_MEMORY.md` (living runtime truth)
3. `CAIO_IMPLEMENTATION_PLAN.md` (v4.5)
4. `docs/CAIO_UIUX_BULLETPROOF_HANDOFF_FOR_CLAUDE_2026-02-19.md` (UI/UX hardening handoff)

### Current Status (Phase 4: Autonomy Graduation — 98%)

```
Phase 0-3: Foundation → Burn-In → Harden    COMPLETE (33+ pipeline runs, 10 consecutive 6/6 PASS)
Phase 4A: Instantly V2 Go-Live               COMPLETE (6 domains warmed, 100% health)
Phase 4B: HeyReach LinkedIn Integration      80% (API verified, 3 campaigns, 4 webhooks — awaiting LinkedIn warmup)
Phase 4C: OPERATOR Agent                     COMPLETE (unified dispatch + revival scanner + GATEKEEPER gate)
Phase 4D: Multi-Channel Cadence              COMPLETE (8-step 21-day sequence + CRAFTER follow-ups + auto-enroll)
Phase 4E: Supervised Live Sends              RAMP MODE ACTIVE (5/day, tier_1, 3 supervised days)
Phase 4F: Monaco Signal Loop                 COMPLETE (lead_signals + activity_timeline + leads dashboard + decay cron)
```

**Safety**: `actually_send: true` (informational), real control: `--live` CLI flag + `EMERGENCY_STOP` env var + `gatekeeper_required: true`.
**Ramp Mode**: 5 emails/day, tier_1 only (C-Suite at agencies/consulting/law), 3 supervised days starting 2026-02-18. Set `operator.ramp.enabled: false` to graduate to 25/day.

### Pending Queue Non-Regression Contract (Required)

To prevent repeating "Tier queue drift / campaign mismatch" incidents, every pending card in `/api/pending-emails` MUST expose deterministic classifier metadata:

- `classifier.queue_origin` (e.g., `pipeline`, `gatekeeper_queue_sync`, `website_intent_monitor`)
- `classifier.message_direction` (`outbound` or `inbound`)
- `classifier.target_platform` (`ghl`, `instantly`, `heyreach`, `unknown`)
- `classifier.sync_state` (`external_campaign_mapped`, `pending_external_campaign_mapping`, `n/a_ghl_direct_path`, etc.)
- `campaign_ref.internal_id` + `campaign_ref.pipeline_run_id`
- `campaign_ref.external_campaign_id/name` when routed to Instantly

Operational interpretation rule:
- If `target_platform=ghl` and `sync_state=n/a_ghl_direct_path`, those cards are **not** expected to appear as Instantly campaign sequence steps.
- If `target_platform=instantly`, external campaign metadata must be present (or explicitly flagged pending mapping).

Pre-live gate (must pass in staging + production):
1. `python scripts/deployed_full_smoke_matrix.py --staging-url <...> --staging-token <...> --production-url <...> --production-token <...>`
2. Assert `pending_emails_classifier_contract.passed=true`.
3. Assert pending queue debug excludes stale/tier-mismatch/placeholder entries during ramp mode.

Do not proceed to unsupervised sends if classifier contract fails.

See `docs/CAIO_TASK_TRACKER.md` for detailed progress and next steps.

### Dashboard Pipeline Improvements (commit `b8dfc0f`)

- **HoS Dashboard v3.0** (`/sales`): Full 4-tab UI — Overview (live KPIs from `/api/scorecard`, 12-agent health grid, pipeline funnel, constraint banner, activity feed), Email Queue (pending approvals + review history + queue diagnostics + refresh heartbeat), Campaigns (dispatch history, cadence pipeline, queue metrics), Settings (ramp config, guardrails, dependencies, safety controls). Backend compliance checks (reply_stop, signature, CTA, footer) on every pending email. Tab routing via URL hash.
- **Email bodies fixed**: Pipeline send stage now extracts subject/body from per-lead sequences (CRAFTER stores sequences on each lead, not campaign level)
- **Enriched lead insights**: Shadow emails now include location, employees, industry in `recipient_data` for dashboard display
- **HoS-aligned scrape targets**: TARGET_COMPANIES aligned to HoS Tier 1 ICP: Wpromote, Tinuiti, Power Digital (agencies), Insight Global, Kforce (staffing), Slalom, West Monroe (consulting), ShipBob (e-commerce), Chili Piper (Tier 2 test). Old SaaS targets removed.
- **Deliverability guards (2026-02-18)**: 4-layer defense in `instantly_dispatcher.py` — Guard 1: email format (RFC 5322), Guard 2: excluded domains (12 competitors + 7 customer domains), Guard 3: domain concentration (max 3/domain/batch), Guard 4: individual email exclusion (27 customer emails from HoS Section 1.4). Config in `production.json` under `guardrails.deliverability`.
- **Tier_1 scoring**: Requires 80+ ICP points (with HoS multipliers). C-Suite at agency/consulting: 20pts size + 25pts title + 20pts industry = 65 x 1.5 = 97 → tier_1. VP at SaaS: 20 + 22 + 15 = 57 x 1.2 = 68 → tier_2.

### Autonomy Graduation Path (Ramp → Full Autonomy)

**Current state**: RAMP MODE — 5 emails/day, tier_1 only, GATEKEEPER batch approval required.

**Phase 4E Completion Checklist**:
1. Run pipeline with mid-market source: `echo yes | python execution/run_pipeline.py --mode production`
2. Approve tier_1 leads in HoS dashboard (`/sales`)
3. First live dispatch: `python -m execution.operator_outbound --motion outbound --live`
4. Review GATEKEEPER batch at `/api/operator/pending-batch` → approve → re-run dispatch
5. Activate DRAFTED campaigns in Instantly (dashboard UI or API)
6. Monitor 3 days: open rate >=50%, reply rate >=8%, bounce <5%

**Graduation to Full Autonomy** (after 3 clean supervised days):
```json
// config/production.json changes:
"operator.ramp.enabled": false,          // Unlocks 25 emails/day + all tiers
"operator.gatekeeper_required": false,   // Optional: skip batch approval
// HeyReach LinkedIn: enable after 4-week warmup
```

**KPI Red Flags** (trigger `EMERGENCY_STOP`):
| Metric | Target | Red Flag |
|--------|--------|----------|
| Open rate | >=50% | <30% (deliverability) |
| Reply rate | >=8% | 0 replies after 15 sends |
| Bounce rate | <5% | >10% (email quality) |
| Unsubscribe | <2% | >5% (spam risk) |

---

## Agent Architecture

### Alpha Swarm Agents (12 Agents + Queen)

| Agent | Role | Key Files |
|-------|------|-----------|
| ALPHA QUEEN | Master Orchestrator | `execution/unified_queen_orchestrator.py` |
| HUNTER | Lead Discovery (Apollo — default source: vidyard, non-competitor) | `execution/hunter_scrape_followers.py` |
| ENRICHER | Data Enrichment (Apollo + BetterContact) | `execution/enricher_clay_waterfall.py` |
| SEGMENTOR | ICP Scoring + Tier Assignment | `execution/segmentor_classify.py` |
| CRAFTER | Campaign Copy + Cadence Follow-ups | `execution/crafter_campaign.py` |
| GATEKEEPER | AE Approval Gate | `execution/gatekeeper_queue.py` |
| OPERATOR | Unified Outbound Execution (3 motions) | `execution/operator_outbound.py` |
| | - `dispatch_outbound()`: Instantly email + HeyReach LinkedIn | |
| | - `dispatch_cadence()`: 21-day follow-up sequence | `execution/cadence_engine.py` |
| | - `dispatch_revival()`: GHL stale contact re-engagement | `execution/operator_revival_scanner.py` |
| SCOUT | Pipeline Intelligence | `execution/revenue_scout_intent_detection.py` |
| COACH | Pipeline Coaching | `core/call_coach.py` |
| PIPER | Pipeline Management | `execution/ingest_ghl_deals.py` |
| SCHEDULER | Calendar + Scheduling | `core/scheduler_service.py` |
| RESEARCHER | Read-Only Research | `execution/researcher_agent.py` |

---

---

## File Organization

```
chiefaiofficer-alpha-swarm/
├── .hive-mind/                    # Persistent memory & state
│   ├── knowledge/                 # Vector DB, product context
│   ├── scraped/                   # Raw scraped data (Apollo)
│   ├── enriched/                  # Enriched leads
│   ├── campaigns/                 # Generated campaigns
│   ├── shadow_mode_emails/        # Shadow email queue (LOCAL FALLBACK — primary is Redis)
│   ├── lead_status/               # Signal loop state per lead (JSONL)
│   ├── cadence_state/             # Cadence engine state per lead
│   ├── audit/                     # Gatekeeper approval/rejection logs
│   ├── operator_state.json        # OPERATOR daily state (dedup, counts)
│   └── unsubscribes.jsonl         # Suppression list (append-only)
├── config/
│   └── production.json            # Master config (shadow_mode, actually_send, domains, cadence)
├── core/                          # Shared libraries
│   ├── lead_signals.py            # Lead signal loop (21 statuses, decay detection)
│   ├── activity_timeline.py       # Per-lead event aggregation
│   ├── alerts.py                  # Slack alerting (WARNING, CRITICAL, INFO)
│   ├── shadow_queue.py             # Redis-backed shadow email queue (local↔Railway bridge)
│   ├── circuit_breaker.py         # Failure protection (3-trip, 5min reset)
│   ├── ghl_local_sync.py          # GHL contact cache + search
│   ├── unified_guardrails.py      # Main guardrails system
│   └── ...                        # 60+ modules
├── dashboard/
│   ├── health_app.py              # FastAPI app (50+ endpoints, port 8080)
│   ├── leads_dashboard.html       # Lead Signal Loop UI (/leads)
│   ├── hos_dashboard.html         # Head of Sales email queue (/sales) — v2.4, RAMP MODE banner
│   └── scorecard.html             # Precision Scorecard (/scorecard)
├── execution/                     # Agent execution scripts
│   ├── run_pipeline.py            # 6-stage pipeline runner (send stage extracts per-lead sequences for email body)
│   ├── operator_outbound.py       # OPERATOR agent (3 motions: outbound/cadence/revival)
│   ├── operator_revival_scanner.py # GHL stale contact mining + scoring
│   ├── cadence_engine.py          # 21-day Email+LinkedIn cadence scheduler
│   ├── instantly_dispatcher.py    # Shadow → Instantly campaigns
│   ├── heyreach_dispatcher.py     # Lead-list-first LinkedIn dispatch
│   ├── hunter_scrape_followers.py # Apollo People Search + Match
│   ├── enricher_clay_waterfall.py # Apollo (primary) + BetterContact (fallback)
│   ├── segmentor_classify.py      # ICP scoring + "Why This Score"
│   ├── crafter_campaign.py        # Campaign copy + cadence follow-up templates
│   ├── gatekeeper_queue.py        # Approval queue management
│   └── ...                        # 70+ scripts
├── webhooks/
│   ├── instantly_webhook.py       # Email open/reply/bounce/unsub handlers
│   ├── heyreach_webhook.py        # 11 LinkedIn event handlers
│   └── rb2b_webhook.py            # RB2B visitor enrichment
├── scripts/
│   ├── canary_lane_b.py               # Lane B: Safe HoS training with synthetic leads (no real contacts)
│   ├── register_instantly_webhooks.py  # Instantly webhook CRUD
│   ├── register_heyreach_webhooks.py   # HeyReach webhook CRUD
│   └── ...                        # Deploy, test, validate scripts
├── mcp-servers/
│   ├── ghl-mcp/                   # GHL CRM + Calendar MCP server
│   ├── instantly-mcp/             # Instantly V2 MCP server
│   ├── hunter-mcp/                # Hunter MCP server
│   └── enricher-mcp/              # Enricher MCP server
├── directives/                    # SOPs
├── docs/                          # Documentation
│   ├── CAIO_TASK_TRACKER.md       # Single source of truth for progress
│   └── research/                  # Provider research docs
└── CAIO_IMPLEMENTATION_PLAN.md    # Full implementation plan (v4.5)
```

---

## Key Directives Reference

| Directive | Purpose |
|-----------|---------|
| `directives/scraping_sop.md` | LinkedIn scraping rules |
| `directives/enrichment_sop.md` | Clay/RB2B enrichment |
| `directives/icp_criteria.md` | ICP definition |
| `directives/campaign_sop.md` | Campaign creation |
| `directives/compliance.md` | Safety rules |

---

## Tech Stack Integration

| Platform | API Key Variable | Purpose |
|----------|-----------------|---------|
| GoHighLevel | `GHL_API_KEY` | CRM + Nurture Email (chiefai.ai domain) + Calendar |
| Instantly | `INSTANTLY_API_KEY` | Cold Outreach Email (V2 API, 6 domains, round-robin) |
| HeyReach | `HEYREACH_API_KEY` | LinkedIn Outreach (connection requests, DMs, InMails) |
| Apollo.io | `APOLLO_API_KEY` | Lead Discovery (People Search) + Enrichment (People Match) |
| Clay | `CLAY_API_KEY` | RB2B Visitor Enrichment only (NOT pipeline leads) |
| RB2B | `RB2B_WEBHOOK_SECRET` | Visitor ID (webhook-based) |
| Supabase | `SUPABASE_URL`, `SUPABASE_KEY` | Data Layer |
| Slack | `SLACK_WEBHOOK_URL` | Alerts (WARNING, CRITICAL, INFO) |
| Twilio | `TWILIO_ACCOUNT_SID` | SMS/Voice (future) |
| SendGrid | `SENDGRID_API_KEY` | Transactional email (future) |
| Redis (Upstash) | `CONTEXT_REDIS_PREFIX` | Context caching, rate limiting, **shadow email queue** |

### Email + LinkedIn Platform Strategy (Multi-Channel)

| Channel | Platform | Domains/Accounts | Daily Limit | Purpose |
|---------|----------|------------------|-------------|---------|
| Cold email | Instantly (V2) | 6 domains, chris.d@ sender | 25/day (warmed) | Cold outreach, round-robin rotation |
| LinkedIn | HeyReach | 3 CAIO campaigns (tier 1/2/3) | 5/day (warmup) → 20/day | Connection requests + DMs |
| Nurture/warm | GHL (LC Email) | chiefai.ai | N/A | Warm leads, follow-ups, booking confirmations |
| Revival | Instantly (warm) | GHL nurture domains | 5/day | Re-engagement of stale GHL contacts |

**Instantly Cold Domains (all 100% health)**:
`chiefaiofficerai.com`, `chiefaiofficerconsulting.com`, `chiefaiofficerguide.com`, `chiefaiofficerlabs.com`, `chiefaiofficerresources.com`, `chiefaiofficersolutions.com`

> **NEVER send cold outreach through GHL. NEVER send nurture through Instantly. Domain reputation isolation is non-negotiable.**

---

## Commands

```bash
# --- Pipeline ---
echo yes | python execution/run_pipeline.py                    # Full 6-stage pipeline (non-interactive)
python execution/run_pipeline.py --mode sandbox                # Sandbox mode with test data

# --- OPERATOR Agent (unified dispatch) ---
python -m execution.operator_outbound --status                 # Today's state + warmup schedule
python -m execution.operator_outbound --motion outbound --dry-run   # Dry-run email + LinkedIn dispatch
python -m execution.operator_outbound --motion cadence --dry-run    # Dry-run cadence follow-ups
python -m execution.operator_outbound --motion revival --dry-run    # Dry-run GHL revival
python -m execution.operator_outbound --motion all --dry-run        # All 3 motions (dry-run)
python -m execution.operator_outbound --history                # Last 50 dispatch logs

# --- Cadence Engine ---
python -m execution.cadence_engine --due                       # Actions due today
python -m execution.cadence_engine --status                    # Cadence summary stats
python -m execution.cadence_engine --list                      # All enrolled leads
python -m execution.cadence_engine --enroll user@example.com   # Manually enroll lead
python -m execution.cadence_engine --sync                      # Sync signals (exit replied/bounced)

# --- Revival Scanner ---
python -m execution.operator_revival_scanner --scan --limit 10 # Preview revival candidates

# --- Lane B: Canary Training (safe HoS practice, no real contacts) ---
python scripts/canary_lane_b.py                               # Generate 5 canary training emails
python scripts/canary_lane_b.py --count 3                     # Generate N canary emails
python scripts/canary_lane_b.py --status                      # Show canary email statuses
python scripts/canary_lane_b.py --clear                       # Remove all canary emails from queue

# --- Dispatchers (standalone) ---
python -m execution.instantly_dispatcher --dry-run             # Preview Instantly dispatch
python -m execution.heyreach_dispatcher --dry-run              # Preview HeyReach dispatch

# --- Webhook Registration ---
python scripts/register_instantly_webhooks.py --list           # List registered webhooks
python scripts/register_heyreach_webhooks.py --list            # List registered webhooks

# --- Dashboard ---
uvicorn dashboard.health_app:app --host 0.0.0.0 --port 8080   # Start dashboard

# --- Lead Discovery + Enrichment ---
python execution/hunter_scrape_followers.py --url "linkedin_url"
python execution/test_connections.py                           # Test API connections
```

---

## HoS Email Crafting Reference (Canonical — Source: HEAD_OF_SALES_REQUIREMENTS 01.26.2026)

This section is the **authoritative reference** for all outbound email copy, ICP definitions, and messaging. Every session uses this as the canonical basis for crafting emails.

### Offer & Positioning

- **Offer**: Fractional Chief AI Officer embedding into mid-market firms
- **Buyer**: Execs under pressure, skeptical, but open to AI transformation
- **KPI**: Booked calls with qualified buyers
- **Pain Points**: Stalled AI pilots, no AI lead, leadership pressure, CTO buried in legacy tech
- **Mechanism**: M.A.P.™ Framework — Measure → Automate → Prove (90-day cycles)
- **Proof**: 1,000+ hrs clawed back, 27% productivity boost, 300+ hrs saved in 30 days, AI handles work of 20+ staff
- **Offer Stack**: Embedded exec + Day 1 Bootcamp + support layers + risk-free guarantee
- **Key Line**: "Measurable ROI, or you don't pay the next phase"

### ICP Tier Definitions

| Tier | Titles | Ideal Industries | Company Size | Revenue | Multiplier |
|------|--------|-----------------|--------------|---------|------------|
| **1** | CEO, Founder, President, COO, Owner, Managing Partner | Agencies, Staffing, Consulting, Law/CPA, Real Estate, E-commerce | 51-500 (sweet: 101-250) | $5-100M | 1.5x |
| **2** | CTO, CIO, CSO, Chief of Staff, VP Ops/Strategy, Head of Innovation, Managing Director | B2B SaaS, IT Services, Healthcare, Financial Services | 51-500 | $5-100M | 1.2x |
| **3** | Director Ops/IT/Strategy, VP Engineering, Head of AI/Data | Manufacturing, Logistics, Construction, Home Services | 10-1000 | $1-250M | 1.0x |

**Disqualify (NEVER Contact)**: <10 employees, >1000 employees, <$1M revenue, Government, Non-profit, Education, Academic, Current customers, Competitors.

### 11 Email Angles Summary

**Tier 1 (C-Suite / Founders — 4 angles)**:
- **A: Executive Buy-In** — "Fractional CAIO" gap, M.A.P.™ 90-day pitch, Day 1 Bootcamp CTA
- **B: Industry-Specific** — YPO/Construction/Manufacturing pain, back-office automation, 300+ hrs saved
- **C: Hiring Trigger** — Company hiring AI roles, "bridge strategy" pitch, set roadmap before hire starts
- **D: Value-First** — 2-minute AI Readiness audit, soft CTA ("Mind if I send the link over?")

**Tier 2 (CTO, CIO, VP Ops, Head of Innovation — 3 angles)**:
- **A: Tech Stack Integration** — AI integration playbook for their specific stack, lead enrichment/doc processing/support triage
- **B: Operations Efficiency** — 40-60% time savings, M.A.P. framework, "open to a brief sync?"
- **C: Innovation Champion** — 75% of AI pilots stall, AI Council inside company, 90-day bootcamp→co-pilot→handoff

**Tier 3 (Directors, Managers, Smaller Companies — 4 angles)**:
- **A: Quick Win** — One workflow to automate, 8 hrs/month back, "Reply yes" CTA
- **B: Time Savings** — 10 hrs/week back, AI agents not chatbots, "send a quick video?"
- **C: Competitor FOMO** — Others already automating, 40-60% time savings, "reply show me"
- **D: DIY Resource** — Free 1-page checklist, tools <$100/mo, softest CTA

### Follow-Up Sequences

- **Follow-Up 1 (Day 3-4)**: Two variants:
  - *Value-First*: AI Readiness audit, no pitch, 3 biggest automation wins
  - *Case Study*: 27% productivity boost, 300+ hours saved, "Want me to share the one-pager?"
- **Follow-Up 2 (Day 7 — Break-Up)**: Three variants:
  - *Permission to Close*: "I'll take this off my follow-up list"
  - *Last Value Drop*: Quick win automations + real metrics + "book call or reply not now"
  - *Direct Yes/No/Not Yet*: Three-option close (one word is all I need)

### Objection Handling Playbook

1. **"We already have CRM/Apollo/ZoomInfo"** → Complementary, not competitive. We automate the "what" and "how"
2. **"Already have a solution"** → Acknowledge, plant seeds of doubt (forecasting, pipeline visibility, rep productivity)
3. **"What's the pricing?"** → Lead with ROI, pivot to call ("most teams see ROI within 90 days")
4. **"Not interested"** → Graceful exit, remove from sequence immediately
5. **"Need to talk to my team"** → Schedule specific follow-up ("reach back out next quarter?")

### Email Signature & CAN-SPAM Footer

- **Sender**: Dani Apgar, Chief AI Officer
- **Booking Link**: `https://caio.cx/ai-exec-briefing-call`
- **Opt-out**: "Reply STOP to unsubscribe."
- **Physical Address**: 5700 Harper Dr, Suite 210, Albuquerque, NM 87109
- **Support**: support@chiefaiofficer.com

Footer block (appended to every email):
```
---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109
```

### Customer Exclusion List (27 emails, 7 domains — from GHL export)

**Domains (block ALL emails)**: jbcco.com, frazerbilt.com, immatics.com, debconstruction.com, credegroup.com, verifiedcredentials.com, exitmomentum.com

**Individual emails**: chudziak@jbcco.com, hkephart@frazerbilt.com, jmusil@jbcco.com, imorris@jbcco.com, mdabler@jbcco.com, maria.martinezcisnado@immatics.com, mm@immatics.com, slee@debconstruction.com, bzupan@jbcco.com, mfolsom@jbcco.com, kelsey.irvin@credegroup.com, michael.loveridge@credegroup.com, amejia@debconstruction.com, kjacinto@debconstruction.com, lagriffin@frazerbilt.com, aneblett@verifiedcredentials.com, tek@debconstruction.com, wmitchell@frazerbilt.com, cole@exitmomentum.com, alex.wagas@credegroup.com, avali@debconstruction.com, jnavarro@jbcco.com, kvale@frazerbilt.com, phirve@frazerbilt.com, mkcole@frazerbilt.com, tschaaf@jbcco.com, sharrell@frazerbilt.com

---

## Important Reminders

- Do what has been asked; nothing more, nothing less.
- NEVER create files unless absolutely necessary.
- ALWAYS prefer editing existing files.
- NEVER proactively create documentation unless requested.
- Never save working files to the root folder.
- **ALL campaigns require AE approval via GATEKEEPER**.
- **ALWAYS update** `docs/CAIO_CLAUDE_MEMORY.md` after deploys/hotfixes/incidents.
- After updating memory, sync key truth back into `CLAUDE.md` (deploy hash, gates, active risks).

### CRITICAL: Local ↔ Railway Filesystem Constraint (ARCHITECTURAL LAW)

> **This is the #1 recurring bug source in this project. Three separate incidents have been caused by violating these rules. Read this entire section before touching ANY data flow between pipeline and dashboard.**

**Pipeline runs locally (Windows). Dashboard runs on Railway (Linux container). They have completely separate filesystems. NOTHING written to disk locally is visible on Railway. NOTHING written to disk on Railway persists across deploys.**

```
┌─────────────────────┐          ┌─────────────────────┐
│   LOCAL (Windows)    │          │  RAILWAY (Linux)     │
│                      │          │                      │
│  Pipeline writes     │    ✗     │  Dashboard reads     │
│  .hive-mind/...      │ ←──────→ │  .hive-mind/...      │
│                      │  NEVER   │                      │
│  These are DIFFERENT │ CONNECTED│  These are DIFFERENT  │
│  directories!        │          │  directories!         │
└──────────┬───────────┘          └──────────┬───────────┘
           │                                  │
           │     ┌──────────────────┐         │
           └────→│  Redis (Upstash)  │←────────┘
                 │  ONLY shared      │
                 │  persistence      │
                 └──────────────────┘
```

#### The Law: Every Cross-Environment Data Path MUST Use Redis

If a piece of data is:
- **Written** by the pipeline (local) AND **read** by the dashboard (Railway), OR
- **Written** by the dashboard (Railway) AND **read** by the pipeline (local)

Then it **MUST** go through Redis. No exceptions. No "temporary" filesystem workarounds.

#### Shadow Email Queue Architecture (`core/shadow_queue.py`)

This is the **canonical pattern** for cross-environment data. All new cross-environment features MUST follow this pattern:

```
Local Pipeline → shadow_queue.push() → Redis (primary) + disk (fallback)
                                            ↓
Railway Dashboard → shadow_queue.list_pending() → Redis (primary) + disk (fallback)
```

#### Ironclad Rules

1. **NEVER** write cross-environment data directly to disk — always use a Redis-backed module (`core/shadow_queue.py`, `core/state_store.py`)
2. **NEVER** read cross-environment data from disk on Railway — the disk is ephemeral and isolated
3. **NEVER** assume a filesystem path that "works locally" will work on Railway
4. **ALWAYS** use `CONTEXT_REDIS_PREFIX` (not `STATE_REDIS_PREFIX`) for shared Redis keys — it's consistently `caio:production:context` on both environments
5. **ALWAYS** verify data appears on Railway after any pipeline change (check `/api/pending-emails` or relevant API endpoint)
6. **ALWAYS** sync gatekeeper queue items through `shadow_queue.push()` (Redis + file), never file-only mirroring
7. **ALWAYS** merge Redis and file pending sources in `/api/pending-emails` until all producers are Redis-native (dedup by `email_id`)
8. **NEVER** re-open terminal statuses (`approved`, `rejected`, `sent_via_ghl`, etc.) back to `pending` during queue sync
9. **ALWAYS** fail-closed in UI: if `/api/pending-emails` returns `401`, show explicit auth-required state (never render "All caught up")
10. **ALWAYS** clear stale dashboard token on `401` and reprompt (or require `?token=`) before declaring queue empty
11. **ALWAYS** keep legacy bookmark routes (`/ChiefAIOfficer`, `/chiefaiofficer`) redirecting to canonical `/sales`
12. **ALWAYS** apply queue hygiene before rendering approvals:
    - exclude placeholder-body drafts (`"No Body Content"` / empty),
    - exclude stale drafts older than `PENDING_QUEUE_MAX_AGE_HOURS` (default 72h),
    - exclude tier mismatch when ramp is active (`tier_filter` from `/api/operator/status`),
    - exclude duplicate recipient+subject drafts (keep newest only).
13. **ALWAYS** run queue hygiene cleanup before supervised cycles if pending list drifts:
    - `python scripts/cleanup_pending_queue.py --base-url "https://<dashboard>" --token "<DASHBOARD_AUTH_TOKEN>" --apply`

#### Redis Key Schema (Shadow Queue)

| Key Pattern | Type | Purpose |
|-------------|------|---------|
| `{prefix}:shadow:email:{email_id}` | String (JSON) | Individual email data |
| `{prefix}:shadow:pending_ids` | Sorted Set (score=timestamp) | Index of pending email IDs |

Where `{prefix}` = `CONTEXT_REDIS_PREFIX` = `caio:production:context`

#### Redis Prefix Pitfall (Bug Incident — Fixed in commit `2d074c6`)

| Variable | Local Value | Railway Value | Safe for Shared Keys? |
|----------|-------------|---------------|----------------------|
| `STATE_REDIS_PREFIX` | `""` (empty) | `"caio"` | **NO** — differs between environments |
| `CONTEXT_REDIS_PREFIX` | `"caio:production:context"` | `"caio:production:context"` | **YES** — same everywhere |

**Rule**: Any Redis module that stores data accessed by BOTH local and Railway MUST use `CONTEXT_REDIS_PREFIX` as primary. The `_prefix()` function in `shadow_queue.py` demonstrates the correct pattern:
```python
def _prefix() -> str:
    return (os.getenv("CONTEXT_REDIS_PREFIX") or os.getenv("STATE_REDIS_PREFIX") or "caio").strip()
```

#### Pre-Flight Checklist (MANDATORY for Any New Feature That Shares Data)

Before implementing ANY feature where data flows between local and Railway:

- [ ] **Q1**: Does this data need to be visible on both local AND Railway? → If YES, use Redis
- [ ] **Q2**: Am I using `CONTEXT_REDIS_PREFIX` for the Redis key prefix? → Must be YES
- [ ] **Q3**: Have I tested the Railway dashboard after the change? → Must verify via API
- [ ] **Q4**: Is there a filesystem fallback for when Redis is unavailable? → Should have one
- [ ] **Q5**: Does the API endpoint return diagnostic info for debugging? → Add `_debug` field
- [ ] **Q6**: If endpoint is polled by browser (`/api/pending-emails`), did I enforce `Cache-Control: no-store` + query timestamp cache-buster?
- [ ] **Q7**: Does the dashboard auto-refresh (`setInterval`) and refresh on tab visibility return (`visibilitychange`)?

#### Historical Incidents (Learn From These)

| Incident | Root Cause | Fix | Commit |
|----------|-----------|-----|--------|
| Dashboard shows "no pending emails" (1st) | Pipeline wrote to disk, dashboard on Railway can't see local disk | Created `core/shadow_queue.py` with Redis bridge | `077e34b` |
| Dashboard shows "no pending emails" (2nd) | `_prefix()` checked `STATE_REDIS_PREFIX` first, which differs between environments | Swapped to check `CONTEXT_REDIS_PREFIX` first | `2d074c6` |
| Dashboard shows "no pending emails" (3rd) | Same root — filesystem assumption | Same pattern — always Redis first | Various |

**The pattern is always the same**: something was written to disk locally and expected to appear on Railway. The fix is always the same: use Redis.

#### Pending Email Refresh Non-Regression Gate (MANDATORY)

Before shipping any queue/dashboard change, run:

1. `python -m pytest -q tests/test_runtime_determinism_flows.py`
2. `curl -s "https://<dashboard>/api/pending-emails?token=<DASHBOARD_AUTH_TOKEN>" | python -m json.tool`
3. `python scripts/deployed_full_smoke_checklist.py --base-url "https://<dashboard>" --token "<DASHBOARD_AUTH_TOKEN>"`

Pass criteria:
- `count` reflects new queue items without manual page reload
- `_shadow_queue_debug.redis_connected=true` in deployed env
- `_shadow_queue_debug.merged_count >= _shadow_queue_debug.redis_returned`
- `sales_page_auto_refresh_wiring.passed=true`
- `pending_emails_refresh_timestamp_changes.passed=true`
- Browser shows **Authentication Required** (not **All caught up**) when token is missing/invalid

---

## 🛡️ Unified Guardrails System (CRITICAL)

The Unified Guardrails System provides enterprise-grade protection for all 12 agents in the swarm.

### Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                    UNIFIED GUARDRAILS                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ CircuitBreaker│  │ RateLimiter │  │PermissionMgr│       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ GroundingVal │  │ ActionValid │  │  HookSystem  │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### Key Files
| File | Purpose |
|------|---------|
| `core/unified_guardrails.py` | **Main guardrails system** |
| `core/agent_action_permissions.json` | **JSON config for all 12 agents** |
| `core/ghl_execution_gateway.py` | Single entry point for GHL actions |
| `core/circuit_breaker.py` | Failure protection (3-trip, 5min reset) |
| `core/self_annealing.py` | Learning from outcomes |

### Agent Permission Matrix (12 Agents)
| Agent | Role | Can Approve | Key Actions |
|-------|------|-------------|-------------|
| UNIFIED_QUEEN | Orchestrator | ✅ (weight: 3) | All actions |
| HUNTER | Lead Gen | ❌ | scrape, create_contact |
| ENRICHER | Lead Gen | ❌ | update_contact, add_tag |
| SEGMENTOR | Lead Gen | ❌ | score, classify |
| CRAFTER | Lead Gen | ❌ | get_templates, create_task |
| GATEKEEPER | Approval | ✅ (weight: 2) | send_email, bulk_send |
| SCOUT | Pipeline | ❌ | read_pipeline, search |
| OPERATOR | Unified Outbound (3 motions) | ❌ | dispatch_outbound, dispatch_cadence, dispatch_revival, instantly_*, heyreach_* |
| COACH | Pipeline | ❌ | update_contact |
| PIPER | Pipeline | ❌ | update_opportunity |
| SCHEDULER | Scheduling | ❌ | calendar_ops |
| RESEARCHER | Research | ❌ | read-only |

### Outbound Volume Limits (Warmup-Aware)

Managed by OPERATOR via `WarmupSchedule` in `execution/operator_outbound.py`.

| Channel | Daily Limit | Platform | Notes |
|---------|------------|----------|-------|
| Cold Email (Instantly) | 25/day | Instantly V2 | 6 warmed domains, round-robin |
| LinkedIn (HeyReach) | 5/day (warmup) → 20/day | HeyReach | 4-week warmup, then full volume |
| Revival Email | 5/day | Instantly (warm domains) | GHL nurture domains, separate budget |
| **Total** | **35/day** (warmup) → **50/day** | | |

**Three-Layer Dedup** (prevents double-dispatch):
1. `OperatorDailyState.leads_dispatched` — same lead not dispatched twice/day
2. `LeadStatusManager` terminal check — no re-engaging bounced/unsubscribed
3. Shadow email `dispatched_to_*` flags — no cross-channel double-dispatch

### Risk Levels & Grounding Requirements
| Risk Level | Requires Grounding | Requires Approval |
|------------|-------------------|-------------------|
| LOW | ❌ | ❌ |
| MEDIUM | ❌ | ❌ |
| HIGH | ✅ | ❌ |
| CRITICAL | ✅ | ✅ |

### Grounding Evidence Format
```python
grounding_evidence = {
    "source": "supabase",     # Where data came from
    "data_id": "lead_123",    # Specific record ID
    "verified_at": "2026-01-21T10:30:00Z"  # Must be <1 hour old
}
```

### Using Unified Guardrails (REQUIRED)
```python
from core.unified_guardrails import UnifiedGuardrails, ActionType

guardrails = UnifiedGuardrails()

# Execute with full protection
result = await guardrails.execute_with_guardrails(
    agent_name="GATEKEEPER",
    action_type=ActionType.SEND_EMAIL,
    action_fn=send_email_function,
    parameters={'contact_id': '...', 'subject': '...'},
    grounding_evidence={'source': 'supabase', 'data_id': 'lead_123', 'verified_at': '...'}
)
```

### Blocked Operations (NEVER ALLOWED)
- `bulk_delete` - Permanently blocked for data safety
- `export_all_contacts` - Blocked for GDPR compliance
- `mass_unsubscribe` - Requires manual intervention

> ⚠️ **ALL actions must go through UnifiedGuardrails. Direct API calls are PROHIBITED.**

---

---

## 🌐 Unified Integration Gateway (NEW)

Centralized API management for ALL external integrations.

### Architecture
```
┌──────────────────────────────────────────────────────────────────┐
│                 UNIFIED INTEGRATION GATEWAY                       │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │    GHL     │  │  Instantly │  │  HeyReach  │  │   Clay     │  │
│  │   Adapter  │  │  V2 API   │  │  LinkedIn  │  │  Adapter   │  │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │  Apollo    │  │  Supabase  │  │   RB2B     │  │  Webhook   │  │
│  │   Adapter  │  │  Adapter   │  │  Adapter   │  │  Ingress   │  │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Key Files
| File | Purpose |
|------|---------|
| `core/unified_integration_gateway.py` | **Centralized API gateway** |
| `mcp-servers/google-calendar-mcp/` | Google Calendar MCP server |
| `core/unified_health_monitor.py` | Real-time health monitoring |
| `dashboard/health_app.py` | Health dashboard API |

### Usage
```python
from core.unified_integration_gateway import get_gateway

gateway = get_gateway()

# Execute through gateway (automatic guardrails, rate limiting, circuit breakers)
result = await gateway.execute(
    integration="google_calendar",
    action="create_event",
    params={"title": "Meeting", "start_time": "...", "end_time": "..."},
    agent="SCHEDULER",
    grounding_evidence={"source": "supabase", "data_id": "lead_123", "verified_at": "..."}
)
```

### Supported Integrations
| Integration | Rate Limit | Key Actions |
|-------------|------------|-------------|
| ghl | 150/day | send_email, create_contact, trigger_workflow, calendar_ops |
| instantly | 25/day (warmup-aware) | create_campaign, add_leads, activate, pause |
| heyreach | 300/min API, 5-20/day sends | add_leads_to_campaign, get_campaigns |
| apollo | 200/hour | people_search, people_match |
| clay | 500/hour | enrich_contact (RB2B visitors only) |
| supabase | 5000/hour | query, insert, update |
| rb2b | webhook-based | visitor_id (inbound only) |

---

## Calendar (GHL-backed, replaced Google Calendar)

Calendar operations use GHL Calendar API via `mcp-servers/ghl-mcp/calendar_client.py` (drop-in replacement for Google Calendar MCP). Guardrails in `mcp-servers/google-calendar-mcp/guardrails.py` (shared, backend-agnostic).

### Tools Available
| Tool | Description | Guardrails |
|------|-------------|------------|
| `get_availability` | Check calendar availability | Rate limit: 100/hr |
| `create_event` | Create event with Zoom link | No double-booking, working hours only |
| `update_event` | Modify existing event | Buffer validation |
| `delete_event` | Cancel event | Attendee notification |
| `find_available_slots` | Find meeting slots | 15-min buffer enforced |

### Calendar Guardrails
- Working hours: 9 AM - 6 PM (configurable)
- Minimum buffer: 15 minutes between meetings
- Max duration: 2 hours
- No weekend booking (unless explicitly allowed)
- No double-booking (mutex lock)
- GHL Calendar ID: `2tqUa6LBhhrT7Y99YVyD`

---

## 📊 Health Dashboard

### Start Dashboard
```bash
cd chiefaiofficer-alpha-swarm
uvicorn dashboard.health_app:app --host 0.0.0.0 --port 8080
```

### Endpoints (50+)

**Pages**:
| Route | Page |
|-------|------|
| `GET /` | System Health dashboard |
| `GET /scorecard` | Precision Scorecard (12 metrics) |
| `GET /sales` | Head of Sales email approval queue (v2.4 — live RAMP MODE banner from `/api/operator/status`) |
| `GET /leads` | Lead Signal Loop + Activity Timeline |

**Health & System**:
| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Full health status + runtime deps |
| `GET /api/health/ready` | Kubernetes readiness probe |
| `GET /api/agents` | All 12 agent statuses |
| `GET /api/integrations` | Integration status |
| `GET /api/guardrails` | Rate limits & circuit breakers |
| `GET /api/scorecard` | Precision Scorecard summary |
| `WS /ws` | Real-time WebSocket updates |

**Email Queue (Head of Sales)** — reads from Redis via `core/shadow_queue.py`:
| Endpoint | Description |
|----------|-------------|
| `GET /api/pending-emails` | Pending emails (Redis primary, filesystem fallback) |
| `POST /api/emails/{id}/approve` | Approve email — syncs status to Redis + disk |
| `POST /api/emails/{id}/reject` | Reject email — syncs status to Redis + disk |

**Lead Signal Loop**:
| Endpoint | Description |
|----------|-------------|
| `GET /api/leads` | All tracked leads with status |
| `GET /api/leads/funnel` | Pipeline funnel counts |
| `GET /api/leads/status-summary` | Leads by engagement status |
| `GET /api/leads/{email}/timeline` | Unified activity timeline |
| `POST /api/leads/detect-decay` | Run ghosting/stall detection |
| `POST /api/leads/bootstrap` | Seed lead status from shadow emails |

**OPERATOR Agent**:
| Endpoint | Description |
|----------|-------------|
| `GET /api/operator/status` | Today's state + warmup schedule |
| `GET /api/operator/revival-candidates` | Preview revival candidates |
| `POST /api/operator/trigger` | Trigger dispatch (dry_run, motion) |
| `GET /api/operator/history` | Last 50 dispatch logs |

**Cadence Engine**:
| Endpoint | Description |
|----------|-------------|
| `GET /api/cadence/summary` | Enrolled, active, completed, due today |
| `GET /api/cadence/due` | Actions due today |
| `GET /api/cadence/leads` | All cadence states (filter by status) |
| `POST /api/cadence/sync` | Sync with signal loop (auto-exit) |

**Webhooks (Mounted)**:
| Endpoint | Source |
|----------|--------|
| `POST /webhooks/clay` | RB2B visitor enrichment |
| `POST /webhooks/instantly/*` | Instantly campaign events |
| `POST /webhooks/heyreach/*` | HeyReach LinkedIn events |
| `POST /inngest` | Inngest task scheduler |

---

## 📦 Product Context System (NEW)

Centralized product knowledge for all agents from the ChiefAIOfficer.com pitchdeck.

### Key Files
| File | Purpose |
|------|---------|
| `core/product_context.py` | **Product context provider** |
| `.hive-mind/knowledge/company/product_offerings.json` | Full product catalog JSON |
| `.hive-mind/knowledge/company/sales_context.md` | Sales context for agents |

### Product Offerings
| Product | Price | Duration |
|---------|-------|----------|
| AI Opportunity Audit | $10,000 | 2-4 weeks |
| AI Executive Certification Workshop | $12,000 | 1 day |
| On-Site Plan (DIY) | $14,500/mo | Ongoing |
| Enterprise Plan (Done For You) | Custom | Ongoing |
| AI Consulting | $800/hr | 10hr min |

### Using Product Context
```python
from core.product_context import get_product_context

ctx = get_product_context()

# Get all products
products = ctx.get_products()

# Get agent-specific context
agent_ctx = ctx.get_agent_context("CRAFTER")

# Format for prompt injection
prompt_ctx = ctx.format_for_prompt("CRAFTER")

# Check lead qualification
result = ctx.check_qualification(lead_data)
```

### Agent Context Injection
Each agent receives tailored product context:
- **CRAFTER/COACH**: Full product details, pricing, ROI, case studies
- **ENRICHER/SEGMENTOR**: ICP criteria, disqualifiers
- **GATEKEEPER**: Pricing, guarantees for approval
- **SCHEDULER**: CTAs, booking links

### Self-Annealing Integration
Product knowledge is automatically seeded into the reasoning bank on startup:
- Products → "insight" patterns (searchable by similarity)
- Typical Results → "success" patterns
- Disqualifiers → "failure" patterns
- M.A.P. Framework → "insight" patterns

### Key CTAs
- **Executive Briefing**: https://caio.cx/ai-exec-briefing-call
- **AI Readiness Assessment**: https://ai-readiness-assessment-549851735707.us-west1.run.app/

### Typical Results (Quote These)
- 20-30% operational cost reduction
- 40%+ efficiency improvement
- 62.5% administrative time reduction
- 60% capacity increase

### Guarantee
> "Measured ROI, or you don't pay the next phase"

---

## 🔄 Swarm Coordination (Day 8)

Centralized swarm lifecycle with heartbeats, auto-restart, and worker scaling (2-12). Key file: `core/swarm_coordination.py`, state: `.hive-mind/swarm_state.json`.


---

## LLM Routing Gateway

Task-aware LLM routing for cost optimization (`core/llm_routing_gateway.py`).

Key files: `core/llm_routing_gateway.py`, `core/agent_llm_mixin.py`. Routes: Claude (planning/orchestration), Gemini Flash (creative/email copy), GPT-4o (API integrations). Env vars: `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`.

---

## 🌐 Website Intent Monitor (Blog Triggers + Warm Connections)

Monitors RB2B visitors for high-intent blog page visits and detects warm connections with our sales team.

### Architecture
```
RB2B Webhook → Website Intent Monitor → Match Triggers → Find Connections
                                              ↓                    ↓
                                        Calculate Intent    Check Team Network
                                              ↓                    ↓
                                        Generate Email (Gemini) ← Personalize
                                              ↓
                                    Queue for GATEKEEPER Approval
```

### Key Files
| File | Purpose |
|------|---------|
| `core/website_intent_monitor.py` | **Main monitoring engine** |
| `.hive-mind/knowledge/templates/blog_triggered_emails.json` | Email templates |
| `.hive-mind/gatekeeper_queue/` | Pending email approvals |

### Blog Trigger Rules
| Category | URL Pattern | Intent Boost | Template |
|----------|-------------|--------------|----------|
| AI Case Study | `/blog.*p&g.*product` | +25 | `case_study_pg` |
| ROI Metrics | `/blog.*roi\|efficiency` | +20 | `roi_focused` |
| Sales AI | `/blog.*sales.*ai` | +30 | `sales_ai` |
| Implementation | `/blog.*implementation` | +35 | `implementation_ready` |

### Connection Matching
The system checks visitors against team members' work history:
```python
# Team network is configured in website_intent_monitor.py
TEAM_NETWORK = {
    "dani_apgar": {
        "name": "Dani Apgar",
        "previous_companies": [
            {"name": "Gong", "domain": "gong.io"},
            {"name": "Outreach", "domain": "outreach.io"},
            {"name": "Salesforce", "domain": "salesforce.com"},
        ]
    }
}
```

Connection types detected:
- **FORMER_COLLEAGUE**: Visitor worked at same company, same time
- **SAME_PREVIOUS_COMPANY**: Visitor at company where team member worked
- **MUTUAL_CONNECTION**: Known LinkedIn connection

### Usage
```python
from core.website_intent_monitor import get_website_monitor

monitor = get_website_monitor()

# Process RB2B webhook
result = await monitor.process_visitor({
    "email": "todd@acme.com",
    "first_name": "Todd",
    "company_name": "Acme Corp",
    "job_title": "VP Sales",
    "pages_viewed": ["/blog/how-pg-cut-product-development-time-22-percent-using-ai"],
    "work_history": [{"company_name": "Gong", "company_domain": "gong.io"}]
})

# Result includes:
# - intent_score: 75
# - warm_connections: [WarmConnection(type=SAME_PREVIOUS_COMPANY, shared="Gong")]
# - generated_email: {subject, body}
# - queued_for_approval: True
```

### Adding Team Connections
```python
monitor.add_team_member_connection(
    "dani_apgar",
    company_name="HubSpot",
    company_domain="hubspot.com",
    years="2017-2019"
)

monitor.add_known_linkedin_connection(
    "dani_apgar",
    "https://linkedin.com/in/someconnection"
)
```

### Sample Email Output
```
Subject: Quick thought on Acme Corp's development cycle

Hi Todd,

I saw you were reading our piece on how P&G cut product development time 
by 22% using AI.

Small world—my colleague Dani Apgar spent time at Gong as well.

When VPs of Sales look at that example, it's usually because they're under 
pressure to move faster—shorter cycles, better decisions, less drag between 
teams—without blowing up headcount or process.

Quick question: where are you seeing the most friction right now—speed to 
execution, cross-team alignment, or insight visibility?

Would later today or tomorrow work better?

Kind regards,
Dani Apgar
```

> ⚠️ **All blog-triggered emails require GATEKEEPER approval before sending.**

