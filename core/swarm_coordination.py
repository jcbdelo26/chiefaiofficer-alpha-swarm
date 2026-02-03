#!/usr/bin/env python3
"""
Swarm Coordination Module
=========================
Day 8 Implementation: Heartbeats, Auto-Restart, Worker Concurrency

Features:
- Heartbeat monitoring with configurable intervals
- Auto-restart on agent/worker failure
- Dynamic worker concurrency scaling
- Stuck task detection and recovery
- Safe shutdown procedure
- Hook system (pre-task, post-task, on-error)
- Hive-mind memory integration

Architecture:
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SWARM COORDINATION ENGINE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    HEARTBEAT MONITOR                                  │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐             │   │
│  │  │ Agent 1  │  │ Agent 2  │  │ Agent N  │  │ Worker   │             │   │
│  │  │ ❤️ 30s   │  │ ❤️ 30s   │  │ ❤️ 30s   │  │ ❤️ 15s   │             │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    WORKER POOL                                        │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐             │   │
│  │  │Worker 0  │  │Worker 1  │  │Worker 2  │  │Worker 3  │ (scalable) │   │
│  │  │ ACTIVE   │  │ ACTIVE   │  │ IDLE     │  │ IDLE     │             │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    RECOVERY MANAGER                                   │   │
│  │  • Auto-restart failed agents    • Requeue stuck tasks               │   │
│  │  • Scale workers on demand       • Safe shutdown                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    HOOK SYSTEM                                        │   │
│  │  PRE_TASK → TASK_EXECUTION → POST_TASK / ON_ERROR                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Usage:
    from core.swarm_coordination import SwarmCoordinator, WorkerPool
    
    coordinator = SwarmCoordinator()
    await coordinator.start()
    
    # Register hooks
    coordinator.register_hook("pre_task", my_pre_task_handler)
    coordinator.register_hook("post_task", my_post_task_handler)
    
    # Scale workers
    await coordinator.scale_workers(8)
"""

import os
import sys
import json
import asyncio
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Set, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("swarm_coordination")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# ENUMS
# =============================================================================

class AgentStatus(Enum):
    """Agent lifecycle status."""
    IDLE = "idle"
    BUSY = "busy"
    STARTING = "starting"
    STOPPING = "stopping"
    DEAD = "dead"
    RECOVERING = "recovering"


class WorkerStatus(Enum):
    """Worker lifecycle status."""
    IDLE = "idle"
    PROCESSING = "processing"
    WAITING = "waiting"
    DEAD = "dead"


class HookType(Enum):
    """Types of lifecycle hooks."""
    PRE_TASK = "pre_task"
    POST_TASK = "post_task"
    ON_ERROR = "on_error"
    ON_AGENT_START = "on_agent_start"
    ON_AGENT_STOP = "on_agent_stop"
    ON_AGENT_RECOVER = "on_agent_recover"
    ON_WORKER_SCALE = "on_worker_scale"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Heartbeat:
    """Agent heartbeat record."""
    agent_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "alive"
    current_task: Optional[str] = None
    memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    
    @property
    def age_seconds(self) -> float:
        """Get age of heartbeat in seconds."""
        hb_time = datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        return (now - hb_time).total_seconds()


@dataclass
class WorkerState:
    """State of a single worker."""
    worker_id: int
    status: WorkerStatus = WorkerStatus.IDLE
    current_task_id: Optional[str] = None
    task_started_at: Optional[str] = None
    tasks_processed: int = 0
    errors: int = 0
    last_activity: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    @property
    def is_stuck(self) -> bool:
        """Check if worker is stuck on a task."""
        if self.status != WorkerStatus.PROCESSING or not self.task_started_at:
            return False
        started = datetime.fromisoformat(self.task_started_at.replace('Z', '+00:00'))
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        return elapsed > 300  # 5 minute timeout


@dataclass
class CoordinationConfig:
    """Configuration for swarm coordination."""
    # Heartbeat settings
    heartbeat_interval_seconds: int = 30
    heartbeat_timeout_multiplier: int = 3  # Dead after N missed heartbeats
    
    # Worker settings
    min_workers: int = 2
    max_workers: int = 12
    initial_workers: int = 4
    
    # Task settings
    task_timeout_seconds: int = 300  # 5 minutes
    max_task_retries: int = 3
    
    # Recovery settings
    auto_restart: bool = True
    restart_delay_seconds: float = 1.0
    max_restart_attempts: int = 3
    restart_backoff_multiplier: float = 2.0
    
    # Scaling settings
    scale_up_threshold: float = 0.8  # Queue > 80% capacity
    scale_down_threshold: float = 0.2  # Queue < 20% capacity
    scale_check_interval_seconds: int = 60


# =============================================================================
# HOOK REGISTRY
# =============================================================================

class HookRegistry:
    """Registry for lifecycle hooks."""
    
    def __init__(self):
        self._hooks: Dict[HookType, List[Callable]] = defaultdict(list)
    
    def register(self, hook_type: HookType, handler: Callable):
        """Register a hook handler."""
        self._hooks[hook_type].append(handler)
        logger.debug(f"Registered hook: {hook_type.value} -> {handler.__name__}")
    
    def unregister(self, hook_type: HookType, handler: Callable):
        """Unregister a hook handler."""
        if handler in self._hooks[hook_type]:
            self._hooks[hook_type].remove(handler)
    
    async def execute(self, hook_type: HookType, **kwargs) -> List[Any]:
        """Execute all handlers for a hook type."""
        results = []
        for handler in self._hooks[hook_type]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(**kwargs)
                else:
                    result = handler(**kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Hook {hook_type.value} handler {handler.__name__} failed: {e}")
                results.append({"error": str(e)})
        return results
    
    def get_handlers(self, hook_type: HookType) -> List[Callable]:
        """Get all handlers for a hook type."""
        return list(self._hooks[hook_type])


# =============================================================================
# HEARTBEAT MONITOR
# =============================================================================

class HeartbeatMonitor:
    """
    Monitors agent heartbeats and triggers recovery.
    
    Features:
    - Tracks heartbeats from all agents
    - Detects missed heartbeats
    - Triggers recovery procedures
    - Records heartbeat history
    """
    
    def __init__(self, config: CoordinationConfig):
        self.config = config
        self._heartbeats: Dict[str, Heartbeat] = {}
        self._history: Dict[str, List[Heartbeat]] = defaultdict(list)
        self._max_history = 100
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._on_agent_dead: Optional[Callable] = None
    
    def set_dead_callback(self, callback: Callable):
        """Set callback for when agent is detected as dead."""
        self._on_agent_dead = callback
    
    def record_heartbeat(self, agent_id: str, **kwargs) -> Heartbeat:
        """Record a heartbeat from an agent."""
        hb = Heartbeat(
            agent_id=agent_id,
            **kwargs
        )
        self._heartbeats[agent_id] = hb
        
        # Keep history
        self._history[agent_id].append(hb)
        if len(self._history[agent_id]) > self._max_history:
            self._history[agent_id] = self._history[agent_id][-self._max_history:]
        
        return hb
    
    def get_heartbeat(self, agent_id: str) -> Optional[Heartbeat]:
        """Get latest heartbeat for an agent."""
        return self._heartbeats.get(agent_id)
    
    def get_all_heartbeats(self) -> Dict[str, Heartbeat]:
        """Get all current heartbeats."""
        return dict(self._heartbeats)
    
    def is_alive(self, agent_id: str) -> bool:
        """Check if agent is alive based on heartbeat."""
        hb = self._heartbeats.get(agent_id)
        if not hb:
            return False
        
        timeout = self.config.heartbeat_interval_seconds * self.config.heartbeat_timeout_multiplier
        return hb.age_seconds < timeout
    
    def get_dead_agents(self) -> List[str]:
        """Get list of agents that have missed heartbeats."""
        dead = []
        for agent_id in self._heartbeats.keys():
            if not self.is_alive(agent_id):
                dead.append(agent_id)
        return dead
    
    async def start(self):
        """Start heartbeat monitoring."""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Heartbeat monitor started")
    
    async def stop(self):
        """Stop heartbeat monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Heartbeat monitor stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval_seconds)
                
                # Check for dead agents
                dead_agents = self.get_dead_agents()
                for agent_id in dead_agents:
                    hb = self._heartbeats[agent_id]
                    if hb.status != "dead":
                        logger.warning(f"Agent {agent_id} detected as dead (last heartbeat: {hb.age_seconds:.1f}s ago)")
                        hb.status = "dead"
                        
                        # Trigger callback
                        if self._on_agent_dead:
                            if asyncio.iscoroutinefunction(self._on_agent_dead):
                                await self._on_agent_dead(agent_id)
                            else:
                                self._on_agent_dead(agent_id)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat monitor error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics."""
        alive = sum(1 for aid in self._heartbeats if self.is_alive(aid))
        dead = len(self._heartbeats) - alive
        
        return {
            "total_agents": len(self._heartbeats),
            "alive": alive,
            "dead": dead,
            "heartbeat_interval": self.config.heartbeat_interval_seconds,
            "agents": {
                aid: {
                    "status": hb.status,
                    "age_seconds": round(hb.age_seconds, 1),
                    "alive": self.is_alive(aid)
                }
                for aid, hb in self._heartbeats.items()
            }
        }


# =============================================================================
# WORKER POOL
# =============================================================================

class WorkerPool:
    """
    Manages a pool of task workers with auto-scaling.
    
    Features:
    - Dynamic worker scaling
    - Stuck task detection
    - Worker health monitoring
    - Task distribution
    """
    
    def __init__(self, config: CoordinationConfig):
        self.config = config
        self._workers: Dict[int, WorkerState] = {}
        self._worker_tasks: Dict[int, asyncio.Task] = {}
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._next_worker_id = 0
        self._lock = asyncio.Lock()
        
        # Callbacks
        self._task_handler: Optional[Callable] = None
        self._on_error: Optional[Callable] = None
    
    def set_task_handler(self, handler: Callable):
        """Set the function that processes tasks."""
        self._task_handler = handler
    
    def set_error_handler(self, handler: Callable):
        """Set the function called on task error."""
        self._on_error = handler
    
    async def start(self, num_workers: Optional[int] = None):
        """Start the worker pool."""
        if self._running:
            return
        
        self._running = True
        
        # Start initial workers
        target = num_workers or self.config.initial_workers
        for _ in range(target):
            await self._spawn_worker()
        
        logger.info(f"Worker pool started with {len(self._workers)} workers")
    
    async def stop(self):
        """Stop all workers gracefully."""
        self._running = False
        
        # Cancel all worker tasks
        for worker_id, task in list(self._worker_tasks.items()):
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        
        self._workers.clear()
        self._worker_tasks.clear()
        
        logger.info("Worker pool stopped")
    
    async def _spawn_worker(self) -> int:
        """Spawn a new worker."""
        async with self._lock:
            worker_id = self._next_worker_id
            self._next_worker_id += 1
            
            state = WorkerState(worker_id=worker_id)
            self._workers[worker_id] = state
            
            task = asyncio.create_task(self._worker_loop(worker_id))
            self._worker_tasks[worker_id] = task
            
            logger.debug(f"Spawned worker {worker_id}")
            return worker_id
    
    async def _kill_worker(self, worker_id: int):
        """Kill a specific worker."""
        async with self._lock:
            if worker_id in self._worker_tasks:
                self._worker_tasks[worker_id].cancel()
                try:
                    await self._worker_tasks[worker_id]
                except asyncio.CancelledError:
                    pass
                del self._worker_tasks[worker_id]
            
            if worker_id in self._workers:
                del self._workers[worker_id]
            
            logger.debug(f"Killed worker {worker_id}")
    
    async def _worker_loop(self, worker_id: int):
        """Main worker loop."""
        state = self._workers[worker_id]
        
        while self._running:
            try:
                state.status = WorkerStatus.WAITING
                state.current_task_id = None
                
                # Get task with timeout
                try:
                    task_data = await asyncio.wait_for(
                        self._task_queue.get(),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process task
                state.status = WorkerStatus.PROCESSING
                state.current_task_id = task_data.get("task_id", "unknown")
                state.task_started_at = datetime.now(timezone.utc).isoformat()
                state.last_activity = datetime.now(timezone.utc).isoformat()
                
                try:
                    if self._task_handler:
                        if asyncio.iscoroutinefunction(self._task_handler):
                            await self._task_handler(task_data)
                        else:
                            self._task_handler(task_data)
                    
                    state.tasks_processed += 1
                    
                except Exception as e:
                    state.errors += 1
                    logger.error(f"Worker {worker_id} task error: {e}")
                    
                    if self._on_error:
                        try:
                            if asyncio.iscoroutinefunction(self._on_error):
                                await self._on_error(task_data, e)
                            else:
                                self._on_error(task_data, e)
                        except Exception as ee:
                            logger.error(f"Error handler failed: {ee}")
                
                finally:
                    self._task_queue.task_done()
                    state.status = WorkerStatus.IDLE
                    state.current_task_id = None
                    state.task_started_at = None
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} loop error: {e}")
                state.status = WorkerStatus.DEAD
                break
        
        state.status = WorkerStatus.DEAD
    
    async def submit_task(self, task_data: Dict[str, Any]):
        """Submit a task to the worker pool."""
        await self._task_queue.put(task_data)
    
    async def scale_to(self, target_count: int):
        """Scale worker pool to target count."""
        target = max(self.config.min_workers, min(target_count, self.config.max_workers))
        current = len(self._workers)
        
        if target > current:
            # Scale up
            for _ in range(target - current):
                await self._spawn_worker()
            logger.info(f"Scaled up workers: {current} -> {target}")
        
        elif target < current:
            # Scale down (remove idle workers first)
            to_remove = current - target
            idle_workers = [
                wid for wid, state in self._workers.items()
                if state.status in [WorkerStatus.IDLE, WorkerStatus.WAITING]
            ]
            
            for worker_id in idle_workers[:to_remove]:
                await self._kill_worker(worker_id)
            
            logger.info(f"Scaled down workers: {current} -> {len(self._workers)}")
    
    def get_stuck_workers(self) -> List[int]:
        """Get list of workers stuck on tasks."""
        return [wid for wid, state in self._workers.items() if state.is_stuck]
    
    async def recover_stuck_workers(self):
        """Recover workers stuck on tasks."""
        stuck = self.get_stuck_workers()
        
        for worker_id in stuck:
            state = self._workers[worker_id]
            logger.warning(f"Recovering stuck worker {worker_id} (task: {state.current_task_id})")
            
            # Kill and respawn
            await self._kill_worker(worker_id)
            await self._spawn_worker()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get worker pool statistics."""
        statuses = defaultdict(int)
        for state in self._workers.values():
            statuses[state.status.value] += 1
        
        return {
            "total_workers": len(self._workers),
            "queue_size": self._task_queue.qsize(),
            "statuses": dict(statuses),
            "stuck_workers": len(self.get_stuck_workers()),
            "total_processed": sum(w.tasks_processed for w in self._workers.values()),
            "total_errors": sum(w.errors for w in self._workers.values()),
            "workers": {
                wid: {
                    "status": state.status.value,
                    "current_task": state.current_task_id,
                    "processed": state.tasks_processed,
                    "errors": state.errors
                }
                for wid, state in self._workers.items()
            }
        }


# =============================================================================
# RECOVERY MANAGER
# =============================================================================

class RecoveryManager:
    """
    Manages agent and worker recovery.
    
    Features:
    - Auto-restart with exponential backoff
    - Failed agent tracking
    - Recovery attempt limits
    - Restart notification
    """
    
    def __init__(self, config: CoordinationConfig):
        self.config = config
        self._restart_attempts: Dict[str, int] = defaultdict(int)
        self._last_restart: Dict[str, float] = {}
        self._recovery_handlers: Dict[str, Callable] = {}
    
    def register_recovery_handler(self, agent_id: str, handler: Callable):
        """Register a recovery handler for an agent."""
        self._recovery_handlers[agent_id] = handler
    
    async def attempt_recovery(self, agent_id: str) -> bool:
        """
        Attempt to recover a failed agent.
        
        Returns True if recovery succeeded.
        """
        if not self.config.auto_restart:
            logger.info(f"Auto-restart disabled, skipping recovery for {agent_id}")
            return False
        
        attempts = self._restart_attempts[agent_id]
        
        if attempts >= self.config.max_restart_attempts:
            logger.error(f"Agent {agent_id} exceeded max restart attempts ({attempts})")
            return False
        
        # Calculate backoff delay
        delay = self.config.restart_delay_seconds * (
            self.config.restart_backoff_multiplier ** attempts
        )
        
        logger.info(f"Attempting recovery of {agent_id} (attempt {attempts + 1}, delay {delay:.1f}s)")
        
        await asyncio.sleep(delay)
        
        # Execute recovery handler if registered
        handler = self._recovery_handlers.get(agent_id)
        if handler:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(agent_id)
                else:
                    result = handler(agent_id)
                
                if result:
                    logger.info(f"Agent {agent_id} recovered successfully")
                    self._restart_attempts[agent_id] = 0
                    return True
                else:
                    self._restart_attempts[agent_id] += 1
                    return False
                    
            except Exception as e:
                logger.error(f"Recovery handler for {agent_id} failed: {e}")
                self._restart_attempts[agent_id] += 1
                return False
        else:
            # Default recovery: just mark as recovered
            self._restart_attempts[agent_id] = 0
            return True
    
    def reset_attempts(self, agent_id: str):
        """Reset restart attempts for an agent."""
        self._restart_attempts[agent_id] = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get recovery statistics."""
        return {
            "restart_attempts": dict(self._restart_attempts),
            "max_attempts": self.config.max_restart_attempts,
            "auto_restart": self.config.auto_restart
        }


# =============================================================================
# SWARM COORDINATOR
# =============================================================================

class SwarmCoordinator:
    """
    Main swarm coordination engine.
    
    Integrates:
    - Heartbeat monitoring
    - Worker pool management
    - Recovery manager
    - Hook system
    - Auto-scaling
    """
    
    def __init__(self, config: Optional[CoordinationConfig] = None):
        self.config = config or CoordinationConfig()
        
        # Components
        self.heartbeat_monitor = HeartbeatMonitor(self.config)
        self.worker_pool = WorkerPool(self.config)
        self.recovery_manager = RecoveryManager(self.config)
        self.hooks = HookRegistry()
        
        # State
        self._running = False
        self._scaling_task: Optional[asyncio.Task] = None
        self._stuck_detection_task: Optional[asyncio.Task] = None
        
        # Storage
        self._storage_path = PROJECT_ROOT / ".hive-mind" / "swarm_state.json"
        
        # Setup callbacks
        self.heartbeat_monitor.set_dead_callback(self._on_agent_dead)
        self.worker_pool.set_error_handler(self._on_task_error)
    
    async def start(self):
        """Start the swarm coordinator."""
        if self._running:
            return
        
        self._running = True
        logger.info("=" * 60)
        logger.info("SWARM COORDINATOR - STARTING")
        logger.info("=" * 60)
        
        # Start components
        await self.heartbeat_monitor.start()
        await self.worker_pool.start()
        
        # Start background tasks
        self._scaling_task = asyncio.create_task(self._auto_scaling_loop())
        self._stuck_detection_task = asyncio.create_task(self._stuck_detection_loop())
        
        logger.info(f"Swarm coordinator started")
        logger.info(f"  Workers: {len(self.worker_pool._workers)}")
        logger.info(f"  Heartbeat interval: {self.config.heartbeat_interval_seconds}s")
        logger.info(f"  Auto-restart: {self.config.auto_restart}")
    
    async def stop(self):
        """Stop the swarm coordinator gracefully."""
        if not self._running:
            return
        
        logger.info("SWARM COORDINATOR - STOPPING")
        self._running = False
        
        # Cancel background tasks
        for task in [self._scaling_task, self._stuck_detection_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Stop components
        await self.worker_pool.stop()
        await self.heartbeat_monitor.stop()
        
        # Save state
        self._save_state()
        
        logger.info("Swarm coordinator stopped")
    
    def register_hook(self, hook_type: str, handler: Callable):
        """Register a lifecycle hook."""
        try:
            ht = HookType(hook_type)
            self.hooks.register(ht, handler)
        except ValueError:
            logger.error(f"Unknown hook type: {hook_type}")
    
    def set_task_handler(self, handler: Callable):
        """Set the function that processes tasks."""
        self.worker_pool.set_task_handler(handler)
    
    async def submit_task(self, task_data: Dict[str, Any]):
        """Submit a task for processing."""
        # Execute pre-task hooks
        await self.hooks.execute(HookType.PRE_TASK, task=task_data)
        
        # Submit to worker pool
        await self.worker_pool.submit_task(task_data)
    
    def record_heartbeat(self, agent_id: str, **kwargs):
        """Record an agent heartbeat."""
        return self.heartbeat_monitor.record_heartbeat(agent_id, **kwargs)
    
    async def scale_workers(self, count: int):
        """Manually scale workers."""
        old_count = len(self.worker_pool._workers)
        await self.worker_pool.scale_to(count)
        new_count = len(self.worker_pool._workers)
        
        await self.hooks.execute(
            HookType.ON_WORKER_SCALE,
            old_count=old_count,
            new_count=new_count
        )
    
    async def _on_agent_dead(self, agent_id: str):
        """Handle dead agent detection."""
        logger.warning(f"Agent {agent_id} dead, attempting recovery")
        
        success = await self.recovery_manager.attempt_recovery(agent_id)
        
        if success:
            # Re-register heartbeat
            self.heartbeat_monitor.record_heartbeat(agent_id, status="alive")
            await self.hooks.execute(HookType.ON_AGENT_RECOVER, agent_id=agent_id)
        else:
            logger.error(f"Failed to recover agent {agent_id}")
    
    async def _on_task_error(self, task_data: Dict[str, Any], error: Exception):
        """Handle task error."""
        await self.hooks.execute(
            HookType.ON_ERROR,
            task=task_data,
            error=str(error)
        )
    
    async def _auto_scaling_loop(self):
        """Automatically scale workers based on queue depth."""
        while self._running:
            try:
                await asyncio.sleep(self.config.scale_check_interval_seconds)
                
                queue_size = self.worker_pool._task_queue.qsize()
                worker_count = len(self.worker_pool._workers)
                
                # Calculate utilization
                utilization = queue_size / max(worker_count * 10, 1)  # 10 tasks per worker target
                
                if utilization > self.config.scale_up_threshold:
                    # Scale up
                    new_count = min(worker_count + 2, self.config.max_workers)
                    if new_count > worker_count:
                        await self.worker_pool.scale_to(new_count)
                        logger.info(f"Auto-scaled up: {worker_count} -> {new_count} (queue: {queue_size})")
                
                elif utilization < self.config.scale_down_threshold and worker_count > self.config.min_workers:
                    # Scale down
                    new_count = max(worker_count - 1, self.config.min_workers)
                    await self.worker_pool.scale_to(new_count)
                    logger.info(f"Auto-scaled down: {worker_count} -> {new_count} (queue: {queue_size})")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto-scaling error: {e}")
    
    async def _stuck_detection_loop(self):
        """Detect and recover stuck workers."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                stuck = self.worker_pool.get_stuck_workers()
                if stuck:
                    logger.warning(f"Found {len(stuck)} stuck workers, recovering...")
                    await self.worker_pool.recover_stuck_workers()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stuck detection error: {e}")
    
    def _save_state(self):
        """Save coordinator state to disk."""
        state = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "heartbeats": self.heartbeat_monitor.get_stats(),
            "workers": self.worker_pool.get_stats(),
            "recovery": self.recovery_manager.get_stats()
        }
        
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._storage_path, 'w') as f:
            json.dump(state, f, indent=2)
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive coordinator status."""
        return {
            "running": self._running,
            "config": {
                "heartbeat_interval": self.config.heartbeat_interval_seconds,
                "min_workers": self.config.min_workers,
                "max_workers": self.config.max_workers,
                "auto_restart": self.config.auto_restart
            },
            "heartbeats": self.heartbeat_monitor.get_stats(),
            "workers": self.worker_pool.get_stats(),
            "recovery": self.recovery_manager.get_stats(),
            "hooks": {
                ht.value: len(self.hooks.get_handlers(ht))
                for ht in HookType
            }
        }


# =============================================================================
# DEMO
# =============================================================================

async def demo():
    """Demonstrate swarm coordination."""
    print("\n" + "=" * 60)
    print("SWARM COORDINATION - Demo")
    print("=" * 60)
    
    config = CoordinationConfig(
        heartbeat_interval_seconds=5,
        initial_workers=4,
        min_workers=2,
        max_workers=8
    )
    
    coordinator = SwarmCoordinator(config)
    
    # Task counter for demo
    processed = []
    
    async def task_handler(task_data):
        await asyncio.sleep(0.1)  # Simulate work
        processed.append(task_data["task_id"])
    
    coordinator.set_task_handler(task_handler)
    
    # Register hooks
    def on_error(task, error):
        print(f"  [HOOK] Error in task {task.get('task_id')}: {error}")
    
    coordinator.register_hook("on_error", on_error)
    
    await coordinator.start()
    
    try:
        # Record some agent heartbeats
        print("\n[Recording Heartbeats]")
        for agent in ["HUNTER", "ENRICHER", "CRAFTER", "SCHEDULER"]:
            coordinator.record_heartbeat(agent, current_task=None)
            print(f"  Heartbeat: {agent}")
        
        # Submit tasks
        print("\n[Submitting Tasks]")
        for i in range(10):
            await coordinator.submit_task({
                "task_id": f"task_{i}",
                "task_type": "test",
                "data": {"index": i}
            })
        print(f"  Submitted 10 tasks")
        
        # Wait for processing
        await asyncio.sleep(2)
        
        # Get status
        print("\n[Status]")
        status = coordinator.get_status()
        print(f"  Workers: {status['workers']['total_workers']}")
        print(f"  Queue size: {status['workers']['queue_size']}")
        print(f"  Tasks processed: {len(processed)}")
        print(f"  Heartbeats tracked: {status['heartbeats']['total_agents']}")
        
        # Scale workers
        print("\n[Scaling Workers]")
        await coordinator.scale_workers(6)
        print(f"  Workers after scale: {len(coordinator.worker_pool._workers)}")
        
    finally:
        await coordinator.stop()
    
    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
