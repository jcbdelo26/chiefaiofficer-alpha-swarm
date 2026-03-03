# Development Continuation Plan While Secrets Are Visually Compromised (March 4, 2026)

**Audience:** PTO/GTM operator + engineering  
**Mode:** Dev-progress only (no live-send sign-off)

Primary references:
- `docs/PTO_NON_TECH_REAL_PIPELINE_AND_DEPLOYED_SMOKE_GUIDE.md`
- `docs/CAIO_PTO_INPUTS_NON_TECH_SETUP_GUIDE.md`
- `docs/POST_AUDIT_EXECUTION_LOG.md`
- `task.md` (canonical live tracker)

---

## Summary

Continue development, but only in **dev-progress mode** (no live-send sign-off).

Focus on active parity blockers:
1. `N3`: `session_secret_explicit=false`
2. `N6`: `/docs`, `/redoc`, `/openapi.json` exposed

Existing validations reusable for diagnosis:
- `endpoint_auth_smoke.py`: pass
- `webhook_strict_smoke_matrix.py`: pass
- `deployed_full_smoke_matrix.py`: pass

Not reusable as final security sign-off:
- any auth/secrets-sensitive conclusion before post-fix reruns.

---

## Phase 1 — Guardrails While Continuing

1. Keep `EMERGENCY_STOP=true` if any outbound risk exists.
2. Do not run supervised live sends.
3. Continue only code/tests/documentation work and non-live validation.

Success criteria:
- no production send activity during this window.

---

## Phase 2 — Lock Current Baseline (No New Decisions)

Treat current baseline as:
- runtime env mapping fixed (`staging`/`production` correct)
- isolation auth working when correct tokens are used
- `N3` + `N6` still open

This baseline is sufficient to continue development on targeted fixes.

---

## Phase 3 — Close N3 (`session_secret_explicit=false`)

1. In Railway, re-enter `SESSION_SECRET_KEY` in each env as plain single-line value (no quotes/newlines).
2. Confirm `ENVIRONMENT=staging` and `ENVIRONMENT=production`.
3. Force redeploy each env (staging, then production).
4. Run:

```powershell
$st = Invoke-RestMethod -Uri "$STAGING_URL/api/runtime/dependencies" -Headers @{ "X-Dashboard-Token" = $STAGING_TOKEN }
$pd = Invoke-RestMethod -Uri "$PROD_URL/api/runtime/dependencies" -Headers @{ "X-Dashboard-Token" = $PROD_TOKEN }

"STAGING env=$($st.auth.environment) session_secret_explicit=$($st.auth.session_secret_explicit) session_secret_source=$($st.auth.session_secret_source)"
"PROD env=$($pd.auth.environment) session_secret_explicit=$($pd.auth.session_secret_explicit) session_secret_source=$($pd.auth.session_secret_source)"
```

Exit criteria:
- both envs show `session_secret_explicit=true`
- both envs show `session_secret_source=SESSION_SECRET_KEY`

---

## Phase 4 — Close N6 (OpenAPI/docs exposure)

1. Deploy runtime code version that includes docs-disable logic for production-like env.
2. Verify:

```powershell
Invoke-WebRequest "$STAGING_URL/docs" -MaximumRedirection 0
Invoke-WebRequest "$STAGING_URL/redoc" -MaximumRedirection 0
Invoke-WebRequest "$STAGING_URL/openapi.json" -MaximumRedirection 0
Invoke-WebRequest "$PROD_URL/docs" -MaximumRedirection 0
Invoke-WebRequest "$PROD_URL/redoc" -MaximumRedirection 0
Invoke-WebRequest "$PROD_URL/openapi.json" -MaximumRedirection 0
```

Exit criteria:
- all six endpoints return `404`.

---

## Phase 5 — Rerun Full Gates

Run in order:

```powershell
python scripts/endpoint_auth_smoke.py --base-url $STAGING_URL --token $STAGING_TOKEN --expect-query-token-enabled false --timeout-seconds 15
python scripts/endpoint_auth_smoke.py --base-url $PROD_URL --token $PROD_TOKEN --expect-query-token-enabled false --timeout-seconds 15
python scripts/strict_auth_parity_smoke.py --base-url $STAGING_URL --token $STAGING_TOKEN --timeout 15
python scripts/strict_auth_parity_smoke.py --base-url $PROD_URL --token $PROD_TOKEN --timeout 15
python scripts/webhook_strict_smoke_matrix.py --staging-url $STAGING_URL --staging-dashboard-token $STAGING_TOKEN --production-url $PROD_URL --production-dashboard-token $PROD_TOKEN --require-heyreach-hard-auth --timeout-seconds 15
python scripts/deployed_full_smoke_matrix.py --staging-url $STAGING_URL --staging-token $STAGING_TOKEN --production-url $PROD_URL --production-token $PROD_TOKEN --expect-query-token-enabled false --require-heyreach-hard-auth --timeout-seconds 15
```

Exit criteria:
- parity passes in both envs (no N3/N6 failures)
- both matrix scripts pass.

---

## Phase 6 — Parallel Development Allowed Now

While Phases 3-5 run, continue:
1. HR-05 payload work (`inspect_heyreach_payloads.py` flow)
2. local/unit regression work
3. docs and tracker sync

Blocked until Phases 3-5 are green:
- live sends
- autonomy/ramp graduation
- final security/go-live sign-off

---

## Important changes or additions to public APIs/interfaces/types

- No public API/interface/type changes required.
- Operational contract unchanged:
  - `X-Dashboard-Token` remains canonical auth path.
  - `/api/runtime/dependencies` remains source of truth.

---

## Test cases and scenarios

1. Staging runtime deps shows `env=staging`.
2. Production runtime deps shows `env=production`.
3. Both envs show `session_secret_explicit=true`.
4. Both envs show `session_secret_source=SESSION_SECRET_KEY`.
5. `/docs`, `/redoc`, `/openapi.json` return `404` in both envs.
6. `endpoint_auth_smoke.py` passes in both envs.
7. `strict_auth_parity_smoke.py` passes with no N3/N6 failures.
8. Matrix scripts pass with strict flags.

---

## Assumptions and defaults

1. You accept dev-only progress while secrets are visually compromised.
2. No live-send/go-live decision is made until rerun gates are green.
3. Railway deploys trigger correctly after env variable updates.
4. Secret rotation can be completed later, but final security sign-off requires post-rotation reruns.
