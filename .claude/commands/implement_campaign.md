---
model: opus
description: Phase-by-phase campaign implementation with verification pauses
---

# Campaign Implementation Command

<context>
<purpose>Execute approved campaign plans in verified phases</purpose>
<input>.hive-mind/plans/{campaign}_plan.md (status: APPROVED)</input>
<philosophy>Trust completed work, verify incrementally</philosophy>
</context>

## Pre-Implementation Check

<prerequisite>
1. Locate plan file in `.hive-mind/plans/`
2. Verify status is APPROVED (not DRAFT)
3. Confirm AE approval via GATEKEEPER
4. If any check fails → STOP and report
</prerequisite>

---

## Execution Phases

### Phase 1: SETUP
<phase name="setup">
<tasks>
- [ ] Create campaign directory: `.hive-mind/campaigns/{campaign_id}/`
- [ ] Copy approved plan to campaign directory
- [ ] Initialize tracking file: `progress.json`
- [ ] Validate target segment exists in system
</tasks>
<verification>
```
═══════════════════════════════════════════
⏸️ PHASE 1 COMPLETE: SETUP
═══════════════════════════════════════════
Created: .hive-mind/campaigns/{id}/
Files: plan.md, progress.json

Ready to proceed to CONTENT phase?
Reply "CONTINUE" or provide corrections.
═══════════════════════════════════════════
```
</verification>
</phase>

### Phase 2: CONTENT
<phase name="content">
<tasks>
- [ ] Generate email templates from plan structure
- [ ] Create LinkedIn message variants
- [ ] Apply personalization tokens
- [ ] Save to `{campaign_id}/content/`
</tasks>
<verification>
```
═══════════════════════════════════════════
⏸️ PHASE 2 COMPLETE: CONTENT
═══════════════════════════════════════════
Generated:
- emails/step_1.md, step_2.md, step_3.md
- linkedin/connection.md, followup.md

Review content before loading to platforms?
Reply "CONTINUE" or request revisions.
═══════════════════════════════════════════
```
</verification>
</phase>

### Phase 3: LOAD
<phase name="load">
<tasks>
- [ ] Load sequences to Instantly (if email)
- [ ] Configure GHL workflow (if CRM-triggered)
- [ ] Set timing/delays per plan
- [ ] Verify in platform (provide screenshot or log)
</tasks>
<verification>
```
═══════════════════════════════════════════
⏸️ PHASE 3 COMPLETE: LOAD
═══════════════════════════════════════════
Loaded to:
- Instantly: Campaign #{id} created
- GHL: Workflow #{id} configured

Test with 1 lead before full activation?
Reply "CONTINUE" or "TEST FIRST".
═══════════════════════════════════════════
```
</verification>
</phase>

### Phase 4: ACTIVATE
<phase name="activate">
<tasks>
- [ ] Add target leads to campaign
- [ ] Activate sequences
- [ ] Set up monitoring alerts
- [ ] Update progress.json → status: ACTIVE
</tasks>
<verification>
```
═══════════════════════════════════════════
✅ PHASE 4 COMPLETE: ACTIVATE
═══════════════════════════════════════════
Campaign {name} is now LIVE

Leads enrolled: {count}
First send: {datetime}
Monitoring: enabled

Create handoff document for tracking?
═══════════════════════════════════════════
```
</verification>
</phase>

---

## Resume Protocol

<resume_logic>
When resuming implementation:

1. Read `{campaign_id}/progress.json`
2. Find first unchecked item in current phase
3. Trust all checked items as complete
4. Resume from unchecked item

```json
// progress.json example
{
  "campaign_id": "q1_tier1_outreach",
  "current_phase": "content",
  "phases": {
    "setup": {
      "status": "complete",
      "tasks": ["✓", "✓", "✓", "✓"]
    },
    "content": {
      "status": "in_progress",
      "tasks": ["✓", "✓", " ", " "]
    }
  },
  "last_updated": "2024-01-15T10:30:00Z"
}
```
</resume_logic>

---

## Handoff on Session End

<handoff_trigger>
If session is ending before Phase 4 completion:
1. Update progress.json with current state
2. Run `.claude/commands/create_handoff.md`
3. Save handoff to `.hive-mind/handoffs/`
</handoff_trigger>

---

## Error Handling

<on_error>
1. Log error to `{campaign_id}/errors.log`
2. Update progress.json → status: BLOCKED
3. Create handoff with error context
4. Do NOT proceed to next phase
5. Request human intervention
</on_error>
