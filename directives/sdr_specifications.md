# 🎯 SDR Automation Specifications (SPARC Phase 1)

> Complete specifications for autonomous SDR agent behavior

---

## Overview

This document defines the precise acceptance criteria, constraints, and handoff triggers for SDR automation within the Chief AI Officer Alpha Swarm system.

---

## 1. SDR Agent Responsibilities

### 1.1 Primary Functions

| Function | Owner Agent | Automation Level | Human Touchpoint |
|----------|-------------|------------------|------------------|
| Lead Qualification | SEGMENTOR | Full | Spot-check sampling |
| Initial Outreach | CRAFTER | Supervised | GATEKEEPER approval |
| Follow-up Sequencing | CRAFTER + Instantly | Full | Exception handling |
| Meeting Scheduling | GHL Integration | Full | Calendar conflicts |
| Data Quality | ENRICHER | Full | Validation reviews |
| Objection Handling | CRAFTER | Partial | Complex escalation |

### 1.2 Automation Boundaries

```
FULLY AUTOMATED:
├── LinkedIn profile scraping
├── Data enrichment via Clay/RB2B
├── ICP scoring and segmentation
├── Email personalization (Tier 3)
├── Follow-up sequence triggering
├── Calendar link delivery
└── Performance tracking

SUPERVISED (AE Review):
├── Tier 1 VIP campaigns
├── Tier 2 high-priority campaigns
├── Custom personalization
├── Competitive positioning
└── Enterprise account messaging

HUMAN ONLY:
├── C-level direct engagement
├── Existing customer contact
├── Pricing negotiations
├── Security/compliance questions
├── Contract discussions
└── Complex technical requirements
```

---

## 2. Acceptance Criteria

### 2.1 Lead Qualification Metrics

| Metric | Target | Minimum | Critical Alert |
|--------|--------|---------|----------------|
| Tier 1 Accuracy | ≥90% | ≥85% | <80% |
| Tier 2 Accuracy | ≥85% | ≥80% | <75% |
| False Positive Rate | ≤15% | ≤20% | >25% |
| Enrichment Success | ≥90% | ≥85% | <80% |
| Data Freshness | ≤14 days | ≤30 days | >45 days |

**Measurement Method:**
- Weekly AE audit of 50 random leads
- Track SDR overrides (upgrade/downgrade)
- Compare automated tier vs deal outcome

### 2.2 Outreach Performance

| Metric | Target | Minimum | Critical Alert |
|--------|--------|---------|----------------|
| Email Deliverability | ≥95% | ≥92% | <90% |
| Open Rate | ≥50% | ≥40% | <35% |
| Reply Rate | ≥8% | ≥5% | <4% |
| Positive Reply Ratio | ≥50% | ≥40% | <30% |
| Unsubscribe Rate | ≤0.5% | ≤1% | >2% |
| Spam Report Rate | ≤0.01% | ≤0.05% | >0.1% |

**Measurement Method:**
- Instantly campaign analytics
- Sentiment classification on replies
- Daily automated reporting

### 2.3 Meeting Metrics

| Metric | Target | Minimum | Critical Alert |
|--------|--------|---------|----------------|
| Meeting Book Rate | ≥15% | ≥10% | <8% |
| Show Rate | ≥80% | ≥70% | <60% |
| Time-to-Meeting | ≤72hr | ≤120hr | >168hr |
| AE Satisfaction | ≥4.5/5 | ≥4/5 | <3.5/5 |

### 2.4 Data Quality Standards

| Standard | Requirement |
|----------|-------------|
| Email Format | Valid RFC 5322 format |
| Email Verification | Pass MX lookup + not catch-all |
| Phone Format | E.164 international format |
| Company Match | ≥90% confidence on domain |
| Title Normalization | Mapped to standard taxonomy |
| Duplicate Detection | Email + LinkedIn URL dedup |

---

## 3. Compliance Requirements

### 3.1 CAN-SPAM Compliance

```yaml
Required Elements:
  - Accurate "From" header
  - Non-deceptive subject line
  - Physical mailing address
  - Working unsubscribe mechanism
  - Honor unsubscribe within 10 business days
  
Prohibited:
  - Harvested email addresses
  - Purchased lists
  - Misleading headers
  - False urgency claims
```

### 3.2 LinkedIn Terms of Service

```yaml
Rate Limits:
  profiles_per_hour: 100
  profiles_per_day: 500
  connections_per_week: 100
  messages_per_day: 50

Session Management:
  rotation_interval: 24 hours
  user_agent_rotation: enabled
  proxy_rotation: per_session
  
Prohibited:
  - Automated connection requests
  - Scraping without Sales Navigator
  - Bypassing access controls
  - Storing scraped data >90 days
```

### 3.3 GDPR Compliance

```yaml
Rights Handling:
  right_to_access:
    response_time: 30 days
    format: Structured JSON export
    
  right_to_deletion:
    response_time: 24 hours
    scope: All personal data
    verification: Required
    
  right_to_rectification:
    response_time: 72 hours
    audit_trail: Required

Consent:
  basis: Legitimate interest
  documentation: Per-lead tracking
  withdrawal: Honored immediately
  
Data Retention:
  active_leads: 24 months
  inactive_leads: 12 months
  deleted_requests: 90 days (audit only)
```

### 3.4 Brand Safety

```yaml
Content Rules:
  - No competitor disparagement
  - Factual claims only
  - Professional tone always
  - No false urgency
  - No misleading statistics
  
Review Requirements:
  tier_1_campaigns: AE approval required
  tier_2_campaigns: AE approval recommended
  tier_3_campaigns: Batch sampling (10%)
  
Prohibited Terms:
  - "Guarantee" without qualification
  - "Best" / "Only" without evidence
  - Competitor names in subject lines
  - Fake personalization
```

---

## 4. Personalization Thresholds

### 4.1 Personalization Depth by Tier

```yaml
TIER_1_VIP (Score 85-100):
  depth: deep
  required_elements:
    - First name
    - Company name
    - Specific engagement reference
    - Recent company news/events
    - Inferred pain points (2-3)
    - Mutual connections if any
    - Industry-specific value prop
    - Competitor displacement angle
  optional_elements:
    - Personal interests from profile
    - Recent content they created
    - Shared education/experience
  generation: AI with human review
  approval: Required before send

TIER_2_HIGH (Score 70-84):
  depth: medium
  required_elements:
    - First name
    - Company name
    - Engagement reference
    - Industry-specific hook
    - One pain point
  optional_elements:
    - Company news
    - Tech stack reference
  generation: AI with sampling
  approval: Recommended

TIER_3_STANDARD (Score 50-69):
  depth: light
  required_elements:
    - First name
    - Company name
    - Source-based hook
  optional_elements:
    - Industry mention
  generation: Template-based
  approval: Batch only

TIER_4_NURTURE (Score 30-49):
  depth: minimal
  required_elements:
    - First name
  optional_elements:
    - Company name
  generation: Standard template
  approval: None
```

### 4.2 Personalization Quality Checks

```yaml
Quality Gates:
  - No placeholder tokens in output
  - Company name matches domain
  - Title capitalization correct
  - Grammar check passed
  - No lorem ipsum
  - No duplicate content
  
Fallback Rules:
  - If company news unavailable: Skip element
  - If no mutual connections: Use industry angle
  - If no comment content: Use source type
  - If low confidence: Default to minimal
```

---

## 5. Handoff Triggers

### 5.1 Immediate Escalation (Within 5 Minutes)

| Trigger | Destination | Priority |
|---------|-------------|----------|
| Enterprise account (>1000 emp) | Enterprise AE | Critical |
| C-level engagement | Senior AE | Critical |
| Existing customer flag | CSM | Critical |
| Competitor employee | Skip | Block |
| Negative reply sentiment | AE Review | High |
| Pricing mentioned | AE | High |
| Security question | SE | High |

### 5.2 Standard Escalation (Within 1 Hour)

| Trigger | Destination | Priority |
|---------|-------------|----------|
| Buying signals detected | AE | Medium |
| Meeting request (manual) | AE Calendar | Medium |
| Technical deep-dive request | SE | Medium |
| Integration requirements | SE | Medium |
| Demo request | AE + SE | Medium |

### 5.3 Deferred Escalation (Daily Review)

| Trigger | Destination | Priority |
|---------|-------------|----------|
| ICP score ≥95 | VIP Campaign | Low |
| Multiple touchpoints | Nurture upgrade | Low |
| Engagement pattern change | Outreach adjustment | Low |
| Persona mismatch | Re-qualification | Low |

### 5.4 Objection Escalation Matrix

```yaml
objection_responses:
  not_interested:
    action: soft_breakup
    escalation: none
    automation: full
    
  bad_timing:
    action: schedule_future
    escalation: none
    automation: full
    
  already_have_solution:
    action: displacement_nurture
    escalation: if_enterprise
    automation: partial
    
  need_more_info:
    action: send_resources
    escalation: none
    automation: full
    
  pricing_objection:
    action: value_framework
    escalation: always
    automation: none
    
  technical_question:
    action: route_to_se
    escalation: always
    automation: none
    
  positive_interest:
    action: book_meeting
    escalation: if_tier_1
    automation: partial
```

---

## 6. SLA Definitions

### 6.1 Response Time SLAs

| Scenario | Target | Maximum |
|----------|--------|---------|
| Positive reply | 15 min | 1 hour |
| Meeting request | 30 min | 2 hours |
| Technical question | 2 hours | 4 hours |
| General inquiry | 4 hours | 24 hours |
| Negative reply | 24 hours | 48 hours |

### 6.2 Process SLAs

| Process | Target | Maximum |
|---------|--------|---------|
| Lead enrichment | 10 min | 1 hour |
| Campaign generation | 5 min | 30 min |
| AE review queue | 4 hours | 24 hours |
| Campaign launch | 1 hour | 4 hours |
| Unsubscribe processing | 1 hour | 10 days |

---

## 7. Exception Handling

### 7.1 System Failures

```yaml
enrichment_failure:
  action: Queue for retry
  max_retries: 3
  fallback: Proceed with partial data
  notification: If batch >10% failure

scraping_blocked:
  action: Pause immediately
  notification: Critical alert
  recovery: Manual intervention
  
campaign_delivery_failure:
  action: Retry with backoff
  max_retries: 5
  fallback: Notify AE
  
api_rate_limit:
  action: Exponential backoff
  max_wait: 1 hour
  fallback: Queue for later
```

### 7.2 Data Quality Issues

```yaml
duplicate_detected:
  action: Merge latest
  preference: Higher ICP score
  notification: None

email_bounced:
  action: Remove from sequence
  flag: Invalid email
  re_enrich: After 30 days
  
company_mismatch:
  action: Flag for review
  hold_outreach: true
  notification: Weekly digest
```

---

## 8. Reporting Requirements

### 8.1 Daily Reports

- Leads scraped (by source)
- Enrichment success rate
- Emails sent/delivered/opened
- Replies received (by sentiment)
- Meetings booked

### 8.2 Weekly Reports

- ICP tier distribution
- Conversion funnel analysis
- AE approval/rejection trends
- Self-annealing adjustments
- Performance vs targets

### 8.3 Monthly Reports

- ROI analysis
- Campaign performance comparison
- ICP criteria validation
- Compliance audit results
- System health summary

---

*Document Version: 1.0*
*Last Updated: 2026-01-13*
*Owner: Alpha Swarm SDR Automation Team*
