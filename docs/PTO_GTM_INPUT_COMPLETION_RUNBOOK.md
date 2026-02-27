# PTO/GTM Input Completion Runbook (Non-Technical)

**Purpose:** Close the remaining operational inputs before next supervised execution.
**Scope:** Production `/sales` review proof, pending-card decisions, token rotation scheduling, and script auth compatibility.

---

## Input Status Snapshot

- Input 1: **OPEN** — Andrew approved-send proof in GHL conversation
- Input 2: **OPEN** — Pending queue decisions with structured rejection tags
- Input 3: **OPEN** — Final `DASHBOARD_AUTH_TOKEN` rotation date/time
- Input 4: **DONE** — `scripts/trace_outbound_ghl_queue.py` updated to header-token auth (`X-Dashboard-Token`), with tests passing

Verification for Input 4:
- `python -m pytest -q tests/test_trace_outbound_ghl_queue.py`
- Result: `2 passed`

---

## Input 1 — Confirm Andrew Email Is Visible in GHL Conversation

1. Open production dashboard:
   - `https://caio-swarm-dashboard-production.up.railway.app/sales`
2. If prompted, enter production `DASHBOARD_AUTH_TOKEN`.
3. In `/sales`, locate Andrew row (`andrew.mahr@wpromote.com`) in recently reviewed/history.
4. Open GHL:
   - `https://app.gohighlevel.com`
5. Select correct CAIO sub-account/location.
6. Go to `Contacts` and search `andrew.mahr@wpromote.com`.
7. Open contact -> `Conversations`.
8. Confirm outbound message exists after approval timestamp and content matches approved draft.
9. Capture proof screenshots:
   - `/sales` approved item
   - GHL conversation with sent message
10. Mark complete:
    - `Input 1 complete: Andrew message confirmed in GHL conversation.`

---

## Input 2 — Action Remaining Pending Cards with Structured Tags

1. Stay in `/sales` -> `Pending Email Approvals`.
2. Open each card via `Edit & Preview`.
3. Decision rule:
   - Approve when copy quality + personalization are acceptable.
   - Reject when quality/personalization/compliance is weak.
4. If rejecting:
   - Select required rejection tag from dropdown.
   - Add short, concrete reason in feedback.
   - Submit reject.
5. Continue until current pending queue is fully actioned.
6. Report outcome:
   - `Approved: X`
   - `Rejected: Y`
   - `Top rejection tags: [...]`

---

## Input 3 — Final `DASHBOARD_AUTH_TOKEN` Rotation Date

1. Pick low-risk maintenance window (15–30 minutes), outside active send/review period.
2. Use exact format:
   - `YYYY-MM-DD HH:MM EST`
3. Confirm scope:
   - staging + production
4. Share one-line confirmation:
   - `Token rotation scheduled: <date/time EST>`

Default recommendation:
- `15:00 EST` ops window.

---

## Input 4 — Script Patch Permission and Execution (Completed)

Completed change:
- `scripts/trace_outbound_ghl_queue.py` no longer sends `?token=...`
- Uses `X-Dashboard-Token` header for protected API calls
- Keeps functional query params (example: `include_non_dispatchable=true`)

What changed:
- From:
  - `GET /api/pending-emails?token=<token>`
- To:
  - `GET /api/pending-emails` with header `X-Dashboard-Token: <token>`

No backend API contract changes were required.

---

## Quick Command (Post-Patch Queue Trace)

```powershell
python scripts/trace_outbound_ghl_queue.py --base-url https://caio-swarm-dashboard-production.up.railway.app --token <PROD_DASHBOARD_AUTH_TOKEN>
```

---

## Done Criteria

1. Input 1 pass: Andrew approved outbound is visible in GHL conversation.
2. Input 2 pass: all pending cards actioned, rejects include required tags.
3. Input 3 pass: token rotation date/time confirmed.
4. Input 4 pass: header-auth script patch merged and tested (complete).

