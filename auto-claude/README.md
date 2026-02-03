# 🤖 Auto-Claude Development Workflow

> Local integration for autonomous feature development and improvement cycles

---

## Overview

This directory contains the Auto-Claude integration for the Alpha Swarm project. Auto-Claude is used for **development-time automation** - building new features, fixing bugs, and improving templates.

**Important**: Auto-Claude handles DEVELOPMENT. Claude-Flow handles PRODUCTION.

---

## Directory Structure

```
auto-claude/
├── README.md          # This file
├── specs/             # Feature specifications
│   ├── template.md    # Spec template
│   └── *.md          # Individual specs
├── outputs/           # Generated code (review before merge)
└── backlog.md         # Prioritized improvement backlog
```

---

## Quick Start

### 1. Download Auto-Claude

Download the latest stable release for Windows:
- [Auto-Claude-2.7.3-win32-x64.exe](https://github.com/AndyMik90/Auto-Claude/releases/download/v2.7.3/Auto-Claude-2.7.3-win32-x64.exe)

### 2. Install Claude Code CLI

```powershell
npm install -g @anthropic-ai/claude-code
```

### 3. Open Project in Auto-Claude

1. Launch Auto-Claude
2. Click "Open Project"
3. Select: `D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm`
4. Connect your Claude account via OAuth

---

## Creating a Spec

### Step 1: Copy Template

```powershell
Copy-Item "auto-claude\specs\template.md" "auto-claude\specs\001-your-feature.md"
```

### Step 2: Fill Out Spec

Edit the spec file with:
- **Goal**: What you want to achieve
- **Requirements**: Specific acceptance criteria
- **Context**: Relevant files and background
- **Constraints**: What NOT to do

### Step 3: Run Autonomous Build

In Auto-Claude:
```bash
# Interactive mode (recommended for first time)
python spec_runner.py --interactive

# Or direct spec execution
python run.py --spec 001
```

### Step 4: Review Output

Generated code appears in `auto-claude/outputs/`. Review before merging.

```bash
# Review changes
python run.py --spec 001 --review

# If approved, merge
python run.py --spec 001 --merge
```

---

## Spec Template

Use this structure for all specs:

```markdown
# [Feature Name]

## Goal
[One sentence describing what you want]

## Requirements
- [ ] Requirement 1
- [ ] Requirement 2
- [ ] Requirement 3

## Context
### Relevant Files
- `execution/file.py` - [why relevant]
- `directives/sop.md` - [why relevant]

### Background
[Any context Auto-Claude needs to know]

## Constraints
- Do NOT modify [protected files]
- Follow existing patterns in [reference file]
- Maintain compatibility with [system]

## Acceptance Criteria
1. [Test case 1]
2. [Test case 2]
3. [Test case 3]
```

---

## Common Spec Types

### Bug Fix Spec

```markdown
# Fix: [Bug Description]

## Problem
[What's broken, with error messages]

## Reproduction
1. [Step 1]
2. [Step 2]
3. [Expected vs Actual]

## Root Cause Analysis
[If known, otherwise "To be determined"]

## Solution
[Proposed fix approach]
```

### Feature Spec

```markdown
# Feature: [Feature Name]

## Goal
[Business value and user story]

## Requirements
[Detailed requirements]

## Integration Points
[How it connects to existing system]
```

### Improvement Spec

```markdown
# Improve: [Component Name]

## Current State
[What exists today]

## Desired State
[What it should become]

## Metrics
[How to measure improvement]
```

---

## Weekly Development Cycle

### Monday: Review & Plan
1. Review `learnings.json` for patterns
2. Check rejection reasons in GATEKEEPER
3. Identify improvement opportunities
4. Create specs for top 3 priorities

### Tuesday-Wednesday: Build
1. Run specs through Auto-Claude
2. Review generated code
3. Test changes locally
4. Create additional specs if needed

### Thursday: Integrate
1. Merge approved changes
2. Run full test suite
3. Update affected directives
4. Document changes

### Friday: Deploy & Monitor
1. Deploy to production
2. Monitor first runs
3. Update backlog with findings
4. Plan next week

---

## Integration with Alpha Swarm

### Files Auto-Claude Can Modify

```yaml
modifiable:
  - execution/*.py      # Execution scripts
  - mcp-servers/*/      # MCP server code
  - directives/*.md     # SOPs (with caution)
  - tests/*.py          # Test files

protected:
  - .env                # Never modify credentials
  - .hive-mind/         # Production data
  - CLAUDE.md           # Agent instructions
  - GEMINI.md           # Agent instructions
```

### Handoff to Claude-Flow

After Auto-Claude generates code:

1. **Test locally**: Run the script manually
2. **Merge to main**: Git commit
3. **Claude-Flow picks up**: Next scheduled run uses new code

---

## Troubleshooting

### Auto-Claude Not Finding Files

Make sure you opened the correct project root:
```
D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm
```

### Generated Code Doesn't Match Pattern

Add more context to the spec:
```markdown
## Reference Implementation
See `execution/existing_script.py` for pattern to follow.
```

### Build Fails

Check the spec for:
- Missing requirements
- Conflicting constraints
- Unclear acceptance criteria

---

## Resources

- [Auto-Claude GitHub](https://github.com/AndyMik90/Auto-Claude)
- [CLI Documentation](https://github.com/AndyMik90/Auto-Claude/blob/develop/guides/CLI-USAGE.md)
- [Discord Community](https://discord.gg/KCXaPBr4Dj)

---

*Version: 1.0*
*Created: 2026-01-15*
