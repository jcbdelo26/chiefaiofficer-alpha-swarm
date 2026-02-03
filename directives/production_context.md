# 📚 Production Context - What Agents Need to Know

> This document defines the operational context required for Alpha Swarm agents to mesh with Chiefaiofficer.com's daily revenue operations.

---

## Overview

For autonomous agents to operate effectively in production, they must have:
1. **Domain Knowledge** - Understanding of our business
2. **Operational History** - What worked/didn't work before
3. **Voice & Brand** - How we communicate
4. **Competitor Intelligence** - Market positioning
5. **Workflow Integration** - How we work daily

---

## 1. Required Knowledge Sources

### 1.1 Sales Playbook Integration

**Source**: Existing sales materials, call recordings, winning sequences

```yaml
knowledge_sources:
  email_sequences:
    location: Google Drive / Instantly
    format: Export successful sequences
    refresh: Monthly
    
  objection_library:
    location: Sales team knowledge base
    format: Objection → Response pairs
    refresh: As new objections appear
    
  meeting_scripts:
    location: Demo recordings
    format: Transcripts of successful demos
    refresh: Quarterly
    
  win_loss_analysis:
    location: CRM notes
    format: Deal close reasons
    refresh: Weekly
```

### 1.2 Voice & Brand Guidelines

**Purpose**: Ensure all generated content sounds like Chris/team

```yaml
voice_profile:
  tone: Professional, consultative, direct
  reading_level: Executive (8th grade readability)
  
  preferred_phrases:
    - "Revenue operations transformation"
    - "AI-powered intelligence"
    - "Autonomous workflows"
    
  prohibited_phrases:
    - "Growth hacking"
    - "Synergy"
    - "Circle back"
    - False urgency ("Today only!")
    
  writing_samples: 
    location: .hive-mind/knowledge/voice_samples/
    examples:
      - Successful cold emails (10+)
      - LinkedIn posts (top performers)
      - Website copy
```

### 1.3 Competitor Intelligence

**Purpose**: Enable competitive displacement messaging

```yaml
competitors:
  primary:
    - name: Gong
      positioning: "Conversation intelligence"
      our_angle: "Beyond conversation - full revenue orchestration"
      pain_points: "Expensive, limited to calls"
      
    - name: Clari
      positioning: "Revenue platform"
      our_angle: "More autonomous, AI-native"
      pain_points: "Complex implementation"
      
    - name: Chorus
      positioning: "CI for sales teams"
      our_angle: "We do what they do + more"
      pain_points: "Now part of ZoomInfo (lock-in)"

  displacement_playbook:
    location: directives/competitor_displacement.md
    templates:
      - From Gong → ChiefAIO
      - From Clari → ChiefAIO
      - From Chorus → ChiefAIO
```

### 1.4 Historical Performance Data

**Purpose**: Train RL Engine and baseline expectations

```yaml
historical_data:
  campaigns:
    location: Instantly exports + GHL reports
    metrics_to_import:
      - Open rates by segment
      - Reply rates by template
      - Meeting rates by source
      - Rejection reasons
      
  leads:
    location: GHL export
    metrics_to_import:
      - ICP validation (did we call them correctly?)
      - Deal outcomes by segment
      - Time-to-close by source
      
  enrichment:
    location: Clay logs
    metrics_to_import:
      - Success rates by data point
      - Provider reliability
      - Data freshness at use
```

---

## 2. Operational Workflow Integration

### 2.1 Daily Operations Calendar

```yaml
weekday_schedule:
  05:00-07:00 (PST):
    - LinkedIn scraping (low-traffic window)
    - Rate: 50 profiles/hour max
    
  07:00-08:00:
    - Enrichment processing (overnight scrapes)
    - Segmentation and scoring
    
  08:00-10:00:
    - Campaign generation
    - GATEKEEPER queue prep
    
  10:00-12:00:
    - AE review window (primary)
    - Prioritize Tier 1 & Tier 2
    
  12:00-14:00:
    - Approved campaigns pushed to Instantly
    - Sending begins
    
  14:00-16:00:
    - Reply monitoring
    - Escalation routing
    
  16:00-17:00:
    - Daily metrics sync
    - Self-annealing from morning outcomes
    
weekend_schedule:
  - No scraping (LinkedIn flags)
  - Read-only mode
  - Analytics catch-up only
```

### 2.2 Team Integration Points

```yaml
team_touchpoints:
  ae_team:
    interaction: GATEKEEPER review dashboard
    frequency: 2x daily (morning + afternoon)
    escalation: Slack #alpha-swarm-alerts
    
  revops_team:
    interaction: Weekly performance review
    frequency: Friday 4pm
    reports: Segment analysis, ICP validation
    
  founder_chris:
    interaction: Strategic oversight
    frequency: Weekly summary
    reports: ROI tracking, system health
```

---

## 3. Knowledge Ingestion Workflow

### Step 1: Export Existing Data

```powershell
# Run these to bootstrap the knowledge base

# Export successful email templates from Instantly
python execution/ingest_instantly_templates.py \
  --filter "open_rate > 50%" \
  --output .hive-mind/knowledge/templates/

# Export winning deals from GHL
python execution/ingest_ghl_deals.py \
  --status "Won" \
  --output .hive-mind/knowledge/deals/

# Export historical enrichment data
python execution/ingest_clay_history.py \
  --days 90 \
  --output .hive-mind/knowledge/enrichment/
```

### Step 2: Voice Training

```yaml
voice_training:
  input_sources:
    - Chris's LinkedIn posts (last 50)
    - Successful outbound emails (last 100)
    - Website copy
    - Proposal templates
    
  output:
    - .hive-mind/knowledge/voice_profile.json
    - Fine-tuned prompts in directives/voice_guide.md
```

### Step 3: Competitor Analysis

```yaml
competitor_analysis:
  process:
    1. Scrape competitor LinkedIn followers (HUNTER)
    2. Analyze common pain points
    3. Document displacement angles
    4. Create template library
    
  output:
    - directives/competitor_intel.md
    - .hive-mind/knowledge/competitor_data/
```

---

## 4. Self-Annealing Knowledge Updates

### Automatic Learning

```yaml
learning_triggers:
  campaign_outcome:
    - Update RL Q-table on every open/reply/meeting
    - Store in .hive-mind/q_table.json
    
  ae_rejection:
    - Capture rejection reason
    - Categorize issue type
    - Update learnings.json
    - Trigger directive review if pattern emerges
    
  icp_mismatch:
    - When AE overrides tier
    - Adjust scoring weights
    - Document in reasoning_bank.json
```

### Weekly Knowledge Refresh

```yaml
weekly_refresh:
  monday:
    - Pull Instantly campaign analytics
    - Update performance baselines
    
  tuesday:
    - Review rejection patterns
    - Generate improvement suggestions
    
  friday:
    - Weekly summary report
    - Update directives if needed
    - Archive learnings
```

---

## 5. Production Readiness Checklist

### Required Before Go-Live

- [ ] **Voice samples loaded** (10+ successful emails)
- [ ] **Historical data imported** (90 days minimum)
- [ ] **Competitor intel documented** (3+ primary competitors)
- [ ] **Scoring weights validated** (AE spot-check 50 leads)
- [ ] **Template library created** (5+ categories)
- [ ] **Daily schedule configured** (in scheduler)
- [ ] **Slack/Email alerts set up** (for escalations)
- [ ] **AE dashboard accessible** (GATEKEEPER UI)
- [ ] **Backup/recovery tested** (data resilience)
- [ ] **Rate limits configured** (per platform)

### Validation Gates

| Gate | Criteria | Owner |
|------|----------|-------|
| ICP Accuracy | ≥85% AE agreement | RevOps |
| Voice Match | Chris signs off on samples | Founder |
| Competitor Data | Reviewed by sales team | AE Team |
| Performance Baseline | Historical data loaded | System |
| Workflow Fit | Schedule fits team rhythm | All |

---

*Document Version: 1.0*
*Created: 2026-01-14*
*Owner: Alpha Swarm Production Team*
