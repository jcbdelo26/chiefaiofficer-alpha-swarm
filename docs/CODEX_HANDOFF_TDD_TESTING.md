# Codex Handoff: TDD & Testing Feedback Loops

> **Purpose**: Targeted regression testing on the critical path + closing open feedback loops before Phase 5 autonomy graduation.
> **NOT full TDD** — startup-practical, blast-radius-prioritized.

---

## Architecture Context

```
Local Pipeline (Windows) → Redis (Upstash) → Railway Dashboard (Linux)
                               ↑                        ↑
                     shadow_queue.py              health_app.py
                     (dual-write: Redis + disk)   (reads Redis only)
```

- 12 agents + Queen orchestrator, 6-stage pipeline: SCRAPE → ENRICH → SEGMENT → CRAFT → APPROVE → SEND
- Phase 4E active: 5 emails/day, tier_1 only, GATEKEEPER batch approval required
- Existing: 1,372 tests / 56 files, CI gate at 95% replay-harness, smoke test matrices
- Pytest config: `pytest.ini` with `asyncio_mode=auto`, `conftest.py` resets singletons

---

## Task 1: `tests/test_shadow_queue.py`

**Why**: 3 production incidents. Zero tests. When this breaks, HoS dashboard shows empty queue — blocks ALL supervised sends.

**Source**: `core/shadow_queue.py` (263 lines)

**Module API**:
- `push(email_data, shadow_dir=None) -> bool` — dual-write to Redis + filesystem
- `list_pending(limit=20, shadow_dir=None) -> List[Dict]` — Redis sorted set first, filesystem fallback
- `update_status(email_id, new_status, shadow_dir=None, extra_fields=None) -> Optional[Dict]`
- `get_email(email_id, shadow_dir=None) -> Optional[Dict]`
- `_prefix() -> str` — reads `CONTEXT_REDIS_PREFIX` → `STATE_REDIS_PREFIX` → `"caio"` fallback
- `_key(email_id)` → `"{prefix}:shadow:email:{email_id}"`
- `_index_key()` → `"{prefix}:shadow:pending_ids"`

**Global state**: `_client` (Redis instance or None), `_init_done` (bool). Must reset both per test.

**Mock pattern** — create `FakeRedis` (dict-backed) implementing:
- `set(key, value)`, `get(key) -> str|None`
- `zadd(key, mapping)`, `zrevrange(key, start, end) -> list`
- `zrem(key, *members)`, `scan_iter(match, count) -> iter`
- `ping() -> True`

Patch via `monkeypatch`:
```python
monkeypatch.setattr(shadow_queue, "_client", fake_redis)
monkeypatch.setattr(shadow_queue, "_init_done", True)
```

Use `tmp_path` for filesystem isolation. Follow pattern in `tests/test_operator_dedup_and_send_path.py`.

**Tests (12-15)**:

| # | Test | Assert |
|---|------|--------|
| 1 | `push()` with Redis available | Returns True, data in FakeRedis at `_key(email_id)` |
| 2 | `push()` with Redis unavailable + shadow_dir | Returns True, JSON file written to `tmp_path` |
| 3 | `push()` with both available | Returns True, data in BOTH Redis and filesystem |
| 4 | `push()` with both unavailable (no Redis, no shadow_dir) | Returns False |
| 5 | `push()` with `status=pending` | `email_id` added to sorted set at `_index_key()` |
| 6 | `push()` with `status=approved` | NOT added to sorted set |
| 7 | `list_pending()` from Redis sorted set | Returns items newest-first, matches push order |
| 8 | `list_pending()` removes stale index entries | If underlying key deleted, entry removed from sorted set |
| 9 | `list_pending()` removes non-pending from index | If status changed to "approved", entry removed |
| 10 | `list_pending()` rebuilds index from stray keys | Keys exist without index → rebuilds sorted set, returns results |
| 11 | `list_pending()` filesystem fallback | Redis unavailable → reads from `tmp_path/*.json`, filters `status=pending` |
| 12 | `update_status()` changes Redis + filesystem | Both locations updated, returns updated data |
| 13 | `update_status()` removes from pending index | New status != "pending" → `zrem` called |
| 14 | `get_email()` from Redis | Returns parsed data |
| 15 | `get_email()` filesystem fallback | Redis unavailable → reads from `tmp_path` |

**Prefix regression test**: Set `CONTEXT_REDIS_PREFIX=caio:production:context` via monkeypatch. Verify `_key("test123")` == `"caio:production:context:shadow:email:test123"`. This is pitfall #2 from CLAUDE.md.

**Acceptance**: `pytest tests/test_shadow_queue.py -v` — all green. Tests pass with BOTH FakeRedis and `_client=None` (file-only mode).

---

## Task 2: `tests/test_enricher_waterfall.py`

**Why**: Every pipeline run depends on correct parsing. Bad parsing → garbage emails, wrong personalization, silent corruption downstream. Zero tests today.

**Source**: `execution/enricher_waterfall.py`

**Key functions to test** (pure functions — no mocking needed for parser tests):
- `_parse_apollo_response(response_json) -> dict` — extracts fields from Apollo People Match
- `_parse_bettercontact_response(response_json) -> dict` — extracts fields from BetterContact
- `_calculate_quality(enriched_data) -> float` — quality score 0-100
- `_select_provider() -> str` — picks provider based on available API keys

**Read these sections** before writing tests:
- Apollo parser: search for `def _parse_apollo_response` in `execution/enricher_waterfall.py`
- BetterContact parser: search for `def _parse_bettercontact_response`
- Quality calculator: search for `def _calculate_quality`

**Tests (15-18)**:

| # | Group | Test | Assert |
|---|-------|------|--------|
| 1 | Apollo | Complete response (all fields) | All fields extracted correctly |
| 2 | Apollo | Missing `organization` key | No crash, `company_name=None` or empty |
| 3 | Apollo | `email_status=verified` | `email_verified=True` |
| 4 | Apollo | `email_status=unverified` | `email_verified=False` |
| 5 | Apollo | `personal_emails` populated | Extracted to output |
| 6 | Apollo | `phone_numbers` array with multiple types | Correct primary phone extraction |
| 7 | Apollo | Empty/None response | Returns empty dict or None, no crash |
| 8 | BetterContact | Deliverable email | `work_email` populated |
| 9 | BetterContact | `catch_all_safe` status | Email still usable |
| 10 | BetterContact | Undeliverable status | `work_email=None` |
| 11 | Routing | `APOLLO_API_KEY` set | provider="apollo" |
| 12 | Routing | No Apollo key, `BETTERCONTACT_API_KEY` set | provider="bettercontact" |
| 13 | Routing | No keys at all | Falls back to mock mode |
| 14 | Quality | Full enriched data (email + phone + company + title) | Score >= 70 |
| 15 | Quality | Only email | Score <= 40 |
| 16 | Quality | Empty data | Score == 0 or minimal |

**Mock strategy for routing tests**: `monkeypatch.setenv("APOLLO_API_KEY", "test")` or `monkeypatch.delenv("APOLLO_API_KEY", raising=False)`. For HTTP calls: `unittest.mock.patch("requests.post")`.

**Acceptance**: `pytest tests/test_enricher_waterfall.py -v` — all green.

---

## Task 3: `tests/test_instantly_dispatcher_guards.py`

**Why**: 4-layer deliverability guard system is the last defense before real emails reach recipients. If Guard 2 fails → emails to competitors. If Guard 3 fails → spam one company.

**Source**: `execution/instantly_dispatcher.py`

**Read these sections** before writing:
- Guard functions: search for `_validate_email_format`, domain exclusion logic, concentration limit logic
- Config loading: how guards read from `config/production.json` → `guardrails.deliverability`
- The `_load_approved_emails()` function that filters shadow emails through all 4 guards

**Config structure** (`config/production.json` → `guardrails.deliverability`):
```json
{
  "excluded_recipient_domains": ["apollo.io", "gong.io", ...],  // 12+ domains
  "excluded_recipient_emails": ["chudziak@jbcco.com", ...],     // 27 emails
  "max_leads_per_domain_per_batch": 3,
  "require_valid_email_format": true
}
```

**Pattern**: Same `monkeypatch` + `tmp_path` as `tests/test_operator_dedup_and_send_path.py`. Write minimal `production.json` to `tmp_path/config/`. Write shadow email JSON files to `tmp_path/.hive-mind/shadow_mode_emails/`.

**Tests (12-15)**:

| # | Guard | Test | Assert |
|---|-------|------|--------|
| 1 | G1 | Valid email `user@company.com` | Passes format check |
| 2 | G1 | Invalid email `no-at-sign` | Fails format check |
| 3 | G1 | Invalid email `user@` | Fails format check |
| 4 | G2 | Email at `apollo.io` (competitor) | Blocked |
| 5 | G2 | Email at `gong.io` (competitor) | Blocked |
| 6 | G2 | Email at `safe-company.com` | Passes |
| 7 | G2 | Case insensitive: `User@APOLLO.IO` | Blocked |
| 8 | G3 | 3 emails from same domain | All 3 pass |
| 9 | G3 | 4th email from same domain | Rejected (max 3/domain) |
| 10 | G3 | Different domains don't interfere | Each gets own 3-count |
| 11 | G4 | Exact match from excluded list | Blocked |
| 12 | G4 | Case insensitive individual match | Blocked |
| 13 | Integration | Canary email (`canary: true`) | Never dispatched |
| 14 | Integration | `_do_not_dispatch: true` flag | Never dispatched |
| 15 | Integration | `EMERGENCY_STOP` env var set | All dispatch blocked |

**Load actual exclusion lists**: Read `config/production.json` in test setup, iterate all 27 customer emails through guards, assert zero pass. This catches accidental config edits.

**Acceptance**: `pytest tests/test_instantly_dispatcher_guards.py -v` — all green.

---

## Task 4: `.coveragerc` + CI Update

**Create** `.coveragerc` at project root:
```ini
[run]
source = core,execution
omit =
    */mcp-servers/*
    */dashboard/*
    */__pycache__/*
    */tests/*

[report]
fail_under = 40
show_missing = true
exclude_lines =
    pragma: no cover
    if __name__
    raise NotImplementedError
```

**Modify** `.github/workflows/replay-harness.yml` — add a `unit-tests` job:
```yaml
  unit-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -r requirements.txt pytest pytest-asyncio pytest-cov
      - name: Run tests with coverage
        env:
          PYTHONPATH: .
        run: |
          python -m pytest tests/ -x -q --tb=short \
            --ignore=tests/failure_scenarios \
            --ignore=tests/stress_test_swarm.py \
            --cov=core --cov=execution \
            --cov-report=term-missing \
            --cov-fail-under=40
```

**Acceptance**: CI workflow runs, coverage >= 40%.

---

## Task 5: `tests/test_pipeline_integration.py`

**Why**: Individual stages are tested in isolation, but inter-stage data format mismatches cause silent corruption. Classic example: `company` field is string in enricher output but crafter expects dict.

**Source files**:
- `execution/enricher_waterfall.py` — enricher output format
- `execution/segmentor_icp.py` — segmentor input/output
- `execution/crafter_campaign.py` — crafter input/output
- `execution/run_pipeline.py` — send stage input
- `core/shadow_queue.py` — final output format
- `tests/golden/caio_alpha_golden_set_v1.json` — fixture data

**Tests (6-8)**:

| # | Test | Assert |
|---|------|--------|
| 1 | Enricher output → segmentor input | All required fields present, correct types |
| 2 | Segmentor output → crafter input | `tier`, `icp_score`, `industry` fields present |
| 3 | Crafter output → send stage input | `subject`, `body`, `recipient_data` fields present |
| 4 | Send stage → `shadow_queue.push()` → `list_pending()` | Round-trip data integrity |
| 5 | Status lifecycle: pending → approved → dispatched | `update_status()` transitions correctly |
| 6 | `company` field normalization | String and dict both handled without crash |

**Mock strategy**: Load golden set fixtures. Patch Redis with FakeRedis from Task 1. Run through actual parser/transform functions.

**Acceptance**: `pytest tests/test_pipeline_integration.py -v` — all green.

---

## Task 6: `core/feedback_loop.py` + `tests/test_feedback_loop.py`

**Why**: `FeedbackCollector.export_for_training()` produces RL training tuples but NOTHING consumes them. The system cannot learn from live campaign outcomes. This is the highest-leverage gap for Phase 5.

**Source files to read first**:
- `core/feedback_collector.py` — `export_for_training()` (line 357), `FeedbackType` enum, `REWARD_MAP`
- `core/self_annealing.py` — `learn_from_outcome()`, `get_best_action()`, `anneal_step()`

**New module** `core/feedback_loop.py` (~150 lines):

```python
class FeedbackLoop:
    def __init__(self, collector: FeedbackCollector, engine: SelfAnnealingEngine,
                 auto_apply: bool = False):
        ...

    def process_pending(self) -> dict:
        """
        Export unprocessed tuples from collector.
        Map each to WorkflowOutcome.
        Feed to engine.learn_from_outcome().
        Mark as applied (track processed feedback_ids).
        Return summary: {processed: int, total_reward: float, refinements: list}
        """
        ...

    def get_recommendations(self) -> list:
        """Return high-confidence refinements from engine for human review."""
        ...
```

**Key constraints**:
- `auto_apply=False` by default — refinements are surfaced, NOT auto-applied to config
- Must be idempotent — tracks `processed_ids` set, second call processes nothing new
- Maps `FeedbackType` rewards: MEETING_BOOKED=+1.0, REPLY_POSITIVE=+0.7, BOUNCE=-0.2, etc.
- Terminal states (MEETING_BOOKED, UNSUBSCRIBE, BOUNCE) mark `done=True`

**Tests (8-10)**:

| # | Test | Assert |
|---|------|--------|
| 1 | `process_pending()` no events | Returns `{processed: 0, total_reward: 0.0}` |
| 2 | MEETING_BOOKED event | Reward +1.0 fed to engine |
| 3 | BOUNCE event | Reward -0.2 fed to engine |
| 4 | Idempotent | Second call returns `{processed: 0}` |
| 5 | Mixed events | Correct aggregate reward |
| 6 | `get_recommendations()` after positive data | Returns non-empty refinement list |
| 7 | End-to-end: Collector → Loop → Engine | Refinements appear in engine state |
| 8 | `auto_apply=False` guard | Refinements returned but NOT written to config |

**Acceptance**: `pytest tests/test_feedback_loop.py -v` — all green.

---

## Task 7: Wire VerificationHooks into Send Stage

**Why**: `core/verification_hooks.py` runs 12 compliance rules and produces a report, but the pipeline doesn't check it before sending. Failed leads should be skipped.

**Source**: `execution/run_pipeline.py` — find the send stage function (search for `_stage_send` or the stage that calls `shadow_queue.push` or `instantly_dispatcher`)

**Change** (~20 lines): Before pushing to shadow queue or dispatching, call:
```python
from core.verification_hooks import VerificationHooks

hooks = VerificationHooks()
report = hooks.run_all_verifications(lead, email_content, agent_name="CRAFTER")
if report.overall_status == "failed":
    logger.warning("Verification FAILED for %s: %s", lead.get("email"), report.failed_rules)
    skipped_count += 1
    continue  # Skip this lead
```

**Do NOT block on warnings** — only on `overall_status == "failed"` (ERROR-severity rules).

**Acceptance**: Pipeline run with a deliberately bad lead (missing unsubscribe link) skips that lead instead of queuing it.

---

## Task 8: Wire CircuitBreaker Pre-Check

**Why**: If Apollo's circuit opens mid-pipeline, the enricher silently returns None for all leads. Pipeline continues with garbage data.

**Source**: `execution/run_pipeline.py` — find the enrichment stage entry point

**Change** (~15 lines): Before ENRICH and SEND stages:
```python
from core.circuit_breaker import get_registry

registry = get_registry()
if not registry.is_available("apollo_api"):
    logger.error("ENRICH stage aborted: Apollo circuit breaker OPEN")
    return StageResult(success=False, error="Apollo circuit breaker OPEN")
```

Similarly for SEND stage — check `instantly_api` and `heyreach_api` circuits.

**Acceptance**: If a circuit is forced OPEN, pipeline aborts that stage with clear error instead of silently returning None.

---

## Execution Order

| Order | Task | Creates/Modifies | Dependencies |
|-------|------|-----------------|--------------|
| 1 | Task 1: test_shadow_queue.py | CREATE `tests/test_shadow_queue.py` | None |
| 2 | Task 2: test_enricher_waterfall.py | CREATE `tests/test_enricher_waterfall.py` | None |
| 3 | Task 3: test_instantly_dispatcher_guards.py | CREATE `tests/test_instantly_dispatcher_guards.py` | None |
| 4 | Task 4: .coveragerc + CI | CREATE `.coveragerc`, MODIFY `.github/workflows/replay-harness.yml` | None |
| 5 | Task 5: test_pipeline_integration.py | CREATE `tests/test_pipeline_integration.py` | Tasks 1-3 (reuse FakeRedis) |
| 6 | Task 6: feedback_loop.py | CREATE `core/feedback_loop.py` + `tests/test_feedback_loop.py` | Read `core/feedback_collector.py` + `core/self_annealing.py` first |
| 7 | Task 7: Wire VerificationHooks | MODIFY `execution/run_pipeline.py` (+20 lines) | Read `core/verification_hooks.py` first |
| 8 | Task 8: Wire CircuitBreaker | MODIFY `execution/run_pipeline.py` (+15 lines) | Read `core/circuit_breaker.py` first |

Tasks 1-3 are independent and can execute in parallel.

---

## Verification Checklist

After all tasks:
```bash
# Sprint 1 tests
python -m pytest tests/test_shadow_queue.py tests/test_enricher_waterfall.py tests/test_instantly_dispatcher_guards.py -v

# Sprint 2 tests
python -m pytest tests/test_pipeline_integration.py tests/test_feedback_loop.py -v

# Full suite (must not break existing 1,372 tests)
python -m pytest tests/ -x -q --tb=short

# Coverage
python -m pytest tests/ --cov=core --cov=execution --cov-report=term-missing
```

**Do NOT proceed to Phase 5 graduation** unless:
- All new tests pass
- Full existing suite still passes (1,372+ tests)
- Coverage >= 40%
- Smoke tests pass: `python scripts/deployed_full_smoke_checklist.py`

---

## What NOT to Do

- Do NOT adopt full TDD ceremony — impractical for this stage
- Do NOT auto-apply self-annealing refinements to config — leave manual for Phase 4E
- Do NOT auto-adjust ramp limits from health monitor — human decision during ramp
- Do NOT add tests for modules that already have good coverage (guardrails, security, compliance)
- Do NOT mock external APIs with live calls — use dict fixtures and `monkeypatch`
- Do NOT break existing test patterns — follow `conftest.py` fixtures and `monkeypatch` + `tmp_path` convention
