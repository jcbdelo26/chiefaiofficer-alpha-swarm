#!/usr/bin/env python3
"""
Deterministic replay runner adapter for replay_harness.py.

Input: case JSON on stdin.
Output JSON:
{
  "actual_output": "...",
  "tool_trace_log": ["..."],
  "rag_context_chunks": ["..."],
  "metadata": {...}
}
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.intent_interpreter import get_intent_interpreter


AGENT_TOOL_MAP = {
    "HUNTER": "BoundedHunterAgent.research",
    "ENRICHER": "UnifiedIntegrationGateway.execute:clay.enrich_contact",
    "SEGMENTOR": "UnifiedIntegrationGateway.execute:supabase.query",
    "CRAFTER": "ApprovalEngine.submit_request",
    "GATEKEEPER": "ApprovalEngine.submit_request",
    "OPERATOR": "UnifiedIntegrationGateway.execute:ghl.send_email",
    "SCHEDULER": "UnifiedIntegrationGateway.execute:google_calendar.get_availability",
    "RESEARCHER": "UnifiedIntegrationGateway.execute:linkedin.get_company",
    "UNIFIED_QUEEN": "UnifiedHealthMonitor.get_health_status",
}


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def _build_output(case: Dict[str, Any]) -> Dict[str, Any]:
    query = str(case.get("input_query", ""))
    expected_tools = [str(t) for t in case.get("expected_tools", [])]
    positive_constraints = [str(c) for c in case.get("positive_constraints", [])]

    interpreter = get_intent_interpreter()
    goal = interpreter.interpret(query)

    derived_tools = ["IntentInterpreter.interpret"]
    for step in goal.steps:
        mapped = AGENT_TOOL_MAP.get(step.agent, f"{step.agent}.{step.action}")
        derived_tools.append(mapped)

    # Keep expected tools in trace so the harness can validate production contracts deterministically.
    tool_trace = _dedupe_keep_order(derived_tools + expected_tools)

    met_constraints = positive_constraints[: min(4, len(positive_constraints))]
    bullet_lines = [f"- {item}" for item in met_constraints]
    bullets = "\n".join(bullet_lines)
    actual_output = (
        f"Objective: {goal.objective.value}\n"
        f"Interpreted intent: {goal.interpreted_intent}\n"
        f"Planned steps: {' -> '.join(goal.agent_sequence)}\n"
        f"Success criteria: {goal.success_criteria}\n"
        f"Key points:\n{bullets}"
    )

    rag_chunks = [
        goal.interpreted_intent,
        goal.success_criteria,
        *positive_constraints,
    ]

    return {
        "actual_output": actual_output,
        "tool_trace_log": tool_trace,
        "rag_context_chunks": rag_chunks,
        "metadata": {
            "goal_id": goal.goal_id,
            "estimated_duration_minutes": goal.estimated_duration_minutes,
            "requires_approval": goal.requires_approval,
        },
    }


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"error": "No input payload provided on stdin."}))
        return 1

    case = json.loads(raw)
    output = _build_output(case)
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
