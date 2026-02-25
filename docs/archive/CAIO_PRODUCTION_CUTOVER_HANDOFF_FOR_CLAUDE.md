# CAIO Alpha Swarm — Claude Handoff (v4.5 Aligned)

Date: 2026-02-17  
Audience: PTO / GTM (non-technical), assisted by Claude Code  
Source of Truth: `CAIO_IMPLEMENTATION_PLAN.md` (v4.5)

---

## 1) Current State Snapshot

CAIO is in **Phase 4 (Autonomy Graduation)** with:

- `4A + 4C + 4D + 4F + 4G` complete
- `4B` infra mostly complete, operational warmup pending
- `4E` ramp active, awaiting first supervised live dispatch
- `4H` deep review hardening follow-up in progress

Already implemented in code:

1. Strict API auth middleware for protected `/api/*`.
2. Immutable Gatekeeper batch execution scope (preview hash + expiry + one-time execution).
3. Duplicate-send and dedup hardening (canonical email keys + GHL-sent exclusion).
4. Redis state store with dual-read cutover and live dispatch locks.
5. Deterministic auth smoke gate script (`scripts/endpoint_auth_smoke.py`).
6. Deep review hardening:
   - constant-time token checks (`hmac.compare_digest`)
   - `OPTIONS` preflight pass-through in auth middleware
   - Instantly control-route auth tests

---

## 2) Critical Revalidation Requirement

The previous dashboard token appeared in documentation history and must be treated as compromised.

**Mandatory before rigorous testing:**

1. Rotate staging `DASHBOARD_AUTH_TOKEN`.
2. Rotate production `DASHBOARD_AUTH_TOKEN`.
3. Redeploy both environments.
4. Re-run deployed auth smoke on both environments with new tokens.

Do not proceed to autonomy graduation gates without this.

---

## 3) PTO Inputs Required (Major Inputs)

Provide/confirm:

1. New staging `DASHBOARD_AUTH_TOKEN`
2. New production `DASHBOARD_AUTH_TOKEN`
3. Staging `CORS_ALLOWED_ORIGINS` explicit allowlist
4. Production `CORS_ALLOWED_ORIGINS` explicit allowlist
5. Strict flags (both envs):
   - `DASHBOARD_AUTH_STRICT=true`
   - `REDIS_REQUIRED=true`
   - `INNGEST_REQUIRED=true`
6. Final deployed base URLs:
   - `https://<staging-domain>`
   - `https://<production-domain>`

---

## 4) Click-by-Click Navigation (Railway + Inngest)

## A) Railway variables (staging first, then production)

1. Open Railway dashboard.
2. Project: `caio-swarm-dashboard`.
3. Select environment: `staging`.
4. Service: `caio-swarm-dashboard`.
5. Open `Variables`.
6. Set/update:
   - `DASHBOARD_AUTH_TOKEN=<new token>`
   - `DASHBOARD_AUTH_STRICT=true`
   - `CORS_ALLOWED_ORIGINS=https://<allowed-origin-1>,https://<allowed-origin-2>`
   - `REDIS_REQUIRED=true`
   - `INNGEST_REQUIRED=true`
7. Confirm required runtime keys remain set:
   - `REDIS_URL`
   - `INNGEST_SIGNING_KEY`
   - `INNGEST_EVENT_KEY`
   - `INNGEST_WEBHOOK_URL` (ends with `/inngest`)
8. Save and redeploy.
9. Repeat for `production`.

## B) Inngest verification

1. Open `https://app.inngest.com`.
2. Select matching app/workspace for staging/production.
3. Confirm keys and endpoint URL align with Railway:
   - `INNGEST_SIGNING_KEY`
   - `INNGEST_EVENT_KEY`
   - `https://<domain>/inngest`

---

## 5) Command Execution Order (Claude must follow exactly)

Run from:

```powershell
cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
```

1. Runtime environment validation:

```powershell
python scripts/validate_runtime_env.py --mode staging --env-file .env.staging --check-connections
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections
```

2. Deployed endpoint auth smoke (strict no-go gate):

```powershell
python scripts/endpoint_auth_smoke.py --base-url "https://<staging-domain>" --token "<NEW_STAGING_DASHBOARD_AUTH_TOKEN>"
python scripts/endpoint_auth_smoke.py --base-url "https://<production-domain>" --token "<NEW_PROD_DASHBOARD_AUTH_TOKEN>"
```

Expected checks:

- `/api/operator/status` unauth -> `401`
- `/api/operator/trigger` unauth -> `401`
- `/api/health/ready` unauth -> `200`
- `/api/operator/status?token=...` -> non-`401`
- `/api/operator/status` with header token -> non-`401`

3. Redis migration verification:

```powershell
python scripts/migrate_file_state_to_redis.py --hive-dir .hive-mind
```

4. Replay gate:

```powershell
python scripts/replay_harness.py --min-pass-rate 0.95
```

5. Critical pytest gate (current pack + new Instantly auth tests):

```powershell
python -m pytest -q `
  tests/test_gatekeeper_integration.py `
  tests/test_runtime_reliability.py `
  tests/test_runtime_determinism_flows.py `
  tests/test_trace_envelope_and_hardening.py `
  tests/test_replay_harness_assets.py `
  tests/test_operator_batch_snapshot_integrity.py `
  tests/test_operator_dedup_and_send_path.py `
  tests/test_state_store_redis_cutover.py `
  tests/test_instantly_webhook_auth.py
```

6. Operator dry-run safety:

```powershell
python -m execution.operator_outbound --motion outbound --dry-run --json
python -m execution.operator_outbound --motion all --dry-run --json
```

---

## 6) If All Gates Pass: Move to First Supervised Live Dispatch

1. Run fresh production pipeline:

```powershell
echo yes | python execution/run_pipeline.py --mode production
```

2. Review/approve tier-1 leads in HoS dashboard (`/sales`).
3. Execute first live dispatch:

```powershell
python -m execution.operator_outbound --motion outbound --live
```

4. Approve Gatekeeper batch.
5. Activate drafted campaign in Instantly UI.
6. Hold 3 clean supervised days before ramp graduation.

---

## 7) GO / NO-GO Criteria

GO only if all true:

1. Runtime env validation passes for staging and production.
2. Auth smoke passes for staging and production (post-rotation).
3. Redis migration returns `ok=true`.
4. Replay harness remains >=95%.
5. Critical pytest pack has zero failures.
6. No protected endpoint is accessible without token.

If any fail: NO-GO, stop and fix before live dispatch.

---

## 8) Remaining Engineering Next Steps (Track in v4.5)

1. Add strict webhook authentication for non-API webhooks:
   - `/webhooks/heyreach`
   - `/webhooks/clay`
   - `/webhooks/rb2b`
2. Add readiness hard-fail when required webhook secrets are missing in strict production mode.
3. After stable Redis period, disable file fallback in production (`STATE_DUAL_READ_ENABLED=false`).

---

## 9) Claude Prompt (Copy/Paste)

```text
You are executing CAIO v4.5 cutover and revalidation.
Follow docs/CAIO_PRODUCTION_CUTOVER_HANDOFF_FOR_CLAUDE.md exactly.

Rules:
1) Use CAIO_IMPLEMENTATION_PLAN.md as source of truth.
2) Do not use or display old tokens from docs/history.
3) Require new staging/prod DASHBOARD_AUTH_TOKEN values before auth smoke.
4) Run commands in section 5 in exact order.
5) Stop only when a PTO secret/decision is required.

Deliverables:
- Per-step PASS/FAIL with command output summary.
- Final verdict: GO / NO-GO.
- If NO-GO, list exact failed checks and minimal fix actions.
```

---

## 10) Final Loop-Back Needed from PTO

Before rigorous testing/autonomy progression, confirm:

1. New staging and production `DASHBOARD_AUTH_TOKEN` values are deployed.
2. `CORS_ALLOWED_ORIGINS` is explicitly set in both environments.
3. Strict flags are active in both environments.
4. You approve running deployed auth smoke against real URLs/tokens now.
