# Sprint Close

Compound skill: closes a sprint with full validation and documentation updates.

## Steps

1. **Run full test suite**
   - Pre-commit curated suite: all files listed in `.githooks/pre-commit`
   - Verify test count matches or exceeds expected count in `task.md`
   - Note any new test files that should be added to pre-commit

2. **Update trackers**
   - `task.md`: Update sprint history table with new sprint row (scope, test count, status)
   - `task.md`: Update test suite count in header
   - `docs/CAIO_TASK_TRACKER.md`: Update relevant section status, add change log entry
   - Mark sprint tasks as DONE in tracker tables

3. **Update documentation freshness**
   - Run `python scripts/check_doc_freshness.py` — fix any stale docs
   - Update `last_updated` in YAML frontmatter of changed docs

4. **Commit with conventional format**
   - Use format: `feat(sprint-N): <summary of sprint scope>`
   - Include test count in commit body

5. **Post-sprint capture**
   - Capture key lessons: `python scripts/capture_lesson.py --category <cat> --description "..."`
   - Update MEMORY.md if any new key files, patterns, or gotchas emerged

## Exit criteria
- All pre-commit tests pass
- task.md sprint history updated
- CAIO_TASK_TRACKER.md change log updated
- No stale docs flagged by freshness checker
