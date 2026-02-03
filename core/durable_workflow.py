#!/usr/bin/env python3
"""
Durable Workflow Engine - Checkpoint Persistence
=================================================
Provides fault-tolerant, resumable workflow execution with checkpointing.

Based on Vercel's Workflow DevKit pattern where:
- Each step is independently checkpointed
- Workflows survive restarts and deployments
- Automatic retries on failure
- Conditional branching based on step results

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    DURABLE WORKFLOW ENGINE                   │
    │                                                              │
    │  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
    │  │ Step 1   │ -> │ Step 2   │ -> │ Step 3   │              │
    │  │ ✓ Done   │    │ Running  │    │ Pending  │              │
    │  └────┬─────┘    └────┬─────┘    └──────────┘              │
    │       │               │                                     │
    │       ▼               ▼                                     │
    │  ┌────────────────────────────────────────┐                │
    │  │           CHECKPOINT STORE              │                │
    │  │  (SQLite / .hive-mind/workflows/)       │                │
    │  └────────────────────────────────────────┘                │
    └─────────────────────────────────────────────────────────────┘

Usage:
    workflow = DurableWorkflow("lead_pipeline_001")
    
    research = await workflow.step("research", hunter.research, {"lead": lead})
    enriched = await workflow.step("enrich", enricher.augment, {"data": research})
    
    if await workflow.checkpoint_exists("qualify"):
        qualification = await workflow.get_checkpoint("qualify")
    else:
        qualification = await workflow.step("qualify", segmentor.qualify, enriched)
"""

import json
import sqlite3
import asyncio
import logging
import uuid
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, TypeVar, Generic
from dataclasses import dataclass, field, asdict
from enum import Enum
from contextlib import contextmanager
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("durable_workflow")

T = TypeVar('T')


class WorkflowStatus(Enum):
    """Workflow lifecycle status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(Enum):
    """Individual step status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


@dataclass
class StepCheckpoint:
    """Checkpoint for a single workflow step."""
    step_name: str
    workflow_id: str
    status: StepStatus
    sequence: int
    agent: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "status": self.status.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StepCheckpoint':
        data["status"] = StepStatus(data["status"])
        return cls(**data)


@dataclass
class WorkflowCheckpoint:
    """Complete workflow state checkpoint."""
    workflow_id: str
    workflow_type: str
    status: WorkflowStatus
    current_step: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    steps_completed: int = 0
    steps_total: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "status": self.status.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowCheckpoint':
        data["status"] = WorkflowStatus(data["status"])
        return cls(**data)


class CheckpointStore:
    """
    SQLite-backed checkpoint persistence store.
    
    Provides durable storage for workflow and step checkpoints.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path(".hive-mind/workflows/checkpoints.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
    
    @contextmanager
    def _transaction(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def _init_db(self):
        """Initialize database schema."""
        with self._transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    workflow_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_step TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    context TEXT,
                    error TEXT,
                    steps_completed INTEGER DEFAULT 0,
                    steps_total INTEGER DEFAULT 0
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    agent TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    input_data TEXT,
                    output_data TEXT,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id),
                    UNIQUE (workflow_id, step_name)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_steps_workflow 
                ON steps(workflow_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflows_status 
                ON workflows(status)
            """)
    
    def save_workflow(self, checkpoint: WorkflowCheckpoint):
        """Save or update workflow checkpoint."""
        with self._transaction() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO workflows 
                (workflow_id, workflow_type, status, current_step, created_at, 
                 updated_at, completed_at, context, error, steps_completed, steps_total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                checkpoint.workflow_id,
                checkpoint.workflow_type,
                checkpoint.status.value,
                checkpoint.current_step,
                checkpoint.created_at,
                checkpoint.updated_at,
                checkpoint.completed_at,
                json.dumps(checkpoint.context),
                checkpoint.error,
                checkpoint.steps_completed,
                checkpoint.steps_total
            ))
    
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowCheckpoint]:
        """Get workflow checkpoint."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM workflows WHERE workflow_id = ?",
            (workflow_id,)
        ).fetchone()
        
        if not row:
            return None
        
        return WorkflowCheckpoint(
            workflow_id=row["workflow_id"],
            workflow_type=row["workflow_type"],
            status=WorkflowStatus(row["status"]),
            current_step=row["current_step"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            context=json.loads(row["context"]) if row["context"] else {},
            error=row["error"],
            steps_completed=row["steps_completed"],
            steps_total=row["steps_total"]
        )
    
    def save_step(self, checkpoint: StepCheckpoint):
        """Save or update step checkpoint."""
        with self._transaction() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO steps 
                (workflow_id, step_name, sequence, status, agent, started_at, 
                 completed_at, input_data, output_data, error, retry_count, max_retries)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                checkpoint.workflow_id,
                checkpoint.step_name,
                checkpoint.sequence,
                checkpoint.status.value,
                checkpoint.agent,
                checkpoint.started_at,
                checkpoint.completed_at,
                json.dumps(checkpoint.input_data) if checkpoint.input_data else None,
                json.dumps(checkpoint.output_data) if checkpoint.output_data else None,
                checkpoint.error,
                checkpoint.retry_count,
                checkpoint.max_retries
            ))
    
    def get_step(self, workflow_id: str, step_name: str) -> Optional[StepCheckpoint]:
        """Get step checkpoint."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM steps WHERE workflow_id = ? AND step_name = ?",
            (workflow_id, step_name)
        ).fetchone()
        
        if not row:
            return None
        
        return StepCheckpoint(
            step_name=row["step_name"],
            workflow_id=row["workflow_id"],
            status=StepStatus(row["status"]),
            sequence=row["sequence"],
            agent=row["agent"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            input_data=json.loads(row["input_data"]) if row["input_data"] else None,
            output_data=json.loads(row["output_data"]) if row["output_data"] else None,
            error=row["error"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"]
        )
    
    def get_all_steps(self, workflow_id: str) -> List[StepCheckpoint]:
        """Get all steps for a workflow."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM steps WHERE workflow_id = ? ORDER BY sequence",
            (workflow_id,)
        ).fetchall()
        
        return [
            StepCheckpoint(
                step_name=row["step_name"],
                workflow_id=row["workflow_id"],
                status=StepStatus(row["status"]),
                sequence=row["sequence"],
                agent=row["agent"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                input_data=json.loads(row["input_data"]) if row["input_data"] else None,
                output_data=json.loads(row["output_data"]) if row["output_data"] else None,
                error=row["error"],
                retry_count=row["retry_count"],
                max_retries=row["max_retries"]
            )
            for row in rows
        ]
    
    def list_in_progress_workflows(self) -> List[WorkflowCheckpoint]:
        """List all in-progress workflows (for resumption)."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM workflows WHERE status IN (?, ?, ?)",
            (WorkflowStatus.IN_PROGRESS.value, WorkflowStatus.PAUSED.value, 
             WorkflowStatus.AWAITING_APPROVAL.value)
        ).fetchall()
        
        return [
            WorkflowCheckpoint(
                workflow_id=row["workflow_id"],
                workflow_type=row["workflow_type"],
                status=WorkflowStatus(row["status"]),
                current_step=row["current_step"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                completed_at=row["completed_at"],
                context=json.loads(row["context"]) if row["context"] else {},
                error=row["error"],
                steps_completed=row["steps_completed"],
                steps_total=row["steps_total"]
            )
            for row in rows
        ]
    
    def delete_workflow(self, workflow_id: str):
        """Delete workflow and its steps."""
        with self._transaction() as conn:
            conn.execute("DELETE FROM steps WHERE workflow_id = ?", (workflow_id,))
            conn.execute("DELETE FROM workflows WHERE workflow_id = ?", (workflow_id,))


class DurableWorkflow:
    """
    A durable, checkpoint-based workflow execution engine.
    
    Implements the Vercel Workflow DevKit pattern:
    - Each step is independently checkpointed
    - Automatic resumption from last checkpoint on restart
    - Built-in retry logic with exponential backoff
    - Conditional branching based on step results
    
    Usage:
        workflow = DurableWorkflow("lead_pipeline_001", workflow_type="lead_processing")
        
        # Steps are checkpointed automatically
        research = await workflow.step("research", hunter.research, lead)
        
        # If workflow restarts, completed steps return cached results
        enriched = await workflow.step("enrich", enricher.augment, research)
        
        # Conditional branching
        if enriched.get("qualified"):
            await workflow.step("craft", crafter.generate, enriched)
    """
    
    def __init__(
        self, 
        workflow_id: str,
        workflow_type: str = "default",
        store: Optional[CheckpointStore] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.workflow_id = workflow_id
        self.workflow_type = workflow_type
        self.store = store or CheckpointStore()
        self._step_sequence = 0
        self._context = context or {}
        
        # Load or create workflow checkpoint
        existing = self.store.get_workflow(workflow_id)
        if existing:
            self._checkpoint = existing
            self._context.update(existing.context)
            logger.info(f"Resuming workflow {workflow_id} from step: {existing.current_step}")
        else:
            self._checkpoint = WorkflowCheckpoint(
                workflow_id=workflow_id,
                workflow_type=workflow_type,
                status=WorkflowStatus.IN_PROGRESS,
                context=self._context
            )
            self.store.save_workflow(self._checkpoint)
            logger.info(f"Created new workflow {workflow_id}")
    
    async def step(
        self,
        name: str,
        fn: Callable,
        input_data: Any = None,
        agent: Optional[str] = None,
        max_retries: int = 3,
        timeout_seconds: int = 300
    ) -> Any:
        """
        Execute a workflow step with automatic checkpointing.
        
        If the step was previously completed (from a prior run), returns
        the cached result without re-executing.
        
        Args:
            name: Unique step name
            fn: The function to execute (sync or async)
            input_data: Data to pass to the function
            agent: Optional agent name for logging
            max_retries: Number of retry attempts
            timeout_seconds: Step timeout
            
        Returns:
            The result of the step execution
        """
        self._step_sequence += 1
        
        # Check if step already completed (resumption case)
        existing_step = self.store.get_step(self.workflow_id, name)
        if existing_step and existing_step.status == StepStatus.COMPLETED:
            logger.info(f"Step '{name}' already completed, returning cached result")
            return existing_step.output_data
        
        # Create or update step checkpoint
        step_checkpoint = StepCheckpoint(
            step_name=name,
            workflow_id=self.workflow_id,
            status=StepStatus.RUNNING,
            sequence=self._step_sequence,
            agent=agent,
            started_at=datetime.now(timezone.utc).isoformat(),
            input_data=input_data if isinstance(input_data, dict) else {"value": input_data},
            max_retries=max_retries,
            retry_count=existing_step.retry_count if existing_step else 0
        )
        
        # Update workflow current step
        self._checkpoint.current_step = name
        self._checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        self.store.save_workflow(self._checkpoint)
        self.store.save_step(step_checkpoint)
        
        # Execute with retry logic
        result = None
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Execute the function
                if asyncio.iscoroutinefunction(fn):
                    result = await asyncio.wait_for(
                        fn(input_data) if input_data else fn(),
                        timeout=timeout_seconds
                    )
                else:
                    result = fn(input_data) if input_data else fn()
                
                # Success - save checkpoint
                step_checkpoint.status = StepStatus.COMPLETED
                step_checkpoint.completed_at = datetime.now(timezone.utc).isoformat()
                step_checkpoint.output_data = result if isinstance(result, dict) else {"result": result}
                step_checkpoint.error = None
                
                self.store.save_step(step_checkpoint)
                
                # Update workflow progress
                self._checkpoint.steps_completed += 1
                self._checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
                self.store.save_workflow(self._checkpoint)
                
                logger.info(f"Step '{name}' completed successfully")
                return result
                
            except asyncio.TimeoutError as e:
                last_error = f"Step timed out after {timeout_seconds}s"
                logger.warning(f"Step '{name}' timed out (attempt {attempt + 1}/{max_retries})")
                
            except Exception as e:
                last_error = f"{type(e).__name__}: {str(e)}"
                logger.warning(f"Step '{name}' failed (attempt {attempt + 1}/{max_retries}): {last_error}")
                
            # Update retry count
            step_checkpoint.retry_count = attempt + 1
            step_checkpoint.status = StepStatus.RETRYING
            step_checkpoint.error = last_error
            self.store.save_step(step_checkpoint)
            
            # Exponential backoff before retry
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        # All retries exhausted
        step_checkpoint.status = StepStatus.FAILED
        step_checkpoint.error = last_error
        self.store.save_step(step_checkpoint)
        
        # Mark workflow as failed
        self._checkpoint.status = WorkflowStatus.FAILED
        self._checkpoint.error = f"Step '{name}' failed: {last_error}"
        self._checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        self.store.save_workflow(self._checkpoint)
        
        raise RuntimeError(f"Step '{name}' failed after {max_retries} attempts: {last_error}")
    
    async def checkpoint_exists(self, step_name: str) -> bool:
        """Check if a step checkpoint exists and is completed."""
        step = self.store.get_step(self.workflow_id, step_name)
        return step is not None and step.status == StepStatus.COMPLETED
    
    async def get_checkpoint(self, step_name: str) -> Optional[Any]:
        """Get the output of a completed step."""
        step = self.store.get_step(self.workflow_id, step_name)
        if step and step.status == StepStatus.COMPLETED:
            return step.output_data
        return None
    
    async def pause(self, reason: str = ""):
        """Pause the workflow (e.g., for human approval)."""
        self._checkpoint.status = WorkflowStatus.PAUSED
        self._checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        self._checkpoint.context["pause_reason"] = reason
        self.store.save_workflow(self._checkpoint)
        logger.info(f"Workflow {self.workflow_id} paused: {reason}")
    
    async def await_approval(self, approval_id: str):
        """Mark workflow as awaiting approval."""
        self._checkpoint.status = WorkflowStatus.AWAITING_APPROVAL
        self._checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        self._checkpoint.context["approval_id"] = approval_id
        self.store.save_workflow(self._checkpoint)
        logger.info(f"Workflow {self.workflow_id} awaiting approval: {approval_id}")
    
    async def resume(self):
        """Resume a paused workflow."""
        if self._checkpoint.status in (WorkflowStatus.PAUSED, WorkflowStatus.AWAITING_APPROVAL):
            self._checkpoint.status = WorkflowStatus.IN_PROGRESS
            self._checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
            self.store.save_workflow(self._checkpoint)
            logger.info(f"Workflow {self.workflow_id} resumed")
    
    async def complete(self, result: Optional[Dict[str, Any]] = None):
        """Mark workflow as completed."""
        self._checkpoint.status = WorkflowStatus.COMPLETED
        self._checkpoint.completed_at = datetime.now(timezone.utc).isoformat()
        self._checkpoint.updated_at = self._checkpoint.completed_at
        if result:
            self._checkpoint.context["final_result"] = result
        self.store.save_workflow(self._checkpoint)
        logger.info(f"Workflow {self.workflow_id} completed")
    
    async def fail(self, error: str):
        """Mark workflow as failed."""
        self._checkpoint.status = WorkflowStatus.FAILED
        self._checkpoint.error = error
        self._checkpoint.updated_at = datetime.now(timezone.utc).isoformat()
        self.store.save_workflow(self._checkpoint)
        logger.error(f"Workflow {self.workflow_id} failed: {error}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current workflow status."""
        steps = self.store.get_all_steps(self.workflow_id)
        
        return {
            "workflow_id": self.workflow_id,
            "workflow_type": self.workflow_type,
            "status": self._checkpoint.status.value,
            "current_step": self._checkpoint.current_step,
            "steps_completed": sum(1 for s in steps if s.status == StepStatus.COMPLETED),
            "steps_total": len(steps),
            "steps": [
                {
                    "name": s.step_name,
                    "status": s.status.value,
                    "agent": s.agent,
                    "retry_count": s.retry_count
                }
                for s in steps
            ],
            "created_at": self._checkpoint.created_at,
            "updated_at": self._checkpoint.updated_at,
            "error": self._checkpoint.error
        }


class WorkflowManager:
    """
    Manager for all durable workflows.
    
    Provides:
    - Listing of active/paused workflows
    - Bulk resumption after restart
    - Cleanup of old workflows
    """
    
    def __init__(self, store: Optional[CheckpointStore] = None):
        self.store = store or CheckpointStore()
    
    def create_workflow(
        self,
        workflow_id: Optional[str] = None,
        workflow_type: str = "default",
        context: Optional[Dict[str, Any]] = None
    ) -> DurableWorkflow:
        """Create a new durable workflow."""
        if workflow_id is None:
            workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        
        return DurableWorkflow(
            workflow_id=workflow_id,
            workflow_type=workflow_type,
            store=self.store,
            context=context
        )
    
    def get_workflow(self, workflow_id: str) -> Optional[DurableWorkflow]:
        """Get existing workflow (for resumption)."""
        existing = self.store.get_workflow(workflow_id)
        if not existing:
            return None
        
        return DurableWorkflow(
            workflow_id=workflow_id,
            workflow_type=existing.workflow_type,
            store=self.store,
            context=existing.context
        )
    
    def list_in_progress(self) -> List[Dict[str, Any]]:
        """List all in-progress workflows."""
        workflows = self.store.list_in_progress_workflows()
        return [w.to_dict() for w in workflows]
    
    async def resume_all(self):
        """Resume all paused workflows."""
        in_progress = self.store.list_in_progress_workflows()
        resumed = 0
        
        for wf_checkpoint in in_progress:
            if wf_checkpoint.status == WorkflowStatus.PAUSED:
                workflow = self.get_workflow(wf_checkpoint.workflow_id)
                if workflow:
                    await workflow.resume()
                    resumed += 1
        
        logger.info(f"Resumed {resumed} paused workflows")
        return resumed
    
    def cleanup_old_workflows(self, days: int = 30):
        """Delete completed workflows older than specified days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        conn = self.store._get_connection()
        old_workflows = conn.execute(
            "SELECT workflow_id FROM workflows WHERE status = ? AND completed_at < ?",
            (WorkflowStatus.COMPLETED.value, cutoff)
        ).fetchall()
        
        for row in old_workflows:
            self.store.delete_workflow(row["workflow_id"])
        
        logger.info(f"Cleaned up {len(old_workflows)} old workflows")
        return len(old_workflows)


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_manager_instance: Optional[WorkflowManager] = None


def get_workflow_manager() -> WorkflowManager:
    """Get singleton instance of WorkflowManager."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = WorkflowManager()
    return _manager_instance


# =============================================================================
# DEMO
# =============================================================================

async def demo():
    """Demonstrate durable workflow functionality."""
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    console.print("\n[bold blue]Durable Workflow Demo[/bold blue]\n")
    
    manager = get_workflow_manager()
    
    # Create a workflow
    workflow = manager.create_workflow(
        workflow_id="demo_lead_pipeline_001",
        workflow_type="lead_processing",
        context={"source": "competitor_followers"}
    )
    
    # Define mock step functions
    async def mock_research(data):
        await asyncio.sleep(0.1)
        return {"leads": ["lead_1", "lead_2", "lead_3"], "count": 3}
    
    async def mock_enrich(data):
        await asyncio.sleep(0.1)
        return {"enriched_count": 3, "email_found": 2}
    
    async def mock_qualify(data):
        await asyncio.sleep(0.1)
        return {"tier_1": 1, "tier_2": 2, "qualified": True}
    
    console.print("[yellow]Executing workflow steps...[/yellow]\n")
    
    # Execute steps
    research = await workflow.step("research", mock_research, {"source": "gong"}, agent="HUNTER")
    console.print(f"  ✓ Research: {research}")
    
    enriched = await workflow.step("enrich", mock_enrich, research, agent="ENRICHER")
    console.print(f"  ✓ Enrich: {enriched}")
    
    qualified = await workflow.step("qualify", mock_qualify, enriched, agent="SEGMENTOR")
    console.print(f"  ✓ Qualify: {qualified}")
    
    # Complete workflow
    await workflow.complete({"final_count": qualified["tier_1"] + qualified["tier_2"]})
    
    # Show status
    status = workflow.get_status()
    
    table = Table(title="Workflow Status")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Workflow ID", status["workflow_id"])
    table.add_row("Status", status["status"])
    table.add_row("Steps Completed", str(status["steps_completed"]))
    table.add_row("Steps", ", ".join(s["name"] for s in status["steps"]))
    
    console.print(table)
    
    # Demonstrate resumption
    console.print("\n[yellow]Simulating resumption...[/yellow]")
    
    resumed_workflow = manager.get_workflow("demo_lead_pipeline_001")
    if resumed_workflow:
        # Try to get cached step result
        cached_research = await resumed_workflow.get_checkpoint("research")
        console.print(f"  Cached research result: {cached_research}")
    
    console.print("\n[green]Demo complete![/green]")


if __name__ == "__main__":
    asyncio.run(demo())
