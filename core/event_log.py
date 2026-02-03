"""
Event logging module for SDR automation.
Writes structured events to JSONL format.
"""

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class EventType(Enum):
    """Classification of SDR automation events."""
    LEAD_SEGMENTED = "lead_segmented"
    RESEARCH_COMPLETED = "research_completed"
    CAMPAIGN_CREATED = "campaign_created"
    CAMPAIGN_QUEUED = "campaign_queued"
    CAMPAIGN_APPROVED = "campaign_approved"
    CAMPAIGN_REJECTED = "campaign_rejected"
    CAMPAIGN_SENT = "campaign_sent"
    REPLY_RECEIVED = "reply_received"
    REPLY_CLASSIFIED = "reply_classified"
    HANDOFF_CREATED = "handoff_created"
    MEETING_BOOKED = "meeting_booked"
    COMPLIANCE_FAILED = "compliance_failed"
    RETRY_SCHEDULED = "retry_scheduled"
    ENRICHMENT_COMPLETED = "enrichment_completed"
    ENRICHMENT_FAILED = "enrichment_failed"
    SCRAPE_COMPLETED = "scrape_completed"
    SCRAPE_FAILED = "scrape_failed"
    ESCALATION_TRIGGERED = "escalation_triggered"
    SLA_BREACH = "sla_breach"
    SYSTEM_ERROR = "system_error"


EVENTS_FILE = Path(".hive-mind/events.jsonl")


def log_event(
    event_type: EventType,
    payload: dict[str, Any],
    metadata: Optional[dict[str, Any]] = None
) -> str:
    """
    Log an event to the JSONL event store.
    
    Args:
        event_type: The type of event being logged
        payload: Event-specific data
        metadata: Optional additional context
        
    Returns:
        The generated event_id
    """
    event_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    
    event = {
        "timestamp": timestamp,
        "event_id": event_id,
        "event_type": event_type.value,
        "payload": payload
    }
    
    if metadata:
        event["metadata"] = metadata
    
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    
    return event_id
