# ✅ Week 1 Quick Start Checklist
**Chief AI Officer Alpha Swarm - Foundation & Integration**

**Start Date:** January 17, 2026  
**End Date:** January 24, 2026  
**Current Progress:** 🟡 IN PROGRESS

---

## 📅 Daily Progress Tracker

```
┌─────────────────────────────────────────────────────────────┐
│                    WEEK 1 PROGRESS                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Day 1-2: API Credentials ................ [████░░] 80%    │
│  Day 3-4: Framework Integration .......... [░░░░░░]  0%    │
│  Day 5:   Webhook Setup .................. [░░░░░░]  0%    │
│  Day 6-7: Dashboard & Monitoring ......... [░░░░░░]  0%    │
│                                                             │
│  Overall Week 1 .......................... [██░░░░] 20%    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 DAY 1-2: API CREDENTIALS & CONNECTIONS

### ⏰ Time Estimate: 2-3 hours

### Part 1: GoHighLevel (30 min) ⬜

- [ ] **Login to GoHighLevel**
  - URL: https://app.gohighlevel.com/
  - Navigate to: Settings → Integrations → Private Integrations

- [ ] **Create Private Integration**
  - Name: `Chief AI Officer Alpha Swarm`
  - Set permissions (contacts, opportunities, calendars, workflows)
  - Copy Private Integration Key (starts with `pit-`)

- [ ] **Get Location ID**
  - Settings → Business Profile
  - Copy Location ID

- [ ] **Update .env file**
  ```bash
  GHL_API_KEY=pit-your-key-here
  GHL_LOCATION_ID=your-location-id
  ```

- [ ] **Test connection**
  ```powershell
  python execution/test_connections.py
  ```
  Expected: `[PASS] GoHighLevel: Connected to: CAIO Corporate`

---

### Part 2: LinkedIn Cookie (20 min) ⬜

- [ ] **Open Chrome Incognito** (Ctrl+Shift+N)

- [ ] **Login to LinkedIn**
  - URL: https://www.linkedin.com/
  - Email: `jcdelossantos.avt@gmail.com`
  - Stay logged in!

- [ ] **Extract li_at cookie**
  - Press F12 (DevTools)
  - Application tab → Cookies → https://www.linkedin.com
  - Find cookie named `li_at`
  - Copy entire value (200+ characters)

- [ ] **Update .env file**
  ```bash
  LINKEDIN_COOKIE=your-li-at-value-here
  ```

- [ ] **Update rotation timestamp**
  ```powershell
  python execution/health_monitor.py --update-linkedin-rotation
  ```

- [ ] **Set calendar reminder**
  - Date: 25 days from today
  - Task: Refresh LinkedIn cookie

- [ ] **Test connection**
  ```powershell
  python execution/test_connections.py
  ```
  Expected: `[PASS] LinkedIn: Session valid`

---

### Part 3: Clay API (15 min) ⬜

- [ ] **Login to Clay**
  - URL: https://app.clay.com/

- [ ] **Get API Key**
  - Profile → Settings → API Keys
  - Create new key: `Chief AI Officer Alpha Swarm`
  - Copy API key

- [ ] **Get Workspace ID**
  - Look at URL: `https://app.clay.com/workspaces/559107/...`
  - Number after `/workspaces/` is your ID

- [ ] **Update .env file**
  ```bash
  CLAY_API_KEY=your-api-key-here
  CLAY_BASE_URL=https://app.clay.com/workspaces/your-workspace-id
  ```

- [ ] **Test connection**
  ```powershell
  python execution/test_connections.py
  ```
  Expected: `[PASS] Clay: API key format valid`

---

### Part 4: Anthropic Claude (15 min) ⬜

- [ ] **Create Anthropic account**
  - URL: https://console.anthropic.com/
  - Sign up and verify email

- [ ] **Add payment method**
  - Settings → Billing
  - Add credit card

- [ ] **Get API Key**
  - Console → API Keys
  - Create key: `Chief AI Officer Alpha Swarm`
  - Copy key (starts with `sk-ant-`)

- [ ] **Update .env file**
  ```bash
  ANTHROPIC_API_KEY=sk-ant-your-key-here
  ```

- [ ] **Test connection**
  ```powershell
  python execution/test_connections.py
  ```
  Expected: `[PASS] Anthropic: Claude API accessible`

---

### Part 5: Verify All Connections (10 min) ⬜

- [ ] **Run full connection test**
  ```powershell
  cd "d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
  python execution/test_connections.py
  ```

- [ ] **Verify results**
  - [ ] Supabase: PASS
  - [ ] GoHighLevel: PASS
  - [ ] Clay: PASS
  - [ ] Instantly: PASS
  - [ ] LinkedIn: PASS
  - [ ] Anthropic: PASS

- [ ] **Check results file**
  ```powershell
  code .hive-mind/connection_test.json
  ```

- [ ] **Setup health monitoring**
  ```powershell
  python execution/health_monitor.py --once
  ```

---

### 📊 Day 1-2 Exit Criteria

**Must have ALL of these:**
- ✅ 6/6 required services passing connection test
- ✅ No error messages in test output
- ✅ `.hive-mind/connection_test.json` shows all_required_pass: true
- ✅ LinkedIn rotation timestamp updated
- ✅ Health monitor runs successfully

**Status:** ⬜ NOT STARTED | 🟡 IN PROGRESS | ✅ COMPLETE

---

## 🏗️ DAY 3-4: CORE FRAMEWORK INTEGRATION

### ⏰ Time Estimate: 4-6 hours

### Part 1: Context Manager (2 hours) ⬜

- [ ] **Create directory structure**
  ```powershell
  mkdir -p core
  mkdir -p tests
  ```

- [ ] **Create Context Manager**
  - File: `core/context_manager.py`
  - Features: Token counting, FIC compaction, history management
  - See: `.hive-mind/WEEK_1_DAY_3-4_FRAMEWORK.md`

- [ ] **Create test file**
  - File: `tests/test_context_manager.py`
  - Test: Basic functionality, compaction, save/load

- [ ] **Run tests**
  ```powershell
  python tests/test_context_manager.py
  ```
  Expected: `✅ Context Manager tests passed!`

- [ ] **Verify features**
  - [ ] Token counting works
  - [ ] FIC compaction reduces tokens
  - [ ] Save/load preserves state
  - [ ] Stats reporting accurate

---

### Part 2: Grounding Chain (2 hours) ⬜

- [ ] **Create Grounding Chain**
  - File: `core/grounding_chain.py`
  - Features: Fact verification, source attribution, audit logging

- [ ] **Create test file**
  - File: `tests/test_grounding_chain.py`
  - Test: Claim verification, confidence scoring

- [ ] **Run tests**
  ```powershell
  python tests/test_grounding_chain.py
  ```
  Expected: `✅ Grounding Chain tests passed!`

- [ ] **Verify features**
  - [ ] Verifies claims against sources
  - [ ] Calculates confidence scores
  - [ ] Logs audit trail
  - [ ] Generates explanations

---

### Part 3: Feedback Collector (1 hour) ⬜

- [ ] **Create Feedback Collector**
  - File: `core/feedback_collector.py`
  - Features: Event tracking, performance analysis, learning extraction

- [ ] **Create test file**
  - File: `tests/test_feedback_collector.py`
  - Test: Event recording, campaign analysis

- [ ] **Run tests**
  ```powershell
  python tests/test_feedback_collector.py
  ```

- [ ] **Verify features**
  - [ ] Records campaign events
  - [ ] Calculates metrics
  - [ ] Extracts learnings
  - [ ] Generates insights

---

### Part 4: Agent Integration (1-2 hours) ⬜

- [ ] **Update CRAFTER agent**
  - File: `execution/crafter_campaign.py`
  - Add: Context manager, grounding chain, feedback collector
  - Test: Generate campaign with verification

- [ ] **Update HUNTER agent (optional)**
  - File: `execution/hunter_scrape_followers.py`
  - Add: Context manager for rate limiting

- [ ] **Update ENRICHER agent (optional)**
  - File: `execution/enricher_clay_waterfall.py`
  - Add: Grounding chain for data verification

- [ ] **Test integrated agents**
  ```powershell
  python execution/crafter_campaign.py --test
  ```

---

### 📊 Day 3-4 Exit Criteria

**Must have ALL of these:**
- ✅ All core components created and tested
- ✅ All tests passing
- ✅ At least one agent integrated
- ✅ No import errors
- ✅ Context management working
- ✅ Grounding verification working
- ✅ Feedback collection working

**Status:** ⬜ NOT STARTED | 🟡 IN PROGRESS | ✅ COMPLETE

---

## 🔗 DAY 5: WEBHOOK SETUP

### ⏰ Time Estimate: 2-3 hours

### Part 1: Webhook Server (1 hour) ⬜

- [ ] **Verify webhook server exists**
  ```powershell
  ls webhooks/webhook_server.py
  ```

- [ ] **Start webhook server**
  ```powershell
  python webhooks/webhook_server.py
  ```
  Expected: Server running on port 5000

- [ ] **Test local endpoint**
  ```powershell
  curl http://localhost:5000/health
  ```

---

### Part 2: Ngrok Setup (30 min) ⬜

- [ ] **Install ngrok**
  - Download from: https://ngrok.com/download
  - Extract to: `C:\ngrok\`
  - Add to PATH

- [ ] **Start ngrok tunnel**
  ```powershell
  ngrok http 5000
  ```

- [ ] **Copy public URL**
  - Format: `https://xxxx-xx-xx-xx-xx.ngrok-free.app`
  - Save for webhook configuration

---

### Part 3: Configure Webhooks (1 hour) ⬜

- [ ] **Instantly webhooks**
  - Login: https://app.instantly.ai/
  - Settings → Webhooks
  - Add URL: `https://your-ngrok-url/webhooks/instantly`
  - Events: opens, replies, bounces, unsubscribes
  - Test webhook

- [ ] **GoHighLevel webhooks**
  - Login: https://app.gohighlevel.com/
  - Settings → Webhooks
  - Add URL: `https://your-ngrok-url/webhooks/ghl`
  - Events: contact.updated, appointment.created
  - Test webhook

- [ ] **Verify webhook reception**
  - Check webhook server logs
  - Verify events in `.hive-mind/webhook_events.jsonl`

---

### 📊 Day 5 Exit Criteria

**Must have ALL of these:**
- ✅ Webhook server running
- ✅ Ngrok tunnel active
- ✅ Instantly webhooks configured and tested
- ✅ GHL webhooks configured and tested
- ✅ Events being received and logged

**Status:** ⬜ NOT STARTED | 🟡 IN PROGRESS | ✅ COMPLETE

---

## 📊 DAY 6-7: DASHBOARD & MONITORING

### ⏰ Time Estimate: 3-4 hours

### Part 1: KPI Dashboard (2 hours) ⬜

- [ ] **Generate initial dashboard**
  ```powershell
  python dashboard/kpi_dashboard.py --all
  ```

- [ ] **Review dashboard output**
  - Check: `.hive-mind/kpi_report.html`
  - Verify: All metrics displaying

- [ ] **Test dashboard updates**
  ```powershell
  python dashboard/kpi_dashboard.py --json
  ```

---

### Part 2: Slack Alerts (1 hour) ⬜

- [ ] **Create Slack webhook**
  - URL: https://api.slack.com/apps
  - Create app: "Alpha Swarm Alerts"
  - Enable Incoming Webhooks
  - Copy webhook URL

- [ ] **Update .env file**
  ```bash
  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
  ```

- [ ] **Test alert**
  ```powershell
  python execution/send_alert.py --test
  ```

- [ ] **Verify alert received in Slack**

---

### Part 3: Scheduled Tasks (1 hour) ⬜

- [ ] **Open Task Scheduler**
  - Windows: Search "Task Scheduler"

- [ ] **Create daily scrape task**
  - Name: Alpha Swarm - Daily Scrape
  - Trigger: Daily at 9:00 PM
  - Action: `powershell.exe -File "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm\scripts\daily_scrape.ps1"`

- [ ] **Create daily enrich task**
  - Name: Alpha Swarm - Daily Enrich
  - Trigger: Daily at 11:00 PM
  - Action: `powershell.exe -File "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm\scripts\daily_enrich.ps1"`

- [ ] **Create daily campaign task**
  - Name: Alpha Swarm - Daily Campaign
  - Trigger: Daily at 12:00 AM
  - Action: `powershell.exe -File "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm\scripts\daily_campaign.ps1"`

- [ ] **Create daily dashboard task**
  - Name: Alpha Swarm - Daily Dashboard
  - Trigger: Daily at 7:00 AM
  - Action: `python.exe "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm\dashboard\kpi_dashboard.py" --all`

- [ ] **Test each task manually**

---

### 📊 Day 6-7 Exit Criteria

**Must have ALL of these:**
- ✅ KPI dashboard generating successfully
- ✅ Slack alerts working
- ✅ All scheduled tasks created
- ✅ Tasks tested and working
- ✅ Dashboard accessible and readable

**Status:** ⬜ NOT STARTED | 🟡 IN PROGRESS | ✅ COMPLETE

---

## 🎯 WEEK 1 FINAL CHECKLIST

### Overall Completion Status

```
┌─────────────────────────────────────────────────────────────┐
│                  WEEK 1 COMPLETION                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ✅ API Credentials & Connections                           │
│     └─ All 6 required services passing                      │
│                                                             │
│  ⬜ Core Framework Integration                              │
│     └─ Context, Grounding, Feedback implemented             │
│                                                             │
│  ⬜ Webhook Setup                                           │
│     └─ Real-time event processing active                    │
│                                                             │
│  ⬜ Dashboard & Monitoring                                  │
│     └─ KPIs tracking, alerts configured                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Must-Have Deliverables

- [ ] **All APIs connected** (6/6 passing)
- [ ] **Core framework integrated** (3/3 components)
- [ ] **Webhooks receiving events** (2/2 platforms)
- [ ] **Dashboard generating** (HTML + JSON)
- [ ] **Scheduled tasks running** (4/4 tasks)
- [ ] **Health monitoring active**
- [ ] **Documentation complete**

### Success Metrics

- [ ] Connection uptime: 100%
- [ ] All tests passing: Yes
- [ ] No critical errors: Yes
- [ ] Team trained: Yes
- [ ] Ready for Week 2: Yes

---

## 📁 Key Files Reference

### Documentation
- **Main Guide:** `.hive-mind/WEEK_1_IMPLEMENTATION_GUIDE.md`
- **Framework Guide:** `.hive-mind/WEEK_1_DAY_3-4_FRAMEWORK.md`
- **This Checklist:** `.hive-mind/WEEK_1_QUICK_START_CHECKLIST.md`

### Scripts
- **Test Connections:** `execution/test_connections.py`
- **Health Monitor:** `execution/health_monitor.py`
- **Rate Limiter:** `execution/rate_limiter.py`

### Core Components
- **Context Manager:** `core/context_manager.py`
- **Grounding Chain:** `core/grounding_chain.py`
- **Feedback Collector:** `core/feedback_collector.py`

### Data Files
- **Connection Test:** `.hive-mind/connection_test.json`
- **Health Log:** `.hive-mind/health_log.jsonl`
- **Feedback History:** `.hive-mind/feedback_history.jsonl`

---

## 🚀 Ready for Week 2?

Once Week 1 is complete, proceed to:

**Week 2: Testing & Validation**
- Unit testing (90% coverage)
- Integration testing
- ICP validation
- Baseline metrics

See: `IMPLEMENTATION_ROADMAP.md` for full 4-week plan

---

**Last Updated:** 2026-01-17T18:21:50+08:00  
**Checklist Version:** 1.0  
**Status:** 🟡 IN PROGRESS - Day 1-2 (80% complete)
