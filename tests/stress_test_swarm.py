
import asyncio
import pytest
import random
import time
from unittest.mock import MagicMock, AsyncMock
from typing import Dict, Any, List

from execution.unified_queen_orchestrator import UnifiedQueen, Task, AgentName, TaskPriority, TaskStatus
from execution.scheduler_agent import SchedulerAgent
from execution.researcher_agent import ResearcherAgent
from execution.gatekeeper_queue import EnhancedGatekeeperQueue
from core.approval_engine import ApprovalRequest

# ============================================================================
# CHAOS MONKEY
# ============================================================================

class ChaosMonkey:
    """Injects random failures and delays into the system."""
    def __init__(self, failure_rate: float = 0.1, max_delay: float = 0.1):
        self.failure_rate = failure_rate
        self.max_delay = max_delay

    async def interfere(self):
        """Potentially raise an error or sleep."""
        # Random delay to simulate network/processing jitter
        if self.max_delay > 0:
            delay = random.uniform(0, self.max_delay)
            await asyncio.sleep(delay)
        
        # Random failure
        if random.random() < self.failure_rate:
            raise RuntimeError("🐒 Chaos Monkey struck this agent!")

# ============================================================================
# STRESS TEST MOCKS
# ============================================================================

class LegacyMockScheduler(SchedulerAgent):
    """Scheduler stub with chaos."""
    def __init__(self, chaos: ChaosMonkey):
        self.chaos = chaos
        self.calendar = AsyncMock()
        self.booked_meetings = []

    async def generate_proposals(self, prospect_timezone: str, duration_minutes: int) -> list:
        await self.chaos.interfere()
        return [{"start": "2026-01-24T10:00:00Z", "score": 1.0}]

    async def book_meeting(self, prospect_email: str, start_time: str, duration_minutes: int, title: str, with_zoom: bool = False):
        await self.chaos.interfere()
        self.booked_meetings.append(prospect_email)
        return MagicMock(success=True, event_id=f"evt_{len(self.booked_meetings)}")

class LegacyMockResearcher(ResearcherAgent):
    """Researcher stub with chaos."""
    def __init__(self, chaos: ChaosMonkey):
        self.chaos = chaos
    
    async def research_company(self, company_name: str, domain: str):
        await self.chaos.interfere()
        return MagicMock(company_name=company_name, industry="Stress Tested")
    
    async def research_attendee(self, email: str, name: str, ghl_contact_id: str = None):
        await self.chaos.interfere()
        return MagicMock(email=email, ghl_tags=["vip"])

class StressQueen(UnifiedQueen):
    """
    Coordinator for stress tests. 
    Bypasses external APIs but uses real internal logic (queues, task tracking).
    """
    def __init__(self, scheduler, researcher, gatekeeper):
        super().__init__()
        self.scheduler_agent = scheduler
        self.researcher_agent = researcher
        self.gatekeeper_agent = gatekeeper
        
        # We Mock the router to avoid loading the ML model, 
        # but we simulate routing behavior in _execute_task
        self.router = MagicMock()
        self.consensus_engine = AsyncMock() 

    async def _execute_task(self, task: Task) -> Dict[str, Any]:
        """
        Directly delegates to the injected mock agents (which have Chaos embedded).
        """
        result = {}
        
        # Simple routing based on task type since router is mocked
        if task.task_type in ["scheduling_request", "meeting_book"]:
            agent = AgentName.SCHEDULER
        elif task.task_type in ["company_intel", "meeting_prep"]:
            agent = AgentName.RESEARCHER
        else:
            agent = AgentName.RESEARCHER # Fallback for test

        try:
            if agent == AgentName.SCHEDULER:
                if task.task_type == "scheduling_request":
                    data = await self.scheduler_agent.generate_proposals(
                        task.parameters.get("prospect_timezone", "UTC"),
                        task.parameters.get("duration_minutes", 30)
                    )
                    result = {"proposals": data}
                elif task.task_type == "meeting_book":
                    data = await self.scheduler_agent.book_meeting(
                        task.parameters["prospect_email"],
                        task.parameters["start_time"],
                        task.parameters.get("duration_minutes", 30),
                        title="Stress Test"
                    )
                    result = {"booking": data}
                    
            elif agent == AgentName.RESEARCHER:
                if task.task_type == "company_intel":
                    data = await self.researcher_agent.research_company(
                        task.parameters["company_name"],
                        task.parameters["domain"]
                    )
                    result = {"intel": data}

            task.status = TaskStatus.COMPLETED
            task.result = result
            return {
                "task_id": task.id,
                "agent": agent.value,
                "status": "completed",
                "result": result
            }
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            raise e

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def chaos_monkey():
    return ChaosMonkey(failure_rate=0.0, max_delay=0.05) # Default: No failure, just jitter

@pytest.fixture
def stress_queen(chaos_monkey):
    scheduler = LegacyMockScheduler(chaos_monkey)
    researcher = LegacyMockResearcher(chaos_monkey)
    
    gatekeeper = EnhancedGatekeeperQueue(test_mode=True)
    gatekeeper.approval_engine.submit_request = MagicMock(return_value=ApprovalRequest(
        request_id="req_stress_1", status="approved", requester_agent="stress_queen", 
        action_type="test", payload={}, risk_score=0.1, created_at="", updated_at=""
    ))
    
    queen = StressQueen(scheduler, researcher, gatekeeper)
    return queen

# ============================================================================
# TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_high_concurrency_load(stress_queen):
    """
    Stress Test 1: Concurrency
    Launch 50 tasks simultaneously and ensure they all complete correctly.
    """
    # Using low jitter, 0% failure for pure throughput test
    stress_queen.scheduler_agent.chaos.failure_rate = 0.0
    stress_queen.scheduler_agent.chaos.max_delay = 0.01 
    
    # Pre-configure router to always pick Researcher for this test
    stress_queen.router.select_agent.return_value = AgentName.RESEARCHER
    
    # Generate batch of tasks
    num_tasks = 50
    tasks = []
    for i in range(num_tasks):
        task = stress_queen.create_task(
            task_type="company_intel",
            parameters={"company_name": f"Company {i}", "domain": f"company{i}.com"}
        )
        tasks.append(task)
        
    # Submit all tasks (simulate burst)
    start_time = time.time()
    await asyncio.gather(*(stress_queen._execute_task(t) for t in tasks))
    end_time = time.time()
    
    # Validation
    successful = [t for t in tasks if t.status.value == "completed"]
    assert len(successful) == num_tasks
    
    duration = end_time - start_time
    print(f"\n[Performance] Processed {num_tasks} tasks in {duration:.2f}s (Throughput: {num_tasks/duration:.1f} tasks/s)")


@pytest.mark.asyncio
async def test_chaos_resilience(stress_queen):
    """
    Stress Test 2: Chaos Monkey
    Inject 20% failure rate and verify system handles exceptions gracefully 
    (i.e., tasks marked as failed, system doesn't crash).
    """
    stress_queen.scheduler_agent.chaos.failure_rate = 0.2
    
    num_tasks = 20
    tasks = []
    for i in range(num_tasks):
        task = stress_queen.create_task(
            task_type="scheduling_request",
            parameters={"prospect_timezone": "UTC", "duration_minutes": 30}
        )
        tasks.append(task)
        
    # Execute batch with return_exceptions=True
    results = await asyncio.gather(*(stress_queen._execute_task(t) for t in tasks), return_exceptions=True)
    
    # Analyze
    completed = [t for t in tasks if t.status.value == "completed"]
    failed = [t for t in tasks if t.status.value == "failed"]
    
    filtered_results = [r for r in results if not isinstance(r, Exception)]
    failure_exceptions = [r for r in results if isinstance(r, Exception)]
    
    print(f"\n[Chaos] Completed: {len(completed)}, Failed: {len(failed)}")
    print(f"Exceptions Caught: {len(failure_exceptions)}")
    
    # Verification: Total tasks = Completed + Failed
    assert len(completed) + len(failed) == num_tasks
    
    # Verification: Failed tasks should have errors
    for t in failed:
        assert "monkey" in str(t.error).lower() or "chaos" in str(t.error).lower()
