#!/usr/bin/env python3
"""
Retry Worker - Processes failed jobs from the retry queue.
============================================================
Reads pending retry jobs and executes them with appropriate backoff.

Usage:
    python execution/retry_worker.py
    python execution/retry_worker.py --once
    python execution/retry_worker.py --dry-run
"""

import sys
import time
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Callable

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.live import Live

from core.retry import (
    RetryJob, RetryStatus, RetryPolicy,
    read_retry_queue, update_retry_queue, get_policy, schedule_retry
)
from core.alerts import send_alert, send_critical, AlertLevel
from core.event_log import log_event, EventType

console = Console()

OPERATION_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {}


def register_handler(operation_name: str) -> Callable:
    """Decorator to register a retry handler for an operation."""
    def decorator(fn: Callable[[dict[str, Any]], Any]) -> Callable:
        OPERATION_HANDLERS[operation_name] = fn
        return fn
    return decorator


@register_handler("enrichment")
def handle_enrichment_retry(payload: dict[str, Any]) -> Any:
    """Retry enrichment for a lead."""
    from execution.enricher_waterfall import ClayEnricher
    
    enricher = ClayEnricher()
    result = enricher.enrich_lead(
        lead_id=payload.get("lead_id", ""),
        linkedin_url=payload.get("linkedin_url", ""),
        name=payload.get("name", ""),
        company=payload.get("company", "")
    )
    
    if result is None:
        policy = get_policy("enrichment_failure")
        if payload.get("retry_count", 0) >= policy.max_retries:
            console.print(f"[yellow]Proceeding with partial data for {payload.get('lead_id')}[/yellow]")
            return {"status": "partial", "lead_id": payload.get("lead_id")}
        raise Exception("Enrichment returned no data")
    
    return result


@register_handler("campaign_delivery")
def handle_campaign_delivery_retry(payload: dict[str, Any]) -> Any:
    """Retry campaign delivery."""
    console.print(f"[dim]Retrying campaign delivery: {payload.get('campaign_id')}[/dim]")
    raise NotImplementedError("Campaign delivery handler not yet implemented")


@register_handler("scraping")
def handle_scraping_retry(payload: dict[str, Any]) -> Any:
    """Handle scraping retry - typically requires manual intervention."""
    send_critical(
        title="Scraping Blocked - Manual Intervention Required",
        message=f"Scraping operation failed and requires manual review.\nSource: {payload.get('source', 'unknown')}",
        metadata=payload,
        source="retry_worker"
    )
    raise Exception("Scraping blocked - paused for manual intervention")


@register_handler("api_call")
def handle_api_retry(payload: dict[str, Any]) -> Any:
    """Retry a generic API call."""
    import requests
    
    method = payload.get("method", "GET").upper()
    url = payload.get("url", "")
    headers = payload.get("headers", {})
    body = payload.get("body")
    
    if not url:
        raise ValueError("No URL in payload")
    
    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        json=body if body else None,
        timeout=30
    )
    
    if response.status_code == 429:
        raise Exception(f"Rate limited: {response.status_code}")
    
    response.raise_for_status()
    return response.json() if response.content else None


def process_job(job: RetryJob, dry_run: bool = False) -> tuple[bool, Optional[str]]:
    """
    Process a single retry job.
    
    Returns:
        Tuple of (success, error_message)
    """
    operation = job.operation_name
    handler = OPERATION_HANDLERS.get(operation)
    
    if not handler:
        base_op = operation.split("_")[0] if "_" in operation else operation
        handler = OPERATION_HANDLERS.get(base_op)
    
    if not handler:
        return False, f"No handler registered for operation: {operation}"
    
    if dry_run:
        console.print(f"[dim]Would execute: {operation} with payload: {json.dumps(job.payload)[:100]}...[/dim]")
        return True, None
    
    try:
        console.print(f"[cyan]Executing retry: {operation} (attempt {job.retry_count})[/cyan]")
        result = handler(job.payload)
        console.print(f"[green]✅ Success: {operation}[/green]")
        return True, None
    except Exception as e:
        console.print(f"[red]❌ Failed: {operation} - {e}[/red]")
        return False, str(e)


def get_ready_jobs() -> list[RetryJob]:
    """Get jobs that are ready to be processed (next_attempt_at <= now)."""
    now = datetime.now(timezone.utc)
    all_jobs = read_retry_queue()
    
    ready = []
    for job in all_jobs:
        if job.status not in [RetryStatus.PENDING.value, "pending"]:
            continue
        
        try:
            next_attempt = datetime.fromisoformat(job.next_attempt_at.replace("Z", "+00:00"))
            if next_attempt <= now:
                ready.append(job)
        except Exception:
            ready.append(job)
    
    return ready


def run_worker(once: bool = False, dry_run: bool = False, interval: int = 60) -> None:
    """
    Run the retry worker.
    
    Args:
        once: Run once and exit
        dry_run: Don't actually execute jobs
        interval: Seconds between queue checks
    """
    console.print("[bold blue]🔄 RETRY WORKER: Starting[/bold blue]")
    
    if dry_run:
        console.print("[yellow]Dry run mode - no jobs will be executed[/yellow]")
    
    while True:
        ready_jobs = get_ready_jobs()
        
        if not ready_jobs:
            if once:
                console.print("[dim]No jobs ready to process[/dim]")
                break
            console.print(f"[dim]No jobs ready. Sleeping {interval}s...[/dim]")
            time.sleep(interval)
            continue
        
        console.print(f"\n[bold]Processing {len(ready_jobs)} jobs[/bold]")
        
        all_jobs = read_retry_queue()
        job_map = {j.job_id: j for j in all_jobs}
        
        for job in ready_jobs:
            success, error = process_job(job, dry_run)
            
            if dry_run:
                continue
            
            current_job = job_map.get(job.job_id)
            if not current_job:
                continue
            
            if success:
                current_job.status = RetryStatus.COMPLETED.value
            else:
                policy = get_policy(job.policy_name or "default")
                
                if job.retry_count >= policy.max_retries:
                    current_job.status = RetryStatus.EXHAUSTED.value
                    current_job.last_error = error
                    
                    handle_exhausted_job(current_job, policy)
                else:
                    new_job = schedule_retry(
                        operation_name=job.operation_name,
                        payload=job.payload,
                        error=Exception(error or "Unknown error"),
                        retry_count=job.retry_count,
                        policy_name=job.policy_name or "default",
                        metadata=job.metadata
                    )
                    
                    current_job.status = RetryStatus.EXHAUSTED.value
                    current_job.last_error = f"Rescheduled as {new_job.job_id if new_job else 'N/A'}"
        
        if not dry_run:
            update_retry_queue(list(job_map.values()))
        
        if once:
            break
        
        time.sleep(interval)


def handle_exhausted_job(job: RetryJob, policy: RetryPolicy) -> None:
    """Handle a job that has exhausted all retries."""
    policy_name = job.policy_name or "default"
    
    if policy_name == "enrichment_failure":
        send_alert(
            AlertLevel.WARNING,
            title="Enrichment Retries Exhausted",
            message=f"Lead enrichment failed after {job.retry_count} attempts. Proceeding with partial data.",
            metadata={
                "job_id": job.job_id,
                "operation": job.operation_name,
                "lead_id": job.payload.get("lead_id"),
                "error": job.last_error
            },
            source="retry_worker"
        )
    
    elif policy_name == "scraping_blocked":
        send_critical(
            title="Scraping Blocked - Immediate Action Required",
            message="Scraping operation was blocked. All scraping paused pending manual review.",
            metadata={
                "job_id": job.job_id,
                "operation": job.operation_name,
                "source": job.payload.get("source"),
                "error": job.last_error
            },
            source="retry_worker"
        )
    
    elif policy_name == "campaign_delivery_failure":
        send_alert(
            AlertLevel.WARNING,
            title="Campaign Delivery Failed",
            message=f"Campaign delivery failed after {job.retry_count} attempts. AE notified.",
            metadata={
                "job_id": job.job_id,
                "campaign_id": job.payload.get("campaign_id"),
                "error": job.last_error
            },
            source="retry_worker"
        )
    
    elif policy_name == "api_rate_limit":
        send_alert(
            AlertLevel.WARNING,
            title="API Rate Limit Exhausted",
            message=f"API rate limit retries exhausted after reaching max wait of 1hr.",
            metadata={
                "job_id": job.job_id,
                "operation": job.operation_name,
                "api": job.payload.get("api", job.payload.get("url", "unknown")),
                "error": job.last_error
            },
            source="retry_worker"
        )
    
    else:
        send_alert(
            AlertLevel.WARNING,
            title="Retry Exhausted",
            message=f"Operation {job.operation_name} failed after {job.retry_count} attempts.",
            metadata={
                "job_id": job.job_id,
                "operation": job.operation_name,
                "error": job.last_error
            },
            source="retry_worker"
        )
    
    log_event(
        EventType.SYSTEM_ERROR,
        {
            "job_id": job.job_id,
            "operation": job.operation_name,
            "status": "retry_exhausted",
            "retry_count": job.retry_count,
            "error": job.last_error,
            "policy": policy_name
        }
    )


def print_queue_status() -> None:
    """Print current retry queue status."""
    jobs = read_retry_queue()
    
    if not jobs:
        console.print("[dim]Retry queue is empty[/dim]")
        return
    
    table = Table(title="Retry Queue Status")
    table.add_column("Job ID", style="cyan", max_width=12)
    table.add_column("Operation", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Retries", style="magenta")
    table.add_column("Next Attempt", style="blue")
    table.add_column("Last Error", style="red", max_width=30)
    
    now = datetime.now(timezone.utc)
    
    for job in jobs[-20:]:
        try:
            next_attempt = datetime.fromisoformat(job.next_attempt_at.replace("Z", "+00:00"))
            if next_attempt <= now:
                next_str = "[green]READY[/green]"
            else:
                delta = next_attempt - now
                next_str = f"in {int(delta.total_seconds())}s"
        except Exception:
            next_str = job.next_attempt_at[:19]
        
        table.add_row(
            job.job_id[:12],
            job.operation_name[:20],
            job.status,
            str(job.retry_count),
            next_str,
            (job.last_error or "")[:30]
        )
    
    console.print(table)
    
    pending = sum(1 for j in jobs if j.status == RetryStatus.PENDING.value)
    completed = sum(1 for j in jobs if j.status == RetryStatus.COMPLETED.value)
    exhausted = sum(1 for j in jobs if j.status == RetryStatus.EXHAUSTED.value)
    
    console.print(f"\n[bold]Total: {len(jobs)} | Pending: {pending} | Completed: {completed} | Exhausted: {exhausted}[/bold]")


def main():
    parser = argparse.ArgumentParser(description="Process retry queue")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--dry-run", action="store_true", help="Don't execute jobs")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    parser.add_argument("--status", action="store_true", help="Show queue status and exit")
    
    args = parser.parse_args()
    
    if args.status:
        print_queue_status()
        return
    
    try:
        run_worker(once=args.once, dry_run=args.dry_run, interval=args.interval)
    except KeyboardInterrupt:
        console.print("\n[yellow]Worker stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]Worker error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
