# CAIO Alpha Swarm — Codex Deep Review Handoff

**Date**: 2026-02-17
**Last deployed commit**: `21297d8` (Railway: `caio-swarm-dashboard-production.up.railway.app`)
**Previous key commits**: `b8dfc0f`, `87225fa`, `bcd3815`, `bcf7c02`
**Plan version**: v4.3
**Phase**: 4E — Supervised Live Sends (RAMP MODE ACTIVE)

---

## 1. What This System Does

CAIO Alpha Swarm is an autonomous B2B outbound sales pipeline that discovers leads, enriches them, scores ICP fit, generates personalized email copy, and dispatches via Instantly (email) + HeyReach (LinkedIn). It runs on Railway with a FastAPI dashboard.

**Architecture**: 6 active agents (consolidated from 12) + Queen orchestrator, 6-stage pipeline.

```
HUNTER (scrape) → ENRICHER (enrich) → SEGMENTOR (classify) → CRAFTER (campaign) → GATEKEEPER (approve) → OUTBOX (send)
```

**Current state**: All infrastructure is built. System is in **ramp mode** — 5 emails/day, tier_1 leads only, for 3 supervised days before graduating to full autonomy (25/day, all tiers).

---

## 2. Recent Changes (Last 5 Commits)

### `21297d8` — Deep audit: task tracker + graduation roadmap
- Updated `docs/CAIO_TASK_TRACKER.md` with verified status for all 12 implementation claims
- Restructured next steps into IMMEDIATE / SHORT-TERM / PARALLEL / POST-GRADUATION sections
- Updated `CAIO_IMPLEMENTATION_PLAN.md` to v4.3

### `af12208` — CLAUDE.md: dashboard improvements + autonomy graduation path
- Added "Dashboard Pipeline Improvements" section
- Added "Autonomy Graduation Path" with Phase 4E checklist and KPI red flags table

### `b8dfc0f` — Fix empty email bodies + ramp banner + mid-market targets
- **CRITICAL FIX**: Pipeline send stage now extracts email subject/body from per-lead sequences (was reading empty campaign-level sequence)
- Added enriched recipient data (location, employees, industry) to shadow emails
- Changed default scrape source from "gong" (enterprise) to "apollo.io" (mid-market SaaS — higher tier_1 eligibility)
- Added 5 mid-market companies to COMPETITORS dict in hunter
- Dashboard v2.4: RAMP MODE banner with live operator status polling

### `87225fa` — Phase 4E: Supervised live sends — ramp mode + bug fixes
- Fixed Instantly V2 timezone bug (`America/New_York` → `America/Detroit`)
- Fixed Windows cp1252 encoding bug in cadence engine (`→` → `->`)
- Added ramp config to `config/production.json`
- Wired ramp into OPERATOR agent (`_get_ramp_status()`)
- Set `actually_send: true` (informational flag)

### `bcd3815` — GATEKEEPER approval gate + daily decay detection cron
- Built batch approval flow: `create_batch` → `approve_batch` → execute
- 3 dashboard endpoints: `pending-batch`, `approve-batch/{id}`, `reject-batch/{id}`
- Inngest `daily_decay_detection` cron at 10 AM UTC

---

## 3. Full Diff Stats (Phases 4A–4E)

34 files changed, 8,887 insertions, 1,063 deletions. Key new files:

| File | Lines | Purpose |
|------|-------|---------|
| `execution/operator_outbound.py` | 1,439 | OPERATOR agent: unified dispatch, ramp, GATEKEEPER gate |
| `execution/enricher_waterfall.py` | 901 | Renamed from enricher_clay_waterfall.py |
| `execution/heyreach_dispatcher.py` | 697 | LinkedIn dispatch via HeyReach API |
| `execution/cadence_engine.py` | 671 | 21-day multi-channel cadence (8 steps) |
| `dashboard/leads_dashboard.html` | 638 | Pipeline flow + lead list + timeline modal |
| `docs/CAIO_TASK_TRACKER.md` | 640 | Unified task tracker with graduation roadmap |
| `core/activity_timeline.py` | 453 | Per-lead activity aggregation across channels |
| `execution/operator_revival_scanner.py` | 429 | GHL contact mining for revival sequences |
| `core/lead_signals.py` | 418 | 21-status signal loop (incl. revival, ghosting, stall) |
| `webhooks/heyreach_webhook.py` | 371 | 11 webhook events, signal updates, Slack alerts |

---

## 4. Critical Code Paths to Review

### 4.1 Pipeline Body Extraction (THE FIX)

**File**: `execution/run_pipeline.py` lines 687–696

```python
# Extract subject/body from per-lead sequence (production mode)
# CampaignCrafter stores sequences on each lead, not campaign
lead_sequence = lead.get("sequence", [])
if lead_sequence:
    step0 = lead_sequence[0] if isinstance(lead_sequence[0], dict) else {}
    subject = step0.get("subject_a", campaign_subject)
    body = step0.get("body_a", campaign_body)
else:
    subject = campaign_subject
    body = campaign_body
```

**Why this matters**: `CampaignCrafter.create_campaign()` stores email sequences on each lead dict (`lead["sequence"]`), NOT at the campaign level (`campaign.sequence = []`). The old code read the always-empty campaign-level sequence, producing shadow emails with blank bodies. This fix reads per-lead sequences.

**Review**: Trace `execution/crafter_campaign.py` `create_campaign()` → verify `lead["sequence"]` is set → verify `step0` has `subject_a` and `body_a` keys.

### 4.2 Ramp Mode Logic

**File**: `execution/operator_outbound.py` lines 209–258

```python
def _get_ramp_status(self) -> Dict[str, Any]:
    ramp_cfg = self._operator_config.get("ramp", {})
    result = {
        "enabled": ramp_cfg.get("enabled", False),
        "active": False,
        "day": 0,
        "remaining_days": 0,
        "email_limit_override": None,
        "tier_filter": None,
    }
    if not ramp_cfg.get("enabled", False):
        return result
    start_str = ramp_cfg.get("start_date", "")
    ramp_days = ramp_cfg.get("ramp_days", 3)
    if not start_str:
        return result
    try:
        start = datetime.strptime(start_str, "%Y-%m-%d").date()
        days_since = (date.today() - start).days
        if 0 <= days_since < ramp_days:
            result["active"] = True
            result["day"] = days_since + 1
            result["remaining_days"] = ramp_days - days_since
            result["email_limit_override"] = ramp_cfg.get("email_daily_limit_override", 5)
            result["tier_filter"] = ramp_cfg.get("tier_filter", "tier_1")
        elif days_since < 0:
            result["active"] = True
            result["day"] = 0
            result["remaining_days"] = ramp_days
            result["email_limit_override"] = ramp_cfg.get("email_daily_limit_override", 5)
            result["tier_filter"] = ramp_cfg.get("tier_filter", "tier_1")
    except ValueError:
        logger.warning("Invalid ramp start_date: %s", start_str)
    return result
```

**Review**: Check that `dispatch_outbound()` actually reads this ramp status and enforces the tier filter and daily limit override. Search for `_get_ramp_status` call sites.

### 4.3 ICP Scoring (Tier Assignment)

**File**: `execution/segmentor_classify.py`

Scoring breakdown (100 points max):
- Company size: 20pts max (51-500 employees = 20, 501-1000 = 15, >1000 = 10)
- Title seniority: 25pts (C-level = 25, VP = 20, Director = 15)
- Industry fit: 20pts (SaaS/tech = 20, adjacent = 10)
- Tech stack: 15pts (relevant tools detected)
- Intent signals: 20pts (website visits, content downloads)

Tier thresholds: `tier_1 >= 80`, `tier_2 >= 60`, `tier_3 >= 40`, `tier_4 < 40`

**Review**: Verify scoring weights align with the target profile (mid-market SaaS VP+). A cold lead with 0 intent from a mid-market company scores ~75-85 — right at the tier_1 boundary. This is intentional — it means tier_1 requires either a strong company fit OR some intent signal.

### 4.4 GATEKEEPER Batch Approval

**File**: `execution/operator_outbound.py` (search for `create_batch`, `approve_batch`)

**Flow**: When `gatekeeper_required: true` and `--live` flag is used:
1. OPERATOR calls `create_batch()` → stores batch in `.hive-mind/gatekeeper_batches/`
2. Slack alert fires with batch details
3. Human reviews at `GET /api/operator/pending-batch`
4. Approves: `POST /api/operator/approve-batch/{id}`
5. Re-run OPERATOR → finds approved batch → executes dispatch

**Review**: Verify batch can't be auto-approved. Verify `--dry-run` bypasses GATEKEEPER (it should — dry-run never sends).

### 4.5 Instantly Campaign Creation

**File**: `execution/instantly_dispatcher.py` line ~459

Key gotcha: Instantly V2 rejects `America/New_York` as timezone. We use `America/Detroit` (same Eastern Time).

**Review**: Verify timezone is set to `America/Detroit`. Verify campaigns are created as DRAFTED (status=0). Verify rollback deletes orphaned campaigns if `add_leads` fails.

### 4.6 Cadence Engine

**File**: `execution/cadence_engine.py`

8-step, 21-day sequence (email + LinkedIn, no phone):
| Step | Day | Channel | Action |
|------|-----|---------|--------|
| 1 | 1 | Email | Personalized intro |
| 2 | 2 | LinkedIn | Connection request |
| 3 | 5 | Email | Value/case study follow-up |
| 4 | 7 | LinkedIn | Direct message (if connected) |
| 5 | 10 | Email | Social proof/testimonial |
| 6 | 14 | LinkedIn | Follow-up message |
| 7 | 17 | Email | Break-up email |
| 8 | 21 | Email | Graceful close |

Exit conditions: `replied`, `meeting_booked`, `bounced`, `unsubscribed`, `linkedin_replied`, `rejected`

**Review**: Check condition evaluation logic (e.g., `linkedin_connected` for step 4 — what happens if the connection request from step 2 wasn't accepted by day 7?). Verify CRAFTER generates follow-up copy for steps 3/5/7/8.

---

## 5. Configuration State

### `config/production.json` — Key Sections

```json
{
    "operator": {
        "enabled": true,
        "gatekeeper_required": true,
        "outbound": {
            "email_daily_limit": 25,
            "linkedin_warmup_start": "2026-02-16",
            "linkedin_warmup_daily_limit": 5,
            "dispatch_order": ["instantly", "heyreach"],
            "tier_channel_routing": {
                "tier_1": ["instantly", "heyreach"],
                "tier_2": ["instantly", "heyreach"],
                "tier_3": ["instantly"]
            }
        },
        "revival": {
            "enabled": true,
            "daily_limit": 5,
            "min_inactive_days": 30,
            "scan_pipeline_stages": ["Cold", "Lost", "Nurture"]
        },
        "ramp": {
            "enabled": true,
            "email_daily_limit_override": 5,
            "tier_filter": "tier_1",
            "start_date": "2026-02-17",
            "ramp_days": 3
        }
    },
    "cadence": {
        "default_21day": { /* 8-step Email+LinkedIn sequence */ }
    },
    "guardrails": {
        "email_limits": {
            "monthly_limit": 2500,
            "daily_limit": 25,
            "hourly_limit": 15,
            "per_domain_hourly_limit": 3,
            "min_delay_seconds": 45
        }
    }
}
```

### Safety Controls (Layered)

| Control | Location | Purpose |
|---------|----------|---------|
| `EMERGENCY_STOP` env var | Railway | Kills all outbound instantly |
| `shadow_mode: true` | production.json | Emails go to file, not inbox |
| `gatekeeper_required: true` | production.json | Batch approval before dispatch |
| `ramp.enabled: true` | production.json | 5/day, tier_1 only |
| `--dry-run` / `--live` CLI flag | operator_outbound.py | Default is dry-run |
| Campaigns start DRAFTED | Instantly V2 behavior | Must explicitly activate |

---

## 6. Dashboard Endpoints

### FastAPI (`dashboard/health_app.py`, port 8080)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health/ready` | GET | Health check (Redis, Inngest) |
| `/api/operator/status` | GET | Ramp status, warmup schedule, daily state |
| `/api/operator/pending-batch` | GET | Current GATEKEEPER batch |
| `/api/operator/approve-batch/{id}` | POST | Approve batch for dispatch |
| `/api/operator/reject-batch/{id}` | POST | Reject batch |
| `/api/cadence/summary` | GET | Enrolled leads, active cadences |
| `/api/cadence/due` | GET | Steps due today |
| `/api/cadence/enroll` | POST | Manually enroll lead |
| `/api/cadence/status/{email}` | GET | Individual cadence status |
| `/api/leads/funnel` | GET | Pipeline flow visualization |
| `/api/leads/{email}/timeline` | GET | Activity timeline |
| `/sales` | GET | HoS (Head of Sales) dashboard — approve/reject emails |
| `/leads` | GET | Leads dashboard — pipeline flow + timeline |

### Inngest Functions (`core/inngest_scheduler.py`)

| Function | Schedule | Purpose |
|----------|----------|---------|
| `pipeline_scan` | On-demand | Trigger pipeline run |
| `daily_health_check` | Daily | System health verification |
| `weekly_icp_analysis` | Weekly | ICP threshold tuning |
| `meeting_prep_trigger` | On-demand | Pre-meeting intelligence |
| `daily_decay_detection` | `0 10 * * *` (10 AM UTC) | Decay scan + batch expiry + cadence sync |

---

## 7. Known API Gotchas

### Apollo
- `reveal_phone_number` requires `webhook_url` — removed from enricher payload
- `mixed_people/search` deprecated → use `mixed_people/api_search`
- `api_search` returns anonymized results → need `people/match` by ID to reveal
- 402 = credits exhausted, 404 = no match

### Instantly V2
- `America/New_York` REJECTED as timezone → use `America/Detroit`
- Auth: `Authorization: Bearer <key>` (NOT query param)
- Campaigns start DRAFTED (status=0) — must explicitly activate
- Leads bulk: `campaign` key (NOT `campaign_id`)
- Webhook list: data inside `items` key (NOT top-level array)

### HeyReach
- CANNOT create campaigns via API (404) — UI only
- CANNOT create/list/delete webhooks via API — UI only
- Adding leads to paused campaign AUTO-REACTIVATES it
- `aiohttp` needs `content_type=None` — no Content-Type header in responses
- Auth: `X-API-KEY` header (NOT Bearer)

### Windows (Local Dev)
- `nul` file blocks Railway upload → `.railwayignore`
- Rich console braille/emoji crash on cp1252 → ASCII spinners
- `→` (U+2192) → `->` in cadence engine output

---

## 8. Go-Live Checklist (Phase 4E)

| # | Step | Status | Notes |
|---|------|--------|-------|
| 1 | Fix Instantly timezone bug | DONE | `America/Detroit` |
| 2 | Fix Windows encoding bug | DONE | `→` to `->` |
| 3 | Add ramp config | DONE | 5/day, tier_1, 3 days |
| 4 | Wire ramp into OPERATOR | DONE | `_get_ramp_status()` |
| 5 | Deploy to Railway | DONE | `b8dfc0f` |
| 6 | Run fresh pipeline | PENDING | Need new leads with proper bodies |
| 7 | Dry-run dispatch | PENDING | `--motion outbound --dry-run` |
| 8 | Live dispatch (GATEKEEPER) | PENDING | `--motion outbound --live` |
| 9 | Monitor KPIs (3 days) | PENDING | Open >50%, Reply >8%, Bounce <5% |

---

## 9. Files to Review (Priority Order)

### P0 — Critical Path (sends real emails)
1. `execution/operator_outbound.py` — Unified dispatch, ramp enforcement, GATEKEEPER gate
2. `execution/instantly_dispatcher.py` — Campaign creation, lead adding, timezone, rollback
3. `execution/run_pipeline.py` — 6-stage pipeline, body extraction fix
4. `config/production.json` — All safety controls, ramp config, cadence config

### P1 — Supporting Infrastructure
5. `execution/cadence_engine.py` — 21-day sequence, condition evaluation, state management
6. `core/lead_signals.py` — 21 statuses, signal transitions, revivability checks
7. `dashboard/health_app.py` — All API endpoints, auth, GATEKEEPER endpoints
8. `execution/crafter_campaign.py` — Email copy generation, per-lead sequence storage

### P2 — Integration Code
9. `execution/heyreach_dispatcher.py` — LinkedIn dispatch, lead-list-first safety
10. `webhooks/heyreach_webhook.py` — 11 event types, signal updates
11. `webhooks/instantly_webhook.py` — Reply/bounce/open/unsub handlers
12. `execution/operator_revival_scanner.py` — GHL contact mining, scoring

### P3 — Observability
13. `core/inngest_scheduler.py` — 5 scheduled functions, decay detection cron
14. `core/activity_timeline.py` — Per-lead activity aggregation
15. `core/alerts.py` — Slack webhook, Windows-safe formatting

---

## 10. Questions for Codex Review

1. **Body extraction**: Is the `lead.get("sequence", [])` path robust? What if CampaignCrafter changes its storage format?
2. **Ramp enforcement**: Is there a race condition if two OPERATOR instances run simultaneously? (OperatorDailyState is file-based)
3. **GATEKEEPER bypass**: Can a `--live` dispatch ever skip the GATEKEEPER when `gatekeeper_required: true`?
4. **Cadence state**: State files are in `.hive-mind/cadence_state/` — what happens if Railway filesystem is ephemeral? (It is — need Redis or Supabase migration)
5. **Dedup layers**: Three-layer dedup (OperatorDailyState + LeadStatusManager + shadow flags). Are there edge cases where a lead slips through?
6. **Error handling in dispatcher**: If Instantly API returns 500 mid-batch, does the rollback correctly clean up?
7. **Signal loop completeness**: 21 statuses in `lead_signals.py` — are transitions correctly guarded? Can a `bounced` lead be re-enrolled?

---

## 11. Environment Variables (63 in Railway)

Key ones for outbound path:
- `INSTANTLY_API_KEY` — V2 Bearer token
- `INSTANTLY_WORKSPACE_ID` — workspace scope
- `HEYREACH_API_KEY` — X-API-KEY header
- `APOLLO_API_KEY` — enrichment
- `GHL_PROD_API_KEY` — CRM
- `SLACK_WEBHOOK_URL` — alerts
- `EMERGENCY_STOP` — kill switch (set to `true` to halt all outbound)
- `ENVIRONMENT` — `production`

---

## 12. How to Run

```bash
# Pipeline (generates leads with email bodies)
echo yes | python execution/run_pipeline.py --mode production

# Operator dry-run (preview what would be dispatched)
python -m execution.operator_outbound --motion outbound --dry-run

# Operator live (GATEKEEPER intercepts)
python -m execution.operator_outbound --motion outbound --live

# Cadence due steps
python -m execution.cadence_engine --due

# Operator status
python -m execution.operator_outbound --status

# Health check
curl https://caio-swarm-dashboard-production.up.railway.app/api/health/ready
```
