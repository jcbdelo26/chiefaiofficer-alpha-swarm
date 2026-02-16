#!/usr/bin/env python3
"""
Instantly MCP Server (API V2)
==============================

Complete MCP server for Instantly.ai email outreach with:
- Async HTTP operations (API V2 — Bearer token auth)
- Idempotency for campaign creation
- Full campaign lifecycle management
- Lead status tracking
- Reply handling integration
- A/B test variant support
- Programmatic webhook CRUD

API V2 Reference: https://developer.instantly.ai/api/v2
Migrated from V1 (deprecated Jan 19, 2026) on 2026-02-14.

Tools:
- instantly_create_campaign: Create new campaign (idempotent, starts DRAFTED)
- instantly_add_leads: Add leads to campaign (bulk)
- instantly_get_analytics: Get campaign metrics
- instantly_pause_campaign: Pause/resume campaign
- instantly_activate_campaign: Activate a drafted/paused campaign
- instantly_list_campaigns: List all campaigns
- instantly_get_lead_status: Check lead email status
- instantly_delete_campaign: Delete a campaign
- instantly_export_replies: Export campaign replies
- instantly_update_campaign: Update campaign settings
- instantly_setup_webhooks: Register webhook subscriptions
"""

import os
import sys
import json
import hashlib
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import logging

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("instantly-mcp")


# ============================================================================
# Idempotency Manager (shared with GHL)
# ============================================================================

class IdempotencyManager:
    """Manages idempotency keys for Instantly operations."""

    def __init__(self):
        self.storage_dir = Path(__file__).parent.parent.parent / ".hive-mind" / "idempotency"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.cache: Dict[str, Dict] = {}

    def generate_key(self, operation: str, data: Dict) -> str:
        key_data = f"instantly:{operation}:{json.dumps(data, sort_keys=True)}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    def check(self, key: str) -> Optional[Dict]:
        file_path = self.storage_dir / f"{key}.json"
        if file_path.exists():
            try:
                with open(file_path) as f:
                    data = json.load(f)
                if datetime.fromisoformat(data["expires_at"]) > datetime.utcnow():
                    return data["response"]
            except:
                pass
        return None

    def store(self, key: str, response: Dict):
        data = {
            "key": key,
            "response": response,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat()
        }
        file_path = self.storage_dir / f"{key}.json"
        with open(file_path, "w") as f:
            json.dump(data, f)


# ============================================================================
# V2 Status Enum
# ============================================================================

class CampaignStatus:
    """Instantly V2 campaign status codes."""
    DRAFTED = 0
    ACTIVE = 1
    PAUSED = 2
    COMPLETED = 3

    _FROM_STRING = {
        "all": None,
        "drafted": 0,
        "active": 1,
        "paused": 2,
        "completed": 3,
    }

    @classmethod
    def from_string(cls, status: str) -> Optional[int]:
        return cls._FROM_STRING.get(status.lower())


# ============================================================================
# Async Instantly Client (API V2)
# ============================================================================

class AsyncInstantlyClient:
    """
    Production-ready Instantly.ai API V2 client.

    V2 changes from V1:
    - Auth: Bearer token header (NOT query param)
    - Base URL: /api/v2/ (NOT /api/v1/)
    - V2 keys required (V1 keys do NOT work)
    - Campaigns start as DRAFTED (status=0) — cannot send until activated
    - Separate /pause and /activate endpoints (no combined status toggle)
    - Cursor-based pagination (starting_after, NOT skip)
    - Leads bulk endpoint: POST /leads/bulk
    - Lead list is POST (not GET)
    - Sequences are inline on campaign create/update
    """

    def __init__(self):
        self.api_key = os.getenv("INSTANTLY_API_KEY")
        self.base_url = "https://api.instantly.ai/api/v2"

        if not self.api_key:
            raise ValueError("INSTANTLY_API_KEY not set")

        self.idempotency = IdempotencyManager()
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        idempotency_key: Optional[str] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """Make async API V2 request with Bearer auth."""

        # Check idempotency
        if idempotency_key:
            cached = self.idempotency.check(idempotency_key)
            if cached:
                logger.info(f"Idempotency hit: {idempotency_key[:8]}...")
                return cached

        session = await self._get_session()
        url = f"{self.base_url}/{endpoint}"

        for attempt in range(max_retries):
            try:
                if method == "GET":
                    async with session.get(url, params=params) as response:
                        result = await self._handle_response(response)
                elif method == "POST":
                    async with session.post(url, params=params, json=data) as response:
                        result = await self._handle_response(response)
                elif method == "PATCH":
                    async with session.patch(url, params=params, json=data) as response:
                        result = await self._handle_response(response)
                elif method == "DELETE":
                    async with session.delete(url, params=params, json=data) as response:
                        result = await self._handle_response(response)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                # Store idempotent result
                if idempotency_key and result.get("success"):
                    self.idempotency.store(idempotency_key, result)

                return result

            except aiohttp.ClientError as e:
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return {"success": False, "error": str(e)}

        return {"success": False, "error": "Max retries exceeded"}

    async def _handle_response(self, response: aiohttp.ClientResponse) -> Dict[str, Any]:
        if response.status in [200, 201]:
            try:
                data = await response.json()
                return {"success": True, "data": data}
            except:
                return {"success": True, "data": await response.text()}
        elif response.status == 429:
            raise aiohttp.ClientError("Rate limited")
        else:
            return {"success": False, "error": await response.text(), "status": response.status}

    # ========================================================================
    # Campaign Operations
    # ========================================================================

    async def create_campaign(
        self,
        name: str,
        from_email: str,
        subject: str,
        body: str,
        schedule: Optional[Dict] = None,
        idempotency_key: Optional[str] = None,
        email_list: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new campaign (idempotent).

        V2 SAFETY: Campaigns start as DRAFTED (status=0) and CANNOT send
        until explicitly activated via activate_campaign(). This is the
        natural paused-by-default behavior — no hack needed.

        Args:
            name: Campaign name
            from_email: Primary sending email (added to email_list if not already present)
            subject: First email subject line
            body: First email body (HTML supported)
            schedule: Optional schedule config {timezone, days, startHour, endHour}
            idempotency_key: Optional idempotency key
            email_list: Optional list of sending account emails for rotation
        """
        if not idempotency_key:
            idempotency_key = self.idempotency.generate_key("create_campaign", {
                "name": name,
                "from_email": from_email
            })

        # Build V2 schedule
        # NOTE: Instantly V2 has a quirky timezone whitelist — "America/New_York" is NOT accepted.
        # "America/Detroit" is the same Eastern Time zone and IS accepted.
        tz = "America/Detroit"
        days_list = ["monday", "tuesday", "wednesday", "thursday", "friday"]
        start_hour = 9
        end_hour = 17

        if schedule:
            tz = schedule.get("timezone", tz)
            days_list = schedule.get("days", days_list)
            start_hour = schedule.get("startHour", start_hour)
            end_hour = schedule.get("endHour", end_hour)

        days_map = {}
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            days_map[day] = day in days_list

        # Build sending accounts list
        accounts = list(email_list) if email_list else []
        if from_email and from_email not in accounts:
            accounts.insert(0, from_email)

        data = {
            "name": name,
            "campaign_schedule": {
                "schedules": [{
                    "name": "Default",
                    "timezone": tz,
                    "days": days_map,
                    "timing": {
                        "from": f"{start_hour:02d}:00",
                        "to": f"{end_hour:02d}:00",
                    }
                }]
            },
            "sequences": [{
                "steps": [{
                    "type": "email",
                    "delay": 0,
                    "variants": [{
                        "subject": subject,
                        "body": body,
                    }]
                }]
            }],
            "stop_on_reply": True,
            "daily_limit": 50,
            "email_gap": 90,
        }

        # V2: email_list assigns sending accounts to the campaign for rotation
        if accounts:
            data["email_list"] = accounts

        result = await self._request("POST", "campaigns", data, idempotency_key=idempotency_key)

        # V2: campaigns start as DRAFTED (status=0) — no safety fallback needed
        # They literally cannot send until activate_campaign() is called
        if result.get("success"):
            campaign_id = result.get("data", {}).get("id", "unknown")
            logger.info(
                "Campaign %s created as DRAFTED with %d sending accounts (V2 default safe state)",
                campaign_id, len(accounts),
            )

        return result

    async def update_campaign(
        self,
        campaign_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update campaign settings. V2: campaign_id is in URL path."""
        return await self._request("PATCH", f"campaigns/{campaign_id}", updates)

    async def delete_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Delete a campaign."""
        return await self._request("DELETE", f"campaigns/{campaign_id}")

    async def list_campaigns(
        self,
        status: str = "all",
        limit: int = 50,
        starting_after: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List campaigns with cursor-based pagination.

        V2 changes:
        - status is integer (0=DRAFTED, 1=ACTIVE, 2=PAUSED, 3=COMPLETED)
        - pagination uses starting_after cursor (not skip/offset)
        """
        params: Dict[str, Any] = {"limit": limit}

        status_int = CampaignStatus.from_string(status)
        if status_int is not None:
            params["status"] = status_int

        if starting_after:
            params["starting_after"] = starting_after

        return await self._request("GET", "campaigns", params=params)

    async def pause_campaign(self, campaign_id: str, action: str = "pause") -> Dict[str, Any]:
        """
        Pause or activate a campaign.

        V2: Separate endpoints — POST /campaigns/{id}/pause and /campaigns/{id}/activate.
        Maintains backward-compatible signature from V1 (action="pause" or "resume").
        """
        if action == "resume":
            return await self._request("POST", f"campaigns/{campaign_id}/activate")
        return await self._request("POST", f"campaigns/{campaign_id}/pause")

    async def activate_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Activate a drafted or paused campaign. This is the ONLY way campaigns go live."""
        return await self._request("POST", f"campaigns/{campaign_id}/activate")

    async def bulk_pause_all(self) -> Dict[str, Any]:
        """
        Emergency: pause ALL active campaigns in the workspace.

        Uses cursor-based pagination to handle any number of campaigns.
        """
        paused = []
        errors = []
        starting_after = None

        while True:
            result = await self.list_campaigns(
                status="active", limit=100, starting_after=starting_after
            )
            if not result.get("success"):
                errors.append({"error": "Failed to list campaigns", "detail": str(result.get("error"))})
                break

            campaigns = result.get("data", [])
            if isinstance(campaigns, dict):
                campaigns = campaigns.get("campaigns", [])

            if not campaigns:
                break

            for campaign in campaigns:
                cid = campaign.get("id")
                if not cid:
                    continue
                pause_result = await self.pause_campaign(cid)
                if pause_result.get("success"):
                    paused.append(cid)
                else:
                    errors.append({"campaign_id": cid, "error": pause_result.get("error")})

            # Cursor pagination: use last campaign's ID
            last_id = campaigns[-1].get("id")
            if not last_id or last_id == starting_after:
                break  # No progress, stop
            starting_after = last_id

        return {
            "success": len(errors) == 0,
            "paused_count": len(paused),
            "error_count": len(errors),
            "paused_campaigns": paused,
            "errors": errors
        }

    # ========================================================================
    # Sequence Operations
    # ========================================================================

    async def create_sequence(
        self,
        campaign_id: str,
        steps: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create/update multi-step email sequence.

        V2: Sequences are inline on campaign update — no separate endpoint.
        This method routes through update_campaign() with the sequences field.
        """
        v2_steps = []
        for step in steps:
            variants = [{
                "subject": step.get("subject", ""),
                "body": step.get("body", ""),
            }]
            # A/B variant support
            if "subject_b" in step or "body_b" in step:
                variants.append({
                    "subject": step.get("subject_b", step.get("subject", "")),
                    "body": step.get("body_b", step.get("body", "")),
                })

            v2_steps.append({
                "type": "email",
                "delay": step.get("delay_days", 0),
                "variants": variants,
            })

        return await self.update_campaign(campaign_id, {
            "sequences": [{"steps": v2_steps}]
        })

    # ========================================================================
    # Lead Operations
    # ========================================================================

    async def add_leads(
        self,
        campaign_id: str,
        leads: List[Dict[str, Any]],
        skip_duplicates: bool = True
    ) -> Dict[str, Any]:
        """
        Add leads to a campaign (bulk).

        V2 changes:
        - Endpoint: POST /leads/bulk (not /lead/add)
        - campaign_id is top-level "campaign" field
        - skip_if_in_workspace/skip_if_in_campaign replace skip_duplicates
        - custom_variables values must be scalar (string/number/boolean/null)
        """
        formatted_leads = []
        for lead in leads:
            formatted = {
                "email": lead["email"],
                "first_name": lead.get("first_name", lead.get("firstName", "")),
                "last_name": lead.get("last_name", lead.get("lastName", "")),
                "company_name": lead.get("company_name", lead.get("company", lead.get("companyName", "")))
            }

            # Custom variables (V2: values must be scalar)
            custom = lead.get("custom_variables", lead.get("customFields", {}))
            if custom:
                # Ensure all values are scalar
                sanitized = {}
                for k, v in custom.items():
                    if isinstance(v, (str, int, float, bool)) or v is None:
                        sanitized[k] = v
                    else:
                        sanitized[k] = str(v)
                formatted["custom_variables"] = sanitized

            formatted_leads.append(formatted)

        data = {
            "campaign": campaign_id,
            "leads": formatted_leads,
            "skip_if_in_workspace": skip_duplicates,
            "skip_if_in_campaign": True,
        }

        return await self._request("POST", "leads/bulk", data)

    async def get_lead_status(
        self,
        email: str,
        campaign_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get status of a lead. V2: POST /leads/list (not GET).
        """
        data: Dict[str, Any] = {"search": email, "limit": 1}
        if campaign_id:
            data["campaign_id"] = campaign_id
        return await self._request("POST", "leads/list", data)

    async def remove_lead(
        self,
        campaign_id: str,
        email: str
    ) -> Dict[str, Any]:
        """Remove a lead from a campaign. V2: DELETE /leads."""
        data = {"campaign_id": campaign_id, "email": email, "limit": 1}
        return await self._request("DELETE", "leads", data)

    # ========================================================================
    # Analytics Operations
    # ========================================================================

    async def get_analytics(
        self,
        campaign_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get campaign analytics summary. V2: GET /campaigns/analytics."""
        params: Dict[str, Any] = {}
        if campaign_id:
            params["id"] = campaign_id
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        return await self._request("GET", "campaigns/analytics", params=params)

    async def export_replies(
        self,
        campaign_id: str,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Export replies from a campaign.
        V2: No direct equivalent — uses leads/list with interest filter.
        """
        data = {
            "campaign_id": campaign_id,
            "interest_status": "interested",
            "limit": limit,
        }
        return await self._request("POST", "leads/list", data)

    async def get_detailed_analytics(
        self,
        campaign_id: str
    ) -> Dict[str, Any]:
        """Get detailed analytics including per-step breakdown. V2: same as summary."""
        params = {"id": campaign_id}
        return await self._request("GET", "campaigns/analytics", params=params)

    # ========================================================================
    # Webhook Operations (V2 — programmatic CRUD)
    # ========================================================================

    async def setup_webhooks(self, base_url: str) -> Dict[str, Any]:
        """
        Register all webhook subscriptions programmatically.

        V2 provides a full webhook CRUD API — no manual Instantly dashboard config needed.

        Args:
            base_url: The public URL of the dashboard (e.g., https://caio-swarm-dashboard-production.up.railway.app)
        """
        event_map = {
            "reply_received": "reply",
            "email_bounced": "bounce",
            "email_opened": "open",
            "lead_unsubscribed": "unsubscribe",
        }

        results = []
        for event_type, path_suffix in event_map.items():
            r = await self._request("POST", "webhooks", {
                "event_type": event_type,
                "target_hook_url": f"{base_url}/webhooks/instantly/{path_suffix}",
            })
            results.append({"event": event_type, "result": r})
            logger.info("Webhook %s → %s: %s", event_type, path_suffix,
                         "OK" if r.get("success") else r.get("error", "unknown"))

        return {
            "success": all(r["result"].get("success") for r in results),
            "webhooks": results,
        }

    async def list_webhooks(self) -> Dict[str, Any]:
        """List all registered webhooks."""
        return await self._request("GET", "webhooks")

    async def delete_webhook(self, webhook_id: str) -> Dict[str, Any]:
        """Delete a webhook subscription."""
        return await self._request("DELETE", f"webhooks/{webhook_id}")

    async def test_webhook(self, webhook_id: str) -> Dict[str, Any]:
        """Send a test payload to a webhook."""
        return await self._request("POST", f"webhooks/{webhook_id}/test")


# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS = [
    {
        "name": "instantly_create_campaign",
        "description": "Create a new email campaign in Instantly (V2). Idempotent. Starts as DRAFTED — must be activated separately.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Campaign name"},
                "from_email": {"type": "string", "description": "Primary sending email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body (HTML supported)"},
                "email_list": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of sending account emails for multi-account rotation"
                },
                "schedule": {
                    "type": "object",
                    "properties": {
                        "timezone": {"type": "string", "default": "America/Detroit"},
                        "days": {"type": "array", "items": {"type": "string"}},
                        "startHour": {"type": "integer", "default": 9},
                        "endHour": {"type": "integer", "default": 17}
                    }
                },
                "idempotencyKey": {"type": "string", "description": "Optional idempotency key"}
            },
            "required": ["name", "from_email", "subject", "body"]
        }
    },
    {
        "name": "instantly_update_campaign",
        "description": "Update campaign settings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "updates": {
                    "type": "object",
                    "description": "Fields to update (name, schedule, sequences, daily_limit, etc.)"
                }
            },
            "required": ["campaign_id", "updates"]
        }
    },
    {
        "name": "instantly_add_leads",
        "description": "Add leads to an existing campaign (bulk) with automatic deduplication.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Campaign ID (UUID)"},
                "leads": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string"},
                            "first_name": {"type": "string"},
                            "last_name": {"type": "string"},
                            "company_name": {"type": "string"},
                            "custom_variables": {"type": "object"}
                        },
                        "required": ["email"]
                    }
                },
                "skip_duplicates": {"type": "boolean", "default": True}
            },
            "required": ["campaign_id", "leads"]
        }
    },
    {
        "name": "instantly_get_analytics",
        "description": "Get analytics summary for campaigns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Campaign ID (optional, all if not provided)"},
                "start_date": {"type": "string", "format": "date"},
                "end_date": {"type": "string", "format": "date"}
            }
        }
    },
    {
        "name": "instantly_get_detailed_analytics",
        "description": "Get detailed per-step analytics including A/B test results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Campaign ID"}
            },
            "required": ["campaign_id"]
        }
    },
    {
        "name": "instantly_pause_campaign",
        "description": "Pause or resume a campaign.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "action": {"type": "string", "enum": ["pause", "resume"]}
            },
            "required": ["campaign_id", "action"]
        }
    },
    {
        "name": "instantly_activate_campaign",
        "description": "Activate a drafted or paused campaign. This is the ONLY way campaigns start sending.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"}
            },
            "required": ["campaign_id"]
        }
    },
    {
        "name": "instantly_delete_campaign",
        "description": "Delete a campaign permanently.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"}
            },
            "required": ["campaign_id"]
        }
    },
    {
        "name": "instantly_list_campaigns",
        "description": "List all campaigns with their status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "paused", "completed", "drafted", "all"], "default": "all"},
                "limit": {"type": "integer", "default": 50},
                "starting_after": {"type": "string", "description": "Cursor for pagination (campaign UUID)"}
            }
        }
    },
    {
        "name": "instantly_create_sequence",
        "description": "Create a multi-step email sequence with optional A/B variants. V2: updates campaign inline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "delay_days": {"type": "integer"},
                            "subject": {"type": "string"},
                            "body": {"type": "string"},
                            "subject_b": {"type": "string", "description": "A/B test variant subject"},
                            "body_b": {"type": "string", "description": "A/B test variant body"}
                        },
                        "required": ["delay_days", "subject", "body"]
                    }
                }
            },
            "required": ["campaign_id", "steps"]
        }
    },
    {
        "name": "instantly_get_lead_status",
        "description": "Check the status of a lead's email (sent, opened, replied, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Lead email address"},
                "campaign_id": {"type": "string", "description": "Optional campaign ID to filter"}
            },
            "required": ["email"]
        }
    },
    {
        "name": "instantly_export_replies",
        "description": "Export interested leads from a campaign.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "limit": {"type": "integer", "default": 100}
            },
            "required": ["campaign_id"]
        }
    },
    {
        "name": "instantly_setup_webhooks",
        "description": "Register webhook subscriptions for reply, bounce, open, and unsubscribe events.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "base_url": {"type": "string", "description": "Public dashboard URL (e.g., https://caio-swarm-dashboard-production.up.railway.app)"}
            },
            "required": ["base_url"]
        }
    }
]


# ============================================================================
# MCP Server
# ============================================================================

async def main():
    if not MCP_AVAILABLE:
        print("MCP package not available")
        return

    if not AIOHTTP_AVAILABLE:
        print("aiohttp required: pip install aiohttp")
        return

    server = Server("instantly-mcp")

    try:
        instantly = AsyncInstantlyClient()
    except ValueError as e:
        print(f"Warning: {e}")
        instantly = None

    @server.list_tools()
    async def list_tools():
        return [Tool(**tool) for tool in TOOLS]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if not instantly:
            return [TextContent(type="text", text=json.dumps({"error": "Instantly not configured"}))]

        try:
            if name == "instantly_create_campaign":
                idem_key = arguments.pop("idempotencyKey", None)
                result = await instantly.create_campaign(
                    arguments["name"],
                    arguments["from_email"],
                    arguments["subject"],
                    arguments["body"],
                    arguments.get("schedule"),
                    idempotency_key=idem_key,
                    email_list=arguments.get("email_list"),
                )

            elif name == "instantly_update_campaign":
                result = await instantly.update_campaign(
                    arguments["campaign_id"],
                    arguments["updates"]
                )

            elif name == "instantly_add_leads":
                result = await instantly.add_leads(
                    arguments["campaign_id"],
                    arguments["leads"],
                    arguments.get("skip_duplicates", True)
                )

            elif name == "instantly_get_analytics":
                result = await instantly.get_analytics(
                    arguments.get("campaign_id"),
                    arguments.get("start_date"),
                    arguments.get("end_date")
                )

            elif name == "instantly_get_detailed_analytics":
                result = await instantly.get_detailed_analytics(arguments["campaign_id"])

            elif name == "instantly_pause_campaign":
                result = await instantly.pause_campaign(
                    arguments["campaign_id"],
                    arguments["action"]
                )

            elif name == "instantly_activate_campaign":
                result = await instantly.activate_campaign(arguments["campaign_id"])

            elif name == "instantly_delete_campaign":
                result = await instantly.delete_campaign(arguments["campaign_id"])

            elif name == "instantly_list_campaigns":
                result = await instantly.list_campaigns(
                    arguments.get("status", "all"),
                    arguments.get("limit", 50),
                    arguments.get("starting_after")
                )

            elif name == "instantly_create_sequence":
                result = await instantly.create_sequence(
                    arguments["campaign_id"],
                    arguments["steps"]
                )

            elif name == "instantly_get_lead_status":
                result = await instantly.get_lead_status(
                    arguments["email"],
                    arguments.get("campaign_id")
                )

            elif name == "instantly_export_replies":
                result = await instantly.export_replies(
                    arguments["campaign_id"],
                    arguments.get("limit", 100)
                )

            elif name == "instantly_setup_webhooks":
                result = await instantly.setup_webhooks(arguments["base_url"])

            else:
                result = {"error": f"Unknown tool: {name}"}

        except Exception as e:
            logger.exception(f"Tool error: {name}")
            result = {"error": str(e)}

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    try:
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1])
    finally:
        if instantly:
            await instantly.close()


if __name__ == "__main__":
    asyncio.run(main())
