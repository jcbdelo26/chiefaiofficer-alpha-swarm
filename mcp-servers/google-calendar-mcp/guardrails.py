#!/usr/bin/env python3
"""
Google Calendar Guardrails
===========================
Calendar-specific guardrails to prevent booking issues.

Rules:
- Never double-book (mutex lock on create)
- Respect working hours (configurable, default 9 AM - 6 PM)
- Minimum 15-min buffer between meetings
- Rate limit: 100 requests/hour
- Timezone validation and conversion
- Maximum meeting duration limits
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import logging

logger = logging.getLogger("calendar-guardrails")


# =============================================================================
# TIMEZONE ALIASES - Common abbreviations to IANA names
# =============================================================================

TIMEZONE_ALIASES: Dict[str, str] = {
    # US Timezones
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "AKST": "America/Anchorage",
    "AKDT": "America/Anchorage",
    "HST": "Pacific/Honolulu",
    # European Timezones
    "GMT": "Europe/London",
    "BST": "Europe/London",
    "WET": "Europe/Lisbon",
    "WEST": "Europe/Lisbon",
    "CET": "Europe/Paris",
    "CEST": "Europe/Paris",
    "EET": "Europe/Helsinki",
    "EEST": "Europe/Helsinki",
    # Asian Timezones
    "IST": "Asia/Kolkata",
    "JST": "Asia/Tokyo",
    "KST": "Asia/Seoul",
    "CST_CHINA": "Asia/Shanghai",
    "HKT": "Asia/Hong_Kong",
    "SGT": "Asia/Singapore",
    "PHT": "Asia/Manila",
    # Australian Timezones
    "AEST": "Australia/Sydney",
    "AEDT": "Australia/Sydney",
    "ACST": "Australia/Adelaide",
    "ACDT": "Australia/Adelaide",
    "AWST": "Australia/Perth",
    # Other common
    "UTC": "UTC",
    "Z": "UTC",
    "NZST": "Pacific/Auckland",
    "NZDT": "Pacific/Auckland",
}


# =============================================================================
# GUARDRAIL CONSTANTS - NEVER EXCEED
# =============================================================================

MAX_REQUESTS_PER_HOUR = 100
MIN_BUFFER_MINUTES = 15
WORKING_HOURS_START = 9   # 9 AM
WORKING_HOURS_END = 18    # 6 PM
MAX_MEETING_DURATION = 120  # 2 hours max
MIN_MEETING_DURATION = 15   # 15 minutes min
MAX_ATTENDEES = 50
BLOCKED_HOURS = []  # e.g., lunch hour [12, 13]


@dataclass
class BookingValidation:
    """Result of booking validation."""
    valid: bool
    error: Optional[str] = None
    warnings: List[str] = None
    suggestions: List[str] = None
    
    def __post_init__(self):
        self.warnings = self.warnings or []
        self.suggestions = self.suggestions or []


@dataclass
class WorkingHours:
    """Working hours configuration."""
    start_hour: int = WORKING_HOURS_START
    end_hour: int = WORKING_HOURS_END
    timezone: str = "America/New_York"
    blocked_hours: List[int] = None
    weekend_allowed: bool = False
    
    def __post_init__(self):
        self.blocked_hours = self.blocked_hours or BLOCKED_HOURS


class CalendarGuardrails:
    """
    Guardrails for calendar operations.
    Ensures bookings follow business rules and prevent conflicts.
    """
    
    def __init__(self, working_hours: Optional[WorkingHours] = None):
        self.working_hours = working_hours or WorkingHours()
        self._booked_slots: Dict[str, List[Tuple[datetime, datetime]]] = {}
    
    def validate_booking(
        self,
        start_time: str,
        end_time: str,
        calendar_id: str = "primary",
        timezone_str: str = None,
        attendees: List[str] = None
    ) -> BookingValidation:
        """
        Validate a booking request against all guardrails.
        
        Args:
            start_time: ISO start time
            end_time: ISO end time
            calendar_id: Calendar ID
            timezone_str: Timezone for validation
            attendees: List of attendee emails
        
        Returns:
            BookingValidation with valid/invalid status and details
        """
        warnings = []
        suggestions = []
        
        try:
            # Parse times
            start = self._parse_time(start_time)
            end = self._parse_time(end_time)
        except Exception as e:
            return BookingValidation(
                valid=False,
                error=f"Invalid time format: {e}"
            )
        
        # 1. Check basic time validity
        if end <= start:
            return BookingValidation(
                valid=False,
                error="End time must be after start time"
            )
        
        # 2. Check duration limits
        duration = (end - start).total_seconds() / 60
        
        if duration > MAX_MEETING_DURATION:
            return BookingValidation(
                valid=False,
                error=f"Meeting duration ({duration}min) exceeds maximum ({MAX_MEETING_DURATION}min)",
                suggestions=[f"Split into multiple {MAX_MEETING_DURATION//2}min meetings"]
            )
        
        if duration < MIN_MEETING_DURATION:
            return BookingValidation(
                valid=False,
                error=f"Meeting duration ({duration}min) below minimum ({MIN_MEETING_DURATION}min)"
            )
        
        # 3. Check working hours
        tz = ZoneInfo(timezone_str or self.working_hours.timezone)
        local_start = start.astimezone(tz)
        local_end = end.astimezone(tz)
        
        if local_start.hour < self.working_hours.start_hour:
            return BookingValidation(
                valid=False,
                error=f"Meeting starts before working hours ({self.working_hours.start_hour}:00)",
                suggestions=[f"Schedule after {self.working_hours.start_hour}:00 {timezone_str or self.working_hours.timezone}"]
            )
        
        if local_end.hour > self.working_hours.end_hour or (
            local_end.hour == self.working_hours.end_hour and local_end.minute > 0
        ):
            return BookingValidation(
                valid=False,
                error=f"Meeting ends after working hours ({self.working_hours.end_hour}:00)",
                suggestions=[f"End meeting by {self.working_hours.end_hour}:00"]
            )
        
        # 4. Check weekend
        if not self.working_hours.weekend_allowed:
            if local_start.weekday() >= 5:  # Saturday = 5, Sunday = 6
                return BookingValidation(
                    valid=False,
                    error="Weekend meetings are not allowed",
                    suggestions=["Schedule for next Monday"]
                )
        
        # 5. Check blocked hours
        for blocked in self.working_hours.blocked_hours:
            if local_start.hour == blocked or local_end.hour == blocked:
                warnings.append(f"Meeting overlaps blocked hour ({blocked}:00)")
        
        # 6. Check attendee limits
        attendees = attendees or []
        if len(attendees) > MAX_ATTENDEES:
            return BookingValidation(
                valid=False,
                error=f"Too many attendees ({len(attendees)} > {MAX_ATTENDEES})"
            )
        
        # 7. Check if too far in future (>90 days)
        days_ahead = (start - datetime.now(timezone.utc)).days
        if days_ahead > 90:
            warnings.append(f"Meeting is {days_ahead} days in the future - attendees may forget")
        
        # 8. Check if too soon (<1 hour)
        hours_until = (start - datetime.now(timezone.utc)).total_seconds() / 3600
        if 0 < hours_until < 1:
            warnings.append("Meeting is less than 1 hour away - attendees may not see invite in time")
        
        if hours_until < 0:
            return BookingValidation(
                valid=False,
                error="Cannot book meetings in the past"
            )
        
        return BookingValidation(
            valid=True,
            warnings=warnings,
            suggestions=suggestions
        )
    
    def check_buffer(
        self,
        start_time: str,
        end_time: str,
        existing_events: List[Dict[str, Any]],
        buffer_minutes: int = MIN_BUFFER_MINUTES
    ) -> BookingValidation:
        """
        Check if there's adequate buffer between meetings.
        
        Args:
            start_time: Proposed start time
            end_time: Proposed end time
            existing_events: List of existing events
            buffer_minutes: Required buffer in minutes
        
        Returns:
            BookingValidation result
        """
        start = self._parse_time(start_time)
        end = self._parse_time(end_time)
        buffer = timedelta(minutes=buffer_minutes)
        
        for event in existing_events:
            event_start = self._parse_time(event.get("start", ""))
            event_end = self._parse_time(event.get("end", ""))
            
            # Check if proposed meeting is too close to existing
            if abs((start - event_end).total_seconds()) < buffer.total_seconds():
                return BookingValidation(
                    valid=False,
                    error=f"Insufficient buffer before meeting (need {buffer_minutes}min)",
                    suggestions=[f"Start at {(event_end + buffer).isoformat()}"]
                )
            
            if abs((event_start - end).total_seconds()) < buffer.total_seconds():
                return BookingValidation(
                    valid=False,
                    error=f"Insufficient buffer after meeting (need {buffer_minutes}min)",
                    suggestions=[f"End by {(event_start - buffer).isoformat()}"]
                )
        
        return BookingValidation(valid=True)
    
    def check_double_booking(
        self,
        start_time: str,
        end_time: str,
        existing_events: List[Dict[str, Any]]
    ) -> BookingValidation:
        """
        Check for double-booking conflicts.
        
        Args:
            start_time: Proposed start time
            end_time: Proposed end time
            existing_events: List of existing events
        
        Returns:
            BookingValidation result
        """
        start = self._parse_time(start_time)
        end = self._parse_time(end_time)
        
        for event in existing_events:
            event_start = self._parse_time(event.get("start", ""))
            event_end = self._parse_time(event.get("end", ""))
            
            # Check overlap
            if start < event_end and end > event_start:
                return BookingValidation(
                    valid=False,
                    error=f"Double-booking conflict with: {event.get('title', 'Existing event')}",
                    suggestions=[
                        f"Schedule before {event_start.isoformat()}",
                        f"Schedule after {event_end.isoformat()}"
                    ]
                )
        
        return BookingValidation(valid=True)
    
    def resolve_timezone_alias(self, timezone_str: str) -> str:
        """
        Resolve timezone alias to IANA name.
        
        Args:
            timezone_str: Timezone string (alias or IANA name)
        
        Returns:
            IANA timezone name
        """
        if not timezone_str:
            return self.working_hours.timezone
        
        upper_tz = timezone_str.upper().strip()
        if upper_tz in TIMEZONE_ALIASES:
            return TIMEZONE_ALIASES[upper_tz]
        
        return timezone_str
    
    def validate_timezone(self, timezone_str: str) -> Tuple[bool, Optional[str]]:
        """
        Validate timezone string is valid and supported.
        
        Args:
            timezone_str: Timezone string to validate
        
        Returns:
            Tuple of (is_valid, resolved_timezone_or_error)
        """
        if not timezone_str:
            return True, self.working_hours.timezone
        
        resolved = self.resolve_timezone_alias(timezone_str)
        
        try:
            ZoneInfo(resolved)
            return True, resolved
        except ZoneInfoNotFoundError:
            suggestions = []
            search = timezone_str.lower()
            for alias, iana in TIMEZONE_ALIASES.items():
                if search in alias.lower() or search in iana.lower():
                    suggestions.append(f"{alias} ({iana})")
            
            error_msg = f"Unknown timezone: '{timezone_str}'"
            if suggestions:
                error_msg += f". Did you mean: {', '.join(suggestions[:3])}?"
            
            return False, error_msg
        except Exception as e:
            return False, f"Invalid timezone '{timezone_str}': {e}"
    
    def convert_timezone(
        self,
        time_str: str,
        from_tz: str,
        to_tz: str
    ) -> str:
        """
        Convert time between timezones.
        
        Args:
            time_str: ISO time string
            from_tz: Source timezone
            to_tz: Target timezone
        
        Returns:
            Converted ISO time string
        """
        dt = self._parse_time(time_str)
        
        from_tz = self.resolve_timezone_alias(from_tz)
        to_tz = self.resolve_timezone_alias(to_tz)
        
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(from_tz))
        
        converted = dt.astimezone(ZoneInfo(to_tz))
        
        return converted.isoformat()
    
    def convert_timezone_safe(
        self,
        time_str: str,
        from_tz: str,
        to_tz: str,
        fallback_tz: str = "UTC"
    ) -> Tuple[str, bool]:
        """
        Safe timezone conversion with fallback.
        
        Handles:
        - Invalid timezone names (falls back to fallback_tz)
        - DST transitions (gap and fold detection)
        - Missing timezone info (naive datetime)
        - Edge of day boundaries (23:59 -> 00:00)
        
        Args:
            time_str: ISO time string
            from_tz: Source timezone
            to_tz: Target timezone
            fallback_tz: Fallback timezone if conversion fails
        
        Returns:
            Tuple of (converted_time_string, success_flag)
        """
        warnings = []
        
        from_valid, from_resolved = self.validate_timezone(from_tz)
        if not from_valid:
            logger.warning(f"Invalid source timezone '{from_tz}', using fallback '{fallback_tz}'")
            from_resolved = fallback_tz
            warnings.append(f"source_tz_fallback:{fallback_tz}")
        
        to_valid, to_resolved = self.validate_timezone(to_tz)
        if not to_valid:
            logger.warning(f"Invalid target timezone '{to_tz}', using fallback '{fallback_tz}'")
            to_resolved = fallback_tz
            warnings.append(f"target_tz_fallback:{fallback_tz}")
        
        try:
            dt = self._parse_time(time_str)
        except ValueError as e:
            logger.error(f"Failed to parse time '{time_str}': {e}")
            return time_str, False
        
        try:
            from_zone = ZoneInfo(from_resolved)
            to_zone = ZoneInfo(to_resolved)
        except ZoneInfoNotFoundError as e:
            logger.error(f"Timezone not found: {e}")
            return time_str, False
        
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=from_zone)
            warnings.append("naive_datetime_assumed_source_tz")
        
        dst_info = self._check_dst_transition(dt, from_zone)
        if dst_info["in_gap"]:
            logger.warning(f"Time {time_str} falls in DST gap, adjusting forward")
            dt = dst_info["adjusted_time"]
            warnings.append("dst_gap_adjusted")
        elif dst_info["in_fold"]:
            logger.warning(f"Time {time_str} is ambiguous (DST fold), using earlier time")
            dt = dt.replace(fold=0)
            warnings.append("dst_fold_earlier")
        
        converted = dt.astimezone(to_zone)
        
        if dt.date() != converted.date():
            warnings.append("date_boundary_crossed")
        
        success = not any("fallback" in w for w in warnings)
        
        return converted.isoformat(), success
    
    def _check_dst_transition(
        self,
        dt: datetime,
        tz: ZoneInfo
    ) -> Dict[str, Any]:
        """
        Check if a datetime falls in a DST gap or fold.
        
        Args:
            dt: Datetime to check
            tz: Timezone to check in
        
        Returns:
            Dict with in_gap, in_fold, adjusted_time, message
        """
        result = {
            "in_gap": False,
            "in_fold": False,
            "adjusted_time": dt,
            "message": None
        }
        
        if dt.tzinfo is None:
            dt_local = dt.replace(tzinfo=tz)
        else:
            dt_local = dt.astimezone(tz)
        
        try:
            utc_time = dt_local.astimezone(timezone.utc)
            back_to_local = utc_time.astimezone(tz)
            
            if back_to_local.replace(tzinfo=None) != dt_local.replace(tzinfo=None):
                result["in_gap"] = True
                result["adjusted_time"] = back_to_local
                result["message"] = f"Time adjusted from {dt_local} to {back_to_local} (DST gap)"
        except Exception:
            pass
        
        try:
            dt_fold0 = dt_local.replace(fold=0)
            dt_fold1 = dt_local.replace(fold=1)
            
            utc_fold0 = dt_fold0.astimezone(timezone.utc)
            utc_fold1 = dt_fold1.astimezone(timezone.utc)
            
            if utc_fold0 != utc_fold1:
                result["in_fold"] = True
                result["message"] = f"Ambiguous time (DST fold): could be {utc_fold0} or {utc_fold1} UTC"
        except Exception:
            pass
        
        return result
    
    def get_user_working_hours_in_tz(
        self,
        target_tz: str
    ) -> Tuple[int, int]:
        """
        Convert working hours to target timezone.
        
        Handles working hours that span midnight when converted.
        
        Args:
            target_tz: Target timezone for working hours
        
        Returns:
            Tuple of (start_hour, end_hour) in target timezone.
            If hours span midnight, end_hour may be < start_hour.
        """
        target_valid, target_resolved = self.validate_timezone(target_tz)
        if not target_valid:
            logger.warning(f"Invalid target timezone '{target_tz}', returning default hours")
            return self.working_hours.start_hour, self.working_hours.end_hour
        
        source_tz = self.resolve_timezone_alias(self.working_hours.timezone)
        
        today = datetime.now().date()
        
        start_dt = datetime.combine(
            today,
            datetime.min.time().replace(hour=self.working_hours.start_hour),
        )
        start_dt = start_dt.replace(tzinfo=ZoneInfo(source_tz))
        
        end_dt = datetime.combine(
            today,
            datetime.min.time().replace(hour=self.working_hours.end_hour),
        )
        end_dt = end_dt.replace(tzinfo=ZoneInfo(source_tz))
        
        target_zone = ZoneInfo(target_resolved)
        converted_start = start_dt.astimezone(target_zone)
        converted_end = end_dt.astimezone(target_zone)
        
        start_hour = converted_start.hour
        end_hour = converted_end.hour
        
        if converted_start.date() != today:
            logger.info(f"Working hours start on different day in {target_tz}")
        if converted_end.date() != today:
            logger.info(f"Working hours end on different day in {target_tz}")
        
        return start_hour, end_hour
    
    def get_working_hours_info(
        self,
        target_tz: str
    ) -> Dict[str, Any]:
        """
        Get detailed working hours info for a timezone.
        
        Args:
            target_tz: Target timezone
        
        Returns:
            Dict with start/end hours, spans_midnight flag, and descriptions
        """
        start_hour, end_hour = self.get_user_working_hours_in_tz(target_tz)
        
        spans_midnight = end_hour < start_hour
        
        if spans_midnight:
            description = f"{start_hour}:00 - midnight, then midnight - {end_hour}:00 (spans midnight)"
        else:
            description = f"{start_hour}:00 - {end_hour}:00"
        
        return {
            "start_hour": start_hour,
            "end_hour": end_hour,
            "spans_midnight": spans_midnight,
            "description": description,
            "source_timezone": self.working_hours.timezone,
            "target_timezone": target_tz
        }
    
    def suggest_alternative_times(
        self,
        start_time: str,
        duration_minutes: int,
        existing_events: List[Dict[str, Any]],
        num_suggestions: int = 3
    ) -> List[Dict[str, str]]:
        """
        Suggest alternative meeting times.
        
        Args:
            start_time: Original proposed start
            duration_minutes: Meeting duration
            existing_events: List of existing events
            num_suggestions: Number of alternatives to suggest
        
        Returns:
            List of alternative time slots
        """
        start = self._parse_time(start_time)
        duration = timedelta(minutes=duration_minutes)
        suggestions = []
        
        # Try next day at same time
        next_day = start + timedelta(days=1)
        if self.validate_booking(next_day.isoformat(), (next_day + duration).isoformat()).valid:
            suggestions.append({
                "start": next_day.isoformat(),
                "end": (next_day + duration).isoformat(),
                "reason": "Same time tomorrow"
            })
        
        # Try 1 hour later today
        later = start + timedelta(hours=1)
        if self.validate_booking(later.isoformat(), (later + duration).isoformat()).valid:
            suggestions.append({
                "start": later.isoformat(),
                "end": (later + duration).isoformat(),
                "reason": "1 hour later today"
            })
        
        # Try 1 hour earlier today
        earlier = start - timedelta(hours=1)
        if self.validate_booking(earlier.isoformat(), (earlier + duration).isoformat()).valid:
            suggestions.append({
                "start": earlier.isoformat(),
                "end": (earlier + duration).isoformat(),
                "reason": "1 hour earlier today"
            })
        
        return suggestions[:num_suggestions]
    
    def _parse_time(self, time_str: str) -> datetime:
        """Parse ISO time string to datetime."""
        if not time_str:
            raise ValueError("Empty time string")
        
        # Handle various ISO formats
        time_str = time_str.replace('Z', '+00:00')
        
        try:
            return datetime.fromisoformat(time_str)
        except ValueError:
            # Try parsing without timezone
            for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    return datetime.strptime(time_str, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
            raise ValueError(f"Cannot parse time: {time_str}")


def demo():
    """Demonstrate calendar guardrails."""
    print("\n" + "=" * 50)
    print("CALENDAR GUARDRAILS - Demo")
    print("=" * 50)
    
    guardrails = CalendarGuardrails()
    
    tests = [
        ("Valid meeting", "2026-01-22T14:00:00-05:00", "2026-01-22T14:30:00-05:00"),
        ("Too early", "2026-01-22T07:00:00-05:00", "2026-01-22T07:30:00-05:00"),
        ("Too late", "2026-01-22T20:00:00-05:00", "2026-01-22T20:30:00-05:00"),
        ("Too long", "2026-01-22T10:00:00-05:00", "2026-01-22T14:00:00-05:00"),
        ("Weekend", "2026-01-24T14:00:00-05:00", "2026-01-24T14:30:00-05:00"),  # Saturday
        ("In the past", "2026-01-01T14:00:00-05:00", "2026-01-01T14:30:00-05:00"),
    ]
    
    for name, start, end in tests:
        result = guardrails.validate_booking(start, end)
        status = "✅" if result.valid else "❌"
        print(f"  {status} {name}: {result.error or 'Valid'}")
        if result.suggestions:
            print(f"     Suggestions: {result.suggestions[0]}")
    
    # Timezone conversion
    print("\n[Timezone Conversion]")
    ny_time = "2026-01-22T14:00:00-05:00"
    la_time = guardrails.convert_timezone(ny_time, "America/New_York", "America/Los_Angeles")
    print(f"  NY: {ny_time}")
    print(f"  LA: {la_time}")
    
    print("\n" + "=" * 50)


if __name__ == "__main__":
    demo()
