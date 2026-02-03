#!/usr/bin/env python3
"""
Slack MCP Server
================
MCP server for Slack integration providing:
- Approval request UI (Block Kit)
- Alert notifications
- Channel messaging
- Interactive message handling

Tools:
- send_approval_request: Send approval request with Block Kit buttons
- send_alert: Send alert notification to channel
- send_message: Send simple message to channel
- update_message: Update existing message
- get_channel_history: Get recent messages from channel
- handle_interaction: Process button clicks and interactions

Usage:
    python mcp-servers/slack-mcp/server.py
"""

import os
import sys
import json
import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
from enum import Enum

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("[slack-mcp] MCP library not available, running in standalone mode")


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


# =============================================================================
# SLACK CLIENT (Mock for development, real client for production)
# =============================================================================

class SlackClient:
    """
    Slack API client wrapper.
    Uses environment variables for configuration.
    """
    
    def __init__(self):
        self.token = os.getenv("SLACK_BOT_TOKEN", "")
        self.signing_secret = os.getenv("SLACK_SIGNING_SECRET", "")
        self.default_channel = os.getenv("SLACK_DEFAULT_CHANNEL", "#revops-alerts")
        self.approval_channel = os.getenv("SLACK_APPROVAL_CHANNEL", "#revops-approvals")
        self.is_configured = bool(self.token)
        
        # Pending approvals storage (in production, use Redis/DB)
        self.pending_approvals: Dict[str, Dict[str, Any]] = {}
        self._storage_path = PROJECT_ROOT / ".hive-mind" / "approval_queue.json"
        self._load_pending()
    
    def _load_pending(self):
        """Load pending approvals from disk."""
        if self._storage_path.exists():
            try:
                with open(self._storage_path) as f:
                    self.pending_approvals = json.load(f)
            except Exception:
                self.pending_approvals = {}
    
    def _save_pending(self):
        """Save pending approvals to disk."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._storage_path, 'w') as f:
            json.dump(self.pending_approvals, f, indent=2)
    
    async def send_message(
        self,
        channel: str,
        text: str,
        blocks: Optional[List[Dict]] = None,
        thread_ts: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a message to a Slack channel."""
        if not self.is_configured:
            return self._mock_send(channel, text, blocks)
        
        try:
            from slack_sdk.web.async_client import AsyncWebClient
            client = AsyncWebClient(token=self.token)
            
            response = await client.chat_postMessage(
                channel=channel,
                text=text,
                blocks=blocks,
                thread_ts=thread_ts
            )
            return {
                "ok": response["ok"],
                "ts": response["ts"],
                "channel": response["channel"]
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Update an existing message."""
        if not self.is_configured:
            return {"ok": True, "ts": ts, "channel": channel, "mock": True}
        
        try:
            from slack_sdk.web.async_client import AsyncWebClient
            client = AsyncWebClient(token=self.token)
            
            response = await client.chat_update(
                channel=channel,
                ts=ts,
                text=text,
                blocks=blocks
            )
            return {
                "ok": response["ok"],
                "ts": response["ts"],
                "channel": response["channel"]
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def _mock_send(
        self,
        channel: str,
        text: str,
        blocks: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Mock send for development."""
        ts = datetime.now(timezone.utc).timestamp()
        print(f"[slack-mcp MOCK] Sending to {channel}: {text[:100]}...")
        return {
            "ok": True,
            "ts": str(ts),
            "channel": channel,
            "mock": True
        }
    
    def create_approval_id(self, workflow_id: str, action_type: str) -> str:
        """Generate unique approval ID."""
        data = f"{workflow_id}_{action_type}_{datetime.now(timezone.utc).isoformat()}"
        return f"APR-{hashlib.sha256(data.encode()).hexdigest()[:12]}"


# =============================================================================
# BLOCK KIT BUILDERS
# =============================================================================

def build_approval_blocks(
    approval_id: str,
    title: str,
    description: str,
    context: Dict[str, Any],
    requester: str,
    risk_level: str = "medium"
) -> List[Dict]:
    """Build Block Kit blocks for approval request."""
    
    risk_emoji = {
        "low": "🟢",
        "medium": "🟡",
        "high": "🟠",
        "critical": "🔴"
    }.get(risk_level.lower(), "⚪")
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🔔 Approval Request: {title}",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": description
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*Requester:* {requester}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Risk Level:* {risk_emoji} {risk_level.upper()}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*ID:* `{approval_id}`"
                }
            ]
        },
        {"type": "divider"}
    ]
    
    # Add context fields
    if context:
        fields = []
        for key, value in list(context.items())[:10]:  # Max 10 fields
            fields.append({
                "type": "mrkdwn",
                "text": f"*{key}:*\n{str(value)[:100]}"
            })
        
        if fields:
            blocks.append({
                "type": "section",
                "fields": fields[:10]
            })
            blocks.append({"type": "divider"})
    
    # Add action buttons
    blocks.append({
        "type": "actions",
        "block_id": f"approval_{approval_id}",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "✅ Approve", "emoji": True},
                "style": "primary",
                "action_id": f"approve_{approval_id}",
                "value": approval_id
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "❌ Reject", "emoji": True},
                "style": "danger",
                "action_id": f"reject_{approval_id}",
                "value": approval_id
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "✏️ Edit", "emoji": True},
                "action_id": f"edit_{approval_id}",
                "value": approval_id
            }
        ]
    })
    
    return blocks


def build_alert_blocks(
    title: str,
    message: str,
    level: str,
    details: Optional[Dict[str, Any]] = None
) -> List[Dict]:
    """Build Block Kit blocks for alert notification."""
    
    level_config = {
        "info": ("ℹ️", "#36a64f"),
        "warning": ("⚠️", "#daa038"),
        "error": ("❌", "#cc4444"),
        "critical": ("🚨", "#ff0000")
    }
    
    emoji, color = level_config.get(level.lower(), ("❔", "#808080"))
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {title}",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": message
            }
        }
    ]
    
    if details:
        fields = []
        for key, value in list(details.items())[:6]:
            fields.append({
                "type": "mrkdwn",
                "text": f"*{key}:* {str(value)[:50]}"
            })
        
        if fields:
            blocks.append({
                "type": "section",
                "fields": fields
            })
    
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"_Alert generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}_"
            }
        ]
    })
    
    return blocks


# =============================================================================
# MCP TOOLS
# =============================================================================

slack_client = SlackClient()


async def send_approval_request(
    workflow_id: str,
    action_type: str,
    title: str,
    description: str,
    context: Dict[str, Any],
    requester: str = "UNIFIED_QUEEN",
    risk_level: str = "medium",
    timeout_minutes: int = 30,
    channel: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send an approval request with interactive buttons.
    
    Args:
        workflow_id: Workflow requesting approval
        action_type: Type of action requiring approval
        title: Short title for the approval
        description: Detailed description of what's being approved
        context: Additional context data
        requester: Agent/system requesting approval
        risk_level: low/medium/high/critical
        timeout_minutes: Minutes before escalation
        channel: Override default approval channel
        
    Returns:
        Dict with approval_id, status, message_ts
    """
    approval_id = slack_client.create_approval_id(workflow_id, action_type)
    target_channel = channel or slack_client.approval_channel
    
    blocks = build_approval_blocks(
        approval_id=approval_id,
        title=title,
        description=description,
        context=context,
        requester=requester,
        risk_level=risk_level
    )
    
    result = await slack_client.send_message(
        channel=target_channel,
        text=f"Approval Request: {title}",
        blocks=blocks
    )
    
    if result.get("ok"):
        # Store pending approval
        slack_client.pending_approvals[approval_id] = {
            "approval_id": approval_id,
            "workflow_id": workflow_id,
            "action_type": action_type,
            "title": title,
            "description": description,
            "context": context,
            "requester": requester,
            "risk_level": risk_level,
            "status": "pending",
            "channel": target_channel,
            "message_ts": result.get("ts"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "timeout_at": (datetime.now(timezone.utc).timestamp() + timeout_minutes * 60)
        }
        slack_client._save_pending()
    
    return {
        "approval_id": approval_id,
        "status": "pending" if result.get("ok") else "failed",
        "message_ts": result.get("ts"),
        "channel": target_channel,
        "error": result.get("error")
    }


async def send_alert(
    title: str,
    message: str,
    level: str = "info",
    details: Optional[Dict[str, Any]] = None,
    channel: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send an alert notification.
    
    Args:
        title: Alert title
        message: Alert message body
        level: info/warning/error/critical
        details: Additional key-value details
        channel: Override default channel
        
    Returns:
        Dict with ok status and message_ts
    """
    target_channel = channel or slack_client.default_channel
    
    blocks = build_alert_blocks(
        title=title,
        message=message,
        level=level,
        details=details
    )
    
    result = await slack_client.send_message(
        channel=target_channel,
        text=f"[{level.upper()}] {title}: {message[:100]}",
        blocks=blocks
    )
    
    return {
        "ok": result.get("ok", False),
        "message_ts": result.get("ts"),
        "channel": target_channel,
        "error": result.get("error")
    }


async def send_message(
    text: str,
    channel: Optional[str] = None,
    thread_ts: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send a simple text message.
    
    Args:
        text: Message text (supports mrkdwn)
        channel: Target channel (default: alerts channel)
        thread_ts: Reply in thread
        
    Returns:
        Dict with ok status and message_ts
    """
    target_channel = channel or slack_client.default_channel
    
    result = await slack_client.send_message(
        channel=target_channel,
        text=text,
        thread_ts=thread_ts
    )
    
    return {
        "ok": result.get("ok", False),
        "message_ts": result.get("ts"),
        "channel": target_channel,
        "error": result.get("error")
    }


async def get_approval_status(approval_id: str) -> Dict[str, Any]:
    """
    Get the status of a pending approval.
    
    Args:
        approval_id: The approval ID to check
        
    Returns:
        Dict with status and approval details
    """
    approval = slack_client.pending_approvals.get(approval_id)
    
    if not approval:
        return {"found": False, "error": "Approval not found"}
    
    # Check for timeout
    if approval["status"] == "pending":
        if datetime.now(timezone.utc).timestamp() > approval.get("timeout_at", float('inf')):
            approval["status"] = "timeout"
            slack_client._save_pending()
    
    return {
        "found": True,
        "approval_id": approval_id,
        "status": approval["status"],
        "workflow_id": approval["workflow_id"],
        "action_type": approval["action_type"],
        "created_at": approval["created_at"],
        "approved_by": approval.get("approved_by"),
        "approved_at": approval.get("approved_at")
    }


async def process_interaction(
    approval_id: str,
    action: str,
    user_id: str,
    user_name: str
) -> Dict[str, Any]:
    """
    Process an approval interaction (approve/reject/edit).
    
    Args:
        approval_id: The approval being acted upon
        action: approve/reject/edit
        user_id: Slack user ID who took action
        user_name: Slack user name
        
    Returns:
        Dict with result of the action
    """
    approval = slack_client.pending_approvals.get(approval_id)
    
    if not approval:
        return {"ok": False, "error": "Approval not found"}
    
    if approval["status"] != "pending":
        return {"ok": False, "error": f"Approval already {approval['status']}"}
    
    if action == "approve":
        approval["status"] = "approved"
        approval["approved_by"] = user_name
        approval["approved_at"] = datetime.now(timezone.utc).isoformat()
        result_text = f"✅ Approved by {user_name}"
        
    elif action == "reject":
        approval["status"] = "rejected"
        approval["rejected_by"] = user_name
        approval["rejected_at"] = datetime.now(timezone.utc).isoformat()
        result_text = f"❌ Rejected by {user_name}"
        
    elif action == "edit":
        approval["edit_requested_by"] = user_name
        result_text = f"✏️ Edit requested by {user_name}"
        # Don't change status yet - wait for edited version
        return {
            "ok": True,
            "action": "edit_requested",
            "approval_id": approval_id
        }
    else:
        return {"ok": False, "error": f"Unknown action: {action}"}
    
    slack_client._save_pending()
    
    # Update the original message
    if approval.get("message_ts") and approval.get("channel"):
        await slack_client.update_message(
            channel=approval["channel"],
            ts=approval["message_ts"],
            text=f"Approval {approval_id}: {result_text}",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{approval['title']}*\n{result_text}"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"_Processed at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}_"
                        }
                    ]
                }
            ]
        )
    
    return {
        "ok": True,
        "action": action,
        "status": approval["status"],
        "approval_id": approval_id,
        "processed_by": user_name
    }


async def list_pending_approvals() -> Dict[str, Any]:
    """
    List all pending approvals.
    
    Returns:
        Dict with list of pending approvals
    """
    pending = []
    now = datetime.now(timezone.utc).timestamp()
    
    for approval_id, approval in slack_client.pending_approvals.items():
        if approval["status"] == "pending":
            # Check timeout
            is_timed_out = now > approval.get("timeout_at", float('inf'))
            
            pending.append({
                "approval_id": approval_id,
                "title": approval["title"],
                "workflow_id": approval["workflow_id"],
                "action_type": approval["action_type"],
                "risk_level": approval["risk_level"],
                "created_at": approval["created_at"],
                "timed_out": is_timed_out
            })
    
    return {
        "count": len(pending),
        "approvals": pending
    }


# =============================================================================
# MCP SERVER
# =============================================================================

if MCP_AVAILABLE:
    server = Server("slack-mcp")
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="send_approval_request",
                description="Send an approval request with interactive Slack buttons",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Workflow ID requesting approval"},
                        "action_type": {"type": "string", "description": "Type of action (send_email, create_event, etc.)"},
                        "title": {"type": "string", "description": "Short approval title"},
                        "description": {"type": "string", "description": "Detailed description"},
                        "context": {"type": "object", "description": "Additional context data"},
                        "requester": {"type": "string", "description": "Agent requesting approval"},
                        "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        "timeout_minutes": {"type": "integer", "description": "Minutes before escalation"}
                    },
                    "required": ["workflow_id", "action_type", "title", "description"]
                }
            ),
            Tool(
                name="send_alert",
                description="Send an alert notification to Slack",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Alert title"},
                        "message": {"type": "string", "description": "Alert message"},
                        "level": {"type": "string", "enum": ["info", "warning", "error", "critical"]},
                        "details": {"type": "object", "description": "Additional details"}
                    },
                    "required": ["title", "message"]
                }
            ),
            Tool(
                name="send_message",
                description="Send a simple message to Slack",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Message text"},
                        "channel": {"type": "string", "description": "Target channel"},
                        "thread_ts": {"type": "string", "description": "Thread timestamp for reply"}
                    },
                    "required": ["text"]
                }
            ),
            Tool(
                name="get_approval_status",
                description="Check the status of a pending approval",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "approval_id": {"type": "string", "description": "Approval ID to check"}
                    },
                    "required": ["approval_id"]
                }
            ),
            Tool(
                name="list_pending_approvals",
                description="List all pending approvals",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="process_interaction",
                description="Process an approval action (approve/reject/edit)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "approval_id": {"type": "string"},
                        "action": {"type": "string", "enum": ["approve", "reject", "edit"]},
                        "user_id": {"type": "string"},
                        "user_name": {"type": "string"}
                    },
                    "required": ["approval_id", "action", "user_id", "user_name"]
                }
            )
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "send_approval_request":
            result = await send_approval_request(**arguments)
        elif name == "send_alert":
            result = await send_alert(**arguments)
        elif name == "send_message":
            result = await send_message(**arguments)
        elif name == "get_approval_status":
            result = await get_approval_status(**arguments)
        elif name == "list_pending_approvals":
            result = await list_pending_approvals()
        elif name == "process_interaction":
            result = await process_interaction(**arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


# =============================================================================
# CLI / DEMO
# =============================================================================

async def demo():
    """Run demo of slack-mcp tools."""
    print("\n=== Slack MCP Demo ===\n")
    
    # Demo approval request
    print("1. Sending approval request...")
    approval_result = await send_approval_request(
        workflow_id="W-demo-001",
        action_type="send_email",
        title="Cold Outreach to Acme Corp",
        description="Send introductory email to john.smith@acme.com",
        context={
            "contact": "John Smith",
            "company": "Acme Corp",
            "template": "thought_leadership_v2"
        },
        requester="CRAFTER",
        risk_level="medium"
    )
    print(f"   Result: {json.dumps(approval_result, indent=2)}")
    
    # Demo alert
    print("\n2. Sending alert...")
    alert_result = await send_alert(
        title="Rate Limit Warning",
        message="GHL email rate limit at 80% capacity",
        level="warning",
        details={
            "current": "120/150",
            "reset_in": "45 minutes"
        }
    )
    print(f"   Result: {json.dumps(alert_result, indent=2)}")
    
    # Demo simple message
    print("\n3. Sending simple message...")
    msg_result = await send_message(
        text="🚀 *Daily Pipeline Report*\n• 15 new leads\n• 3 meetings booked\n• 2 approvals pending"
    )
    print(f"   Result: {json.dumps(msg_result, indent=2)}")
    
    # Check approval status
    print("\n4. Checking approval status...")
    status = await get_approval_status(approval_result["approval_id"])
    print(f"   Status: {json.dumps(status, indent=2)}")
    
    # List pending
    print("\n5. Listing pending approvals...")
    pending = await list_pending_approvals()
    print(f"   Pending: {json.dumps(pending, indent=2)}")
    
    print("\n=== Demo Complete ===\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        asyncio.run(demo())
    elif MCP_AVAILABLE:
        import mcp
        mcp.run(server)
    else:
        print("Run with 'demo' argument for standalone demo")
        print("Example: python server.py demo")
