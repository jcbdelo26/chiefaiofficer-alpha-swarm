#!/usr/bin/env python3
"""
Intent Interpreter - System Two Logic Layer
=============================================
Translates vague user prompts into specific, multi-step agentic goals.

This is the "Intent Layer" from Vercel's Lead Agent architecture that sits
between raw input and the UNIFIED_QUEEN orchestrator.

Key Features:
- Converts natural language to structured AgenticGoal
- Generates multi-step execution plans
- Maps goals to specific agents
- Validates goals against available capabilities

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    INTENT INTERPRETER                        │
    │  Raw Input → Parse Intent → Generate Plan → Validate → Goal │
    │                                                              │
    │  "Find new customers" →                                      │
    │    AgenticGoal(                                              │
    │      objective="discover_leads",                             │
    │      steps=[HUNTER.scrape, ENRICHER.validate, ...],          │
    │      success_criteria="10+ qualified leads"                  │
    │    )                                                         │
    └─────────────────────────────────────────────────────────────┘

Based on Vercel's Lead Agent "Intent Layer" pattern.
"""

import json
import logging
import uuid
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("intent_interpreter")


class ObjectiveType(Enum):
    """High-level objective categories."""
    DISCOVER_LEADS = "discover_leads"
    ENRICH_LEADS = "enrich_leads"
    QUALIFY_LEADS = "qualify_leads"
    CREATE_CAMPAIGN = "create_campaign"
    SEND_OUTREACH = "send_outreach"
    SCHEDULE_MEETING = "schedule_meeting"
    RESEARCH_COMPANY = "research_company"
    ANALYZE_PIPELINE = "analyze_pipeline"
    CUSTOM = "custom"


class AgentRole(Enum):
    """Agents available in the swarm."""
    UNIFIED_QUEEN = "UNIFIED_QUEEN"
    HUNTER = "HUNTER"
    ENRICHER = "ENRICHER"
    SEGMENTOR = "SEGMENTOR"
    CRAFTER = "CRAFTER"
    GATEKEEPER = "GATEKEEPER"
    OPERATOR = "OPERATOR"
    SCHEDULER = "SCHEDULER"
    RESEARCHER = "RESEARCHER"


@dataclass
class GoalStep:
    """A single step in an agentic goal execution plan."""
    step_id: str
    sequence: int
    agent: str
    action: str
    description: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    timeout_seconds: int = 300
    retry_count: int = 2
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgenticGoal:
    """
    A structured, multi-step goal translated from natural language input.
    
    This is the output of the Intent Interpreter and the input to the
    UNIFIED_QUEEN orchestrator.
    """
    goal_id: str
    objective: ObjectiveType
    original_input: str
    interpreted_intent: str
    steps: List[GoalStep]
    success_criteria: str
    estimated_duration_minutes: int
    priority: int = 1  # 1=highest
    requires_approval: bool = False
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "objective": self.objective.value,
            "steps": [s.to_dict() for s in self.steps]
        }
    
    @property
    def agent_sequence(self) -> List[str]:
        """Get the sequence of agents involved."""
        return [step.agent for step in sorted(self.steps, key=lambda s: s.sequence)]


# =============================================================================
# INTENT PATTERNS
# =============================================================================

INTENT_PATTERNS: Dict[str, Dict[str, Any]] = {
    "discover_leads": {
        "keywords": ["find", "discover", "scrape", "hunt", "get leads", "find customers", "prospect"],
        "objective": ObjectiveType.DISCOVER_LEADS,
        "default_steps": [
            {"agent": "HUNTER", "action": "scrape_leads", "description": "Scrape leads from source"},
            {"agent": "ENRICHER", "action": "validate_emails", "description": "Validate and enrich lead data"},
            {"agent": "SEGMENTOR", "action": "score_and_tier", "description": "Score leads and assign tiers"}
        ],
        "success_criteria": "Leads discovered and scored with ICP tiers assigned",
        "duration_minutes": 30
    },
    "enrich_leads": {
        "keywords": ["enrich", "validate", "augment", "fill in", "complete data"],
        "objective": ObjectiveType.ENRICH_LEADS,
        "default_steps": [
            {"agent": "ENRICHER", "action": "enrich_batch", "description": "Enrich leads via Clay waterfall"},
            {"agent": "SEGMENTOR", "action": "rescore", "description": "Rescore with enriched data"}
        ],
        "success_criteria": "Leads enriched with email, company size, and industry",
        "duration_minutes": 15
    },
    "qualify_leads": {
        "keywords": ["qualify", "score", "segment", "classify", "tier", "prioritize"],
        "objective": ObjectiveType.QUALIFY_LEADS,
        "default_steps": [
            {"agent": "SEGMENTOR", "action": "qualify_batch", "description": "Score and tier leads"},
        ],
        "success_criteria": "Leads categorized into tiers with qualification scores",
        "duration_minutes": 10
    },
    "create_campaign": {
        "keywords": ["campaign", "write emails", "draft", "create outreach", "personalize"],
        "objective": ObjectiveType.CREATE_CAMPAIGN,
        "default_steps": [
            {"agent": "CRAFTER", "action": "generate_emails", "description": "Generate personalized emails"},
            {"agent": "GATEKEEPER", "action": "review_content", "description": "Review for compliance"},
        ],
        "success_criteria": "Campaign emails generated and approved",
        "duration_minutes": 20,
        "requires_approval": True
    },
    "send_outreach": {
        "keywords": ["send", "email", "outreach", "launch", "execute campaign"],
        "objective": ObjectiveType.SEND_OUTREACH,
        "default_steps": [
            {"agent": "GATEKEEPER", "action": "approve_send", "description": "Final approval check"},
            {"agent": "OPERATOR", "action": "send_emails", "description": "Execute email send via GHL"},
        ],
        "success_criteria": "Emails sent successfully via GHL",
        "duration_minutes": 15,
        "requires_approval": True
    },
    "schedule_meeting": {
        "keywords": ["schedule", "book", "meeting", "calendar", "appointment"],
        "objective": ObjectiveType.SCHEDULE_MEETING,
        "default_steps": [
            {"agent": "SCHEDULER", "action": "find_slots", "description": "Find available time slots"},
            {"agent": "SCHEDULER", "action": "create_event", "description": "Create calendar event"},
        ],
        "success_criteria": "Meeting scheduled with calendar invite sent",
        "duration_minutes": 5
    },
    "research_company": {
        "keywords": ["research", "analyze", "investigate", "learn about", "company info"],
        "objective": ObjectiveType.RESEARCH_COMPANY,
        "default_steps": [
            {"agent": "RESEARCHER", "action": "deep_research", "description": "Comprehensive company research"},
        ],
        "success_criteria": "Research report generated with key insights",
        "duration_minutes": 10
    },
    "analyze_pipeline": {
        "keywords": ["pipeline", "deals", "opportunities", "forecast", "analyze deals"],
        "objective": ObjectiveType.ANALYZE_PIPELINE,
        "default_steps": [
            {"agent": "UNIFIED_QUEEN", "action": "analyze_pipeline", "description": "Analyze deal pipeline"},
        ],
        "success_criteria": "Pipeline analysis with recommendations",
        "duration_minutes": 15
    }
}


class IntentInterpreter:
    """
    Translates vague user prompts into specific, multi-step agentic goals.
    
    This is the "Intent Layer" that sits between raw input and the orchestrator.
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path(".hive-mind/intents")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.patterns = INTENT_PATTERNS
    
    def interpret(self, raw_input: str, context: Optional[Dict[str, Any]] = None) -> AgenticGoal:
        """
        Interpret natural language input into a structured agentic goal.
        
        Args:
            raw_input: Natural language description of what the user wants
            context: Optional context (current leads, active campaigns, etc.)
            
        Returns:
            AgenticGoal with multi-step execution plan
        """
        context = context or {}
        
        # Step 1: Identify objective type
        objective_type, confidence = self._identify_objective(raw_input)
        
        # Step 2: Extract parameters from input
        params = self._extract_parameters(raw_input, objective_type)
        
        # Step 3: Build execution steps
        steps = self._build_steps(objective_type, params, context)
        
        # Step 4: Determine success criteria
        success_criteria = self._determine_success_criteria(objective_type, params)
        
        # Step 5: Create the goal
        goal = AgenticGoal(
            goal_id=f"goal_{uuid.uuid4().hex[:8]}",
            objective=objective_type,
            original_input=raw_input,
            interpreted_intent=self._generate_intent_description(objective_type, params),
            steps=steps,
            success_criteria=success_criteria,
            estimated_duration_minutes=self._estimate_duration(steps),
            priority=self._calculate_priority(params, context),
            requires_approval=self._requires_approval(objective_type, params),
            context={**context, "extracted_params": params, "confidence": confidence}
        )
        
        # Save for audit
        self._save_goal(goal)
        
        logger.info(f"Interpreted intent: '{raw_input}' → {objective_type.value} ({len(steps)} steps)")
        
        return goal
    
    def _identify_objective(self, raw_input: str) -> Tuple[ObjectiveType, float]:
        """Identify the objective type from raw input."""
        input_lower = raw_input.lower()
        best_match = ObjectiveType.CUSTOM
        best_score = 0.0
        
        for pattern_key, pattern_data in self.patterns.items():
            keywords = pattern_data["keywords"]
            score = sum(1 for kw in keywords if kw in input_lower) / len(keywords)
            
            if score > best_score:
                best_score = score
                best_match = pattern_data["objective"]
        
        # Minimum threshold
        if best_score < 0.1:
            best_match = ObjectiveType.CUSTOM
            best_score = 0.0
        
        return best_match, best_score
    
    def _extract_parameters(self, raw_input: str, objective: ObjectiveType) -> Dict[str, Any]:
        """Extract parameters from raw input."""
        params = {
            "raw_input": raw_input,
            "objective": objective.value
        }
        
        # Extract numbers (limits, counts)
        numbers = re.findall(r'\b(\d+)\b', raw_input)
        if numbers:
            params["limit"] = int(numbers[0])
        
        # Extract company names (quoted or capitalized)
        quoted = re.findall(r'"([^"]+)"', raw_input)
        if quoted:
            params["target_companies"] = quoted
        
        # Extract tier mentions
        tier_match = re.search(r'tier[_\s]?(\d)', raw_input.lower())
        if tier_match:
            params["target_tier"] = f"tier_{tier_match.group(1)}"
        
        # Extract source type
        source_keywords = {
            "competitor": "competitor_follower",
            "event": "event_attendee",
            "group": "group_member",
            "website": "website_visitor"
        }
        for kw, source in source_keywords.items():
            if kw in raw_input.lower():
                params["source_type"] = source
                break
        
        # Extract urgency
        if any(word in raw_input.lower() for word in ["urgent", "asap", "immediately", "now"]):
            params["urgency"] = "high"
        elif any(word in raw_input.lower() for word in ["when possible", "eventually", "later"]):
            params["urgency"] = "low"
        else:
            params["urgency"] = "normal"
        
        return params
    
    def _build_steps(
        self, 
        objective: ObjectiveType, 
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[GoalStep]:
        """Build execution steps for the goal."""
        steps = []
        
        # Get default steps for this objective
        pattern_key = objective.value
        if pattern_key in self.patterns:
            default_steps = self.patterns[pattern_key]["default_steps"]
        else:
            # Custom objective - single research step
            default_steps = [
                {"agent": "UNIFIED_QUEEN", "action": "analyze_request", "description": "Analyze custom request"}
            ]
        
        # Build GoalStep objects with dependencies
        prev_step_id = None
        for i, step_def in enumerate(default_steps):
            step_id = f"step_{i+1}"
            
            step = GoalStep(
                step_id=step_id,
                sequence=i + 1,
                agent=step_def["agent"],
                action=step_def["action"],
                description=step_def["description"],
                inputs=self._prepare_step_inputs(step_def, params, context),
                outputs=self._determine_step_outputs(step_def),
                depends_on=[prev_step_id] if prev_step_id else [],
                timeout_seconds=self._get_step_timeout(step_def["agent"]),
                retry_count=2
            )
            
            steps.append(step)
            prev_step_id = step_id
        
        return steps
    
    def _prepare_step_inputs(
        self, 
        step_def: Dict[str, Any], 
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare inputs for a step based on params and context."""
        inputs = {}
        
        agent = step_def["agent"]
        action = step_def["action"]
        
        # Agent-specific input mapping
        if agent == "HUNTER":
            if "limit" in params:
                inputs["limit"] = params["limit"]
            if "source_type" in params:
                inputs["source_type"] = params["source_type"]
            if "target_companies" in params:
                inputs["companies"] = params["target_companies"]
        
        elif agent == "ENRICHER":
            inputs["validate_email"] = True
            inputs["enrich_company"] = True
        
        elif agent == "SEGMENTOR":
            if "target_tier" in params:
                inputs["filter_tier"] = params["target_tier"]
        
        elif agent == "CRAFTER":
            if "target_tier" in params:
                inputs["tier"] = params["target_tier"]
        
        elif agent == "SCHEDULER":
            if "meeting_type" in params:
                inputs["meeting_type"] = params["meeting_type"]
        
        # Pass through context references
        if "leads_file" in context:
            inputs["leads_file"] = context["leads_file"]
        
        return inputs
    
    def _determine_step_outputs(self, step_def: Dict[str, Any]) -> List[str]:
        """Determine expected outputs from a step."""
        agent = step_def["agent"]
        action = step_def["action"]
        
        output_map = {
            "HUNTER": ["leads_file", "lead_count"],
            "ENRICHER": ["enriched_leads_file", "enrichment_rate"],
            "SEGMENTOR": ["segmented_leads_file", "tier_distribution"],
            "CRAFTER": ["campaign_file", "email_count"],
            "GATEKEEPER": ["approval_status", "approval_id"],
            "OPERATOR": ["send_results", "sent_count"],
            "SCHEDULER": ["event_id", "meeting_link"],
            "RESEARCHER": ["research_report", "insights"]
        }
        
        return output_map.get(agent, ["result"])
    
    def _get_step_timeout(self, agent: str) -> int:
        """Get timeout for a step based on agent."""
        timeouts = {
            "HUNTER": 600,      # 10 min (scraping is slow)
            "ENRICHER": 300,    # 5 min
            "SEGMENTOR": 120,   # 2 min
            "CRAFTER": 300,     # 5 min
            "GATEKEEPER": 3600, # 1 hour (waiting for approval)
            "OPERATOR": 300,    # 5 min
            "SCHEDULER": 60,    # 1 min
            "RESEARCHER": 300   # 5 min
        }
        return timeouts.get(agent, 300)
    
    def _determine_success_criteria(self, objective: ObjectiveType, params: Dict[str, Any]) -> str:
        """Determine success criteria for the goal."""
        pattern_key = objective.value
        if pattern_key in self.patterns:
            base_criteria = self.patterns[pattern_key]["success_criteria"]
        else:
            base_criteria = "Request analyzed and action taken"
        
        # Add specifics from params
        if "limit" in params:
            base_criteria += f" (target: {params['limit']} leads)"
        
        if "target_tier" in params:
            base_criteria += f" (focus: {params['target_tier']})"
        
        return base_criteria
    
    def _estimate_duration(self, steps: List[GoalStep]) -> int:
        """Estimate total duration in minutes."""
        total_seconds = sum(step.timeout_seconds / 2 for step in steps)  # Assume 50% of timeout
        return max(5, int(total_seconds / 60))
    
    def _calculate_priority(self, params: Dict[str, Any], context: Dict[str, Any]) -> int:
        """Calculate priority (1=highest, 5=lowest)."""
        if params.get("urgency") == "high":
            return 1
        elif params.get("urgency") == "low":
            return 4
        else:
            return 2
    
    def _requires_approval(self, objective: ObjectiveType, params: Dict[str, Any]) -> bool:
        """Determine if the goal requires human approval."""
        always_approve = {
            ObjectiveType.SEND_OUTREACH,
            ObjectiveType.CREATE_CAMPAIGN
        }
        
        return objective in always_approve
    
    def _generate_intent_description(self, objective: ObjectiveType, params: Dict[str, Any]) -> str:
        """Generate a human-readable intent description."""
        descriptions = {
            ObjectiveType.DISCOVER_LEADS: "Find and scrape new leads from specified sources",
            ObjectiveType.ENRICH_LEADS: "Enrich existing leads with additional data",
            ObjectiveType.QUALIFY_LEADS: "Score and tier leads based on ICP criteria",
            ObjectiveType.CREATE_CAMPAIGN: "Generate personalized outreach campaign",
            ObjectiveType.SEND_OUTREACH: "Execute email outreach campaign",
            ObjectiveType.SCHEDULE_MEETING: "Schedule a meeting or appointment",
            ObjectiveType.RESEARCH_COMPANY: "Research a company for insights",
            ObjectiveType.ANALYZE_PIPELINE: "Analyze deal pipeline for insights",
            ObjectiveType.CUSTOM: "Process custom request"
        }
        
        base = descriptions.get(objective, "Process request")
        
        # Add context
        if "limit" in params:
            base += f" (limit: {params['limit']})"
        if "target_companies" in params:
            base += f" (targets: {', '.join(params['target_companies'])})"
        
        return base
    
    def _save_goal(self, goal: AgenticGoal):
        """Save goal for audit trail."""
        goal_file = self.storage_dir / f"{goal.goal_id}.json"
        with open(goal_file, 'w', encoding='utf-8') as f:
            json.dump(goal.to_dict(), f, indent=2)
    
    def get_goal(self, goal_id: str) -> Optional[AgenticGoal]:
        """Retrieve a saved goal."""
        goal_file = self.storage_dir / f"{goal_id}.json"
        if not goal_file.exists():
            return None
        
        with open(goal_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Reconstruct
        data["objective"] = ObjectiveType(data["objective"])
        data["steps"] = [GoalStep(**s) for s in data["steps"]]
        return AgenticGoal(**data)
    
    def list_recent_goals(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent goals."""
        goals = []
        for goal_file in sorted(self.storage_dir.glob("goal_*.json"), reverse=True)[:limit]:
            with open(goal_file, 'r', encoding='utf-8') as f:
                goals.append(json.load(f))
        return goals


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_interpreter_instance: Optional[IntentInterpreter] = None


def get_intent_interpreter() -> IntentInterpreter:
    """Get singleton instance of IntentInterpreter."""
    global _interpreter_instance
    if _interpreter_instance is None:
        _interpreter_instance = IntentInterpreter()
    return _interpreter_instance


# =============================================================================
# DEMO
# =============================================================================

async def demo():
    """Demonstrate intent interpretation."""
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    console.print("\n[bold blue]Intent Interpreter Demo[/bold blue]\n")
    
    interpreter = IntentInterpreter()
    
    test_inputs = [
        "Find 100 new leads from Gong competitors",
        "Enrich the leads we scraped yesterday",
        "Score and tier all tier_1 leads",
        "Create a campaign for tier_1 event attendees",
        "Send the approved emails urgently",
        "Schedule a meeting with the prospect",
        "Research Acme Corp for our upcoming call"
    ]
    
    for raw_input in test_inputs:
        console.print(f"\n[yellow]Input:[/yellow] {raw_input}")
        
        goal = interpreter.interpret(raw_input)
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Goal ID", goal.goal_id)
        table.add_row("Objective", goal.objective.value)
        table.add_row("Intent", goal.interpreted_intent)
        table.add_row("Steps", " → ".join(goal.agent_sequence))
        table.add_row("Duration", f"{goal.estimated_duration_minutes} min")
        table.add_row("Requires Approval", str(goal.requires_approval))
        table.add_row("Success Criteria", goal.success_criteria)
        
        console.print(table)
    
    console.print("\n[green]Demo complete![/green]")


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo())
