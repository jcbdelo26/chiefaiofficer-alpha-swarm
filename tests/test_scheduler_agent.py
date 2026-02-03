#!/usr/bin/env python3
"""
Tests for Scheduler Agent - Day 11
===================================
Tests for calendar scheduling, time proposals, and exchange handling.
"""

import pytest
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.scheduler_agent import (
    SchedulerAgent,
    SchedulingRequest,
    SchedulingStatus,
    ExchangeType,
    TimeProposal,
    BookingResult,
    SchedulingMetrics,
    MAX_SCHEDULING_EXCHANGES,
    DEFAULT_MEETING_DURATION,
    WORKING_HOURS_START,
    WORKING_HOURS_END,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_hive_mind(tmp_path):
    """Create temporary hive-mind directory."""
    hive_mind = tmp_path / ".hive-mind"
    hive_mind.mkdir()
    (hive_mind / "scheduler").mkdir()
    return hive_mind


@pytest.fixture
def scheduler(temp_hive_mind, monkeypatch):
    """Create scheduler agent with mocked hive-mind (no real calendar)."""
    monkeypatch.setattr(
        "execution.scheduler_agent.PROJECT_ROOT",
        temp_hive_mind.parent
    )
    agent = SchedulerAgent()
    # Force mock mode - no real calendar API calls
    agent.calendar = None
    return agent


# ============================================================================
# Test: Initialization
# ============================================================================

class TestSchedulerInitialization:
    """Test scheduler agent initialization."""
    
    def test_scheduler_creates_without_calendar(self, scheduler):
        """Test scheduler initializes in mock mode."""
        assert scheduler is not None
        # May or may not have calendar depending on dependencies
    
    def test_scheduler_has_patterns(self, scheduler):
        """Test scheduler has learned patterns."""
        assert scheduler._patterns is not None
        assert "preferred_hours" in scheduler._patterns
        assert "avoid_hours" in scheduler._patterns
        assert "success_by_day" in scheduler._patterns
    
    def test_scheduler_directory_created(self, scheduler, temp_hive_mind):
        """Test scheduler creates its directory."""
        scheduler_dir = temp_hive_mind / "scheduler"
        assert scheduler_dir.exists()


# ============================================================================
# Test: Time Proposals
# ============================================================================

class TestTimeProposals:
    """Test time proposal generation."""
    
    @pytest.mark.asyncio
    async def test_generate_proposals_returns_list(self, scheduler):
        """Test proposals are generated as a list."""
        proposals = await scheduler.generate_proposals(
            prospect_timezone="America/New_York",
            duration_minutes=30
        )
        
        assert isinstance(proposals, list)
        assert len(proposals) >= 3
        assert len(proposals) <= 5
    
    @pytest.mark.asyncio
    async def test_proposals_have_correct_structure(self, scheduler):
        """Test each proposal has required fields."""
        proposals = await scheduler.generate_proposals(
            prospect_timezone="America/New_York"
        )
        
        for prop in proposals:
            assert hasattr(prop, "proposal_id")
            assert hasattr(prop, "start_time")
            assert hasattr(prop, "end_time")
            assert hasattr(prop, "timezone")
            assert hasattr(prop, "duration_minutes")
            assert hasattr(prop, "display_text")
            assert hasattr(prop, "confidence")
    
    @pytest.mark.asyncio
    async def test_proposals_respect_num_proposals(self, scheduler):
        """Test correct number of proposals generated."""
        for num in [3, 4, 5]:
            proposals = await scheduler.generate_proposals(
                prospect_timezone="PST",
                num_proposals=num
            )
            assert len(proposals) == num
    
    @pytest.mark.asyncio
    async def test_proposals_use_correct_timezone(self, scheduler):
        """Test proposals use resolved timezone."""
        proposals = await scheduler.generate_proposals(
            prospect_timezone="PST"  # Should resolve to America/Los_Angeles
        )
        
        for prop in proposals:
            assert prop.timezone in ["America/Los_Angeles", "PST"]
    
    @pytest.mark.asyncio
    async def test_proposals_have_confidence_scores(self, scheduler):
        """Test proposals have confidence scores between 0 and 1."""
        proposals = await scheduler.generate_proposals(
            prospect_timezone="America/New_York"
        )
        
        for prop in proposals:
            assert 0.0 <= prop.confidence <= 1.0


# ============================================================================
# Test: Scheduling Request
# ============================================================================

class TestSchedulingRequest:
    """Test scheduling request creation and handling."""
    
    @pytest.mark.asyncio
    async def test_create_request_returns_tuple(self, scheduler):
        """Test create_scheduling_request returns request and proposals."""
        request, proposals = await scheduler.create_scheduling_request(
            prospect_email="test@example.com",
            prospect_name="Test User",
            prospect_timezone="EST",
            prospect_company="Test Corp"
        )
        
        assert isinstance(request, SchedulingRequest)
        assert isinstance(proposals, list)
    
    @pytest.mark.asyncio
    async def test_request_has_correct_fields(self, scheduler):
        """Test request has all required fields."""
        request, _ = await scheduler.create_scheduling_request(
            prospect_email="test@example.com",
            prospect_name="Test User",
            prospect_timezone="EST",
            prospect_company="Test Corp"
        )
        
        assert request.prospect_email == "test@example.com"
        assert request.prospect_name == "Test User"
        assert request.prospect_company == "Test Corp"
        assert request.request_id is not None
        assert request.status == SchedulingStatus.AWAITING_RESPONSE
        assert request.exchange_count == 1
    
    @pytest.mark.asyncio
    async def test_request_stored_in_active_requests(self, scheduler):
        """Test request is stored in active requests."""
        request, _ = await scheduler.create_scheduling_request(
            prospect_email="test@example.com",
            prospect_name="Test User",
            prospect_timezone="EST",
            prospect_company="Test Corp"
        )
        
        assert request.request_id in scheduler._active_requests
    
    @pytest.mark.asyncio
    async def test_request_timezone_resolved(self, scheduler):
        """Test timezone aliases are resolved."""
        request, _ = await scheduler.create_scheduling_request(
            prospect_email="test@example.com",
            prospect_name="Test User",
            prospect_timezone="PST",  # Alias
            prospect_company="Test Corp"
        )
        
        assert request.prospect_timezone == "America/Los_Angeles"


# ============================================================================
# Test: Prospect Response Handling
# ============================================================================

class TestProspectResponseHandling:
    """Test handling of prospect responses."""
    
    @pytest.mark.asyncio
    async def test_handle_acceptance(self, scheduler):
        """Test handling acceptance response."""
        request, proposals = await scheduler.create_scheduling_request(
            prospect_email="test@example.com",
            prospect_name="Test User",
            prospect_timezone="EST",
            prospect_company="Test Corp"
        )
        
        result = await scheduler.handle_prospect_response(
            request_id=request.request_id,
            response_type="accept",
            selected_time=proposals[0].start_time_utc
        )
        
        assert result["success"] == True
        assert result["action"] == "booked"
        assert "event_id" in result
    
    @pytest.mark.asyncio
    async def test_handle_rejection(self, scheduler):
        """Test handling rejection response."""
        request, _ = await scheduler.create_scheduling_request(
            prospect_email="test@example.com",
            prospect_name="Test User",
            prospect_timezone="EST",
            prospect_company="Test Corp"
        )
        
        result = await scheduler.handle_prospect_response(
            request_id=request.request_id,
            response_type="reject",
            message="Not interested"
        )
        
        assert result["success"] == True
        assert result["action"] == "rejected"
        assert scheduler._active_requests[request.request_id].status == SchedulingStatus.CANCELLED
    
    @pytest.mark.asyncio
    async def test_handle_counter_proposal(self, scheduler):
        """Test handling counter proposal."""
        request, _ = await scheduler.create_scheduling_request(
            prospect_email="test@example.com",
            prospect_name="Test User",
            prospect_timezone="EST",
            prospect_company="Test Corp"
        )
        
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        counter_time = tomorrow.replace(hour=10, minute=0).isoformat()
        
        result = await scheduler.handle_prospect_response(
            request_id=request.request_id,
            response_type="counter",
            counter_times=[counter_time]
        )
        
        assert result["success"] == True
        assert result["action"] in ["review_counter", "send_counter"]
    
    @pytest.mark.asyncio
    async def test_handle_reschedule(self, scheduler):
        """Test handling reschedule request."""
        request, _ = await scheduler.create_scheduling_request(
            prospect_email="test@example.com",
            prospect_name="Test User",
            prospect_timezone="EST",
            prospect_company="Test Corp"
        )
        
        result = await scheduler.handle_prospect_response(
            request_id=request.request_id,
            response_type="reschedule",
            message="Need to move our call"
        )
        
        assert result["success"] == True
        assert result["action"] == "rescheduling"
        assert "proposals" in result
    
    @pytest.mark.asyncio
    async def test_invalid_request_id(self, scheduler):
        """Test handling with invalid request ID."""
        result = await scheduler.handle_prospect_response(
            request_id="INVALID-ID",
            response_type="accept",
            selected_time="2026-01-23T10:00:00Z"
        )
        
        assert result["success"] == False
        assert "error" in result


# ============================================================================
# Test: Escalation
# ============================================================================

class TestEscalation:
    """Test scheduling escalation after max exchanges."""
    
    @pytest.mark.asyncio
    async def test_escalation_after_max_exchanges(self, scheduler):
        """Test escalation triggers after MAX_SCHEDULING_EXCHANGES."""
        request, _ = await scheduler.create_scheduling_request(
            prospect_email="test@example.com",
            prospect_name="Test User",
            prospect_timezone="EST",
            prospect_company="Test Corp"
        )
        
        # Simulate multiple exchanges
        for _ in range(MAX_SCHEDULING_EXCHANGES - 1):
            tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
            await scheduler.handle_prospect_response(
                request_id=request.request_id,
                response_type="counter",
                counter_times=[tomorrow.isoformat()]
            )
        
        # Next exchange should trigger escalation
        result = await scheduler.handle_prospect_response(
            request_id=request.request_id,
            response_type="counter",
            counter_times=[(datetime.now(timezone.utc) + timedelta(days=2)).isoformat()]
        )
        
        assert result["action"] == "escalated"
        assert scheduler._active_requests[request.request_id].status == SchedulingStatus.ESCALATED
    
    @pytest.mark.asyncio
    async def test_escalation_creates_file(self, scheduler, temp_hive_mind):
        """Test escalation creates an escalation file."""
        request, _ = await scheduler.create_scheduling_request(
            prospect_email="test@example.com",
            prospect_name="Test User",
            prospect_timezone="EST",
            prospect_company="Test Corp"
        )
        
        # Force escalation
        request.exchange_count = MAX_SCHEDULING_EXCHANGES - 1
        
        result = await scheduler.handle_prospect_response(
            request_id=request.request_id,
            response_type="counter",
            counter_times=["2026-01-25T10:00:00Z"]
        )
        
        # Check escalation file exists
        escalation_file = temp_hive_mind / "scheduler" / f"escalation_{request.request_id}.json"
        assert escalation_file.exists()


# ============================================================================
# Test: Booking
# ============================================================================

class TestBooking:
    """Test meeting booking functionality."""
    
    @pytest.mark.asyncio
    async def test_book_meeting_success(self, scheduler):
        """Test successful meeting booking."""
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        # Use 14:00 UTC = 9:00 AM EST to be within working hours
        start_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0).isoformat()
        
        result = await scheduler.book_meeting(
            prospect_email="test@example.com",
            start_time=start_time,
            duration_minutes=30,
            title="Test Meeting",
            with_zoom=True
        )
        
        assert isinstance(result, BookingResult)
        assert result.success == True
        assert result.event_id is not None
        assert result.zoom_link is not None
    
    @pytest.mark.asyncio
    async def test_book_meeting_calculates_end_time(self, scheduler):
        """Test meeting end time is calculated correctly."""
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        # Use 14:00 UTC = 9:00 AM EST to be within working hours
        start_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0).isoformat()
        
        result = await scheduler.book_meeting(
            prospect_email="test@example.com",
            start_time=start_time,
            duration_minutes=45,
            title="Test Meeting"
        )
        
        start_dt = datetime.fromisoformat(result.start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(result.end_time.replace('Z', '+00:00'))
        
        assert (end_dt - start_dt).total_seconds() == 45 * 60
    
    @pytest.mark.asyncio
    async def test_book_meeting_invalid_time(self, scheduler):
        """Test booking with invalid time fails gracefully."""
        result = await scheduler.book_meeting(
            prospect_email="test@example.com",
            start_time="invalid-time",
            title="Test Meeting"
        )
        
        assert result.success == False
        assert result.error is not None


# ============================================================================
# Test: Timezone Handling
# ============================================================================

class TestTimezoneHandling:
    """Test timezone resolution and conversion."""
    
    def test_resolve_pst(self, scheduler):
        """Test PST resolves to America/Los_Angeles."""
        resolved = scheduler._resolve_timezone("PST")
        assert resolved == "America/Los_Angeles"
    
    def test_resolve_est(self, scheduler):
        """Test EST resolves to America/New_York."""
        resolved = scheduler._resolve_timezone("EST")
        assert resolved == "America/New_York"
    
    def test_resolve_iana_passthrough(self, scheduler):
        """Test IANA names pass through unchanged."""
        resolved = scheduler._resolve_timezone("Asia/Tokyo")
        assert resolved == "Asia/Tokyo"
    
    def test_resolve_empty_default(self, scheduler):
        """Test empty timezone returns default."""
        resolved = scheduler._resolve_timezone("")
        assert resolved == "America/New_York"


# ============================================================================
# Test: Metrics and Patterns
# ============================================================================

class TestMetricsAndPatterns:
    """Test metrics collection and pattern learning."""
    
    def test_get_metrics_summary(self, scheduler):
        """Test metrics summary structure."""
        summary = scheduler.get_metrics_summary()
        
        assert "total_requests" in summary
        assert "successful_bookings" in summary
        assert "success_rate" in summary
        assert "avg_exchanges_to_book" in summary
        assert "patterns" in summary
    
    def test_patterns_have_required_keys(self, scheduler):
        """Test patterns have all required keys."""
        patterns = scheduler._patterns
        
        assert "preferred_hours" in patterns
        assert "avoid_hours" in patterns
        assert "success_by_day" in patterns
        assert "avg_exchanges_to_book" in patterns


# ============================================================================
# Test: Request Status
# ============================================================================

class TestRequestStatus:
    """Test request status retrieval."""
    
    @pytest.mark.asyncio
    async def test_get_request_status(self, scheduler):
        """Test getting status of a request."""
        request, _ = await scheduler.create_scheduling_request(
            prospect_email="test@example.com",
            prospect_name="Test User",
            prospect_timezone="EST",
            prospect_company="Test Corp"
        )
        
        status = scheduler.get_request_status(request.request_id)
        
        assert status is not None
        assert status["request_id"] == request.request_id
        assert status["status"] == "awaiting_response"
        assert "exchanges" in status
    
    def test_get_status_invalid_id(self, scheduler):
        """Test getting status with invalid ID returns None."""
        status = scheduler.get_request_status("INVALID-ID")
        assert status is None


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
