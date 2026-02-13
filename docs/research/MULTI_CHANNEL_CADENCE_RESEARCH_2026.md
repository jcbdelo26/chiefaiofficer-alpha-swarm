# Multi-Channel Outreach Cadence Architecture for CAIO Alpha Swarm

**Status**: COMPLETE
**Date**: 2026-02-13
**Purpose**: Research multi-channel SDR cadence options to expand beyond email-only outreach
**Author**: Claude Code research agents

---

## Executive Summary

Researched 9+ LinkedIn automation and multi-channel tools. The recommended approach is **HeyReach + Instantly.ai** — native bidirectional integration, full API/webhooks on all plans, cloud-based safety with sender rotation. Multi-channel sequences using 3+ channels achieve ~287% higher purchase rates than single-channel.

### Top Recommendations

| Rank | Tool | Type | Pricing | API | Instantly Integration |
|------|------|------|---------|-----|----------------------|
| 1 | **HeyReach** | LinkedIn automation + sender rotation | $79/mo/sender ($59 annual) | Full REST API + 20+ webhooks | **Native bidirectional** |
| 2 | **Lemlist** | Multi-channel (email + LI + WhatsApp) | $99/user/mo (Expert) | Full REST API (18 categories) | No (replaces Instantly) |
| 3 | **La Growth Machine** | Multi-channel (email + LI + Twitter) | EUR 120/mo/identity | Partial API | No |

---

## 1. Multi-Channel Cadence Best Practices

### Channels a Modern B2B SDR Cadence Should Include

| Channel | Role | Share of Touchpoints |
|---------|------|---------------------|
| **Email** | Primary — scalable, trackable, automatable | 40-50% |
| **LinkedIn** | Social proof, warm connection, personal touch | 15-25% |
| **Phone/Cold Call** | High-intent signal, urgency driver | 20-30% |
| **SMS/WhatsApp** | Emerging channel with 90%+ open rates | 5-10% |
| **Video (Loom/Vidyard)** | Differentiation, best mid-sequence | 5-10% |

### Optimal 21-Day Multi-Channel Cadence Template

```
Day 1:   Email #1    — Personalized intro (reference news, funding, pain point)
Day 2:   LinkedIn    — Connection request with short personalized note
Day 3:   Phone       — Call attempt #1 + voicemail
Day 5:   Email #2    — Value-focused (case study, ROI stat, industry insight)
Day 7:   LinkedIn    — Message (if connected) or engage with content (like/comment)
Day 9:   Phone       — Call attempt #2
Day 10:  Email #3    — Social proof / testimonial from similar company
Day 14:  LinkedIn    — Voice message or InMail (if not connected)
Day 17:  Email #4    — "Break-up" / last chance framing
Day 19:  Phone       — Final call attempt
Day 21:  Email #5    — Graceful close with door left open
```

### Key Timing Rules
- **Best email days**: Tuesday and Thursday (highest open rates)
- **Best email times**: 9-10 AM and 1 PM in prospect's local timezone
- **LinkedIn timing**: Space actions across 9 AM - 6 PM with 45-120s random delays
- **Total touchpoints**: 8-12 across 15-21 business days (sweet spot)
- **Quick follow-ups**: Message immediately after LinkedIn connection accepted = 2x response rate

---

## 2. LinkedIn Automation Tools — Detailed Comparison

### HeyReach — RECOMMENDED

| Attribute | Detail |
|-----------|--------|
| Type | Cloud-based LinkedIn automation with sender rotation |
| Pricing | Growth: $79/mo/sender ($59 annual). Agency: $999/mo (50 senders). |
| API | Full REST API + 20+ webhook event types on **all plans** |
| Instantly integration | **Native bidirectional** — leads sync both directions |
| Safety | Cloud-based, dedicated IPs, sender rotation reduces per-account risk |
| CRM | HubSpot, Pipedrive, Clay, RB2B, Make, Zapier |

### Expandi

| Attribute | Detail |
|-----------|--------|
| Type | Cloud-based LinkedIn + email automation |
| Pricing | $99/mo/seat ($79 annual) |
| API | No public REST API. Webhooks only for campaign events |
| Safety | Industry-leading anti-detection (full browser simulation, dedicated IP) |
| Limitation | Per-account pricing, no native Instantly integration |

### Lemlist — Strong Alternative

| Attribute | Detail |
|-----------|--------|
| Type | Multi-channel (email + LinkedIn + WhatsApp + calls) |
| Pricing | Multichannel Expert: $99/user/mo (required for LinkedIn) |
| API | Full REST API at `api.lemlist.com/api` (18 endpoint categories) |
| Webhooks | emailsSent, emailsOpened, emailsReplied, linkedinInterested, etc. |
| Limitation | Replaces Instantly (not complementary), credits don't roll over |

### La Growth Machine

| Attribute | Detail |
|-----------|--------|
| Type | Multi-channel (LinkedIn + Email + Twitter + Calls) |
| Pricing | Pro: EUR 120/mo/identity |
| API | Partial (lead management) |
| Key feature | Visual workflow builder with conditional branching across all channels |
| Limitation | No native Instantly integration |

### NOT Recommended for Our Pipeline

| Tool | Reason |
|------|--------|
| **Waalaxy** | Browser extension (high ban risk), no API |
| **Dripify** | No public API, no native Instantly integration |
| **PhantomBuster** | Data extraction tool, not cadence orchestrator. Moderate ban risk |

### API Availability Matrix

| Tool | REST API | Webhooks | Zapier/Make | Native Instantly |
|------|----------|----------|-------------|-----------------|
| **HeyReach** | Yes (all plans) | 20+ events | Yes | **Yes** |
| **Lemlist** | Yes (18 categories) | Yes | Yes | No |
| **La Growth Machine** | Partial | Via n8n/Pipedream | Yes | No |
| **Expandi** | No | Yes | Yes | No |
| **Salesflow** | Yes | Unknown | Yes | No |

---

## 3. LinkedIn Safety at Scale

### Daily Limits (2025-2026)

| Action | Free Account | Premium / SN | Safe Weekly Max |
|--------|-------------|-------------|----------------|
| Connection requests | 10-15/day | 20-25/day | 80-100/week |
| Messages (connections) | 20-30/day | 50-100/day | 150/day max |
| Profile views | 80/day | 150/day | — |
| InMails | N/A | 20-50/month | — |

### Mandatory Warm-Up Protocol

```
Week 1:   10 requests/day,  5 messages/day
Week 2:   15 requests/day, 10 messages/day
Week 3:   20 requests/day, 20 messages/day
Week 4+:  25 requests/day, 30-50 messages/day (plateau — do not exceed)
```

### Safety Rules
1. **Cloud-based tools only** — browser extensions carry ~60% higher detection risk
2. **Dedicated residential IP per account**
3. **Random delays** — 45-120s between views, 2-5 min between requests
4. **Sender rotation** — distribute across multiple accounts
5. **Business hours only** — 9 AM to 6 PM in prospect's timezone
6. **Monitor acceptance rate** — below 20% = LinkedIn may restrict account

---

## 4. Recommended Architecture: Instantly + HeyReach

### Pipeline Flow

```
                        CAIO ALPHA SWARM PIPELINE
                        ========================

  [Apollo.io] → [Enrichment: Apollo + BetterContact] → [ICP Scoring]
       → [AI Message Crafting (email + LinkedIn variants)]
       → [Queen Approval Dashboard]
       → [Channel Router]

  Channel Router:
    ALL leads ──────────────────→ [Instantly.ai] (Email Cadence)
    linkedin_url + icp ≥ 75 ──→ [HeyReach] (LinkedIn Automation)

  Bidirectional Sync (native):
    Reply on email    → HeyReach pauses LinkedIn sequence
    Accept on LinkedIn → Instantly updates lead status
    Meeting booked    → Both channels mark as converted
```

### Cost Estimate
- HeyReach Growth (3 senders, annual): ~$177/mo
- Instantly.ai: existing cost (unchanged)
- **Total additional**: ~$180-240/mo

### Implementation Phases

**Phase 1 (Week 1-2): HeyReach Setup**
- Sign up for HeyReach Growth ($79/mo/sender)
- Connect 1-2 warm LinkedIn accounts
- Configure native Instantly integration via API key exchange
- Create first LinkedIn sequence template
- Begin warm-up: 10 requests/day → ramp to 25 by week 4

**Phase 2 (Week 2-3): Pipeline Integration**
- Add HeyReach API calls after approval stage in Inngest pipeline
- Add webhook listeners in `dashboard/health_app.py`
- Implement channel routing: `linkedin_url` + `icp_score >= 75` → both channels

**Phase 3 (Week 3-4): Cross-Channel Sync**
- Configure HeyReach ↔ Instantly native sync automations
- Test bidirectional pause/resume
- Add unified inbox view to dashboard

**Phase 4 (Month 2+): Scale**
- Add more LinkedIn sender accounts
- A/B test LinkedIn message templates
- Implement dynamic branching (email opened → increase LinkedIn)
- Evaluate WhatsApp/call channels via Lemlist

---

## Key Takeaways

1. **HeyReach + Instantly.ai** — native integration, lowest friction, ~$180-240/mo additional
2. **Lemlist** — strongest single-tool alternative (replaces Instantly, $99/user/mo)
3. **Do NOT build cadence orchestration from scratch** — LinkedIn safety alone takes months
4. **LinkedIn safety is non-negotiable** — cloud-based, 20-25 requests/day max, 4-week warm-up
5. **Build in your pipeline**: lead scoring, AI personalization, approval workflow, routing logic
6. **Let tools handle**: channel execution, deliverability, safety, warm-up
