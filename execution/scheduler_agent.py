#!/usr/bin/env python3
"""
Scheduler Agent - Beta Swarm
=============================
Calendar scheduling agent with full guardrails.

Capabilities:
1. Calendar availability checking (GHL Calendar API)
2. Time proposal generation (3-5 options, prospect's timezone)
3. Back-and-forth handling (max 5 exchanges, then escalate)
4. Calendar invite creation with Zoom link
5. Conflict detection and resolution

Guardrails:
- Never double-book (check before create)
- Respect working hours (9 AM - 6 PM)
- Minimum 15-min buffer between meetings
- Max 5 scheduling exchanges (then escalate to human)
- Always convert to prospect's timezone

Self-Annealing:
- Log successful booking patterns
- Track average exchanges to book
- Learn preferred time slots per prospect
- Update ReasoningBank with scheduling heuristics

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                     SCHEDULER AGENT                              │
    ├─────────────────────────────────────────────────────────────────┤
    │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
    │  │ Availability    │  │ Time Proposal   │  │ Booking         │ │
    │  │ Checker         │  │ Generator       │  │ Manager         │ │
    │  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
    │           │                    │                    │          │
    │           └────────────────────┴────────────────────┘          │
    │                              │                                  │
    │                    ┌─────────▼─────────┐                       │
    │                    │ GHL Calendar      │                       │
    │                    │ Client (API)      │                       │
    │                    └───────────────────┘                       │
    └─────────────────────────────────────────────────────────────────┘

Usage:
    from execution.scheduler_agent import SchedulerAgent
    
    scheduler = SchedulerAgent()
    
    # Check availability
    slots = await scheduler.check_availability(
        prospect_email="john@example.com",
        prospect_timezone="America/New_York"
    )
    
    # Generate time proposals
    proposals = await scheduler.generate_proposals(
        duration_minutes=30,
        prospect_timezone="America/New_York",
        num_proposals=5
    )
    
    # Book meeting
    result = await scheduler.book_meeting(
        prospect_email="john@example.com",
        start_time="2026-01-23T14:00:00-05:00",
        duration_minutes=30,
        title="Discovery Call",
        with_zoom=True
    )
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scheduler_agent")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import GHL Calendar Client (drop-in replacement for GoogleCalendarMCP)
try:
    from mcp_servers.ghl_mcp.calendar_client import GHLCalendarClient
except ImportError:
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "mcp-servers" / "ghl-mcp"))
        from calendar_client import GHLCalendarClient
    except ImportError as e:
        logger.warning(f"GHL Calendar Client not available: {e}")
        GHLCalendarClient = None

# Import CalendarGuardrails (backend-agnostic)
try:
    from mcp_servers.google_calendar_mcp.guardrails import CalendarGuardrails, TIMEZONE_ALIASES
except ImportError:
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "mcp-servers" / "google-calendar-mcp"))
        from guardrails import CalendarGuardrails, TIMEZONE_ALIASES
    except ImportError:
        CalendarGuardrails = None
        TIMEZONE_ALIASES = {}


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class SchedulingStatus(Enum):
    """Status of a scheduling request."""
    PENDING = "pending"
    AWAITING_RESPONSE = "awaiting_response"
    CONFIRMED = "confirmed"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"
    ESCALATED = "escalated"
    FAILED = "failed"


class ExchangeType(Enum):
    """Type of scheduling exchange."""
    INITIAL_PROPOSAL = "initial_proposal"
    COUNTER_PROPOSAL = "counter_proposal"
    PROSPECT_PROPOSAL = "prospect_proposal"
    CONFIRMATION = "confirmation"
    REJECTION = "rejection"
    RESCHEDULE_REQUEST = "reschedule_request"


# Guardrail Constants
MAX_SCHEDULING_EXCHANGES = 5
DEFAULT_MEETING_DURATION = 30
WORKING_HOURS_START = 9
WORKING_HOURS_END = 18
MIN_BUFFER_MINUTES = 15
MAX_LOOKAHEAD_DAYS = 14
MIN_NOTICE_HOURS = 2
DEFAULT_TIMEZONE = "America/New_York"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SchedulingRequest:
    """A scheduling request from a prospect or agent."""
    request_id: str
    prospect_email: str
    prospect_name: str
    prospect_timezone: str
    prospect_company: str
    meeting_type: str = "discovery"
    duration_minutes: int = DEFAULT_MEETING_DURATION
    preferred_times: List[str] = field(default_factory=list)
    exchange_count: int = 0
    status: SchedulingStatus = SchedulingStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ghl_contact_id: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class TimeProposal:
    """A proposed meeting time."""
    proposal_id: str
    start_time: str  # ISO format in prospect's timezone
    end_time: str
    start_time_utc: str
    end_time_utc: str
    timezone: str
    duration_minutes: int
    display_text: str  # Human-friendly format
    is_available: bool = True
    confidence: float = 1.0


@dataclass
class SchedulingExchange:
    """A single exchange in the scheduling conversation."""
    exchange_id: str
    request_id: str
    exchange_type: ExchangeType
    proposed_times: List[str]
    message: str
    sender: str  # "agent" or "prospect"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    response: Optional[str] = None


@dataclass
class BookingResult:
    """Result of a booking attempt."""
    success: bool
    event_id: Optional[str] = None
    calendar_link: Optional[str] = None
    zoom_link: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class SchedulingMetrics:
    """Metrics for self-annealing learning."""
    request_id: str
    prospect_email: str
    exchanges_to_book: int
    booking_success: bool
    accepted_slot_index: Optional[int]  # Which of the proposals was accepted (0-4)
    accepted_day_of_week: Optional[int]  # 0=Mon, 6=Sun
    accepted_hour: Optional[int]
    prospect_timezone: str
    total_duration_hours: float  # Time from first proposal to booking
    escalated: bool
    notes: str = ""


# =============================================================================
# SCHEDULER AGENT
# =============================================================================

class SchedulerAgent:
    """
    Scheduler Agent for the Beta Swarm.
    
    Handles all calendar scheduling with built-in guardrails,
    timezone management, and self-annealing learning.
    """
    
    def __init__(self, calendar_client=None):
        """
        Initialize the Scheduler Agent.

        Args:
            calendar_client: Optional pre-configured calendar client instance.
                             Accepts GHLCalendarClient (default) or GoogleCalendarMCP.
        """
        # Calendar integration — GHL Calendar is the default backend
        if calendar_client:
            self.calendar = calendar_client
        elif GHLCalendarClient:
            try:
                self.calendar = GHLCalendarClient()
            except Exception as e:
                logger.warning(f"GHL Calendar init failed: {e}. Running in mock mode.")
                self.calendar = None
        else:
            self.calendar = None
            logger.warning("Running in mock mode - no calendar integration")
        
        # Guardrails
        if CalendarGuardrails:
            self.guardrails = CalendarGuardrails()
        else:
            self.guardrails = None
        
        # State
        self._active_requests: Dict[str, SchedulingRequest] = {}
        self._exchanges: Dict[str, List[SchedulingExchange]] = {}
        self._metrics: List[SchedulingMetrics] = []
        
        # Hive-mind storage
        self.hive_mind = PROJECT_ROOT / ".hive-mind"
        self.scheduler_dir = self.hive_mind / "scheduler"
        self.scheduler_dir.mkdir(parents=True, exist_ok=True)
        
        # Load learned patterns
        self._patterns = self._load_patterns()
        
        logger.info("Scheduler Agent initialized")
    
    def _load_patterns(self) -> Dict[str, Any]:
        """Load learned scheduling patterns from hive-mind."""
        patterns_file = self.scheduler_dir / "patterns.json"
        if patterns_file.exists():
            try:
                return json.loads(patterns_file.read_text())
            except Exception as e:
                logger.warning(f"Failed to load patterns: {e}")
        
        return {
            "preferred_hours": {
                # Default preferences (learned over time)
                "America/New_York": [10, 11, 14, 15],
                "America/Los_Angeles": [10, 11, 14, 15],
                "Europe/London": [10, 11, 14, 15],
                "Asia/Manila": [10, 11, 14, 15],
            },
            "avoid_hours": [12, 13],  # Lunch
            "success_by_day": {
                # 0=Monday, success rates
                "0": 0.85, "1": 0.90, "2": 0.92,
                "3": 0.88, "4": 0.75, "5": 0.20, "6": 0.10
            },
            "avg_exchanges_to_book": 1.8,
            "proposal_acceptance_rate": [0.4, 0.25, 0.20, 0.10, 0.05],  # By position
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    
    def _save_patterns(self):
        """Save learned patterns to hive-mind."""
        patterns_file = self.scheduler_dir / "patterns.json"
        self._patterns["updated_at"] = datetime.now(timezone.utc).isoformat()
        patterns_file.write_text(json.dumps(self._patterns, indent=2))
    
    def _generate_id(self, prefix: str = "SCH") -> str:
        """Generate a unique ID."""
        hash_input = f"{prefix}:{datetime.now().isoformat()}:{id(self)}"
        return f"{prefix}-{hashlib.md5(hash_input.encode()).hexdigest()[:8].upper()}"
    
    # =========================================================================
    # CORE SCHEDULING METHODS
    # =========================================================================
    
    async def check_availability(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        calendar_id: str = "primary"
    ) -> Dict[str, Any]:
        """
        Check calendar availability for a date range.
        
        Args:
            start_date: ISO start date (default: now)
            end_date: ISO end date (default: 14 days from now)
            calendar_id: Calendar to check
        
        Returns:
            Availability info with free/busy slots
        """
        if not self.calendar:
            # Mock response
            return {
                "success": True,
                "calendar_id": calendar_id,
                "busy_slots": [],
                "free_slots": [],
                "message": "Mock mode - no real calendar data"
            }
        
        return await self.calendar.get_availability(
            calendar_id=calendar_id,
            start_time=start_date,
            end_time=end_date
        )
    
    async def generate_proposals(
        self,
        prospect_timezone: str,
        duration_minutes: int = DEFAULT_MEETING_DURATION,
        num_proposals: int = 5,
        calendar_id: str = "primary",
        exclude_dates: Optional[List[str]] = None
    ) -> List[TimeProposal]:
        """
        Generate meeting time proposals for a prospect.
        
        Uses learned patterns to prioritize likely-to-be-accepted times.
        
        Args:
            prospect_timezone: Prospect's timezone
            duration_minutes: Meeting duration in minutes
            num_proposals: Number of proposals to generate (3-5)
            calendar_id: Calendar to check availability against
            exclude_dates: Dates to exclude (ISO format)
        
        Returns:
            List of TimeProposal objects ranked by likelihood of acceptance
        """
        num_proposals = max(3, min(5, num_proposals))
        exclude_dates = exclude_dates or []
        
        # Validate timezone
        tz_resolved = self._resolve_timezone(prospect_timezone)
        
        # Get available slots
        if self.calendar:
            slots_result = await self.calendar.find_available_slots(
                calendar_ids=[calendar_id],
                duration_minutes=duration_minutes,
                working_hours_start=WORKING_HOURS_START,
                working_hours_end=WORKING_HOURS_END,
                timezone_str=tz_resolved,
                buffer_minutes=MIN_BUFFER_MINUTES
            )
            available_slots = slots_result.get("available_slots", [])
        else:
            # Mock slots
            available_slots = self._generate_mock_slots(duration_minutes)
        
        # Score and rank slots
        scored_slots = self._score_slots(available_slots, tz_resolved, exclude_dates)
        
        # Take top proposals
        top_slots = sorted(scored_slots, key=lambda x: x["score"], reverse=True)[:num_proposals]
        
        # Convert to TimeProposal objects
        proposals = []
        for slot in top_slots:
            proposal = TimeProposal(
                proposal_id=self._generate_id("PROP"),
                start_time=slot["start_local"],
                end_time=slot["end_local"],
                start_time_utc=slot["start"],
                end_time_utc=slot["end"],
                timezone=tz_resolved,
                duration_minutes=duration_minutes,
                display_text=self._format_time_display(slot["start_local"], tz_resolved),
                is_available=True,
                confidence=slot["score"]
            )
            proposals.append(proposal)
        
        logger.info(f"Generated {len(proposals)} time proposals for {tz_resolved}")
        return proposals
    
    async def create_scheduling_request(
        self,
        prospect_email: str,
        prospect_name: str,
        prospect_timezone: str,
        prospect_company: str,
        meeting_type: str = "discovery",
        duration_minutes: int = DEFAULT_MEETING_DURATION,
        ghl_contact_id: Optional[str] = None
    ) -> Tuple[SchedulingRequest, List[TimeProposal]]:
        """
        Create a new scheduling request and generate initial proposals.
        
        Args:
            prospect_email: Prospect's email
            prospect_name: Prospect's name
            prospect_timezone: Prospect's timezone
            prospect_company: Prospect's company
            meeting_type: Type of meeting
            duration_minutes: Meeting duration
            ghl_contact_id: GHL contact ID
        
        Returns:
            Tuple of (SchedulingRequest, List[TimeProposal])
        """
        request_id = self._generate_id("REQ")
        
        tz_resolved = self._resolve_timezone(prospect_timezone)
        
        request = SchedulingRequest(
            request_id=request_id,
            prospect_email=prospect_email,
            prospect_name=prospect_name,
            prospect_timezone=tz_resolved,
            prospect_company=prospect_company,
            meeting_type=meeting_type,
            duration_minutes=duration_minutes,
            ghl_contact_id=ghl_contact_id,
            status=SchedulingStatus.PENDING
        )
        
        # Generate proposals
        proposals = await self.generate_proposals(
            prospect_timezone=tz_resolved,
            duration_minutes=duration_minutes
        )
        
        # Store preferred times
        request.preferred_times = [p.start_time for p in proposals]
        
        # Record initial exchange
        exchange = SchedulingExchange(
            exchange_id=self._generate_id("EXC"),
            request_id=request_id,
            exchange_type=ExchangeType.INITIAL_PROPOSAL,
            proposed_times=[p.display_text for p in proposals],
            message=self._format_proposal_message(prospect_name, proposals),
            sender="agent"
        )
        
        # Store in state
        self._active_requests[request_id] = request
        self._exchanges[request_id] = [exchange]
        
        # Update request status
        request.status = SchedulingStatus.AWAITING_RESPONSE
        request.exchange_count = 1
        
        logger.info(f"Created scheduling request {request_id} for {prospect_email}")
        
        return request, proposals
    
    async def handle_prospect_response(
        self,
        request_id: str,
        response_type: str,
        selected_time: Optional[str] = None,
        counter_times: Optional[List[str]] = None,
        message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle a prospect's response to scheduling proposals.
        
        Args:
            request_id: Scheduling request ID
            response_type: "accept", "counter", "reject", "reschedule"
            selected_time: Selected time if accepting
            counter_times: Counter-proposed times
            message: Message from prospect
        
        Returns:
            Result dict with next action
        """
        if request_id not in self._active_requests:
            return {"error": f"Request {request_id} not found", "success": False}
        
        request = self._active_requests[request_id]
        request.exchange_count += 1
        request.updated_at = datetime.now(timezone.utc).isoformat()
        
        # Check escalation threshold
        if request.exchange_count >= MAX_SCHEDULING_EXCHANGES:
            return await self._escalate_request(request, "Max exchanges reached")
        
        # Handle by response type
        if response_type == "accept" and selected_time:
            return await self._handle_acceptance(request, selected_time)
        
        elif response_type == "counter" and counter_times:
            return await self._handle_counter_proposal(request, counter_times, message)
        
        elif response_type == "reject":
            return await self._handle_rejection(request, message)
        
        elif response_type == "reschedule":
            return await self._handle_reschedule(request, message)
        
        else:
            return {"error": "Invalid response type", "success": False}
    
    async def book_meeting(
        self,
        prospect_email: str,
        start_time: str,
        duration_minutes: int = DEFAULT_MEETING_DURATION,
        title: str = "Discovery Call",
        description: str = "",
        with_zoom: bool = True,
        calendar_id: str = "primary",
        request_id: Optional[str] = None
    ) -> BookingResult:
        """
        Book a meeting on the calendar.
        
        Args:
            prospect_email: Prospect's email
            start_time: ISO start time
            duration_minutes: Meeting duration
            title: Meeting title
            description: Meeting description
            with_zoom: Whether to include Zoom link
            calendar_id: Calendar to book on
            request_id: Associated scheduling request ID
        
        Returns:
            BookingResult with success/failure details
        """
        # Calculate end time
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            end_time = end_dt.isoformat()
        except Exception as e:
            return BookingResult(
                success=False,
                error=f"Invalid start time: {e}"
            )
        
        # Generate Zoom link (mock)
        zoom_link = None
        if with_zoom:
            zoom_link = f"https://zoom.us/j/{self._generate_id('ZOOM').replace('ZOOM-', '')}"
        
        # Book via calendar MCP
        if self.calendar:
            result = await self.calendar.create_event(
                calendar_id=calendar_id,
                title=title,
                start_time=start_time,
                end_time=end_time,
                attendees=[prospect_email],
                description=description,
                zoom_link=zoom_link
            )
            
            if not result.get("success"):
                return BookingResult(
                    success=False,
                    error=result.get("error", "Unknown error"),
                    warnings=result.get("suggestions", [])
                )
            
            booking_result = BookingResult(
                success=True,
                event_id=result.get("event_id"),
                calendar_link=result.get("html_link"),
                zoom_link=zoom_link,
                start_time=start_time,
                end_time=end_time
            )
        else:
            # Mock booking
            mock_id = self._generate_id("EVT")
            booking_result = BookingResult(
                success=True,
                event_id=mock_id,
                calendar_link=f"https://app.gohighlevel.com/calendars/appointments/{mock_id}",
                zoom_link=zoom_link,
                start_time=start_time,
                end_time=end_time,
                warnings=["Mock mode - no real calendar event created"]
            )
        
        # Update request if provided
        if request_id and request_id in self._active_requests:
            request = self._active_requests[request_id]
            request.status = SchedulingStatus.CONFIRMED
            request.updated_at = datetime.now(timezone.utc).isoformat()
            
            # Log metrics for learning
            self._log_booking_metrics(request, booking_result)
        
        logger.info(f"Meeting booked: {title} at {start_time}")
        return booking_result
    
    async def update_meeting(
        self,
        event_id: str,
        updates: Dict[str, Any],
        calendar_id: str = "primary"
    ) -> Dict[str, Any]:
        """
        Update an existing meeting.
        
        Args:
            event_id: Event ID to update
            updates: Fields to update (start_time, end_time, title, etc.)
            calendar_id: Calendar containing the event
        
        Returns:
            Update result
        """
        if not self.calendar:
            return {
                "success": True,
                "event_id": event_id,
                "message": "Mock update - no real calendar"
            }
        
        return await self.calendar.update_event(
            event_id=event_id,
            calendar_id=calendar_id,
            updates=updates
        )
    
    async def cancel_meeting(
        self,
        event_id: str,
        calendar_id: str = "primary",
        notify_attendees: bool = True
    ) -> Dict[str, Any]:
        """
        Cancel a scheduled meeting.
        
        Args:
            event_id: Event ID to cancel
            calendar_id: Calendar containing the event
            notify_attendees: Whether to notify attendees
        
        Returns:
            Cancellation result
        """
        if not self.calendar:
            return {
                "success": True,
                "event_id": event_id,
                "message": "Mock cancellation - no real calendar"
            }
        
        return await self.calendar.delete_event(
            event_id=event_id,
            calendar_id=calendar_id,
            send_updates=notify_attendees
        )
    
    # =========================================================================
    # INTERNAL HELPER METHODS
    # =========================================================================
    
    def _resolve_timezone(self, timezone_str: str) -> str:
        """Resolve timezone alias to IANA name."""
        if not timezone_str:
            return DEFAULT_TIMEZONE
        
        upper_tz = timezone_str.upper().strip()
        if upper_tz in TIMEZONE_ALIASES:
            return TIMEZONE_ALIASES[upper_tz]
        
        return timezone_str
    
    def _score_slots(
        self,
        slots: List[Dict],
        timezone_str: str,
        exclude_dates: List[str]
    ) -> List[Dict]:
        """Score slots based on learned patterns."""
        scored = []
        preferred_hours = self._patterns.get("preferred_hours", {}).get(
            timezone_str, [10, 11, 14, 15]
        )
        avoid_hours = self._patterns.get("avoid_hours", [12, 13])
        success_by_day = self._patterns.get("success_by_day", {})
        
        for slot in slots:
            try:
                start = datetime.fromisoformat(slot["start"].replace('Z', '+00:00'))
            except:
                continue
            
            # Check if excluded
            if start.date().isoformat() in exclude_dates:
                continue
            
            score = 0.5  # Base score
            
            # Prefer learned hours
            if start.hour in preferred_hours:
                score += 0.3
            
            # Avoid lunch and late hours
            if start.hour in avoid_hours:
                score -= 0.2
            
            # Day of week preference
            day_score = float(success_by_day.get(str(start.weekday()), 0.5))
            score += (day_score - 0.5) * 0.2
            
            # Prefer earlier in the lookahead window (urgency)
            days_out = (start - datetime.now(timezone.utc)).days
            if days_out <= 3:
                score += 0.1
            elif days_out > 7:
                score -= 0.05
            
            # Convert to local time for display
            try:
                if self.guardrails:
                    local_start, _ = self.guardrails.convert_timezone_safe(
                        slot["start"], "UTC", timezone_str
                    )
                    local_end, _ = self.guardrails.convert_timezone_safe(
                        slot["end"], "UTC", timezone_str
                    )
                else:
                    local_start = slot["start"]
                    local_end = slot["end"]
            except:
                local_start = slot["start"]
                local_end = slot["end"]
            
            scored.append({
                **slot,
                "start_local": local_start,
                "end_local": local_end,
                "score": min(1.0, max(0.0, score))
            })
        
        return scored
    
    def _generate_mock_slots(self, duration_minutes: int) -> List[Dict]:
        """Generate mock available slots for testing."""
        slots = []
        now = datetime.now(timezone.utc)
        current = now + timedelta(hours=2)  # Start 2 hours from now
        
        # Generate slots in America/New_York working hours (9 AM - 6 PM EST)
        # EST is UTC-5, so 9 AM EST = 14:00 UTC, 6 PM EST = 23:00 UTC
        working_start_utc = 14  # 9 AM EST in UTC
        working_end_utc = 23    # 6 PM EST in UTC
        
        for day in range(MAX_LOOKAHEAD_DAYS):
            day_start = (current + timedelta(days=day)).replace(
                hour=working_start_utc, minute=0, second=0, microsecond=0
            )
            day_end = day_start.replace(hour=working_end_utc)
            
            # Skip weekends
            if day_start.weekday() >= 5:
                continue
            
            # Generate slots every 30 minutes
            slot_start = day_start
            while slot_start + timedelta(minutes=duration_minutes) <= day_end:
                # Skip lunch (12-1pm EST = 17-18 UTC)
                if slot_start.hour not in [17, 18]:
                    slots.append({
                        "start": slot_start.isoformat(),
                        "end": (slot_start + timedelta(minutes=duration_minutes)).isoformat(),
                        "duration_minutes": duration_minutes
                    })
                slot_start += timedelta(minutes=30)
        
        return slots[:50]  # Limit
    
    def _format_time_display(self, iso_time: str, timezone_str: str) -> str:
        """Format time for human-readable display."""
        try:
            dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
            # Format: "Monday, January 23 at 2:00 PM EST"
            day_name = dt.strftime("%A")
            # Use %#d for Windows, %-d for Unix (we try both)
            try:
                month_day = dt.strftime("%B %#d")  # Windows
            except ValueError:
                month_day = dt.strftime("%B %-d")  # Unix/Mac
            
            try:
                time_str = dt.strftime("%#I:%M %p")  # Windows
            except ValueError:
                time_str = dt.strftime("%-I:%M %p")  # Unix/Mac
            
            # Get timezone abbreviation
            tz_abbr = timezone_str.split("/")[-1][:3].upper()
            
            return f"{day_name}, {month_day} at {time_str} {tz_abbr}"
        except Exception as e:
            logger.warning(f"Failed to format time: {e}")
            return iso_time
    
    def _format_proposal_message(
        self,
        prospect_name: str,
        proposals: List[TimeProposal]
    ) -> str:
        """Format proposal message for prospect."""
        times_list = "\n".join([
            f"  {i+1}. {p.display_text}"
            for i, p in enumerate(proposals)
        ])
        
        return f"""Hi {prospect_name},

I'd love to schedule a quick call to discuss how we can help. Here are some times that work on my end:

{times_list}

Let me know which works best for you, or feel free to suggest an alternative time.

Looking forward to connecting!"""
    
    async def _handle_acceptance(
        self,
        request: SchedulingRequest,
        selected_time: str
    ) -> Dict[str, Any]:
        """Handle prospect accepting a proposed time."""
        # Book the meeting
        title = f"{request.meeting_type.title()} Call: {request.prospect_company}"
        
        result = await self.book_meeting(
            prospect_email=request.prospect_email,
            start_time=selected_time,
            duration_minutes=request.duration_minutes,
            title=title,
            with_zoom=True,
            request_id=request.request_id
        )
        
        if result.success:
            # Record exchange
            exchange = SchedulingExchange(
                exchange_id=self._generate_id("EXC"),
                request_id=request.request_id,
                exchange_type=ExchangeType.CONFIRMATION,
                proposed_times=[selected_time],
                message="Meeting confirmed",
                sender="prospect"
            )
            self._exchanges[request.request_id].append(exchange)
            
            return {
                "success": True,
                "action": "booked",
                "event_id": result.event_id,
                "calendar_link": result.calendar_link,
                "zoom_link": result.zoom_link,
                "start_time": result.start_time,
                "end_time": result.end_time
            }
        else:
            return {
                "success": False,
                "action": "booking_failed",
                "error": result.error
            }
    
    async def _handle_counter_proposal(
        self,
        request: SchedulingRequest,
        counter_times: List[str],
        message: Optional[str]
    ) -> Dict[str, Any]:
        """Handle prospect proposing alternative times."""
        # Record exchange
        exchange = SchedulingExchange(
            exchange_id=self._generate_id("EXC"),
            request_id=request.request_id,
            exchange_type=ExchangeType.PROSPECT_PROPOSAL,
            proposed_times=counter_times,
            message=message or "Prospect proposed alternative times",
            sender="prospect"
        )
        self._exchanges[request.request_id].append(exchange)
        
        # Check if any proposed times work
        valid_times = []
        for time_str in counter_times:
            # Validate time
            if self.guardrails:
                try:
                    dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                    end_time = (dt + timedelta(minutes=request.duration_minutes)).isoformat()
                    
                    validation = self.guardrails.validate_booking(
                        start_time=time_str,
                        end_time=end_time,
                        timezone_str=request.prospect_timezone
                    )
                    
                    if validation.valid:
                        valid_times.append(time_str)
                except Exception as e:
                    logger.warning(f"Invalid counter time {time_str}: {e}")
            else:
                valid_times.append(time_str)
        
        if valid_times:
            return {
                "success": True,
                "action": "review_counter",
                "valid_times": valid_times,
                "message": "Prospect proposed times, review and accept or counter"
            }
        else:
            # Generate new proposals
            new_proposals = await self.generate_proposals(
                prospect_timezone=request.prospect_timezone,
                duration_minutes=request.duration_minutes
            )
            
            return {
                "success": True,
                "action": "send_counter",
                "proposals": [asdict(p) for p in new_proposals],
                "message": "Proposed times don't work, sending new proposals"
            }
    
    async def _handle_rejection(
        self,
        request: SchedulingRequest,
        message: Optional[str]
    ) -> Dict[str, Any]:
        """Handle prospect rejecting scheduling."""
        request.status = SchedulingStatus.CANCELLED
        
        exchange = SchedulingExchange(
            exchange_id=self._generate_id("EXC"),
            request_id=request.request_id,
            exchange_type=ExchangeType.REJECTION,
            proposed_times=[],
            message=message or "Prospect declined to schedule",
            sender="prospect"
        )
        self._exchanges[request.request_id].append(exchange)
        
        return {
            "success": True,
            "action": "rejected",
            "message": "Scheduling request cancelled by prospect"
        }
    
    async def _handle_reschedule(
        self,
        request: SchedulingRequest,
        message: Optional[str]
    ) -> Dict[str, Any]:
        """Handle reschedule request."""
        request.status = SchedulingStatus.RESCHEDULED
        request.exchange_count = 0  # Reset for new scheduling
        
        # Generate new proposals
        new_proposals = await self.generate_proposals(
            prospect_timezone=request.prospect_timezone,
            duration_minutes=request.duration_minutes
        )
        
        exchange = SchedulingExchange(
            exchange_id=self._generate_id("EXC"),
            request_id=request.request_id,
            exchange_type=ExchangeType.RESCHEDULE_REQUEST,
            proposed_times=[p.display_text for p in new_proposals],
            message=message or "Rescheduling requested",
            sender="agent"
        )
        self._exchanges[request.request_id].append(exchange)
        
        request.status = SchedulingStatus.AWAITING_RESPONSE
        
        return {
            "success": True,
            "action": "rescheduling",
            "proposals": [asdict(p) for p in new_proposals],
            "message": self._format_proposal_message(request.prospect_name, new_proposals)
        }
    
    async def _escalate_request(
        self,
        request: SchedulingRequest,
        reason: str
    ) -> Dict[str, Any]:
        """Escalate scheduling to human."""
        request.status = SchedulingStatus.ESCALATED
        
        logger.warning(f"Escalating scheduling request {request.request_id}: {reason}")
        
        # Save escalation details - convert ExchangeType enum to string
        def serialize_exchange(e):
            d = asdict(e)
            if 'exchange_type' in d and isinstance(d['exchange_type'], ExchangeType):
                d['exchange_type'] = d['exchange_type'].value
            elif 'exchange_type' in d and hasattr(d['exchange_type'], 'value'):
                d['exchange_type'] = d['exchange_type'].value
            return d
        
        escalation = {
            "request_id": request.request_id,
            "prospect_email": request.prospect_email,
            "prospect_name": request.prospect_name,
            "prospect_company": request.prospect_company,
            "exchange_count": request.exchange_count,
            "reason": reason,
            "exchanges": [serialize_exchange(e) for e in self._exchanges.get(request.request_id, [])],
            "escalated_at": datetime.now(timezone.utc).isoformat()
        }
        
        escalation_file = self.scheduler_dir / f"escalation_{request.request_id}.json"
        escalation_file.write_text(json.dumps(escalation, indent=2))
        
        return {
            "success": True,
            "action": "escalated",
            "reason": reason,
            "message": f"Request escalated after {request.exchange_count} exchanges. Human intervention required."
        }
    
    def _log_booking_metrics(self, request: SchedulingRequest, result: BookingResult):
        """Log metrics for self-annealing learning."""
        if not result.success:
            return
        
        try:
            start_dt = datetime.fromisoformat(result.start_time.replace('Z', '+00:00'))
            
            # Find which proposal was accepted (if any)
            accepted_index = None
            for i, pt in enumerate(request.preferred_times):
                if pt == result.start_time:
                    accepted_index = i
                    break
            
            metrics = SchedulingMetrics(
                request_id=request.request_id,
                prospect_email=request.prospect_email,
                exchanges_to_book=request.exchange_count,
                booking_success=True,
                accepted_slot_index=accepted_index,
                accepted_day_of_week=start_dt.weekday(),
                accepted_hour=start_dt.hour,
                prospect_timezone=request.prospect_timezone,
                total_duration_hours=(
                    datetime.now(timezone.utc) - 
                    datetime.fromisoformat(request.created_at.replace('Z', '+00:00'))
                ).total_seconds() / 3600,
                escalated=request.status == SchedulingStatus.ESCALATED
            )
            
            self._metrics.append(metrics)
            
            # Update patterns
            self._update_patterns(metrics)
            
        except Exception as e:
            logger.warning(f"Failed to log booking metrics: {e}")
    
    def _update_patterns(self, metrics: SchedulingMetrics):
        """Update learned patterns from booking outcome."""
        # Update preferred hours
        if metrics.accepted_hour is not None:
            tz = metrics.prospect_timezone
            if tz not in self._patterns["preferred_hours"]:
                self._patterns["preferred_hours"][tz] = []
            
            if metrics.accepted_hour not in self._patterns["preferred_hours"][tz]:
                self._patterns["preferred_hours"][tz].append(metrics.accepted_hour)
        
        # Update day success rates
        if metrics.accepted_day_of_week is not None:
            day_key = str(metrics.accepted_day_of_week)
            current_rate = float(self._patterns["success_by_day"].get(day_key, 0.5))
            # Simple exponential moving average
            new_rate = current_rate * 0.9 + 0.1 * (1.0 if metrics.booking_success else 0.0)
            self._patterns["success_by_day"][day_key] = round(new_rate, 2)
        
        # Update average exchanges
        exchanges = [m.exchanges_to_book for m in self._metrics if m.booking_success]
        if exchanges:
            self._patterns["avg_exchanges_to_book"] = round(sum(exchanges) / len(exchanges), 2)
        
        # Save patterns
        self._save_patterns()
    
    # =========================================================================
    # STATUS AND REPORTING
    # =========================================================================
    
    def get_request_status(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a scheduling request."""
        if request_id not in self._active_requests:
            return None
        
        request = self._active_requests[request_id]
        exchanges = self._exchanges.get(request_id, [])
        
        return {
            "request_id": request_id,
            "status": request.status.value,
            "prospect_email": request.prospect_email,
            "prospect_name": request.prospect_name,
            "exchange_count": request.exchange_count,
            "created_at": request.created_at,
            "updated_at": request.updated_at,
            "exchanges": [asdict(e) for e in exchanges]
        }
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of scheduling metrics for reporting."""
        total = len(self._metrics)
        successful = sum(1 for m in self._metrics if m.booking_success)
        escalated = sum(1 for m in self._metrics if m.escalated)
        
        avg_exchanges = sum(m.exchanges_to_book for m in self._metrics) / max(1, total)
        
        return {
            "total_requests": total,
            "successful_bookings": successful,
            "success_rate": round(successful / max(1, total), 2),
            "escalated": escalated,
            "escalation_rate": round(escalated / max(1, total), 2),
            "avg_exchanges_to_book": round(avg_exchanges, 2),
            "patterns": self._patterns
        }
    
    # =========================================================================
    # DAY 12: GHL INTEGRATION
    # =========================================================================
    
    async def update_ghl_after_booking(
        self,
        request: SchedulingRequest,
        booking_result: 'BookingResult'
    ) -> Dict[str, Any]:
        """
        Update GoHighLevel after successful booking.
        
        Actions:
        - Update contact with meeting details
        - Add "meeting_scheduled" tag
        - Log activity
        - Create opportunity if not exists
        - Trigger RESEARCHER agent for meeting prep
        
        Args:
            request: The scheduling request
            booking_result: Result from book_meeting
        
        Returns:
            GHL update result
        """
        if not booking_result.success:
            return {"success": False, "error": "Booking not successful"}
        
        ghl_updates = {
            "contact_updated": False,
            "tag_added": False,
            "activity_logged": False,
            "researcher_triggered": False
        }
        
        try:
            # Try to import GHL client
            sys.path.insert(0, str(PROJECT_ROOT / "mcp-servers" / "ghl-mcp"))
            from server import AsyncGHLClient
            
            ghl_client = AsyncGHLClient()
            
            # 1. Update contact with meeting details
            if request.ghl_contact_id:
                contact_updates = {
                    "customFields": {
                        "last_meeting_scheduled": booking_result.start_time,
                        "meeting_zoom_link": booking_result.zoom_link,
                        "meeting_calendar_link": booking_result.calendar_link
                    }
                }
                
                await ghl_client.update_contact(
                    contact_id=request.ghl_contact_id,
                    updates=contact_updates
                )
                ghl_updates["contact_updated"] = True
                
                # 2. Add tag
                await ghl_client.add_tag(
                    contact_id=request.ghl_contact_id,
                    tag="meeting_scheduled"
                )
                ghl_updates["tag_added"] = True
                
                logger.info(f"GHL updated for contact {request.ghl_contact_id}")
            
            await ghl_client.close()
            
        except ImportError:
            logger.warning("GHL client not available - skipping CRM update")
        except Exception as e:
            logger.error(f"GHL update failed: {e}")
        
        # 3. Trigger RESEARCHER for meeting prep
        try:
            researcher_result = await self._trigger_researcher(
                request=request,
                meeting_time=booking_result.start_time
            )
            ghl_updates["researcher_triggered"] = researcher_result.get("success", False)
        except Exception as e:
            logger.warning(f"Failed to trigger researcher: {e}")
        
        return {"success": True, "updates": ghl_updates}
    
    async def _trigger_researcher(
        self,
        request: SchedulingRequest,
        meeting_time: str
    ) -> Dict[str, Any]:
        """
        Trigger RESEARCHER agent to prepare meeting brief.
        
        Creates a research task in .hive-mind/researcher/queue/
        """
        research_task = {
            "task_id": self._generate_id("RSRCH"),
            "type": "meeting_prep",
            "priority": "high",
            "prospect_email": request.prospect_email,
            "prospect_name": request.prospect_name,
            "prospect_company": request.prospect_company,
            "prospect_timezone": request.prospect_timezone,
            "meeting_time": meeting_time,
            "meeting_type": request.meeting_type,
            "ghl_contact_id": request.ghl_contact_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending"
        }
        
        # Save to researcher queue
        queue_dir = self.hive_mind / "researcher" / "queue"
        queue_dir.mkdir(parents=True, exist_ok=True)
        
        task_file = queue_dir / f"{research_task['task_id']}.json"
        task_file.write_text(json.dumps(research_task, indent=2))
        
        logger.info(f"Research task {research_task['task_id']} created for {request.prospect_company}")
        
        return {"success": True, "task_id": research_task["task_id"]}
    
    # =========================================================================
    # DAY 12: REMINDERS
    # =========================================================================
    
    async def schedule_reminders(
        self,
        event_id: str,
        start_time: str,
        prospect_email: str,
        prospect_name: str,
        request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Schedule reminder notifications for upcoming meeting.
        
        Reminders:
        - 24 hours before
        - 1 hour before
        
        Args:
            event_id: Calendar event ID
            start_time: Meeting start time (ISO)
            prospect_email: Prospect's email
            prospect_name: Prospect's name
            request_id: Optional scheduling request ID
        
        Returns:
            Reminder scheduling result
        """
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        except Exception as e:
            return {"success": False, "error": f"Invalid start time: {e}"}
        
        now = datetime.now(timezone.utc)
        reminders_scheduled = []
        
        # Calculate reminder times
        reminder_24h = start_dt - timedelta(hours=24)
        reminder_1h = start_dt - timedelta(hours=1)
        
        # Create reminder tasks
        reminder_dir = self.scheduler_dir / "reminders"
        reminder_dir.mkdir(parents=True, exist_ok=True)
        
        for reminder_time, label in [(reminder_24h, "24h"), (reminder_1h, "1h")]:
            if reminder_time > now:
                reminder = {
                    "reminder_id": self._generate_id(f"REM-{label}"),
                    "event_id": event_id,
                    "request_id": request_id,
                    "prospect_email": prospect_email,
                    "prospect_name": prospect_name,
                    "meeting_time": start_time,
                    "reminder_time": reminder_time.isoformat(),
                    "reminder_type": label,
                    "status": "pending",
                    "created_at": now.isoformat()
                }
                
                reminder_file = reminder_dir / f"{reminder['reminder_id']}.json"
                reminder_file.write_text(json.dumps(reminder, indent=2))
                
                reminders_scheduled.append({
                    "type": label,
                    "scheduled_for": reminder_time.isoformat()
                })
                
                logger.info(f"Reminder {label} scheduled for {reminder_time.isoformat()}")
        
        return {
            "success": True,
            "reminders": reminders_scheduled,
            "count": len(reminders_scheduled)
        }
    
    async def check_pending_reminders(self) -> List[Dict[str, Any]]:
        """
        Check for reminders that need to be sent.
        
        Returns list of reminders due within the next 5 minutes.
        """
        reminder_dir = self.scheduler_dir / "reminders"
        if not reminder_dir.exists():
            return []
        
        now = datetime.now(timezone.utc)
        due_reminders = []
        
        for reminder_file in reminder_dir.glob("*.json"):
            try:
                reminder = json.loads(reminder_file.read_text())
                
                if reminder.get("status") != "pending":
                    continue
                
                reminder_time = datetime.fromisoformat(
                    reminder["reminder_time"].replace('Z', '+00:00')
                )
                
                # Check if due within 5 minutes
                if reminder_time <= now + timedelta(minutes=5) and reminder_time >= now - timedelta(minutes=5):
                    due_reminders.append(reminder)
                    
                    # Mark as sent
                    reminder["status"] = "sent"
                    reminder["sent_at"] = now.isoformat()
                    reminder_file.write_text(json.dumps(reminder, indent=2))
                    
            except Exception as e:
                logger.warning(f"Error processing reminder {reminder_file}: {e}")
        
        return due_reminders
    
    async def send_reminder_notification(
        self,
        reminder: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send a reminder notification (to be implemented with actual email/SMS).
        
        Currently logs the reminder and saves to outbox.
        """
        outbox_dir = self.hive_mind / "outbox"
        outbox_dir.mkdir(parents=True, exist_ok=True)
        
        notification = {
            "type": "meeting_reminder",
            "to": reminder["prospect_email"],
            "subject": f"Reminder: Your call is in {reminder['reminder_type']}",
            "body": f"""Hi {reminder['prospect_name']},

Just a friendly reminder that we have a call scheduled for {reminder['meeting_time']}.

Looking forward to speaking with you!

Best regards""",
            "reminder_id": reminder["reminder_id"],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        notification_file = outbox_dir / f"reminder_{reminder['reminder_id']}.json"
        notification_file.write_text(json.dumps(notification, indent=2))
        
        logger.info(f"Reminder notification saved for {reminder['prospect_email']}")
        
        return {"success": True, "notification_file": str(notification_file)}
    
    # =========================================================================
    # DAY 12: ENHANCED BOOKING WITH GHL + REMINDERS
    # =========================================================================
    
    async def book_meeting_with_integrations(
        self,
        prospect_email: str,
        start_time: str,
        duration_minutes: int = DEFAULT_MEETING_DURATION,
        title: str = "Discovery Call",
        description: str = "",
        with_zoom: bool = True,
        calendar_id: str = "primary",
        request_id: Optional[str] = None,
        prospect_name: str = "",
        ghl_contact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Book meeting with full integrations (Calendar + GHL + Reminders + Researcher).
        
        This is the recommended method for production use.
        """
        # 1. Book the meeting
        booking = await self.book_meeting(
            prospect_email=prospect_email,
            start_time=start_time,
            duration_minutes=duration_minutes,
            title=title,
            description=description,
            with_zoom=with_zoom,
            calendar_id=calendar_id,
            request_id=request_id
        )
        
        if not booking.success:
            return {"success": False, "error": booking.error, "phase": "booking"}
        
        result = {
            "success": True,
            "booking": asdict(booking),
            "integrations": {}
        }
        
        # 2. Schedule reminders
        reminders = await self.schedule_reminders(
            event_id=booking.event_id,
            start_time=booking.start_time,
            prospect_email=prospect_email,
            prospect_name=prospect_name or prospect_email.split("@")[0],
            request_id=request_id
        )
        result["integrations"]["reminders"] = reminders
        
        # 3. Update GHL if we have contact info
        if request_id and request_id in self._active_requests:
            request = self._active_requests[request_id]
            ghl_result = await self.update_ghl_after_booking(request, booking)
            result["integrations"]["ghl"] = ghl_result
        elif ghl_contact_id:
            # Create minimal request for GHL update
            temp_request = SchedulingRequest(
                request_id=request_id or "temp",
                prospect_email=prospect_email,
                prospect_name=prospect_name,
                prospect_timezone="America/New_York",
                prospect_company="",
                ghl_contact_id=ghl_contact_id
            )
            ghl_result = await self.update_ghl_after_booking(temp_request, booking)
            result["integrations"]["ghl"] = ghl_result
        
        logger.info(f"Meeting booked with integrations: {booking.event_id}")
        
        return result



# =============================================================================
# CLI INTERFACE
# =============================================================================

async def main():
    """Demo the Scheduler Agent."""
    print("\n" + "=" * 60)
    print("SCHEDULER AGENT - Beta Swarm")
    print("=" * 60)
    
    scheduler = SchedulerAgent()
    
    # Demo: Generate proposals
    print("\n[1. Generating Time Proposals]")
    proposals = await scheduler.generate_proposals(
        prospect_timezone="America/New_York",
        duration_minutes=30,
        num_proposals=5
    )
    
    print(f"Generated {len(proposals)} proposals:")
    for i, p in enumerate(proposals):
        print(f"  {i+1}. {p.display_text} (confidence: {p.confidence:.2f})")
    
    # Demo: Create scheduling request
    print("\n[2. Creating Scheduling Request]")
    request, props = await scheduler.create_scheduling_request(
        prospect_email="john@acmecorp.com",
        prospect_name="John Smith",
        prospect_timezone="PST",
        prospect_company="Acme Corp",
        meeting_type="discovery"
    )
    print(f"Created request: {request.request_id}")
    print(f"Status: {request.status.value}")
    
    # Demo: Handle acceptance
    print("\n[3. Simulating Prospect Acceptance]")
    if props:
        result = await scheduler.handle_prospect_response(
            request_id=request.request_id,
            response_type="accept",
            selected_time=props[0].start_time_utc
        )
        print(f"Result: {result.get('action')}")
        if result.get("success"):
            print(f"  Event ID: {result.get('event_id')}")
            print(f"  Zoom: {result.get('zoom_link')}")
    
    # Demo: Metrics
    print("\n[4. Metrics Summary]")
    metrics = scheduler.get_metrics_summary()
    print(f"  Success rate: {metrics['success_rate']}")
    print(f"  Avg exchanges: {metrics['avg_exchanges_to_book']}")
    
    print("\n" + "=" * 60)
    print("Demo complete!")


if __name__ == "__main__":
    asyncio.run(main())
