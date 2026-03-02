---
title: Lessons Learned
version: "1.0"
last_updated: 2026-03-02
audience: [all-agents, engineers]
tags: [lessons, gotchas, debugging, compound]
canonical_for: [lessons-learned]
---

# CAIO Alpha Swarm -- Lessons Learned

Compound knowledge base. Entries added via `python scripts/capture_lesson.py`.

---

### [2026-02-15] DATA (commit `2d074c6`)

Shadow queue prefix mismatch: `STATE_REDIS_PREFIX` differs between local ("") and Railway ("caio"), causing keys to not match across environments. Fix: always use `CONTEXT_REDIS_PREFIX` first (consistently "caio:production:context" everywhere). This caused 3 separate incidents of "no pending emails" on the Railway dashboard.

---

### [2026-02-20] DEPLOYMENT (commit `b12f595`)

Missing transitive dependencies in `requirements.txt`: `itsdangerous` and `python-multipart` were needed by SessionMiddleware and login form processing but were only installed transitively in local dev. Railway installs only from requirements.txt, causing 502 crashes. Always add explicit entries for every import.

---

### [2026-02-22] API (commit `42f829a`)

Apollo.io `q_organization_name` does fuzzy matching, not exact. Searching for "Acme Corp" can return "Acme Corporation International" and competitors. Always verify Apollo results against the intended target. Never set default scrape source to a competitor domain.

---

### [2026-02-26] PIPELINE (commit `d9b8c63`)

Production code with emoji characters (checkmarks, clipboard icons, hospital emojis) crashes on Windows cp1252 encoding. Python's `print()` throws `UnicodeEncodeError` when stdout is not UTF-8. Fix: use ASCII-only characters in production code, enforce via `scripts/check_ascii.py` in pre-commit hook.

---

### [2026-02-27] DASHBOARD (commit `f1cb70a`)

Query-token auth (`?token=` in URL) leaks credentials to browser history, server logs, and copied URLs. Fix: migrate to header-only auth (`X-Dashboard-Token`) and session cookies. Disable query-token in production via `DASHBOARD_QUERY_TOKEN_ENABLED=false`.

---

### [2026-03-01] TESTING (commit `9606327`)

Rich console + pytest capture conflict on Windows: Rich braille spinners cause encoding crashes when pytest captures stdout. Always use `-s` flag with pytest on Windows, and use ASCII-only spinners in production code.

---

