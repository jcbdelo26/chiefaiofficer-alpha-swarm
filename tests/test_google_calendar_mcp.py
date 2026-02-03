#!/usr/bin/env python3
"""
Tests for Google Calendar MCP Server
=====================================
"""

import pytest
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-servers" / "google-calendar-mcp"))

from config import CalendarConfig, get_config, set_config
from guardrails import CalendarGuardrails, BookingValidation, WorkingHours


class TestCalendarConfig:
    """Test calendar configuration."""
    
    def test_default_config(self):
        config = CalendarConfig()
        assert config.max_requests_per_hour == 100
        assert config.min_buffer_minutes == 15
        assert config.default_working_hours_start == 9
        assert config.default_working_hours_end == 18
    
    def test_get_working_hours_known_timezone(self):
        config = CalendarConfig()
        hours = config.get_working_hours("America/New_York")
        assert hours["start"] == 9
        assert hours["end"] == 18
    
    def test_get_working_hours_unknown_timezone(self):
        config = CalendarConfig()
        hours = config.get_working_hours("Unknown/Timezone")
        assert hours["start"] == config.default_working_hours_start
        assert hours["end"] == config.default_working_hours_end
    
    def test_set_custom_config(self):
        custom = CalendarConfig(
            max_requests_per_hour=50,
            default_timezone="Europe/London"
        )
        set_config(custom)
        
        retrieved = get_config()
        assert retrieved.max_requests_per_hour == 50
        assert retrieved.default_timezone == "Europe/London"


class TestCalendarGuardrails:
    """Test calendar guardrails."""
    
    def test_valid_booking(self):
        guardrails = CalendarGuardrails()
        
        # Valid meeting during working hours
        result = guardrails.validate_booking(
            start_time="2026-01-22T14:00:00-05:00",
            end_time="2026-01-22T14:30:00-05:00",
            timezone_str="America/New_York"
        )
        
        assert result.valid is True
        assert result.error is None
    
    def test_booking_before_working_hours(self):
        guardrails = CalendarGuardrails()
        
        result = guardrails.validate_booking(
            start_time="2026-01-22T07:00:00-05:00",
            end_time="2026-01-22T07:30:00-05:00",
            timezone_str="America/New_York"
        )
        
        assert result.valid is False
        assert "before working hours" in result.error
    
    def test_booking_after_working_hours(self):
        guardrails = CalendarGuardrails()
        
        result = guardrails.validate_booking(
            start_time="2026-01-22T20:00:00-05:00",
            end_time="2026-01-22T20:30:00-05:00",
            timezone_str="America/New_York"
        )
        
        assert result.valid is False
        assert "after working hours" in result.error
    
    def test_booking_too_long(self):
        guardrails = CalendarGuardrails()
        
        result = guardrails.validate_booking(
            start_time="2026-01-22T10:00:00-05:00",
            end_time="2026-01-22T14:00:00-05:00",  # 4 hours
            timezone_str="America/New_York"
        )
        
        assert result.valid is False
        assert "exceeds maximum" in result.error
    
    def test_booking_too_short(self):
        guardrails = CalendarGuardrails()
        
        result = guardrails.validate_booking(
            start_time="2026-01-22T14:00:00-05:00",
            end_time="2026-01-22T14:10:00-05:00",  # 10 minutes
            timezone_str="America/New_York"
        )
        
        assert result.valid is False
        assert "below minimum" in result.error
    
    def test_weekend_booking_blocked(self):
        guardrails = CalendarGuardrails()
        
        # January 24, 2026 is a Saturday
        result = guardrails.validate_booking(
            start_time="2026-01-24T14:00:00-05:00",
            end_time="2026-01-24T14:30:00-05:00",
            timezone_str="America/New_York"
        )
        
        assert result.valid is False
        assert "Weekend" in result.error
    
    def test_weekend_allowed_with_config(self):
        working_hours = WorkingHours(weekend_allowed=True)
        guardrails = CalendarGuardrails(working_hours=working_hours)
        
        result = guardrails.validate_booking(
            start_time="2026-01-24T14:00:00-05:00",
            end_time="2026-01-24T14:30:00-05:00",
            timezone_str="America/New_York"
        )
        
        assert result.valid is True
    
    def test_end_before_start(self):
        guardrails = CalendarGuardrails()
        
        result = guardrails.validate_booking(
            start_time="2026-01-22T15:00:00-05:00",
            end_time="2026-01-22T14:00:00-05:00",
            timezone_str="America/New_York"
        )
        
        assert result.valid is False
        assert "after start time" in result.error
    
    def test_too_many_attendees(self):
        guardrails = CalendarGuardrails()
        
        result = guardrails.validate_booking(
            start_time="2026-01-22T14:00:00-05:00",
            end_time="2026-01-22T14:30:00-05:00",
            attendees=["user@example.com"] * 100  # 100 attendees
        )
        
        assert result.valid is False
        assert "Too many attendees" in result.error
    
    def test_timezone_conversion(self):
        guardrails = CalendarGuardrails()
        
        ny_time = "2026-01-22T14:00:00-05:00"
        la_time = guardrails.convert_timezone(
            ny_time,
            "America/New_York",
            "America/Los_Angeles"
        )
        
        # 2 PM EST = 11 AM PST
        assert "11:00:00" in la_time


class TestDoubleBookingPrevention:
    """Test double-booking prevention."""
    
    def test_no_conflict(self):
        guardrails = CalendarGuardrails()
        
        existing = [
            {"start": "2026-01-22T10:00:00-05:00", "end": "2026-01-22T11:00:00-05:00", "title": "Meeting 1"}
        ]
        
        result = guardrails.check_double_booking(
            start_time="2026-01-22T14:00:00-05:00",
            end_time="2026-01-22T15:00:00-05:00",
            existing_events=existing
        )
        
        assert result.valid is True
    
    def test_direct_conflict(self):
        guardrails = CalendarGuardrails()
        
        existing = [
            {"start": "2026-01-22T14:00:00-05:00", "end": "2026-01-22T15:00:00-05:00", "title": "Existing Meeting"}
        ]
        
        result = guardrails.check_double_booking(
            start_time="2026-01-22T14:00:00-05:00",
            end_time="2026-01-22T14:30:00-05:00",
            existing_events=existing
        )
        
        assert result.valid is False
        assert "Double-booking conflict" in result.error
    
    def test_partial_overlap(self):
        guardrails = CalendarGuardrails()
        
        existing = [
            {"start": "2026-01-22T14:00:00-05:00", "end": "2026-01-22T15:00:00-05:00", "title": "Existing"}
        ]
        
        result = guardrails.check_double_booking(
            start_time="2026-01-22T14:30:00-05:00",
            end_time="2026-01-22T15:30:00-05:00",
            existing_events=existing
        )
        
        assert result.valid is False


class TestBufferChecking:
    """Test buffer between meetings."""
    
    def test_adequate_buffer(self):
        guardrails = CalendarGuardrails()
        
        existing = [
            {"start": "2026-01-22T10:00:00-05:00", "end": "2026-01-22T11:00:00-05:00"}
        ]
        
        result = guardrails.check_buffer(
            start_time="2026-01-22T11:30:00-05:00",  # 30 min after
            end_time="2026-01-22T12:00:00-05:00",
            existing_events=existing
        )
        
        assert result.valid is True
    
    def test_insufficient_buffer_before(self):
        guardrails = CalendarGuardrails()
        
        existing = [
            {"start": "2026-01-22T10:00:00-05:00", "end": "2026-01-22T11:00:00-05:00"}
        ]
        
        result = guardrails.check_buffer(
            start_time="2026-01-22T11:05:00-05:00",  # Only 5 min after
            end_time="2026-01-22T11:35:00-05:00",
            existing_events=existing,
            buffer_minutes=15
        )
        
        assert result.valid is False
        assert "buffer" in result.error.lower()


class TestAlternativeTimeSuggestions:
    """Test alternative time suggestions."""
    
    def test_suggest_alternatives(self):
        guardrails = CalendarGuardrails()
        
        suggestions = guardrails.suggest_alternative_times(
            start_time="2026-01-22T14:00:00-05:00",
            duration_minutes=30,
            existing_events=[]
        )
        
        assert len(suggestions) > 0
        assert all("start" in s and "end" in s for s in suggestions)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
