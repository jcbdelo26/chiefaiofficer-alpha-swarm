#!/usr/bin/env python3
"""
Failure Tracker
===============
Capture, categorize, and store all agent failures for self-annealing.

Features:
- Automatic failure logging
- Categorization (API, validation, logic, resource)
- Context preservation
- Reasoning bank integration

Usage:
    from core.failure_tracker import FailureTracker
    
    tracker = FailureTracker()
    tracker.log_failure(agent="HUNTER", task_id="task_123", error=e, context={...})
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

class FailureCategory(Enum):
    """Categories of failures."""
    API_ERROR = "api_error"              # External API failures
    VALIDATION_ERROR = "validation_error"  # Data validation issues
    LOGIC_ERROR = "logic_error"          # Business logic errors
    RESOURCE_ERROR = "resource_error"    # Resource exhaustion
    UNKNOWN = "unknown"                  # Uncategorized

@dataclass
class FailureRecord:
    """Single failure record."""
    failure_id: str
    agent_name: str
    task_id: str
    category: str
    error_message: str
    error_type: str
    context: Dict[str, Any]
    stack_trace: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved: bool = False
    resolution_notes: Optional[str] = None

class FailureTracker:
    """Track and analyze agent failures."""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path(".hive-mind/failures")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.failures_file = self.storage_dir / "all_failures.json"
        self.reasoning_bank_file = Path(".hive-mind/reasoning_bank.json")
        
        # Load existing failures
        self.failures = self._load_failures()
    
    def _load_failures(self) -> Dict[str, FailureRecord]:
        """Load failures from disk."""
        if self.failures_file.exists():
            try:
                with open(self.failures_file) as f:
                    data = json.load(f)
                    return {
                        fid: FailureRecord(**record) 
                        for fid, record in data.items()
                    }
            except:
                return {}
        return {}
    
    def _save_failures(self):
        """Save failures to disk."""
        data = {fid: asdict(record) for fid, record in self.failures.items()}
        with open(self.failures_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _categorize_failure(self, error: Exception, context: Dict[str, Any]) -> FailureCategory:
        """
        Automatically categorize a failure based on error type and context.
        """
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # API errors
        if any(keyword in error_str for keyword in ['rate limit', 'timeout', 'connection', 'api', '429', '500', '502', '503']):
            return FailureCategory.API_ERROR
        
        # Validation errors
        if any(keyword in error_str for keyword in ['validation', 'invalid', 'missing', 'required', 'format']):
            return FailureCategory.VALIDATION_ERROR
        
        # Resource errors
        if any(keyword in error_str for keyword in ['memory', 'context', 'budget', 'queue', 'overflow']):
            return FailureCategory.RESOURCE_ERROR
        
        # Logic errors
        if any(keyword in error_type for keyword in ['assertion', 'logic', 'attribute', 'key', 'index']):
            return FailureCategory.LOGIC_ERROR
        
        return FailureCategory.UNKNOWN
    
    def log_failure(
        self,
        agent: str,
        task_id: str,
        error: Exception,
        context: Dict[str, Any],
        stack_trace: Optional[str] = None
    ) -> str:
        """
        Log a failure.
        
        Returns:
            failure_id: Unique ID for this failure
        """
        # Generate failure ID
        fingerprint = f"{agent}_{type(error).__name__}_{str(error)[:50]}"
        failure_id = hashlib.md5(fingerprint.encode()).hexdigest()[:12]
        
        # Categorize
        category = self._categorize_failure(error, context)
        
        # Create record
        record = FailureRecord(
            failure_id=failure_id,
            agent_name=agent,
            task_id=task_id,
            category=category.value,
            error_message=str(error),
            error_type=type(error).__name__,
            context=context,
            stack_trace=stack_trace
        )
        
        # Store
        self.failures[failure_id] = record
        self._save_failures()
        
        # Also save individual failure file for detailed analysis
        individual_file = self.storage_dir / f"{failure_id}.json"
        with open(individual_file, 'w') as f:
            json.dump(asdict(record), f, indent=2)
        
        # Update reasoning bank
        self._update_reasoning_bank(record)
        
        print(f"[FailureTracker] Logged {category.value} failure: {failure_id} ({agent})")
        
        return failure_id
    
    def _update_reasoning_bank(self, record: FailureRecord):
        """Add failure to reasoning bank for pattern analysis."""
        # Load reasoning bank
        if self.reasoning_bank_file.exists():
            with open(self.reasoning_bank_file) as f:
                bank = json.load(f)
        else:
            bank = {"failures": [], "learnings": [], "updated_at": ""}
        
        # Add failure entry
        bank["failures"].append({
            "failure_id": record.failure_id,
            "agent": record.agent_name,
            "category": record.category,
            "error": record.error_message,
            "timestamp": record.timestamp
        })
        
        # Keep only last 1000 failures
        bank["failures"] = bank["failures"][-1000:]
        bank["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Save
        self.reasoning_bank_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.reasoning_bank_file, 'w') as f:
            json.dump(bank, f, indent=2)
    
    def get_failure(self, failure_id: str) -> Optional[FailureRecord]:
        """Retrieve a specific failure."""
        return self.failures.get(failure_id)
    
    def get_failures_by_agent(self, agent_name: str) -> list:
        """Get all failures for a specific agent."""
        return [f for f in self.failures.values() if f.agent_name == agent_name]
    
    def get_failures_by_category(self, category: FailureCategory) -> list:
        """Get all failures of a specific category."""
        return [f for f in self.failures.values() if f.category == category.value]
    
    def get_unresolved_failures(self) -> list:
        """Get all unresolved failures."""
        return [f for f in self.failures.values() if not f.resolved]
    
    def mark_resolved(self, failure_id: str, resolution_notes: str):
        """Mark a failure as resolved."""
        if failure_id in self.failures:
            self.failures[failure_id].resolved = True
            self.failures[failure_id].resolution_notes = resolution_notes
            self._save_failures()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get failure statistics."""
        total = len(self.failures)
        if total == 0:
            return {"total": 0}
        
        by_category = {}
        by_agent = {}
        resolved_count = 0
        
        for failure in self.failures.values():
            # By category
            by_category[failure.category] = by_category.get(failure.category, 0) + 1
            
            # By agent
            by_agent[failure.agent_name] = by_agent.get(failure.agent_name, 0) + 1
            
            # Resolved
            if failure.resolved:
                resolved_count += 1
        
        return {
            "total": total,
            "resolved": resolved_count,
            "unresolved": total - resolved_count,
            "by_category": by_category,
            "by_agent": by_agent,
            "resolution_rate": resolved_count / total if total > 0 else 0
        }

# Global instance
_tracker_instance = None

def get_failure_tracker() -> FailureTracker:
    """Get global failure tracker instance."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = FailureTracker()
    return _tracker_instance
