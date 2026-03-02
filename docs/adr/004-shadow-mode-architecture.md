---
title: "ADR-004: Shadow Mode Architecture"
status: accepted
date: 2026-02-10
---

# ADR-004: Shadow Mode Architecture (Redis-Backed Approval Queue)

## Status
Accepted (Phase 4E ramp mode active as of 2026-03-02)

## Context
The system must allow Head of Sales (HoS) approval of all outbound emails before they reach external platforms (GHL, Instantly, HeyReach). Shadow mode bridges autonomous pipeline execution and human-in-the-loop safety.

## Decision
Implement a three-layer shadow mode architecture:

1. **Local Disk Fallback** (`.hive-mind/shadow_mode_emails/`): JSON files for local debugging
2. **Redis Primary Queue** (Upstash): Shared between local pipeline and Railway dashboard
3. **Railway Dashboard UI** (`/sales`): 4-tab interface with per-email approve/reject

**Email Lifecycle**:
```
Pipeline stages 1-4 --> Tier_1 leads + campaigns
    --> _stage_send() --> shadow_queue.push() --> Redis + disk
    --> HoS sees in /sales dashboard (auto-refresh 5s)
    --> HoS clicks Approve --> GHL delivery
    --> Bounce/open/reply webhooks --> cadence engine feedback
```

**Safety Controls**:
- `shadow_mode: true` in `config/production.json`
- GATEKEEPER gate: live dispatch requires batch approval
- Tier_1 filter: during ramp, only tier_1 leads queued
- Ramp mode: 5 emails/day, 3 supervised days before graduation
- `EMERGENCY_STOP` env var: blocks all outbound

Implementation: `execution/run_pipeline.py`, `core/shadow_queue.py`, `dashboard/health_app.py`

## Alternatives Considered
1. **Direct GHL send (no shadow)**: Rejected — violates HoS requirement for 100% human review
2. **Email table in Supabase**: Rejected — still needs Redis as cross-env bridge
3. **Approval via Slack reaction**: Rejected — doesn't scale, reduces visibility
4. **Async approval task queue**: Rejected — Redis sorted set sufficient

## Consequences
- Complete audit trail: every email decision logged with timestamp + username
- Human-in-the-loop for ramp period; configurable auto-approval after graduation
- Tier_1 leads never auto-approve, even after graduation
- Requires active HoS dashboard monitoring
- If HoS doesn't approve for 72h, queue backs up (mitigation: auto-archive stale)
