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
**Purpose**: LinkedIn intelligence & lead generation system
**Founder**: Chris Daigle (https://www.linkedin.com/in/doctordaigle/)
**Company**: Chiefaiofficer.com

---

## Agent Architecture

### Alpha Swarm Agents
| Agent | Role | Location |
|-------|------|----------|
| 👑 ALPHA QUEEN | Master Orchestrator | `mcp-servers/orchestrator-mcp/` |
| 🕵️ HUNTER | LinkedIn Scraper | `mcp-servers/hunter-mcp/` |
| 💎 ENRICHER | Data Enrichment | `mcp-servers/enricher-mcp/` |
| 📊 SEGMENTOR | Lead Classification | `execution/segmentor_*.py` |
| ✍️ CRAFTER | Campaign Generation | `execution/crafter_*.py` |
| 🚪 GATEKEEPER | AE Approval | `execution/gatekeeper_*.py` |

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
    # instantly-mcp REMOVED - GHL is exclusive email platform
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
├── .agent/workflows/       # Agent workflow definitions
├── .claude/                # Claude-specific config
├── .hive-mind/             # Persistent memory
│   ├── knowledge/          # Vector DB
│   ├── scraped/            # Raw scraped data
│   ├── enriched/           # Enriched leads
│   └── campaigns/          # Generated campaigns
├── directives/             # SOPs (Layer 1)
├── execution/              # Python scripts (Layer 3)
├── mcp-servers/            # MCP tools
└── .tmp/                   # Temporary files
```

---

## Concurrent Execution Pattern

### ✅ CORRECT: Single message, multiple parallel operations
```javascript
[Single Message - Parallel Execution]:
  Task("Hunter Agent", "Scrape followers from Gong.io", "researcher")
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
| GoHighLevel | `GHL_API_KEY` | CRM + Email Outreach (UNIFIED) |
| Clay | `CLAY_API_KEY` | Enrichment |
| RB2B | `RB2B_API_KEY` | Visitor ID |
| LinkedIn | `LINKEDIN_COOKIE` | Scraping |
| Supabase | `SUPABASE_URL`, `SUPABASE_KEY` | Data Layer |

> ⚠️ **GHL is the ONLY email platform** - No Instantly. All outreach goes through GHL.

---

## Commands

```bash
# Initialize project
npx claude-flow@alpha swarm init --topology mesh

# Test connections
python execution/test_connections.py

# Run scraping workflow
python execution/hunter_scrape_followers.py --url "linkedin_url"

# Generate campaign
python execution/crafter_campaign.py --segment "tier1"
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

## ICP Quick Reference

**Target**:
- 51-500 employees
- B2B SaaS / Technology
- VP Sales, CRO, RevOps
- Using CRM + seeking AI

**Disqualify**:
- < 20 employees
- Agency (unless enterprise)
- Already customer

---

## Important Reminders

- Do what has been asked; nothing more, nothing less.
- NEVER create files unless absolutely necessary.
- ALWAYS prefer editing existing files.
- NEVER proactively create documentation unless requested.
- Never save working files to the root folder.
- **ALL campaigns require AE approval via GATEKEEPER**.

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
| OPERATOR | Pipeline | ❌ | trigger_workflow |
| COACH | Pipeline | ❌ | update_contact |
| PIPER | Pipeline | ❌ | update_opportunity |
| SCHEDULER | Scheduling | ❌ | calendar_ops |
| RESEARCHER | Research | ❌ | read-only |

### Email Limits (NEVER EXCEED)
| Limit | Value | Reset |
|-------|-------|-------|
| Monthly | 3,000 | 1st of month |
| Daily | 150 | Midnight |
| Hourly | 20 | Top of hour |
| Per Domain/Hour | 5 | Top of hour |
| Min Delay | 30 sec | Between sends |

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

## 🛡️ GHL Guardrails (Legacy Reference)

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
│  │    GHL     │  │  Google    │  │   Gmail    │  │   Clay     │  │
│  │   Adapter  │  │  Calendar  │  │  Adapter   │  │  Adapter   │  │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │  LinkedIn  │  │  Supabase  │  │   Zoom     │  │  Webhook   │  │
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
| ghl | 150/day | send_email, create_contact, trigger_workflow |
| google_calendar | 100/hour | create_event, get_availability, find_slots |
| gmail | 500/hour | send_email, parse_thread, extract_intent |
| clay | 500/hour | enrich_contact, enrich_company |
| linkedin | 10/min | get_profile, search_people |
| supabase | 5000/hour | query, insert, update |
| zoom | 200/hour | create_meeting, get_meeting |

---

## 📅 Google Calendar MCP Server

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

---

## 📊 Health Dashboard

### Start Dashboard
```bash
cd chiefaiofficer-alpha-swarm
uvicorn dashboard.health_app:app --host 0.0.0.0 --port 8080
```

### Endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Current health status |
| `GET /api/agents` | Agent status (12 agents) |
| `GET /api/integrations` | Integration status |
| `GET /api/guardrails` | Rate limits & circuit breakers |
| `WS /ws` | Real-time WebSocket updates |

### Health Status Colors
- 🟢 HEALTHY: <5% error rate
- 🟡 DEGRADED: 5-20% error rate
- 🔴 UNHEALTHY: >20% error rate

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
