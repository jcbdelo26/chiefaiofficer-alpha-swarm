# CAIO Alpha Swarm: Head of Sales Action Items Guide

**Date:** February 10, 2026
**For:** Head of Sales
**Purpose:** Define quality standards and approval workflows for AI-generated outreach

---

## What This Document Is About

The CAIO Alpha Swarm AI system generates:
- **Outbound emails** to prospects
- **Meeting prep documents** for sales calls
- **Follow-up sequences** for leads

**Your role:** Define the **quality standards** so the AI knows what "good" looks like.

**This is NOT about:**
- Technical configuration
- Code changes
- Server setup

**This IS about:**
- What makes an email "good enough" to send
- When to reject AI-generated content
- What information is needed for call prep
- How fast emails should be reviewed

---

## Section 1: Approval Rubric (Pass/Fail Checklist)

### Why This Matters

Right now, the AI generates emails and waits for your approval. But it doesn't have a **clear rubric** for what makes an email "approvable."

**Goal:** Create a simple checklist the AI can learn from.

---

### 1.1 Email Quality Checklist

For each email the AI generates, it should check:

| Criteria | Pass ✅ | Fail ❌ | Weight |
|----------|---------|---------|--------|
| **Personalization** | Mentions specific company/role detail | Generic template language | HIGH |
| **Value Proposition** | Clear benefit stated in first 2 sentences | Vague or buried benefit | HIGH |
| **Tone** | Professional, conversational, not salesy | Too formal, robotic, or pushy | MEDIUM |
| **Length** | 75-150 words (mobile-friendly) | Too long (>200 words) or too short (<50) | MEDIUM |
| **CTA (Call-to-Action)** | Single, clear ask (e.g., "15-min call?") | Multiple CTAs or unclear ask | HIGH |
| **Compliance** | No false claims, respects unsubscribe rules | Misleading statements, spam triggers | CRITICAL |

**Action Required:**
- [ ] Review this checklist
- [ ] Add or remove criteria based on your standards
- [ ] Assign weights (HIGH, MEDIUM, LOW, CRITICAL)

**Example: What "Good" Looks Like**

✅ **PASS Example:**
```
Hi [Name],

I noticed [Company] recently expanded into [Market]. We've helped
similar B2B SaaS companies reduce CAC by 30% through our outbound
automation platform.

Would you be open to a quick 15-minute call next week to explore
how this could work for your team?

Best,
[Your Name]
```

❌ **FAIL Example:**
```
Dear Sir/Madam,

I am reaching out to introduce our revolutionary AI-powered solution
that will transform your business operations. Our platform leverages
cutting-edge technology to deliver unparalleled results...

[Goes on for 5 more paragraphs]

Please let me know if you would like to schedule a call at your
earliest convenience.

Sincerely,
[Your Name]
```

**What to provide:**
- 5-10 examples of emails you would **approve**
- 5-10 examples of emails you would **reject** (with reasons)

---

### 1.2 Meeting Prep Quality Bar

Before a sales call, the AI prepares a document with:
- Company overview
- Pain points
- Objection prep
- Call talking points

**What "good" call prep looks like:**

| Section | Minimum Required | Optional Nice-to-Have |
|---------|------------------|----------------------|
| **Company Overview** | Industry, size, recent news (1-2 sentences) | Org chart, tech stack |
| **Pain Points** | 2-3 specific challenges based on research | Quantified pain (e.g., "losing $X/month") |
| **Objection Prep** | Top 2 likely objections with responses | Competitive analysis |
| **Talking Points** | 3-5 key discussion topics | Personalized anecdotes |
| **Confidence Score** | AI rates its own confidence (0-100%) | Source citations |

**Action Required:**
- [ ] Define minimum required fields for call prep
- [ ] Set confidence threshold (e.g., "only auto-populate if >80% confident")
- [ ] Provide 3-5 examples of "great" call prep docs you've used

---

## Section 2: Rejection Taxonomy (Why Was It Rejected?)

### Why This Matters

When you reject an AI-generated email, the system needs to know **why** so it can improve.

Right now, rejections are just "approved" or "rejected." We need **categories with examples**.

---

### 2.1 Rejection Categories

| Category | Description | Example | Action |
|----------|-------------|---------|--------|
| **Too Generic** | Doesn't mention company-specific details | "Hi, I wanted to reach out..." | Auto-regenerate with more research |
| **Wrong Tone** | Too formal, too casual, or salesy | "Pursuant to our previous correspondence..." | Regenerate with tone guidance |
| **Weak Value Prop** | Benefit unclear or buried | "We help companies succeed..." | Regenerate with specific benefit |
| **CTA Issues** | No clear ask or too many asks | "Let me know if you're interested" | Regenerate with single clear CTA |
| **Compliance Risk** | False claims, spam language | "Guaranteed 10x ROI..." | Hard reject, escalate to human |
| **Length Issues** | Too long or too short | 300-word email wall of text | Auto-trim or expand |
| **Timing Issues** | Wrong time of day/week to send | Email scheduled for 11pm Friday | Reschedule automatically |

**Action Required:**
- [ ] Review these categories - add or remove as needed
- [ ] For each category, provide 5 real examples from past rejections
- [ ] Specify which categories should trigger **auto-regeneration** vs **manual review**

---

### 2.2 Auto-Regenerate vs Manual Rewrite

**Auto-Regenerate (AI Fixes Itself):**
- Too Generic → AI adds more research
- Wrong Tone → AI adjusts language
- Weak Value Prop → AI clarifies benefit
- Length Issues → AI edits length

**Manual Rewrite (Human Required):**
- Compliance Risk → Needs human judgment
- Multiple rejections → AI is stuck, needs help
- Complex objections → Requires strategic input

**Action Required:**
- [ ] Confirm which categories should auto-regenerate
- [ ] Define escalation rule: "After X rejections, escalate to human"

---

## Section 3: Segment-Specific Messaging Standards

### Why This Matters

Different types of prospects need different messaging styles:
- **Enterprise** (500+ employees): More formal, focus on ROI and compliance
- **Mid-Market** (50-500 employees): Balance of personal + professional
- **SMB** (<50 employees): Casual, focus on speed and simplicity

---

### 3.1 Messaging Matrix

| Segment | Tone | Value Prop Focus | CTA Style | Example Subject Line |
|---------|------|------------------|-----------|----------------------|
| **Enterprise** | Professional, data-driven | ROI, compliance, scalability | "Schedule a demo with our team" | "Reducing CAC by 30% at [Similar Company]" |
| **Mid-Market** | Conversational, results-focused | Efficiency, competitive edge | "Quick call this week?" | "How [Company] is beating competitors" |
| **SMB** | Friendly, action-oriented | Speed, cost savings | "15-min call tomorrow?" | "Save 10 hours/week on outbound" |

**Action Required:**
- [ ] Review this matrix - adjust based on your ICP segments
- [ ] Provide 3 subject lines and 3 email bodies for each segment
- [ ] Define "forbidden phrases" for each segment (e.g., don't say "synergy" to SMBs)

---

### 3.2 Forbidden Claims and Phrasing

**These should NEVER appear in AI-generated emails:**

| Forbidden Phrase | Why | Better Alternative |
|------------------|-----|-------------------|
| "Guaranteed ROI" | Legal risk, unverifiable | "Typical clients see X% improvement" |
| "Revolutionary" | Overused, sounds spammy | "Proven approach to [specific outcome]" |
| "Just checking in" | Weak, no value | "Wanted to share [specific insight]" |
| "Synergy" | Buzzword, meaningless | "How our tools integrate with yours" |
| "World-class" | Vague, self-promotional | "Rated 4.8/5 by 500+ customers" |

**Action Required:**
- [ ] Provide a list of 10-20 forbidden phrases for your industry/market
- [ ] Include reasons why they're forbidden
- [ ] Suggest better alternatives

---

## Section 4: Operational Limits & SLAs

### Why This Matters

The AI can generate emails 24/7, but **you** need to approve them during working hours.

We need to set realistic expectations for:
- How many emails you can review per day
- How fast you'll approve/reject
- When emails should queue vs auto-reject

---

### 4.1 Daily Approval Capacity

**Question:** How many AI-generated emails can you realistically review per day?

| Scenario | Emails/Day | Time Required | Recommendation |
|----------|------------|---------------|----------------|
| **Light Day** | 10-20 | 15-30 min | Sustainable daily target |
| **Normal Day** | 20-40 | 30-60 min | Target for steady state |
| **Heavy Day** | 40-60 | 60-90 min | Only during campaigns |
| **Max Capacity** | 60-100 | 2+ hours | Unsustainable, need help |

**Action Required:**
- [ ] Set daily approval capacity target: _____ emails/day
- [ ] Define "overflow" process: What happens if AI generates >capacity?
  - Option A: Queue for next day
  - Option B: Auto-approve low-risk emails
  - Option C: Escalate to backup approver

---

### 4.2 Approval SLA (Time-to-Approve)

**Question:** How fast should emails be approved?

| Priority | Target Approval Time | When to Use |
|----------|---------------------|-------------|
| **High Priority** | <2 hours | Hot leads, inbound responses |
| **Normal Priority** | <24 hours | Standard outbound |
| **Low Priority** | <48 hours | Follow-ups, nurture emails |

**Action Required:**
- [ ] Confirm these SLA targets or adjust
- [ ] Define what makes an email "high priority"
- [ ] Set up alert if SLA is breached

---

### 4.3 Queue Aging Thresholds

**Question:** How long can an email sit in the approval queue before it's "too old"?

**Recommendation:**
- **<2 hours:** Green (healthy)
- **2-6 hours:** Yellow (needs attention)
- **>6 hours:** Red (escalate)

**Action Required:**
- [ ] Confirm these thresholds or adjust
- [ ] Define escalation process if queue ages >6 hours
  - Option A: Send Slack alert to backup approver
  - Option B: Auto-approve emails with >90% confidence score
  - Option C: Pause AI email generation until queue clears

---

## Section 5: Meeting Prep Expectations

### Why This Matters

Before every sales call, the AI prepares a briefing document. We need to know:
- What fields are **required** (must have)
- What fields are **nice-to-have** (optional)
- How confident the AI should be before auto-populating

---

### 5.1 Required Fields

**Minimum required for every call prep doc:**

| Field | Description | Example |
|-------|-------------|---------|
| **Company Name** | Full legal name | "Acme Corp (Acme Technologies Inc.)" |
| **Industry** | Primary industry/vertical | "B2B SaaS - HR Tech" |
| **Company Size** | Employee count | "150 employees" |
| **Contact Info** | Name, title, email, phone | "Jane Doe, VP Sales, jane@acme.com" |
| **Pain Points** | Top 2-3 challenges | "Struggling with manual lead routing" |

**Action Required:**
- [ ] Review this list - add or remove fields
- [ ] Mark which fields are **blocking** (can't proceed without them)

---

### 5.2 Nice-to-Have Fields

**Optional fields that improve call quality but aren't required:**

| Field | Description | When to Include |
|-------|-------------|-----------------|
| **Recent News** | Funding, product launch, etc. | If found in last 30 days |
| **Tech Stack** | Tools they currently use | If discoverable via LinkedIn/job posts |
| **Decision Process** | Who else is involved in buying decision | If multi-stakeholder deal |
| **Competitive Intel** | What competitors they're considering | If mentioned publicly |
| **Budget Signals** | Indicators of budget availability | If funding/revenue data available |

**Action Required:**
- [ ] Confirm which optional fields are most valuable to you
- [ ] Prioritize: Which should AI spend time researching?

---

### 5.3 Confidence Threshold

**Question:** How confident should the AI be before auto-populating call prep?

**Recommendation:**

| Confidence Score | Action | Example |
|------------------|--------|---------|
| **90-100%** | Auto-populate, no review needed | Company size from LinkedIn (verified) |
| **70-89%** | Auto-populate, flag for review | Pain points inferred from job postings |
| **50-69%** | Leave blank, mark as "uncertain" | Budget signals based on indirect data |
| **<50%** | Don't populate, show error | No data found |

**Action Required:**
- [ ] Set confidence threshold: "Only auto-populate if confidence ≥ ____%"
- [ ] Decide: Should low-confidence fields show "uncertain" or stay blank?

---

### 5.4 Call Prep Format

**What should the final document look like?**

**Option A: Brief Summary (Recommended)**
```markdown
# Call Prep: Jane Doe @ Acme Corp

**Industry:** B2B SaaS - HR Tech (150 employees)
**Pain Points:**
- Manual lead routing causing 30% slower response times
- No integration between CRM and calendar

**Talking Points:**
1. Show case study: Similar company reduced response time 50%
2. Demo: CRM-calendar sync in action
3. Address budget: Most clients see ROI in 90 days

**Likely Objections:**
- "We already have a CRM" → Show integration options
- "Too expensive" → Share pricing tiers and ROI calculator

**Confidence:** 85% (High confidence)
```

**Option B: Detailed Dossier**
```markdown
[Full company background, org chart, tech stack, competitive analysis, etc.]
```

**Action Required:**
- [ ] Choose preferred format (Brief vs Detailed)
- [ ] Provide 2-3 examples of call prep docs you've loved in the past

---

## Section 6: Quick Start Actions (This Week)

To unblock the AI system's quality improvements, complete these actions **this week:**

### Monday-Tuesday:
- [ ] **30 minutes:** Review Section 1 (Approval Rubric)
  - Provide 5 examples of "good" emails
  - Provide 5 examples of "bad" emails

### Wednesday:
- [ ] **45 minutes:** Review Section 2 (Rejection Taxonomy)
  - Define top 5 rejection categories
  - Specify which should auto-regenerate
  - Set escalation rule (e.g., "after 3 rejections, escalate")

### Thursday:
- [ ] **30 minutes:** Review Section 3 (Messaging Standards)
  - Provide 3 subject lines per segment (Enterprise, Mid-Market, SMB)
  - List 10 forbidden phrases

### Friday:
- [ ] **20 minutes:** Review Section 4 (Operational Limits)
  - Set daily approval capacity target
  - Confirm approval SLA (time-to-approve)
  - Set queue aging threshold

---

## Section 7: Meeting Schedule

To align on these inputs, let's schedule:

**Wednesday, February 12 @ 2:00 PM ET (30 min)**
- Review approval rubric and rejection taxonomy
- Align on auto-regenerate vs manual review

**Friday, February 14 @ 10:00 AM ET (30 min)**
- Review messaging standards and operational limits
- Finalize quality thresholds

**Ongoing: Twice Weekly (15 min)**
- Review recent rejects/edits
- Map to taxonomy
- Update AI guidance

---

## Section 8: How Your Input Improves the AI

**What happens after you provide these inputs:**

1. **Approval Rubric** → AI learns what "good" looks like
   - Fewer rejections over time
   - Higher first-pass approval rate

2. **Rejection Taxonomy** → AI learns from mistakes
   - Auto-fixes common issues
   - Reduces your review time

3. **Messaging Standards** → AI adapts to segments
   - Better personalization
   - Higher response rates

4. **Operational Limits** → System respects your capacity
   - No more than X emails/day
   - Queues intelligently

**Expected Timeline:**
- **Week 1:** Initial training data provided (your examples)
- **Week 2-3:** AI learns patterns, approval rate improves
- **Week 4+:** 80%+ first-pass approval rate (goal)

---

## Section 9: Success Metrics (What "Better" Looks Like)

| Metric | Current (Estimate) | Target (1 Month) |
|--------|-------------------|------------------|
| **First-Pass Approval Rate** | 60% | 85% |
| **Time Spent Reviewing** | 60 min/day | 30 min/day |
| **Average Approval Time** | 3 hours | <2 hours |
| **Rejection → Auto-Fix Rate** | 0% | 60% |
| **Email Quality Score (HoS Rating)** | TBD | 4/5 average |

---

## Appendix: Contact & Next Steps

**Questions?**
- Technical questions: Contact Product Technical Officer
- Business questions: Reply to this doc or schedule time

**Next Actions:**
1. Review this document (30 min)
2. Complete "Quick Start Actions" (Week of Feb 10)
3. Schedule alignment meetings (Feb 12 & 14)
4. Provide example emails and call prep docs
5. Weekly rhythm: 15-min feedback sessions (Wed)

---

## Document Version

**Version:** 1.0
**Last Updated:** February 10, 2026
**Owner:** Head of Sales
**Next Review:** February 17, 2026 (After initial inputs provided)
