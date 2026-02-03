---
description: End-to-end workflow from lead generation to booked meeting with all 12 agent handoffs
triggers:
  - type: webhook
    source: linkedin_scrape_complete
  - type: manual
    command: /lead-to-meeting
agents:
  - HUNTER
  - ENRICHER
  - SEGMENTOR
  - CRAFTER
  - GATEKEEPER
  - COMMUNICATOR
  - SCHEDULER
  - RESEARCHER
---

# Unified Lead-to-Meeting Workflow

## Overview
This workflow orchestrates the complete journey from identifying a LinkedIn prospect to booking a qualified meeting with them. It coordinates all 12 agents through a deterministic handoff sequence with built-in guardrails.

## Prerequisites
- [ ] Google Calendar MCP configured (`mcp-servers/google-calendar-mcp/`)
- [ ] Email Threading MCP configured (`mcp-servers/email-threading-mcp/`)
- [ ] GHL MCP authenticated (`mcp-servers/ghl-mcp/`)
- [ ] Clay enrichment API key in `.env`

---

## Workflow Steps

### Phase 1: Lead Generation (LEAD_GEN Swarm)

// turbo-all

#### Step 1: HUNTER Scrapes LinkedIn Source
```bash
python execution/hunter_scrape_followers.py --url "$LINKEDIN_URL" --limit 50
```
**Success Criteria:**
- Raw profile data saved to `.hive-mind/scraped/`
- Minimum 10 profiles extracted
- No duplicate records

**Handoff:** → ENRICHER

---

#### Step 2: ENRICHER Adds Contact/Company Data
```bash
python execution/enricher_clay_waterfall.py --input ".hive-mind/scraped/$BATCH_ID.json"
```
**Success Criteria:**
- Email found for >70% of profiles
- Company data enriched (size, industry, revenue)
- Tech stack detected where available
- Saved to `.hive-mind/enriched/`

**Handoff:** → SEGMENTOR

---

#### Step 3: SEGMENTOR Classifies and Scores
```bash
python execution/segmentor_agent.py --input ".hive-mind/enriched/$BATCH_ID.json"
```
**Scoring Criteria (ICP Match):**
| Factor | Weight | Criteria |
|--------|--------|----------|
| Company Size | 25% | 51-500 employees |
| Industry | 20% | B2B SaaS, Technology, Professional Services |
| Revenue | 20% | $5M - $100M ARR |
| Title | 25% | VP Sales, VP Revenue, CRO, RevOps Director |
| Tech Stack | 10% | Salesforce/HubSpot + looking for AI |

**Tier Assignment:**
- **Tier 1**: Score >= 80 (high-touch, personalized)
- **Tier 2**: Score >= 60 (standard outreach)
- **Tier 3**: Score >= 40 (nurture sequence)
- **Disqualified**: Score < 40 or exclusion criteria match

**Disqualification Triggers:**
- Company < 20 employees
- Agency/consultancy (unless enterprise)
- Already a customer
- Previously unsubscribed

**Handoff:** → CRAFTER (for qualified leads)

---

### Phase 2: Campaign Creation

#### Step 4: CRAFTER Generates Personalized Campaign
```bash
python execution/crafter_campaign.py --segment "tier1_$BATCH_ID" --template "cold_outreach"
```
**Requirements:**
- Match Head of Sales tone (>85% similarity via `directives/scheduling/tone_matching.md`)
- Personalize with company-specific pain points
- Include clear CTA for scheduling

**Output:**
- Initial outreach email
- 3-email follow-up sequence
- Saved to `.hive-mind/campaigns/`

**Handoff:** → GATEKEEPER

---

### Phase 3: Approval Gate

#### Step 5: GATEKEEPER Reviews and Approves
```bash
python execution/gatekeeper_review.py --campaign "$CAMPAIGN_ID"
```
**Auto-Approve Conditions:**
- Template match >90%
- No pricing/contract mentions
- No legal commitments
- Standard follow-up sequence

**Manual Review Required:**
- Custom messaging
- High-value Tier 1 leads
- Any modified templates

**Approval Channels (Priority Order):**
1. Slack DM to Head of Sales
2. SMS for urgent (30-min timeout)
3. Email fallback (2-hour timeout)

**Timeout Handling:**
- After timeout → escalate to secondary approver
- Log escalation reason

**Handoff:** → COMMUNICATOR (if approved)

---

### Phase 4: Outreach Execution

#### Step 6: COMMUNICATOR Sends Outreach
```bash
python execution/communicator_send.py --campaign "$CAMPAIGN_ID" --approved
```
**Guardrails:**
- Rate limit: 5 emails/domain/hour
- CAN-SPAM compliance check
- Working unsubscribe link
- Thread preservation (In-Reply-To headers)

**Handoff:** → WAIT for response

---

### Phase 5: Response Handling (Trigger: Response Received)

#### Step 7: COMMUNICATOR Detects Scheduling Intent
```bash
python mcp-servers/email-threading-mcp/tools/detect_intent.py --email "$EMAIL_ID"
```
**Intent Classification:**
| Intent | Action |
|--------|--------|
| `scheduling_request` | → SCHEDULER |
| `question` | → COMMUNICATOR (follow-up) |
| `objection` | → COMMUNICATOR (objection handling) |
| `acceptance` | → SCHEDULER |
| `rejection` | Log + end sequence |
| `information_request` | → RESEARCHER + COMMUNICATOR |

**Handoff:** → Agent per intent

---

### Phase 6: Scheduling

#### Step 8: SCHEDULER Checks Calendar Availability
```bash
python execution/scheduler_agent.py --action "check_availability" --prospect_tz "$TZ"
```
**Working Hours:** 9 AM - 6 PM (prospect's timezone)
**Buffer:** Minimum 15-min between meetings
**Lookahead:** Next 10 business days

**Handoff:** → COMMUNICATOR

---

#### Step 9: COMMUNICATOR Proposes Meeting Times
```bash
python execution/communicator_respond.py --intent "scheduling" --times "$AVAILABLE_TIMES"
```
**Proposal Format:**
- 3-5 time options
- Times in prospect's timezone
- Clear format: "Monday, January 27th at 2:00 PM PST"

**Exchange Tracking:**
- Max 5 scheduling exchanges
- After 5 → escalate to human

**Handoff:** → GATEKEEPER

---

#### Step 10: GATEKEEPER Approves Scheduling Email
```bash
python execution/gatekeeper_review.py --action "scheduling_response" --email "$DRAFT_ID"
```
**Smart Approval:**
- Auto-approve if template match >90%
- Manual if custom times requested

**Handoff:** → SCHEDULER (if time confirmed)

---

#### Step 11: SCHEDULER Creates Calendar Invite
```bash
python execution/scheduler_agent.py --action "create_event" \
  --title "Discovery Call: $COMPANY - ChiefAIOfficer" \
  --attendees "$PROSPECT_EMAIL" \
  --duration "30" \
  --zoom "true"
```
**Guardrails:**
- Double-booking prevention (mutex lock)
- Zoom link auto-generation
- GHL contact update with meeting info
- Trigger RESEARCHER for brief generation

**Handoff:** → RESEARCHER

---

### Phase 7: Meeting Preparation

#### Step 12: RESEARCHER Schedules Brief Generation
```bash
python execution/researcher_agent.py --schedule "8pm_night_before" --meeting "$MEETING_ID"
```
**Brief Delivery:**
- Generated at 8 PM night before meeting
- Emailed to AE
- Saved to `.hive-mind/researcher/briefs/`

**Handoff:** → QUEEN (outcome update)

---

### Phase 8: Learning Loop

#### Step 13: QUEEN Updates ReasoningBank
```bash
python execution/unified_queen_orchestrator.py --update_learning \
  --workflow "lead_to_meeting" \
  --lead_id "$LEAD_ID" \
  --outcome "$OUTCOME"
```
**Tracked Metrics:**
- Time from first contact to meeting
- Number of email exchanges
- Scheduling attempts
- Meeting show rate

**Self-Annealing:**
- Log patterns to `.hive-mind/reasoning_bank.json`
- Update Q-learning values
- Refine future routing decisions

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Time to First Response | < 24 hours |
| Emails to Book Meeting | < 2 |
| Meeting Show Rate | > 90% |
| GATEKEEPER Approval Rate | > 90% |
| Scheduling Accuracy (no double-books) | 100% |
| Timezone Conversion Accuracy | 100% |

---

## Failure Handling

| Scenario | Action |
|----------|--------|
| Enrichment fails | Retry with alternate provider |
| Email bounces | Mark invalid, remove from sequence |
| No response after 3 follow-ups | Move to nurture list |
| Scheduling > 5 exchanges | Escalate to human |
| Calendar conflict | Propose alternate times |
| Meeting no-show | Trigger re-engagement sequence |

---

## Audit Trail
All actions logged to:
- `core/audit_trail.py` → `.hive-mind/audit.db`
- JSON backup daily
- 90-day retention
