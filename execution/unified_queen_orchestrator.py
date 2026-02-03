#!/usr/bin/env python3
"""
Unified Queen Orchestrator
===========================
Master orchestrator merging Alpha Swarm and Revenue Swarm capabilities.

Features:
- 12-agent registry with health monitoring
- Q-learning intelligent task routing
- Byzantine consensus for critical decisions
- Context budget management (<40% "Dumb Zone")
- SPARC methodology enforcement
- Parallel agent spawning
- Self-annealing integration

Architecture:
                    ┌─────────────────────────────────┐
                    │       UNIFIED QUEEN              │
                    │  ┌─────────────────────────┐    │
                    │  │ Q-Learning Router       │    │
                    │  │ Byzantine Consensus     │    │
                    │  │ Context Manager         │    │
                    │  └─────────────────────────┘    │
                    └───────────────┬─────────────────┘
         ┌────────────┬────────────┼────────────┬────────────┐
         ▼            ▼            ▼            ▼            ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
    │LEAD GEN │ │PIPELINE │ │SCHEDULE │ │RESEARCH │ │APPROVAL │
    ├─────────┤ ├─────────┤ ├─────────┤ ├─────────┤ ├─────────┤
    │ HUNTER  │ │ SCOUT   │ │SCHEDULER│ │RESEARCHER│ │GATEKEEPER
    │ ENRICHER│ │ OPERATOR│ │ COMMUN. │ │         │ │         │
    │ SEGMENTR│ │ COACH   │ │         │ │         │ │         │
    │ CRAFTER │ │ PIPER   │ │         │ │         │ │         │
    └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘

Usage:
    from execution.unified_queen_orchestrator import UnifiedQueen
    
    queen = UnifiedQueen()
    await queen.start()
    result = await queen.route_task(task)
"""

import os
import sys
import json
import asyncio
import random
import time
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict
import threading
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("unified_queen")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.unified_guardrails import UnifiedGuardrails, ActionType, RiskLevel
from core.unified_integration_gateway import get_gateway
from core.self_annealing_engine import SelfAnnealingEngine


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class AgentName(Enum):
    """All 12 agents in the unified swarm."""
    UNIFIED_QUEEN = "UNIFIED_QUEEN"
    HUNTER = "HUNTER"
    ENRICHER = "ENRICHER"
    SEGMENTOR = "SEGMENTOR"
    CRAFTER = "CRAFTER"
    GATEKEEPER = "GATEKEEPER"
    SCOUT = "SCOUT"
    OPERATOR = "OPERATOR"
    COACH = "COACH"
    PIPER = "PIPER"
    SCHEDULER = "SCHEDULER"
    RESEARCHER = "RESEARCHER"
    COMMUNICATOR = "COMMUNICATOR"


class TaskCategory(Enum):
    """Task categories for routing."""
    LEAD_GEN = "lead_gen"
    PIPELINE = "pipeline"
    SCHEDULING = "scheduling"
    RESEARCH = "research"
    APPROVAL = "approval"
    SYSTEM = "system"


class TaskPriority(Enum):
    """Task priority levels."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


# Task type to category mapping
TASK_CATEGORIES: Dict[str, TaskCategory] = {
    # Lead Gen
    "linkedin_scraping": TaskCategory.LEAD_GEN,
    "data_enrichment": TaskCategory.LEAD_GEN,
    "lead_scoring": TaskCategory.LEAD_GEN,
    "campaign_creation": TaskCategory.LEAD_GEN,
    "icp_classification": TaskCategory.LEAD_GEN,
    
    # Pipeline
    "pipeline_scan": TaskCategory.PIPELINE,
    "ghost_hunting": TaskCategory.PIPELINE,
    "deal_update": TaskCategory.PIPELINE,
    "sequence_trigger": TaskCategory.PIPELINE,
    "engagement_tracking": TaskCategory.PIPELINE,
    
    # Scheduling
    "scheduling_request": TaskCategory.SCHEDULING,
    "calendar_check": TaskCategory.SCHEDULING,
    "meeting_book": TaskCategory.SCHEDULING,
    "email_response": TaskCategory.SCHEDULING,
    "reschedule": TaskCategory.SCHEDULING,
    
    # Research
    "meeting_prep": TaskCategory.RESEARCH,
    "company_intel": TaskCategory.RESEARCH,
    "objection_prediction": TaskCategory.RESEARCH,
    "competitor_analysis": TaskCategory.RESEARCH,
    
    # Approval
    "email_approval": TaskCategory.APPROVAL,
    "campaign_approval": TaskCategory.APPROVAL,
    "bulk_action_approval": TaskCategory.APPROVAL,
    
    # System
    "health_check": TaskCategory.SYSTEM,
    "self_annealing": TaskCategory.SYSTEM,
    "audit_log": TaskCategory.SYSTEM,
}

# Category to agents mapping
CATEGORY_AGENTS: Dict[TaskCategory, List[AgentName]] = {
    TaskCategory.LEAD_GEN: [
        AgentName.HUNTER, AgentName.ENRICHER, 
        AgentName.SEGMENTOR, AgentName.CRAFTER
    ],
    TaskCategory.PIPELINE: [
        AgentName.SCOUT, AgentName.OPERATOR, 
        AgentName.COACH, AgentName.PIPER
    ],
    TaskCategory.SCHEDULING: [
        AgentName.SCHEDULER, AgentName.COMMUNICATOR
    ],
    TaskCategory.RESEARCH: [
        AgentName.RESEARCHER
    ],
    TaskCategory.APPROVAL: [
        AgentName.GATEKEEPER
    ],
    TaskCategory.SYSTEM: [
        AgentName.UNIFIED_QUEEN
    ],
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Task:
    """Task to be executed by an agent."""
    id: str
    task_type: str
    category: TaskCategory
    priority: TaskPriority
    parameters: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    requires_approval: bool = False
    grounding_evidence: Optional[Dict] = None


@dataclass
class AgentState:
    """Current state of an agent."""
    name: AgentName
    status: str = "idle"
    current_task: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    last_heartbeat: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error_rate: float = 0.0
    avg_latency_ms: float = 0.0


@dataclass
class ContextBudget:
    """Context window budget tracking (HumanLayer 12-Factor)."""
    max_tokens: int = 100000
    used_tokens: int = 0
    threshold_warning: float = 0.4  # "Dumb Zone" starts at 40%
    threshold_critical: float = 0.6
    
    @property
    def usage_percent(self) -> float:
        return self.used_tokens / self.max_tokens
    
    @property
    def is_in_dumb_zone(self) -> bool:
        return self.usage_percent > self.threshold_warning
    
    def should_compact(self) -> bool:
        return self.usage_percent > self.threshold_critical


@dataclass
class LearningOutcome:
    """Outcome to log to self-annealing system."""
    context: str
    action: str
    success: bool
    details: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Experience:
    """Experience tuple for replay buffer."""
    state_key: str
    agent: str
    reward: float
    next_state_key: Optional[str]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ExperienceBuffer:
    """Experience replay buffer for batch learning."""
    
    def __init__(self, max_size: int = 1000):
        self.buffer: List[Experience] = []
        self.max_size = max_size
    
    def add(self, exp: Experience):
        """Add experience to buffer, removing oldest if at capacity."""
        if len(self.buffer) >= self.max_size:
            self.buffer.pop(0)
        self.buffer.append(exp)
    
    def sample(self, batch_size: int) -> List[Experience]:
        """Sample random batch from buffer."""
        if len(self.buffer) <= batch_size:
            return self.buffer.copy()
        return random.sample(self.buffer, batch_size)
    
    def __len__(self) -> int:
        return len(self.buffer)


# =============================================================================
# Q-LEARNING ROUTER
# =============================================================================

class QLearningRouter:
    """
    Q-Learning based task routing.
    
    Learns optimal agent assignment for each task type based on:
    - Historical success rates
    - Latency
    - Agent availability
    - Task complexity
    
    Features:
    - Adaptive epsilon decay for exploration -> exploitation
    - UCB1 exploration strategy
    - Experience replay buffer
    - Composite reward shaping
    """
    
    def __init__(
        self,
        learning_rate: float = 0.1,
        discount_factor: float = 0.95,
        epsilon: float = 0.1,
        epsilon_min: float = 0.01,
        epsilon_decay: float = 0.995,
        ucb_constant: float = 1.41,
        q_table_path: Optional[Path] = None
    ):
        self.alpha = learning_rate
        self.gamma = discount_factor
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.ucb_constant = ucb_constant
        
        self.q_table_path = q_table_path or (PROJECT_ROOT / ".hive-mind" / "q_table.json")
        self.q_table: Dict[str, Dict[str, float]] = self._load_q_table()
        
        self.experience_buffer = ExperienceBuffer(max_size=1000)
        self.action_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.reward_history: List[float] = []
        
        self.route_count = 0
        self.exploration_count = 0
        self.training_episodes = 0
    
    def _load_q_table(self) -> Dict[str, Dict[str, float]]:
        """Load Q-table from persistent storage."""
        if self.q_table_path.exists():
            try:
                return json.loads(self.q_table_path.read_text())
            except:
                pass
        return {}
    
    def _save_q_table(self):
        """Persist Q-table to storage."""
        self.q_table_path.parent.mkdir(parents=True, exist_ok=True)
        self.q_table_path.write_text(json.dumps(self.q_table, indent=2))
    
    def _state_key(self, task: Task) -> str:
        """Generate state key for Q-table lookup."""
        return f"{task.task_type}|{task.priority.value}"
    
    def decay_epsilon(self):
        """Decay epsilon after each episode for exploration -> exploitation transition."""
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
            if self.epsilon < self.epsilon_min:
                self.epsilon = self.epsilon_min
        self.training_episodes += 1
    
    def calculate_reward(
        self,
        task: Task,
        agent: AgentName,
        success: bool,
        latency_ms: float,
        agent_error_rate: float
    ) -> float:
        """
        Calculate composite reward based on multiple factors.
        
        Args:
            task: The task that was executed
            agent: The agent that executed it
            success: Whether execution succeeded
            latency_ms: Execution latency in milliseconds
            agent_error_rate: Agent's historical error rate (0.0 to 1.0)
        
        Returns:
            Composite reward value
        """
        reward = 1.0 if success else -1.0
        
        if success:
            if latency_ms < 500:
                reward += 0.2
            if agent_error_rate < 0.1:
                reward += 0.1
            if task.priority in [TaskPriority.CRITICAL, TaskPriority.HIGH]:
                reward += 0.1
        
        return reward
    
    def select_agent(
        self,
        task: Task,
        available_agents: List[AgentName]
    ) -> AgentName:
        """
        Select best agent for task using epsilon-greedy policy.
        
        Args:
            task: Task to route
            available_agents: Agents that can handle this task
        
        Returns:
            Selected agent name
        """
        self.route_count += 1
        state_key = self._state_key(task)
        
        if state_key not in self.q_table:
            self.q_table[state_key] = {
                agent.value: 0.0 for agent in available_agents
            }
        
        if random.random() < self.epsilon:
            self.exploration_count += 1
            selected = random.choice(available_agents)
        else:
            agent_scores = self.q_table[state_key]
            available_scores = {
                agent.value: agent_scores.get(agent.value, 0.0)
                for agent in available_agents
            }
            best_agent = max(available_scores, key=available_scores.get)
            selected = AgentName(best_agent)
        
        self.action_counts[state_key][selected.value] += 1
        return selected
    
    def select_agent_ucb(
        self,
        task: Task,
        available_agents: List[AgentName]
    ) -> AgentName:
        """
        Upper Confidence Bound selection for better exploration-exploitation balance.
        
        UCB = Q(s,a) + c * sqrt(ln(N) / n(s,a))
        where c is exploration constant (default 1.41)
        
        Args:
            task: Task to route
            available_agents: Agents that can handle this task
        
        Returns:
            Selected agent name using UCB1 strategy
        """
        import math
        
        self.route_count += 1
        state_key = self._state_key(task)
        
        if state_key not in self.q_table:
            self.q_table[state_key] = {
                agent.value: 0.0 for agent in available_agents
            }
        
        total_count = sum(self.action_counts[state_key].values())
        
        if total_count == 0:
            selected = random.choice(available_agents)
            self.action_counts[state_key][selected.value] += 1
            return selected
        
        best_agent = None
        best_ucb = float('-inf')
        
        for agent in available_agents:
            q_value = self.q_table[state_key].get(agent.value, 0.0)
            action_count = self.action_counts[state_key].get(agent.value, 0)
            
            if action_count == 0:
                self.action_counts[state_key][agent.value] += 1
                return agent
            
            ucb_value = q_value + self.ucb_constant * math.sqrt(
                math.log(total_count) / action_count
            )
            
            if ucb_value > best_ucb:
                best_ucb = ucb_value
                best_agent = agent
        
        self.action_counts[state_key][best_agent.value] += 1
        return best_agent
    
    def update(
        self,
        task: Task,
        agent: AgentName,
        reward: float,
        next_task: Optional[Task] = None
    ):
        """
        Update Q-value based on task outcome.
        
        Args:
            task: Completed task
            agent: Agent that executed the task
            reward: Reward signal (-1 to 1)
            next_task: Next task in sequence (for TD learning)
        """
        state_key = self._state_key(task)
        next_state_key = self._state_key(next_task) if next_task else None
        
        if state_key not in self.q_table:
            self.q_table[state_key] = {}
        
        current_q = self.q_table[state_key].get(agent.value, 0.0)
        
        max_future_q = 0.0
        if next_state_key and next_state_key in self.q_table:
            max_future_q = max(self.q_table[next_state_key].values(), default=0.0)
        
        new_q = current_q + self.alpha * (reward + self.gamma * max_future_q - current_q)
        self.q_table[state_key][agent.value] = new_q
        
        self.reward_history.append(reward)
        if len(self.reward_history) > 100:
            self.reward_history.pop(0)
        
        exp = Experience(
            state_key=state_key,
            agent=agent.value,
            reward=reward,
            next_state_key=next_state_key
        )
        self.experience_buffer.add(exp)
        
        if self.route_count % 10 == 0:
            self._save_q_table()
    
    def batch_update(self, batch_size: int = 32):
        """
        Sample from experience buffer and update Q-values.
        
        Args:
            batch_size: Number of experiences to sample
        """
        experiences = self.experience_buffer.sample(batch_size)
        
        for exp in experiences:
            if exp.state_key not in self.q_table:
                self.q_table[exp.state_key] = {}
            
            current_q = self.q_table[exp.state_key].get(exp.agent, 0.0)
            
            max_future_q = 0.0
            if exp.next_state_key and exp.next_state_key in self.q_table:
                max_future_q = max(self.q_table[exp.next_state_key].values(), default=0.0)
            
            new_q = current_q + self.alpha * (exp.reward + self.gamma * max_future_q - current_q)
            self.q_table[exp.state_key][exp.agent] = new_q
    
    def get_stats(self) -> Dict[str, Any]:
        """Get routing statistics."""
        avg_reward = 0.0
        if self.reward_history:
            avg_reward = sum(self.reward_history) / len(self.reward_history)
        
        return {
            "total_routes": self.route_count,
            "explorations": self.exploration_count,
            "exploration_rate": self.exploration_count / max(1, self.route_count),
            "q_table_size": len(self.q_table),
            "epsilon": self.epsilon,
            "epsilon_current": self.epsilon,
            "training_episodes": self.training_episodes,
            "experience_buffer_size": len(self.experience_buffer),
            "avg_reward_last_100": round(avg_reward, 4)
        }


# =============================================================================
# BYZANTINE CONSENSUS
# =============================================================================

class ByzantineConsensus:
    """
    Byzantine fault-tolerant consensus for critical decisions.
    
    Requires 2/3 agreement with weighted voting:
    - UNIFIED_QUEEN: weight 3
    - GATEKEEPER: weight 2
    - Other agents: weight 1
    """
    
    WEIGHTS = {
        AgentName.UNIFIED_QUEEN: 3,
        AgentName.GATEKEEPER: 2,
    }
    DEFAULT_WEIGHT = 1
    THRESHOLD = 2/3
    
    def __init__(self):
        self._votes: Dict[str, Dict[str, Tuple[bool, AgentName]]] = {}
    
    def _get_weight(self, agent: AgentName) -> int:
        return self.WEIGHTS.get(agent, self.DEFAULT_WEIGHT)
    
    async def propose(
        self,
        decision_id: str,
        action: str,
        proposer: AgentName,
        voters: List[AgentName],
        vote_fn: Callable[[AgentName, str], bool]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Propose an action for consensus.
        
        Args:
            decision_id: Unique ID for this decision
            action: Action being proposed
            proposer: Agent proposing the action
            voters: Agents that should vote
            vote_fn: Function to get each agent's vote
        
        Returns:
            Tuple of (approved, details)
        """
        votes = {}
        total_weight = 0
        approve_weight = 0
        
        # Proposer automatically votes yes
        votes[proposer.value] = True
        proposer_weight = self._get_weight(proposer)
        total_weight += proposer_weight
        approve_weight += proposer_weight
        
        # Collect votes
        for voter in voters:
            if voter == proposer:
                continue
            
            try:
                vote = vote_fn(voter, action)
            except:
                vote = False  # Default to reject on error
            
            votes[voter.value] = vote
            weight = self._get_weight(voter)
            total_weight += weight
            if vote:
                approve_weight += weight
        
        # Check threshold
        approval_ratio = approve_weight / total_weight if total_weight > 0 else 0
        approved = approval_ratio >= self.THRESHOLD
        
        result = {
            "decision_id": decision_id,
            "action": action,
            "proposer": proposer.value,
            "votes": votes,
            "total_weight": total_weight,
            "approve_weight": approve_weight,
            "approval_ratio": round(approval_ratio, 2),
            "threshold": self.THRESHOLD,
            "approved": approved,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"Consensus {decision_id}: {approved} ({approval_ratio:.0%})")
        
        return approved, result


# =============================================================================
# UNIFIED QUEEN ORCHESTRATOR
# =============================================================================

class UnifiedQueen:
    """
    Unified Queen Orchestrator - Master agent for the CAIO RevOps Swarm.
    
    Responsibilities:
    1. Task routing with Q-learning optimization
    2. Agent health monitoring and recovery
    3. Context budget management (prevent "Dumb Zone")
    4. SPARC methodology enforcement
    5. Byzantine consensus for critical decisions
    6. Self-annealing integration
    7. Audit trail maintenance
    """
    
    MAX_CONCURRENT_AGENTS = 12
    HEARTBEAT_INTERVAL = 30  # seconds
    
    def __init__(self):
        # Core components
        self.guardrails = UnifiedGuardrails()
        self.gateway = get_gateway()
        self.router = QLearningRouter()
        self.consensus = ByzantineConsensus()
        self.annealing = SelfAnnealingEngine()
        
        # Agent state
        self.agents: Dict[AgentName, AgentState] = {
            agent: AgentState(name=agent)
            for agent in AgentName
        }
        
        # Task management
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.active_tasks: Dict[str, Task] = {}
        self.completed_tasks: List[Task] = []
        
        # Context budget
        self.context = ContextBudget()
        
        # Runtime state
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._worker_tasks: List[asyncio.Task] = []
        
        # Hive-mind storage
        self.hive_mind = PROJECT_ROOT / ".hive-mind"
        self.hive_mind.mkdir(exist_ok=True)
        self.audit_file = self.hive_mind / "queen_audit.json"
        
        logger.info("Unified Queen initialized")
    
    async def start(self):
        """Start the orchestrator."""
        if self._running:
            return
        
        self._running = True
        logger.info("=" * 60)
        logger.info("UNIFIED QUEEN ORCHESTRATOR - STARTING")
        logger.info("=" * 60)
        
        # Start heartbeat monitor
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        # Start worker tasks
        for i in range(min(4, self.MAX_CONCURRENT_AGENTS)):
            task = asyncio.create_task(self._worker_loop(i))
            self._worker_tasks.append(task)
        
        logger.info(f"Started {len(self._worker_tasks)} worker tasks")
    
    async def stop(self):
        """Stop the orchestrator."""
        if not self._running:
            return
        
        self._running = False
        
        # Cancel tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        
        for task in self._worker_tasks:
            task.cancel()
        
        # Save state
        self.router._save_q_table()
        
        logger.info("Unified Queen stopped")
    
    async def _heartbeat_loop(self):
        """Monitor agent health via heartbeats."""
        while self._running:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                
                for agent_name, state in self.agents.items():
                    # Check for stale heartbeats
                    last_hb = datetime.fromisoformat(state.last_heartbeat)
                    if last_hb.tzinfo is None:
                        last_hb = last_hb.replace(tzinfo=timezone.utc)
                    age = (datetime.now(timezone.utc) - last_hb).total_seconds()
                    
                    if age > self.HEARTBEAT_INTERVAL * 3:
                        if state.status != "dead":
                            logger.warning(f"Agent {agent_name.value} missed heartbeats")
                            state.status = "dead"
                            await self._recover_agent(agent_name)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def _worker_loop(self, worker_id: int):
        """Process tasks from queue."""
        while self._running:
            try:
                # Get task with timeout
                try:
                    task = await asyncio.wait_for(
                        self.task_queue.get(),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process task
                await self._execute_task(task)
                self.task_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
    
    async def _recover_agent(self, agent_name: AgentName):
        """Attempt to recover a dead agent."""
        state = self.agents[agent_name]
        
        logger.info(f"Attempting recovery of {agent_name.value}")
        
        # Simulate recovery (in real implementation, restart process)
        await asyncio.sleep(1)
        
        state.status = "idle"
        state.last_heartbeat = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"Agent {agent_name.value} recovered")
    
    def create_task(
        self,
        task_type: str,
        parameters: Dict[str, Any],
        priority: TaskPriority = TaskPriority.MEDIUM,
        requires_approval: bool = False,
        grounding_evidence: Optional[Dict] = None
    ) -> Task:
        """
        Create a new task for execution.
        
        Args:
            task_type: Type of task (maps to category)
            parameters: Task parameters
            priority: Priority level
            requires_approval: Whether human approval is needed
            grounding_evidence: Evidence for high-risk actions
        
        Returns:
            Created Task object
        """
        task_id = hashlib.md5(
            f"{task_type}:{datetime.now(timezone.utc).isoformat()}:{random.random()}".encode()
        ).hexdigest()[:12]
        
        category = TASK_CATEGORIES.get(task_type, TaskCategory.SYSTEM)
        
        task = Task(
            id=task_id,
            task_type=task_type,
            category=category,
            priority=priority,
            parameters=parameters,
            requires_approval=requires_approval,
            grounding_evidence=grounding_evidence
        )
        
        return task
    
    async def submit_task(self, task: Task) -> str:
        """
        Submit a task for execution.
        
        Args:
            task: Task to execute
        
        Returns:
            Task ID
        """
        # Check context budget
        if self.context.should_compact():
            await self._compact_context()
        
        # Add to queue
        await self.task_queue.put(task)
        self.active_tasks[task.id] = task
        
        logger.info(f"Task {task.id} ({task.task_type}) submitted")
        
        return task.id
    
    async def route_task(self, task: Task) -> AgentName:
        """
        Route task to optimal agent using Q-learning.
        
        Args:
            task: Task to route
        
        Returns:
            Selected agent
        """
        # Get eligible agents for this category
        eligible = CATEGORY_AGENTS.get(task.category, [AgentName.UNIFIED_QUEEN])
        
        # Filter by availability
        available = [
            agent for agent in eligible
            if self.agents[agent].status in ["idle", "available"]
        ]
        
        if not available:
            # Fall back to any eligible agent
            available = eligible
        
        # Use Q-learning router
        selected = self.router.select_agent(task, available)
        
        task.assigned_agent = selected.value
        
        logger.info(f"Task {task.id} routed to {selected.value}")
        
        return selected
    
    async def _execute_task(self, task: Task):
        """Execute a task with full guardrails."""
        start_time = time.time()
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc).isoformat()
        
        try:
            # Route to agent
            agent = await self.route_task(task)
            agent_state = self.agents[agent]
            agent_state.status = "busy"
            agent_state.current_task = task.id
            
            # Check if approval needed
            if task.requires_approval:
                approved, details = await self._request_approval(task)
                if not approved:
                    task.status = TaskStatus.BLOCKED
                    task.error = "Approval denied"
                    return
            
            # Execute task (simulate - real implementation calls agent)
            result = await self._simulate_task_execution(task, agent)
            
            # Update task
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc).isoformat()
            task.result = result
            
            # Update agent stats
            agent_state.tasks_completed += 1
            agent_state.status = "idle"
            agent_state.current_task = None
            latency = (time.time() - start_time) * 1000
            agent_state.avg_latency_ms = (
                (agent_state.avg_latency_ms * (agent_state.tasks_completed - 1) + latency)
                / agent_state.tasks_completed
            )
            
            # Update Q-learning
            reward = 1.0  # Success
            self.router.update(task, agent, reward)
            
            # Log to self-annealing
            await self._log_outcome(task, agent, True)
            
        except Exception as e:
            # Handle failure
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now(timezone.utc).isoformat()
            
            if task.assigned_agent:
                agent = AgentName(task.assigned_agent)
                agent_state = self.agents[agent]
                agent_state.tasks_failed += 1
                agent_state.status = "idle"
                agent_state.current_task = None
                agent_state.error_rate = (
                    agent_state.tasks_failed / 
                    (agent_state.tasks_completed + agent_state.tasks_failed)
                )
                
                # Negative reward for Q-learning
                self.router.update(task, agent, -1.0)
            
            # Retry if possible
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                await self.task_queue.put(task)
                logger.warning(f"Task {task.id} failed, retrying ({task.retry_count})")
            else:
                await self._log_outcome(task, AgentName(task.assigned_agent), False)
                logger.error(f"Task {task.id} failed permanently: {e}")
        
        finally:
            # Move to completed
            if task.id in self.active_tasks:
                del self.active_tasks[task.id]
            self.completed_tasks.append(task)
            
            # Trim history
            if len(self.completed_tasks) > 1000:
                self.completed_tasks = self.completed_tasks[-500:]
    
    async def _simulate_task_execution(
        self,
        task: Task,
        agent: AgentName
    ) -> Dict[str, Any]:
        """Simulate task execution (replace with real agent calls)."""
        await asyncio.sleep(0.1)  # Simulate work
        
        return {
            "task_id": task.id,
            "agent": agent.value,
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def _request_approval(self, task: Task) -> Tuple[bool, Dict]:
        """Request approval via Byzantine consensus."""
        voters = [AgentName.GATEKEEPER, AgentName.UNIFIED_QUEEN]
        
        def vote_fn(agent: AgentName, action: str) -> bool:
            # In real implementation, this would query the agent
            # For now, approve based on grounding evidence
            return task.grounding_evidence is not None
        
        return await self.consensus.propose(
            decision_id=f"approve_{task.id}",
            action=f"Execute {task.task_type}",
            proposer=AgentName.UNIFIED_QUEEN,
            voters=voters,
            vote_fn=vote_fn
        )
    
    async def _log_outcome(
        self,
        task: Task,
        agent: AgentName,
        success: bool
    ):
        """Log outcome to self-annealing engine."""
        outcome = {
            "task_type": task.task_type,
            "agent": agent.value,
            "success": success,
            "category": task.category.value,
            "priority": task.priority.value,
            "retry_count": task.retry_count
        }
        
        # Use process_outcome from self-annealing engine
        try:
            self.annealing.process_outcome(
                workflow_id=f"queen_task_{task.id}",
                outcome=outcome,
                context={"task_id": task.id}
            )
        except Exception as e:
            logger.warning(f"Failed to log to annealing: {e}")
    
    async def _compact_context(self):
        """Compact context when approaching Dumb Zone."""
        logger.warning("Context budget high - compacting")
        
        # Clear old completed tasks
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        self.completed_tasks = [
            t for t in self.completed_tasks
            if datetime.fromisoformat(t.completed_at or t.created_at) > cutoff
        ]
        
        # Estimate savings
        self.context.used_tokens = int(self.context.used_tokens * 0.6)
        
        logger.info(f"Context compacted to {self.context.usage_percent:.0%}")
    
    def execute_sparc_scan(self) -> Dict[str, Any]:
        """
        Execute SPARC methodology scan.
        
        S - SPECIFICATION: Current state
        P - PLANNING: Action plan
        A - ARCHITECTURE: Agent assignments
        R - REFINEMENT: Optimization opportunities
        C - COMPLETION: Verification
        """
        logger.info("Executing SPARC scan...")
        
        # S - Specification
        specification = {
            "active_agents": sum(1 for a in self.agents.values() if a.status != "dead"),
            "pending_tasks": self.task_queue.qsize(),
            "active_tasks": len(self.active_tasks),
            "completed_today": len([
                t for t in self.completed_tasks
                if t.completed_at and 
                datetime.fromisoformat(t.completed_at).date() == datetime.now(timezone.utc).date()
            ]),
            "context_usage": self.context.usage_percent,
            "in_dumb_zone": self.context.is_in_dumb_zone
        }
        
        # P - Planning
        planning = {
            "priority_tasks": [
                t.task_type for t in self.active_tasks.values()
                if t.priority in [TaskPriority.CRITICAL, TaskPriority.HIGH]
            ],
            "recommended_actions": self._generate_recommendations()
        }
        
        # A - Architecture
        architecture = {
            agent.value: {
                "status": state.status,
                "tasks_completed": state.tasks_completed,
                "error_rate": round(state.error_rate, 2)
            }
            for agent, state in self.agents.items()
        }
        
        # R - Refinement
        try:
            annealing_report = self.annealing.report_to_queen()
        except:
            annealing_report = {}
        
        refinement = {
            "routing_stats": self.router.get_stats(),
            "annealing_report": annealing_report
        }
        
        # C - Completion
        completion = {
            "scan_time": datetime.now(timezone.utc).isoformat(),
            "system_healthy": specification["active_agents"] >= 10,
            "recommendations_count": len(planning["recommended_actions"])
        }
        
        return {
            "specification": specification,
            "planning": planning,
            "architecture": architecture,
            "refinement": refinement,
            "completion": completion
        }
    
    def _generate_recommendations(self) -> List[str]:
        """Generate action recommendations based on current state."""
        recommendations = []
        
        # Check for dead agents
        dead_agents = [
            a.name.value for a in self.agents.values()
            if a.status == "dead"
        ]
        if dead_agents:
            recommendations.append(f"Recover agents: {', '.join(dead_agents)}")
        
        # Check error rates
        high_error_agents = [
            a.name.value for a in self.agents.values()
            if a.error_rate > 0.2
        ]
        if high_error_agents:
            recommendations.append(f"Investigate errors: {', '.join(high_error_agents)}")
        
        # Check context budget
        if self.context.is_in_dumb_zone:
            recommendations.append("Compact context - approaching Dumb Zone")
        
        # Check queue depth
        if self.task_queue.qsize() > 50:
            recommendations.append(f"High queue depth ({self.task_queue.qsize()}) - scale workers")
        
        return recommendations
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        return {
            "queen": {
                "running": self._running,
                "workers": len(self._worker_tasks)
            },
            "agents": {
                agent.value: {
                    "status": state.status,
                    "tasks": state.tasks_completed,
                    "errors": state.tasks_failed,
                    "error_rate": round(state.error_rate, 2)
                }
                for agent, state in self.agents.items()
            },
            "tasks": {
                "pending": self.task_queue.qsize(),
                "active": len(self.active_tasks),
                "completed": len(self.completed_tasks)
            },
            "context": {
                "usage_percent": round(self.context.usage_percent * 100, 1),
                "in_dumb_zone": self.context.is_in_dumb_zone
            },
            "routing": self.router.get_stats(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# =============================================================================
# DEMO
# =============================================================================

async def demo():
    """Demonstrate Unified Queen capabilities."""
    print("\n" + "=" * 60)
    print("UNIFIED QUEEN ORCHESTRATOR - Demo")
    print("=" * 60)
    
    queen = UnifiedQueen()
    await queen.start()
    
    try:
        # Create and submit tasks
        print("\n[Submitting Tasks]")
        
        tasks = [
            ("linkedin_scraping", {"url": "https://linkedin.com/company/test"}),
            ("pipeline_scan", {"pipeline_id": "main"}),
            ("scheduling_request", {"email": "Schedule a call for next week"}),
            ("meeting_prep", {"contact_id": "123", "meeting_date": "2026-01-28"}),
        ]
        
        for task_type, params in tasks:
            task = queen.create_task(task_type, params)
            await queen.submit_task(task)
            print(f"  Submitted: {task.id} ({task_type}) -> {task.category.value}")
        
        # Wait for processing
        await asyncio.sleep(0.5)
        
        # SPARC scan
        print("\n[SPARC Scan]")
        scan = queen.execute_sparc_scan()
        print(f"  Active agents: {scan['specification']['active_agents']}")
        print(f"  Completed today: {scan['specification']['completed_today']}")
        print(f"  Recommendations: {scan['planning']['recommended_actions']}")
        
        # Status
        print("\n[System Status]")
        status = queen.get_status()
        print(f"  Tasks completed: {status['tasks']['completed']}")
        print(f"  Q-table size: {status['routing']['q_table_size']}")
        print(f"  Exploration rate: {status['routing']['exploration_rate']:.0%}")
        
    finally:
        await queen.stop()
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
