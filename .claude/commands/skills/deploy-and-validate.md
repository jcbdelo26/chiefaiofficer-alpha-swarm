# Deploy and Validate

Compound skill: deploys to Railway and runs full validation suite.

## Steps

1. **Pre-deploy checks**
   - Run pre-commit test suite: `python -m pytest` with curated files from `.githooks/pre-commit`
   - Run ASCII enforcement: `python scripts/check_ascii.py --staged`
   - Verify no uncommitted changes: `git status`

2. **Deploy**
   - Commit changes with conventional commit format
   - Push to main branch (triggers Railway auto-deploy)
   - Wait for Railway build to complete

3. **Post-deploy validation**
   - Run all smoke tests: `python scripts/smoke_all.py --base-url https://caio-swarm-dashboard-production.up.railway.app --token <DASHBOARD_AUTH_TOKEN>`
   - This runs: deployed_full_smoke_checklist + strict_auth_parity_smoke + validate_dashboard_ui
   - Run doc freshness check: `python scripts/check_doc_freshness.py`

4. **Update records**
   - Update `docs/CAIO_CLAUDE_MEMORY.md` with new deploy hash and date
   - Update MEMORY.md with latest commit hash
   - Capture lesson if any issues were encountered: `python scripts/capture_lesson.py --category deployment --description "..."`

## Exit criteria
- All smoke tests pass
- Dashboard `/api/health` returns `status: healthy`
- MEMORY.md reflects new deploy state
