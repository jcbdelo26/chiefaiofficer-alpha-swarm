#!/usr/bin/env python3
"""
Learning MCP Server (Self-Annealing Interface)
===============================================
MCP interface for the reinforcement learning engine and self-annealing system.

Provides tools for:
- Recording outcomes and updating Q-values
- Querying learned policies
- Getting workflow insights and failure patterns
- Suggesting refinements based on historical data

Tools:
- record_outcome: Record an action outcome and update Q-table
- get_q_value: Get Q-value for state-action pair
- update_q_table: Directly update Q-table entry
- get_best_action: Get optimal action for a state
- get_workflow_insights: Analyze workflow performance
- get_failure_patterns: Identify common failure patterns
- suggest_refinements: Get AI-suggested improvements

Usage:
    python mcp-servers/learning-mcp/server.py [--dry-run]
"""

import os
import sys
import json
import asyncio
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict, field
from collections import defaultdict
import logging

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

try:
    from execution.rl_engine import RLEngine, RLState
    RL_ENGINE_AVAILABLE = True
except ImportError:
    RL_ENGINE_AVAILABLE = False
    RLEngine = None
    RLState = None

try:
    from core.event_log import log_event, EventType
    EVENT_LOG_AVAILABLE = True
except ImportError:
    EVENT_LOG_AVAILABLE = False
    def log_event(*args, **kwargs):
        pass
    class EventType:
        SYSTEM_ERROR = "system_error"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("learning-mcp")

DRY_RUN = False


@dataclass
class FailurePattern:
    """Represents a detected failure pattern."""
    pattern_id: str
    pattern_type: str
    frequency: int
    last_seen: str
    context: Dict[str, Any]
    suggested_fix: Optional[str]


@dataclass
class WorkflowInsight:
    """Insight derived from workflow analysis."""
    insight_type: str
    metric: str
    value: float
    trend: str  # improving, declining, stable
    recommendation: str


class LearningMCPServer:
    """
    Self-annealing MCP server integrating with RL engine.
    
    Features:
    - Q-learning integration for decision optimization
    - Failure pattern detection
    - Workflow performance analysis
    - Automated refinement suggestions
    """
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.storage_path = Path(__file__).parent.parent.parent / ".hive-mind" / "learning"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        if RL_ENGINE_AVAILABLE:
            self.rl_engine = RLEngine()
        else:
            self.rl_engine = None
            logger.warning("RL engine not available. Some features disabled.")
        
        self.outcome_history: List[Dict[str, Any]] = []
        self.failure_patterns: Dict[str, FailurePattern] = {}
        
        self._load_history()
    
    def _load_history(self):
        """Load outcome history from disk."""
        history_file = self.storage_path / "outcome_history.json"
        if history_file.exists():
            try:
                with open(history_file) as f:
                    self.outcome_history = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load history: {e}")
    
    def _save_history(self):
        """Persist outcome history."""
        if self.dry_run:
            return
        
        history_file = self.storage_path / "outcome_history.json"
        recent = self.outcome_history[-10000:]
        with open(history_file, "w") as f:
            json.dump(recent, f)
    
    def _create_state(self, state_data: Dict[str, Any]) -> Optional[Any]:
        """Create RLState from dictionary."""
        if not RL_ENGINE_AVAILABLE:
            return None
        
        return RLState(
            icp_tier=state_data.get("icp_tier", "tier_4"),
            intent_bucket=state_data.get("intent_bucket", "cold"),
            source_type=state_data.get("source_type", "unknown"),
            day_of_week=state_data.get("day_of_week", datetime.utcnow().weekday()),
            time_bucket=state_data.get("time_bucket", "off_hours")
        )
    
    async def record_outcome(
        self,
        state: Dict[str, Any],
        action: str,
        outcome: Dict[str, Any],
        next_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Record action outcome and update Q-table."""
        
        if self.dry_run:
            return {"success": True, "dry_run": True}
        
        outcome_record = {
            "state": state,
            "action": action,
            "outcome": outcome,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.outcome_history.append(outcome_record)
        
        if self.rl_engine:
            rl_state = self._create_state(state)
            rl_next_state = self._create_state(next_state) if next_state else rl_state
            
            reward = self.rl_engine.calculate_reward(outcome)
            
            self.rl_engine.update(rl_state, action, reward, rl_next_state)
            
            self.rl_engine.save_policy()
            
            self._save_history()
            
            is_failure = reward < 0 or outcome.get("error") or outcome.get("failed")
            if is_failure:
                self._record_failure(state, action, outcome)
            
            return {
                "success": True,
                "reward": reward,
                "new_q_value": self.rl_engine.q_table[rl_state.to_key()].get(action, 0.0),
                "epsilon": self.rl_engine.epsilon,
                "is_failure": is_failure
            }
        
        self._save_history()
        return {"success": True, "warning": "RL engine not available"}
    
    def _record_failure(self, state: Dict[str, Any], action: str, outcome: Dict[str, Any]):
        """Track failure patterns."""
        pattern_key = f"{state.get('icp_tier', 'unknown')}:{action}"
        
        if pattern_key in self.failure_patterns:
            self.failure_patterns[pattern_key].frequency += 1
            self.failure_patterns[pattern_key].last_seen = datetime.utcnow().isoformat()
        else:
            self.failure_patterns[pattern_key] = FailurePattern(
                pattern_id=pattern_key,
                pattern_type="action_failure",
                frequency=1,
                last_seen=datetime.utcnow().isoformat(),
                context={"state": state, "action": action, "outcome": outcome},
                suggested_fix=None
            )
    
    async def get_q_value(
        self,
        state: Dict[str, Any],
        action: str
    ) -> Dict[str, Any]:
        """Get Q-value for state-action pair."""
        
        if not self.rl_engine:
            return {"success": False, "error": "RL engine not available"}
        
        rl_state = self._create_state(state)
        state_key = rl_state.to_key()
        
        q_value = self.rl_engine.q_table[state_key].get(action, 0.0)
        
        all_actions = self.rl_engine.q_table[state_key]
        rank = sorted(all_actions.items(), key=lambda x: x[1], reverse=True)
        action_rank = next((i for i, (a, _) in enumerate(rank) if a == action), -1) + 1
        
        return {
            "success": True,
            "state_key": state_key,
            "action": action,
            "q_value": q_value,
            "rank": action_rank,
            "total_actions": len(all_actions)
        }
    
    async def update_q_table(
        self,
        state: Dict[str, Any],
        action: str,
        q_value: float
    ) -> Dict[str, Any]:
        """Directly update Q-table entry (use with caution)."""
        
        if self.dry_run:
            return {"success": True, "dry_run": True}
        
        if not self.rl_engine:
            return {"success": False, "error": "RL engine not available"}
        
        rl_state = self._create_state(state)
        state_key = rl_state.to_key()
        
        old_value = self.rl_engine.q_table[state_key].get(action, 0.0)
        self.rl_engine.q_table[state_key][action] = q_value
        self.rl_engine.save_policy()
        
        return {
            "success": True,
            "state_key": state_key,
            "action": action,
            "old_q_value": old_value,
            "new_q_value": q_value
        }
    
    async def get_best_action(
        self,
        state: Dict[str, Any],
        action_type: Optional[str] = None,
        exploit_only: bool = False
    ) -> Dict[str, Any]:
        """Get optimal action for a state."""
        
        if not self.rl_engine:
            return {"success": False, "error": "RL engine not available"}
        
        rl_state = self._create_state(state)
        
        if exploit_only:
            original_epsilon = self.rl_engine.epsilon
            self.rl_engine.epsilon = 0.0
            action = self.rl_engine.select_action(rl_state, action_type)
            self.rl_engine.epsilon = original_epsilon
        else:
            action = self.rl_engine.select_action(rl_state, action_type)
        
        state_key = rl_state.to_key()
        q_value = self.rl_engine.q_table[state_key].get(action, 0.0)
        
        all_actions = self.rl_engine.q_table[state_key]
        alternatives = sorted(all_actions.items(), key=lambda x: x[1], reverse=True)[:3]
        
        return {
            "success": True,
            "action": action,
            "q_value": q_value,
            "explored": not exploit_only and self.rl_engine.epsilon > 0,
            "alternatives": [{"action": a, "q_value": v} for a, v in alternatives]
        }
    
    async def get_workflow_insights(
        self,
        workflow_type: Optional[str] = None,
        time_range_hours: int = 24
    ) -> Dict[str, Any]:
        """Analyze workflow performance and generate insights."""
        
        cutoff = datetime.utcnow() - timedelta(hours=time_range_hours)
        
        recent_outcomes = [
            o for o in self.outcome_history
            if datetime.fromisoformat(o["timestamp"]) > cutoff
        ]
        
        if not recent_outcomes:
            return {
                "success": True,
                "insights": [],
                "message": "No recent outcomes to analyze"
            }
        
        insights = []
        
        total = len(recent_outcomes)
        successes = sum(1 for o in recent_outcomes if o["outcome"].get("success", False))
        success_rate = successes / total if total > 0 else 0
        
        trend = "stable"
        if len(recent_outcomes) > 10:
            first_half = recent_outcomes[:len(recent_outcomes)//2]
            second_half = recent_outcomes[len(recent_outcomes)//2:]
            first_rate = sum(1 for o in first_half if o["outcome"].get("success", False)) / len(first_half)
            second_rate = sum(1 for o in second_half if o["outcome"].get("success", False)) / len(second_half)
            if second_rate > first_rate + 0.05:
                trend = "improving"
            elif second_rate < first_rate - 0.05:
                trend = "declining"
        
        recommendation = "Performance is stable. Continue current approach."
        if trend == "declining":
            recommendation = "Performance declining. Review recent action changes."
        elif trend == "improving":
            recommendation = "Performance improving. Current optimizations working."
        
        insights.append(WorkflowInsight(
            insight_type="success_rate",
            metric="overall_success_rate",
            value=round(success_rate, 4),
            trend=trend,
            recommendation=recommendation
        ))
        
        action_counts = defaultdict(int)
        for o in recent_outcomes:
            action_counts[o["action"]] += 1
        
        most_used = sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        policy_summary = None
        if self.rl_engine:
            policy_summary = self.rl_engine.get_policy_summary(top_n=5)
        
        return {
            "success": True,
            "time_range_hours": time_range_hours,
            "total_outcomes": total,
            "insights": [asdict(i) for i in insights],
            "action_distribution": dict(most_used),
            "policy_summary": policy_summary
        }
    
    async def get_failure_patterns(
        self,
        min_frequency: int = 2
    ) -> Dict[str, Any]:
        """Identify common failure patterns."""
        
        patterns = [
            asdict(p) for p in self.failure_patterns.values()
            if p.frequency >= min_frequency
        ]
        
        patterns.sort(key=lambda x: x["frequency"], reverse=True)
        
        for pattern in patterns:
            if pattern["frequency"] >= 5:
                pattern["suggested_fix"] = f"High failure rate detected. Consider removing or modifying action in this context."
            elif pattern["frequency"] >= 3:
                pattern["suggested_fix"] = "Moderate failure rate. Monitor and consider alternatives."
        
        return {
            "success": True,
            "patterns": patterns[:20],
            "total_patterns": len(patterns),
            "summary": {
                "high_frequency": sum(1 for p in patterns if p["frequency"] >= 5),
                "medium_frequency": sum(1 for p in patterns if 3 <= p["frequency"] < 5),
                "low_frequency": sum(1 for p in patterns if p["frequency"] < 3)
            }
        }
    
    async def suggest_refinements(
        self,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get AI-suggested improvements based on learning data."""
        
        suggestions = []
        
        failure_result = await self.get_failure_patterns(min_frequency=3)
        high_failure_patterns = [p for p in failure_result["patterns"] if p["frequency"] >= 5]
        
        for pattern in high_failure_patterns[:3]:
            suggestions.append({
                "type": "reduce_failure",
                "priority": "high",
                "pattern": pattern["pattern_id"],
                "suggestion": f"Pattern '{pattern['pattern_id']}' failing frequently. Consider deprecating or adding guard conditions.",
                "expected_impact": "Reduce failure rate by avoiding problematic action-state combinations"
            })
        
        if self.rl_engine:
            policy = self.rl_engine.get_policy_summary()
            
            if policy["current_epsilon"] > 0.05:
                suggestions.append({
                    "type": "exploitation",
                    "priority": "medium",
                    "suggestion": f"Exploration rate is {policy['current_epsilon']:.2%}. Consider reducing to exploit learned policy more.",
                    "expected_impact": "More consistent action selection based on learned Q-values"
                })
            
            if policy["total_states"] < 10:
                suggestions.append({
                    "type": "exploration",
                    "priority": "low",
                    "suggestion": "Limited state coverage. Increase exploration to learn more state-action pairs.",
                    "expected_impact": "Better generalization across different scenarios"
                })
        
        insights_result = await self.get_workflow_insights(time_range_hours=168)
        for insight in insights_result.get("insights", []):
            if insight.get("trend") == "declining":
                suggestions.append({
                    "type": "performance_decline",
                    "priority": "high",
                    "metric": insight["metric"],
                    "suggestion": insight["recommendation"],
                    "expected_impact": "Reverse declining performance trend"
                })
        
        return {
            "success": True,
            "suggestions": suggestions,
            "context_used": context is not None,
            "generated_at": datetime.utcnow().isoformat()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "learning-mcp",
            "timestamp": datetime.utcnow().isoformat(),
            "rl_engine_available": self.rl_engine is not None,
            "outcome_history_size": len(self.outcome_history),
            "failure_patterns_count": len(self.failure_patterns),
            "dry_run": self.dry_run
        }


TOOLS = [
    {
        "name": "record_outcome",
        "description": "Record an action outcome and update the Q-table. Central learning mechanism.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {
                    "type": "object",
                    "description": "State when action was taken (icp_tier, intent_bucket, source_type, etc.)"
                },
                "action": {"type": "string", "description": "Action that was taken"},
                "outcome": {
                    "type": "object",
                    "description": "Outcome signals (email_opened, reply_received, meeting_booked, etc.)"
                },
                "next_state": {
                    "type": "object",
                    "description": "Optional next state after action"
                }
            },
            "required": ["state", "action", "outcome"]
        }
    },
    {
        "name": "get_q_value",
        "description": "Get Q-value for a specific state-action pair.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "object", "description": "State to query"},
                "action": {"type": "string", "description": "Action to query"}
            },
            "required": ["state", "action"]
        }
    },
    {
        "name": "update_q_table",
        "description": "Directly update a Q-table entry (use with caution).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "object", "description": "State to update"},
                "action": {"type": "string", "description": "Action to update"},
                "q_value": {"type": "number", "description": "New Q-value"}
            },
            "required": ["state", "action", "q_value"]
        }
    },
    {
        "name": "get_best_action",
        "description": "Get the optimal action for a given state based on learned policy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "object", "description": "Current state"},
                "action_type": {
                    "type": "string",
                    "enum": ["template", "timing", "personalization", "channel"],
                    "description": "Filter to specific action type"
                },
                "exploit_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, always return best action (no exploration)"
                }
            },
            "required": ["state"]
        }
    },
    {
        "name": "get_workflow_insights",
        "description": "Analyze workflow performance and get insights.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_type": {"type": "string", "description": "Filter to specific workflow"},
                "time_range_hours": {
                    "type": "integer",
                    "default": 24,
                    "description": "Hours of history to analyze"
                }
            }
        }
    },
    {
        "name": "get_failure_patterns",
        "description": "Identify common failure patterns from historical data.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_frequency": {
                    "type": "integer",
                    "default": 2,
                    "description": "Minimum failure count to include"
                }
            }
        }
    },
    {
        "name": "suggest_refinements",
        "description": "Get AI-suggested improvements based on learning data.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "object",
                    "description": "Optional context for targeted suggestions"
                }
            }
        }
    }
]


async def main():
    parser = argparse.ArgumentParser(description="Learning MCP Server")
    parser.add_argument("--dry-run", action="store_true", help="Run without making changes")
    args = parser.parse_args()
    
    global DRY_RUN
    DRY_RUN = args.dry_run
    
    if not MCP_AVAILABLE:
        print("MCP package not available. Install with: pip install mcp")
        return
    
    server = Server("learning-mcp")
    learning_server = LearningMCPServer(dry_run=DRY_RUN)
    
    if DRY_RUN:
        logger.info("Running in DRY-RUN mode")
    
    @server.list_tools()
    async def list_tools():
        return [Tool(**tool) for tool in TOOLS]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        try:
            if name == "record_outcome":
                result = await learning_server.record_outcome(
                    arguments["state"],
                    arguments["action"],
                    arguments["outcome"],
                    arguments.get("next_state")
                )
            elif name == "get_q_value":
                result = await learning_server.get_q_value(
                    arguments["state"],
                    arguments["action"]
                )
            elif name == "update_q_table":
                result = await learning_server.update_q_table(
                    arguments["state"],
                    arguments["action"],
                    arguments["q_value"]
                )
            elif name == "get_best_action":
                result = await learning_server.get_best_action(
                    arguments["state"],
                    arguments.get("action_type"),
                    arguments.get("exploit_only", False)
                )
            elif name == "get_workflow_insights":
                result = await learning_server.get_workflow_insights(
                    arguments.get("workflow_type"),
                    arguments.get("time_range_hours", 24)
                )
            elif name == "get_failure_patterns":
                result = await learning_server.get_failure_patterns(
                    arguments.get("min_frequency", 2)
                )
            elif name == "suggest_refinements":
                result = await learning_server.suggest_refinements(
                    arguments.get("context")
                )
            else:
                result = {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.exception(f"Tool error: {name}")
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1])


if __name__ == "__main__":
    asyncio.run(main())
