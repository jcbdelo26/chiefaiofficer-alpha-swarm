---
model: sonnet
description: Create context-compacted handoff document for session transitions
---

# Handoff Document Creation

<context>
<purpose>Preserve critical context for session transitions</purpose>
<output_dir>.hive-mind/handoffs/</output_dir>
<philosophy>Next session should start productive, not confused</philosophy>
</context>

## Gather Context

Before creating handoff, collect:

```bash
# Current git state
git rev-parse HEAD          # commit sha
git branch --show-current   # branch name
git status --short          # uncommitted changes
```

---

## Handoff Template

Create file: `.hive-mind/handoffs/{date}_{task_slug}_handoff.md`

```markdown
---
git_commit: {sha}
branch: {branch_name}
status: IN_PROGRESS | BLOCKED | READY_FOR_REVIEW | COMPLETE
created: {ISO_timestamp}
---

# Handoff: {Task Title}

## Task(s)

<current_task>
{What we were doing — 1-2 sentences max}
</current_task>

<next_action>
{The very next thing to do — specific and actionable}
</next_action>

---

## Critical References

<files priority="must_read">
- `path/to/file.py#L45-L67` — {why this matters}
- `path/to/other.md` — {why this matters}
</files>

<files priority="context">
- `path/to/background.py` — {optional context}
</files>

---

## Recent Changes

<changes since="{last_handoff_or_start}">
| File | Change | Lines |
|------|--------|-------|
| `execution/new.py` | Created campaign executor | 1-150 |
| `config/instantly.json` | Added rate limits | 12-18 |
</changes>

---

## Learnings

<learnings type="gotchas">
- {Thing that was surprising or tricky}
- {Constraint discovered during work}
</learnings>

<learnings type="decisions">
- Chose X over Y because {reason}
- {Other architectural decision}
</learnings>

---

## Artifacts

<artifacts>
| Type | Location | Status |
|------|----------|--------|
| Plan | `.hive-mind/plans/campaign_plan.md` | APPROVED |
| Research | `.hive-mind/research/sources.xml` | COMPLETE |
| Progress | `.hive-mind/campaigns/q1/progress.json` | Phase 2/4 |
</artifacts>

---

## Action Items

<action_items>
- [ ] {First thing next session must do}
- [ ] {Second priority item}
- [ ] {Third priority item}
</action_items>

<blockers>
- {If any blockers, list here with who can unblock}
</blockers>
```

---

## Compaction Rules

<compaction>
**DO include:**
- File paths with line numbers
- Specific error messages (verbatim)
- Decisions made and why
- Uncommitted changes list

**DO NOT include:**
- Full file contents (use references)
- Conversation history
- Exploration dead-ends (unless learning)
- Redundant context from existing docs
</compaction>

---

## Quality Check

Before saving handoff:
- [ ] Next action is specific (not "continue working")
- [ ] All file references exist and are correct
- [ ] Status accurately reflects state
- [ ] A new session could start immediately from this

---

## Auto-Trigger Conditions

Create handoff automatically when:
- Context window >50% full
- Explicit "create handoff" request
- Session ending with work in progress
- Switching to different major task
- Error blocks further progress
