#!/usr/bin/env python3
"""
Orchestrator MCP Server (Alpha Queen)
======================================
Master orchestration server that coordinates all agents and workflows.

Tools:
- orchestrate_workflow: Run a complete workflow
- get_swarm_status: Get status of all agents
- dispatch_task: Send task to specific agent
- coordinate_batch: Coordinate batch processing
- query_hive_mind: Query the hive mind knowledge

Usage:
    python mcp-servers/orchestrator-mcp/server.py
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


class AgentStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class AgentState:
    """State of an individual agent."""
    name: str
    status: str
    current_task: Optional[str]
    last_heartbeat: str
    tasks_completed: int
    tasks_failed: int
    avg_task_duration_ms: float


@dataclass
class WorkflowState:
    """State of a running workflow."""
    workflow_id: str
    workflow_type: str
    status: str
    current_step: int
    total_steps: int
    started_at: str
    completed_at: Optional[str]
    error: Optional[str]
    results: Dict[str, Any] = field(default_factory=dict)


TOOLS = [
    {
        "name": "orchestrator_run_workflow",
        "description": "Run a complete end-to-end workflow (scrape → enrich → segment → campaign).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_type": {
                    "type": "string",
                    "enum": ["lead_harvesting", "campaign_generation", "full_pipeline"],
                    "description": "Type of workflow to run"
                },
                "source_type": {
                    "type": "string",
                    "enum": ["competitor_followers", "event_attendees", "group_members", "post_engagers"],
                    "description": "Lead source type"
                },
                "source_url": {"type": "string", "description": "LinkedIn URL for source"},
                "limit": {"type": "integer", "default": 100, "description": "Max leads to process"}
            },
            "required": ["workflow_type"]
        }
    },
    {
        "name": "orchestrator_swarm_status",
        "description": "Get status of all agents in the swarm.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "orchestrator_dispatch_task",
        "description": "Dispatch a specific task to an agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "enum": ["hunter", "enricher", "segmentor", "crafter", "gatekeeper"],
                    "description": "Target agent"
                },
                "task_type": {"type": "string", "description": "Type of task"},
                "params": {"type": "object", "description": "Task parameters"}
            },
            "required": ["agent", "task_type"]
        }
    },
    {
        "name": "orchestrator_query_hivemind",
        "description": "Query the hive mind for knowledge, learnings, or past decisions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": ["learnings", "reasoning", "performance", "history"],
                    "description": "Type of query"
                },
                "filters": {"type": "object", "description": "Optional filters"}
            },
            "required": ["query_type"]
        }
    },
    {
        "name": "orchestrator_get_metrics",
        "description": "Get system metrics and health status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "time_range": {
                    "type": "string",
                    "enum": ["1h", "24h", "7d", "30d"],
                    "default": "24h"
                }
            }
        }
    }
]


class AlphaQueenOrchestrator:
    """
    Master orchestrator (Alpha Queen) that coordinates all agents.
    
    Responsibilities:
    - Route tasks to appropriate agents
    - Manage workflow state
    - Coordinate between agents
    - Maintain hive mind
    - Self-anneal from outcomes
    """
    
    def __init__(self):
        self.agents: Dict[str, AgentState] = self._initialize_agents()
        self.workflows: Dict[str, WorkflowState] = {}
        self.hive_mind_path = Path(__file__).parent.parent.parent / ".hive-mind"
        
        # Load fail-safe manager
        try:
            from execution.fail_safe_manager import GracefulDegradation, CircuitBreaker
            self.degradation = GracefulDegradation()
            self.circuit_breakers = {
                "hunter": CircuitBreaker("hunter", failure_threshold=3),
                "enricher": CircuitBreaker("enricher", failure_threshold=5),
                "ghl": CircuitBreaker("ghl", failure_threshold=3),
                "instantly": CircuitBreaker("instantly", failure_threshold=3)
            }
        except ImportError:
            self.degradation = None
            self.circuit_breakers = {}
        
        # Load RL engine
        try:
            from execution.rl_engine import RLEngine
            self.rl_engine = RLEngine()
        except ImportError:
            self.rl_engine = None
    
    def _initialize_agents(self) -> Dict[str, AgentState]:
        """Initialize agent states."""
        agents = {}
        for name in ["hunter", "enricher", "segmentor", "crafter", "gatekeeper"]:
            agents[name] = AgentState(
                name=name,
                status=AgentStatus.IDLE.value,
                current_task=None,
                last_heartbeat=datetime.utcnow().isoformat(),
                tasks_completed=0,
                tasks_failed=0,
                avg_task_duration_ms=0.0
            )
        return agents
    
    async def run_workflow(self, workflow_type: str, **kwargs) -> Dict[str, Any]:
        """Run a complete workflow."""
        
        workflow_id = f"wf_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        workflow = WorkflowState(
            workflow_id=workflow_id,
            workflow_type=workflow_type,
            status=WorkflowStatus.RUNNING.value,
            current_step=0,
            total_steps=self._get_workflow_steps(workflow_type),
            started_at=datetime.utcnow().isoformat(),
            completed_at=None,
            error=None
        )
        
        self.workflows[workflow_id] = workflow
        
        try:
            if workflow_type == "lead_harvesting":
                result = await self._run_lead_harvesting(workflow, **kwargs)
            elif workflow_type == "campaign_generation":
                result = await self._run_campaign_generation(workflow, **kwargs)
            elif workflow_type == "full_pipeline":
                result = await self._run_full_pipeline(workflow, **kwargs)
            else:
                raise ValueError(f"Unknown workflow: {workflow_type}")
            
            workflow.status = WorkflowStatus.COMPLETED.value
            workflow.completed_at = datetime.utcnow().isoformat()
            workflow.results = result
            
            return {"success": True, "workflow_id": workflow_id, "results": result}
            
        except Exception as e:
            workflow.status = WorkflowStatus.FAILED.value
            workflow.error = str(e)
            return {"success": False, "workflow_id": workflow_id, "error": str(e)}
    
    def _get_workflow_steps(self, workflow_type: str) -> int:
        """Get number of steps in workflow."""
        steps = {
            "lead_harvesting": 3,  # scrape → enrich → segment
            "campaign_generation": 2,  # create → queue
            "full_pipeline": 5  # scrape → enrich → segment → campaign → queue
        }
        return steps.get(workflow_type, 1)
    
    async def _run_lead_harvesting(self, workflow: WorkflowState, **kwargs) -> Dict[str, Any]:
        """Run lead harvesting workflow."""
        results = {}
        
        # Step 1: Scrape
        workflow.current_step = 1
        self.agents["hunter"].status = AgentStatus.BUSY.value
        self.agents["hunter"].current_task = "scraping"
        
        # Would call hunter agent here
        results["scrape"] = {"status": "completed", "leads_scraped": 0}
        
        self.agents["hunter"].status = AgentStatus.IDLE.value
        self.agents["hunter"].current_task = None
        self.agents["hunter"].tasks_completed += 1
        
        # Step 2: Enrich
        workflow.current_step = 2
        self.agents["enricher"].status = AgentStatus.BUSY.value
        self.agents["enricher"].current_task = "enriching"
        
        results["enrich"] = {"status": "completed", "leads_enriched": 0}
        
        self.agents["enricher"].status = AgentStatus.IDLE.value
        self.agents["enricher"].current_task = None
        self.agents["enricher"].tasks_completed += 1
        
        # Step 3: Segment
        workflow.current_step = 3
        self.agents["segmentor"].status = AgentStatus.BUSY.value
        self.agents["segmentor"].current_task = "segmenting"
        
        results["segment"] = {"status": "completed", "leads_segmented": 0}
        
        self.agents["segmentor"].status = AgentStatus.IDLE.value
        self.agents["segmentor"].current_task = None
        self.agents["segmentor"].tasks_completed += 1
        
        return results
    
    async def _run_campaign_generation(self, workflow: WorkflowState, **kwargs) -> Dict[str, Any]:
        """Run campaign generation workflow."""
        results = {}
        
        # Step 1: Generate campaigns
        workflow.current_step = 1
        self.agents["crafter"].status = AgentStatus.BUSY.value
        self.agents["crafter"].current_task = "generating"
        
        results["campaigns"] = {"status": "completed", "campaigns_created": 0}
        
        self.agents["crafter"].status = AgentStatus.IDLE.value
        self.agents["crafter"].current_task = None
        self.agents["crafter"].tasks_completed += 1
        
        # Step 2: Queue for review
        workflow.current_step = 2
        self.agents["gatekeeper"].status = AgentStatus.BUSY.value
        self.agents["gatekeeper"].current_task = "queuing"
        
        results["queue"] = {"status": "completed", "pending_review": 0}
        
        self.agents["gatekeeper"].status = AgentStatus.IDLE.value
        self.agents["gatekeeper"].current_task = None
        self.agents["gatekeeper"].tasks_completed += 1
        
        return results
    
    async def _run_full_pipeline(self, workflow: WorkflowState, **kwargs) -> Dict[str, Any]:
        """Run full end-to-end pipeline."""
        harvest_result = await self._run_lead_harvesting(workflow, **kwargs)
        campaign_result = await self._run_campaign_generation(workflow, **kwargs)
        
        return {**harvest_result, **campaign_result}
    
    def get_swarm_status(self) -> Dict[str, Any]:
        """Get status of all agents."""
        
        agent_statuses = {name: asdict(agent) for name, agent in self.agents.items()}
        
        # Count by status
        status_counts = {}
        for agent in self.agents.values():
            status_counts[agent.status] = status_counts.get(agent.status, 0) + 1
        
        # Get degradation level
        degradation_level = 0
        if self.degradation:
            degradation_level = self.degradation.current_level
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "agents": agent_statuses,
            "status_summary": status_counts,
            "active_workflows": len([w for w in self.workflows.values() if w.status == "running"]),
            "degradation_level": degradation_level,
            "healthy": all(a.status != "error" for a in self.agents.values())
        }
    
    async def dispatch_task(self, agent: str, task_type: str, params: Dict = None) -> Dict[str, Any]:
        """Dispatch a task to a specific agent."""
        
        if agent not in self.agents:
            return {"success": False, "error": f"Unknown agent: {agent}"}
        
        agent_state = self.agents[agent]
        
        if agent_state.status == AgentStatus.BUSY.value:
            return {"success": False, "error": f"Agent {agent} is busy"}
        
        if agent_state.status == AgentStatus.ERROR.value:
            return {"success": False, "error": f"Agent {agent} is in error state"}
        
        # Mark agent as busy
        agent_state.status = AgentStatus.BUSY.value
        agent_state.current_task = task_type
        
        # Would dispatch actual task here
        
        return {
            "success": True,
            "agent": agent,
            "task_type": task_type,
            "dispatched_at": datetime.utcnow().isoformat()
        }
    
    def query_hivemind(self, query_type: str, filters: Dict = None) -> Dict[str, Any]:
        """Query the hive mind."""
        
        results = {}
        
        if query_type == "learnings":
            learnings_path = self.hive_mind_path / "learnings.json"
            if learnings_path.exists():
                with open(learnings_path) as f:
                    results = json.load(f)
        
        elif query_type == "reasoning":
            reasoning_path = self.hive_mind_path / "reasoning_bank.json"
            if reasoning_path.exists():
                with open(reasoning_path) as f:
                    results = json.load(f)
        
        elif query_type == "performance":
            # Aggregate performance from RL engine
            if self.rl_engine:
                results = self.rl_engine.get_policy_summary()
            else:
                results = {"error": "RL engine not available"}
        
        elif query_type == "history":
            # Get workflow history
            results = {
                "workflows": [asdict(w) for w in list(self.workflows.values())[-10:]]
            }
        
        return {
            "query_type": query_type,
            "filters": filters,
            "results": results,
            "queried_at": datetime.utcnow().isoformat()
        }
    
    def get_metrics(self, time_range: str = "24h") -> Dict[str, Any]:
        """Get system metrics."""
        
        # Calculate metrics from workflow history
        workflows = list(self.workflows.values())
        
        completed = [w for w in workflows if w.status == "completed"]
        failed = [w for w in workflows if w.status == "failed"]
        
        total_tasks = sum(a.tasks_completed + a.tasks_failed for a in self.agents.values())
        failed_tasks = sum(a.tasks_failed for a in self.agents.values())
        
        return {
            "time_range": time_range,
            "workflows": {
                "total": len(workflows),
                "completed": len(completed),
                "failed": len(failed),
                "success_rate": len(completed) / max(1, len(workflows))
            },
            "tasks": {
                "total": total_tasks,
                "failed": failed_tasks,
                "success_rate": (total_tasks - failed_tasks) / max(1, total_tasks)
            },
            "agents": {
                name: {
                    "tasks_completed": a.tasks_completed,
                    "tasks_failed": a.tasks_failed,
                    "avg_duration_ms": a.avg_task_duration_ms
                }
                for name, a in self.agents.items()
            },
            "health": {
                "degradation_level": self.degradation.current_level if self.degradation else 0,
                "circuit_breakers": {
                    name: cb.state.value if hasattr(cb, 'state') else "unknown"
                    for name, cb in self.circuit_breakers.items()
                }
            }
        }


async def main():
    if not MCP_AVAILABLE:
        print("MCP package not available")
        return
    
    server = Server("orchestrator-mcp")
    orchestrator = AlphaQueenOrchestrator()
    
    @server.list_tools()
    async def list_tools():
        return [Tool(**tool) for tool in TOOLS]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        try:
            if name == "orchestrator_run_workflow":
                result = await orchestrator.run_workflow(
                    arguments["workflow_type"],
                    source_type=arguments.get("source_type"),
                    source_url=arguments.get("source_url"),
                    limit=arguments.get("limit", 100)
                )
            elif name == "orchestrator_swarm_status":
                result = orchestrator.get_swarm_status()
            elif name == "orchestrator_dispatch_task":
                result = await orchestrator.dispatch_task(
                    arguments["agent"],
                    arguments["task_type"],
                    arguments.get("params", {})
                )
            elif name == "orchestrator_query_hivemind":
                result = orchestrator.query_hivemind(
                    arguments["query_type"],
                    arguments.get("filters")
                )
            elif name == "orchestrator_get_metrics":
                result = orchestrator.get_metrics(
                    arguments.get("time_range", "24h")
                )
            else:
                result = {"error": f"Unknown tool: {name}"}
                
        except Exception as e:
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1])


if __name__ == "__main__":
    asyncio.run(main())
