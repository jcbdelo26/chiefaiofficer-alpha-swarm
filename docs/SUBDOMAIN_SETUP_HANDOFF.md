# Subdomain Setup Handoff: business.chiefaiofficer.com

**Document Purpose:** Step-by-step guide for setting up a new sending subdomain in GHL and Cloudflare for cold email outreach.

**Prepared For:** GTM Engineer / Agent Manager  
**Technical Level:** Non-technical (detailed screenshots-style instructions)  
**Estimated Time:** 45-60 minutes

---

## 📋 EXECUTIVE SUMMARY

**Goal:** Create `business.chiefaiofficer.com` as a secondary sending domain to:
- Protect `b2b.chiefaiofficer.com` reputation
- Handle Tier 3 (lower-value) outreach volume
- Enable future scaling without risking primary domain

**Key Decision:** Route Tier 3 leads to `business.` **AFTER warmup is complete** (2-3 weeks), not during warmup.

---

## 🎯 WHEN TO ROUTE TIER 3 TO business.chiefaiofficer.com

### ❌ NOT During Warmup

| Why Not | Risk |
|---------|------|
| New domain has no reputation | Emails go to spam |
| High volume on cold domain | Triggers spam filters |
| Tier 3 has lower engagement | Damages new domain fast |
| No baseline metrics yet | Can't detect problems |

### ✅ AFTER Warmup Complete (Week 3-4)

| Condition | Target | Before Routing Tier 3 |
|-----------|--------|----------------------|
| Warmup days completed | 14-21 days | ✓ Required |
| Open rate | >40% | ✓ Required |
| Reply rate | >3% | ✓ Required |
| Bounce rate | <2% | ✓ Required |
| Spam complaints | 0 | ✓ Required |
| Total sends during warmup | 300-500 | ✓ Required |

**Rule:** Only route Tier 3 to `business.` when ALL conditions are met.

---

## 📍 PART 1: CLOUDFLARE DNS SETUP

### Step 1.1: Log into Cloudflare

1. Go to: **https://dash.cloudflare.com**
2. Enter your email and password
3. Select the domain: **chiefaiofficer.com**

### Step 1.2: Navigate to DNS Settings

1. In the left sidebar, click **"DNS"**
2. Click **"Records"** (should be the default view)
3. You'll see a list of existing DNS records

### Step 1.3: Add MX Record for business.chiefaiofficer.com

This tells email servers where to deliver mail for `business.chiefaiofficer.com`.

1. Click the blue **"+ Add record"** button
2. Fill in:
   - **Type:** Select `MX`
   - **Name:** Enter `business`
   - **Mail server:** Enter `smtp.leadconnectorhq.com` (GHL's mail server)
   - **Priority:** Enter `10`
   - **TTL:** Leave as `Auto`
   - **Proxy status:** Make sure it shows **DNS only** (gray cloud, NOT orange)
3. Click **"Save"**

### Step 1.4: Add SPF Record

SPF tells receiving servers which servers are allowed to send email for your domain.

1. Click **"+ Add record"**
2. Fill in:
   - **Type:** Select `TXT`
   - **Name:** Enter `business`
   - **Content:** Enter exactly:
     ```
     v=spf1 include:_spf.leadconnectorhq.com ~all
     ```
   - **TTL:** Leave as `Auto`
3. Click **"Save"**

### Step 1.5: Add DKIM Records

DKIM adds a digital signature to verify emails are legitimate. GHL requires specific DKIM records.

**Record 1:**
1. Click **"+ Add record"**
2. Fill in:
   - **Type:** Select `CNAME`
   - **Name:** Enter `lc1._domainkey.business`
   - **Target:** Enter `lc1._domainkey.leadconnectorhq.com`
   - **TTL:** Leave as `Auto`
   - **Proxy status:** **DNS only** (gray cloud)
3. Click **"Save"**

**Record 2:**
1. Click **"+ Add record"**
2. Fill in:
   - **Type:** Select `CNAME`
   - **Name:** Enter `lc2._domainkey.business`
   - **Target:** Enter `lc2._domainkey.leadconnectorhq.com`
   - **TTL:** Leave as `Auto`
   - **Proxy status:** **DNS only** (gray cloud)
3. Click **"Save"**

### Step 1.6: Add DMARC Record

DMARC tells receiving servers what to do with emails that fail SPF/DKIM checks.

1. Click **"+ Add record"**
2. Fill in:
   - **Type:** Select `TXT`
   - **Name:** Enter `_dmarc.business`
   - **Content:** Enter exactly:
     ```
     v=DMARC1; p=none; rua=mailto:dmarc@chiefaiofficer.com
     ```
   - **TTL:** Leave as `Auto`
3. Click **"Save"**

### Step 1.7: Verify Your DNS Records

Your DNS records should now look like this:

| Type | Name | Content/Target |
|------|------|----------------|
| MX | business | smtp.leadconnectorhq.com (Priority: 10) |
| TXT | business | v=spf1 include:_spf.leadconnectorhq.com ~all |
| CNAME | lc1._domainkey.business | lc1._domainkey.leadconnectorhq.com |
| CNAME | lc2._domainkey.business | lc2._domainkey.leadconnectorhq.com |
| TXT | _dmarc.business | v=DMARC1; p=none; rua=mailto:dmarc@chiefaiofficer.com |

**⏰ Wait 15-30 minutes** for DNS changes to propagate before proceeding to GHL.

---

## 📍 PART 2: GHL SUB-ACCOUNT SETUP

### Step 2.1: Log into GoHighLevel

1. Go to: **https://app.gohighlevel.com**
2. Log in with your credentials
3. Switch to sub-account: **CAIO Corporate**
   - Click on the account name in the top-left
   - Select "CAIO Corporate" from the dropdown

### Step 2.2: Navigate to Email Settings

1. Click **"Settings"** (gear icon) in the left sidebar
2. Scroll down and click **"Email Services"**
3. Click on the **"Domains"** tab

### Step 2.3: Add New Sending Domain

1. Click the **"+ Add Domain"** button
2. Enter: `business.chiefaiofficer.com`
3. Click **"Add Domain"**

### Step 2.4: Verify Domain in GHL

GHL will show you the required DNS records. Since you already added them:

1. Click **"Verify Domain"** or **"Check DNS"**
2. Wait for GHL to verify each record:
   - ✅ MX Record
   - ✅ SPF Record
   - ✅ DKIM Records (2)
   - ✅ DMARC Record

**If verification fails:**
- Wait 30 more minutes (DNS propagation)
- Double-check spelling in Cloudflare
- Make sure proxy is OFF (gray cloud) for CNAME records

### Step 2.5: Set Up Sending Email Address

1. Once domain is verified, click on `business.chiefaiofficer.com`
2. Click **"+ Add Email"**
3. Create sending email:
   - **Email:** `dani@business.chiefaiofficer.com`
   - **Display Name:** `Dani Apgar`
   - **Reply-To:** `dani@chiefaiofficer.com` (routes replies to main inbox)
4. Click **"Save"**

### Step 2.6: Test Email Delivery

1. Click **"Send Test Email"**
2. Enter your personal email address
3. Click **"Send"**
4. Check your inbox (and spam folder)
5. Verify:
   - ✅ Email arrived
   - ✅ Sender shows as `Dani Apgar <dani@business.chiefaiofficer.com>`
   - ✅ NOT in spam folder

---

## 📍 PART 3: WARMUP PROTOCOL

### 3.1 Warmup Schedule (21 Days)

**Important:** During warmup, only send to ENGAGED contacts (people who have interacted before).

| Week | Day | Daily Sends | Who to Send To |
|------|-----|-------------|----------------|
| 1 | 1-2 | 5/day | Internal team only |
| 1 | 3-4 | 10/day | Warm contacts (existing relationships) |
| 1 | 5-7 | 15/day | Warm contacts + newsletter subscribers |
| 2 | 8-10 | 25/day | Warm contacts + Tier 1 replies (engaged leads) |
| 2 | 11-14 | 40/day | Mix of warm + select Tier 2 |
| 3 | 15-17 | 60/day | Tier 2 engaged leads |
| 3 | 18-21 | 80/day | Tier 2 + select cold Tier 3 (test batch) |

### 3.2 Warmup Best Practices

| Do ✅ | Don't ❌ |
|-------|---------|
| Send to people who will open/reply | Send to purchased lists |
| Mix in internal team emails | Blast 100 emails on day 1 |
| Encourage replies (ask questions) | Use hard-sell CTAs |
| Send during business hours | Send at 2am |
| Monitor metrics daily | Ignore bounce alerts |
| Pause if bounces spike | Keep sending through problems |

### 3.3 Daily Monitoring Checklist

Every day during warmup, check:

| Metric | Target | Action if Below |
|--------|--------|-----------------|
| Open rate | >50% | Improve subject lines |
| Reply rate | >5% | Add more questions in email |
| Bounce rate | <1% | Clean list, pause if >2% |
| Spam complaints | 0 | STOP immediately, investigate |

### 3.4 Warmup Email Content Tips

**Good warmup emails:**
- Ask a genuine question (encourages reply)
- Keep it short (2-3 sentences)
- No links or images (in first week)
- Personal tone, not salesy

**Example warmup email:**
```
Subject: Quick question

Hi [Name],

I'm testing a new email setup and wanted to make sure 
it's working properly.

Could you do me a quick favor and just reply "got it"?

Thanks!
Dani
```

---

## 📍 PART 4: TIER 3 ROUTING CONFIGURATION

### 4.1 When to Start Routing Tier 3

**Checklist before routing Tier 3 to business.chiefaiofficer.com:**

```
□ Warmup completed (21 days minimum)
□ Total sends during warmup: 300+
□ Open rate during warmup: >40%
□ Reply rate during warmup: >3%
□ Bounce rate: <2%
□ Spam complaints: 0
□ Domain verified healthy in GHL
□ Dani approves transition
```

**Only proceed when ALL boxes are checked.**

### 4.2 Gradual Tier 3 Transition

Don't switch all Tier 3 at once. Use this schedule:

| Week | % of Tier 3 to business.* | Daily Volume |
|------|---------------------------|--------------|
| Week 4 | 25% | 25-30/day |
| Week 5 | 50% | 40-50/day |
| Week 6 | 75% | 60-75/day |
| Week 7+ | 100% | 80-100/day |

### 4.3 Update Swarm Configuration

Once ready, update the swarm to route Tier 3:

**File:** `config/domain_protection.json`

Change:
```json
"tier_3_general": {
  "domain": "business.chiefaiofficer.com",
  "available": true  // Change from false to true
}
```

**File:** `config/production.json`

Add:
```json
"sending_domains": {
  "tier_1": "b2b.chiefaiofficer.com",
  "tier_2": "b2b.chiefaiofficer.com",
  "tier_3": "business.chiefaiofficer.com"
}
```

---

## 📍 PART 5: TROUBLESHOOTING

### DNS Records Not Verifying

| Problem | Solution |
|---------|----------|
| "Record not found" | Wait 30 more minutes for propagation |
| SPF error | Check for typos, must be exact |
| DKIM error | Make sure proxy is OFF (gray cloud) |
| Multiple SPF records | Delete old SPF, only one allowed |

### Emails Going to Spam

| Problem | Solution |
|---------|----------|
| New domain, no reputation | Continue warmup, send to engaged contacts |
| SPF/DKIM failing | Verify DNS records in GHL |
| Content triggering filters | Remove links, images, spam words |
| Sending too fast | Reduce daily volume |

### High Bounce Rate

| Problem | Solution |
|---------|----------|
| >2% bounces | PAUSE immediately |
| Invalid emails | Clean your list, use email verification |
| Domain reputation | Slow down, warmup longer |

---

## 📍 PART 6: TIMELINE SUMMARY

```
┌─────────────────────────────────────────────────────────────────┐
│  SUBDOMAIN LAUNCH TIMELINE                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Day 0: DNS + GHL Setup                                         │
│  └─ Add DNS records in Cloudflare (30 min)                      │
│  └─ Verify domain in GHL (30 min)                               │
│  └─ Send test email                                             │
│                                                                 │
│  Week 1: Light Warmup                                           │
│  └─ 5-15 emails/day to internal + warm contacts                 │
│  └─ Monitor open/reply rates                                    │
│                                                                 │
│  Week 2: Moderate Warmup                                        │
│  └─ 25-40 emails/day to warm + select Tier 2                    │
│  └─ Add variety in recipients                                   │
│                                                                 │
│  Week 3: Full Warmup                                            │
│  └─ 60-80 emails/day                                            │
│  └─ Test small batch of Tier 3                                  │
│                                                                 │
│  Week 4: Transition Decision                                    │
│  └─ Review all metrics                                          │
│  └─ If healthy → Start routing 25% of Tier 3                    │
│  └─ If issues → Extend warmup 1 more week                       │
│                                                                 │
│  Week 5-7: Gradual Tier 3 Increase                              │
│  └─ 50% → 75% → 100% of Tier 3                                  │
│  └─ Monitor for reputation drops                                │
│                                                                 │
│  Week 8+: Full Production                                       │
│  └─ b2b.* = Tier 1 & 2 only                                     │
│  └─ business.* = All Tier 3                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📍 PART 7: CONTACTS & ESCALATION

| Question Type | Contact |
|---------------|---------|
| DNS/Cloudflare issues | tech@chiefaiofficer.com |
| GHL configuration | GHL support or tech team |
| Warmup strategy | dani@chiefaiofficer.com |
| Tier routing decisions | dani@chiefaiofficer.com |

---

## ✅ HANDOFF CHECKLIST

Before marking this task complete:

```
□ DNS records added in Cloudflare (5 records)
□ Domain verified in GHL
□ Sending email created (dani@business.chiefaiofficer.com)
□ Test email received successfully
□ Warmup schedule documented
□ Dani notified that warmup is starting
□ Daily monitoring plan in place
```

---

**Document Version:** 1.0  
**Created:** January 28, 2026  
**Author:** AI Agent Manager  
**Next Review:** After warmup complete (Week 4)
