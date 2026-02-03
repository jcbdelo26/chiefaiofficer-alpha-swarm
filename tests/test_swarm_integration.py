
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any

from execution.unified_queen_orchestrator import UnifiedQueen, Task, TaskCategory, AgentName, TaskPriority
from execution.scheduler_agent import SchedulerAgent
from execution.researcher_agent import ResearcherAgent
from execution.gatekeeper_queue import EnhancedGatekeeperQueue
from core.approval_engine import ApprovalResult, ApprovalRequest

# ============================================================================
# MOCKS & STUBS
# ============================================================================

class MockScheduler(SchedulerAgent):
    """Stubbed Scheduler that tracks calls."""
    def __init__(self):
        self.calendar = AsyncMock()
        self.booked_meetings = []

    async def generate_proposals(self, prospect_timezone: str, duration_minutes: int) -> list:
        return [{"start": "2026-01-24T10:00:00Z", "score": 1.0}]

    async def book_meeting(self, prospect_email: str, start_time: str, duration_minutes: int, title: str, with_zoom: bool = False):
        self.booked_meetings.append({
            "email": prospect_email,
            "time": start_time
        })
        return MagicMock(success=True, event_id="evt_integrated_123")

class MockResearcher(ResearcherAgent):
    """Stubbed Researcher."""
    async def research_company(self, company_name: str, domain: str):
        return MagicMock(
            company_name=company_name,
            industry="Integrated Tech",
            description=f"Analysis of {company_name}"
        )
    
    async def research_attendee(self, email: str, name: str, ghl_contact_id: str = None):
        return MagicMock(
            email=email,
            ghl_tags=["vip"],
            past_interactions=[]
        )

# ============================================================================
# INTEGRATION QUEEN
# ============================================================================

class IntegrationQueen(UnifiedQueen):
    """
    Queen subclass that actually dispatches to agent instances 
    instead of just simulating sleep.
    """
    def __init__(self, scheduler: SchedulerAgent, researcher: ResearcherAgent, gatekeeper: EnhancedGatekeeperQueue):
        # Bypass standard init to avoid side effects if needed, 
        # but we want standard init structure, just override execution.
        super().__init__()
        self.scheduler_agent = scheduler
        self.researcher_agent = researcher
        self.gatekeeper_agent = gatekeeper
        
        # Override router to be deterministic for tests if needed, 
        # or mock it in the test fixture.

    async def _simulate_task_execution(self, task: Task, agent: AgentName) -> Dict[str, Any]:
        """
        Override: Dispatch to the actual injected agent instances.
        """
        result = {}
        
        if agent == AgentName.SCHEDULER:
            if task.task_type == "scheduling_request":
                # Map parameters
                # Assuming task.parameters has 'prospect_timezone', 'duration_minutes'
                proposals = await self.scheduler_agent.generate_proposals(
                    prospect_timezone=task.parameters.get("prospect_timezone", "UTC"),
                    duration_minutes=task.parameters.get("duration_minutes", 30)
                )
                result = {"proposals": proposals}
            
            elif task.task_type == "meeting_book":
                booking = await self.scheduler_agent.book_meeting(
                    prospect_email=task.parameters["prospect_email"],
                    start_time=task.parameters["start_time"],
                    duration_minutes=task.parameters.get("duration_minutes", 30),
                    title=task.parameters.get("title", "Meeting"),
                    with_zoom=task.parameters.get("with_zoom", False)
                )
                result = {"booking": booking}

        elif agent == AgentName.RESEARCHER:
            if task.task_type == "company_intel":
                intel = await self.researcher_agent.research_company(
                    company_name=task.parameters["company_name"],
                    domain=task.parameters["domain"]
                )
                result = {"intel": intel}
            
            elif task.task_type == "meeting_prep":
                # Assuming simple attendee research
                intel = await self.researcher_agent.research_attendee(
                    email=task.parameters["email"],
                    name=task.parameters["name"]
                )
                result = {"intel": intel}

        elif agent == AgentName.GATEKEEPER:
            # Gatekeeper usually works via queue, but here we can simulate direct action
            pass

        return {
            "task_id": task.id,
            "agent": agent.value,
            "status": "completed",
            "result": result
        }

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def swarm_context():
    """Shared state for integration tests."""
    return {}

@pytest.fixture
def integration_queen():
    # Setup agents
    scheduler = MockScheduler()
    researcher = MockResearcher()
    
    # Gatekeeper Setup with Inner Mock
    gatekeeper = EnhancedGatekeeperQueue(test_mode=True)
    gatekeeper.approval_engine.submit_request = MagicMock(return_value=ApprovalRequest(
        request_id="req_int_1", status="pending", requester_agent="queen", action_type="test", payload={}, risk_score=0.1, created_at="", updated_at=""
    ))
    
    queen = IntegrationQueen(scheduler, researcher, gatekeeper)
    
    # Mock internal components
    queen.consensus_engine = AsyncMock() 
    queen.router = MagicMock() # Router methods are synchronous
    
    return queen

# ============================================================================
# TEST CASES
# ============================================================================

@pytest.mark.asyncio
async def test_queen_researcher_handoff(integration_queen):
    """
    Test 1: Queen -> Researcher
    Verify Queen correctly delegates a research task and captures the structured output.
    """
    # Setup Router to send to Researcher
    integration_queen.router.select_agent.return_value = AgentName.RESEARCHER
    
    # Create Task
    task = integration_queen.create_task(
        task_type="company_intel",
        parameters={"company_name": "TestCorp", "domain": "testcorp.com"},
        priority=TaskPriority.HIGH
    )
    
    # Execute
    await integration_queen.submit_task(task)
    await integration_queen._execute_task(task)
    
    # Verify
    assert task.status.value == "completed"
    assert task.result["agent"] == "RESEARCHER"
    # Note: result["result"] contains the "intel" key from our mock
    assert task.result["result"]["intel"].company_name == "TestCorp"

@pytest.mark.asyncio
async def test_researcher_scheduler_chain(integration_queen):
    """
    Test 2: Researcher -> Scheduler Chain (Simulated)
    Simulate a simplified control loop where Research Output feeds Scheduling Input.
    """
    # Step 1: Research
    integration_queen.router.select_agent.return_value = AgentName.RESEARCHER
    r_task = integration_queen.create_task(
        task_type="meeting_prep",
        parameters={"email": "ceo@bigcorp.com", "name": "Big CEO"}
    )
    await integration_queen._execute_task(r_task)
    
    assert r_task.status.value == "completed"
    intel = r_task.result["result"]["intel"]
    assert "vip" in intel.ghl_tags
    
    # Step 2: Decision (Simulated Logic: "If VIP, Book Meeting")
    if "vip" in intel.ghl_tags:
        integration_queen.router.select_agent.return_value = AgentName.SCHEDULER
        s_task = integration_queen.create_task(
            task_type="meeting_book",
            parameters={
                "prospect_email": intel.email, # Handoff data
                "start_time": "2026-01-25T14:00:00Z",
                "title": f"VIP Meeting with {intel.email}"
            }
        )
        await integration_queen._execute_task(s_task)
        
        assert s_task.status.value == "completed"
        assert s_task.result["result"]["booking"].success is True
        
        # Verify Scheduler State
        booked = integration_queen.scheduler_agent.booked_meetings
        assert len(booked) == 1
        assert booked[0]["email"] == "ceo@bigcorp.com"

@pytest.mark.asyncio
async def test_lead_to_meeting_e2e(integration_queen):
    """
    Test 3: Full End-to-End Simulation
    Queen coordinates a multi-step workflow.
    """
    # 1. Lead Gen (Simulated)
    lead = {"company": "StartupAI", "domain": "startup.ai"}
    
    # 2. Research
    integration_queen.router.select_agent.return_value = AgentName.RESEARCHER
    task1 = integration_queen.create_task("company_intel", {"company_name": lead["company"], "domain": lead["domain"]})
    await integration_queen._execute_task(task1)
    
    # 3. Schedule
    integration_queen.router.select_agent.return_value = AgentName.SCHEDULER
    task2 = integration_queen.create_task("scheduling_request", {"prospect_timezone": "EST", "duration_minutes": 45})
    await integration_queen._execute_task(task2)
    
    proposals = task2.result["result"]["proposals"]
    assert len(proposals) > 0
    
    # 4. Book
    # Router is already set to scheduler, but good practice to reset if logic was dynamic
    selected_time = proposals[0]["start"]
    task3 = integration_queen.create_task("meeting_book", {
        "prospect_email": "founder@startup.ai",
        "start_time": selected_time,
        "title": "Demo"
    })
    await integration_queen._execute_task(task3)
    
    assert task3.status.value == "completed"
    assert integration_queen.scheduler_agent.booked_meetings[0]["time"] == selected_time
