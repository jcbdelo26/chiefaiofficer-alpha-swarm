# Chief AI Officer Alpha Swarm - Gemini & Agent Instructions

> **CRITICAL: PRODUCTION DEPLOYMENT RULES**
> This system is LIVE in production. All changes must be deployed immediately to prevent "stale code" errors.

## 🚀 Deployment SOP (Standard Operating Procedure)

**Whenever you modify code (Python or HTML):**
1.  **Run the Safe Deploy Script:**
    ```bash
    python execution/deploy_safe.py
    ```
    *This script automatically checks for uncommitted changes, verifies connections, and triggers `railway up`.*

2.  **NEVER** bypass this script unless debugging a specific deployment failure.
3.  **NEVER** leave the production server running an older version than the codebase.

---

## ⚡ API Synchronization Rule

**The Dashboard (`hos_dashboard.html`) and API (`health_app.py`) are coupled.**

*   **IF** you add a function to `hos_dashboard.html` (e.g., `rejectEmail` calling `/api/reject`)...
*   **THEN** you MUST confirm `health_app.py` has the corresponding endpoint (`@app.post("/api/emails/{email_id}/reject")`).
*   **Verify signatures:** Ensure query params vs JSON body match exactly.

---

## 🚫 Anti-Regression Rules

1.  **Do NOT Revert:** Never replace the `hos_dashboard.html` with an older version. It contains critical fixes (v2.3 CSS, ContentEditable, API calls).
2.  **Check Imports:** specific libraries like `GHLOutreachClient` must be imported inside the function or at top level if used. Guard against `NameError`.
3.  **Preserve Context:** When editing `implementation_plan.md` or `task.md`, check `rollout_roadmap.md` first. It is the source of truth.

---

## 📁 Project Structure

*   `dashboard/` -> Contains the UI (`hos_dashboard.html`) and API (`health_app.py`).
*   `core/` -> Contains the brain (`messaging_strategy.py`, `signal_detector.py`).
*   `execution/` -> Scripts for manual or cron execution.
*   `.hive-mind/` -> Persistent storage (do not delete).

---

## 🛠 Command Cheatsheet

*   **Deploy:** `railway up --detach`
*   **Logs:** `railway logs --service caio-swarm-dashboard`
*   **Status:** `railway status`
*   **Test Script:** `python execution/test_connections.py`

---

## 🔌 External API Resilience Rules

> **Added 2026-02-13:** After LinkedIn scraper hung the pipeline for 8+ minutes.

### Timeout Requirements
1.  **Every external API call MUST have a hard timeout (≤30s).** No exceptions.
2.  **NEVER use `time.sleep()` for rate-limit handling.** Use `tenacity` exponential backoff with `max=10`.
3.  **Every pipeline stage MUST complete within 60 seconds.** Use `asyncio.wait_for()` around network-bound stages.

### Session Validation
4.  **Before calling LinkedIn/Clay/any cookie-based API, ALWAYS validate the session first.** Call `/voyager/api/me` for LinkedIn. If validation fails, skip the call and use fallback data.
5.  **LINKEDIN_COOKIE** is the canonical env var name (not `LINKEDIN_COOKIES` plural). Must match in `.env`, `.env.staging`, and all code.

### Method Signature Verification
6.  **When calling a method from another module, ALWAYS check the actual method signature.** Don't assume parameters exist. Use `view_code_item` or `grep_search` first.

### Scraper Architecture
7.  **All 4 LinkedIn scrapers (`followers`, `events`, `posts`, `groups`) are scaffolds.** They return empty results. Real scraping requires Proxycurl API or Playwright browser automation.
8.  **The pipeline MUST work with test-data fallback in all modes.** `_is_safe_mode()` triggers on SANDBOX, DRY_RUN, or missing `LINKEDIN_COOKIE`.
9.  **Scraper errors are INFO-level, not CRITICAL.** The `generate_test_batch()` fallback is the expected path in local dev and staging.

### Health Monitoring
10. **`health_monitor.py` checks scraper readiness** via `_check_scraper_readiness()`. This validates cookie existence, length, and live session status.
11. **Run `python execution/health_monitor.py --once`** before any production pipeline run to verify all APIs are reachable.

---

## 🧠 Skills Library

**Location**: `.claude/skills/` in the workspace root (NOT inside `chiefaiofficer-alpha-swarm/`).

A library of 26 SKILL.md files organized into 9 categories:

| Directory | Key Skills |
|-----------|-----------|
| `02-development/` | tdd, mcp-builder, webapp-testing, changelog-generator |
| `03-security/` | vibesec, systematic-debugging, defense-in-depth |
| `05-business-marketing/` | lead-research-assistant, competitive-ads, content-research-writer |
| `06-creative-media/` | brand-guidelines, theme-factory, canvas-design |
| `07-productivity/` | file-organizer, invoice-organizer |
| `09-workspace-meta/` | skill-creator, template-skill |

### When to Read Skills

- **Before building/deploying**: Read `vibesec` + `defense-in-depth`
- **Before debugging**: Read `systematic-debugging`
- **Before lead-gen tasks**: Read `lead-research-assistant`
- **Before writing content**: Read `content-research-writer`
- **When creating MCP servers**: Read `mcp-builder`

### Always-Active Guardrails (from Skills)

- Every external API call MUST have a timeout (≤30s)
- Never hardcode secrets; use env vars
- Reproduce bugs before attempting fixes
- Write failing tests before fixing bugs
