# 🤖 Auto-Claude + Claude-Flow Integration Guide

> How to use Auto-Claude and Claude-Flow together without over-engineering

---

## Executive Summary

| Tool | Purpose | When to Use |
|------|---------|-------------|
| **Auto-Claude** | Development-time AI coding | Building/modifying scripts |
| **Claude-Flow** | Runtime agent orchestration | Production execution |

**They complement each other, not compete.**

---

## 1. Architecture Clarity

### The Complete Picture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DEVELOPMENT TIME                                     │
│                         (Auto-Claude Domain)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │   SPEC RUNNER   │───▶│  MULTI-AGENT    │───▶│  QA PIPELINE    │         │
│  │   (Planning)    │    │  CODING         │    │  (Validation)   │         │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘         │
│           │                     │                      │                    │
│           └─────────────────────┴──────────────────────┘                    │
│                                 │                                            │
│                    PRODUCES: execution/*.py, mcp-servers/*, tests/*         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼ Git Push / File Sync
┌─────────────────────────────────────────────────────────────────────────────┐
│                          RUNTIME                                             │
│                          (Claude-Flow Domain)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │   ORCHESTRATOR  │───▶│  AGENT SWARM    │───▶│  MCP SERVERS    │         │
│  │   (Alpha Queen) │    │  (5 Agents)     │    │  (Tool Access)  │         │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘         │
│           │                     │                      │                    │
│           └─────────────────────┴──────────────────────┘                    │
│                                 │                                            │
│                    EXECUTES: Daily workflows, lead processing                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Auto-Claude Usage Patterns

### Pattern 1: New Feature Development

**Use Case**: Adding a new scraping source (e.g., LinkedIn Newsletters)

```bash
# In Auto-Claude terminal:

# 1. Create feature spec
cat > specs/001-newsletter-scraping.md << 'EOF'
# Newsletter Subscriber Scraping

## Goal
Add capability to scrape LinkedIn Newsletter subscribers as a lead source.

## Requirements
- Input: Newsletter URL
- Output: Subscriber list with profiles
- Rate limit: Same as followers (100/hour)
- Store in: .hive-mind/scraped/newsletters/

## Integration
- Follow hunter_scrape_followers.py pattern
- Add to HUNTER agent's capabilities
- Update scraping_sop.md directive
EOF

# 2. Run autonomous development
python run.py --spec 001

# 3. Review generated code
python run.py --spec 001 --review

# 4. If approved, merge to Alpha Swarm
python run.py --spec 001 --merge --target "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
```

### Pattern 2: Bug Fix

**Use Case**: Fixing rate limiting issue in Clay integration

```bash
# In Auto-Claude:

# 1. Describe the bug
cat > specs/002-clay-rate-fix.md << 'EOF'
# Fix Clay API Rate Limiting

## Problem
enricher_clay_waterfall.py hits rate limits when processing >50 leads.

## Root Cause
No backoff between batch calls.

## Solution
- Add exponential backoff
- Implement batch chunking (20 leads per batch)
- Add retry logic per chunk
EOF

# 2. Auto-fix
python run.py --spec 002

# 3. Test fix
python run.py --spec 002 --review
```

### Pattern 3: Template Improvement

**Use Case**: AE rejected 5 campaigns for "wrong tone"

```bash
# In Auto-Claude:

# 1. Create improvement spec from learnings
cat > specs/003-tone-improvement.md << 'EOF'
# Template Tone Improvement

## Problem
AE rejections citing "wrong tone" - too salesy.

## Analysis
Review learnings.json for rejection patterns.

## Solution
- Update voice_guide.md with examples
- Modify crafter_templates.py
- Add pre-send tone check
- Include 3 sample improvements
EOF

# 2. Generate improvements
python run.py --spec 003
```

---

## 3. Claude-Flow Usage Patterns

### Pattern 1: Daily Automated Workflow

**This runs in production without human intervention.**

```bash
# Initialize swarm (once)
npx claude-flow@alpha swarm init --topology mesh

# Check swarm status
npx claude-flow@alpha swarm status

# Swarm runs automatically via scheduled tasks
# See: deployment_framework.md for scheduler setup
```

### Pattern 2: On-Demand Scraping

**AE requests immediate scrape of specific source.**

```bash
# Spawn HUNTER for specific task
npx claude-flow@alpha swarm spawn --agent hunter \
  --task "Scrape followers of https://linkedin.com/company/newcompetitor"
```

### Pattern 3: Campaign Rush

**Need to generate campaigns for urgent opportunity.**

```bash
# Priority campaign generation
npx claude-flow@alpha workflow run lead-harvesting \
  --source "urgent-event-list.json" \
  --priority high \
  --skip-queue  # Goes to AE immediately
```

---

## 4. When NOT to Use Each Tool

### Don't Use Auto-Claude For:

```yaml
avoid_auto_claude_for:
  - Running production workflows
  - Live data processing
  - AE approval flows
  - Real-time lead routing
  - Campaign sending
  
reason: "Auto-Claude is for building, not running"
```

### Don't Use Claude-Flow For:

```yaml
avoid_claude_flow_for:
  - Writing new Python scripts
  - Modifying existing code
  - Creating new templates
  - Updating SOPs/directives
  - Debugging issues
  
reason: "Claude-Flow is for orchestration, not development"
```

---

## 5. Integration Workflow

### Weekly Development Cycle

```
Monday-Wednesday: Development Mode (Auto-Claude)
├── Review last week's learnings.json
├── Identify improvement opportunities
├── Create specs for fixes/features
├── Run Auto-Claude autonomous builds
├── Review and test changes
└── Prepare for deployment

Thursday: Integration & Testing
├── Merge Auto-Claude outputs to Alpha Swarm
├── Run full test suite
├── Validate in staging mode
└── Prepare for production

Friday: Production Validation
├── Deploy changes via Git
├── Run production with new code
├── Monitor for issues
└── Collect weekend metrics

Weekend: Autonomous Operation (Claude-Flow)
├── Scheduled workflows run automatically
├── No development activity
├── System self-monitors
└── Alerts if issues arise
```

### Change Deployment Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Auto-Claude │────▶│   Review    │────▶│   Staging   │────▶│ Production  │
│ Development │     │   & Test    │     │   Test      │     │ Deploy      │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
      │                   │                   │                   │
      ▼                   ▼                   ▼                   ▼
  New code            Test suite         Shadow mode          Live mode
  generated           passes             (no sending)         (full auto)
```

---

## 6. Avoiding Over-Engineering

### Keep It Simple Principles

| DO | DON'T |
|----|-------|
| Use Windows Task Scheduler | Build custom orchestration |
| Store state in JSON files | Implement database layer |
| Use Slack webhooks for alerts | Build monitoring stack |
| Git for version control | Custom deployment pipeline |
| Manual AE review | Full approval automation |

### When to Add Complexity

Add complexity ONLY when:
1. **Volume exceeds**: >1000 leads/day
2. **Team grows**: >3 AEs reviewing
3. **Failure rate hits**: >10% workflow failures
4. **Response time matters**: <1 min required

Until then: **Simple is better.**

---

## 7. Troubleshooting Matrix

| Issue | Use Auto-Claude | Use Claude-Flow | Manual |
|-------|-----------------|-----------------|--------|
| Script error | ✅ Fix code | ❌ | ❌ |
| Rate limited | ✅ Adjust logic | ❌ | ❌ |
| Workflow stuck | ❌ | ✅ Restart agent | ❌ |
| API key expired | ❌ | ❌ | ✅ Update .env |
| AE rejects all | ✅ Improve templates | ❌ | ✅ Review ICP |
| LinkedIn blocked | ✅ Adjust scraping | ❌ | ✅ New session |

---

## 8. Success Metrics

### Auto-Claude Effectiveness

```yaml
track_auto_claude:
  - specs_created_per_week
  - autonomous_builds_successful
  - time_to_fix_bugs
  - code_review_pass_rate
  - features_shipped_monthly
```

### Claude-Flow Effectiveness

```yaml
track_claude_flow:
  - workflow_completion_rate
  - agent_uptime_percent
  - leads_processed_daily
  - campaigns_generated_daily
  - error_rate_per_workflow
```

---

## 9. Recommended Setup

### For ChiefAIOfficer's Daily Operations

```yaml
recommended_setup:
  auto_claude:
    install: Download latest stable release
    usage: Weekly development sessions
    integration: Git-based merge to Alpha Swarm
    
  claude_flow:
    install: npm install -g claude-flow@alpha
    usage: Daily automated workflows
    integration: Windows Task Scheduler
    
  human_touchpoints:
    - AE review dashboard (GATEKEEPER)
    - Weekly strategy meeting
    - Monthly ICP review
    
  fully_automated:
    - Scraping (daily)
    - Enrichment (daily)
    - Segmentation (daily)
    - Campaign generation (daily)
    - Self-annealing (daily)
    - Reporting (daily)
```

---

## 10. Getting Started Checklist

### Week 1: Setup Both Tools

- [ ] Download Auto-Claude stable release
- [ ] Install Claude-Flow: `npm install -g claude-flow@alpha`
- [ ] Initialize Claude-Flow swarm: `npx claude-flow@alpha swarm init --topology mesh`
- [ ] Create first Auto-Claude spec from existing backlog
- [ ] Test end-to-end workflow manually

### Week 2: Establish Routines

- [ ] Set up Windows Task Scheduler (see deployment_framework.md)
- [ ] Configure Slack webhook for alerts
- [ ] Create first Auto-Claude improvement cycle
- [ ] Validate production workflow execution
- [ ] Document any gaps or issues

### Week 3+: Optimize

- [ ] Weekly Auto-Claude development sessions
- [ ] Daily Claude-Flow automated operations
- [ ] Continuous improvement from learnings.json
- [ ] Scale based on actual needs (not anticipated)

---

*Guide Version: 1.0*
*Created: 2026-01-14*
*Owner: Alpha Swarm Development Team*
