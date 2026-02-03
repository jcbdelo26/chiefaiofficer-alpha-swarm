# Unified Swarm Daily Prompt Cheat Sheet
## Quick Reference for 30-Day Implementation

**Start Date**: January 22, 2026  
**End Date**: February 20, 2026  
**Location**: `D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm`

---

## 🚀 QUICK START: Master Prompt

For first-time setup, copy the full master prompt from `UNIFIED_SWARM_IMPLEMENTATION_ROADMAP.md`. This cheat sheet provides daily quick prompts.

---

## 📅 WEEK 1: INFRASTRUCTURE (Jan 22-26)

### Day 1 (Jan 22) - Guardrails Core ✅ COMPLETE
```
Create core/unified_guardrails.py with circuit breaker (3-failure trip), 
rate limits (GHL: 150/day, 20/hour), per-agent quotas, exponential backoff 
(1s-16s), and grounding evidence validation. Reference rate_limiter.py 
and ghl_guardrails.py. Include tests in tests/test_unified_guardrails.py.
```
**IMPLEMENTED**: `core/unified_guardrails.py`, `tests/test_unified_guardrails.py`

### Day 2 (Jan 23) - Permission Matrix ✅ COMPLETE
```
Enhance core/unified_guardrails.py with permission matrix for all 12 agents, 
action validation framework, pre/post hooks. Create core/agent_action_permissions.json 
defining agent permissions and approval levels. Update CLAUDE.md.
```
**IMPLEMENTED**: `core/agent_action_permissions.json`, CLAUDE.md updated

### Day 3 (Jan 24) - Self-Annealing ✅ COMPLETE
```
Create core/self_annealing_engine.py with 4-step pipeline: RETRIEVE (HNSW 
from reasoning_bank.json), JUDGE (success/failure rating), DISTILL (extract 
learnings), CONSOLIDATE (EWC++ knowledge retention). Hook into Queen, log to 
learnings.json. Include tests.
```
**IMPLEMENTED**: `core/self_annealing_engine.py`, `tests/test_self_annealing_engine.py`

### Day 4 (Jan 25) - Google Calendar MCP ✅ COMPLETE
```
Create mcp-servers/google-calendar-mcp/ with Python/FastMCP: get_availability, 
create_event (Zoom link), update_event, delete_event, timezone_utils. 
Guardrails: mutex lock, working hours (9-6), 15-min buffer, 100 req/hour. 
OAuth 2.0 in credentials/google_calendar.json.
```
**IMPLEMENTED**:
- `mcp-servers/google-calendar-mcp/server.py` - MCP server with 6 tools
- `mcp-servers/google-calendar-mcp/guardrails.py` - Calendar guardrails
- `mcp-servers/google-calendar-mcp/config.py` - Configuration
- `tests/test_google_calendar_mcp.py` - 20 passing tests

**BONUS - Also implemented**:
- `core/unified_integration_gateway.py` - Centralized API management (7 adapters)
- `core/unified_health_monitor.py` - Real-time health monitoring
- `dashboard/health_app.py` - FastAPI health dashboard
- `tests/test_unified_integration_gateway.py` - 26 passing tests

### Day 5 (Jan 26) - Email Threading MCP ✅ COMPLETE
```
Create mcp-servers/email-threading-mcp/ with parse_thread, extract_context, 
detect_intent, maintain_thread. Update .mcp.json. Create directives/scheduling/ 
with calendar_coordination.md, meeting_preparation.md, tone_matching.md. 
Test with: npx claude-flow@alpha mcp test
```
**IMPLEMENTED**:
- `mcp-servers/email-threading-mcp/server.py` - 6 tools (parse, extract, detect, maintain, summarize, action_items)
- `directives/scheduling/calendar_coordination.md` - Calendar operations SOP
- `directives/scheduling/meeting_preparation.md` - Meeting brief generation SOP
- `directives/scheduling/tone_matching.md` - Communication style matching SOP
- `mcp_servers.json` - MCP server configuration
- `tests/test_email_threading_mcp.py` - 26 passing tests

---

## 📅 WEEK 2: UNIFIED QUEEN (Jan 27-31)

### Day 6 (Jan 27) - Queen Core ✅ COMPLETE
```
Create execution/unified_queen_orchestrator.py merging revenue_queen and Alpha 
Queen. Add: agent registry (12 agents), task queue, context budget (<40%), 
SPARC enforcement, audit integration. Reference CLAUDE.md and sparc_methodology.md.
```
**IMPLEMENTED**:
- `execution/unified_queen_orchestrator.py` - Full implementation with:
  - 13-agent registry (all AgentName enum members)
  - Q-learning intelligent routing with epsilon-greedy (ε=0.1)
  - Byzantine consensus for critical decisions (2/3 vote, weighted)
  - Context budget management (Dumb Zone at 40%)
  - SPARC methodology enforcement (5-phase scan)
  - Parallel task workers (4 concurrent)
  - Self-annealing integration
- `tests/test_unified_queen_orchestrator.py` - 30 passing tests

### Day 7 (Jan 28) - Queen Routing ✅ COMPLETE (merged with Day 6)
```
Enhance unified_queen_orchestrator.py with Q-learning routing: Q-table init, 
epsilon-greedy (ε=0.1), Q-value updates, persist to .hive-mind/q_table.json. 
Add routing: LEAD_GEN, PIPELINE, SCHEDULING, RESEARCH task categories. 
Byzantine consensus for critical decisions (2/3 vote, Queen 3x weight).
```
**ALREADY IMPLEMENTED in Day 6**:
- QLearningRouter class with full TD-learning update rule
- Q-table persistence to `.hive-mind/q_table.json`
- Task categories: LEAD_GEN, PIPELINE, SCHEDULING, RESEARCH, APPROVAL, SYSTEM
- ByzantineConsensus with weighted voting (QUEEN=3, GATEKEEPER=2, others=1)

### Day 8 (Jan 29) - Swarm Coordination ✅ COMPLETE
```
Enhance unified_queen_orchestrator.py with parallel spawning (12 concurrent), 
heartbeats, auto-restart. Hive-mind memory (.hive-mind/knowledge/, LRU cache, 
SQLite WAL). Hook system (pre-task, post-task, on-error). Integrate 
self_annealing_engine.py.
```
**IMPLEMENTED**:
- `core/swarm_coordination.py` - Full swarm coordination module with:
  - HeartbeatMonitor: 30s intervals, dead agent detection, history tracking
  - WorkerPool: Dynamic scaling (min/max), stuck task detection, recovery
  - RecoveryManager: Auto-restart with exponential backoff, max attempts
  - HookRegistry: pre_task, post_task, on_error, on_agent_start/stop/recover
  - SwarmCoordinator: Main engine integrating all components
  - Auto-scaling based on queue depth (80% up, 20% down thresholds)
- `tests/test_swarm_coordination.py` - 31 passing tests
- Competitive intelligence integrated from Qualified.com and Artisan.co

### Day 9 (Jan 30) - Unified Workflows ✅ COMPLETE
```
Create .agent/workflows/: unified-lead-to-meeting.md, unified-pipeline-scan.md, 
unified-meeting-prep.md, unified-approval-flow.md. YAML format with agent 
assignments, triggers, success criteria. Full 12-agent handoff definition.
```
**IMPLEMENTED**:
- `.agent/workflows/unified-lead-to-meeting.md` - Full 12-agent pipeline (LinkedIn → booked meeting)
- `.agent/workflows/unified-pipeline-scan.md` - 15-min interval monitoring with ghost detection
- `.agent/workflows/unified-meeting-prep.md` - 8 PM brief generation with research workflow
- `.agent/workflows/unified-approval-flow.md` - GATEKEEPER routing, auto-approve, escalation

### Day 10 (Jan 31) - Week 2 Integration Test ✅ COMPLETE
```
Test unified_queen_orchestrator.py: routing accuracy, Q-learning updates, 
Byzantine consensus, context budget. Test workflows: lead-to-meeting simulation, 
handoffs, logging. Create tests/test_unified_queen_integration.py. Fix issues, 
document in learnings.json.
```
**IMPLEMENTED**:
- `tests/test_unified_queen_integration.py` - 41 passing tests covering:
  - Routing accuracy (6 tests)
  - Q-learning updates and persistence (4 tests)
  - Byzantine consensus voting (4 tests)
  - Context budget management (5 tests)
  - Workflow simulations: lead-to-meeting, pipeline-scan, meeting-prep, approval-flow (15 tests)
  - Swarm coordination integration (4 tests)
  - Self-annealing integration (2 tests)
  - Audit trail logging (2 tests)
- `.hive-mind/learnings.json` - Updated with Day 10 learnings

**DAY 9-10 REFINEMENTS (Jan 22, 2026)** ✅ COMPLETE:

1. **Timezone Edge Cases** (`mcp-servers/google-calendar-mcp/guardrails.py`):
   - 48 timezone aliases (EST→America/New_York, PST, GMT, CET, IST, JST, etc.)
   - `validate_timezone()` with suggestions for invalid timezones
   - `convert_timezone_safe()` with fallback and DST handling
   - `_check_dst_transition()` for gap/fold detection
   - `get_user_working_hours_in_tz()` with midnight-span support
   - 45 tests in `tests/test_calendar_timezone.py`

2. **Q-Learning Fine-Tuning** (`execution/unified_queen_orchestrator.py`):
   - Adaptive epsilon decay (ε=0.1→0.01 over training)
   - Composite reward calculation (latency, error rate, priority bonuses)
   - UCB1 exploration strategy (`select_agent_ucb()`)
   - Experience replay buffer with batch learning
   - Enhanced stats: epsilon_current, training_episodes, avg_reward_last_100
   - 5 new tests for Q-learning enhancements

3. **Google Calendar Integration Tests** (`tests/test_calendar_integration.py`):
   - 29 passing tests + 4 real API tests (skipped by default)
   - TestCalendarAvailability, TestEventCreation, TestFindSlots
   - TestRateLimits, TestEventOperations, TestMCPTools
   - Graceful credential error handling in server.py

**Test Summary**: 109 passed, 4 skipped in 13.07s

---

## 📅 WEEK 3: SPECIALIZED AGENTS (Feb 1-5)

### Day 11 (Feb 1) - Scheduler Core ✅ COMPLETE
```
Create execution/scheduler_agent.py with: calendar availability check via 
google-calendar-mcp, 3-5 time proposals in prospect's timezone, exchange 
tracking. Guardrails: max 5 exchanges → escalate, never double-book, 
working hours (9-6), 15-min buffer. Reference responder_objections.py.
```
**IMPLEMENTED**:
- `execution/scheduler_agent.py` - Full scheduler agent with:
  - Calendar availability checking via Google Calendar MCP
  - Time proposal generation (3-5 options) with learned patterns
  - Exchange tracking (max 5 before escalation)
  - Timezone resolution (48+ aliases → IANA)
  - Guardrails: working hours (9-6), 15-min buffer, no double-booking
  - Booking with auto-generated Zoom links
  - Self-annealing pattern learning (preferred hours, success by day)
- `tests/test_scheduler_agent.py` - 25 passing tests covering:
  - Initialization and patterns
  - Time proposals (structure, count, timezone)
  - Scheduling requests (creation, storage, status)
  - Prospect response handling (accept, reject, counter, reschedule)
  - Escalation after max exchanges
  - Meeting booking and timezone resolution


### Day 12 (Feb 2) - Scheduler Calendar Ops ✅ COMPLETE
```
Enhance scheduler_agent.py with: create invite (Zoom link), update/cancel 
meetings, reminders (24h, 1h). GHL integration: update contact, log activity, 
trigger RESEARCHER. Self-annealing: log booking patterns, track avg exchanges, 
learn preferred slots.
```
**IMPLEMENTED** (additions to scheduler_agent.py):
- `update_ghl_after_booking()` - GHL integration with contact update, tagging, activity log
- `_trigger_researcher()` - Creates research task in .hive-mind/researcher/queue/
- `schedule_reminders()` - 24h and 1h reminder scheduling
- `check_pending_reminders()` - Reminder queue processing
- `send_reminder_notification()` - Notification to outbox
- `book_meeting_with_integrations()` - Full booking with Calendar + GHL + Reminders + Researcher

### Day 13 (Feb 3) - Researcher Core ✅ COMPLETE
```
Create execution/researcher_agent.py with: company research (website, LinkedIn, 
news) via exa-mcp, attendee research (profiles, GHL history), tech stack and 
funding detection. Caching: .hive-mind/researcher/cache/ (7d company, 1d news). 
Trigger: 8 PM night before meeting.
```
**IMPLEMENTED**:
- `execution/researcher_agent.py` - Full researcher agent (1,100+ lines) with:
  - `research_company()` - Company intel (website, industry, news, tech stack, pain points)
  - `research_attendee()` - Attendee profiles (title inference, GHL history, LinkedIn)
  - `_detect_tech_stack()` - Technology detection from website
  - `predict_objections()` - Objection prediction with recommended responses
  - `generate_talking_points()` - Personalized talking points with evidence
  - `generate_meeting_brief()` - Complete one-page brief with quality scoring
  - `process_research_queue()` - Queue processing for scheduled research
  - Caching layer with 7-day TTL
- Integration with SCHEDULER via task queue

### Day 14 (Feb 4) - Researcher Brief Gen ✅ INCLUDED IN DAY 13
```
Enhance researcher_agent.py with: objection prediction (industry/size/role), 
proof point selection (similar companies), question generation (5 business, 
2 BANT). Brief: markdown one-page, email to AE, save to .hive-mind/researcher/briefs/. 
Quality scoring: min 80% completeness.
```
**NOTE**: Day 14 features were included in Day 13 implementation:
- Objection prediction with industry/size/role factors ✅
- Talking point generation with evidence ✅
- Meeting brief with quality scoring ✅
- Save to .hive-mind/researcher/briefs/ ✅

### Day 15 (Feb 5) - Communicator (Enhanced Crafter) ✅ COMPLETE
```
Enhance execution/crafter_agent.py with: tone matching (>85% similarity), 
email-threading-mcp context, scheduling intent detection, 8-stage sales 
awareness (SalesGPT), follow-up automation (2d cadence). Preserve campaign 
creation. Route scheduling intents to SCHEDULER.
```
**Implementation Complete (1,050+ lines)**:
- Created `execution/communicator_agent.py` with full enhanced crafter ✅
- ToneAnalyzer class with 6-dimension analysis (formality, warmth, urgency, complexity, assertiveness, sentiment) ✅
- Tone matching with >85% similarity threshold ✅
- Email-threading-mcp integration for context extraction ✅
- Scheduling intent detection → routes to SCHEDULER agent ✅
- 8-stage SalesGPT sales awareness model:
  1. INTRODUCTION - Initial outreach, brand awareness
  2. QUALIFICATION - ICP fit validation, needs discovery
  3. VALUE_PROP - Pain points addressed, solution positioning
  4. NEEDS_ANALYSIS - Deep dive into requirements
  5. SOLUTION_PRESENT - Demo/proposal offered
  6. OBJECTION_HANDLE - Address concerns and blockers
  7. CLOSE - Ask for commitment, next steps
  8. FOLLOW_UP - Post-meeting nurture, retention
- FollowUpManager with 2-day cadence automation ✅
- ProspectStateManager for tracking communication state ✅
- Stage advancement based on intent triggers ✅
- Campaign creation preserved from Crafter ✅
- 50 tests passing (tests/test_communicator_agent.py) ✅

---

## 📅 WEEK 4: REDUNDANCY (Feb 6-10)

### Day 16 (Feb 6) - Failsafe Layers 1-2 ✅ COMPLETE
```
Create core/multi_layer_failsafe.py Layer 1 (Input Validation: type check, 
sanitize, length limits, encoding). Layer 2 (Circuit Breaker: per-agent, 
3-failure trip, backoff 1-60s, auto-reset 5min, half-open test). 
Integrate with unified_guardrails.py.
```
**Implementation Complete (1,400+ lines)**:
- Created `core/multi_layer_failsafe.py` with Layer 1 and Layer 2 ✅
- **Layer 1: Input Validation** ✅
  - Type checking with automatic coercion (str, int, float, bool)
  - InputSanitizer: strip, normalize whitespace, escape HTML, max length
  - InjectionDetector: SQL injection, XSS, command injection patterns
  - FieldSchema for declarative validation (required, min/max length, pattern, allowed values)
  - Custom validators support
  - Encoding validation (UTF-8)
- **Layer 2: Circuit Breaker (Enhanced Per-Agent)** ✅
  - Per-agent configurations for all 13 agents
  - 3-failure trip (configurable per agent)
  - Exponential backoff 1-60s with jitter
  - Auto-reset after 5 minutes (configurable)
  - Half-open test mode before full recovery
  - Integrates with existing `core/circuit_breaker.py`
- **MultiLayerFailsafe Manager** ✅
  - `execute_with_failsafe()` for protected execution
  - Layer selection: apply specific layers [1, 2]
  - Fallback support when circuit open or operation fails
  - Metrics tracking
- **Decorators** ✅
  - `@validate_input()` for input validation
  - `@with_failsafe()` for full protection
- 77 tests passing (tests/test_multi_layer_failsafe.py) ✅

### Day 17 (Feb 7) - Failsafe Layers 3-4 ✅ COMPLETE
```
Enhance multi_layer_failsafe.py Layer 3 (Fallback Chain: primary → secondary 
→ human escalation, log activations). Layer 4 (Byzantine Consensus: 2/3 
agreement, Queen 3x weight, 3 rounds max, escalate on no consensus). 
Create unit tests.
```
**Implementation Complete (Day 17 adds ~800 lines)**:
- **Layer 3: Fallback Chain** ✅
  - `FallbackChain` class with `FallbackLevel` enum (PRIMARY, SECONDARY, TERTIARY, HUMAN_ESCALATION)
  - `register_handler()` for per-agent/operation fallbacks
  - `register_human_escalation()` queues for human review
  - `execute_with_fallback()` tries primary → fallbacks in order
  - Activation logging with stats tracking
  - Persistent storage in `.hive-mind/failsafe/fallback/`
- **Layer 4: Byzantine Consensus** ✅
  - `ByzantineConsensus` class with weighted voting
  - Queen gets 3x voting weight, all other agents get 1x
  - Default 2/3 (67%) agreement required
  - Maximum 3 rounds before escalation
  - `quick_vote()` for single-round decisions
  - `start_session()` + `cast_vote()` + `finalize_round()` for multi-round
  - Persistent history in `.hive-mind/failsafe/consensus/`
- **MultiLayerFailsafe Integration** ✅
  - `execute_with_failsafe()` now supports layers=[1,2,3,4]
  - `require_consensus` parameter for Layer 4
  - `register_fallback()` and `register_human_escalation()` helper methods
  - Metrics tracking for all 4 layers
- 110 tests passing (expanded from 77)

**AMP ACCELERATION SESSION 1 (Jan 22, 2026)** ✅:
```
Test Suite: 598 passed, 4 skipped, 0 failed
Deprecations: 0 (fixed 43+ datetime.utcnow() calls)
Mock Framework: tests/mocks/ with unified adapters
Workflow Simulator: execution/workflow_simulator.py (39 tests)
CI/CD: scripts/test-all.ps1, scripts/deploy.ps1, scripts/quick-test.ps1
Acceleration Plan: AMP_ACCELERATION_PLAN.md (remaining days in 5 sessions)
```

### Day 18 (Feb 8) - Audit Trail ✅ COMPLETE
```
Create core/audit_trail.py logging: timestamp, agent_id, action_type, 
target_resource, input/output summary (redact PII), approval_status, 
grounding_evidence, duration_ms, success. SQLite primary (.hive-mind/audit.db), 
JSON backup, 90d retention, query API, weekly reports.
```
**Implementation Complete**:
- **PIIRedactor class** ✅
  - Detects & redacts: email, phone, SSN, credit card, IP address, API keys
  - Sensitive field detection (password, token, secret, etc.)
  - Recursive dictionary/list redaction
  - `create_summary()` for truncated, redacted summaries
- **Enhanced AuditEntry** ✅
  - New fields: target_resource, input_summary, output_summary, approval_status
  - ApprovalStatus enum (approved, pending, rejected, auto_approved, escalated, not_required)
- **Enhanced log_action()** ✅
  - Automatic PII redaction (toggleable with `redact_pii=False`)
  - Input/output data → redacted summaries
  - Target resource PII redaction
- **Database migration** ✅
  - Added new columns with ALTER TABLE fallback for existing DBs
- 48 tests passing (27 existing + 21 Day 18)


### Day 19 (Feb 9) - Health Monitor ✅ COMPLETE
```
Create core/unified_health_monitor.py monitoring: heartbeats (30s), rate limit 
status, circuit breakers, ReasoningBank size, queue depths, error rates, 
response times (p50/p95/p99). Alerts: Slack (failure, 80% limit), SMS (critical), 
email (daily summary). Streamlit dashboard.
```
**Implementation Complete**:
- **QueueDepthTracker class** ✅
  - Tracks: lead_processing, email_outbox, enrichment, campaign_generation, escalation, consensus_voting
  - Status levels: healthy/warning/critical
  - Methods: record_enqueue/dequeue, get_all_depths, get_critical_queues
- **ReasoningBankMonitor class** ✅
  - Tracks: entries count, file size (MB), modification time
  - Status thresholds: >50MB warning, >100MB critical
- **Enhanced AlertManager** ✅
  - `send_email_alert()` - SMTP/SendGrid (logs if not configured)
  - `send_daily_summary_email()` - Full system health report
- **Enhanced HealthMonitor** ✅
  - `get_health_status()` now includes: queue_depths, reasoning_bank, latency_stats, stale_agents, health_score
  - Convenience methods: record_enqueue/dequeue, get_queue_depths, get_critical_queues, get_reasoning_bank_stats
- **Streamlit Dashboard** ✅
  - Created `dashboard/health_dashboard.py`
  - Real-time metrics: agents, queues, latency, rate limits, alerts
  - Auto-refresh with configurable interval
- 59 tests passing (52 existing + 7 Day 19 tests)



### Day 20 (Feb 10) - Week 4 Integration Test ✅ COMPLETE
```
Test multi_layer_failsafe.py: input validation, circuit breakers, fallback 
chain, Byzantine consensus. Test audit_trail.py: action logging, query API, 
reports. Test unified_health_monitor.py: agent failures, alerts, dashboard. 
Create tests/test_redundancy_systems.py.
```
**Implementation Complete**:
- Created `tests/test_redundancy_systems.py` ✅
  - **TestMultiLayerFailsafeIntegration** (5 tests): injection detection, circuit breaker, fallback chain, Byzantine consensus, all layers
  - **TestAuditTrailIntegration** (5 tests): logging, PII redaction, query API, weekly report, retention
  - **TestHealthMonitorIntegration** (5 tests): failures, circuit state, queue depth, alerts, health score
  - **TestCrossSystemIntegration** (6 tests): failsafe→audit, failsafe→health, full failure scenario, recovery, PII protection
  - **TestRedundancyStress** (3 tests): concurrent logging, rapid circuit changes, high volume queues
- **24 new integration tests** all passing
- Total test count: **131 tests** (107 existing + 24 new)



---

## 📅 WEEK 5: SECURITY (Feb 11-15)

### Day 21 (Feb 11) - AIDefence Threats ✅ COMPLETE
```
Create core/aidefence.py with threat categories: prompt injection, jailbreak, 
data exfiltration, command injection. Detection: regex patterns, HNSW similarity, 
LLM classification. Confidence scoring (0-1, threshold 0.7). Log all detections.
```
**Implementation Complete**:
- `core/aidefence.py` (980 lines) ✅
  - **Prompt Injection Detection**: 17 regex patterns (ignore instructions, reveal prompt, developer mode, etc.)
  - **Jailbreak Detection**: 20 patterns (DAN, STAN, hypothetical scenarios, base64 obfuscation)
  - **Data Exfiltration Detection**: 17 patterns (export all, dump database, API keys, credentials)
  - **Command Injection Detection**: Reuses patterns from multi_layer_failsafe.py (SQL, XSS, shell)
  - **PII Detection**: 12 PII types with validation (email, phone, SSN, credit card, API keys, etc.)
  - **Confidence Scoring**: 0-1 scale with thresholds (safe <0.3, suspicious 0.3-0.7, threat >0.7)
  - **TF-IDF Similarity**: Lightweight pattern matching for known threats
  - **Risk Assessment**: Weighted scoring across all threat categories
- `tests/test_aidefence.py` - **77 tests passing** ✅
- Total test count: **1,345 tests** (1,268 existing + 77 AIDefence)


### Day 22 (Feb 12) - AIDefence PII - [COMPLETE]
**Implementation Complete**:
- `core/aidefence.py`: Enhanced with `PIIResponse` (BLOCK, SANITIZE, WARN, LOG) and `PIIDetector` improvements.
- **Self-Learning**: Implemented false positive/negative tracking in `.hive-mind/aidefence/`.
- **Integration**: Added `@with_pii_protection` decorator for agent I/O.
- **Testing**: **22/22 tests passed** in `tests/test_aidefence_day22.py`.


### Day 23 (Feb 13) - Approval Engine Part 1
```
Create core/approval_engine.py with: ALWAYS_APPROVE (email_send, calendar_create, 
crm_change, close_lost), SMART_APPROVAL (follow_up >90% match), 
NEVER_AUTO_APPROVE (pricing, contracts, legal, bulk). Queue: 
.hive-mind/approval_queue.json with timeout tracking.
```

### Day 24 (Feb 14) - Approval Engine Part 2
```
Enhance approval_engine.py with: Slack Block Kit (approve/reject/edit buttons, 
context preview), SMS for urgent (<30min timeout), email fallback (2hr timeout). 
Timeout handling: escalate to fallback approver. GATEKEEPER integration, 
audit logging.
```

### Day 25 (Feb 15) - Security Testing
```
Test aidefence.py: known threats, PII detection, prompt injection, jailbreak. 
Compliance: CAN-SPAM, GDPR, unsubscribe. Penetration test: bypass attempts, 
edge cases. Create tests/test_security_compliance.py. Generate compliance report.
```

---

## 📅 WEEK 6: PRODUCTION (Feb 16-20)

### Day 26 (Feb 16) - Test Suite Part 1
```
Create tests/test_unified_swarm.py with unit tests for: UNIFIED QUEEN routing, 
SCHEDULER calendar ops, RESEARCHER brief gen, COMMUNICATOR tone matching, 
GATEKEEPER approvals. Mock external APIs: Google Calendar, Gmail, GHL. 
Target 80%+ coverage.
```

### Day 27 (Feb 17) - Test Suite Part 2
```
Add to test_unified_swarm.py: integration tests (lead-to-meeting, pipeline 
scan, meeting prep, approval flow), end-to-end (full lead pipeline, handoffs, 
audit), stress tests (rate limits, concurrent agents, queue depth), 
failover tests (circuit breakers, fallback, consensus).
```

### Day 28 (Feb 18) - Deployment Script
```
Create scripts/deploy_unified_swarm.ps1: pre-deploy (validate deps, check 
creds, run tests, backup), deploy (update MCP, spawn queen, start agents, 
init monitoring), post-deploy (smoke tests, verify agents, start dashboard). 
Rollback procedure (auto on failure, manual command). Create .sh for Linux.
```

### Day 29 (Feb 19) - Staging Deploy
```
Deploy to staging: run deployment script, verify all agents, test all workflows 
end-to-end. Performance: <5s response, 0 double-bookings in 100 tests, 100% 
timezone accuracy, 95%+ brief delivery. Collect metrics, fix issues, 
document results.
```

### Day 30 (Feb 20) - Production Go-Live 🚀
```
Final checks: all tests passing, staging validated, team trained, monitoring 
ready. Execute deploy_unified_swarm.ps1, monitor 1hr, verify metrics. 
Process real leads, monitor flows, check AE satisfaction. Create go-live docs, 
update CLAUDE.md, email team. Plan ongoing optimization.
```

---

## 📁 KEY FILES QUICK REFERENCE

### Core (create Week 1 & 4)
```
core/unified_guardrails.py
core/self_annealing_engine.py
core/multi_layer_failsafe.py
core/audit_trail.py
core/unified_health_monitor.py
core/aidefence.py
core/approval_engine.py
```

### MCP (create Week 1)
```
mcp-servers/google-calendar-mcp/server.py
mcp-servers/email-threading-mcp/server.py
```

### Agents (create Week 2-3)
```
execution/unified_queen_orchestrator.py
execution/scheduler_agent.py
execution/researcher_agent.py
execution/crafter_agent.py (enhance)
```

### Workflows (create Week 2)
```
.agent/workflows/unified-lead-to-meeting.md
.agent/workflows/unified-pipeline-scan.md
.agent/workflows/unified-meeting-prep.md
.agent/workflows/unified-approval-flow.md
```

### Tests (create Week 4-6)
```
tests/test_unified_guardrails.py
tests/test_self_annealing.py
tests/test_redundancy_systems.py
tests/test_security_compliance.py
tests/test_unified_swarm.py
```

---

## ✅ DAILY VERIFICATION CHECKLIST

After each day's work, verify:
- [ ] Code runs without errors
- [ ] Unit tests passing
- [ ] No regressions in existing functionality
- [ ] Documentation updated if needed
- [ ] Learnings logged to `.hive-mind/learnings.json`

---

## 🔧 TROUBLESHOOTING

### If tests fail:
```
python -m pytest tests/ -v --tb=short
```

### If MCP server fails:
```
npx claude-flow@alpha mcp test
```

### If agent not responding:
```
python execution/health_check.py --agent <agent_name>
```

### To rollback:
```
.\scripts\deploy_unified_swarm.ps1 -Rollback
```

---

## 📞 REFERENCE DOCS

- Full roadmap: `UNIFIED_SWARM_IMPLEMENTATION_ROADMAP.md`
- SkejClone strategy: `D:\Antigravity Projects\SKEJCLONE_INTEGRATION_STRATEGY.md`
- SkejClone PRD: `C:\Users\ADMIN\Downloads\CAIO_RevOps_Agentic_PRD.md`
- Architecture: `CLAUDE.md`
- Existing PRD: `PRD.md`

---

**Good luck with the implementation! 🎯**
