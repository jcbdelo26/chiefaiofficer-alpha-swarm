# Railway Deployment Debug Handoff

## Date: 2026-02-04
## Issue: Sales Dashboard returning `{"detail":"Not Found"}` on Railway

---

## Problem Summary

The CAIO Sales Dashboard at `https://caio-swarm-dashboard-production.up.railway.app/sales?token=caio-swarm-secret-2026` is returning a 404 JSON error `{"detail":"Not Found"}` instead of rendering the dashboard HTML.

---

## Fixes Already Applied (Committed & Pushed)

### 1. Added Missing Core Modules (commit `aecec4a`)
The following files were missing from Git and have been added:
- `core/unified_health_monitor.py`
- `core/precision_scorecard.py`
- `core/messaging_strategy.py`
- `core/signal_detector.py`
- `core/ghl_outreach.py`
- `config/production.json`

### 2. Added circuit_breaker.py Dependency (commit `7a67d91`)
- `core/circuit_breaker.py` - required by `unified_health_monitor.py`

### 3. Fixed Procfile (commit `8b959c1`)
Changed from:
```
web: uvicorn webhooks.rb2b_webhook:app --host 0.0.0.0 --port ${PORT:-8000}
```
To:
```
web: uvicorn dashboard.health_app:app --host 0.0.0.0 --port ${PORT:-8080}
```

---

## Current Git State

```bash
# Latest commits (newest first)
8b959c1 fix: update Procfile to run dashboard.health_app instead of webhook
7a67d91 fix: add circuit_breaker.py dependency for unified_health_monitor
aecec4a fix: add missing core modules required for dashboard deployment
1ff05b1 chore: trigger Railway deployment
202b47d fix: properly handle email approve/reject API parameters and errors
```

All changes are pushed to `origin/main`.

---

## Files Currently Tracked in Git (Core)

```
core/__init__.py
core/agent_action_permissions.json
core/call_prep_agent.py
core/circuit_breaker.py          # Added
core/clay_direct_enrichment.py
core/ghl_outreach.py             # Added
core/inngest_scheduler.py
core/messaging_strategy.py       # Added
core/precision_scorecard.py      # Added
core/self_learning_icp.py
core/signal_detector.py          # Added
core/unified_health_monitor.py   # Added
core/website_intent_monitor.py
```

---

## Debugging Steps to Try

### Step 1: Check Railway Build Logs
In Railway dashboard, check the **Deploy Logs** for the latest deployment:
- Look for import errors (ModuleNotFoundError)
- Look for startup failures
- Look for Python syntax errors

### Step 2: Check if App is Running
Test the root endpoint:
```bash
curl https://caio-swarm-dashboard-production.up.railway.app/
```
If this returns 404, the app may not be starting at all.

Test the health endpoint:
```bash
curl https://caio-swarm-dashboard-production.up.railway.app/api/health
```

### Step 3: Verify Procfile is Being Used
Railway should be using the Procfile to start the app. Check that:
- Railway is configured to use the `web` process
- The PORT environment variable is set correctly

### Step 4: Check for Additional Missing Dependencies
The `health_app.py` imports these modules - verify all exist in Git:

```python
from core.unified_health_monitor import get_health_monitor, HealthMonitor  # Added
from core.precision_scorecard import get_scorecard, reset_scorecard        # Added
from core.messaging_strategy import MessagingStrategy                       # Added
from core.signal_detector import SignalDetector                            # Added
from core.ghl_outreach import OutreachConfig, GHLOutreachClient, EmailTemplate, OutreachType  # Added
```

And `unified_health_monitor.py` imports:
```python
from core.circuit_breaker import get_registry as get_circuit_registry, CircuitState  # Added
```

### Step 5: Check requirements.txt
Verify all Python packages are in `requirements.txt`:
```
python-dotenv>=1.0.0
requests>=2.31.0
aiohttp>=3.9.0
pydantic>=2.5.0
fastapi>=0.109.0
uvicorn[standard]>=0.25.0
supabase>=2.0.0
redis>=5.0.0
inngest>=0.4.0
anthropic>=0.8.0
openai>=1.6.0
httpx>=0.26.0
python-dateutil>=2.8.0
pytz>=2023.3
tenacity>=8.2.0
```

### Step 6: Local Test
Run locally to verify the app starts:
```bash
cd chiefaiofficer-alpha-swarm
uvicorn dashboard.health_app:app --host 0.0.0.0 --port 8080
```
Then visit: `http://localhost:8080/sales`

---

## Key Files

| File | Purpose | Location |
|------|---------|----------|
| `dashboard/health_app.py` | FastAPI backend | Lines 610-624: `/sales` route |
| `dashboard/hos_dashboard.html` | Sales dashboard HTML | Served by FileResponse |
| `Procfile` | Railway startup command | Should run `dashboard.health_app:app` |
| `requirements.txt` | Python dependencies | Root directory |
| `config/production.json` | Production config | Loaded by health_app.py |

---

## The `/sales` Route Code

```python
@app.get("/sales")
async def sales_dashboard():
    """
    Serve the Head of Sales Dashboard.
    """
    hos_html = Path(__file__).parent / "hos_dashboard.html"
    if hos_html.exists():
        return FileResponse(str(hos_html))
    raise HTTPException(status_code=404, detail="Sales dashboard not found")
```

If this returns 404, either:
1. The route isn't being registered (app failed to start)
2. The file `hos_dashboard.html` doesn't exist in the deployment
3. The wrong app is running (webhook instead of dashboard)

---

## Railway Configuration to Check

1. **Service Settings**:
   - Root Directory: Should be empty or `/`
   - Start Command: Should use Procfile or `uvicorn dashboard.health_app:app`
   - Port: Should be `$PORT` or `8080`

2. **Environment Variables**:
   - `DASHBOARD_AUTH_TOKEN` - for authentication
   - `GHL_API_KEY` or `GHL_PROD_API_KEY` - for email sending
   - `GHL_LOCATION_ID` - for GHL integration

3. **GitHub Integration**:
   - Auto-deploy should be enabled
   - Should be watching `main` branch

---

## Potential Root Causes Still to Investigate

1. **Railway caching old build** - Try "Redeploy" button in Railway
2. **Import error on startup** - Check deploy logs for Python errors
3. **Missing file in deployment** - Verify `hos_dashboard.html` is deployed
4. **Port mismatch** - Railway expects `$PORT`, Procfile uses `${PORT:-8080}`
5. **Worker processes** - Procfile defines `worker` and `orchestrator` which may fail

---

## Quick Commands for Agent Manager

```bash
# Check what's tracked in git
git ls-files core/
git ls-files dashboard/

# Check recent commits
git log --oneline -10

# Check if there are uncommitted changes
git status

# Test local startup
uvicorn dashboard.health_app:app --host 0.0.0.0 --port 8080

# Check for import errors
python -c "from dashboard.health_app import app; print('OK')"
```

---

## Contact/Escalation

If the issue persists after all debugging steps:
1. Check Railway status page for outages
2. Review Railway deploy logs in detail
3. Consider redeploying from scratch (delete and recreate service)
4. Verify GitHub webhook is triggering Railway builds
