---
model: opus
description: Interactive campaign planning with skepticism checkpoints
---

# Campaign Planning Command

<context>
<purpose>Create structured campaign plans with human verification</purpose>
<output_dir>.hive-mind/plans/</output_dir>
<philosophy>Skeptical planning prevents wasted implementation</philosophy>
</context>

## Process Steps

### Step 1: GATHERING
<step name="gathering">
<action>Collect all relevant context about the campaign request</action>
<questions>
- What is the target segment?
- What is the campaign goal (meetings, demos, signups)?
- What channels are available (email, LinkedIn, both)?
- What is the timeline?
- What existing campaigns can we reference?
</questions>
<output>Raw context dump to share with human</output>
</step>

### Step 2: RESEARCH
<step name="research">
<action>Analyze existing campaigns and patterns</action>
<use_command>.claude/commands/research_leads.md</use_command>
<also_check>
- .hive-mind/campaigns/ for past performance
- directives/campaign_sop.md for constraints
- templates/ for approved formats
</also_check>
<output>Structured findings in compact XML</output>
</step>

### Step 3: QUESTIONS
<step name="questions">
<action>Surface uncertainties and assumptions</action>
<format>
```
ASSUMPTIONS I'M MAKING:
1. [assumption] — risk if wrong: [consequence]
2. ...

QUESTIONS I NEED ANSWERED:
1. [question] — blocking: [yes/no]
2. ...

THINGS THAT SEEM OFF:
1. [observation] — concern: [why]
```
</format>
<checkpoint>⏸️ PAUSE — Wait for human response before proceeding</checkpoint>
</step>

### Step 4: STRUCTURE
<step name="structure">
<action>Create campaign skeleton</action>
<include>
- Campaign name and ID
- Target segment definition
- Channel strategy
- Sequence structure (touchpoints, timing)
- Success metrics
</include>
<exclude>Actual copy, specific subjects, body text</exclude>
</step>

### Step 5: DETAILS
<step name="details">
<action>Fill in specifics after structure approval</action>
<requires>Human approval of Step 4 structure</requires>
<output>Complete campaign plan document</output>
</step>

---

## What We're NOT Doing

<not_doing>
- ❌ Implementing anything — this is PLANNING only
- ❌ Creating email copy without structure approval
- ❌ Guessing at ICP criteria — use defined segments
- ❌ Skipping the QUESTIONS step — this is mandatory
- ❌ Proceeding without human verification at Step 3
- ❌ Recommending tools/platforms not in tech stack
- ❌ Creating new segments without directive update
</not_doing>

---

## Output Format

Save plan to `.hive-mind/plans/{date}_{campaign_name}_plan.md`:

```markdown
# Campaign Plan: {name}

## Metadata
- Created: {date}
- Status: DRAFT | APPROVED | IMPLEMENTING
- Approved By: {name} | PENDING
- Target Segment: {segment}

## Objective
{1-2 sentences}

## Structure
### Sequence
| Step | Channel | Timing | Purpose |
|------|---------|--------|---------|
| 1    | Email   | Day 0  | Intro   |
| 2    | LinkedIn| Day 3  | Soften  |
...

## Success Metrics
- Primary: {metric} target: {value}
- Secondary: {metric} target: {value}

## Copy (if approved)
### Email 1: {subject}
{body}

## Verification Checklist
- [ ] ICP alignment confirmed
- [ ] Compliance review passed
- [ ] AE approval obtained (GATEKEEPER)
```

---

## Human Verification Checkpoint

<checkpoint type="mandatory">
Before moving from QUESTIONS to STRUCTURE:

```
═══════════════════════════════════════════
🛑 HUMAN VERIFICATION REQUIRED
═══════════════════════════════════════════
Please review the assumptions and questions above.

Reply with:
- Answers to blocking questions
- Corrections to assumptions
- "PROCEED" to continue to STRUCTURE step
═══════════════════════════════════════════
```
</checkpoint>
