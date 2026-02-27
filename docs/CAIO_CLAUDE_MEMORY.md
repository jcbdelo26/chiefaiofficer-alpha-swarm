# CAIO Claude Memory (Living Source of Truth)

**Last Updated**: 2026-02-19  
**Maintainer**: Codex/Claude handoff chain  
**Purpose**: Keep runtime truth, deploy truth, and known gaps synchronized across sessions.

---

## 1) Runtime Truth (As of 2026-02-19)

- Production service: `https://caio-swarm-dashboard-production.up.railway.app`
- Latest successful deployment:
  - Railway deployment ID: `077ac100-c179-418b-add0-c2a48a204fb8`
  - Git commit: `27488b6737ac8127146dcdbe18a21f0871ff7377`
  - Commit message: `fix(hotfix): resolve python 3.11 f-string syntax crash in email_signature`
  - Deploy reason: `redeploy`

---

## 2) Verified Working Behaviors

- Strict API auth is active:
  - Protected endpoints return `401` when unauthenticated.
  - Query token (`?token=`) and header token (`X-Dashboard-Token`) both accepted.
- Health/readiness endpoints remain public:
  - `/api/health/ready` returns `200`.
- `/sales` auto-refresh wiring exists:
  - polling interval + `visibilitychange` refresh.
- Pending queue classifier contract is present:
  - `classifier.*` and `campaign_ref.*` metadata returned by `/api/pending-emails`.
- Redis-backed queue is active in production:
  - `_shadow_queue_debug.redis_connected=true`
  - `_shadow_queue_debug.filesystem_merge_enabled=false`

---

## 3) Known Gaps Needing Immediate Follow-Through

1. **Footer parity gap in deployed content**
- Current deployed pending bodies include:
  - `Schedule a call with CAIO: https://caio.cx/ai-exec-briefing-call`
  - `support@chiefaiofficer.com`
- But some live pending bodies still do **not** include:
  - `Reply STOP to unsubscribe.`
- Interpretation:
  - Code-level intent exists in local branch, but deployed commit (`27488b6`) still reflects older canonical footer content for production payloads.
  - Local patch (not deployed yet) now enforces footer order/format as requested:
    - centered HTML compliance block
    - `Reply STOP to unsubscribe.` as final line
    - CTA remains `Schedule a call with CAIO: https://caio.cx/ai-exec-briefing-call`

2. **Version drift in docs**
- `CLAUDE.md` had stale references (old dashboard/plan version text).  
- Must keep memory and plan synchronized after each deploy.

3. **Possible false negatives in smoke due network timeout**
- `deployed_full_smoke_checklist.py` can fail transiently on TLS/handshake timeout with shorter timeout settings.
- Stable run succeeded with `--timeout-seconds 60`.

---

## 4) Last Verification Snapshot

- Successful full smoke command:
  - `python scripts/deployed_full_smoke_checklist.py --base-url https://caio-swarm-dashboard-production.up.railway.app --token <TOKEN> --timeout-seconds 60 --refresh-wait-seconds 3`
- Result: `"passed": true`
- Additional manual checks:
  - `/api/operator/status` unauth=`401`, token auth=`200`
  - `/api/operator/trigger` unauth=`401`
  - `/api/runtime/dependencies?token=...`=`200`
  - `/api/health/ready`=`200`

---

## 5) Current Engineering Priorities

1. Deploy and verify footer parity patch so all pending/live outbound emails contain:
- Hyperlinked `Schedule a call with CAIO` -> `https://caio.cx/ai-exec-briefing-call`
- `Reply STOP to unsubscribe.`

2. Eliminate frontend/backend formatting drift:
- Keep canonical signature/footer enforcement backend-owned.
- UI should render/preview, not diverge from backend canonicalization rules.

3. Keep supervised Tier_1 send ritual strict:
- smoke -> queue review -> HoS approve -> live send -> GHL conversation proof.

---

## 6) Mandatory Memory Update Protocol

After **every** deploy, hotfix, or operational incident:

1. Update this file (`docs/CAIO_CLAUDE_MEMORY.md`) with:
- deployment ID
- commit hash
- what passed
- what still failed

2. Update `CLAUDE.md`:
- current deploy truth
- links to latest handoff/memory docs
- any new architectural laws

3. If a behavior regressed, add:
- root cause
- prevention rule
- exact verification command
