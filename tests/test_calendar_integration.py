#!/usr/bin/env python3
"""
Google Calendar Integration Tests
==================================
Tests that verify real Calendar API behavior.

Run with credentials:
    GOOGLE_CALENDAR_TEST=1 pytest tests/test_calendar_integration.py -v

Run in mock mode (default):
    pytest tests/test_calendar_integration.py -v
"""

import os
import sys
import pytest
import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-servers" / "google-calendar-mcp"))

from server import GoogleCalendarMCP, CalendarEvent, TimeSlot
from config import CalendarConfig, get_config, set_config
from guardrails import CalendarGuardrails, BookingValidation, WorkingHours

INTEGRATION_MODE = os.getenv("GOOGLE_CALENDAR_TEST", "0") == "1"

skip_if_no_creds = pytest.mark.skipif(
    not INTEGRATION_MODE,
    reason="Set GOOGLE_CALENDAR_TEST=1 to run integration tests"
)


@pytest.fixture
def mock_calendar_service():
    """Mock Google Calendar service for unit tests."""
    service = MagicMock()
    
    service.freebusy().query().execute.return_value = {
        "calendars": {
            "primary": {
                "busy": []
            }
        }
    }
    
    service.events().insert().execute.return_value = {
        "id": "mock_event_123",
        "summary": "Test Event",
        "start": {"dateTime": "2026-01-22T14:00:00-05:00"},
        "end": {"dateTime": "2026-01-22T14:30:00-05:00"},
        "htmlLink": "https://calendar.google.com/event?eid=mock_event_123"
    }
    
    service.events().list().execute.return_value = {
        "items": []
    }
    
    service.events().get().execute.return_value = {
        "id": "mock_event_123",
        "summary": "Existing Event",
        "start": {"dateTime": "2026-01-22T14:00:00-05:00"},
        "end": {"dateTime": "2026-01-22T14:30:00-05:00"},
        "attendees": []
    }
    
    service.events().delete().execute.return_value = None
    
    service.events().update().execute.return_value = {
        "id": "mock_event_123",
        "summary": "Updated Event",
        "htmlLink": "https://calendar.google.com/event?eid=mock_event_123"
    }
    
    return service


@pytest.fixture
def sample_events() -> List[Dict[str, Any]]:
    """Sample events for testing."""
    return [
        {
            "id": "event_1",
            "summary": "Team Meeting",
            "start": {"dateTime": "2026-01-22T10:00:00-05:00"},
            "end": {"dateTime": "2026-01-22T11:00:00-05:00"}
        },
        {
            "id": "event_2",
            "summary": "Lunch Break",
            "start": {"dateTime": "2026-01-22T12:00:00-05:00"},
            "end": {"dateTime": "2026-01-22T13:00:00-05:00"}
        },
        {
            "id": "event_3",
            "summary": "Client Call",
            "start": {"dateTime": "2026-01-22T15:00:00-05:00"},
            "end": {"dateTime": "2026-01-22T16:00:00-05:00"}
        }
    ]


@pytest.fixture
def busy_slots_from_events(sample_events) -> List[Dict[str, str]]:
    """Convert sample events to busy slots format."""
    return [
        {
            "start": event["start"]["dateTime"],
            "end": event["end"]["dateTime"]
        }
        for event in sample_events
    ]


@pytest.fixture
def calendar_mcp():
    """Create a GoogleCalendarMCP instance for testing."""
    mcp = GoogleCalendarMCP()
    mcp._request_times = []
    return mcp


@pytest.fixture
def calendar_mcp_with_mock_service(calendar_mcp, mock_calendar_service):
    """Calendar MCP with mocked service."""
    calendar_mcp._service = mock_calendar_service
    return calendar_mcp


class TestCalendarAvailability:
    """Test get_availability endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_availability_primary(self, calendar_mcp):
        """Test getting availability from primary calendar."""
        result = await calendar_mcp.get_availability(calendar_id="primary")
        
        assert result["success"] is True
        assert result["calendar_id"] == "primary"
        assert "start" in result
        assert "end" in result
        assert "busy_slots" in result
        assert "free_slots" in result
    
    @pytest.mark.asyncio
    async def test_availability_with_date_range(self, calendar_mcp):
        """Test availability with specific date range."""
        start = datetime.now(timezone.utc).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        
        result = await calendar_mcp.get_availability(
            calendar_id="primary",
            start_time=start,
            end_time=end
        )
        
        assert result["success"] is True
        assert result["start"] is not None
        assert result["end"] is not None
    
    @pytest.mark.asyncio
    async def test_availability_empty_calendar(self, calendar_mcp):
        """Test availability when no events exist (mock mode returns empty)."""
        result = await calendar_mcp.get_availability()
        
        assert result["success"] is True
        assert result["busy_slots"] == []
        assert len(result["free_slots"]) > 0
    
    @pytest.mark.asyncio
    async def test_availability_with_mock_service(self, calendar_mcp_with_mock_service, busy_slots_from_events):
        """Test availability with mocked busy slots."""
        calendar_mcp_with_mock_service._service.freebusy().query().execute.return_value = {
            "calendars": {
                "primary": {
                    "busy": busy_slots_from_events
                }
            }
        }
        
        result = await calendar_mcp_with_mock_service.get_availability()
        
        assert result["success"] is True
        assert len(result["busy_slots"]) == 3


class TestEventCreation:
    """Test create_event endpoint."""
    
    @pytest.mark.asyncio
    async def test_create_simple_event(self, calendar_mcp):
        """Create a basic event."""
        result = await calendar_mcp.create_event(
            title="Test Meeting",
            start_time="2026-01-22T14:00:00-05:00",
            end_time="2026-01-22T14:30:00-05:00"
        )
        
        assert result["success"] is True
        assert result["title"] == "Test Meeting"
        assert "event_id" in result
    
    @pytest.mark.asyncio
    async def test_create_event_with_attendees(self, calendar_mcp):
        """Create event with attendees."""
        result = await calendar_mcp.create_event(
            title="Team Sync",
            start_time="2026-01-22T14:00:00-05:00",
            end_time="2026-01-22T14:30:00-05:00",
            attendees=["alice@example.com", "bob@example.com"]
        )
        
        assert result["success"] is True
        assert result["attendees"] == ["alice@example.com", "bob@example.com"]
    
    @pytest.mark.asyncio
    async def test_create_event_with_zoom(self, calendar_mcp):
        """Create event with Zoom link."""
        zoom_url = "https://zoom.us/j/123456789"
        result = await calendar_mcp.create_event(
            title="Zoom Call",
            start_time="2026-01-22T14:00:00-05:00",
            end_time="2026-01-22T14:30:00-05:00",
            zoom_link=zoom_url
        )
        
        assert result["success"] is True
        assert result["zoom_link"] == zoom_url
    
    @pytest.mark.asyncio
    async def test_create_event_outside_hours_fails(self, calendar_mcp):
        """Verify guardrails block after-hours booking."""
        result = await calendar_mcp.create_event(
            title="Late Night Meeting",
            start_time="2026-01-22T23:00:00-05:00",
            end_time="2026-01-22T23:30:00-05:00"
        )
        
        assert result["success"] is False
        assert "error" in result
        assert "working hours" in result["error"].lower() or "after" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_create_event_before_hours_fails(self, calendar_mcp):
        """Verify guardrails block before-hours booking."""
        result = await calendar_mcp.create_event(
            title="Early Bird Meeting",
            start_time="2026-01-22T06:00:00-05:00",
            end_time="2026-01-22T06:30:00-05:00"
        )
        
        assert result["success"] is False
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_double_booking_prevention(self, calendar_mcp_with_mock_service):
        """Verify mutex prevents double booking."""
        calendar_mcp_with_mock_service._service.freebusy().query().execute.return_value = {
            "calendars": {
                "primary": {
                    "busy": [
                        {
                            "start": "2026-01-22T14:00:00-05:00",
                            "end": "2026-01-22T15:00:00-05:00"
                        }
                    ]
                }
            }
        }
        
        result = await calendar_mcp_with_mock_service.create_event(
            title="Conflicting Meeting",
            start_time="2026-01-22T14:30:00-05:00",
            end_time="2026-01-22T15:30:00-05:00"
        )
        
        assert result["success"] is False
        assert "double-booking" in result["error"].lower() or "no longer available" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_create_event_weekend_fails(self, calendar_mcp):
        """Verify guardrails block weekend booking by default."""
        result = await calendar_mcp.create_event(
            title="Weekend Meeting",
            start_time="2026-01-24T14:00:00-05:00",  # Saturday
            end_time="2026-01-24T14:30:00-05:00"
        )
        
        assert result["success"] is False
        assert "weekend" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_create_event_too_long_fails(self, calendar_mcp):
        """Verify guardrails block overly long meetings."""
        result = await calendar_mcp.create_event(
            title="Marathon Meeting",
            start_time="2026-01-22T10:00:00-05:00",
            end_time="2026-01-22T14:00:00-05:00"  # 4 hours
        )
        
        assert result["success"] is False
        assert "exceeds maximum" in result["error"]


class TestFindSlots:
    """Test find_available_slots endpoint."""
    
    @pytest.mark.asyncio
    async def test_find_30min_slots(self, calendar_mcp):
        """Find 30-minute slots."""
        result = await calendar_mcp.find_available_slots(
            duration_minutes=30,
            working_hours_start=9,
            working_hours_end=17
        )
        
        assert result["success"] is True
        assert result["duration_minutes"] == 30
        assert len(result["available_slots"]) > 0
        
        for slot in result["available_slots"]:
            assert slot["duration_minutes"] == 30
    
    @pytest.mark.asyncio
    async def test_find_60min_slots(self, calendar_mcp):
        """Find 60-minute slots."""
        result = await calendar_mcp.find_available_slots(
            duration_minutes=60,
            working_hours_start=9,
            working_hours_end=17
        )
        
        assert result["success"] is True
        assert result["duration_minutes"] == 60
    
    @pytest.mark.asyncio
    async def test_find_slots_respects_buffer(self, calendar_mcp_with_mock_service):
        """Verify 15-min buffer is enforced."""
        calendar_mcp_with_mock_service._service.freebusy().query().execute.return_value = {
            "calendars": {
                "primary": {
                    "busy": [
                        {
                            "start": "2026-01-22T10:00:00+00:00",
                            "end": "2026-01-22T11:00:00+00:00"
                        }
                    ]
                }
            }
        }
        
        result = await calendar_mcp_with_mock_service.find_available_slots(
            duration_minutes=30,
            buffer_minutes=15,
            working_hours_start=9,
            working_hours_end=17
        )
        
        assert result["success"] is True
        
        for slot in result["available_slots"]:
            slot_start = datetime.fromisoformat(slot["start"].replace("Z", "+00:00"))
            slot_end = datetime.fromisoformat(slot["end"].replace("Z", "+00:00"))
            
            busy_start = datetime.fromisoformat("2026-01-22T10:00:00+00:00")
            busy_end = datetime.fromisoformat("2026-01-22T11:00:00+00:00")
            
            if slot_start.date() == busy_start.date():
                assert slot_end <= busy_start - timedelta(minutes=15) or \
                       slot_start >= busy_end + timedelta(minutes=15)
    
    @pytest.mark.asyncio
    async def test_find_slots_working_hours_only(self, calendar_mcp):
        """Verify only working hours slots returned."""
        result = await calendar_mcp.find_available_slots(
            duration_minutes=30,
            working_hours_start=9,
            working_hours_end=17
        )
        
        assert result["success"] is True
        assert result["working_hours"] == "9:00-17:00"
        
        for slot in result["available_slots"]:
            start = datetime.fromisoformat(slot["start"].replace("Z", "+00:00"))
            assert start.hour >= 9
            end = datetime.fromisoformat(slot["end"].replace("Z", "+00:00"))
            assert end.hour <= 17
    
    @pytest.mark.asyncio
    async def test_find_slots_multiple_calendars(self, calendar_mcp):
        """Find slots across multiple calendars."""
        result = await calendar_mcp.find_available_slots(
            calendar_ids=["primary", "secondary@example.com"],
            duration_minutes=30
        )
        
        assert result["success"] is True
        assert "primary" in result["calendar_ids"]
        assert "secondary@example.com" in result["calendar_ids"]


class TestRateLimits:
    """Test rate limiting behavior."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_tracking(self, calendar_mcp):
        """Verify rate limit counter works."""
        initial_count = len(calendar_mcp._request_times)
        
        await calendar_mcp.get_availability()
        
        assert len(calendar_mcp._request_times) == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, calendar_mcp):
        """Verify error when rate limit exceeded."""
        calendar_mcp._request_times = [time.time()] * 100
        
        result = await calendar_mcp.get_availability()
        
        assert result["success"] is False
        assert "rate limit" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_rate_limit_clears_after_hour(self, calendar_mcp):
        """Verify old requests clear from rate limit."""
        old_time = time.time() - 3700  # Over an hour ago
        calendar_mcp._request_times = [old_time] * 50
        
        result = await calendar_mcp.get_availability()
        
        assert result["success"] is True
        assert len(calendar_mcp._request_times) == 1


class TestEventOperations:
    """Test update and delete event operations."""
    
    @pytest.mark.asyncio
    async def test_update_event(self, calendar_mcp):
        """Test updating an event."""
        result = await calendar_mcp.update_event(
            event_id="mock_event_123",
            updates={"title": "Updated Meeting"}
        )
        
        assert result["success"] is True
        assert "title" in result.get("updated_fields", [])
    
    @pytest.mark.asyncio
    async def test_delete_event(self, calendar_mcp):
        """Test deleting an event."""
        result = await calendar_mcp.delete_event(event_id="mock_event_123")
        
        assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_get_events(self, calendar_mcp):
        """Test getting events list."""
        result = await calendar_mcp.get_events()
        
        assert result["success"] is True
        assert "events" in result
        assert "count" in result


class TestMCPTools:
    """Test MCP tool definitions."""
    
    def test_get_tools_returns_all_tools(self, calendar_mcp):
        """Verify all expected tools are defined."""
        tools = calendar_mcp.get_tools()
        
        tool_names = [t["name"] for t in tools]
        expected_tools = [
            "get_availability",
            "create_event",
            "update_event",
            "delete_event",
            "get_events",
            "find_available_slots"
        ]
        
        for expected in expected_tools:
            assert expected in tool_names
    
    def test_tool_schemas_valid(self, calendar_mcp):
        """Verify tool schemas have required fields."""
        tools = calendar_mcp.get_tools()
        
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert "type" in tool["inputSchema"]
            assert tool["inputSchema"]["type"] == "object"


@skip_if_no_creds
class TestRealAPI:
    """Integration tests that hit real Google API."""
    
    @pytest.mark.asyncio
    async def test_real_availability_check(self):
        """Real API: Check availability."""
        mcp = GoogleCalendarMCP()
        result = await mcp.get_availability()
        
        assert result["success"] is True
        assert "busy_slots" in result
        assert "free_slots" in result
    
    @pytest.mark.asyncio
    async def test_real_create_and_delete_event(self):
        """Real API: Create event, verify, delete."""
        mcp = GoogleCalendarMCP()
        
        start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
            hour=14, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(minutes=30)
        
        if start.weekday() >= 5:
            start += timedelta(days=2)
            end += timedelta(days=2)
        
        create_result = await mcp.create_event(
            title="[TEST] Integration Test Event - DELETE ME",
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            description="This is an automated test event and should be deleted."
        )
        
        assert create_result["success"] is True, f"Create failed: {create_result.get('error')}"
        event_id = create_result["event_id"]
        
        try:
            events_result = await mcp.get_events(
                start_time=start.isoformat(),
                end_time=end.isoformat()
            )
            assert events_result["success"] is True
            
            event_ids = [e["id"] for e in events_result["events"]]
            assert event_id in event_ids, "Created event not found in events list"
            
        finally:
            delete_result = await mcp.delete_event(event_id=event_id)
            assert delete_result["success"] is True, f"Delete failed: {delete_result.get('error')}"
    
    @pytest.mark.asyncio
    async def test_real_find_slots(self):
        """Real API: Find available slots."""
        mcp = GoogleCalendarMCP()
        
        result = await mcp.find_available_slots(
            duration_minutes=30,
            working_hours_start=9,
            working_hours_end=17
        )
        
        assert result["success"] is True
        assert result["total_slots"] > 0
    
    @pytest.mark.asyncio
    async def test_real_guardrails_enforced(self):
        """Real API: Verify guardrails are enforced."""
        mcp = GoogleCalendarMCP()
        
        result = await mcp.create_event(
            title="Should Fail - After Hours",
            start_time="2026-01-22T23:00:00-05:00",
            end_time="2026-01-22T23:30:00-05:00"
        )
        
        assert result["success"] is False


class TestHelperMethods:
    """Test internal helper methods."""
    
    def test_calculate_free_slots_empty_busy(self, calendar_mcp):
        """Test free slots calculation with no busy periods."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=8)
        
        free = calendar_mcp._calculate_free_slots(start, end, [])
        
        assert len(free) == 1
        assert free[0]["start"] == start.isoformat()
        assert free[0]["end"] == end.isoformat()
    
    def test_calculate_free_slots_with_busy(self, calendar_mcp):
        """Test free slots calculation with busy periods."""
        start = datetime(2026, 1, 22, 9, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 22, 17, 0, tzinfo=timezone.utc)
        
        busy = [
            {
                "start": "2026-01-22T10:00:00+00:00",
                "end": "2026-01-22T11:00:00+00:00"
            },
            {
                "start": "2026-01-22T14:00:00+00:00",
                "end": "2026-01-22T15:00:00+00:00"
            }
        ]
        
        free = calendar_mcp._calculate_free_slots(start, end, busy)
        
        assert len(free) == 3
    
    def test_check_rate_limit_allows_requests(self, calendar_mcp):
        """Test rate limit allows requests when under limit."""
        calendar_mcp._request_times = []
        
        for _ in range(10):
            assert calendar_mcp._check_rate_limit() is True
    
    def test_check_rate_limit_blocks_excess(self, calendar_mcp):
        """Test rate limit blocks when limit exceeded."""
        calendar_mcp._request_times = [time.time()] * 100
        
        assert calendar_mcp._check_rate_limit() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
