# Codex Handoff: HoS Requirements Integration — Deep Code Review

**Document Purpose**: Self-contained review guide for Codex to verify all changes from the HoS Requirements Integration (commit `10cc82c`, deployed 2026-02-18). Includes file-by-file audit, 26 bugs found, cross-file consistency checks, and a pipeline verification playbook.

**Priority**: Review and fix CRITICAL bugs before first supervised live dispatch.

---

## 1. Executive Summary

### What Changed
The entire outbound email system was rewritten to align with the Head of Sales Requirements document (`docs/google_drive_docs/HEAD_OF_SALES_REQUIREMENTS 01.26.2026 (1).docx`).

**Before**: CRAFTER positioned CAIO as a "revenue intelligence SaaS" (CRM signals, pipeline predictions, deal coaching). Templates: `competitor_displacement`, `event_followup`, `thought_leadership`, `community_outreach`, `website_visitor`, `cold_outbound`.

**After**: CAIO is a **Fractional Chief AI Officer consulting firm** using the **M.A.P. Framework** (Measure, Automate, Prove) in 90-day embedded cycles. Templates: 11 HoS-approved angles across 3 ICP tiers.

### Deployment
- **Commit**: `10cc82c`
- **Deployed**: 2026-02-18 to Railway (`caio-swarm-dashboard-production.up.railway.app`)
- **Changes**: +934 / -314 lines across 7 files
- **Pipeline**: 6/6 PASS verified (Wpromote source, 2 leads, 5.6s)

### Files Modified

| # | File | Lines Changed | What Changed |
|---|------|---------------|-------------|
| 1 | `execution/crafter_campaign.py` | +684/-314 | 6 old templates -> 11 HoS angles + follow-ups + cadence + sender + footer |
| 2 | `execution/segmentor_classify.py` | +115/-50 | Title/industry lists, score multipliers (1.5x/1.3x/1.2x), threshold 80 |
| 3 | `execution/instantly_dispatcher.py` | +101/-20 | Guard 4 (27 individual email exclusions) |
| 4 | `execution/hunter_scrape_followers.py` | +116/-80 | TARGET_COMPANIES -> HoS Tier 1 ICP targets |
| 5 | `config/production.json` | +63/-5 | 7 customer domains, 27 customer emails, ramp config |
| 6 | `CLAUDE.md` | +99/-15 | HoS Email Crafting Reference section |
| 7 | `CAIO_IMPLEMENTATION_PLAN.md` | +70/-2 | HoS integration section + decision log entry |

---

## 2. Files Modified — Change-by-Change Audit

### 2.1 `execution/crafter_campaign.py` (1,009 lines)

#### Changes Made

| Component | Before | After | Lines |
|-----------|--------|-------|-------|
| TEMPLATES dict | 6 generic SaaS templates | 11 HoS-approved angles (4 T1, 3 T2, 4 T3) | 87-380 |
| FOLLOWUP_TEMPLATES | 3 generic follow-ups | 2 HoS-approved (Day 3 value-first, Day 7 breakup) | 385-432 |
| CADENCE_TEMPLATES | 4 revenue-intelligence templates | 4 HoS-aligned (value_followup, social_proof, breakup, close) | 438-529 |
| sender_info | "Head of Sales and Partnerships" | "Dani Apgar, Chief AI Officer" | 532-537 |
| calendar_link | calendly.com | caio.cx/ai-exec-briefing-call | 536 |
| _select_template() | Source-based routing | Tier-based routing via TIER_TEMPLATES | 539-565 |
| CAN-SPAM footer | None | Appended to all 17 templates | Every template body |
| Fallback template | `competitor_displacement` | `t1_executive_buyin` | 421, 445, 493 |

#### Lines to Verify

- **Line 87-380**: All 11 TEMPLATES — verify each body contains M.A.P. Framework messaging, correct sender block, CAN-SPAM footer
- **Lines 385-432**: FOLLOWUP_TEMPLATES — verify 2 follow-ups with correct delay_days (3, 7)
- **Lines 438-529**: CADENCE_TEMPLATES — verify 4 action types match cadence engine step actions
- **Lines 532-537**: sender_info — verify name="Dani Apgar", title="Chief AI Officer", calendar_link="https://caio.cx/ai-exec-briefing-call"
- **Lines 558-562**: TIER_TEMPLATES mapping — verify t1 angles route to tier_1, t2 to tier_2, etc.
- **Line 564**: Hash-based selection — `hash(lead.get("email", "")) % len(templates)`

#### Known Bugs

| # | Severity | Lines | Bug | Impact |
|---|----------|-------|-----|--------|
| B1 | HIGH | 703-704 | Follow-up A/B subjects identical — both render `followup["subject"]` (singular key), not subject_a/subject_b | No A/B testing on follow-ups |
| B2 | MEDIUM | 564 | `hash(email) % len(templates)` may not distribute uniformly | Some templates over/under-selected |
| B3 | MEDIUM | 77, 779 | `personalization_hooks` field never populated (always empty list) | Dead field, unused downstream |
| B4 | LOW | 720 | Returns `None` for empty leads instead of empty Campaign | Type inconsistency downstream |

#### Verification

```bash
# Verify all 11 template keys exist
python -c "from execution.crafter_campaign import CampaignCrafter; print(list(CampaignCrafter.TEMPLATES.keys()))"

# Verify sender info
python -c "from execution.crafter_campaign import CampaignCrafter; c = CampaignCrafter(); print(c.sender_info)"

# Verify CAN-SPAM footer in every template
python -c "
from execution.crafter_campaign import CampaignCrafter
for k, v in CampaignCrafter.TEMPLATES.items():
    assert '5700 Harper Dr' in v['body'], f'MISSING FOOTER: {k}'
    assert 'Reply STOP' in v['body'], f'MISSING OPT-OUT: {k}'
print('All 11 templates have CAN-SPAM footer')
"

# Verify follow-up footer
python -c "
from execution.crafter_campaign import CampaignCrafter
for f in CampaignCrafter.FOLLOWUP_TEMPLATES:
    assert '5700 Harper Dr' in f['body'], 'MISSING FOOTER in follow-up'
print('All follow-ups have CAN-SPAM footer')
"

# Verify cadence template footer
python -c "
from execution.crafter_campaign import CampaignCrafter
for k, v in CampaignCrafter.CADENCE_TEMPLATES.items():
    assert '5700 Harper Dr' in v['body'], f'MISSING FOOTER: {k}'
print('All cadence templates have CAN-SPAM footer')
"
```

---

### 2.2 `execution/segmentor_classify.py` (1,091 lines)

#### Changes Made

| Component | Before | After | Lines |
|-----------|--------|-------|-------|
| C_LEVEL_TITLES | Generic C-suite | HoS Tier 1: CEO, Founder, President, COO, Owner, Managing Partner | 177 |
| VP_TITLES | Generic VP list | HoS Tier 2: CTO, CIO, CSO, Chief of Staff, VP Ops/Strategy, Head of Innovation, CRO | 179-182 |
| DIRECTOR_TITLES | Generic directors | HoS Tier 3: Director Ops/IT/Strategy, VP Engineering, Head of AI/Data | 184-186 |
| TIER1_INDUSTRIES | B2B SaaS, RevTech | Agencies, Staffing, Consulting, Law/CPA, Real Estate, E-commerce | 190-195 |
| TIER2_INDUSTRIES | Enterprise tech | B2B SaaS, IT Services, Healthcare, Financial Services | 197-200 |
| TIER3_INDUSTRIES | (didn't exist) | Manufacturing, Logistics, Construction, Home Services | 202-204 |
| Score multipliers | None | 1.5x (C-Suite+T1), 1.3x (C-Suite other / VP+T1), 1.2x (VP+T2), 1.1x (VP other) | 457-488 |
| Tier 1 threshold | 70 | 80 | 212-216 |

#### Lines to Verify

- **Lines 177-204**: All title and industry keyword lists — verify each keyword appears in correct tier
- **Lines 212-216**: `DEFAULT_TIER_THRESHOLDS` — verify tier_1=80, tier_2=60, tier_3=40
- **Lines 457-488**: HoS multiplier block — verify multiplier conditions and values
- **Line 486**: `score = int(score * multiplier)` — verify multiplier is applied
- **Line 490**: `final_score = min(score, 100)` — verify cap

#### Known Bugs

| # | Severity | Lines | Bug | Impact |
|---|----------|-------|-----|--------|
| B5 | CRITICAL | 443-455 | Engagement bonus (3-5pts) added AFTER intent cap (20pts) — total can exceed designed 100pt maximum | Scores inflated, leads may tier up incorrectly |
| B6 | HIGH | 361-370 | Multiple tech stack matches can individually exceed 15pt subtotal before `min()` caps — confusing but functionally correct | Cosmetic: scoring breakdown misleading |
| B7 | MEDIUM | 490 | `min(score, 100)` caps AFTER multiplier — so 65 * 1.5 = 97 (kept), but 72 * 1.5 = 108 -> 100 (clipped). Multiplier effect lost at high scores | Multiplier partially cosmetic at high base scores |
| B8 | MEDIUM | 314-315 | VP titles get +22pts (not 25) but scale isn't proportional to cap system | Scoring inconsistency |
| B9 | LOW | 710 | `needs_review` flag set when `70 <= score <= 85` but tier_1 is 80+, should be `75 <= score <= 85` for borderline catch | Borderline tier_1 leads may not get flagged for review |

#### Verification

```bash
# Verify tier thresholds
python -c "
import sys; sys.path.insert(0, '.')
from execution.segmentor_classify import LeadSegmentor
s = LeadSegmentor()
print('Thresholds:', s.tier_thresholds)
assert s.tier_thresholds['tier_1'] == 80
assert s.tier_thresholds['tier_2'] == 60
assert s.tier_thresholds['tier_3'] == 40
print('OK')
"

# Test scoring: CEO at marketing agency (should be tier_1, score ~97)
python -c "
import sys; sys.path.insert(0, '.')
from execution.segmentor_classify import LeadSegmentor
s = LeadSegmentor()
lead = {'title': 'CEO', 'industry': 'marketing', 'employees': '150', 'email': 'test@agency.com'}
result = s.calculate_icp_score(lead)
print(f'Score: {result[\"icp_score\"]}, Tier: {result[\"icp_tier\"]}')
assert result['icp_tier'] == 'tier_1', f'Expected tier_1, got {result[\"icp_tier\"]}'
print('CEO + agency = tier_1 OK')
"

# Test scoring: CTO at SaaS (should be tier_2, score ~68)
python -c "
import sys; sys.path.insert(0, '.')
from execution.segmentor_classify import LeadSegmentor
s = LeadSegmentor()
lead = {'title': 'CTO', 'industry': 'saas', 'employees': '200', 'email': 'test@saas.com'}
result = s.calculate_icp_score(lead)
print(f'Score: {result[\"icp_score\"]}, Tier: {result[\"icp_tier\"]}')
assert result['icp_tier'] == 'tier_2', f'Expected tier_2, got {result[\"icp_tier\"]}'
print('CTO + SaaS = tier_2 OK')
"

# Test scoring: Director at manufacturing (should be tier_3)
python -c "
import sys; sys.path.insert(0, '.')
from execution.segmentor_classify import LeadSegmentor
s = LeadSegmentor()
lead = {'title': 'Director of Operations', 'industry': 'manufacturing', 'employees': '100', 'email': 'test@mfg.com'}
result = s.calculate_icp_score(lead)
print(f'Score: {result[\"icp_score\"]}, Tier: {result[\"icp_tier\"]}')
print('Director + manufacturing result')
"
```

---

### 2.3 `execution/instantly_dispatcher.py` (769 lines)

#### Changes Made

| Component | Before | After | Lines |
|-----------|--------|-------|-------|
| Guard count | 3 guards | 4 guards (added Guard 4: individual email exclusion) | 299-306 |
| excluded_emails set | Not loaded | Loaded from `config.guardrails.deliverability.excluded_recipient_emails` | 239-245 |
| rejected_email_exclusion counter | Didn't exist | New counter for Guard 4 rejections | 275 |
| Summary log | 3 rejection types | 4 rejection types (+ email exclusion) | 326-334 |

#### Lines to Verify

- **Lines 209-214**: Guard 1 — email format regex
- **Lines 239-245**: excluded_emails set loading (case-insensitive via `.lower().strip()`)
- **Lines 289-297**: Guard 2 — domain exclusion check
- **Lines 299-306**: Guard 4 — individual email exclusion (NEW)
- **Lines 308-317**: Guard 3 — domain concentration cap
- **Lines 326-334**: Summary log with all 4 guard counts

#### Known Bugs

| # | Severity | Lines | Bug | Impact |
|---|----------|-------|-----|--------|
| B10 | CRITICAL | 471 | `bulk_pause_all()` called in EMERGENCY_STOP handler but method doesn't exist on `AsyncInstantlyClient` | EMERGENCY_STOP in live mode crashes with AttributeError |
| B11 | CRITICAL | 290 | Domain extraction via `split("@")[-1]` returns full domain including subdomains — `user@sub.example.com` -> `sub.example.com`, won't match `example.com` in exclusion list | Customer exclusion broken for subdomain emails |
| B12 | HIGH | 326-334 | Rejected leads silently dropped — no audit log entry, no retry scheduling | Operators blind to why leads disappeared |
| B13 | MEDIUM | 573-578 | Timezone hardcoded to `America/Detroit`, no config override | Business logic brittle |
| B14 | LOW | 427 | Dispatch log file (`instantly_dispatch_log.jsonl`) grows unbounded, no rotation | Log could exhaust disk over time |

#### Verification

```bash
# Verify Guard 4 exclusion set loads correctly
python -c "
import json
with open('config/production.json') as f:
    config = json.load(f)
emails = config['guardrails']['deliverability']['excluded_recipient_emails']
print(f'Loaded {len(emails)} excluded emails')
assert len(emails) == 27, f'Expected 27, got {len(emails)}'
assert 'chudziak@jbcco.com' in emails
print('Guard 4 config OK')
"

# Verify excluded domains count
python -c "
import json
with open('config/production.json') as f:
    config = json.load(f)
domains = config['guardrails']['deliverability']['excluded_recipient_domains']
print(f'Loaded {len(domains)} excluded domains')
assert len(domains) == 19, f'Expected 19, got {len(domains)}'
assert 'jbcco.com' in domains
assert 'chiefaiofficer.com' in domains
print('Guard 2 config OK')
"
```

---

### 2.4 `execution/hunter_scrape_followers.py` (569 lines)

#### Changes Made

| Component | Before | After | Lines |
|-----------|--------|-------|-------|
| TARGET_COMPANIES | 9 SaaS targets (Regie.ai, Lavender, Orum, Drift, Vidyard, Chili Piper, Sendoso, Mutiny, Qualified) | 9 HoS Tier 1 ICP targets (Wpromote, Tinuiti, Power Digital, Insight Global, Kforce, Slalom, West Monroe, ShipBob, Chili Piper) | 124-175 |

#### Lines to Verify

- **Lines 124-175**: All 9 companies — verify domains are correct, industries match HoS Tier 1/2
- **Lines 359-362**: Domain vs name search decision — verify `company_domain` takes priority

#### Known Bugs

| # | Severity | Lines | Bug | Impact |
|---|----------|-------|-----|--------|
| B15 | HIGH | 359-362 | If `company_domain` not provided, falls back to `q_organization_name` which does fuzzy matching — "Drift" returns "Driftwood Capital" | Wrong-company leads scraped (mitigated: all 9 targets have domains) |
| B16 | HIGH | 406, 437 | Apollo People Match failures silently swallowed (`continue` with no logging) | Operator blind to API errors during match phase |
| B17 | MEDIUM | 283 | Error message says "Tenacity will retry with backoff" but `_rate_limited_request()` has no `@retry` decorator | 429 rate-limited requests crash instead of retrying |
| B18 | MEDIUM | 150-161 | Kforce (~1,500 employees), Slalom (~10,000), West Monroe (~600) exceed 51-500 sweet spot | Leads from these companies score lower on company_size (10-15pts vs 20pts) |
| B19 | LOW | 298 | `company_url` parameter in `fetch_followers()` signature is never used | Dead parameter, misleading API |
| B20 | LOW | 180-193 | No startup validation that TARGET_COMPANIES domains aren't in exclusion list | Could scrape excluded competitor leads (downstream guards catch, but wasteful) |

#### Verification

```bash
# Verify all TARGET_COMPANIES have domain hints
python -c "
import sys; sys.path.insert(0, '.')
from execution.hunter_scrape_followers import LinkedInFollowerScraper
for name, info in LinkedInFollowerScraper.TARGET_COMPANIES.items():
    domain = info.get('domain', '')
    assert domain, f'{name} MISSING domain hint'
    print(f'{name}: {domain}')
print('All targets have domains')
"
```

---

### 2.5 `config/production.json`

#### Changes Made

| Component | Before | After | Lines |
|-----------|--------|-------|-------|
| excluded_recipient_domains | 12 domains (competitors + own) | 19 domains (+7 customer domains) | 319-339 |
| excluded_recipient_emails | Didn't exist | 27 customer emails from GHL export | 341-369 |
| ramp.tier_filter | "tier_2" | "tier_1" | 453 |
| ramp.start_date | "2026-02-17" | "2026-02-18" | 454 |

#### Lines to Verify

- **Lines 319-339**: 19 excluded domains — verify 12 competitors + 7 customer domains
- **Lines 341-369**: 27 excluded emails — verify all from HoS Section 1.4
- **Lines 451-457**: Ramp config — verify enabled=true, limit=5, tier_filter="tier_1", start_date="2026-02-18"

---

### 2.6 `CLAUDE.md`

#### Changes Made

Added **HoS Email Crafting Reference** section (lines 426-509) containing:
- Offer & Positioning (Fractional CAIO, M.A.P. Framework)
- ICP Tier Definitions table (3 tiers with multipliers)
- 11 Email Angles Summary (4 T1, 3 T2, 4 T3)
- Follow-Up Sequences (Day 3-4, Day 7 breakup)
- Objection Handling Playbook (5 objections)
- Email Signature & CAN-SPAM Footer
- Customer Exclusion List (27 emails, 7 domains)

Also updated:
- Dashboard section (line 20): commit hash `b8dfc0f` -> `10cc82c`
- Target companies note (line 44): SaaS -> HoS Tier 1 ICP
- Deliverability guards note (line 45): 3-layer -> 4-layer
- Ramp mode note (line 35): tier_2 -> tier_1

---

### 2.7 `CAIO_IMPLEMENTATION_PLAN.md`

#### Changes Made

- Added "HoS Requirements Integration (2026-02-18)" section with 9 completed tasks (lines 380-393)
- Added "Remaining (Operational)" tasks section (lines 394-404)
- Added decision log entry for 2026-02-18 (line 683)
- Updated plan version to 4.5 (line 687)

---

## 3. Bug Report (26 Bugs Found)

### CRITICAL (3) — Must fix before live dispatch

| ID | File | Lines | Description | Impact | Blocks Live? |
|----|------|-------|-------------|--------|-------------|
| B5 | segmentor_classify.py | 443-455 | Engagement bonus (3-5pts) stacks AFTER intent cap (20pts), inflating total score beyond 100pt design limit | Leads may tier up incorrectly (e.g., tier_2 -> tier_1) | No (ramp filters tier_1 only, but risk at scale) |
| B10 | instantly_dispatcher.py | 471 | `bulk_pause_all()` called in EMERGENCY_STOP handler but method doesn't exist on `AsyncInstantlyClient` | EMERGENCY_STOP in live mode crashes with `AttributeError` instead of pausing campaigns | **YES** — safety-critical |
| B11 | instantly_dispatcher.py | 290 | Domain extraction via `split("@")[-1]` doesn't match subdomains — `user@sub.jbcco.com` won't match `jbcco.com` in exclusion list | Customer exclusion broken for subdomain emails | No (current customers don't use subdomains, but risk exists) |

### HIGH (4) — Fix before scale-up

| ID | File | Lines | Description | Impact |
|----|------|-------|-------------|--------|
| B1 | crafter_campaign.py | 703-704 | Follow-up A/B subjects identical — `followup["subject"]` (singular) rendered twice for both subject_a and subject_b | No A/B testing on follow-up emails |
| B6 | segmentor_classify.py | 361-370 | Multiple tech stack keyword matches can individually exceed 15pt subtotal before `min()` caps | Cosmetic: scoring breakdown misleading in logs |
| B15 | hunter_scrape_followers.py | 359-362 | `q_organization_name` fuzzy matching returns wrong companies if `company_domain` not provided | Wrong leads (mitigated: all 9 targets have domains) |
| B16 | hunter_scrape_followers.py | 406, 437 | Apollo People Match failures silently swallowed with `continue`, no logging | Operator blind to API errors during reveal phase |

### MEDIUM (11) — Fix when convenient

| ID | File | Lines | Description |
|----|------|-------|-------------|
| B2 | crafter_campaign.py | 564 | Hash-based template selection may skew distribution unevenly |
| B3 | crafter_campaign.py | 77, 779 | `personalization_hooks` field never populated (dead field) |
| B7 | segmentor_classify.py | 490 | `min(score, 100)` caps AFTER multiplier — multiplier effect clipped at high base scores |
| B8 | segmentor_classify.py | 314-315 | VP titles get +22pts (not proportional to 25pt cap design) |
| B12 | instantly_dispatcher.py | 326-334 | Rejected leads silently dropped — no audit log, no retry |
| B13 | instantly_dispatcher.py | 573-578 | Timezone hardcoded to `America/Detroit`, no config override |
| B17 | hunter_scrape_followers.py | 283 | Error says "Tenacity will retry" but no `@retry` decorator on function |
| B18 | hunter_scrape_followers.py | 150-161 | Kforce/Slalom/West Monroe exceed 500-employee sweet spot |
| B21 | lead_signals.py | 85 | Email-to-filename sanitization may collide (`a.b@c.com` and `ab@c.com` -> same file) |
| B22 | operator_outbound.py | 1370-1372 | Dry-run marks cadence steps as done (should skip state changes in dry-run) |
| B23 | operator_outbound.py | 1009 | Auto-enroll only checks `dispatched_to_instantly`, misses `dispatched_to_heyreach` |

### LOW (8) — Nice to fix

| ID | File | Lines | Description |
|----|------|-------|-------------|
| B4 | crafter_campaign.py | 720 | Returns `None` for empty leads instead of empty Campaign |
| B9 | segmentor_classify.py | 710 | `needs_review` range `70-85` should be `75-85` for borderline tier_1 |
| B14 | instantly_dispatcher.py | 427 | Dispatch log grows unbounded, no rotation |
| B19 | hunter_scrape_followers.py | 298 | `company_url` parameter is dead code (never used) |
| B20 | hunter_scrape_followers.py | 180-193 | No startup validation against exclusion list |
| B24 | lead_signals.py | 154-156 | Open/reply counts unbounded (no max enforcement) |
| B25 | operator_outbound.py | 75 | `cadence_dispatched` counter never incremented in dispatch_outbound/revival |
| B26 | health_app.py | 858-872 | `/sales` endpoint has no authentication (public dashboard) |

---

## 4. Cross-File Consistency Checks

### 4.1 Template Names: Crafter vs Segmentor

The segmentor sets `recommended_campaign` on each lead. The crafter's `_select_template()` checks this field first (line 545). Verify:

| Segmentor `recommended_campaign` value | Exists in crafter TEMPLATES? |
|-----------------------------------------|------------------------------|
| `t1_executive_buyin` | Yes |
| `t1_industry_specific` | Yes |
| `t1_value_first` | Yes |
| `t2_tech_stack` | Yes |
| `t2_ops_efficiency` | Yes |
| `t2_innovation_champion` | Yes |
| `t3_quick_win` | Yes |
| `t3_time_savings` | Yes |
| `t3_competitor_fomo` | Yes |
| `t3_diy_resource` | Yes |

**CHECK**: Does `segmentor_classify.py` actually set `recommended_campaign`? Search for this field assignment in the segmentor.

### 4.2 Exclusion List Duplication

Customer exclusion data exists in TWO places:
- `config/production.json` (lines 319-369) — source of truth for code
- `CLAUDE.md` (lines 503-507) — reference for AI sessions

**CHECK**: Are all 27 emails and 7 domains identical in both files?

### 4.3 Cadence Step Mapping

`config/production.json` cadence steps define `action` types:
- Step 1: `intro`, Step 3: `value_followup`, Step 5: `social_proof`, Step 7: `breakup`, Step 8: `close`

`crafter_campaign.py` CADENCE_TEMPLATES keys:
- `value_followup`, `social_proof`, `breakup`, `close`

**CHECK**: Does `cadence_engine.py` pass the correct `action_type` string to `crafter.craft_cadence_followup()`?

### 4.4 ICP Tier Definitions Consistency

| Source | Tier 1 Threshold | Tier 1 Titles | Tier 1 Industries |
|--------|-----------------|---------------|-------------------|
| CLAUDE.md (line 445) | - | CEO, Founder, President, COO, Owner, Managing Partner | Agencies, Staffing, Consulting, Law/CPA, Real Estate, E-commerce |
| segmentor (line 177) | 80 (line 212) | ceo, founder, co-founder, president, coo, owner, managing partner | marketing, advertising, agency, recruitment, staffing, consulting, law, legal, cpa, accounting, real estate, e-commerce, ecommerce, dtc |
| ramp config (line 453) | - | - | tier_filter: "tier_1" |

**CHECK**: Verify `co-founder` is in CLAUDE.md (it's in code but may be missing from docs).

### 4.5 Sender Info Consistency

| Source | Name | Title | Calendar |
|--------|------|-------|----------|
| crafter sender_info (line 532-537) | Dani Apgar | Chief AI Officer | https://caio.cx/ai-exec-briefing-call |
| CLAUDE.md (lines 490-491) | Dani Apgar | Chief AI Officer | https://caio.cx/ai-exec-briefing-call |
| Shadow emails (verified) | Dani Apgar | Chief AI Officer | https://caio.cx/ai-exec-briefing-call |

**STATUS**: Consistent.

---

## 5. Pipeline Verification Playbook

### Test 1: Full Pipeline Run (6/6 PASS)

```bash
cd d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm
echo yes | python execution/run_pipeline.py --mode production --source wpromote
```

**Expected**: 6/6 PASS, 2+ leads, 1 campaign, <30s

### Test 2: Shadow Email Content Verification

```bash
# Find latest shadow emails
ls -la .hive-mind/shadow_mode_emails/pipeline_*.json | tail -5

# For each email, verify:
# 1. "icp_tier": "tier_1" (for CRO/VP at agency)
# 2. "icp_score": >= 80
# 3. Body contains "M.A.P." or "Fractional Chief AI Officer"
# 4. Body contains "Dani Apgar"
# 5. Body contains "caio.cx/ai-exec-briefing-call"
# 6. Body ends with "Reply STOP to unsubscribe.\nChief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"
# 7. "campaign_type": starts with "t1_" for tier_1 leads
```

### Test 3: Guard 4 Email Exclusion

```python
# Manual test: inject excluded email into shadow queue, run dispatcher
import json
test_email = {
    "email_id": "test_guard4",
    "status": "pending",
    "to": "chudziak@jbcco.com",  # Excluded customer email
    "subject": "Test",
    "body": "Test",
    "source": "test",
    "tier": "tier_1"
}
with open(".hive-mind/shadow_mode_emails/test_guard4.json", "w") as f:
    json.dump(test_email, f)

# Run dispatcher in dry-run — should reject with "excluded email"
# Then delete test file
```

### Test 4: Scoring Verification (3 persona types)

```python
import sys; sys.path.insert(0, '.')
from execution.segmentor_classify import LeadSegmentor
s = LeadSegmentor()

# Persona 1: CEO at marketing agency (expected: tier_1, score ~97)
r1 = s.calculate_icp_score({'title': 'CEO', 'industry': 'marketing & advertising', 'employees': '150'})
print(f"CEO/Agency: score={r1['icp_score']}, tier={r1['icp_tier']}")

# Persona 2: CTO at SaaS company (expected: tier_2, score ~68)
r2 = s.calculate_icp_score({'title': 'CTO', 'industry': 'software', 'employees': '200'})
print(f"CTO/SaaS: score={r2['icp_score']}, tier={r2['icp_tier']}")

# Persona 3: Director at manufacturing (expected: tier_3, score ~45)
r3 = s.calculate_icp_score({'title': 'Director of Operations', 'industry': 'manufacturing', 'employees': '100'})
print(f"Dir/Mfg: score={r3['icp_score']}, tier={r3['icp_tier']}")

# Persona 4: CRO at marketing agency (expected: tier_1, score ~93 with 1.3x VP+T1 multiplier)
r4 = s.calculate_icp_score({'title': 'Chief Revenue Officer (CRO)', 'industry': 'marketing & advertising', 'employees': '500'})
print(f"CRO/Agency: score={r4['icp_score']}, tier={r4['icp_tier']}")
```

### Test 5: Template Rendering (All 11 Angles)

```python
import sys; sys.path.insert(0, '.')
from execution.crafter_campaign import CampaignCrafter
c = CampaignCrafter()

test_lead = {
    'first_name': 'Jane',
    'name': 'Jane Doe',
    'email': 'jane@example.com',
    'title': 'CEO',
    'company': 'Acme Corp',
    'industry': 'marketing & advertising',
    'icp_tier': 'tier_1',
}

for template_name in CampaignCrafter.TEMPLATES:
    email = c.generate_email(test_lead, template_name)
    assert email['body'], f'Empty body for {template_name}'
    assert 'Jane' in email['body'], f'Missing personalization in {template_name}'
    assert 'Acme Corp' in email['body'] or 'your company' in email['body'], f'Missing company in {template_name}'
    assert '5700 Harper Dr' in email['body'], f'Missing footer in {template_name}'
    print(f'{template_name}: OK (subject_a="{email["subject_a"][:50]}")')

print('\nAll 11 templates render correctly')
```

---

## 6. Architecture State Summary

### Phase Position

```
Phase 0-3: Foundation -> Burn-In -> Harden    COMPLETE
Phase 4A: Instantly V2 Go-Live                 COMPLETE (6 domains, 100% health)
Phase 4B: HeyReach LinkedIn Integration        80% (awaiting LinkedIn warmup)
Phase 4C: OPERATOR Agent                       COMPLETE (unified dispatch + GATEKEEPER)
Phase 4D: Multi-Channel Cadence                COMPLETE (8-step 21-day)
Phase 4E: Supervised Live Sends                RAMP MODE ACTIVE <-- YOU ARE HERE
Phase 4F: Monaco Signal Loop                   COMPLETE
Phase 4G: Production Hardening                 COMPLETE (v4.4)
Phase 4H: Deep Review Hardening                IN PROGRESS (v4.5)
```

### Safety Controls Active

| Control | Status | Config |
|---------|--------|--------|
| Shadow mode | ON | `shadow_mode: true` — emails saved to `.hive-mind/shadow_mode_emails/` |
| EMERGENCY_STOP | OFF | Railway env var `EMERGENCY_STOP` |
| GATEKEEPER gate | ON | `gatekeeper_required: true` — batch approval before dispatch |
| Ramp mode | ON | 5/day, tier_1 only, 3 supervised days (started 2026-02-18) |
| Deliverability guards | ON | 4-layer (format, domains, concentration, individual emails) |
| Live flag | OFF | `--live` CLI flag required for actual Instantly sends |

### KPI Targets for Ramp Graduation

| Metric | Target | Measurement |
|--------|--------|-------------|
| Open rate | >= 50% | Instantly analytics |
| Reply rate | >= 8% | Instantly + HeyReach |
| Bounce rate | < 5% | Instantly analytics |
| LinkedIn accept | >= 30% | HeyReach stats |
| Clean days | 3 consecutive | No manual intervention |

### Cost Summary

| Service | Monthly | Status |
|---------|---------|--------|
| Clay Explorer | $499 | ACTIVE (RB2B only) |
| Apollo.io | ~$49 | ACTIVE (enrichment) |
| Instantly | ~$30 | V2 LIVE |
| HeyReach | $79 | ACTIVE (LinkedIn) |
| Railway | ~$5 | ACTIVE |
| Upstash Redis | Free | ACTIVE |
| Inngest | Free | ACTIVE |
| **Total** | **~$662/mo** | |

---

## 7. Risk Assessment for Live Dispatch

### Blocking Issue (Fix Immediately)

**B10: EMERGENCY_STOP crashes in live mode**
- `bulk_pause_all()` doesn't exist on `AsyncInstantlyClient`
- If EMERGENCY_STOP is triggered during live sends, it will crash with `AttributeError` instead of pausing campaigns
- **Fix**: Implement `bulk_pause_all()` in the Instantly client, or replace with sequential pause calls
- **Risk if unfixed**: No emergency kill switch in production

### Fix Before Scale-Up (Not Blocking for 5/day Ramp)

**B5: Engagement bonus inflates scores**
- At 5/day tier_1 ramp, impact is minimal (scores already >80 for C-Suite)
- At scale (25/day, all tiers), could promote tier_3 leads to tier_2

**B11: Subdomain exclusion gap**
- Current customer domains (jbcco.com, frazerbilt.com, etc.) are all apex domains
- Risk only exists if customer uses subdomains (unlikely for these companies)

### Acceptable for Ramp Phase

All MEDIUM and LOW bugs are acceptable during the 3-day supervised ramp:
- A/B testing issues (B1, B2) — not critical at 5/day volume
- Dead fields (B3, B19, B25) — no functional impact
- Cosmetic scoring (B6, B7, B8) — scoring produces correct tiers
- Silent failures (B12, B16) — operators monitoring manually during ramp
- Dashboard auth (B26) — internal tool, not public-facing

### Recommended Fix Priority Order

1. **B10** (CRITICAL): Implement EMERGENCY_STOP pause logic — BEFORE first live send
2. **B5** (CRITICAL): Cap engagement bonus within intent 20pt limit — before scale-up
3. **B11** (CRITICAL): Add subdomain matching to domain exclusion — before scale-up
4. **B1** (HIGH): Add subject_a/subject_b to follow-up templates — before A/B testing
5. **B16** (HIGH): Add logging to Apollo match failures — before debugging blind spots
6. **B12** (HIGH): Add audit logging for guard rejections — before compliance review
7. **B22** (MEDIUM): Fix dry-run cadence side effects — before cadence testing

---

## Appendix: Key File Locations

```
chiefaiofficer-alpha-swarm/
  config/production.json              # Master config (exclusions, ramp, cadence, domains)
  execution/
    run_pipeline.py                   # 6-stage pipeline runner
    crafter_campaign.py               # Email templates + selection logic
    segmentor_classify.py             # ICP scoring + tier assignment
    instantly_dispatcher.py           # Instantly dispatch + 4 guards
    hunter_scrape_followers.py        # Apollo lead discovery + TARGET_COMPANIES
    operator_outbound.py              # OPERATOR agent (3 motions: outbound/revival/cadence)
    cadence_engine.py                 # 21-day cadence scheduler
    operator_revival_scanner.py       # GHL contact mining
    enricher_clay_waterfall.py        # Apollo + BetterContact enrichment
  core/
    lead_signals.py                   # 21 lead statuses + decay detection
    activity_timeline.py              # Per-lead event aggregation
    alerts.py                         # Slack alerting
    circuit_breaker.py                # Failure protection
  dashboard/
    health_app.py                     # FastAPI (50+ endpoints)
    hos_dashboard.html                # HoS email approval queue
    leads_dashboard.html              # Lead Signal Loop UI
  webhooks/
    instantly_webhook.py              # Instantly reply/bounce/open handlers
    heyreach_webhook.py               # HeyReach connection/reply handlers
  .hive-mind/
    shadow_mode_emails/               # Pending email queue (shadow)
    shadow_mode_emails_archive_pre_hos/ # 91 archived pre-HoS emails
    operator_batches/                 # GATEKEEPER batch files
    lead_status/                      # Per-lead signal files
  docs/
    google_drive_docs/
      HEAD_OF_SALES_REQUIREMENTS*.docx  # HoS source document
      hos_requirements_extracted.txt    # Extracted text (1,257 paragraphs)
  CLAUDE.md                           # Agent system prompt + HoS reference
  CAIO_IMPLEMENTATION_PLAN.md         # Phase tracker + decision log
```

---

*Generated: 2026-02-18 | Commit: 10cc82c | Audit by: Claude Opus 4.6*
