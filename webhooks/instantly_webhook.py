#!/usr/bin/env python3
"""
Instantly.ai Webhook & Campaign Management Router
==================================================
FastAPI router providing:
1. Campaign activation gate (list / activate / emergency-stop)
2. Instantly webhook callbacks (reply, bounce, open, unsubscribe)
3. Dispatch status (daily ceiling tracker)

Mounted into the main dashboard at dashboard/health_app.py.
"""

import os
import sys
import json
import hmac
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, Request, HTTPException, Query, Depends, BackgroundTasks
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("instantly_webhook")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Lazy Instantly client
_instantly_client = None

# Lazy signal manager (Monaco signal loop)
_signal_manager = None


def _get_signal_manager():
    """Lazy-initialize the LeadStatusManager for engagement tracking."""
    global _signal_manager
    if _signal_manager is None:
        from core.lead_signals import LeadStatusManager
        _signal_manager = LeadStatusManager(hive_dir=PROJECT_ROOT / ".hive-mind")
    return _signal_manager


async def _get_client():
    """Lazy-initialize the AsyncInstantlyClient."""
    global _instantly_client
    if _instantly_client is None:
        sys.path.insert(0, str(PROJECT_ROOT / "mcp-servers" / "instantly-mcp"))
        from server import AsyncInstantlyClient
        _instantly_client = AsyncInstantlyClient()
    return _instantly_client


# =============================================================================
# AUTH (re-use dashboard pattern)
# =============================================================================

def _require_auth(request: Request, token: str = Query(None, alias="token")):
    """Dashboard-compatible auth for Instantly control endpoints."""
    configured_token = (os.getenv("DASHBOARD_AUTH_TOKEN") or "").strip()
    strict_raw = (os.getenv("DASHBOARD_AUTH_STRICT") or "").strip().lower()
    strict_mode = strict_raw in {"1", "true", "yes", "on"}

    supplied_token = (
        token
        or request.headers.get("X-Dashboard-Token")
        or request.headers.get("x-dashboard-token")
    )

    if not configured_token:
        if strict_mode:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return True

    if not supplied_token or supplied_token != configured_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


# =============================================================================
# WEBHOOK SIGNATURE VERIFICATION
# =============================================================================

INSTANTLY_WEBHOOK_SECRET = os.getenv("INSTANTLY_WEBHOOK_SECRET", "")


def _verify_signature(raw_body: bytes, signature: str) -> bool:
    """Verify HMAC SHA256 signature from Instantly webhooks."""
    if not INSTANTLY_WEBHOOK_SECRET:
        return True  # No secret configured, skip verification
    if not signature:
        return False
    expected = hmac.new(
        INSTANTLY_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature.replace("sha256=", ""))


router = APIRouter()


# =============================================================================
# CAMPAIGN MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("/api/instantly/campaigns")
async def list_instantly_campaigns(auth: bool = Depends(_require_auth)):
    """List all Instantly campaigns with status and lead counts."""
    try:
        client = await _get_client()
        result = await client.list_campaigns(status="all", limit=100)

        if not result.get("success"):
            raise HTTPException(
                status_code=502,
                detail=f"Instantly API error: {result.get('error')}",
            )

        campaigns = result.get("data", [])
        if isinstance(campaigns, dict):
            campaigns = campaigns.get("campaigns", [])

        # Enrich with local dispatch metadata
        dispatch_log = PROJECT_ROOT / ".hive-mind" / "instantly_dispatch_log.jsonl"
        local_campaigns: Dict[str, Dict] = {}
        if dispatch_log.exists():
            try:
                with open(dispatch_log, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            cid = entry.get("campaign_id")
                            if cid:
                                local_campaigns[cid] = entry
                        except (json.JSONDecodeError, KeyError):
                            continue
            except IOError:
                pass

        enriched = []
        for c in campaigns:
            cid = c.get("id", "")
            local = local_campaigns.get(cid, {})
            enriched.append({
                "campaign_id": cid,
                "name": c.get("name", ""),
                "status": c.get("status", "unknown"),
                "created_at": c.get("timestamp_created", ""),
                "local_dispatch": local,
            })

        return {"campaigns": enriched, "count": len(enriched)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/instantly/campaigns/{campaign_id}/activate")
async def activate_campaign(
    campaign_id: str,
    approver: str = Query("dashboard_user"),
    auth: bool = Depends(_require_auth),
):
    """
    Human approval to resume (activate) a paused Instantly campaign.
    This is the ONLY way a campaign goes live.
    """
    # Check emergency stop
    if os.getenv("EMERGENCY_STOP", "false").lower().strip() in ("true", "1", "yes", "on"):
        raise HTTPException(
            status_code=403,
            detail="EMERGENCY_STOP is active -- cannot activate campaigns",
        )

    try:
        client = await _get_client()
        result = await client.activate_campaign(campaign_id)

        if not result.get("success"):
            raise HTTPException(
                status_code=502,
                detail=f"Instantly API error: {result.get('error')}",
            )

        # Audit log
        audit_dir = PROJECT_ROOT / ".hive-mind" / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_log = audit_dir / "instantly_activations.jsonl"
        with open(audit_log, "a", encoding="utf-8") as f:
            f.write(
                json.dumps({
                    "action": "campaign_activated",
                    "campaign_id": campaign_id,
                    "approver": approver,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                + "\n"
            )

        # Slack alert
        try:
            from core.alerts import send_info
            send_info(
                f"Instantly Campaign Activated: {campaign_id}",
                f"Approved by {approver}. Campaign is now LIVE.",
                metadata={"campaign_id": campaign_id, "approver": approver},
                source="instantly_dashboard",
            )
        except ImportError:
            pass

        return {
            "status": "activated",
            "campaign_id": campaign_id,
            "activated_by": approver,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/instantly/emergency-stop")
async def instantly_emergency_stop(
    approver: str = Query("dashboard_user"),
    auth: bool = Depends(_require_auth),
):
    """Emergency: bulk-pause ALL active Instantly campaigns + Slack CRITICAL."""
    try:
        client = await _get_client()
        result = await client.bulk_pause_all()

        # Audit log
        audit_dir = PROJECT_ROOT / ".hive-mind" / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_log = audit_dir / "instantly_activations.jsonl"
        with open(audit_log, "a", encoding="utf-8") as f:
            f.write(
                json.dumps({
                    "action": "emergency_bulk_pause",
                    "approver": approver,
                    "paused_count": result.get("paused_count", 0),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                + "\n"
            )

        # Slack CRITICAL alert
        try:
            from core.alerts import send_critical
            send_critical(
                "INSTANTLY EMERGENCY STOP",
                f"{result.get('paused_count', 0)} campaigns paused by {approver}",
                metadata=result,
                source="instantly_dashboard",
            )
        except ImportError:
            pass

        return {
            "status": "emergency_stopped",
            "paused_count": result.get("paused_count", 0),
            "errors": result.get("errors", []),
            "triggered_by": approver,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/instantly/dispatch-status")
async def get_dispatch_status(auth: bool = Depends(_require_auth)):
    """Get today's dispatch status (ceiling tracker state)."""
    state_file = PROJECT_ROOT / ".hive-mind" / "instantly_dispatch_state.json"
    state: Dict[str, Any] = {"date": "N/A", "dispatched_count": 0}
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # Daily limit from config
    config_path = PROJECT_ROOT / "config" / "production.json"
    daily_limit = 25
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                daily_limit = (
                    config.get("guardrails", {})
                    .get("email_limits", {})
                    .get("daily_limit", 25)
                )
        except (json.JSONDecodeError, IOError):
            pass

    dispatched = state.get("dispatched_count", 0)
    return {
        "date": state.get("date"),
        "dispatched_today": dispatched,
        "daily_limit": daily_limit,
        "remaining": max(0, daily_limit - dispatched),
        "campaigns_created_today": state.get("campaigns_created", []),
    }


# =============================================================================
# GHL TAG UPDATE HELPER
# =============================================================================

async def _update_ghl_tags(lead_email: str, tags: list):
    """Look up GHL contact by email and add tags."""
    api_key = os.getenv("GHL_API_KEY") or os.getenv("GHL_PROD_API_KEY")
    location_id = os.getenv("GHL_LOCATION_ID")
    if not api_key or not location_id:
        logger.warning("GHL credentials not configured -- skipping tag update")
        return

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Version": "2021-07-28",
                "Content-Type": "application/json",
            }
            # Look up contact
            lookup_url = "https://services.leadconnectorhq.com/contacts/lookup"
            async with session.get(
                lookup_url,
                headers=headers,
                params={"email": lead_email, "locationId": location_id},
            ) as resp:
                if resp.status != 200:
                    logger.warning("GHL contact lookup failed: %s", resp.status)
                    return
                data = await resp.json()
                contacts = data.get("contacts", [])
                if not contacts:
                    logger.warning("No GHL contact found for %s", lead_email)
                    return
                contact_id = contacts[0].get("id")

            # Add tags
            tag_url = f"https://services.leadconnectorhq.com/contacts/{contact_id}/tags"
            async with session.post(
                tag_url, headers=headers, json={"tags": tags}
            ) as resp:
                if resp.status in (200, 201):
                    logger.info("GHL tags %s added for %s", tags, lead_email)
                else:
                    logger.warning("GHL tag add failed: %s", resp.status)
    except Exception as e:
        logger.error("GHL tag update error for %s: %s", lead_email, e)


# =============================================================================
# SUPPRESSION LIST HELPER
# =============================================================================

def _add_to_suppression(email: str):
    """Add email to local suppression list (append-only JSONL — no race condition)."""
    suppression_file = PROJECT_ROOT / ".hive-mind" / "unsubscribes.jsonl"
    suppression_file.parent.mkdir(parents=True, exist_ok=True)
    with open(suppression_file, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "email": email,
            "at": datetime.now(timezone.utc).isoformat(),
        }) + "\n")
    logger.info("Added %s to suppression list", email)


def _is_suppressed(email: str) -> bool:
    """Check if email is in the suppression list."""
    suppression_file = PROJECT_ROOT / ".hive-mind" / "unsubscribes.jsonl"
    if not suppression_file.exists():
        return False
    with open(suppression_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                if json.loads(line.strip()).get("email") == email:
                    return True
            except (json.JSONDecodeError, KeyError):
                continue
    return False


# =============================================================================
# EVENT LOGGING HELPER
# =============================================================================

def _log_event(event_type: str, payload: Dict[str, Any]):
    """Write event to .hive-mind/instantly_events/."""
    events_dir = PROJECT_ROOT / ".hive-mind" / "instantly_events"
    events_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    lead = payload.get("data", {}).get("lead_email", "unknown")
    safe_lead = lead.replace("@", "_at_")[:30]
    filepath = events_dir / f"{event_type}_{ts}_{safe_lead}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


# =============================================================================
# WEBHOOK BACKGROUND TASKS
# =============================================================================

async def _process_reply(payload: Dict[str, Any]):
    """Background: process reply webhook."""
    lead_email = payload.get("data", {}).get("lead_email", "")
    campaign_id = payload.get("data", {}).get("campaign_id", "")
    reply_text = payload.get("data", {}).get("reply_text", "")

    # GHL tag
    await _update_ghl_tags(lead_email, ["status-replied"])

    # Slack notify
    try:
        from core.alerts import send_info
        send_info(
            f"Instantly Reply: {lead_email}",
            f"Campaign: {campaign_id}\nReply: {reply_text[:200]}",
            metadata={"lead_email": lead_email, "campaign_id": campaign_id},
            source="instantly_webhook",
        )
    except ImportError:
        pass

    # Log event
    _log_event("reply", payload)

    # Signal loop: update lead engagement status
    try:
        _get_signal_manager().handle_email_replied(lead_email, reply_text, campaign_id)
    except Exception as e:
        logger.error("Signal loop error (reply): %s", e)


async def _process_bounce(payload: Dict[str, Any]):
    """Background: process bounce webhook."""
    lead_email = payload.get("data", {}).get("lead_email", "")
    bounce_type = payload.get("data", {}).get("bounce_type", "unknown")

    # GHL tag
    await _update_ghl_tags(lead_email, ["status-bounced"])

    # Suppression
    _add_to_suppression(lead_email)

    # Slack warn
    try:
        from core.alerts import send_warning
        send_warning(
            f"Instantly Bounce: {lead_email}",
            f"Bounce type: {bounce_type}",
            source="instantly_webhook",
        )
    except ImportError:
        pass

    # Log event
    _log_event("bounce", payload)

    # Signal loop: update lead engagement status
    try:
        _get_signal_manager().handle_email_bounced(lead_email, bounce_type)
    except Exception as e:
        logger.error("Signal loop error (bounce): %s", e)


async def _process_unsubscribe(payload: Dict[str, Any]):
    """Background: process unsubscribe webhook (compliance-critical)."""
    lead_email = payload.get("data", {}).get("lead_email", "")

    # GHL tags (DNC = do not contact)
    await _update_ghl_tags(lead_email, ["status-unsubscribed", "DNC"])

    # Suppression
    _add_to_suppression(lead_email)

    # Slack warn (compliance event)
    try:
        from core.alerts import send_warning
        send_warning(
            f"Unsubscribe: {lead_email}",
            "Added to suppression list and GHL DNC tag. Compliance action taken.",
            source="instantly_webhook",
        )
    except ImportError:
        pass

    # Log event
    _log_event("unsubscribe", payload)

    # Signal loop: update lead engagement status
    try:
        _get_signal_manager().handle_email_unsubscribed(lead_email)
    except Exception as e:
        logger.error("Signal loop error (unsubscribe): %s", e)


# =============================================================================
# INSTANTLY WEBHOOK HANDLERS
# =============================================================================

@router.post("/webhooks/instantly/reply")
async def handle_instantly_reply(request: Request, background_tasks: BackgroundTasks):
    """Handle reply webhook from Instantly."""
    raw = await request.body()
    sig = request.headers.get("X-Instantly-Signature", "")

    if INSTANTLY_WEBHOOK_SECRET and not _verify_signature(raw, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    background_tasks.add_task(_process_reply, payload)
    return {"status": "received", "event": "reply"}


@router.post("/webhooks/instantly/bounce")
async def handle_instantly_bounce(request: Request, background_tasks: BackgroundTasks):
    """Handle bounce webhook from Instantly."""
    raw = await request.body()
    sig = request.headers.get("X-Instantly-Signature", "")

    if INSTANTLY_WEBHOOK_SECRET and not _verify_signature(raw, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    background_tasks.add_task(_process_bounce, payload)
    return {"status": "received", "event": "bounce"}


@router.post("/webhooks/instantly/open")
async def handle_instantly_open(request: Request):
    """Handle open tracking webhook from Instantly."""
    raw = await request.body()
    sig = request.headers.get("X-Instantly-Signature", "")

    if INSTANTLY_WEBHOOK_SECRET and not _verify_signature(raw, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    _log_event("open", payload)

    # Signal loop: update lead engagement status
    lead_email = payload.get("data", {}).get("lead_email", "")
    campaign_id = payload.get("data", {}).get("campaign_id", "")
    if lead_email:
        try:
            _get_signal_manager().handle_email_opened(lead_email, campaign_id)
        except Exception as e:
            logger.error("Signal loop error (open): %s", e)

    return {"status": "received", "event": "open"}


@router.post("/webhooks/instantly/unsubscribe")
async def handle_instantly_unsubscribe(
    request: Request, background_tasks: BackgroundTasks
):
    """Handle unsubscribe webhook from Instantly (compliance-critical)."""
    raw = await request.body()
    sig = request.headers.get("X-Instantly-Signature", "")

    if INSTANTLY_WEBHOOK_SECRET and not _verify_signature(raw, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    background_tasks.add_task(_process_unsubscribe, payload)
    return {"status": "received", "event": "unsubscribe"}


@router.get("/webhooks/instantly/health")
async def instantly_webhook_health():
    """Health check for Instantly webhook router."""
    return {
        "status": "healthy",
        "webhook": "instantly",
        "secret_configured": bool(INSTANTLY_WEBHOOK_SECRET),
        "client_available": _instantly_client is not None,
    }
