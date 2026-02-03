---
description: Automated meeting brief generation triggered at 8 PM night before scheduled meetings
triggers:
  - type: cron
    schedule: "0 20 * * *"  # 8 PM daily
  - type: event
    source: meeting_confirmed
  - type: manual
    command: /meeting-prep
agents:
  - RESEARCHER
  - QUEEN
---

# Unified Meeting Prep Workflow

## Overview
This workflow automatically generates comprehensive meeting briefs for all scheduled meetings the following day. It triggers at 8 PM to give AEs time to review before their meetings.

## Prerequisites
- [ ] Google Calendar API authenticated
- [ ] Exa MCP for web research (`mcp-servers/exa-mcp/`)
- [ ] GHL MCP for contact history
- [ ] SMTP configured for brief delivery

---

## Trigger Configuration

### Daily Cron (Primary)
```yaml
schedule: "0 20 * * *"
# 8:00 PM daily (Manila Time)
# Generates briefs for all tomorrow's meetings
```

### Event Trigger (Secondary)
```yaml
trigger: meeting_confirmed
delay: "calculate_8pm_night_before"
# When new meeting is booked, schedule brief for 8 PM night before
```

### Manual Override
```bash
# Generate brief for specific meeting
python execution/workflows/meeting_prep.py --meeting-id "CAL-xxx"

# Generate briefs for specific date
python execution/workflows/meeting_prep.py --date "2026-01-25"

# Dry run (generate but don't deliver)
python execution/workflows/meeting_prep.py --dry-run --tomorrow

# Force regenerate existing brief
python execution/workflows/meeting_prep.py --meeting-id "CAL-xxx" --force

# Start scheduled daemon (runs daily at 8 PM)
python execution/workflows/meeting_prep.py --daemon
```

---

## Workflow Steps

// turbo-all

### Step 1: QUEEN Fetches Tomorrow's Meetings
```bash
python execution/unified_queen_orchestrator.py --get_meetings \
  --date "tomorrow" \
  --include_attendees
```

**Query Parameters:**
- Date: Tomorrow (current date + 1)
- Status: Confirmed only (no tentative)
- Include: External attendees only (exclude internal)

**Output Format:**
```json
{
  "meetings": [
    {
      "meeting_id": "CAL-12345",
      "title": "Discovery Call: Acme Corp",
      "datetime": "2026-01-23T14:00:00-08:00",
      "duration_minutes": 30,
      "attendees": [
        {
          "email": "john@acmecorp.com",
          "name": "John Smith",
          "role": "VP Sales"
        }
      ],
      "ghl_contact_id": "GHL-67890",
      "meeting_type": "discovery"
    }
  ]
}
```

**Handoff:** → RESEARCHER (for each meeting)

---

### Step 2: RESEARCHER Conducts Company Research
```bash
python execution/researcher_agent.py --research_type "company" \
  --company "$COMPANY_NAME" \
  --domain "$COMPANY_DOMAIN"
```

**Research Sources:**
| Source | Data Points |
|--------|-------------|
| Company Website | About, Products, Pricing, Team |
| LinkedIn Company | Size, Industry, Recent Posts |
| Crunchbase/ZoomInfo | Funding, Revenue, Growth |
| News (last 30 days) | Press releases, Mentions |
| Tech Stack (BuiltWith) | Current tools |

**Cache Strategy:**
- Company data: 7-day cache
- News: 1-day cache
- Location: `.hive-mind/researcher/cache/`

**Guardrails:**
- Max research time: 60 seconds per company
- Fallback to cached data if API fails
- Skip if company already researched today

**Output:** Company intel JSON

**Handoff:** → Step 3 (Attendee Research)

---

### Step 3: RESEARCHER Conducts Attendee Research
```bash
python execution/researcher_agent.py --research_type "attendee" \
  --email "$ATTENDEE_EMAIL" \
  --ghl_contact_id "$GHL_ID"
```

**Research Sources:**
| Source | Data Points |
|--------|-------------|
| LinkedIn Profile | Title, Experience, Posts, Mutual Connections |
| GHL Contact History | Previous emails, Calls, Notes |
| Previous Meetings | Past briefs, Outcomes |
| Email Thread | Recent conversation context |

**Data Points Collected:**
- Current role & tenure
- Career history (last 3 positions)
- Recent LinkedIn activity
- Known pain points (from GHL notes)
- Communication preferences
- Previous objections raised

**Output:** Attendee profile JSON

**Handoff:** → Step 4 (Objection Prediction)

---

### Step 4: RESEARCHER Predicts Likely Objections
```bash
python execution/researcher_agent.py --predict_objections \
  --company_data "$COMPANY_JSON" \
  --attendee_data "$ATTENDEE_JSON"
```

**Objection Prediction Model:**
| Factor | Likely Objection |
|--------|------------------|
| Company < 100 employees | "Too small for this" |
| Already using competitor | "We have a solution" |
| Recent layoffs | "Budget constraints" |
| Long sales cycle industry | "Need more stakeholders" |
| Technical role | "Need to see demo first" |

**Response Preparation:**
For each predicted objection, generate:
1. Acknowledgment statement
2. Reframe using value
3. Proof point from similar company
4. Transition to next topic

**Output:** Objection + Response pairs (Top 3)

**Handoff:** → Step 5 (Proof Points)

---

### Step 5: RESEARCHER Selects Relevant Proof Points
```bash
python execution/researcher_agent.py --select_proof_points \
  --industry "$INDUSTRY" \
  --company_size "$SIZE" \
  --use_case "$PRIMARY_NEED"
```

**Proof Point Matching:**
- Match by industry (exact > similar)
- Match by company size (+/- 50%)
- Match by use case/pain point
- Prioritize recent wins (< 6 months)

**Output Format:**
```json
{
  "proof_points": [
    {
      "company": "Similar Corp",
      "industry": "B2B SaaS",
      "size": "120 employees",
      "outcome": "40% increase in meetings booked",
      "quote": "The system paid for itself in 2 weeks",
      "relevance_score": 0.92
    }
  ]
}
```

**Handoff:** → Step 6 (Question Generation)

---

### Step 6: RESEARCHER Generates Discovery Questions
```bash
python execution/researcher_agent.py --generate_questions \
  --meeting_type "$MEETING_TYPE" \
  --stage "$SALES_STAGE"
```

**Question Categories:**

#### Business Questions (5)
1. Current state inquiry
2. Challenge/pain point probe
3. Impact of problem
4. Decision process query
5. Success criteria definition

#### BANT Questions (2)
1. Budget: "What's the investment range you're considering?"
2. Timeline: "When are you looking to have a solution in place?"

**Question Personalization:**
- Reference company-specific findings
- Tie to industry trends
- Build on previous conversation context

**Output:** 7 prioritized questions

**Handoff:** → Step 7 (Brief Generation)

---

### Step 7: RESEARCHER Generates Meeting Brief
```bash
python execution/researcher_agent.py --generate_brief \
  --meeting_id "$MEETING_ID" \
  --output_format "markdown"
```

**Brief Template:**
```markdown
# Pre-Meeting Brief: {{Company}} 
## {{Meeting Date}} at {{Meeting Time}} ({{Timezone}})

### 🎯 Meeting Objective
{{Discovery/Demo/Proposal/Close}} call with {{Attendees}}

### 📰 Recent Developments (Last 30 Days)
- {{News item 1}}
- {{News item 2}}
- {{News item 3}}

### 👥 Meeting Attendees
**{{Name}}** - {{Title}}
- Tenure: {{X}} years at {{Company}}
- Previous: {{Last role}}
- LinkedIn: {{Recent activity summary}}
- GHL Notes: {{Key history points}}

### ⚠️ Likely Objections & Responses
1. **{{Objection}}**
   - Acknowledge: "{{Acknowledgment}}"
   - Reframe: "{{Value statement}}"
   - Proof: "{{Similar company}} saw {{outcome}}"

2. **{{Objection}}**
   ...

### 🏆 Relevant Proof Points
| Company | Outcome | Relevance |
|---------|---------|-----------|
| {{Company}} | {{Outcome}} | {{Score}}% |

### ❓ Questions to Ask
**Business:**
1. {{Question}}
2. {{Question}}
...

**BANT:**
1. {{Budget question}}
2. {{Timeline question}}

### 📋 Suggested Agenda (30 min)
- 0-5 min: Rapport & context setting
- 5-15 min: Discovery questions
- 15-20 min: Value proposition
- 20-25 min: Proof points & objections
- 25-30 min: Next steps & BANT

---
*Generated: {{Timestamp}} | Quality Score: {{Score}}%*
```

**Quality Scoring:**
| Component | Weight | Criteria |
|-----------|--------|----------|
| Company info | 20% | Recency, completeness |
| Attendee info | 20% | Profile depth, history |
| Objections | 20% | Relevance, response quality |
| Proof points | 20% | Match score, recency |
| Questions | 20% | Specificity, personalization |

**Minimum Quality:** 80% (regenerate if below)

**Handoff:** → Step 8 (Delivery)

---

### Step 8: RESEARCHER Delivers Brief to AE
```bash
python execution/researcher_agent.py --deliver_brief \
  --brief_id "$BRIEF_ID" \
  --recipient "$AE_EMAIL"
```

**Delivery Channels:**
1. **Email** (Primary)
   - Subject: "📋 Brief: {{Company}} - {{Date}} {{Time}}"
   - Inline markdown rendering
   - PDF attachment option

2. **Slack** (Secondary)
   - Direct message to AE
   - Brief summary with link to full

3. **GHL** (Logging)
   - Attach brief to contact timeline
   - Tag meeting with "brief_generated"

**Storage:**
- Save to `.hive-mind/researcher/briefs/{{MEETING_ID}}.md`
- Index in brief registry

**Handoff:** → QUEEN (logging)

---

### Step 9: QUEEN Logs Brief Generation
```bash
python execution/unified_queen_orchestrator.py --log_brief \
  --meeting_id "$MEETING_ID" \
  --quality_score "$SCORE" \
  --delivery_status "$STATUS"
```

**Tracked Metrics:**
| Metric | Description |
|--------|-------------|
| `briefs_generated` | Count of briefs created |
| `avg_quality_score` | Average quality score |
| `delivery_success_rate` | Successful deliveries |
| `generation_time_ms` | Time to generate |
| `cache_hit_rate` | Research cache usage |

**Self-Annealing:**
- Track which proof points lead to closed deals
- Refine objection predictions based on actual objections
- Update question effectiveness scores

---

## Parallel Execution (Multiple Meetings)

When multiple meetings exist for tomorrow:

```
                ┌──────────────────┐
                │ QUEEN: Get List  │
                └────────┬─────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
   ┌─────────┐      ┌─────────┐      ┌─────────┐
   │Meeting 1│      │Meeting 2│      │Meeting 3│
   │Research │      │Research │      │Research │
   └────┬────┘      └────┬────┘      └────┬────┘
        │                │                │
        ▼                ▼                ▼
   ┌─────────┐      ┌─────────┐      ┌─────────┐
   │ Brief 1 │      │ Brief 2 │      │ Brief 3 │
   └────┬────┘      └────┬────┘      └────┬────┘
        │                │                │
        └────────────────┼────────────────┘
                         │
                         ▼
                  ┌─────────────┐
                  │ Batch Email │
                  └─────────────┘
```

**Concurrency Limit:** 3 parallel researches (API rate limiting)

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Brief Delivery Time | By 8:30 PM (30 min after trigger) |
| Brief Quality Score | > 80% |
| Delivery Success Rate | > 95% |
| AE Open Rate | > 90% |
| On-Time Delivery | > 98% |

---

## Failure Handling

| Scenario | Action |
|----------|--------|
| Research API timeout | Use cached data + flag |
| No meetings tomorrow | Log, no action needed |
| Quality < 80% | Regenerate (max 2 attempts) |
| Delivery fails | Retry via alternate channel |
| All retries fail | Alert AE directly |

---

## Configuration

### Environment Variables
```env
MEETING_PREP_TRIGGER_HOUR=20  # 8 PM
MIN_BRIEF_QUALITY_SCORE=80
MAX_RESEARCH_TIME_SEC=60
BRIEF_CACHE_DAYS=7
NEWS_CACHE_DAYS=1
```

### AE Notification Settings
```json
{
  "notification_preferences": {
    "email": true,
    "slack": true,
    "sms": false,
    "delivery_time": "20:15"
  }
}
```
