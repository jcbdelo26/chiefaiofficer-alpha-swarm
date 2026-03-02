---
title: "ADR-001: Redis Over Filesystem for Shadow Email Queue"
status: accepted
date: 2026-02-15
---

# ADR-001: Redis Over Filesystem for Shadow Email Queue

## Status
Accepted (implemented commit `2d074c6`, refined through `4226583`)

## Context
The pipeline executes locally (Windows) while the dashboard runs on Railway (Linux container). These are **completely separate filesystems** with zero synchronization.

Initially, the pipeline wrote shadow emails to `.hive-mind/shadow_mode_emails/` on the local filesystem. The Railway dashboard attempted to read from the same path — but on its own isolated Linux filesystem. This caused **3 separate incidents** where the dashboard showed "no pending emails" despite the pipeline queuing them.

## Decision
Use Redis (Upstash) as the **primary** persistence layer for shadow emails, with local filesystem as a **fallback** only.

```
Local Pipeline --> shadow_queue.push() --> Redis (primary) + disk (fallback)
                                               |
Railway Dashboard --> shadow_queue.list_pending() --> Redis (primary) + disk (fallback)
```

Implementation: `core/shadow_queue.py`
- Redis write attempted first with retries and connection pooling
- Filesystem write occurs in parallel as a safety net
- Both write paths independent; either success is sufficient

## Alternatives Considered
1. **Supabase/PostgreSQL**: Rejected — added complexity for simple queue semantics
2. **Filesystem with periodic sync**: Rejected — race conditions across platforms
3. **File-only with cron export**: Rejected — 3 incidents proved this unreliable

## Consequences
- Cross-environment data visible in near-real-time
- Redis unavailability doesn't block pipeline (falls back to filesystem)
- Dashboard auto-refreshes without manual reload
- Requires `REDIS_URL` env var in production
- Redis key schema must use `CONTEXT_REDIS_PREFIX` (see ADR-005)

## Enforcement
This is the **canonical pattern** for all cross-environment data flows. Any new feature requiring bidirectional visibility must use Redis as primary.
