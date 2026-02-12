# CAIO Dashboard Email Refresh: Root Cause and Sustainable Fix

## Executive Summary
- The dashboard refresh issue was primarily frontend polling and state-handling drift, not a failure in email generation.
- Queue generation is healthy (`.hive-mind/gatekeeper_queue` and `.hive-mind/shadow_mode_emails` both contain pending items).
- The fix now makes refresh deterministic, prevents stale UI states, and bridges queue sources so training can continue reliably before full evaluation-set runs.

## Deep Diagnostic Findings

### 1. Frontend Polling Bug (Primary)
- File: `dashboard/hos_dashboard.html`
- Prior behavior: auto-refresh timer only logged `"Auto-refresh..."` and did not call the API.
- Impact: inbox appeared frozen unless full page reload happened.

### 2. Frontend Stale State Bug (Primary)
- File: `dashboard/hos_dashboard.html`
- Prior behavior: in-memory `pendingEmails` updated only when backend returned non-empty list.
- Impact: stale cards remained visible and gave false perception of refresh failures.

### 3. Wrong Endpoint in Bulk Approve (Secondary)
- File: `dashboard/hos_dashboard.html`
- Prior behavior: bulk action called `/api/approve` (non-matching route).
- Impact: low-priority bulk approvals silently failed or partially failed.

### 4. Queue Source Divergence (Systemic)
- Files: `dashboard/health_app.py`, runtime queue directories
- Prior behavior: dashboard read only `shadow_mode_emails`; upstream could write to `gatekeeper_queue`.
- Impact: generated emails could exist but not appear in dashboard.

## Implemented Fixes

### Backend
- File: `dashboard/health_app.py`
- Added `_sync_gatekeeper_queue_to_shadow(...)` to mirror pending queue files from `gatekeeper_queue` into `shadow_mode_emails` when missing.
- Added cache-control headers on `GET /api/pending-emails`:
  - `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`
  - `Pragma: no-cache`
  - `Expires: 0`
- `GET /api/pending-emails` now also returns:
  - `synced_from_gatekeeper`
  - `refreshed_at`

### Frontend
- File: `dashboard/hos_dashboard.html`
- Replaced no-op refresh with deterministic polling:
  - `startAutoRefresh()` invokes API every 15s and on tab-visibility return.
- Added cache-busting + no-store fetch path for pending emails.
- Fixed stale state handling by always clearing/rebuilding list from server response.
- Updated approve/reject flows to refresh from server after successful mutation.
- Fixed bulk approve endpoint usage to call `/api/emails/{id}/approve`.

### Test Coverage
- File: `tests/test_runtime_determinism_flows.py`
- Added/updated deterministic checks for:
  - `/api/pending-emails` cache headers.
  - gatekeeper-to-shadow queue sync behavior.

## Validation Results
- Command: `python -m pytest tests/test_runtime_determinism_flows.py -q`
- Result: `2 passed, 1 skipped`
- Command: `python execution/diagnose_email_pipeline.py`
- Result: pipeline healthy, pending queue present.

## Sustainable Solution for Agent Training (Pre-Evaluation)

### A. Treat Dashboard Approval as a Supervised Training Loop
- Approve/reject feedback already writes to audit logs in `.hive-mind/audit`.
- Keep this active daily to build correction signals while running in controlled send mode.

### B. Make Queue Contract Explicit
- Define one canonical queue schema document and keep adapters only at boundaries.
- Keep bridge sync as short-term resilience, but converge producers to one source of truth to reduce drift.

### C. Replay Harness Gate Before Major Iterations
- For each code change:
  1. Replay Golden Set scenarios.
  2. Judge tool selection + groundedness + completeness.
  3. Block merge on score regression threshold.

### D. Observability Minimum for Reliability
- Ensure every queued item and decision path logs:
  - correlation ID
  - case ID
  - tool calls
  - final action outcome (approved/rejected/sent/simulated)

## Recommended Next Steps (Ordered)
1. Run a 24-hour soak test with live dashboard polling and confirm no stale UI incidents.
2. Standardize producer writes to a single queue contract (deprecate dual-write drift).
3. Expand Golden Set scenarios around approval edge cases (empty queues, malformed payloads, retries).
4. Add CI gate to fail builds when replay-judge pass rate drops below threshold.
5. Review feedback taxonomy quality weekly with Head of Sales to improve agent learning labels.

## Inputs Needed from Product Technical Officer / Head of Sales
- Confirm allowed auto-approval policy for low-priority leads.
- Confirm rejection reason taxonomy (to improve learning consistency).
- Confirm evaluation pass/fail thresholds by phase (alpha, beta, production).
- Confirm whether Redis/Inngest-backed async retries should be enabled now or deferred until post-alpha.
