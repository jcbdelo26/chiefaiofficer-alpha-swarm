# CAIO Alpha Swarm: Major Inputs Required from Leadership

Date: February 9, 2026  
Purpose: Unblock remaining implementation and improve decision quality/reliability.

## 0) Decision Log (Confirmed)

1. Replay gate threshold: `0.95` minimum pass rate.
2. Critical evaluation failures: hard-fail conditions.
3. Redis and Inngest: required as production reliability baseline.
4. Router split + parity tests: approved as next engineering milestone.

## 1) Inputs Needed from You (Product/Technical Owner)

1. Replay Gate Policy
- Confirm required pass rate for merge/release (`0.95` currently in CI).
- Confirm whether critical-tool mismatches should be hard-fail even if pass rate is above threshold.

2. Environment Strategy
- Confirm production `REDIS_URL` rollout timeline (staging first vs direct production cutover).
- Confirm whether Redis is mandatory for production (fail-start if unavailable) or best-effort fallback is acceptable.

3. Trace Retention and Compliance
- Confirm retention window for trace envelopes (e.g., 14/30/90 days).
- Confirm approved redaction policy for payload summaries (current default masks auth/secrets/tokens).

4. Release Scorecard Ownership
- Confirm who owns weekly sign-off on Golden Set scorecards.
- Confirm target date for enforcing scorecards as release blocker in all branches.

5. Simulation Boundary
- Confirm which workflows may remain simulated in production-adjacent environments.
- Confirm timeline to remove simulated execution from primary orchestration paths.

## 2) Inputs Needed from Head of Sales

1. Approval Rubric (Deterministic)
- Define explicit approve/reject checklist for outbound emails:
  - tone
  - personalization depth
  - value proposition clarity
  - CTA style
  - compliance constraints

2. Rejection Taxonomy (Training Quality)
- Provide canonical rejection categories and examples (5-10 per category).
- Define which categories should trigger automatic regeneration vs manual rewrite.

3. Messaging Standards
- Provide approved subject/body exemplars by segment/tier.
- Define forbidden claims and phrasing for each ICP segment.

4. Operational Limits
- Confirm daily approval capacity targets and SLA (time-to-approve).
- Confirm acceptable queue aging thresholds before escalation.

5. Meeting Prep Expectations
- Define minimum required fields for call prep quality:
  - summary format
  - pain points depth
  - objection prep quality bar
  - confidence threshold for auto-population

## 3) Decisions Needed in Next Review

1. Approve or adjust current replay threshold and hard-fail conditions.
2. Approve Redis production policy (required vs fallback).
3. Approve HoS deterministic rubric and rejection taxonomy.
4. Approve timeline for `health_app.py` router split completion and endpoint parity gate.

## 4) Recommended Cadence

- Weekly (30 min): Evaluation scorecard + regression review.
- Twice weekly (15 min): HoS feedback loop on rejects/edits.
- Per release: Deterministic judge run + sign-off checkpoint.
