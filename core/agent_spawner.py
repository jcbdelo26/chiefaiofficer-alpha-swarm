"""
Agent Spawner Module
=====================
Implements parallel agent spawning for HumanLayer's 12-Factor Agents patterns.

Key Features:
- spawn_parallel_agents() - run multiple focused agents in parallel
- AgentTask dataclass for typed task definitions
- wait_all() - collect results from parallel agents
- Built-in agent types for common operations

Based on the pattern of spawning specialized, focused agents for
specific tasks rather than overloading a single agent.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Callable, Awaitable, Union
from pathlib import Path
from enum import Enum
import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class AgentType(Enum):
    """Built-in agent types for common operations."""
    LEAD_ANALYZER = "lead-analyzer"
    CAMPAIGN_PATTERN_FINDER = "campaign-pattern-finder"
    ENRICHMENT_CHECKER = "enrichment-checker"
    ICP_SCORER = "icp-scorer"
    CONTENT_GENERATOR = "content-generator"
    COMPLIANCE_CHECKER = "compliance-checker"
    CUSTOM = "custom"


class AgentStatus(Enum):
    """Agent execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class AgentTask:
    """
    Definition of a task for a spawned agent.
    
    Attributes:
        agent_type: Type of agent to spawn
        prompt: Task prompt or instruction
        timeout: Maximum execution time in seconds
        context: Additional context data for the agent
        task_id: Unique identifier for this task
        priority: Task priority (higher = more important)
    """
    agent_type: Union[AgentType, str]
    prompt: str
    timeout: float = 30.0
    context: Dict[str, Any] = field(default_factory=dict)
    task_id: Optional[str] = None
    priority: int = 0
    
    def __post_init__(self):
        if self.task_id is None:
            self.task_id = str(uuid.uuid4())[:8]
        if isinstance(self.agent_type, str):
            try:
                self.agent_type = AgentType(self.agent_type)
            except ValueError:
                self.agent_type = AgentType.CUSTOM


@dataclass
class AgentResult:
    """
    Result from a spawned agent execution.
    
    Attributes:
        task_id: ID of the task that was executed
        agent_type: Type of agent that executed
        status: Execution status
        result: The actual result data
        error: Error message if failed
        execution_time: Time taken in seconds
        token_estimate: Estimated tokens used
    """
    task_id: str
    agent_type: Union[AgentType, str]
    status: AgentStatus
    result: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    token_estimate: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'task_id': self.task_id,
            'agent_type': self.agent_type.value if isinstance(self.agent_type, AgentType) else self.agent_type,
            'status': self.status.value,
            'result': self.result,
            'error': self.error,
            'execution_time': self.execution_time,
            'token_estimate': self.token_estimate,
            'started_at': self.started_at,
            'completed_at': self.completed_at
        }
    
    @property
    def success(self) -> bool:
        return self.status == AgentStatus.COMPLETED


class AgentExecutor:
    """
    Executes agent tasks with built-in handlers for common agent types.
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path('.hive-mind')
        self._handlers: Dict[AgentType, Callable] = {
            AgentType.LEAD_ANALYZER: self._analyze_leads,
            AgentType.CAMPAIGN_PATTERN_FINDER: self._find_campaign_patterns,
            AgentType.ENRICHMENT_CHECKER: self._check_enrichment,
            AgentType.ICP_SCORER: self._score_icp,
            AgentType.CONTENT_GENERATOR: self._generate_content,
            AgentType.COMPLIANCE_CHECKER: self._check_compliance,
        }
    
    def register_handler(self, agent_type: AgentType, handler: Callable):
        """Register a custom handler for an agent type."""
        self._handlers[agent_type] = handler
    
    def execute(self, task: AgentTask) -> AgentResult:
        """Execute a single agent task."""
        start_time = datetime.now(timezone.utc)
        
        try:
            handler = self._handlers.get(task.agent_type)
            
            if handler is None:
                if task.agent_type == AgentType.CUSTOM:
                    result = self._execute_custom(task)
                else:
                    raise ValueError(f"No handler for agent type: {task.agent_type}")
            else:
                result = handler(task)
            
            end_time = datetime.now(timezone.utc)
            execution_time = (end_time - start_time).total_seconds()
            
            return AgentResult(
                task_id=task.task_id,
                agent_type=task.agent_type,
                status=AgentStatus.COMPLETED,
                result=result,
                execution_time=execution_time,
                token_estimate=self._estimate_tokens(result),
                started_at=start_time.isoformat(),
                completed_at=end_time.isoformat()
            )
            
        except Exception as e:
            end_time = datetime.now(timezone.utc)
            return AgentResult(
                task_id=task.task_id,
                agent_type=task.agent_type,
                status=AgentStatus.FAILED,
                error=str(e),
                execution_time=(end_time - start_time).total_seconds(),
                started_at=start_time.isoformat(),
                completed_at=end_time.isoformat()
            )
    
    def _estimate_tokens(self, data: Any) -> int:
        """Estimate token count for result data."""
        if isinstance(data, str):
            return len(data) // 4
        elif isinstance(data, (dict, list)):
            return len(json.dumps(data, default=str)) // 4
        return len(str(data)) // 4
    
    def _analyze_leads(self, task: AgentTask) -> Dict[str, Any]:
        """Analyze leads for patterns and insights."""
        leads = task.context.get('leads', [])
        
        if not leads:
            return {'analysis': 'No leads provided', 'patterns': []}
        
        tiers = {}
        industries = {}
        sources = {}
        titles = {}
        
        for lead in leads:
            tier = lead.get('icp_tier', 'unknown')
            tiers[tier] = tiers.get(tier, 0) + 1
            
            industry = lead.get('industry', 'unknown')
            industries[industry] = industries.get(industry, 0) + 1
            
            source = lead.get('source', 'unknown')
            sources[source] = sources.get(source, 0) + 1
            
            title = lead.get('title', 'unknown')
            titles[title] = titles.get(title, 0) + 1
        
        icp_scores = [l.get('icp_score', 0) for l in leads]
        
        return {
            'total_leads': len(leads),
            'tier_distribution': tiers,
            'top_industries': dict(sorted(industries.items(), key=lambda x: -x[1])[:5]),
            'top_sources': dict(sorted(sources.items(), key=lambda x: -x[1])[:3]),
            'top_titles': dict(sorted(titles.items(), key=lambda x: -x[1])[:5]),
            'avg_icp_score': round(sum(icp_scores) / len(icp_scores), 2) if icp_scores else 0,
            'high_value_count': sum(1 for s in icp_scores if s >= 80),
            'patterns': self._identify_patterns(leads)
        }
    
    def _identify_patterns(self, leads: List[Dict]) -> List[str]:
        """Identify patterns in lead data."""
        patterns = []
        
        competitor_followers = sum(1 for l in leads if 'competitor' in l.get('source', '').lower())
        if competitor_followers > len(leads) * 0.3:
            patterns.append(f"High competitor follower concentration ({competitor_followers}/{len(leads)})")
        
        event_attendees = sum(1 for l in leads if 'event' in l.get('source', '').lower())
        if event_attendees > len(leads) * 0.2:
            patterns.append(f"Significant event attendee presence ({event_attendees}/{len(leads)})")
        
        high_icp = sum(1 for l in leads if l.get('icp_score', 0) >= 85)
        if high_icp > len(leads) * 0.1:
            patterns.append(f"Quality batch: {high_icp} leads with ICP >= 85")
        
        return patterns
    
    def _find_campaign_patterns(self, task: AgentTask) -> Dict[str, Any]:
        """Find patterns in campaign performance data."""
        campaigns_dir = self.data_dir / 'campaigns'
        patterns = []
        metrics = {}
        
        if campaigns_dir.exists():
            for f in sorted(campaigns_dir.glob('*.json'), reverse=True)[:10]:
                try:
                    with open(f) as fp:
                        data = json.load(fp)
                        if 'campaigns' in data:
                            for c in data['campaigns']:
                                template = c.get('template', 'unknown')
                                if template not in metrics:
                                    metrics[template] = {'count': 0, 'total_leads': 0}
                                metrics[template]['count'] += 1
                                metrics[template]['total_leads'] += c.get('lead_count', 0)
                except (json.JSONDecodeError, IOError):
                    continue
        
        for template, m in metrics.items():
            patterns.append(f"Template '{template}': {m['count']} campaigns, {m['total_leads']} total leads")
        
        return {
            'patterns': patterns,
            'template_metrics': metrics,
            'campaigns_analyzed': sum(m['count'] for m in metrics.values())
        }
    
    def _check_enrichment(self, task: AgentTask) -> Dict[str, Any]:
        """Check enrichment status of leads."""
        leads = task.context.get('leads', [])
        
        enrichment_fields = ['company_size', 'industry', 'linkedin_url', 'email', 'phone']
        
        field_coverage = {}
        for field in enrichment_fields:
            filled = sum(1 for l in leads if l.get(field))
            field_coverage[field] = {
                'filled': filled,
                'total': len(leads),
                'coverage': round(filled / len(leads) * 100, 1) if leads else 0
            }
        
        needs_enrichment = []
        for lead in leads:
            missing = [f for f in enrichment_fields if not lead.get(f)]
            if len(missing) > len(enrichment_fields) / 2:
                needs_enrichment.append({
                    'id': lead.get('id', lead.get('linkedin_url', 'unknown')),
                    'missing_fields': missing
                })
        
        return {
            'total_leads': len(leads),
            'field_coverage': field_coverage,
            'needs_enrichment_count': len(needs_enrichment),
            'needs_enrichment_sample': needs_enrichment[:5],
            'overall_score': round(
                sum(f['coverage'] for f in field_coverage.values()) / len(enrichment_fields), 1
            ) if enrichment_fields else 0
        }
    
    def _score_icp(self, task: AgentTask) -> Dict[str, Any]:
        """Score leads against ICP criteria."""
        leads = task.context.get('leads', [])
        icp_criteria = task.context.get('icp_criteria', {})
        
        scored_leads = []
        for lead in leads:
            score = lead.get('icp_score', 0)
            
            if not score:
                score = 50
                if lead.get('company_size', 0) >= 100:
                    score += 15
                if lead.get('title', '').lower() in ['cro', 'ceo', 'vp sales', 'director']:
                    score += 20
                if 'competitor' in lead.get('source', '').lower():
                    score += 10
            
            scored_leads.append({
                'id': lead.get('id', lead.get('linkedin_url', 'unknown')),
                'score': min(100, score),
                'tier': 'tier_1' if score >= 85 else 'tier_2' if score >= 70 else 'tier_3'
            })
        
        return {
            'total_scored': len(scored_leads),
            'tier_1_count': sum(1 for l in scored_leads if l['tier'] == 'tier_1'),
            'tier_2_count': sum(1 for l in scored_leads if l['tier'] == 'tier_2'),
            'tier_3_count': sum(1 for l in scored_leads if l['tier'] == 'tier_3'),
            'avg_score': round(sum(l['score'] for l in scored_leads) / len(scored_leads), 1) if scored_leads else 0,
            'top_leads': sorted(scored_leads, key=lambda x: -x['score'])[:10]
        }
    
    def _generate_content(self, task: AgentTask) -> Dict[str, Any]:
        """Generate content based on task prompt."""
        template = task.context.get('template', 'default')
        variables = task.context.get('variables', {})
        
        return {
            'template_used': template,
            'variables_applied': list(variables.keys()),
            'content_generated': True,
            'note': 'Full LLM content generation should be integrated separately'
        }
    
    def _check_compliance(self, task: AgentTask) -> Dict[str, Any]:
        """Check compliance of campaign content."""
        content = task.context.get('content', '')
        
        issues = []
        
        spam_words = ['free', 'guarantee', 'act now', 'limited time']
        for word in spam_words:
            if word.lower() in content.lower():
                issues.append(f"Potential spam trigger: '{word}'")
        
        if len(content) > 2000:
            issues.append("Email content exceeds recommended length (2000 chars)")
        
        if '[unsubscribe]' not in content.lower() and 'unsubscribe' not in content.lower():
            issues.append("Missing unsubscribe link (CAN-SPAM requirement)")
        
        return {
            'compliant': len(issues) == 0,
            'issues': issues,
            'content_length': len(content),
            'checks_performed': ['spam_triggers', 'length', 'can_spam']
        }
    
    def _execute_custom(self, task: AgentTask) -> Dict[str, Any]:
        """Execute a custom task using the prompt."""
        return {
            'prompt_received': task.prompt[:100] + '...' if len(task.prompt) > 100 else task.prompt,
            'context_keys': list(task.context.keys()),
            'note': 'Custom task execution - integrate with LLM for full capability'
        }


class AgentSpawner:
    """
    Spawns and manages parallel agent execution.
    
    Implements HumanLayer's pattern of running multiple focused agents
    in parallel for specific tasks.
    """
    
    def __init__(self, max_workers: int = 4, data_dir: Optional[Path] = None):
        self.max_workers = max_workers
        self.executor = AgentExecutor(data_dir)
        self._thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        self._results: Dict[str, AgentResult] = {}
        self._lock = threading.Lock()
    
    def spawn_parallel_agents(self, tasks: List[AgentTask]) -> List[str]:
        """
        Spawn multiple focused agents in parallel.
        
        Args:
            tasks: List of AgentTask definitions
            
        Returns:
            List of task IDs that were spawned
        """
        task_ids = []
        
        sorted_tasks = sorted(tasks, key=lambda t: -t.priority)
        
        for task in sorted_tasks:
            future = self._thread_pool.submit(self._execute_task, task)
            task_ids.append(task.task_id)
        
        return task_ids
    
    def _execute_task(self, task: AgentTask) -> AgentResult:
        """Execute a task and store the result."""
        result = self.executor.execute(task)
        
        with self._lock:
            self._results[task.task_id] = result
        
        return result
    
    def wait_all(self, task_ids: List[str], timeout: Optional[float] = None) -> List[AgentResult]:
        """
        Wait for all tasks to complete and return results.
        
        Args:
            task_ids: List of task IDs to wait for
            timeout: Maximum time to wait (None = wait forever)
            
        Returns:
            List of AgentResult objects
        """
        start_time = datetime.now(timezone.utc)
        results = []
        
        while len(results) < len(task_ids):
            if timeout:
                elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                if elapsed > timeout:
                    for task_id in task_ids:
                        if task_id not in [r.task_id for r in results]:
                            results.append(AgentResult(
                                task_id=task_id,
                                agent_type=AgentType.CUSTOM,
                                status=AgentStatus.TIMEOUT,
                                error=f"Task timed out after {timeout}s"
                            ))
                    break
            
            with self._lock:
                for task_id in task_ids:
                    if task_id in self._results and task_id not in [r.task_id for r in results]:
                        results.append(self._results[task_id])
            
            if len(results) < len(task_ids):
                import time
                time.sleep(0.1)
        
        return results
    
    def get_result(self, task_id: str) -> Optional[AgentResult]:
        """Get result for a specific task."""
        with self._lock:
            return self._results.get(task_id)
    
    def shutdown(self, wait: bool = True):
        """Shutdown the thread pool."""
        self._thread_pool.shutdown(wait=wait)


def spawn_parallel_agents(tasks: List[AgentTask], max_workers: int = 4) -> List[AgentResult]:
    """
    Convenience function to spawn parallel agents and wait for results.
    
    Args:
        tasks: List of AgentTask definitions
        max_workers: Maximum parallel workers
        
    Returns:
        List of AgentResult objects
    """
    spawner = AgentSpawner(max_workers=max_workers)
    
    try:
        task_ids = spawner.spawn_parallel_agents(tasks)
        max_timeout = max(t.timeout for t in tasks) * 2 if tasks else 60
        results = spawner.wait_all(task_ids, timeout=max_timeout)
        return results
    finally:
        spawner.shutdown()


def wait_all(spawner: AgentSpawner, task_ids: List[str], timeout: Optional[float] = None) -> List[AgentResult]:
    """
    Wait for all spawned tasks to complete.
    
    Args:
        spawner: The AgentSpawner instance
        task_ids: List of task IDs to wait for
        timeout: Maximum wait time
        
    Returns:
        List of AgentResult objects
    """
    return spawner.wait_all(task_ids, timeout)
