---
title: Codex Handoff - Sprints B + C
version: "1.0"
last_updated: 2026-03-02
audience: [codex, engineers, agent-manager]
tags: [codex, handoff, sprints, remediation, agentic-engineering]
canonical_for: [codex-handoff-b-c]
related_docs: [AGENTIC_ENGINEERING_AUDIT_HANDOFF.md, CAIO_TASK_TRACKER.md, DORMANT_ENGINES.md, GLOSSARY.md]
---

# CODEX HANDOFF: Sprints B + C (Structural + Compound Engineering)

## Context

Sprint A (Quick Wins) has been completed. This handoff covers Sprints B (Structural Improvements) and C (Compound Engineering Enhancements) from the Agentic Engineering Audit v1.1 remediation plan.

**Prerequisite reading**:
- `docs/AGENTIC_ENGINEERING_AUDIT_HANDOFF.md` (v1.1 audit baseline + scorecard)
- `docs/CAIO_TASK_TRACKER.md` Section 9 (full Codex handoff spec)
- `CLAUDE.md` (session config, pitfalls, mandatory read order)

**Completed in Sprint A** (do NOT redo):
- A-1: DORMANT headers on 5 engine files + `docs/DORMANT_ENGINES.md`
- A-2/A-3/A-4: Security hardening P0 (N1-N7) + tests + smoke script
- A-5: `docs/GLOSSARY.md`
- A-6: Cleaned 16 TODO stubs in `core/agent_manager.py`
- A-7: YAML frontmatter on 8 critical docs
- A-8: `scripts/check_ascii.py` + pre-commit integration

---

## SPRINT B: Structural Improvements (6 tasks)

### B-1: Create Knowledge Index (Gap G1.1)

**Goal**: Master index of all docs organized by phase, role, and status.

**Output**: `docs/KNOWLEDGE_INDEX.md`

**Requirements**:
- List all files in `docs/` (96+ files) with: filename, purpose (1 line), audience, phase relevance
- Organize by category: Architecture, Deployment, API Integration, Testing, Handoffs, Operations, Archive
- Include files from root: `CLAUDE.md`, `task.md`, `CAIO_IMPLEMENTATION_PLAN.md`, `CONTEXT_HANDOFF.md`, `DEPLOYMENT_GUIDE.md`, `DEPLOYMENT_CHECKLIST.md`
- Add YAML frontmatter with standard fields
- Link from `CLAUDE.md` as optional reference (do NOT add to mandatory read order)

**Acceptance**: File exists, covers 90%+ of docs, categories are logical, renders in markdown viewer.

---

### B-2: Create Unified CLI Entry Point (Gap G3.1)

**Goal**: Single CLI that delegates to existing scripts — zero new logic.

**Output**: `cli.py` at project root

**Requirements**:
- Use `argparse` (no new dependencies)
- Subcommands mapping to existing scripts:
  | Command | Delegates To |
  |---------|-------------|
  | `cli.py deploy` | `scripts/deploy_shadow_mode.py` |
  | `cli.py validate` | `scripts/validate_apis.py` |
  | `cli.py health` | `scripts/check_health.py` |
  | `cli.py canary` | `scripts/canary_lane_b.py` |
  | `cli.py seed-queue` | `core/seed_queue.py` (or POST to `/api/admin/seed_queue`) |
  | `cli.py approve` | `scripts/approval_cli.py` |
  | `cli.py smoke` | `scripts/deployed_full_smoke_checklist.py` |
  | `cli.py smoke-auth` | `scripts/strict_auth_parity_smoke.py` |
  | `cli.py ascii` | `scripts/check_ascii.py` |
  | `cli.py diagnose` | `scripts/diagnose.py` (Sprint C, stub if not yet created) |
- Each subcommand passes through `sys.argv` to the target script
- `cli.py --help` shows all available subcommands with descriptions
- Must handle missing scripts gracefully (print "not yet implemented" if target doesn't exist)

**Acceptance**: `python cli.py --help` shows all commands. `python cli.py health --help` delegates correctly.

---

### B-3: Create Smoke Test Orchestrator (Gap G3.3)

**Goal**: Single script that runs all smoke tests in sequence with summary.

**Output**: `scripts/smoke_all.py`

**Requirements**:
- Run in order:
  1. `scripts/deployed_full_smoke_checklist.py` (if it accepts `--base-url`)
  2. `scripts/strict_auth_parity_smoke.py --base-url <URL> --token <TOKEN>`
  3. `scripts/endpoint_auth_smoke.py` (if it exists and accepts similar args)
- CLI: `--base-url` (required), `--token` (required), `--timeout` (default 20)
- Collect pass/fail per script, output JSON summary + human-readable table
- Exit 0 if all pass, exit 1 if any fail
- Use only stdlib (subprocess, json, argparse)

**Acceptance**: `python scripts/smoke_all.py --base-url <URL> --token <TOKEN>` runs all smoke scripts and reports combined results.

---

### B-4: Create Cross-Environment Bridge Test (Gap G2.4)

**Goal**: Test that LOCAL <-> RAILWAY data flow works correctly via Redis.

**Output**: `tests/test_cross_environment_bridge.py`

**Requirements**:
- Test `shadow_queue.push()` writes to correct Redis key format
- Test `shadow_queue.get_pending()` reads from correct Redis key format
- Verify Redis key uses `CONTEXT_REDIS_PREFIX` (not `STATE_REDIS_PREFIX`)
- Test filesystem fallback when Redis is unavailable (mock Redis failure)
- Test round-trip: push -> get_pending -> approve -> verify state change
- Use existing fixtures from `tests/conftest.py` and mock Redis
- Follow test patterns from `tests/test_shadow_queue.py` (read it first)

**Acceptance**: All tests pass in pre-commit suite. Covers the 3 incidents documented in CLAUDE.md pitfall #1.

---

### B-5: Create Dashboard UI Validation Script (Gap G2.2)

**Goal**: DOM-assertion validation for key dashboard endpoints.

**Output**: `scripts/validate_dashboard_ui.py`

**Requirements**:
- CLI: `--base-url` (required), `--token` (required)
- Checks per endpoint:
  | Endpoint | Expected |
  |----------|----------|
  | `/login` | HTTP 200, contains `name="token"` input |
  | `/sales` (with session) | HTTP 200, contains email table or "no pending" |
  | `/scorecard` (with session) | HTTP 200, contains KPI elements |
  | `/api/health` | HTTP 200, JSON with `status` field |
  | `/api/health/ready` | HTTP 200 |
  | `/api/runtime/dependencies` (with token) | HTTP 200, JSON with `auth` field |
- Use only stdlib (urllib, json, html.parser or regex)
- Output JSON summary with pass/fail per check

**Acceptance**: `python scripts/validate_dashboard_ui.py --base-url <URL> --token <TOKEN>` validates all endpoints.

---

### B-6: Create Doc Freshness Checker (Gap G1.3)

**Goal**: Detect stale docs by checking YAML frontmatter `last_updated` field.

**Output**: `scripts/check_doc_freshness.py`

**Requirements**:
- Scan all `.md` files in `docs/` and project root for YAML frontmatter
- Parse `last_updated` field
- Freshness policy:
  | Category | Max Age |
  |----------|---------|
  | `canonical_for` contains "runtime-truth" | 7 days |
  | `canonical_for` contains "sprint-tracker" | 7 days |
  | All other docs with frontmatter | 30 days |
- Output: list of stale docs with days-since-update
- Exit 0 if none stale, exit 1 if any found
- CLI: `--warn-only` (exit 0 even if stale), `--days N` (override default threshold)
- Do NOT add to pre-commit (informational only)

**Acceptance**: `python scripts/check_doc_freshness.py` reports stale docs correctly.

---

## SPRINT C: Compound Engineering Enhancements (5 tasks)

### C-1: Create MCP Server Catalog (Gap G3.2)

**Goal**: Comprehensive catalog of all 16 MCP servers.

**Output**: `docs/MCP_SERVER_CATALOG.md`

**Requirements**:
- For each server in `mcp-servers/`:
  | Field | Required |
  |-------|----------|
  | Name | Yes |
  | Directory | Yes |
  | Purpose (1 sentence) | Yes |
  | Exposed functions (name + params) | Yes |
  | Dependencies (APIs, env vars) | Yes |
  | Health check endpoint | If applicable |
  | Status (active/stub/deprecated) | Yes |
- Read each server's `server.py` or `index.js` to extract function signatures
- Add YAML frontmatter
- Differentiate between production-active servers and stubs

**Acceptance**: All 16 servers documented. Function signatures match actual code.

---

### C-2: Backfill Architecture Decision Records (Gap G1.4)

**Goal**: Record 5 key architectural decisions formally.

**Output**: `docs/adr/` directory with 6 files

**Files to create**:
1. `docs/adr/README.md` — ADR index and template
2. `docs/adr/001-redis-over-filesystem.md` — Why shadow emails go through Redis
3. `docs/adr/002-six-stage-pipeline.md` — Why Scrape>Enrich>Segment>Craft>Approve>Send
4. `docs/adr/003-tier-scoring-multipliers.md` — Why Tier_1=1.5x, Tier_2=1.2x
5. `docs/adr/004-shadow-mode-architecture.md` — Why shadow_mode before live sends
6. `docs/adr/005-context-redis-prefix.md` — Why CONTEXT_REDIS_PREFIX over STATE_REDIS_PREFIX

**ADR format** (per file):
```
# ADR-NNN: Title

## Status: Accepted

## Context
[What problem were we solving?]

## Decision
[What did we decide?]

## Consequences
[What are the trade-offs?]

## References
[Links to relevant code/docs]
```

**Source material**:
- CLAUDE.md pitfalls #1 and #2 for Redis decisions
- `config/production.json` for pipeline/shadow mode decisions
- `config/icp_config.py` for tier scoring
- `core/shadow_queue.py` for Redis bridge architecture

**Acceptance**: All 5 ADRs exist, reference actual code paths, and follow consistent format.

---

### C-3: Create Lessons Learned System (Gap G5.3)

**Goal**: CLI + doc for capturing operational lessons.

**Output**: `scripts/capture_lesson.py` + `docs/LESSONS_LEARNED.md`

**Requirements for `scripts/capture_lesson.py`**:
- CLI: `--category` (api/deployment/data/testing/security), `--description` (required), `--commit` (optional, auto-detects HEAD)
- Appends to `docs/LESSONS_LEARNED.md` with: date, commit hash, category, description
- Uses only stdlib

**Requirements for `docs/LESSONS_LEARNED.md`**:
- YAML frontmatter
- Pre-populated with 5-6 known lessons from CLAUDE.md pitfalls:
  1. LOCAL <-> Railway filesystem separation (pitfall #1)
  2. Redis prefix mismatch (pitfall #2)
  3. Missing transitive deps in requirements.txt (pitfall #4)
  4. Empty queue after approval (pitfall #5)
  5. Windows cp1252 emoji crash (emoji pitfall)
  6. Rich console + pytest capture conflict

**Acceptance**: `python scripts/capture_lesson.py --category api --description "..."` appends correctly.

---

### C-4: Create Compound Skill Commands (Gap G5.4)

**Goal**: Reusable Claude Code skill files for common multi-step workflows.

**Output**: 3 files in `.claude/commands/skills/`

**Skill 1: `deploy-and-validate.md`**:
```
Run the full deploy-and-validate workflow:
1. Run pre-commit tests
2. Deploy to Railway (if tests pass)
3. Run strict-auth parity smoke against deployed URL
4. Update docs/CAIO_CLAUDE_MEMORY.md with new commit hash
5. Report pass/fail summary
```

**Skill 2: `sprint-close.md`**:
```
Close the current sprint:
1. Run full pre-commit test suite
2. Update task.md with sprint completion status
3. Update CLAUDE.md with any new pitfalls discovered
4. Create git commit with sprint summary
5. Report test count and sprint status
```

**Skill 3: `diagnose-failure.md`**:
```
Diagnose a pipeline or deployment failure:
1. Check /api/health and /api/health/ready on production
2. Check /api/runtime/dependencies for auth state
3. Read recent git log for recent changes
4. Check core/event_log.py output if available
5. Check circuit breaker states
6. Report diagnosis summary with suggested fix
```

**Acceptance**: All 3 files exist in `.claude/commands/skills/`. Each is a valid Claude Code command file.

---

### C-5: Create Diagnosis CLI Tool (Gap G3.4)

**Goal**: Structured failure diagnosis from command line.

**Output**: `scripts/diagnose.py`

**Requirements**:
- CLI: `--base-url` (required), `--token` (required), `--case-id` (optional)
- Checks:
  1. `/api/health` — overall status
  2. `/api/health/ready` — readiness
  3. `/api/runtime/dependencies` — auth state, integration status
  4. `/api/metrics` — recent KPIs (if endpoint exists)
- If `--case-id` provided, search local `.hive-mind/` logs for trace events
- Output structured JSON with: health, auth_state, integrations, recent_errors
- Use only stdlib

**Acceptance**: `python scripts/diagnose.py --base-url <URL> --token <TOKEN>` outputs structured diagnosis.

---

## EXECUTION GUIDELINES FOR CODEX

### Environment Setup
```bash
cd chiefaiofficer-alpha-swarm
python -m pip install -r requirements.txt
git config core.hooksPath .githooks
```

### Test Validation (run after each task)
```bash
# Run the curated pre-commit suite
python -m pytest tests/test_security_hardening_v11.py tests/test_dashboard_login.py -x -q --tb=short -s

# Verify imports
python -c "import core; import execution; import dashboard"
```

### Key Pitfalls (MUST read before writing code)
1. **cp1252**: Windows terminal crashes on non-ASCII — use ASCII in all production code
2. **load_dotenv(override=True)**: Many modules call this — test fixtures MUST set env vars AFTER import
3. **Redis prefix**: Use `CONTEXT_REDIS_PREFIX` for cross-env data, never `STATE_REDIS_PREFIX`
4. **Rich + pytest**: Always use `-s` flag with pytest on Windows
5. **No new dependencies**: All scripts must use stdlib unless explicitly stated

### File Naming Conventions
- Scripts: `scripts/{action}_{target}.py` (e.g., `check_ascii.py`, `smoke_all.py`)
- Tests: `tests/test_{module}.py`
- Docs: `docs/{TOPIC}.md` (UPPER_SNAKE_CASE for docs)
- ADRs: `docs/adr/NNN-{topic}.md` (numbered, lowercase-kebab)

### Commit Convention
- Format: `type(scope): description`
- Types: feat, fix, docs, test, chore, hardening
- Example: `feat(tooling): add unified CLI entry point (Sprint B-2)`

---

## PRIORITY ORDER

Execute in this order (dependencies flow downward):

1. **B-4** (cross-env bridge test) — Tests existing code, zero risk
2. **B-1** (knowledge index) — Documentation only, zero risk
3. **B-6** (doc freshness checker) — New script, zero risk
4. **B-2** (unified CLI) — New script, delegates to existing
5. **B-3** (smoke orchestrator) — New script, delegates to existing
6. **B-5** (dashboard UI validation) — New script, hits deployed endpoints
7. **C-2** (ADRs) — Documentation only, zero risk
8. **C-3** (lessons learned) — New script + doc, zero risk
9. **C-4** (skill commands) — New command files, zero risk
10. **C-1** (MCP server catalog) — Documentation, requires reading 16 servers
11. **C-5** (diagnosis CLI) — New script, depends on B-3 patterns

---

## VERIFICATION CHECKLIST

After completing all Sprint B + C tasks:

- [ ] `docs/KNOWLEDGE_INDEX.md` exists and covers 90%+ of docs
- [ ] `cli.py --help` shows all subcommands
- [ ] `scripts/smoke_all.py --help` works
- [ ] `tests/test_cross_environment_bridge.py` passes
- [ ] `scripts/validate_dashboard_ui.py --help` works
- [ ] `scripts/check_doc_freshness.py` runs without error
- [ ] `docs/MCP_SERVER_CATALOG.md` covers all 16 servers
- [ ] `docs/adr/` contains 6 files (README + 5 ADRs)
- [ ] `scripts/capture_lesson.py --help` works
- [ ] `docs/LESSONS_LEARNED.md` has 5+ pre-populated entries
- [ ] `.claude/commands/skills/` contains 3 skill files
- [ ] `scripts/diagnose.py --help` works
- [ ] Pre-commit test suite still passes (502+ tests)
- [ ] `python -c "import core; import execution; import dashboard"` succeeds
