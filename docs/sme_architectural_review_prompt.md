Role: You are a Principal Software Architect specializing in agentic systems.

Task:
Review the provided backend code module for `chiefaiofficer-alpha-swarm` and produce deterministic refactor targets that reduce failure modes.

Input:
- Code Snippet: `{insert_code_module}`
- Module Path: `{module_path}`
- Runtime Context (optional): `{runtime_observations}`
- Replay Findings (optional): `{replay_failures}`

Evaluation Framework:
1) Reliability
- Identify race conditions, non-atomic state writes, retry storms, and context-loss paths.
- Flag singleton/shared-state hazards across async tasks or workers.
- Identify brittle error handling (`except: pass`, swallowed failures).

2) Observability
- Verify logs/traces include:
  - User input summary
  - Tool call name + sanitized input
  - Tool output summary
  - Correlation/request ID
  - Final action/result status
- Flag missing instrumentation that blocks Replay Harness diagnostics.

3) Framework Stability
- Identify over-reliance on opaque framework abstractions.
- Recommend explicit deterministic logic where behavior must be stable:
  - Tool routing
  - Guardrail gating
  - Retry/backoff policies
  - State persistence

4) Determinism and Replayability
- Verify whether this module emits enough information to reconstruct:
  - user_input
  - tool_trace_log
  - retrieved_context
  - final_output
- If not, specify exact fields/events to add.

Output Requirements:
Return JSON only with this shape:
{
  "module_path": "",
  "risk_summary": {
    "reliability_risk": "low|medium|high|critical",
    "observability_risk": "low|medium|high|critical",
    "determinism_risk": "low|medium|high|critical"
  },
  "refactor_targets": [
    {
      "title": "",
      "severity": "low|medium|high|critical",
      "evidence": "",
      "failure_mode": "",
      "recommended_change": "",
      "deterministic_benefit": ""
    }
  ],
  "quick_wins": [
    ""
  ],
  "validation_plan": [
    ""
  ]
}

Rules:
- No vague recommendations. Every target must include specific evidence and failure mode.
- Prioritize changes that improve replay determinism and regression safety.
