# Codex Handoff: Shadow Email Queue — Dashboard Refresh Fix

**Date**: 2026-02-18
**Commits covered**: `077e34b` → `ccca9b4` → `2d074c6` → `ce7a533`
**Deployed**: commit `2d074c6` to Railway (`caio-swarm-dashboard-production.up.railway.app`)
**Plan reference**: `CAIO_IMPLEMENTATION_PLAN.md` v4.5 (Phase 4E: Supervised Live Sends)

---

## 1. Problem Statement

**The HoS email approval dashboard (`/sales`) showed "All caught up! No pending emails to review" even though the pipeline had successfully generated and queued 4+ emails.**

This blocked Phase 4E — the first supervised live dispatch cannot happen until the Head of Sales can review and approve pipeline-generated emails in the dashboard.

---

## 2. Root Cause Analysis

### 2.1 The Fundamental Architecture Mismatch

The CAIO Alpha Swarm has a **split-environment architecture**:

```
┌──────────────────────┐          ┌──────────────────────┐
│   LOCAL (Windows)     │          │   RAILWAY (Linux)     │
│                       │          │                       │
│   Pipeline runs here  │    ✗     │   Dashboard runs here │
│   Writes to disk:     │ ←──────→ │   Reads from disk:    │
│   .hive-mind/shadow_  │  NEVER   │   .hive-mind/shadow_  │
│   mode_emails/*.json  │ CONNECTED│   mode_emails/*.json  │
└───────────────────────┘          └───────────────────────┘
```

The pipeline writes shadow emails to `.hive-mind/shadow_mode_emails/` on the **local Windows filesystem**. The dashboard on Railway reads from `.hive-mind/shadow_mode_emails/` on the **Railway Linux container filesystem**. These are completely separate directories. Files written locally are **never** visible on Railway.

### 2.2 Why This Wasn't Caught Earlier

During Phase 2 (Supervised Burn-In), the dashboard was tested locally (`uvicorn dashboard.health_app:app`), where filesystem reads worked because the pipeline and dashboard ran on the same machine. The issue only manifested when the dashboard deployed to Railway and the pipeline continued running locally.

The `CAIO_IMPLEMENTATION_PLAN.md` (v4.5) documents shadow emails at line 707:

```
| Shadow emails | `.hive-mind/shadow_mode_emails/` | Review before enabling real sends |
```

This is **incorrect/incomplete** — it implies the filesystem path is the sole data store. The plan does NOT document the Redis bridge requirement. The Key Files section (lines 663-695) also does NOT include `core/shadow_queue.py`.

### 2.3 Two Bugs, Same Root Cause

**Bug 1** (commit `077e34b`): No Redis bridge existed. Pipeline wrote only to disk. Dashboard on Railway had no way to access the data.

**Bug 2** (commit `2d074c6`): Redis bridge was created but used wrong key prefix. The `_prefix()` function checked `STATE_REDIS_PREFIX` first. This variable resolves to `""` (empty) locally but `"caio"` on Railway, causing the pipeline to write keys under `caio:production:context:shadow:email:*` while Railway looked for them under `caio:shadow:email:*`.

---

## 3. What Was Built (Commit-by-Commit)

### 3.1 Commit `077e34b` — Redis Shadow Queue Bridge

**Created**: `core/shadow_queue.py` (264 lines)

This module bridges the local↔Railway gap using Upstash Redis as a shared persistence layer.

**Architecture**:
```
Pipeline (local) → shadow_queue.push() → Redis + disk
                                             ↓
Dashboard (Railway) → shadow_queue.list_pending() → Redis + disk
```

**Key functions**:
| Function | Purpose |
|----------|---------|
| `push(email_data, shadow_dir)` | Write email to Redis sorted set + string key, and optionally to disk |
| `list_pending(limit, shadow_dir)` | Read pending emails from Redis index, fallback to filesystem |
| `update_status(email_id, new_status, ...)` | Update email status in Redis + disk |
| `get_email(email_id, shadow_dir)` | Get single email by ID from Redis or disk |

**Redis key schema**:
| Key | Type | Purpose |
|-----|------|---------|
| `{prefix}:shadow:email:{email_id}` | String (JSON) | Full email data |
| `{prefix}:shadow:pending_ids` | Sorted Set (score=UTC timestamp) | Index of pending email IDs for fast retrieval |

**Modified**: `dashboard/health_app.py` — All three email endpoints (`/api/pending-emails`, `/api/emails/{id}/approve`, `/api/emails/{id}/reject`) now use `core/shadow_queue` for reads/writes instead of direct filesystem access.

**Modified**: `execution/run_pipeline.py` — Send stage (Stage 6, `_stage_send()`) now calls `shadow_queue.push()` instead of writing directly to disk. Fallback to disk-only if import fails.

### 3.2 Commit `ccca9b4` — Documentation

Created `docs/HOS_EMAIL_REVIEW_GUIDE.md` — Step-by-step guide for the Head of Sales to review pipeline emails. Added CLAUDE.md sections documenting the Redis bridge architecture.

### 3.3 Commit `2d074c6` — Redis Prefix Fix

**Bug**: `_prefix()` in `shadow_queue.py` checked `STATE_REDIS_PREFIX` first:

```python
# BEFORE (broken)
def _prefix() -> str:
    return (os.getenv("STATE_REDIS_PREFIX") or os.getenv("CONTEXT_REDIS_PREFIX") or "caio").strip()
```

| Variable | Local | Railway |
|----------|-------|---------|
| `STATE_REDIS_PREFIX` | `""` (empty, falls through) | `"caio"` (uses this) |
| `CONTEXT_REDIS_PREFIX` | `"caio:production:context"` | `"caio:production:context"` |
| **Effective prefix** | `caio:production:context` | `caio` |

Pipeline wrote to `caio:production:context:shadow:email:*`. Dashboard looked for `caio:shadow:email:*`. Prefix mismatch → 0 results.

**Fix**:
```python
# AFTER (correct)
def _prefix() -> str:
    # CONTEXT_REDIS_PREFIX first — consistently set on both local and Railway
    return (os.getenv("CONTEXT_REDIS_PREFIX") or os.getenv("STATE_REDIS_PREFIX") or "caio").strip()
```

**Also added**: `_shadow_queue_debug` diagnostic field to `/api/pending-emails` response:
```json
{
  "count": 4,
  "_shadow_queue_debug": {
    "prefix": "caio:production:context",
    "redis_connected": true,
    "redis_returned": 4
  }
}
```

### 3.4 Commit `ce7a533` — CLAUDE.md Pitfall Documentation

Added Redis prefix mismatch pitfall to CLAUDE.md so future sessions don't repeat the same mistake.

---

## 4. Cross-Reference with CAIO_IMPLEMENTATION_PLAN.md

### 4.1 Gaps in the Implementation Plan (v4.5)

The implementation plan needs these updates to reflect the Redis bridge:

| Section | Line | Current Content | Should Be |
|---------|------|----------------|-----------|
| Safety Controls | 707 | `Shadow emails \| .hive-mind/shadow_mode_emails/ \| Review before enabling real sends` | `Shadow emails \| core/shadow_queue.py → Redis (Upstash) primary, .hive-mind/shadow_mode_emails/ fallback \| Review in /sales dashboard` |
| Key Files | 663-695 | Missing `core/shadow_queue.py` | Add: `Shadow email queue (Redis bridge) \| core/shadow_queue.py` |
| Phase 2B | 80 | `5 emails queued to shadow_mode_emails` | `5 emails queued via shadow_queue (Redis + disk)` |
| Current API Status | 652 | `Redis (Upstash) \| WORKING \| 62ms from Railway` | `Redis (Upstash) \| WORKING \| 62ms from Railway. Also serves as shadow email queue bridge (local pipeline ↔ Railway dashboard)` |

### 4.2 Phase 4E Dependencies

Phase 4E "Supervised Live Sends" requires the Head of Sales to review emails at `/sales`. The shadow queue fix is a **critical dependency** for Phase 4E:

```
Phase 4E Step 1: Run pipeline → generates emails → shadow_queue.push() → Redis
Phase 4E Step 2: HoS reviews at /sales → shadow_queue.list_pending() → Redis → emails appear
Phase 4E Step 3: HoS approves → shadow_queue.update_status() → Redis
Phase 4E Step 4: OPERATOR dispatches approved emails via Instantly
```

Without the shadow queue fix, Step 2 fails silently (empty dashboard).

### 4.3 Code-Plan Contradictions

| Plan Says | Code Does | Resolution |
|-----------|-----------|------------|
| "Shadow emails stored at `.hive-mind/shadow_mode_emails/`" | Emails stored in Redis AND disk | Plan needs update — Redis is primary |
| No mention of `core/shadow_queue.py` in Key Files | Module exists, is critical | Add to Key Files section |
| "Send stage: 5 emails queued to shadow_mode_emails" | Send stage calls `shadow_queue.push()` which writes to Redis + disk | Plan needs update — describe Redis bridge |

---

## 5. Dashboard Email Refresh — How It Works Now

### 5.1 Data Flow (End-to-End)

```
1. Pipeline runs locally (Windows):
   execution/run_pipeline.py → _stage_send()

2. For each lead in approved campaigns:
   Creates shadow_email dict with: email_id, to, subject, body, recipient_data, context, status="pending"

3. Writes to shadow queue:
   core/shadow_queue.push(shadow_email, shadow_dir=.hive-mind/shadow_mode_emails/)
   → Redis SET {prefix}:shadow:email:{email_id} = JSON
   → Redis ZADD {prefix}:shadow:pending_ids {email_id} = UTC_timestamp
   → disk write to .hive-mind/shadow_mode_emails/{email_id}.json

4. Dashboard on Railway reads:
   GET /api/pending-emails → core/shadow_queue.list_pending()
   → Redis ZREVRANGE {prefix}:shadow:pending_ids → get top N pending IDs
   → Redis GET {prefix}:shadow:email:{id} for each
   → Filter status=="pending"
   → Return to dashboard

5. HoS approves/rejects:
   POST /api/emails/{id}/approve → core/shadow_queue.update_status()
   → Redis SET updates status field
   → Redis ZREM removes from pending index
   → Disk update if file exists
```

### 5.2 Fallback Chain

The shadow queue has a 3-tier fallback for reads:

1. **Redis sorted set index** — fast O(log N) retrieval of pending IDs
2. **Redis SCAN** — catches stray keys not in the index (migration scenario)
3. **Filesystem glob** — last resort if Redis is completely unavailable

### 5.3 Dashboard Frontend Behavior

`dashboard/hos_dashboard.html` → `fetchPendingEmails()`:
- Polls `/api/pending-emails?token={token}&_ts={timestamp}` on page load
- Auth via `X-Dashboard-Token` header or `?token=` query param
- Displays email cards with recipient name, email, company, title, subject, body, tier, score
- Shows RAMP MODE banner (fetched from `/api/operator/status`)

### 5.4 Verification After Changes

To verify emails appear on Railway:

```bash
# Check pending emails count (requires DASHBOARD_AUTH_TOKEN)
curl -s "https://caio-swarm-dashboard-production.up.railway.app/api/pending-emails?token=<TOKEN>" | python -m json.tool

# Expected response:
# {
#   "count": 4,
#   "pending_emails": [...],
#   "_shadow_queue_debug": {
#     "prefix": "caio:production:context",
#     "redis_connected": true,
#     "redis_returned": 4
#   }
# }
```

---

## 6. Files Modified (Complete List)

| File | Commit | Change |
|------|--------|--------|
| `core/shadow_queue.py` | `077e34b`, `2d074c6` | **CREATED** then **FIXED** — Redis-backed shadow email queue with prefix fix |
| `dashboard/health_app.py` | `077e34b`, `2d074c6` | Updated pending-emails/approve/reject endpoints to use shadow_queue, added debug info |
| `execution/run_pipeline.py` | `077e34b` | Send stage now calls `shadow_queue.push()` instead of direct disk write |
| `docs/HOS_EMAIL_REVIEW_GUIDE.md` | `ccca9b4` | **CREATED** — HoS email review checklist and feedback template |
| `CLAUDE.md` | `ccca9b4`, `ce7a533` | Added Redis bridge architecture, prefix pitfall, pre-flight checklist |

---

## 7. What Codex Should Do Next

### 7.1 Update CAIO_IMPLEMENTATION_PLAN.md

Apply the gap fixes from Section 4.1:
1. Add `core/shadow_queue.py` to Key Files section (after line 695)
2. Update Safety Controls line 707 to mention Redis bridge
3. Update Phase 2B results to mention shadow_queue
4. Update Redis entry in Current API Status to mention shadow email queue

### 7.2 Ensure Dashboard Email Auto-Refresh

The current dashboard does NOT auto-refresh. The HoS must manually reload the page to see new emails. For a better UX during supervised ramp:

**Option A (Polling)**: Add a `setInterval` in `hos_dashboard.html` that calls `fetchPendingEmails()` every 30-60 seconds. Simple, no backend changes needed.

**Option B (WebSocket)**: The dashboard already has a WebSocket at `/ws`. Emit a `new_email` event when `shadow_queue.push()` succeeds. Frontend listens and refreshes.

**Recommendation**: Option A (polling) — simplest, no new dependencies, sufficient for 5 emails/day ramp volume.

### 7.3 Verify Redis Health

Before any pipeline run, verify Redis connectivity:

```bash
# Check Redis health via dashboard API
curl -s "https://caio-swarm-dashboard-production.up.railway.app/api/health/ready"
# Should include: "redis": {"status": "connected", "latency_ms": ...}
```

### 7.4 Run the First Pipeline Review Cycle

Execute the Phase 4E first live review:

```bash
# Step 1: Run pipeline (local)
echo yes | python execution/run_pipeline.py --mode production --source "wpromote" --limit 3

# Step 2: Verify emails in Redis (local)
python -c "
from core.shadow_queue import list_pending
emails = list_pending(limit=20)
print(f'Pending emails: {len(emails)}')
for e in emails:
    print(f'  {e[\"email_id\"]}: {e[\"to\"]} — {e[\"subject\"][:50]}')
"

# Step 3: Verify emails on Railway dashboard
curl -s "https://caio-swarm-dashboard-production.up.railway.app/api/pending-emails?token=<TOKEN>" | python -c "
import json, sys
data = json.load(sys.stdin)
print(f'Count: {data[\"count\"]}')
print(f'Debug: {data[\"_shadow_queue_debug\"]}')
"

# Step 4: HoS reviews at /sales and approves/rejects
# Step 5: First live dispatch after approval
```

---

## 8. Known Issues & Edge Cases

| Issue | Severity | Status |
|-------|----------|--------|
| Dashboard doesn't auto-refresh (manual page reload needed) | LOW | Open — add polling interval |
| `_shadow_queue_debug` field exposed in API response | LOW | Intentional for now — remove after stabilization |
| Filesystem fallback writes orphaned files on Railway | LOW | Files are ephemeral (container restart clears them) |
| No TTL on Redis shadow email keys | LOW | Manual cleanup needed if keys accumulate — add EXPIRE in future |
| Archived emails in `archived_20260218/` still have old template artifacts | LOW | Historical data, not blocking |

### 8.1 Archived Email Quality Issues (Pre-HoS Rewrite)

Shadow emails generated before the HoS requirements integration (commit `10cc82c`) contain template artifacts:

- `"Reference their tech stack"` appears literally in email body (unfilled template variable)
- `"Director of Strategic Saless"` typo in one email
- Wrong sender: "Chris Daigle, CEO" instead of "Dani Apgar, Chief AI Officer"
- Wrong booking link: `calendly.com/chiefaiofficer/intro` instead of `caio.cx/ai-exec-briefing-call`
- Missing CAN-SPAM footer

These are in the `archived_20260218/` directory and are NOT blocking. Post-HoS emails use the correct templates.

---

## 9. Architectural Rule (ENFORCE THIS)

**Every piece of data that must be visible on BOTH local AND Railway MUST go through Redis.**

This is documented in CLAUDE.md under "CRITICAL: Local ↔ Railway Filesystem Constraint (ARCHITECTURAL LAW)".

The shadow queue (`core/shadow_queue.py`) is the canonical pattern. Any new cross-environment feature must:

1. Use Redis as primary data store (via Upstash)
2. Use `CONTEXT_REDIS_PREFIX` (not `STATE_REDIS_PREFIX`) for key prefixes
3. Include filesystem fallback for when Redis is unavailable
4. Include `_debug` diagnostic fields in API responses
5. Be verified on Railway after deployment (not just locally)

---

*Handoff prepared by Claude Opus 4.6 — 2026-02-18*
