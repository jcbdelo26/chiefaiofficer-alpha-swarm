#!/usr/bin/env python3
"""
Inngest Agent Scheduler

Event-driven scheduling for 24/7 autonomous swarm operation.
Runs agent tasks on schedule without requiring open terminals.

Setup:
1. pip install inngest
2. Set INNGEST_SIGNING_KEY in environment
3. Deploy to Railway (same app as webhook)
"""

import os
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import inngest
from inngest.fast_api import serve
from dotenv import load_dotenv

load_dotenv()

# Initialize Inngest client
inngest_client = inngest.Inngest(
    app_id="caio-alpha-swarm",
    is_production=os.getenv("ENVIRONMENT", "development") == "production"
)

# =============================================================================
# SCHEDULED FUNCTIONS
# =============================================================================

@inngest_client.create_function(
    fn_id="pipeline-scan",
    trigger=inngest.TriggerCron(cron="*/15 * * * *"),  # Every 15 minutes
)
async def pipeline_scan(ctx: inngest.Context, step: inngest.Step) -> Dict[str, Any]:
    """
    Scan pipeline every 15 minutes for:
    - Stale leads needing follow-up
    - Upcoming meetings needing prep
    - Ghost recovery opportunities
    """
    scan_time = datetime.now(timezone.utc).isoformat()
    
    # Step 1: Check for stale leads
    stale_leads = await step.run("check-stale-leads", check_stale_leads)
    
    # Step 2: Check for upcoming meetings
    upcoming_meetings = await step.run("check-meetings", check_upcoming_meetings)
    
    # Step 3: Check for ghost recovery
    ghost_candidates = await step.run("check-ghosts", check_ghost_candidates)
    
    # Step 4: Log results
    await step.run("log-scan", lambda: log_scan_results({
        "scan_time": scan_time,
        "stale_leads": stale_leads,
        "upcoming_meetings": upcoming_meetings,
        "ghost_candidates": ghost_candidates
    }))
    
    return {
        "status": "completed",
        "scan_time": scan_time,
        "stale_leads_count": len(stale_leads) if stale_leads else 0,
        "meetings_count": len(upcoming_meetings) if upcoming_meetings else 0,
        "ghost_count": len(ghost_candidates) if ghost_candidates else 0
    }


@inngest_client.create_function(
    fn_id="daily-health-check",
    trigger=inngest.TriggerCron(cron="0 8 * * *"),  # Daily at 8 AM
)
async def daily_health_check(ctx: inngest.Context, step: inngest.Step) -> Dict[str, Any]:
    """
    Daily system health check:
    - API connectivity
    - Queue depths
    - Error rates
    - Domain health scores
    """
    check_time = datetime.now(timezone.utc).isoformat()
    
    # Check all API connections
    api_status = await step.run("check-apis", check_api_connections)
    
    # Check queue depths
    queue_status = await step.run("check-queues", check_queue_depths)
    
    # Check error rates
    error_status = await step.run("check-errors", check_error_rates)
    
    # Generate report
    report = await step.run("generate-report", lambda: generate_health_report({
        "check_time": check_time,
        "api_status": api_status,
        "queue_status": queue_status,
        "error_status": error_status
    }))
    
    return report


@inngest_client.create_function(
    fn_id="weekly-icp-analysis",
    trigger=inngest.TriggerCron(cron="0 9 * * 1"),  # Every Monday at 9 AM
)
async def weekly_icp_analysis(ctx: inngest.Context, step: inngest.Step) -> Dict[str, Any]:
    """
    Weekly ICP analysis:
    - Analyze won vs lost deals
    - Update ICP scoring weights
    - Generate insights report
    """
    analysis_time = datetime.now(timezone.utc).isoformat()
    
    # Get deal outcomes
    outcomes = await step.run("get-outcomes", get_deal_outcomes)
    
    # Analyze patterns
    patterns = await step.run("analyze-patterns", lambda: analyze_deal_patterns(outcomes))
    
    # Update ICP weights
    await step.run("update-weights", lambda: update_icp_weights(patterns))
    
    return {
        "status": "completed",
        "analysis_time": analysis_time,
        "deals_analyzed": len(outcomes) if outcomes else 0,
        "patterns_found": len(patterns) if patterns else 0
    }


@inngest_client.create_function(
    fn_id="meeting-prep-trigger",
    trigger=inngest.TriggerCron(cron="0 20 * * *"),  # Daily at 8 PM
)
async def meeting_prep_trigger(ctx: inngest.Context, step: inngest.Step) -> Dict[str, Any]:
    """
    Trigger meeting prep for tomorrow's meetings.
    Runs at 8 PM to generate briefs overnight.
    """
    # Get tomorrow's meetings
    meetings = await step.run("get-tomorrow-meetings", get_tomorrow_meetings)
    
    if not meetings:
        return {"status": "no_meetings", "count": 0}
    
    # Generate prep for each meeting
    for meeting in meetings:
        await step.run(
            f"prep-{meeting.get('id', 'unknown')}",
            lambda m=meeting: generate_meeting_prep(m)
        )
    
    return {
        "status": "completed",
        "meetings_prepped": len(meetings)
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def check_stale_leads() -> list:
    """Check for leads that haven't been contacted in 3+ days."""
    # TODO: Query GHL for stale leads
    return []


async def check_upcoming_meetings() -> list:
    """Check for meetings in the next 24 hours."""
    # TODO: Query GHL/GCal for upcoming meetings
    return []


async def check_ghost_candidates() -> list:
    """Check for leads that stopped responding (ghost recovery)."""
    # TODO: Query GHL for ghost candidates
    return []


def log_scan_results(results: Dict[str, Any]) -> bool:
    """Log pipeline scan results."""
    log_dir = Path(".hive-mind/scheduler/scans")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, 'w') as f:
        json.dump(results, f, indent=2)
    return True


async def check_api_connections() -> Dict[str, bool]:
    """Check all API connections."""
    # TODO: Ping each API endpoint
    return {
        "ghl": True,
        "instantly": True,
        "supabase": True,
        "anthropic": True
    }


async def check_queue_depths() -> Dict[str, int]:
    """Check queue depths for each agent."""
    queue_dir = Path(".hive-mind/enrichment/queue")
    enrichment_count = len(list(queue_dir.glob("*.json"))) if queue_dir.exists() else 0
    
    return {
        "enrichment_queue": enrichment_count,
        "approval_queue": 0  # TODO: Count pending approvals
    }


async def check_error_rates() -> Dict[str, float]:
    """Calculate error rates for the last 24 hours."""
    # TODO: Analyze failure logs
    return {
        "error_rate_percent": 0.0,
        "warning_count": 0
    }


def generate_health_report(data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a health report."""
    all_apis_healthy = all(data.get("api_status", {}).values())
    low_queues = all(v < 100 for v in data.get("queue_status", {}).values())
    low_errors = data.get("error_status", {}).get("error_rate_percent", 0) < 5
    
    return {
        "overall_health": "healthy" if (all_apis_healthy and low_queues and low_errors) else "degraded",
        "details": data
    }


async def get_deal_outcomes() -> list:
    """Get won/lost deal data from ICP memory."""
    try:
        from core.self_learning_icp import icp_memory
        return icp_memory.deals
    except Exception as e:
        print(f"Error getting deal outcomes: {e}")
        return []


def analyze_deal_patterns(outcomes: list) -> Dict[str, Any]:
    """Analyze patterns in deal outcomes using PatternAnalyzer."""
    try:
        from core.self_learning_icp import pattern_analyzer
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in async context
            return pattern_analyzer.memory.generate_insights_report()
        else:
            return asyncio.run(pattern_analyzer.run_weekly_analysis())
    except Exception as e:
        print(f"Error analyzing patterns: {e}")
        return {}


def update_icp_weights(patterns: Dict[str, Any]) -> bool:
    """Update ICP scoring weights based on patterns."""
    try:
        from core.self_learning_icp import icp_memory
        # Weights are updated automatically when deals are recorded
        # This function just triggers a save
        icp_memory._save_weights()
        print(f"✓ ICP weights updated ({len(icp_memory.weights)} traits)")
        return True
    except Exception as e:
        print(f"Error updating weights: {e}")
        return False


async def get_tomorrow_meetings() -> list:
    """Get meetings scheduled for tomorrow."""
    # TODO: Query GHL/GCal
    return []


def generate_meeting_prep(meeting: Dict[str, Any]) -> Dict[str, Any]:
    """Generate meeting prep brief."""
    # TODO: Call RESEARCHER agent for prep
    return {"meeting_id": meeting.get("id"), "status": "prepared"}


# =============================================================================
# FASTAPI INTEGRATION
# =============================================================================

def get_inngest_serve():
    """Get the Inngest serve middleware for FastAPI."""
    return serve(
        client=inngest_client,
        functions=[
            pipeline_scan,
            daily_health_check,
            weekly_icp_analysis,
            meeting_prep_trigger
        ]
    )


if __name__ == "__main__":
    print("Inngest Agent Scheduler")
    print("=" * 50)
    print("Scheduled Functions:")
    print("  - pipeline-scan: Every 15 minutes")
    print("  - daily-health-check: Daily at 8 AM")
    print("  - weekly-icp-analysis: Monday at 9 AM")
    print("  - meeting-prep-trigger: Daily at 8 PM")
    print()
    print("To run locally with Inngest Dev Server:")
    print("  npx inngest-cli@latest dev")
    print()
    print("Then start your FastAPI app with the Inngest middleware.")
