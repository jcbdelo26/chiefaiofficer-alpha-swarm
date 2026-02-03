# Cold/Warm Lead Routing Architecture

## Overview

Context-aware lead routing system that automatically directs leads to the optimal outreach platform based on engagement signals and behavioral analysis.

| Platform | Use Case | Lead Type |
|----------|----------|-----------|
| **Instantly** | Cold outbound sequences | No prior engagement |
| **GoHighLevel** | Warm nurture & pipeline | Prior engagement detected |

---

## Engagement Classification

### Scoring Weights

| Signal | Points | Description |
|--------|--------|-------------|
| Meeting completed | 80 | Highest intent signal |
| Requested contact | 70 | Inbound intent |
| Meeting booked | 60 | Active interest |
| Form submitted | 55 | Direct engagement |
| Email reply | 50 | Two-way communication |
| LinkedIn message received | 45 | Active response |
| LinkedIn connected | 40 | Relationship established |
| Downloaded content | 25 | Interest in offerings |
| Email clicked | 20 | Engaged with content |
| RB2B identified | 15 | Website visitor |
| Email opened | 10 | Passive engagement |
| Website visit | 8 | Awareness signal |

### Engagement Levels

| Level | Score Range | Platform | Action |
|-------|-------------|----------|--------|
| **COLD** | 0-14 | Instantly | Cold outbound sequence |
| **LUKEWARM** | 15-39 | Hybrid | Start cold, monitor closely |
| **WARM** | 40-69 | GoHighLevel | Nurture sequence |
| **HOT** | 70+ | GoHighLevel | Priority pipeline, immediate follow-up |

---

## Routing Logic

```
┌─────────────────────────────────────────────────────────────────┐
│                      NEW LEAD ENTERS                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              FETCH ENGAGEMENT SIGNALS                           │
│  - Supabase (leads, outcomes, engagement_signals)               │
│  - GoHighLevel (contact activity)                               │
│  - Instantly (campaign stats)                                   │
│  - LinkedIn (connection status)                                 │
│  - RB2B (website visits)                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              CALCULATE ENGAGEMENT SCORE                         │
│  - Apply signal weights                                         │
│  - Apply recency decay (signals > 30 days weighted less)        │
│  - Sum total score                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              CLASSIFY ENGAGEMENT LEVEL                          │
│  COLD (0-14) │ LUKEWARM (15-39) │ WARM (40-69) │ HOT (70+)      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
         ┌────────────────────┴────────────────────┐
         │                                          │
    COLD/LUKEWARM                              WARM/HOT
         │                                          │
         ▼                                          ▼
┌─────────────────────┐                ┌─────────────────────┐
│     INSTANTLY       │                │    GOHIGHLEVEL      │
│ ─────────────────── │                │ ─────────────────── │
│ • Cold sequences    │                │ • Nurture workflows │
│ • Email warmup      │                │ • SMS follow-up     │
│ • Inbox rotation    │                │ • Pipeline tracking │
│ • Deliverability    │                │ • Meeting booking   │
└─────────────────────┘                └─────────────────────┘
         │                                          │
         │ ◄──── TRANSITION TRIGGERS ────►          │
         │  • Email reply received                  │
         │  • Meeting booked                        │
         │  • Form submitted                        │
         │  • 3+ opens in 7 days                    │
         │  • Requested contact                     │
         └──────────────────────────────────────────┘
```

---

## Transition Triggers

Leads automatically transition from Instantly → GoHighLevel when:

| Trigger | Priority | Description |
|---------|----------|-------------|
| Email reply | HIGH | Two-way communication established |
| Meeting booked | HIGH | Clear buying intent |
| Form submitted | HIGH | Direct engagement action |
| Requested contact | HIGH | Inbound intent signal |
| 3+ opens in 7 days | MEDIUM | High engagement pattern |
| Score reaches 40+ | MEDIUM | Accumulated signals |

---

## Database Schema

### engagement_signals table
Tracks aggregated engagement metrics per lead:
- Email signals (sent, opened, clicked, replied)
- LinkedIn signals (connected, messages)
- Website signals (visits, pages, RB2B)
- CRM signals (stage, meetings, forms)
- Routing state (current platform, score, level)

### engagement_events table
Event log for individual engagement actions:
- Enables audit trail
- Supports recency calculations
- Tracks signal sources

### platform_transitions table
Records lead movements between platforms:
- From/to platform
- Trigger event
- Score at transition
- Routing decision snapshot

---

## Implementation Files

| File | Purpose |
|------|---------|
| `core/lead_router.py` | Main routing engine |
| `mcp-servers/supabase-mcp/schema_engagement_signals.sql` | Database schema |
| `execution/sync_engagement_signals.py` | Signal aggregation job |

---

## Usage

```python
from core.lead_router import LeadRouter, EngagementSignals

router = LeadRouter(supabase_client=supabase)

# Route a new lead
signals = EngagementSignals(
    emails_sent=3,
    emails_opened=2,
    linkedin_connected=True,
)

decision = router.route_lead(signals)
# decision.platform = OutreachPlatform.GOHIGHLEVEL
# decision.engagement_level = EngagementLevel.WARM
# decision.reasoning = ["Warm engagement - route to GHL..."]
```

---

## Next Steps

1. [ ] Run `schema_engagement_signals.sql` in Supabase SQL Editor
2. [ ] Configure Instantly API key in `.env`
3. [ ] Configure GoHighLevel API key in `.env`
4. [ ] Create sync job to aggregate signals from both platforms
5. [ ] Set up webhook handlers for real-time signal updates
