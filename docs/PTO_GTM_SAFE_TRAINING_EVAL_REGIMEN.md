# CAIO Safe Training + Evaluation Regimen (PTO/GTM, Non-Technical)

**Audience**: PTO/GTM operator  
**Aligned with**: `docs/CAIO_TASK_TRACKER.md` (Weekly Focus, Week of 2026-02-23)  
**Goal**: Train safely, run deterministic evaluation, and graduate to autonomy without risking live contacts.

---

## 1) Your Operating Role

- You are the final go/no-go owner for each live cycle.
- HoS owns approval/rejection quality decisions inside `/sales`.
- System safety gates must pass before every live cycle.

---

## 2) One-Time Environment Confirmation (Required)

Confirm in deployed env (staging + production):

- `DASHBOARD_AUTH_STRICT=true`
- `REDIS_REQUIRED=true`
- `INNGEST_REQUIRED=true`
- `PENDING_QUEUE_MAX_AGE_HOURS=72` (or your chosen SLA-backed value)

Confirm token and URLs are correct:

- `CAIO_STAGING_URL`, `CAIO_STAGING_TOKEN`
- `CAIO_PROD_URL`, `CAIO_PROD_TOKEN`

---

## 3) Weekly Implementation Tracker (This Week)

- [ ] Deploy structured rejection-tag patch to Railway.
- [ ] Verify `/api/rejection-tags` returns tags in production.
- [ ] Verify `/sales` reject flow blocks rejection unless a tag is selected.
- [ ] Confirm clean-days ramp config is active (`mode=clean_days`, `clean_days_required=3`).
- [ ] Run supervised Tier_1 cycles and capture outcomes.
- [ ] Run replay + smoke gates after each deploy touching queue/approval/dispatch logic.

---

## 4) Daily Pre-Flight Ritual (Before Any Live Cycle)

Run in `D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm`:

```powershell
python scripts/deployed_full_smoke_checklist.py --base-url $env:CAIO_PROD_URL --token $env:CAIO_PROD_TOKEN
python scripts/trace_outbound_ghl_queue.py --base-url $env:CAIO_PROD_URL --token $env:CAIO_PROD_TOKEN
```

Proceed only if:

- Smoke checklist passes.
- Queue trace shows expected pending items.
- No obvious queue drift/noise.

If drift/noise appears:

```powershell
python scripts/cleanup_pending_queue.py --base-url $env:CAIO_PROD_URL --token $env:CAIO_PROD_TOKEN --apply
```

---

## 5) Supervised Live Cycle (Step-by-Step)

1. Run a small production pipeline batch.

```powershell
echo yes | python execution/run_pipeline.py --mode production --source "wpromote" --limit 2
```

2. Open `/sales` with token and review cards.
3. HoS approves/rejects each card:
   - Approve only real, high-quality Tier_1 cards.
   - Reject with a required structured tag.
4. Execute live dispatch (only after approvals are complete).

```powershell
python -m execution.operator_outbound --motion outbound --live
```

5. Verify sent evidence in GHL conversations for approved contacts.
6. Record outcomes in your daily log:
   - Approved count
   - Rejected count by tag
   - Sent count
   - Any anomaly observed

---

## 6) Approval SLA (Recommended Default)

- First review SLA: within 30 minutes of pending card creation.
- Final decision SLA: within 2 hours.
- If not decided within SLA, do not execute next live cycle until backlog is resolved.

Confirmed owner schedule:

- Daily supervised review window: 15:00 EST.
- Daily HoS approver owner: PTO.
- SLA owner for unresolved pending cards: PTO.
- Escalation for smoke/gate failure: Slack.

---

## 7) Stale Card Handling (Recommended Default)

- Stale cards (`>72h`) are non-actionable for live dispatch.
- Keep them out of live queue by hygiene cleanup using tag:
  - `queue_hygiene_non_actionable`
- Do not re-approve stale cards without fresh regenerated copy.

---

## 8) Evaluation Gates (Safety Net)

After deploys touching queue/approval/dispatch/ramp:

```powershell
python scripts/replay_harness.py --min-pass-rate 0.95
python -m pytest -q tests/test_runtime_determinism_flows.py tests/test_operator_ramp_logic.py
python scripts/deployed_full_smoke_matrix.py --staging-url $env:CAIO_STAGING_URL --staging-token $env:CAIO_STAGING_TOKEN --production-url $env:CAIO_PROD_URL --production-token $env:CAIO_PROD_TOKEN
```

Pass condition:

- Replay pass rate >= 0.95
- Pytest zero failures for target suite
- Smoke matrix passes on staging and production

---

## 9) Ramp Graduation Rule (Now Recommended in Code)

Stay in ramp until **3 clean supervised live days** are recorded.

Clean day means:

- Live run (not dry run)
- No pending-approval hold
- No errors
- At least one actual dispatch completed

Only after 3 clean days:

- Consider expanding beyond Tier_1
- Increase daily cap gradually

---

## 10) Immediate Inputs Needed From You (PTO/GTM)

- Confirmed: daily HoS approver owner is PTO (you).
- Confirmed: supervised operating window is 15:00 EST.
- Confirmed: unresolved pending-card SLA owner is PTO (you).
- Confirmed: smoke/gate escalation channel is Slack.
