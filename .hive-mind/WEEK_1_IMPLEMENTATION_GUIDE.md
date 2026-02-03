# 🚀 Week 1 Implementation Guide
**Chief AI Officer Alpha Swarm - Foundation & Integration**

**Timeline:** Day 1-7 (January 17-24, 2026)  
**Goal:** Complete API setup, verify all connections, integrate core framework  
**Status:** 🟡 IN PROGRESS

---

## 📋 Week 1 Overview

```
Day 1-2: API Credentials & Connections ............ [████░░] 80%
Day 3-4: Core Framework Integration ............... [░░░░░░]  0%
Day 5:   Webhook Setup ............................ [░░░░░░]  0%
Day 6-7: Dashboard & Monitoring ................... [░░░░░░]  0%
────────────────────────────────────────────────────────────
Overall Week 1 Progress ........................... [██░░░░] 20%
```

---

## 🎯 Day 1-2: API Credentials & Connections

### Prerequisites Checklist

Before starting, ensure you have:
- [ ] Admin access to GoHighLevel account
- [ ] LinkedIn account credentials
- [ ] Instantly.ai account access
- [ ] Clay.com account access (if using)
- [ ] Anthropic account for Claude API
- [ ] Text editor (VS Code recommended)
- [ ] PowerShell terminal access

---

## 🔧 Part 1: GoHighLevel Private Integration

### Overview
GoHighLevel requires a **Private Integration** token for API access. This is different from the Location API key.

### Step-by-Step Instructions

#### Step 1: Access GoHighLevel Settings

1. **Login to GoHighLevel:**
   - Go to: https://app.gohighlevel.com/
   - Login with your credentials

2. **Navigate to Integrations:**
   ```
   Click Profile Icon (top right)
   → Settings
   → Integrations
   → Private Integrations
   ```

#### Step 2: Create Private Integration

1. **Click "Create Integration"**

2. **Fill in Integration Details:**
   ```
   Name: Chief AI Officer Alpha Swarm
   Description: Automated lead management and campaign orchestration
   Redirect URL: https://localhost:3000/oauth/callback
   ```

3. **Set Permissions (Scopes):**
   
   Select the following scopes:
   - ✅ `contacts.readonly` - Read contact information
   - ✅ `contacts.write` - Create/update contacts
   - ✅ `opportunities.readonly` - Read pipeline deals
   - ✅ `opportunities.write` - Create/update deals
   - ✅ `calendars.readonly` - Read appointments
   - ✅ `calendars.write` - Create appointments
   - ✅ `conversations.readonly` - Read messages
   - ✅ `conversations.write` - Send messages
   - ✅ `workflows.readonly` - Read workflows

4. **Click "Create"**

#### Step 3: Get Your API Credentials

After creation, you'll see:

```
Client ID: abc123def456...
Client Secret: xyz789uvw012...
Private Integration Key: pit-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**IMPORTANT:** Copy the **Private Integration Key** (starts with `pit-`)

#### Step 4: Get Your Location ID

1. **Navigate to Settings:**
   ```
   Click Profile Icon (top right)
   → Settings
   → Business Profile
   ```

2. **Copy Location ID:**
   - Look for "Location ID" field
   - It's a long alphanumeric string (e.g., `FgaFLGYrbGZSBVprTkhR`)
   - Copy this value

#### Step 5: Update .env File

1. **Open your .env file:**
   ```powershell
   cd "d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
   code .env
   ```

2. **Update these lines:**
   ```bash
   # GoHighLevel API credentials
   GHL_API_KEY=pit-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   GHL_BASE_URL=https://services.leadconnectorhq.com
   GHL_LOCATION_ID=YourLocationIdHere
   ```

   **Example:**
   ```bash
   GHL_API_KEY=pit-d34dff24-d1cb-4d2e-9598-7d5b6db12083
   GHL_BASE_URL=https://services.leadconnectorhq.com
   GHL_LOCATION_ID=FgaFLGYrbGZSBVprTkhR
   ```

3. **Save the file** (Ctrl+S)

#### Step 6: Verify GoHighLevel Connection

```powershell
# Test the connection
python execution/test_connections.py
```

**Expected Output:**
```
🔗 Testing GoHighLevel...
  [PASS] GoHighLevel: Connected to: CAIO Corporate
```

### Troubleshooting GoHighLevel

| Issue | Solution |
|-------|----------|
| `401 Unauthorized` | Token expired - regenerate Private Integration key |
| `403 Forbidden` | Missing scopes - add required permissions |
| `404 Not Found` | Wrong Location ID - verify in Business Profile |
| `Invalid API key format` | Ensure key starts with `pit-` |

---

## 🔗 Part 2: LinkedIn li_at Cookie

### Overview
LinkedIn doesn't have an official scraping API. We use session cookies to authenticate. The `li_at` cookie is your session token.

### ⚠️ Important Warnings

- **LinkedIn cookies expire every ~30 days**
- **Don't share your cookie** - it's like your password
- **Use incognito mode** to avoid conflicts
- **Respect LinkedIn's rate limits** (5 requests/min max)
- **If you log out, the cookie becomes invalid**

### Step-by-Step Instructions

#### Step 1: Prepare Your Browser

**Option A: Google Chrome (Recommended)**

1. **Open Chrome in Incognito Mode:**
   - Press `Ctrl + Shift + N`
   - Or: Menu → New Incognito Window

2. **Navigate to LinkedIn:**
   - Go to: https://www.linkedin.com/

3. **Login:**
   - Enter your email: `jcdelossantos.avt@gmail.com`
   - Enter your password
   - Complete any 2FA if enabled
   - **Important:** Stay logged in!

#### Step 2: Extract li_at Cookie (Chrome)

1. **Open Developer Tools:**
   - Press `F12`
   - Or: Right-click → Inspect

2. **Navigate to Application Tab:**
   ```
   Click "Application" tab (top menu)
   If you don't see it, click the >> icon
   ```

3. **Find Cookies:**
   ```
   Left sidebar:
   Storage
   └── Cookies
       └── https://www.linkedin.com
   ```

4. **Locate li_at Cookie:**
   - Scroll through the cookie list
   - Find the cookie named exactly: `li_at`
   - It should look like this:

   ```
   Name:     li_at
   Value:    AQEvfZ3hi3JvBQAAAZvIgSdFyM-y5KWzzKs_qtq3wWJBIkoEtAVTQtmB1POxWXYppUdRWRvJUb0itslP61ZX9j--x68HjoEYoy0bg3OYzxPR9iRfvjCmrvv3udv8k6zrQ9HuFv1H7r515IQOWqpVqZEuYNJ39MM4J_1_dUaEDXr-xh9PECDPiNb9USzaUr1bvSr74EquWMg2PZMq1ZNFOlXj2palF0BMivbY8dFAlqoChQGFaRiWOUNCZVStNOcq0IbrRxdja100qS0SmNHf-wpoEa9p1b4HQKV1jmvjxak2VlwR0ee7BsxPLBLXuCIVsul16huk-S_O5oX8FBizug
   Domain:   .linkedin.com
   Path:     /
   Expires:  [Date ~30 days from now]
   ```

5. **Copy the Value:**
   - **Double-click** the Value field
   - Press `Ctrl + A` to select all
   - Press `Ctrl + C` to copy
   - The value should be **200+ characters long**

#### Step 2B: Extract li_at Cookie (Firefox Alternative)

1. **Open Firefox in Private Window:**
   - Press `Ctrl + Shift + P`

2. **Login to LinkedIn** (same as above)

3. **Open Developer Tools:**
   - Press `F12`

4. **Navigate to Storage Tab:**
   ```
   Click "Storage" tab
   └── Cookies
       └── https://www.linkedin.com
   ```

5. **Find and copy li_at value** (same as Chrome)

#### Step 3: Update .env File

1. **Open .env file:**
   ```powershell
   code .env
   ```

2. **Find the LINKEDIN_COOKIE line:**
   ```bash
   LINKEDIN_COOKIE=AQEvfZ3hi3JvBQAAAZvIgSdFyM-y5KWzzKs_qtq3wWJBIkoEtAVTQtmB1POxWXYppUdRWRvJUb0itslP61ZX9j--x68HjoEYoy0bg3OYzxPR9iRfvjCmrvv3udv8k6zrQ9HuFv1H7r515IQOWqpVqZEuYNJ39MM4J_1_dUaEDXr-xh9PECDPiNb9USzaUr1bvSr74EquWMg2PZMq1ZNFOlXj2palF0BMivbY8dFAlqoChQGFaRiWOUNCZVStNOcq0IbrRxdja100qS0SmNHf-wpoEa9p1b4HQKV1jmvjxak2VlwR0ee7BsxPLBLXuCIVsul16huk-S_O5oX8FBizug
   ```

3. **Replace with your new cookie:**
   - Delete the old value
   - Paste your new cookie value
   - **No quotes needed**
   - **No spaces before or after**

4. **Save the file** (Ctrl+S)

#### Step 4: Update Rotation Timestamp

This helps track when the cookie expires:

```powershell
python execution/health_monitor.py --update-linkedin-rotation
```

**Expected Output:**
```
✅ LinkedIn rotation timestamp updated: 2026-01-17T18:21:50+08:00
```

#### Step 5: Verify LinkedIn Connection

```powershell
python execution/test_connections.py
```

**Expected Output:**
```
🔗 Testing LinkedIn Session...
  [PASS] LinkedIn: Session valid
```

### LinkedIn Cookie Maintenance

**Set a reminder for 25 days from now to refresh the cookie!**

Create a calendar reminder:
```
Title: Refresh LinkedIn Cookie
Date: [25 days from today]
Description: 
1. Open incognito browser
2. Login to LinkedIn
3. Extract new li_at cookie
4. Update .env file
5. Run: python execution/health_monitor.py --update-linkedin-rotation
```

### Troubleshooting LinkedIn

| Issue | Solution |
|-------|----------|
| `HTTP 403 Forbidden` | Cookie expired - get fresh cookie |
| `HTTP 401 Unauthorized` | Invalid cookie - verify you copied correctly |
| `Session invalid` | Logged out of LinkedIn - login again |
| `Cookie too short` | Didn't copy full value - should be 200+ chars |
| `Rate limit exceeded` | Wait 1 minute, reduce scraping frequency |

---

## 🎨 Part 3: Clay API Integration

### Overview
Clay is used for lead enrichment (email finding, company data, etc.). You need an API key from your Clay workspace.

### Step-by-Step Instructions

#### Step 1: Access Clay Dashboard

1. **Login to Clay:**
   - Go to: https://app.clay.com/
   - Login with your credentials

2. **Navigate to your Workspace:**
   - You should see your workspace name in the top left
   - Current workspace: `559107`

#### Step 2: Get API Key

1. **Open Settings:**
   ```
   Click your profile icon (top right)
   → Settings
   → API Keys
   ```

2. **Create New API Key:**
   - Click "Create API Key"
   - Name: `Chief AI Officer Alpha Swarm`
   - Permissions: Select all (or minimum: Read Tables, Write Tables)
   - Click "Create"

3. **Copy API Key:**
   - The key will be shown once
   - **Copy it immediately** - you won't see it again!
   - Format: Usually a hex string like `ad8a077082e1ab2a722a`

#### Step 3: Get Workspace ID

1. **Find Workspace ID in URL:**
   - Look at your browser URL when in Clay
   - Format: `https://app.clay.com/workspaces/559107/...`
   - The number after `/workspaces/` is your Workspace ID
   - Example: `559107`

#### Step 4: Update .env File

1. **Open .env file:**
   ```powershell
   code .env
   ```

2. **Update Clay credentials:**
   ```bash
   # Clay.com Enrichment
   CLAY_API_KEY=ad8a077082e1ab2a722a
   CLAY_BASE_URL=https://app.clay.com/workspaces/559107
   ```

   **Replace with your values:**
   ```bash
   CLAY_API_KEY=your_actual_api_key_here
   CLAY_BASE_URL=https://app.clay.com/workspaces/your_workspace_id
   ```

3. **Save the file** (Ctrl+S)

#### Step 5: Verify Clay Connection

```powershell
python execution/test_connections.py
```

**Expected Output:**
```
🔗 Testing Clay...
  [PASS] Clay: API key format valid (full test requires usage)
```

### Clay API Usage Notes

**Rate Limits:**
- Free tier: 100 credits/month
- Pro tier: 1,000 credits/month
- Enterprise: Custom limits

**Credit Costs:**
- Email finding: 1-2 credits
- Company enrichment: 1 credit
- Person enrichment: 2-3 credits

**Best Practices:**
1. **Cache results** - Don't re-enrich known leads
2. **Batch requests** - Use Clay tables for bulk enrichment
3. **Validate before enriching** - Check if data already exists
4. **Monitor credit usage** - Set up alerts at 80% usage

### Troubleshooting Clay

| Issue | Solution |
|-------|----------|
| `401 Unauthorized` | Invalid API key - regenerate in settings |
| `403 Forbidden` | Insufficient permissions - check API key scopes |
| `429 Too Many Requests` | Rate limited - wait 1 minute |
| `Credits exhausted` | Upgrade plan or wait for monthly reset |
| `Invalid workspace ID` | Check URL for correct workspace number |

---

## 🤖 Part 4: Anthropic Claude API

### Overview
Anthropic's Claude is used for AI-powered campaign generation, personalization, and content creation.

### Step-by-Step Instructions

#### Step 1: Create Anthropic Account

1. **Sign up at Anthropic:**
   - Go to: https://console.anthropic.com/
   - Click "Sign Up"
   - Use email: `jcdelossantos.avt@gmail.com` (or your preferred email)
   - Verify email

2. **Add Payment Method:**
   - Go to: Settings → Billing
   - Add credit card
   - **Note:** Anthropic charges per token usage
   - Typical cost: $50-200/month for this use case

#### Step 2: Get API Key

1. **Navigate to API Keys:**
   ```
   Console → API Keys
   Or: https://console.anthropic.com/settings/keys
   ```

2. **Create New Key:**
   - Click "Create Key"
   - Name: `Chief AI Officer Alpha Swarm`
   - Click "Create"

3. **Copy API Key:**
   - Format: `sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   - **Copy immediately** - shown only once!
   - Store securely

#### Step 3: Update .env File

1. **Open .env file:**
   ```powershell
   code .env
   ```

2. **Update Anthropic key:**
   ```bash
   # AI Models
   ANTHROPIC_API_KEY=sk-ant-api03-your-actual-key-here
   ```

3. **Save the file** (Ctrl+S)

#### Step 4: Verify Anthropic Connection

```powershell
python execution/test_connections.py
```

**Expected Output:**
```
🔗 Testing Anthropic Claude...
  [PASS] Anthropic: Claude API accessible
```

### Anthropic Usage & Costs

**Models Available:**
- `claude-3-haiku-20240307` - Fast, cheap ($0.25/$1.25 per M tokens)
- `claude-3-sonnet-20240229` - Balanced ($3/$15 per M tokens)
- `claude-3-opus-20240229` - Most capable ($15/$75 per M tokens)

**Recommended for this project:**
- Campaign generation: Sonnet
- Quick responses: Haiku
- Complex analysis: Opus (sparingly)

**Cost Estimation:**
- Average campaign: ~5,000 tokens = $0.02-0.10
- 100 campaigns/month: $2-10
- With analysis and refinement: $50-200/month

### Troubleshooting Anthropic

| Issue | Solution |
|-------|----------|
| `401 Authentication Error` | Invalid API key - regenerate |
| `429 Rate Limit` | Too many requests - implement rate limiting |
| `402 Payment Required` | Add payment method or add credits |
| `400 Invalid Request` | Check prompt format and parameters |
| `Module not found` | Run: `pip install anthropic` |

---

## ✅ Part 5: Verify All Connections

### Run Complete Connection Test

```powershell
cd "d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
python execution/test_connections.py
```

### Expected Output (All Pass)

```
============================================================
[*] Alpha Swarm Connection Test
============================================================

🔗 Testing Supabase...
  [PASS] Supabase: Connected - leads table accessible

🔗 Testing GoHighLevel...
  [PASS] GoHighLevel: Connected to: CAIO Corporate

🔗 Testing Clay...
  [PASS] Clay: API key format valid

🔗 Testing RB2B...
  [PASS] RB2B: API key format valid

🔗 Testing Instantly...
  [PASS] Instantly: Found 1 account(s)

🔗 Testing LinkedIn Session...
  [PASS] LinkedIn: Session valid

🔗 Testing Anthropic Claude...
  [PASS] Anthropic: Claude API accessible

🔗 Testing Exa Search...
  [PASS] Exa: Search API accessible

============================================================
📊 Summary
============================================================

Required Services: 6/6 passed
Optional Services: 2/2 passed

✅ All required services connected! Ready to proceed.

Results saved to: .hive-mind/connection_test.json
```

### If Any Tests Fail

1. **Review the error message carefully**
2. **Check the troubleshooting section** for that service
3. **Verify .env file** has no extra spaces or quotes
4. **Restart terminal** after updating .env
5. **Run test again**

---

## 📊 Part 6: Connection Health Monitoring

### Setup Automated Monitoring

1. **Start health monitor:**
   ```powershell
   # Run once to test
   python execution/health_monitor.py --once
   ```

2. **Setup as background service (optional):**
   ```powershell
   # Monitors every 6 hours
   python execution/health_monitor.py --daemon --interval 6
   ```

3. **View health summary:**
   ```powershell
   # Last 7 days
   python execution/health_monitor.py --summary 7
   ```

### Setup Slack Alerts (Optional)

1. **Create Slack Webhook:**
   - Go to: https://api.slack.com/apps
   - Create New App → From Scratch
   - Name: "Alpha Swarm Alerts"
   - Select your workspace
   - Features → Incoming Webhooks → Activate
   - Add New Webhook to Workspace
   - Copy Webhook URL

2. **Update .env:**
   ```bash
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```

3. **Test alert:**
   ```powershell
   python execution/send_alert.py --test
   ```

---

## 📝 Day 1-2 Completion Checklist

### API Credentials ✅

- [ ] GoHighLevel Private Integration created
- [ ] GHL_API_KEY updated in .env (starts with `pit-`)
- [ ] GHL_LOCATION_ID updated in .env
- [ ] GoHighLevel connection test passes

- [ ] LinkedIn li_at cookie extracted
- [ ] LINKEDIN_COOKIE updated in .env (200+ chars)
- [ ] LinkedIn rotation timestamp updated
- [ ] LinkedIn connection test passes

- [ ] Clay API key obtained
- [ ] CLAY_API_KEY updated in .env
- [ ] CLAY_BASE_URL updated with workspace ID
- [ ] Clay connection test passes

- [ ] Anthropic account created
- [ ] ANTHROPIC_API_KEY updated in .env (starts with `sk-ant-`)
- [ ] Anthropic connection test passes

### Verification ✅

- [ ] All connection tests pass (6/6 required services)
- [ ] Health monitor runs successfully
- [ ] Connection test results saved to `.hive-mind/connection_test.json`
- [ ] No error messages in terminal

### Documentation ✅

- [ ] API credentials stored securely
- [ ] LinkedIn rotation reminder set (25 days)
- [ ] Slack webhook configured (optional)
- [ ] Team notified of successful setup

---

## 🎯 Next Steps: Day 3-4

Once all API connections are verified, proceed to:

1. **Core Framework Integration**
   - Context Manager setup
   - Grounding Chain implementation
   - Feedback Collector integration

2. **Test Individual Agents**
   - HUNTER: Test LinkedIn scraping
   - ENRICHER: Test Clay enrichment
   - CRAFTER: Test campaign generation

See: `WEEK_1_DAY_3-4_FRAMEWORK.md` (coming next)

---

## 🆘 Getting Help

### If You're Stuck

1. **Check the diagnostic report:**
   ```powershell
   code .hive-mind/api_diagnostic_report.md
   ```

2. **View connection test results:**
   ```powershell
   code .hive-mind/connection_test.json
   ```

3. **Check health logs:**
   ```powershell
   code .hive-mind/health_log.jsonl
   ```

### Common Issues

**"Module not found" errors:**
```powershell
pip install -r requirements.txt
```

**".env file not found":**
```powershell
# Make sure you're in the right directory
cd "d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
```

**"Permission denied":**
```powershell
# Run PowerShell as Administrator
```

---

## 📊 Progress Tracking

Update this section as you complete each part:

```
✅ Part 1: GoHighLevel Integration - COMPLETE
✅ Part 2: LinkedIn Cookie - COMPLETE  
✅ Part 3: Clay API - COMPLETE
✅ Part 4: Anthropic API - COMPLETE
✅ Part 5: Verify All Connections - COMPLETE
✅ Part 6: Health Monitoring - COMPLETE

Day 1-2 Status: ✅ COMPLETE
Ready for Day 3-4: ✅ YES
```

---

**Last Updated:** 2026-01-17T18:21:50+08:00  
**Guide Version:** 1.0  
**Next:** Day 3-4 Framework Integration
