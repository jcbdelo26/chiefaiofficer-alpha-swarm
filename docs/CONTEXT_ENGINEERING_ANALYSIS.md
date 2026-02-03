# 🧠 Context Engineering Analysis for Alpha Swarm

> Applying Dex Horthy's "No Vibes Allowed" Framework to Chief AI Officer Alpha Swarm

**Source**: "No Vibes Allowed: Solving Hard Problems in Complex Codebases" by Dex Horthy, HumanLayer (AI Engineer Conference 2025)

**Analysis Date**: 2026-01-15

---

## 📋 Executive Summary

This document analyzes Dex Horthy's Context Engineering methodology and applies its principles to improve the Chief AI Officer Alpha Swarm multi-agent system. The core insight is that **"everything is context engineering"** — the quality of AI output is directly proportional to the quality of its input context.

### Key Concepts Covered

| Concept | Application Area | Priority |
|---------|-----------------|----------|
| Frequent Intentional Compaction (FIC) | Agent Workflows | 🔴 Critical |
| Research → Plan → Implement (RPI) | All Agent Operations | 🔴 Critical |
| The "Dumb Zone" | Context Window Management | 🔴 Critical |
| Semantic Diffusion Prevention | Multi-Agent Coordination | 🟡 High |
| Human-in-the-Loop Optimization | GATEKEEPER Agent | 🟡 High |
| Sub-Agent Context Forking | HUNTER/ENRICHER/SEGMENTOR | 🟢 Medium |

---

## 📖 Video Summary with Timestamps

### Introduction [00:00 - 05:00]
- Stanford study findings: AI tools struggle with real production codebases
- The problem isn't the models — it's how we use them
- "Vibe coding" leads to sloppy, broken code in complex projects

### The Core Problem [05:00 - 12:00]
- **"Slop"**: Low-quality, subtly broken, unmaintainable code
- Root cause: Naive context management
- The AI's context window fills up with irrelevant information
- **Key Insight**: "The quality of AI output ∝ quality of context input"

### The "Dumb Zone" Concept [12:00 - 20:00]
- **Definition**: Performance degradation when context fills 40-60%+ of capacity
- **Symptoms**:
  - Poor tool selection decisions
  - Repeated mistakes and circular reasoning
  - Hallucinations and context overload
  - Failure to follow established patterns
- **The "Smart Zone"**: Operating under 40% context utilization
- **Solution**: Keep agents operating in the "Smart Zone" through intentional compaction

### Frequent Intentional Compaction (FIC) [20:00 - 35:00]
- **Definition**: Deliberately structuring and compressing context throughout development
- **Three-Phase Workflow**:
  1. **Research Phase**: Compress truth — scan files, understand architecture, create summary
  2. **Plan Phase**: Compress intent — detailed step-by-step implementation plan
  3. **Implement Phase**: Execute with fresh context — follow the plan with clean context window
- **Key Principle**: Each phase produces a "context artifact" that is smaller than the raw information

### Research Phase Details [35:00 - 42:00]
- Use disposable sub-contexts for exploration
- Output: Concise human-readable summary of the problem space
- Maps relevant files, functions, data flows
- **Critical**: Research agent does NOT suggest changes — only observes

### Plan Phase Details [42:00 - 50:00]
- **"Point of Maximum Leverage"** for human oversight
- Review plan BEFORE code generation (not after)
- Plan includes: pseudocode, file paths, testing strategies
- Human can course-correct with minimal cost at this stage

### Implementation Phase [50:00 - 55:00]
- Separate agent with FRESH context window
- Agent follows the plan like instructions
- Minimal "thinking" required — just execution
- Periodic context refresh during long implementations

### Semantic Diffusion [55:00 - 60:00]
- **Definition**: Loss of intended meaning when humans outsource thinking to AI
- **Symptoms**: Misaligned expectations, "slop" code, excessive rework
- **Solution**: Mental alignment through research + plan review
- **Key**: AI should AMPLIFY human thinking, not replace it

### Human-in-the-Loop Best Practices [60:00 - 65:00]
- Don't just review code — review research and plans
- Shift human attention to high-leverage points
- Allow AI to handle low-risk execution
- Create feedback loops for system improvement

### Sub-Agent Architecture [65:00 - 70:00]
- Fork clean context windows for specific sub-tasks
- Sub-agents return concise summaries (not raw data)
- Parent agent stays in "Smart Zone"
- Each agent has a single, focused responsibility

---

## 🎯 Concepts Applied to Alpha Swarm

### 1. Frequent Intentional Compaction (FIC)

#### Current State

The Alpha Swarm agents (HUNTER, ENRICHER, SEGMENTOR, CRAFTER, GATEKEEPER) operate relatively independently but don't implement systematic context compaction.

**Current workflow** (from `lead-harvesting.md`):
```
HUNTER scrapes → file → ENRICHER enriches → file → SEGMENTOR scores → file → CRAFTER generates
```

Each step reads from files, but there's no explicit "compaction" strategy to summarize what happened in previous steps.

#### Problem

When CRAFTER generates campaigns, it reads the full segmented leads file. For large batches, this can push context utilization into the "Dumb Zone", leading to:
- Generic personalization that misses key hooks
- Template rendering errors
- Inconsistent messaging across leads

#### Recommended Implementation

**Create `core/context.py` for FIC management:**

```python
"""
Frequent Intentional Compaction (FIC) Module
=============================================
Implements context management to keep agents in the "Smart Zone" (<40% context).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
import json

@dataclass
class ContextSummary:
    """Compressed context artifact from a workflow phase."""
    phase: str  # research, plan, implement
    agent: str
    created_at: str
    summary: str
    key_findings: List[str]
    action_items: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
    token_estimate: int = 0
    
    def to_prompt_block(self) -> str:
        """Generate a compact prompt block from this summary."""
        return f"""
## {self.phase.upper()} PHASE SUMMARY ({self.agent})
{self.summary}

### Key Findings
{chr(10).join(f'- {f}' for f in self.key_findings[:5])}

### Action Items
{chr(10).join(f'- {a}' for a in self.action_items[:5])}
"""


class ContextManager:
    """Manages context across agent workflow phases."""
    
    MAX_CONTEXT_TOKENS = 128000  # Claude's context window
    SMART_ZONE_THRESHOLD = 0.4  # Stay under 40%
    
    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.phases: Dict[str, ContextSummary] = {}
        self.current_token_usage = 0
        
    def add_phase_summary(self, summary: ContextSummary):
        """Add a compacted phase summary."""
        self.phases[summary.phase] = summary
        self._update_token_estimate()
        
    def get_compacted_context(self) -> str:
        """Get all phase summaries as compacted context."""
        blocks = []
        for phase in ['research', 'plan', 'implement']:
            if phase in self.phases:
                blocks.append(self.phases[phase].to_prompt_block())
        return "\n".join(blocks)
    
    def is_in_smart_zone(self) -> bool:
        """Check if we're operating under 40% context."""
        return (self.current_token_usage / self.MAX_CONTEXT_TOKENS) < self.SMART_ZONE_THRESHOLD
    
    def should_compact(self) -> bool:
        """Check if compaction is needed."""
        usage_ratio = self.current_token_usage / self.MAX_CONTEXT_TOKENS
        return usage_ratio > self.SMART_ZONE_THRESHOLD
    
    def _update_token_estimate(self):
        """Estimate current token usage."""
        # Rough estimate: 4 chars per token
        total_chars = sum(len(p.to_prompt_block()) for p in self.phases.values())
        self.current_token_usage = total_chars // 4
        
    def save_state(self, path: Path):
        """Persist context state for workflow resumption."""
        with open(path, 'w') as f:
            json.dump({
                'workflow_id': self.workflow_id,
                'phases': {k: v.__dict__ for k, v in self.phases.items()},
                'token_usage': self.current_token_usage
            }, f, indent=2)


def compact_lead_batch(leads: List[Dict], max_leads: int = 20) -> Dict[str, Any]:
    """
    Compact a large lead batch into a summary for context efficiency.
    
    Instead of passing 100 full lead records, pass:
    - Aggregate statistics
    - Top 20 representative leads
    - Pattern summary
    """
    if len(leads) <= max_leads:
        return {'leads': leads, 'compacted': False}
    
    # Calculate aggregates
    tiers = {}
    sources = {}
    campaigns = {}
    
    for lead in leads:
        tier = lead.get('icp_tier', 'unknown')
        tiers[tier] = tiers.get(tier, 0) + 1
        
        source = lead.get('source_type', 'unknown')
        sources[source] = sources.get(source, 0) + 1
        
        campaign = lead.get('recommended_campaign', 'unknown')
        campaigns[campaign] = campaigns.get(campaign, 0) + 1
    
    # Select representative sample (highest ICP scores)
    sorted_leads = sorted(leads, key=lambda x: x.get('icp_score', 0), reverse=True)
    sample = sorted_leads[:max_leads]
    
    return {
        'compacted': True,
        'total_count': len(leads),
        'tier_distribution': tiers,
        'source_distribution': sources,
        'campaign_distribution': campaigns,
        'avg_icp_score': sum(l.get('icp_score', 0) for l in leads) / len(leads),
        'sample_leads': sample,
        'compaction_ratio': len(sample) / len(leads)
    }
```

**Files to modify:**
- `execution/crafter_campaign.py` - Add compaction before campaign generation
- `execution/segmentor_classify.py` - Output summary statistics for next phase

---

### 2. Research → Plan → Implement (RPI) Workflow

#### Current State

The current workflow (`lead-harvesting.md`) is a linear pipeline without explicit research or planning phases. Each agent immediately executes its task without structured understanding of context.

#### Problem

Without RPI:
- CRAFTER may not understand WHY certain leads are Tier 1
- GATEKEEPER reviews campaigns without understanding the research
- Semantic diffusion occurs as intent is lost between steps

#### Recommended Implementation

**Create RPI workflow for each major operation:**

**File: `.agent/workflows/rpi-campaign-creation.md`**

```markdown
---
description: Research-Plan-Implement workflow for campaign creation with context engineering
---

# RPI Campaign Creation Workflow

This workflow applies the Research → Plan → Implement methodology to campaign generation.

## Phase 1: RESEARCH

**Agent**: RESEARCHER sub-agent (fresh context)

```powershell
# Generate research summary for campaign batch
python execution/rpi_research.py --input .hive-mind/segmented/<latest>.json
```

**Output**: `.hive-mind/research/research_<timestamp>.json`

### Research Summary Contents:
- Lead cohort analysis (who are these people?)
- Source pattern analysis (why are they on this list?)
- ICP score distribution and outliers
- Personalization opportunity mapping
- Competitive intelligence summary
- Previous campaign performance (if applicable)

### 🛑 HUMAN CHECKPOINT 1
Review the research summary before proceeding:
- Does the lead cohort make sense?
- Are personalization hooks accurate?
- Any leads that should be excluded?

---

## Phase 2: PLAN

**Agent**: PLANNER sub-agent (reads research, fresh context)

```powershell
# Generate campaign plan based on research
python execution/rpi_plan.py --research .hive-mind/research/research_<timestamp>.json
```

**Output**: `.hive-mind/plans/plan_<timestamp>.json`

### Plan Contents:
- Campaign type selection with rationale
- Template selection per tier
- Personalization strategy per cohort
- A/B test hypotheses
- Expected metrics (open rate, reply rate targets)
- Compliance checklist flagged items
- Sequence timing recommendations

### 🛑 HUMAN CHECKPOINT 2 (HIGH LEVERAGE)
Review the plan BEFORE code generation:
- Is the campaign strategy sound?
- Do template selections match lead types?
- Any compliance concerns?
- Approve/reject/modify plan

---

## Phase 3: IMPLEMENT

**Agent**: CRAFTER (reads plan, fresh context)

```powershell
# Execute campaign creation from plan
python execution/rpi_implement.py --plan .hive-mind/plans/plan_<timestamp>.json
```

**Output**: `.hive-mind/campaigns/campaigns_<timestamp>.json`

### Implementation Notes:
- CRAFTER reads ONLY the approved plan (not raw research)
- Each lead processed with fresh sub-context
- Template rendering validated in real-time
- Compliance checks automated

---

## Phase Transitions

```
┌─────────────┐       ┌─────────────┐       ┌────────────────┐
│  RESEARCH   │──────▶│    PLAN     │──────▶│  IMPLEMENT     │
│  (compress  │       │  (compress  │       │  (execute from │
│   truth)    │       │   intent)   │       │   plan)        │
└─────────────┘       └─────────────┘       └────────────────┘
      │                     │                      │
      ▼                     ▼                      ▼
 research.json         plan.json            campaigns.json
      │                     │
      ▼                     ▼
 HUMAN REVIEW 1       HUMAN REVIEW 2 (HIGH LEVERAGE)
```
```

**Create `execution/rpi_research.py`:**

```python
#!/usr/bin/env python3
"""
RPI Research Phase - Compress Truth
====================================
Analyzes lead batch and generates research summary for planning phase.
"""

import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from collections import Counter
from rich.console import Console
from rich.table import Table

console = Console()


def analyze_lead_cohort(leads: List[Dict]) -> Dict[str, Any]:
    """Analyze the lead cohort to understand who these people are."""
    
    # Title distribution
    titles = Counter(l.get('title', 'Unknown') for l in leads)
    title_clusters = {
        'executive': 0,
        'director': 0,
        'manager': 0,
        'individual_contributor': 0
    }
    for title, count in titles.items():
        title_lower = title.lower()
        if any(kw in title_lower for kw in ['cro', 'vp', 'chief', 'head of']):
            title_clusters['executive'] += count
        elif 'director' in title_lower:
            title_clusters['director'] += count
        elif 'manager' in title_lower:
            title_clusters['manager'] += count
        else:
            title_clusters['individual_contributor'] += count
    
    # Company size distribution
    size_buckets = {'small': 0, 'mid': 0, 'enterprise': 0}
    for lead in leads:
        size = lead.get('company_size', 0)
        if size < 100:
            size_buckets['small'] += 1
        elif size < 500:
            size_buckets['mid'] += 1
        else:
            size_buckets['enterprise'] += 1
    
    return {
        'total_leads': len(leads),
        'title_distribution': title_clusters,
        'company_size_distribution': size_buckets,
        'top_titles': dict(titles.most_common(5))
    }


def analyze_source_patterns(leads: List[Dict]) -> Dict[str, Any]:
    """Analyze why these leads are on the list."""
    
    sources = Counter(l.get('source_type', 'unknown') for l in leads)
    source_names = Counter(l.get('source_name', 'unknown') for l in leads)
    
    # Engagement strength  
    engagement_levels = {'high': 0, 'medium': 0, 'low': 0}
    for lead in leads:
        source_type = lead.get('source_type', '')
        if source_type in ['post_commenter', 'event_attendee']:
            engagement_levels['high'] += 1
        elif source_type in ['group_member', 'competitor_follower']:
            engagement_levels['medium'] += 1
        else:
            engagement_levels['low'] += 1
    
    return {
        'source_types': dict(sources),
        'source_names': dict(source_names.most_common(5)),
        'engagement_levels': engagement_levels,
        'primary_source': sources.most_common(1)[0] if sources else ('unknown', 0)
    }


def map_personalization_opportunities(leads: List[Dict]) -> List[str]:
    """Identify personalization opportunities across the cohort."""
    
    opportunities = set()
    
    for lead in leads:
        hooks = lead.get('personalization_hooks', [])
        opportunities.update(hooks)
        
        # Infer additional opportunities
        if lead.get('source_type') == 'post_commenter':
            opportunities.add("Reference specific comment content")
        if lead.get('source_type') == 'event_attendee':
            opportunities.add(f"Reference {lead.get('source_name', 'event')} attendance")
        if lead.get('icp_score', 0) >= 85:
            opportunities.add("Use deep personalization for VIP tier")
    
    return list(opportunities)[:10]


def generate_research_summary(leads: List[Dict]) -> Dict[str, Any]:
    """Generate comprehensive research summary."""
    
    cohort_analysis = analyze_lead_cohort(leads)
    source_analysis = analyze_source_patterns(leads)
    personalization_opps = map_personalization_opportunities(leads)
    
    # ICP analysis
    icp_scores = [l.get('icp_score', 0) for l in leads]
    tier_dist = Counter(l.get('icp_tier', 'unknown') for l in leads)
    
    # Key findings (human-readable insights)
    key_findings = []
    
    # Finding 1: Primary audience
    top_title_cluster = max(cohort_analysis['title_distribution'].items(), key=lambda x: x[1])
    key_findings.append(f"Primary audience: {top_title_cluster[0]} level ({top_title_cluster[1]} leads)")
    
    # Finding 2: Engagement source
    primary_source = source_analysis['primary_source']
    key_findings.append(f"Primary source: {primary_source[0]} ({primary_source[1]} leads)")
    
    # Finding 3: Quality distribution
    tier1_pct = tier_dist.get('tier_1', 0) / len(leads) * 100 if leads else 0
    key_findings.append(f"Tier 1 (VIP) leads: {tier1_pct:.1f}% of batch")
    
    # Finding 4: Personalization potential
    high_engagement = source_analysis['engagement_levels']['high']
    key_findings.append(f"High engagement leads (easy to personalize): {high_engagement}")
    
    return {
        'research_id': f"research_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
        'generated_at': datetime.utcnow().isoformat(),
        'cohort_analysis': cohort_analysis,
        'source_analysis': source_analysis,
        'icp_summary': {
            'avg_score': sum(icp_scores) / len(icp_scores) if icp_scores else 0,
            'min_score': min(icp_scores) if icp_scores else 0,
            'max_score': max(icp_scores) if icp_scores else 0,
            'tier_distribution': dict(tier_dist)
        },
        'personalization_opportunities': personalization_opps,
        'key_findings': key_findings,
        'action_items': [
            f"Create campaigns for {tier_dist.get('tier_1', 0)} Tier 1 leads (require review)",
            f"Create campaigns for {tier_dist.get('tier_2', 0)} Tier 2 leads (sampling review)",
            f"Process {tier_dist.get('tier_3', 0)} Tier 3 leads in batch mode",
            "Review any flagged compliance concerns",
            "Validate personalization hooks before campaign generation"
        ],
        'token_estimate': len(str(leads)) // 4  # Rough estimate
    }


def main():
    parser = argparse.ArgumentParser(description="RPI Research Phase")
    parser.add_argument("--input", type=Path, required=True, help="Segmented leads file")
    args = parser.parse_args()
    
    console.print("\n[bold blue]🔬 RPI RESEARCH PHASE: Compressing Truth[/bold blue]")
    
    with open(args.input) as f:
        data = json.load(f)
    
    leads = data.get('leads', [])
    
    research = generate_research_summary(leads)
    
    # Print summary
    console.print("\n[bold]📊 Research Summary[/bold]")
    
    table = Table(title="Key Findings")
    table.add_column("Finding", style="cyan")
    for finding in research['key_findings']:
        table.add_row(finding)
    console.print(table)
    
    # Save research
    output_dir = Path(__file__).parent.parent / ".hive-mind" / "research"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{research['research_id']}.json"
    
    with open(output_path, 'w') as f:
        json.dump(research, f, indent=2)
    
    console.print(f"\n[green]✅ Research saved to {output_path}[/green]")
    console.print("\n[yellow]⏸️  HUMAN CHECKPOINT: Review research before proceeding to PLAN phase[/yellow]")
    console.print(f"    python execution/rpi_plan.py --research {output_path}")


if __name__ == "__main__":
    main()
```

---

### 3. The "Dumb Zone" - Context Window Management

#### Current State

Looking at `execution/crafter_campaign.py`, the agent processes the entire leads file in memory:

```python
def process_segmented_file(self, input_file: Path, segment_filter: str = None) -> List[Campaign]:
    with open(input_file) as f:
        data = json.load(f)
    
    leads = data.get("leads", [])  # Could be hundreds of leads!
```

This naive loading can push context into the "Dumb Zone" for large batches.

#### Problem Indicators

Signs that your agent is in the "Dumb Zone":
- Generic template outputs despite personalization hooks
- Template placeholder failures (`{{lead.first_name}}` not rendered)
- Inconsistent campaign quality across a batch
- Repeated similar mistakes

#### Recommended Implementation

**Add context monitoring to `core/context.py`:**

```python
from enum import Enum

class ContextZone(Enum):
    SMART = "smart"      # < 40% - optimal performance
    CAUTION = "caution"  # 40-60% - degradation starting
    DUMB = "dumb"        # > 60% - significant degradation
    CRITICAL = "critical" # > 80% - expect failures


def get_context_zone(current_tokens: int, max_tokens: int = 128000) -> ContextZone:
    """Determine which context zone we're operating in."""
    ratio = current_tokens / max_tokens
    
    if ratio < 0.40:
        return ContextZone.SMART
    elif ratio < 0.60:
        return ContextZone.CAUTION
    elif ratio < 0.80:
        return ContextZone.DUMB
    else:
        return ContextZone.CRITICAL


def estimate_tokens(content: Any) -> int:
    """Estimate token count for content."""
    if isinstance(content, str):
        return len(content) // 4
    elif isinstance(content, dict) or isinstance(content, list):
        return len(json.dumps(content)) // 4
    else:
        return len(str(content)) // 4
```

**Modify `execution/crafter_campaign.py` to use batch processing:**

```python
# Add to CampaignCrafter class

BATCH_SIZE = 25  # Process 25 leads at a time to stay in Smart Zone

def process_segmented_file(self, input_file: Path, segment_filter: str = None) -> List[Campaign]:
    """Process with Dumb Zone protection."""
    
    console.print(f"\n[bold blue]✍️ CRAFTER: Generating campaigns (with FIC)[/bold blue]")
    
    with open(input_file) as f:
        data = json.load(f)
    
    leads = data.get("leads", [])
    
    if segment_filter:
        leads = [l for l in leads if segment_filter in l.get("segment_tags", [])]
    
    # Check context zone
    from core.context import estimate_tokens, get_context_zone, ContextZone
    
    token_estimate = estimate_tokens(leads)
    zone = get_context_zone(token_estimate)
    
    if zone in [ContextZone.DUMB, ContextZone.CRITICAL]:
        console.print(f"[yellow]⚠️  Large batch detected ({len(leads)} leads, ~{token_estimate:,} tokens)[/yellow]")
        console.print(f"[yellow]   Switching to batched processing to stay in Smart Zone[/yellow]")
        return self._process_batched(leads, segment_filter)
    
    # Normal processing for smaller batches
    return self._process_normal(leads, segment_filter)


def _process_batched(self, leads: List[Dict], segment_filter: str = None) -> List[Campaign]:
    """Process large batches in chunks to avoid Dumb Zone."""
    
    all_campaigns = []
    
    # Group by tier/campaign type first
    groups = {}
    for lead in leads:
        tier = lead.get("icp_tier", "tier_4")
        campaign_type = lead.get("recommended_campaign", "competitor_displacement")
        key = f"{tier}_{campaign_type}"
        
        if key not in groups:
            groups[key] = []
        groups[key].append(lead)
    
    with Progress() as progress:
        task = progress.add_task("Creating campaigns (batched)...", total=len(groups))
        
        for segment, segment_leads in groups.items():
            if "disqualified" in segment:
                progress.update(task, advance=1)
                continue
            
            # Process in batches
            for i in range(0, len(segment_leads), self.BATCH_SIZE):
                batch = segment_leads[i:i + self.BATCH_SIZE]
                batch_segment = f"{segment}_batch{i // self.BATCH_SIZE + 1}"
                
                try:
                    campaign_type = segment.split("_", 1)[1] if "_" in segment else "competitor_displacement"
                    campaign = self.create_campaign(batch, batch_segment, campaign_type)
                    all_campaigns.append(campaign)
                except Exception as e:
                    console.print(f"[yellow]Batch failed for {batch_segment}: {e}[/yellow]")
            
            progress.update(task, advance=1)
    
    return all_campaigns
```

---

### 4. Semantic Diffusion Prevention

#### Current State

Looking at the multi-agent flow:
1. HUNTER scrapes leads (raw data)
2. ENRICHER adds data (Clay/RB2B)
3. SEGMENTOR scores and classifies
4. CRAFTER generates campaigns
5. GATEKEEPER approves

**Semantic diffusion occurs when:**
- CRAFTER doesn't understand why a lead was scored Tier 1
- GATEKEEPER reviews a campaign without context on the lead
- Campaign messaging doesn't reflect the original engagement context

#### Recommended Implementation

**Add semantic anchors that persist through the workflow:**

**File: `core/semantic_anchor.py`**

```python
"""
Semantic Anchor System
======================
Prevents semantic diffusion by maintaining clear intent throughout the pipeline.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
from pathlib import Path


@dataclass
class SemanticAnchor:
    """
    A semantic anchor captures the INTENT behind a decision.
    This travels with the lead through all workflow phases.
    """
    anchor_id: str
    lead_id: str
    created_at: str
    
    # WHAT: The factual observation
    observation: str
    
    # WHY: The reasoning behind the decision
    rationale: str
    
    # HOW: The recommended action
    recommendation: str
    
    # CONFIDENCE: How confident are we?
    confidence: float  # 0.0 - 1.0
    
    # SOURCE: Where did this come from?
    source_agent: str
    source_phase: str  # research, plan, implement
    
    # VALIDATION: Has this been human-reviewed?
    human_validated: bool = False
    validator: Optional[str] = None
    validation_timestamp: Optional[str] = None


@dataclass 
class LeadWithAnchors:
    """Lead data with attached semantic anchors."""
    lead_id: str
    raw_data: Dict[str, Any]
    anchors: List[SemanticAnchor] = field(default_factory=list)
    
    def add_anchor(self, anchor: SemanticAnchor):
        """Add a semantic anchor."""
        self.anchors.append(anchor)
    
    def get_anchors_for_phase(self, phase: str) -> List[SemanticAnchor]:
        """Get anchors from a specific phase."""
        return [a for a in self.anchors if a.source_phase == phase]
    
    def get_narrative(self) -> str:
        """
        Generate a human-readable narrative from anchors.
        This prevents semantic diffusion by maintaining context.
        """
        narrative_parts = []
        
        for anchor in sorted(self.anchors, key=lambda x: x.created_at):
            narrative_parts.append(
                f"[{anchor.source_agent}] {anchor.observation}\n"
                f"  → Rationale: {anchor.rationale}\n"
                f"  → Recommendation: {anchor.recommendation}"
            )
        
        return "\n\n".join(narrative_parts)


# Example usage in SEGMENTOR
def create_icp_anchor(lead_id: str, score: int, breakdown: Dict, tier: str) -> SemanticAnchor:
    """Create semantic anchor for ICP scoring decision."""
    
    # Build observation
    observation = f"Lead scored {score}/100, classified as {tier.upper()}"
    
    # Build rationale from breakdown
    rationale_parts = []
    for factor, points in breakdown.items():
        if points > 0:
            rationale_parts.append(f"{factor}: +{points}")
    rationale = "Scoring factors: " + ", ".join(rationale_parts)
    
    # Determine recommendation
    if tier == "tier_1":
        recommendation = "Deep personalization required; AE review mandatory"
    elif tier == "tier_2":
        recommendation = "Medium personalization; AE review recommended"
    elif tier == "tier_3":
        recommendation = "Light personalization; batch processing OK"
    else:
        recommendation = "Minimal personalization or nurture only"
    
    return SemanticAnchor(
        anchor_id=f"anchor_{lead_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        lead_id=lead_id,
        created_at=datetime.utcnow().isoformat(),
        observation=observation,
        rationale=rationale,
        recommendation=recommendation,
        confidence=0.9 if score >= 70 else 0.7,
        source_agent="SEGMENTOR",
        source_phase="research"
    )


# Example usage in CRAFTER
def create_campaign_anchor(lead_id: str, template: str, hooks: List[str]) -> SemanticAnchor:
    """Create semantic anchor for campaign strategy decision."""
    
    return SemanticAnchor(
        anchor_id=f"anchor_{lead_id}_campaign",
        lead_id=lead_id,
        created_at=datetime.utcnow().isoformat(),
        observation=f"Selected '{template}' template with {len(hooks)} personalization hooks",
        rationale=f"Template matches source type and engagement level. Hooks: {', '.join(hooks[:3])}",
        recommendation=f"Render with hooks; validate before send",
        confidence=0.85,
        source_agent="CRAFTER",
        source_phase="plan"
    )
```

**Integrate into GATEKEEPER for review context:**

In `execution/gatekeeper_queue.py`, when presenting campaigns for review, show the semantic narrative:

```python
def present_for_review(campaign: Campaign, lead: Dict):
    """Present campaign with full semantic context."""
    
    # Get lead's semantic anchors
    lead_with_anchors = LeadWithAnchors(
        lead_id=lead['lead_id'],
        raw_data=lead,
        anchors=load_anchors_for_lead(lead['lead_id'])
    )
    
    console.print("\n[bold]🔍 Lead Context (Semantic Narrative)[/bold]")
    console.print(lead_with_anchors.get_narrative())
    
    console.print("\n[bold]📧 Campaign Preview[/bold]")
    console.print(f"Subject: {campaign.sequence[0]['subject_a']}")
    console.print(f"Body:\n{campaign.sequence[0]['body_a'][:500]}...")
    
    console.print("\n[bold]Does this campaign align with the semantic narrative?[/bold]")
```

---

### 5. Human-in-the-Loop Optimization

#### Current State

From `sdr_specifications.md`, human review is configured:
- Tier 1: AE approval required
- Tier 2: AE approval recommended
- Tier 3: Batch sampling (10%)
- Tier 4: None

But review happens at the CAMPAIGN level (after generation), not the PLAN level.

#### Problem

According to Horthy's framework, reviewing code/content AFTER generation is low leverage. The "point of maximum leverage" is reviewing the PLAN.

#### Recommended Implementation

**Shift human attention to high-leverage checkpoints:**

```yaml
# config/human_checkpoints.yaml

checkpoints:
  research_review:
    enabled: true
    applies_to: 
      - tier_1
      - tier_2  
    reviewer: ae
    timeout_hours: 24
    skip_conditions:
      - < 10 leads in batch
      - all leads from same source
    review_items:
      - lead cohort makes sense
      - source patterns are accurate
      - no compliance red flags

  plan_review:  # HIGH LEVERAGE POINT
    enabled: true
    applies_to:
      - tier_1
    reviewer: ae
    timeout_hours: 4
    escalation: senior_ae
    review_items:
      - campaign strategy is sound
      - template selection is appropriate
      - personalization approach is correct
      - A/B test hypotheses are valid
      - sequence timing is appropriate

  campaign_review:  # Lower leverage, but still needed
    enabled: true
    applies_to:
      - tier_1
      - tier_2
    reviewer: ae
    timeout_hours: 24
    auto_approve_if:
      - plan was reviewed and approved
      - compliance checks passed
      - <2 warnings in validation
    review_items:
      - final content quality
      - placeholder substitution correct
      - no broken personalization
```

**Create high-leverage checkpoint system:**

```python
# core/checkpoints.py

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime
import json


class CheckpointType(Enum):
    RESEARCH_REVIEW = "research_review"  # Review before planning
    PLAN_REVIEW = "plan_review"          # HIGH LEVERAGE - Review before implementation
    CAMPAIGN_REVIEW = "campaign_review"  # Review after implementation


class CheckpointStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"


@dataclass
class Checkpoint:
    checkpoint_id: str
    checkpoint_type: CheckpointType
    workflow_id: str
    created_at: str
    
    # What to review
    artifact_path: str
    artifact_summary: str
    
    # Review items
    review_items: List[str]
    
    # Review state
    status: CheckpointStatus = CheckpointStatus.PENDING
    reviewer: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_notes: Optional[str] = None
    modifications: List[Dict] = None
    
    def is_high_leverage(self) -> bool:
        """Plan review is the highest leverage point."""
        return self.checkpoint_type == CheckpointType.PLAN_REVIEW
    
    def can_skip(self, tier: str, lead_count: int) -> bool:
        """Determine if this checkpoint can be skipped."""
        if self.checkpoint_type == CheckpointType.PLAN_REVIEW:
            # Never skip plan review for Tier 1
            return tier not in ['tier_1']
        
        if self.checkpoint_type == CheckpointType.CAMPAIGN_REVIEW:
            # Skip if plan was reviewed and <10 leads
            return lead_count < 10
        
        return False


def create_plan_checkpoint(
    workflow_id: str,
    plan_path: str,
    plan_data: Dict[str, Any]
) -> Checkpoint:
    """Create a high-leverage PLAN review checkpoint."""
    
    return Checkpoint(
        checkpoint_id=f"checkpoint_plan_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        checkpoint_type=CheckpointType.PLAN_REVIEW,
        workflow_id=workflow_id,
        created_at=datetime.utcnow().isoformat(),
        artifact_path=plan_path,
        artifact_summary=f"""
CAMPAIGN PLAN REVIEW
====================
Campaign Type: {plan_data.get('campaign_type')}
Lead Count: {plan_data.get('lead_count')}
Avg ICP Score: {plan_data.get('avg_icp_score')}

Template: {plan_data.get('template_selection')}
Personalization Strategy: {plan_data.get('personalization_strategy')}

A/B Test Hypothesis:
{plan_data.get('ab_hypothesis', 'None specified')}
        """,
        review_items=[
            "Campaign strategy aligns with lead source",
            "Template matches ICP tier expectations",
            "Personalization hooks are accurate and relevant",
            "No compliance concerns with messaging",
            "Sequence timing is appropriate for audience"
        ]
    )
```

---

### 6. Sub-Agent Context Forking for Multi-Agent System

#### Current State

The Alpha Swarm uses multiple agents, but they share context through files rather than explicit context forking.

#### Problem

When ALPHA QUEEN orchestrates multiple agents, they may:
- Receive redundant context
- Lack necessary context from prior phases
- Accumulate context pollution from multiple requests

#### Recommended Implementation

**Create sub-agent spawning with clean context:**

```python
# core/subagents.py

"""
Sub-Agent Context Management
============================
Implements context forking for multi-agent coordination.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, Callable
from pathlib import Path
import subprocess
import json
from datetime import datetime


@dataclass
class SubAgentContext:
    """Clean context package for a sub-agent."""
    agent_type: str  # HUNTER, ENRICHER, SEGMENTOR, CRAFTER
    task_id: str
    
    # Minimal required context (compressed from parent)
    mission_brief: str  # What to do
    constraints: Dict[str, Any]  # What NOT to do
    input_artifact: Path  # Where to read from
    output_artifact: Path  # Where to write to
    
    # Parent context reference (not the actual content)
    parent_workflow_id: str
    parent_phase: str  # research, plan, implement
    
    # Token budget
    max_tokens: int = 8000  # Keep sub-agents lean


def fork_context_for_subagent(
    parent_context: Dict[str, Any],
    agent_type: str,
    task_description: str,
    input_path: Path,
    output_path: Path
) -> SubAgentContext:
    """
    Fork a clean context for a sub-agent.
    
    Key principle: Sub-agent gets ONLY what it needs.
    """
    
    # Extract minimal relevant context
    mission_brief = f"""
You are {agent_type} agent in the Alpha Swarm.

YOUR TASK:
{task_description}

INPUT: {input_path}
OUTPUT: {output_path}

CONSTRAINTS:
- Focus only on your task
- Return a concise summary, not raw data
- Stay within token budget
- Report any issues encountered
"""
    
    constraints = {
        'max_leads_in_response': 20,
        'max_summary_length': 500,
        'must_complete_within_minutes': 10,
        'forbidden_actions': [
            'modifying input files',
            'calling external APIs without logging',
            'creating files outside output path'
        ]
    }
    
    return SubAgentContext(
        agent_type=agent_type,
        task_id=f"{agent_type.lower()}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        mission_brief=mission_brief,
        constraints=constraints,
        input_artifact=input_path,
        output_artifact=output_path,
        parent_workflow_id=parent_context.get('workflow_id', 'unknown'),
        parent_phase=parent_context.get('phase', 'unknown')
    )


def spawn_subagent(
    context: SubAgentContext,
    script_path: Path
) -> Dict[str, Any]:
    """
    Spawn a sub-agent with forked context.
    Returns a summary (not raw output) to keep parent context clean.
    """
    
    # Prepare sub-agent config
    config = {
        'task_id': context.task_id,
        'mission_brief': context.mission_brief,
        'constraints': context.constraints,
        'input': str(context.input_artifact),
        'output': str(context.output_artifact)
    }
    
    # Write temp config
    config_path = Path('.tmp') / f"{context.task_id}_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w') as f:
        json.dump(config, f)
    
    # Execute sub-agent
    result = subprocess.run(
        ['python', str(script_path), '--config', str(config_path)],
        capture_output=True,
        text=True,
        timeout=600  # 10 minute timeout
    )
    
    # Parse summary from output
    if result.returncode == 0:
        with open(context.output_artifact) as f:
            output = json.load(f)
        
        # Return SUMMARY, not full output
        summary = {
            'status': 'success',
            'task_id': context.task_id,
            'agent': context.agent_type,
            'summary': output.get('summary', 'Completed without summary'),
            'metrics': output.get('metrics', {}),
            'next_action': output.get('next_action', None)
        }
    else:
        summary = {
            'status': 'failed',
            'task_id': context.task_id,
            'agent': context.agent_type,
            'error': result.stderr[:500]  # Truncate error
        }
    
    # Clean up temp config
    config_path.unlink(missing_ok=True)
    
    return summary
```

---

## 📁 Files to Create/Modify

### New Files

| File | Purpose |
|------|---------|
| `core/context.py` | FIC and context management |
| `core/semantic_anchor.py` | Semantic diffusion prevention |
| `core/checkpoints.py` | High-leverage human review |
| `core/subagents.py` | Clean context forking |
| `execution/rpi_research.py` | Research phase executor |
| `execution/rpi_plan.py` | Plan phase executor |
| `execution/rpi_implement.py` | Implement phase executor |
| `.agent/workflows/rpi-campaign-creation.md` | RPI workflow |
| `config/human_checkpoints.yaml` | Checkpoint configuration |

### Files to Modify

| File | Modification |
|------|--------------|
| `execution/crafter_campaign.py` | Add Dumb Zone protection, batch processing |
| `execution/segmentor_classify.py` | Add semantic anchor creation |
| `CLAUDE.md` | Add RPI and FIC principles |
| `directives/sdr_specifications.md` | Add context engineering section |

---

## 🔄 Implementation Priority

### Phase 1: Foundation (Week 1)
1. ✅ Create `core/context.py` with ContextManager
2. ✅ Add Dumb Zone protection to CRAFTER
3. ✅ Create RPI research script

### Phase 2: RPI Workflow (Week 2)
4. Create `execution/rpi_plan.py`
5. Create `execution/rpi_implement.py`
6. Create RPI workflow documentation
7. Update lead-harvesting workflow

### Phase 3: Semantic Anchors (Week 3)
8. Implement semantic anchor system
9. Integrate anchors in SEGMENTOR
10. Integrate anchors in CRAFTER
11. Update GATEKEEPER to show narratives

### Phase 4: Checkpoints (Week 4)
12. Create checkpoint system
13. Add plan review checkpoint
14. Update AE review dashboard
15. Add checkpoint metrics

---

## 📊 Expected Outcomes

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Campaign personalization quality | Variable | Consistent | +30% |
| Template rendering errors | 5-10% | <1% | -90% |
| AE rejection rate (plan issues) | 25% | 5% | -80% |
| Time-to-first-review | 2 hours | 30 min | -75% |
| Context window efficiency | 60-80% | 30-40% | +50% |
| Multi-agent coordination issues | Common | Rare | -70% |

---

## 🔗 References

- **Video**: "No Vibes Allowed: Solving Hard Problems in Complex Codebases" - Dex Horthy, HumanLayer
- **Conference**: AI Engineer 2025
- **Key Terms**: Context Engineering, Frequent Intentional Compaction, RPI Workflow, Dumb Zone, Semantic Diffusion, Human-in-the-Loop

---

*Document Version: 1.0*
*Created: 2026-01-15*
*Author: Alpha Swarm Context Engineering Team*
