# Production Launch Guide for ChiefAIOfficer-Alpha-Swarm

**Document Purpose:** Step-by-step guide for a non-technical GTM engineer to launch the chiefaiofficer-alpha-swarm to production.

**Status:** ✅ HoS APPROVED - Ready for Production  
**Approved By:** Dani Apgar, Head of Sales  
**Date:** January 27, 2026

---

## 📋 PRE-LAUNCH CHECKLIST

Complete these items before proceeding:

### ✅ Business Approvals (Complete)
- [x] Email templates approved by HoS
- [x] ICP criteria confirmed
- [x] Sending limits approved (100/day, 15/hour)
- [x] Customer exclusion list imported
- [x] Competitor exclusion list updated
- [x] CAN-SPAM footer updated (no physical address)

### ⏳ Technical Requirements (Your Responsibility)

| Requirement | Status | How to Verify |
|-------------|--------|---------------|
| API Keys configured | ⏳ | Check `.env` file |
| Slack webhook set up | ⏳ | Test notification |
| GHL connection verified | ⏳ | Run test script |
| Dashboard accessible | ⏳ | Open http://localhost:8080 |

---

## 🔑 STEP 1: CONFIGURE ENVIRONMENT VARIABLES

Create or update the `.env` file in the project root with these values:

```bash
# =============================================================================
# REQUIRED: GoHighLevel (Primary CRM + Email)
# =============================================================================
GHL_API_KEY=your_ghl_api_key_here
GHL_LOCATION_ID=your_ghl_location_id_here

# =============================================================================
# REQUIRED: Slack (Notifications + Approvals)
# =============================================================================
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_SIGNING_SECRET=your_slack_signing_secret

# =============================================================================
# REQUIRED: Email Notifications (Fallback)
# =============================================================================
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
NOTIFICATION_EMAIL_FROM=notifications@chiefaiofficer.com

# =============================================================================
# REQUIRED: SMS Alerts (Twilio)
# =============================================================================
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_FROM_NUMBER=+1XXXXXXXXXX

# =============================================================================
# REQUIRED: Escalation Contacts
# =============================================================================
ESCALATION_PHONE_L2=+15057995035
ESCALATION_EMAIL_L2=dani@chiefaiofficer.com
ESCALATION_PHONE_L3=+15057995035
ESCALATION_EMAIL_L3=dani@chiefaiofficer.com

# =============================================================================
# OPTIONAL: Enrichment Services
# =============================================================================
CLAY_API_KEY=your_clay_api_key
RB2B_API_KEY=your_rb2b_api_key

# =============================================================================
# OPTIONAL: Database (Supabase)
# =============================================================================
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
```

### How to Get These Keys:

| Service | Where to Get It |
|---------|-----------------|
| **GHL API Key** | GoHighLevel → Settings → API Keys → Create New |
| **GHL Location ID** | GoHighLevel → Settings → Business Info → Location ID |
| **Slack Webhook** | Slack App Settings → Incoming Webhooks → Add New |
| **Slack Signing Secret** | Slack App Settings → Basic Information → Signing Secret |
| **Twilio Credentials** | Twilio Console → Account → API Keys |
| **SMTP Password** | Gmail → Security → App Passwords (requires 2FA) |

---

## 🧪 STEP 2: VERIFY CONNECTIONS

Run the connection test script:

```powershell
cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
python execution/test_connections.py
```

**Expected Output:**
```
✅ GHL API: Connected
✅ Slack Webhook: Connected
✅ Twilio SMS: Connected
✅ SMTP Email: Connected
✅ Clay API: Connected (or ⚠️ Not configured)
```

If any connection fails, check the corresponding API key in `.env`.

---

## 🖥️ STEP 3: START THE DASHBOARD

### Option A: Local Development (Recommended for Testing)

```powershell
cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Start the dashboard
python -m uvicorn dashboard.health_app:app --host 0.0.0.0 --port 8080 --reload
```

Then open: **http://localhost:8080/sales**

### Option B: Production (Docker)

```powershell
cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"

# Build and run
docker-compose up -d
```

---

## 📧 STEP 4: SEND A TEST EMAIL

Before going live, send 3-5 test emails to internal accounts:

### Via Dashboard:
1. Go to http://localhost:8080/sales
2. Click "Create Test Email"
3. Enter an internal email address (e.g., your own)
4. Select Tier 1, Angle A
5. Click "Queue for Approval"
6. Approve the email in the pending queue
7. Verify it arrives in the inbox

### Via CLI:
```powershell
python execution/send_test_email.py --to "your@email.com" --tier 1 --angle A
```

---

## 🚀 STEP 5: ENABLE PRODUCTION MODE

Once tests pass, enable production sending:

### Update config/production.json:

```json
{
  "mode": "production",
  "shadow_mode": false,
  "daily_limit": 25,
  "approval_required": true,
  "soft_launch": true
}
```

**Soft Launch Schedule:**
| Week | Daily Limit | Notes |
|------|-------------|-------|
| Week 1 | 25/day | Monitor deliverability |
| Week 2 | 50/day | Scale if healthy |
| Week 3 | 100/day | Full production via GHL |

---

### 🛡️ Domain Reputation Protection (CRITICAL)

**Primary Sending Domain:** `b2b.chiefaiofficer.com`

To avoid damaging domain reputation during production:

| Rule | Limit | Why |
|------|-------|-----|
| **Week 1 Max** | 25/day | Warmup period |
| **Bounce Threshold** | Pause if >2% | Indicates list quality issues |
| **Spam Complaint** | Immediate pause | Investigate before resuming |
| **Reply Rate Check** | Target >5% | Low reply = spam signal |
| **Unsubscribe Rate** | Pause if >1% | Indicates targeting issues |

**Auto-Pause Triggers (Built into guardrails):**
- 5+ bounces in 1 hour → Auto-pause 4 hours
- Any spam complaint → Auto-pause + alert Dani
- 10+ unsubscribes in 1 day → Auto-pause + review targeting

### 📧 Recommended Multi-Domain Strategy

**Phase 1 (Now):** Use `b2b.chiefaiofficer.com` at low volume (25-50/day)

**Phase 2 (Week 4+):** Add `business.chiefaiofficer.com` as secondary domain:
- Warm up separately over 2-3 weeks
- Use for Tier 3 (lower-value) outreach
- Keep Tier 1 (C-suite) on `b2b.` for better deliverability

**Phase 3 (Month 2+):** Add Instantly.ai with dedicated sending domains:
- `outreach1.chiefaiofficer.com`
- `outreach2.chiefaiofficer.com`
- Rotate domains to spread reputation risk

### 📈 Future Scaling Plan: Instantly Integration

**Note:** After verifying the agents are working with our current environment, we plan to add Instantly.ai for:
- Scaling cold outreach beyond GHL limits (1000+/day)
- Protecting the primary B2B domain's health
- Automatic domain rotation and warmup
- Separate sending infrastructure for high-volume campaigns

**This is NOT implemented yet.** Current production uses GHL exclusively.

---

## ☁️ STEP 6: DEPLOY TO CLOUD (For Remote Access)

**Important:** For Dani to access the dashboard from her computer, deploy to a cloud environment.

### Option A: Railway (Recommended - Easiest)

```powershell
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
railway login
railway init
railway up
```

After deployment, Railway provides a URL like:
`https://chiefaiofficer-alpha-swarm-production.up.railway.app`

### Option B: Render.com

1. Go to https://render.com
2. Connect your GitHub repo
3. Create new "Web Service"
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `uvicorn dashboard.health_app:app --host 0.0.0.0 --port $PORT`
6. Add environment variables from `.env`

### Option C: Google Cloud Run

```powershell
# Build and deploy
gcloud run deploy caio-dashboard \
  --source . \
  --region us-west1 \
  --allow-unauthenticated
```

### Cloud URLs (After Deployment)

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| **Sales Dashboard** | https://YOUR-DOMAIN/sales | Email approvals, metrics |
| **Health Dashboard** | https://YOUR-DOMAIN/ | System health |
| **Scorecard** | https://YOUR-DOMAIN/scorecard | Full metrics |
| **API Health** | https://YOUR-DOMAIN/api/health | JSON status |

**Share the Sales Dashboard URL with Dani after deployment.**

---

## 📊 STEP 7: MONITOR THE DASHBOARD

### What to Watch:

| Metric | Target | Alert If |
|--------|--------|----------|
| Deliverability | >98% | <95% |
| Open Rate | >40% | <25% |
| Bounce Rate | <2% | >5% |
| Reply Rate | >5% | <2% |

---

## 🔔 STEP 8: CONFIGURE SLACK NOTIFICATIONS

### Create Slack App:

1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name: `CAIO Approval Bot`
4. Workspace: Your Slack workspace
5. Go to "Incoming Webhooks" → Enable
6. Click "Add New Webhook to Workspace"
7. Select channel: `#approvals` (create if needed)
8. Copy the webhook URL to `.env`

### Get Dani's Slack User ID:

1. In Slack, click on Dani's profile
2. Click "More" → "Copy member ID"
3. Add to `.env`: `SLACK_DANI_USER_ID=UXXXXXXXXXX`

### Enable Interactive Messages:

1. Go to "Interactivity & Shortcuts" → Enable
2. Set Request URL: `https://your-domain.com/api/slack/interactions`
3. Save Changes

### All Notifications Route to Dani:

| Escalation Level | Channel | Contact |
|------------------|---------|---------|
| Level 1 | Slack | @dani in #approvals |
| Level 2 | Email | dani@chiefaiofficer.com |
| Level 3 | SMS | +1 505-799-5035 |

---

## 🎯 STEP 9: UNDERSTAND THE ESCALATION WORKFLOW

### How Dani Handles Escalations (Streamlined Process)

**Scenario 1: Email Approval Request**
```
1. Slack notification arrives in #approvals
2. Dani sees email preview with recommended action
3. Click "✅ Approve" or "❌ Reject" directly in Slack
4. Done - email sends or gets archived
```

**Scenario 2: Response Escalation (Lead Replied)**
```
1. Lead replies with interest/questions/doubts
2. System analyzes reply and creates escalation ticket
3. Dani gets Slack notification with:
   - Lead's reply text
   - Recommended actions (e.g., "Answer their pricing question")
   - Action buttons: "📞 Call Now", "✉️ Draft Response", "✅ Mark Handled"
4. Dani clicks the appropriate action
5. System logs resolution
```

**Escalation Types That Route to Dani:**

| Type | Trigger | Urgency | SLA |
|------|---------|---------|-----|
| Meeting Request | "schedule a call", "book time" | 🚨 CRITICAL | 15 min |
| High Value | Strong buying signals | 🔥 HIGH | 30 min |
| Vague Interest | "maybe", "interesting", "tell me more" | ⚠️ MEDIUM | 2 hours |
| Doubt/Questions | "how much", "what's involved", "ROI" | ⚠️ MEDIUM | 2 hours |
| Soft Objection | "not right now", "bad timing" | 📋 LOW | 24 hours |

### Quick Actions from Slack

Dani can handle most escalations directly from Slack without opening the dashboard:

| Button | What It Does |
|--------|--------------|
| **✅ Approve** | Sends the queued email |
| **❌ Reject** | Archives the email |
| **📞 Call Now** | Opens phone dialer |
| **✉️ Draft Response** | Opens email composer |
| **⏰ Snooze 2hrs** | Delays notification |
| **✅ Mark Handled** | Closes the ticket |

### For Complex Decisions → Use Dashboard

If a response needs more context:
1. Click the "View Details" button in Slack
2. Opens the Sales Dashboard with full conversation history
3. Review lead profile, email thread, and AI recommendations
4. Take action from the dashboard UI

---

## 🛑 STEP 10: EMERGENCY PROCEDURES

### Stop All Sending Immediately:

**Option 1: Dashboard**
1. Go to http://localhost:8080/sales
2. Click "⏸️ Pause All Sends" (top right)

**Option 2: CLI**
```powershell
python execution/emergency_stop.py
```

**Option 3: Config**
```powershell
# Edit config/production.json
# Set "mode": "paused"
```

### Rollback Plan:

| Issue | Action |
|-------|--------|
| Bounce rate >5% | Pause, check domain health |
| Spam complaints | Immediate pause, review templates |
| Negative replies >10% | Pause, revise messaging |
| System errors | Tech team fixes before resuming |

---

## 📞 STEP 11: SUPPORT CONTACTS

| Role | Contact | When to Reach |
|------|---------|---------------|
| **Technical Issues** | tech@chiefaiofficer.com | Dashboard down, API errors |
| **Business Questions** | dani@chiefaiofficer.com | Template changes, limits |
| **Emergency** | +1 505-799-5035 (SMS) | Critical system failure |

---

## ✅ STEP 12: LAUNCH DAY CHECKLIST

```
□ .env file configured with all API keys
□ Connection tests passed
□ Dashboard accessible at /sales
□ Test emails sent and received
□ Slack notifications working
□ Approver (Dani) confirmed available
□ production.json set to soft_launch mode
□ Emergency stop procedure understood
```

**Once all boxes are checked, the system is live!**

---

## 📁 KEY FILE LOCATIONS

| File | Purpose |
|------|---------|
| `.env` | API keys and secrets |
| `config/production.json` | Sending limits, mode |
| `config/approvers.json` | Approver contact info |
| `.hive-mind/exclusions/customers.json` | Never-contact list |
| `.hive-mind/exclusions/competitors.json` | Competitor list |
| `templates/email_templates/` | Email templates |
| `docs/HEAD_OF_SALES_REQUIREMENTS.md` | Full requirements doc |

---

**Document Version:** 1.0  
**Last Updated:** January 27, 2026  
**Next Review:** February 3, 2026
