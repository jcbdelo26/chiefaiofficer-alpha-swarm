# 🔄 Alpha Swarm Complete Workflow Walkthrough

> Detailed step-by-step guide for running the lead harvesting through campaign execution pipeline

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Workflow Overview](#workflow-overview)
3. [Step 1: Source Selection](#step-1-source-selection)
4. [Step 2: Lead Scraping (HUNTER)](#step-2-lead-scraping-hunter)
5. [Step 3: Lead Enrichment (ENRICHER)](#step-3-lead-enrichment-enricher)
6. [Step 4: Segmentation & Scoring (SEGMENTOR)](#step-4-segmentation--scoring-segmentor)
7. [Step 5: Campaign Generation (CRAFTER)](#step-5-campaign-generation-crafter)
8. [Step 6: AE Review (GATEKEEPER)](#step-6-ae-review-gatekeeper)
9. [Step 7: Campaign Execution](#step-7-campaign-execution)
10. [Self-Annealing Loop](#self-annealing-loop)

---

## Prerequisites

Before running the workflow, ensure:

```powershell
# 1. Activate virtual environment
cd "d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
.\.venv\Scripts\Activate.ps1

# 2. Verify dependencies are installed
pip list | Select-String "requests|anthropic|rich"

# 3. Verify .env is configured
cat .env | Select-String "API_KEY"

# 4. Test all connections
python execution\test_connections.py
```

**Expected output:**
```
🔌 Alpha Swarm Connection Test
=================================
✅ GoHighLevel: Connected to: [Your Location Name]
✅ Clay: API accessible
✅ RB2B: Connected
✅ Instantly: Found 1 account(s)
✅ LinkedIn: Session valid
```

---

## Workflow Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        COMPLETE WORKFLOW PIPELINE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌───────────────┐│
│  │ 1. SOURCE   │ →  │ 2. HUNTER   │ →  │ 3. ENRICHER │ →  │ 4. SEGMENTOR  ││
│  │ Selection   │    │ Scraping    │    │ Clay/RB2B   │    │ ICP Scoring   ││
│  └─────────────┘    └─────────────┘    └─────────────┘    └───────────────┘│
│                                                                  │          │
│                                                                  ▼          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌───────────────┐│
│  │ 7. EXECUTE  │ ←  │ 6. APPROVE  │ ←  │ GATEKEEPER  │ ←  │ 5. CRAFTER    ││
│  │ Instantly   │    │ AE Review   │    │ Queue       │    │ Campaign Gen  ││
│  └─────────────┘    └─────────────┘    └─────────────┘    └───────────────┘│
│                                                                             │
│                              ┌─────────────┐                                │
│                              │ 8. LEARN    │                                │
│                              │ Self-Anneal │                                │
│                              └─────────────┘                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Time Estimates:**
| Step | Automated Time | Human Time |
|------|----------------|------------|
| Scraping | ~5-30 min | - |
| Enrichment | ~1-10 min | - |
| Segmentation | ~30 sec | - |
| Campaign Gen | ~1 min | - |
| AE Review | - | 5-15 min |
| Execution | Automated | - |

---

## Step 1: Source Selection

### Available Sources

| Source Type | Command Flag | Best For | ICP Weight |
|-------------|--------------|----------|------------|
| Competitor Followers | `--company gong` | Volume | +10 |
| Event Attendees | `--url event_url` | High Intent | +18 |
| Group Members | `--url group_url` | Community | +12 |
| Post Commenters | `--url post_url` | Engagement | +20 |
| Post Likers | `--url post_url --include-likers` | Passive | +8 |

### Pre-Defined Competitors

```python
COMPETITORS = {
    "gong": "https://linkedin.com/company/gong",
    "clari": "https://linkedin.com/company/clari",
    "chorus": "https://linkedin.com/company/chorus-ai",
    "people.ai": "https://linkedin.com/company/people-ai",
    "outreach": "https://linkedin.com/company/outreach"
}
```

### Target LinkedIn Groups

```python
TARGET_GROUPS = {
    "revenue-collective": "15K+ members - RevOps leaders",
    "revops-coop": "8K+ members - RevOps practitioners",
    "sales-operations": "45K+ members - Sales Ops pros",
    "modern-sales-pros": "25K+ members - Sales leaders"
}
```

---

## Step 2: Lead Scraping (HUNTER)

### Running the Scraper

```powershell
# Option A: Competitor followers
python execution\hunter_scrape_followers.py --company gong --limit 100

# Option B: Event attendees
python execution\hunter_scrape_events.py --url "https://linkedin.com/events/your-event-id" --limit 100

# Option C: Group members
python execution\hunter_scrape_groups.py --group revenue-collective --limit 100

# Option D: Post engagers
python execution\hunter_scrape_posts.py --url "https://linkedin.com/posts/activity-id" --limit 100
```

### Expected Output Structure

```
.hive-mind/scraped/followers_abc123_20260112_160000.json
```

**Sample Output:**
```json
{
  "batch_id": "abc123-def456-...",
  "scraped_at": "2026-01-12T16:00:00Z",
  "source_type": "competitor_follower",
  "lead_count": 87,
  "leads": [
    {
      "lead_id": "uuid",
      "source_type": "competitor_follower",
      "source_name": "Gong",
      "linkedin_url": "https://linkedin.com/in/john-smith",
      "name": "John Smith",
      "first_name": "John",
      "last_name": "Smith",
      "title": "VP Revenue Operations",
      "company": "Acme Corp",
      "location": "San Francisco, CA",
      "engagement_action": "followed"
    }
  ]
}
```

### Rate Limit Protections

```
🕵️ HUNTER: Rate limiting applied
- Max 5 requests/minute
- Max 100 profiles/hour
- Max 500 profiles/day
- Auto-pause on 429 response
```

---

## Step 3: Lead Enrichment (ENRICHER)

### Running Enrichment

```powershell
# Enrich the batch
python execution\enricher_clay_waterfall.py --input .hive-mind\scraped\followers_abc123_20260112_160000.json
```

### Enrichment Pipeline

```
┌───────────────────────────────────────────────────────────────┐
│                    ENRICHMENT WATERFALL                       │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  1. CLAY WATERFALL                                            │
│     ├─ Apollo.io (primary)                                    │
│     ├─ ZoomInfo (fallback 1)                                  │
│     ├─ Clearbit (fallback 2)                                  │
│     ├─ Hunter.io (fallback 3)                                 │
│     └─ Lusha (fallback 4)                                     │
│                                                               │
│  2. RB2B CROSS-REFERENCE                                      │
│     └─ Match against website visitors                         │
│                                                               │
│  3. COMPANY INTELLIGENCE                                      │
│     ├─ Tech stack (BuiltWith)                                 │
│     ├─ Funding data (Crunchbase)                              │
│     └─ News/signals (Exa Search)                              │
│                                                               │
│  4. INTENT SIGNALS                                            │
│     ├─ Hiring signals                                         │
│     ├─ Funding announcements                                  │
│     ├─ Leadership changes                                     │
│     └─ Competitor usage                                       │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### Expected Output

```
.hive-mind/enriched/enriched_20260112_161500.json
```

**Sample Enriched Lead:**
```json
{
  "lead_id": "uuid",
  "linkedin_url": "https://linkedin.com/in/john-smith",
  "contact": {
    "work_email": "john.smith@acmecorp.com",
    "phone": "+1-555-123-4567",
    "email_verified": true,
    "email_confidence": 95
  },
  "company": {
    "name": "Acme Corp",
    "domain": "acmecorp.com",
    "employee_count": 250,
    "industry": "SaaS",
    "revenue_estimate": 25000000,
    "technologies": ["Salesforce", "HubSpot", "Gong"]
  },
  "intent": {
    "hiring_revops": true,
    "recent_funding": false,
    "competitor_user": true,
    "intent_score": 65,
    "signals": ["hiring", "competitor_user"]
  },
  "enrichment_quality": 85
}
```

---

## Step 4: Segmentation & Scoring (SEGMENTOR)

### Running Segmentation

```powershell
python execution\segmentor_classify.py --input .hive-mind\enriched\enriched_20260112_161500.json
```

### ICP Scoring Algorithm

```
┌─────────────────────────────────────────────────────────────────┐
│                    ICP SCORING (0-100)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  COMPANY SIZE (20 points max)                                   │
│  ├─ 51-200 employees: +20                                       │
│  ├─ 201-500 employees: +15                                      │
│  ├─ 20-50 employees: +10                                        │
│  └─ 501-1000 employees: +10                                     │
│                                                                 │
│  INDUSTRY (20 points max)                                       │
│  ├─ SaaS/Software: +20                                          │
│  ├─ Technology: +15                                             │
│  └─ Professional Services: +10                                  │
│                                                                 │
│  TITLE (25 points max)                                          │
│  ├─ CRO/VP Revenue/VP Sales: +25                                │
│  ├─ Director Sales/RevOps: +15                                  │
│  └─ Manager RevOps/Sales Ops: +5                                │
│                                                                 │
│  REVENUE (15 points max)                                        │
│  ├─ $10M-$50M: +15                                              │
│  ├─ $5M-$10M: +12                                               │
│  └─ $50M-$100M: +10                                             │
│                                                                 │
│  ENGAGEMENT (20 points max)                                     │
│  ├─ Post commenter: +20                                         │
│  ├─ Event attendee: +18                                         │
│  ├─ Group member: +12                                           │
│  ├─ Competitor follower: +10                                    │
│  └─ Post liker: +8                                              │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  TIER CLASSIFICATION                                            │
│  ├─ Tier 1 (85-100): VIP treatment, 1:1 personalization         │
│  ├─ Tier 2 (70-84): High priority, 7-touch sequence             │
│  ├─ Tier 3 (50-69): Standard outreach, 4-touch sequence         │
│  ├─ Tier 4 (30-49): Nurture only                                │
│  └─ Disqualified (0-29): Do not contact                         │
└─────────────────────────────────────────────────────────────────┘
```

### Expected Output

```
📊 Segmentation Summary

ICP Tier Distribution:
| Tier         | Count | Percentage |
|--------------|-------|------------|
| TIER_1       | 8     | 9.2%       |
| TIER_2       | 15    | 17.2%      |
| TIER_3       | 32    | 36.8%      |
| TIER_4       | 22    | 25.3%      |
| DISQUALIFIED | 10    | 11.5%      |

Campaign Recommendations:
| Campaign               | Count |
|------------------------|-------|
| competitor_displacement| 45    |
| thought_leadership     | 12    |
| community_outreach     | 20    |
```

---

## Step 5: Campaign Generation (CRAFTER)

### Running Campaign Generator

```powershell
python execution\crafter_campaign.py --input .hive-mind\segmented\segmented_20260112_162000.json
```

### Template Selection Logic

```python
SOURCE_TO_TEMPLATE = {
    "competitor_follower": "competitor_displacement",
    "event_attendee": "event_followup",
    "post_commenter": "thought_leadership",
    "group_member": "community_outreach",
    "post_liker": "competitor_displacement",
    "website_visitor": "website_visitor"
}
```

### Email Sequence Structure

```
┌───────────────────────────────────────────────────────────────┐
│                 STANDARD 4-TOUCH SEQUENCE                     │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  STEP 1: Initial Outreach (Day 0)                             │
│  ├─ Subject A/B variants                                      │
│  ├─ Personalized body with hooks                              │
│  └─ Clear CTA with calendar link                              │
│                                                               │
│  STEP 2: Follow-up 1 (Day 3)                                  │
│  ├─ Shorter, value-focused                                    │
│  └─ Case study or social proof                                │
│                                                               │
│  STEP 3: Follow-up 2 (Day 7)                                  │
│  ├─ Different angle                                           │
│  └─ Specific benefit for their role                           │
│                                                               │
│  STEP 4: Breakup (Day 14)                                     │
│  ├─ Respectful close                                          │
│  └─ Leave door open                                           │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### Personalization Variables

```jinja2
{{ lead.first_name }}     → "John"
{{ lead.company }}        → "Acme Corp"
{{ lead.title }}          → "VP Revenue Operations"
{{ source.name }}         → "Gong"
{{ context.competitor }}  → "Gong"
{{ engagement.content }}  → "[Their LinkedIn comment]"
{{ sender.calendar_link }} → "https://calendly.com/..."
```

### Expected Output

```
Campaign Summary
| Campaign                    | Type                  | Leads | Avg ICP | Status         |
|-----------------------------|-----------------------|-------|---------|----------------|
| tier1_competitor_displ_2026 | competitor_displacement| 8    | 92      | pending_review |
| tier2_competitor_displ_2026 | competitor_displacement| 15   | 76      | pending_review |
| tier3_community_outre_2026  | community_outreach    | 20   | 58      | pending_review |

Total: 3 campaigns, 43 leads
```

---

## Step 6: AE Review (GATEKEEPER)

### Queue Campaigns for Review

```powershell
python execution\gatekeeper_queue.py --input .hive-mind\campaigns\campaigns_20260112_163000.json
```

### Start Review Dashboard

```powershell
python execution\gatekeeper_queue.py --serve --port 5000
```

**Open in browser:** http://localhost:5000

### Dashboard Features

```
┌─────────────────────────────────────────────────────────────────┐
│  🚪 GATEKEEPER - Campaign Review Dashboard                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐    │
│  │ PENDING │  │ APPROVED│  │ REJECTED│  │ APPROVAL RATE   │    │
│  │    3    │  │   12    │  │    2    │  │      86%        │    │
│  └─────────┘  └─────────┘  └─────────┘  └─────────────────┘    │
│                                                                 │
│  [Campaign Card]                                                │
│  ├─ Campaign Name: tier1_competitor_disp_20260112               │
│  ├─ Segment: tier_1 | Leads: 8 | ICP Score: 92                  │
│  ├─ Email Preview:                                              │
│  │   Subject A: "John, what Gong isn't showing you"             │
│  │   Subject B: "Beyond Gong for Acme Corp"                     │
│  │   Body: "Hi John, I noticed you follow Gong's updates..."    │
│  └─ Actions: [✓ Approve] [✗ Reject] [✎ Edit]                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### CLI Approve/Reject

```powershell
# Approve a campaign
python execution\gatekeeper_queue.py --approve "abc123-review-id"

# Reject a campaign
python execution\gatekeeper_queue.py --reject "abc123-review-id" --reason "Subject line too aggressive"

# Check queue status
python execution\gatekeeper_queue.py --status
```

---

## Step 7: Campaign Execution

### Push to Instantly (After Approval)

```powershell
# Approved campaigns are pushed to Instantly
python execution\instantly_push.py --input .hive-mind\campaigns\approved\campaign_abc123.json
```

> Note: This script would be created as part of Phase 4 implementation.

### Instantly Campaign Structure

```json
{
  "name": "tier1_competitor_disp_20260112",
  "from_email": "chris@chiefaiofficer.com",
  "schedule": {
    "timezone": "America/New_York",
    "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    "start_hour": 9,
    "end_hour": 17
  },
  "leads": [...],
  "sequences": [
    {"delay_days": 0, "subject": "...", "body": "..."},
    {"delay_days": 3, "subject": "...", "body": "..."},
    {"delay_days": 7, "subject": "...", "body": "..."},
    {"delay_days": 14, "subject": "...", "body": "..."}
  ]
}
```

---

## Self-Annealing Loop

### Learning from Outcomes

The system continuously learns from:

1. **AE Rejections** → Updates campaign templates
2. **Email Performance** → Optimizes send timing, subject lines
3. **ICP Misses** → Refines scoring algorithm
4. **Pipeline Errors** → Improves error handling

### Reinforcement Learning Integration

```python
# After campaign results come in
from execution.rl_engine import RLEngine

engine = RLEngine()

# Create state from lead
state = engine.get_state(lead)

# Get action that was taken
action = "template_competitor_displacement"

# Calculate reward from outcome
outcome = {
    "email_opened": 1,
    "reply_received": 0,
    "meeting_booked": 0
}
reward = engine.calculate_reward(outcome)

# Update Q-table
engine.update(state, action, reward, next_state)

# Periodically save learned policy
engine.save_policy()
```

### Drift Detection

```python
from execution.drift_detector import DriftDetector, DynamicAssurance

# Monitor for distribution shifts
detector = DriftDetector()
result = detector.check_drift("icp_score")

if result.has_drift:
    # Alert team and potentially pause
    trigger_human_review()

# Verify assurance cases
assurance = DynamicAssurance()
assurance.verify_all()
```

---

## Quick Reference Commands

```powershell
# Full pipeline command sequence
cd "d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
.\.venv\Scripts\Activate.ps1

# 1. Scrape competitors
python execution\hunter_scrape_followers.py --company gong --limit 100

# 2. Enrich leads
python execution\enricher_clay_waterfall.py --input (Get-ChildItem .hive-mind\scraped\*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

# 3. Segment and score
python execution\segmentor_classify.py --input (Get-ChildItem .hive-mind\enriched\*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

# 4. Generate campaigns
python execution\crafter_campaign.py --input (Get-ChildItem .hive-mind\segmented\*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

# 5. Queue for review
python execution\gatekeeper_queue.py --input (Get-ChildItem .hive-mind\campaigns\*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

# 6. Start dashboard
python execution\gatekeeper_queue.py --serve --port 5000
```

---

*Workflow Version: 1.0*
*Last Updated: 2026-01-12*
