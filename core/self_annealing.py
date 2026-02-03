#!/usr/bin/env python3
"""
Unified Self-Annealing Engine
=============================
Core engine for adaptive learning and continuous system improvement.

Integrates:
- RL Engine for Q-learning based decision optimization
- Context Management for efficient token usage
- Pattern detection and refinement generation

The self-annealing loop continuously:
1. Observes outcomes from workflows
2. Detects patterns (success/failure)
3. Updates Q-values for state-action pairs
4. Generates refinements to ICP, messaging, routing
5. Reports insights to the QUEEN orchestrator

Usage:
    from core.self_annealing import SelfAnnealingEngine
    
    engine = SelfAnnealingEngine()
    engine.learn_from_outcome(workflow="campaign_001", outcome=outcome_data, success=True)
    insights = engine.get_workflow_insights("campaign")
"""

import os
import sys
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from collections import defaultdict
from enum import Enum

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from execution.rl_engine import RLEngine, RLState
    RL_AVAILABLE = True
except ImportError:
    RL_AVAILABLE = False
    RLEngine = None
    RLState = None

try:
    from core.context import ContextManager, EventThread, EventType
    CONTEXT_AVAILABLE = True
except ImportError:
    CONTEXT_AVAILABLE = False


class OutcomeType(Enum):
    MEETING_BOOKED = "meeting_booked"
    POSITIVE_REPLY = "positive_reply"
    NEUTRAL_REPLY = "neutral_reply"
    NEGATIVE_REPLY = "negative_reply"
    EMAIL_OPENED = "email_opened"
    EMAIL_CLICKED = "email_clicked"
    UNSUBSCRIBE = "unsubscribe"
    SPAM_REPORT = "spam_report"
    BOUNCE = "bounce"
    NO_RESPONSE = "no_response"


class RefinementTarget(Enum):
    ICP_CRITERIA = "icp_criteria"
    MESSAGING = "messaging"
    ROUTING = "routing"
    TIMING = "timing"
    PERSONALIZATION = "personalization"
    TEMPLATE = "template"


REWARD_MAP = {
    OutcomeType.MEETING_BOOKED: 100,
    OutcomeType.POSITIVE_REPLY: 50,
    OutcomeType.NEUTRAL_REPLY: 10,
    OutcomeType.NEGATIVE_REPLY: -5,
    OutcomeType.EMAIL_OPENED: 20,
    OutcomeType.EMAIL_CLICKED: 30,
    OutcomeType.UNSUBSCRIBE: -10,
    OutcomeType.SPAM_REPORT: -50,
    OutcomeType.BOUNCE: -10,
    OutcomeType.NO_RESPONSE: -2,
}


@dataclass
class WorkflowOutcome:
    """Represents an outcome from a workflow execution."""
    workflow_id: str
    workflow_type: str
    outcome_type: OutcomeType
    success: bool
    details: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    state: Optional[Dict[str, Any]] = None
    action: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "workflow_type": self.workflow_type,
            "outcome_type": self.outcome_type.value,
            "success": self.success,
            "details": self.details,
            "timestamp": self.timestamp,
            "state": self.state,
            "action": self.action
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'WorkflowOutcome':
        return cls(
            workflow_id=d["workflow_id"],
            workflow_type=d["workflow_type"],
            outcome_type=OutcomeType(d["outcome_type"]),
            success=d["success"],
            details=d["details"],
            timestamp=d.get("timestamp", datetime.now(timezone.utc).isoformat()),
            state=d.get("state"),
            action=d.get("action")
        )


@dataclass
class Pattern:
    """Represents a detected pattern in outcomes."""
    pattern_id: str
    pattern_type: str  # "success" or "failure"
    frequency: int
    last_seen: str
    context: Dict[str, Any]
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Refinement:
    """Represents a suggested refinement to the system."""
    refinement_id: str
    target: RefinementTarget
    suggestion: str
    confidence: float
    reason: str
    priority: int = 0  # 0=low, 1=medium, 2=high
    auto_apply: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["target"] = self.target.value
        return d


class SelfAnnealingEngine:
    """
    Unified self-annealing engine for adaptive system improvement.
    
    Features:
    - Tracks workflow outcomes and learns from them
    - Detects success/failure patterns
    - Generates refinements to improve system performance
    - Integrates with RL engine for Q-learning
    - Reports to QUEEN orchestrator
    """
    
    def __init__(
        self,
        epsilon: float = 0.30,
        epsilon_decay: float = 0.995,
        min_epsilon: float = 0.05,
        learning_rate: float = 0.1,
        discount_factor: float = 0.95
    ):
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.min_epsilon = min_epsilon
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        
        self.storage_path = PROJECT_ROOT / ".hive-mind"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        if RL_AVAILABLE:
            self.rl_engine = RLEngine(
                learning_rate=learning_rate,
                discount_factor=discount_factor,
                epsilon=epsilon,
                epsilon_decay=epsilon_decay,
                min_epsilon=min_epsilon
            )
        else:
            self.rl_engine = None
        
        self.outcomes: List[WorkflowOutcome] = []
        self.patterns: Dict[str, Pattern] = {}
        self.refinements: List[Refinement] = []
        self.q_table: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        
        self.metrics = {
            "total_outcomes": 0,
            "success_count": 0,
            "failure_count": 0,
            "patterns_detected": 0,
            "refinements_generated": 0,
            "annealing_steps": 0,
            "last_annealing": None
        }
        
        self._load_state()
    
    def learn_from_outcome(
        self,
        workflow: str,
        outcome: Dict[str, Any],
        success: bool = True,
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Learn from a workflow outcome.
        
        Args:
            workflow: Workflow identifier (e.g., "campaign_tier1_001")
            outcome: Outcome data with type, signals, etc.
            success: Whether the workflow was successful
            details: Additional context about the outcome
        
        Returns:
            Learning result with Q-update info
        """
        details = details or {}
        
        outcome_type = self._determine_outcome_type(outcome)
        workflow_type = workflow.split("_")[0] if "_" in workflow else "unknown"
        
        workflow_outcome = WorkflowOutcome(
            workflow_id=workflow,
            workflow_type=workflow_type,
            outcome_type=outcome_type,
            success=success,
            details={**outcome, **details},
            state=outcome.get("state"),
            action=outcome.get("action")
        )
        
        self.outcomes.append(workflow_outcome)
        self.metrics["total_outcomes"] += 1
        if success:
            self.metrics["success_count"] += 1
        else:
            self.metrics["failure_count"] += 1
        
        reward = REWARD_MAP.get(outcome_type, 0)
        
        if self.rl_engine and outcome.get("state") and outcome.get("action"):
            state_data = outcome["state"]
            action = outcome["action"]
            
            rl_state = RLState(
                icp_tier=state_data.get("icp_tier", "tier_4"),
                intent_bucket=state_data.get("intent_bucket", "cold"),
                source_type=state_data.get("source_type", "unknown"),
                day_of_week=state_data.get("day_of_week", datetime.now(timezone.utc).weekday()),
                time_bucket=state_data.get("time_bucket", "off_hours")
            )
            
            self.rl_engine.update(rl_state, action, reward, rl_state)
            
            state_key = rl_state.to_key()
            new_q = self.rl_engine.q_table[state_key][action]
        else:
            state_key = f"{workflow_type}|{outcome_type.value}"
            old_q = self.q_table[state_key].get("default", 0.0)
            new_q = old_q + self.learning_rate * (reward - old_q)
            self.q_table[state_key]["default"] = new_q
        
        self._update_patterns(workflow_outcome)
        
        self._auto_save()
        
        return {
            "success": True,
            "workflow": workflow,
            "outcome_type": outcome_type.value,
            "reward": reward,
            "new_q_value": new_q,
            "patterns_updated": len(self.patterns)
        }
    
    def _determine_outcome_type(self, outcome: Dict[str, Any]) -> OutcomeType:
        """Determine outcome type from outcome signals."""
        if outcome.get("meeting_booked"):
            return OutcomeType.MEETING_BOOKED
        elif outcome.get("positive_reply"):
            return OutcomeType.POSITIVE_REPLY
        elif outcome.get("spam_report"):
            return OutcomeType.SPAM_REPORT
        elif outcome.get("unsubscribe"):
            return OutcomeType.UNSUBSCRIBE
        elif outcome.get("bounce"):
            return OutcomeType.BOUNCE
        elif outcome.get("reply_received") or outcome.get("neutral_reply"):
            return OutcomeType.NEUTRAL_REPLY
        elif outcome.get("negative_reply"):
            return OutcomeType.NEGATIVE_REPLY
        elif outcome.get("email_clicked"):
            return OutcomeType.EMAIL_CLICKED
        elif outcome.get("email_opened"):
            return OutcomeType.EMAIL_OPENED
        else:
            return OutcomeType.NO_RESPONSE
    
    def _update_patterns(self, outcome: WorkflowOutcome):
        """Update pattern detection from new outcome."""
        pattern_key = f"{outcome.workflow_type}_{outcome.outcome_type.value}"
        
        if pattern_key in self.patterns:
            self.patterns[pattern_key].frequency += 1
            self.patterns[pattern_key].last_seen = outcome.timestamp
        else:
            self.patterns[pattern_key] = Pattern(
                pattern_id=pattern_key,
                pattern_type="success" if outcome.success else "failure",
                frequency=1,
                last_seen=outcome.timestamp,
                context={
                    "workflow_type": outcome.workflow_type,
                    "outcome_type": outcome.outcome_type.value
                }
            )
            self.metrics["patterns_detected"] += 1
    
    def get_workflow_insights(self, workflow_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get insights for a workflow type.
        
        Returns success rate, recent patterns, and recommendations.
        """
        if workflow_type:
            relevant_outcomes = [o for o in self.outcomes if o.workflow_type == workflow_type]
        else:
            relevant_outcomes = self.outcomes
        
        if not relevant_outcomes:
            return {
                "workflow_type": workflow_type or "all",
                "total_outcomes": 0,
                "success_rate": 0.0,
                "patterns": [],
                "recommendations": ["Insufficient data for analysis"]
            }
        
        success_count = sum(1 for o in relevant_outcomes if o.success)
        success_rate = success_count / len(relevant_outcomes)
        
        outcome_distribution = defaultdict(int)
        for o in relevant_outcomes:
            outcome_distribution[o.outcome_type.value] += 1
        
        relevant_patterns = [
            p for p in self.patterns.values()
            if not workflow_type or p.context.get("workflow_type") == workflow_type
        ]
        top_patterns = sorted(relevant_patterns, key=lambda p: p.frequency, reverse=True)[:5]
        
        recommendations = self._generate_recommendations(
            success_rate, outcome_distribution, top_patterns
        )
        
        return {
            "workflow_type": workflow_type or "all",
            "total_outcomes": len(relevant_outcomes),
            "success_rate": round(success_rate, 4),
            "outcome_distribution": dict(outcome_distribution),
            "patterns": [p.to_dict() for p in top_patterns],
            "recommendations": recommendations,
            "analyzed_at": datetime.now(timezone.utc).isoformat()
        }
    
    def _generate_recommendations(
        self,
        success_rate: float,
        distribution: Dict[str, int],
        patterns: List[Pattern]
    ) -> List[str]:
        """Generate recommendations based on analysis."""
        recommendations = []
        
        if success_rate < 0.1:
            recommendations.append("Critical: Success rate below 10%. Review ICP criteria and messaging urgently.")
        elif success_rate < 0.3:
            recommendations.append("Low success rate. Consider narrowing ICP focus to higher-value segments.")
        
        spam_rate = distribution.get("spam_report", 0) / max(sum(distribution.values()), 1)
        if spam_rate > 0.01:
            recommendations.append(f"High spam rate ({spam_rate:.1%}). Review email content and sending frequency.")
        
        bounce_rate = distribution.get("bounce", 0) / max(sum(distribution.values()), 1)
        if bounce_rate > 0.05:
            recommendations.append(f"High bounce rate ({bounce_rate:.1%}). Verify email data quality and enrichment sources.")
        
        failure_patterns = [p for p in patterns if p.pattern_type == "failure" and p.frequency > 5]
        for pattern in failure_patterns[:2]:
            recommendations.append(f"Recurring failure: {pattern.pattern_id} ({pattern.frequency}x). Investigate root cause.")
        
        if not recommendations:
            recommendations.append("System performing within expected parameters.")
        
        return recommendations
    
    def detect_patterns(self, min_frequency: int = 3) -> List[Pattern]:
        """
        Detect significant patterns from outcome history.
        
        Returns patterns that appear frequently enough to be actionable.
        """
        significant = [
            p for p in self.patterns.values()
            if p.frequency >= min_frequency
        ]
        
        for pattern in significant:
            pattern.confidence = min(1.0, pattern.frequency / 20.0)
        
        return sorted(significant, key=lambda p: p.frequency, reverse=True)
    
    def generate_refinements(self) -> List[Refinement]:
        """
        Generate refinements based on detected patterns and insights.
        """
        refinements = []
        refinement_id = 0
        
        patterns = self.detect_patterns(min_frequency=5)
        
        failure_patterns = [p for p in patterns if p.pattern_type == "failure"]
        for pattern in failure_patterns[:3]:
            outcome_type = pattern.context.get("outcome_type", "unknown")
            
            if outcome_type == "spam_report":
                refinements.append(Refinement(
                    refinement_id=f"ref_{refinement_id:04d}",
                    target=RefinementTarget.MESSAGING,
                    suggestion="Reduce promotional language and add more personalization",
                    confidence=pattern.confidence,
                    reason=f"High spam reports in {pattern.pattern_id}",
                    priority=2
                ))
            elif outcome_type == "bounce":
                refinements.append(Refinement(
                    refinement_id=f"ref_{refinement_id:04d}",
                    target=RefinementTarget.ICP_CRITERIA,
                    suggestion="Add email verification step before outreach",
                    confidence=pattern.confidence,
                    reason=f"High bounce rate in {pattern.pattern_id}",
                    priority=2
                ))
            elif outcome_type == "no_response":
                refinements.append(Refinement(
                    refinement_id=f"ref_{refinement_id:04d}",
                    target=RefinementTarget.TIMING,
                    suggestion="Experiment with different send times (morning vs afternoon)",
                    confidence=pattern.confidence * 0.8,
                    reason=f"Low engagement in {pattern.pattern_id}",
                    priority=1
                ))
            
            refinement_id += 1
        
        success_patterns = [p for p in patterns if p.pattern_type == "success"]
        for pattern in success_patterns[:2]:
            refinements.append(Refinement(
                refinement_id=f"ref_{refinement_id:04d}",
                target=RefinementTarget.TEMPLATE,
                suggestion=f"Double down on {pattern.context.get('workflow_type', 'this')} approach",
                confidence=pattern.confidence,
                reason=f"High success rate: {pattern.frequency} successes",
                priority=1
            ))
            refinement_id += 1
        
        self.refinements.extend(refinements)
        self.metrics["refinements_generated"] += len(refinements)
        
        return refinements
    
    def anneal_step(self) -> Dict[str, Any]:
        """
        Execute one step of the self-annealing loop.
        
        1. Analyze recent outcomes
        2. Detect patterns
        3. Generate refinements
        4. Decay epsilon (exploration rate)
        """
        patterns = self.detect_patterns()
        refinements = self.generate_refinements()
        
        self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)
        if self.rl_engine:
            self.rl_engine.epsilon = self.epsilon
        
        insights = self.get_workflow_insights()
        
        self.metrics["annealing_steps"] += 1
        self.metrics["last_annealing"] = datetime.now(timezone.utc).isoformat()
        
        self._auto_save()
        
        return {
            "step": self.metrics["annealing_steps"],
            "epsilon": round(self.epsilon, 4),
            "patterns_found": len(patterns),
            "refinements_generated": len(refinements),
            "success_rate": insights.get("success_rate", 0),
            "recommendations": insights.get("recommendations", [])[:3],
            "timestamp": self.metrics["last_annealing"]
        }
    
    def report_to_queen(self) -> Dict[str, Any]:
        """
        Generate a summary report for the QUEEN orchestrator.
        """
        insights = self.get_workflow_insights()
        patterns = self.detect_patterns(min_frequency=3)
        
        success_patterns = [p for p in patterns if p.pattern_type == "success"][:3]
        failure_patterns = [p for p in patterns if p.pattern_type == "failure"][:3]
        
        recent_refinements = self.refinements[-5:] if self.refinements else []
        
        return {
            "report_type": "self_annealing_summary",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "total_outcomes": self.metrics["total_outcomes"],
                "success_rate": insights.get("success_rate", 0),
                "patterns_detected": self.metrics["patterns_detected"],
                "refinements_generated": self.metrics["refinements_generated"],
                "annealing_steps": self.metrics["annealing_steps"],
                "current_epsilon": round(self.epsilon, 4)
            },
            "health_status": self._determine_health_status(insights),
            "top_success_patterns": [p.to_dict() for p in success_patterns],
            "top_failure_patterns": [p.to_dict() for p in failure_patterns],
            "recent_refinements": [r.to_dict() for r in recent_refinements],
            "recommendations": insights.get("recommendations", [])
        }
    
    def _determine_health_status(self, insights: Dict[str, Any]) -> str:
        """Determine overall system health."""
        success_rate = insights.get("success_rate", 0)
        
        if success_rate >= 0.3:
            return "healthy"
        elif success_rate >= 0.15:
            return "warning"
        elif success_rate >= 0.05:
            return "degraded"
        else:
            return "critical"
    
    def get_annealing_status(self) -> Dict[str, Any]:
        """Get current annealing state and metrics."""
        return {
            "epsilon": round(self.epsilon, 4),
            "epsilon_target": self.min_epsilon,
            "decay_rate": self.epsilon_decay,
            "total_outcomes": self.metrics["total_outcomes"],
            "patterns_count": len(self.patterns),
            "refinements_count": len(self.refinements),
            "annealing_steps": self.metrics["annealing_steps"],
            "last_annealing": self.metrics["last_annealing"],
            "rl_engine_active": self.rl_engine is not None,
            "q_table_size": len(self.q_table) if not self.rl_engine else len(self.rl_engine.q_table)
        }
    
    def get_best_action(self, state: Dict[str, Any], action_type: Optional[str] = None) -> str:
        """Get the best action for a given state."""
        if self.rl_engine:
            rl_state = RLState(
                icp_tier=state.get("icp_tier", "tier_4"),
                intent_bucket=state.get("intent_bucket", "cold"),
                source_type=state.get("source_type", "unknown"),
                day_of_week=state.get("day_of_week", datetime.now(timezone.utc).weekday()),
                time_bucket=state.get("time_bucket", "off_hours")
            )
            return self.rl_engine.select_action(rl_state, action_type)
        else:
            default_actions = {
                "template": "template_thought_leadership",
                "timing": "timing_morning_optimal",
                "personalization": "personalization_medium",
                "channel": "channel_email_only"
            }
            return default_actions.get(action_type, "template_thought_leadership")
    
    def save_state(self, path: Optional[Path] = None):
        """Save engine state to disk."""
        if path is None:
            path = self.storage_path / "self_annealing_state.json"
        
        q_table_serializable = {
            k: dict(v) for k, v in self.q_table.items()
        }
        
        state = {
            "epsilon": self.epsilon,
            "metrics": self.metrics,
            "outcomes": [o.to_dict() for o in self.outcomes[-1000:]],
            "patterns": {k: p.to_dict() for k, p in self.patterns.items()},
            "refinements": [r.to_dict() for r in self.refinements[-100:]],
            "q_table": q_table_serializable,
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
        
        if self.rl_engine:
            self.rl_engine.save_policy()
    
    def _load_state(self):
        """Load engine state from disk."""
        path = self.storage_path / "self_annealing_state.json"
        
        if not path.exists():
            return
        
        try:
            with open(path) as f:
                state = json.load(f)
            
            self.epsilon = state.get("epsilon", self.epsilon)
            self.metrics = state.get("metrics", self.metrics)
            
            for o_data in state.get("outcomes", []):
                try:
                    self.outcomes.append(WorkflowOutcome.from_dict(o_data))
                except Exception:
                    pass
            
            for k, p_data in state.get("patterns", {}).items():
                self.patterns[k] = Pattern(**p_data)
            
            for k, v in state.get("q_table", {}).items():
                self.q_table[k] = defaultdict(float, v)
            
        except Exception as e:
            print(f"Warning: Failed to load self-annealing state: {e}")
    
    def _auto_save(self):
        """Auto-save every N outcomes."""
        if self.metrics["total_outcomes"] % 10 == 0:
            self.save_state()


if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    
    console.print("\n[bold blue]Self-Annealing Engine Demo[/bold blue]\n")
    
    engine = SelfAnnealingEngine(epsilon=0.30)
    
    console.print("[dim]Simulating workflow outcomes...[/dim]\n")
    
    scenarios = [
        {"workflow": "campaign_tier1_001", "outcome": {"meeting_booked": True}, "success": True},
        {"workflow": "campaign_tier1_002", "outcome": {"positive_reply": True}, "success": True},
        {"workflow": "campaign_tier2_001", "outcome": {"email_opened": True}, "success": True},
        {"workflow": "campaign_tier2_002", "outcome": {"no_response": True}, "success": False},
        {"workflow": "campaign_tier3_001", "outcome": {"bounce": True}, "success": False},
        {"workflow": "campaign_tier3_002", "outcome": {"spam_report": True}, "success": False},
        {"workflow": "campaign_tier1_003", "outcome": {"positive_reply": True}, "success": True},
        {"workflow": "campaign_tier2_003", "outcome": {"email_clicked": True}, "success": True},
    ]
    
    for scenario in scenarios:
        result = engine.learn_from_outcome(
            workflow=scenario["workflow"],
            outcome=scenario["outcome"],
            success=scenario["success"]
        )
        console.print(f"  Learned: {scenario['workflow']} -> reward={result['reward']}")
    
    console.print("\n[bold]Running annealing step...[/bold]")
    step_result = engine.anneal_step()
    
    table = Table(title="Annealing Step Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Step", str(step_result["step"]))
    table.add_row("Epsilon", f"{step_result['epsilon']:.4f}")
    table.add_row("Patterns Found", str(step_result["patterns_found"]))
    table.add_row("Refinements", str(step_result["refinements_generated"]))
    table.add_row("Success Rate", f"{step_result['success_rate']:.1%}")
    
    console.print(table)
    
    console.print("\n[bold]QUEEN Report:[/bold]")
    report = engine.report_to_queen()
    console.print(f"  Health Status: {report['health_status']}")
    console.print(f"  Total Outcomes: {report['metrics']['total_outcomes']}")
    console.print(f"  Recommendations: {report['recommendations'][:2]}")
    
    console.print("\n[green]Demo complete![/green]")
