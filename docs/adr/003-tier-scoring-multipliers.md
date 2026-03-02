---
title: "ADR-003: Tier Scoring Multipliers (1.5x, 1.2x, 1.0x)"
status: accepted
date: 2026-01-20
---

# ADR-003: Tier Scoring Multipliers

## Status
Accepted (aligned with HoS requirements)

## Context
The ICP scoring system must differentiate lead quality to route Tier_1 (C-Suite) leads to high-touch campaigns while allowing Tier_2/3 auto-approval.

## Decision
Implement tier multipliers that scale base ICP scores:

| Tier | Target Persona | Multiplier | Threshold |
|------|---------------|-----------|-----------|
| Tier_1 | CEO/Founder/COO at agency/consulting (51-500 emp, $5-100M) | **1.5x** | >= 80 |
| Tier_2 | CTO/CIO/VP Ops at B2B SaaS/IT Services | **1.2x** | >= 60 |
| Tier_3 | Director/VP Engineering at manufacturing/logistics | **1.0x** | >= 40 |
| Tier_4 | Below threshold | — | < 40 |

**Score Components** (from `config/icp_config.py`):
- Title Score: Tier_1=30pts, Tier_2=20pts, Tier_3=10pts
- Industry Score: IDEAL=25pts, GOOD=18pts, ACCEPTABLE=10pts
- Size Score: 15pts x company size multiplier (1.0-1.5x)
- Revenue Score: 10pts x revenue tier multiplier (0.8-1.5x)
- Pain Points: 25-60pts per signal (e.g., "AI overwhelm"=60pts)
- Tech Stack: +20pts for CRM, +15pts for automation tools

**Example**: CEO at 150-person agency: (30+25+20) base = 75 x 1.5 = **112** -> Tier_1

Implementation: `config/icp_config.py`, `execution/segmentor_classify.py`

## Alternatives Considered
1. **Flat thresholds (no multipliers)**: Rejected — loses signal that C-Suite at agencies is higher ROI
2. **Persona-only tiers**: Rejected — misses company size/revenue sweet spot (101-250 emp, $5-100M)
3. **AI-learned thresholds**: Rejected — not enough historical data; HoS requires explicit rules
4. **Continuous score (no bucketing)**: Rejected — HoS needs distinct tier-based approval workflows

## Consequences
- Aligns with HoS tier definitions and operational bottleneck thesis
- Multipliers are transparent and auditable (not ML-derived)
- Manual calibration may need tuning when conversion data arrives
- Leads can shift tiers with small enrichment changes (company size update)
