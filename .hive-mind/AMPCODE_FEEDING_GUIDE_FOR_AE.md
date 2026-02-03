# 🎯 Ampcode Feeding Guide: Training Your AI Revenue Team
**How to Continuously Improve the System**

**Date:** January 19, 2026  
**For:** Account Executives & Revenue Operations  
**Purpose:** What to feed the AI to make it smarter

---

## 📚 What is "Feeding" the System?

Think of the AI like a new employee. The more examples and feedback you give it, the better it performs. "Feeding" means giving it the right information to learn from.

---

## 🎯 The 4 Types of Food Your AI Needs

### **1. 📧 Email Templates (Your Best Work)**

**What to feed:**
- Your highest-performing cold emails
- Subject lines that get opened
- Follow-up sequences that work
- Emails that got meetings booked

**How to feed it:**
```
Create a Google Doc or text file with:
- Subject line
- Email body
- Context (who it worked for, why it worked)
- Results (open rate, reply rate)
```

**Example:**
```
Subject: Quick question about [Company]'s sales automation

Hi [First Name],

I noticed [Company] is hiring SDRs - congrats on the growth!

Most companies your size struggle with [specific pain point]. 
We helped [similar company] achieve [specific result] in [timeframe].

Would you be open to a 15-minute call to explore if we could 
help [Company] achieve similar results?

Best,
Chris

---
Context: Sent to VP Sales at 100-500 employee companies
Results: 45% open rate, 12% reply rate, 3 meetings booked
Why it worked: Specific, relevant, short
```

**When to feed:**
- Week 1: Your top 5 templates
- Monthly: New templates that work
- Quarterly: Updated messaging

**Ampcode Prompt:**
```
"Add these email templates to the AI training:

[Paste your templates here]

Train the CRAFTER agent to use this style and messaging."
```

---

### **2. 🎯 Ideal Customer Profile (Who to Target)**

**What to feed:**
- Company characteristics (size, industry, revenue)
- Job titles to target
- Technologies they use
- Buying signals to look for
- Red flags (who to avoid)

**How to feed it:**
```
Create a simple document with:
- Tier 1 (hot leads): Characteristics
- Tier 2 (warm leads): Characteristics  
- Tier 3 (cold leads): Characteristics
- Do NOT contact: Disqualifiers
```

**Example:**
```
TIER 1 - High Priority:
- Company size: 100-500 employees
- Revenue: $20M-$100M
- Industry: B2B SaaS, Technology
- Job titles: VP Sales, CRO, VP Revenue
- Tech stack: Salesforce or HubSpot
- Buying signals: Recently hired SDRs, raised funding
- Why: High budget, clear need, decision-making authority

TIER 2 - Medium Priority:
- Company size: 50-100 employees
- Revenue: $5M-$20M
- Industry: Professional Services
- Job titles: Sales Director, RevOps Manager
- Why: Growing, some budget, may need education

TIER 3 - Low Priority:
- Company size: 20-50 employees
- Revenue: $1M-$5M
- Industry: Startups
- Why: Limited budget, longer sales cycle

DO NOT CONTACT:
- Companies < 20 employees
- Agencies (unless enterprise)
- Competitors
- Previous customers who churned
- Unsubscribed contacts
```

**When to feed:**
- Week 1: Initial ICP definition
- Monthly: Refinements based on results
- Quarterly: Major updates

**Ampcode Prompt:**
```
"Update the ICP (Ideal Customer Profile) for the SEGMENTOR agent:

[Paste your ICP here]

Ensure leads are scored and prioritized based on these criteria."
```

---

### **3. ❌ Rejection Feedback (What NOT to Do)**

**What to feed:**
- Why you rejected an AI-generated email
- What was wrong with it
- How it should be improved

**How to feed it:**
```
When reviewing AI emails, note:
- What's wrong: "Too pushy", "Wrong tone", "Missing context"
- What to fix: "Add more personalization", "Soften the ask"
- Better example: Show what it should say instead
```

**Example:**
```
REJECTED EMAIL:
Subject: We can help you

Hi John,

We have a great solution for your company. Let's talk.

Best,
Chris

---
REJECTION REASON:
- Too generic (no personalization)
- No context (why are we reaching out?)
- Weak subject line (no value proposition)
- Pushy tone (no relationship building)

BETTER VERSION:
Subject: Quick question about Acme's SDR hiring

Hi John,

Saw you're hiring 3 SDRs on LinkedIn - congrats on the growth!

Most VPs I talk to struggle with ramping new SDRs quickly. 
We helped [similar company] cut ramp time from 90 to 30 days.

Would you be open to a quick call to share what worked?

Best,
Chris
```

**When to feed:**
- Week 4-5: During canary testing (every rejection)
- Week 6+: Weekly batch of rejections
- Ongoing: Major issues immediately

**Ampcode Prompt:**
```
"Log this rejection as a learning event:

Campaign ID: [ID]
Rejection reason: [Why you rejected it]
What was wrong: [Specific issues]
Better approach: [What it should have been]

Update the CRAFTER agent to avoid this pattern."
```

---

### **4. ✅ Success Stories (What's Working)**

**What to feed:**
- Campaigns that got great responses
- What made them successful
- Patterns to replicate

**How to feed it:**
```
Share:
- Campaign details (who, what, when)
- Results (open rate, reply rate, meetings)
- Why it worked (your analysis)
- What to repeat
```

**Example:**
```
SUCCESSFUL CAMPAIGN:
Campaign: "SDR Hiring Outreach"
Sent to: VP Sales at 100-500 employee companies
Subject: "Quick question about [Company]'s SDR hiring"

RESULTS:
- Sent: 50 emails
- Opened: 28 (56% open rate)
- Replied: 8 (16% reply rate)
- Meetings: 3 (6% meeting rate)

WHY IT WORKED:
- Timely (referenced recent hiring)
- Relevant (addressed specific pain point)
- Social proof (mentioned similar company)
- Soft ask (just a quick call)
- Personal (researched each company)

WHAT TO REPLICATE:
- Use hiring as a trigger
- Reference specific pain points
- Include social proof
- Keep asks small
- Personalize with research
```

**When to feed:**
- Weekly: Top performers
- Monthly: Pattern analysis
- Quarterly: Major wins

**Ampcode Prompt:**
```
"Log this successful campaign:

[Paste campaign details and results]

Update the CRAFTER agent to replicate these successful patterns."
```

---

## 📅 Feeding Schedule (What to Do When)

### **Week 1: Initial Training**
**Time: 2 hours**

Feed the AI:
1. ✅ Your top 5 email templates
2. ✅ Your Ideal Customer Profile
3. ✅ Examples of good vs. bad leads
4. ✅ Your brand voice guidelines

**Ampcode Prompts:**
```
"Train the system on my email templates and ICP:

EMAIL TEMPLATES:
[Paste your 5 best templates]

IDEAL CUSTOMER PROFILE:
[Paste your ICP definition]

Ensure all agents use this style and targeting."
```

---

### **Week 2-3: Shadow Mode Feedback**
**Time: 1 hour/week**

Feed the AI:
1. ⬜ Comparison feedback (AI vs. your emails)
2. ⬜ What AI did better
3. ⬜ What AI did worse
4. ⬜ Adjustments needed

**Ampcode Prompts:**
```
"Review shadow mode results:

AI performed better at: [List strengths]
AI needs improvement on: [List weaknesses]
Specific adjustments: [What to change]

Update agents accordingly."
```

---

### **Week 4-5: Canary Testing Feedback**
**Time: 2-3 hours/week**

Feed the AI:
1. ⬜ Every rejection (with reason)
2. ⬜ Every approval (with notes)
3. ⬜ Response patterns
4. ⬜ What's working/not working

**Ampcode Prompts:**
```
"Process this week's feedback:

REJECTIONS (5 total):
1. [Campaign ID] - [Reason] - [Better approach]
2. [Campaign ID] - [Reason] - [Better approach]
...

APPROVALS (45 total):
- Common success patterns: [List]
- What to replicate: [List]

Update CRAFTER and log learnings."
```

---

### **Week 6+: Production Feedback**
**Time: 1 hour/week**

Feed the AI:
1. ⬜ Weekly performance summary
2. ⬜ Top performers (replicate)
3. ⬜ Bottom performers (avoid)
4. ⬜ New templates or messaging

**Ampcode Prompts:**
```
"Weekly performance update:

TOP PERFORMERS:
- [Campaign] - [Results] - [Why it worked]

BOTTOM PERFORMERS:
- [Campaign] - [Results] - [Why it failed]

NEW TEMPLATES:
[Any new messaging to add]

Update system and apply learnings."
```

---

### **Monthly: Deep Analysis**
**Time: 30 minutes**

Feed the AI:
1. ⬜ Month-over-month trends
2. ⬜ Pattern analysis
3. ⬜ ICP refinements
4. ⬜ Strategic adjustments

**Ampcode Prompts:**
```
"Monthly optimization:

PERFORMANCE TRENDS:
- Reply rates: [Trend]
- Meeting rates: [Trend]
- Best performing segments: [List]

ICP UPDATES:
[Any changes to targeting]

STRATEGIC ADJUSTMENTS:
[New approaches to test]

Implement improvements."
```

---

## 🎯 Quick Reference: Ampcode Prompts

### **Adding Email Templates:**
```
"Add these email templates to CRAFTER training:

[Template 1]
[Template 2]
[Template 3]

Use this style for all future campaigns."
```

### **Updating ICP:**
```
"Update SEGMENTOR ICP criteria:

[New ICP definition]

Re-score existing leads and apply to new leads."
```

### **Logging Rejections:**
```
"Log rejection learning:

Campaign: [ID]
Reason: [Why rejected]
Fix: [What to do instead]

Update CRAFTER to avoid this pattern."
```

### **Logging Successes:**
```
"Log successful campaign:

Campaign: [ID]
Results: [Metrics]
Why it worked: [Analysis]

Replicate this pattern in future campaigns."
```

### **Weekly Batch Update:**
```
"Process this week's feedback:

Rejections: [Count] - [Common patterns]
Approvals: [Count] - [Common patterns]
Top performer: [Campaign] - [Why]
Bottom performer: [Campaign] - [Why]

Apply learnings and update agents."
```

---

## 📊 What Good Feeding Looks Like

### **Example: Week 4 Feedback Session**

**You spend 2 hours reviewing 50 AI-generated emails:**

**Approved: 45 (90%)**
- Note common success patterns
- Identify best performers
- Feed back what's working

**Rejected: 5 (10%)**
- Note why each was rejected
- Provide better examples
- Feed back what to avoid

**Ampcode Prompt:**
```
"Week 4 canary testing results:

APPROVED (45/50 = 90%):
Common success patterns:
- Personalized subject lines (mentioned company name)
- Referenced specific pain points
- Included social proof
- Soft, consultative tone

Best performer:
- Campaign: tier2_saas_outreach_v3
- Open rate: 58%
- Reply rate: 14%
- Why: Perfect personalization + timing

REJECTED (5/50 = 10%):
1. Campaign_123: Too generic, no personalization
2. Campaign_124: Wrong pain point for this industry
3. Campaign_125: Subject line too salesy
4. Campaign_126: Email too long (>150 words)
5. Campaign_127: Mentioned competitor incorrectly

LEARNINGS:
- Always personalize subject line
- Match pain points to industry
- Keep emails under 150 words
- Verify competitor mentions
- Maintain consultative tone

Update CRAFTER agent with these learnings."
```

**Result:** AI improves from 90% → 95% approval rate next week

---

## 🎯 Bottom Line: The Feeding Loop

```
1. AI generates campaigns
   ↓
2. You review and provide feedback
   ↓
3. Feed feedback to Ampcode
   ↓
4. AI learns and improves
   ↓
5. Next campaigns are better
   ↓
(Repeat weekly)
```

**Time investment:**
- Week 1: 2 hours (initial training)
- Week 2-3: 1 hour/week (shadow feedback)
- Week 4-5: 2-3 hours/week (canary feedback)
- Week 6+: 1 hour/week (production feedback)

**Result:**
- AI gets smarter every week
- Approval rates increase
- Your time decreases
- Results improve

---

## 📚 Templates for You

### **Email Template Submission:**
```
TEMPLATE NAME: [Name]
SUBJECT: [Subject line]
BODY:
[Email body]

CONTEXT:
- Target: [Who this is for]
- Results: [Open/reply/meeting rates]
- Why it works: [Your analysis]
```

### **ICP Update:**
```
TIER 1 (Hot):
- Company size: [Range]
- Revenue: [Range]
- Industry: [List]
- Job titles: [List]
- Buying signals: [List]

TIER 2 (Warm):
[Same format]

TIER 3 (Cold):
[Same format]

DO NOT CONTACT:
[Disqualifiers]
```

### **Rejection Feedback:**
```
CAMPAIGN: [ID]
REJECTED BECAUSE:
- [Reason 1]
- [Reason 2]

BETTER APPROACH:
[What it should have been]
```

### **Success Story:**
```
CAMPAIGN: [ID]
RESULTS:
- Sent: [Number]
- Opened: [Number] ([%])
- Replied: [Number] ([%])
- Meetings: [Number] ([%])

WHY IT WORKED:
- [Reason 1]
- [Reason 2]

REPLICATE:
- [Pattern 1]
- [Pattern 2]
```

---

**Questions?** Just ask: "How do I feed [specific thing] to the AI?"

**Ready to start?** Begin with your top 5 email templates and ICP definition.

---

**Created:** January 19, 2026  
**Version:** 1.0  
**For:** Account Executives & Revenue Operations
