# CAIO Alpha Swarm — Production Cutover Handoff (Claude-Assist Ready)

Date: 2026-02-17  
Audience: PTO / GTM (non-technical), assisted by Claude Code  
Source of Truth: `CAIO_IMPLEMENTATION_PLAN.md` (v4.4)

---

## 1) Objective

Finish production cutover inputs and verify strict runtime/auth behavior before rigorous testing and autonomy progression.

This runbook operationalizes the remaining post-P0 checklist:

1. Finalize production/staging `DASHBOARD_AUTH_TOKEN`.
2. Finalize production/staging `CORS_ALLOWED_ORIGINS`.
3. Confirm strict runtime flags:
   - `DASHBOARD_AUTH_STRICT=true`
   - `REDIS_REQUIRED=true`
   - `INNGEST_REQUIRED=true`
4. Run deployed endpoint auth smoke.
5. Run one-time Redis state migration.
6. Re-run validation/replay gates.

---

## 2) PTO Inputs Required (Major Inputs)

You must provide final values for:

1. `DASHBOARD_AUTH_TOKEN` (staging + production, different tokens recommended).
2. `CORS_ALLOWED_ORIGINS` (explicit allowlist, comma-separated, no wildcard).
3. Production/staging strict-mode confirmation:
   - `DASHBOARD_AUTH_STRICT=true`
   - `REDIS_REQUIRED=true`
   - `INNGEST_REQUIRED=true`
4. Final deployed base URLs:
   - `https://<staging-domain>`
   - `https://<production-domain>`

If any of these are missing, do not proceed to rigorous testing.

---

## 3) Click-by-Click Navigation (Railway + Inngest)

## A. Railway: set env vars (staging first)

1. Open Railway dashboard.
2. Open project `caio-swarm-dashboard`.
3. Select environment `staging`.
4. Open service `caio-swarm-dashboard`.
5. Go to `Variables`.
6. Set/update:
   - `DASHBOARD_AUTH_TOKEN=<staging token>`
   - `DASHBOARD_AUTH_STRICT=true`
   - `CORS_ALLOWED_ORIGINS=https://<staging-frontend-domain>,https://<other-allowed-origin>`
   - `REDIS_REQUIRED=true`
   - `INNGEST_REQUIRED=true`
7. Confirm existing runtime keys are present:
   - `REDIS_URL`
   - `INNGEST_SIGNING_KEY`
   - `INNGEST_EVENT_KEY`
   - `INNGEST_WEBHOOK_URL` (must end with `/inngest`)
8. Save variables.
9. Trigger redeploy/restart.

Repeat the same steps for `production` with production values.

## B. Inngest: quick verification

1. Open `https://app.inngest.com`.
2. Select correct app/workspace for staging/production.
3. Confirm signing key/event key match what Railway has.
4. Confirm app endpoint URL is `https://<domain>/inngest`.

---

## 4) Command Sequence (Run Exactly in Order)

From:

```powershell
cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
```

## A. Validate runtime env files

```powershell
python scripts/validate_runtime_env.py --mode staging --env-file .env.staging --check-connections
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections
```

Expected: both return PASS.

## B. Deployed endpoint auth smoke (strict no-go gate)

Use new deterministic checker:

```powershell
python scripts/endpoint_auth_smoke.py --base-url "https://<staging-domain>" --token "<STAGING_DASHBOARD_AUTH_TOKEN>"
python scripts/endpoint_auth_smoke.py --base-url "https://<production-domain>" --token "<PROD_DASHBOARD_AUTH_TOKEN>"
```

Expected pass conditions:

1. `/api/operator/status` unauth -> `401`
2. `/api/operator/trigger` unauth -> `401`
3. `/api/health/ready` unauth -> `200`
4. `/api/operator/status?token=...` -> non-`401`
5. `/api/operator/status` with header token -> non-`401`

## C. One-time state migration to Redis

```powershell
python scripts/migrate_file_state_to_redis.py --hive-dir .hive-mind
```

Expected: summary has `"ok": true`.

## D. Replay gate

```powershell
python scripts/replay_harness.py --min-pass-rate 0.95
```

Expected: pass rate `>= 0.95`, `block_build=false`.

---

## 5) Claude Prompt (Copy/Paste)

Use this in Claude Code to guide your execution:

```text
You are assisting production cutover for CAIO Alpha Swarm.
Follow docs/CAIO_PRODUCTION_CUTOVER_HANDOFF_FOR_CLAUDE.md exactly.

Tasks:
1) Validate required PTO inputs are present (DASHBOARD_AUTH_TOKEN, CORS_ALLOWED_ORIGINS, strict flags).
2) Walk me click-by-click in Railway for staging then production variables.
3) Run runtime validation commands and explain any failures with exact fixes.
4) Run scripts/endpoint_auth_smoke.py for staging and production and interpret results.
5) Run scripts/migrate_file_state_to_redis.py --hive-dir .hive-mind.
6) Run replay harness gate and summarize go/no-go.

Output requirements:
- Show each command before running it.
- Stop and ask me only when a secret value or final business decision is required.
- At end, provide a cutover verdict: GO / NO-GO with failed checks listed.
```

---

## 6) GO / NO-GO Criteria for Rigorous Testing

Proceed to rigorous testing only if all are true:

1. Runtime env validation passes in staging + production.
2. Endpoint auth smoke passes in staging + production.
3. Redis migration reports success (`ok=true`).
4. Replay harness remains >=95% pass.
5. No protected endpoint is reachable without token.

If any fail: NO-GO, fix and rerun gates.

---

## 7) Fast Troubleshooting Map

1. Auth smoke fails on unauth protected route not returning `401`:
   - Check `DASHBOARD_AUTH_TOKEN` is set.
   - Check `DASHBOARD_AUTH_STRICT=true`.
   - Redeploy service.
2. Auth smoke fails on token route returning `401`:
   - Token mismatch (copy exact value again).
   - Try header and query token forms.
3. Health ready not `200`:
   - Check runtime required keys exist (`REDIS_URL`, Inngest keys).
   - Run `validate_runtime_env.py --check-connections`.
4. Migration not ok:
   - Verify Redis connectivity.
   - Re-run with same command and inspect `"errors"` array.

---

## 8) Final Loop-Back Needed from PTO

Before final autonomy testing, confirm these explicitly:

1. Final staging and production `DASHBOARD_AUTH_TOKEN` values are set.
2. Final staging and production `CORS_ALLOWED_ORIGINS` values are set.
3. Strict flags are enforced in deployed env:
   - `DASHBOARD_AUTH_STRICT=true`
   - `REDIS_REQUIRED=true`
   - `INNGEST_REQUIRED=true`
4. You approve running deployed auth smoke against real URLs/tokens now.
