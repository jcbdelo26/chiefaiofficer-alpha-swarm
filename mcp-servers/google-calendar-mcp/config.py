#!/usr/bin/env python3
"""
Google Calendar MCP Configuration
===================================
Configuration for the Google Calendar MCP server.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CalendarConfig:
    """Configuration for calendar operations."""
    
    # Google OAuth
    credentials_path: str = "credentials.json"
    token_path: str = "token.json"
    scopes: List[str] = field(default_factory=lambda: [
        'https://www.googleapis.com/auth/calendar'
    ])
    
    # Rate limits
    max_requests_per_hour: int = 100
    max_requests_per_minute: int = 20
    
    # Working hours defaults
    default_working_hours_start: int = 9   # 9 AM
    default_working_hours_end: int = 18    # 6 PM
    default_timezone: str = "America/New_York"
    
    # Buffer rules
    min_buffer_minutes: int = 15
    default_meeting_duration: int = 30
    max_meeting_duration: int = 120
    
    # Booking rules
    max_days_ahead: int = 90
    min_hours_notice: float = 0.5  # 30 minutes
    allow_weekend_booking: bool = False
    max_attendees: int = 50
    
    # Blocked times (hour of day to block, e.g., [12] for lunch)
    blocked_hours: List[int] = field(default_factory=list)
    
    # Per-timezone working hours override
    timezone_working_hours: Dict[str, Dict[str, int]] = field(default_factory=lambda: {
        "America/New_York": {"start": 9, "end": 18},
        "America/Los_Angeles": {"start": 9, "end": 18},
        "America/Chicago": {"start": 9, "end": 18},
        "Europe/London": {"start": 9, "end": 17},
        "Europe/Paris": {"start": 9, "end": 18},
        "Asia/Tokyo": {"start": 9, "end": 18},
    })
    
    def get_working_hours(self, timezone: str) -> Dict[str, int]:
        """Get working hours for a specific timezone."""
        return self.timezone_working_hours.get(timezone, {
            "start": self.default_working_hours_start,
            "end": self.default_working_hours_end
        })


# Singleton config instance
_config: Optional[CalendarConfig] = None


def get_config() -> CalendarConfig:
    """Get or create the configuration instance."""
    global _config
    if _config is None:
        _config = CalendarConfig()
        
        # Override from environment
        if os.getenv("CALENDAR_MAX_REQUESTS_PER_HOUR"):
            _config.max_requests_per_hour = int(os.getenv("CALENDAR_MAX_REQUESTS_PER_HOUR"))
        
        if os.getenv("CALENDAR_DEFAULT_TIMEZONE"):
            _config.default_timezone = os.getenv("CALENDAR_DEFAULT_TIMEZONE")
        
        if os.getenv("CALENDAR_WORKING_HOURS_START"):
            _config.default_working_hours_start = int(os.getenv("CALENDAR_WORKING_HOURS_START"))
        
        if os.getenv("CALENDAR_WORKING_HOURS_END"):
            _config.default_working_hours_end = int(os.getenv("CALENDAR_WORKING_HOURS_END"))
    
    return _config


def set_config(config: CalendarConfig):
    """Set a custom configuration."""
    global _config
    _config = config
