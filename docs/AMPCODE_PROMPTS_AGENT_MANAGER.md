# 🤖 Ampcode Implementation Prompts for Agent Manager

**Purpose**: Ready-to-use prompts for AI coding assistants (Cursor, Copilot, Claude) to complete Agent Manager implementation

**Usage**: Copy these prompts into your AI assistant and iterate step-by-step

---

## 📋 Implementation Sequence

1. ✅ Core structure created → `core/agent_manager.py`
2. 🔨 Complete TODO implementations (use prompts below)
3. 🧪 Create test suite
4. 🔌 Create MCP server wrapper
5. 🚀 Build unified workflows

---

## 🎯 Prompt 1: Complete Agent Discovery Function

```
# CONTEXT:
I have an Agent Manager core at @core/agent_manager.py with a stub discover_agents() function that needs implementation.

# TASK:
Complete the `discover_agents()` method in the AgentRegistry class.

# REQUIREMENTS:
1. Scan the given directory path for Python files
2. Look for agent metadata in file docstrings or class definitions
3. Extract: agent_id, agent_type, capabilities, dependencies
4. Optionally auto-register discovered agents
5. Return list of discovered agent IDs

# IMPLEMENTATION DETAILS:
- Use pathlib for file scanning
- Parse Python files with ast module to avoid imports
- Look for patterns like:
  ```python
  class HunterAgent:
      """
      Agent Type: sourcing
      Capabilities: linkedin_scraping, profile_extraction
      Dependencies: enricher
      """
  ```
- Handle files without proper metadata gracefully
- Support both execution/ and revenue_coordination/ structures

# OUTPUT:
Complete implementation of discover_agents() method with:
- File scanning logic
- Metadata extraction
- Auto-registration
- Error handling
- Logging
```

---

## 🎯 Prompt 2: Complete Health Check Function

```
# CONTEXT:
I have @core/agent_manager.py with stub agent_health_check() that needs real implementation.

# TASK:
Complete the agent_health_check() method in AgentRegistry class.

# REQUIREMENTS:
1. Check if agent is registered
2. Verify MCP server is running (if agent has one)
3. Test agent dependencies are available
4. Ping agent for basic functionality
5. Return comprehensive health status

# IMPLEMENTATION DETAILS:
- For MCP servers: try connecting to server and calling a simple tool
- For dependencies: recursively check if required agents are healthy
- Add timeout handling (5 seconds max)
- Return detailed error messages for failures

# EXAMPLE OUTPUT:
```python
{
    "healthy": True,
    "agent_id": "hunter",
    "status": "running",
    "mcp_server_ok": True,
    "mcp_server_details": {
        "path": "./mcp-servers/hunter-mcp",
        "responding": True,
        "tools_available": ["scrape_linkedin", "extract_profile"]
    },
    "dependencies_ok": True,
    "dependency_details": {
        "enricher": {"healthy": True, "status": "running"}
    },
    "last_check": "2026-01-16T03:42:30Z"
}
```

# OUTPUT:
Complete implementation with MCP server checks and dependency validation
```

---

## 🎯 Prompt 3: Implement Context Monitoring

```
# CONTEXT:
I have @core/agent_manager.py with a ContextManager class that needs monitor_context_usage() implemented.

This is for FIC (Frequent Intentional Compaction) methodology - keep agents in "smart zone" (<40% context).

# TASK:
Complete the monitor_context_usage() method.

# REQUIREMENTS:
1. Query agent's current context window usage
2. Calculate percentage of context used
3. Determine zone: smart (<40%), warning (40-70%), dumb (>70%)
4. Recommend compaction strategy if needed

# IMPLEMENTATION DETAILS:
- For Python agents: estimate context from message history length
- For MCP agents: call a monitoring tool if available
- Use heuristics: rough estimate is 4 chars ≈ 1 token
- Store history in .hive-mind/context_history/{agent_id}.json

# COMPACTION RECOMMENDATIONS:
- smart zone → None
- warning zone → Suggest "rpi" or "semantic_anchor"
- dumb zone → Force "checkpoint" (save and restart)

# EXAMPLE OUTPUT:
```python
{
    "agent_id": "crafter",
    "context_used": "42%",
    "context_tokens": 3400,
    "max_tokens": 8000,
    "zone": "warning",
    "recommendation": "rpi",
    "history": {
        "messages": 45,
        "avg_length": 150
    },
    "trend": "increasing"
}
```

# OUTPUT:
Complete implementation with token counting and zone detection
```

---

## 🎯 Prompt 4: Implement Workflow System

```
# CONTEXT:
I have @core/agent_manager.py with stub create_workflow() and execute_workflow() methods.

# TASK:
Complete both methods to create and execute multi-agent workflows.

# REQUIREMENTS FOR create_workflow():
1. Validate all agents in steps exist
2. Check dependencies between agents
3. Create workflow definition JSON
4. Save to .hive-mind/workflows/{workflow_id}.json
5. Return workflow ID

# REQUIREMENTS FOR execute_workflow():
1. Load workflow definition
2. Initialize required agents if not running
3. Execute steps in sequence
4. Create handoffs between agents
5. Handle errors and retries
6. Track progress
7. Return final output

# WORKFLOW DEFINITION FORMAT:
```json
{
    "workflow_id": "lead_to_campaign_unified",
    "name": "Lead to Campaign (Unified)",
    "steps": [
        {
            "step_id": "1_scrape",
            "agent": "hunter",
            "action": "scrape_linkedin",
            "inputs": ["linkedin_url"],
            "outputs": ["scraped_leads"]
        },
        {
            "step_id": "2_intent",
            "agent": "revenue_scout",
            "action": "detect_intent",
            "inputs": ["scraped_leads"],
            "outputs": ["intent_signals"]
        }
    ],
    "created_at": "2026-01-16T03:42:30Z"
}
```

# EXECUTION FLOW:
1. For each step:
   - Get input data (from previous step output or initial input)
   - Create handoff to agent
   - Wait for agent to complete
   - Store output for next step
   - Update workflow state

# ERROR HANDLING:
- If agent fails: retry up to 3 times
- If still failing: mark workflow as failed, save state
- Support resume from last successful step

# OUTPUT:
Complete implementations of both methods with workflow persistence
```

---

## 🎯 Prompt 5: Implement Pattern Detection in Learnings

```
# CONTEXT:
I have @core/agent_manager.py with LearningManager class that needs identify_patterns() implemented.

# TASK:
Complete the identify_patterns() method to find recurring issues in learnings.

# REQUIREMENTS:
1. Group learnings by similarity
2. Find patterns that occur >= min_occurrences times
3. Suggest systematic fixes
4. Calculate confidence scores

# IMPLEMENTATION DETAILS:
- For event_type filtering: only analyze specified type
- Use fuzzy matching to group similar learnings
- Pattern examples:
  - "tier1_leads_reject_price_mentions" → Don't mention pricing in tier1 emails
  - "competitor_comparisons_fail" → Avoid direct competitor comparisons
- Confidence = (occurrences / total_similar_events)

# ALGORITHM:
1. Filter learnings by event_type and time period
2. Extract key features from learning_data (e.g., rejection_reason, tier, template)
3. Cluster similar learnings
4. For clusters >= min_occurrences:
   - Identify common pattern
   - Suggest fix based on pattern type
   - Calculate confidence
5. Return sorted by confidence (highest first)

# EXAMPLE OUTPUT:
```python
[
    {
        "pattern_id": "pattern_001",
        "pattern": "tier1_leads_reject_price_focus",
        "description": "Tier 1 leads consistently reject emails that mention pricing early",
        "occurrences": 7,
        "total_similar": 10,
        "confidence": 0.70,
        "suggested_fix": "add_value_prop_emphasis",
        "suggested_directive_update": "directives/crafter_rules.md: Add rule to delay pricing discussion for tier1",
        "affected_agents": ["crafter"],
        "learnings": ["learning_45_gatekeeper", "learning_52_gatekeeper", ...]
    },
    {
        "pattern_id": "pattern_002",
        "pattern": "missing_personalization_fails",
        "description": "Campaigns without company-specific details have low approval",
        "occurrences": 5,
        "total_similar": 6,
        "confidence": 0.83,
        "suggested_fix": "require_research_phase",
        "suggested_directive_update": "directives/rpi_workflow.md: Make research phase mandatory",
        "affected_agents": ["crafter", "revenue_scout"],
        "learnings": ["learning_38_gatekeeper", "learning_41_gatekeeper", ...]
    }
]
```

# OUTPUT:
Complete implementation with clustering and pattern detection
```

---

## 🎯 Prompt 6: Create Agent Manager MCP Server

```
# CONTEXT:
I have a complete Agent Manager core at @core/agent_manager.py.

Now I need to expose it as an MCP server for Claude/AI agents to use.

# TASK:
Create a new MCP server at mcp-servers/agent-manager-mcp/

# REQUIREMENTS:
Create files:
1. mcp-servers/agent-manager-mcp/server.py - Main MCP server
2. mcp-servers/agent-manager-mcp/README.md - Documentation
3. mcp-servers/agent-manager-mcp/__init__.py - Package init

# MCP TOOLS TO IMPLEMENT:
1. register_agent(agent_id, agent_type, capabilities, dependencies, mcp_server)
2. get_agent(agent_id)
3. list_agents(filter_by_type, filter_by_status)
4. initialize_agent(agent_id, config, warm_start)
5. create_handoff(from_agent, to_agent, data, priority)
6. get_handoff_queue(agent_id)
7. monitor_context_usage(agent_id)
8. log_learning(source_agent, event_type, learning_data)
9. create_workflow(name, steps)
10. execute_workflow(workflow_id, input_data)
11. health_check()

# MCP SERVER STRUCTURE:
```python
from mcp.server import Server
from mcp.types import Tool, TextContent
import sys
sys.path.append("../..")
from core.agent_manager import AgentManager

app = Server("agent-manager-mcp")
agent_manager = AgentManager()

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="register_agent",
            description="Register a new agent in the unified registry",
            inputSchema={...}
        ),
        # ... more tools
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "register_agent":
        result = agent_manager.registry.register_agent(**arguments)
        return [TextContent(type="text", text=json.dumps(asdict(result)))]
    # ... more tool implementations

if __name__ == "__main__":
    import asyncio
    asyncio.run(app.run())
```

# README STRUCTURE:
- Overview
- Installation
- Available Tools (with examples)
- Integration with Claude Desktop
- Troubleshooting

# OUTPUT:
Complete MCP server with all tools implemented and documentation
```

---

## 🎯 Prompt 7: Create Integration Tests

```
# CONTEXT:
I have @core/agent_manager.py and need comprehensive tests.

# TASK:
Create tests/test_agent_manager.py with full test coverage.

# REQUIREMENTS:
Test suites for each manager:

1. **Test AgentRegistry**:
   - test_register_agent()
   - test_get_agent_by_id()
   - test_get_agent_by_capability()
   - test_list_agents_with_filters()
   - test_agent_health_check()
   - test_discover_agents()
   - test_registry_persistence()

2. **Test LifecycleManager**:
   - test_initialize_agent()
   - test_shutdown_agent()
   - test_restart_agent()
   - test_pause_resume_agent()
   - test_warm_start()

3. **Test StateManager**:
   - test_get_agent_state()
   - test_update_agent_state()
   - test_persist_and_restore_state()
   - test_workflow_state_tracking()

4. **Test HandoffManager**:
   - test_create_handoff()
   - test_get_handoff_queue()
   - test_complete_handoff()
   - test_validate_handoff()
   - test_retry_failed_handoff()
   - test_priority_sorting()

5. **Test ContextManager**:
   - test_monitor_context_usage()
   - test_trigger_compaction()
   - test_context_zones()
   - test_context_analytics()

6. **Test LearningManager**:
   - test_log_learning()
   - test_get_learnings_with_filters()
   - test_apply_learning()
   - test_identify_patterns()
   - test_learning_persistence()

7. **Test AgentManager (Integration)**:
   - test_bootstrap_swarm()
   - test_create_workflow()
   - test_execute_workflow()
   - test_end_to_end_handoff()
   - test_health_check()

# USE FIXTURES:
```python
@pytest.fixture
def temp_hive_mind(tmp_path):
    """Create temporary .hive-mind directory"""
    hive_mind = tmp_path / ".hive-mind"
    hive_mind.mkdir()
    return str(tmp_path)

@pytest.fixture
def agent_manager(temp_hive_mind):
    """Create AgentManager with temp directory"""
    return AgentManager(base_path=temp_hive_mind)

@pytest.fixture
def sample_learning():
    """Sample learning data"""
    return {
        "reason": "tone_too_aggressive",
        "campaign_id": "camp_123",
        "tier": "tier1"
    }
```

# MOCK EXTERNAL DEPENDENCIES:
- Mock MCP server connections
- Mock file I/O where appropriate
- Use unittest.mock for agent instances

# OUTPUT:
Complete test suite with >80% coverage and all edge cases
```

---

## 🎯 Prompt 8: Create Unified Workflow Examples

```
# CONTEXT:
I have @core/agent_manager.py with workflow capabilities.

Now I need to create practical, production-ready workflows.

# TASK:
Create execution/unified_workflows.py with 4 workflows.

# WORKFLOWS TO IMPLEMENT:

## 1. lead_to_campaign_workflow
**Description**: Complete LinkedIn → Campaign pipeline
**Steps**:
1. hunter.scrape_linkedin(url) → leads
2. revenue_scout.detect_intent(leads) → intent_signals
3. enricher.enrich_data(leads + intent) → enriched_leads
4. segmentor.score_leads(enriched_leads) → scored_leads
5. revenue_coach.predict_conversion(scored_leads) → predicted_leads
6. crafter.rpi_research(predicted_leads) → research
7. crafter.rpi_plan(research) → plan
8. crafter.rpi_implement(plan) → campaigns
9. gatekeeper.queue_review(campaigns) → queued

## 2. real_time_engagement_workflow
**Description**: Respond to website visitors in real-time
**Steps**:
1. revenue_piper.scan_visitor(visitor_id) → visitor_data
2. revenue_scout.detect_intent(visitor_data) → intent
3. revenue_operator.trigger_sequence(visitor + intent) → sequence

## 3. document_enrichment_workflow
**Description**: Extract data from documents to enrich leads
**Steps**:
1. document_parser.parse(pdf_path) → structured_data
2. enricher.enrich_from_document(lead + structured_data) → enriched_lead
3. segmentor.score_lead(enriched_lead) → scored_lead

## 4. self_annealing_workflow
**Description**: Learn from failures and improve
**Steps**:
1. revenue_coach.analyze_failures(time_period) → patterns
2. learning_manager.identify_patterns(patterns) → systematic_issues
3. revenue_coach.suggest_fixes(systematic_issues) → improvements
4. learning_manager.apply_learning(improvements) → updated_directives

# IMPLEMENTATION STRUCTURE:
```python
from core.agent_manager import AgentManager
from typing import Dict, Any, List

am = AgentManager()

def lead_to_campaign_workflow(linkedin_url: str) -> List[Dict]:
    """
    Complete workflow: LinkedIn → Campaign
    
    Args:
        linkedin_url: LinkedIn source (company page, event, etc.)
    
    Returns:
        List of generated campaigns ready for GATEKEEPER
    """
    workflow_id = am.create_workflow(
        name="lead_to_campaign",
        steps=[
            {"agent": "hunter", "action": "scrape_linkedin"},
            {"agent": "revenue_scout", "action": "detect_intent"},
            # ... more steps
        ]
    )
    
    result = am.execute_workflow(
        workflow_id,
        input_data={"linkedin_url": linkedin_url}
    )
    
    return result["output"]["campaigns"]

# ... implement other 3 workflows
```

# REQUIREMENTS:
- Error handling at each step
- Progress logging
- State persistence (can resume if interrupted)
- Type hints and docstrings
- CLI interface for testing

# OUTPUT:
Complete unified_workflows.py with all 4 workflows and CLI
```

---

## 🎯 Prompt 9: Create Agent Manager Dashboard

```
# CONTEXT:
I have @core/agent_manager.py and want a web dashboard to monitor all agents.

# TASK:
Create dashboard/agent_manager_dashboard.py - Flask web app for monitoring.

# REQUIREMENTS:

## Pages:
1. **Home** - System overview
   - Total agents registered
   - Agents running/stopped/error
   - Recent activity
   - System health score

2. **Agents** - Agent list and details
   - Table of all agents
   - Status indicators
   - Quick actions (start/stop/restart)
   - Agent detail view with:
     - Capabilities
     - Dependencies
     - Current state
     - Context usage graph
     - Recent handoffs

3. **Workflows** - Workflow management
   - List of workflows
   - Create new workflow (form)
   - Execute workflow
   - View workflow progress (real-time)
   - Workflow execution history

4. **Learnings** - Learning insights
   - Recent learnings table
   - Pattern detection results
   - Applied vs unapplied learnings
   - Learning analytics graphs

5. **Health** - System health monitoring
   - MCP server status
   - Agent health checks
   - Context usage across agents
   - Error log

## API Endpoints:
```python
@app.route('/api/agents')
def get_agents():
    """Get all agents"""

@app.route('/api/agents/<agent_id>/state')
def get_agent_state(agent_id):
    """Get agent state"""

@app.route('/api/agents/<agent_id>/start', methods=['POST'])
def start_agent(agent_id):
    """Start an agent"""

@app.route('/api/workflows/<workflow_id>/execute', methods=['POST'])
def execute_workflow(workflow_id):
    """Execute workflow"""

# ... more endpoints
```

## Frontend:
- Use Vanilla JS + CSS (no frameworks)
- Real-time updates via polling (every 2 seconds)
- Charts with Chart.js for context/learning analytics
- Responsive design

## Styling:
- Dark mode by default (premium look)
- Use glassmorphism for cards
- Smooth animations
- Color scheme:
  - Background: #0f172a
  - Cards: rgba(30, 41, 59, 0.8)
  - Accent: #3b82f6 (blue)
  - Success: #10b981 (green)
  - Warning: #f59e0b (orange)
  - Error: #ef4444 (red)

# OUTPUT:
Complete Flask app with all pages, API endpoints, and frontend
```

---

## 🎯 Prompt 10: Create Development Utilities

```
# CONTEXT:
I have @core/agent_manager.py and need developer utilities for working with Ampcode.

# TASK:
Create execution/agent_dev_utils.py with development helper functions.

# UTILITIES TO IMPLEMENT:

## 1. Code Generation
```python
def generate_agent_wrapper(agent_id: str, agent_spec: Dict) -> str:
    """
    Generate Python wrapper for new agent
    
    Creates:
    - execution/{agent_id}_agent.py
    - tests/test_{agent_id}_agent.py
    - docs/{agent_id}_README.md
    
    Returns path to generated files
    """

def generate_mcp_tools(server_name: str, tools: List[Dict]) -> str:
    """
    Scaffold new MCP server
    
    Creates:
    - mcp-servers/{server_name}/server.py
    - mcp-servers/{server_name}/README.md
    - mcp-servers/{server_name}/__init__.py
    """

def generate_handoff_validator(from_agent: str, to_agent: str) -> str:
    """
    Create Pydantic schemas for agent handoff validation
    
    Returns Python code as string
    """
```

## 2. Testing Utilities
```python
def create_test_fixtures(agent_id: str, scenario: str = "happy_path") -> Dict:
    """
    Generate test data for agent
    
    Scenarios:
    - happy_path: Ideal inputs
    - edge_cases: Boundary conditions
    - error_cases: Expected failures
    """

def simulate_workflow(workflow_id: str, mock_data: Dict) -> Dict:
    """
    Dry-run workflow without API calls
    
    Uses mock data for each step
    """

def replay_handoff(handoff_id: str, breakpoint_agent: str = None):
    """
    Replay a handoff for debugging
    
    If breakpoint_agent specified, pause at that agent
    """
```

## 3. Documentation Generators
```python
def generate_agent_docs(agent_id: str) -> str:
    """
    Auto-generate markdown docs for agent
    
    Includes:
    - Overview
    - Capabilities
    - API reference
    - Usage examples
    - Configuration
    """

def generate_mermaid_diagrams(scope: str = "all") -> str:
    """
    Generate architecture diagrams
    
    Scopes:
    - all: Complete system
    - agents: Agent dependency graph
    - workflow: Specific workflow
    """

def generate_changelog(since_version: str) -> str:
    """
    Auto-generate CHANGELOG.md from:
    - Git commits
    - Learnings applied
    - Pattern fixes
    """
```

## 4. Debugging Tools
```python
def trace_workflow(workflow_id: str) -> Dict:
    """
    Detailed trace of workflow execution
    
    Returns:
    - Each agent's inputs/outputs
    - Timing per step
    - Context usage
    - Errors
    """

def analyze_failure(event_id: str) -> Dict:
    """
    Root cause analysis for failures
    
    Returns:
    - Error stack trace
    - Agent state at failure
    - Suggested fixes
    - Related learnings
    """

def export_debug_bundle(workflow_id: str) -> str:
    """
    Create debug bundle with:
    - Workflow definition
    - All agent states
    - Handoff data
    - Logs
    - Screenshots (if dashboard)
    
    Returns path to .zip file
    """
```

## 5. Deployment Helpers
```python
def validate_production_readiness() -> Dict:
    """
    Pre-deployment checklist
    
    Checks:
    - All agents healthy
    - Tests passing
    - API credentials configured
    - Rate limits set
    - Monitoring enabled
    """

def create_deployment_package(environment: str = "staging") -> str:
    """
    Create deployment artifact
    
    Includes:
    - Requirements.txt
    - Environment config
    - Migration scripts
    - Rollback plan
    """
```

# OUTPUT:
Complete agent_dev_utils.py with all utilities and examples
```

---

## 📅 Suggested Implementation Order

### Week 1: Core Functionality
1. ✅ Prompt 1: Agent Discovery
2. ✅ Prompt 2: Health Checks
3. ✅ Prompt 4: Workflow System
4. ✅ Prompt 7: Tests (basic)

### Week 2: Intelligence
5. ✅ Prompt 3: Context Monitoring
6. ✅ Prompt 5: Pattern Detection
7. ✅ Prompt 7: Tests (complete)

### Week 3: Integration
8. ✅ Prompt 6: MCP Server
9. ✅ Prompt 8: Unified Workflows
10. ✅ Prompt 10: Dev Utilities

### Week 4: Polish
11. ✅ Prompt 9: Dashboard
12. ✅ Documentation
13. ✅ Production deployment

---

## 💡 Tips for Using These Prompts

### With Cursor/Cursor Composer:
1. Open relevant file first (e.g., `core/agent_manager.py`)
2. Press Cmd/Ctrl+K for inline AI
3. Paste prompt
4. Review changes, iterate if needed
5. Run tests: `pytest tests/test_agent_manager.py -v`

### With Claude Desktop:
1. Reference files with `@filename`
2. Paste prompt
3. Copy generated code to files
4. Test and iterate

### With GitHub Copilot:
1. Leave TODO comments from prompts
2. Let Copilot autocomplete
3. Use Copilot Chat for complex logic

### General Best Practices:
- **One prompt at a time** - Don't try to do everything at once
- **Test after each prompt** - Ensure it works before moving on
- **Commit frequently** - `git commit -am "Implemented {feature}"`
- **Iterate** - First implementation won't be perfect, refine it

---

## 🚀 Quick Start

```bash
# 1. Ensure Agent Manager core exists
python core/agent_manager.py bootstrap

# 2. Pick first prompt (Agent Discovery)
# Copy Prompt 1 into Cursor/Claude

# 3. Test the implementation
python core/agent_manager.py list

# 4. If it works, commit
git add core/agent_manager.py
git commit -m "Implemented agent discovery"

# 5. Move to next prompt
# Repeat for Prompts 2-10
```

---

**Ready to build!** 🚀 Start with Prompt 1 and work your way through systematically.
