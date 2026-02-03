#!/usr/bin/env python3
"""
Fail-Safe Manager
=================
Implements circuit breaker, graceful degradation, and retry strategies
for robust system operation.

Usage:
    from execution.fail_safe_manager import CircuitBreaker, GracefulDegradation, RetryStrategy
"""

import os
import sys
import json
import time
import random
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Any, Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console

console = Console()


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitOpenError(Exception):
    """Raised when circuit is open and calls are blocked."""
    pass


class MaxRetriesExceeded(Exception):
    """Raised when max retries are exhausted."""
    pass


class RetryableError(Exception):
    """Errors that should trigger a retry."""
    pass


class NonRetryableError(Exception):
    """Errors that should NOT be retried."""
    pass


@dataclass
class CircuitBreakerState:
    """Persistent state for circuit breaker."""
    name: str
    state: str
    failure_count: int
    success_count: int
    last_failure_time: Optional[str]
    last_success_time: Optional[str]
    total_calls: int
    total_failures: int


class CircuitBreaker:
    """
    Prevents cascading failures by stopping calls to failing services.
    
    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Service failing, calls blocked for recovery_timeout
    - HALF_OPEN: Testing if service has recovered
    
    Usage:
        breaker = CircuitBreaker("linkedin_api", failure_threshold=5)
        
        try:
            result = breaker.call(some_api_function, arg1, arg2)
        except CircuitOpenError:
            # Handle service unavailable
            use_fallback()
    """
    
    _instances: Dict[str, 'CircuitBreaker'] = {}
    _lock = threading.Lock()
    
    def __new__(cls, name: str, **kwargs):
        """Singleton per circuit name."""
        with cls._lock:
            if name not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[name] = instance
            return cls._instances[name]
    
    def __init__(self, 
                 name: str,
                 failure_threshold: int = 5,
                 success_threshold: int = 2,
                 recovery_timeout: int = 60):
        
        if hasattr(self, '_initialized'):
            return
        
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.recovery_timeout = recovery_timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
        
        # Metrics
        self.total_calls = 0
        self.total_failures = 0
        
        self._lock = threading.Lock()
        self._initialized = True
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through the circuit breaker.
        
        Raises:
            CircuitOpenError: If circuit is open
        """
        with self._lock:
            self.total_calls += 1
            
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    console.print(f"[yellow]Circuit '{self.name}' entering HALF_OPEN state[/yellow]")
                else:
                    raise CircuitOpenError(
                        f"Circuit '{self.name}' is OPEN. "
                        f"Retry after {self._time_until_reset():.0f}s"
                    )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            raise
    
    def _on_success(self):
        """Handle successful call."""
        with self._lock:
            self.last_success_time = datetime.utcnow()
            
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    console.print(f"[green]Circuit '{self.name}' recovered - CLOSED[/green]")
            else:
                self.failure_count = 0
    
    def _on_failure(self, error: Exception):
        """Handle failed call."""
        with self._lock:
            self.failure_count += 1
            self.total_failures += 1
            self.last_failure_time = datetime.utcnow()
            
            if self.state == CircuitState.HALF_OPEN:
                # Failed during recovery test
                self.state = CircuitState.OPEN
                self.success_count = 0
                console.print(f"[red]Circuit '{self.name}' failed recovery test - OPEN[/red]")
            
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                console.print(f"[red]Circuit '{self.name}' opened after {self.failure_count} failures[/red]")
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        
        elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout
    
    def _time_until_reset(self) -> float:
        """Get seconds until reset attempt."""
        if self.last_failure_time is None:
            return 0
        
        elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return max(0, self.recovery_timeout - elapsed)
    
    def get_state(self) -> CircuitBreakerState:
        """Get current state for monitoring."""
        return CircuitBreakerState(
            name=self.name,
            state=self.state.value,
            failure_count=self.failure_count,
            success_count=self.success_count,
            last_failure_time=self.last_failure_time.isoformat() if self.last_failure_time else None,
            last_success_time=self.last_success_time.isoformat() if self.last_success_time else None,
            total_calls=self.total_calls,
            total_failures=self.total_failures
        )
    
    def reset(self):
        """Manually reset the circuit breaker."""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            console.print(f"[green]Circuit '{self.name}' manually reset[/green]")


class GracefulDegradation:
    """
    Maintains system operation with reduced functionality when components fail.
    
    Degradation Levels:
    0 - Full operation
    1 - Reduced enrichment (use cached data)
    2 - Scraping only (no enrichment)
    3 - Read only (serve cached data)
    4 - Maintenance mode (queue only)
    """
    
    DEGRADATION_LEVELS = {
        0: "FULL_OPERATION",
        1: "REDUCED_ENRICHMENT",
        2: "SCRAPING_ONLY",
        3: "READ_ONLY",
        4: "MAINTENANCE"
    }
    
    OPERATIONS_BY_LEVEL = {
        0: ["scrape", "enrich", "segment", "campaign", "send", "sync"],
        1: ["scrape", "segment_cached", "campaign", "send", "sync"],
        2: ["scrape", "queue_for_enrichment"],
        3: ["read_cached", "queue_all"],
        4: ["queue_only", "emergency_read"]
    }
    
    COMPONENT_TO_LEVEL = {
        "clay_api": 1,
        "rb2b_api": 1,
        "exa_api": 1,
        "linkedin_session": 2,
        "ghl_api": 3,
        "instantly_api": 3,
        "database": 4,
        "file_system": 4
    }
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self.current_level = 0
        self.component_status: Dict[str, Dict] = {}
        self.level_history: List[Dict] = []
        self._initialized = True
    
    def report_component_failure(self, component: str, error: str = None):
        """Report a component failure."""
        
        self.component_status[component] = {
            "healthy": False,
            "error": error,
            "failed_at": datetime.utcnow().isoformat()
        }
        
        new_level = self.COMPONENT_TO_LEVEL.get(component, 0)
        
        if new_level > self.current_level:
            old_level = self.current_level
            self.current_level = new_level
            
            self.level_history.append({
                "from_level": old_level,
                "to_level": new_level,
                "reason": f"{component} failure",
                "timestamp": datetime.utcnow().isoformat()
            })
            
            console.print(f"[yellow]Degraded to {self.DEGRADATION_LEVELS[new_level]}[/yellow]")
    
    def report_component_recovery(self, component: str):
        """Report a component recovery."""
        
        if component in self.component_status:
            self.component_status[component] = {
                "healthy": True,
                "recovered_at": datetime.utcnow().isoformat()
            }
        
        # Recalculate level based on all failures
        max_level = 0
        for comp, status in self.component_status.items():
            if not status.get("healthy", True):
                comp_level = self.COMPONENT_TO_LEVEL.get(comp, 0)
                max_level = max(max_level, comp_level)
        
        if max_level < self.current_level:
            old_level = self.current_level
            self.current_level = max_level
            
            console.print(f"[green]Recovered to {self.DEGRADATION_LEVELS[max_level]}[/green]")
    
    def is_operation_available(self, operation: str) -> bool:
        """Check if an operation is available at current degradation level."""
        available = self.OPERATIONS_BY_LEVEL.get(self.current_level, [])
        return operation in available
    
    def get_available_operations(self) -> List[str]:
        """Get list of available operations."""
        return self.OPERATIONS_BY_LEVEL.get(self.current_level, [])
    
    def get_status(self) -> Dict:
        """Get current degradation status."""
        return {
            "level": self.current_level,
            "level_name": self.DEGRADATION_LEVELS[self.current_level],
            "available_operations": self.get_available_operations(),
            "component_status": self.component_status,
            "history": self.level_history[-10:]
        }


class RetryStrategy:
    """
    Intelligent retry mechanism with exponential backoff and jitter.
    
    Usage:
        retry = RetryStrategy(max_retries=5)
        result = retry.execute(some_function, arg1, arg2)
    """
    
    def __init__(self,
                 max_retries: int = 5,
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 exponential_base: float = 2.0,
                 jitter_factor: float = 0.25):
        
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter_factor = jitter_factor
        
        # Metrics
        self.total_attempts = 0
        self.total_retries = 0
        self.total_successes = 0
    
    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with retry logic."""
        
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            self.total_attempts += 1
            
            try:
                result = func(*args, **kwargs)
                self.total_successes += 1
                return result
                
            except NonRetryableError:
                # Don't retry these
                raise
                
            except Exception as e:
                last_exception = e
                
                if attempt < self.max_retries:
                    self.total_retries += 1
                    delay = self._calculate_delay(attempt)
                    
                    console.print(
                        f"[yellow]Retry {attempt + 1}/{self.max_retries} "
                        f"for {func.__name__} in {delay:.1f}s: {str(e)[:50]}[/yellow]"
                    )
                    
                    time.sleep(delay)
        
        raise MaxRetriesExceeded(
            f"Failed after {self.max_retries} retries: {last_exception}"
        )
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter."""
        
        # Exponential backoff
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        
        # Add jitter to prevent thundering herd
        jitter_range = delay * self.jitter_factor
        jitter = random.uniform(-jitter_range, jitter_range)
        delay += jitter
        
        return max(0, delay)
    
    def get_stats(self) -> Dict:
        """Get retry statistics."""
        return {
            "total_attempts": self.total_attempts,
            "total_retries": self.total_retries,
            "total_successes": self.total_successes,
            "retry_rate": self.total_retries / max(1, self.total_attempts),
            "success_rate": self.total_successes / max(1, self.total_attempts - self.total_retries)
        }


class HealthMonitor:
    """
    Monitors system health and component availability.
    """
    
    def __init__(self):
        self.checks: Dict[str, Callable] = {}
        self.last_results: Dict[str, Dict] = {}
        self.check_interval = 60  # seconds
    
    def register_check(self, name: str, check_func: Callable[[], bool]):
        """Register a health check function."""
        self.checks[name] = check_func
    
    def run_checks(self) -> Dict[str, Dict]:
        """Run all health checks."""
        
        results = {}
        
        for name, check_func in self.checks.items():
            try:
                start = time.time()
                healthy = check_func()
                duration = time.time() - start
                
                results[name] = {
                    "healthy": healthy,
                    "latency_ms": duration * 1000,
                    "checked_at": datetime.utcnow().isoformat()
                }
            except Exception as e:
                results[name] = {
                    "healthy": False,
                    "error": str(e),
                    "checked_at": datetime.utcnow().isoformat()
                }
        
        self.last_results = results
        return results
    
    def is_healthy(self, component: str = None) -> bool:
        """Check if system or specific component is healthy."""
        
        if not self.last_results:
            self.run_checks()
        
        if component:
            return self.last_results.get(component, {}).get("healthy", False)
        
        return all(r.get("healthy", False) for r in self.last_results.values())


# Convenience function to save fail-safe state
def save_fail_safe_state(output_dir: Path = None):
    """Save current fail-safe state to disk."""
    
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / ".hive-mind"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    state = {
        "timestamp": datetime.utcnow().isoformat(),
        "circuit_breakers": {
            name: asdict(cb.get_state())
            for name, cb in CircuitBreaker._instances.items()
        },
        "degradation": GracefulDegradation().get_status()
    }
    
    with open(output_dir / "fail_safe_state.json", "w") as f:
        json.dump(state, f, indent=2)


if __name__ == "__main__":
    # Demo usage
    console.print("[bold]Fail-Safe Manager Demo[/bold]")
    
    # Create circuit breaker
    breaker = CircuitBreaker("test_service", failure_threshold=3, recovery_timeout=10)
    
    # Simulate failures
    def failing_function():
        raise Exception("Simulated failure")
    
    for i in range(5):
        try:
            breaker.call(failing_function)
        except CircuitOpenError as e:
            console.print(f"[red]Call blocked: {e}[/red]")
        except Exception as e:
            console.print(f"[yellow]Call failed: {e}[/yellow]")
    
    console.print(f"\nCircuit state: {asdict(breaker.get_state())}")
