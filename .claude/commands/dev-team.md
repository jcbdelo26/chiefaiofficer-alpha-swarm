---
model: opus
description: Run a 3-pass code review using FDE, PM, and PTO agents. Each pass reviews from a different lens (implementation, product, testing). Use after completing a sprint task.
---

# /dev-team — 3-Pass Code Review

<context>
<purpose>Sequential review of recent changes through 3 specialized lenses</purpose>
<agents>
  - Pass 1: Forward Deployment Engineer (implementation safety)
  - Pass 2: Product Manager (plan alignment + safety contract)
  - Pass 3: Principal Test Officer (test quality + coverage)
</agents>
<philosophy>Ship fast, but never ship blind. Three reviewers catch what one misses.</philosophy>
</context>

---

## Process

### Step 0: Scope Discovery

Before starting reviews, identify what changed:

```
1. Run `git diff --stat` to see modified files
2. Run `git log --oneline -5` to see recent commits
3. Read task.md to understand the current sprint context
4. Identify: source files changed, test files changed, config changes
```

Output a summary:
```
REVIEW SCOPE:
  Sprint: {sprint_name}
  Task: {task_id} — {description}
  Files changed: {count}
  Source files: [list]
  Test files: [list]
  Config files: [list]
```

---

### Step 1: FDE Review (Pass 1 of 3)

Use the `forward-deployment-engineer` agent mindset.

```
Focus: Implementation correctness and production safety
Read: All modified source files + their callers
Check: Error handling, pattern consistency, edge cases, regressions
Output: FDE REVIEW report (see agent definition)
```

<checkpoint>
```
=== FDE REVIEW COMPLETE (Pass 1/3) ===
Findings: {count} ({breakdown})
Verdict: {verdict}

Proceeding to PM review...
```
</checkpoint>

---

### Step 2: PM Review (Pass 2 of 3)

Use the `product-manager` agent mindset.

```
Focus: Plan alignment, safety contract, scope assessment
Read: task.md + CLAUDE.md + config/production.json + changed files
Check: Sprint alignment, safety controls, scope creep, documentation
Output: PM REVIEW report (see agent definition)
```

<checkpoint>
```
=== PM REVIEW COMPLETE (Pass 2/3) ===
Alignment: {status}
Safety: {status}
Scope: {verdict}

Proceeding to PTO review...
```
</checkpoint>

---

### Step 3: PTO Review (Pass 3 of 3)

Use the `principal-test-officer` agent mindset.

```
Focus: Test quality, coverage gaps, mock realism
Read: All test files + .githooks/pre-commit + source files
Check: Assertion quality, coverage, mock realism, pre-commit suite
Output: PTO REVIEW report (see agent definition)
```

<checkpoint>
```
=== PTO REVIEW COMPLETE (Pass 3/3) ===
Tests: {count} new, {count} modified
Coverage: {verdict}
Quality: {verdict}
```
</checkpoint>

---

### Step 4: Consolidated Report

Combine all 3 passes into a final report:

```
============================================================
  DEV TEAM REVIEW — CONSOLIDATED REPORT
============================================================

Sprint: {sprint_name}
Task: {task_id}
Files: {count} changed

--- Pass 1: FDE (Implementation) ---
Verdict: {verdict}
Critical: {count} | High: {count} | Medium: {count} | Low: {count}
Top issue: {description}

--- Pass 2: PM (Product) ---
Verdict: {verdict}
Alignment: {status}
Safety: {status}
Scope: {status}
Top concern: {description}

--- Pass 3: PTO (Testing) ---
Verdict: {verdict}
New tests: {count}
Coverage: {status}
Top gap: {description}

============================================================
  OVERALL VERDICT: SHIP IT / NEEDS FIXES / BLOCK
============================================================

ACTION ITEMS:
1. [item from FDE]
2. [item from PM]
3. [item from PTO]
```

---

## When to Use

```
Use /dev-team when you need to:
- Review a completed sprint task before committing
- Audit changes before a Railway deployment
- Validate a complex multi-file change
- Get a second opinion on a tricky implementation
```

## When NOT to Use

```
Skip /dev-team for:
- Single-line typo fixes
- Documentation-only changes
- Adding a comment or log statement
- Changes already reviewed in a previous /dev-team pass
```
