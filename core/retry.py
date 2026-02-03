"""
Retry and exception handling system for SDR automation.
Implements exponential backoff with jitter and persistent retry queue.
"""

import json
import random
import uuid
import functools
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Optional, Type, Tuple, TypeVar, ParamSpec
from enum import Enum

from core.event_log import log_event, EventType


class RetryStatus(Enum):
    """Status of a retry job."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXHAUSTED = "exhausted"
    CANCELLED = "cancelled"


@dataclass
class RetryPolicy:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 3600.0
    exponential_factor: float = 2.0
    jitter_factor: float = 0.1
    
    def calculate_delay(self, retry_count: int) -> float:
        """Calculate delay with exponential backoff and jitter."""
        delay = min(
            self.base_delay * (self.exponential_factor ** retry_count),
            self.max_delay
        )
        jitter = delay * self.jitter_factor * random.uniform(-1, 1)
        return max(0, delay + jitter)


@dataclass
class RetryJob:
    """A job queued for retry."""
    job_id: str
    operation_name: str
    payload: dict[str, Any]
    next_attempt_at: str
    retry_count: int = 0
    last_error: Optional[str] = None
    created_at: str = ""
    status: str = "pending"
    policy_name: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.job_id:
            self.job_id = str(uuid.uuid4())


RETRY_QUEUE_FILE = Path(".hive-mind/retry_queue.jsonl")

EXCEPTION_POLICIES: dict[str, RetryPolicy] = {
    "enrichment_failure": RetryPolicy(
        max_retries=3,
        base_delay=30.0,
        max_delay=300.0,
        exponential_factor=2.0
    ),
    "scraping_blocked": RetryPolicy(
        max_retries=0,
        base_delay=0,
        max_delay=0,
        exponential_factor=1.0
    ),
    "campaign_delivery_failure": RetryPolicy(
        max_retries=5,
        base_delay=60.0,
        max_delay=1800.0,
        exponential_factor=2.0
    ),
    "api_rate_limit": RetryPolicy(
        max_retries=10,
        base_delay=60.0,
        max_delay=3600.0,
        exponential_factor=2.0
    ),
    "default": RetryPolicy(
        max_retries=3,
        base_delay=5.0,
        max_delay=300.0,
        exponential_factor=2.0
    )
}


def get_policy(policy_name: str) -> RetryPolicy:
    """Get a retry policy by name, falling back to default."""
    return EXCEPTION_POLICIES.get(policy_name, EXCEPTION_POLICIES["default"])


def write_retry_job(job: RetryJob) -> None:
    """Append a retry job to the queue file."""
    RETRY_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RETRY_QUEUE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(job)) + "\n")


def read_retry_queue() -> list[RetryJob]:
    """Read all pending retry jobs from the queue."""
    if not RETRY_QUEUE_FILE.exists():
        return []
    
    jobs = []
    with open(RETRY_QUEUE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data = json.loads(line)
                jobs.append(RetryJob(**data))
    return jobs


def update_retry_queue(jobs: list[RetryJob]) -> None:
    """Rewrite the entire retry queue (used after processing)."""
    RETRY_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RETRY_QUEUE_FILE, "w", encoding="utf-8") as f:
        for job in jobs:
            f.write(json.dumps(asdict(job)) + "\n")


def schedule_retry(
    operation_name: str,
    payload: dict[str, Any],
    error: Exception,
    retry_count: int = 0,
    policy_name: str = "default",
    metadata: Optional[dict[str, Any]] = None
) -> Optional[RetryJob]:
    """
    Schedule a retry for a failed operation.
    
    Returns the created RetryJob, or None if retries are exhausted.
    """
    policy = get_policy(policy_name)
    
    if retry_count >= policy.max_retries:
        log_event(
            EventType.RETRY_SCHEDULED,
            {
                "operation": operation_name,
                "status": "exhausted",
                "retry_count": retry_count,
                "error": str(error),
                "policy": policy_name
            },
            metadata
        )
        return None
    
    delay = policy.calculate_delay(retry_count)
    next_attempt = datetime.now(timezone.utc) + timedelta(seconds=delay)
    
    job = RetryJob(
        job_id=str(uuid.uuid4()),
        operation_name=operation_name,
        payload=payload,
        next_attempt_at=next_attempt.isoformat(),
        retry_count=retry_count + 1,
        last_error=str(error),
        status=RetryStatus.PENDING.value,
        policy_name=policy_name,
        metadata=metadata or {}
    )
    
    write_retry_job(job)
    
    log_event(
        EventType.RETRY_SCHEDULED,
        {
            "job_id": job.job_id,
            "operation": operation_name,
            "status": "scheduled",
            "retry_count": job.retry_count,
            "next_attempt_at": job.next_attempt_at,
            "delay_seconds": delay,
            "error": str(error),
            "policy": policy_name
        },
        metadata
    )
    
    return job


P = ParamSpec("P")
T = TypeVar("T")


def retry(
    operation_name: str,
    policy_name: str = "default",
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
    on_exhausted: Optional[Callable[[Exception, int], None]] = None
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator for adding retry logic to a function.
    
    Args:
        operation_name: Name of the operation for logging
        policy_name: Name of the retry policy to use
        retryable_exceptions: Tuple of exception types that should trigger retry
        on_retry: Callback when a retry is scheduled
        on_exhausted: Callback when retries are exhausted
    
    Returns:
        Decorated function with retry behavior
    """
    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            policy = get_policy(policy_name)
            last_error: Optional[Exception] = None
            
            for attempt in range(policy.max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except retryable_exceptions as e:
                    last_error = e
                    
                    if attempt < policy.max_retries:
                        delay = policy.calculate_delay(attempt)
                        
                        log_event(
                            EventType.RETRY_SCHEDULED,
                            {
                                "operation": operation_name,
                                "status": "retry_inline",
                                "attempt": attempt + 1,
                                "max_retries": policy.max_retries,
                                "delay_seconds": delay,
                                "error": str(e),
                                "policy": policy_name
                            }
                        )
                        
                        if on_retry:
                            on_retry(e, attempt + 1)
                        
                        import time
                        time.sleep(delay)
                    else:
                        log_event(
                            EventType.RETRY_SCHEDULED,
                            {
                                "operation": operation_name,
                                "status": "exhausted",
                                "attempts": attempt + 1,
                                "error": str(e),
                                "policy": policy_name
                            }
                        )
                        
                        if on_exhausted:
                            on_exhausted(e, attempt + 1)
                        
                        raise
            
            raise last_error
        
        return wrapper
    return decorator


def with_retry_queue(
    operation_name: str,
    payload: dict[str, Any],
    fn: Callable[[], T],
    policy_name: str = "default",
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    metadata: Optional[dict[str, Any]] = None
) -> Tuple[Optional[T], Optional[RetryJob]]:
    """
    Execute a function and queue for retry on failure.
    
    This is for async/background retry where we don't want to block.
    
    Args:
        operation_name: Name of the operation
        payload: Data needed to retry the operation later
        fn: The function to execute
        policy_name: Name of the retry policy
        retryable_exceptions: Exceptions that should trigger retry
        metadata: Additional context for logging
    
    Returns:
        Tuple of (result or None, retry_job or None)
    """
    try:
        result = fn()
        return (result, None)
    except retryable_exceptions as e:
        job = schedule_retry(
            operation_name=operation_name,
            payload=payload,
            error=e,
            retry_count=0,
            policy_name=policy_name,
            metadata=metadata
        )
        return (None, job)
