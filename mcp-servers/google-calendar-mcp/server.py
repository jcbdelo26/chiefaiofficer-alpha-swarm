#!/usr/bin/env python3
"""
Google Calendar MCP Server
===========================
Model Context Protocol server for Google Calendar operations.

Tools:
- get_availability: Check calendar availability
- create_event: Create event with Zoom link
- update_event: Modify existing event
- delete_event: Cancel event
- get_events: List events
- find_available_slots: Find meeting slots across calendars

Guardrails:
- Never double-book (mutex lock on create)
- Respect working hours (9 AM - 6 PM default)
- Minimum 15-min buffer between meetings
- Rate limit: 100 requests/hour
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("google-calendar-mcp")

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from .config import CalendarConfig, get_config
    from .guardrails import CalendarGuardrails, BookingValidation, TIMEZONE_ALIASES
except ImportError:
    from config import CalendarConfig, get_config
    from guardrails import CalendarGuardrails, BookingValidation, TIMEZONE_ALIASES

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    logger.warning("Google API libraries not installed. Running in mock mode.")


SCOPES = ['https://www.googleapis.com/auth/calendar']


@dataclass
class CalendarEvent:
    """Calendar event structure."""
    id: str
    title: str
    start: str
    end: str
    attendees: List[str]
    description: Optional[str] = None
    location: Optional[str] = None
    zoom_link: Optional[str] = None
    calendar_id: str = "primary"


@dataclass
class TimeSlot:
    """Available time slot."""
    start: str
    end: str
    duration_minutes: int


class GoogleCalendarMCP:
    """
    Google Calendar MCP Server implementation.
    Provides calendar operations with built-in guardrails.
    """
    
    def __init__(self):
        self.config = get_config()
        self.guardrails = CalendarGuardrails()
        self._service = None
        self._create_lock = threading.Lock()
        self._request_count = 0
        self._request_times: List[float] = []
        
        logger.info("Google Calendar MCP Server initialized")
    
    def _get_service(self):
        """Get authenticated Google Calendar service."""
        if self._service:
            return self._service
        
        if not GOOGLE_API_AVAILABLE:
            return None
        
        creds = None
        token_path = PROJECT_ROOT / "token.json"
        creds_path = PROJECT_ROOT / "credentials.json"
        
        try:
            if token_path.exists():
                creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                    except Exception as e:
                        logger.warning(f"Failed to refresh credentials: {e}. Running in mock mode.")
                        return None
                elif creds_path.exists():
                    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
                    creds = flow.run_local_server(port=0)
                
                if creds:
                    token_path.write_text(creds.to_json())
            
            if creds and creds.valid:
                self._service = build('calendar', 'v3', credentials=creds)
        except Exception as e:
            logger.warning(f"Credential initialization error: {e}. Running in mock mode.")
            return None
        
        return self._service
    
    def _check_rate_limit(self) -> bool:
        """Check if within rate limits."""
        import time
        now = time.time()
        self._request_times = [t for t in self._request_times if now - t < 3600]
        
        if len(self._request_times) >= self.config.max_requests_per_hour:
            return False
        
        self._request_times.append(now)
        return True
    
    async def get_availability(
        self,
        calendar_id: str = "primary",
        start_time: str = None,
        end_time: str = None
    ) -> Dict[str, Any]:
        """
        Check calendar availability for a time range.
        
        Args:
            calendar_id: Calendar ID (default: primary)
            start_time: ISO start time (default: now)
            end_time: ISO end time (default: 7 days from now)
        
        Returns:
            Dict with busy/free slots
        """
        if not self._check_rate_limit():
            return {"error": "Rate limit exceeded", "success": False}
        
        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(start_time.replace('Z', '+00:00')) if start_time else now
        end = datetime.fromisoformat(end_time.replace('Z', '+00:00')) if end_time else now + timedelta(days=7)
        
        service = self._get_service()
        if not service:
            # Mock response for testing
            return {
                "success": True,
                "calendar_id": calendar_id,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "busy_slots": [],
                "free_slots": [
                    {"start": start.isoformat(), "end": end.isoformat()}
                ]
            }
        
        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "items": [{"id": calendar_id}]
        }
        
        result = service.freebusy().query(body=body).execute()
        busy = result.get('calendars', {}).get(calendar_id, {}).get('busy', [])
        
        return {
            "success": True,
            "calendar_id": calendar_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "busy_slots": busy,
            "free_slots": self._calculate_free_slots(start, end, busy)
        }
    
    def _calculate_free_slots(
        self,
        start: datetime,
        end: datetime,
        busy: List[Dict]
    ) -> List[Dict]:
        """Calculate free slots from busy periods."""
        if not busy:
            return [{"start": start.isoformat(), "end": end.isoformat()}]
        
        free = []
        current = start
        
        for slot in sorted(busy, key=lambda x: x['start']):
            slot_start = datetime.fromisoformat(slot['start'].replace('Z', '+00:00'))
            slot_end = datetime.fromisoformat(slot['end'].replace('Z', '+00:00'))
            
            if current < slot_start:
                free.append({"start": current.isoformat(), "end": slot_start.isoformat()})
            
            current = max(current, slot_end)
        
        if current < end:
            free.append({"start": current.isoformat(), "end": end.isoformat()})
        
        return free
    
    async def create_event(
        self,
        calendar_id: str = "primary",
        title: str = "",
        start_time: str = "",
        end_time: str = "",
        attendees: List[str] = None,
        description: str = "",
        zoom_link: str = None,
        timezone_str: str = "America/New_York"
    ) -> Dict[str, Any]:
        """
        Create a calendar event with guardrails.
        
        Args:
            calendar_id: Calendar ID
            title: Event title
            start_time: ISO start time
            end_time: ISO end time
            attendees: List of attendee emails
            description: Event description
            zoom_link: Optional Zoom meeting link
            timezone_str: Timezone for the event
        
        Returns:
            Created event details or error
        """
        if not self._check_rate_limit():
            return {"error": "Rate limit exceeded", "success": False}
        
        attendees = attendees or []
        
        # Validate and resolve timezone
        tz_valid, tz_resolved = self.guardrails.validate_timezone(timezone_str)
        if not tz_valid:
            logger.warning(f"Invalid timezone '{timezone_str}': {tz_resolved}. Using default.")
            timezone_str = self.config.default_timezone
        else:
            timezone_str = tz_resolved
        
        # Check if we have a real calendar service
        service = self._get_service()
        
        # Always validate with guardrails (including mock mode)
        validation = self.guardrails.validate_booking(
            start_time=start_time,
            end_time=end_time,
            calendar_id=calendar_id,
            timezone_str=timezone_str
        )
        
        if not validation.valid:
            return {
                "success": False,
                "error": validation.error,
                "suggestions": validation.suggestions
            }
        
        # Use mutex to prevent double-booking
        with self._create_lock:
            # Check availability one more time (only if we have a real service)
            if service:
                avail = await self.get_availability(calendar_id, start_time, end_time)
                if avail.get("busy_slots"):
                    return {
                        "success": False,
                        "error": "Time slot is no longer available (double-booking prevented)",
                        "busy_slots": avail["busy_slots"]
                    }
            
            event_body = {
                "summary": title,
                "description": description + (f"\n\nZoom: {zoom_link}" if zoom_link else ""),
                "start": {"dateTime": start_time, "timeZone": timezone_str},
                "end": {"dateTime": end_time, "timeZone": timezone_str},
                "attendees": [{"email": email} for email in attendees],
            }
            
            if zoom_link:
                event_body["conferenceData"] = {
                    "entryPoints": [{"entryPointType": "video", "uri": zoom_link}]
                }
            
            if not service:
                # Mock response
                event_id = f"mock_event_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                return {
                    "success": True,
                    "event_id": event_id,
                    "calendar_id": calendar_id,
                    "title": title,
                    "start": start_time,
                    "end": end_time,
                    "attendees": attendees,
                    "zoom_link": zoom_link,
                    "html_link": f"https://calendar.google.com/event?eid={event_id}"
                }
            
            event = service.events().insert(
                calendarId=calendar_id,
                body=event_body,
                sendUpdates="all"
            ).execute()
            
            return {
                "success": True,
                "event_id": event.get("id"),
                "calendar_id": calendar_id,
                "title": title,
                "start": start_time,
                "end": end_time,
                "attendees": attendees,
                "zoom_link": zoom_link,
                "html_link": event.get("htmlLink")
            }
    
    async def update_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        updates: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Update an existing calendar event.
        
        Args:
            event_id: Event ID to update
            calendar_id: Calendar ID
            updates: Dict with fields to update (title, start, end, description, attendees)
        
        Returns:
            Updated event details or error
        """
        if not self._check_rate_limit():
            return {"error": "Rate limit exceeded", "success": False}
        
        updates = updates or {}
        
        # Validate time changes if present
        if "start_time" in updates or "end_time" in updates:
            validation = self.guardrails.validate_booking(
                start_time=updates.get("start_time", ""),
                end_time=updates.get("end_time", ""),
                calendar_id=calendar_id
            )
            if not validation.valid:
                return {"success": False, "error": validation.error}
        
        service = self._get_service()
        
        if not service:
            return {
                "success": True,
                "event_id": event_id,
                "updated_fields": list(updates.keys()),
                "message": "Event updated (mock)"
            }
        
        # Get existing event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        
        # Apply updates
        if "title" in updates:
            event["summary"] = updates["title"]
        if "description" in updates:
            event["description"] = updates["description"]
        if "start_time" in updates:
            event["start"]["dateTime"] = updates["start_time"]
        if "end_time" in updates:
            event["end"]["dateTime"] = updates["end_time"]
        if "attendees" in updates:
            event["attendees"] = [{"email": e} for e in updates["attendees"]]
        
        updated = service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event,
            sendUpdates="all"
        ).execute()
        
        return {
            "success": True,
            "event_id": updated.get("id"),
            "updated_fields": list(updates.keys()),
            "html_link": updated.get("htmlLink")
        }
    
    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: bool = True
    ) -> Dict[str, Any]:
        """
        Delete/cancel a calendar event.
        
        Args:
            event_id: Event ID to delete
            calendar_id: Calendar ID
            send_updates: Whether to notify attendees
        
        Returns:
            Deletion result
        """
        if not self._check_rate_limit():
            return {"error": "Rate limit exceeded", "success": False}
        
        service = self._get_service()
        
        if not service:
            return {
                "success": True,
                "event_id": event_id,
                "message": "Event deleted (mock)"
            }
        
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
            sendUpdates="all" if send_updates else "none"
        ).execute()
        
        return {
            "success": True,
            "event_id": event_id,
            "message": "Event deleted successfully"
        }
    
    async def get_events(
        self,
        calendar_id: str = "primary",
        start_time: str = None,
        end_time: str = None,
        max_results: int = 50
    ) -> Dict[str, Any]:
        """
        List calendar events.
        
        Args:
            calendar_id: Calendar ID
            start_time: ISO start time (default: now)
            end_time: ISO end time (default: 30 days from now)
            max_results: Maximum events to return
        
        Returns:
            List of events
        """
        if not self._check_rate_limit():
            return {"error": "Rate limit exceeded", "success": False}
        
        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(start_time.replace('Z', '+00:00')) if start_time else now
        end = datetime.fromisoformat(end_time.replace('Z', '+00:00')) if end_time else now + timedelta(days=30)
        
        service = self._get_service()
        
        if not service:
            return {
                "success": True,
                "calendar_id": calendar_id,
                "events": [],
                "count": 0
            }
        
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        return {
            "success": True,
            "calendar_id": calendar_id,
            "events": [
                {
                    "id": e.get("id"),
                    "title": e.get("summary"),
                    "start": e.get("start", {}).get("dateTime"),
                    "end": e.get("end", {}).get("dateTime"),
                    "attendees": [a.get("email") for a in e.get("attendees", [])],
                    "html_link": e.get("htmlLink")
                }
                for e in events
            ],
            "count": len(events)
        }
    
    async def find_available_slots(
        self,
        calendar_ids: List[str] = None,
        duration_minutes: int = 30,
        start_date: str = None,
        end_date: str = None,
        working_hours_start: int = 9,
        working_hours_end: int = 18,
        timezone_str: str = "America/New_York",
        buffer_minutes: int = 15
    ) -> Dict[str, Any]:
        """
        Find available meeting slots across multiple calendars.
        
        Args:
            calendar_ids: List of calendar IDs to check
            duration_minutes: Meeting duration
            start_date: ISO start date
            end_date: ISO end date
            working_hours_start: Start of working hours (24h)
            working_hours_end: End of working hours (24h)
            timezone_str: Timezone for working hours
            buffer_minutes: Buffer between meetings
        
        Returns:
            List of available slots
        """
        if not self._check_rate_limit():
            return {"error": "Rate limit exceeded", "success": False}
        
        # Validate and resolve timezone
        tz_valid, tz_resolved = self.guardrails.validate_timezone(timezone_str)
        if not tz_valid:
            logger.warning(f"Invalid timezone '{timezone_str}': {tz_resolved}. Using default.")
            timezone_str = self.config.default_timezone
        else:
            timezone_str = tz_resolved
        
        calendar_ids = calendar_ids or ["primary"]
        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00')) if start_date else now
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00')) if end_date else now + timedelta(days=14)
        
        # Collect busy times from all calendars
        all_busy = []
        for cal_id in calendar_ids:
            avail = await self.get_availability(cal_id, start.isoformat(), end.isoformat())
            all_busy.extend(avail.get("busy_slots", []))
        
        # Generate available slots within working hours
        available_slots = []
        current_date = start.date()
        end_date_obj = end.date()
        
        while current_date <= end_date_obj:
            # Create working hours for this day
            day_start = datetime.combine(
                current_date,
                datetime.min.time().replace(hour=working_hours_start),
                tzinfo=timezone.utc
            )
            day_end = datetime.combine(
                current_date,
                datetime.min.time().replace(hour=working_hours_end),
                tzinfo=timezone.utc
            )
            
            # Find free slots within working hours
            slot_start = day_start
            while slot_start + timedelta(minutes=duration_minutes) <= day_end:
                slot_end = slot_start + timedelta(minutes=duration_minutes)
                
                # Check if slot overlaps with any busy period
                is_free = True
                for busy in all_busy:
                    busy_start = datetime.fromisoformat(busy["start"].replace('Z', '+00:00'))
                    busy_end = datetime.fromisoformat(busy["end"].replace('Z', '+00:00'))
                    
                    # Add buffer
                    busy_start -= timedelta(minutes=buffer_minutes)
                    busy_end += timedelta(minutes=buffer_minutes)
                    
                    if not (slot_end <= busy_start or slot_start >= busy_end):
                        is_free = False
                        break
                
                if is_free:
                    available_slots.append({
                        "start": slot_start.isoformat(),
                        "end": slot_end.isoformat(),
                        "duration_minutes": duration_minutes
                    })
                
                slot_start += timedelta(minutes=15)  # Check every 15 min
            
            current_date += timedelta(days=1)
        
        return {
            "success": True,
            "calendar_ids": calendar_ids,
            "duration_minutes": duration_minutes,
            "working_hours": f"{working_hours_start}:00-{working_hours_end}:00",
            "available_slots": available_slots[:50],  # Limit results
            "total_slots": len(available_slots)
        }
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Return MCP tool definitions."""
        return [
            {
                "name": "get_availability",
                "description": "Check calendar availability for a time range",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "calendar_id": {"type": "string", "default": "primary"},
                        "start_time": {"type": "string", "description": "ISO start time"},
                        "end_time": {"type": "string", "description": "ISO end time"}
                    }
                }
            },
            {
                "name": "create_event",
                "description": "Create a calendar event with optional Zoom link",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                        "calendar_id": {"type": "string", "default": "primary"},
                        "attendees": {"type": "array", "items": {"type": "string"}},
                        "description": {"type": "string"},
                        "zoom_link": {"type": "string"},
                        "timezone_str": {"type": "string", "default": "America/New_York"}
                    },
                    "required": ["title", "start_time", "end_time"]
                }
            },
            {
                "name": "update_event",
                "description": "Update an existing calendar event",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string"},
                        "calendar_id": {"type": "string", "default": "primary"},
                        "updates": {"type": "object"}
                    },
                    "required": ["event_id"]
                }
            },
            {
                "name": "delete_event",
                "description": "Delete/cancel a calendar event",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string"},
                        "calendar_id": {"type": "string", "default": "primary"},
                        "send_updates": {"type": "boolean", "default": True}
                    },
                    "required": ["event_id"]
                }
            },
            {
                "name": "get_events",
                "description": "List calendar events",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "calendar_id": {"type": "string", "default": "primary"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                        "max_results": {"type": "integer", "default": 50}
                    }
                }
            },
            {
                "name": "find_available_slots",
                "description": "Find available meeting slots across calendars",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "calendar_ids": {"type": "array", "items": {"type": "string"}},
                        "duration_minutes": {"type": "integer", "default": 30},
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"},
                        "working_hours_start": {"type": "integer", "default": 9},
                        "working_hours_end": {"type": "integer", "default": 18},
                        "timezone_str": {"type": "string", "default": "America/New_York"},
                        "buffer_minutes": {"type": "integer", "default": 15}
                    }
                }
            }
        ]


async def main():
    """Run MCP server."""
    import sys
    
    server = GoogleCalendarMCP()
    
    print("Google Calendar MCP Server")
    print("=" * 40)
    print("Tools available:")
    for tool in server.get_tools():
        print(f"  - {tool['name']}: {tool['description']}")
    
    # Demo
    print("\n[Demo: Find available slots]")
    slots = await server.find_available_slots(
        duration_minutes=30,
        working_hours_start=9,
        working_hours_end=17
    )
    print(f"  Found {slots['total_slots']} available slots")
    
    print("\n[Demo: Create event with guardrails]")
    # Try to create event outside working hours
    result = await server.create_event(
        title="Late Night Meeting",
        start_time="2026-01-22T23:00:00-05:00",
        end_time="2026-01-22T23:30:00-05:00"
    )
    print(f"  Result: {result.get('error', 'Created')}")
    
    # Create valid event
    result = await server.create_event(
        title="Strategy Session",
        start_time="2026-01-22T14:00:00-05:00",
        end_time="2026-01-22T14:30:00-05:00",
        attendees=["test@example.com"],
        zoom_link="https://zoom.us/j/123456789"
    )
    print(f"  Result: {'✅ Created' if result.get('success') else result.get('error')}")


if __name__ == "__main__":
    asyncio.run(main())
