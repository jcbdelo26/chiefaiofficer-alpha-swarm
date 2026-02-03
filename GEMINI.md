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
