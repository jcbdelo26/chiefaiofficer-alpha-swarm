#!/usr/bin/env python3
"""
GHL Calendar Client — Drop-in replacement for GoogleCalendarMCP
================================================================

Provides the same interface as GoogleCalendarMCP so the scheduler agent
can use GHL calendars without code changes.

GHL Calendar API endpoints used:
- GET  /calendars/                              → list calendars
- GET  /calendars/:calendarId/free-slots        → availability
- POST /calendars/events/appointments           → create appointment
- PUT  /calendars/events/appointments/:eventId  → update appointment
- DELETE /calendars/events/:eventId             → delete event
- GET  /calendars/events                        → list events

Usage:
    from mcp_servers.ghl_mcp.calendar_client import GHLCalendarClient

    calendar = GHLCalendarClient()
    slots = await calendar.find_available_slots(duration_minutes=30)
    event = await calendar.create_event(title="Discovery Call", ...)
"""

import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ghl-calendar-client")

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import the existing AsyncGHLClient (same directory)
try:
    # Ensure our own directory is first on path (avoid google-calendar-mcp server.py)
    _ghl_dir = str(Path(__file__).parent)
    if _ghl_dir not in sys.path[:3]:
        sys.path.insert(0, _ghl_dir)
    from server import AsyncGHLClient
except ImportError as e:
    logger.error(f"Cannot import AsyncGHLClient: {e}")
    AsyncGHLClient = None

# Import CalendarGuardrails (backend-agnostic — reused from google-calendar-mcp)
CalendarGuardrails = None
try:
    from mcp_servers.google_calendar_mcp.guardrails import CalendarGuardrails
except ImportError:
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "mcp-servers" / "google-calendar-mcp"))
        from guardrails import CalendarGuardrails
    except ImportError:
        logger.info("CalendarGuardrails not available — booking validation disabled")


class GHLCalendarClient:
    """
    GHL Calendar adapter matching the GoogleCalendarMCP interface.

    Drop-in replacement: the scheduler agent calls the same methods
    (find_available_slots, create_event, update_event, delete_event,
    get_events, get_availability) and gets the same response shapes.
    """

    def __init__(self, calendar_id: Optional[str] = None):
        """
        Args:
            calendar_id: GHL calendar ID. Falls back to GHL_CALENDAR_ID env var.
                         If not set, will be fetched from GHL API on first use.
        """
        if not AsyncGHLClient:
            raise ImportError("AsyncGHLClient not available")

        self._client = AsyncGHLClient()
        self._calendar_id = calendar_id or os.getenv("GHL_CALENDAR_ID")
        self._calendar_id_resolved = False

        # Reuse the backend-agnostic guardrails
        self.guardrails = CalendarGuardrails() if CalendarGuardrails else None

        logger.info(f"GHLCalendarClient initialized (calendar_id={self._calendar_id or 'auto-detect'})")

    async def _resolve_calendar_id(self, calendar_id: str = "primary") -> str:
        """Resolve 'primary' or None to an actual GHL calendar ID."""
        # If caller passed a real ID (not "primary"), use it
        if calendar_id and calendar_id != "primary":
            return calendar_id

        # If we already have a resolved ID, use it
        if self._calendar_id and self._calendar_id_resolved:
            return self._calendar_id

        # If set via env/constructor but not yet validated
        if self._calendar_id:
            self._calendar_id_resolved = True
            return self._calendar_id

        # Fetch from GHL API — use the first calendar
        try:
            result = await self._client.get_calendars()
            if result.get("success"):
                calendars = result.get("data", {}).get("calendars", [])
                if calendars:
                    self._calendar_id = calendars[0].get("id")
                    self._calendar_id_resolved = True
                    logger.info(f"Auto-detected GHL calendar: {self._calendar_id}")
                    return self._calendar_id
        except Exception as e:
            logger.warning(f"Failed to auto-detect calendar: {e}")

        raise ValueError(
            "No GHL calendar ID available. Set GHL_CALENDAR_ID env var "
            "or pass calendar_id to the constructor."
        )

    async def _resolve_contact_id(self, attendees: List[str]) -> Optional[str]:
        """Look up or create a GHL contact for the first attendee email."""
        if not attendees:
            return None

        email = attendees[0]

        # Look up by email
        try:
            result = await self._client.get_contact(email=email)
            if result.get("success"):
                data = result.get("data", {})
                # GHL nests contact data under "contacts" (plural, list) or "contact" (singular)
                contacts = data.get("contacts", [])
                if contacts:
                    return contacts[0].get("id")
                contact = data.get("contact", data)
                if contact and contact.get("id"):
                    return contact["id"]
        except Exception as e:
            logger.warning(f"Contact lookup failed for {email}: {e}")

        # Create a minimal contact so we can book
        try:
            result = await self._client.create_contact({
                "email": email,
                "source": "calendar_booking"
            })
            if result.get("success"):
                contact = result.get("data", {}).get("contact", {})
                contact_id = contact.get("id")
                if contact_id:
                    logger.info(f"Auto-created GHL contact for {email}: {contact_id}")
                    return contact_id
        except Exception as e:
            logger.warning(f"Contact creation failed for {email}: {e}")

        return None

    # =========================================================================
    # Public interface — matches GoogleCalendarMCP
    # =========================================================================

    async def find_available_slots(
        self,
        calendar_ids: Optional[List[str]] = None,
        duration_minutes: int = 30,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        working_hours_start: int = 9,
        working_hours_end: int = 18,
        timezone_str: str = "America/New_York",
        buffer_minutes: int = 15
    ) -> Dict[str, Any]:
        """
        Find available meeting slots — same interface as GoogleCalendarMCP.

        GHL's free-slots endpoint already respects the calendar's configured
        availability, so we just need to format the response.

        Returns:
            {success, available_slots[{start, end, duration_minutes}], total_slots}
        """
        now = datetime.now(timezone.utc)
        start = (
            datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if start_date else now
        )
        end = (
            datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if end_date else now + timedelta(days=14)
        )

        # Resolve calendar IDs
        resolved_ids = []
        for cid in (calendar_ids or ["primary"]):
            resolved_ids.append(await self._resolve_calendar_id(cid))

        all_slots = []
        for cal_id in resolved_ids:
            try:
                result = await self._client.get_free_slots(
                    calendar_id=cal_id,
                    start_date=start.isoformat(),
                    end_date=end.isoformat(),
                    timezone_str=timezone_str
                )

                if not result.get("success"):
                    logger.warning(f"Free-slots failed for {cal_id}: {result.get('error')}")
                    continue

                # Parse GHL response — slots are grouped by date
                data = result.get("data", {})

                # Handle different GHL response formats
                for date_key, date_data in data.items():
                    # Skip non-date keys (like metadata)
                    if not date_key or len(date_key) < 8:
                        continue

                    # date_data can be: {"slots": [...]} or [...] directly
                    if isinstance(date_data, dict):
                        slot_times = date_data.get("slots", [])
                    elif isinstance(date_data, list):
                        slot_times = date_data
                    else:
                        continue

                    for slot_time in slot_times:
                        try:
                            slot_start = datetime.fromisoformat(
                                slot_time.replace('Z', '+00:00')
                            )
                            slot_end = slot_start + timedelta(minutes=duration_minutes)

                            # Filter by working hours
                            if slot_start.hour < working_hours_start:
                                continue
                            if slot_start.hour >= working_hours_end:
                                continue

                            all_slots.append({
                                "start": slot_start.isoformat(),
                                "end": slot_end.isoformat(),
                                "duration_minutes": duration_minutes
                            })
                        except (ValueError, TypeError) as e:
                            logger.debug(f"Skipping invalid slot {slot_time}: {e}")

            except Exception as e:
                logger.warning(f"Error getting free slots for {cal_id}: {e}")

        # Sort by start time
        all_slots.sort(key=lambda s: s["start"])

        return {
            "success": True,
            "calendar_ids": resolved_ids,
            "duration_minutes": duration_minutes,
            "working_hours": f"{working_hours_start}:00-{working_hours_end}:00",
            "available_slots": all_slots[:50],
            "total_slots": len(all_slots)
        }

    async def create_event(
        self,
        calendar_id: str = "primary",
        title: str = "",
        start_time: str = "",
        end_time: str = "",
        attendees: Optional[List[str]] = None,
        description: str = "",
        zoom_link: Optional[str] = None,
        timezone_str: str = "America/New_York"
    ) -> Dict[str, Any]:
        """
        Create a calendar event — same interface as GoogleCalendarMCP.

        Maps to GHL POST /calendars/events/appointments.

        Returns:
            {success, event_id, calendar_id, title, start, end, attendees, zoom_link, html_link}
        """
        attendees = attendees or []

        # Validate with guardrails if available
        if self.guardrails:
            tz_valid, tz_resolved = self.guardrails.validate_timezone(timezone_str)
            if tz_valid:
                timezone_str = tz_resolved

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

        # Resolve calendar ID
        cal_id = await self._resolve_calendar_id(calendar_id)

        # Resolve contact ID from attendee email
        contact_id = await self._resolve_contact_id(attendees)
        if not contact_id and attendees:
            return {
                "success": False,
                "error": f"Could not resolve GHL contact for {attendees[0]}. "
                         f"Create the contact first via ghl_create_contact."
            }

        # Build appointment description with Zoom link
        full_description = description
        if zoom_link:
            full_description += f"\n\nZoom: {zoom_link}"

        # Create GHL appointment
        appointment_data = {
            "calendarId": cal_id,
            "contactId": contact_id,
            "startTime": start_time,
            "endTime": end_time,
            "title": title,
            "appointmentStatus": "confirmed",
            "toNotify": True,
        }
        if full_description.strip():
            appointment_data["notes"] = full_description.strip()

        result = await self._client.create_appointment(appointment_data)

        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Failed to create GHL appointment")
            }

        event_data = result.get("data", {})
        event_id = event_data.get("id", event_data.get("eventId", ""))

        return {
            "success": True,
            "event_id": event_id,
            "calendar_id": cal_id,
            "title": title,
            "start": start_time,
            "end": end_time,
            "attendees": attendees,
            "zoom_link": zoom_link,
            "html_link": f"https://app.gohighlevel.com/calendars/appointments/{event_id}"
        }

    async def update_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        updates: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update an existing event — same interface as GoogleCalendarMCP.

        Returns:
            {success, event_id, updated_fields}
        """
        updates = updates or {}

        # Validate time changes if present
        if self.guardrails and ("start_time" in updates or "end_time" in updates):
            validation = self.guardrails.validate_booking(
                start_time=updates.get("start_time", ""),
                end_time=updates.get("end_time", ""),
                calendar_id=calendar_id
            )
            if not validation.valid:
                return {"success": False, "error": validation.error}

        # Map GoogleCalendar field names to GHL field names
        ghl_updates = {}
        if "title" in updates:
            ghl_updates["title"] = updates["title"]
        if "start_time" in updates:
            ghl_updates["startTime"] = updates["start_time"]
        if "end_time" in updates:
            ghl_updates["endTime"] = updates["end_time"]
        if "description" in updates:
            ghl_updates["notes"] = updates["description"]

        result = await self._client.update_appointment(event_id, ghl_updates)

        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Failed to update GHL appointment")
            }

        return {
            "success": True,
            "event_id": event_id,
            "updated_fields": list(updates.keys()),
            "message": "Appointment updated via GHL"
        }

    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: bool = True
    ) -> Dict[str, Any]:
        """
        Delete a calendar event — same interface as GoogleCalendarMCP.

        Returns:
            {success, event_id, message}
        """
        result = await self._client.delete_calendar_event(event_id)

        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Failed to delete GHL event")
            }

        return {
            "success": True,
            "event_id": event_id,
            "message": "Event deleted via GHL"
        }

    async def get_events(
        self,
        calendar_id: str = "primary",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        max_results: int = 50
    ) -> Dict[str, Any]:
        """
        List calendar events — same interface as GoogleCalendarMCP.

        Returns:
            {success, calendar_id, events[], count}
        """
        cal_id = await self._resolve_calendar_id(calendar_id)

        result = await self._client.get_calendar_events(
            calendar_id=cal_id,
            start_time=start_time,
            end_time=end_time
        )

        if not result.get("success"):
            return {
                "success": True,
                "calendar_id": cal_id,
                "events": [],
                "count": 0
            }

        data = result.get("data", {})
        raw_events = data.get("events", [])

        events = []
        for e in raw_events[:max_results]:
            events.append({
                "id": e.get("id"),
                "title": e.get("title", e.get("name", "")),
                "start": e.get("startTime", e.get("start", "")),
                "end": e.get("endTime", e.get("end", "")),
                "attendees": [
                    a.get("email", "") for a in e.get("attendees", [])
                ] if isinstance(e.get("attendees"), list) else [],
                "html_link": f"https://app.gohighlevel.com/calendars/appointments/{e.get('id', '')}"
            })

        return {
            "success": True,
            "calendar_id": cal_id,
            "events": events,
            "count": len(events)
        }

    async def get_availability(
        self,
        calendar_id: str = "primary",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check calendar availability — same interface as GoogleCalendarMCP.

        Uses GHL free-slots to determine busy/free periods.

        Returns:
            {success, busy_slots, free_slots}
        """
        now = datetime.now(timezone.utc)
        start = (
            datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            if start_time else now
        )
        end = (
            datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            if end_time else now + timedelta(days=7)
        )

        cal_id = await self._resolve_calendar_id(calendar_id)

        # Get existing events to determine busy slots
        events_result = await self.get_events(
            calendar_id=cal_id,
            start_time=start.isoformat(),
            end_time=end.isoformat()
        )

        busy_slots = []
        if events_result.get("success"):
            for event in events_result.get("events", []):
                if event.get("start") and event.get("end"):
                    busy_slots.append({
                        "start": event["start"],
                        "end": event["end"]
                    })

        # Calculate free slots from busy
        free_slots = self._calculate_free_slots(start, end, busy_slots)

        return {
            "success": True,
            "calendar_id": cal_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "busy_slots": busy_slots,
            "free_slots": free_slots
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

        for slot in sorted(busy, key=lambda x: x.get('start', '')):
            try:
                slot_start = datetime.fromisoformat(slot['start'].replace('Z', '+00:00'))
                slot_end = datetime.fromisoformat(slot['end'].replace('Z', '+00:00'))
            except (ValueError, KeyError):
                continue

            if current < slot_start:
                free.append({"start": current.isoformat(), "end": slot_start.isoformat()})

            current = max(current, slot_end)

        if current < end:
            free.append({"start": current.isoformat(), "end": end.isoformat()})

        return free

    async def close(self):
        """Close the underlying HTTP client."""
        await self._client.close()
