#!/usr/bin/env python3
"""
Instantly MCP Server (Production-Ready)
========================================

Complete MCP server for Instantly.ai email outreach with:
- Async HTTP operations
- Idempotency for campaign creation
- Full campaign lifecycle management
- Lead status tracking
- Reply handling integration
- A/B test variant support

Tools:
- instantly_create_campaign: Create new campaign (idempotent)
- instantly_add_leads: Add leads to campaign
- instantly_get_analytics: Get campaign metrics
- instantly_pause_campaign: Pause/resume campaign
- instantly_list_campaigns: List all campaigns
- instantly_create_sequence: Create multi-step sequence
- instantly_get_lead_status: Check lead email status
- instantly_delete_campaign: Delete a campaign
- instantly_export_replies: Export campaign replies
- instantly_update_campaign: Update campaign settings
"""

import os
import sys
import json
import hashlib
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
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
# Async Instantly Client
# ============================================================================

class AsyncInstantlyClient:
    """
    Production-ready Instantly.ai API client.
    
    Features:
    - Async HTTP with aiohttp
    - Idempotent campaign creation
    - Full API coverage
    - Error handling and retries
    """
    
    def __init__(self):
        self.api_key = os.getenv("INSTANTLY_API_KEY")
        self.base_url = "https://api.instantly.ai/api/v1"
        
        if not self.api_key:
            raise ValueError("INSTANTLY_API_KEY not set")
        
        self.idempotency = IdempotencyManager()
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
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
        """Make async API request."""
        
        # Check idempotency
        if idempotency_key:
            cached = self.idempotency.check(idempotency_key)
            if cached:
                logger.info(f"Idempotency hit: {idempotency_key[:8]}...")
                return cached
        
        session = await self._get_session()
        url = f"{self.base_url}/{endpoint}"
        
        # Instantly uses API key as query param
        if params is None:
            params = {}
        params["api_key"] = self.api_key
        
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
                    async with session.delete(url, params=params) as response:
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
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new campaign (idempotent)."""
        
        if not idempotency_key:
            idempotency_key = self.idempotency.generate_key("create_campaign", {
                "name": name,
                "from_email": from_email
            })
        
        data = {
            "name": name,
            "from_email": from_email,
            "subject": subject,
            "body": body
        }
        
        if schedule:
            data["schedule"] = schedule
        
        return await self._request("POST", "campaign/create", data, idempotency_key=idempotency_key)
    
    async def update_campaign(
        self,
        campaign_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update campaign settings."""
        data = {"campaign_id": campaign_id, **updates}
        return await self._request("PATCH", "campaign/update", data)
    
    async def delete_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Delete a campaign."""
        return await self._request("DELETE", f"campaign/{campaign_id}")
    
    async def list_campaigns(
        self,
        status: str = "all",
        limit: int = 50,
        skip: int = 0
    ) -> Dict[str, Any]:
        """List campaigns with pagination."""
        params = {"limit": limit, "skip": skip}
        if status != "all":
            params["status"] = status
        return await self._request("GET", "campaign/list", params=params)
    
    async def pause_campaign(self, campaign_id: str, action: str) -> Dict[str, Any]:
        """Pause or resume a campaign."""
        data = {
            "campaign_id": campaign_id,
            "status": "paused" if action == "pause" else "active"
        }
        return await self._request("POST", "campaign/status", data)
    
    # ========================================================================
    # Sequence Operations
    # ========================================================================
    
    async def create_sequence(
        self,
        campaign_id: str,
        steps: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create multi-step email sequence with A/B variants."""
        sequences = []
        
        for step in steps:
            seq_item = {
                "delay_days": step.get("delay_days", 0),
                "subject": step.get("subject", ""),
                "body": step.get("body", "")
            }
            
            # Support A/B variants
            if "subject_b" in step:
                seq_item["subject_b"] = step["subject_b"]
            if "body_b" in step:
                seq_item["body_b"] = step["body_b"]
            
            sequences.append(seq_item)
        
        data = {
            "campaign_id": campaign_id,
            "sequences": sequences
        }
        
        return await self._request("POST", "campaign/sequence", data)
    
    # ========================================================================
    # Lead Operations
    # ========================================================================
    
    async def add_leads(
        self,
        campaign_id: str,
        leads: List[Dict[str, Any]],
        skip_duplicates: bool = True
    ) -> Dict[str, Any]:
        """Add leads to a campaign."""
        # Format leads for Instantly API
        formatted_leads = []
        for lead in leads:
            formatted = {
                "email": lead["email"],
                "first_name": lead.get("first_name", lead.get("firstName", "")),
                "last_name": lead.get("last_name", lead.get("lastName", "")),
                "company_name": lead.get("company", lead.get("companyName", ""))
            }
            
            # Add custom variables
            custom = lead.get("custom_variables", lead.get("customFields", {}))
            if custom:
                formatted["custom_variables"] = custom
            
            formatted_leads.append(formatted)
        
        data = {
            "campaign_id": campaign_id,
            "leads": formatted_leads,
            "skip_if_in_workspace": skip_duplicates
        }
        
        return await self._request("POST", "lead/add", data)
    
    async def get_lead_status(
        self,
        email: str,
        campaign_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get status of a lead across campaigns."""
        params = {"email": email}
        if campaign_id:
            params["campaign_id"] = campaign_id
        return await self._request("GET", "lead/status", params=params)
    
    async def remove_lead(
        self,
        campaign_id: str,
        email: str
    ) -> Dict[str, Any]:
        """Remove a lead from a campaign."""
        data = {"campaign_id": campaign_id, "email": email}
        return await self._request("POST", "lead/remove", data)
    
    # ========================================================================
    # Analytics Operations
    # ========================================================================
    
    async def get_analytics(
        self,
        campaign_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get campaign analytics summary."""
        params = {}
        if campaign_id:
            params["campaign_id"] = campaign_id
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        
        return await self._request("GET", "analytics/campaign/summary", params=params)
    
    async def export_replies(
        self,
        campaign_id: str,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Export replies from a campaign."""
        params = {"campaign_id": campaign_id, "limit": limit}
        return await self._request("GET", "analytics/replies", params=params)
    
    async def get_detailed_analytics(
        self,
        campaign_id: str
    ) -> Dict[str, Any]:
        """Get detailed analytics including open/click rates per step."""
        params = {"campaign_id": campaign_id}
        return await self._request("GET", "analytics/campaign/steps", params=params)


# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS = [
    {
        "name": "instantly_create_campaign",
        "description": "Create a new email campaign in Instantly. Idempotent - safe to retry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Campaign name"},
                "from_email": {"type": "string", "description": "Sending email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body (HTML supported)"},
                "schedule": {
                    "type": "object",
                    "properties": {
                        "timezone": {"type": "string", "default": "America/New_York"},
                        "days": {"type": "array", "items": {"type": "string"}},
                        "start_hour": {"type": "integer", "default": 9},
                        "end_hour": {"type": "integer", "default": 17}
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
                    "description": "Fields to update (name, schedule, etc.)"
                }
            },
            "required": ["campaign_id", "updates"]
        }
    },
    {
        "name": "instantly_add_leads",
        "description": "Add leads to an existing campaign with automatic deduplication.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Campaign ID"},
                "leads": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string"},
                            "first_name": {"type": "string"},
                            "last_name": {"type": "string"},
                            "company": {"type": "string"},
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
                "status": {"type": "string", "enum": ["active", "paused", "completed", "all"], "default": "all"},
                "limit": {"type": "integer", "default": 50},
                "skip": {"type": "integer", "default": 0}
            }
        }
    },
    {
        "name": "instantly_create_sequence",
        "description": "Create a multi-step email sequence with optional A/B variants.",
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
        "description": "Export all replies from a campaign for processing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "limit": {"type": "integer", "default": 100}
            },
            "required": ["campaign_id"]
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
                    idempotency_key=idem_key
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
            
            elif name == "instantly_delete_campaign":
                result = await instantly.delete_campaign(arguments["campaign_id"])
            
            elif name == "instantly_list_campaigns":
                result = await instantly.list_campaigns(
                    arguments.get("status", "all"),
                    arguments.get("limit", 50),
                    arguments.get("skip", 0)
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
