# 🧠 Thoughts System - SDR Automation Knowledge Base

> Shared memory architecture for the Chief AI Officer Alpha Swarm

---

## Overview

The `thoughts/` directory serves as the persistent memory layer for the SDR automation swarm. Inspired by HumanLayer's pattern, this system enables agents and human operators to capture, organize, and retrieve knowledge across sessions.

**Purpose:**
- Preserve institutional knowledge across agent sessions
- Document proven patterns and learnings
- Enable searchable, structured knowledge retrieval
- Support handoffs between agents and humans

---

## Directory Structure

```
thoughts/
├── README.md                 # This file
├── shared/                   # Collaborative knowledge base
│   ├── research/            # Deep-dive research documents
│   ├── patterns/            # Proven patterns and frameworks
│   ├── playbooks/           # Operational procedures
│   └── learnings/           # Post-mortems and insights
├── searchable/              # Quick-reference indexed notes
└── templates/               # Standard document templates
    ├── research.md          # Research document template
    ├── plan.md              # Phase-based plan template
    └── handoff.md           # Session transition template
```

---

## Directory Purposes

### `shared/research/`
Deep-dive research documents on specific topics:
- Competitor analysis
- Market research
- Technology evaluations
- Integration feasibility studies

### `shared/patterns/`
Proven, reusable patterns:
- Objection handling frameworks
- Personalization strategies
- Segmentation approaches
- Campaign optimization techniques

### `shared/playbooks/`
Step-by-step operational procedures:
- Campaign launch checklist
- Escalation workflows
- Compliance audits
- System troubleshooting

### `shared/learnings/`
Post-mortems and retrospectives:
- Campaign performance reviews
- Failed experiment analysis
- System incident reports
- A/B test conclusions

### `searchable/`
Quick-reference notes indexed for fast retrieval:
- Brief insights (1-2 paragraphs)
- Tagged for semantic search
- Date-stamped for recency

---

## Creating Notes

### For Research Documents

Use `templates/research.md`:

```yaml
---
date: 2026-01-15
researcher: agent_name
git_commit: abc1234
status: draft | in_review | published
tags: [sdr, automation, specific-topic]
---
```

### For Patterns

Document proven approaches with:
- Problem statement
- Solution pattern
- Implementation examples
- Performance data

### For Playbooks

Include:
- Prerequisites
- Step-by-step instructions
- Expected outcomes
- Rollback procedures

### For Learnings

Capture:
- Context and timeline
- What happened
- Root cause analysis
- Action items and follow-ups

---

## Best Practices for SDR Automation Knowledge

### 1. **Tag Consistently**
Use standardized tags:
- `tier-1`, `tier-2`, `tier-3`, `tier-4` - Lead tiers
- `objection-*` - Objection types
- `personalization` - Personalization strategies
- `compliance` - CAN-SPAM, GDPR, LinkedIn ToS
- `integration-*` - Platform integrations

### 2. **Reference Existing Context**
Link to canonical sources:
- `directives/sdr_specifications.md` - Automation rules
- `directives/icp_criteria.md` - ICP scoring
- `templates/objections/*.j2` - Response templates

### 3. **Include Performance Data**
When documenting patterns, capture:
- Open rates, reply rates, conversion rates
- Sample sizes and time periods
- Statistical significance notes

### 4. **Version Control Awareness**
Include git commit references when documenting:
- System state at time of observation
- Specific configurations being tested

### 5. **Handoff Completeness**
When ending a session, create a handoff note with:
- Current task status
- Critical file references
- Pending decisions
- Blocking issues

---

## Searching Thoughts

### By Tag
```bash
grep -r "tags:.*personalization" thoughts/
```

### By Date
```bash
find thoughts/ -name "*.md" -newer thoughts/reference_date.txt
```

### By Status
```bash
grep -r "status: published" thoughts/
```

---

## Integration Points

| System Component | Usage |
|-----------------|-------|
| **CRAFTER Agent** | Reads patterns for email generation |
| **SEGMENTOR Agent** | References ICP learnings |
| **GATEKEEPER Agent** | Consults playbooks for escalation |
| **Human Operators** | Reviews learnings and handoffs |

---

*Last Updated: 2026-01-15*
*Version: 1.0*
