# CAIO Alpha Swarm Handoff: Redis + Inngest Setup (Non-Technical PTO/GTM)

Date: February 11, 2026  
Owner: Product Technical Officer (PTO) + GTM Operator  
Purpose: Finalize major runtime inputs before continuing CAIO hardening and full Golden Set replay.

---

## 1) Executive Summary

Backend implementation is **largely ready**, but environment/runtime configuration is **not yet complete** for strict production reliability.

### Current Assessment

Implemented in backend:
- Runtime dependency health model (`redis` + `inngest`) exists.
- `/api/runtime/dependencies` endpoint exists.
- `/api/health/ready` blocks when required dependencies are unhealthy.
- Bootstrap script exists to generate/update runtime env config.
- Validator exists for env and dependency checks.

Not yet complete in current runtime:
- `REDIS_URL` not configured.
- `INNGEST_SIGNING_KEY` + `INNGEST_EVENT_KEY` not configured.
- `INNGEST_WEBHOOK_URL` not configured.
- Strict policy not enforced (`REDIS_REQUIRED` and `INNGEST_REQUIRED` currently not set true in local `.env`).
- Local Python environment currently does not have `inngest` package installed.

Conclusion:
- **Code path is ready**, but **production readiness is blocked by missing PTO inputs and runtime env configuration**.

---

## 2) Evidence Snapshot (What Was Verified)

Verified files and routes:
- `core/runtime_reliability.py`
- `scripts/bootstrap_runtime_reliability.py`
- `scripts/validate_runtime_env.py`
- `dashboard/health_app.py`:
  - `/api/runtime/dependencies`
  - `/api/health/ready`
  - Inngest mount-state tracking

Validation result in current env:
- `python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections`
- Result: `PASS`, but only because required flags are not enforced and Redis/Inngest are not configured.

Package check in current local runtime:
- `redis` package: present
- `inngest` package: missing

---

## 3) Major Inputs Required from PTO (Must Be Confirmed)

1. `REDIS_URL` (staging + production).
2. `INNGEST_SIGNING_KEY` and `INNGEST_EVENT_KEY`.
3. Final production `INNGEST_WEBHOOK_URL` (format: `https://<your-domain>/inngest`).
4. Strict startup policy decision:
   - Enforce now: `REDIS_REQUIRED=true` and `INNGEST_REQUIRED=true`
   - Delay enforcement temporarily: one or both `false`

Recommended policy:
- Staging: enforce now (`true/true`) to mirror production.
- Production: enforce now (`true/true`) for fail-fast reliability.

---

## 4) Non-Technical Step-by-Step Execution Plan

## Step 1: Collect values from PTO

Use this message:

```text
Please confirm final CAIO runtime inputs:

1) REDIS_URL
   - Staging:
   - Production:

2) Inngest keys
   - INNGEST_SIGNING_KEY:
   - INNGEST_EVENT_KEY:

3) Production INNGEST_WEBHOOK_URL
   - Expected format: https://<your-domain>/inngest

4) Policy decision
   - Enforce strict startup now? (REDIS_REQUIRED=true and INNGEST_REQUIRED=true)
```

## Step 2: Update deployment environment variables

In your hosting platform (Railway/Render/etc), open:
- Service -> Settings -> Variables (Environment)

Set for each environment:

```text
REDIS_URL=<from PTO>
REDIS_REQUIRED=true|false
REDIS_MAX_CONNECTIONS=50
RATE_LIMIT_REDIS_NAMESPACE=caio:<env>:ratelimit
CONTEXT_REDIS_PREFIX=caio:<env>:context
CONTEXT_STATE_TTL_SECONDS=3600 (staging) / 7200 (production)

INNGEST_SIGNING_KEY=<from PTO>
INNGEST_EVENT_KEY=<from PTO>
INNGEST_REQUIRED=true|false
INNGEST_APP_ID=caio-alpha-swarm-<env>
INNGEST_APP_NAME=CAIO Alpha Swarm
INNGEST_WEBHOOK_URL=<from PTO>

TRACE_ENVELOPE_FILE=.hive-mind/traces/tool_trace_envelopes_<env>.jsonl
TRACE_ENVELOPE_ENABLED=true
TRACE_RETENTION_DAYS=30
TRACE_CLEANUP_ENABLED=true
```

Replace `<env>` with `staging` or `production`.

## Step 3: Save and redeploy

- Save variables.
- Redeploy/restart both staging and production.

This is mandatory; new env variables do not apply until restart/redeploy.

## Step 4: Validate with command-line checks

From repo root:

```powershell
cd d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm
```

Run staging:

```powershell
python scripts/validate_runtime_env.py --mode staging --env-file .env.staging --check-connections
```

Run production:

```powershell
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections
```

Optional strict route verification:

```powershell
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections --verify-inngest-route
```

Expected: `Result: PASS`

## Step 5: Validate running API endpoints

After deployment:

1. `GET /api/runtime/dependencies?token=<DASHBOARD_AUTH_TOKEN>`
2. `GET /api/health/ready`

Expected:
- Runtime dependencies report `ready: true`
- Readiness endpoint returns HTTP `200`

## Step 6: Only then continue hardening/evaluation

When all above pass:

```powershell
python scripts/replay_harness.py --min-pass-rate 0.95
```

---

## 5) What to Feed Claude (Copy/Paste Prompt)

Use this prompt in Claude after you have PTO values:

```text
I need you to guide me step by step as a non-technical PTO/GTM operator.

Context:
- Repository: d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm
- Goal: configure Redis and Inngest runtime inputs and verify readiness.
- Inputs:
  - STAGING_REDIS_URL=<...>
  - PRODUCTION_REDIS_URL=<...>
  - INNGEST_SIGNING_KEY=<...>
  - INNGEST_EVENT_KEY=<...>
  - INNGEST_WEBHOOK_URL=<...>
  - STRICT_POLICY=<true/false> for REDIS_REQUIRED and INNGEST_REQUIRED

Please do the following in order:
1) Show exactly what env keys I should set for staging and production.
2) Give me copy/paste commands to run bootstrap + validation.
3) Tell me how to verify /api/runtime/dependencies and /api/health/ready.
4) Stop after each step and ask me to paste the output before moving on.
```

---

## 6) Decision Gate: Go / No-Go

Go:
- PTO confirmed all 4 inputs.
- Variables applied in both environments.
- Validation commands PASS.
- `/api/runtime/dependencies` ready.
- `/api/health/ready` returns 200.

No-Go:
- Any required key missing while strict policy is true.
- Redis connection check fails.
- Inngest route/keys fail.
- Readiness endpoint returns 503.

---

## 7) Risks If You Skip This

- False confidence from local PASS with non-strict config.
- Runtime instability under load (rate limiting/context state fallback).
- Scheduler/orchestration drift due missing Inngest runtime setup.
- Regression gate results become less trustworthy.

---

## 8) Completion Template (Send to Leadership)

```text
CAIO Redis/Inngest setup completed.

Environment: [staging/production]
REDIS_REQUIRED: [true/false]
INNGEST_REQUIRED: [true/false]

Checks:
- validate_runtime_env: PASS
- /api/runtime/dependencies: ready=true
- /api/health/ready: 200

Open issues:
- [none OR list]
```
