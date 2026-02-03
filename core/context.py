"""
Context Engineering Core Module
================================
Implements HumanLayer's 12-Factor Agents patterns for context management.

Key Features:
- Event-Based Threading with typed events
- Custom XML-style serialization for token efficiency
- Context Window Management with smart compaction
- Pre-fetch pattern for deterministic data loading

Based on Dex Horthy's Context Engineering methodology from "No Vibes Allowed".
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Union, Callable
from pathlib import Path
from enum import Enum
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor


class ContextZone(Enum):
    """Context utilization zones and their expected behavior."""
    SMART = "smart"       # < 40% - optimal performance
    CAUTION = "caution"   # 40-60% - degradation starting
    DUMB = "dumb"         # > 60% - significant degradation
    CRITICAL = "critical" # > 80% - expect failures


class EventType(Enum):
    """Typed event types for event-based threading."""
    RESEARCH_COMPLETE = "research_complete"
    PLAN_CREATED = "plan_created"
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETE = "phase_complete"
    ERROR = "error"
    HUMAN_APPROVAL = "human_approval"
    COMPACTION = "compaction"
    PREFETCH_COMPLETE = "prefetch_complete"
    AGENT_SPAWNED = "agent_spawned"
    AGENT_COMPLETED = "agent_completed"


ZONE_THRESHOLDS = {
    ContextZone.SMART: 0.40,
    ContextZone.CAUTION: 0.60,
    ContextZone.DUMB: 0.80,
    ContextZone.CRITICAL: 1.0
}

MODEL_CONTEXT_WINDOWS = {
    'claude-3-sonnet': 200000,
    'claude-3-opus': 200000,
    'claude-3-haiku': 200000,
    'claude-sonnet-4': 200000,
    'gpt-4-turbo': 128000,
    'gpt-4': 8192,
    'gemini-pro': 128000,
    'gemini-2.0-flash': 1000000,
    'default': 128000
}


@dataclass
class Event:
    """A typed event in the event thread."""
    event_type: EventType
    timestamp: str
    data: Dict[str, Any]
    resolved: bool = False
    phase: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_type': self.event_type.value,
            'timestamp': self.timestamp,
            'data': self.data,
            'resolved': self.resolved,
            'phase': self.phase
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Event':
        return cls(
            event_type=EventType(d['event_type']),
            timestamp=d['timestamp'],
            data=d['data'],
            resolved=d.get('resolved', False),
            phase=d.get('phase')
        )


class EventThread:
    """
    Event-based threading for agent workflows.
    
    Implements HumanLayer's pattern of maintaining a typed events array
    that can be compacted and serialized efficiently.
    """
    
    def __init__(self, thread_id: str, max_events: int = 100):
        self.thread_id = thread_id
        self.events: List[Event] = []
        self.max_events = max_events
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.metadata: Dict[str, Any] = {}
    
    def add_event(self, event_type: EventType, data: Dict[str, Any], phase: Optional[str] = None) -> Event:
        """Add a typed event to the thread."""
        event = Event(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            data=data,
            phase=phase
        )
        self.events.append(event)
        
        if len(self.events) > self.max_events:
            self.compact()
        
        return event
    
    def get_recent_events(self, n: int = 10) -> List[Event]:
        """Returns last N events."""
        return self.events[-n:]
    
    def get_events_by_type(self, event_type: EventType) -> List[Event]:
        """Get all events of a specific type."""
        return [e for e in self.events if e.event_type == event_type]
    
    def get_unresolved_errors(self) -> List[Event]:
        """Get all unresolved error events."""
        return [e for e in self.events 
                if e.event_type == EventType.ERROR and not e.resolved]
    
    def resolve_event(self, index: int):
        """Mark an event as resolved."""
        if 0 <= index < len(self.events):
            self.events[index].resolved = True
    
    def compact(self) -> int:
        """
        Remove resolved errors and completed phases.
        Returns number of events removed.
        """
        original_count = len(self.events)
        
        self.events = [
            e for e in self.events
            if not (e.event_type == EventType.ERROR and e.resolved)
            and not (e.event_type == EventType.PHASE_COMPLETE and e.resolved)
        ]
        
        removed = original_count - len(self.events)
        
        if removed > 0:
            self.add_event(EventType.COMPACTION, {
                'events_removed': removed,
                'events_remaining': len(self.events)
            })
        
        return removed
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'thread_id': self.thread_id,
            'created_at': self.created_at,
            'events': [e.to_dict() for e in self.events],
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'EventThread':
        thread = cls(d['thread_id'])
        thread.created_at = d.get('created_at', thread.created_at)
        thread.events = [Event.from_dict(e) for e in d.get('events', [])]
        thread.metadata = d.get('metadata', {})
        return thread


def serialize_event(event: Event) -> str:
    """
    Serialize event to compact XML string.
    Token-efficient format matching HumanLayer patterns.
    """
    data_str = ' '.join(f'{k}="{v}"' for k, v in event.data.items() 
                        if isinstance(v, (str, int, float, bool)))
    
    phase_attr = f' phase="{event.phase}"' if event.phase else ''
    resolved_attr = ' resolved="true"' if event.resolved else ''
    
    return f'<event type="{event.event_type.value}" ts="{event.timestamp[:19]}"{phase_attr}{resolved_attr} {data_str}/>'


def serialize_thread(thread: EventThread) -> str:
    """
    Serialize full thread to context string for LLM.
    Uses compact XML format for token efficiency.
    """
    lines = [f'<thread id="{thread.thread_id}" created="{thread.created_at[:19]}">']
    
    for event in thread.events:
        lines.append(f'  {serialize_event(event)}')
    
    lines.append('</thread>')
    return '\n'.join(lines)


def serialize_thread_summary(thread: EventThread) -> str:
    """
    Create an ultra-compact summary of thread state.
    Used when context budget is tight.
    """
    error_count = len([e for e in thread.events if e.event_type == EventType.ERROR and not e.resolved])
    completed_phases = [e.phase for e in thread.events if e.event_type == EventType.PHASE_COMPLETE]
    
    return f'<thread-summary id="{thread.thread_id}" events="{len(thread.events)}" errors="{error_count}" phases="{",".join(completed_phases) if completed_phases else "none"}"/>'


def estimate_tokens(content: Union[str, Dict, List, Any]) -> int:
    """
    Estimate token count for content.
    Uses ~4 characters per token heuristic.
    """
    if isinstance(content, str):
        return len(content) // 4
    elif isinstance(content, dict) or isinstance(content, list):
        return len(json.dumps(content, default=str)) // 4
    else:
        return len(str(content)) // 4


def check_context_budget(current_tokens: int, max_tokens: int = 128000, max_budget: float = 0.6) -> bool:
    """
    Check if current token usage is under budget.
    
    Args:
        current_tokens: Current estimated token count
        max_tokens: Maximum context window size
        max_budget: Maximum utilization ratio (default 0.6 = 60%)
        
    Returns:
        True if under budget, False if over
    """
    return (current_tokens / max_tokens) < max_budget


def get_context_zone(current_tokens: int, max_tokens: int = 128000) -> ContextZone:
    """Determine which context zone we're operating in."""
    ratio = current_tokens / max_tokens
    
    if ratio < ZONE_THRESHOLDS[ContextZone.SMART]:
        return ContextZone.SMART
    elif ratio < ZONE_THRESHOLDS[ContextZone.CAUTION]:
        return ContextZone.CAUTION
    elif ratio < ZONE_THRESHOLDS[ContextZone.DUMB]:
        return ContextZone.DUMB
    else:
        return ContextZone.CRITICAL


def trigger_compaction(thread: EventThread, max_tokens: int = 128000) -> bool:
    """
    Auto-compact when over budget.
    
    Returns True if compaction was triggered.
    """
    current_tokens = estimate_tokens(serialize_thread(thread))
    
    if not check_context_budget(current_tokens, max_tokens):
        thread.compact()
        return True
    
    return False


@dataclass
class PrefetchedContext:
    """Container for prefetched data."""
    context_type: str  # lead, campaign, enrichment
    context_id: str
    data: Dict[str, Any]
    fetched_at: str
    token_estimate: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'context_type': self.context_type,
            'context_id': self.context_id,
            'data': self.data,
            'fetched_at': self.fetched_at,
            'token_estimate': self.token_estimate
        }


def prefetch_lead_context(lead_id: str, data_dir: Optional[Path] = None) -> PrefetchedContext:
    """
    Deterministically fetch lead data before decision.
    
    Pre-fetch pattern: Load all necessary data upfront to avoid
    mid-decision data fetching that can corrupt context.
    """
    if data_dir is None:
        data_dir = Path('.hive-mind')
    
    lead_data = {}
    
    enriched_dir = data_dir / 'enriched'
    if enriched_dir.exists():
        for f in sorted(enriched_dir.glob('*.json'), reverse=True):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    leads = data.get('leads', [])
                    for lead in leads:
                        if lead.get('id') == lead_id or lead.get('linkedin_url', '').endswith(lead_id):
                            lead_data = lead
                            break
                if lead_data:
                    break
            except (json.JSONDecodeError, IOError):
                continue
    
    context = PrefetchedContext(
        context_type='lead',
        context_id=lead_id,
        data=lead_data,
        fetched_at=datetime.now(timezone.utc).isoformat()
    )
    context.token_estimate = estimate_tokens(context.data)
    
    return context


def prefetch_campaign_context(campaign_id: str, data_dir: Optional[Path] = None) -> PrefetchedContext:
    """
    Fetch campaign history before decision.
    
    Loads campaign performance data, A/B test results, and
    historical metrics for informed decision making.
    """
    if data_dir is None:
        data_dir = Path('.hive-mind')
    
    campaign_data = {}
    
    campaigns_dir = data_dir / 'campaigns'
    if campaigns_dir.exists():
        for f in sorted(campaigns_dir.glob('*.json'), reverse=True):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    if data.get('plan_id') == campaign_id:
                        campaign_data = data
                        break
                    campaigns = data.get('campaigns', [])
                    for c in campaigns:
                        if c.get('campaign_id') == campaign_id:
                            campaign_data = c
                            break
                if campaign_data:
                    break
            except (json.JSONDecodeError, IOError):
                continue
    
    context = PrefetchedContext(
        context_type='campaign',
        context_id=campaign_id,
        data=campaign_data,
        fetched_at=datetime.now(timezone.utc).isoformat()
    )
    context.token_estimate = estimate_tokens(context.data)
    
    return context


def inject_prefetched(thread: EventThread, prefetched: PrefetchedContext) -> None:
    """Add prefetched data to context via event."""
    thread.add_event(
        EventType.PREFETCH_COMPLETE,
        {
            'context_type': prefetched.context_type,
            'context_id': prefetched.context_id,
            'token_estimate': prefetched.token_estimate,
            'data_keys': list(prefetched.data.keys()) if prefetched.data else []
        }
    )
    thread.metadata[f'prefetch_{prefetched.context_type}_{prefetched.context_id}'] = prefetched.to_dict()


@dataclass
class ContextSummary:
    """Compressed context artifact from a workflow phase."""
    phase: str
    agent: str
    created_at: str
    summary: str
    key_findings: List[str]
    action_items: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
    token_estimate: int = 0
    
    def to_prompt_block(self) -> str:
        """Generate a compact prompt block from this summary."""
        findings = '\n'.join(f'- {f}' for f in self.key_findings[:5])
        actions = '\n'.join(f'- {a}' for a in self.action_items[:5])
        
        return f"""
## {self.phase.upper()} PHASE SUMMARY ({self.agent})
**Generated**: {self.created_at}

{self.summary}

### Key Findings
{findings}

### Action Items
{actions}
"""
    
    def to_xml(self) -> str:
        """Generate compact XML representation."""
        findings_xml = ''.join(f'<f>{f}</f>' for f in self.key_findings[:5])
        actions_xml = ''.join(f'<a>{a}</a>' for a in self.action_items[:5])
        
        return f'<summary phase="{self.phase}" agent="{self.agent}" ts="{self.created_at[:19]}"><s>{self.summary}</s><findings>{findings_xml}</findings><actions>{actions_xml}</actions></summary>'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'phase': self.phase,
            'agent': self.agent,
            'created_at': self.created_at,
            'summary': self.summary,
            'key_findings': self.key_findings,
            'action_items': self.action_items,
            'metadata': self.metadata,
            'token_estimate': self.token_estimate
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContextSummary':
        return cls(
            phase=data['phase'],
            agent=data['agent'],
            created_at=data['created_at'],
            summary=data['summary'],
            key_findings=data.get('key_findings', []),
            action_items=data.get('action_items', []),
            metadata=data.get('metadata', {}),
            token_estimate=data.get('token_estimate', 0)
        )


class ContextManager:
    """
    Manages context across agent workflow phases.
    
    Implements Frequent Intentional Compaction (FIC) with
    event-based threading and pre-fetch patterns.
    """
    
    def __init__(
        self, 
        workflow_id: str, 
        model: str = 'default',
        max_context: Optional[int] = None
    ):
        self.workflow_id = workflow_id
        self.model = model
        self.max_context_tokens = max_context or MODEL_CONTEXT_WINDOWS.get(model, 128000)
        self.smart_zone_threshold = self.max_context_tokens * ZONE_THRESHOLDS[ContextZone.SMART]
        
        self.phases: Dict[str, ContextSummary] = {}
        self.current_token_usage = 0
        self.compaction_history: List[Dict[str, Any]] = []
        
        self.thread = EventThread(workflow_id)
        
    def add_phase_summary(self, summary: ContextSummary):
        """Add a compacted phase summary."""
        summary.token_estimate = estimate_tokens(summary.to_prompt_block())
        
        self.phases[summary.phase] = summary
        self._update_token_estimate()
        
        self.thread.add_event(
            EventType.PHASE_COMPLETE,
            {'phase': summary.phase, 'agent': summary.agent},
            phase=summary.phase
        )
        
        if self.should_compact():
            self.compaction_history.append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'phase': summary.phase,
                'reason': 'approaching_dumb_zone',
                'token_usage_before': self.current_token_usage
            })
            self.thread.compact()
        
    def get_compacted_context(self, phases: Optional[List[str]] = None, use_xml: bool = False) -> str:
        """Get all phase summaries as compacted context."""
        if phases is None:
            phases = ['research', 'plan', 'implement']
        
        blocks = []
        for phase in phases:
            if phase in self.phases:
                if use_xml:
                    blocks.append(self.phases[phase].to_xml())
                else:
                    blocks.append(self.phases[phase].to_prompt_block())
        
        return "\n".join(blocks)
    
    def get_full_context(self, use_xml: bool = True) -> str:
        """Get full context including thread and summaries."""
        parts = []
        
        if use_xml:
            parts.append(serialize_thread_summary(self.thread))
        else:
            parts.append(serialize_thread(self.thread))
        
        parts.append(self.get_compacted_context(use_xml=use_xml))
        
        return '\n'.join(parts)
    
    def get_context_zone(self) -> ContextZone:
        """Get the current context utilization zone."""
        return get_context_zone(self.current_token_usage, self.max_context_tokens)
    
    def is_in_smart_zone(self) -> bool:
        """Check if we're operating under 40% context."""
        return self.get_context_zone() == ContextZone.SMART
    
    def should_compact(self) -> bool:
        """Check if compaction is needed."""
        zone = self.get_context_zone()
        return zone in [ContextZone.CAUTION, ContextZone.DUMB, ContextZone.CRITICAL]
    
    def get_utilization_report(self) -> Dict[str, Any]:
        """Get detailed context utilization report."""
        zone = self.get_context_zone()
        ratio = self.current_token_usage / self.max_context_tokens
        
        return {
            'workflow_id': self.workflow_id,
            'model': self.model,
            'max_tokens': self.max_context_tokens,
            'current_tokens': self.current_token_usage,
            'utilization_ratio': round(ratio, 4),
            'utilization_percent': f"{ratio * 100:.1f}%",
            'zone': zone.value,
            'is_healthy': zone == ContextZone.SMART,
            'headroom_tokens': int(self.smart_zone_threshold - self.current_token_usage),
            'phases_loaded': list(self.phases.keys()),
            'compaction_count': len(self.compaction_history),
            'thread_events': len(self.thread.events),
            'unresolved_errors': len(self.thread.get_unresolved_errors())
        }
        
    def _update_token_estimate(self):
        """Estimate current total token usage."""
        phase_tokens = sum(
            len(p.to_prompt_block()) 
            for p in self.phases.values()
        )
        thread_tokens = len(serialize_thread(self.thread))
        
        self.current_token_usage = (phase_tokens + thread_tokens) // 4
        
    def save_state(self, path: Optional[Path] = None):
        """Persist context state for workflow resumption."""
        if path is None:
            path = Path('.hive-mind') / 'context' / f"{self.workflow_id}_context.json"
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w') as f:
            json.dump({
                'workflow_id': self.workflow_id,
                'model': self.model,
                'max_context_tokens': self.max_context_tokens,
                'phases': {k: v.to_dict() for k, v in self.phases.items()},
                'token_usage': self.current_token_usage,
                'compaction_history': self.compaction_history,
                'thread': self.thread.to_dict(),
                'saved_at': datetime.now(timezone.utc).isoformat()
            }, f, indent=2)
    
    @classmethod
    def load_state(cls, path: Path) -> 'ContextManager':
        """Load context state from file."""
        with open(path) as f:
            data = json.load(f)
        
        manager = cls(
            workflow_id=data['workflow_id'],
            model=data.get('model', 'default'),
            max_context=data.get('max_context_tokens')
        )
        
        for phase, summary_data in data.get('phases', {}).items():
            manager.phases[phase] = ContextSummary.from_dict(summary_data)
        
        manager.current_token_usage = data.get('token_usage', 0)
        manager.compaction_history = data.get('compaction_history', [])
        
        if 'thread' in data:
            manager.thread = EventThread.from_dict(data['thread'])
        
        return manager


def compact_lead_batch(leads: List[Dict], max_leads: int = 20) -> Dict[str, Any]:
    """
    Compact a large lead batch into a summary for context efficiency.
    """
    if len(leads) <= max_leads:
        return {
            'leads': leads, 
            'compacted': False,
            'token_estimate': estimate_tokens(leads)
        }
    
    tiers = {}
    sources = {}
    campaigns = {}
    industries = {}
    
    for lead in leads:
        tier = lead.get('icp_tier', 'unknown')
        tiers[tier] = tiers.get(tier, 0) + 1
        
        source = lead.get('source_type', 'unknown')
        sources[source] = sources.get(source, 0) + 1
        
        campaign = lead.get('recommended_campaign', 'unknown')
        campaigns[campaign] = campaigns.get(campaign, 0) + 1
        
        industry = lead.get('industry', 'unknown')
        industries[industry] = industries.get(industry, 0) + 1
    
    icp_scores = [l.get('icp_score', 0) for l in leads]
    intent_scores = [l.get('intent_score', 0) for l in leads]
    
    sorted_leads = sorted(leads, key=lambda x: x.get('icp_score', 0), reverse=True)
    sample = sorted_leads[:max_leads]
    
    result = {
        'compacted': True,
        'total_count': len(leads),
        'sample_count': len(sample),
        'compaction_ratio': round(len(sample) / len(leads), 4),
        'tier_distribution': tiers,
        'source_distribution': sources,
        'campaign_distribution': campaigns,
        'top_industries': dict(sorted(industries.items(), key=lambda x: -x[1])[:5]),
        'avg_icp_score': round(sum(icp_scores) / len(icp_scores), 1) if icp_scores else 0,
        'max_icp_score': max(icp_scores) if icp_scores else 0,
        'min_icp_score': min(icp_scores) if icp_scores else 0,
        'avg_intent_score': round(sum(intent_scores) / len(intent_scores), 1) if intent_scores else 0,
        'sample_leads': sample,
        'compacted_at': datetime.now(timezone.utc).isoformat()
    }
    
    result['token_estimate'] = estimate_tokens(result)
    return result


def create_phase_summary(
    phase: str,
    agent: str,
    raw_data: Dict[str, Any],
    max_findings: int = 5,
    max_actions: int = 5
) -> ContextSummary:
    """Create a compacted phase summary from raw processing data."""
    
    summary = raw_data.get('summary', '')
    if not summary:
        count = raw_data.get('lead_count', raw_data.get('count', 0))
        summary = f"Processed {count} items in {phase} phase."
    
    key_findings = raw_data.get('key_findings', [])
    if not key_findings and 'findings' in raw_data:
        key_findings = raw_data['findings']
    key_findings = key_findings[:max_findings]
    
    action_items = raw_data.get('action_items', [])
    if not action_items and 'next_steps' in raw_data:
        action_items = raw_data['next_steps']
    action_items = action_items[:max_actions]
    
    return ContextSummary(
        phase=phase,
        agent=agent,
        created_at=datetime.now(timezone.utc).isoformat(),
        summary=summary,
        key_findings=key_findings,
        action_items=action_items,
        metadata={
            'source_token_estimate': estimate_tokens(raw_data),
            'compaction_achieved': True
        }
    )
