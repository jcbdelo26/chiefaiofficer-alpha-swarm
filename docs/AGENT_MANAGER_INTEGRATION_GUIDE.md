# 🎯 Agent Manager Integration Guide
## Unified Revenue Swarm Orchestration & Ampcode Development

**Purpose**: Leverage Agent Manager as the central coordination layer for chiefaiofficer-alpha-swarm + revenue-swarm unification

**Version**: 1.0.0 | **Updated**: 2026-01-16

---

## 🧠 What is Agent Manager?

**Agent Manager** is your **central orchestration and coordination layer** that sits between:
- **Human Intent** (You, the founder)
- **Agent Swarms** (Alpha Swarm + Revenue Swarm)
- **Execution Systems** (MCP servers, Python scripts, APIs)
- **Development Environment** (Ampcode/Cursor AI assistants)

Think of it as your **Chief of Staff for AI Agents** - it manages agent lifecycles, coordinates handoffs, tracks state, and ensures consistency across your unified revenue operations platform.

---

## 🏗️ Agent Manager Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                        AGENT MANAGER CORE                          │
│                  (Master Orchestration Layer)                      │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │   Registry   │  │   Lifecycle  │  │    State     │            │
│  │   Manager    │  │   Manager    │  │   Manager    │            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │   Handoff    │  │   Context    │  │  Learning    │            │
│  │   Manager    │  │   Manager    │  │   Manager    │            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
    ┌─────────┐         ┌─────────┐         ┌─────────┐
    │ Alpha   │         │ Revenue │         │ Ampcode │
    │ Swarm   │         │ Swarm   │         │ Agent   │
    └─────────┘         └─────────┘         └─────────┘
```

---

## 📋 Core Agent Manager Functions

### **1. Registry Manager** - "Who exists and what can they do?"

**Purpose**: Single source of truth for all agents across both swarms

**Functions**:
```python
# Function: register_agent()
# Description: Register a new agent with capabilities
def register_agent(agent_id, agent_type, capabilities, dependencies, mcp_server=None):
    """
    Register an agent in unified registry
    
    Args:
        agent_id: Unique identifier (e.g., "hunter", "scout")
        agent_type: Category (e.g., "sourcing", "enrichment", "orchestration")
        capabilities: List of what agent can do
        dependencies: List of required agents/services
        mcp_server: Associated MCP server path if applicable
    
    Returns:
        Agent registration object
    """
    pass

# Function: get_agent()
# Description: Retrieve agent by ID or capability
def get_agent(agent_id=None, capability=None):
    """Get agent by ID or find agents with specific capability"""
    pass

# Function: list_agents()
# Description: List all registered agents
def list_agents(filter_by_type=None, filter_by_status=None):
    """List agents with optional filters"""
    pass

# Function: agent_health_check()
# Description: Verify agent is operational
def agent_health_check(agent_id):
    """Test if agent and its dependencies are functioning"""
    pass
```

**Ampcode Development Support**:
- Auto-discover agents from both swarms
- Generate agent interface stubs
- Validate agent compatibility before integration
- Create unified agent documentation

---

### **2. Lifecycle Manager** - "When should agents start/stop?"

**Purpose**: Manage agent initialization, running, pausing, and shutdown

**Functions**:
```python
# Function: initialize_agent()
# Description: Start up an agent with proper configuration
def initialize_agent(agent_id, config=None, warm_start=False):
    """
    Initialize agent with dependencies
    
    Args:
        agent_id: Agent to initialize
        config: Override default configuration
        warm_start: Load previous state from .hive-mind
    
    Returns:
        Initialized agent instance
    """
    pass

# Function: shutdown_agent()
# Description: Gracefully stop an agent
def shutdown_agent(agent_id, persist_state=True):
    """Shutdown agent and optionally save state"""
    pass

# Function: restart_agent()
# Description: Restart agent with new configuration
def restart_agent(agent_id, new_config=None):
    """Restart agent (useful for hot-reloading during dev)"""
    pass

# Function: pause_resume_agent()
# Description: Temporarily pause agent operations
def pause_resume_agent(agent_id, action="pause"):
    """Pause or resume agent for maintenance"""
    pass

# Function: agent_status()
# Description: Get current agent lifecycle status
def agent_status(agent_id):
    """Returns: initializing, running, paused, stopped, error"""
    pass
```

**Ampcode Development Support**:
- Hot-reload agents during development without full restart
- Test agent initialization sequences
- Debug startup failures with detailed logs
- Manage development vs. production configurations

---

### **3. State Manager** - "What's happening right now?"

**Purpose**: Track agent state, work queues, and data flow across swarms

**Functions**:
```python
# Function: get_agent_state()
# Description: Retrieve current agent state
def get_agent_state(agent_id):
    """
    Get agent's current operational state
    
    Returns:
        {
            "status": "running",
            "current_task": "enriching_leads",
            "queue_size": 15,
            "last_activity": "2026-01-16T03:42:30Z",
            "memory_usage": "245MB",
            "context_window_used": "38%"
        }
    """
    pass

# Function: update_agent_state()
# Description: Update agent state
def update_agent_state(agent_id, new_state):
    """Agent reports state changes"""
    pass

# Function: get_workflow_state()
# Description: Track multi-agent workflow progress
def get_workflow_state(workflow_id):
    """
    Returns workflow progress across agents
    
    Example: lead_to_campaign_workflow
    {
        "hunter": "complete",
        "enricher": "running",
        "segmentor": "queued",
        "crafter": "pending",
        "gatekeeper": "pending"
    }
    """
    pass

# Function: persist_state()
# Description: Save state to .hive-mind for recovery
def persist_state(agent_id, state_data):
    """Save to .hive-mind/state/{agent_id}_state.json"""
    pass

# Function: restore_state()
# Description: Restore agent state from .hive-mind
def restore_state(agent_id):
    """Load state from .hive-mind for warm start"""
    pass
```

**Ampcode Development Support**:
- Real-time monitoring dashboard for all agents
- State snapshots for debugging
- Workflow progress visualization
- Rollback to previous states during testing

---

### **4. Handoff Manager** - "How do agents work together?"

**Purpose**: Coordinate data flow and task handoffs between agents (critical for swarm unification!)

**Functions**:
```python
# Function: create_handoff()
# Description: Transfer work from one agent to another
def create_handoff(from_agent, to_agent, data, priority="normal"):
    """
    Create handoff between agents
    
    Args:
        from_agent: Source agent ID
        to_agent: Destination agent ID
        data: Data payload to transfer
        priority: urgent, high, normal, low
    
    Returns:
        Handoff ticket ID for tracking
    """
    pass

# Function: get_handoff_queue()
# Description: Check pending handoffs for an agent
def get_handoff_queue(agent_id):
    """Get all pending work for this agent"""
    pass

# Function: complete_handoff()
# Description: Mark handoff as complete
def complete_handoff(handoff_id, output_data=None):
    """Agent reports handoff completion"""
    pass

# Function: validate_handoff()
# Description: Check if handoff is compatible
def validate_handoff(from_agent, to_agent, data_schema):
    """
    Validate handoff before creation
    
    Returns:
        {
            "valid": True,
            "warnings": ["enricher prefers 'company_name' field"],
            "required_transforms": ["normalize_linkedin_url"]
        }
    """
    pass

# Function: retry_failed_handoff()
# Description: Retry a failed handoff with fixes
def retry_failed_handoff(handoff_id, retry_config=None):
    """Retry failed handoff with optional config changes"""
    pass
```

**Ampcode Development Support**:
- Visualize agent dependency graphs
- Test handoff schemas before deployment
- Auto-generate handoff validation code
- Simulate workflows without real API calls

---

### **5. Context Manager** - "Keep agents in the Smart Zone"

**Purpose**: Implement FIC (Frequent Intentional Compaction) across all agents

**Functions**:
```python
# Function: monitor_context_usage()
# Description: Track agent's context window usage
def monitor_context_usage(agent_id):
    """
    Monitor context window percentage
    
    Returns:
        {
            "agent_id": "crafter",
            "context_used": "42%",
            "zone": "smart",  # smart, warning, dumb
            "recommendation": "compact_research"
        }
    """
    pass

# Function: trigger_compaction()
# Description: Force context compaction
def trigger_compaction(agent_id, strategy="rpi"):
    """
    Strategies:
    - "rpi": Research → Plan → Implement
    - "semantic_anchor": Extract WHY/WHAT/HOW
    - "summarize": Progressive summarization
    - "checkpoint": Save state and restart fresh
    """
    pass

# Function: create_context_checkpoint()
# Description: Save current context as checkpoint
def create_context_checkpoint(agent_id, checkpoint_name):
    """Save context state for later restoration"""
    pass

# Function: get_context_analytics()
# Description: Analyze context usage patterns
def get_context_analytics(agent_id, time_period="7d"):
    """
    Returns context usage trends:
    - Average context usage per workflow
    - Compaction frequency
    - Context-related failures
    - Optimization opportunities
    """
    pass
```

**Ampcode Development Support**:
- Real-time context monitoring during development
- Test context compaction strategies
- Identify context bottlenecks in workflows
- Generate context optimization reports

---

### **6. Learning Manager** - "How do we get smarter?"

**Purpose**: Centralize self-annealing and continuous improvement

**Functions**:
```python
# Function: log_learning()
# Description: Record a learning event
def log_learning(source_agent, event_type, learning_data):
    """
    Record learning event
    
    Example:
        log_learning(
            source_agent="gatekeeper",
            event_type="campaign_rejection",
            learning_data={
                "reason": "tone_too_aggressive",
                "campaign_id": "camp_123",
                "tier": "tier1",
                "template_used": "competitor_attack"
            }
        )
    """
    pass

# Function: get_learnings()
# Description: Retrieve learnings by filter
def get_learnings(agent_id=None, event_type=None, time_period="30d"):
    """Query learning database"""
    pass

# Function: apply_learning()
# Description: Apply learning to directive/configuration
def apply_learning(learning_id, target_directive=None):
    """
    Apply learning to system
    
    Actions:
    - Update directive with new rule
    - Modify agent configuration
    - Add validation check
    - Update training data
    """
    pass

# Function: identify_patterns()
# Description: Analyze learnings for patterns
def identify_patterns(event_type=None, min_occurrences=3):
    """
    Find recurring issues
    
    Returns:
        [
            {
                "pattern": "tier1_leads_reject_price_focus",
                "occurrences": 7,
                "suggested_fix": "add_value_prop_emphasis",
                "confidence": 0.85
            }
        ]
    """
    pass

# Function: suggest_improvements()
# Description: AI-generated improvement suggestions
def suggest_improvements(agent_id=None):
    """Analyze learnings and suggest system improvements"""
    pass
```

**Ampcode Development Support**:
- Auto-generate improvement tasks from learnings
- Test learning application before production
- Visualize learning trends over time
- Export learnings for AI training

---

## 🚀 Agent Manager for Swarm Unification

### **Integration Workflow**

#### **Step 1: Discovery & Registration**

```python
# Use Agent Manager to discover both swarms
from agent_manager import AgentManager

am = AgentManager()

# Discover Alpha Swarm agents
am.discover_agents(path="./execution", prefix="alpha_")
# Discovers: hunter, enricher, segmentor, crafter, gatekeeper

# Discover Revenue Swarm agents
am.discover_agents(path="./revenue_coordination", prefix="revenue_")
# Discovers: scout, operator, piper, coach, queen

# View unified registry
all_agents = am.list_agents()
print(f"Total agents registered: {len(all_agents)}")
```

#### **Step 2: Dependency Mapping**

```python
# Map cross-swarm dependencies
am.map_dependencies()

# Returns:
# {
#     "hunter": ["enricher"],  # Alpha to Alpha
#     "scout": ["operator"],   # Revenue to Revenue
#     "enricher": ["scout"],   # Alpha to Revenue (NEW!)
#     "piper": ["segmentor"]   # Revenue to Alpha (NEW!)
# }
```

#### **Step 3: Workflow Creation**

```python
# Create unified workflow
workflow_id = am.create_workflow(
    name="lead_to_campaign_unified",
    steps=[
        {"agent": "hunter", "action": "scrape_linkedin"},
        {"agent": "scout", "action": "detect_intent"},      # Cross-swarm!
        {"agent": "enricher", "action": "enrich_data"},
        {"agent": "piper", "action": "scan_visitor"},       # Cross-swarm!
        {"agent": "segmentor", "action": "score_lead"},
        {"agent": "coach", "action": "predict_conversion"}, # Cross-swarm!
        {"agent": "crafter", "action": "generate_campaign"},
        {"agent": "gatekeeper", "action": "queue_review"}
    ]
)

# Execute workflow
am.execute_workflow(workflow_id, input_data={"linkedin_url": "..."})

# Monitor progress
status = am.get_workflow_state(workflow_id)
```

---

## 🔧 Ampcode Development Functions

### **Function Suite for AI-Assisted Development**

#### **1. Code Generation Functions**

```python
# Function: generate_agent_wrapper()
# Description: Auto-generate agent wrapper code
def generate_agent_wrapper(agent_id, agent_spec):
    """
    Generate Python wrapper for agent
    
    Input:
        agent_spec = {
            "type": "enrichment",
            "apis": ["clay", "rb2b"],
            "inputs": ["lead_data"],
            "outputs": ["enriched_lead"],
            "mcp_server": "./mcp-servers/enricher-mcp"
        }
    
    Output:
        - execution/{agent_id}_wrapper.py
        - tests/test_{agent_id}_wrapper.py
        - docs/{agent_id}_API.md
    """
    pass

# Function: generate_handoff_validator()
# Description: Create validation code for agent handoffs
def generate_handoff_validator(from_agent, to_agent):
    """Generate Pydantic schemas + validation logic"""
    pass

# Function: generate_mcp_tools()
# Description: Scaffold new MCP server tools
def generate_mcp_tools(tool_spec):
    """
    Create MCP server tools from spec
    
    Example:
        tool_spec = {
            "server_name": "revenue-orchestrator-mcp",
            "tools": [
                {
                    "name": "coordinate_campaign",
                    "description": "Coordinate multi-agent campaign",
                    "parameters": {...}
                }
            ]
        }
    """
    pass
```

#### **2. Testing Functions**

```python
# Function: generate_integration_tests()
# Description: Auto-generate test suites
def generate_integration_tests(workflow_id):
    """
    Create pytest suite for workflow
    
    Generates:
    - Unit tests for each step
    - Integration test for full workflow
    - Mock data fixtures
    - Performance benchmarks
    """
    pass

# Function: create_test_fixtures()
# Description: Generate test data
def create_test_fixtures(agent_id, scenario="happy_path"):
    """
    Scenarios:
    - happy_path: Ideal inputs
    - edge_cases: Boundary conditions
    - error_cases: Expected failures
    - performance: Large datasets
    """
    pass

# Function: simulate_workflow()
# Description: Dry-run workflow without API calls
def simulate_workflow(workflow_id, mock_data):
    """Test workflow logic without external dependencies"""
    pass
```

#### **3. Documentation Functions**

```python
# Function: generate_agent_docs()
# Description: Auto-generate documentation
def generate_agent_docs(agent_id):
    """
    Create comprehensive docs:
    - README.md with usage examples
    - API reference
    - Configuration options
    - Troubleshooting guide
    """
    pass

# Function: generate_mermaid_diagrams()
# Description: Visualize agent architecture
def generate_mermaid_diagrams(scope="all"):
    """
    Generate diagrams:
    - Agent dependency graph
    - Workflow sequence diagrams
    - State machine diagrams
    - Data flow diagrams
    """
    pass

# Function: generate_changelog()
# Description: Auto-generate changelog from learnings
def generate_changelog(since_version="1.0.0"):
    """Create changelog from git commits + learnings"""
    pass
```

#### **4. Debugging Functions**

```python
# Function: trace_workflow()
# Description: Debug workflow execution
def trace_workflow(workflow_id):
    """
    Detailed trace:
    - Each agent's inputs/outputs
    - Timing per step
    - Context usage
    - Errors and warnings
    """
    pass

# Function: replay_handoff()
# Description: Replay failed handoff for debugging
def replay_handoff(handoff_id, breakpoint_agent=None):
    """Step through handoff with debugger"""
    pass

# Function: analyze_failure()
# Description: Root cause analysis for failures
def analyze_failure(event_id):
    """
    Returns:
    - Error stack trace
    - Agent state at failure
    - Suggested fixes
    - Related learnings
    """
    pass
```

#### **5. Deployment Functions**

```python
# Function: validate_production_readiness()
# Description: Pre-deployment validation
def validate_production_readiness():
    """
    Checks:
    - All agents healthy
    - Tests passing
    - API credentials configured
    - Rate limits configured
    - Monitoring enabled
    """
    pass

# Function: create_deployment_package()
# Description: Package for deployment
def create_deployment_package(environment="staging"):
    """
    Create deployment artifact:
    - Docker containers
    - Environment configs
    - Migration scripts
    - Rollback plan
    """
    pass

# Function: health_dashboard()
# Description: Live monitoring dashboard
def health_dashboard():
    """
    Launch dashboard showing:
    - Agent status
    - Workflow progress
    - Error rates
    - Performance metrics
    """
    pass
```

---

## 📊 Ampcode Prompts for Agent Manager Development

### **Prompt 1: Create Agent Manager Core**

```
# Task: Create Agent Manager Core Module

## Context:
I have two agent swarms (Alpha + Revenue) that need unified orchestration.
I need an Agent Manager to coordinate them.

## Requirements:
Create: core/agent_manager.py

Implement these classes:
1. AgentRegistry - Track all agents
2. LifecycleManager - Start/stop agents
3. StateManager - Track agent state
4. HandoffManager - Coordinate handoffs
5. ContextManager - Monitor context usage
6. LearningManager - Track improvements

## Reference Files:
@chiefaiofficer-alpha-swarm/docs/AGENT_MANAGER_INTEGRATION_GUIDE.md
@chiefaiofficer-alpha-swarm/core/context.py
@chiefaiofficer-alpha-swarm/.hive-mind/learnings.json

## Expected Output:
Complete agent_manager.py with:
- All 6 manager classes
- Type hints
- Docstrings
- Error handling
- Logging
- Unit tests in tests/test_agent_manager.py
```

### **Prompt 2: Create MCP Server for Agent Manager**

```
# Task: Create Agent Manager MCP Server

## Context:
I need to expose Agent Manager functions via MCP for use in workflows.

## Requirements:
Create: mcp-servers/agent-manager-mcp/

Implement MCP tools:
- register_agent
- initialize_agent
- create_handoff
- monitor_context
- log_learning
- execute_workflow

Reference the function signatures in:
@chiefaiofficer-alpha-swarm/docs/AGENT_MANAGER_INTEGRATION_GUIDE.md

## Expected Output:
- mcp-servers/agent-manager-mcp/server.py
- mcp-servers/agent-manager-mcp/README.md
- Test script: tests/test_agent_manager_mcp.py
```

### **Prompt 3: Create Unified Workflow Orchestrator**

```
# Task: Create Unified Workflow Orchestrator

## Context:
I have Agent Manager implemented. Now create workflows combining both swarms.

## Requirements:
Create: execution/unified_workflows.py

Implement workflows:
1. lead_to_campaign_unified - Full pipeline
2. real_time_engagement - PIPER → SCOUT → OPERATOR
3. document_enrichment - DOC_PARSER → ENRICHER → SEGMENTOR
4. self_annealing - COACH → LEARNING_MANAGER

Use Agent Manager for all orchestration.

## Reference:
@core/agent_manager.py
@docs/AGENT_MANAGER_INTEGRATION_GUIDE.md
@execution/rpi_plan.py

## Expected Output:
Complete unified_workflows.py with all 4 workflows using Agent Manager
```

---

## 🎯 Implementation Roadmap

### **Week 1: Core Infrastructure**
- [ ] Create `core/agent_manager.py` with 6 manager classes
- [ ] Create `mcp-servers/agent-manager-mcp/` server
- [ ] Implement agent discovery for both swarms
- [ ] Create unified registry in `.hive-mind/registry.json`

### **Week 2: Workflows**
- [ ] Implement `create_workflow()` function
- [ ] Create 4 unified workflows
- [ ] Add workflow monitoring dashboard
- [ ] Test cross-swarm handoffs

### **Week 3: Ampcode Integration**
- [ ] Implement code generation functions
- [ ] Create testing automation
- [ ] Build debugging tools
- [ ] Generate documentation

### **Week 4: Production**
- [ ] Validate production readiness
- [ ] Deploy to staging
- [ ] Performance testing
- [ ] Launch monitoring dashboard

---

## 💡 Key Benefits for Your Use Case

### **For Swarm Unification:**
1. **Single Control Point**: Manage all agents from Agent Manager
2. **Dependency Resolution**: Automatically handle cross-swarm dependencies
3. **State Synchronization**: Keep both swarms in sync
4. **Unified Monitoring**: Single dashboard for all agents

### **For Ampcode Development:**
1. **Hot Reloading**: Test agents without full restart
2. **Auto-Generated Code**: Scaffolding for new agents/tools
3. **Test Automation**: Generate tests from specifications
4. **Documentation**: Auto-generate docs from code

### **For Daily Operations:**
1. **Workflow Templates**: Pre-built revenue workflows
2. **Error Recovery**: Automatic retry and fallback
3. **Performance Optimization**: Context monitoring prevents degradation
4. **Continuous Learning**: System improves from every execution

---

## 📚 Next Steps

1. **Read**: `AI_ASSISTED_INTEGRATION_GUIDE.md` - Ampcode strategies
2. **Create**: Use Prompt 1 above to generate Agent Manager core
3. **Test**: Run agent discovery on both swarms
4. **Integrate**: Build first unified workflow
5. **Monitor**: Launch health dashboard
6. **Iterate**: Use learnings to improve system

---

## 📞 Questions to Consider

1. **Which workflows are highest priority for unification?**
   - Lead harvesting (HUNTER → SCOUT → ENRICHER)?
   - Real-time engagement (PIPER → OPERATOR)?
   - Campaign creation (CRAFTER with COACH predictions)?

2. **What are your most common failures/bottlenecks?**
   - This will guide which Agent Manager functions to prioritize

3. **How do you want to use Ampcode?**
   - More code generation vs. more debugging tools?
   - Interactive development vs. automated testing?

4. **What's your deployment target?**
   - Local development vs. cloud production?
   - This affects State Manager implementation

---

**Built to unify** 🕵️ **Alpha Swarm** + 💰 **Revenue Swarm** = 🚀 **Unified Revenue Platform**
