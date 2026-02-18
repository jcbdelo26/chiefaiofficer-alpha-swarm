# CAIO Alpha Swarm — Operational Roadmap & Daily Playbook

**Audience**: PTO / GTM Engineer (non-technical)
**Updated**: 2026-02-18
**Status**: Phase 4E — Supervised Live Sends (RAMP MODE ACTIVE)

---

## 1. Executive Summary

### What's Deployed

| Item | Value |
|------|-------|
| Production URL | `https://caio-swarm-dashboard-production.up.railway.app` |
| Latest commits | `b2c14a9` (bearer token auth), `890df6d` (HeyReach fix) |
| Pipeline runs | 33 total, 10 consecutive 6/6 PASS |
| Auth status | Webhook bearer token + HMAC verified, dashboard auth enforced |
| Ramp mode | 5 emails/day, tier_1 only, 3 supervised days |

### System Health (Verified 2026-02-18)

| Component | Status |
|-----------|--------|
| 12/12 Agents | Healthy, all circuits closed |
| Redis (Upstash) | Connected, 35ms latency |
| Inngest | Keys present, route mounted |
| Webhook auth | All 4 providers authed (Instantly=bearer, Clay=bearer, RB2B=HMAC, HeyReach=no-auth-accepted) |
| GHL, Clay, Supabase | Healthy, circuits closed |
| 5/5 MCP Servers | Healthy |
| LinkedIn | Degraded (cookie auth, non-blocking — HeyReach uses API) |

### Known Issues (Non-Blocking)

| Issue | Impact | Action |
|-------|--------|--------|
| Inngest `pipeline-scan` returning 500 | Cron function only. Does not affect pipeline, webhooks, or email sends | Will fix separately |
| LinkedIn integration half_open | Cookie-based auth is fragile. HeyReach uses API key (unaffected) | No action needed |

---

## 2. Phase 1 — First Live Sends (Days 1-3)

### 2.1 Run Your First Pipeline

Open a terminal in the project directory and run:

```
echo yes | python execution/run_pipeline.py --mode production --source "wpromote" --limit 3
```

**What each flag does**:

| Flag | What It Does |
|------|-------------|
| `echo yes \|` | Auto-confirms the production safety prompt (non-interactive) |
| `--mode production` | Uses real Apollo enrichment + real ICP scoring |
| `--source "wpromote"` | Scrapes leads from Wpromote (Tier 1 ICP target) |
| `--limit 3` | Process only 3 leads (safe for Day 1) |

**Other source options** (Tier 1 ICP targets):

```
wpromote, tinuiti, power-digital, insight-global, kforce,
slalom, west-monroe, shipbob, chili-piper
```

**What happens after the pipeline runs**:
1. HUNTER scrapes 3 leads from the company
2. ENRICHER enriches them via Apollo (email, title, company data)
3. SEGMENTOR scores them (ICP tier + score)
4. CRAFTER generates personalized emails using the matching template
5. GATEKEEPER queues tier_1 leads for approval
6. SEND stage writes shadow emails to the HoS approval queue

Emails now appear at: **`https://caio-swarm-dashboard-production.up.railway.app/sales`**

---

### 2.2 HoS Email Review Guide

#### What You See in the Approval Queue

Each email card shows these fields:

| Field | What to Check |
|-------|--------------|
| **Recipient name** | Is the name spelled correctly? Does it match the company? |
| **Company** | Is this a real company we want to target? |
| **Title** | Is this person actually C-Suite/VP? (tier_1 = C-Suite only during ramp) |
| **Industry** | Does the industry match what's in the email body? |
| **Email address** | Does the domain match the company? (e.g., `@wpromote.com`) |
| **Subject line** | Does it sound human? Would YOU open this email? |
| **Email body** | Read every word. See the review checklist below. |
| **Tier** | Should show `tier_1` during ramp mode |
| **Angle** | Template used (e.g., `t1_executive_buyin`) |
| **ICP Score** | Higher = better fit. Tier 1 = 80+ |

#### RAMP MODE Banner

The top of the HoS dashboard shows a live status bar:
- **Day X/3** — Which supervised day you're on
- **Sent Y/5** — How many emails sent today vs. daily limit
- **Tier: tier_1** — Only C-Suite leads during ramp
- Refreshes every 30 seconds from `/api/operator/status`

#### Email Review Checklist (Check All 8 Before Approving)

- [ ] **Subject line**: Does it sound like a real person wrote it? Would you open it? Not too salesy?
- [ ] **Opening hook**: Is the first sentence specific to this person/company, not generic?
- [ ] **Company reference**: Is the company name correct and used naturally (not forced)?
- [ ] **Industry reference**: Does the industry mention match reality? (e.g., "marketing & advertising" for Wpromote)
- [ ] **CTA**: Is the call-to-action soft and appropriate? (No "book a demo" — should be "worth a brief chat?" or "mind if I send a resource?")
- [ ] **M.A.P. Framework**: If `t1_executive_buyin` or `t2_ops_efficiency` template, verify it mentions "M.A.P." (Measure, Automate, Prove)
- [ ] **Sender signature**: Should show "Dani Apgar, Chief AI Officer" with calendar link `https://caio.cx/ai-exec-briefing-call`
- [ ] **CAN-SPAM footer**: Must end with "Reply STOP to unsubscribe" + physical address

#### Common Edits to Make

| Problem | How to Fix |
|---------|-----------|
| "I noticed that your company..." | Change to something specific: "Saw Wpromote's recent campaign for [client]..." |
| Generic industry reference | Replace with specific detail about the company |
| Too formal/robotic | Make it conversational. Read it aloud — if it sounds stiff, rewrite it |
| Weak CTA like "let me know if interested" | Replace with specific: "Worth a 15-minute call this week?" |
| Template variables not filled | e.g., `{{lead.industry}}` still showing — reject and report |

#### Actions Available

| Action | What It Does | When to Use |
|--------|-------------|-------------|
| **Approve** | Marks email as approved, queues for Instantly dispatch | Email passes all 8 checklist items |
| **Edit + Approve** | Lets you modify the body/subject, then approves | Email is close but needs tweaks |
| **Reject** | Marks email as rejected with your reason | Wrong person, wrong company, or bad template output |

---

### 2.3 Instantly Campaign Verification

After you approve emails, the OPERATOR dispatches them to Instantly. Verify:

**Step 1**: Go to `https://app.instantly.ai` > **Campaigns**

**Step 2**: Find the new campaign. Naming pattern:
```
t1_pipeline_YYYYMMDD_v1
```
Example: `t1_pipeline_20260218_v1`

**Step 3**: Verify these items:

| Check | Expected | If Wrong |
|-------|----------|----------|
| Campaign status | **DRAFTED** (paused by default) | If ACTIVE, it's already sending — check if intended |
| Number of leads | Matches how many you approved | If fewer, check deliverability guards filtered some |
| Lead emails | Match the ones you approved | If different emails, report immediately |
| Lead names/companies | Match what you saw in HoS queue | Confirms enrichment data is flowing correctly |
| Sender accounts | `chris.d@` across 6 domains | If different sender format, report |

**Step 4**: Check sender accounts in campaign settings:
```
chris.d@chiefaiofficerai.com
chris.d@chiefaiofficerconsulting.com
chris.d@chiefaiofficerguide.com
chris.d@chiefaiofficerlabs.com
chris.d@chiefaiofficerresources.com
chris.d@chiefaiofficersolutions.com
```
All 6 should show 100% health. Round-robin rotation (not all 6 per email — Instantly rotates automatically).

**Step 5**: Check custom variables on a lead:

| Variable | Should Contain |
|----------|---------------|
| `title` | Lead's job title (e.g., "Chief Revenue Officer") |
| `icpTier` | `tier_1` (during ramp) |
| `icpScore` | Number 80-100 |
| `sourceType` | `pipeline` |
| `campaignType` | Template name (e.g., `t1_executive_buyin`) |

**Step 6**: Activation

Campaigns start DRAFTED. To activate, you have two options:
1. **Dashboard**: Use the Instantly management section in the HoS dashboard
2. **Direct**: The OPERATOR can activate via `/api/instantly/campaigns/{id}/activate` (requires dashboard token)

**NEVER activate directly in Instantly UI** — always use the dashboard so the system tracks it.

---

### 2.4 Daily Ramp Schedule

| Day | Max Sends | What to Do |
|-----|-----------|-----------|
| **Day 1** | 3-5 | Run pipeline with `--limit 3`. Hand-approve every email. Read every word. Check Instantly campaign after approval. |
| **Day 2** | 5 | Run pipeline with `--limit 5`. Still hand-approve. Note patterns: are you making the same edits repeatedly? (If so, the template needs updating.) |
| **Day 3** | 5 | Run pipeline with `--limit 5`. Check: 0 bounces? >35% open rate? If both yes, ready for Phase 2. |

**If you get a bounce on any day**: STOP. Check:
1. Was the bounced email a real address? (Sometimes Apollo returns stale data)
2. Is the domain on our excluded list? (If not, add it)
3. Was it a hard bounce or soft bounce? (Hard = bad address. Soft = temporary, retry later)

---

## 3. Daily Monitoring Ritual

### Morning Checklist (Do This Every Day)

#### Check 1: Instantly Domain Health
- **Where**: `https://app.instantly.ai` > **Accounts** > Each domain
- **Target**: All 6 domains at **100% health**
- **Red flag**: Any domain below **95%** — pause all campaigns from that domain immediately

#### Check 2: Instantly Open Rates
- **Where**: `https://app.instantly.ai` > **Analytics**
- **Target**: **>40% open rate** (Days 1-3), **>30%** ongoing
- **Red flag**: Open rate **<25%** — subject lines need work, or deliverability issue

#### Check 3: Railway Deploy Logs
- **Where**: `https://railway.com` > caio-swarm-dashboard > **Deploy Logs**
- **Look for**: Any lines with `CRITICAL` or `WARNING` or `Error`
- **Ignore**: Inngest `pipeline-scan` 500s (known, non-blocking)
- **Red flag**: New errors you haven't seen before — screenshot and investigate

#### Check 4: HoS Dashboard
- **Where**: `https://caio-swarm-dashboard-production.up.railway.app/sales`
- **Look for**: New pending emails, any bounced/replied status updates
- **Action**: Approve pending emails, note any replies for follow-up

#### Check 5: Slack Alerts
- **Where**: Your Slack channel (webhook-connected)
- **Alert levels**:
  - **INFO** (green): Reply received, campaign created — no action needed
  - **WARNING** (yellow): Bounce, unsubscribe, rate limit — review the details
  - **CRITICAL** (red): Emergency stop, circuit breaker open — take immediate action

#### Check 6: System Health
- **URL**: `https://caio-swarm-dashboard-production.up.railway.app/api/health/ready`
- **Expected**: `{"status": "ready", "runtime_dependencies": {"ready": true}}`
- **Red flag**: Any dependency showing `ready: false`

#### Check 7: Ramp Progress
- **URL**: `https://caio-swarm-dashboard-production.up.railway.app/api/operator/status`
- **Shows**: Day X/3, sent today, daily limit, tier filter
- **Or**: Check the RAMP MODE banner on the HoS dashboard (`/sales`)

---

### Webhook Event Reference

When leads interact with your emails, webhooks fire automatically:

| Event | What Happens | Lead Status Becomes | GHL Tag Added | Added to Suppression | Slack Alert |
|-------|-------------|--------------------|--------------|--------------------|-------------|
| **Reply received** | Lead replied to your email | `replied` | `status-replied` | No | INFO |
| **Email bounced** | Email address invalid/rejected | `bounced` | `status-bounced` | Yes | WARNING |
| **Email opened** | Lead opened the email | `opened` (or `engaged_not_replied` if 2+ opens) | None | No | None |
| **Unsubscribed** | Lead opted out (compliance-critical) | `unsubscribed` | `status-unsubscribed` + `DNC` | Yes | WARNING |

### Red Flags — Stop Everything

| Signal | Action |
|--------|--------|
| Any domain health drops below 95% | Pause ALL campaigns on that domain. Check DNS, check if emails are hitting spam. |
| Bounce rate exceeds 5% | Stop sending immediately. Audit the email list — likely stale Apollo data. |
| `EMERGENCY_STOP` env var set to `true` | All outbound is halted across the system. This is the kill switch. |
| Circuit breaker OPEN alert (Slack CRITICAL) | A provider integration is failing repeatedly. Check which one and investigate. |
| Unsubscribe from a current customer | Add their email to Guard 4 exclusion list in `production.json` immediately. |

---

## 4. Phase 2 — Graduation (Days 4-10)

### Graduation Criteria

ALL of these must be true to move past ramp mode:

- [ ] 3 consecutive clean days completed (Days 1-3)
- [ ] 0 hard bounces across all 3 days
- [ ] 0 spam complaints
- [ ] Open rate >35% sustained
- [ ] All 6 domain health scores still at 100%
- [ ] No CRITICAL Slack alerts

### Graduation Action

Tell Claude:

> "Set operator.ramp.enabled to false in config/production.json and increase the daily ceiling to 25. Push to Railway."

**What changes**:

| Setting | Before (Ramp) | After (Graduated) |
|---------|--------------|-------------------|
| Daily ceiling | 5 | 25 |
| Tier filter | tier_1 only | All tiers (tier_1 + tier_2 + tier_3) |
| Templates active | 4 (tier_1 only) | All 11 |
| Approval required | Yes (hand-approve all) | Yes (but you can batch-approve) |

### Reply Tracking (Start on Day 4)

Every reply that comes in, categorize it:

| Category | Example Replies | Next Step |
|----------|----------------|-----------|
| **Hot** | "Let's talk", "When are you available?", "Send more info" | Book meeting within 24 hours via GHL |
| **Warm** | "Not right now but interesting", "Forward to my colleague" | Add to cadence Day 10 follow-up |
| **Negative** | "Not interested", "Remove me" | Respect immediately, auto-handled by signal loop |
| **Auto-reply** | OOO, generic acknowledgment | Ignore, cadence handles timing |

**Where to find replies**:
1. **Slack**: INFO alert fires with reply preview
2. **GHL**: Contact tagged `status-replied`
3. **Instantly**: Analytics > Replies tab
4. **Leads Dashboard**: `https://caio-swarm-dashboard-production.up.railway.app/leads` — lead shows `replied` status

### Revenue Attribution (Start Tracking Now)

Keep a simple spreadsheet:

| Date | Lead Name | Company | Template Used | Reply Category | Meeting Booked? | Deal Value |
|------|-----------|---------|--------------|----------------|-----------------|------------|
| 2026-02-19 | Andrew Mahr | Wpromote | t1_executive_buyin | Hot | Yes | $TBD |

---

## 5. Phase 3 — Multi-Channel / LinkedIn (Weeks 2-3)

### LinkedIn Activation via HeyReach

**Prerequisites** (must be true before activating):
- [ ] Email channel graduated (Phase 2 complete)
- [ ] Open rate >30% sustained
- [ ] At least 5 replies received
- [ ] LinkedIn warmup completed (4 weeks from account creation)

**Existing CAIO HeyReach Campaigns**:

| Campaign ID | Name | Status |
|-------------|------|--------|
| 334314 | CAIO Campaign 1 | Pre-built |
| 334364 | CAIO Campaign 2 | Pre-built |
| 334381 | CAIO Campaign 3 | Pre-built |

**Shadow test first**: Tell Claude:

> "Run a shadow test of the HeyReach dispatcher with 5 leads from the latest pipeline run."

Monitor HeyReach dashboard for 48 hours. Check:
- Connection requests sent correctly?
- Profile views triggering?
- No errors in webhook events?

**Daily LinkedIn ceiling**: 5/day (warmup) → 20/day (graduated)

### 21-Day Cadence Sequence

Once both channels are active, leads enter the automated cadence:

| Step | Day | Channel | Action | What Happens | Exit If |
|------|-----|---------|--------|-------------|---------|
| 1 | 1 | Email | Intro | Personalized first email (from pipeline) | - |
| 2 | 2 | LinkedIn | Connect | Connection request sent via HeyReach | No LinkedIn URL |
| 3 | 5 | Email | Value follow-up | CRAFTER generates "quick resource" email | Replied |
| 4 | 7 | LinkedIn | Message | Direct message (only if connected) | Not connected |
| 5 | 10 | Email | Social proof | Case study / 27% productivity proof | Replied |
| 6 | 14 | LinkedIn | Follow-up | Second LinkedIn message | Not connected |
| 7 | 17 | Email | Break-up | "Closing the loop" — permission to stop | Replied |
| 8 | 21 | Email | Close | "Last note from me" — Yes/No/Not yet | Always (end) |

**Auto-exit triggers**: replied, meeting_booked, bounced, unsubscribed, linkedin_replied, rejected

**Cadence dashboard**: `https://caio-swarm-dashboard-production.up.railway.app` > use API endpoints:
- `/api/cadence/summary` — enrolled, active, completed, due today
- `/api/cadence/due` — what needs to go out today
- `/api/cadence/leads` — all cadence states

---

## 6. Phase 4 — Scaling (Weeks 3-8)

### Volume Ramp Schedule

**Never increase more than 2x in a single week.**

| Week | Email/Day | LinkedIn/Day | Total Touches/Day | Templates Active |
|------|-----------|-------------|-------------------|-----------------|
| Week 1-2 (Post-graduation) | 25 | 0 | 25 | All 11 |
| Week 3 | 50 | 5 | 55 | All 11 |
| Week 4 | 75 | 10 | 85 | All 11 |
| Week 6+ | 100 | 20 | 120 | All 11 |

To increase limits, tell Claude:

> "Update the email daily ceiling to [number] in production.json and push to Railway."

### Adding New ICP Targets

Once you exhaust your Tier 1 target list:

1. Analyze which companies replied positively — what do they have in common?
2. Find 10 similar companies (same size, industry, pain points)
3. Tell Claude: "Add [company1, company2, ...] to the scraper source list"
4. Run a small test batch: `--source "new_company" --limit 3`
5. Review quality before scaling

### Weekly Review Cadence (Every Friday)

- [ ] **Pipeline performance**: How many leads processed this week? Scrape-to-send conversion rate?
- [ ] **Reply analysis**: Categorize all replies. What's the hot lead percentage?
- [ ] **Template performance**: Which angles get the most opens/replies? Kill underperformers.
- [ ] **ICP refinement**: Any surprising wins from unexpected segments? Update scoring.
- [ ] **Cost review**: Apollo credits used, Instantly sends, Clay credits — ROI tracking.

---

## 7. Email Template Reference

### Tier 1 — C-Suite/Founders (4 Templates)

| Template | Subject Line A | Subject Line B | CTA | M.A.P.? |
|----------|---------------|---------------|-----|---------|
| `t1_executive_buyin` | "AI Roadmap for {{company}}" | "Quick question regarding {{company}}'s AI strategy" | "Worth a brief chat?" | Yes — Day 1 Bootcamp, risk-free guarantee |
| `t1_industry_specific` | "AI in {{industry}} / {{company}}" | "Automating {{company}}'s back-office?" | "Open to seeing a quick breakdown?" | No (implicit ROI) |
| `t1_hiring_trigger` | "Re: {{company}}'s AI hiring" | "Bridge strategy for {{company}}" | "Open to a 15-minute 'bridge strategy' call?" | No |
| `t1_value_first` | "2-minute AI readiness check for {{company}}" | "{{first_name}} - quick resource for {{industry}} leaders" | "Mind if I send the link? (No pitch)" | No (softest CTA) |

### Tier 2 — VP/CTO/Head of Innovation (3 Templates)

| Template | Subject Line A | Subject Line B | CTA | M.A.P.? |
|----------|---------------|---------------|-----|---------|
| `t2_tech_stack` | "AI for {{company}}'s tech stack" | "AI integration for {{industry}} teams" | "Would it help if I shared the AI playbook?" | No |
| `t2_ops_efficiency` | "{{company}}'s operational efficiency" | "{{first_name}} - cutting {{company}}'s overhead" | "Brief sync, or should I send a one-pager?" | Yes — Measure, Automate, Prove |
| `t2_innovation_champion` | "AI transformation at {{company}}" | "Building the AI Council" | "Mind if I send a 2-minute video?" | Yes — M.A.P. cycle + guarantee |

### Tier 3 — Directors/Managers/Smaller Teams (4 Templates)

| Template | Subject Line A | Subject Line B | CTA | M.A.P.? |
|----------|---------------|---------------|-----|---------|
| `t3_quick_win` | "Quick idea for {{company}}" | "One workflow to automate" | "Reply 'yes' for a 2-minute breakdown" | No |
| `t3_time_savings` | "{{first_name}} - 10 hours back per week" | "What if admin work did itself?" | "Should I send a quick video?" | No |
| `t3_competitor_fomo` | "What {{industry}} teams are automating" | "How competitors are scaling" | "Reply 'show me'" | No |
| `t3_diy_resource` | "Free AI checklist for {{industry}}" | "Quick resource for small teams" | "Mind if I send it? (No strings attached)" | No |

### Follow-Up Emails (2 Templates)

| Template | Delay | Subject | CTA |
|----------|-------|---------|-----|
| Follow-Up 1 (Value) | Day 3 | "Re: {{original_subject}}" | "Mind if I send the link? No pitch, no demo request" |
| Follow-Up 2 (Break-up) | Day 7 | "Closing the loop / {{company}}" | "Should I close your file?" |

### Cadence Emails (4 Templates — Steps 3/5/7/8)

| Action | Step | Day | Subject | CTA |
|--------|------|-----|---------|-----|
| `value_followup` | 3 | 5 | "{{first_name}} - quick resource" | "Mind if I send the link?" |
| `social_proof` | 5 | 10 | "Case study for {{company}}" | "Want me to share the one-pager?" |
| `breakup` | 7 | 17 | "Closing the loop / {{company}}" | "I'll take this off my follow-up list" |
| `close` | 8 | 21 | "Last note from me, {{first_name}}" | "Yes / No / Not yet — one word is all I need" |

### Template Personalization Fields

Every template uses:

| Variable | Source | Example |
|----------|--------|---------|
| `{{lead.first_name}}` | Apollo enrichment | "Andrew" |
| `{{lead.company}}` | Apollo enrichment | "Wpromote" |
| `{{lead.industry}}` | Apollo enrichment | "marketing & advertising" |
| `{{lead.title}}` | Apollo enrichment | "Chief Revenue Officer" |
| `{{sender.name}}` | Config | "Dani Apgar" |
| `{{sender.title}}` | Config | "Chief AI Officer" |
| `{{sender.calendar_link}}` | Config | `https://caio.cx/ai-exec-briefing-call` |

---

## 8. ICP Scoring Quick Reference

### Tier Thresholds

| Tier | Score Range | Who | Templates |
|------|------------|-----|-----------|
| Tier 1 | 80-100 | C-Suite: CEO, Founder, President, COO, Managing Partner | 4 templates |
| Tier 2 | 60-79 | VP-level: CTO, CIO, VP Ops/Strategy, Head of Innovation | 3 templates |
| Tier 3 | 40-59 | Directors: Director Ops/IT, VP Engineering, Head of AI/Data | 4 templates |
| Tier 4 | <40 | Low-fit — not sent | None |

### Scoring Breakdown (100 points max, before multiplier)

| Category | Max Points | Sweet Spot |
|----------|-----------|------------|
| Company Size | 20 | 51-500 employees (full 20 pts) |
| Title Seniority | 25 | C-Level/Founder (full 25 pts) |
| Industry Fit | 20 | Agencies, Staffing, Consulting, Law (full 20 pts) |
| Technology Stack | 15 | CRM user + Sales tech (13 pts) |
| Intent Signals | 20 | Demo requested + pricing page (16 pts) |

### HoS Multipliers (Applied After Base Score)

| Lead Profile | Multiplier | Example |
|-------------|-----------|---------|
| C-Suite + Tier 1 industry | 1.5x | CEO at Wpromote (agency) = 65 base x 1.5 = 97 |
| C-Suite + other industry | 1.3x | CEO at SaaS company = 60 base x 1.3 = 78 |
| VP + Tier 1 industry | 1.3x | CTO at staffing firm = 55 base x 1.3 = 71 |
| VP + Tier 2 industry | 1.2x | VP Ops at SaaS = 57 base x 1.2 = 68 |
| Everyone else | 1.0x | No multiplier |

---

## 9. Deliverability Guards Reference

### 4-Layer Defense (Applied Before Every Send)

| Guard | What It Does | Config |
|-------|-------------|--------|
| **Guard 1** | Validates email format (RFC 5322) | Automatic |
| **Guard 2** | Blocks 19 excluded domains | `guardrails.deliverability.excluded_recipient_domains` |
| **Guard 3** | Max 3 leads per domain per batch | `guardrails.deliverability.max_leads_per_domain_per_batch` |
| **Guard 4** | Blocks 27 specific email addresses | `guardrails.deliverability.excluded_recipient_emails` |

### Excluded Domains (19) — Guard 2

**Competitors** (10): apollo.io, gong.io, outreach.io, salesloft.com, chorus.ai, people.ai, seamless.ai, zoominfo.com, lusha.com, cognism.com

**Own domains** (2): chiefaiofficer.com, chiefai.ai

**Customer domains** (7): jbcco.com, frazerbilt.com, immatics.com, debconstruction.com, credegroup.com, verifiedcredentials.com, exitmomentum.com

**To add a domain**: Tell Claude "Add [domain] to the excluded domains list in production.json"

### Excluded Emails (27) — Guard 4

Individual customer email addresses. Full list in `config/production.json` under `guardrails.deliverability.excluded_recipient_emails`.

**To add an email**: Tell Claude "Add [email] to the excluded emails list in production.json"

---

## 10. Codex Edge-Case Test Prompts

Copy-paste these into Codex to build your test suite. Run them one at a time.

### Prompt 1 — Bounce Storm Test
```
In the CAIO Alpha Swarm project, write a test that simulates 10 consecutive
bounces from the same domain (e.g., 10 leads all @badcompany.com) in a
single pipeline run. Verify that:
(a) Deliverability Guard 3 (domain concentration >3/batch) rejects leads 4-10
(b) Each rejection is logged with a structured reason
(c) The circuit breaker opens after threshold failures
Run the test and report results.
```

### Prompt 2 — Reply Signal Propagation
```
In the CAIO Alpha Swarm project, write an integration test that:
(a) Sends a mock reply webhook to POST /webhooks/instantly/reply with valid
    bearer token auth
(b) Verifies the lead status changes to 'replied' in the signal loop
(c) Verifies the cadence engine auto-exits the lead (status check)
(d) Verifies GHL contact gets tagged 'status-replied'
Test the full chain end-to-end. Use test fixtures, don't hit real APIs.
```

### Prompt 3 — Duplicate Lead Dedup
```
In the CAIO Alpha Swarm project, write a test that runs the OPERATOR
dispatcher with duplicate leads:
(a) Same exact email address (should be caught)
(b) Same person, different email (fuzzy name match — should be caught)
(c) Same company, different person (should NOT be caught — valid)
Verify the 3-layer dedup in operator_outbound.py handles each case correctly.
```

### Prompt 4 — Emergency Stop Mid-Pipeline
```
In the CAIO Alpha Swarm project, write a test that:
(a) Starts a pipeline run
(b) Sets EMERGENCY_STOP=true mid-execution
(c) Verifies no emails are sent after the stop
(d) Verifies the pipeline returns a clear error message
(e) Verifies a Slack CRITICAL alert fires
(f) Resets EMERGENCY_STOP=false and verifies next run works
```

### Prompt 5 — Bearer Token Rotation
```
In the CAIO Alpha Swarm project, write a test that simulates token rotation:
(a) Set WEBHOOK_BEARER_TOKEN to "old-token-value"
(b) Verify requests with "old-token-value" return 200
(c) Change WEBHOOK_BEARER_TOKEN to "new-token-value"
(d) Verify requests with "old-token-value" now return 401
(e) Verify requests with "new-token-value" return 200
(f) Verify health endpoints reflect the change
```

### Prompt 6 — Concurrent Pipeline Runs
```
In the CAIO Alpha Swarm project, write a test that starts 3 pipeline runs
simultaneously (different source companies). Verify:
(a) No duplicate leads across runs
(b) No race conditions on the shadow email queue
(c) No Redis key collisions
(d) Each run produces independent campaign IDs
```

### Prompt 7 — Apollo Credit Exhaustion
```
In the CAIO Alpha Swarm project, write a test that simulates Apollo returning
HTTP 402 (credits exhausted) during enrichment. Verify:
(a) The pipeline doesn't crash
(b) The lead is marked as 'enrichment_failed'
(c) An appropriate warning is logged
(d) The rest of the pipeline continues for other leads
(e) A Slack WARNING alert fires
```

### Prompt 8 — Webhook Replay Attack
```
In the CAIO Alpha Swarm project, write a test that replays the same Instantly
reply webhook payload 5 times in rapid succession. Verify idempotency:
(a) Lead status updates only once (not 5 times)
(b) Suppression list has only 1 entry (not 5)
(c) Only 1 Slack alert fires (not 5)
(d) GHL tag is applied once
```

### Prompt 9 — Security Audit
```
In the CAIO Alpha Swarm project, review ALL files in webhooks/ and
dashboard/health_app.py for:
(a) Any endpoint that accepts user input without validation
(b) Any place where secrets could leak into logs or error responses
(c) Any SQL injection vectors in Supabase queries
(d) Any path traversal risks in file operations
(e) Any timing attacks on auth comparisons
Report findings as a table with file, line, severity, and recommendation.
```

### Prompt 10 — Error Handling Audit
```
In the CAIO Alpha Swarm project, review execution/run_pipeline.py,
execution/operator_outbound.py, and execution/cadence_engine.py. For each
external API call (Apollo, Instantly, HeyReach, GHL), verify there is:
(a) Specific HTTP error handling (402, 404, 429, 500)
(b) Retry logic with backoff
(c) Circuit breaker integration
(d) Slack alert on failure
Report gaps as a table with file, line, API call, and what's missing.
```

---

## 11. Quick Reference Card

### Key URLs

| What | URL |
|------|-----|
| System Health | `https://caio-swarm-dashboard-production.up.railway.app/` |
| HoS Email Queue | `https://caio-swarm-dashboard-production.up.railway.app/sales` |
| Lead Signal Loop | `https://caio-swarm-dashboard-production.up.railway.app/leads` |
| Scorecard | `https://caio-swarm-dashboard-production.up.railway.app/scorecard` |
| Health Readiness | `https://caio-swarm-dashboard-production.up.railway.app/api/health/ready` |
| Operator Status | `https://caio-swarm-dashboard-production.up.railway.app/api/operator/status` |
| Queue Status | `https://caio-swarm-dashboard-production.up.railway.app/api/queue-status` |
| Instantly | `https://app.instantly.ai` |
| HeyReach | `https://app.heyreach.io` |
| Railway | `https://railway.com` > caio-swarm-dashboard |

### Emergency Actions

| Situation | Action |
|-----------|--------|
| **Stop all email sends** | Set `EMERGENCY_STOP=true` in Railway Variables > Redeploy |
| **Pause one Instantly campaign** | Instantly UI > Campaign > Pause button |
| **Pause ALL Instantly campaigns** | Dashboard: `/api/instantly/emergency-stop` (with dashboard token) |
| **Add domain to exclusion list** | Tell Claude: "Add [domain] to excluded domains in production.json" |
| **Report a bug** | Screenshot + Railway logs + tell Claude what happened |

### Pipeline Command Cheat Sheet

```bash
# Day 1-3: Supervised ramp (3-5 leads)
echo yes | python execution/run_pipeline.py --mode production --source "wpromote" --limit 3

# Post-graduation: Standard batch (10-25 leads)
echo yes | python execution/run_pipeline.py --mode production --source "tinuiti" --limit 10

# Test without sending (safe, no API calls)
python execution/run_pipeline.py --mode sandbox --source "test_company" --limit 5

# Specific tier only
echo yes | python execution/run_pipeline.py --mode production --source "slalom" --limit 10 --segment tier_1
```

### Daily Ceiling Reference

| Mode | Email/Day | LinkedIn/Day | Who Qualifies |
|------|-----------|-------------|---------------|
| Ramp (Days 1-3) | 5 | 0 | Tier 1 only (C-Suite) |
| Graduated | 25 | 0 | All tiers |
| Scaled (Week 3) | 50 | 5 | All tiers |
| Scaled (Week 4) | 75 | 10 | All tiers |
| Full capacity | 100 | 20 | All tiers |

### 6 Cold Email Domains

| # | Domain | Sender |
|---|--------|--------|
| 1 | chiefaiofficerai.com | chris.d@chiefaiofficerai.com |
| 2 | chiefaiofficerconsulting.com | chris.d@chiefaiofficerconsulting.com |
| 3 | chiefaiofficerguide.com | chris.d@chiefaiofficerguide.com |
| 4 | chiefaiofficerlabs.com | chris.d@chiefaiofficerlabs.com |
| 5 | chiefaiofficerresources.com | chris.d@chiefaiofficerresources.com |
| 6 | chiefaiofficersolutions.com | chris.d@chiefaiofficersolutions.com |

All domains at 100% health, DNS verified, round-robin rotation.

---

*This document is the single source of truth for CAIO Alpha Swarm operations. Update it after each phase transition.*
