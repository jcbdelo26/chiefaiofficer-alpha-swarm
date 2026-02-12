# CAIO Alpha Swarm: PTO Inputs Setup Guide (Non-Technical GTM)

Date: February 11, 2026  
Audience: Non-technical GTM engineer/operator  
Goal: Safely collect and configure the 4 critical PTO inputs before Golden Set replay.

---

## 0) Step-by-Step (Follow This Exactly)

If you only follow one section, follow this one.

1. Collect the 4 PTO decisions first.
- `REDIS_URL` for staging and production.
- `INNGEST_SIGNING_KEY` and `INNGEST_EVENT_KEY`.
- Production `INNGEST_WEBHOOK_URL` (format: `https://<your-domain>/inngest`).
- Strict startup policy choice:
  - Strict now: `REDIS_REQUIRED=true` and `INNGEST_REQUIRED=true`
  - Temporary fallback: one or both set to `false`

2. Open your deployment platform variables page.
- Usually: Service -> Settings -> Variables (or Environment).
- Do this separately for `staging` and `production`.

3. Paste the runtime keys into **staging**.
- Use the key list in section 4.
- Set `<env>` values to `staging`.

4. Paste the runtime keys into **production**.
- Use the same key list.
- Set `<env>` values to `production`.

5. Save variables and redeploy/restart both environments.
- This is required for new env values to take effect.

6. Validate staging in terminal.

```powershell
cd d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm
python scripts/validate_runtime_env.py --mode staging --env-file .env.staging --check-connections
```

7. Validate production in terminal.

```powershell
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections
```

8. Confirm both commands end with `Result: PASS`.
- If not, fix only the keys shown as missing/failing, then rerun.

9. Confirm runtime endpoints after deploy.
- `GET /api/runtime/dependencies?token=<DASHBOARD_AUTH_TOKEN>` should show `ready: true`
- `GET /api/health/ready` should return `200`

10. Run replay gate only after runtime checks pass.

```powershell
python scripts/replay_harness.py --min-pass-rate 0.95
```

11. Send completion note to PTO/leadership (template in section 10).

---

## 1) What You Are Configuring

You need 4 decisions/inputs from PTO:

1. Production/staging `REDIS_URL`.
2. `INNGEST_SIGNING_KEY` and `INNGEST_EVENT_KEY`.
3. Final production `INNGEST_WEBHOOK_URL`.
4. Whether to enforce strict startup policy immediately:
   - `REDIS_REQUIRED=true`
   - `INNGEST_REQUIRED=true`

If these are not set correctly, runtime reliability checks can fail and block release readiness.

---

## 2) Fast Ownership Split

- You (GTM operator): collect values, enter them in deployment environment variables, run validation.
- PTO: approves final values and strict policy decision.
- Engineering (if needed): support troubleshooting failed checks.

---

## 3) Copy/Paste Message to PTO

Use this exact message:

```text
Need final approval for CAIO runtime reliability inputs:

1) REDIS_URL
   - Staging:
   - Production:

2) Inngest keys
   - INNGEST_SIGNING_KEY:
   - INNGEST_EVENT_KEY:

3) Production INNGEST_WEBHOOK_URL
   - Example format: https://<your-domain>/inngest

4) Strict startup policy (choose one):
   A) Enforce now: REDIS_REQUIRED=true and INNGEST_REQUIRED=true
   B) Delay enforcement (temporary fallback mode)

Please confirm final values and go-live timing.
```

---

## 4) Where to Enter Values

Enter the values in your deployment platform environment variables (for both staging and production), usually under:

- Service -> Settings -> Variables (or Environment)

Set these keys:

```text
REDIS_URL=<from PTO>
REDIS_REQUIRED=true|false
REDIS_MAX_CONNECTIONS=50
RATE_LIMIT_REDIS_NAMESPACE=caio:<env>:ratelimit
CONTEXT_REDIS_PREFIX=caio:<env>:context
CONTEXT_STATE_TTL_SECONDS=3600 (staging) or 7200 (production)

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

Notes:
- Replace `<env>` with `staging` or `production`.
- If PTO chooses strict policy now, set both `*_REQUIRED=true`.

---

## 4A) Click-by-Click: Find Staging Inngest Signing Key + Webhook URL

Use this section if you are non-technical and only need the exact navigation path.

### A. Find the staging `INNGEST_SIGNING_KEY` in Inngest UI

1. Open `https://app.inngest.com` and sign in.
2. From the top-left workspace/app selector, open your CAIO app.
- Recommended app naming:
  - Production: `caio-alpha-swarm-production`
  - Staging: `caio-alpha-swarm-staging`
3. In the left sidebar, open `Settings`.
4. In `Settings`, open `Signing Key` (or `Keys` if UI labels differ).
5. Copy the full key that starts with `signkey-...`.
6. Paste that value into:
- Railway staging variable: `INNGEST_SIGNING_KEY`
- Local staging file (if used): `.env.staging` -> `INNGEST_SIGNING_KEY=...`

Important:
- Do not trim characters at the end.
- Do not add quotes unless your deployment platform requires them.
- Keep staging and production keys separate.

### B. Find or create staging `INNGEST_EVENT_KEY`

1. In the same Inngest app, open `Event Keys` (or `Keys`).
2. Copy an existing staging key, or create a new one named `caio-alpha-swarm-staging`.
3. Paste into:
- Railway staging variable: `INNGEST_EVENT_KEY`
- Local staging file: `.env.staging` -> `INNGEST_EVENT_KEY=...`

### C. Locate staging public domain in Railway

1. Open Railway dashboard and select project `caio-swarm-dashboard`.
2. Switch to the `staging` environment.
3. Open service `caio-swarm-dashboard`.
4. Open `Settings` -> `Domains` (or `Networking`).
5. Copy the public staging domain (example: `https://caio-swarm-dashboard-staging.up.railway.app`).

### D. Build final staging `INNGEST_WEBHOOK_URL`

1. Take the staging domain from step C.
2. Append `/inngest` exactly.
- Example: `https://caio-swarm-dashboard-staging.up.railway.app/inngest`
3. Save as:
- Railway staging variable: `INNGEST_WEBHOOK_URL`
- Optional local staging file: `.env.staging` -> `INNGEST_WEBHOOK_URL=...`

### E. Validate the webhook URL in browser (simple check)

1. Open the full URL from step D in browser.
2. Expected response is JSON containing at least:
- `mode`
- `function_count`
3. If page is not reachable:
- Confirm staging deployment is live.
- Confirm domain is correct.
- Confirm app route `/inngest` is mounted in deployed build.

### F. Turn on strict staging mode after keys are set

Set these in Railway staging variables:

```text
INNGEST_REQUIRED=true
REDIS_REQUIRED=true
```

Then redeploy staging and run:

```powershell
python scripts/validate_runtime_env.py --mode staging --env-file .env.staging --check-connections
```

Expected:
- `Result: PASS`
- Inngest check should be `OK` (not `SKIP`).

---

## 5) No-Code Bootstrap Option (Recommended)

If you have terminal access, this command can generate/update runtime keys in `.env`:

```powershell
python scripts/bootstrap_runtime_reliability.py `
  --mode production `
  --env-file .env `
  --redis-url "<REDIS_URL>" `
  --inngest-signing-key "<INNGEST_SIGNING_KEY>" `
  --inngest-event-key "<INNGEST_EVENT_KEY>" `
  --inngest-webhook-url "<INNGEST_WEBHOOK_URL>" `
  --validate --check-connections
```

For staging:

```powershell
python scripts/bootstrap_runtime_reliability.py `
  --mode staging `
  --env-file .env.staging `
  --redis-url "<STAGING_REDIS_URL>" `
  --inngest-signing-key "<STAGING_INNGEST_SIGNING_KEY>" `
  --inngest-event-key "<STAGING_INNGEST_EVENT_KEY>" `
  --inngest-webhook-url "<STAGING_INNGEST_WEBHOOK_URL>" `
  --validate --check-connections
```

---

## 6) Validation Checklist (Must Pass)

Run:

```powershell
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections
python scripts/validate_runtime_env.py --mode staging --env-file .env.staging --check-connections
```

Optional strict route check:

```powershell
python scripts/validate_runtime_env.py --mode production --env-file .env --check-connections --verify-inngest-route
```

Expected:
- `Result: PASS`
- Redis check is `OK` when required.
- Inngest check is `OK` when required.

After deploy, confirm API endpoints:

1. `GET /api/runtime/dependencies?token=<DASHBOARD_AUTH_TOKEN>`
2. `GET /api/health/ready`

Expected:
- Runtime `ready: true`
- Readiness returns HTTP 200.

---

## 7) Go/No-Go Decision

Go if all are true:

- PTO confirmed the 4 inputs.
- Env vars updated in staging and production.
- Validation is PASS for target environment.
- `/api/runtime/dependencies` reports `ready: true`.
- `/api/health/ready` returns 200.

No-Go if any are true:

- Missing Redis/Inngest values while `*_REQUIRED=true`.
- Validation fails.
- Readiness endpoint returns 503.

---

## 8) Common Failure Fixes

1. Redis fails ping
- Check `REDIS_URL` format and network allowlist/firewall.
- Confirm Redis instance is active.

2. Inngest missing/invalid keys
- Re-copy keys from Inngest app settings.
- Ensure no extra spaces or quotes in env values.

3. Inngest route check fails
- Confirm app deployed with `/inngest` mounted.
- Re-run strict validation after restart/deploy.

4. Readiness fails with runtime dependency error
- Match `*_REQUIRED` flags to actual credential availability.
- If policy is strict, credentials must be valid now.

---

## 9) Security Rules (Do Not Skip)

- Never paste keys in Slack/public channels.
- Never commit real keys into git or docs.
- Rotate keys immediately if accidentally exposed.

---

## 10) Final Handoff Note Template

Use this when reporting completion:

```text
PTO runtime inputs configured.

Environment: [staging/production]
REDIS_REQUIRED: [true/false]
INNGEST_REQUIRED: [true/false]

Validation:
- validate_runtime_env: PASS
- runtime_dependencies endpoint: ready=true
- health/ready: 200

Open issues:
- [none OR list]
```
