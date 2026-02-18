# Head of Sales — Email Review & Feedback Guide

**Purpose**: This is your source of truth for reviewing pipeline-generated emails before they reach prospects. Your edits and feedback directly improve the AI system over time.

**Updated**: 2026-02-18 (First Live Pipeline Run)

---

## How This Works

1. The swarm scrapes leads, enriches them, scores them, and writes an email
2. Emails land in your approval queue at **`/sales`** in shadow mode (nothing sends without you)
3. You review, edit, approve, or reject each email
4. Your feedback gets compiled and fed back to improve templates and personalization

**Your review is the quality gate.** The AI is fast but not infallible — you're the final set of human eyes.

---

## Where to Review

**URL**: `https://caio-swarm-dashboard-production.up.railway.app/sales`

Each email card shows:

| Field | What It Tells You |
|-------|------------------|
| **Recipient name** | Who we're emailing |
| **Email address** | Their work email (verify domain matches company) |
| **Company** | Target company |
| **Title** | Their job title (critical — see Tier Check below) |
| **Industry** | Company's industry vertical |
| **Subject line** | What they see in their inbox |
| **Email body** | The full email text |
| **ICP Tier** | tier_1 (C-Suite), tier_2 (VP), tier_3 (Director) |
| **ICP Score** | 0-100 fit score (higher = better match) |
| **Template** | Which email angle was used (e.g., `t1_executive_buyin`) |
| **Delivery Classifier** | Outbound/Inbound + target platform (Instantly/GHL/HeyReach) |
| **Campaign Mapping** | Internal campaign ID/type + sync state to external campaign |

### Classifier Interpretation (new)

- `OUTBOUND -> GHL`: Pre-send approval currently routed through dashboard/GHL path.
- `OUTBOUND -> INSTANTLY`: Draft is intended for Instantly campaign execution path.
- `Sync: pending_external_campaign_mapping`: Internal campaign exists, external campaign link not created yet.
- `Sync: n/a_ghl_direct_path`: This card is not expected to map to an Instantly campaign.

---

## Backend Connection Clarity — Outbound GHL

When you see:

- `Campaign: t1_executive_buyin (camp_20260219_005010)`
- `Delivery Classifier: OUTBOUND -> GHL`
- `Sync: n/a_ghl_direct_path`

this means:

1. `camp_...` is an **internal CAIO pipeline campaign ID** (grouping/trace ID), not a native GHL campaign object.
2. The email was queued by pipeline into pending approvals (`source=pipeline`, `status=pending`).
3. On approval, system sends a **direct GHL conversation email** (not "create GHL campaign sequence").
4. If `contact_id` is missing, system now **auto-resolves/creates contact in GHL by email before send**.

Code path:

- Queue creation: `execution/run_pipeline.py` (`_stage_send`) writes pending cards with:
  - `source: "pipeline"`
  - `delivery_platform: "ghl"`
  - `context.campaign_id` and `context.pipeline_run_id`
- Queue classifier/mapping: `dashboard/health_app.py` (`_infer_pending_email_classifier`)
  - sets `target_platform=ghl`, `sync_state=n/a_ghl_direct_path`
- Live send on approval: `dashboard/health_app.py` (`/api/emails/{email_id}/approve`)
  - builds `EmailTemplate(...)`
  - calls `GHLOutreachClient.send_email(...)`
  - marks result as `sent_via_ghl` with `ghl_message_id`
- GHL API call details: `core/ghl_outreach.py`
  - endpoint: `POST /conversations/messages`
  - payload includes `contactId`, `subject`, `html`

---

## Pre-Live Cross-Check Ritual (Required)

### 1) Validate pending queue routing and live-send readiness

Run:

```powershell
python scripts/trace_outbound_ghl_queue.py `
  --base-url https://caio-swarm-dashboard-production.up.railway.app `
  --token <DASHBOARD_AUTH_TOKEN>
```

Interpretation:

- `target_platform=ghl` confirms approval path is GHL.
- `sendability=ready_for_live_send` means card has required fields for live send.
- `sendability=auto_resolve_on_approve` means contact will be upserted by email at approve time.
- `sendability=blocked_missing_contact_id` means neither existing contact nor resolvable email is present.

### 2) Approve one card from `/sales`

- Open `/sales?token=<DASHBOARD_AUTH_TOKEN>`
- Click `Edit & Preview` -> final QA -> `Approve & Send`

### 3) Confirm backend result

- Card status should transition from `pending` to `sent_via_ghl` when successful.
- Approval audit entry should be appended in `.hive-mind/audit/email_approvals.jsonl`.

### 4) Confirm in GHL UI

- Search contact by recipient email.
- Open contact conversation.
- Verify email subject/body and timestamp match approval action.

If step 1 shows many `blocked_missing_contact_id`, do not run bulk live approvals until contact mapping is fixed.

---

## First Pipeline Results — What You're Looking At

Your first run (2026-02-18) scraped **Wpromote** and produced **2 emails**:

### Email 1: Andrew Mahr

| Field | Value |
|-------|-------|
| To | andrew.mahr@wpromote.com |
| Title | Chief Revenue Officer (CRO) |
| ICP Score | 93 (tier_1) |
| Template | t1_executive_buyin |

**Subject**: AI Roadmap for Wpromote

**Body**:
> Hi Andrew,
>
> Seeing a lot of marketing & advertising firms stuck in "AI research mode" without moving to implementation.
>
> Usually, it's because the CTO is buried in legacy tech and there's no dedicated AI lead to drive the strategy forward.
>
> We act as your Fractional Chief AI Officer to move Wpromote from curiosity to ROI—typically in 90 days.
>
> What that looks like:
> - Day 1: One-day M.A.P. Bootcamp (your team leaves with an AI-ready action plan)
> - Days 2-90: We embed with your team, build the workflows, and measure results
> - Guarantee: Measurable ROI, or you don't pay the next phase
>
> Worth a brief chat on how we're doing this for similar marketing & advertising companies?
>
> Best,
> Dani Apgar
> Chief AI Officer
> https://caio.cx/ai-exec-briefing-call

---

### Email 2: Celia Kettering

| Field | Value |
|-------|-------|
| To | celia.kettering@wpromote.com |
| Title | Senior Director, Performance Media Sales |
| ICP Score | 93 (tier_1) |
| Template | t1_executive_buyin |

**Subject**: AI Roadmap for Wpromote

**Body**: Identical to Andrew's (only first name changed)

---

## Issues Found in This Run (Your Feedback Starts Here)

Here are the problems I've flagged. **Mark which ones you agree with, disagree with, or want to add to.**

### Issue 1: Title-Pain Mismatch

The email says: *"Usually, it's because the CTO is buried in legacy tech"*

But Andrew is a **CRO (Chief Revenue Officer)** — his pain is revenue, pipeline, and sales efficiency. Not legacy tech. A CRO cares about:
- Revenue acceleration
- Sales team productivity
- Pipeline visibility and forecasting
- Marketing-to-sales handoff speed

**Your call**: Should the opening pain point change based on the recipient's title? If yes, what should a CRO-specific pain point sound like?

**Write your version here** (or say "keep as-is"):

> _____________________________________________

---

### Issue 2: Identical Emails to Same Company

Andrew and Celia both received **word-for-word identical emails** (only the greeting name changed). If two people at Wpromote compare notes, this looks automated.

**Your call**: Options:
- **A)** Only email one person per company per batch (safest)
- **B)** Use different templates for the second person (e.g., Andrew gets `t1_executive_buyin`, Celia gets `t1_value_first`)
- **C)** Keep as-is (risk of looking automated)

**Your choice**: ___

---

### Issue 3: Tier Scoring Question

Celia Kettering is a **"Senior Director, Performance Media Sales"**. During ramp mode, we're targeting **tier_1 = C-Suite only**. Senior Director is not C-Suite.

The system scored her at **93** (tier_1 threshold is 80+) because:
- Wpromote is a perfect industry fit (marketing & advertising) = 20 pts
- "Director" gets partial title points = ~15 pts
- Company size likely in sweet spot (51-500) = 20 pts
- HoS multiplier (Tier 1 industry) may have boosted her

**Your call**: Should "Senior Director" level be:
- **A)** Included in tier_1 (current behavior — cast a wider net at C-Suite companies)
- **B)** Moved to tier_2 (only true C-Suite: CEO, CRO, CTO, COO, Founder, President, Managing Partner)
- **C)** Excluded during ramp (strict C-Suite only for first 3 days, relax later)

**Your choice**: ___

---

### Issue 4: Generic Industry Reference

The email says: *"Seeing a lot of marketing & advertising firms stuck in 'AI research mode'"*

This is correct but generic. Wpromote is one of the largest independent performance marketing agencies in the US. The email could reference:
- Their scale (500+ employees)
- Their focus on performance marketing specifically
- Their client portfolio (enterprise brands)
- Recent industry awards or campaigns

**Your call**: How much personalization do you want per email?
- **A)** Keep it industry-level (faster, less research needed)
- **B)** Add 1 company-specific line in the opening (slower but higher reply rates)
- **C)** Full custom research per lead (highest quality but doesn't scale)

**Your choice**: ___

---

### Issue 5: CTA Softness

Current CTA: *"Worth a brief chat on how we're doing this for similar marketing & advertising companies?"*

This is intentionally soft. Options to consider:
- **Keep** — soft CTA lowers resistance, good for C-Suite
- **Strengthen** — "Would a 15-minute call this week be useful?"
- **Offer value first** — "Mind if I send a 2-minute breakdown of what we're doing for similar agencies?"

**Your preference**: ___

---

## The 8-Point Checklist (Use This for Every Email)

Before approving any email, verify ALL of these:

- [ ] **1. Subject line** — Does it sound human? Would you open it? Not clickbait?
- [ ] **2. Opening line** — Is it specific to this person or their company? Not generic?
- [ ] **3. Pain point** — Does the problem described match this person's JOB TITLE? (CRO = revenue, CTO = tech, CEO = strategy)
- [ ] **4. Company name** — Used correctly and naturally (not forced)?
- [ ] **5. Industry** — Matches reality? (Check against LinkedIn if unsure)
- [ ] **6. CTA** — Soft and appropriate? No aggressive "book a demo" language?
- [ ] **7. Signature** — Shows "Dani Apgar, Chief AI Officer" with calendar link?
- [ ] **8. Footer** — Has "Reply STOP to unsubscribe" + physical address?

**Automatic reject if:**
- Template variables unfilled (you see `{{lead.company}}` or `Reference their tech stack` literally)
- Wrong sender name (should be "Dani Apgar", not "Chris Daigle")
- Missing CAN-SPAM footer
- Email domain doesn't match company (e.g., gmail.com instead of company domain)
- Title is clearly wrong (person left the company, wrong attribution)

---

## How to Give Feedback

### For Individual Emails

In the `/sales` dashboard:
- **Approve** — Email passes all 8 checks
- **Edit + Approve** — You fix the copy, then approve
- **Reject** — Note the reason (wrong person, bad copy, wrong template)

### For System-Wide Improvements

After reviewing a batch, note patterns here. These get compiled into template improvements:

**Feedback Template** (copy this, fill it out, hand to Claude):

```
BATCH FEEDBACK — [Date]
Pipeline run: [run ID from dashboard]
Company: [company name]
Leads reviewed: [number]

TEMPLATE ISSUES:
- [ ] Pain points don't match titles (describe pattern)
- [ ] Same email to multiple people at same company
- [ ] Opening too generic (need company-specific research)
- [ ] CTA too weak / too strong
- [ ] Wrong sender name/title
- [ ] Missing personalization fields
- [ ] Other: ___

TITLE/TIER ISSUES:
- [ ] Non-C-Suite person scored as tier_1 (names: ___)
- [ ] Scoring too generous for [title type]
- [ ] Scoring too strict for [title type]

COPY QUALITY (rate 1-5):
- Subject lines: ___/5
- Opening hooks: ___/5
- Value proposition clarity: ___/5
- CTA effectiveness: ___/5
- Overall authenticity (sounds human): ___/5

SPECIFIC EDITS MADE:
1. Email to [name]: Changed [what] from [old] to [new]
2. Email to [name]: Changed [what] from [old] to [new]

PATTERNS I KEEP FIXING:
- ___
- ___

THINGS THAT WORK WELL (keep these):
- ___
- ___
```

---

## What Happens With Your Feedback

| Your Feedback | What Changes |
|---------------|-------------|
| "Pain point doesn't match title" | Template gets title-aware conditional blocks |
| "Too generic — need company research" | Enrichment adds company-specific data points |
| "Scored too high for Director title" | ICP scoring weights adjusted (title seniority points) |
| "Same email to two people at company" | Domain concentration guard adds per-template dedup |
| "CTA too soft/strong" | Template CTA variants updated |
| "Sounds robotic" | Copy rewritten to your voice |
| Pattern of same edit across 3+ emails | Template updated to avoid the pattern permanently |

**The system learns from your edits.** Every change you make teaches the AI what "good" looks like for CAIO outreach. The more specific your feedback, the faster the improvement.

---

## Red Lines — Reject Immediately

| Problem | Why | Action |
|---------|-----|--------|
| Emailing a current customer | Damages relationship | Reject + tell Claude to add domain to exclusion list |
| Emailing a competitor employee | Wastes sends + awkward | Reject + add to exclusion list |
| Broken template (`{{variable}}` visible) | Unprofessional | Reject + report as bug |
| Wrong sender identity | Confusing/unprofessional | Reject + report which name appeared |
| No unsubscribe mechanism | CAN-SPAM violation | Reject immediately — compliance issue |
| Personal email (gmail, yahoo, etc.) | Not professional outreach | Reject — should only email work addresses |
| Person you know personally | Bypasses cold outreach norms | Reject + handle personally |

---

## Daily Review Rhythm

| Time | Action |
|------|--------|
| **Morning** | Check `/sales` for overnight pending emails. Review and approve/reject. |
| **After pipeline run** | New emails appear within 60 seconds. Review the batch. |
| **End of day** | Fill out the batch feedback template above. Hand to Claude. |
| **Friday** | Weekly summary: what patterns are you still fixing? What's improving? |

---

## Metrics to Track (Starting Day 1)

Keep a simple log:

| Date | Leads | Approved | Rejected | Edited | Edit Pattern | Notes |
|------|-------|----------|----------|--------|-------------|-------|
| 2026-02-18 | 2 | | | | | First run — Wpromote |
| | | | | | | |

After 5+ batches, you'll see patterns. Share those patterns with Claude to improve templates at the source.

---

## Quick Actions

| I want to... | Do this |
|--------------|---------|
| Approve an email | Click Approve on the email card at `/sales` |
| Edit before approving | Click Edit, modify the text, then Approve |
| Reject with reason | Click Reject, type the reason |
| Add a domain to exclusion | Tell Claude: "Add [domain] to excluded domains in production.json" |
| Add an email to exclusion | Tell Claude: "Add [email] to excluded emails in production.json" |
| Stop all sends | Set `EMERGENCY_STOP=true` in Railway Variables |
| Run another batch | `echo yes \| python execution/run_pipeline.py --mode production --source "[company]" --limit 3` |
| See system health | Visit `https://caio-swarm-dashboard-production.up.railway.app/api/health/ready` |

---

## Template Reference (What's Generating Your Emails)

During ramp mode (Days 1-3), only **tier_1 templates** are active:

| Template | When It's Used | Subject Pattern | CTA Style |
|----------|---------------|----------------|-----------|
| `t1_executive_buyin` | C-Suite at Tier 1 industry (primary) | "AI Roadmap for {{company}}" | "Worth a brief chat?" |
| `t1_industry_specific` | C-Suite + strong industry match | "AI in {{industry}} / {{company}}" | "Open to seeing a quick breakdown?" |
| `t1_hiring_trigger` | C-Suite + hiring signal detected | "Re: {{company}}'s AI hiring" | "Open to a 15-min bridge strategy call?" |
| `t1_value_first` | C-Suite + softest approach | "2-minute AI readiness check" | "Mind if I send the link? (No pitch)" |

After graduation (Day 4+), all 11 templates unlock (tier_2 + tier_3 angles).

---

*Your feedback shapes this system. Every edit you make, every rejection reason you write, and every pattern you flag makes the next batch better.*
