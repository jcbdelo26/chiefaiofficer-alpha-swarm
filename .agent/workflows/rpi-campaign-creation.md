---
description: Research-Plan-Implement workflow for campaign creation with context engineering
---

# RPI Campaign Creation Workflow

> Based on Dex Horthy's "No Vibes Allowed" Context Engineering methodology

This workflow applies the **Research → Plan → Implement** (RPI) methodology to campaign generation, preventing semantic diffusion and keeping agents in the "Smart Zone".

## Overview

```
┌─────────────┐       ┌─────────────┐       ┌────────────────┐
│  RESEARCH   │──────▶│    PLAN     │──────▶│  IMPLEMENT     │
│  (compress  │       │  (compress  │       │  (execute from │
│   truth)    │       │   intent)   │       │   clean plan)  │
└─────────────┘       └─────────────┘       └────────────────┘
      │                     │                      │
      ▼                     ▼                      ▼
 research.json         plan.json            campaigns.json
      │                     │
      ▼                     ▼
 Human Review 1       Human Review 2 
                     (HIGH LEVERAGE)
```

## Key Concepts

### The "Dumb Zone"
When an AI's context window fills >40%, performance degrades significantly:
- Poor tool selection
- Repeated mistakes
- Hallucinations
- Missed patterns

**Solution**: Intentional compaction between phases keeps agents in the "Smart Zone" (<40% context).

### Semantic Diffusion
Loss of intended meaning when context passes between agents without compression.

**Solution**: Each phase outputs a structured summary that preserves intent while reducing tokens.

---

## Phase 1: RESEARCH

**Agent**: RESEARCHER sub-agent (fresh context)

**Purpose**: Compress truth — understand the lead batch without making changes

### Command

```powershell
# Generate research summary for campaign batch
python execution\rpi_research.py --input .hive-mind\segmented\<latest>.json
```

### Output

- **Location**: `.hive-mind/research/research_<timestamp>.json`
- **Contents**:
  - Lead cohort analysis (who are these people?)
  - Source pattern analysis (why are they prospects?)
  - ICP quality assessment
  - Personalization opportunity mapping
  - Compliance flags

### What Research Does

1. Analyzes lead demographics (titles, company sizes, industries)
2. Maps source patterns (where did these leads come from?)
3. Evaluates ICP score distribution and quality
4. Identifies personalization hooks available
5. Flags any compliance concerns
6. Generates compressed summary (~90% token reduction)

### 🛑 HUMAN CHECKPOINT 1

**Review the research summary before proceeding:**

- [ ] Does the lead cohort make sense for this campaign?
- [ ] Are the source patterns accurate?
- [ ] Is the ICP scoring reasonable?
- [ ] Are there any compliance flags that need attention?
- [ ] Are the personalization opportunities valid?

**If issues found**: Adjust input data or exclude problematic leads before planning.

---

## Phase 2: PLAN

**Agent**: PLANNER sub-agent (reads research, fresh context)

**Purpose**: Compress intent — create detailed implementation plan

### Command

```powershell
# Generate campaign plan based on research
python execution\rpi_plan.py --research .hive-mind\research\research_<timestamp>.json
```

### Output

- **Location**: `.hive-mind/plans/plan_<timestamp>.json`
- **Contents**:
  - Campaign type selection with rationale
  - Template selection per tier
  - Personalization strategy
  - A/B test hypotheses
  - Sequence timing recommendations
  - Expected metrics

### What Planning Does

1. Reviews research summary (NOT raw leads)
2. Selects appropriate campaign strategies
3. Maps template to tier/source combinations
4. Defines personalization depth per segment
5. Creates A/B testing plan
6. Sets sequence timing
7. Predicts expected metrics

### 🛑 HUMAN CHECKPOINT 2 (HIGH LEVERAGE)

**This is the most important review point!**

Review the plan BEFORE code generation:

- [ ] Is the overall campaign strategy sound?
- [ ] Do template selections match lead types?
- [ ] Is the personalization approach appropriate?
- [ ] Are the A/B test hypotheses valid?
- [ ] Is the sequence timing appropriate?
- [ ] Any compliance concerns with the approach?

**Why this matters**: Reviewing the plan is 10x more efficient than reviewing generated content. Changes here have maximum impact.

**If issues found**: Modify the plan directly before proceeding to implementation.

---

## Phase 3: IMPLEMENT

**Agent**: CRAFTER (reads plan, fresh context)

**Purpose**: Execute the plan with clean context

### Command

```powershell
# Execute campaign creation from approved plan
python execution\rpi_implement.py --plan .hive-mind\plans\plan_<timestamp>.json
```

### Output

- **Location**: `.hive-mind/campaigns/campaigns_<timestamp>.json`
- **Contents**:
  - Generated campaigns with all emails
  - Lead assignments
  - Personalization applied
  - Compliance validation results

### What Implementation Does

1. Loads approved plan (NOT research, NOT raw leads)
2. Processes leads in batches to stay in Smart Zone
3. Applies templates with personalization
4. Validates compliance on each email
5. Generates A/B variants
6. **Attaches semantic anchors** for context preservation
7. Bundles into campaign packages

### Semantic Anchors

Each generated campaign includes semantic anchors that preserve the WHY + WHAT + HOW context:

```json
"semantic_anchors": [
  "TEMPLATE: competitor_displacement - Default template - no specific source match",
  "PERSONALIZATION: deep depth using hooks: company_size_messaging, leadership_value_props",
  "A/B TEST: Subject A (pain point) vs Subject B (transformation) - expect A higher open rate",
  "REVIEW: AE approval required for 2 leads"
]
```

These anchors flow to GATEKEEPER and are displayed during AE review.

### Post-Implementation

After implementation, campaigns go to GATEKEEPER review:

```powershell
python execution\gatekeeper_queue.py --input .hive-mind\campaigns\campaigns_rpi_<timestamp>.json
```

The GATEKEEPER dashboard displays semantic anchors to give AEs full context for informed decision-making.

**If the plan was reviewed and approved:**
- Tier 3 campaigns may auto-approve (no semantic anchor for "REVIEW: AE approval")
- Tier 1-2 still require AE review of final content

---

## Quick Reference

### Command Sequence

```powershell
# Step 1: Research
python execution\rpi_research.py --input .hive-mind\segmented\latest.json

# [REVIEW RESEARCH]

# Step 2: Plan  
python execution\rpi_plan.py --research .hive-mind\research\research_<id>.json

# [REVIEW PLAN - HIGH LEVERAGE]

# Step 3: Implement
python execution\rpi_implement.py --plan .hive-mind\plans\plan_<id>.json

# Step 4: Queue for final review
python execution\gatekeeper_queue.py --input .hive-mind\campaigns\campaigns_<id>.json
```

### File Locations

| Phase | Output Location | Token Reduction |
|-------|-----------------|-----------------|
| Research | `.hive-mind/research/` | ~90% from raw leads |
| Plan | `.hive-mind/plans/` | ~50% from research |
| Implement | `.hive-mind/campaigns/` | Full output |

### Context Zone Targets

| Phase | Target Context Usage |
|-------|---------------------|
| Research | <30% (exploring) |
| Plan | <40% (reasoning) |
| Implement | <50% (executing) |

---

## Error Handling

### Research Phase Errors

```yaml
lead_file_not_found:
  action: Check path, verify segmentation ran
  
empty_lead_batch:
  action: Re-run segmentation with different input
  
compliance_critical_flags:
  action: Address before proceeding (e.g., remove unsubscribed)
```

### Plan Phase Errors

```yaml
research_too_old:
  action: Re-run research if >24 hours old
  
insufficient_quality:
  action: If <10 Tier 1+2 leads, consider skipping or adjusting
  
template_mismatch:
  action: Override template selection in plan
```

### Implementation Phase Errors

```yaml
context_overflow:
  action: Automatic batching kicks in; reduce batch size if needed
  
template_rendering_failure:
  action: Review plan for invalid personalization hooks
  
compliance_block:
  action: Review and fix compliance issues in plan
```

---

## Metrics

### Process Metrics

| Metric | Target |
|--------|--------|
| Research time | <2 minutes |
| Plan time | <1 minute |
| Implementation time | <30 seconds per lead |
| Total RPI cycle | <15 minutes for 100 leads |

### Quality Metrics

| Metric | Before RPI | After RPI |
|--------|------------|-----------|
| Template errors | 5-10% | <1% |
| Personalization accuracy | 70% | 95% |
| AE rejection rate | 25% | 5% |
| Context overflow events | Common | Rare |

---

## Tips for Success

1. **Never skip research**: Even for small batches, research provides crucial context compression.

2. **Plan review is highest leverage**: Spend more time here than anywhere else.

3. **Trust the compaction**: Each phase needs only its input summary, not the full history.

4. **Batch large jobs**: For >100 leads, implementation auto-batches to stay in Smart Zone.

5. **Track context usage**: If seeing degraded quality, check context utilization metrics.

---

*Based on Dex Horthy's "No Vibes Allowed: Solving Hard Problems in Complex Codebases" (AI Engineer 2025)*
