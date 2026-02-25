# CAIO Alpha Swarm - Pre-Live Inputs Handoff for Claude

Date: 2026-02-18  
Audience: PTO / GTM (non-technical), Claude Code assistant  
Source of truth: `CAIO_IMPLEMENTATION_PLAN.md` (v4.5)

---

## 1) Current State (What is already done)

The following hardening updates are implemented in code and locally validated:

1. Strict API auth for protected `/api/*` routes (health routes remain unauthenticated).
2. Immutable Gatekeeper batch execution scope (approved IDs/hash/expiry enforced).
3. Duplicate-send protections (`sent_via_ghl` exclusion + canonical dedup).
4. Redis-backed state store with locks and dual-read cutover.
5. Non-API webhook signature enforcement for:
   - `/webhooks/instantly/*`
   - `/webhooks/heyreach`
   - `/webhooks/rb2b`
   - `/webhooks/clay`
6. Runtime readiness now includes webhook-secret dependency checks in strict mode.
7. Structured deliverability rejection audit logs added.
8. Auth smoke matrix script added for staging + production in one run.
9. Edge-case regression coverage expanded (EMERGENCY_STOP, exclusions, dry-run safety, auth parity, etc.).

---

## 2) Validation Status (latest)

All local release gates passed:

1. Replay gate:
   - `python scripts/replay_harness.py --min-pass-rate 0.95`
   - Result: `50/50`, `pass_rate=1.0`, `block_build=false`
2. Critical pytest pack:
   - Result: `77 passed, 0 failed`
3. New webhook hardening tests:
   - `tests/test_webhook_signature_enforcement.py` passed
4. Runtime webhook strictness tests:
   - `tests/test_runtime_reliability.py` webhook dependency checks passed

Operational gap still pending:

1. Deployed staging/production smoke with final rotated tokens and real domains.

---

## 3) Major Inputs Still Needed From PTO (Required)

You must provide and set these in both `staging` and `production`:

1. `DASHBOARD_AUTH_TOKEN` (new rotated value per environment)
2. `CORS_ALLOWED_ORIGINS` (explicit allowlist, comma-separated)
3. `INSTANTLY_WEBHOOK_SECRET`
4. `HEYREACH_WEBHOOK_SECRET`
5. `RB2B_WEBHOOK_SECRET`
6. `CLAY_WEBHOOK_SECRET`
7. Confirm strict flags are all `true`:
   - `DASHBOARD_AUTH_STRICT=true`
   - `REDIS_REQUIRED=true`
   - `INNGEST_REQUIRED=true`
   - `WEBHOOK_SIGNATURE_REQUIRED=true`

Also confirm these are present and valid:

1. `REDIS_URL`
2. `INNGEST_SIGNING_KEY`
3. `INNGEST_EVENT_KEY`
4. `INNGEST_WEBHOOK_URL` (must end with `/inngest`)
5. `STATE_BACKEND=redis`

---

## 4) Click-by-Click Setup (Non-Technical)

Do this for `staging`, then repeat for `production`.

1. Open Railway dashboard.
2. Open project: `caio-swarm-dashboard`.
3. Select environment (`staging` first).
4. Open service: `caio-swarm-dashboard`.
5. Open `Variables`.
6. Add/update the required variables from Section 3.
7. Save.
8. Redeploy environment.
9. Repeat for production.

Token/secret generation guidance:

1. Use password manager generator (48+ chars random).
2. Use different values for staging and production.
3. Save values in your vault before pasting.

---

## 5) Commands Claude Should Run After You Set Inputs

From:

```powershell
cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
```

1. Deployed auth smoke in one command:

```powershell
python scripts/endpoint_auth_smoke_matrix.py `
  --staging-url "https://<staging-domain>" `
  --staging-token "<NEW_STAGING_DASHBOARD_AUTH_TOKEN>" `
  --production-url "https://<production-domain>" `
  --production-token "<NEW_PROD_DASHBOARD_AUTH_TOKEN>"
```

2. Optional per-env runtime endpoint checks:

```text
GET https://<env-domain>/api/runtime/dependencies?token=<ENV_DASHBOARD_AUTH_TOKEN>
GET https://<env-domain>/api/health/ready
```

Expected:

1. Protected endpoints unauth -> `401`
2. Token-auth protected endpoints -> non-`401`
3. `/api/health/ready` -> `200`
4. Runtime dependencies: `"ready": true`
5. Runtime webhooks dependency: `"dependencies.webhooks.ready": true`

---

## 6) Copy/Paste Prompt for Claude

```text
Use docs/CAIO_HANDOFF_PRELIVE_INPUTS_FOR_CLAUDE_2026-02-18.md as the execution guide.

Goal:
1) Validate deployed staging and production after PTO input setup.
2) Run auth smoke matrix and runtime dependency checks.
3) Return GO/NO-GO with exact failing checks if any.

Rules:
1) Do not print secrets in output.
2) Stop only if a PTO value is missing.
3) If any check fails, provide minimum-fix actions and re-run plan.

Required commands:
1) python scripts/endpoint_auth_smoke_matrix.py --staging-url "<...>" --staging-token "<...>" --production-url "<...>" --production-token "<...>"
2) Verify /api/runtime/dependencies and /api/health/ready for both environments.

Output format:
1) Environment-by-environment PASS/FAIL table.
2) Final GO/NO-GO verdict.
3) Remaining PTO inputs, if any.
```

---

## 7) GO / NO-GO Criteria

GO only if all are true:

1. Staging auth smoke passes.
2. Production auth smoke passes.
3. Both environments return runtime dependencies `ready=true`.
4. Both environments show webhook dependency `ready=true`.
5. Both environments keep health readiness at `200`.

NO-GO if any fail. Fix inputs first, then re-run.

---

## 8) Immediate Next Step After GO

1. Execute first supervised live dispatch ritual.
2. Hold 3 clean supervised days before ramp graduation.
3. Keep replay gate and critical pytest pack required on each release.

