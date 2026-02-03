# Quick Fix Guide - API Connections
**Chief AI Officer Alpha Swarm**

## 🚨 Critical Fixes (Do These First!)

### 1. Fix Instantly API Key (15 minutes)

**Problem:** Invalid API key - email campaigns blocked

**Steps:**
1. Go to https://app.instantly.ai/
2. Log in with your credentials
3. Click on your profile (top right) → Settings
4. Navigate to "API & Integrations" tab
5. Click "Generate New API Key" or copy existing key
6. Copy the API key

**Update .env:**
```bash
# Open .env file
# Replace this line:
INSTANTLY_API_KEY=YmM5OWMxODctZTU2NC00YjYzLWExMzctZDYxNGVkNTgxNTdmOkxYVXFWUWdWUkpyUw==

# With your new key:
INSTANTLY_API_KEY=your_actual_api_key_here
```

**Test:**
```powershell
python execution/test_connections.py
```

---

### 2. Refresh LinkedIn Cookie (10 minutes)

**Problem:** HTTP 403 - session expired, lead scraping blocked

**Steps:**

#### Option A: Chrome
1. Open Chrome in **Incognito Mode** (Ctrl+Shift+N)
2. Go to https://www.linkedin.com/
3. Log in with your credentials
4. Press **F12** to open DevTools
5. Click **Application** tab
6. In left sidebar: Cookies → https://www.linkedin.com
7. Find cookie named **`li_at`**
8. Double-click the **Value** column and copy the entire value
9. It should be a long string like: `AQEvfZ3hi3JvBQAAAZvIgSdFyM...`

#### Option B: Firefox
1. Open Firefox in **Private Window** (Ctrl+Shift+P)
2. Go to https://www.linkedin.com/
3. Log in with your credentials
4. Press **F12** to open DevTools
5. Click **Storage** tab
6. Expand Cookies → https://www.linkedin.com
7. Find cookie named **`li_at`**
8. Copy the entire **Value**

**Update .env:**
```bash
# Open .env file
# Replace the entire LINKEDIN_COOKIE value with your new cookie:
LINKEDIN_COOKIE=paste_your_new_li_at_value_here
```

**Important Notes:**
- ⚠️ LinkedIn cookies expire every ~30 days
- ⚠️ Don't share this cookie - it's like your password
- ⚠️ Use incognito/private mode to avoid conflicts
- ⚠️ If you log out of LinkedIn, the cookie becomes invalid

**Update rotation timestamp:**
```powershell
python execution/health_monitor.py --update-linkedin-rotation
```

**Test:**
```powershell
python execution/test_connections.py
```

---

### 3. Install Anthropic SDK (5 minutes)

**Problem:** Missing Python package - AI features disabled

**Steps:**

1. **Install the package:**
```powershell
pip install anthropic
```

2. **Get API Key:**
   - Go to https://console.anthropic.com/
   - Sign up or log in
   - Click "API Keys" in left sidebar
   - Click "Create Key"
   - Copy the key (starts with `sk-ant-`)

3. **Update .env:**
```bash
# Replace this line:
ANTHROPIC_API_KEY=your_anthropic_api_key

# With your real key:
ANTHROPIC_API_KEY=sk-ant-api03-your-actual-key-here
```

**Test:**
```powershell
python execution/test_connections.py
```

---

## ✅ Verification

After completing all fixes, run:

```powershell
cd "d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
python execution/test_connections.py
```

**Expected Output:**
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

============================================================
📊 Summary
============================================================

Required Services: 6/6 passed
Optional Services: 1/2 passed

✅ All required services connected! Ready to proceed.
```

---

## 🔄 Optional: Setup RB2B (20 minutes)

**Why:** Identify anonymous website visitors → convert to leads

**Steps:**

1. **Sign up:**
   - Go to https://www.rb2b.com/
   - Create account
   - Choose plan (starts at $49/month)

2. **Get API Key:**
   - Dashboard → Settings → API
   - Copy API Key

3. **Update .env:**
```bash
RB2B_API_KEY=your_actual_rb2b_key
RB2B_WEBHOOK_SECRET=your_webhook_secret
```

4. **Test:**
```powershell
python execution/test_connections.py
```

---

## 📋 Maintenance Checklist

### Weekly
- [ ] Run connection test: `python execution/test_connections.py`
- [ ] Check API costs: `python execution/rate_limiter.py --costs 7`

### Monthly
- [ ] Rotate LinkedIn cookie (before expiration)
- [ ] Review API usage and costs
- [ ] Update API keys if needed

### Setup Automation
```powershell
# Run health monitor in background (checks every 6 hours)
python execution/health_monitor.py --daemon
```

---

## 🆘 Troubleshooting

### Instantly Still Failing?
1. Verify you're using the correct workspace
2. Check if API access is enabled in your plan
3. Try regenerating the API key
4. Contact Instantly support: support@instantly.ai

### LinkedIn Cookie Keeps Expiring?
1. Make sure you're copying from incognito/private mode
2. Don't log out of LinkedIn after copying cookie
3. Consider using LinkedIn's official API (if available)
4. Setup monthly reminder to rotate cookie

### Anthropic API Errors?
1. Check your account has credits: https://console.anthropic.com/settings/billing
2. Verify API key starts with `sk-ant-`
3. Check rate limits (50 requests/min)

### General Issues?
1. Check `.env` file has no extra spaces or quotes
2. Restart terminal after updating `.env`
3. Run: `python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('INSTANTLY_API_KEY'))"`
4. Review full diagnostic: `.hive-mind/api_diagnostic_report.md`

---

## 📞 Support

**Documentation:**
- Full diagnostic report: `.hive-mind/api_diagnostic_report.md`
- Connection test results: `.hive-mind/connection_test.json`
- Health logs: `.hive-mind/health_log.jsonl`

**Scripts:**
- Test connections: `execution/test_connections.py`
- Health monitor: `execution/health_monitor.py`
- Rate limiter: `execution/rate_limiter.py`

**Next Steps:**
After fixing connections, test the full workflows:
1. Lead harvesting: `/lead-harvesting`
2. Campaign creation: `/rpi-campaign-creation`
