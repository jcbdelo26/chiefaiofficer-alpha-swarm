#!/usr/bin/env python3
"""
Tests for Calendar Timezone Edge Cases
======================================
Tests for timezone validation, safe conversion, DST handling,
and working hours conversion across timezones.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-servers" / "google-calendar-mcp"))

from guardrails import (
    CalendarGuardrails,
    WorkingHours,
    TIMEZONE_ALIASES,
)


class TestTimezoneValidation:
    """Test timezone validation and alias resolution."""
    
    def test_valid_iana_timezone(self):
        guardrails = CalendarGuardrails()
        
        valid, result = guardrails.validate_timezone("America/New_York")
        
        assert valid is True
        assert result == "America/New_York"
    
    def test_valid_timezone_alias_est(self):
        guardrails = CalendarGuardrails()
        
        valid, result = guardrails.validate_timezone("EST")
        
        assert valid is True
        assert result == "America/New_York"
    
    def test_valid_timezone_alias_pst(self):
        guardrails = CalendarGuardrails()
        
        valid, result = guardrails.validate_timezone("PST")
        
        assert valid is True
        assert result == "America/Los_Angeles"
    
    def test_valid_timezone_alias_gmt(self):
        guardrails = CalendarGuardrails()
        
        valid, result = guardrails.validate_timezone("GMT")
        
        assert valid is True
        assert result == "Europe/London"
    
    def test_valid_timezone_alias_ist(self):
        guardrails = CalendarGuardrails()
        
        valid, result = guardrails.validate_timezone("IST")
        
        assert valid is True
        assert result == "Asia/Kolkata"
    
    def test_valid_timezone_alias_jst(self):
        guardrails = CalendarGuardrails()
        
        valid, result = guardrails.validate_timezone("JST")
        
        assert valid is True
        assert result == "Asia/Tokyo"
    
    def test_valid_timezone_alias_case_insensitive(self):
        guardrails = CalendarGuardrails()
        
        valid, result = guardrails.validate_timezone("pst")
        
        assert valid is True
        assert result == "America/Los_Angeles"
    
    def test_invalid_timezone(self):
        guardrails = CalendarGuardrails()
        
        valid, result = guardrails.validate_timezone("Invalid/Timezone")
        
        assert valid is False
        assert "Unknown timezone" in result
    
    def test_invalid_timezone_with_suggestions(self):
        guardrails = CalendarGuardrails()
        
        valid, result = guardrails.validate_timezone("NewYork")
        
        assert valid is False
        assert "Unknown timezone" in result
    
    def test_empty_timezone_returns_default(self):
        guardrails = CalendarGuardrails()
        
        valid, result = guardrails.validate_timezone("")
        
        assert valid is True
        assert result == "America/New_York"  # Default working hours timezone
    
    def test_none_timezone_returns_default(self):
        guardrails = CalendarGuardrails()
        
        valid, result = guardrails.validate_timezone(None)
        
        assert valid is True
        assert result == "America/New_York"


class TestTimezoneAliasResolution:
    """Test timezone alias resolution."""
    
    def test_resolve_est_alias(self):
        guardrails = CalendarGuardrails()
        
        result = guardrails.resolve_timezone_alias("EST")
        
        assert result == "America/New_York"
    
    def test_resolve_cet_alias(self):
        guardrails = CalendarGuardrails()
        
        result = guardrails.resolve_timezone_alias("CET")
        
        assert result == "Europe/Paris"
    
    def test_resolve_utc_alias(self):
        guardrails = CalendarGuardrails()
        
        result = guardrails.resolve_timezone_alias("UTC")
        
        assert result == "UTC"
    
    def test_resolve_z_alias(self):
        guardrails = CalendarGuardrails()
        
        result = guardrails.resolve_timezone_alias("Z")
        
        assert result == "UTC"
    
    def test_resolve_passthrough_iana(self):
        guardrails = CalendarGuardrails()
        
        result = guardrails.resolve_timezone_alias("Europe/Berlin")
        
        assert result == "Europe/Berlin"
    
    def test_resolve_empty_returns_default(self):
        guardrails = CalendarGuardrails()
        
        result = guardrails.resolve_timezone_alias("")
        
        assert result == "America/New_York"


class TestTimezoneConversion:
    """Test basic timezone conversion."""
    
    def test_convert_ny_to_la(self):
        guardrails = CalendarGuardrails()
        
        ny_time = "2026-01-22T14:00:00-05:00"
        la_time = guardrails.convert_timezone(
            ny_time,
            "America/New_York",
            "America/Los_Angeles"
        )
        
        assert "11:00:00" in la_time
        assert "-08:00" in la_time
    
    def test_convert_using_aliases(self):
        guardrails = CalendarGuardrails()
        
        ny_time = "2026-01-22T14:00:00-05:00"
        la_time = guardrails.convert_timezone(ny_time, "EST", "PST")
        
        assert "11:00:00" in la_time
    
    def test_convert_naive_datetime(self):
        guardrails = CalendarGuardrails()
        
        naive_time = "2026-01-22T14:00:00"
        utc_time = guardrails.convert_timezone(
            naive_time,
            "America/New_York",
            "UTC"
        )
        
        assert "19:00:00" in utc_time
    
    def test_convert_to_tokyo(self):
        guardrails = CalendarGuardrails()
        
        utc_time = "2026-01-22T12:00:00+00:00"
        tokyo_time = guardrails.convert_timezone(utc_time, "UTC", "Asia/Tokyo")
        
        assert "21:00:00" in tokyo_time


class TestSafeTimezoneConversion:
    """Test safe timezone conversion with fallback."""
    
    def test_safe_convert_valid_timezones(self):
        guardrails = CalendarGuardrails()
        
        ny_time = "2026-01-22T14:00:00-05:00"
        result, success = guardrails.convert_timezone_safe(
            ny_time,
            "America/New_York",
            "America/Los_Angeles"
        )
        
        assert success is True
        assert "11:00:00" in result
    
    def test_safe_convert_invalid_source_tz_fallback(self):
        guardrails = CalendarGuardrails()
        
        time_str = "2026-01-22T14:00:00"
        result, success = guardrails.convert_timezone_safe(
            time_str,
            "Invalid/Source",
            "America/Los_Angeles",
            fallback_tz="UTC"
        )
        
        assert success is False
        assert result is not None
    
    def test_safe_convert_invalid_target_tz_fallback(self):
        guardrails = CalendarGuardrails()
        
        time_str = "2026-01-22T14:00:00-05:00"
        result, success = guardrails.convert_timezone_safe(
            time_str,
            "America/New_York",
            "Invalid/Target",
            fallback_tz="UTC"
        )
        
        assert success is False
        assert result is not None
    
    def test_safe_convert_naive_datetime(self):
        guardrails = CalendarGuardrails()
        
        naive_time = "2026-01-22T14:00:00"
        result, success = guardrails.convert_timezone_safe(
            naive_time,
            "America/New_York",
            "UTC"
        )
        
        assert success is True
        assert "19:00:00" in result
    
    def test_safe_convert_invalid_time_string(self):
        guardrails = CalendarGuardrails()
        
        result, success = guardrails.convert_timezone_safe(
            "not-a-valid-time",
            "America/New_York",
            "UTC"
        )
        
        assert success is False
        assert result == "not-a-valid-time"


class TestMidnightCrossing:
    """Test timezone conversions that cross midnight."""
    
    def test_conversion_crosses_midnight_forward(self):
        guardrails = CalendarGuardrails()
        
        late_ny = "2026-01-22T23:00:00-05:00"
        result, success = guardrails.convert_timezone_safe(
            late_ny,
            "America/New_York",
            "Europe/London"
        )
        
        assert success is True
        assert "2026-01-23" in result
        assert "04:00:00" in result
    
    def test_conversion_crosses_midnight_backward(self):
        guardrails = CalendarGuardrails()
        
        early_utc = "2026-01-22T02:00:00+00:00"
        result, success = guardrails.convert_timezone_safe(
            early_utc,
            "UTC",
            "America/Los_Angeles"
        )
        
        assert success is True
        assert "2026-01-21" in result
        assert "18:00:00" in result
    
    def test_edge_of_day_2359(self):
        guardrails = CalendarGuardrails()
        
        edge_time = "2026-01-22T23:59:00-05:00"
        result, success = guardrails.convert_timezone_safe(
            edge_time,
            "America/New_York",
            "UTC"
        )
        
        assert success is True
        assert "2026-01-23" in result
        assert "04:59:00" in result
    
    def test_edge_of_day_0000(self):
        guardrails = CalendarGuardrails()
        
        midnight = "2026-01-22T00:00:00+00:00"
        result, success = guardrails.convert_timezone_safe(
            midnight,
            "UTC",
            "America/New_York"
        )
        
        assert success is True
        assert "2026-01-21" in result
        assert "19:00:00" in result


class TestDSTTransitions:
    """Test DST transition handling."""
    
    def test_dst_check_normal_time(self):
        guardrails = CalendarGuardrails()
        
        normal_time = datetime(2026, 1, 22, 14, 0, 0)
        tz = ZoneInfo("America/New_York")
        
        result = guardrails._check_dst_transition(normal_time, tz)
        
        assert result["in_gap"] is False
        assert result["in_fold"] is False
    
    def test_convert_through_spring_forward(self):
        guardrails = CalendarGuardrails()
        
        before_dst = "2026-03-08T01:30:00-05:00"
        result, success = guardrails.convert_timezone_safe(
            before_dst,
            "America/New_York",
            "UTC"
        )
        
        assert success is True
    
    def test_convert_through_fall_back(self):
        guardrails = CalendarGuardrails()
        
        during_dst = "2026-11-01T01:30:00-04:00"
        result, success = guardrails.convert_timezone_safe(
            during_dst,
            "America/New_York",
            "UTC"
        )
        
        assert success is True


class TestWorkingHoursConversion:
    """Test working hours conversion across timezones."""
    
    def test_working_hours_same_timezone(self):
        working_hours = WorkingHours(
            start_hour=9,
            end_hour=18,
            timezone="America/New_York"
        )
        guardrails = CalendarGuardrails(working_hours=working_hours)
        
        start, end = guardrails.get_user_working_hours_in_tz("America/New_York")
        
        assert start == 9
        assert end == 18
    
    def test_working_hours_ny_to_la(self):
        working_hours = WorkingHours(
            start_hour=9,
            end_hour=18,
            timezone="America/New_York"
        )
        guardrails = CalendarGuardrails(working_hours=working_hours)
        
        start, end = guardrails.get_user_working_hours_in_tz("America/Los_Angeles")
        
        assert start == 6
        assert end == 15
    
    def test_working_hours_ny_to_london(self):
        working_hours = WorkingHours(
            start_hour=9,
            end_hour=18,
            timezone="America/New_York"
        )
        guardrails = CalendarGuardrails(working_hours=working_hours)
        
        start, end = guardrails.get_user_working_hours_in_tz("Europe/London")
        
        assert start == 14
        assert end == 23
    
    def test_working_hours_with_alias(self):
        working_hours = WorkingHours(
            start_hour=9,
            end_hour=18,
            timezone="America/New_York"
        )
        guardrails = CalendarGuardrails(working_hours=working_hours)
        
        start, end = guardrails.get_user_working_hours_in_tz("PST")
        
        assert start == 6
        assert end == 15
    
    def test_working_hours_invalid_timezone_returns_default(self):
        working_hours = WorkingHours(
            start_hour=9,
            end_hour=18,
            timezone="America/New_York"
        )
        guardrails = CalendarGuardrails(working_hours=working_hours)
        
        start, end = guardrails.get_user_working_hours_in_tz("Invalid/Timezone")
        
        assert start == 9
        assert end == 18
    
    def test_working_hours_info_normal(self):
        working_hours = WorkingHours(
            start_hour=9,
            end_hour=18,
            timezone="America/New_York"
        )
        guardrails = CalendarGuardrails(working_hours=working_hours)
        
        info = guardrails.get_working_hours_info("America/New_York")
        
        assert info["start_hour"] == 9
        assert info["end_hour"] == 18
        assert info["spans_midnight"] is False
        assert "9:00 - 18:00" in info["description"]
    
    def test_working_hours_spans_midnight(self):
        working_hours = WorkingHours(
            start_hour=9,
            end_hour=18,
            timezone="America/New_York"
        )
        guardrails = CalendarGuardrails(working_hours=working_hours)
        
        info = guardrails.get_working_hours_info("Asia/Tokyo")
        
        assert info["start_hour"] == 23
        assert info["end_hour"] == 8
        assert info["spans_midnight"] is True
        assert "spans midnight" in info["description"]


class TestTimezoneAliasesCompleteness:
    """Test timezone aliases mapping is complete and correct."""
    
    def test_us_timezones_covered(self):
        assert "EST" in TIMEZONE_ALIASES
        assert "PST" in TIMEZONE_ALIASES
        assert "CST" in TIMEZONE_ALIASES
        assert "MST" in TIMEZONE_ALIASES
    
    def test_european_timezones_covered(self):
        assert "GMT" in TIMEZONE_ALIASES
        assert "CET" in TIMEZONE_ALIASES
        assert "EET" in TIMEZONE_ALIASES
    
    def test_asian_timezones_covered(self):
        assert "IST" in TIMEZONE_ALIASES
        assert "JST" in TIMEZONE_ALIASES
        assert "KST" in TIMEZONE_ALIASES
    
    def test_australian_timezones_covered(self):
        assert "AEST" in TIMEZONE_ALIASES
        assert "AWST" in TIMEZONE_ALIASES
    
    def test_all_aliases_resolve_to_valid_timezones(self):
        for alias, iana in TIMEZONE_ALIASES.items():
            try:
                ZoneInfo(iana)
            except Exception as e:
                pytest.fail(f"Alias {alias} maps to invalid timezone {iana}: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
