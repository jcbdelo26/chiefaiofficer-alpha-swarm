# CAIO Alpha Swarm — Claude Handoff (Aligned to Task Tracker)

**Date (UTC):** 2026-02-24  
**Primary source of truth:** `docs/CAIO_TASK_TRACKER.md`  
**This handoff purpose:** Continue implementation safely from the exact current state without re-opening already closed work.

---

## 1) Current State Snapshot (Do Not Re-Assume)

Use `docs/CAIO_TASK_TRACKER.md` as canonical. Current high-confidence state:

- Webhook strict mode is enabled in staging and production.
- Query-token auth is deprecated and disabled in staging + production.
- Header-token auth is the required auth path for protected `/api/*` endpoints.
- Production/staging strict smoke and full deployed smoke have been passing.
- Tier_1 supervised lane is still active and should remain conservative.

Do not re-open completed tasks unless you find a clear regression with proof.

---

## 2) Completed Work (Treat as Baseline)

1. `WEBHOOK_SIGNATURE_REQUIRED=true` in staging and production.
2. `DASHBOARD_QUERY_TOKEN_ENABLED=false` in staging and production.
3. Header-only auth behavior validated through deployed smoke checks.
4. Runtime strict webhook checks validated through `webhook_strict_smoke.py`.

If any of these appear broken, treat as a regression incident and capture evidence before changing behavior.

---

## 3) Open Priorities (Execute in This Order)

## Priority A (P0): Finalize HeyReach strict auth strategy

Problem:
- HeyReach currently depends on unsigned-provider allowlist behavior (`HEYREACH_UNSIGNED_ALLOWLIST=true`).

Decision path:
1. Preferred: secure ingress + set `HEYREACH_UNSIGNED_ALLOWLIST=false`.
2. Temporary fallback: keep `true` but document explicit risk and expiry date.

Done criteria:
- Strategy is explicit in env + docs.
- Strict smoke remains green.
- No hidden unsigned bypass outside declared policy.

## Priority B (P1): Redis state cutover completion

Set explicit production flags so file fallback does not silently mutate state:
- `STATE_BACKEND=redis` (already expected)
- `STATE_DUAL_READ_ENABLED=false`
- `STATE_FILE_FALLBACK_WRITE=false`

Done criteria:
- Env values set in production.
- Deployed smoke + runtime checks green.
- No regressions in pending queue, batch integrity, and cadence state behavior.

## Priority C (P1): CORS tightening

Current risk:
- `allow_methods=["*"]` and `allow_headers=["*"]` are broader than needed.

Target:
- Methods: `GET,POST,OPTIONS`
- Headers: `Content-Type, X-Dashboard-Token`

Done criteria:
- Browser/API smoke still passes.
- Preflight still works.
- No unauthorized widening.

## Priority D (P1): Supervised real-send proof loop

Operational proof requirement:
1. Run one supervised generation cycle.
2. HoS approves one valid Tier_1 card.
3. API response should show `Email sent via GHL`.
4. Verify message appears in GHL conversation thread.

Done criteria:
- One end-to-end proof recorded with timestamp and lead email.

---

## 4) Commands to Run (Copy/Paste)

Use placeholders; do not hardcode secrets into docs/logs.

### 4.1 Baseline production checks
```powershell
python scripts/deployed_full_smoke_checklist.py --base-url https://caio-swarm-dashboard-production.up.railway.app --token <PROD_DASHBOARD_AUTH_TOKEN> --expect-query-token-enabled false
python scripts/webhook_strict_smoke.py --base-url https://caio-swarm-dashboard-production.up.railway.app --dashboard-token <PROD_DASHBOARD_AUTH_TOKEN> --expect-webhook-required true --webhook-bearer-token <PROD_WEBHOOK_BEARER_TOKEN>
```

### 4.2 Redis cutover env set (production)
```powershell
railway variable set -s caio-swarm-dashboard -e production STATE_DUAL_READ_ENABLED=false
railway variable set -s caio-swarm-dashboard -e production STATE_FILE_FALLBACK_WRITE=false
```

Then re-run baseline checks from 4.1.

### 4.3 Supervised cycle ritual
```powershell
echo yes | python execution/run_pipeline.py --mode production --source "wpromote" --limit 2
python scripts/trace_outbound_ghl_queue.py --base-url https://caio-swarm-dashboard-production.up.railway.app --token <PROD_DASHBOARD_AUTH_TOKEN>
```

Then manually in `/sales`:
- Approve one real Tier_1 card.
- Confirm response is `Email sent via GHL`.
- Confirm delivery in GHL conversation thread.

---

## 5) Guardrails (Do Not Violate)

1. Do not re-enable query-token auth.
2. Do not weaken strict webhook requirement in production.
3. Do not run uncontrolled live volume; keep supervised Tier_1 limits.
4. Do not bypass HoS approval for Tier_1 live sends.
5. Do not mark a send as successful without GHL conversation proof.

---

## 6) Inputs Needed From PTO (Current)

1. Confirm HeyReach final policy choice:
   - move to secure ingress + `HEYREACH_UNSIGNED_ALLOWLIST=false`, or
   - keep temporary allowlist mode with a deadline.
2. Confirm Redis cutover permission to set:
   - `STATE_DUAL_READ_ENABLED=false`
   - `STATE_FILE_FALLBACK_WRITE=false`
3. Confirm token rotation date for dashboard auth token post-hardening.

---

## 7) Evidence Required in Next Claude Update

Next update must include:

1. Deployment commit hash(es).
2. Exact smoke results (pass/fail only + failing check names if any).
3. Env diff applied (keys only, no secret values).
4. One supervised send proof entry (lead + timestamp + GHL confirmation).
5. Updated `docs/CAIO_TASK_TRACKER.md` status lines for any changed tasks.

---

## 8) Required Doc Hygiene After Any Change

After each meaningful change, update all three:

1. `docs/CAIO_TASK_TRACKER.md` (source of truth status)
2. `docs/CAIO_CLAUDE_MEMORY.md` (runtime/deploy memory)
3. This handoff file (if execution order or blockers changed)

If these three diverge, `docs/CAIO_TASK_TRACKER.md` remains canonical.
