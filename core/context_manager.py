"""
Context Manager with Frequent Intentional Compaction (FIC)
===========================================================
Prevents context overflow and the "Dumb Zone" problem through proactive
token budget management and priority-based context retention.

Key Features:
- Token budget management with warning/critical thresholds
- Priority-based retention (high-value context survives compaction)
- TTL-based expiration for ephemeral context
- Session state persistence
- Integration with existing context.py patterns
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from enum import IntEnum
import os
import json
import logging
import tempfile
import threading
import uuid
import time

logger = logging.getLogger(__name__)

try:
    import redis
except Exception:  # pragma: no cover - optional dependency in some environments
    redis = None


# Priority levels for context items
class Priority(IntEnum):
    """Priority levels for context retention during compaction."""
    EPHEMERAL = 10   # Temporary, first to be dropped
    LOW = 25         # Nice to have
    MEDIUM = 50      # Standard importance
    HIGH = 75        # Important, keep if possible
    CRITICAL = 100   # Never drop automatically


class BudgetStatus:
    """Budget status constants."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ContextBudget:
    """Token budget configuration and tracking."""
    max_tokens: int = 128000
    current_tokens: int = 0
    warning_threshold: float = 0.40   # 40% - start monitoring
    critical_threshold: float = 0.60  # 60% - trigger compaction
    
    @property
    def utilization(self) -> float:
        """Current utilization ratio (0.0 to 1.0+)."""
        if self.max_tokens == 0:
            return 0.0
        return self.current_tokens / self.max_tokens
    
    @property
    def utilization_percent(self) -> float:
        """Current utilization as percentage."""
        return self.utilization * 100
    
    @property
    def remaining_tokens(self) -> int:
        """Tokens remaining before max."""
        return max(0, self.max_tokens - self.current_tokens)
    
    @property
    def tokens_until_warning(self) -> int:
        """Tokens remaining before warning threshold."""
        warning_limit = int(self.max_tokens * self.warning_threshold)
        return max(0, warning_limit - self.current_tokens)
    
    @property
    def tokens_until_critical(self) -> int:
        """Tokens remaining before critical threshold."""
        critical_limit = int(self.max_tokens * self.critical_threshold)
        return max(0, critical_limit - self.current_tokens)
    
    def get_status(self) -> str:
        """Get current budget status."""
        if self.utilization >= self.critical_threshold:
            return BudgetStatus.CRITICAL
        elif self.utilization >= self.warning_threshold:
            return BudgetStatus.WARNING
        return BudgetStatus.HEALTHY
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "current_tokens": self.current_tokens,
            "warning_threshold": self.warning_threshold,
            "critical_threshold": self.critical_threshold,
            "utilization": round(self.utilization, 4),
            "status": self.get_status()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextBudget":
        return cls(
            max_tokens=data.get("max_tokens", 128000),
            current_tokens=data.get("current_tokens", 0),
            warning_threshold=data.get("warning_threshold", 0.40),
            critical_threshold=data.get("critical_threshold", 0.60)
        )


@dataclass
class ContextItem:
    """A single context item with priority and lifecycle metadata."""
    id: str
    content: str
    priority: int
    timestamp: float
    token_count: int
    source: str
    ttl_seconds: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """Check if item has exceeded its TTL."""
        if self.ttl_seconds is None:
            return False
        return (time.time() - self.timestamp) > self.ttl_seconds
    
    @property
    def age_seconds(self) -> float:
        """Age of this item in seconds."""
        return time.time() - self.timestamp
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "priority": self.priority,
            "timestamp": self.timestamp,
            "token_count": self.token_count,
            "source": self.source,
            "ttl_seconds": self.ttl_seconds,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextItem":
        return cls(
            id=data["id"],
            content=data["content"],
            priority=data["priority"],
            timestamp=data["timestamp"],
            token_count=data["token_count"],
            source=data["source"],
            ttl_seconds=data.get("ttl_seconds"),
            metadata=data.get("metadata", {})
        )


def count_tokens(text: str) -> int:
    """
    Count tokens in text. Uses tiktoken if available, otherwise word-based estimate.
    
    Tiktoken provides accurate token counts for OpenAI/Anthropic models.
    Falls back to word-based heuristic (~1.3 tokens per word).
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        # Fallback: ~4 chars per token (similar to existing context.py)
        return max(1, len(text) // 4)
    except Exception as e:
        logger.warning(f"Token counting error, using fallback: {e}")
        return max(1, len(text) // 4)


class ContextManager:
    """
    Manages context with Frequent Intentional Compaction (FIC).
    
    Prevents the "Dumb Zone" problem by:
    1. Tracking token usage against budget
    2. Warning at 40% utilization
    3. Auto-compacting at 60% utilization
    4. Priority-based retention during compaction
    5. TTL-based expiration for ephemeral items
    """
    
    DEFAULT_STATE_PATH = Path(".hive-mind/context_state.json")
    
    def __init__(
        self,
        max_tokens: int = 128000,
        warning_threshold: float = 0.40,
        critical_threshold: float = 0.60,
        session_id: Optional[str] = None,
        redis_url: Optional[str] = None,
        redis_prefix: str = "caio:context",
        state_ttl_seconds: int = 3600,
    ):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.budget = ContextBudget(
            max_tokens=max_tokens,
            warning_threshold=warning_threshold,
            critical_threshold=critical_threshold
        )
        self.items: Dict[str, ContextItem] = {}
        self.compaction_count = 0
        self.items_added = 0
        self.items_removed = 0
        self.created_at = time.time()
        self._state_lock = threading.RLock()
        
        self.redis_prefix = os.getenv("CONTEXT_REDIS_PREFIX", redis_prefix)
        ttl_value = os.getenv("CONTEXT_STATE_TTL_SECONDS", str(state_ttl_seconds))
        try:
            self.state_ttl_seconds = int(ttl_value)
        except ValueError:
            logger.warning(
                "Invalid CONTEXT_STATE_TTL_SECONDS='%s', using default %s",
                ttl_value,
                state_ttl_seconds,
            )
            self.state_ttl_seconds = state_ttl_seconds
        self._redis = None
        self._use_redis = False
        configured_redis_url = os.getenv("REDIS_URL") if redis_url is None else redis_url
        self._init_redis(configured_redis_url)
        
        logger.info(
            f"ContextManager initialized: session={self.session_id}, "
            f"max_tokens={max_tokens}, warn={warning_threshold:.0%}, "
            f"critical={critical_threshold:.0%}"
        )
    
    def _init_redis(self, redis_url: Optional[str]) -> None:
        if not redis_url or redis is None:
            return
        try:
            self._redis = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._redis.ping()
            self._use_redis = True
            logger.info("ContextManager configured with Redis backend")
        except Exception as exc:
            self._use_redis = False
            self._redis = None
            logger.warning("ContextManager Redis unavailable (%s), using file fallback.", exc)
    
    def _redis_key(self) -> str:
        return f"{self.redis_prefix}:{self.session_id}"
    
    def _serialize_state(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "saved_at": time.time(),
            "budget": self.budget.to_dict(),
            "items": {k: v.to_dict() for k, v in self.items.items()},
            "stats": {
                "compaction_count": self.compaction_count,
                "items_added": self.items_added,
                "items_removed": self.items_removed
            }
        }
    
    def _apply_state(self, state: Dict[str, Any]) -> None:
        self.session_id = state.get("session_id", self.session_id)
        self.created_at = state.get("created_at", self.created_at)
        self.budget = ContextBudget.from_dict(state.get("budget", {}))
        
        self.items = {
            k: ContextItem.from_dict(v)
            for k, v in state.get("items", {}).items()
        }
        
        stats = state.get("stats", {})
        self.compaction_count = stats.get("compaction_count", 0)
        self.items_added = stats.get("items_added", 0)
        self.items_removed = stats.get("items_removed", 0)
        
        self.budget.current_tokens = sum(item.token_count for item in self.items.values())
    
    def add_context(
        self,
        content: str,
        priority: int = Priority.MEDIUM,
        source: str = "unknown",
        ttl_seconds: Optional[float] = None,
        item_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ContextItem:
        """
        Add context with auto-token counting.
        
        Args:
            content: The context content to add
            priority: Priority level (use Priority enum)
            source: Source identifier for debugging
            ttl_seconds: Optional time-to-live in seconds
            item_id: Optional custom ID (auto-generated if not provided)
            metadata: Optional metadata dict
            
        Returns:
            The created ContextItem
        """
        token_count = count_tokens(content)
        item_id = item_id or f"{source}_{uuid.uuid4().hex[:8]}"
        
        item = ContextItem(
            id=item_id,
            content=content,
            priority=priority,
            timestamp=time.time(),
            token_count=token_count,
            source=source,
            ttl_seconds=ttl_seconds,
            metadata=metadata or {}
        )
        
        self.items[item.id] = item
        self.budget.current_tokens += token_count
        self.items_added += 1
        
        logger.debug(
            f"Added context: id={item.id}, tokens={token_count}, "
            f"priority={priority}, source={source}"
        )
        
        # Check if compaction needed
        status = self.check_budget()
        if status == BudgetStatus.CRITICAL:
            logger.warning(
                f"Context budget CRITICAL ({self.budget.utilization_percent:.1f}%), "
                "triggering auto-compaction"
            )
            self.compact()
        elif status == BudgetStatus.WARNING:
            logger.info(
                f"Context budget WARNING ({self.budget.utilization_percent:.1f}%)"
            )
        
        return item
    
    def get_context(
        self,
        max_tokens: Optional[int] = None,
        min_priority: int = Priority.EPHEMERAL,
        sources: Optional[List[str]] = None
    ) -> str:
        """
        Retrieve context within token budget.
        
        Items are returned in priority order (highest first), then by recency.
        
        Args:
            max_tokens: Maximum tokens to return (defaults to remaining budget)
            min_priority: Minimum priority level to include
            sources: Optional list of sources to filter by
            
        Returns:
            Combined context string within budget
        """
        if max_tokens is None:
            max_tokens = self.budget.remaining_tokens
        
        # Filter and sort items
        eligible = [
            item for item in self.items.values()
            if item.priority >= min_priority
            and not item.is_expired
            and (sources is None or item.source in sources)
        ]
        
        # Sort by priority (desc), then timestamp (desc for recency)
        eligible.sort(key=lambda x: (x.priority, x.timestamp), reverse=True)
        
        # Collect within budget
        result_parts = []
        tokens_used = 0
        
        for item in eligible:
            if tokens_used + item.token_count > max_tokens:
                continue
            result_parts.append(item.content)
            tokens_used += item.token_count
        
        logger.debug(
            f"Retrieved context: {len(result_parts)} items, {tokens_used} tokens"
        )
        
        return "\n\n".join(result_parts)
    
    def compact(self, target_utilization: Optional[float] = None) -> Dict[str, Any]:
        """
        Remove low-priority and expired items to reduce token usage.
        
        Strategy:
        1. Remove all expired items first
        2. Remove items by priority (lowest first) until under target
        
        Args:
            target_utilization: Target utilization ratio (default: warning_threshold - 0.1)
            
        Returns:
            Compaction report with items removed and tokens freed
        """
        if target_utilization is None:
            target_utilization = max(0.1, self.budget.warning_threshold - 0.1)
        
        target_tokens = int(self.budget.max_tokens * target_utilization)
        initial_tokens = self.budget.current_tokens
        initial_items = len(self.items)
        removed_items = []
        
        logger.info(
            f"Compaction started: {initial_tokens} tokens -> target {target_tokens}"
        )
        
        # Phase 1: Remove expired items
        expired_ids = [
            item_id for item_id, item in self.items.items()
            if item.is_expired
        ]
        for item_id in expired_ids:
            item = self.items.pop(item_id)
            self.budget.current_tokens -= item.token_count
            self.items_removed += 1
            removed_items.append({
                "id": item.id,
                "reason": "expired",
                "priority": item.priority,
                "tokens": item.token_count
            })
        
        # Phase 2: Remove by priority if still over target
        if self.budget.current_tokens > target_tokens:
            # Sort by priority (lowest first), then age (oldest first)
            by_priority = sorted(
                self.items.values(),
                key=lambda x: (x.priority, -x.age_seconds)
            )
            
            for item in by_priority:
                if self.budget.current_tokens <= target_tokens:
                    break
                if item.priority >= Priority.CRITICAL:
                    continue  # Never auto-remove critical items
                
                self.items.pop(item.id)
                self.budget.current_tokens -= item.token_count
                self.items_removed += 1
                removed_items.append({
                    "id": item.id,
                    "reason": "low_priority",
                    "priority": item.priority,
                    "tokens": item.token_count
                })
        
        self.compaction_count += 1
        tokens_freed = initial_tokens - self.budget.current_tokens
        
        report = {
            "compaction_number": self.compaction_count,
            "initial_tokens": initial_tokens,
            "final_tokens": self.budget.current_tokens,
            "tokens_freed": tokens_freed,
            "initial_items": initial_items,
            "final_items": len(self.items),
            "items_removed": len(removed_items),
            "removed_items": removed_items,
            "new_utilization": round(self.budget.utilization, 4),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(
            f"Compaction complete: freed {tokens_freed} tokens, "
            f"removed {len(removed_items)} items, "
            f"utilization now {self.budget.utilization_percent:.1f}%"
        )
        
        return report
    
    def check_budget(self) -> str:
        """
        Check current budget status.
        
        Returns:
            One of: "healthy", "warning", "critical"
        """
        return self.budget.get_status()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get detailed usage statistics.
        
        Returns:
            Dictionary with comprehensive stats
        """
        priority_breakdown = {}
        source_breakdown = {}
        
        for item in self.items.values():
            # By priority
            p_name = Priority(item.priority).name if item.priority in [p.value for p in Priority] else str(item.priority)
            priority_breakdown[p_name] = priority_breakdown.get(p_name, 0) + item.token_count
            
            # By source
            source_breakdown[item.source] = source_breakdown.get(item.source, 0) + item.token_count
        
        expired_count = sum(1 for item in self.items.values() if item.is_expired)
        
        return {
            "session_id": self.session_id,
            "status": self.check_budget(),
            "budget": self.budget.to_dict(),
            "items_count": len(self.items),
            "items_expired": expired_count,
            "items_added_total": self.items_added,
            "items_removed_total": self.items_removed,
            "compaction_count": self.compaction_count,
            "priority_breakdown": priority_breakdown,
            "source_breakdown": source_breakdown,
            "session_age_seconds": round(time.time() - self.created_at, 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def remove_item(self, item_id: str) -> bool:
        """
        Remove a specific item by ID.
        
        Returns:
            True if removed, False if not found
        """
        if item_id in self.items:
            item = self.items.pop(item_id)
            self.budget.current_tokens -= item.token_count
            self.items_removed += 1
            logger.debug(f"Removed item: {item_id}")
            return True
        return False
    
    def clear(self):
        """Clear all context items."""
        count = len(self.items)
        self.items.clear()
        self.budget.current_tokens = 0
        self.items_removed += count
        logger.info(f"Cleared all context: {count} items removed")
    
    def save_state(self, path: Optional[Path] = None) -> Path:
        """
        Persist context state to JSON file.
        
        Args:
            path: Optional custom path (default: .hive-mind/context_state.json)
            
        Returns:
            Path where state was saved
        """
        if path is None:
            path = self.DEFAULT_STATE_PATH
        
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        state = self._serialize_state()
        
        if self._use_redis and self._redis:
            try:
                self._redis.setex(
                    self._redis_key(),
                    self.state_ttl_seconds,
                    json.dumps(state),
                )
            except Exception as exc:
                logger.warning("Failed to persist context state to Redis: %s", exc)
                self._use_redis = False
                self._redis = None
        
        with self._state_lock:
            fd = None
            temp_path = None
            try:
                fd, temp_path = tempfile.mkstemp(
                    suffix=".json",
                    prefix="context_state_",
                    dir=str(path.parent),
                )
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    fd = None
                    json.dump(state, f, indent=2)
                os.replace(temp_path, path)
                temp_path = None
            finally:
                if fd is not None:
                    os.close(fd)
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
        
        logger.info("Context state saved to %s", path)
        return path
    
    def restore_state(self, path: Optional[Path] = None) -> bool:
        """
        Restore context state from JSON file.
        
        Args:
            path: Optional custom path (default: .hive-mind/context_state.json)
            
        Returns:
            True if restored successfully, False otherwise
        """
        if path is None:
            path = self.DEFAULT_STATE_PATH
        
        path = Path(path)
        
        if self._use_redis and self._redis:
            try:
                raw = self._redis.get(self._redis_key())
                if raw:
                    state = json.loads(raw)
                    self._apply_state(state)
                    logger.info(
                        "Context state restored from Redis key %s: %s items, %s tokens",
                        self._redis_key(),
                        len(self.items),
                        self.budget.current_tokens,
                    )
                    return True
            except Exception as exc:
                logger.warning("Failed to restore context state from Redis: %s", exc)
                self._use_redis = False
                self._redis = None
        
        if not path.exists():
            logger.warning(f"State file not found: {path}")
            return False
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            self._apply_state(state)
            
            logger.info(
                f"Context state restored from {path}: "
                f"{len(self.items)} items, {self.budget.current_tokens} tokens"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore state from {path}: {e}")
            return False
    
    def get_item(self, item_id: str) -> Optional[ContextItem]:
        """Get a specific item by ID."""
        return self.items.get(item_id)
    
    def update_item_priority(self, item_id: str, new_priority: int) -> bool:
        """Update the priority of an existing item."""
        if item_id in self.items:
            self.items[item_id].priority = new_priority
            return True
        return False


def main():
    """Test demonstration of the Context Manager."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    print("=" * 60)
    print("Context Manager - FIC System Demo")
    print("=" * 60)
    
    # Create manager with small budget for demo
    manager = ContextManager(
        max_tokens=1000,  # Small for demo
        warning_threshold=0.40,
        critical_threshold=0.60
    )
    
    print(f"\n[1] Initial state:")
    print(f"    Status: {manager.check_budget()}")
    print(f"    Utilization: {manager.budget.utilization_percent:.1f}%")
    
    # Add some context at different priorities
    print("\n[2] Adding context items...")
    
    manager.add_context(
        "System configuration and critical settings for agent behavior.",
        priority=Priority.CRITICAL,
        source="system"
    )
    
    manager.add_context(
        "User preferences and personalization data.",
        priority=Priority.HIGH,
        source="user"
    )
    
    manager.add_context(
        "Recent conversation history for context.",
        priority=Priority.MEDIUM,
        source="conversation"
    )
    
    manager.add_context(
        "Temporary calculation results.",
        priority=Priority.LOW,
        source="temp",
        ttl_seconds=60  # Expires in 60 seconds
    )
    
    manager.add_context(
        "Debug trace information for this request.",
        priority=Priority.EPHEMERAL,
        source="debug"
    )
    
    print(f"\n[3] After adding items:")
    stats = manager.get_stats()
    print(f"    Items: {stats['items_count']}")
    print(f"    Tokens: {stats['budget']['current_tokens']}")
    print(f"    Status: {stats['status']}")
    print(f"    Utilization: {stats['budget']['utilization'] * 100:.1f}%")
    print(f"    Priority breakdown: {stats['priority_breakdown']}")
    
    # Add more to trigger compaction
    print("\n[4] Adding more context to trigger compaction...")
    
    for i in range(5):
        manager.add_context(
            f"Additional context chunk #{i+1} with medium-length content to fill budget.",
            priority=Priority.LOW,
            source="bulk"
        )
    
    print(f"\n[5] After bulk add:")
    stats = manager.get_stats()
    print(f"    Items: {stats['items_count']}")
    print(f"    Tokens: {stats['budget']['current_tokens']}")
    print(f"    Status: {stats['status']}")
    print(f"    Compactions triggered: {stats['compaction_count']}")
    
    # Get context within budget
    print("\n[6] Retrieving context (max 200 tokens):")
    context = manager.get_context(max_tokens=200)
    print(f"    Retrieved: {len(context)} chars")
    
    # Manual compaction
    print("\n[7] Manual compaction to 20%:")
    report = manager.compact(target_utilization=0.20)
    print(f"    Tokens freed: {report['tokens_freed']}")
    print(f"    Items removed: {report['items_removed']}")
    print(f"    New utilization: {report['new_utilization'] * 100:.1f}%")
    
    # Save and restore state
    print("\n[8] Testing state persistence...")
    save_path = manager.save_state()
    print(f"    Saved to: {save_path}")
    
    # Create new manager and restore
    manager2 = ContextManager()
    restored = manager2.restore_state(save_path)
    print(f"    Restored: {restored}")
    print(f"    Restored items: {len(manager2.items)}")
    print(f"    Restored tokens: {manager2.budget.current_tokens}")
    
    # Final stats
    print("\n[9] Final statistics:")
    final_stats = manager.get_stats()
    for key, value in final_stats.items():
        if key != "priority_breakdown" and key != "source_breakdown":
            print(f"    {key}: {value}")
    
    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
