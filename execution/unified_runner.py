#!/usr/bin/env python3
"""
Unified Runner
==============
The single production entry point for the Chief AI Officer Alpha Swarm.
Bridges the 'Ghost Code' gap by wiring the UnifiedQueen and MultiLayerFailsafe
to the execution layer.

Usage:
    python execution/unified_runner.py --mode parallel --generate 5
    python execution/unified_runner.py --dashboard
"""

import os
import sys
import asyncio
import logging
import argparse
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Core Imports (The Brain)
from execution.unified_queen_orchestrator import UnifiedQueen, Task, TaskCategory, TaskPriority
from core.multi_layer_failsafe import with_failsafe, ValidationResult
from core.unified_guardrails import UnifiedGuardrails

# Execution Imports (The Body) - for parallel mode queue
from execution.priority_4_parallel_mode import ParallelModeQueue, print_dashboard, interactive_approval

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("unified_runner")
console = Console()

class UnifiedSystem:
    """
    Wrapper that connects:
    1. UnifiedQueen (Orchestration)
    2. MultiLayerFailsafe (Protection)
    3. ParallelModeQueue (Human Control)
    """
    
    def __init__(self):
        self.queen = UnifiedQueen()
        self.approval_queue = ParallelModeQueue()
        self.guardrails = UnifiedGuardrails()
        
    @with_failsafe(agent_name="UNIFIED_QUEEN")
    async def start(self):
        """Start the system with full protection."""
        logger.info("Initializing Unified System...")
        
        # Start Queen logic
        await self.queen.start()
        
        console.print(Panel(
            "[bold green]UNIFIED SYSTEM ONLINE[/bold green]\n"
            "• UnifiedQueen: [green]Active[/green]\n"
            "• MultiLayerFailsafe: [green]Active[/green]\n"
            "• CircuitBreakers: [green]Registered[/green]",
            title="System Status"
        ))

    async def inject_task(self, task_type: str, params: dict, priority: TaskPriority = TaskPriority.MEDIUM):
        """Inject a task into the Queen's neural network."""
        task = Task(
            id=f"task_{os.urandom(4).hex()}",
            task_type=task_type,
            category=self._map_category(task_type),
            priority=priority,
            parameters=params
        )
        
        logger.info(f"Injecting task {task.id} ({task_type})")
        await self.queen.task_queue.put(task)
        return task.id

    def _map_category(self, task_type: str) -> TaskCategory:
        """Map raw types to Queen categories."""
        if "email" in task_type or "outreach" in task_type:
            return TaskCategory.LEAD_GEN
        if "research" in task_type:
            return TaskCategory.RESEARCH
        return TaskCategory.SYSTEM

    async def shutdown(self):
        await self.queen.stop()

async def interactive_mode(system: UnifiedSystem):
    """Run interactive CLI."""
    while True:
        console.print("\n[bold]Unified Runner Commands:[/bold]")
        console.print("1. Inject Test Task (Lead Gen)")
        console.print("2. View Dashboard (Parallel Mode)")
        console.print("3. Approve Actions")
        console.print("4. Exit")
        
        choice = input("\nSelect > ")
        
        if choice == "1":
            await system.inject_task(
                "lead_gen_outreach", 
                {"linkedin_url": "test_url", "name": "Test Lead"}
            )
            console.print("[green]Task Injected[/green]")
        elif choice == "2":
            print_dashboard(system.approval_queue)
        elif choice == "3":
            interactive_approval(system.approval_queue)
        elif choice == "4":
            await system.shutdown()
            break

async def main():
    parser = argparse.ArgumentParser(description="Unified Runner")
    parser.add_argument("--interactive", action="store_true", help="Run interactive mode")
    args = parser.parse_args()
    
    system = UnifiedSystem()
    
    try:
        await system.start()
        
        if args.interactive:
            await interactive_mode(system)
        else:
            # Default behavior: run forever or until signal
            print_dashboard(system.approval_queue)
            console.print("[yellow]Running in background... (Ctrl+C to stop)[/yellow]")
            while True:
                await asyncio.sleep(1)
                
    except KeyboardInterrupt:
        logger.info("Stopping...")
        await system.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
