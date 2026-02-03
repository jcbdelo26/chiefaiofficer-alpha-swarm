# RevOps Sales Playbook
## Chief AI Officer Unified Swarm

---

## 1. Target Market

### Ideal Customer Profile (ICP)
| Attribute | Criteria |
|-----------|----------|
| Company Type | B2B SaaS |
| Employee Count | 51-500 |
| Primary Buyers | VP Sales, CRO, RevOps Leaders |
| Tech Stack | Using CRM (Salesforce, HubSpot, Pipedrive) |
| Pain Point | Seeking AI enhancement for revenue operations |

### Qualification Signals
- Active job postings for RevOps/Sales Ops roles
- Recent CRM implementation or migration
- Leadership discussing AI/automation on LinkedIn
- Attending revenue operations conferences
- Using point solutions that indicate scaling challenges

---

## 2. Lead Tiers & Actions

### Tier 1: VIP
**Criteria:** Fortune 1000, known brand, $50M+ ARR, C-suite contact
| Action | Details |
|--------|---------|
| Approach | High-touch, fully personalized |
| Approval | AE approval required before any outreach |
| Research | Deep company + individual research by SCOUT |
| Cadence | Custom timing, max 1 touch per week |
| Content | Executive-level, ROI-focused |

### Tier 2: High
**Criteria:** 200-500 employees, VP+ title, strong intent signals
| Action | Details |
|--------|---------|
| Approach | Personalized sequences |
| Approval | Auto-approved |
| Research | Company research + role-specific insights |
| Cadence | Standard with personalization tokens |
| Content | Role-specific pain points |

### Tier 3: Standard
**Criteria:** 51-199 employees, Manager+ title, moderate intent
| Action | Details |
|--------|---------|
| Approach | Templated nurture sequences |
| Approval | Auto-approved |
| Research | Basic enrichment |
| Cadence | Automated standard sequence |
| Content | Educational, problem-aware |

### Tier 4: Low
**Criteria:** Below ICP threshold, informational interest only
| Action | Details |
|--------|---------|
| Approach | Newsletter/content only |
| Approval | N/A |
| Research | None |
| Cadence | Monthly newsletter |
| Content | Thought leadership, no CTA |

---

## 3. Campaign Templates

### competitor_displacement
**Trigger:** Lead following competitors (Salesloft, Outreach, Gong)
```
Focus: Differentiation + migration ease
Messaging: "Noticed you're using [Competitor]. Here's how teams are getting 3x the results..."
Assets: Comparison guides, migration case studies
```

### event_followup
**Trigger:** Conference/webinar attendee
```
Focus: Session-specific value add
Messaging: Reference specific session/topic discussed
Assets: Session recordings, related content, exclusive offers
Timing: Within 24h of event
```

### intent_based
**Trigger:** Website visitor with high-intent behavior (pricing page, demo page, multiple visits)
```
Focus: Address specific interest area
Messaging: "Saw you were checking out [feature]. Here's a quick overview..."
Assets: Feature-specific demos, customer stories
Timing: Within 2h of intent signal
```

### thought_leadership
**Trigger:** Downloaded content, engaged with posts, newsletter subscriber
```
Focus: Education and trust building
Messaging: Non-salesy, genuine value delivery
Assets: Research reports, industry insights, how-to guides
Timing: Bi-weekly nurture
```

---

## 4. Outreach Cadence

### Standard Sequence (14-Day)

| Day | Action | Channel | Goal |
|-----|--------|---------|------|
| 0 | Initial outreach | Email | Hook with personalized insight |
| 3 | Follow-up (if no open) | Email | Different subject line, same core message |
| 5 | Social touch | LinkedIn | Profile view + connection request |
| 7 | Value-add content | Email | Share relevant resource, no ask |
| 10 | LinkedIn message | LinkedIn | Soft reference to emails |
| 14 | Break-up email | Email | Clear close, leave door open |

### Cadence Rules
- **Max emails/day per lead:** 1
- **Min gap between touches:** 48 hours
- **Weekend sends:** Disabled
- **Optimal send times:** Tue-Thu, 9-11am recipient timezone

---

## 5. Response Handling

### Positive Reply
```yaml
action: IMMEDIATE_ESCALATION
steps:
  - Notify assigned AE via Slack + email within 5 minutes
  - Auto-create opportunity in CRM
  - Schedule follow-up task for AE
  - Pause all automated sequences
  - PIPER drafts personalized response for AE review
```

### Objection Received
```yaml
action: ROUTE_TO_HANDLER
common_objections:
  - "Not interested" → Acknowledge, offer content instead
  - "Using competitor" → Trigger competitor_displacement track
  - "Bad timing" → Schedule 90-day re-engagement
  - "Need to involve others" → Offer multi-stakeholder content
  - "Too expensive" → Route to ROI calculator flow
```

### Unsubscribe Request
```yaml
action: IMMEDIATE_COMPLIANCE
steps:
  - Add to suppression list within 1 hour
  - Remove from all active sequences
  - Log in CRM with reason if provided
  - No further email outreach (LinkedIn OK if not requested otherwise)
```

### No Response (Sequence Complete)
```yaml
action: NURTURE_TRANSITION
steps:
  - Move to long-term nurture (monthly content)
  - Re-engage after 90 days if new intent signal
  - Keep in newsletter unless unsubscribed
```

---

## 6. Meeting Booking Flow

### Pre-Booking
```
1. Calendly/GHL calendar integration active
2. Available slots synced with AE calendars
3. Booking page includes:
   - Meeting purpose selection
   - Company size qualifier
   - Primary challenge dropdown
```

### Booking Confirmation
```
1. Auto-confirm email sent immediately
2. Calendar invite with Zoom/Meet link
3. Add to CRM as scheduled meeting
4. Notify AE via Slack
```

### Pre-Meeting (SCOUT Agent)
```
Execute 24h before meeting:
1. Company research refresh
2. Recent news/funding alerts
3. Attendee LinkedIn analysis
4. Competitor intel check
5. Prepare briefing doc for AE
```

### Post-Meeting (PIPER Agent)
```
Execute within 2h of meeting end:
1. Generate meeting summary from notes/recording
2. Extract action items
3. Draft follow-up email for AE approval
4. Update CRM with meeting outcome
5. Create next steps tasks
```

---

## 7. Self-Annealing Triggers

### Automatic Adjustments

| Metric | Threshold | Action |
|--------|-----------|--------|
| Spam Rate | > 1% | Reduce daily send volume by 50%, pause & review messaging |
| Bounce Rate | > 5% | Halt sends, audit enrichment data quality, verify email addresses |
| Open Rate | < 20% | Trigger A/B testing on subject lines, check send times |
| Reply Rate | < 2% | Review personalization depth, test new angles |
| Unsubscribe Rate | > 0.5% | Audit frequency, review content relevance |
| Meeting No-Show | > 25% | Add reminder sequence, verify qualification |

### Escalation Protocol
```
Level 1 (Threshold breached): Auto-adjust + log
Level 2 (No improvement 48h): Alert RevOps lead
Level 3 (Continued degradation): Pause campaign, manual review required
```

### Weekly Health Check
- Review all campaign metrics
- Identify top/bottom performers
- Propose optimizations to playbook
- Update suppression lists

---

## 8. Compliance Rules

### CAN-SPAM Compliance
- [ ] Physical mailing address in footer
- [ ] Clear unsubscribe mechanism (one-click)
- [ ] Accurate sender information
- [ ] Truthful subject lines
- [ ] Honor opt-outs within 10 business days (target: 24h)

### GDPR Compliance
- [ ] Lawful basis documented for EU contacts
- [ ] Delete requests honored within 48 hours
- [ ] Data access requests fulfilled within 30 days
- [ ] Clear privacy policy link in all communications
- [ ] No purchased lists for EU contacts

### CCPA Compliance
- [ ] "Do Not Sell" requests honored
- [ ] Data disclosure available upon request
- [ ] Opt-out mechanism clearly visible

### Daily Operations
```
Daily sync tasks:
1. Import new suppression list entries
2. Cross-check unsubscribes across all platforms
3. Verify bounce removals
4. Audit new contacts for compliance flags
```

### Suppression List Sources
- CRM unsubscribes
- Email platform bounces
- Manual requests
- Legal/competitor domains
- Previous customers (unless re-engagement approved)

---

## Quick Reference: Agent Responsibilities

| Agent | Primary Role | Playbook Touchpoints |
|-------|--------------|---------------------|
| SCOUT | Research & Intel | Pre-meeting research, company enrichment |
| PIPER | Content & Comms | Email drafts, meeting summaries, follow-ups |
| MIDAS | Revenue Ops | CRM updates, pipeline management, metrics |
| SENTRY | Compliance | Suppression lists, audit trails, GDPR/CAN-SPAM |

---

*Last Updated: Auto-generated*
*Version: 1.0*
*Owner: Chief AI Officer RevOps Swarm*
