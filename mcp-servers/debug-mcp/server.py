#!/usr/bin/env python3
"""
Debug MCP Server - Full-Stack Error Correlation
================================================

MCP server providing debugging and troubleshooting tools for the CAIO dashboard:
- Error correlation between frontend and backend
- Unified log aggregation from all sources
- UI capture and visual debugging via Playwright
- Request tracing with correlation IDs
- Circuit breaker status monitoring

Tools:
- get_correlated_errors: Match frontend errors to backend traces
- get_recent_errors: Aggregate errors from all sources
- get_error_context: Get full context for a specific error
- trace_request: Follow a request through the stack
- get_circuit_breaker_status: Current state of all circuit breakers
- search_logs: Full-text search across all log sources
- capture_ui_state: Capture screenshot and DOM state
- get_console_errors: Get browser console errors
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
import logging
import sqlite3
import re

# Add project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

# Import local modules
from correlator import ErrorCorrelator, CorrelatedError
from log_parser import LogParser, LogSource
from ui_capture import UICapture

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debug-mcp")

# Paths
HIVE_MIND_DIR = PROJECT_ROOT / ".hive-mind"
AUDIT_DB_PATH = HIVE_MIND_DIR / "audit.db"
RETRY_QUEUE_PATH = HIVE_MIND_DIR / "retry_queue.jsonl"
LOGS_DIR = HIVE_MIND_DIR / "logs"
FRONTEND_ERRORS_PATH = HIVE_MIND_DIR / "frontend_errors.jsonl"


# ============================================================================
# Debug Client
# ============================================================================

class DebugClient:
    """
    Main debugging client that coordinates error correlation, log parsing,
    and UI capture for full-stack debugging.
    """

    def __init__(self):
        self.correlator = ErrorCorrelator(
            audit_db_path=AUDIT_DB_PATH,
            frontend_errors_path=FRONTEND_ERRORS_PATH
        )
        self.log_parser = LogParser(
            audit_db_path=AUDIT_DB_PATH,
            logs_dir=LOGS_DIR,
            retry_queue_path=RETRY_QUEUE_PATH
        )
        self.ui_capture = UICapture(
            base_url=os.getenv("DASHBOARD_URL", "http://localhost:8080")
        )
        self._initialized = False

    async def initialize(self):
        """Initialize all components."""
        if self._initialized:
            return

        await self.correlator.initialize()
        await self.log_parser.initialize()
        self._initialized = True

    async def close(self):
        """Close all connections."""
        await self.ui_capture.close()

    # ========================================================================
    # Error Correlation
    # ========================================================================

    async def get_correlated_errors(
        self,
        correlation_id: Optional[str] = None,
        time_window_seconds: int = 60,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get errors correlated between frontend and backend.

        Args:
            correlation_id: Specific correlation ID to look up
            time_window_seconds: Time window for matching errors
            limit: Maximum number of results

        Returns:
            List of correlated error objects with frontend and backend context
        """
        await self.initialize()

        if correlation_id:
            return await self.correlator.get_by_correlation_id(correlation_id)

        return await self.correlator.get_recent_correlated(
            time_window_seconds=time_window_seconds,
            limit=limit
        )

    async def get_recent_errors(
        self,
        source: Optional[str] = None,
        agent_name: Optional[str] = None,
        hours: int = 24,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get recent errors aggregated from all sources.

        Args:
            source: Filter by source (audit, frontend, retry_queue, logs)
            agent_name: Filter by agent name
            hours: Look back this many hours
            limit: Maximum number of results

        Returns:
            Aggregated error data with counts and details
        """
        await self.initialize()

        errors = await self.log_parser.get_errors(
            source=source,
            agent_name=agent_name,
            hours=hours,
            limit=limit
        )

        # Group by error type
        by_type = {}
        for error in errors:
            error_type = error.get("error_type", "unknown")
            if error_type not in by_type:
                by_type[error_type] = []
            by_type[error_type].append(error)

        return {
            "total_count": len(errors),
            "time_range_hours": hours,
            "by_type": {k: len(v) for k, v in by_type.items()},
            "errors": errors,
            "sources": list(set(e.get("source", "unknown") for e in errors))
        }

    async def get_error_context(
        self,
        error_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        include_screenshot: bool = False
    ) -> Dict[str, Any]:
        """
        Get full context for a specific error.

        Args:
            error_id: Audit log entry ID
            correlation_id: Correlation ID from request
            include_screenshot: Whether to capture current UI state

        Returns:
            Full error context with stack traces, related logs, and optionally UI state
        """
        await self.initialize()

        context = {
            "error_id": error_id,
            "correlation_id": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Get backend error from audit log
        if error_id:
            backend_error = await self.log_parser.get_audit_entry(error_id)
            if backend_error:
                context["backend"] = backend_error

        # Get correlated frontend errors
        if correlation_id:
            correlated = await self.correlator.get_by_correlation_id(correlation_id)
            if correlated:
                context["frontend"] = correlated.get("frontend_errors", [])
                context["backend"] = context.get("backend") or correlated.get("backend_error")

        # Get related logs (within 30 seconds of the error)
        if context.get("backend"):
            error_time = context["backend"].get("timestamp")
            if error_time:
                context["related_logs"] = await self.log_parser.get_logs_around_time(
                    error_time,
                    window_seconds=30,
                    limit=20
                )

        # Capture current UI state if requested
        if include_screenshot:
            try:
                ui_state = await self.ui_capture.capture_state()
                context["ui_state"] = ui_state
            except Exception as e:
                context["ui_state_error"] = str(e)

        return context

    async def trace_request(
        self,
        correlation_id: str
    ) -> Dict[str, Any]:
        """
        Trace a request through the entire stack using its correlation ID.

        Args:
            correlation_id: The X-Correlation-ID header value

        Returns:
            Complete request trace with timeline
        """
        await self.initialize()

        trace = {
            "correlation_id": correlation_id,
            "timeline": [],
            "errors": [],
            "duration_ms": None
        }

        # Get all events with this correlation ID
        events = await self.log_parser.get_by_correlation_id(correlation_id)

        if not events:
            trace["status"] = "not_found"
            return trace

        # Sort by timestamp
        events.sort(key=lambda x: x.get("timestamp", ""))

        for event in events:
            trace["timeline"].append({
                "timestamp": event.get("timestamp"),
                "source": event.get("source"),
                "action": event.get("action_type") or event.get("type"),
                "status": event.get("status"),
                "agent": event.get("agent_name"),
                "duration_ms": event.get("duration_ms")
            })

            if event.get("status") == "failure" or event.get("error_message"):
                trace["errors"].append({
                    "timestamp": event.get("timestamp"),
                    "error": event.get("error_message") or event.get("error"),
                    "source": event.get("source")
                })

        # Calculate total duration
        if len(events) >= 2:
            try:
                start = datetime.fromisoformat(events[0].get("timestamp", "").replace("Z", "+00:00"))
                end = datetime.fromisoformat(events[-1].get("timestamp", "").replace("Z", "+00:00"))
                trace["duration_ms"] = (end - start).total_seconds() * 1000
            except (ValueError, TypeError):
                pass

        trace["status"] = "traced"
        trace["event_count"] = len(events)

        return trace

    # ========================================================================
    # Circuit Breaker Status
    # ========================================================================

    async def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """
        Get current status of all circuit breakers.

        Returns:
            Status of each circuit breaker with failure counts and state
        """
        await self.initialize()

        # Try to load from circuit breaker state file
        cb_state_file = HIVE_MIND_DIR / "circuit_breakers.json"

        status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "breakers": {}
        }

        if cb_state_file.exists():
            try:
                with open(cb_state_file) as f:
                    status["breakers"] = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load circuit breaker state: {e}")

        # Also check recent failures from audit log to infer circuit state
        recent_failures = await self.log_parser.get_failure_counts(hours=1)

        for agent, count in recent_failures.items():
            if agent not in status["breakers"]:
                status["breakers"][agent] = {
                    "state": "UNKNOWN",
                    "recent_failures": count
                }
            else:
                status["breakers"][agent]["recent_failures"] = count

            # Infer state from failure count (5 failures typically trips the breaker)
            if count >= 5:
                status["breakers"][agent]["inferred_state"] = "LIKELY_OPEN"
            elif count >= 3:
                status["breakers"][agent]["inferred_state"] = "AT_RISK"
            else:
                status["breakers"][agent]["inferred_state"] = "HEALTHY"

        return status

    # ========================================================================
    # Log Search
    # ========================================================================

    async def search_logs(
        self,
        query: str,
        source: Optional[str] = None,
        hours: int = 24,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Full-text search across all log sources.

        Args:
            query: Search query
            source: Optional source filter
            hours: Time window
            limit: Maximum results

        Returns:
            Matching log entries
        """
        await self.initialize()
        return await self.log_parser.search(
            query=query,
            source=source,
            hours=hours,
            limit=limit
        )

    # ========================================================================
    # UI Capture
    # ========================================================================

    async def capture_ui_state(
        self,
        url: Optional[str] = None,
        selector: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Capture current UI state including screenshot and DOM.

        Args:
            url: URL to capture (defaults to dashboard)
            selector: Optional CSS selector to capture specific element

        Returns:
            UI state with screenshot path and DOM snapshot
        """
        return await self.ui_capture.capture_state(url=url, selector=selector)

    async def get_console_errors(
        self,
        url: Optional[str] = None,
        wait_seconds: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get browser console errors from the dashboard.

        Args:
            url: URL to check (defaults to dashboard)
            wait_seconds: How long to wait and collect errors

        Returns:
            List of console errors with timestamps
        """
        return await self.ui_capture.get_console_errors(
            url=url,
            wait_seconds=wait_seconds
        )


# ============================================================================
# Tool Definitions
# ============================================================================

TOOLS = [
    {
        "name": "debug_get_correlated_errors",
        "description": "Get errors correlated between frontend UI and backend services. Matches frontend console errors with backend failures using correlation IDs and timestamps.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "correlation_id": {
                    "type": "string",
                    "description": "Specific correlation ID to look up (from X-Correlation-ID header)"
                },
                "time_window_seconds": {
                    "type": "integer",
                    "description": "Time window for matching errors (default: 60)",
                    "default": 60
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 20)",
                    "default": 20
                }
            }
        }
    },
    {
        "name": "debug_get_recent_errors",
        "description": "Get recent errors aggregated from all sources: audit trail, frontend logs, retry queue, and Python logs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "enum": ["audit", "frontend", "retry_queue", "logs"],
                    "description": "Filter by source"
                },
                "agent_name": {
                    "type": "string",
                    "description": "Filter by agent name (e.g., HUNTER, ENRICHER, ORCHESTRATOR)"
                },
                "hours": {
                    "type": "integer",
                    "description": "Look back this many hours (default: 24)",
                    "default": 24
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 50)",
                    "default": 50
                }
            }
        }
    },
    {
        "name": "debug_get_error_context",
        "description": "Get full context for a specific error including stack traces, related logs, and optionally a UI screenshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "error_id": {
                    "type": "string",
                    "description": "Audit log entry ID"
                },
                "correlation_id": {
                    "type": "string",
                    "description": "Correlation ID from request header"
                },
                "include_screenshot": {
                    "type": "boolean",
                    "description": "Whether to capture current UI state (default: false)",
                    "default": False
                }
            }
        }
    },
    {
        "name": "debug_trace_request",
        "description": "Trace a request through the entire stack (frontend -> API -> database) using its correlation ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "correlation_id": {
                    "type": "string",
                    "description": "The X-Correlation-ID header value"
                }
            },
            "required": ["correlation_id"]
        }
    },
    {
        "name": "debug_get_circuit_breaker_status",
        "description": "Get current status of all circuit breakers including failure counts and state (CLOSED/OPEN/HALF_OPEN).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "debug_search_logs",
        "description": "Full-text search across all log sources (audit trail, frontend errors, retry queue, Python logs).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "source": {
                    "type": "string",
                    "enum": ["audit", "frontend", "retry_queue", "logs"],
                    "description": "Optional source filter"
                },
                "hours": {
                    "type": "integer",
                    "description": "Time window in hours (default: 24)",
                    "default": 24
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default: 50)",
                    "default": 50
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "debug_capture_ui_state",
        "description": "Capture current UI state including screenshot and DOM snapshot. Useful for visual debugging.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to capture (defaults to dashboard)"
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector to capture specific element"
                }
            }
        }
    },
    {
        "name": "debug_get_console_errors",
        "description": "Get browser console errors from the dashboard. Waits and collects JavaScript errors.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to check (defaults to dashboard)"
                },
                "wait_seconds": {
                    "type": "integer",
                    "description": "How long to wait and collect errors (default: 5)",
                    "default": 5
                }
            }
        }
    },
    {
        "name": "debug_get_error_timeline",
        "description": "Get a timeline of errors sorted by time with frontend/backend markers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Look back this many hours (default: 6)",
                    "default": 6
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default: 100)",
                    "default": 100
                }
            }
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

    if not AIOSQLITE_AVAILABLE:
        print("aiosqlite required. Install with: pip install aiosqlite")
        return

    server = Server("debug-mcp")

    try:
        debug_client = DebugClient()
        await debug_client.initialize()
    except Exception as e:
        print(f"Initialization error: {e}")
        debug_client = None

    @server.list_tools()
    async def list_tools():
        return [Tool(**tool) for tool in TOOLS]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if not debug_client:
            return [TextContent(type="text", text=json.dumps({"error": "Debug client not initialized"}))]

        try:
            if name == "debug_get_correlated_errors":
                result = await debug_client.get_correlated_errors(
                    correlation_id=arguments.get("correlation_id"),
                    time_window_seconds=arguments.get("time_window_seconds", 60),
                    limit=arguments.get("limit", 20)
                )

            elif name == "debug_get_recent_errors":
                result = await debug_client.get_recent_errors(
                    source=arguments.get("source"),
                    agent_name=arguments.get("agent_name"),
                    hours=arguments.get("hours", 24),
                    limit=arguments.get("limit", 50)
                )

            elif name == "debug_get_error_context":
                result = await debug_client.get_error_context(
                    error_id=arguments.get("error_id"),
                    correlation_id=arguments.get("correlation_id"),
                    include_screenshot=arguments.get("include_screenshot", False)
                )

            elif name == "debug_trace_request":
                result = await debug_client.trace_request(
                    correlation_id=arguments["correlation_id"]
                )

            elif name == "debug_get_circuit_breaker_status":
                result = await debug_client.get_circuit_breaker_status()

            elif name == "debug_search_logs":
                result = await debug_client.search_logs(
                    query=arguments["query"],
                    source=arguments.get("source"),
                    hours=arguments.get("hours", 24),
                    limit=arguments.get("limit", 50)
                )

            elif name == "debug_capture_ui_state":
                result = await debug_client.capture_ui_state(
                    url=arguments.get("url"),
                    selector=arguments.get("selector")
                )

            elif name == "debug_get_console_errors":
                result = await debug_client.get_console_errors(
                    url=arguments.get("url"),
                    wait_seconds=arguments.get("wait_seconds", 5)
                )

            elif name == "debug_get_error_timeline":
                # Get errors and sort by timestamp
                errors = await debug_client.get_recent_errors(
                    hours=arguments.get("hours", 6),
                    limit=arguments.get("limit", 100)
                )
                # Sort timeline
                timeline = sorted(
                    errors.get("errors", []),
                    key=lambda x: x.get("timestamp", ""),
                    reverse=True
                )
                result = {
                    "timeline": timeline,
                    "total_count": len(timeline)
                }

            else:
                result = {"error": f"Unknown tool: {name}"}

        except Exception as e:
            logger.exception(f"Tool error: {name}")
            result = {"error": str(e)}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    try:
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1])
    finally:
        if debug_client:
            await debug_client.close()


if __name__ == "__main__":
    asyncio.run(main())
