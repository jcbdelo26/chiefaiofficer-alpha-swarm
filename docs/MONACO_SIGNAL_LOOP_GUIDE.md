# Monaco-Inspired Signal Loop — Task Guide

**Created**: 2026-02-16
**Source**: [Monaco.com](https://www.monaco.com) product research + CAIO Alpha Swarm Phase 4F
**Plan Reference**: `CAIO_IMPLEMENTATION_PLAN.md` v3.6, Phase 4F

---

## What Was Built

The Monaco research identified that the #1 architectural gap in CAIO was a **linear pipeline** (scrape → send → done) vs. Monaco's **feedback loop** (scrape → send → engagement signals → re-score → next action). We built the feedback loop.

### New Files Created

| File | Purpose |
|------|---------|
| `core/lead_signals.py` | Lead status management + engagement signal handlers + ghosting/stall detection |
| `core/activity_timeline.py` | Unified per-lead activity aggregation across all channels |
| `dashboard/leads_dashboard.html` | Pipeline flow visualization + filterable lead list + timeline modal |

### Files Modified

| File | Change |
|------|--------|
| `execution/segmentor_classify.py` | Added `scoring_reasons` field — human-readable "Why This Score" explanations |
| `dashboard/health_app.py` | Added 6 new API endpoints for leads, funnel, timeline, decay detection |
| `CAIO_IMPLEMENTATION_PLAN.md` | Added Phase 4F section with Monaco-inspired improvements |

---

## How It Works

### Lead Status Progression

```
PIPELINE                    OUTREACH                 ENGAGEMENT
pending ──► approved ──► dispatched ──► sent ──► opened ──► replied ──► meeting_booked
   │                                      │          │
   ▼                                      ▼          ▼
 rejected                              ghosted    stalled
                                       (72h)      (7 days)
                                                     │
                                                     ▼
                                              engaged_not_replied
                                              (2+ opens, 0 replies)

TERMINAL: bounced | unsubscribed | disqualified

LINKEDIN: linkedin_sent → linkedin_connected → linkedin_replied
                                                    │
                                              linkedin_exhausted
```

### Signal Sources

| Source | Events | Updates Lead Status |
|--------|--------|-------------------|
| **Instantly Webhooks** | open, reply, bounce, unsubscribe | `handle_email_opened()`, `handle_email_replied()`, etc. |
| **HeyReach Webhooks** | connection_sent/accepted, message_reply | `handle_linkedin_*()` methods |
| **Time-based Rules** | ghosting (72h), stalling (7d) | `detect_engagement_decay()` |
| **Pipeline** | segmentation, campaign creation | Via events.jsonl |

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/leads` | GET | List all leads with current status |
| `/api/leads/funnel` | GET | Pipeline funnel counts for visualization |
| `/api/leads/status-summary` | GET | Count of leads by status |
| `/api/leads/{email}/timeline` | GET | Unified activity timeline for one lead |
| `/api/leads/detect-decay` | POST | Run ghosting/stall detection scan |
| `/api/leads/bootstrap` | POST | Seed lead status records from shadow emails |
| `/leads` | GET | Serve the Lead Signal Loop dashboard |

---

## Your Task Guide (Step-by-Step)

### DONE (Already Built)

- [x] `core/lead_signals.py` — LeadStatusManager with 18 status types
- [x] `core/activity_timeline.py` — ActivityTimeline aggregator
- [x] `execution/segmentor_classify.py` — scoring_reasons added to SegmentedLead
- [x] `dashboard/health_app.py` — 6 new API endpoints + /leads route
- [x] `dashboard/leads_dashboard.html` — Full dashboard with pipeline flow, lead list, timeline modal
- [x] `CAIO_IMPLEMENTATION_PLAN.md` — Phase 4F documented

### TO DO (When You're Ready)

#### Step 1: Bootstrap Lead Data (5 minutes)

After deploying to Railway, visit:
```
https://caio-swarm-dashboard-production.up.railway.app/leads
```

Click **"Bootstrap Leads"** to seed lead status records from your existing shadow emails. This creates one status file per lead in `.hive-mind/lead_status/`.

#### Step 2: Wire Signal Loop into Instantly Webhooks

When Instantly webhooks fire (reply, open, bounce, unsub), they should update lead status. This requires a small addition to `webhooks/instantly_webhook.py`:

In each event handler, add a call to LeadStatusManager:

```python
# At top of file:
from core.lead_signals import LeadStatusManager
_lead_mgr = LeadStatusManager()

# In reply handler:
_lead_mgr.handle_email_replied(lead_email, reply_text, campaign_id)

# In open handler:
_lead_mgr.handle_email_opened(lead_email, campaign_id)

# In bounce handler:
_lead_mgr.handle_email_bounced(lead_email, bounce_type)

# In unsubscribe handler:
_lead_mgr.handle_email_unsubscribed(lead_email)
```

**When to do this**: Before or during Phase 4E (Supervised Live Sends). The signal loop only generates value when real emails are being sent and engagement data flows back.

#### Step 3: Wire Signal Loop into HeyReach Webhooks

Same pattern as Step 2, but for `webhooks/heyreach_webhook.py`:

```python
from core.lead_signals import LeadStatusManager
_lead_mgr = LeadStatusManager()

# In connection_accepted handler:
_lead_mgr.handle_linkedin_connection_accepted(linkedin_url, email)

# In message_reply handler:
_lead_mgr.handle_linkedin_reply(linkedin_url, message_text, email)
```

**When to do this**: After HeyReach subscription is active and webhooks are registered.

#### Step 4: Run Decay Detection Periodically

The decay scan checks for ghosted (72h) and stalled (7d) leads. You can:

1. **Manual**: Click "Run Decay Scan" on the `/leads` dashboard
2. **Scheduled**: Add to Inngest as a daily function (recommended once live)

#### Step 5: Use Scoring Reasons for Better Approvals

When reviewing emails in the Head of Sales dashboard (`/sales`), you can now understand **why** each lead was scored the way it was. The `scoring_reasons` field is available in the lead data.

Example output:
```
+20: Company size 150 employees (ideal 51-500 sweet spot)
+22: VP-level title "VP of Sales" (budget influencer)
+20: Industry "Computer Software" is core ICP (B2B SaaS/Software)
+8: Tech stack signals — crm_user (sales maturity indicator)
+0: No behavioral intent signals detected
= 70/100 total ICP score
```

---

## Monaco Features: Adopted vs. Deferred vs. Rejected

### Adopted (BUILT)
| Monaco Feature | CAIO Implementation |
|----------------|-------------------|
| Signal-based pipeline progression | LeadStatusManager — engagement drives status |
| Self-maintaining CRM records | Webhooks auto-update lead status files |
| Explainable scoring ("Why this account") | `scoring_reasons` in segmentor output |
| Unified activity capture | ActivityTimeline aggregates all channels |
| Pipeline funnel visualization | 5-stage flow on /leads dashboard |
| Human-guided agents | Gatekeeper approval gate (already existed) |

### Deferred (Phase 5+)
| Feature | Trigger |
|---------|---------|
| CRO Copilot ("Ask Monaco" chat) | When lead volume exceeds 500+ |
| Meeting Intelligence (auto note-taking) | When phone outreach goes live (Phase 4D) |
| Multi-source intent fusion (RB2B + email + LinkedIn) | 30 days of send data (Phase 5B) |
| A/B testing infrastructure | Real send data needed first (Phase 5B) |

### Rejected (Not Doing)
| Feature | Reason |
|---------|--------|
| Proprietary prospect database | We rent Apollo — correct at our scale |
| Custom CRM | GHL works, "Rent the Pipes" |
| Replace RB2B with custom pixel | IP-to-identity is proprietary tech |

---

## Architecture Diagram

```
                    ┌─────────────────────────────────┐
                    │   6-STAGE PIPELINE (existing)     │
                    │ Scrape → Enrich → Segment →       │
                    │ Craft → Approve → Send             │
                    └────────────┬────────────────────┘
                                 │
                    ┌────────────▼────────────────────┐
                    │   SHADOW QUEUE (.hive-mind/)      │
                    │   Shadow emails + dispatch logs    │
                    └────────────┬────────────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                     │
    ┌───────▼───────┐   ┌───────▼───────┐   ┌────────▼──────┐
    │   Instantly     │   │   HeyReach    │   │    GHL         │
    │   (Email)       │   │  (LinkedIn)   │   │   (Nurture)    │
    └───────┬───────┘   └───────┬───────┘   └────────────────┘
            │                    │
    ┌───────▼───────┐   ┌───────▼───────┐
    │   Webhooks     │   │   Webhooks     │
    │ open/reply/    │   │ connect/reply/ │
    │ bounce/unsub   │   │ campaign done  │
    └───────┬───────┘   └───────┬───────┘
            │                    │
            └────────┬───────────┘
                     │
         ┌───────────▼────────────────┐  ◄── NEW (Phase 4F)
         │   LEAD SIGNAL LOOP          │
         │   core/lead_signals.py      │
         │                             │
         │  Status updates:            │
         │  opened, replied, ghosted,  │
         │  stalled, connected...      │
         │                             │
         │  Decay detection:           │
         │  72h ghost, 7d stall        │
         └───────────┬────────────────┘
                     │
         ┌───────────▼────────────────┐  ◄── NEW (Phase 4F)
         │   ACTIVITY TIMELINE         │
         │   core/activity_timeline.py │
         │                             │
         │  Aggregates ALL sources     │
         │  into per-lead timeline     │
         └───────────┬────────────────┘
                     │
         ┌───────────▼────────────────┐  ◄── NEW (Phase 4F)
         │   LEADS DASHBOARD           │
         │   /leads                    │
         │                             │
         │  Pipeline flow (5 stages)   │
         │  Lead list (filterable)     │
         │  Click → Timeline modal     │
         │  + "Why This Score"         │
         └────────────────────────────┘
```

---

## Key Metrics to Watch (Once Live)

| Metric | What It Tells You | Dashboard Location |
|--------|-------------------|-------------------|
| Funnel drop-off | Where leads stall in the pipeline | `/leads` pipeline flow |
| Ghost rate | % of emails never opened | `/leads` → filter "Ghosted" |
| Stall rate | % of opens that never reply | `/leads` → filter "Stalled" |
| Engaged-not-replied | Interested but hesitant leads | `/leads` → filter candidates for follow-up |
| Open → Reply conversion | Outreach quality metric | `/leads` funnel numbers |
| Time-to-first-open | Delivery + subject line quality | Lead timeline events |
