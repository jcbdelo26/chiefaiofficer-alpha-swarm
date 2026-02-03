"""
Handoff Queue Manager for SDR Automation
=========================================
Manages the handoff queue for escalated leads requiring human attention.

Persists to .hive-mind/handoff_queue.json with methods to:
- Create new handoffs
- Acknowledge pending handoffs
- Close completed handoffs
- Query by priority and status
"""

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.event_log import EventType, log_event
from core.routing import HandoffTicket, HandoffPriority

console = Console()


class HandoffQueue:
    """
    Manages the handoff queue for leads requiring human escalation.
    
    Persists queue state to .hive-mind/handoff_queue.json.
    """
    
    def __init__(self):
        self.queue_path = Path(__file__).parent.parent / ".hive-mind" / "handoff_queue.json"
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue = self._load_queue()
    
    def _load_queue(self) -> Dict[str, Any]:
        """Load queue from disk."""
        if self.queue_path.exists():
            try:
                with open(self.queue_path) as f:
                    return json.load(f)
            except Exception as e:
                console.print(f"[yellow]Failed to load handoff queue: {e}[/yellow]")
        
        return {
            "pending": [],
            "acknowledged": [],
            "closed": [],
            "total_created": 0,
            "updated_at": None
        }
    
    def _save_queue(self):
        """Save queue to disk."""
        self.queue["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Keep last 500 closed items
        if len(self.queue.get("closed", [])) > 500:
            self.queue["closed"] = self.queue["closed"][-500:]
        
        with open(self.queue_path, "w") as f:
            json.dump(self.queue, f, indent=2)
    
    def create_handoff(self, ticket: HandoffTicket) -> HandoffTicket:
        """
        Add a new handoff ticket to the queue.
        
        Args:
            ticket: HandoffTicket to add
            
        Returns:
            The added ticket
        """
        ticket_dict = asdict(ticket)
        self.queue["pending"].append(ticket_dict)
        self.queue["total_created"] = self.queue.get("total_created", 0) + 1
        self._save_queue()
        
        # Log the event
        log_event(
            EventType.HANDOFF_CREATED,
            {
                "handoff_id": ticket.handoff_id,
                "lead_id": ticket.lead_id,
                "trigger": ticket.trigger,
                "destination": ticket.destination,
                "priority": ticket.priority,
                "sla_due_at": ticket.sla_due_at
            }
        )
        
        console.print(f"[cyan]🎫 Handoff created:[/cyan] {ticket.trigger} → {ticket.destination} [{ticket.priority}]")
        
        return ticket
    
    def create_handoffs(self, tickets: List[HandoffTicket]) -> List[HandoffTicket]:
        """
        Add multiple handoff tickets to the queue.
        
        Args:
            tickets: List of HandoffTicket objects
            
        Returns:
            List of added tickets
        """
        for ticket in tickets:
            self.create_handoff(ticket)
        return tickets
    
    def acknowledge(self, handoff_id: str, acknowledged_by: str = "AE") -> Optional[Dict[str, Any]]:
        """
        Acknowledge a pending handoff.
        
        Args:
            handoff_id: ID of the handoff to acknowledge
            acknowledged_by: Name/ID of acknowledger
            
        Returns:
            The acknowledged ticket dict or None if not found
        """
        for i, ticket in enumerate(self.queue["pending"]):
            if ticket["handoff_id"] == handoff_id:
                ticket["status"] = "acknowledged"
                ticket["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
                ticket["acknowledged_by"] = acknowledged_by
                
                self.queue["acknowledged"].append(ticket)
                self.queue["pending"].pop(i)
                self._save_queue()
                
                console.print(f"[green]✓ Acknowledged:[/green] {ticket['trigger']} by {acknowledged_by}")
                return ticket
        
        console.print(f"[red]Handoff not found: {handoff_id}[/red]")
        return None
    
    def close(
        self, 
        handoff_id: str, 
        closed_by: str = "AE",
        notes: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Close a handoff (from pending or acknowledged).
        
        Args:
            handoff_id: ID of the handoff to close
            closed_by: Name/ID of closer
            notes: Optional closing notes
            
        Returns:
            The closed ticket dict or None if not found
        """
        # Check pending first
        for i, ticket in enumerate(self.queue["pending"]):
            if ticket["handoff_id"] == handoff_id:
                ticket["status"] = "closed"
                ticket["closed_at"] = datetime.now(timezone.utc).isoformat()
                ticket["closed_by"] = closed_by
                if notes:
                    ticket["notes"] = notes
                
                self.queue["closed"].append(ticket)
                self.queue["pending"].pop(i)
                self._save_queue()
                
                console.print(f"[green]✓ Closed:[/green] {ticket['trigger']}")
                return ticket
        
        # Check acknowledged
        for i, ticket in enumerate(self.queue["acknowledged"]):
            if ticket["handoff_id"] == handoff_id:
                ticket["status"] = "closed"
                ticket["closed_at"] = datetime.now(timezone.utc).isoformat()
                ticket["closed_by"] = closed_by
                if notes:
                    ticket["notes"] = notes
                
                self.queue["closed"].append(ticket)
                self.queue["acknowledged"].pop(i)
                self._save_queue()
                
                console.print(f"[green]✓ Closed:[/green] {ticket['trigger']}")
                return ticket
        
        console.print(f"[red]Handoff not found: {handoff_id}[/red]")
        return None
    
    def get_pending(self) -> List[Dict[str, Any]]:
        """Get all pending handoffs."""
        return self.queue.get("pending", [])
    
    def get_acknowledged(self) -> List[Dict[str, Any]]:
        """Get all acknowledged (in-progress) handoffs."""
        return self.queue.get("acknowledged", [])
    
    def get_by_priority(self, priority: str) -> List[Dict[str, Any]]:
        """
        Get all pending handoffs with a specific priority.
        
        Args:
            priority: One of critical, high, medium, low, block
            
        Returns:
            List of matching handoff dicts
        """
        pending = self.queue.get("pending", [])
        return [t for t in pending if t.get("priority") == priority]
    
    def get_by_destination(self, destination: str) -> List[Dict[str, Any]]:
        """
        Get all pending handoffs for a specific destination.
        
        Args:
            destination: One of ae, se, csm, etc.
            
        Returns:
            List of matching handoff dicts
        """
        pending = self.queue.get("pending", [])
        return [t for t in pending if t.get("destination") == destination]
    
    def get_overdue(self) -> List[Dict[str, Any]]:
        """Get all pending handoffs past their SLA due time."""
        now = datetime.now(timezone.utc)
        pending = self.queue.get("pending", [])
        overdue = []
        
        for ticket in pending:
            try:
                sla_due = datetime.fromisoformat(ticket["sla_due_at"].replace("Z", "+00:00"))
                if now > sla_due:
                    overdue.append(ticket)
            except Exception:
                pass
        
        return overdue
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        pending = self.queue.get("pending", [])
        acknowledged = self.queue.get("acknowledged", [])
        closed = self.queue.get("closed", [])
        
        # Count by priority
        priority_counts = {}
        for p in HandoffPriority:
            priority_counts[p.value] = len([t for t in pending if t.get("priority") == p.value])
        
        # Count overdue
        overdue_count = len(self.get_overdue())
        
        return {
            "pending_count": len(pending),
            "acknowledged_count": len(acknowledged),
            "closed_count": len(closed),
            "total_created": self.queue.get("total_created", 0),
            "overdue_count": overdue_count,
            "by_priority": priority_counts,
            "updated_at": self.queue.get("updated_at")
        }
    
    def print_queue(self):
        """Print the handoff queue to console."""
        stats = self.get_stats()
        
        # Stats panel
        stats_text = f"""
Pending: {stats['pending_count']} | Acknowledged: {stats['acknowledged_count']} | Closed: {stats['closed_count']}
Overdue: {stats['overdue_count']} | Total Created: {stats['total_created']}
By Priority: Critical={stats['by_priority'].get('critical', 0)} | High={stats['by_priority'].get('high', 0)} | Medium={stats['by_priority'].get('medium', 0)} | Low={stats['by_priority'].get('low', 0)}
        """
        console.print(Panel(stats_text.strip(), title="🎫 Handoff Queue Statistics"))
        
        # Pending table sorted by priority
        pending = self.queue.get("pending", [])
        if pending:
            # Sort: critical first, then high, medium, low
            priority_order = {"critical": 0, "block": 0, "high": 1, "medium": 2, "low": 3}
            sorted_pending = sorted(pending, key=lambda t: priority_order.get(t.get("priority", "low"), 99))
            
            table = Table(title="Pending Handoffs")
            table.add_column("ID", style="dim", width=8)
            table.add_column("Priority", width=10)
            table.add_column("Trigger", style="cyan", width=25)
            table.add_column("Destination", style="green", width=15)
            table.add_column("Lead", width=25)
            table.add_column("SLA Due", style="yellow", width=18)
            
            for ticket in sorted_pending[:15]:
                priority = ticket.get("priority", "")
                priority_style = {
                    "critical": "[bold red]CRITICAL[/bold red]",
                    "block": "[bold red]BLOCK[/bold red]",
                    "high": "[yellow]HIGH[/yellow]",
                    "medium": "[blue]MEDIUM[/blue]",
                    "low": "[dim]LOW[/dim]"
                }.get(priority, priority)
                
                lead_info = ticket.get("lead_name", "") or ticket.get("lead_email", "") or ticket.get("lead_id", "")[:20]
                sla_due = ticket.get("sla_due_at", "")[:16].replace("T", " ")
                
                table.add_row(
                    ticket.get("handoff_id", "")[:8],
                    priority_style,
                    ticket.get("trigger", ""),
                    ticket.get("destination", ""),
                    lead_info[:25],
                    sla_due
                )
            
            console.print(table)
            
            if len(pending) > 15:
                console.print(f"[dim]... and {len(pending) - 15} more[/dim]")
        else:
            console.print("[dim]No pending handoffs[/dim]")
