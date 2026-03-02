---
title: "ADR-002: Six-Stage Pipeline Design"
status: accepted
date: 2026-01-16
---

# ADR-002: Six-Stage Pipeline Design

## Status
Accepted (implemented from Phase 0, 33+ successful runs)

## Context
The lead-to-send workflow requires multiple transformations with distinct objectives, constraints, and approval gates.

## Decision
Implement a linear six-stage pipeline: **SCRAPE -> ENRICH -> SEGMENT -> CRAFT -> APPROVE -> SEND**

| Stage | Agent | Purpose | Key Constraint |
|-------|-------|---------|----------------|
| 1. Scrape | HUNTER | Acquire raw leads | 45s hard timeout; test data fallback |
| 2. Enrich | ENRICHER | Append company/contact data | Waterfall: Apollo -> BetterContact -> Clay |
| 3. Segment | SEGMENTOR | Score ICP fit, assign tier | Tier_1 >= 80pts, Tier_2 >= 60pts, Tier_3 >= 40pts |
| 4. Craft | CRAFTER | Generate personalized sequences | Per-lead email sequences (not campaign-level) |
| 5. Approve | GATEKEEPER | Human review gate | Tier_1 always requires human approval |
| 6. Send | OUTBOX | Queue to shadow mode | Shadow emails in Redis + filesystem |

Implementation: `execution/run_pipeline.py`

## Order Justification
1. **Scrape first**: Must have leads before enriching
2. **Enrich before segment**: Can't score without company/industry data
3. **Segment before craft**: Need tier for messaging angle personalization
4. **Craft before approve**: Reviewers need to see final copy
5. **Approve before send**: Safety gate — no emails go live without verification
6. **Send last**: Shadow mode provides final human review on Railway dashboard

## Alternatives Considered
1. **Inline enrichment during scrape**: Rejected — increased timeout risk, mixed concerns
2. **Segment-Craft-Enrich order**: Rejected — can't personalize without company context
3. **No separate approve stage**: Rejected — HoS mandates Tier_1 human review
4. **Direct-to-GHL send**: Rejected — violates human-in-loop requirement

## Consequences
- Clear separation of concerns; each stage independently testable
- Graceful degradation: non-critical stage failures don't block completion
- Safety checkpoints at stages 5 and 6
- Linear flow means single stage failure can halt run (mitigated by auto-fallbacks)
