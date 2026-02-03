"""
Tests for Context Engineering Core Module
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context import (
    EventThread, EventType, Event,
    estimate_tokens, check_context_budget, get_context_zone, ContextZone,
    trigger_compaction, serialize_event, serialize_thread, serialize_thread_summary,
    prefetch_lead_context, prefetch_campaign_context, inject_prefetched,
    ContextSummary, ContextManager, create_phase_summary, compact_lead_batch
)
from core.agent_spawner import (
    AgentTask, AgentType, AgentStatus, AgentResult,
    AgentSpawner, spawn_parallel_agents, AgentExecutor
)


class TestEventThread:
    def test_create_thread(self):
        thread = EventThread('test-123')
        assert thread.thread_id == 'test-123'
        assert len(thread.events) == 0
    
    def test_add_event(self):
        thread = EventThread('test-123')
        event = thread.add_event(EventType.PHASE_STARTED, {'phase': 'research'})
        assert event.event_type == EventType.PHASE_STARTED
        assert len(thread.events) == 1
    
    def test_get_recent_events(self):
        thread = EventThread('test-123')
        for i in range(15):
            thread.add_event(EventType.PHASE_STARTED, {'index': i})
        
        recent = thread.get_recent_events(5)
        assert len(recent) == 5
        assert recent[-1].data['index'] == 14
    
    def test_compact_removes_resolved(self):
        thread = EventThread('test-123')
        thread.add_event(EventType.ERROR, {'msg': 'test error'})
        thread.events[0].resolved = True
        
        removed = thread.compact()
        assert removed == 1
        # After compaction, there's a COMPACTION event added
        assert len([e for e in thread.events if e.event_type == EventType.ERROR]) == 0


class TestSerialization:
    def test_serialize_event(self):
        event = Event(
            event_type=EventType.RESEARCH_COMPLETE,
            timestamp='2026-01-15T10:00:00Z',
            data={'leads': 50, 'tier': 'tier_1'}
        )
        xml = serialize_event(event)
        assert 'type="research_complete"' in xml
        assert 'leads="50"' in xml
    
    def test_serialize_thread(self):
        thread = EventThread('test-123')
        thread.add_event(EventType.PHASE_STARTED, {'phase': 'research'})
        
        xml = serialize_thread(thread)
        assert '<thread id="test-123"' in xml
        assert '</thread>' in xml
    
    def test_serialize_thread_summary(self):
        thread = EventThread('test-123')
        thread.add_event(EventType.PHASE_COMPLETE, {'phase': 'research'}, phase='research')
        
        summary = serialize_thread_summary(thread)
        assert 'thread-summary' in summary
        assert 'events="1"' in summary


class TestContextBudget:
    def test_estimate_tokens_string(self):
        text = "a" * 400
        tokens = estimate_tokens(text)
        assert tokens == 100  # 400 / 4
    
    def test_check_context_budget_under(self):
        assert check_context_budget(50000, max_tokens=128000, max_budget=0.6) == True
    
    def test_check_context_budget_over(self):
        assert check_context_budget(80000, max_tokens=128000, max_budget=0.6) == False
    
    def test_get_context_zone_smart(self):
        zone = get_context_zone(30000, 128000)
        assert zone == ContextZone.SMART
    
    def test_get_context_zone_dumb(self):
        zone = get_context_zone(90000, 128000)
        assert zone == ContextZone.DUMB


class TestContextManager:
    def test_create_manager(self):
        manager = ContextManager('workflow-123')
        assert manager.workflow_id == 'workflow-123'
        assert manager.is_in_smart_zone() == True
    
    def test_add_phase_summary(self):
        manager = ContextManager('workflow-123')
        summary = ContextSummary(
            phase='research',
            agent='HUNTER',
            created_at='2026-01-15T10:00:00Z',
            summary='Analyzed 50 leads',
            key_findings=['Finding 1', 'Finding 2'],
            action_items=['Action 1']
        )
        manager.add_phase_summary(summary)
        assert 'research' in manager.phases


class TestAgentSpawner:
    def test_create_task(self):
        task = AgentTask(
            agent_type=AgentType.LEAD_ANALYZER,
            prompt='Analyze leads',
            context={'leads': []}
        )
        assert task.agent_type == AgentType.LEAD_ANALYZER
        assert task.task_id is not None
    
    def test_executor_analyze_leads(self):
        executor = AgentExecutor()
        task = AgentTask(
            agent_type=AgentType.LEAD_ANALYZER,
            prompt='Analyze',
            context={'leads': [
                {'icp_score': 85, 'industry': 'Tech'},
                {'icp_score': 70, 'industry': 'Finance'}
            ]}
        )
        result = executor.execute(task)
        assert result.status == AgentStatus.COMPLETED
        assert result.result['total_leads'] == 2
    
    def test_spawn_parallel(self):
        tasks = [
            AgentTask(AgentType.LEAD_ANALYZER, 'Task 1', context={'leads': [{'icp_score': 80}]}),
            AgentTask(AgentType.ENRICHMENT_CHECKER, 'Task 2', context={'leads': [{'company_size': 100}]})
        ]
        results = spawn_parallel_agents(tasks, max_workers=2)
        assert len(results) == 2
        assert all(r.status == AgentStatus.COMPLETED for r in results)


class TestCompactLeadBatch:
    def test_no_compaction_needed(self):
        leads = [{'id': i, 'icp_score': 80} for i in range(10)]
        result = compact_lead_batch(leads, max_leads=20)
        assert result['compacted'] == False
    
    def test_compaction_applied(self):
        leads = [{'id': i, 'icp_score': 80, 'icp_tier': 'tier_1'} for i in range(50)]
        result = compact_lead_batch(leads, max_leads=10)
        assert result['compacted'] == True
        assert result['total_count'] == 50
        assert result['sample_count'] == 10


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
