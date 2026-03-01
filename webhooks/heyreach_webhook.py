#!/usr/bin/env python3
"""
HeyReach Webhook Handler
=========================
FastAPI router for HeyReach webhook events.

11 event types:
- CONNECTION_REQUEST_SENT / CONNECTION_REQUEST_ACCEPTED
- MESSAGE_SENT / MESSAGE_REPLY_RECEIVED
- INMAIL_SENT / INMAIL_REPLY_RECEIVED
- FOLLOW_SENT / LIKED_POST / VIEWED_PROFILE
- CAMPAIGN_COMPLETED
- LEAD_TAG_UPDATED

Key workflow:
- CONNECTION_REQUEST_ACCEPTED → trigger warm email follow-up via Instantly
- MESSAGE_REPLY_RECEIVED → classify (positive/negative/neutral) + signal loop update
- CAMPAIGN_COMPLETED → mark lead as LinkedIn-exhausted

Mounted into dashboard at dashboard/health_app.py.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, Request, HTTPException
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("heyreach_webhook")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from core.webhook_security import (
    get_webhook_signature_status,
    require_webhook_auth,
)

router = APIRouter()

# Lazy signal manager (Monaco signal loop)
_signal_manager = None


def _get_signal_manager():
    """Lazy-initialize the LeadStatusManager for engagement tracking."""
    global _signal_manager
    if _signal_manager is None:
        from core.lead_signals import LeadStatusManager
        _signal_manager = LeadStatusManager(hive_dir=PROJECT_ROOT / ".hive-mind")
    return _signal_manager


# Event log (append-only JSONL)
EVENT_LOG = PROJECT_ROOT / ".hive-mind" / "heyreach_events.jsonl"


# =============================================================================
# HELPERS
# =============================================================================

def _log_event(event_type: str, payload: Dict[str, Any]):
    """Append event to JSONL log."""
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        entry = {
            "event_type": event_type,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        with open(EVENT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as e:
        logger.error("Failed to log HeyReach event: %s", e)


def _extract_lead_info(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract lead details from webhook payload (HR-05: validated schema).

    HeyReach payloads use nested objects:
    - lead: {profile_url, first_name, last_name, company_name, email_address, id, ...}
    - campaign: {id, name, status}
    - sender: {id, first_name, last_name, email_address, profile_url}
    - Top-level: event_type, timestamp, correlation_id, connection_message

    Validated against real payloads captured 2026-03-01.
    """
    logger.info("HeyReach payload keys: %s", sorted(payload.keys()))

    lead_data = payload.get("lead") or {}
    campaign_data = payload.get("campaign") or {}
    sender_data = payload.get("sender") or {}

    lead = {
        "linkedin_url": lead_data.get("profile_url", ""),
        "first_name": lead_data.get("first_name", ""),
        "last_name": lead_data.get("last_name", ""),
        "full_name": lead_data.get("full_name", ""),
        "company": lead_data.get("company_name", ""),
        "company_url": lead_data.get("company_url", ""),
        "email": lead_data.get("email_address", "") or lead_data.get("enriched_email", "") or "",
        "position": lead_data.get("position", ""),
        "location": lead_data.get("location", ""),
        "campaign_id": str(campaign_data.get("id", "")),
        "campaign_name": campaign_data.get("name", ""),
        "lead_id": str(lead_data.get("id", "")),
        "tags": lead_data.get("tags", []),
        "sender_name": sender_data.get("full_name", ""),
        "connection_message": payload.get("connection_message", ""),
        "correlation_id": payload.get("correlation_id", ""),
    }

    # Log unknown top-level keys for ongoing schema discovery
    known_keys = {"lead", "campaign", "sender", "event_type", "timestamp",
                  "correlation_id", "connection_message", "message_text"}
    unknown_keys = set(payload.keys()) - known_keys
    if unknown_keys:
        logger.info("HeyReach unknown payload keys: %s", sorted(unknown_keys))

    # Warn on critical empty fields
    critical = {k: v for k, v in lead.items() if k in ("linkedin_url", "email", "first_name") and not v}
    if critical:
        logger.warning("HeyReach lead extraction: empty critical fields %s", list(critical.keys()))

    return lead


def _slack_alert(title: str, message: str, level: str = "info", **kwargs):
    """Send Slack alert (best-effort)."""
    try:
        if level == "warning":
            from core.alerts import send_warning
            send_warning(title, message, source="heyreach_webhook", **kwargs)
        elif level == "critical":
            from core.alerts import send_critical
            send_critical(title, message, source="heyreach_webhook", **kwargs)
        else:
            from core.alerts import send_info
            send_info(title, message, source="heyreach_webhook", **kwargs)
    except ImportError:
        pass


# =============================================================================
# UNIFIED WEBHOOK ENDPOINT
# =============================================================================

@router.post("/webhooks/heyreach")
async def heyreach_webhook(request: Request):
    """
    Unified HeyReach webhook endpoint.

    HeyReach sends all events to a single URL. Event type is in the payload.
    """
    raw_body = await request.body()
    require_webhook_auth(
        request=request,
        raw_body=raw_body,
        provider="HeyReach",
        secret_env="HEYREACH_WEBHOOK_SECRET",
        signature_header="X-HeyReach-Signature",
        bearer_env="HEYREACH_BEARER_TOKEN",  # HeyReach has no custom header support
    )
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Extract event type — HR-05 validated: field is "event_type" (snake_case lowercase)
    # Normalize to UPPER_CASE for handler map lookup
    raw_event = payload.get("event_type", "") or payload.get("eventType", "") or ""
    event_type = raw_event.upper() if raw_event else "UNKNOWN"

    logger.info("HeyReach webhook: %s (payload size: %d bytes)", event_type, len(raw_body))
    _log_event(event_type, payload)

    lead = _extract_lead_info(payload)

    # Route to handler
    handler = EVENT_HANDLERS.get(event_type, _handle_unknown)
    result = await handler(event_type, payload, lead)

    return {
        "status": "ok",
        "event": event_type,
        "_debug": {"payload_keys": sorted(payload.keys()), "lead_extracted": lead},
        **result,
    }


# =============================================================================
# EVENT HANDLERS
# =============================================================================

async def _handle_connection_request_sent(event_type: str, payload: Dict, lead: Dict) -> Dict:
    """Track outreach progress."""
    logger.info("LinkedIn connection request sent to %s", lead.get("linkedin_url"))

    # Signal loop: update lead engagement status (HR-12: warn if no email)
    email = lead.get("email", "")
    if not email:
        logger.warning("HR-12: No email for connection_sent — signal loop skipped (linkedin: %s)",
                        lead.get("linkedin_url", "unknown"))
    try:
        _get_signal_manager().handle_linkedin_connection_sent(
            lead.get("linkedin_url", ""), email
        )
    except Exception as e:
        logger.error("Signal loop error (connection_sent): %s", e)

    return {"action": "logged"}


async def _handle_connection_accepted(event_type: str, payload: Dict, lead: Dict) -> Dict:
    """
    CONNECTION_REQUEST_ACCEPTED — key event for multi-channel cadence.

    When a LinkedIn connection is accepted:
    1. Log the event
    2. Alert Slack
    3. Flag lead for warm Instantly follow-up (Day 7 in cadence)
    """
    linkedin_url = lead.get("linkedin_url", "unknown")
    name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()

    logger.info("LinkedIn connection ACCEPTED: %s (%s)", name, linkedin_url)

    _slack_alert(
        f"LinkedIn Connection Accepted: {name}",
        f"Lead accepted connection request.\n"
        f"LinkedIn: {linkedin_url}\n"
        f"Company: {lead.get('company', 'unknown')}\n"
        f"Ready for warm email follow-up.",
        metadata=lead,
    )

    # Flag for warm follow-up — dispatcher can pick this up
    _flag_for_followup(lead, "connection_accepted")

    # Signal loop: update lead engagement status (HR-12: warn if no email)
    email = lead.get("email", "")
    if not email:
        logger.warning("HR-12: No email for connection_accepted — signal loop skipped (linkedin: %s)",
                        lead.get("linkedin_url", "unknown"))
    try:
        _get_signal_manager().handle_linkedin_connection_accepted(
            lead.get("linkedin_url", ""), email
        )
    except Exception as e:
        logger.error("Signal loop error (connection_accepted): %s", e)

    return {"action": "flagged_for_followup"}


async def _handle_message_sent(event_type: str, payload: Dict, lead: Dict) -> Dict:
    """Track LinkedIn message delivery."""
    logger.info("LinkedIn message sent to %s", lead.get("linkedin_url"))
    return {"action": "logged"}


async def _handle_reply_received(event_type: str, payload: Dict, lead: Dict) -> Dict:
    """
    MESSAGE_REPLY_RECEIVED — route to RESPONDER agent.

    Similar to Instantly reply webhook. The reply content needs to be
    classified (interested/not interested/meeting request/objection).
    """
    name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
    # HR-05: real payload uses "message_text" (snake_case); keep camelCase fallback
    reply_text = payload.get("message_text", "") or payload.get("messageText", "") or payload.get("message", "")

    logger.info("LinkedIn REPLY from %s: %s...", name, reply_text[:100] if reply_text else "(empty)")

    _slack_alert(
        f"LinkedIn Reply: {name}",
        f"Lead replied on LinkedIn.\n"
        f"Message: {reply_text[:200] if reply_text else '(empty)'}\n"
        f"LinkedIn: {lead.get('linkedin_url', 'unknown')}",
        metadata={**lead, "reply_text": reply_text},
    )

    # Signal loop: update lead engagement status (HR-12: warn if no email)
    email = lead.get("email", "")
    if not email:
        logger.warning("HR-12: No email for reply — signal loop skipped (linkedin: %s)",
                        lead.get("linkedin_url", "unknown"))
    try:
        _get_signal_manager().handle_linkedin_reply(
            lead.get("linkedin_url", ""), reply_text, email
        )
    except Exception as e:
        logger.error("Signal loop error (linkedin_reply): %s", e)

    # Classify reply sentiment (HR-06)
    sentiment = classify_reply(reply_text)
    logger.info("Reply classified as '%s' for %s", sentiment, email or lead.get("linkedin_url"))

    if sentiment == "positive":
        _slack_alert(
            f"HOT LEAD: {name} replied positively",
            f"Positive LinkedIn reply detected.\n"
            f"Reply: {reply_text[:200] if reply_text else '(empty)'}\n"
            f"Action: Flag for immediate outreach.",
            metadata={**lead, "sentiment": sentiment},
        )
    elif sentiment == "negative":
        # Update signal loop to mark as unsubscribed/not-interested
        try:
            if email:
                _get_signal_manager().update_lead_status(
                    email, "unsubscribed", "heyreach_webhook:negative_reply",
                    {"reply_text": reply_text[:200], "sentiment": "negative"},
                )
        except Exception as e:
            logger.error("Signal loop error (negative classification): %s", e)

    return {
        "action": "reply_classified",
        "sentiment": sentiment,
        "email": email,
    }


async def _handle_inmail_sent(event_type: str, payload: Dict, lead: Dict) -> Dict:
    """Track InMail delivery."""
    logger.info("LinkedIn InMail sent to %s", lead.get("linkedin_url"))
    return {"action": "logged"}


async def _handle_inmail_reply(event_type: str, payload: Dict, lead: Dict) -> Dict:
    """InMail reply — same handling as regular message reply."""
    return await _handle_reply_received(event_type, payload, lead)


async def _handle_follow_sent(event_type: str, payload: Dict, lead: Dict) -> Dict:
    """Track follow actions."""
    return {"action": "logged"}


async def _handle_liked_post(event_type: str, payload: Dict, lead: Dict) -> Dict:
    """Track post engagement."""
    return {"action": "logged"}


async def _handle_viewed_profile(event_type: str, payload: Dict, lead: Dict) -> Dict:
    """Track profile views."""
    return {"action": "logged"}


async def _handle_campaign_completed(event_type: str, payload: Dict, lead: Dict) -> Dict:
    """
    CAMPAIGN_COMPLETED — mark lead as LinkedIn-exhausted.

    All steps in the campaign sequence have been completed for this lead.
    If no response, the lead should be marked as LinkedIn-exhausted in the
    pipeline so it's not re-added to HeyReach.
    """
    campaign_id = lead.get("campaign_id", "unknown")
    logger.info("HeyReach campaign completed: %s", campaign_id)

    _slack_alert(
        "HeyReach Campaign Completed",
        f"Campaign {campaign_id} has finished all sequence steps.",
        metadata={"campaign_id": campaign_id},
    )

    # Signal loop: mark lead as linkedin_exhausted
    email = lead.get("email", "")
    if email:
        try:
            _get_signal_manager().update_lead_status(
                email, "linkedin_exhausted", "heyreach_webhook:campaign_completed",
                {"campaign_id": campaign_id},
            )
        except Exception as e:
            logger.error("Signal loop error (campaign_completed): %s", e)

    return {"action": "campaign_exhausted"}


async def _handle_lead_tag_updated(event_type: str, payload: Dict, lead: Dict) -> Dict:
    """Track lead tag changes for status sync."""
    # HR-05: tags live in lead.tags array; also check top-level tag/tag_name
    tag = payload.get("tag_name", "") or payload.get("tag", "") or payload.get("tagName", "")
    if not tag:
        # Fall back to lead's tags array
        lead_tags = lead.get("tags", [])
        tag = lead_tags[-1] if lead_tags else "unknown"
    logger.info("Lead tag updated: %s → %s", lead.get("linkedin_url"), tag)
    return {"action": "tag_logged", "tag": tag}


async def _handle_unknown(event_type: str, payload: Dict, lead: Dict) -> Dict:
    """Handle unrecognized event types (HR-21: alert on unknown)."""
    logger.warning("Unknown HeyReach event type: %s", event_type)

    _slack_alert(
        f"Unknown HeyReach Event: {event_type}",
        f"Received unrecognized event type '{event_type}'.\n"
        f"Payload keys: {sorted(payload.keys())}\n"
        f"This may indicate a new HeyReach webhook event or a schema change.",
        level="warning",
        metadata={"event_type": event_type, "payload_keys": sorted(payload.keys())},
    )

    return {"action": "unknown_event_logged"}


# =============================================================================
# REPLY CLASSIFICATION (HR-06)
# =============================================================================

# Keyword patterns for rule-based reply classification.
# These avoid the latency/cost of an LLM call in a webhook handler.

_POSITIVE_KEYWORDS = [
    "interested", "tell me more", "send me", "love to", "schedule",
    "sounds great", "let's chat", "book a call", "set up a call",
    "open to", "that works", "count me in", "send it over",
    "i'm in", "yes", "sure", "absolutely", "looking forward",
]

_NEGATIVE_KEYWORDS = [
    "not interested", "no thanks", "no thank you", "unsubscribe",
    "remove me", "stop", "don't contact", "do not contact",
    "opt out", "not the right time", "not for us", "pass",
    "take me off", "wrong person", "not relevant",
]


def classify_reply(reply_text: str) -> str:
    """Classify a LinkedIn reply as positive, negative, or neutral.

    Rule-based classification using keyword matching. Fast and deterministic.
    Returns: "positive", "negative", or "neutral".
    """
    if not reply_text:
        return "neutral"

    text_lower = reply_text.lower().strip()

    # Check negative first (unsubscribe/opt-out takes priority)
    for keyword in _NEGATIVE_KEYWORDS:
        if keyword in text_lower:
            return "negative"

    for keyword in _POSITIVE_KEYWORDS:
        if keyword in text_lower:
            return "positive"

    return "neutral"


# =============================================================================
# FOLLOW-UP FLAG
# =============================================================================

def _flag_for_followup(lead: Dict, reason: str):
    """
    Write a follow-up flag file for the dispatcher to pick up.

    When a LinkedIn connection is accepted, the multi-channel cadence
    should trigger a warm email follow-up via Instantly.
    """
    followup_dir = PROJECT_ROOT / ".hive-mind" / "heyreach_followups"
    followup_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{reason}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(followup_dir / filename, "w", encoding="utf-8") as f:
            json.dump({
                "reason": reason,
                "lead": lead,
                "flagged_at": datetime.now(timezone.utc).isoformat(),
                "processed": False,
            }, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to write follow-up flag: %s", e)


# =============================================================================
# EVENT HANDLER MAP
# =============================================================================

EVENT_HANDLERS = {
    "CONNECTION_REQUEST_SENT": _handle_connection_request_sent,
    "CONNECTION_REQUEST_ACCEPTED": _handle_connection_accepted,
    "MESSAGE_SENT": _handle_message_sent,
    "MESSAGE_REPLY_RECEIVED": _handle_reply_received,
    "INMAIL_SENT": _handle_inmail_sent,
    "INMAIL_REPLY_RECEIVED": _handle_inmail_reply,
    "FOLLOW_SENT": _handle_follow_sent,
    "LIKED_POST": _handle_liked_post,
    "VIEWED_PROFILE": _handle_viewed_profile,
    "CAMPAIGN_COMPLETED": _handle_campaign_completed,
    "LEAD_TAG_UPDATED": _handle_lead_tag_updated,
}


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/webhooks/heyreach/health")
async def heyreach_webhook_health():
    """Health check for HeyReach webhook router."""
    from core.webhook_security import is_unsigned_webhook_provider_allowlisted

    api_key_set = bool(os.getenv("HEYREACH_API_KEY", ""))
    signature_status = get_webhook_signature_status("HEYREACH_WEBHOOK_SECRET")
    unsigned_allowed = is_unsigned_webhook_provider_allowlisted("HeyReach")

    # HR-11: Warn if unsigned webhooks are allowed in production
    warnings = []
    if unsigned_allowed:
        warnings.append("HEYREACH_UNSIGNED_ALLOWLIST is TRUE — webhooks accept unsigned requests")
    if not signature_status["secret_configured"] and not signature_status["bearer_configured"]:
        if not unsigned_allowed:
            warnings.append("No webhook auth configured (secret/bearer/allowlist)")

    return {
        "status": "healthy",
        "webhook": "heyreach",
        "api_key_configured": api_key_set,
        "secret_configured": signature_status["secret_configured"],
        "bearer_configured": signature_status["bearer_configured"],
        "signature_strict_mode": signature_status["strict_mode"],
        "unsigned_allowlisted": unsigned_allowed,
        "warnings": warnings,
        "events_supported": list(EVENT_HANDLERS.keys()),
    }

