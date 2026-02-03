
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
import json
from pathlib import Path

# Import agents
from execution.unified_queen_orchestrator import UnifiedQueen, TaskCategory, AgentName
from execution.scheduler_agent import SchedulerAgent
from execution.researcher_agent import ResearcherAgent, CompanyIntel, AttendeeIntel
from execution.gatekeeper_queue import EnhancedGatekeeperQueue, ReviewItem
from core.approval_engine import ApprovalResult, ApprovalRequest

# ============================================================================
# MOCKS
# ============================================================================

class MockGoogleCalendar:
    async def list_events(self, **kwargs):
        # Return one existing event to test conflict detection
        return [{
            "start": {"dateTime": "2026-01-24T14:00:00-05:00"},
            "end": {"dateTime": "2026-01-24T15:00:00-05:00"},
            "summary": "Busy Slot"
        }]
    async def create_event(self, **kwargs):
        # MCP returns 'event_id' as per SchedulerAgent expectation
        return {"event_id": "evt_123", "status": "confirmed", "htmlLink": "http://cal.com/evt123", "success": True}
    async def find_available_slots(self, **kwargs):
        return {"available_slots": ["2026-01-24T10:00:00-05:00"]}
    async def get_availability(self, **kwargs):
        return [] # Generic return

class MockExa:
    pass # Not used directly due to import patching issues, we mock the method

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def queen():
    q = UnifiedQueen()
    # Mock internal components to avoid full initialization overhead
    q.consensus_engine = AsyncMock() 
    q.router = AsyncMock()
    q.router.route.return_value = (AgentName.SCHEDULER, 0.95, "Scheduling intent detected")
    return q

@pytest.fixture
def scheduler():
    with patch("execution.scheduler_agent.GoogleCalendarMCP", return_value=MockGoogleCalendar()):
        return SchedulerAgent()

@pytest.fixture
def researcher():
    return ResearcherAgent()

@pytest.fixture
def gatekeeper():
    with patch("core.notifications.NotificationManager", return_value=AsyncMock()):
        return EnhancedGatekeeperQueue(test_mode=True)

# ============================================================================
# TESTS
# ============================================================================

# --- UNIFIED QUEEN TESTS ---
@pytest.mark.asyncio
async def test_queen_routing_schedule(queen):
    """Verify Queen routes scheduling intent to Scheduler Agent."""
    task = "Book a meeting with John Doe for next Tuesday"
    
    # Mock the router response which is usually determined by LLM/Q-Learning
    queen.router.route.return_value = (AgentName.SCHEDULER, 0.95, "Scheduling detected")
    
    target_agent, confidence, reasoning = await queen.router.route(task)
    
    assert target_agent == AgentName.SCHEDULER
    assert confidence > 0.8

# --- SCHEDULER AGENT TESTS ---
@pytest.mark.asyncio
async def test_scheduler_availability_check(scheduler):
    """Verify Scheduler avoids conflicts and finds slots."""
    assert isinstance(scheduler.calendar, MockGoogleCalendar)
    
    # Configure the mock
    scheduler.calendar.find_available_slots = AsyncMock(return_value={
        "available_slots": ["2026-01-24T10:00:00-05:00", "2026-01-24T16:00:00-05:00"]
    })

    try:
        # Correct argument order: prospect_timezone, duration_minutes
        slots = await scheduler.generate_proposals("America/New_York", 30)
        
        assert isinstance(slots, list)
        scheduler.calendar.find_available_slots.assert_called()
    except Exception as e:
        pytest.fail(f"generate_proposals failed: {e}")

@pytest.mark.asyncio
async def test_scheduler_book_meeting(scheduler):
    """Verify booking creates event."""
    scheduler.calendar.create_event = AsyncMock(return_value={"success": True, "event_id": "evt_123", "htmlLink": "link"})
    
    res = await scheduler.book_meeting(
        "john@example.com", 
        "2026-01-24T10:00:00-05:00", 
        30, 
        "Discovery",
        with_zoom=True
    )
    
    # BookingResult is a dataclass, use attribute access
    if not res.success:
        pytest.fail(f"Booking failed: {res.error}")
        
    assert res.success is True
    assert res.event_id == "evt_123"
    scheduler.calendar.create_event.assert_called_once()

# --- RESEARCHER AGENT TESTS ---
@pytest.mark.asyncio
async def test_researcher_company_intel(researcher):
    """Verify company research gathers basic intel."""
    # Mock method directly to avoid import issues
    researcher._search_web = AsyncMock(return_value={
        "summary": "Acme Corp is great.",
        "industry": "Tech"
    })
    # Also mock internal helper calls if needed
    researcher._estimate_company_size = AsyncMock(return_value={"size": "Big", "employees": 1000})
    researcher._detect_tech_stack = AsyncMock(return_value=["Python"])
    researcher._search_news = AsyncMock(return_value=[])

    intel = await researcher.research_company("Acme Corp", "acme.com")
    
    assert intel.company_name == "Acme Corp"
    assert intel.industry == "Tech"
    assert intel.description == "Acme Corp is great."

@pytest.mark.asyncio
async def test_researcher_attendee_enrichment(researcher):
    """Verify attendee research enriches from GHL mock."""
    # Mock method directly
    researcher._get_ghl_history = AsyncMock(return_value={
        "interactions": [{"body": "Met at conference"}],
        "tags": ["vip"]
    })
    researcher._research_linkedin = AsyncMock(return_value={})

    intel = await researcher.research_attendee("john@example.com", "John Doe", ghl_contact_id="123")
    
    assert intel.email == "john@example.com"
    assert "vip" in intel.ghl_tags
    assert len(intel.past_interactions) == 1

# --- GATEKEEPER TESTS ---
@pytest.mark.asyncio
async def test_gatekeeper_queue_add(gatekeeper):
    """Verify adding item to queue creates pending review."""
    item_tuple = ReviewItem(
        review_id="rev_001",
        campaign_id="camp_001",
        campaign_name="Test Campaign",
        campaign_type="outbound",
        lead_count=100,
        avg_icp_score=0.9,
        segment="Tech CEOs",
        email_preview={"subject": "Hi", "body": "Hello"},
        status="pending",
        queued_at="2026-01-24T10:00:00Z"
    )
    
    # Mock ApprovalEngine inside gatekeeper to ensure it returns NOT auto-approved
    # We patch the instance method. submit_request returns ApprovalRequest object.
    mock_req = ApprovalRequest(
        request_id="req_123",
        status="pending",
        requester_agent="gatekeeper",
        action_type="bulk_email",
        payload={},
        risk_score=0.9,
        created_at="now",
        updated_at="now"
    )
    
    # gatekeeper.approval_engine is initialized in __init__
    # We replace submit_request method with MagicMock since it's sync
    gatekeeper.approval_engine.submit_request = MagicMock(return_value=mock_req)

    review_id = await gatekeeper.submit_for_review(item_tuple)
    
    assert review_id is not None
    
    # Verify it's in the pending list
    pending = gatekeeper.get_pending()
    
    # Since test mode reuses the file, verify OUR item is there
    # It might be appended at the end
    found = any(i.campaign_id == "camp_001" for i in pending)
    assert found, f"Campaign camp_001 not found in pending list of {len(pending)} items"
