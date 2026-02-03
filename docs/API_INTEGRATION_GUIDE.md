# API Integration Guide - Priority Order

Complete these integrations in order. Each phase builds on the previous.

---

## Current Status

| Priority | Platform | Status | Required For |
|----------|----------|--------|--------------|
| 1 | **Supabase** | ✅ CONNECTED | Data layer |
| 2 | **GoHighLevel** | ❌ Invalid JWT | Warm leads, CRM |
| 3 | **Instantly** | ❌ Invalid key | Cold outreach |
| 4 | **LinkedIn** | ❌ Session expired | Lead scraping |
| 5 | **Clay** | ✅ Key valid | Enrichment |
| 6 | **RB2B** | ✅ Key valid | Website visitors |

---

## Priority 1: Supabase ✅ Complete

Already configured and working.

```
SUPABASE_URL=https://ysftgoclztfoaoyqsbgd.supabase.co
SUPABASE_KEY=eyJ... (anon key)
```

---

## Priority 2: GoHighLevel 🔧 Fix Required

### Issue
`HTTP 401: Invalid JWT` - API key expired or invalid

### How to Get New API Key

1. **Login to GoHighLevel**
   - Go to https://app.gohighlevel.com

2. **Navigate to Settings**
   - Click Settings (gear icon) → Integrations → API Keys

3. **Create New API Key**
   - Click "Create API Key"
   - Name: `Chief AI Officer Alpha Swarm`
   - Select permissions:
     - ✅ Contacts (Read/Write)
     - ✅ Opportunities (Read/Write)
     - ✅ Calendars (Read)
     - ✅ Conversations (Read/Write)
   - Copy the generated key

4. **Get Location ID**
   - Go to Settings → Business Profile
   - Copy the Location ID from the URL or settings

5. **Update .env file**
   ```
   GHL_API_KEY=your_new_api_key_here
   GHL_LOCATION_ID=your_location_id_here
   ```

### Test Connection
```bash
python execution/test_connections.py
```

---

## Priority 3: Instantly 🔧 Fix Required

### Issue
`Invalid API key` - Need valid Instantly API key

### How to Get API Key

1. **Login to Instantly**
   - Go to https://app.instantly.ai

2. **Navigate to Settings**
   - Click your profile → Settings → Integrations → API

3. **Copy API Key**
   - Your API key is displayed on this page
   - If not visible, click "Generate New Key"

4. **Update .env file**
   ```
   INSTANTLY_API_KEY=your_instantly_api_key_here
   ```

### Test Connection
```bash
python -c "
import requests
key = 'YOUR_KEY_HERE'
r = requests.get(f'https://api.instantly.ai/api/v1/account/list?api_key={key}')
print(r.status_code, r.json() if r.status_code == 200 else r.text)
"
```

---

## Priority 4: LinkedIn Session 🔧 Fix Required

### Issue
`HTTP 403` - LinkedIn session cookie expired

### How to Get li_at Cookie

1. **Login to LinkedIn**
   - Go to https://www.linkedin.com and login

2. **Open Developer Tools**
   - Press F12 or right-click → Inspect

3. **Navigate to Cookies**
   - Go to Application tab → Cookies → linkedin.com

4. **Find li_at Cookie**
   - Search for `li_at` in the cookie list
   - Copy the entire value (long string)

5. **Update .env file**
   ```
   LINKEDIN_COOKIE=AQEDAxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

### Important Notes
- Cookie expires after ~1 year but can be invalidated if LinkedIn detects automation
- Use rate limiting to avoid detection
- Consider using LinkedIn's official API for production

### Test Connection
```bash
python -c "
import requests
cookie = 'YOUR_LI_AT_VALUE'
headers = {'Cookie': f'li_at={cookie}', 'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://www.linkedin.com/voyager/api/me', headers=headers)
print('Success' if r.status_code == 200 else f'Failed: {r.status_code}')
"
```

---

## Priority 5: Clay ✅ Valid

Already configured. Key format validated.

```
CLAY_API_KEY=your_clay_key
```

---

## Priority 6: RB2B ✅ Valid

Already configured. Key format validated.

```
RB2B_API_KEY=your_rb2b_key
```

---

## Quick Test All Connections

After updating your `.env` file with new credentials:

```bash
cd chiefaiofficer-alpha-swarm
python execution/test_connections.py
```

Expected output when all configured:
```
Required Services: 6/6 passed
Optional Services: 2/2 passed
✅ All required services connected! Ready to proceed.
```

---

## After All APIs Connected

Run the signal sync job:

```bash
# Sync engagement signals from all platforms
python execution/sync_engagement_signals.py

# Or sync from specific source
python execution/sync_engagement_signals.py --source ghl
python execution/sync_engagement_signals.py --source instantly
```

---

## .env Template

```bash
# Supabase (Data Layer)
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJ...

# GoHighLevel (Warm Leads CRM)
GHL_API_KEY=your_ghl_api_key
GHL_LOCATION_ID=your_location_id

# Instantly (Cold Outreach)
INSTANTLY_API_KEY=your_instantly_key

# LinkedIn (Scraping)
LINKEDIN_COOKIE=AQEDAxxxxxxxx

# Clay (Enrichment)
CLAY_API_KEY=your_clay_key

# RB2B (Website Visitors)
RB2B_API_KEY=your_rb2b_key

# Optional
ANTHROPIC_API_KEY=your_anthropic_key
EXA_API_KEY=your_exa_key
```
