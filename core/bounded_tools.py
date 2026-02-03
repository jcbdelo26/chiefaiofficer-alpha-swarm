#!/usr/bin/env python3
"""
Bounded Tools - Fixed Tool Boundaries
======================================
Implements Vercel's Lead Agent pattern of bounded tool execution
with iteration limits to prevent runaway loops.

Key Concepts:
- Each agent has a defined set of tools (not general purpose)
- MAX_TOOL_CALLS limit prevents infinite loops
- Tool execution is monitored and rate-limited
- Automatic stop when iteration limit reached

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    BOUNDED TOOLS ENGINE                      │
    │                                                              │
    │  Agent (e.g., HUNTER)                                       │
    │       │                                                      │
    │       ▼                                                      │
    │  ┌─────────────────────────────────────────────────────┐    │
    │  │                   TOOL REGISTRY                       │    │
    │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │    │
    │  │  │ search  │ │ fetch   │ │ crm     │ │ analyze │    │    │
    │  │  │ _rb2b   │ │ _url    │ │ _lookup │ │ _tech   │    │    │
    │  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘    │    │
    │  └─────────────────────────────────────────────────────┘    │
    │                          │                                   │
    │                          ▼                                   │
    │  ┌─────────────────────────────────────────────────────┐    │
    │  │              EXECUTION MONITOR                        │    │
    │  │  • Iteration count: 5/20                              │    │
    │  │  • Rate limit: 10/min                                 │    │
    │  │  • Stop condition: stepCountIs(20)                    │    │
    │  └─────────────────────────────────────────────────────┘    │
    └─────────────────────────────────────────────────────────────┘

Based on Vercel's Lead Agent `stopWhen: [stepCountIs(20)]` pattern.
"""

import json
import logging
import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, TypeVar, Set, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from abc import ABC, abstractmethod
from functools import wraps

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bounded_tools")

T = TypeVar('T')


class ToolCategory(Enum):
    """Categories of tools by risk and purpose."""
    SEARCH = "search"       # Web/database search
    FETCH = "fetch"         # Content retrieval
    CRM = "crm"             # CRM operations
    ANALYZE = "analyze"     # Data analysis
    ENRICH = "enrich"       # Data enrichment
    NOTIFY = "notify"       # Notifications
    EXECUTE = "execute"     # Actions (email, etc.)


class StopReason(Enum):
    """Reasons for stopping tool execution."""
    MAX_ITERATIONS = "max_iterations"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    COMPLETE = "complete"
    ERROR = "error"
    USER_STOP = "user_stop"


@dataclass
class ToolDefinition:
    """Definition of a bounded tool."""
    name: str
    category: ToolCategory
    description: str
    handler: Callable
    max_calls_per_session: int = 10
    cooldown_seconds: float = 0.0
    requires_grounding: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "max_calls_per_session": self.max_calls_per_session,
            "cooldown_seconds": self.cooldown_seconds,
            "requires_grounding": self.requires_grounding
        }


@dataclass
class ToolCall:
    """Record of a single tool invocation."""
    tool_name: str
    sequence: int
    input_data: Dict[str, Any]
    output_data: Optional[Any] = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    duration_ms: float = 0
    success: bool = False
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionStats:
    """Statistics for a tool execution session."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_duration_ms: float = 0
    tools_used: Set[str] = field(default_factory=set)
    stop_reason: Optional[StopReason] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "total_duration_ms": self.total_duration_ms,
            "tools_used": list(self.tools_used),
            "stop_reason": self.stop_reason.value if self.stop_reason else None
        }


class StopCondition(ABC):
    """Abstract base for stop conditions."""
    
    @abstractmethod
    def should_stop(self, stats: ExecutionStats, call_history: List[ToolCall]) -> bool:
        """Check if execution should stop."""
        pass
    
    @abstractmethod
    def get_reason(self) -> str:
        """Get description of the stop condition."""
        pass


class StepCountIs(StopCondition):
    """Stop after N tool calls (Vercel's stepCountIs pattern)."""
    
    def __init__(self, max_steps: int):
        self.max_steps = max_steps
    
    def should_stop(self, stats: ExecutionStats, call_history: List[ToolCall]) -> bool:
        return stats.total_calls >= self.max_steps
    
    def get_reason(self) -> str:
        return f"Reached maximum step count ({self.max_steps})"


class DurationExceeds(StopCondition):
    """Stop after total duration exceeds threshold."""
    
    def __init__(self, max_duration_seconds: float):
        self.max_duration_seconds = max_duration_seconds
    
    def should_stop(self, stats: ExecutionStats, call_history: List[ToolCall]) -> bool:
        return stats.total_duration_ms >= (self.max_duration_seconds * 1000)
    
    def get_reason(self) -> str:
        return f"Exceeded maximum duration ({self.max_duration_seconds}s)"


class ConsecutiveFailures(StopCondition):
    """Stop after N consecutive failures."""
    
    def __init__(self, max_failures: int = 3):
        self.max_failures = max_failures
    
    def should_stop(self, stats: ExecutionStats, call_history: List[ToolCall]) -> bool:
        if len(call_history) < self.max_failures:
            return False
        
        recent = call_history[-self.max_failures:]
        return all(not call.success for call in recent)
    
    def get_reason(self) -> str:
        return f"Exceeded consecutive failures ({self.max_failures})"


class BoundedToolRegistry:
    """
    Registry of bounded tools for an agent.
    
    Each agent has a specific set of tools with:
    - Defined boundaries (max calls, rate limits)
    - Stop conditions (stepCountIs pattern)
    - Execution monitoring
    """
    
    def __init__(
        self,
        agent_name: str,
        max_tool_calls: int = 20,
        stop_conditions: Optional[List[StopCondition]] = None
    ):
        self.agent_name = agent_name
        self.max_tool_calls = max_tool_calls
        self.stop_conditions = stop_conditions or [
            StepCountIs(max_tool_calls),
            ConsecutiveFailures(3),
            DurationExceeds(300)  # 5 minutes
        ]
        
        self._tools: Dict[str, ToolDefinition] = {}
        self._call_history: List[ToolCall] = []
        self._stats = ExecutionStats()
        self._tool_call_counts: Dict[str, int] = {}
        self._last_call_times: Dict[str, float] = {}
    
    def register_tool(
        self,
        name: str,
        handler: Callable,
        category: ToolCategory = ToolCategory.SEARCH,
        description: str = "",
        max_calls_per_session: int = 10,
        cooldown_seconds: float = 0.0,
        requires_grounding: bool = False
    ):
        """Register a tool with boundaries."""
        self._tools[name] = ToolDefinition(
            name=name,
            category=category,
            description=description,
            handler=handler,
            max_calls_per_session=max_calls_per_session,
            cooldown_seconds=cooldown_seconds,
            requires_grounding=requires_grounding
        )
        self._tool_call_counts[name] = 0
        logger.debug(f"Registered tool '{name}' for agent {self.agent_name}")
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tools that haven't hit their limits."""
        available = []
        for name, tool in self._tools.items():
            if self._tool_call_counts.get(name, 0) < tool.max_calls_per_session:
                available.append(name)
        return available
    
    async def call_tool(
        self,
        name: str,
        input_data: Dict[str, Any],
        grounding_evidence: Optional[Dict[str, Any]] = None
    ) -> Tuple[Any, ToolCall]:
        """
        Call a tool with boundary enforcement.
        
        Args:
            name: Tool name
            input_data: Data to pass to the tool
            grounding_evidence: Required for tools that need grounding
            
        Returns:
            Tuple of (result, ToolCall record)
        """
        # Check if tool exists
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not registered for agent {self.agent_name}")
        
        tool = self._tools[name]
        
        # Check stop conditions
        for condition in self.stop_conditions:
            if condition.should_stop(self._stats, self._call_history):
                self._stats.stop_reason = StopReason.MAX_ITERATIONS
                raise RuntimeError(f"Execution stopped: {condition.get_reason()}")
        
        # Check tool-specific limits
        if self._tool_call_counts.get(name, 0) >= tool.max_calls_per_session:
            raise RuntimeError(f"Tool '{name}' has reached session limit ({tool.max_calls_per_session})")
        
        # Check grounding requirement
        if tool.requires_grounding and not grounding_evidence:
            raise ValueError(f"Tool '{name}' requires grounding evidence")
        
        # Enforce cooldown
        last_call = self._last_call_times.get(name, 0)
        elapsed = time.time() - last_call
        if elapsed < tool.cooldown_seconds:
            await asyncio.sleep(tool.cooldown_seconds - elapsed)
        
        # Create call record
        call = ToolCall(
            tool_name=name,
            sequence=len(self._call_history) + 1,
            input_data=input_data
        )
        
        start_time = time.time()
        
        try:
            # Execute tool
            if asyncio.iscoroutinefunction(tool.handler):
                result = await tool.handler(input_data)
            else:
                result = tool.handler(input_data)
            
            # Record success
            call.success = True
            call.output_data = result
            self._stats.successful_calls += 1
            
        except Exception as e:
            call.success = False
            call.error = str(e)
            self._stats.failed_calls += 1
            result = None
            logger.error(f"Tool '{name}' failed: {e}")
        
        # Update records
        end_time = time.time()
        call.duration_ms = (end_time - start_time) * 1000
        call.completed_at = datetime.now(timezone.utc).isoformat()
        
        self._call_history.append(call)
        self._stats.total_calls += 1
        self._stats.total_duration_ms += call.duration_ms
        self._stats.tools_used.add(name)
        self._tool_call_counts[name] = self._tool_call_counts.get(name, 0) + 1
        self._last_call_times[name] = end_time
        
        logger.info(
            f"Tool '{name}' called ({self._stats.total_calls}/{self.max_tool_calls}): "
            f"{'success' if call.success else 'failed'}"
        )
        
        return result, call
    
    def should_continue(self) -> bool:
        """Check if the agent should continue making tool calls."""
        for condition in self.stop_conditions:
            if condition.should_stop(self._stats, self._call_history):
                return False
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        return {
            "agent": self.agent_name,
            "max_tool_calls": self.max_tool_calls,
            "stats": self._stats.to_dict(),
            "tool_usage": dict(self._tool_call_counts),
            "available_tools": self.get_available_tools(),
            "call_history_length": len(self._call_history)
        }
    
    def reset_session(self):
        """Reset session counters for a new research cycle."""
        self._call_history = []
        self._stats = ExecutionStats()
        self._tool_call_counts = {name: 0 for name in self._tools}
        self._last_call_times = {}
        logger.info(f"Reset tool session for agent {self.agent_name}")


# =============================================================================
# HUNTER AGENT WITH BOUNDED TOOLS
# =============================================================================

class BoundedHunterAgent:
    """
    HUNTER agent with bounded tool execution.
    
    Implements Vercel's pattern of:
    - 5 defined tools (search, fetch, crm, analyze, enrich)
    - MAX_TOOL_CALLS = 20 (prevents runaway loops)
    - Automatic stop when limit reached
    """
    
    MAX_TOOL_CALLS = 20
    
    def __init__(self):
        self.registry = BoundedToolRegistry(
            agent_name="HUNTER",
            max_tool_calls=self.MAX_TOOL_CALLS,
            stop_conditions=[
                StepCountIs(self.MAX_TOOL_CALLS),
                ConsecutiveFailures(3),
                DurationExceeds(600)  # 10 min for scraping
            ]
        )
        
        self._register_tools()
        self._gathered_data: List[Dict[str, Any]] = []
    
    def _register_tools(self):
        """Register HUNTER's bounded tools."""
        
        # Tool 1: Search RB2B for website visitors
        self.registry.register_tool(
            name="search_rb2b",
            handler=self._search_rb2b,
            category=ToolCategory.SEARCH,
            description="Search RB2B for website visitors matching criteria",
            max_calls_per_session=5,
            cooldown_seconds=2.0
        )
        
        # Tool 2: Fetch LinkedIn profile
        self.registry.register_tool(
            name="fetch_linkedin",
            handler=self._fetch_linkedin,
            category=ToolCategory.FETCH,
            description="Fetch LinkedIn profile data",
            max_calls_per_session=10,
            cooldown_seconds=1.0
        )
        
        # Tool 3: Check CRM for existing contact
        self.registry.register_tool(
            name="check_crm",
            handler=self._check_crm,
            category=ToolCategory.CRM,
            description="Check GHL CRM for existing contact",
            max_calls_per_session=15,
            cooldown_seconds=0.5
        )
        
        # Tool 4: Analyze tech stack
        self.registry.register_tool(
            name="analyze_tech_stack",
            handler=self._analyze_tech_stack,
            category=ToolCategory.ANALYZE,
            description="Analyze company technology stack",
            max_calls_per_session=10,
            cooldown_seconds=1.0
        )
        
        # Tool 5: Basic enrichment
        self.registry.register_tool(
            name="basic_enrich",
            handler=self._basic_enrich,
            category=ToolCategory.ENRICH,
            description="Basic lead enrichment (email, phone)",
            max_calls_per_session=10,
            cooldown_seconds=0.5
        )
    
    async def research(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Research a lead using bounded tools.
        
        This is the main entry point for HUNTER research.
        Automatically stops when MAX_TOOL_CALLS is reached.
        """
        self.registry.reset_session()
        self._gathered_data = []
        
        logger.info(f"Starting bounded research for lead: {lead.get('name', 'unknown')}")
        
        # Research loop with automatic stopping
        iteration = 0
        while self.registry.should_continue():
            iteration += 1
            
            # Decide next action based on gathered data
            next_action = self._decide_next_action(lead)
            
            if next_action == "complete":
                self.registry._stats.stop_reason = StopReason.COMPLETE
                break
            
            try:
                tool_name, params = next_action
                result, call = await self.registry.call_tool(tool_name, params)
                
                if result:
                    self._gathered_data.append({
                        "tool": tool_name,
                        "data": result
                    })
                    
            except RuntimeError as e:
                # Stop condition triggered
                logger.info(f"Research stopped: {e}")
                break
        
        # Compile research report
        return self._compile_report(lead)
    
    def _decide_next_action(self, lead: Dict[str, Any]) -> Any:
        """Decide the next tool to call based on current state."""
        gathered_tools = {d["tool"] for d in self._gathered_data}
        
        # Priority order of tools
        if "check_crm" not in gathered_tools:
            return ("check_crm", {"email": lead.get("email"), "name": lead.get("name")})
        
        if "fetch_linkedin" not in gathered_tools and lead.get("linkedin_url"):
            return ("fetch_linkedin", {"url": lead.get("linkedin_url")})
        
        if "analyze_tech_stack" not in gathered_tools and lead.get("company", {}).get("domain"):
            return ("analyze_tech_stack", {"domain": lead["company"]["domain"]})
        
        if "basic_enrich" not in gathered_tools and not lead.get("email"):
            return ("basic_enrich", {"name": lead.get("name"), "company": lead.get("company", {}).get("name")})
        
        if "search_rb2b" not in gathered_tools and lead.get("company", {}).get("domain"):
            return ("search_rb2b", {"domain": lead["company"]["domain"]})
        
        # All tools used or not applicable
        return "complete"
    
    def _compile_report(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Compile gathered data into a research report."""
        stats = self.registry.get_stats()
        
        report = {
            "lead_id": lead.get("lead_id", lead.get("linkedin_url", "unknown")),
            "lead_name": lead.get("name", "unknown"),
            "research_complete": stats["stats"]["stop_reason"] == "complete",
            "tools_used": list(stats["stats"]["tools_used"]),
            "total_tool_calls": stats["stats"]["total_calls"],
            "max_tool_calls": self.MAX_TOOL_CALLS,
            "gathered_data": self._gathered_data,
            "stats": stats["stats"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Merge data from different tools
        merged_data = {}
        for item in self._gathered_data:
            if isinstance(item.get("data"), dict):
                merged_data.update(item["data"])
        
        report["merged_data"] = merged_data
        
        return report
    
    # === TOOL HANDLERS ===
    
    async def _search_rb2b(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search RB2B for visitors (mock implementation)."""
        await asyncio.sleep(0.1)  # Simulate API call
        return {
            "source": "rb2b",
            "visitors_found": 3,
            "domain": params.get("domain")
        }
    
    async def _fetch_linkedin(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch LinkedIn profile (mock implementation)."""
        await asyncio.sleep(0.1)
        return {
            "source": "linkedin",
            "profile_url": params.get("url"),
            "connections": 500,
            "recent_activity": True
        }
    
    async def _check_crm(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check CRM for existing contact (mock implementation)."""
        await asyncio.sleep(0.05)
        return {
            "source": "ghl_crm",
            "exists": False,
            "email_checked": params.get("email")
        }
    
    async def _analyze_tech_stack(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze tech stack (mock implementation)."""
        await asyncio.sleep(0.1)
        return {
            "source": "builtwith",
            "domain": params.get("domain"),
            "technologies": ["Salesforce", "HubSpot", "Intercom"]
        }
    
    async def _basic_enrich(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Basic enrichment (mock implementation)."""
        await asyncio.sleep(0.05)
        return {
            "source": "enrichment",
            "email_found": True,
            "phone_found": False
        }


# =============================================================================
# DECORATOR FOR BOUNDED EXECUTION
# =============================================================================

def bounded_execution(max_calls: int = 20, timeout_seconds: int = 300):
    """
    Decorator to add bounded execution to any async function.
    
    Usage:
        @bounded_execution(max_calls=20)
        async def research_lead(self, lead):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            call_count = 0
            start_time = time.time()
            
            # Patch tool calls to count them
            original_call = getattr(self, 'call_tool', None)
            
            async def counted_call(*a, **kw):
                nonlocal call_count
                call_count += 1
                
                if call_count > max_calls:
                    raise RuntimeError(f"Exceeded maximum tool calls ({max_calls})")
                
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    raise RuntimeError(f"Exceeded timeout ({timeout_seconds}s)")
                
                if original_call:
                    return await original_call(*a, **kw)
            
            if original_call:
                setattr(self, 'call_tool', counted_call)
            
            try:
                return await func(self, *args, **kwargs)
            finally:
                if original_call:
                    setattr(self, 'call_tool', original_call)
        
        return wrapper
    return decorator


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_hunter_instance: Optional[BoundedHunterAgent] = None


def get_bounded_hunter() -> BoundedHunterAgent:
    """Get singleton instance of BoundedHunterAgent."""
    global _hunter_instance
    if _hunter_instance is None:
        _hunter_instance = BoundedHunterAgent()
    return _hunter_instance


# =============================================================================
# DEMO
# =============================================================================

async def demo():
    """Demonstrate bounded tool execution."""
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    console.print("\n[bold blue]Bounded Tools Demo[/bold blue]\n")
    
    hunter = BoundedHunterAgent()
    
    # Test lead
    lead = {
        "lead_id": "test_001",
        "name": "John Smith",
        "title": "VP Sales",
        "email": None,  # Missing - needs enrichment
        "linkedin_url": "https://linkedin.com/in/johnsmith",
        "company": {
            "name": "Acme Corp",
            "domain": "acme.com"
        }
    }
    
    console.print(f"[yellow]Researching lead: {lead['name']}[/yellow]\n")
    console.print(f"MAX_TOOL_CALLS: {hunter.MAX_TOOL_CALLS}")
    
    # Execute bounded research
    report = await hunter.research(lead)
    
    # Display results
    table = Table(title="Research Report")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Lead", report["lead_name"])
    table.add_row("Complete", str(report["research_complete"]))
    table.add_row("Tools Used", ", ".join(report["tools_used"]))
    table.add_row("Total Calls", f"{report['total_tool_calls']}/{report['max_tool_calls']}")
    table.add_row("Stop Reason", report["stats"].get("stop_reason", "N/A"))
    
    console.print(table)
    
    # Show merged data
    console.print("\n[yellow]Merged Research Data:[/yellow]")
    for key, value in report.get("merged_data", {}).items():
        console.print(f"  {key}: {value}")
    
    # Show tool-specific stats
    stats = hunter.registry.get_stats()
    console.print("\n[yellow]Tool Usage:[/yellow]")
    for tool, count in stats["tool_usage"].items():
        console.print(f"  {tool}: {count} calls")
    
    console.print("\n[green]Demo complete![/green]")


if __name__ == "__main__":
    asyncio.run(demo())
