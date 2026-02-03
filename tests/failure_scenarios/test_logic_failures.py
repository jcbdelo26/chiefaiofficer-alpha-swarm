
"""
Logic & Context Scenarios
=========================
Test business logic edge cases and context window exhaustion.
"""

import pytest
from core.failure_tracker import FailureTracker, FailureCategory

class TestLogicAndContext:
    
    def setup_method(self):
        self.tracker = FailureTracker()

    def test_context_window_overflow(self):
        """Verify system detects and handles context overflow."""
        # Simulate a massive conversation history
        huge_context = "msg " * 100000 
        
        try:
            if len(huge_context) > 50000: # Simulated limit
                raise MemoryError("Context Limit Exceeded: 100k tokens > 50k limit")
        except Exception as e:
            failure_id = self.tracker.log_failure(
                agent="QUEEN",
                task_id="test_context_overflow",
                error=e,
                context={"steps": 500}
            )
            
        failure = self.tracker.get_failure(failure_id)
        # Should be RESOURCE_ERROR, but MemoryError might map differently depending on logic
        assert failure.category == FailureCategory.RESOURCE_ERROR.value

    def test_contradictory_instructions(self):
        """Verify agent handles logic conflict (e.g. qualify but blacklist)."""
        lead = {"domain": "competitor.com", "revenue": "$100M"}
        
        try:
            # Simulated logic conflict
            is_qualified = True
            is_blacklisted = True
            
            if is_qualified and is_blacklisted:
                raise AssertionError("Logic Error: Qualified lead is on blacklist")
        except Exception as e:
            failure_id = self.tracker.log_failure(
                agent="GATEKEEPER",
                task_id="test_logic_conflict",
                error=e,
                context={"lead": lead}
            )
            
        failure = self.tracker.get_failure(failure_id)
        assert failure.category == FailureCategory.LOGIC_ERROR.value
