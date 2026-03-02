---
title: "ADR-005: CONTEXT_REDIS_PREFIX Over STATE_REDIS_PREFIX"
status: accepted
date: 2026-02-20
---

# ADR-005: CONTEXT_REDIS_PREFIX Over STATE_REDIS_PREFIX

## Status
Accepted (fixed in commit `2d074c6`, standing architectural rule)

## Context
Two Redis prefix environment variables exist:

| Variable | Local Value | Railway Value | Consistent? |
|----------|-------------|---------------|-------------|
| `STATE_REDIS_PREFIX` | `""` (empty) | `"caio"` | NO |
| `CONTEXT_REDIS_PREFIX` | `"caio:production:context"` | `"caio:production:context"` | YES |

A bug caused the dashboard to show "no pending emails" when the pipeline queued them: the `_prefix()` function checked `STATE_REDIS_PREFIX` first. Local pipeline wrote to `shadow:email:123`, Railway dashboard looked for `caio:shadow:email:123` — silent miss.

## Decision
**Rule: All Redis modules storing cross-environment shared data MUST use `CONTEXT_REDIS_PREFIX` as primary.**

Fallback chain (from `core/shadow_queue.py`):
```python
def _prefix() -> str:
    return (
        os.getenv("CONTEXT_REDIS_PREFIX")     # Primary (consistent)
        or os.getenv("STATE_REDIS_PREFIX")    # Fallback (environment-specific)
        or "caio"                              # Default
    ).strip()
```

**Key Schema**:
```
{CONTEXT_REDIS_PREFIX}:shadow:email:{email_id}    # Individual email
{CONTEXT_REDIS_PREFIX}:shadow:pending_ids          # Pending index (sorted set)
```

Applied in: `core/shadow_queue.py`, `core/state_store.py`, `core/rejection_memory.py`

## Alternatives Considered
1. **Rename STATE_REDIS_PREFIX on Railway**: Rejected — doesn't fix root cause
2. **Universal constant "caio"**: Rejected — loses multi-environment flexibility
3. **Environment detection logic**: Rejected — adds complexity; explicit prefix is clearer

## Consequences
- Eliminates entire class of prefix mismatch bugs
- Explicit and auditable — new engineers see the rule immediately
- Single source of truth for cross-environment keys
- Requires discipline: every new module must follow this pattern
- Risk if new modules accidentally use `STATE_REDIS_PREFIX`

## Enforcement
- Code review: any module with `_get_redis()` or `_prefix()` must use `CONTEXT_REDIS_PREFIX`
- Test: `tests/test_cross_environment_bridge.py` validates prefix consistency
- Pre-flight checklist in CLAUDE.md (#3) requires `CONTEXT_REDIS_PREFIX` verification
