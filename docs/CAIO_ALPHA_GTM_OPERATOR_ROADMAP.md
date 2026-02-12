# CAIO Alpha Swarm: GTM Operator Roadmap (Non-Technical)

Date: February 9, 2026  
Audience: GTM engineer / operator (non-technical) and Product Technical Officer.

## 1) What Has Already Been Accomplished

Completed in the current implementation cycle:

1. Regression safety gate is live in CI.
- File: `.github/workflows/replay-harness.yml`
- Build now runs Golden Set replay and blocks on score drop.

2. Deterministic trace logging is now standardized.
- Runtime now emits structured trace envelopes with:
  - `correlation_id`
  - `case_id`
  - `agent`
  - `tool_name`
  - `tool_input_summary`
  - `tool_output_summary`
  - `retrieved_context_refs`
  - `status`
  - `duration_ms`
  - `error_code` and `error_message`

3. Runtime reliability hardening completed for hot paths.
- Rate limiting and session state now support Redis-first behavior with safe fallback.
- Key audit writes were hardened with lock + atomic write behavior.
- Silent exception handling in critical paths was replaced with structured logging.

4. Inngest path is active and helper stubs are upgraded.
- `/inngest` route mounted in dashboard app.
- Scheduler helper flows now call gateway-backed logic with error handling.

5. Deterministic tests were added.
- Trace envelope tests.
- Queue lifecycle audit consistency tests.
- Runtime hardening tests.

## 2) Confirmed Decisions (Now Active)

The following decisions are now treated as the default operating policy:

1. Replay gate threshold is `95%` minimum pass rate.
2. Critical evaluation failures are hard-fail conditions.
3. Redis + Inngest are part of the production reliability baseline.
4. Router split/parity testing remains the next engineering milestone.

## 3) Immediate Next Steps (Operator Checklist)

## Step A: Configure Environment Variables

Use `.env.example` and `.env.staging.example` as source templates.

Required for reliability:
- `REDIS_URL`
- `REDIS_REQUIRED`
- `RATE_LIMIT_REDIS_NAMESPACE`
- `CONTEXT_REDIS_PREFIX`
- `CONTEXT_STATE_TTL_SECONDS`
- `INNGEST_SIGNING_KEY`
- `INNGEST_EVENT_KEY`
- `INNGEST_REQUIRED`
- `TRACE_ENVELOPE_FILE`

Recommended values:
- Production:
  - `REDIS_REQUIRED=true`
  - `INNGEST_REQUIRED=true`
- Staging:
  - also set both to `true` to mirror production behavior.

## Step B: Run Environment Validation

From repo root:

```powershell
python scripts/validate_runtime_env.py --mode staging --env-file .env.staging --check-connections
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections
```

Expected result:
- Output ends with `Result: PASS`.

If it fails:
- Fill missing keys shown in output.
- Re-run the same command until it passes.

## Step C: Validate Replay Gate

```powershell
python scripts/replay_harness.py --min-pass-rate 0.95
```

Expected result:
- Pass rate >= `0.95`.
- `block_build: false`.

## Step D: Validate Runtime Endpoints

After deployment:

1. Check dashboard health endpoint.
2. Verify `/inngest` is mounted and reachable.
3. Confirm trace file is being updated.
4. Confirm Redis connection check passes in runtime logs.

## 4) Recommended Best Next Steps (Next 2 Weeks)

1. Complete router split of `dashboard/health_app.py`.
- Target modules:
  - `routers/health.py`
  - `routers/emails.py`
  - `routers/queue.py`
  - `routers/webhooks.py`
  - `routers/call_prep.py`

2. Add endpoint parity tests.
- Every existing endpoint must return same payload contract after split.

3. Enforce release scorecard ceremony.
- Weekly review: pass rate, groundedness failures, negative constraint violations.

4. Expand Golden Set (v2).
- Add scenarios based on real production misses from last 2 weeks.

## 5) Inputs Still Needed From Product Technical Officer

Use `docs/CAIO_ALPHA_MAJOR_INPUTS_REQUIRED.md` as the source list.

Priority inputs still needed to improve quality:

1. Trace retention policy (14/30/90 days).
2. Scorecard sign-off owner and release cutoff process.
3. Simulation boundary (what remains simulated vs production-real).

## 6) Inputs Still Needed From Head of Sales

1. Deterministic approval rubric (explicit pass/fail checklist).
2. Rejection taxonomy with examples.
3. Segment-specific messaging standards.
4. SLA targets for approval and queue aging.
5. Meeting prep quality bar and confidence threshold.

## 7) Weekly Operator Rhythm

Monday:
- Run replay harness and publish pass-rate snapshot.

Wednesday:
- Review rejects/edits with HoS and map to taxonomy.

Friday:
- Release readiness check:
  - Replay pass rate
  - Critical failures
  - Queue health
  - Scheduler success

## 8) Escalation Rules

Escalate same day if any occurs:

1. Replay pass rate < `95%`.
2. Any groundedness hard-fail cases.
3. Redis connection unavailable while `REDIS_REQUIRED=true`.
4. Inngest keys missing while `INNGEST_REQUIRED=true`.
5. Queue aging exceeds agreed SLA.
