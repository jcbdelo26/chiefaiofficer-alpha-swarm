# AMP Acceleration Plan - Days 36-40: Vercel Lead Agent Patterns

## Executive Summary

Following deep research on Vercel's Lead Agent architecture, we implemented **4 core patterns** from their GTM automation system into the ChiefAIOfficer-beta-swarm:

1. **Intent Interpreter** (Intent Layer)
2. **Durable Workflow** (Checkpoint Persistence)
3. **Confidence-Based Replanning** (System Two Logic)
4. **Bounded Tools** (Fixed Tool Boundaries)

**Test Results**: 24/25 tests passing (1 failure is Windows file cleanup issue)

---

## Pattern 1: Intent Interpreter

**File**: [`core/intent_interpreter.py`](file:///D:/Agent%20Swarm%20Orchestration/chiefaiofficer-alpha-swarm/core/intent_interpreter.py)

### What It Does
Translates vague natural language inputs into structured, multi-step agentic goals.

### Key Classes
- `IntentInterpreter` - Main interpreter class
- `AgenticGoal` - Structured goal with steps, success criteria, priority
- `GoalStep` - Individual step definition

### Example Usage
```python
from core.intent_interpreter import IntentInterpreter

interpreter = IntentInterpreter()
goal = interpreter.interpret("Find 100 new leads from Gong competitors")

# goal.objective = ObjectiveType.DISCOVER_LEADS
# goal.agent_sequence = ["HUNTER", "ENRICHER", "SEGMENTOR"]
# goal.context["extracted_params"]["limit"] = 100
```

### Features
- Extracts limits, urgency, target companies, tiers from input
- Maps to 8 objective types (DISCOVER_LEADS, ENRICH_LEADS, etc.)
- Generates multi-step execution plans
- Persists goals for audit trail

---

## Pattern 2: Durable Workflow

**File**: [`core/durable_workflow.py`](file:///D:/Agent%20Swarm%20Orchestration/chiefaiofficer-alpha-swarm/core/durable_workflow.py)

### What It Does
Provides fault-tolerant, resumable workflow execution with SQLite-backed checkpointing.

### Key Classes
- `DurableWorkflow` - Main workflow class
- `CheckpointStore` - SQLite persistence layer
- `WorkflowManager` - Manages multiple workflows

### Example Usage
```python
from core.durable_workflow import DurableWorkflow, get_workflow_manager

manager = get_workflow_manager()
workflow = manager.create_workflow("lead_pipeline_001", workflow_type="lead_processing")

# Steps are automatically checkpointed
research = await workflow.step("research", hunter.research, {"lead": lead})
enriched = await workflow.step("enrich", enricher.augment, research)

# If workflow restarts, completed steps return cached results
await workflow.complete()
```

### Features
- Automatic retry on step failure (configurable max_retries)
- Resume from last checkpoint after restart
- Status tracking (PENDING, IN_PROGRESS, PAUSED, AWAITING_APPROVAL, COMPLETED, FAILED)
- `await_approval()` for human-in-the-loop gates
- Cleanup of old completed workflows

---

## Pattern 3: Confidence-Based Replanning

**File**: [`core/confidence_replanning.py`](file:///D:/Agent%20Swarm%20Orchestration/chiefaiofficer-alpha-swarm/core/confidence_replanning.py)

### What It Does
Implements System Two reasoning with confidence scoring and automatic replanning when confidence falls below threshold.

### Key Classes
- `ConfidenceReplanEngine` - Main replanning engine
- `QualificationResult` - Structured output for SEGMENTOR
- `ConfidenceAwareSegmentor` - Enhanced segmentor wrapper

### Example Usage
```python
from core.confidence_replanning import ConfidenceAwareSegmentor

segmentor = ConfidenceAwareSegmentor(confidence_threshold=0.85)

result = segmentor.qualify_lead(
    lead=lead,
    icp_score=75,
    tier="tier_2",
    score_breakdown={"title": 22, "company": 15}
)

# result.category = "WARM_LEAD"
# result.confidence = 0.78
# result.reason = "Score relies on few data points; Missing intent signals"
# result.needs_replan = True  (because 0.78 < 0.85)
# result.enrichment_gaps = ["email", "intent_signals"]
```

### Confidence Factors (Total 100%)
- **Data Completeness** (30%): Required vs optional fields present
- **Score Distribution** (25%): How many ICP components have data
- **Tier Clarity** (20%): Distance from tier boundaries
- **Intent Strength** (15%): Demo request > pricing > content > website
- **Source Reliability** (10%): demo_requester > competitor_follower > unknown

### Features
- Automatic replan loop (up to 3 attempts)
- Context enhancement between attempts
- Enrichment gap identification
- Personalization hook suggestions

---

## Pattern 4: Bounded Tools

**File**: [`core/bounded_tools.py`](file:///D:/Agent%20Swarm%20Orchestration/chiefaiofficer-alpha-swarm/core/bounded_tools.py)

### What It Does
Prevents runaway loops by enforcing iteration limits on agent tool usage.

### Key Classes
- `BoundedToolRegistry` - Registry with limits
- `BoundedHunterAgent` - HUNTER with 5 bounded tools
- `StepCountIs`, `ConsecutiveFailures`, `DurationExceeds` - Stop conditions

### Example Usage
```python
from core.bounded_tools import BoundedHunterAgent

hunter = BoundedHunterAgent()  # MAX_TOOL_CALLS = 20

report = await hunter.research(lead)

# report["total_tool_calls"] = 5  (stopped when complete)
# report["tools_used"] = ["check_crm", "fetch_linkedin", "analyze_tech_stack"]
# report["stats"]["stop_reason"] = "complete"
```

### HUNTER's Bounded Tools
| Tool | Category | Max Calls | Cooldown |
|------|----------|-----------|----------|
| search_rb2b | SEARCH | 5 | 2.0s |
| fetch_linkedin | FETCH | 10 | 1.0s |
| check_crm | CRM | 15 | 0.5s |
| analyze_tech_stack | ANALYZE | 10 | 1.0s |
| basic_enrich | ENRICH | 10 | 0.5s |

### Stop Conditions
- `StepCountIs(20)` - Max 20 total tool calls
- `ConsecutiveFailures(3)` - Stop after 3 failures in a row
- `DurationExceeds(600)` - Stop after 10 minutes

---

## Architecture Integration

```
┌─────────────────────────────────────────────────────────────┐
│              CHIEFAIOFFICER-BETA-SWARM (UPGRADED)            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              INTENT INTERPRETER (NEW)                │    │
│  │  "Find 100 leads" → AgenticGoal(steps=[...])        │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │              DURABLE WORKFLOW (NEW)                  │    │
│  │  workflow.step("research") → checkpoint → resume    │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │              BOUNDED HUNTER (NEW)                    │    │
│  │  5 tools, MAX_TOOL_CALLS=20, auto-stop              │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │                    ENRICHER                          │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │        CONFIDENCE-AWARE SEGMENTOR (NEW)             │    │
│  │  QualificationResult(confidence=0.85, reason="...") │    │
│  │  if confidence < 0.85 → REPLAN with more context    │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│                    (if qualified)                            │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │                    CRAFTER                           │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │         APPROVAL ENGINE (w/ rich context)           │    │
│  │  Includes: qualification.reason, research_summary   │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                    │
│  ┌──────────────────────▼──────────────────────────────┐    │
│  │             OPERATOR → GHL EXECUTION                │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Next Steps

1. **Integrate Intent Interpreter with UNIFIED_QUEEN**
   - Route `interpret()` output to workflow creation

2. **Wire Confidence-Aware Segmentor into existing segmentor**
   - Update `execution/segmentor_classify.py` to use `ConfidenceAwareSegmentor`

3. **Enhance Approval Messages**
   - Include `qualification.reason` and `enrichment_gaps` in Slack Block Kit

4. **Add Context Enhancement Hook**
   - When confidence < threshold, call ENRICHER for additional data

---

## Source References

- [Vercel Lead Agent GitHub](https://github.com/vercel-labs/lead-agent)
- [Workflow DevKit](https://useworkflow.dev/)
- [AI SDK Agent Class](https://ai-sdk.dev/docs/agents/overview)
- Interview: Drew Bredvick, Tenex - "Building the Lead Agent: A Game Changer"
