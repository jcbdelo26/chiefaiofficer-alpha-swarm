# Claude Code Handoff — Troubleshooting Continuation

## 1) Header
- Generated: `2026-03-04 19:16:08 +08:00`
- Repository: `chiefaiofficer-alpha-swarm`
- Branch: `main`
- HEAD: `6ea42de`
- Mode: `dev-progress only`
- Canonical live status source: `task.md`

---

## 2) Deep Code Assessment

### N3 Assessment (`session_secret_explicit`)
Reviewed file: `dashboard/health_app.py`

- Session secret resolution path:
  1. Use `SESSION_SECRET_KEY` when present.
  2. In `production`/`staging`, fallback to `DASHBOARD_AUTH_TOKEN` only if explicitly set.
  3. In local/non-production-like envs, fallback to local token or local default.
- `/api/runtime/dependencies` auth payload now exposes:
  - `session_secret_explicit`
  - `session_secret_source`
  - `environment`
- Runtime environment is normalized through `_runtime_env()` with precedence:
  1. `ENVIRONMENT`
  2. `RAILWAY_ENVIRONMENT`

Risk statement:
- If `SESSION_SECRET_KEY` is overwritten, empty, or shadowed by wrong scope, runtime can report non-explicit secret posture and fail strict parity expectations.

### N6 Assessment (OpenAPI/Docs exposure)
Reviewed file: `dashboard/health_app.py`

- Root cause of prior false negatives:
  - Dashboard auth middleware redirected docs routes to login (`302`) before router resolution, masking whether docs were actually disabled.
- Hardening implemented:
  - Middleware exemption now includes `/docs`, `/redoc`, and exact `/openapi.json`.
  - In production-like envs, docs URLs are disabled at FastAPI app init.
- Expected behavior:
  - `/docs`, `/redoc`, `/openapi.json` return `404` in staging/production.

### Environment Mapping Assessment
Reviewed file: `dashboard/health_app.py`

- `_runtime_env()` enforces `ENVIRONMENT` precedence with `RAILWAY_ENVIRONMENT` fallback.
- Strict/token/docs decisions are now aligned through `_is_production_like_env()`.

Impact statement:
- If `ENVIRONMENT` is mis-set across envs, strict-mode behavior and docs/query-token behavior can diverge from intended posture despite valid deployment.

---

## 3) Validated Results So Far

Observed in terminal evidence during this session:

- Token isolation:
  - `staging + staging token => 200`
  - `prod + prod token => 200`
  - `staging + prod token => 401`
  - `prod + staging token => 401`
- Runtime dependencies:
  - staging: `session_secret_explicit=True`, `session_secret_source=SESSION_SECRET_KEY`
  - production: `session_secret_explicit=True`, `session_secret_source=SESSION_SECRET_KEY`
- Docs endpoints:
  - staging `/docs`, `/redoc`, `/openapi.json` => `404`
  - production `/docs`, `/redoc`, `/openapi.json` => `404`
- Strict parity:
  - evidence captured showing `12/12 checks passed`
- Webhook strict matrix:
  - pass with `--require-heyreach-hard-auth`

Session updates and improvements applied:
- Commit baseline confirmed: `main` at `6ea42de`
- Code hardening reviewed:
  - `_runtime_env()` added
  - `_is_production_like_env()` added and reused
  - docs routes exempted from dashboard redirect masking
  - `session_secret_source` added to runtime deps auth payload
  - session secret source tracking made explicit
- Test hardening reviewed in `tests/test_security_hardening_v11.py`:
  - Railway env fallback tests
  - auth payload contract check for `session_secret_source`
  - regression guard that docs paths resolve `404` when disabled
- Ops/runbook/tracker updates reviewed:
  - `docs/PTO_GTM_INPUT_COMPLETION_RUNBOOK.md`
  - `docs/PTO_GTM_NEXT_STEPS_TASKS.md`
  - `task.md`

Still pending for final sign-off:
- Fresh same-window rerun of full smoke pack (all six commands green in one window).
- Explicit result logging into `task.md` and `docs/POST_AUDIT_EXECUTION_LOG.md`.

---

## 4) Known Error Patterns in Claude Code Terminal

1. `No such file or directory`
- Cause: wrong working directory (not repo root).

2. `argument --staging-url: expected one argument`
- Cause: empty shell variable (`$STAGING_URL`/`$PROD_URL`) in current tab.

3. `Unauthorized ... Provide dashboard token via X-Dashboard-Token header`
- Cause: wrong token pasted, wrong variable bound, or token variable contaminated with non-token text.

4. `>>` continuation prompt
- Cause: multiline paste left shell waiting for completion.

5. `No linked project found. Run railway link`
- Cause: Railway link context lost in this shell tab/session.

---

## 5) Deterministic Recovery Flow

1. Hard reset shell state.
- If `>>` appears, press `Ctrl+C` once.
- Set `$ErrorActionPreference = "Stop"`.

2. Set repo path.
- `Set-Location "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"`

3. Verify Railway link and service.
- `railway status`
- If service/project missing: run `railway link` and select project/env/service.

4. Load tokens from Railway variable list (no manual token paste).
- Read from `railway variable list ... | findstr`.

5. Run length-only sanity checks.
- Confirm token and URL string lengths are non-zero.

6. Run runtime deps + docs checks.
- Validate N3 and N6 runtime truth before matrix reruns.

7. Run full smoke pack.
- endpoint auth x2, strict parity x2, webhook strict matrix, deployed full matrix.

8. Write summary lines to tracker and execution log docs.
- `task.md`
- `docs/POST_AUDIT_EXECUTION_LOG.md`

---

## 6) Next Command Sequence (single, copy-safe block)

```powershell
$ErrorActionPreference = "Stop"
Set-Location "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"

# Railway link check (service-level)
railway status

# URLs
$STAGING_URL = "https://caio-swarm-dashboard-staging.up.railway.app"
$PROD_URL    = "https://caio-swarm-dashboard-production.up.railway.app"

# Token fetch from Railway (avoid manual paste contamination)
$stLine = railway variable list -s caio-swarm-dashboard -e staging -k | findstr /R "^DASHBOARD_AUTH_TOKEN="
$pdLine = railway variable list -s caio-swarm-dashboard -e production -k | findstr /R "^DASHBOARD_AUTH_TOKEN="
$STAGING_TOKEN = $stLine.Substring($stLine.IndexOf("=")+1).Trim()
$PROD_TOKEN    = $pdLine.Substring($pdLine.IndexOf("=")+1).Trim()

# Length-only sanity checks
"staging_url_len=$($STAGING_URL.Length) prod_url_len=$($PROD_URL.Length)"
"staging_token_len=$($STAGING_TOKEN.Length) prod_token_len=$($PROD_TOKEN.Length)"

# Runtime deps verification
$st = Invoke-RestMethod -Uri "$STAGING_URL/api/runtime/dependencies" -Headers @{ "X-Dashboard-Token" = $STAGING_TOKEN } -TimeoutSec 20
$pd = Invoke-RestMethod -Uri "$PROD_URL/api/runtime/dependencies" -Headers @{ "X-Dashboard-Token" = $PROD_TOKEN } -TimeoutSec 20
"STAGING env=$($st.auth.environment) session_secret_explicit=$($st.auth.session_secret_explicit) session_secret_source=$($st.auth.session_secret_source)"
"PROD env=$($pd.auth.environment) session_secret_explicit=$($pd.auth.session_secret_explicit) session_secret_source=$($pd.auth.session_secret_source)"

# Docs status verification (expect 404)
function StatusCode([string]$u){ try { (Invoke-WebRequest -Uri $u -MaximumRedirection 0 -TimeoutSec 20).StatusCode } catch { [int]$_.Exception.Response.StatusCode } }
"st/docs=$(StatusCode "$STAGING_URL/docs") st/redoc=$(StatusCode "$STAGING_URL/redoc") st/openapi=$(StatusCode "$STAGING_URL/openapi.json")"
"pd/docs=$(StatusCode "$PROD_URL/docs") pd/redoc=$(StatusCode "$PROD_URL/redoc") pd/openapi=$(StatusCode "$PROD_URL/openapi.json")"

# Full smoke pack
python ".\scripts\endpoint_auth_smoke.py" --base-url "$STAGING_URL" --token "$STAGING_TOKEN" --expect-query-token-enabled false --timeout-seconds 15
python ".\scripts\endpoint_auth_smoke.py" --base-url "$PROD_URL" --token "$PROD_TOKEN" --expect-query-token-enabled false --timeout-seconds 15
python ".\scripts\strict_auth_parity_smoke.py" --base-url "$STAGING_URL" --token "$STAGING_TOKEN" --timeout 15
python ".\scripts\strict_auth_parity_smoke.py" --base-url "$PROD_URL" --token "$PROD_TOKEN" --timeout 15
python ".\scripts\webhook_strict_smoke_matrix.py" --staging-url "$STAGING_URL" --staging-dashboard-token "$STAGING_TOKEN" --production-url "$PROD_URL" --production-dashboard-token "$PROD_TOKEN" --require-heyreach-hard-auth --timeout-seconds 15
python ".\scripts\deployed_full_smoke_matrix.py" --staging-url "$STAGING_URL" --staging-token "$STAGING_TOKEN" --production-url "$PROD_URL" --production-token "$PROD_TOKEN" --expect-query-token-enabled false --require-heyreach-hard-auth --timeout-seconds 15
```

---

## 7) Exit Criteria

- N3 closed in both envs:
  - `session_secret_explicit=true`
  - `session_secret_source=SESSION_SECRET_KEY`
- N6 closed in both envs:
  - `/docs`, `/redoc`, `/openapi.json` => `404`
- All six smoke commands green in the same execution window.
- Results logged in:
  - `task.md`
  - `docs/POST_AUDIT_EXECUTION_LOG.md`

---

## Important Changes or Additions to Public APIs/Interfaces/Types

1. `GET /api/runtime/dependencies` auth payload includes `session_secret_source`.
2. Environment interpretation supports `RAILWAY_ENVIRONMENT` fallback when `ENVIRONMENT` is absent.
3. No new external endpoint added; behavior hardening only.

---

## Test Cases and Scenarios

1. `runtime/dependencies` returns:
   - staging: `environment=staging`, `session_secret_explicit=true`, `session_secret_source=SESSION_SECRET_KEY`
   - production: `environment=production`, `session_secret_explicit=true`, `session_secret_source=SESSION_SECRET_KEY`
2. Docs routes return `404` on staging and production:
   - `/docs`
   - `/redoc`
   - `/openapi.json`
3. Isolation checks:
   - staging URL + staging token => `200`
   - prod URL + prod token => `200`
   - staging URL + prod token => `401`
   - prod URL + staging token => `401`
4. Smoke pack:
   - endpoint auth smoke passes both envs
   - strict auth parity passes both envs
   - webhook strict matrix passes with hard-auth required
   - deployed full matrix passes with strict flags

---

## Assumptions and Defaults

1. No live sends, ramp graduation, or go-live sign-off until reruns are fully green.
2. Secrets previously shown in chat/screens are non-signoff-safe; final operational sign-off still requires a fresh green evidence window.
3. Railway CLI commands are executed from one stable shell tab to avoid context loss.
4. Existing uncommitted `.hive-mind/*` changes are telemetry/state and should not be reverted as part of this handoff update.
