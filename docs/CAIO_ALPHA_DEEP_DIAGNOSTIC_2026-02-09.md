# CAIO Alpha Swarm Deep Diagnostic (2026-02-09)

## Scope and Source-of-Truth Alignment

This diagnostic uses the handoff file:

- `C:\Users\ADMIN\.gemini\antigravity\brain\74905acf-723a-4cdc-8b03-49400b9007e2\codex_handoff.md.resolved`

and validates claims against the live repo at:

- `chiefaiofficer-alpha-swarm`

## Current Snapshot (Validated)

- Core modules: `73` Python files in `core/`.
- JSON state files: `210` JSON files under `.hive-mind/`.
- `rate_limits.json` size: `1,809,343` bytes (`~1.8 MB`).
- JSON/file I/O hotspots: `471` occurrences of `open/json.load/json.dump` across `core/` and `dashboard/`.
- Swallowed exceptions (`except ...: pass`): `108` occurrences across `core/` and `dashboard/`.

## High-Severity Findings

1. Production replay/regression gate is non-blocking and partially broken.
- Evidence:
  - `scripts/regression_test.py:46` calls `queen.process_task(...)`.
  - `execution/unified_queen_orchestrator.py` has no `process_task` function.
  - `scripts/regression_test.py:78` hardcodes `return True` in validation.
  - `scripts/regression_test.py:80` still points to old 4-case schema file.
- Impact:
  - Regression suite can pass without asserting behavior.
  - Breakages can ship undetected.

2. Inngest scheduler exists but is not mounted to FastAPI.
- Evidence:
  - Scheduler middleware exists in `core/inngest_scheduler.py:300` (`get_inngest_serve()`).
  - No `/inngest` route/mount in `dashboard/health_app.py`.
  - Scheduler helpers still contain TODO stubs (`core/inngest_scheduler.py:174`, `180`, `186`, `203`, `225`, `286`, `292`).
- Impact:
  - Cron/event functions are defined but not operationally wired.
  - Scheduled reliability claims are overstated in runtime behavior.

3. File-backed shared state is non-atomic in core guardrails/rate limiting paths.
- Evidence:
  - `core/unified_guardrails.py:471` uses `.hive-mind/rate_limits.json`.
  - State load/save with plain file I/O at `core/unified_guardrails.py:484-497`.
  - Silent load failure at `core/unified_guardrails.py:489`.
- Impact:
  - Race conditions under concurrent workers.
  - State corruption/loss is possible during write contention.

4. Multiple critical paths suppress errors, reducing diagnosability.
- Evidence:
  - `dashboard/health_app.py:703`, `881`, `1019`, `1065`, `1079`, `1091`, `1093`.
  - Hook/audit suppression in `core/unified_guardrails.py:595`, `604`, `746`.
- Impact:
  - Hidden failure modes and false-positive success responses.
  - Replay harness cannot deterministically attribute root causes.

## Medium-Severity Findings

1. `health_app.py` remains monolithic and operationally coupled.
- Evidence:
  - Single file handles auth, queue ops, approvals, webhooks, readiness, and dashboards:
    - `dashboard/health_app.py:129` FastAPI app definition
    - `dashboard/health_app.py:669` pending queue
    - `dashboard/health_app.py:709` approve flow
    - `dashboard/health_app.py:919` reject flow
    - `dashboard/health_app.py:1030` queue status
    - `dashboard/health_app.py:1118` readiness
- Impact:
  - High blast radius for changes.
  - Difficult to isolate endpoint behavior for replay tests.

2. Auth model allows insecure fallback behavior.
- Evidence:
  - Hardcoded legacy token: `dashboard/health_app.py:104`.
  - Query-string token auth in `dashboard/health_app.py:106-121`.
  - Open access when auth env is missing (`dashboard/health_app.py:111-115`).
- Impact:
  - Increased leakage risk in URLs/logs.
  - Inconsistent enforcement between environments.

3. Context persistence remains single-file and unguarded.
- Evidence:
  - Saves context directly to JSON: `core/context_manager.py:514-515`.
  - Restores directly from JSON: `core/context_manager.py:540-541`.
  - No locking/atomic write strategy in class lifecycle.
- Impact:
  - Concurrent write/read races.
  - Session-state drift under load.

4. Failsafe persistence writes multiple shared files without write coordination.
- Evidence:
  - Fallback activations write: `core/multi_layer_failsafe.py:1075-1076`.
  - Escalation queue write: `core/multi_layer_failsafe.py:1149-1154`.
  - Consensus history write: `core/multi_layer_failsafe.py:1472-1473`.
  - Singleton global instance: `core/multi_layer_failsafe.py:1794-1803`.
- Impact:
  - Potential interleaving races in multi-worker deployment.
  - Hard-to-reproduce state bugs.

5. Integration adapters are partially stubbed in runtime path.
- Evidence:
  - `core/unified_integration_gateway.py:183`, `230`, `269`, `411`, `442`, `473` adapters return placeholder `"status": "executed"` patterns for several integrations.
- Impact:
  - Tool trace can show success while backend side effects are not real.
  - Replay score can overestimate production readiness.

6. Unified Queen still uses simulated execution in core orchestrator path.
- Evidence:
  - `_simulate_task_execution` placeholder at `execution/unified_queen_orchestrator.py:1007-1019`.
- Impact:
  - Orchestrator validation may pass while real tool paths remain untested.

## Low-Severity Findings

1. Redis is declared but not integrated in primary core runtime paths.
- Evidence:
  - Dependency present in `requirements.txt`.
  - Core guardrails still file-backed for rate limits (`core/unified_guardrails.py:471`).
  - Redis-aware limiter exists as isolated execution utility (`execution/rate_limiter.py:81-112`) but is not referenced by core orchestration paths.
- Impact:
  - Performance and contention risks persist despite available dependency.

## Deterministic Refactor Targets

1. Replace file-backed rate-limiter state with Redis atomic counters.
- Replace:
  - `core/unified_guardrails.py:471-497`
- Outcome:
  - Deterministic concurrent limits, low-latency reads, no JSON contention.

2. Mount Inngest middleware and implement TODO helpers with hard failures on missing dependencies.
- Wire:
  - `core/inngest_scheduler.py:get_inngest_serve()`
  - `dashboard/health_app.py` route mount for `/inngest`
- Outcome:
  - Real scheduled execution and replayable event traces.

3. Break `health_app.py` into routers (`health`, `emails`, `queue`, `webhooks`, `call_prep`).
- Replace broad `except: pass` with structured error surfaces.
- Outcome:
  - Smaller blast radius and deterministic endpoint tests.

4. Introduce a shared trace envelope for every request/tool invocation.
- Required fields:
  - `correlation_id`, `case_id`, `tool_name`, `tool_input_summary`, `tool_output_summary`, `status`, `duration_ms`.
- Outcome:
  - Replay harness can score tool routing and groundedness deterministically.

5. Convert regression runner to strict pass/fail gate.
- Replace old script behavior in `scripts/regression_test.py` with harness-backed scoring.
- Outcome:
  - Build fails on measurable score regression.

## Added Assets in This Iteration

- Golden Set (50 cases): `tests/golden/caio_alpha_golden_set_v1.json`
- SME Judge prompt: `tests/golden/sme_judge_system_prompt.md`
- SME Judge output schema: `tests/golden/sme_judge_output_schema.json`
- Replay harness: `scripts/replay_harness.py`
- Deterministic runner adapter: `scripts/swarm_replay_runner.py`
- Harness usage doc: `docs/REPLAY_HARNESS.md`
