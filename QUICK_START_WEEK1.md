# ⚡ Week 1 Quick Start Guide

> Execute these commands in order to complete Week 1 setup

---

## Day 1-2: Fix API Credentials

### 1. GoHighLevel Token (Do This First!)

```
1. Login to GHL → Settings → Integrations → Private Integrations
2. Create new: "Alpha Swarm" with ALL scopes
3. Copy Access Token (starts with 'pit-' or is a long JWT)
4. Update .env: GHL_API_KEY=<your-token>
```

### 2. LinkedIn Cookie

```
1. Chrome → linkedin.com (logged in)
2. F12 → Application → Cookies → linkedin.com
3. Click 'li_at' row → Copy FULL value from bottom panel
4. Update .env: LINKEDIN_COOKIE=<full-cookie-no-quotes>
```

### 3. Verify All APIs

```powershell
cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
.\.venv\Scripts\Activate.ps1
python scripts/validate_apis.py
```

**Expected:** All green ✅

---

## Day 3-4: Test New Framework

### Test Context Manager
```powershell
python core/context_manager.py
```
**Expected:** Token counting demo, budget checks pass

### Test Grounding Chain
```powershell
python core/grounding_chain.py
```
**Expected:** Claims grounded with sources, audit log created

### Test Feedback Collector
```powershell
python core/feedback_collector.py
```
**Expected:** Feedback events recorded, learning signals extracted

### Test Verification Hooks
```powershell
python core/verification_hooks.py
```
**Expected:** Good lead passes, bad lead fails with violations

### Test KPI Dashboard
```powershell
python dashboard/kpi_dashboard.py --all
```
**Expected:** JSON report + HTML dashboard generated

---

## Day 5: Webhook Setup

### Start Webhook Server
```powershell
# Terminal 1: Start server
python webhooks/webhook_server.py
```

### Expose via ngrok (for testing)
```powershell
# Terminal 2: Expose
ngrok http 5000
# Copy the https://xxxxx.ngrok.io URL
```

### Configure Instantly Webhooks
```
1. Instantly → Settings → Webhooks
2. Add URL: https://your-ngrok-url/webhooks/instantly
3. Enable: opens, replies, bounces, unsubscribes
```

### Configure GHL Webhooks
```
1. GHL → Settings → Webhooks
2. Add URL: https://your-ngrok-url/webhooks/ghl
3. Enable: contact.updated, appointment.created
```

### Test Webhook
```powershell
# In browser, visit:
http://localhost:5000/health
# Should return: {"status": "healthy", ...}
```

---

## Day 6-7: Monitoring & Scheduling

### Set Up Slack Alerts
```
1. Create Slack App: api.slack.com/apps
2. Add Incoming Webhook
3. Copy URL to .env: SLACK_WEBHOOK_URL=https://hooks.slack.com/...
4. Test:
```
```powershell
python execution/send_alert.py --test
```

### Create Windows Scheduled Tasks

Open Task Scheduler and create:

| Task | Script | Schedule |
|------|--------|----------|
| Daily Scrape | `scripts\daily_scrape.ps1` | 9:00 PM |
| Daily Enrich | `scripts\daily_enrich.ps1` | 11:00 PM |
| Daily Campaign | `scripts\daily_campaign.ps1` | 12:00 AM |
| Daily Anneal | `scripts\daily_anneal.ps1` | 8:00 AM |
| KPI Dashboard | `dashboard\kpi_dashboard.py --all` | 7:00 AM |

### Generate First Dashboard
```powershell
python dashboard/kpi_dashboard.py --html
start dashboard\kpi_index.html
```

---

## ✅ Week 1 Checklist

Before proceeding to Week 2, verify:

- [ ] GHL API returns 200 on all endpoints
- [ ] LinkedIn cookie is 200+ chars and API returns 200
- [ ] Instantly shows 10 email accounts
- [ ] Supabase connection verified
- [ ] `python core/context_manager.py` runs without errors
- [ ] `python core/grounding_chain.py` runs without errors
- [ ] `python core/feedback_collector.py` runs without errors
- [ ] `python core/verification_hooks.py` runs without errors
- [ ] `python dashboard/kpi_dashboard.py --all` generates report
- [ ] Webhook server starts on port 5000
- [ ] Slack test alert received
- [ ] At least 1 scheduled task created

---

## 🚨 Troubleshooting

### GHL Still 401?
- Make sure you're using **Private Integrations**, not API Keys
- Token must have all required scopes
- Try regenerating the token

### LinkedIn Still 403?
- Cookie expires after ~7 days, get fresh one
- Make sure you're copying from the **bottom panel** (full value)
- Try in incognito, login fresh, then copy cookie

### Webhook Server Won't Start?
```powershell
# Check if port 5000 is in use
netstat -ano | findstr :5000
# If so, change port in .env: WEBHOOK_PORT=5001
```

### Dashboard Shows No Data?
- This is normal initially
- Data populates after first workflow run
- Run `scripts/daily_scrape.ps1` manually to seed data

---

## Next: Week 2

Once all checkboxes above are complete, proceed to:
- Unit testing all components
- Integration testing full pipeline
- ICP validation with AE team
- Baseline metrics capture

See [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) for full Week 2-4 details.
