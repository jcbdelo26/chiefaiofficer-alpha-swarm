---
title: HoS Supervised Ramp Guide
version: "1.0"
last_updated: 2026-03-04
audience: [pto-gtm, hos]
tags: [ramp, supervised, dashboard, guide, non-technical]
canonical_for: [hos-ramp-guide]
---

# Head of Sales -- Supervised Ramp Guide

**Purpose**: This guide walks you through the 3-day supervised email ramp. You will review up to 5 AI-generated cold outreach emails per day. Nothing sends without your explicit approval.

**Time commitment**: ~15 minutes per day at **3:00 PM EST** for 3 consecutive days.

**For detailed email quality criteria**: See [HOS_EMAIL_REVIEW_GUIDE.md](HOS_EMAIL_REVIEW_GUIDE.md).

---

## 1. How to Log In

1. Open your browser and go to:
   `https://caio-swarm-dashboard-production.up.railway.app/sales`
2. You will be automatically redirected to the **login page**
3. In the "Dashboard Token" field, paste the token that was provided to you (keep this token private)
4. Click **"Log In"**
5. You are now on the Sales Dashboard

**If you see "Session Expired"** at any point, click "Log In" and re-enter your token.

**To log out**, click the logout link in the top-right corner of the dashboard.

> **Important**: Do NOT put the token in the URL bar. The login page handles authentication securely.

---

## 2. Dashboard Overview

The dashboard has **5 tabs** along the top navigation bar:

| Tab | What It Shows | Do You Need It? |
|-----|---------------|-----------------|
| **Overview** | System health, email stats (sent, replies, meetings), pipeline funnel | Glance at the start of each session |
| **Email Queue** | Emails waiting for your review + recently reviewed history | **YES -- this is your primary tab** |
| **Campaigns** | Dispatch history and cadence pipeline status | Reference only |
| **Settings** | Ramp mode status, safety controls, system info | Check if unsure about limits |
| **Metrics** | Approval rates, gateway health, compound metrics | Reference only |

### Ramp Mode Banner

While ramp mode is active, you will see a banner showing:
- **Daily limit**: 5 emails per day
- **Tier filter**: Tier 1 only (C-Suite decision makers: CEO, CRO, COO, CTO, President, Founder, Managing Partner)
- **Clean days**: How many clean supervised days have been completed

After 3 clean days, ramp mode is turned off and the system scales to 25 emails/day across all tiers.

---

## 3. Practice First: Generating Training Emails

Before reviewing real prospect emails, you can practice with **synthetic training emails** that will never be sent to anyone.

1. Click the **"Email Queue"** tab
2. If the queue is empty, you will see a message saying the queue is clear with a yellow **"Generate Training Emails"** button -- click it
3. Alternatively, click **"Seed Training Emails"** (yellow button near the top-right of the Email Queue section)
4. A popup appears with two options:
   - **Count**: How many emails to generate (choose 5 to simulate a full ramp day)
   - **Tier Filter**: Select **"Tier 1 - Decision Makers"** to match ramp mode
5. Click **"Generate"**
6. Training emails appear immediately in the queue, marked with a yellow **TRAINING** badge
7. Practice approving and rejecting these -- they use fake email addresses ending in `@seed-training.internal` and will never be delivered

---

## 4. Reviewing and Approving Emails

### Step 1: Open an Email

In the **Email Queue** tab, you will see email cards listed under "Pending Approvals." Each card shows:
- **Recipient**: Name, email address, company
- **Subject line**: What the prospect will see in their inbox
- **Tier badge**: Should show TIER 1 during ramp
- **Priority**: HOT / WARM / LOW based on lead scoring

Click on an email card to open the **Email Editor & Preview** modal.

### Step 2: Review the Email

The modal has two sections:

**Left side (the email)**:
- **To**: Recipient email address
- **Subject**: The email subject line
- **Body**: The full email text (you can edit this!)
- **Feedback**: A text box for your notes
- **Rejection Tag**: A dropdown you must use if rejecting

**Right side (lead details)**:
- Recipient name, job title, company
- Company size (employees), location
- ICP tier and score
- Template/angle used (e.g., "Executive Buy-In")
- Delivery classifier (where it will be sent from)
- Campaign mapping
- Compliance checks (footer, unsubscribe, etc.)

### Step 3: Apply the 8-Point Checklist

Before approving, verify **all 8**:

1. **Subject line** -- Does it sound like a real person wrote it? Would you open this?
2. **Opening line** -- Is it specific to this person or company? Not a generic opener?
3. **Pain point** -- Does the problem match this person's **job title**?
   - CEO/Founder = business strategy, growth, ROI
   - CRO = revenue, pipeline, sales efficiency
   - CTO/CIO = tech stack, technical debt, AI implementation
   - COO = operations, efficiency, process improvement
4. **Company name** -- Used correctly and naturally?
5. **Industry** -- Matches reality? (If unsure, check LinkedIn)
6. **Call to action** -- Soft and appropriate? No aggressive "book a demo" language?
7. **Signature** -- Shows "Dani Apgar, Chief AI Officer" with calendar link?
8. **Footer** -- Has "Reply STOP to unsubscribe" + physical address?

### Step 4: Take Action

You have three options:

**Approve & Send** (green button):
- The email passes all 8 checks
- Click **"Approve & Send"** at the bottom-right of the modal
- The email is sent immediately via GoHighLevel (GHL)
- The card moves to "Recently Reviewed" with a green checkmark

**Edit, then Approve**:
- If the copy needs minor fixes, click into the email body text and make your changes
- Then click **"Approve & Send"**
- Your edits are preserved -- the fixed version gets sent

**Reject** (red button):
- The email fails one or more checks
- You **must** select a **Rejection Tag** from the dropdown (see Section 6 below)
- You **must** type a reason in the Feedback box (minimum 20 characters)
- Click **"Reject"**
- The card moves to "Recently Reviewed" with a red X
- Your rejection reason is used by the AI to improve future emails

---

## 5. The 3-Day Ramp Ritual

Each day at **3:00 PM EST**, follow this exact sequence:

### Day 1

| Step | Action | Time |
|------|--------|------|
| 1 | Log in to the dashboard | 1 min |
| 2 | Click **Overview** tab -- check that system health shows green | 1 min |
| 3 | Click **Email Queue** tab | - |
| 4 | If the queue is empty, click **"Seed Training Emails"** (5, Tier 1) to practice first | 2 min |
| 5 | Review all pending Tier 1 emails (up to 5) | 8 min |
| 6 | For each: apply the 8-point checklist, then Approve or Reject | - |
| 7 | Fill out the Daily Evidence Log (Section 8 below) | 2 min |

### Day 2

| Step | Action | Time |
|------|--------|------|
| 1 | Log in to the dashboard | 1 min |
| 2 | Scroll down in Email Queue to "Recently Reviewed" -- check yesterday's approvals show "sent_via_ghl" status | 2 min |
| 3 | Note any bounce notifications (there should be none) | 1 min |
| 4 | Review today's pending Tier 1 emails | 8 min |
| 5 | Fill out the Daily Evidence Log | 2 min |

### Day 3

| Step | Action | Time |
|------|--------|------|
| 1 | Same as Day 2 | - |
| 2 | After reviewing, if all 3 days are clean: **ramp is complete** | - |
| 3 | Fill out the final Daily Evidence Log | 2 min |
| 4 | Engineering changes a config setting to unlock full capacity | - |

**What "clean day" means**: You reviewed all pending emails, there were no bounce notifications, and no emergency stops were triggered.

**After Day 3**: The system unlocks to 25 emails/day across all tiers (not just C-Suite). The approval gate stays on for 2 more weeks as a safety net -- you will still review every email before it sends.

---

## 6. Rejection Tags Reference

When rejecting an email, you must select the tag that best describes the problem:

| Tag | When to Use |
|-----|-------------|
| **Personalization mismatch** | Opening line or pain point does not match the recipient's role/company |
| **ICP mismatch** | Wrong person or company for our target audience |
| **Campaign mismatch** | Template angle does not fit this lead |
| **Tone/style issue** | Sounds robotic, too aggressive, or off-brand |
| **Factual inaccuracy** | Wrong company info, outdated data, incorrect industry |
| **Weak subject line** | Subject line is generic, unclear, or would not get opened |
| **Weak CTA** | Call to action is too aggressive, too vague, or missing |
| **Length/structure issue** | Email is too long, poorly formatted, or hard to read |
| **Compliance issue** | Missing footer, missing unsubscribe, or CAN-SPAM violation |
| **Placeholder/rendering issue** | Template variables visible (like `{{lead.company}}` in the text) |
| **Other** | Anything not covered above -- describe the issue in the feedback box |

**Instant reject triggers** (do not hesitate):
- Template variables visible in the email text
- Wrong sender name (should always be "Dani Apgar")
- Missing "Reply STOP to unsubscribe" footer
- Personal email address (gmail.com, yahoo.com instead of work domain)
- Recipient is a current customer or competitor
- Title is NOT C-Suite during ramp (e.g., "Director" or "Manager")

---

## 7. Verifying Approved Emails in GHL

After approving an email:

1. You should see a green notification saying the email was approved
2. The email card moves to "Recently Reviewed" (scroll down in Email Queue)
3. The status should show **"sent_via_ghl"**
4. To verify delivery in GoHighLevel:
   - Log into GoHighLevel (GHL)
   - Search for the contact by their email address
   - Open their conversation thread
   - Confirm the email appears with the correct subject line and body
   - Verify the timestamp matches when you approved it

---

## 8. Daily Evidence Log

Copy this template and fill it out each day. Share it with engineering at the end of each session:

```
RAMP DAY [1/2/3] -- [Date, e.g., 2026-03-05]
Time: 3:00 PM EST
Emails reviewed: [number]
Approved: [number]
Rejected: [number]
Bounce notifications: [number or "none"]
Emergency stops: [yes/no -- should always be "no"]
Top rejection reason: [tag, e.g., "personalization_mismatch"]
GHL delivery verified: [yes/no]
Notes: [anything unusual or feedback patterns]
```

**Example (clean day)**:
```
RAMP DAY 1 -- 2026-03-05
Time: 3:00 PM EST
Emails reviewed: 5
Approved: 3
Rejected: 2
Bounce notifications: none
Emergency stops: no
Top rejection reason: personalization_mismatch
GHL delivery verified: yes (checked 1 of 3 approved)
Notes: Two emails had CRO-targeted pain points sent to a CEO. Rejected with detailed feedback.
```

---

## 9. What to Do If Something Goes Wrong

| Situation | What to Do |
|-----------|------------|
| Dashboard will not load | Check your internet. Try refreshing. If still down, contact engineering. |
| "Session Expired" message | Click "Log In" and re-enter your token. This is normal after ~24 hours. |
| Email looks broken (weird formatting, visible code) | Reject with tag "Placeholder/rendering issue" and describe what you see. |
| You accidentally approved a bad email | Contact engineering immediately. They may be able to intercept before delivery. |
| You see a customer or competitor in the queue | Reject with tag "ICP mismatch" and note the company name. Tell engineering to add the domain to the exclusion list. |
| Queue shows 0 emails but you expected some | Click "Seed Training Emails" to verify the system works. If real emails are expected, contact engineering. |
| Something feels seriously wrong (spam, wrong identity, system malfunction) | Contact engineering to activate the emergency stop. Do NOT approve any more emails. |
| You cannot make the 3:00 PM review | Let engineering know. A missed day does not reset progress, but the day does not count toward the 3 required. |

---

## 10. Frequently Asked Questions

**Q: What is "shadow mode"?**
A: Shadow mode means the system logs all emails for your review before sending. Nothing goes out without your approval. This stays on even after the ramp ends.

**Q: What happens if I miss a review day?**
A: Emails stay in the queue. Nothing sends without you. The missed day does not count toward the 3 required clean days, but it does not reset your progress either. Just pick up the next day.

**Q: Can I review from my phone?**
A: The dashboard works in a mobile browser, but the email editor modal is designed for a larger screen. Use a laptop or desktop for the best experience.

**Q: Who is Dani Apgar?**
A: That is the sender identity for all outbound emails. All cold outreach goes out under "Dani Apgar, Chief AI Officer" with a calendar link to `https://caio.cx/ai-exec-briefing-call`.

**Q: What are the emails marked "TRAINING"?**
A: Synthetic practice emails with fake recipients (addresses ending in `@seed-training.internal`). They exist so you can practice the approve/reject workflow safely. They will never be sent to anyone.

**Q: How do I get more emails to review?**
A: For practice: Click "Seed Training Emails." For real prospect emails: Engineering runs the pipeline which generates new emails for your queue.

**Q: What is the Ramp Mode banner?**
A: It shows you are in supervised mode: limited to 5 emails/day, Tier 1 (C-Suite) leads only. After 3 clean days, this limit is removed and the system scales up.

**Q: What happens after the 3 days?**
A: Engineering changes a configuration to unlock full capacity (25 emails/day, all tiers). The approval gate stays on for 2 more weeks -- you still review every email. After that, low-risk emails may auto-approve while you review higher-risk ones.

**Q: What if I think the AI is getting something consistently wrong?**
A: Note the pattern in your Daily Evidence Log. For example, "CRO-targeted pain points keep going to CEOs" or "subject lines are too generic." Engineering compiles these patterns into template improvements. The more specific your feedback, the faster the system improves.

**Q: How do I stop all emails immediately?**
A: Contact engineering. They will set the EMERGENCY_STOP flag which blocks all outbound email instantly. You do not need to do this yourself.

---

## Quick Reference Card

| I want to... | Do this |
|--------------|---------|
| Log in | Go to `/sales`, enter your token on the login page |
| See pending emails | Click the **Email Queue** tab |
| Practice with fake emails | Click **"Seed Training Emails"** (yellow button) |
| Review an email | Click the email card to open the editor modal |
| Approve an email | Apply the 8-point checklist, then click **"Approve & Send"** (green) |
| Edit before approving | Click into the email body, make changes, then click **"Approve & Send"** |
| Reject an email | Select a rejection tag, write a reason (20+ chars), click **"Reject"** (red) |
| Check if approved emails were delivered | Scroll to "Recently Reviewed" -- status should say "sent_via_ghl" |
| Verify in GHL | Search contact by email in GoHighLevel, check conversation thread |
| Report a problem | Contact engineering with details of what you saw |

---

*Your feedback shapes this system. Every edit you make, every rejection reason you write, and every pattern you flag makes the next batch of emails better. Thank you for being the quality gate.*
