# Chief AI Officer Alpha Swarm - Claude Configuration

## 🚨 CRITICAL: CONCURRENT EXECUTION & FILE MANAGEMENT

**ABSOLUTE RULES**:
1. ALL operations MUST be concurrent/parallel in a single message
2. **NEVER save working files to the root folder**
3. ALWAYS organize files in appropriate subdirectories
4. **USE CLAUDE CODE'S TASK TOOL** for spawning agents concurrently

---

## Project Context

**Project**: Chief AI Officer Alpha Swarm
**Purpose**: Autonomous SDR pipeline — lead discovery, enrichment, multi-channel outreach
**Founder**: Chris Daigle (https://www.linkedin.com/in/doctordaigle/)
**Company**: Chiefaiofficer.com
**Platform**: Railway (production) at `caio-swarm-dashboard-production.up.railway.app`
**Dashboard**: v2.7 — deployed commit `2d074c6` (2026-02-18) — Redis shadow queue prefix fix

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

See `docs/CAIO_TASK_TRACKER.md` for detailed progress and next steps.

### Dashboard Pipeline Improvements (commit `b8dfc0f`)

- **HoS Dashboard v2.4** (`/sales`): Live RAMP MODE banner fetches from `/api/operator/status` every 30s — shows day/total, daily limit, tier filter, sent count
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

## MCP Server Configuration

```json
{
  "mcpServers": {
    "hunter-mcp": {
      "command": "python",
      "args": ["mcp-servers/hunter-mcp/server.py"]
    },
    "enricher-mcp": {
      "command": "python",
      "args": ["mcp-servers/enricher-mcp/server.py"]
    },
    "ghl-mcp": {
      "command": "python",
      "args": ["mcp-servers/ghl-mcp/server.py"]
    },
    "instantly-mcp": {
      "command": "python",
      "args": ["mcp-servers/instantly-mcp/server.py"]
    },
    "claude-flow": {
      "command": "npx",
      "args": ["claude-flow@alpha", "mcp", "start"]
    }
  }
}
```

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
└── CAIO_IMPLEMENTATION_PLAN.md    # Full implementation plan (v4.2)
```

---

## Concurrent Execution Pattern

### ✅ CORRECT: Single message, multiple parallel operations
```javascript
[Single Message - Parallel Execution]:
  Task("Hunter Agent", "Scrape leads from apollo.io", "researcher")
  Task("Enricher Agent", "Enrich pending leads via Clay", "enricher")
  Task("Segmentor Agent", "Score and segment new leads", "analyst")
  
  // Batch file operations
  Write "execution/new_script.py"
  Write "directives/new_sop.md"
  
  // Batch todos
  TodoWrite { todos: [...5+ todos...] }
```

### ❌ WRONG: Multiple messages for related work
```javascript
Message 1: Task("Hunter")
Message 2: Write file
Message 3: TodoWrite
// Breaks parallelism!
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

## Self-Annealing Protocol

When errors occur:
1. Log error to `.hive-mind/learnings.json`
2. Fix the execution script
3. Update relevant directive
4. Store pattern in reasoning bank
5. System now handles this case

---

## Context Engineering (HumanLayer 12-Factor Methodology)

Based on Dex Horthy's "No Vibes Allowed" framework and HumanLayer's 12-Factor Agents patterns.

### Core Principles

1. **Own Your Prompts**: Prompts are first-class code (`.claude/commands/*.md`)
2. **Own Your Context Window**: Custom event-based threading (`core/context.py`)
3. **Compact Errors**: Remove resolved errors, keep only actionable context
4. **Small Focused Agents**: 3-10 steps max per agent (`.claude/agents/*.md`)
5. **Pre-fetch Context**: Deterministically fetch data before LLM decisions

### The "Dumb Zone"
AI performance degrades significantly when context fills >40% of capacity:
- **Smart Zone**: <40% context — optimal performance
- **Caution Zone**: 40-60% — degradation starting
- **Dumb Zone**: >60% — significant degradation, expect errors
- **Critical Zone**: >80% — expect failures

**Solution**: Use Frequent Intentional Compaction (FIC) via `core/context.py`.

### Research → Plan → Implement (RPI) Workflow

For complex multi-step operations, use RPI with Claude commands:

```powershell
# Phase 1: RESEARCH (documentarian only - never evaluate)
/research_leads --input .hive-mind\segmented\latest.json
# OR: python execution\rpi_research.py --input <leads.json>

# [HUMAN REVIEW CHECKPOINT] ← Maximum leverage point

# Phase 2: PLAN (skeptical, explicit "What We're NOT Doing")
/create_campaign_plan --research .hive-mind\research\latest.json
# OR: python execution\rpi_plan.py --research <research.json>

# [HUMAN REVIEW CHECKPOINT]

# Phase 3: IMPLEMENT (phase-by-phase with verification pauses)
/implement_campaign --plan .hive-mind\plans\latest.json
# OR: python execution\rpi_implement.py --plan <plan.json>
```

### Parallel Sub-Agent Spawning

Use focused agents in parallel for research (`core/agent_spawner.py`):

```python
from core.agent_spawner import AgentSpawner, AgentTask

spawner = AgentSpawner()
tasks = [
    AgentTask("lead-analyzer", "Trace lead data flow for tier_1"),
    AgentTask("campaign-pattern-finder", "Find competitor displacement patterns"),
    AgentTask("compliance-checker", "Validate CAN-SPAM compliance"),
]
results = spawner.spawn_parallel_agents(tasks)
```

### Context Compaction

Use `core/context.py` for event-based threading:

```python
from core.context import EventThread

thread = EventThread(thread_id="campaign_001")
thread.add_event("research_complete", {"findings": {...}})
thread.add_event("plan_created", {"phases": [...]})

# Auto-compact when over budget
if not thread.check_context_budget():
    thread.compact()  # Removes resolved errors, completed phases
```

### Thoughts System (Persistent Memory)

Store knowledge in `thoughts/` directory:
- `thoughts/shared/research/` — Research documents
- `thoughts/shared/patterns/` — Proven patterns (objection handling, personalization)
- `thoughts/shared/playbooks/` — Operational playbooks
- `thoughts/templates/` — Document templates

### Claude Commands Reference

| Command | Purpose |
|---------|---------|
| `/research_leads` | Parallel research with sub-agents |
| `/create_campaign_plan` | Interactive planning with skepticism |
| `/implement_campaign` | Phase-by-phase execution |
| `/create_handoff` | Context compaction for session transitions |

### Claude Agents Reference

| Agent | Purpose |
|-------|---------|
| `lead-analyzer` | READ-ONLY: Trace lead data flow |
| `campaign-pattern-finder` | READ-ONLY: Find similar implementations |

See `docs/CONTEXT_ENGINEERING_ANALYSIS.md` for full methodology.

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

#### Historical Incidents (Learn From These)

| Incident | Root Cause | Fix | Commit |
|----------|-----------|-----|--------|
| Dashboard shows "no pending emails" (1st) | Pipeline wrote to disk, dashboard on Railway can't see local disk | Created `core/shadow_queue.py` with Redis bridge | `077e34b` |
| Dashboard shows "no pending emails" (2nd) | `_prefix()` checked `STATE_REDIS_PREFIX` first, which differs between environments | Swapped to check `CONTEXT_REDIS_PREFIX` first | `2d074c6` |
| Dashboard shows "no pending emails" (3rd) | Same root — filesystem assumption | Same pattern — always Redis first | Various |

**The pattern is always the same**: something was written to disk locally and expected to appear on Railway. The fix is always the same: use Redis.

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

## GHL Guardrails (Nurture Email Only — Legacy Reference)

### Before ANY Email Send
```
1. ✓ Check limits (monthly/daily/hourly)
2. ✓ Check domain health (score > 50)
3. ✓ Check working hours (8am-6pm)
4. ✓ Validate content (no spam words)
5. ✓ Verify personalization resolved
6. ✓ Confirm unsubscribe present
7. ✓ Get GATEKEEPER approval (cold)
8. ✓ Log action to audit trail
```

### Using the GHL Execution Gateway (For GHL-specific actions)
```python
from core.ghl_execution_gateway import execute_ghl_action, ActionType

result = await execute_ghl_action(
    action_type=ActionType.SEND_EMAIL,
    parameters={'contact_id': '...', 'subject': '...', 'body': '...'},
    agent_name='GHL_MASTER',
    grounding_evidence={'source': 'supabase', 'data_id': 'lead_123'}
)
```

> ⚠️ **NEVER bypass the gateway. Direct GHL API calls are PROHIBITED.**

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

Centralized swarm lifecycle management with heartbeats, auto-restart, and worker concurrency.

### Key Files
| File | Purpose |
|------|---------|
| `core/swarm_coordination.py` | **Main coordination engine** |
| `.hive-mind/swarm_state.json` | Persistent swarm state |

### Architecture
```
┌────────────────────────────────────────────────────────────┐
│               SWARM COORDINATOR                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │  Heartbeat   │ │  Worker      │ │  Recovery    │       │
│  │  Monitor     │ │  Pool        │ │  Manager     │       │
│  │  (30s check) │ │  (2-12 scale)│ │  (auto-fix)  │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
└────────────────────────────────────────────────────────────┘
```

### Using Swarm Coordinator
```python
from core.swarm_coordination import SwarmCoordinator, CoordinationConfig

config = CoordinationConfig(
    heartbeat_interval_seconds=30,
    min_workers=2,
    max_workers=12,
    auto_restart=True
)

coordinator = SwarmCoordinator(config)
await coordinator.start()

# Record agent heartbeats
coordinator.record_heartbeat("HUNTER", current_task="scrape_001")

# Submit tasks
await coordinator.submit_task({"task_id": "T-001", "type": "scrape"})

# Scale workers dynamically
await coordinator.scale_workers(8)

# Register hooks
coordinator.register_hook("pre_task", my_pre_handler)
coordinator.register_hook("on_error", my_error_handler)

await coordinator.stop()
```

### Hook Types
| Hook | Trigger |
|------|---------|
| `pre_task` | Before task execution |
| `post_task` | After successful task |
| `on_error` | On task failure |
| `on_agent_start` | Agent starts |
| `on_agent_stop` | Agent stops |
| `on_agent_recover` | Agent recovered |
| `on_worker_scale` | Workers scaled |

### Auto-Scaling
- **Scale Up**: Queue > 80% capacity → Add 2 workers
- **Scale Down**: Queue < 20% capacity → Remove 1 worker
- **Limits**: min_workers ≤ count ≤ max_workers

---

## 🔍 Competitive Intelligence

Knowledge from Qualified.com and Artisan.co integrated for agent context.

### Key File
`.hive-mind/knowledge/company/competitive_intelligence.json`

### Features Adopted
**From Qualified (Piper):**
- Visitor 360 profile aggregation
- Real-time segment streams
- AI Studio (guardrails + coaching)
- Slack integration for collaboration

**From Artisan (Ava):**
- Personalization Waterfall methodology
- Data Miner (multi-source research)
- Self-optimization (A/B testing)
- Sentiment analysis for responses
- Intent-triggered outbound

### Our Competitive Advantages
- Human approval gates (GATEKEEPER)
- Byzantine consensus for critical decisions
- Q-learning adaptive routing
- EWC++ knowledge consolidation
- Multi-swarm architecture
- Grounding evidence validation

---

## 🧠 LLM Routing Gateway (Multi-Provider)

Task-aware LLM routing for cost optimization. Routes different task types to optimal providers.

### Architecture
```
┌─────────────────────────────────────────────────────────────────────┐
│                     LLM ROUTING GATEWAY                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐        │
│  │   CLAUDE       │  │   GEMINI       │  │   CODEX/GPT-4  │        │
│  │  (Brain/Plan)  │  │  (Creative)    │  │  (Code)        │        │
│  │  Opus/Sonnet   │  │  2.5 Flash/Pro │  │  GPT-4o        │        │
│  └────────────────┘  └────────────────┘  └────────────────┘        │
│                              ↑                                       │
│                    ┌─────────────────────┐                          │
│                    │   TASK ROUTER       │                          │
│                    │  (TaskType → LLM)   │                          │
│                    └─────────────────────┘                          │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Files
| File | Purpose |
|------|---------|
| `core/llm_routing_gateway.py` | **Main routing gateway** |
| `core/agent_llm_mixin.py` | Agent integration helpers |
| `core/llm_provider_fallback.py` | Fallback-only system (legacy) |

### Task Type Routing
| Task Type | Primary Provider | Fallback | Use Case |
|-----------|-----------------|----------|----------|
| PLANNING | Claude Sonnet | Claude Opus | Campaign strategy, orchestration |
| ORCHESTRATION | Claude Sonnet | Claude Opus | QUEEN decisions, workflow control |
| SELF_ANNEALING | Claude Sonnet | Claude Opus | Learning, pattern detection |
| REASONING | Claude Opus | OpenAI o1 | Complex analysis, deep thinking |
| CREATIVE | Gemini Flash | Gemini Pro | Email copy, brand messaging |
| CONTENT_GENERATION | Gemini Flash | Gemini Pro | Templates, personalization |
| SCHEDULING | Gemini Flash | Claude Sonnet | Calendar, timing optimization |
| CODING | GPT-4o | Codex | API integrations, scripts |
| API_INTEGRATION | GPT-4o | Claude Sonnet | External service connections |
| DEBUGGING | GPT-4o | Claude Sonnet | Error resolution |

### Agent Default Routes
| Agent | Default Task Type | Primary LLM |
|-------|-------------------|-------------|
| QUEEN | ORCHESTRATION | Claude Sonnet |
| GATEKEEPER | DECISION | Claude Opus |
| CRAFTER | CREATIVE | Gemini Flash |
| COACH | MESSAGING | Gemini Flash |
| SCHEDULER | SCHEDULING | Gemini Flash |
| OPERATOR | API_INTEGRATION | GPT-4o |
| HUNTER | DATA_TRANSFORMATION | GPT-4o |
| SEGMENTOR | ANALYSIS | Claude Sonnet |

### Usage
```python
from core.llm_routing_gateway import get_llm_router, TaskType

router = get_llm_router()

# Auto-routes based on task type
response = await router.complete(
    messages=[{"role": "user", "content": "Create email for lead"}],
    task_type=TaskType.CREATIVE,  # → Gemini Flash
    agent_name="CRAFTER"
)

# Using the mixin pattern
from core.agent_llm_mixin import AgentLLMMixin

class CrafterAgent(AgentLLMMixin):
    def __init__(self):
        super().__init__(agent_name="CRAFTER")
    
    async def generate_email(self, lead):
        return await self.creative_complete(
            prompt=f"Create personalized email for {lead['name']}"
        )

# Convenience functions
from core.agent_llm_mixin import queen_think, crafter_create, operator_code

result = await queen_think("Plan next campaign phase")  # → Claude
result = await crafter_create("Write cold email")       # → Gemini
result = await operator_code("Build GHL API client")    # → GPT-4o
```

### Environment Variables Required
```bash
ANTHROPIC_API_KEY=...   # Claude Opus/Sonnet
GOOGLE_API_KEY=...      # Gemini Flash/Pro
OPENAI_API_KEY=...      # GPT-4o/Codex
```

### Cost Optimization
The gateway tracks usage and estimates savings:
```python
report = router.get_cost_report()
print(f"Total: ${report['total_cost']}")
print(f"Saved: ${report['cost_saved_estimate']}")  # vs. all-Claude-Opus
```

### Pricing Reference (per 1M tokens)
| Provider | Input | Output |
|----------|-------|--------|
| Claude Opus | $15.00 | $75.00 |
| Claude Sonnet | $3.00 | $15.00 |
| Gemini Flash | $0.075 | $0.30 |
| Gemini Pro | $1.25 | $10.00 |
| GPT-4o | $2.50 | $10.00 |

> ⚠️ **Use TaskType explicitly for best routing. Auto-inference is a fallback.**

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

---

## 🤖 Agent Teams Configuration (Parallel Collaborative Sessions)

Agent Teams are multiple Claude Code instances that communicate peer-to-peer, share task lists, and self-coordinate. Use them for **interdependent** work that benefits from live collaboration.

> ⚠️ **Agent Teams consume 5-15x more tokens than single sessions. Only use when peer collaboration is genuinely needed.**

### Enable Agent Teams

Add to `~/.claude/settings.json`:
```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

### Team Definitions

#### Code Review Team (4 Teammates)
**Trigger**: Before deployments, after major refactoring, or periodic audits.

```
Form an agent team of 4 code reviewers:

1. "Security Reviewer": Audit core/unified_guardrails.py, 
   core/ghl_execution_gateway.py, and core/agent_action_permissions.json 
   for permission gaps, exposed secrets, and gateway bypasses.

2. "Performance Reviewer": Check core/circuit_breaker.py, 
   core/swarm_coordination.py, and execution/unified_runner.py 
   for timeout enforcement, backoff correctness, and async safety.

3. "Integration Reviewer": Verify all API adapters in 
   core/unified_integration_gateway.py match external API contracts.
   Check GHL, Clay, LinkedIn, and Supabase adapter signatures.

4. "Test Reviewer": Audit tests/ for coverage gaps against core/ 
   changes. Check that all mocks match current API signatures.

Share findings. Challenge each other's conclusions. 
Produce a unified security+performance+integration report.
```

#### Debug Team (3 Investigators)
**Trigger**: Production errors, pipeline hangs, unexpected behavior.

```
Debug [DESCRIBE THE BUG] by forming a team of 3 investigators:

1. "Hypothesis A": [First theory — e.g., "session cookie expired"]
   Focus files: [relevant files]
   
2. "Hypothesis B": [Second theory — e.g., "rate limiter not backing off"]
   Focus files: [relevant files]

3. "Hypothesis C": [Third theory — e.g., "async timeout missing"]
   Focus files: [relevant files]

Each investigator: read code, trace execution path, gather evidence.
Share findings with each other. Challenge weak hypotheses.
Converge on the root cause and propose a unified fix.
```

#### Feature Team (4 Specialists)
**Trigger**: New features spanning dashboard ↔ core ↔ execution ↔ tests.

```
Build [DESCRIBE FEATURE] as an agent team:

1. "Frontend Lead": Only modify files in dashboard/
   - Update hos_dashboard.html or health_app.py as needed
   
2. "Backend Lead": Only modify files in core/
   - Implement the core logic with proper guardrails

3. "Pipeline Lead": Only modify files in execution/
   - Wire the feature into the pipeline runner

4. "Test Lead": Only modify files in tests/
   - Write comprehensive tests covering all 3 layers

Coordinate on interfaces. Frontend should NOT import core directly.
Backend provides API endpoints. Pipeline uses core functions.
Tests cover the full integration path.
```

#### Refactoring Team (3 Specialists)
**Trigger**: Cross-module refactoring (e.g., renaming agents, changing routing).

```
Refactor [DESCRIBE CHANGE] as an agent team:

1. "Core Lead": Update the primary module in core/
   
2. "Consumer Lead": Update all files that import/use the changed module
   (execution/, dashboard/, mcp-servers/)

3. "Test Lead": Update all tests to match the refactored interfaces.
   Run verification after changes.

Coordinate to ensure no broken imports. Share interface changes 
before implementing so all teammates stay aligned.
```

### Agent Team Rules

| Rule | Description |
|------|-------------|
| **Max 4 teammates** | More creates coordination overhead > benefit |
| **No recursive teams** | Teams don't spawn sub-teams. Keep it flat |
| **File ownership** | Only ONE teammate touches a given file per session |
| **Start with research** | Teams should gather context before making changes |
| **Monitor token usage** | Check usage after team sessions, adjust scope |

---

## 🔧 Sub-Agent Registry (Specialized Single-Session Workers)

Sub-agents are focused workers that operate within a single Claude Code session, report back to the main agent, and cost less tokens. Use them for **independent** work.

### Available Sub-Agents

| Agent | File | Model | Mode | Purpose |
|-------|------|-------|------|---------|
| **Lead Analyzer** | `.claude/agents/lead-analyzer.md` | Sonnet | READ-ONLY | Trace lead data flow across pipeline |
| **Campaign Pattern Finder** | `.claude/agents/campaign-pattern-finder.md` | Sonnet | READ-ONLY | Find & document campaign patterns |
| **Codebase Researcher** | `.claude/agents/codebase-researcher.md` | Sonnet | READ-ONLY | Find symbol usage, trace imports, map dependencies |
| **File Operator** | `.claude/agents/file-operator.md` | Sonnet | WRITE | Bulk file edits, template updates, config changes |
| **Test Writer** | `.claude/agents/test-writer.md` | Sonnet | READ→WRITE | Generate pytest test suites with mocks |
| **Directive Updater** | `.claude/agents/directive-updater.md` | Sonnet | WRITE | Update SOPs, workflows, directives |
| **Security Auditor** | `.claude/agents/security-auditor.md` | Sonnet | READ-ONLY | Audit for secrets, permission gaps, bypasses |
| **GHL Master** | `.claude/agents/ghl-master-agent.md` | — | Full | GHL CRM operations |
| **GHL Outreach** | `.claude/agents/ghl-outreach-agent.md` | — | Full | GHL email outreach |

### When to Use Sub-Agents vs Agent Teams

```
┌─────────────────────────────────────────────────────────┐
│                  DECISION FLOWCHART                      │
│                                                         │
│  Is the task collaborative? (need peer review/debate)   │
│    YES → Use Agent Team                                 │
│    NO  ↓                                                │
│                                                         │
│  Can it be parallelized into independent pieces?        │
│    YES → Use Sub-Agents (parallel)                      │
│    NO  ↓                                                │
│                                                         │
│  Is it a single focused task?                           │
│    YES → Use one Sub-Agent                              │
│    NO  → Do it directly (no agent overhead)             │
└─────────────────────────────────────────────────────────┘
```

### Sub-Agent Usage Examples

```bash
# Research: "Where is the circuit breaker used?"
# → Auto-delegates to codebase-researcher sub-agent

# File ops: "Update all 12 agent permissions to add new action"
# → Auto-delegates to file-operator sub-agent

# Testing: "Generate tests for core/website_intent_monitor.py"
# → Auto-delegates to test-writer sub-agent

# Security: "Audit execution/ for hardcoded secrets"
# → Auto-delegates to security-auditor sub-agent

# SOPs: "Add the new LinkedIn timeout rule to scraping_sop.md"
# → Auto-delegates to directive-updater sub-agent
```

### Sub-Agent Cost Optimization

All sub-agents default to **Sonnet** model for token efficiency:
- Sonnet: ~$3/1M input, ~$15/1M output
- Opus: ~$15/1M input, ~$75/1M output
- **Savings: ~80% per sub-agent task vs Opus**

Only use Opus for complex reasoning tasks that require the main agent.
