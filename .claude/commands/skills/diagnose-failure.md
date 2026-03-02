# Diagnose Failure

Compound skill: investigates a pipeline or deployment failure using trace correlation.

## Steps

1. **Identify the failure**
   - Check dashboard health: `GET /api/health` for component status
   - Check runtime dependencies: `GET /api/runtime/dependencies` for Redis, Inngest, auth state
   - If case_id available: `python scripts/diagnose.py --case-id <ID>` (when implemented)

2. **Trace the error path**
   - Check `.hive-mind/audit/` for recent gatekeeper logs
   - Check event log for correlation IDs: `core/event_log.py` JSONL files
   - Check circuit breaker states: which agents are tripped?

3. **Check common pitfalls (CLAUDE.md)**
   - Local vs Railway filesystem mismatch (pitfall #1)
   - Redis prefix mismatch — `CONTEXT_REDIS_PREFIX` vs `STATE_REDIS_PREFIX` (pitfall #2)
   - Missing deps in requirements.txt (pitfall #4)
   - Empty queue after approval (pitfall #5)

4. **Run targeted tests**
   - If API-related: `python scripts/validate_apis.py`
   - If dashboard-related: `python scripts/validate_dashboard_ui.py --base-url <URL> --token <TOKEN>`
   - If webhook-related: `python scripts/webhook_strict_smoke.py --base-url <URL> --dashboard-token <TOKEN>`

5. **Document findings**
   - Capture lesson: `python scripts/capture_lesson.py --category <cat> --description "Root cause: ..."`
   - If new pitfall: add to CLAUDE.md common pitfalls section
   - If recurring: create regression test in `tests/`

## Exit criteria
- Root cause identified
- Fix implemented and tested
- Lesson captured for compound knowledge
