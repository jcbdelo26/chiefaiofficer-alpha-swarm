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
- MESSAGE_REPLY_RECEIVED → route to RESPONDER agent
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
    """Extract lead details from webhook payload (HR-05: schema discovery).

    Field names are based on API patterns — not empirically validated.
    The debug log below captures the full payload keys on every webhook
    so the actual schema can be discovered from production logs.
    """
    # HR-05: Log ALL top-level keys for schema discovery
    logger.info("HeyReach payload keys: %s", sorted(payload.keys()))

    lead = {
        "linkedin_url": payload.get("linkedInUrl", payload.get("linkedin_url", "")),
        "first_name": payload.get("firstName", payload.get("first_name", "")),
        "last_name": payload.get("lastName", payload.get("last_name", "")),
        "company": payload.get("companyName", payload.get("company", "")),
        "email": payload.get("email", ""),
        "campaign_id": payload.get("campaignId", payload.get("campaign_id", "")),
        "lead_id": payload.get("leadId", payload.get("lead_id", "")),
    }

    # HR-05: Log which fields matched vs. which are empty
    empty_fields = [k for k, v in lead.items() if not v]
    if empty_fields:
        logger.warning("HeyReach lead extraction: empty fields %s — schema may differ", empty_fields)

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

    # Extract event type — field name TBD (needs empirical validation)
    event_type = (
        payload.get("eventType")
        or payload.get("event_type")
        or payload.get("event")
        or "UNKNOWN"
    )

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
    reply_text = payload.get("messageText", payload.get("message", ""))

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

    # TODO: Route to RESPONDER agent for classification

    return {"action": "reply_logged", "needs_classification": True}


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
    tag = payload.get("tag", payload.get("tagName", "unknown"))
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
