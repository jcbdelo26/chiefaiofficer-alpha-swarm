---
description: Automated pipeline monitoring every 15 minutes with scheduling integration
triggers:
  - type: cron
    schedule: "*/15 6-20 * * 1-5"  # Every 15 min, 6 AM - 8 PM, Mon-Fri
  - type: manual
    command: /pipeline-scan
agents:
  - SCOUT
  - COACH
  - OPERATOR
  - COMMUNICATOR
  - GATEKEEPER
  - SCHEDULER
  - QUEEN
---

# Unified Pipeline Scan Workflow

## Overview
This workflow continuously monitors the GHL pipeline for warm leads, stale deals, and scheduling opportunities. It runs every 15 minutes during business hours to ensure no opportunities slip through the cracks.

## Prerequisites
- [ ] GHL MCP authenticated (`mcp-servers/ghl-mcp/`)
- [ ] Pipeline stages configured in GHL
- [ ] Email Threading MCP for response detection

---

## Trigger Configuration

### Cron Schedule
```yaml
schedule: "*/15 6-20 * * 1-5"
# Translation: Every 15 minutes, 6 AM - 8 PM (Manila Time), Monday - Friday
```

### Rate Limiting
- Max 40 scans/day (prevent API abuse)
- Minimum 15-min between scans
- Skip if previous scan still running

---

## Workflow Steps

// turbo-all

### Step 1: SCOUT Scans GHL Pipeline for Warm Leads
```bash
python execution/scout_pipeline_scan.py --status "active" --last_activity "7d"
```

**Scan Criteria:**
| Stage | Priority | Action Trigger |
|-------|----------|----------------|
| Lead | Low | No action if < 24h old |
| Qualified | Medium | Check for follow-up need |
| Demo Scheduled | High | Verify meeting confirmed |
| Proposal Sent | High | Check for response |
| Negotiation | Critical | Monitor daily |

**Output:**
- Lead list with engagement scores
- Last activity timestamps
- Current pipeline stage
- Saved to `.tmp/pipeline_snapshot_$TIMESTAMP.json`

**Handoff:** → COACH

---

### Step 2: COACH Scores Leads by Engagement/Intent
```bash
python execution/coach_lead_scoring.py --input ".tmp/pipeline_snapshot_$TIMESTAMP.json"
```

**Scoring Factors:**
| Factor | Weight | Description |
|--------|--------|-------------|
| Email Opens | 15% | # opens in last 7 days |
| Link Clicks | 20% | Engagement with content |
| Reply Recency | 25% | Time since last reply |
| Website Visits | 15% | RB2B tracking data |
| Meeting History | 25% | Past meetings/no-shows |

**Priority Classification:**
- **HOT (Score > 80)**: Immediate follow-up needed
- **WARM (Score 50-80)**: Schedule follow-up within 24h
- **COOL (Score 30-50)**: Standard nurture cadence
- **COLD (Score < 30)**: Re-engagement sequence or archive

**Handoff:** → Step 3 (Ghost Detection) + Step 4 (Parallel Actions)

---

### Step 3: COACH Identifies Ghost Deals
```bash
python execution/coach_ghost_detection.py --stale_days 7
```

**Ghost Deal Criteria:**
- No activity for 7+ days
- Was previously engaged (>2 touches)
- Not explicitly rejected
- In stages: Qualified, Demo Scheduled, Proposal Sent

**Ghost Categories:**
| Type | Days Stale | Action |
|------|------------|--------|
| Early Ghost | 7-14 days | Light re-engagement |
| Deep Ghost | 14-30 days | Pattern-break message |
| Cold Ghost | 30+ days | Archive or final attempt |

**Output:** Ghost deal list with recommended action

**Handoff:** → OPERATOR (for ghost revival)

---

### Step 4: Parallel Processing Block

Execute simultaneously:

#### 4a: COMMUNICATOR Drafts Follow-ups for Warm Leads
```bash
python execution/communicator_draft.py --priority "HOT,WARM" --action "follow_up"
```

**Draft Requirements:**
- Reference last interaction
- Add value (insight, resource, case study)
- Clear CTA
- Match tone style (>85%)

**Handoff:** → GATEKEEPER

#### 4b: OPERATOR Triggers Ghostbuster Sequences
```bash
python execution/operator_ghostbuster.py --ghost_list ".tmp/ghost_deals_$TIMESTAMP.json"
```

**Ghostbuster Sequence:**
1. Day 0: Pattern-break email (unexpected value)
2. Day 3: "Last touch" with FOMO element
3. Day 7: Final "closing the loop" message

**Success Metric:** 15% ghost revival rate

**Handoff:** → GATEKEEPER

---

### Step 5: GATEKEEPER Batch-Approves Communications
```bash
python execution/gatekeeper_batch.py --queue ".tmp/pending_comms_$TIMESTAMP.json"
```

**Batch Approval Rules:**
| Type | Auto-Approve Threshold |
|------|------------------------|
| Follow-up (template) | >90% match |
| Ghostbuster sequence | >85% match |
| Custom message | Always manual |
| Pricing/terms | Always manual |

**Timeout:** 30 minutes for batch, then send approved items

**Output:**
- Approved communications → COMMUNICATOR
- Rejected/edited → Back to CRAFTER
- Pending → Wait in queue

**Handoff:** → SCHEDULER (for responses)

---

### Step 6: SCHEDULER Monitors Responses for Scheduling Intent
```bash
python execution/scheduler_agent.py --monitor_responses --since "$LAST_SCAN_TIME"
```

**Response Monitoring:**
- Check all inbound emails since last scan
- Parse for scheduling keywords/intent
- Detect confirmed times in responses
- Check calendar for conflicts

**Scheduling Intent Signals:**
- "Let's schedule a call"
- "I'm free on..."
- "How about [time]?"
- Calendar link clicked
- Accept/propose time response

**Actions on Detection:**
| Intent | Action |
|--------|--------|
| Time proposed by prospect | Confirm & book |
| Request for options | Generate availability |
| Confirmed booking | Create calendar event |
| Reschedule request | Update event |
| Cancellation | Mark & trigger re-engagement |

**Handoff:** → QUEEN (for logging)

---

### Step 7: QUEEN Logs Metrics to ReasoningBank
```bash
python execution/unified_queen_orchestrator.py --log_scan_metrics \
  --scan_id "$SCAN_ID" \
  --leads_processed "$COUNT" \
  --actions_taken "$ACTIONS"
```

**Logged Metrics:**
| Metric | Description |
|--------|-------------|
| `leads_scanned` | Total leads in pipeline |
| `hot_leads` | Leads scoring > 80 |
| `ghost_deals` | Deals 7+ days stale |
| `follow_ups_sent` | Communications approved & sent |
| `meetings_detected` | Scheduling intents found |
| `scan_duration_ms` | Processing time |

**Self-Annealing Updates:**
- Adjust scoring weights based on conversion rates
- Refine ghost detection thresholds
- Update template effectiveness scores

---

## Parallel Execution Diagram

```
                    ┌────────────┐
                    │   SCOUT    │
                    │ (Pipeline) │
                    └─────┬──────┘
                          │
                          ▼
                    ┌────────────┐
                    │   COACH    │
                    │ (Scoring)  │
                    └─────┬──────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
    ┌───────────┐   ┌───────────┐   ┌───────────┐
    │   COACH   │   │COMMUNICATOR│  │  OPERATOR │
    │ (Ghosts)  │   │ (Drafts)   │  │(Ghostbust)│
    └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
          │               │               │
          └───────────────┼───────────────┘
                          │
                          ▼
                    ┌────────────┐
                    │ GATEKEEPER │
                    │  (Batch)   │
                    └─────┬──────┘
                          │
                          ▼
                    ┌────────────┐
                    │ SCHEDULER  │
                    │ (Monitor)  │
                    └─────┬──────┘
                          │
                          ▼
                    ┌────────────┐
                    │   QUEEN    │
                    │ (Logging)  │
                    └────────────┘
```

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Scan Completion Time | < 2 minutes |
| Warm Lead Follow-up | Within 24 hours |
| Ghost Deal Detection | > 95% accuracy |
| Ghost Revival Rate | > 15% |
| False Positive (Ghost) | < 5% |
| Scheduling Intent Detection | > 90% accuracy |

---

## Failure Handling

| Scenario | Action |
|----------|--------|
| GHL API timeout | Retry with backoff (3x) |
| Scan takes > 5 min | Abort, log, alert |
| Previous scan running | Skip this cycle |
| GATEKEEPER timeout | Auto-approve templates, hold custom |
| Rate limit hit | Pause 1 hour, resume |

---

## Dashboard Metrics

View real-time at: `http://localhost:8501/pipeline`

```python
# Key dashboard widgets
- Pipeline funnel visualization
- Lead velocity (leads/stage/time)
- Ghost deal heatmap
- Follow-up queue depth
- Meeting conversion rate
```

---

## Configuration

### Environment Variables
```env
PIPELINE_SCAN_INTERVAL=15  # minutes
GHOST_THRESHOLD_DAYS=7
HOT_LEAD_THRESHOLD=80
WARM_LEAD_THRESHOLD=50
MAX_SCANS_PER_DAY=40
```

### GHL Stage Mapping
```json
{
  "stages": {
    "new_lead": {"priority": 1, "action": "qualify"},
    "qualified": {"priority": 2, "action": "nurture"},
    "demo_scheduled": {"priority": 3, "action": "confirm"},
    "proposal_sent": {"priority": 4, "action": "follow_up"},
    "negotiation": {"priority": 5, "action": "close"}
  }
}
```
