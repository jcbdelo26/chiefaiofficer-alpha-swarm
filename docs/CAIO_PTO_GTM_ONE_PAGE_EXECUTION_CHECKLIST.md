# CAIO Alpha Swarm: One-Page Execution Checklist (PTO/GTM)

Date: February 11, 2026  
Audience: Non-technical PTO/GTM lead  
Purpose: Exact operating ritual, plus current completion status.

---

## 1) Current Status (Executed)

- [x] Local production policy is strict: `.env` has `REDIS_REQUIRED=true` and `INNGEST_REQUIRED=true`.
- [x] Deployed production policy is strict: Railway variables updated to `REDIS_REQUIRED=true` and `INNGEST_REQUIRED=true`.
- [x] Production runtime checks passed:
  - `GET /api/health/ready` -> `200` with runtime dependencies `ready`.
  - `GET /api/runtime/dependencies` -> `ready: true`, Redis healthy, Inngest healthy, both required.
  - `GET /inngest` -> `mode: cloud`, `function_count: 4`.
- [x] Replay quality gate passed: `python scripts/replay_harness.py --min-pass-rate 0.95` -> `50/50`, pass rate `1.0`, `block_build=false`.
- [x] Reliability test suite passed: `python -m pytest -q tests/test_runtime_reliability.py tests/test_runtime_determinism_flows.py tests/test_trace_envelope_and_hardening.py tests/test_replay_harness_assets.py` -> `17 passed`.
- [x] Validator determinism hardening completed: `scripts/validate_runtime_env.py` now loads env files with `override=True`.
- [ ] Staging Inngest hardening is still pending (see section 2).

---

## 2) Inputs Needed From PTO (Only Remaining Blockers)

- [ ] Final **staging** `INNGEST_SIGNING_KEY`.
- [ ] Final **staging** `INNGEST_WEBHOOK_URL` (format: `https://<staging-domain>/inngest`).
- [ ] Confirm whether staging should now enforce strict policy immediately:
  - `INNGEST_REQUIRED=true` (recommended once keys/webhook are present).
- [ ] Follow UI navigation guide:
  - `docs/CAIO_PTO_INPUTS_NON_TECH_SETUP_GUIDE.md` section `4A`.

If these are not provided, staging remains in relaxed mode (`INNGEST_REQUIRED=false`) and cannot be treated as strict pre-prod.

---

## 3) Execution Ritual (Operator Steps)

- [ ] Step A: Confirm PTO inputs in section 2.
- [ ] Step B: Apply staging variables in deployment settings.
- [ ] Step C: Redeploy staging.
- [ ] Step D: Run staging validation:

```powershell
cd d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm
python scripts/validate_runtime_env.py --mode staging --env-file .env.staging --check-connections
```

- [ ] Step E: Verify staging endpoints:
  - `/api/runtime/dependencies?token=<DASHBOARD_AUTH_TOKEN>` -> `ready: true`.
  - `/api/health/ready` -> `200`.
  - `/inngest` -> `mode: cloud`, `function_count: 4`.
- [ ] Step F: Keep staging stable for 24h.
- [ ] Step G: Re-run replay gate before release:

```powershell
python scripts/replay_harness.py --min-pass-rate 0.95
```

---

## 4) No-Go Conditions (Stop Release)

- [ ] Required dependency unhealthy: `REDIS_REQUIRED=true` with Redis unhealthy.
- [ ] Required dependency unhealthy: `INNGEST_REQUIRED=true` with Inngest unhealthy.
- [ ] `/api/health/ready` returns `503`.
- [ ] Replay pass rate `< 95%`.
- [ ] `/inngest` not in cloud mode or function count unexpected.

---

## 5) Completion Report Template (Send to Leadership)

```text
CAIO Runtime Reliability Checkpoint Complete.

Environment: [staging/production]
REDIS_REQUIRED: [true]
INNGEST_REQUIRED: [true]

Checks:
- validate_runtime_env: PASS
- /api/runtime/dependencies: ready=true
- /api/health/ready: 200
- /inngest: mode=cloud, function_count=4
- replay_harness: pass_rate=[x], block_build=false

Release Decision: [GO/NO-GO]
Open Issues: [none OR list]
```
