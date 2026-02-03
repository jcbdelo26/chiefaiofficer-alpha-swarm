"""
Agent Manager - Central Orchestration Layer
Unified coordination for chiefaiofficer-alpha-swarm + revenue-swarm

Author: Chris Daigle (Chiefaiofficer.com)
Version: 1.0.0
Date: 2026-01-16
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Literal
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# DATA MODELS
# ============================================================================

class AgentStatus(str, Enum):
    """Agent lifecycle status"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class ContextZone(str, Enum):
    """Context window usage zones (FIC methodology)"""
    SMART = "smart"      # < 40% - Optimal
    WARNING = "warning"  # 40-70% - Approaching limit
    DUMB = "dumb"        # > 70% - Degraded performance


class HandoffPriority(str, Enum):
    """Handoff priority levels"""
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class AgentMetadata:
    """Agent registration metadata"""
    agent_id: str
    agent_type: str
    capabilities: List[str]
    dependencies: List[str]
    mcp_server: Optional[str] = None
    status: AgentStatus = AgentStatus.STOPPED
    registered_at: str = None
    
    def __post_init__(self):
        if self.registered_at is None:
            self.registered_at = datetime.utcnow().isoformat()


@dataclass
class AgentState:
    """Runtime agent state"""
    agent_id: str
    status: AgentStatus
    current_task: Optional[str] = None
    queue_size: int = 0
    last_activity: str = None
    memory_usage: str = "0MB"
    context_window_used: str = "0%"
    
    def __post_init__(self):
        if self.last_activity is None:
            self.last_activity = datetime.utcnow().isoformat()


@dataclass
class Handoff:
    """Agent-to-agent handoff"""
    handoff_id: str
    from_agent: str
    to_agent: str
    data: Dict[str, Any]
    priority: HandoffPriority = HandoffPriority.NORMAL
    status: str = "pending"
    created_at: str = None
    completed_at: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()


@dataclass
class Learning:
    """Self-annealing learning event"""
    learning_id: str
    source_agent: str
    event_type: str
    learning_data: Dict[str, Any]
    timestamp: str = None
    applied: bool = False
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


# ============================================================================
# 1. REGISTRY MANAGER
# ============================================================================

class AgentRegistry:
    """Manages agent registration and discovery"""
    
    def __init__(self, registry_path: str = "./.hive-mind/registry.json"):
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.agents: Dict[str, AgentMetadata] = {}
        self._load_registry()
    
    def _load_registry(self):
        """Load existing registry from disk"""
        if self.registry_path.exists():
            with open(self.registry_path, 'r') as f:
                data = json.load(f)
                self.agents = {
                    k: AgentMetadata(**v) for k, v in data.items()
                }
                logger.info(f"Loaded {len(self.agents)} agents from registry")
    
    def _save_registry(self):
        """Persist registry to disk"""
        with open(self.registry_path, 'w') as f:
            json.dump(
                {k: asdict(v) for k, v in self.agents.items()},
                f,
                indent=2
            )
    
    def register_agent(
        self,
        agent_id: str,
        agent_type: str,
        capabilities: List[str],
        dependencies: List[str],
        mcp_server: Optional[str] = None
    ) -> AgentMetadata:
        """
        Register a new agent
        
        Args:
            agent_id: Unique identifier (e.g., "hunter", "scout")
            agent_type: Category (e.g., "sourcing", "enrichment")
            capabilities: List of what agent can do
            dependencies: List of required agents/services
            mcp_server: Associated MCP server path
        
        Returns:
            AgentMetadata object
        """
        metadata = AgentMetadata(
            agent_id=agent_id,
            agent_type=agent_type,
            capabilities=capabilities,
            dependencies=dependencies,
            mcp_server=mcp_server
        )
        
        self.agents[agent_id] = metadata
        self._save_registry()
        
        logger.info(f"Registered agent: {agent_id} ({agent_type})")
        return metadata
    
    def get_agent(
        self,
        agent_id: Optional[str] = None,
        capability: Optional[str] = None
    ) -> Optional[AgentMetadata]:
        """
        Get agent by ID or capability
        
        Args:
            agent_id: Agent ID to retrieve
            capability: Find agent with this capability
        
        Returns:
            AgentMetadata or None
        """
        if agent_id:
            return self.agents.get(agent_id)
        
        if capability:
            for agent in self.agents.values():
                if capability in agent.capabilities:
                    return agent
        
        return None
    
    def list_agents(
        self,
        filter_by_type: Optional[str] = None,
        filter_by_status: Optional[AgentStatus] = None
    ) -> List[AgentMetadata]:
        """
        List all registered agents with optional filters
        
        Args:
            filter_by_type: Filter by agent type
            filter_by_status: Filter by status
        
        Returns:
            List of AgentMetadata
        """
        agents = list(self.agents.values())
        
        if filter_by_type:
            agents = [a for a in agents if a.agent_type == filter_by_type]
        
        if filter_by_status:
            agents = [a for a in agents if a.status == filter_by_status]
        
        return agents
    
    def agent_health_check(self, agent_id: str) -> Dict[str, Any]:
        """
        Test if agent and dependencies are functioning
        
        Args:
            agent_id: Agent to check
        
        Returns:
            Health check results
        """
        agent = self.get_agent(agent_id=agent_id)
        if not agent:
            return {"healthy": False, "error": "Agent not found"}
        
        # TODO: Implement actual health checks
        # - Check if MCP server is running
        # - Check if dependencies are available
        # - Test basic agent functionality
        
        return {
            "healthy": True,
            "agent_id": agent_id,
            "status": agent.status,
            "dependencies_ok": True,
            "mcp_server_ok": agent.mcp_server is not None
        }
    
    def discover_agents(
        self,
        path: str,
        prefix: str = "",
        auto_register: bool = True
    ) -> List[str]:
        """
        Discover agents from directory structure
        
        Args:
            path: Directory to scan
            prefix: Prefix for agent IDs
            auto_register: Automatically register discovered agents
        
        Returns:
            List of discovered agent IDs
        """
        # TODO: Implement agent discovery
        # - Scan path for Python files
        # - Extract agent metadata from docstrings
        # - Auto-register if enabled
        
        logger.info(f"Discovering agents in {path} with prefix '{prefix}'")
        discovered = []
        
        # Placeholder implementation
        return discovered


# ============================================================================
# 2. LIFECYCLE MANAGER
# ============================================================================

class LifecycleManager:
    """Manages agent initialization, running, pausing, shutdown"""
    
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.active_agents: Dict[str, Any] = {}
    
    def initialize_agent(
        self,
        agent_id: str,
        config: Optional[Dict] = None,
        warm_start: bool = False
    ) -> Any:
        """
        Initialize agent with dependencies
        
        Args:
            agent_id: Agent to initialize
            config: Override default configuration
            warm_start: Load previous state from .hive-mind
        
        Returns:
            Initialized agent instance
        """
        metadata = self.registry.get_agent(agent_id=agent_id)
        if not metadata:
            raise ValueError(f"Agent {agent_id} not registered")
        
        logger.info(f"Initializing agent: {agent_id}")
        
        # TODO: Implement agent initialization
        # - Load configuration
        # - Initialize dependencies
        # - Restore state if warm_start
        # - Update registry status
        
        metadata.status = AgentStatus.RUNNING
        self.registry._save_registry()
        
        return None  # Placeholder
    
    def shutdown_agent(
        self,
        agent_id: str,
        persist_state: bool = True
    ):
        """
        Gracefully stop an agent
        
        Args:
            agent_id: Agent to shutdown
            persist_state: Save state to .hive-mind
        """
        metadata = self.registry.get_agent(agent_id=agent_id)
        if not metadata:
            raise ValueError(f"Agent {agent_id} not registered")
        
        logger.info(f"Shutting down agent: {agent_id}")
        
        # TODO: Implement shutdown
        # - Save state if persist_state
        # - Clean up resources
        # - Update registry status
        
        metadata.status = AgentStatus.STOPPED
        self.registry._save_registry()
    
    def restart_agent(
        self,
        agent_id: str,
        new_config: Optional[Dict] = None
    ):
        """
        Restart agent with new configuration
        
        Useful for hot-reloading during development
        """
        self.shutdown_agent(agent_id, persist_state=True)
        return self.initialize_agent(agent_id, config=new_config, warm_start=True)
    
    def pause_resume_agent(
        self,
        agent_id: str,
        action: Literal["pause", "resume"]
    ):
        """
        Pause or resume agent operations
        
        Useful for maintenance windows
        """
        metadata = self.registry.get_agent(agent_id=agent_id)
        if not metadata:
            raise ValueError(f"Agent {agent_id} not registered")
        
        if action == "pause":
            metadata.status = AgentStatus.PAUSED
            logger.info(f"Paused agent: {agent_id}")
        else:
            metadata.status = AgentStatus.RUNNING
            logger.info(f"Resumed agent: {agent_id}")
        
        self.registry._save_registry()
    
    def agent_status(self, agent_id: str) -> AgentStatus:
        """
        Get current agent lifecycle status
        
        Returns: initializing, running, paused, stopped, error
        """
        metadata = self.registry.get_agent(agent_id=agent_id)
        if not metadata:
            raise ValueError(f"Agent {agent_id} not registered")
        
        return metadata.status


# ============================================================================
# 3. STATE MANAGER
# ============================================================================

class StateManager:
    """Tracks agent state, work queues, and data flow"""
    
    def __init__(self, state_dir: str = "./.hive-mind/state"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.agent_states: Dict[str, AgentState] = {}
    
    def get_agent_state(self, agent_id: str) -> Optional[AgentState]:
        """
        Get agent's current operational state
        
        Returns detailed state including queue size, context usage, etc.
        """
        return self.agent_states.get(agent_id)
    
    def update_agent_state(self, agent_id: str, new_state: AgentState):
        """
        Update agent state (called by agents themselves)
        """
        self.agent_states[agent_id] = new_state
        self.persist_state(agent_id, asdict(new_state))
    
    def get_workflow_state(self, workflow_id: str) -> Dict[str, str]:
        """
        Track multi-agent workflow progress
        
        Returns progress for each agent in workflow
        """
        # TODO: Implement workflow state tracking
        # - Load workflow definition
        # - Check each agent's progress
        # - Return status map
        
        return {}
    
    def persist_state(self, agent_id: str, state_data: Dict[str, Any]):
        """
        Save state to .hive-mind for recovery
        """
        state_file = self.state_dir / f"{agent_id}_state.json"
        with open(state_file, 'w') as f:
            json.dump(state_data, f, indent=2)
    
    def restore_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Restore agent state from .hive-mind
        
        Used for warm starts after restarts
        """
        state_file = self.state_dir / f"{agent_id}_state.json"
        if not state_file.exists():
            return None
        
        with open(state_file, 'r') as f:
            return json.load(f)


# ============================================================================
# 4. HANDOFF MANAGER
# ============================================================================

class HandoffManager:
    """Coordinates data flow and task handoffs between agents"""
    
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.handoffs: Dict[str, Handoff] = {}
        self.handoff_counter = 0
    
    def create_handoff(
        self,
        from_agent: str,
        to_agent: str,
        data: Dict[str, Any],
        priority: HandoffPriority = HandoffPriority.NORMAL
    ) -> str:
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
        # Validate agents exist
        if not self.registry.get_agent(agent_id=from_agent):
            raise ValueError(f"Source agent {from_agent} not registered")
        if not self.registry.get_agent(agent_id=to_agent):
            raise ValueError(f"Destination agent {to_agent} not registered")
        
        self.handoff_counter += 1
        handoff_id = f"handoff_{self.handoff_counter}_{from_agent}_to_{to_agent}"
        
        handoff = Handoff(
            handoff_id=handoff_id,
            from_agent=from_agent,
            to_agent=to_agent,
            data=data,
            priority=priority
        )
        
        self.handoffs[handoff_id] = handoff
        logger.info(f"Created handoff: {handoff_id} ({priority})")
        
        return handoff_id
    
    def get_handoff_queue(self, agent_id: str) -> List[Handoff]:
        """
        Get all pending handoffs for an agent
        
        Returns sorted by priority (urgent first)
        """
        pending = [
            h for h in self.handoffs.values()
            if h.to_agent == agent_id and h.status == "pending"
        ]
        
        # Sort by priority
        priority_order = {p: i for i, p in enumerate(HandoffPriority)}
        pending.sort(key=lambda h: priority_order[h.priority])
        
        return pending
    
    def complete_handoff(
        self,
        handoff_id: str,
        output_data: Optional[Dict[str, Any]] = None
    ):
        """
        Mark handoff as complete
        
        Args:
            handoff_id: Handoff to complete
            output_data: Optional output from processing
        """
        handoff = self.handoffs.get(handoff_id)
        if not handoff:
            raise ValueError(f"Handoff {handoff_id} not found")
        
        handoff.status = "completed"
        handoff.completed_at = datetime.utcnow().isoformat()
        
        logger.info(f"Completed handoff: {handoff_id}")
    
    def validate_handoff(
        self,
        from_agent: str,
        to_agent: str,
        data_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate handoff before creation
        
        Checks schema compatibility, required fields, etc.
        
        Returns validation results with warnings and required transforms
        """
        # TODO: Implement schema validation
        # - Check if to_agent can accept data format
        # - Identify missing required fields
        # - Suggest data transformations
        
        return {
            "valid": True,
            "warnings": [],
            "required_transforms": []
        }
    
    def retry_failed_handoff(
        self,
        handoff_id: str,
        retry_config: Optional[Dict] = None
    ):
        """
        Retry a failed handoff with optional config changes
        """
        handoff = self.handoffs.get(handoff_id)
        if not handoff:
            raise ValueError(f"Handoff {handoff_id} not found")
        
        # Reset status
        handoff.status = "pending"
        handoff.completed_at = None
        
        logger.info(f"Retrying handoff: {handoff_id}")


# ============================================================================
# 5. CONTEXT MANAGER
# ============================================================================

class ContextManager:
    """Implements FIC (Frequent Intentional Compaction)"""
    
    def monitor_context_usage(self, agent_id: str) -> Dict[str, Any]:
        """
        Monitor agent's context window usage
        
        Returns current usage, zone, and recommendations
        """
        # TODO: Implement context monitoring
        # - Query agent for current context size
        # - Calculate percentage used
        # - Determine zone (smart/warning/dumb)
        # - Suggest compaction strategy if needed
        
        return {
            "agent_id": agent_id,
            "context_used": "0%",
            "zone": ContextZone.SMART,
            "recommendation": None
        }
    
    def trigger_compaction(
        self,
        agent_id: str,
        strategy: Literal["rpi", "semantic_anchor", "summarize", "checkpoint"] = "rpi"
    ):
        """
        Force context compaction using specified strategy
        
        Strategies:
        - rpi: Research → Plan → Implement
        - semantic_anchor: Extract WHY/WHAT/HOW
        - summarize: Progressive summarization
        - checkpoint: Save state and restart fresh
        """
        logger.info(f"Triggering {strategy} compaction for {agent_id}")
        
        # TODO: Implement compaction strategies
        # - Execute appropriate compaction method
        # - Verify context reduction
        # - Log results
    
    def create_context_checkpoint(
        self,
        agent_id: str,
        checkpoint_name: str
    ):
        """
        Save current context as checkpoint
        
        Allows restoration later if needed
        """
        # TODO: Implement checkpoint creation
        # - Save current context state
        # - Tag with checkpoint_name
        # - Store in .hive-mind/checkpoints/
        
        logger.info(f"Created checkpoint '{checkpoint_name}' for {agent_id}")
    
    def get_context_analytics(
        self,
        agent_id: str,
        time_period: str = "7d"
    ) -> Dict[str, Any]:
        """
        Analyze context usage patterns
        
        Returns trends and optimization opportunities
        """
        # TODO: Implement analytics
        # - Load historical context usage
        # - Calculate averages and trends
        # - Identify patterns
        # - Suggest optimizations
        
        return {
            "agent_id": agent_id,
            "period": time_period,
            "avg_context_usage": "35%",
            "compaction_frequency": "2.5 per day",
            "context_failures": 0,
            "optimizations": []
        }


# ============================================================================
# 6. LEARNING MANAGER
# ============================================================================

class LearningManager:
    """Centralizes self-annealing and continuous improvement"""
    
    def __init__(self, learnings_path: str = "./.hive-mind/learnings.json"):
        self.learnings_path = Path(learnings_path)
        self.learnings_path.parent.mkdir(parents=True, exist_ok=True)
        self.learnings: List[Learning] = []
        self.learning_counter = 0
        self._load_learnings()
    
    def _load_learnings(self):
        """Load existing learnings from disk"""
        if self.learnings_path.exists():
            with open(self.learnings_path, 'r') as f:
                data = json.load(f)
                self.learnings = [Learning(**item) for item in data]
                self.learning_counter = len(self.learnings)
                logger.info(f"Loaded {len(self.learnings)} learnings")
    
    def _save_learnings(self):
        """Persist learnings to disk"""
        with open(self.learnings_path, 'w') as f:
            json.dump(
                [asdict(l) for l in self.learnings],
                f,
                indent=2
            )
    
    def log_learning(
        self,
        source_agent: str,
        event_type: str,
        learning_data: Dict[str, Any]
    ) -> str:
        """
        Record a learning event
        
        Args:
            source_agent: Agent that generated the learning
            event_type: Type of event (e.g., "campaign_rejection")
            learning_data: Details of the learning
        
        Returns:
            Learning ID
        """
        self.learning_counter += 1
        learning_id = f"learning_{self.learning_counter}_{source_agent}"
        
        learning = Learning(
            learning_id=learning_id,
            source_agent=source_agent,
            event_type=event_type,
            learning_data=learning_data
        )
        
        self.learnings.append(learning)
        self._save_learnings()
        
        logger.info(f"Logged learning: {learning_id} ({event_type})")
        return learning_id
    
    def get_learnings(
        self,
        agent_id: Optional[str] = None,
        event_type: Optional[str] = None,
        time_period: str = "30d"
    ) -> List[Learning]:
        """
        Query learning database
        
        Filter by agent, event type, and time period
        """
        filtered = self.learnings
        
        if agent_id:
            filtered = [l for l in filtered if l.source_agent == agent_id]
        
        if event_type:
            filtered = [l for l in filtered if l.event_type == event_type]
        
        # TODO: Implement time period filtering
        
        return filtered
    
    def apply_learning(
        self,
        learning_id: str,
        target_directive: Optional[str] = None
    ):
        """
        Apply learning to system
        
        Actions:
        - Update directive with new rule
        - Modify agent configuration
        - Add validation check
        """
        learning = next(
            (l for l in self.learnings if l.learning_id == learning_id),
            None
        )
        
        if not learning:
            raise ValueError(f"Learning {learning_id} not found")
        
        # TODO: Implement learning application
        # - Analyze learning data
        # - Generate directive update
        # - Write to appropriate file
        # - Mark learning as applied
        
        learning.applied = True
        self._save_learnings()
        
        logger.info(f"Applied learning: {learning_id}")
    
    def identify_patterns(
        self,
        event_type: Optional[str] = None,
        min_occurrences: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Find recurring issues in learnings
        
        Returns patterns with suggested fixes
        """
        # TODO: Implement pattern detection
        # - Group learnings by similarity
        # - Identify recurring themes
        # - Suggest systematic fixes
        
        return []
    
    def suggest_improvements(
        self,
        agent_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        AI-generated improvement suggestions based on learnings
        
        Returns list of suggested improvements
        """
        # TODO: Implement improvement suggestion
        # - Analyze learnings for agent
        # - Identify weak points
        # - Generate actionable suggestions
        
        return []


# ============================================================================
# UNIFIED AGENT MANAGER
# ============================================================================

class AgentManager:
    """
    Unified Agent Manager
    
    Central orchestration layer for chiefaiofficer-alpha-swarm + revenue-swarm
    """
    
    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        
        # Initialize all managers
        self.registry = AgentRegistry(
            registry_path=str(self.base_path / ".hive-mind" / "registry.json")
        )
        self.lifecycle = LifecycleManager(self.registry)
        self.state = StateManager(
            state_dir=str(self.base_path / ".hive-mind" / "state")
        )
        self.handoff = HandoffManager(self.registry)
        self.context = ContextManager()
        self.learning = LearningManager(
            learnings_path=str(self.base_path / ".hive-mind" / "learnings.json")
        )
        
        logger.info("Agent Manager initialized")
    
    def bootstrap_swarm(self):
        """
        Bootstrap both swarms with default agents
        
        Registers all known agents from Alpha + Revenue swarms
        """
        # Alpha Swarm agents
        alpha_agents = [
            ("hunter", "sourcing", ["linkedin_scraping", "profile_extraction"]),
            ("enricher", "enrichment", ["data_enrichment", "api_waterfall"]),
            ("segmentor", "classification", ["icp_scoring", "tier_assignment"]),
            ("crafter", "generation", ["email_generation", "rpi_workflow"]),
            ("gatekeeper", "review", ["campaign_review", "ae_dashboard"]),
        ]
        
        for agent_id, agent_type, capabilities in alpha_agents:
            self.registry.register_agent(
                agent_id=agent_id,
                agent_type=agent_type,
                capabilities=capabilities,
                dependencies=[],
                mcp_server=f"./mcp-servers/{agent_id}-mcp"
            )
        
        # Revenue Swarm agents
        revenue_agents = [
            ("scout", "intelligence", ["intent_detection", "signal_analysis"]),
            ("operator", "execution", ["outbound_orchestration", "sequence_management"]),
            ("piper", "monitoring", ["visitor_scanning", "meeting_intelligence"]),
            ("coach", "optimization", ["self_annealing", "performance_tracking"]),
            ("queen", "orchestration", ["master_coordination", "workflow_routing"]),
        ]
        
        for agent_id, agent_type, capabilities in revenue_agents:
            self.registry.register_agent(
                agent_id=f"revenue_{agent_id}",
                agent_type=agent_type,
                capabilities=capabilities,
                dependencies=[],
                mcp_server=f"./mcp-servers/revenue-{agent_id}-mcp"
            )
        
        logger.info(f"Bootstrapped {len(self.registry.agents)} agents")
    
    def create_workflow(
        self,
        name: str,
        steps: List[Dict[str, str]]
    ) -> str:
        """
        Create a multi-agent workflow
        
        Args:
            name: Workflow name
            steps: List of {"agent": agent_id, "action": action_name}
        
        Returns:
            Workflow ID
        """
        # TODO: Implement workflow creation
        # - Validate all agents exist
        # - Check dependencies
        # - Create workflow definition
        # - Save to .hive-mind/workflows/
        
        workflow_id = f"workflow_{name}"
        logger.info(f"Created workflow: {workflow_id} with {len(steps)} steps")
        
        return workflow_id
    
    def execute_workflow(
        self,
        workflow_id: str,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a multi-agent workflow
        
        Coordinates handoffs between agents
        """
        # TODO: Implement workflow execution
        # - Load workflow definition
        # - Initialize required agents
        # - Execute steps in sequence
        # - Handle handoffs
        # - Return final output
        
        logger.info(f"Executing workflow: {workflow_id}")
        
        return {"status": "completed", "output": {}}
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check health of entire system
        
        Returns status of all agents and managers
        """
        agent_health = {}
        for agent_id in self.registry.agents.keys():
            agent_health[agent_id] = self.registry.agent_health_check(agent_id)
        
        return {
            "healthy": all(h["healthy"] for h in agent_health.values()),
            "total_agents": len(self.registry.agents),
            "agents": agent_health,
            "hive_mind_ok": (self.base_path / ".hive-mind").exists(),
        }


# ============================================================================
# CLI INTERFACE (for testing)
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Simple CLI for testing
    am = AgentManager()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "bootstrap":
            am.bootstrap_swarm()
            print("✅ Swarm bootstrapped")
        
        elif command == "list":
            agents = am.registry.list_agents()
            print(f"\n📋 Registered Agents ({len(agents)}):")
            for agent in agents:
                print(f"  - {agent.agent_id} ({agent.agent_type})")
                print(f"    Capabilities: {', '.join(agent.capabilities)}")
        
        elif command == "health":
            health = am.health_check()
            print(f"\n🏥 System Health:")
            print(f"  Overall: {'✅ Healthy' if health['healthy'] else '❌ Unhealthy'}")
            print(f"  Total Agents: {health['total_agents']}")
        
        else:
            print(f"Unknown command: {command}")
            print("Usage: python agent_manager.py [bootstrap|list|health]")
    
    else:
        print("Agent Manager - Chiefaiofficer Alpha Swarm")
        print("Usage: python agent_manager.py [bootstrap|list|health]")
