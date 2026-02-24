# Staging Webhook Strict-Mode Rollout

This is the exact checklist to enable and validate webhook strict mode in **staging** before production.

## Scope
- Provider webhooks:
  - `/webhooks/instantly/*`
  - `/webhooks/heyreach`
  - `/webhooks/rb2b`
  - `/webhooks/clay`
- Runtime policy:
  - `WEBHOOK_SIGNATURE_REQUIRED=true`
- Validation scripts:
  - `scripts/webhook_strict_smoke.py`
  - `scripts/deployed_full_smoke_checklist.py`
  - `scripts/trace_outbound_ghl_queue.py`

---

## 1) Pre-Change Snapshot (Required)

Run and save outputs:

```powershell
python scripts/deployed_full_smoke_checklist.py --base-url <STAGING_URL> --token <STAGING_DASHBOARD_AUTH_TOKEN>
python scripts/trace_outbound_ghl_queue.py --base-url <STAGING_URL> --token <STAGING_DASHBOARD_AUTH_TOKEN>
python scripts/webhook_strict_smoke.py --base-url <STAGING_URL> --dashboard-token <STAGING_DASHBOARD_AUTH_TOKEN> --expect-webhook-required false
```

Expected now (before rollout):
- baseline smoke should pass.
- webhook strict smoke should report `expect_webhook_required=false`.

---

## 2) Staging Env Changes

Set these in Railway **staging** service variables:

```text
WEBHOOK_SIGNATURE_REQUIRED=true
WEBHOOK_BEARER_TOKEN=<LONG_RANDOM_SECRET>
INSTANTLY_WEBHOOK_SECRET=<optional_if_using_hmac>
RB2B_WEBHOOK_SECRET=<optional_if_using_hmac>
CLAY_WEBHOOK_SECRET=<optional_if_using_hmac>
HEYREACH_UNSIGNED_ALLOWLIST=<true_or_false>
```

Notes:
- If you do not manage HMAC signatures for Instantly/RB2B/Clay, bearer token fallback is required.
- HeyReach does not support custom webhook headers. In strict mode:
  - set `HEYREACH_UNSIGNED_ALLOWLIST=true` as a temporary controlled bypass, or
  - keep it `false` only when protected ingress/signature strategy is implemented.
- Keep `DASHBOARD_AUTH_STRICT=true`, `REDIS_REQUIRED=true`, `INNGEST_REQUIRED=true`.

---

## 3) Deploy + Runtime Validation

After staging redeploy:

```powershell
python scripts/webhook_strict_smoke.py `
  --base-url <STAGING_URL> `
  --dashboard-token <STAGING_DASHBOARD_AUTH_TOKEN> `
  --expect-webhook-required true `
  --webhook-bearer-token <WEBHOOK_BEARER_TOKEN>
```

Expected pass conditions:
- `runtime_webhook_required_matches_expectation` -> pass
- `runtime_webhook_ready_when_required` -> pass
- unauthenticated Instantly/Clay/RB2B webhook calls blocked (`401` or `503`)
- bearer-authenticated Instantly/Clay calls accepted (not `401`/`503`)

If enforcing HeyReach hard-auth strategy in this phase:

```powershell
python scripts/webhook_strict_smoke.py `
  --base-url <STAGING_URL> `
  --dashboard-token <STAGING_DASHBOARD_AUTH_TOKEN> `
  --expect-webhook-required true `
  --webhook-bearer-token <WEBHOOK_BEARER_TOKEN> `
  --require-heyreach-hard-auth
```

---

## 4) Full Staging Gate (Post-Change)

Run complete staging operational checks:

```powershell
python scripts/deployed_full_smoke_checklist.py --base-url <STAGING_URL> --token <STAGING_DASHBOARD_AUTH_TOKEN>
python -m pytest -q tests/test_webhook_signature_enforcement.py tests/test_instantly_webhook_auth.py
python scripts/replay_harness.py --min-pass-rate 0.95
```

Required:
- all pass, no regression.

---

## 5) Production Promotion Criteria

Do **not** promote to production until all are true:
- Staging strict smoke passes.
- Staging full smoke passes.
- Replay gate >= `0.95`.
- HoS supervised cycle not degraded (quality + queue behavior stable).

---

## 6) Rollback Plan (Staging)

If critical issue detected:

1. Set:
```text
WEBHOOK_SIGNATURE_REQUIRED=false
```
2. Redeploy staging.
3. Re-run:
```powershell
python scripts/deployed_full_smoke_checklist.py --base-url <STAGING_URL> --token <STAGING_DASHBOARD_AUTH_TOKEN>
python scripts/webhook_strict_smoke.py --base-url <STAGING_URL> --dashboard-token <STAGING_DASHBOARD_AUTH_TOKEN> --expect-webhook-required false
```

---

## 7) Matrix Command (Staging + Production)

Use once staging is stable and you want one command across both environments:

```powershell
python scripts/webhook_strict_smoke_matrix.py `
  --staging-url <STAGING_URL> `
  --staging-dashboard-token <STAGING_DASHBOARD_AUTH_TOKEN> `
  --staging-webhook-required true `
  --staging-webhook-bearer-token <STAGING_WEBHOOK_BEARER_TOKEN> `
  --production-url <PRODUCTION_URL> `
  --production-dashboard-token <PRODUCTION_DASHBOARD_AUTH_TOKEN> `
  --production-webhook-required false `
  --production-webhook-bearer-token <PRODUCTION_WEBHOOK_BEARER_TOKEN>
```
