# CAIO Alpha Swarm — PTO/GTM Next Steps Task Reference

**Date**: 2026-02-19 (updated 2026-02-19 evening)
**Primary audience**: Non-technical PTO / GTM lead
**Source of truth**: `CAIO_IMPLEMENTATION_PLAN.md` (v4.5) + current deployed checks
**Latest deploy**: commit `0f0e0a9` (2026-02-19)
**Weekly execution runbook**: `docs/PTO_GTM_SAFE_TRAINING_EVAL_REGIMEN.md`

---

## 1) Current State Assessment (What is true now)

### Green (working and verified)
- Production deployed auth/runtime smoke is passing (`scripts/deployed_full_smoke_checklist.py`).
- Protected APIs require token (`401` unauth, `200` with token).
- `/sales` auto-refresh wiring and pending refresh timestamp checks are passing.
- Pending queue is visible and classifiable (classifier + campaign_ref metadata present).
- GHL route now supports auto contact resolve/upsert before send on approval (commit `1c9f682` behavior).
- **Dashboard v3.0 live**: 4-tab UI (Overview, Email Queue, Campaigns, Settings) wired to 50+ API endpoints.
- **Backend compliance checks live**: every pending email checked for Reply STOP, signature, CTA, footer — displayed in approval modal.
- **Reply STOP to unsubscribe now in canonical footer**: commit `0f0e0a9` fixed missing line (was present in compliance checks but absent in actual footer).
- **2 real pending emails (Wpromote)**: celia.kettering, andrew.mahr — ALL 4/4 compliance checks PASS.
- **Ramp mode**: Day 2/3, tier_1 only, 5/day limit, 0 sent today.
- **Redis healthy**: connected, 41ms latency.
- **Cadence engine**: 5 leads enrolled at step_1, 5 actions due today.

### Yellow (watch closely)
- Queue shows 37 pending total but only 2 visible after hygiene filters (35 excluded as stale/canary/non-tier_1). Expected behavior but monitor for drift.
- Scorecard metrics mostly at zero (no live sends completed yet). Will populate once sends go through.
- Token was historically exposed in docs/screenshots; rotation hygiene must stay strict.

### Red (must avoid)
- Do not graduate to full autonomy yet.
- Do not widen beyond Tier_1 until 3 clean supervised live days are complete.
- Do not run live sends if smoke or queue integrity checks fail.

---

## 2) Decision: Continue Supervised Tier_1 Go-Live?

**Yes, continue Tier_1 supervised go-live**, with strict guardrails:
- Keep ramp mode at 5/day, Tier_1 only.
- Keep Gatekeeper approval required.
- Keep pre-send HoS review mandatory from `/sales`.
- Stop immediately on any queue drift, classifier mismatch, or deliverability anomaly.

---

## 3) What You Should Focus On (PTO/GTM Priority Order)

1. **Operational safety discipline**
- Run pre-flight smoke before each live cycle.
- Confirm `/api/pending-emails` debug shows Redis active and no unhealthy merge behavior.

2. **Message quality and campaign integrity**
- HoS must approve/reject with explicit reason tags (not just yes/no).
- Reject any malformed body, placeholder text, or campaign mismatch.

3. **Controlled live learning**
- Keep live sends in canary volume (Tier_1 only) while collecting feedback signals.
- Use rejection reasons to tune prompts/templates weekly.

4. **Risk controls and secrets**
- Keep strict auth/runtime flags enabled.
- Rotate dashboard tokens on a schedule and after any exposure.

---

## 4) Task Board (Non-Technical Execution)

## A. Every Live Cycle (Required)
- [ ] Run production smoke:
  - `python scripts/deployed_full_smoke_checklist.py --base-url https://caio-swarm-dashboard-production.up.railway.app --token <DASHBOARD_AUTH_TOKEN>`
- [ ] Run queue trace:
  - `python scripts/trace_outbound_ghl_queue.py --base-url https://caio-swarm-dashboard-production.up.railway.app --token <DASHBOARD_AUTH_TOKEN>`
- [ ] Confirm queue is expected (right leads, right tier, right route labels).
- [ ] HoS reviews and approves only high-quality Tier_1 cards.
- [ ] Execute supervised send cycle.
- [ ] Verify sent messages appear in GHL contact conversation.
- [ ] Log outcomes (approved count, rejected count, sent count, issues).

## B. Daily End-of-Day (Required)
- [ ] Capture KPIs: opens, replies, bounce, unsubscribe, meetings.
- [ ] Capture top 3 rejection reasons from HoS.
- [ ] Capture queue anomalies (if any) and whether cleanup was needed.
- [ ] Decide next-day action: continue / hold / rollback.

## C. Weekly (Required)
- [ ] Prompt/template tuning based on rejection reasons and reply outcomes.
- [ ] Review exclusion rules (customer domains, do-not-contact, subdomains).
- [ ] Confirm auth smoke + replay harness still green after any code changes.

---

## 5) Safe Training Without Compromising Real Contacts

Use a 3-lane model:

1. **Lane A: Offline/Shadow training (no customer risk)**
- Run pipeline in review mode, no live dispatch.
- Train copy quality and classifier consistency from HoS feedback.

2. **Lane B: Canary live training (controlled risk)**
- Tier_1 only, low daily cap.
- Manual HoS approval on every card.
- Immediate stop on anomalies.

3. **Lane C: Deterministic regression training**
- Re-run replay harness + critical pytest pack after patch changes.
- Ship only when gate scores remain above threshold.

---

## 6) Stop Conditions (Immediate No-Go)

Stop live sends immediately if any are true:
- Smoke fails for auth/readiness/runtime.
- Queue classifier/campaign metadata is inconsistent.
- Same lead reappears unexpectedly after send (dedup/regression symptom).
- Bounce/unsubscribe spike beyond your thresholds.
- HoS flags systemic formatting/personalization failure.

---

## 7) Exit Criteria to Expand Beyond Tier_1

Only expand when all pass:
- [ ] 3 clean supervised days completed.
- [ ] No queue drift incidents in those 3 days.
- [ ] KPI floors met (reply/bounce/unsubscribe guardrails).
- [ ] HoS confirms copy quality is stable.
- [ ] Replay + smoke remain green after latest deploy.

Then:
- Increase daily cap gradually.
- Introduce Tier_2 in a canary slice (not full unlock at once).

---

## 8) Inputs Needed From You (PTO) Now

- [ ] Confirm final production/staging dashboard tokens are rotated and stored safely.
- [ ] Confirm strict env flags remain enforced in deployed env.
- [ ] Confirm HoS approves the quality rubric and rejection reason taxonomy.
- [ ] Confirm go/no-go owner for each live cycle (single accountable approver).

---

## 9) Recommended Next 72-Hour Plan

### Day 1 (2026-02-18) — COMPLETED
- [x] Ramp mode activated. Supervised send infrastructure deployed.
- [x] Dashboard v3.0 deployed with 4-tab UI.
- [x] HoS reviewed some emails (2 approved by dashboard_user, 2 by API, 4 rejected by hygiene bot).
- [x] GHL contact resolve/upsert verified for approved cards.
- Finding: compliance checks showed "Reply STOP" missing from footer — logged for Day 2 fix.

### Day 2 (2026-02-19) — IN PROGRESS
- [x] Copy quality improvement applied: "Reply STOP to unsubscribe." added to canonical footer (commit `0f0e0a9`).
- [x] All 4/4 compliance checks now PASS on both real pending emails.
- [x] Dashboard compliance indicators live in approval modal.
- [ ] **NEXT**: HoS reviews 2 Wpromote emails via `/sales?token=<TOKEN>#emails`.
- [ ] **NEXT**: If quality good, approve and execute supervised send.
- [ ] **NEXT**: Verify sent evidence in GHL conversation.
- [ ] **NEXT**: Log outcomes (approved, rejected, sent, issues).

### Day 3 (2026-02-20)
- Repeat with same cap.
- Run production smoke before cycle.
- If clean for 3/3 days, prepare controlled Tier_2 canary plan.

### Best Next Step (Assessment)
**The recommended immediate action is: Execute a supervised send cycle.**

All blockers are cleared:
1. Compliance gap fixed and deployed.
2. 2 real Tier_1 emails ready (Wpromote contacts, 4/4 compliance PASS).
3. Dashboard v3.0 live with compliance indicators for HoS review.
4. Ramp mode Day 2 — capacity for 5 sends, 0 used today.

Execution path:
1. Open `/sales?token=<TOKEN>#emails` in browser.
2. Review each email card — verify personalization, CTA, compliance badge (all green).
3. Click "Approve & Send" on each quality card.
4. Check GHL for sent conversation evidence.
5. Log results in this document under Day 2.
