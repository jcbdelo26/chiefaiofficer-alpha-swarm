#!/usr/bin/env python3
"""
GoHighLevel MCP Server (Production-Ready)
==========================================

MCP server providing CRM operations with:
- Async HTTP using aiohttp (non-blocking)
- Idempotency keys to prevent duplicates
- Retry logic with exponential backoff
- Request/response logging
- Rate limiting protection

Tools:
- ghl_create_contact: Create a new contact (idempotent)
- ghl_update_contact: Update contact fields
- ghl_get_contact: Get contact by ID or email
- ghl_add_tag: Add tag to contact
- ghl_create_opportunity: Create sales opportunity (idempotent)
- ghl_trigger_workflow: Trigger automation workflow
- ghl_bulk_create_contacts: Batch create with idempotency
"""

import os
import sys
import json
import hashlib
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
import logging

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("aiohttp not installed. Install with: pip install aiohttp")

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ghl-mcp")


# ============================================================================
# Idempotency Manager
# ============================================================================

@dataclass
class IdempotencyRecord:
    """Record of an idempotent operation."""
    key: str
    operation: str
    request_hash: str
    response: Dict[str, Any]
    created_at: str
    expires_at: str


class IdempotencyManager:
    """
    Manages idempotency keys to prevent duplicate operations.
    
    Keys are stored in .hive-mind/idempotency/ with 24-hour expiry.
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path(__file__).parent.parent.parent / ".hive-mind" / "idempotency"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.cache: Dict[str, IdempotencyRecord] = {}
        self._load_cache()
    
    def _load_cache(self):
        """Load recent idempotency records into memory."""
        now = datetime.utcnow()
        for file in self.storage_dir.glob("*.json"):
            try:
                with open(file) as f:
                    data = json.load(f)
                if datetime.fromisoformat(data["expires_at"]) > now:
                    self.cache[data["key"]] = IdempotencyRecord(**data)
                else:
                    file.unlink()  # Clean expired
            except Exception:
                pass
    
    def generate_key(self, operation: str, data: Dict[str, Any]) -> str:
        """Generate idempotency key from operation and data."""
        # Create deterministic hash
        key_data = f"{operation}:{json.dumps(data, sort_keys=True)}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]
    
    def check(self, key: str) -> Optional[Dict[str, Any]]:
        """Check if operation was already executed."""
        if key in self.cache:
            record = self.cache[key]
            if datetime.fromisoformat(record.expires_at) > datetime.utcnow():
                logger.info(f"Idempotency hit: {key[:8]}...")
                return record.response
            else:
                del self.cache[key]
        return None
    
    def store(self, key: str, operation: str, request_hash: str, response: Dict[str, Any]):
        """Store completed operation."""
        record = IdempotencyRecord(
            key=key,
            operation=operation,
            request_hash=request_hash,
            response=response,
            created_at=datetime.utcnow().isoformat(),
            expires_at=(datetime.utcnow() + timedelta(hours=24)).isoformat()
        )
        
        self.cache[key] = record
        
        # Persist to disk
        file_path = self.storage_dir / f"{key}.json"
        with open(file_path, "w") as f:
            json.dump(asdict(record), f)


# ============================================================================
# Async GHL Client
# ============================================================================

class AsyncGHLClient:
    """
    Async GoHighLevel API client with production features.
    
    Features:
    - Async HTTP with aiohttp
    - Automatic retry with exponential backoff
    - Rate limiting protection
    - Request/response logging
    """
    
    def __init__(self):
        self.api_key = os.getenv("GHL_API_KEY")
        self.location_id = os.getenv("GHL_LOCATION_ID")
        self.base_url = "https://services.leadconnectorhq.com"
        
        if not self.api_key:
            raise ValueError("GHL_API_KEY not set in .env")
        if not self.location_id:
            raise ValueError("GHL_LOCATION_ID not set in .env")
        
        self.idempotency = IdempotencyManager()
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Rate limiting
        self._request_count = 0
        self._rate_limit_reset = datetime.utcnow()
        self._max_requests_per_minute = 60
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Version": "2021-07-28"
                },
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session
    
    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _check_rate_limit(self):
        """Check and enforce rate limiting."""
        now = datetime.utcnow()
        
        if now > self._rate_limit_reset:
            self._request_count = 0
            self._rate_limit_reset = now + timedelta(minutes=1)
        
        if self._request_count >= self._max_requests_per_minute:
            wait_seconds = (self._rate_limit_reset - now).total_seconds()
            logger.warning(f"Rate limit reached. Waiting {wait_seconds:.1f}s")
            await asyncio.sleep(wait_seconds)
            self._request_count = 0
            self._rate_limit_reset = datetime.utcnow() + timedelta(minutes=1)
        
        self._request_count += 1
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        idempotency_key: Optional[str] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Make async HTTP request with retry logic.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            data: Request body
            params: Query parameters
            idempotency_key: Key for idempotent operations
            max_retries: Maximum retry attempts
        """
        # Check idempotency
        if idempotency_key:
            cached = self.idempotency.check(idempotency_key)
            if cached:
                return cached
        
        await self._check_rate_limit()
        
        session = await self._get_session()
        url = f"{self.base_url}/{endpoint}"
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"GHL {method} {endpoint} (attempt {attempt + 1})")
                
                if method == "GET":
                    async with session.get(url, params=params) as response:
                        result = await self._handle_response(response)
                elif method == "POST":
                    async with session.post(url, json=data, params=params) as response:
                        result = await self._handle_response(response)
                elif method == "PUT":
                    async with session.put(url, json=data, params=params) as response:
                        result = await self._handle_response(response)
                elif method == "DELETE":
                    async with session.delete(url, params=params) as response:
                        result = await self._handle_response(response)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                # Store idempotent result
                if idempotency_key and result.get("success"):
                    self.idempotency.store(
                        idempotency_key,
                        f"{method} {endpoint}",
                        hashlib.md5(json.dumps(data or {}).encode()).hexdigest(),
                        result
                    )
                
                return result
                
            except aiohttp.ClientError as e:
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    wait = 2 ** attempt  # Exponential backoff
                    await asyncio.sleep(wait)
                else:
                    return {"success": False, "error": str(e)}
            
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "Max retries exceeded"}
    
    async def _handle_response(self, response: aiohttp.ClientResponse) -> Dict[str, Any]:
        """Handle API response."""
        if response.status in [200, 201]:
            try:
                data = await response.json()
                return {"success": True, "data": data}
            except:
                return {"success": True, "data": await response.text()}
        elif response.status == 429:
            # Rate limited
            retry_after = int(response.headers.get("Retry-After", 60))
            logger.warning(f"Rate limited by GHL. Retry after {retry_after}s")
            raise aiohttp.ClientError(f"Rate limited. Retry after {retry_after}s")
        else:
            error_text = await response.text()
            return {"success": False, "error": error_text, "status": response.status}
    
    # ========================================================================
    # Contact Operations
    # ========================================================================
    
    async def create_contact(self, data: Dict[str, Any], idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new contact (idempotent).
        
        If idempotency_key not provided, generates one from email.
        """
        if not idempotency_key and "email" in data:
            idempotency_key = self.idempotency.generate_key("create_contact", {"email": data["email"]})
        
        payload = {"locationId": self.location_id, **data}
        return await self._request("POST", "contacts/", payload, idempotency_key=idempotency_key)
    
    async def update_contact(self, contact_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing contact."""
        return await self._request("PUT", f"contacts/{contact_id}", updates)
    
    async def get_contact(self, contact_id: str = None, email: str = None) -> Dict[str, Any]:
        """Get contact by ID or email."""
        if contact_id:
            return await self._request("GET", f"contacts/{contact_id}")
        elif email:
            return await self._request(
                "GET", 
                "contacts/lookup",
                params={"email": email, "locationId": self.location_id}
            )
        else:
            return {"success": False, "error": "Either contactId or email required"}
    
    async def add_tag(self, contact_id: str, tag: str) -> Dict[str, Any]:
        """Add tag to contact."""
        return await self._request("POST", f"contacts/{contact_id}/tags", {"tags": [tag]})
    
    async def bulk_create_contacts(
        self,
        contacts: List[Dict[str, Any]],
        batch_size: int = 10
    ) -> Dict[str, Any]:
        """
        Create multiple contacts with automatic batching and idempotency.
        """
        results = {"created": [], "skipped": [], "failed": []}
        
        for i in range(0, len(contacts), batch_size):
            batch = contacts[i:i + batch_size]
            
            tasks = []
            for contact in batch:
                key = self.idempotency.generate_key("create_contact", {"email": contact.get("email", "")})
                tasks.append(self.create_contact(contact, idempotency_key=key))
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for j, result in enumerate(batch_results):
                contact = batch[j]
                if isinstance(result, Exception):
                    results["failed"].append({"email": contact.get("email"), "error": str(result)})
                elif result.get("success"):
                    if "Idempotency" in str(result):
                        results["skipped"].append(contact.get("email"))
                    else:
                        results["created"].append(contact.get("email"))
                else:
                    results["failed"].append({"email": contact.get("email"), "error": result.get("error")})
        
        return {
            "success": True,
            "summary": {
                "created": len(results["created"]),
                "skipped": len(results["skipped"]),
                "failed": len(results["failed"])
            },
            "details": results
        }
    
    # ========================================================================
    # Opportunity Operations
    # ========================================================================
    
    async def create_opportunity(self, data: Dict[str, Any], idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """Create sales opportunity (idempotent)."""
        if not idempotency_key:
            idempotency_key = self.idempotency.generate_key("create_opportunity", {
                "contactId": data.get("contactId"),
                "name": data.get("name")
            })
        
        payload = {"locationId": self.location_id, **data}
        return await self._request("POST", "opportunities/", payload, idempotency_key=idempotency_key)
    
    # ========================================================================
    # Workflow Operations
    # ========================================================================
    
    async def trigger_workflow(self, contact_id: str, workflow_id: str) -> Dict[str, Any]:
        """Trigger workflow for contact."""
        return await self._request("POST", f"contacts/{contact_id}/workflow/{workflow_id}")


# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS = [
    {
        "name": "ghl_create_contact",
        "description": "Create a new contact in GoHighLevel CRM. Idempotent - safe to retry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Contact email"},
                "firstName": {"type": "string", "description": "First name"},
                "lastName": {"type": "string", "description": "Last name"},
                "phone": {"type": "string", "description": "Phone number"},
                "companyName": {"type": "string", "description": "Company name"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags to apply"},
                "customFields": {"type": "object", "description": "Custom field values"},
                "idempotencyKey": {"type": "string", "description": "Optional idempotency key"}
            },
            "required": ["email"]
        }
    },
    {
        "name": "ghl_update_contact",
        "description": "Update an existing contact in GoHighLevel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contactId": {"type": "string", "description": "GHL contact ID"},
                "updates": {"type": "object", "description": "Fields to update"}
            },
            "required": ["contactId", "updates"]
        }
    },
    {
        "name": "ghl_get_contact",
        "description": "Get contact by ID or email.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contactId": {"type": "string", "description": "GHL contact ID"},
                "email": {"type": "string", "description": "Contact email"}
            }
        }
    },
    {
        "name": "ghl_add_tag",
        "description": "Add a tag to a contact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contactId": {"type": "string", "description": "GHL contact ID"},
                "tag": {"type": "string", "description": "Tag to add"}
            },
            "required": ["contactId", "tag"]
        }
    },
    {
        "name": "ghl_create_opportunity",
        "description": "Create a sales opportunity/deal for a contact. Idempotent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contactId": {"type": "string", "description": "GHL contact ID"},
                "pipelineId": {"type": "string", "description": "Pipeline ID"},
                "stageId": {"type": "string", "description": "Pipeline stage ID"},
                "name": {"type": "string", "description": "Opportunity name"},
                "monetaryValue": {"type": "number", "description": "Deal value"},
                "idempotencyKey": {"type": "string", "description": "Optional idempotency key"}
            },
            "required": ["contactId", "name"]
        }
    },
    {
        "name": "ghl_trigger_workflow",
        "description": "Trigger an automation workflow for a contact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contactId": {"type": "string", "description": "GHL contact ID"},
                "workflowId": {"type": "string", "description": "Workflow ID to trigger"}
            },
            "required": ["contactId", "workflowId"]
        }
    },
    {
        "name": "ghl_bulk_create_contacts",
        "description": "Create multiple contacts with automatic batching. Idempotent - skips duplicates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string"},
                            "firstName": {"type": "string"},
                            "lastName": {"type": "string"},
                            "companyName": {"type": "string"},
                            "tags": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["email"]
                    }
                },
                "batchSize": {"type": "integer", "default": 10, "description": "Contacts per batch"}
            },
            "required": ["contacts"]
        }
    }
]


# ============================================================================
# MCP Server
# ============================================================================

async def main():
    """Run the MCP server."""
    
    if not MCP_AVAILABLE:
        print("MCP package not available. Install with: pip install mcp")
        return
    
    if not AIOHTTP_AVAILABLE:
        print("aiohttp required. Install with: pip install aiohttp")
        return
    
    server = Server("ghl-mcp")
    
    try:
        ghl = AsyncGHLClient()
    except ValueError as e:
        print(f"Configuration error: {e}")
        ghl = None
    
    @server.list_tools()
    async def list_tools():
        return [Tool(**tool) for tool in TOOLS]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if not ghl:
            return [TextContent(type="text", text=json.dumps({"error": "GHL not configured"}))]
        
        try:
            if name == "ghl_create_contact":
                idem_key = arguments.pop("idempotencyKey", None)
                result = await ghl.create_contact(arguments, idempotency_key=idem_key)
            
            elif name == "ghl_update_contact":
                result = await ghl.update_contact(arguments["contactId"], arguments["updates"])
            
            elif name == "ghl_get_contact":
                result = await ghl.get_contact(
                    arguments.get("contactId"),
                    arguments.get("email")
                )
            
            elif name == "ghl_add_tag":
                result = await ghl.add_tag(arguments["contactId"], arguments["tag"])
            
            elif name == "ghl_create_opportunity":
                idem_key = arguments.pop("idempotencyKey", None)
                result = await ghl.create_opportunity(arguments, idempotency_key=idem_key)
            
            elif name == "ghl_trigger_workflow":
                result = await ghl.trigger_workflow(
                    arguments["contactId"],
                    arguments["workflowId"]
                )
            
            elif name == "ghl_bulk_create_contacts":
                result = await ghl.bulk_create_contacts(
                    arguments["contacts"],
                    arguments.get("batchSize", 10)
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
        if ghl:
            await ghl.close()


if __name__ == "__main__":
    asyncio.run(main())
