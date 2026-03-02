# Compliance Reference

**Last Updated**: 2026-03-03
**Scope**: CAN-SPAM, GDPR, LinkedIn ToS, internal safety controls

---

## 1. CAN-SPAM Act (USA)

All outbound cold emails MUST comply with CAN-SPAM (15 U.S.C. 7701-7713).

### Required Elements (every email)

| Requirement | Implementation | Enforced By |
|-------------|----------------|-------------|
| **Honest subject line** | GUARD-004 bans deceptive openers; GUARD-005 blocks generic filler | `core/quality_guard.py` |
| **Identify as advertisement** | Not required for B2B outreach with legitimate business purpose | N/A |
| **Physical address** | `5700 Harper Dr, Suite 210, Albuquerque, NM 87109` in every footer | `execution/crafter_campaign.py` footer block |
| **Opt-out mechanism** | `Reply STOP to unsubscribe.` in every email | Footer block + `core/compliance.py` check |
| **Honor opt-outs within 10 days** | Immediate: `reply_stop` handler removes from all sequences | `webhooks/instantly_webhook.py`, `core/lead_signals.py` |
| **No harvested addresses** | All leads from Apollo People Search (opt-in business data) | `execution/hunter_scrape_followers.py` |

### Footer Block (canonical)

```
---
Reply STOP to unsubscribe.
Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109
```

### Enforcement Points

1. **Pre-queue**: `core/quality_guard.py` — 5 rules block non-compliant drafts
2. **Pre-send**: `core/deliverability_guard.py` — syntax, suppression, role/disposable checks
3. **Post-send**: `webhooks/instantly_webhook.py` — `reply_stop` handler, bounce handler
4. **Dashboard**: `dashboard/health_app.py` — compliance checks on every pending email (reply_stop, signature, CTA, footer)

---

## 2. GDPR Considerations (EU/EEA)

### Lawful Basis

- **Legitimate interest** (Article 6(1)(f)): B2B outreach to business contacts at their professional email for a relevant business proposition.
- NOT relying on consent — legitimate interest basis requires balancing test.

### Data Subject Rights

| Right | Implementation |
|-------|----------------|
| **Right to erasure** | `Reply STOP` triggers immediate removal from all sequences + `unsubscribes.jsonl` |
| **Right of access** | Manual process — contact `support@chiefaiofficer.com` |
| **Data minimization** | Only business-relevant fields collected (name, title, company, business email) |

### Data Storage

- Lead data: `.hive-mind/enriched/` (local) + Redis (shared state)
- Shadow emails: Redis (primary) + `.hive-mind/shadow_mode_emails/` (fallback)
- Rejection memory: Redis + `.hive-mind/rejection_memory/` (30-day TTL)
- No personal data in logs beyond business email addresses

### Safeguards

- **Suppression list**: `.hive-mind/unsubscribes.jsonl` — append-only, checked before every send
- **Customer exclusion**: 27 emails + 7 domains hard-blocked in `config/production.json`
- **Competitor exclusion**: 12 competitor domains blocked in deliverability guard

---

## 3. LinkedIn Terms of Service

### HeyReach Usage Constraints

| Constraint | Limit | Enforcement |
|-----------|-------|-------------|
| **Daily connection requests** | 5/day (warmup) -> 20/day (full) | `LinkedInDailyCeiling` Redis class in `heyreach_dispatcher.py` |
| **Daily messages** | Bundled with connection limit | OPERATOR ramp config |
| **Profile views** | Not automated (HeyReach handles) | Platform-managed |
| **Account warmup** | 4-week warmup period (~Mar 16) | Manual monitoring |

### Safety Measures

- **GATEKEEPER approval** required for all LinkedIn outreach during ramp
- **Multi-channel dedup**: No same-lead on both email AND LinkedIn same day (`OperatorDailyState`)
- **Exit signals respected**: bounced, unsubscribed, or replied leads exit all sequences
- **No scraping**: HeyReach uses official LinkedIn APIs, not scraping

---

## 4. Internal Safety Controls

### Volume Limits

| Control | Setting | Config Location |
|---------|---------|-----------------|
| Email daily limit | 25/day (5 during ramp) | `config/production.json` → `operator.ramp` |
| LinkedIn daily limit | 5/day warmup → 20/day | `config/production.json` → `operator.outbound.linkedin_warmup_daily_limit` |
| Domain concentration | Max 3/domain/batch | `core/deliverability_guard.py` Guard 3 |
| EMERGENCY_STOP | Blocks ALL outbound | Railway env var |

### Disqualification Rules

**NEVER contact**:
- < 10 employees or > 1000 employees
- < $1M revenue
- Government, Non-profit, Education, Academic
- Current customers (27 emails, 7 domains)
- Competitors (12 domains)

### Audit Trail

All email outcomes are recorded as deterministic training tuples in `core/feedback_loop.py`:
- Action taken (approve/reject/send)
- Outcome (sent_proved, sent_unresolved, blocked_deliverability)
- Evidence (proof status, deliverability risk, rejection tags)
- Stored in `.hive-mind/feedback_loop/training_tuples.jsonl`

---

## 5. Compliance Checklist (Pre-Send)

- [ ] Email has `Reply STOP to unsubscribe.` footer
- [ ] Email has physical address in footer
- [ ] Subject line is not deceptive or misleading
- [ ] Recipient is not on suppression list (`unsubscribes.jsonl`)
- [ ] Recipient domain is not excluded (customers + competitors)
- [ ] Recipient meets ICP criteria (size, revenue, industry)
- [ ] Quality guard passed (5 rules)
- [ ] Deliverability guard passed (4 layers)
- [ ] Daily volume limit not exceeded
