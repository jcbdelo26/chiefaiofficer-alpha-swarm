#!/usr/bin/env python3
"""
Health Dashboard - FastAPI Web Server
=====================================
Real-time health monitoring dashboard for the CAIO RevOps Swarm.

Endpoints:
- GET  /api/health       - Current health status
- GET  /api/metrics      - Historical metrics
- GET  /api/agents       - Agent status
- GET  /api/integrations - Integration status
- WS   /ws               - Real-time updates

Usage:
    uvicorn dashboard.health_app:app --host 0.0.0.0 --port 8080 --reload
"""

import os
import sys
import json
import asyncio
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.unified_health_monitor import get_health_monitor, HealthMonitor
from core.precision_scorecard import get_scorecard, reset_scorecard
from core.messaging_strategy import MessagingStrategy
from core.signal_detector import SignalDetector
from core.ghl_outreach import OutreachConfig, GHLOutreachClient, EmailTemplate, OutreachType
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# =============================================================================
# CORRELATION ID MIDDLEWARE
# =============================================================================

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds correlation IDs to all requests for request tracing.

    - Checks for existing X-Correlation-ID header
    - Generates new UUID if not present
    - Adds correlation ID to response headers
    - Stores in request state for access in route handlers
    """

    async def dispatch(self, request: Request, call_next):
        # Get or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid4())

        # Store in request state for route handlers
        request.state.correlation_id = correlation_id

        # Process request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id

        return response


# =============================================================================
# AUTHENTICATION
# =============================================================================

DASHBOARD_AUTH_TOKEN = os.getenv("DASHBOARD_AUTH_TOKEN", "")

def require_auth(token: str = Query(None, alias="token")):
    """
    Simple token-based authentication for sensitive endpoints.
    Requires ?token=xxx query parameter matching DASHBOARD_AUTH_TOKEN.
    """
    if not DASHBOARD_AUTH_TOKEN:
        # If no token configured, allow access (dev mode) but warn
        print("WARNING: DASHBOARD_AUTH_TOKEN not set - endpoints are unprotected!")
        return True
    
    if not token or token != DASHBOARD_AUTH_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized. Please provide valid ?token= parameter."
        )
    return True

# =============================================================================
# APP SETUP
# =============================================================================

app = FastAPI(
    title="CAIO Swarm Health Dashboard",
    description="Real-time health monitoring for the unified agent swarm",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add correlation ID middleware for request tracing
app.add_middleware(CorrelationIDMiddleware)

# Serve static files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# =============================================================================
# WEBSOCKET MANAGER
# =============================================================================

class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# =============================================================================
# BACKGROUND TASKS
# =============================================================================

async def health_broadcast_loop():
    """Broadcast health updates to WebSocket clients."""
    monitor = get_health_monitor()
    
    while True:
        await asyncio.sleep(5)  # Update every 5 seconds
        
        if manager.active_connections:
            try:
                status = monitor.get_health_status()
                await manager.broadcast({
                    "type": "health_update",
                    "data": status
                })
            except Exception as e:
                print(f"Broadcast error: {e}")


@app.on_event("startup")
async def startup_event():
    """Start background tasks on app startup."""
    # Start the health monitor
    monitor = get_health_monitor()
    asyncio.create_task(monitor.start())
    
    # Start broadcast loop
    asyncio.create_task(health_broadcast_loop())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    monitor = get_health_monitor()
    await monitor.stop()


# =============================================================================
# API ROUTES
# =============================================================================

@app.get("/")
async def root():
    """Serve the dashboard HTML."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Health Dashboard</h1><p>Static files not found.</p>")


# =============================================================================
# ADMIN HELPER ENDPOINTS
# =============================================================================

@app.post("/api/admin/regenerate_queue")
async def regenerate_queue(token: str = Query(None)):
    """
    Trigger regeneration of all pending emails in the queue.
    Uses new MessagingStrategy templates.
    """
    require_auth(token)
    
    try:
        updated_count = 0
        shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
        
        if not shadow_dir.exists():
            return {"status": "error", "message": "Shadow email directory not found"}
        
        # Init strategies
        messaging = MessagingStrategy()
        detector = SignalDetector()
        
        for email_file in shadow_dir.glob("*.json"):
            try:
                with open(email_file, "r") as f:
                    data = json.load(f)
                
                if data.get("status") != "pending":
                    continue
                
                # Reconstruct context for regeneration
                recipient = data.get("recipient_data", {})
                
                # Tech stack extraction
                tech_stack_str = "your tech stack"
                if "context" in data:
                     # Attempt to extract from context if available
                     context_triggers = data["context"].get("triggers", [])
                     # This is imperfect as we don't store raw tech stack in dashboard json usually
                     # But we can try to infer or just use generic placeholders which is better than nothing
                
                contact_info = {
                    "first_name": recipient.get("name", "").split(" ")[0],
                    "company_name": recipient.get("company"),
                    "job_title": recipient.get("title"),
                    "tier": 1 if data.get("priority") == "high" else 3
                }
                
                # Run Detection (Simulated based on Tier)
                # Since we don't have raw signals, we use the tier to pick best available logic
                # For high priority (Tier 1), we check if we can detect intent
                
                # Detect signals from available data
                signals = detector.detect_signals(contact_info)
                primary_signal = detector.get_primary_signal(signals)
                
                # Select Template
                template_id, subject_tmpl, body_tmpl = messaging.select_template(contact_info, primary_signal)
                
                # Format
                formatted_subject = subject_tmpl.format(
                    first_name=contact_info["first_name"] or "there",
                    company=contact_info["company_name"] or "your company",
                    industry="your industry",
                    title=contact_info["job_title"] or "Leader",
                    tech_stack=tech_stack_str
                )
                
                formatted_body = body_tmpl.format(
                    first_name=contact_info["first_name"] or "there",
                    company=contact_info["company_name"] or "your company",
                    industry="your industry",
                    title=contact_info["job_title"] or "Leader",
                    tech_stack=tech_stack_str
                )
                
                # Update File
                data["subject"] = formatted_subject
                data["body"] = formatted_body
                data["template_id"] = template_id
                data["regenerated_at"] = datetime.now(timezone.utc).isoformat()
                data["regeneration_note"] = "Applied Email Overhaul v2"
                
                with open(email_file, "w") as f:
                    json.dump(data, f, indent=2)
                
                updated_count += 1
                
            except Exception as e:
                print(f"Error updating {email_file}: {e}")
                continue
        
        return {
            "status": "success", 
            "updated_count": updated_count,
            "message": f"Successfully regenerated {updated_count} emails using new strategies."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check(token: str = Query(None)):
    """Get current health status of all components."""
    require_auth(token)
    monitor = get_health_monitor()
    return monitor.get_health_status()


@app.get("/api/metrics")
async def get_metrics(hours: int = 24) -> Dict[str, Any]:
    """Get historical metrics."""
    monitor = get_health_monitor()
    return monitor.get_metrics_history(hours)


@app.get("/api/agents")
async def get_agents() -> Dict[str, Any]:
    """Get status of all agents."""
    monitor = get_health_monitor()
    status = monitor.get_health_status()
    return {
        "agents": status.get("agents", {}),
        "timestamp": status.get("timestamp")
    }


@app.get("/api/agents/{agent_name}")
async def get_agent(agent_name: str) -> Dict[str, Any]:
    """Get status of a specific agent."""
    monitor = get_health_monitor()
    agent_status = monitor.get_agent_status(agent_name)
    
    if not agent_status:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    return agent_status


@app.get("/api/integrations")
async def get_integrations() -> Dict[str, Any]:
    """Get status of all integrations."""
    monitor = get_health_monitor()
    status = monitor.get_health_status()
    return {
        "integrations": status.get("integrations", {}),
        "timestamp": status.get("timestamp")
    }


@app.get("/api/mcp-servers")
async def get_mcp_servers() -> Dict[str, Any]:
    """Get status of all MCP servers."""
    monitor = get_health_monitor()
    status = monitor.get_health_status()
    return {
        "mcp_servers": status.get("mcp_servers", {}),
        "timestamp": status.get("timestamp")
    }


@app.get("/api/guardrails")
async def get_guardrails() -> Dict[str, Any]:
    """Get status of guardrails."""
    monitor = get_health_monitor()
    status = monitor.get_health_status()
    return {
        "guardrails": status.get("guardrails", {}),
        "rate_limits": status.get("rate_limits", {}),
        "email_limits": status.get("email_limits", {}),
        "timestamp": status.get("timestamp")
    }


@app.get("/api/actions")
async def get_recent_actions(limit: int = 20) -> Dict[str, Any]:
    """Get recent actions."""
    monitor = get_health_monitor()
    status = monitor.get_health_status()
    actions = status.get("recent_actions", [])
    return {
        "actions": actions[:limit],
        "total": len(actions),
        "timestamp": status.get("timestamp")
    }


@app.get("/api/alerts")
async def get_alerts() -> Dict[str, Any]:
    """Get recent alerts."""
    monitor = get_health_monitor()
    status = monitor.get_health_status()
    return {
        "alerts": status.get("alerts", []),
        "timestamp": status.get("timestamp")
    }


# =============================================================================
# FRONTEND ERROR REPORTING (for debug-mcp correlation)
# =============================================================================

@app.post("/api/errors/frontend")
async def report_frontend_error(
    request: Request,
    error_data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Receive frontend/browser errors for correlation with backend failures.

    This endpoint should be called by the dashboard's JavaScript error handler
    to report console errors, unhandled exceptions, and React error boundaries.

    Expected payload:
    {
        "message": "Error message",
        "stack": "Stack trace (optional)",
        "url": "Page URL where error occurred",
        "type": "error|warning|exception",
        "user_agent": "Browser user agent (optional)"
    }

    The correlation ID from the request header is automatically attached.
    """
    # Get correlation ID from request state
    correlation_id = getattr(request.state, "correlation_id", None)

    # Build error entry
    error_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": error_data.get("message", "Unknown error"),
        "stack": error_data.get("stack"),
        "url": error_data.get("url"),
        "console_type": error_data.get("type", "error"),
        "user_agent": error_data.get("user_agent"),
        "correlation_id": correlation_id,
        "source": "frontend"
    }

    # Write to frontend errors log
    frontend_log = PROJECT_ROOT / ".hive-mind" / "frontend_errors.jsonl"
    frontend_log.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(frontend_log, "a") as f:
            f.write(json.dumps(error_entry) + "\n")
    except Exception as e:
        print(f"Failed to log frontend error: {e}")

    return {
        "status": "logged",
        "correlation_id": correlation_id,
        "timestamp": error_entry["timestamp"]
    }


@app.get("/api/debug/correlation-id")
async def get_correlation_id(request: Request) -> Dict[str, Any]:
    """
    Get the current request's correlation ID.

    Useful for debugging and for the frontend to know which
    correlation ID to attach to error reports.
    """
    correlation_id = getattr(request.state, "correlation_id", None)
    return {
        "correlation_id": correlation_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/debug/filesystem")
async def debug_filesystem(path: str = ".hive-mind/shadow_mode_emails"):
    """
    Debug: List files in a directory relative to project root.
    """
    target_dir = PROJECT_ROOT / path
    if not target_dir.exists():
        return {"exists": False, "path": str(target_dir), "files": []}
    
    files = []
    for f in target_dir.iterdir():
        stats = f.stat()
        files.append({
            "name": f.name,
            "size": stats.st_size,
            "modified": datetime.fromtimestamp(stats.st_mtime).isoformat()
        })
    return {"exists": True, "path": str(target_dir), "file_count": len(files), "files": files}


@app.post("/api/actions/record")
async def record_action(
    component: str,
    success: bool,
    latency_ms: float = 0,
    error: Optional[str] = None,
    agent: Optional[str] = None,
    action: Optional[str] = None
) -> Dict[str, Any]:
    """Record an action for a component."""
    monitor = get_health_monitor()
    monitor.record_action(component, success, latency_ms, error, agent, action)
    return {"status": "recorded"}


@app.post("/api/email/record")
async def record_email(count: int = 1) -> Dict[str, Any]:
    """Record emails sent."""
    monitor = get_health_monitor()
    monitor.record_email_sent(count)
    return {"status": "recorded", "count": count}


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    
    # Send initial status
    monitor = get_health_monitor()
    try:
        await websocket.send_json({
            "type": "health_update",
            "data": monitor.get_health_status()
        })
        
        # Keep connection alive and handle messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif data.get("type") == "refresh":
                    await websocket.send_json({
                        "type": "health_update",
                        "data": monitor.get_health_status()
                    })
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# =============================================================================
# PRECISION SCORECARD ENDPOINTS
# =============================================================================

@app.get("/api/scorecard")
async def get_scorecard_summary():
    """
    Get the Precision Scorecard summary.
    
    Returns the 12 key metrics, organized by category, plus the current constraint.
    Inspired by Precision.co: "The only scorecard that tells you what to fix."
    """
    scorecard = get_scorecard()
    return scorecard.get_summary()


@app.post("/api/scorecard/refresh")
async def refresh_scorecard():
    """
    Force refresh all scorecard metrics from data sources.
    """
    scorecard = get_scorecard()
    scorecard.refresh()
    return {"status": "refreshed", "timestamp": datetime.now().isoformat()}


@app.get("/api/scorecard/constraint")
async def get_constraint():
    """
    Get just the current constraint (the ONE thing to fix).
    """
    scorecard = get_scorecard()
    constraint = scorecard.get_constraint()
    
    if constraint:
        return constraint.to_dict()
    else:
        return {"constraint": None, "message": "All metrics on track"}


@app.get("/api/scorecard/markdown")
async def get_scorecard_markdown():
    """
    Get the scorecard as a markdown report (for email/Slack).
    """
    scorecard = get_scorecard()
    return {"markdown": scorecard.to_markdown_report()}


@app.get("/scorecard")
async def scorecard_dashboard():
    """
    Serve the Precision Scorecard HTML dashboard.
    """
    scorecard_html = Path(__file__).parent / "scorecard.html"
    if scorecard_html.exists():
        return FileResponse(str(scorecard_html))
    raise HTTPException(status_code=404, detail="Scorecard dashboard not found")


@app.get("/sales")
async def sales_dashboard():
    """
    Serve the Head of Sales Dashboard.
    
    This is the primary dashboard for Dani Apgar to:
    - Review and approve pending emails
    - See the 4 key conversion metrics
    - View the #1 constraint to fix
    - Monitor recent activity
    """
    hos_html = Path(__file__).parent / "hos_dashboard.html"
    if hos_html.exists():
        return FileResponse(str(hos_html))
    raise HTTPException(status_code=404, detail="Sales dashboard not found")


@app.get("/api/pending-emails")
async def get_pending_emails(auth: bool = Depends(require_auth)):
    """
    Get pending emails awaiting approval.
    
    Returns emails that need HoS review before sending.
    """
    # Load from shadow mode log
    shadow_log = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
    pending = []
    
    if shadow_log.exists():
        for email_file in sorted(shadow_log.glob("*.json"), reverse=True)[:20]:
            try:
                with open(email_file) as f:
                    email_data = json.load(f)
                    if email_data.get("status") == "pending":
                        # Ensure we pass all necessary fields for the frontend
                        email_data["email_id"] = email_data.get("email_id") or email_file.stem
                        email_data["timestamp"] = email_data.get("timestamp", "Unknown")
                        email_data["recipient_data"] = email_data.get("recipient_data", {})
                        pending.append(email_data)
            except Exception:
                pass
    
    return {"pending_emails": pending, "count": len(pending)}


@app.post("/api/emails/{email_id}/approve")
async def approve_email(
    email_id: str,
    approver: str = Query("dashboard_user", description="Who is approving"),
    auth: bool = Depends(require_auth),
    edited_body: Optional[str] = Body(None),
    feedback: Optional[str] = Body(None)
):
    """
    Approve an email for sending, optionally with edits and feedback.
    
    1. If edited_body is provided, updates the email content.
    2. Logs any feedback for agent training.
    3. CHECKS CONFIG for 'actually_send'.
    4. If true, dispatches to GHL API.
    5. Updates status and queues for send.
    """
    shadow_log = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"

    # Ensure the directory exists
    if not shadow_log.exists():
        print(f"ERROR: Shadow email directory not found at {shadow_log}")
        raise HTTPException(
            status_code=500,
            detail=f"Email storage directory not found. Please contact support."
        )

    email_file = None
    email_data = None

    # Find the email file
    for f in shadow_log.glob("*.json"):
        try:
            with open(f) as fp:
                data = json.load(fp)
                if data.get("email_id") == email_id or f.stem == email_id:
                    email_file = f
                    email_data = data
                    break
        except Exception as e:
            print(f"Error reading email file {f}: {e}")
            continue

    if not email_file or not email_data:
        print(f"ERROR: Email {email_id} not found in {shadow_log}")
        raise HTTPException(status_code=404, detail=f"Email {email_id} not found in queue")

    if email_data.get("status") == "approved":
        raise HTTPException(status_code=400, detail="Email already approved")
    
    # Handle Body Edits
    if edited_body:
        email_data["body"] = edited_body
        email_data["was_edited"] = True
    
    # =========================================================================
    # LIVE SENDING LOGIC
    # =========================================================================
    
    # Load config to check if we should send
    project_config = {}
    try:
        config_path = PROJECT_ROOT / "config" / "production.json"
        if config_path.exists():
            with open(config_path) as cp:
                project_config = json.load(cp)
    except Exception as e:
        print(f"Warning: Could not load config: {e}")
    
    actually_send = project_config.get("email_behavior", {}).get("actually_send", False)
    
    formatted_response = "Email approved (simulated)"
    
    if actually_send:
        contact_id = email_data.get("contact_id")
        
        # Guard against synthetic/test data in live mode
        if contact_id and not contact_id.startswith("synthetic_"):
            try:
                # Extract limits from loaded config
                # Default to 150/3000 if not found in config
                # Note: config structure is guardrails -> email_limits
                email_limits = project_config.get("guardrails", {}).get("email_limits", {})

                outreach_config = OutreachConfig(
                    monthly_limit=email_limits.get("monthly_limit", 3000),
                    daily_limit=email_limits.get("daily_limit", 150),
                    min_delay_seconds=email_limits.get("min_delay_seconds", 60)
                )

                # Load GHL credentials from environment
                api_key = os.getenv("GHL_API_KEY") or os.getenv("GHL_PROD_API_KEY")
                location_id = os.getenv("GHL_LOCATION_ID")

                if api_key and location_id:
                    client = GHLOutreachClient(api_key, location_id, config=outreach_config)
                    
                    # Create temp template from the approved content
                    temp_template = EmailTemplate(
                        id=f"approved_{email_id}",
                        name="Approved Dashboard Email",
                        subject=email_data.get("subject", ""),
                        body=email_data.get("body", ""),
                        type=OutreachType.WARM
                    )
                    
                    # Send!
                    result = await client.send_email(contact_id, temp_template)
                    await client.close()
                    
                    if result.get("success"):
                        email_data["sent_via_ghl"] = True
                        email_data["ghl_message_id"] = result.get("message_id")
                        formatted_response = "Email sent via GHL"
                    else:
                        error_msg = result.get("error", "Unknown error")
                        if "limit reached" in str(error_msg):
                            # Rate limit hit - Queue it!
                            email_data["sent_via_ghl"] = False
                            email_data["queued_for_send"] = True
                            email_data["send_error"] = f"Rate Limit Hit: {error_msg}"
                            formatted_response = "Email approved & Queued (Rate Limit Hit)"
                        else:
                            # Other error - Fail hard
                            raise Exception(f"GHL Send Failed: {error_msg}")
                else:
                     print("Warning: GHL Config missing, skipping send.")
                     formatted_response = "Email approved (Config Missing)"
            except Exception as e:
                # If sending fails, we should generally Notify user
                print(f"Critical Error sending email: {e}")
                # For now, we allow approval to proceed but log the error
                email_data["send_error"] = str(e)
                formatted_response = f"Approved but Send Failed: {str(e)}"
        else:
             formatted_response = "Email approved (Synthetic/Test skipped)"

    # =========================================================================
    
    # Update status
    email_data["status"] = "approved"
    email_data["approved_at"] = datetime.now().isoformat()
    email_data["approved_by"] = approver
    email_data["feedback"] = feedback
    
    # Save updated data
    try:
        with open(email_file, "w") as fp:
            json.dump(email_data, fp, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save approval: {e}")
    
    # Log to Audit Log
    audit_log = PROJECT_ROOT / ".hive-mind" / "audit" / "email_approvals.jsonl"
    audit_log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(audit_log, "a") as fp:
            fp.write(json.dumps({
                "email_id": email_id,
                "action": "approved",
                "approver": approver,
                "sent_real": actually_send,
                "timestamp": datetime.now().isoformat(),
                "recipient": email_data.get("to"),
                "subject": email_data.get("subject"),
                "was_edited": bool(edited_body),
                "feedback": feedback
            }) + "\n")
    except Exception:
        pass

    # Log to Training Feedback Log
    if feedback or edited_body:
        training_log = PROJECT_ROOT / ".hive-mind" / "audit" / "agent_feedback.jsonl"
        try:
            with open(training_log, "a") as fp:
                fp.write(json.dumps({
                    "email_id": email_id,
                    "action": "approved_with_changes" if edited_body else "approved_with_feedback",
                    "feedback": feedback,
                    "original_body": email_data.get("body") if edited_body else None,
                    "edited_body": edited_body, 
                    "timestamp": datetime.now().isoformat()
                }) + "\n")
        except Exception:
            pass
    
    return {
        "status": "approved",
        "email_id": email_id,
        "edited": bool(edited_body),
        "message": formatted_response
    }


@app.post("/api/emails/{email_id}/reject")
async def reject_email(
    email_id: str,
    reason: Optional[str] = Query(None, description="Reason for rejection"),
    approver: str = Query("dashboard_user", description="Who is rejecting"),
    auth: bool = Depends(require_auth)
):
    """
    Reject an email.

    Finds the email and marks it as rejected with reason.
    Logs the rejection for agent training.
    """
    shadow_log = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"

    # Ensure the directory exists
    if not shadow_log.exists():
        print(f"ERROR: Shadow email directory not found at {shadow_log}")
        raise HTTPException(
            status_code=500,
            detail=f"Email storage directory not found. Please contact support."
        )

    email_file = None
    email_data = None

    # Find the email file
    for f in shadow_log.glob("*.json"):
        try:
            with open(f) as fp:
                data = json.load(fp)
                if data.get("email_id") == email_id or f.stem == email_id:
                    email_file = f
                    email_data = data
                    break
        except Exception as e:
            print(f"Error reading email file {f}: {e}")
            continue

    if not email_file or not email_data:
        print(f"ERROR: Email {email_id} not found in {shadow_log}")
        raise HTTPException(status_code=404, detail=f"Email {email_id} not found in queue")
    
    if email_data.get("status") == "rejected":
        raise HTTPException(status_code=400, detail="Email already rejected")
    
    # Update status
    email_data["status"] = "rejected"
    email_data["rejected_at"] = datetime.now().isoformat()
    email_data["rejected_by"] = approver
    email_data["rejection_reason"] = reason or "No reason provided"
    
    # Save updated data
    try:
        with open(email_file, "w") as fp:
            json.dump(email_data, fp, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save rejection: {e}")

    # Log to Training Feedback Log
    training_log = PROJECT_ROOT / ".hive-mind" / "audit" / "agent_feedback.jsonl"
    try:
        with open(training_log, "a") as fp:
            fp.write(json.dumps({
                "email_id": email_id,
                "action": "rejected",
                "feedback": reason,
                "original_body": email_data.get("body"),
                "timestamp": datetime.now().isoformat()
            }) + "\n")
    except Exception:
        pass
    
    # Log the rejection
    audit_log = PROJECT_ROOT / ".hive-mind" / "audit" / "email_approvals.jsonl"
    audit_log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(audit_log, "a") as fp:
            fp.write(json.dumps({
                "email_id": email_id,
                "action": "rejected",
                "approver": approver,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
                "recipient": email_data.get("to"),
                "subject": email_data.get("subject")
            }) + "\n")
    except Exception:
        pass  # Non-critical
    
    return {
        "status": "rejected",
        "email_id": email_id,
        "reason": reason,
        "approver": approver,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/queue-status")
async def get_queue_status(auth: bool = Depends(require_auth)):
    """
    Get the status of all email queues for pipeline monitoring.
    
    Returns counts from:
    - shadow_mode_emails (dashboard approvals)
    - gatekeeper_queue (backup/audit)
    - Daily email counts
    """
    shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
    gatekeeper_dir = PROJECT_ROOT / ".hive-mind" / "gatekeeper_queue"
    metrics_file = PROJECT_ROOT / ".hive-mind" / "metrics" / "daily_email_counts.json"
    intent_log = PROJECT_ROOT / ".hive-mind" / "logs" / "intent_queue.jsonl"
    
    # Shadow mode emails breakdown
    shadow_pending = 0
    shadow_approved = 0
    shadow_rejected = 0
    shadow_total = 0
    
    if shadow_dir.exists():
        for f in shadow_dir.glob("*.json"):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    status = data.get("status", "pending")
                    shadow_total += 1
                    if status == "pending":
                        shadow_pending += 1
                    elif status == "approved":
                        shadow_approved += 1
                    elif status == "rejected":
                        shadow_rejected += 1
            except Exception:
                pass
    
    # Gatekeeper queue count
    gatekeeper_count = 0
    if gatekeeper_dir.exists():
        gatekeeper_count = len(list(gatekeeper_dir.glob("*.json")))
    
    # Daily counts
    daily_counts = {"date": "N/A", "queued": 0, "sent": 0}
    if metrics_file.exists():
        try:
            with open(metrics_file) as f:
                daily_counts = json.load(f)
        except Exception:
            pass
    
    # Recent intent queue events (last 10)
    recent_events = []
    if intent_log.exists():
        try:
            with open(intent_log) as f:
                lines = f.readlines()
                for line in lines[-10:]:
                    try:
                        recent_events.append(json.loads(line.strip()))
                    except Exception:
                        pass
        except Exception:
            pass
    
    return {
        "shadow_mode_emails": {
            "total": shadow_total,
            "pending": shadow_pending,
            "approved": shadow_approved,
            "rejected": shadow_rejected
        },
        "gatekeeper_queue": {
            "total": gatekeeper_count
        },
        "daily_limits": {
            "date": daily_counts.get("date", "N/A"),
            "queued_today": daily_counts.get("queued", 0),
            "sent_today": daily_counts.get("sent", 0),
            "limit": 25,
            "remaining": max(0, 25 - daily_counts.get("queued", 0)),
            "last_queued_at": daily_counts.get("last_queued_at")
        },
        "recent_queue_events": recent_events[-5:],
        "pipeline_healthy": shadow_pending > 0 or gatekeeper_count > 0 or daily_counts.get("queued", 0) > 0
    }


@app.get("/api/health/ready")
async def readiness_probe():
    """
    Kubernetes readiness probe endpoint.
    
    Returns 200 if the service is ready to accept traffic.
    """
    try:
        monitor = get_health_monitor()
        status = monitor.get_health_status()
        
        # Check critical dependencies
        integrations = status.get("integrations", {})
        critical_healthy = True
        unhealthy = []
        
        for name, integration in integrations.items():
            if integration.get("critical", False) and integration.get("status") != "healthy":
                critical_healthy = False
                unhealthy.append(name)
        
        if not critical_healthy:
            raise HTTPException(
                status_code=503,
                detail=f"Critical integrations unhealthy: {', '.join(unhealthy)}"
            )
        
        return {
            "status": "ready",
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "health_monitor": "ok",
                "integrations": "ok"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Readiness check failed: {e}")



# =============================================================================
# CALL PREP AGENT ENDPOINTS
# =============================================================================

@app.post("/api/call-prep/{contact_id}")
async def prepare_contact_for_call(
    contact_id: str,
    dry_run: bool = Query(False, description="If true, don't update GHL"),
    auth: bool = Depends(require_auth)
):
    """
    Prepare a contact for an upcoming call by enriching custom fields.
    
    Populates:
    - call_prep_summary: One-paragraph briefing
    - pain_points: Detected pain points
    - warm_connections: Team connections
    - recommended_approach: Conversation angle
    - objection_prep: Likely objections and responses
    """
    try:
        from core.call_prep_agent import get_call_prep_agent
        agent = get_call_prep_agent()
        result = await agent.prepare_contact_for_call(
            contact_id=contact_id,
            update_ghl=not dry_run
        )
        return {
            "status": "success",
            "contact_id": contact_id,
            "contact_name": result.contact_name,
            "company_name": result.company_name,
            "summary": result.summary,
            "pain_points": result.pain_points,
            "warm_connections": result.warm_connections,
            "recommended_approach": result.recommended_approach,
            "objection_prep": result.objection_prep,
            "confidence_score": result.confidence_score,
            "ghl_updated": not dry_run
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Call prep failed: {e}")


@app.post("/api/call-prep/batch")
async def prepare_hot_leads_batch(
    limit: int = Query(10, description="Max leads to prepare"),
    auth: bool = Depends(require_auth)
):
    """
    Prepare all hot leads in queue for upcoming calls.
    """
    try:
        from core.call_prep_agent import get_call_prep_agent
        agent = get_call_prep_agent()
        results = await agent.prepare_hot_leads_batch(limit=limit)
        return {
            "status": "success",
            "prepared_count": len(results),
            "leads": [
                {
                    "contact_id": r.contact_id,
                    "name": r.contact_name,
                    "company": r.company_name,
                    "confidence": r.confidence_score
                }
                for r in results
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch prep failed: {e}")


# =============================================================================
# WEBHOOKS INTEGRATION
# =============================================================================

try:
    from webhooks.rb2b_webhook import router as rb2b_router
    app.include_router(rb2b_router)
    print("✓ RB2B Webhook mounted")
except Exception as e:
    print(f"Warning: RB2B Webhook could not be mounted: {e}")

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  CAIO Swarm Health Dashboard")
    print("=" * 60)
    print("  HTTP:      http://localhost:8080")
    print("  WebSocket: ws://localhost:8080/ws")
    print("  API:       http://localhost:8080/api/health")
    print("  Webhook:   http://localhost:8080/webhooks/rb2b")
    print("=" * 60 + "\n")
    
    uvicorn.run(
        "health_app:app",
        host="0.0.0.0",
        port=8080,
        reload=True
    )
