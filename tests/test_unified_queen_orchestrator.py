#!/usr/bin/env python3
"""
Tests for Unified Queen Orchestrator
=====================================
"""

import pytest
import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

pytest_plugins = ('pytest_asyncio',)

from execution.unified_queen_orchestrator import (
    UnifiedQueen,
    QLearningRouter,
    ByzantineConsensus,
    Task,
    TaskCategory,
    TaskPriority,
    TaskStatus,
    AgentName,
    AgentState,
    ContextBudget,
    Experience,
    ExperienceBuffer,
    TASK_CATEGORIES,
    CATEGORY_AGENTS,
)


class TestTaskCategories:
    """Test task category mapping."""
    
    def test_lead_gen_tasks(self):
        assert TASK_CATEGORIES["linkedin_scraping"] == TaskCategory.LEAD_GEN
        assert TASK_CATEGORIES["data_enrichment"] == TaskCategory.LEAD_GEN
        assert TASK_CATEGORIES["campaign_creation"] == TaskCategory.LEAD_GEN
    
    def test_pipeline_tasks(self):
        assert TASK_CATEGORIES["pipeline_scan"] == TaskCategory.PIPELINE
        assert TASK_CATEGORIES["ghost_hunting"] == TaskCategory.PIPELINE
    
    def test_scheduling_tasks(self):
        assert TASK_CATEGORIES["scheduling_request"] == TaskCategory.SCHEDULING
        assert TASK_CATEGORIES["meeting_book"] == TaskCategory.SCHEDULING
    
    def test_research_tasks(self):
        assert TASK_CATEGORIES["meeting_prep"] == TaskCategory.RESEARCH
        assert TASK_CATEGORIES["company_intel"] == TaskCategory.RESEARCH
    
    def test_approval_tasks(self):
        assert TASK_CATEGORIES["email_approval"] == TaskCategory.APPROVAL


class TestCategoryAgents:
    """Test category to agents mapping."""
    
    def test_lead_gen_agents(self):
        agents = CATEGORY_AGENTS[TaskCategory.LEAD_GEN]
        assert AgentName.HUNTER in agents
        assert AgentName.ENRICHER in agents
        assert AgentName.SEGMENTOR in agents
        assert AgentName.CRAFTER in agents
    
    def test_pipeline_agents(self):
        agents = CATEGORY_AGENTS[TaskCategory.PIPELINE]
        assert AgentName.SCOUT in agents
        assert AgentName.OPERATOR in agents
    
    def test_approval_agents(self):
        agents = CATEGORY_AGENTS[TaskCategory.APPROVAL]
        assert AgentName.GATEKEEPER in agents


class TestQLearningRouter:
    """Test Q-learning router."""
    
    def test_router_initialization(self):
        router = QLearningRouter()
        assert router.alpha == 0.1
        assert router.gamma == 0.95
        assert router.epsilon == 0.1
    
    def test_select_agent(self):
        router = QLearningRouter()
        
        task = Task(
            id="test_1",
            task_type="linkedin_scraping",
            category=TaskCategory.LEAD_GEN,
            priority=TaskPriority.MEDIUM,
            parameters={}
        )
        
        available = [AgentName.HUNTER, AgentName.ENRICHER]
        selected = router.select_agent(task, available)
        
        assert selected in available
        assert router.route_count == 1
    
    def test_q_table_update(self):
        router = QLearningRouter()
        
        task = Task(
            id="test_1",
            task_type="linkedin_scraping",
            category=TaskCategory.LEAD_GEN,
            priority=TaskPriority.MEDIUM,
            parameters={}
        )
        
        # Select agent
        agent = router.select_agent(task, [AgentName.HUNTER])
        
        # Update with positive reward
        router.update(task, agent, 1.0)
        
        state_key = router._state_key(task)
        assert state_key in router.q_table
        assert router.q_table[state_key][agent.value] > 0
    
    def test_exploration_exploitation(self):
        # High epsilon = more exploration
        router = QLearningRouter(epsilon=1.0)
        
        task = Task(
            id="test",
            task_type="test",
            category=TaskCategory.SYSTEM,
            priority=TaskPriority.LOW,
            parameters={}
        )
        
        # With epsilon=1.0, every selection is exploration
        for _ in range(10):
            router.select_agent(task, [AgentName.UNIFIED_QUEEN])
        
        assert router.exploration_count == 10
    
    def test_get_stats(self):
        router = QLearningRouter()
        stats = router.get_stats()
        
        assert "total_routes" in stats
        assert "explorations" in stats
        assert "epsilon" in stats
    
    def test_epsilon_decay(self):
        router = QLearningRouter(epsilon=0.5, epsilon_min=0.01, epsilon_decay=0.9)
        
        initial_epsilon = router.epsilon
        router.decay_epsilon()
        
        assert router.epsilon < initial_epsilon
        assert router.epsilon == 0.5 * 0.9
        assert router.training_episodes == 1
        
        for _ in range(100):
            router.decay_epsilon()
        
        assert router.epsilon == router.epsilon_min
    
    def test_reward_calculation(self):
        router = QLearningRouter()
        
        task = Task(
            id="test_reward",
            task_type="linkedin_scraping",
            category=TaskCategory.LEAD_GEN,
            priority=TaskPriority.CRITICAL,
            parameters={}
        )
        
        reward_success_fast = router.calculate_reward(
            task=task,
            agent=AgentName.HUNTER,
            success=True,
            latency_ms=200,
            agent_error_rate=0.05
        )
        assert reward_success_fast == 1.0 + 0.2 + 0.1 + 0.1  # 1.4
        
        reward_success_slow = router.calculate_reward(
            task=task,
            agent=AgentName.HUNTER,
            success=True,
            latency_ms=1000,
            agent_error_rate=0.2
        )
        assert reward_success_slow == 1.0 + 0.1  # 1.1 (only priority bonus)
        
        reward_failure = router.calculate_reward(
            task=task,
            agent=AgentName.HUNTER,
            success=False,
            latency_ms=100,
            agent_error_rate=0.0
        )
        assert reward_failure == -1.0
    
    def test_ucb_selection(self):
        router = QLearningRouter()
        
        task = Task(
            id="test_ucb",
            task_type="pipeline_scan",
            category=TaskCategory.PIPELINE,
            priority=TaskPriority.MEDIUM,
            parameters={}
        )
        
        available = [AgentName.SCOUT, AgentName.OPERATOR]
        
        selected = router.select_agent_ucb(task, available)
        assert selected in available
        assert router.route_count == 1
        
        for _ in range(10):
            router.select_agent_ucb(task, available)
        
        state_key = router._state_key(task)
        total_selections = sum(router.action_counts[state_key].values())
        assert total_selections == 11
    
    def test_experience_replay(self):
        buffer = ExperienceBuffer(max_size=5)
        
        for i in range(7):
            exp = Experience(
                state_key=f"state_{i}",
                agent="HUNTER",
                reward=1.0,
                next_state_key=None
            )
            buffer.add(exp)
        
        assert len(buffer) == 5
        
        sample = buffer.sample(3)
        assert len(sample) == 3
        
        full_sample = buffer.sample(10)
        assert len(full_sample) == 5
    
    def test_batch_update(self):
        router = QLearningRouter()
        
        task1 = Task(
            id="batch_1",
            task_type="linkedin_scraping",
            category=TaskCategory.LEAD_GEN,
            priority=TaskPriority.MEDIUM,
            parameters={}
        )
        task2 = Task(
            id="batch_2",
            task_type="pipeline_scan",
            category=TaskCategory.PIPELINE,
            priority=TaskPriority.HIGH,
            parameters={}
        )
        
        router.select_agent(task1, [AgentName.HUNTER])
        router.update(task1, AgentName.HUNTER, 1.0)
        
        router.select_agent(task2, [AgentName.SCOUT])
        router.update(task2, AgentName.SCOUT, -0.5)
        
        assert len(router.experience_buffer) == 2
        
        initial_q = router.q_table.copy()
        router.batch_update(batch_size=2)
        
        stats = router.get_stats()
        assert "experience_buffer_size" in stats
        assert stats["experience_buffer_size"] == 2
        assert "avg_reward_last_100" in stats
        assert "training_episodes" in stats
        assert "epsilon_current" in stats


class TestByzantineConsensus:
    """Test Byzantine consensus."""
    
    @pytest.mark.asyncio
    async def test_consensus_approval(self):
        consensus = ByzantineConsensus()
        
        # All vote yes
        def all_yes(agent, action):
            return True
        
        approved, details = await consensus.propose(
            decision_id="test_1",
            action="test_action",
            proposer=AgentName.UNIFIED_QUEEN,
            voters=[AgentName.GATEKEEPER],
            vote_fn=all_yes
        )
        
        assert approved is True
        assert details["approval_ratio"] >= 0.66
    
    @pytest.mark.asyncio
    async def test_consensus_rejection(self):
        consensus = ByzantineConsensus()
        
        # All vote no except proposer
        def all_no(agent, action):
            return False
        
        # With many no votes, should fail
        approved, details = await consensus.propose(
            decision_id="test_2",
            action="test_action",
            proposer=AgentName.HUNTER,  # Low weight
            voters=[AgentName.UNIFIED_QUEEN, AgentName.GATEKEEPER],  # High weight
            vote_fn=all_no
        )
        
        # HUNTER has weight 1, QUEEN has 3, GATEKEEPER has 2
        # Total: 6, Approve: 1, Ratio: 16% < 66%
        assert approved is False
    
    @pytest.mark.asyncio
    async def test_weighted_voting(self):
        consensus = ByzantineConsensus()
        
        # Check weights
        assert consensus._get_weight(AgentName.UNIFIED_QUEEN) == 3
        assert consensus._get_weight(AgentName.GATEKEEPER) == 2
        assert consensus._get_weight(AgentName.HUNTER) == 1


class TestContextBudget:
    """Test context budget management."""
    
    def test_usage_percent(self):
        budget = ContextBudget(max_tokens=100000, used_tokens=40000)
        assert budget.usage_percent == 0.4
    
    def test_dumb_zone_detection(self):
        budget = ContextBudget(max_tokens=100000, used_tokens=35000)
        assert budget.is_in_dumb_zone is False
        
        budget.used_tokens = 45000
        assert budget.is_in_dumb_zone is True
    
    def test_should_compact(self):
        budget = ContextBudget(max_tokens=100000, used_tokens=55000)
        assert budget.should_compact() is False
        
        budget.used_tokens = 65000
        assert budget.should_compact() is True


class TestTask:
    """Test Task dataclass."""
    
    def test_task_creation(self):
        task = Task(
            id="test_123",
            task_type="linkedin_scraping",
            category=TaskCategory.LEAD_GEN,
            priority=TaskPriority.HIGH,
            parameters={"url": "https://linkedin.com"}
        )
        
        assert task.status == TaskStatus.PENDING
        assert task.assigned_agent is None
        assert task.retry_count == 0
    
    def test_task_with_approval(self):
        task = Task(
            id="test_456",
            task_type="email_approval",
            category=TaskCategory.APPROVAL,
            priority=TaskPriority.CRITICAL,
            parameters={},
            requires_approval=True
        )
        
        assert task.requires_approval is True


class TestUnifiedQueen:
    """Test Unified Queen orchestrator."""
    
    def test_queen_initialization(self):
        queen = UnifiedQueen()
        
        assert len(queen.agents) == len(AgentName)
        assert queen.task_queue.empty()
        assert queen._running is False
    
    def test_create_task(self):
        queen = UnifiedQueen()
        
        task = queen.create_task(
            task_type="linkedin_scraping",
            parameters={"url": "test"},
            priority=TaskPriority.HIGH
        )
        
        assert task.category == TaskCategory.LEAD_GEN
        assert task.priority == TaskPriority.HIGH
        assert len(task.id) == 12
    
    @pytest.mark.asyncio
    async def test_submit_task(self):
        queen = UnifiedQueen()
        
        task = queen.create_task(
            task_type="pipeline_scan",
            parameters={}
        )
        
        task_id = await queen.submit_task(task)
        
        assert task_id == task.id
        assert task.id in queen.active_tasks
        assert queen.task_queue.qsize() == 1
    
    @pytest.mark.asyncio
    async def test_route_task(self):
        queen = UnifiedQueen()
        
        task = queen.create_task(
            task_type="linkedin_scraping",
            parameters={}
        )
        
        agent = await queen.route_task(task)
        
        # Should route to a lead gen agent
        assert agent in CATEGORY_AGENTS[TaskCategory.LEAD_GEN]
        assert task.assigned_agent == agent.value
    
    def test_sparc_scan(self):
        queen = UnifiedQueen()
        
        scan = queen.execute_sparc_scan()
        
        assert "specification" in scan
        assert "planning" in scan
        assert "architecture" in scan
        assert "refinement" in scan
        assert "completion" in scan
        
        # Check specification
        assert "active_agents" in scan["specification"]
        assert scan["specification"]["active_agents"] > 0
    
    def test_get_status(self):
        queen = UnifiedQueen()
        
        status = queen.get_status()
        
        assert "queen" in status
        assert "agents" in status
        assert "tasks" in status
        assert "context" in status
        assert "routing" in status
    
    @pytest.mark.asyncio
    async def test_start_stop(self):
        queen = UnifiedQueen()
        
        await queen.start()
        assert queen._running is True
        assert len(queen._worker_tasks) > 0
        
        await queen.stop()
        assert queen._running is False
    
    def test_generate_recommendations(self):
        queen = UnifiedQueen()
        
        # Simulate a dead agent
        queen.agents[AgentName.HUNTER].status = "dead"
        
        recommendations = queen._generate_recommendations()
        
        assert any("HUNTER" in r for r in recommendations)
    
    @pytest.mark.asyncio
    async def test_full_task_flow(self):
        queen = UnifiedQueen()
        await queen.start()
        
        try:
            # Submit a task
            task = queen.create_task(
                task_type="meeting_prep",
                parameters={"contact_id": "123"}
            )
            await queen.submit_task(task)
            
            # Wait for processing
            await asyncio.sleep(0.5)
            
            # Check status
            status = queen.get_status()
            assert status["tasks"]["completed"] >= 0
            
        finally:
            await queen.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
