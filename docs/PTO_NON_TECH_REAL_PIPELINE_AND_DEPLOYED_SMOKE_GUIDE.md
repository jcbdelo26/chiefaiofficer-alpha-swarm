# PTO Non-Technical Guide: Real Pipeline Cycle + `/sales` Refresh + Full Deployed Smoke

**Audience**: PTO / GTM lead (non-technical)  
**Goal**: Run one real pipeline cycle, confirm `/sales` updates without page reload, then run the full staging+production smoke checklist.

---

## 1) Locate Your Staging/Production URL + Dashboard Token

### A. Find your production URL (Railway)
1. Go to `https://railway.app` and open your `chiefaiofficer-alpha-swarm` project.
2. Click the service that hosts the FastAPI dashboard (usually `caio-swarm-dashboard`).
3. Open the `Settings` tab.
4. Open `Domains` (or `Networking` -> `Domains`, depending on Railway UI version).
5. Copy:
   - Railway-generated domain (example format: `https://<service>-production.up.railway.app`)
   - Custom production domain if present.
6. Keep the canonical URL you actually use in browser as `PROD_URL`.

### B. Find your staging URL (Railway)
1. In the same project/service, switch to your **staging** environment.
2. Open `Settings` -> `Domains`.
3. Copy the staging domain as `STAGING_URL`.

### C. Find `DASHBOARD_AUTH_TOKEN` for each environment
1. In Railway, open service -> `Variables`.
2. Switch to **production** environment.
3. Search `DASHBOARD_AUTH_TOKEN`.
4. Click reveal/copy and save as `PROD_TOKEN`.
5. Switch to **staging** environment.
6. Repeat and save as `STAGING_TOKEN`.

Important:
- Do not paste tokens in Slack/email.
- Rotate token immediately if you suspect exposure.

---

## 2) Open Terminal and Set Temporary Variables (PowerShell)

Run this in `D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm`:

```powershell
$env:CAIO_STAGING_URL="<STAGING_URL>"
$env:CAIO_STAGING_TOKEN="<STAGING_DASHBOARD_AUTH_TOKEN>"
$env:CAIO_PROD_URL="<PRODUCTION_URL>"
$env:CAIO_PROD_TOKEN="<PRODUCTION_DASHBOARD_AUTH_TOKEN>"
```

---

## 3) Run One Real Pipeline Cycle (small safe batch)

Use a small limit first:

```powershell
echo yes | python execution/run_pipeline.py --mode production --source "wpromote" --limit 2
```

What success looks like:
- Pipeline completes without crash.
- Send stage reports queued shadow emails.

---

## 4) Confirm `/sales` Updates Without Page Reload

### Browser check (non-technical primary method)
1. Open production dashboard in browser:
   - `https://<PROD_URL>/sales?token=<PROD_TOKEN>`
   - Do **not** use legacy bookmarks like `/ChiefAIOfficer`; canonical route is `/sales`.
2. Keep this tab open.
3. Run the pipeline command above again with `--limit 1` or `--limit 2`.
4. Wait ~15-30 seconds.
5. Confirm new pending email cards appear automatically.
6. Do **not** press refresh (`F5`) during this test.

Expected:
- Page should update itself via polling and show new pending items.

### API check (optional proof)
Run:

```powershell
python scripts/deployed_full_smoke_checklist.py --base-url $env:CAIO_PROD_URL --token $env:CAIO_PROD_TOKEN
```

In output, confirm:
- `sales_page_auto_refresh_wiring` -> `passed: true`
- `pending_emails_refresh_timestamp_changes` -> `passed: true`

---

## 5) Run Full Deployed Smoke Checklist (Staging + Production)

```powershell
python scripts/deployed_full_smoke_matrix.py `
  --staging-url $env:CAIO_STAGING_URL `
  --staging-token $env:CAIO_STAGING_TOKEN `
  --production-url $env:CAIO_PROD_URL `
  --production-token $env:CAIO_PROD_TOKEN
```

Pass criteria:
- top-level `"passed": true`
- both environments pass auth, readiness, runtime dependencies, and pending refresh checks.

---

## 6) Fast Troubleshooting

If smoke fails on auth:
- Verify token copied from correct environment.
- Re-run with exact environment URL/token pair.

If runtime deps fail:
- Check Railway deploy logs for missing env variables (`REDIS_URL`, `INNGEST_*`, webhook secrets).

If `/sales` does not auto-update:
- Confirm smoke check shows `sales_page_auto_refresh_wiring: true`.
- Confirm `pending_emails_refresh_timestamp_changes: true`.
- If either fails, send smoke JSON output to Codex/Claude for direct patching.

---

## 7) Copy/Paste Handoff Message Back to Claude

```text
I completed the real cycle + smoke run.

Staging URL: <STAGING_URL>
Production URL: <PRODUCTION_URL>

Staging token: set
Production token: set

Pipeline run: complete
/sales no-reload update: pass/fail
Full smoke matrix: pass/fail

Please review results and give the next operating step.
```
