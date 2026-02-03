#!/usr/bin/env python3
"""
Approval Engine CLI
===================

Command-line interface for managing the Approval Engine.

Commands:
    list        List all pending requests
    approve     Approve a request
    reject      Reject a request
    show        Show details of a request

Usage:
    python scripts/approval_cli.py list
    python scripts/approval_cli.py approve <request_id> --notes "Reason"
    python scripts/approval_cli.py reject <request_id> --notes "Reason"
"""

import sys
import argparse
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.approval_engine import get_approval_engine, ApprovalStatus

console = Console()

def list_requests(args):
    """List pending requests."""
    engine = get_approval_engine()
    pending = engine.get_pending_requests()
    
    if not pending:
        console.print("[yellow]No pending requests found.[/yellow]")
        return
        
    table = Table(title="Pending Approvals")
    table.add_column("ID", style="cyan")
    table.add_column("Agent", style="magenta")
    table.add_column("Action", style="green")
    table.add_column("Risk", style="red")
    table.add_column("Created", style="dim")
    table.add_column("Description")
    
    for req in pending:
        table.add_row(
            req.request_id,
            req.requester_agent,
            req.action_type,
            f"{req.risk_score:.2f}",
            req.created_at[:16],
            req.description
        )
        
    console.print(table)

def approve_request(args):
    """Approve a request."""
    engine = get_approval_engine()
    try:
        req = engine.approve_request(
            request_id=args.request_id,
            approver_id="CLI_USER",
            notes=args.notes
        )
        console.print(f"[green]Successfully approved request {req.request_id}[/green]")
    except Exception as e:
        console.print(f"[red]Error approving request: {e}[/red]")

def reject_request(args):
    """Reject a request."""
    engine = get_approval_engine()
    try:
        req = engine.reject_request(
            request_id=args.request_id,
            approver_id="CLI_USER",
            notes=args.notes
        )
        console.print(f"[yellow]Successfully rejected request {req.request_id}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error rejecting request: {e}[/red]")

def show_request(args):
    """Show request details."""
    engine = get_approval_engine()
    req = engine.get_request(args.request_id)
    
    if not req:
        console.print(f"[red]Request {args.request_id} not found.[/red]")
        return
        
    details = f"""
    [bold]ID:[/bold] {req.request_id}
    [bold]Status:[/bold] {req.status}
    [bold]Agent:[/bold] {req.requester_agent}
    [bold]Action:[/bold] {req.action_type}
    [bold]Risk Score:[/bold] {req.risk_score}
    [bold]Created:[/bold] {req.created_at}
    
    [bold]Description:[/bold] {req.description}
    
    [bold]Payload:[/bold]
    {req.payload}
    
    [bold]Metadata:[/bold]
    {req.metadata}
    """
    
    console.print(Panel(details, title=f"Request Details: {req.request_id}"))

def main():
    parser = argparse.ArgumentParser(description="Approval Engine CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # list
    subparsers.add_parser("list", help="List pending requests")
    
    # approve
    approve_parser = subparsers.add_parser("approve", help="Approve a request")
    approve_parser.add_argument("request_id", help="ID of the request")
    approve_parser.add_argument("--notes", default="Approved via CLI", help="Notes for approval")
    
    # reject
    reject_parser = subparsers.add_parser("reject", help="Reject a request")
    reject_parser.add_argument("request_id", help="ID of the request")
    reject_parser.add_argument("--notes", default="Rejected via CLI", help="Notes for rejection")
    
    # show
    show_parser = subparsers.add_parser("show", help="Show request details")
    show_parser.add_argument("request_id", help="ID of the request")
    
    args = parser.parse_args()
    
    if args.command == "list":
        list_requests(args)
    elif args.command == "approve":
        approve_request(args)
    elif args.command == "reject":
        reject_request(args)
    elif args.command == "show":
        show_request(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
