# Pre-Live Input Guide for PTO / GTM Engineer

**What this is**: A short walkthrough of the remaining inputs YOU need to provide before the swarm can go live. Most variables are already configured on Railway — this guide covers only what's genuinely missing.

**Time estimate**: ~10 minutes

**When you're done**: Hand this doc back to Claude with "I've completed the PTO inputs" and Claude will run the automated smoke tests.

---

## What's Already Done (DO NOT touch these)

From your Railway screenshots, the following are **already configured and working**. Do NOT regenerate or change them:

| Variable | Status |
|----------|--------|
| `DASHBOARD_AUTH_TOKEN` | SET |
| `DASHBOARD_AUTH_STRICT` | SET |
| `CORS_ALLOWED_ORIGINS` | SET |
| `REDIS_URL` | SET (Upstash) |
| `REDIS_REQUIRED` | SET |
| `INNGEST_*` (all 7 vars) | SET |
| `RB2B_WEBHOOK_SECRET` | SET |
| `WEBHOOK_SIGNATURE_REQUIRED` | SET (`false`) |
| `STATE_BACKEND` | SET (`redis`) |
| All GHL, Supabase, Twilio, SendGrid, Slack, Apollo, Instantly, HeyReach vars | SET |

**Bottom line**: Codex already did the heavy lifting. You only need **1 new variable** + configure 2 provider dashboards.

---

## Background: Why Bearer Token (Not HMAC Signing)

From your screenshots we confirmed:
- **Instantly**: Has "Add header" toggle on each webhook — can send custom headers
- **Clay**: Has "Headers" section with "+ Add a new Key and Value pair" — can send custom headers
- **HeyReach**: Has NO custom header or signing support — URL-only webhooks

Since none of these providers support HMAC webhook signing, we use **bearer token auth** as the fallback. One shared token is added to Railway and configured as an `Authorization: Bearer <token>` header in Instantly and Clay. HeyReach stays unauthenticated (no option to add headers).

---

## Step 1: Generate 1 Bearer Token (2 min)

Open your password manager (1Password, Bitwarden, etc.) and generate **one** random string:
- **Length**: 48+ characters
- **Characters**: alphanumeric (letters + numbers)
- **Save it** in your vault — you'll paste it in 3 places

---

## Step 2: Add to Railway (1 min)

1. Open **Railway > caio-swarm-dashboard > Variables**
2. Click **"New Variable"**
3. Name: `WEBHOOK_BEARER_TOKEN`
4. Value: paste the token you just generated
5. Click the checkmark to save
6. Railway will auto-redeploy

That's the only new Railway variable needed.

---

## Step 3: Configure Instantly Webhooks (5 min)

You have 4 registered webhooks in Instantly. For **each one**:

1. Go to **https://app.instantly.ai > Settings > Webhooks**
2. Click the **pencil icon** (Edit) on the first webhook
3. Toggle ON **"Add header"** (the switch below the URL field)
4. In the header fields that appear:
   - **Key**: `Authorization`
   - **Value**: `Bearer <paste your token here>`

   Example: if your token is `abc123xyz...`, the value should be:
   ```
   Bearer abc123xyz...
   ```
5. Click **Save**
6. Repeat for all 4 webhooks (reply, bounce, open, unsubscribe)

---

## Step 4: Configure Clay HTTP API Column (2 min)

1. Go to **https://app.clay.com** > workbook **"CAIO RB2B ABM Leads Enrichment"**
2. Find the **HTTP API** column (the one that POSTs to your webhook URL)
3. Click to edit the column settings
4. In the **Headers** section, click **"+ Add a new Key and Value pair"**
5. Fill in:
   - **Key**: `Authorization`
   - **Value**: `Bearer <paste your same token here>`
6. Save

---

## Step 5: HeyReach — No Action Needed

HeyReach doesn't support custom headers on webhooks. The swarm code handles this gracefully — HeyReach webhooks will work without authentication since `WEBHOOK_SIGNATURE_REQUIRED` is set to `false`.

---

## Step 6: Hand Off to Claude

Come back to Claude and say:

```
I've completed the PTO inputs.

Variables added to Railway:
- WEBHOOK_BEARER_TOKEN: done

Provider header configuration:
- Instantly: Authorization header added to all 4 webhooks
- Clay: Authorization header added to HTTP API column
- HeyReach: No action (no header support)

Production URL: https://caio-swarm-dashboard-production.up.railway.app
Dashboard token: [your existing DASHBOARD_AUTH_TOKEN]
```

Claude will then run the auth smoke matrix and runtime dependency checks.

---

## Auth Summary

| Provider | Auth Method | What You Did |
|----------|-----------|-------------|
| **RB2B** | HMAC signing (already working) | Nothing — already configured |
| **Instantly** | Bearer token via "Add header" | Added `Authorization` header to 4 webhooks |
| **Clay** | Bearer token via Headers section | Added `Authorization` header to HTTP API column |
| **HeyReach** | None (no header support) | Nothing — accepted as-is |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "I can't find the Add header toggle in Instantly" | Click the pencil (edit) icon on a webhook — the toggle appears below the URL field |
| "Railway says variable already exists" | Good — that means it's already set. Don't duplicate it. |
| "Deployment failed after adding variables" | Check for typos in the variable name. It must be exactly `WEBHOOK_BEARER_TOKEN`. |
| "I accidentally pasted different tokens in Railway vs Instantly" | They must match exactly. Update whichever one is wrong to match the other. |
| "Clay column doesn't show Headers section" | Make sure you're editing the HTTP API column (the one with the POST action), not the webhook source. |

---

*Updated 2026-02-18 — Revised to use bearer token auth after confirming providers don't support HMAC signing.*
