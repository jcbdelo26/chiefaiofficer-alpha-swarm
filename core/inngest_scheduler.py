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
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import inngest
from inngest.fast_api import serve
from dotenv import load_dotenv
from core.trace_envelope import emit_tool_trace

load_dotenv()
logger = logging.getLogger("inngest_scheduler")

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
    result = {
        "status": "completed",
        "scan_time": scan_time,
        "stale_leads_count": len(stale_leads) if stale_leads else 0,
        "meetings_count": len(upcoming_meetings) if upcoming_meetings else 0,
        "ghost_count": len(ghost_candidates) if ghost_candidates else 0
    }
    _emit_scheduler_summary_trace("pipeline_scan", result)
    return result


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
    _emit_scheduler_summary_trace("daily_health_check", report)
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
    
    result = {
        "status": "completed",
        "analysis_time": analysis_time,
        "deals_analyzed": len(outcomes) if outcomes else 0,
        "patterns_found": len(patterns) if patterns else 0
    }
    _emit_scheduler_summary_trace("weekly_icp_analysis", result)
    return result


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
        result = {"status": "no_meetings", "count": 0}
        _emit_scheduler_summary_trace("meeting_prep_trigger", result)
        return result
    
    # Generate prep for each meeting
    for meeting in meetings:
        meeting_id = str(meeting.get("id", "unknown")).replace("/", "_")
        
        async def _prep(m=meeting):
            return await generate_meeting_prep(m)
        
        await step.run(
            f"prep-{meeting_id}",
            _prep
        )
    
    result = {
        "status": "completed",
        "meetings_prepped": len(meetings)
    }
    _emit_scheduler_summary_trace("meeting_prep_trigger", result)
    return result


@inngest_client.create_function(
    fn_id="daily-decay-detection",
    trigger=inngest.TriggerCron(cron="0 10 * * *"),  # Daily at 10 AM UTC
)
async def daily_decay_detection(ctx: inngest.Context, step: inngest.Step) -> Dict[str, Any]:
    """
    Run ghosting/stall detection on all tracked leads daily.

    Detects:
    - Ghosted: sent 72h+ ago, never opened
    - Stalled: opened 7d+ ago, never replied
    - Engaged-not-replied: 2+ opens, no reply (needs human review)

    Also expires stale OPERATOR batches (>24h pending).
    """
    # Step 1: Detect engagement decay
    decay_result = await step.run("detect-decay", _run_decay_detection)

    # Step 2: Expire stale operator batches
    expired = await step.run("expire-batches", _expire_stale_batches)

    # Step 3: Sync cadence signals
    sync_result = await step.run("sync-cadence", _sync_cadence_signals)

    result = {
        "status": "completed",
        "decay_detected": decay_result,
        "batches_expired": expired,
        "cadence_synced": sync_result,
    }
    _emit_scheduler_summary_trace("daily_decay_detection", result)
    return result


async def _run_decay_detection() -> Dict[str, Any]:
    """Run decay detection via LeadStatusManager."""
    try:
        from core.lead_signals import LeadStatusManager
        mgr = LeadStatusManager()
        result = mgr.detect_engagement_decay()
        count = len(result) if isinstance(result, list) else result
        logger.info("Decay detection: %s leads flagged", count)

        # Slack alert if significant decay
        if isinstance(result, list) and len(result) > 0:
            try:
                from core.alerts import send_warning
                summary = ", ".join(f"{r.get('email', '?')}: {r.get('new_status', '?')}" for r in result[:5])
                send_warning(f"Decay detection flagged {len(result)} leads: {summary}")
            except Exception:
                pass

        return {"flagged": count if isinstance(count, int) else len(result)}
    except Exception as e:
        logger.error("Decay detection error: %s", e)
        return {"error": str(e)}


async def _expire_stale_batches() -> int:
    """Expire pending OPERATOR batches older than 24 hours."""
    try:
        from execution.operator_outbound import OperatorOutbound
        op = OperatorOutbound()
        op.expire_stale_batches(max_age_hours=24)
        return 0
    except Exception as e:
        logger.error("Batch expiry error: %s", e)
        return -1


async def _sync_cadence_signals() -> Dict[str, Any]:
    """Sync cadence engine with signal loop."""
    try:
        from execution.cadence_engine import CadenceEngine
        cadence = CadenceEngine()
        result = cadence.sync_signals()
        return result if isinstance(result, dict) else {"synced": True}
    except Exception as e:
        logger.error("Cadence sync error: %s", e)
        return {"error": str(e)}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def check_stale_leads() -> list:
    """Check for leads that haven't been contacted in 3+ days."""
    data = await _gateway_execute(
        integration="ghl",
        action="read_pipeline",
        params={
            "status": "open",
            "stale_days": 3,
            "limit": 200,
        },
    )
    records = _extract_records(data, ["leads", "opportunities", "contacts", "results"])
    return records


async def check_upcoming_meetings() -> list:
    """Check for meetings in the next 24 hours."""
    now_utc = datetime.now(timezone.utc)
    window_end = now_utc + timedelta(hours=24)
    data = await _gateway_execute(
        integration="google_calendar",
        action="get_events",
        params={
            "start": now_utc.isoformat(),
            "end": window_end.isoformat(),
            "limit": 100,
        },
    )
    return _extract_records(data, ["events", "meetings", "items", "results"])


async def check_ghost_candidates() -> list:
    """Check for leads that stopped responding (ghost recovery)."""
    data = await _gateway_execute(
        integration="ghl",
        action="search_contacts",
        params={
            "segment": "ghost_recovery",
            "days_since_last_reply": 14,
            "limit": 200,
        },
    )
    return _extract_records(data, ["contacts", "leads", "results"])


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
    try:
        from core.unified_integration_gateway import get_gateway
        
        gateway = get_gateway()
        health = await gateway.health_check_all()
        status_map = {
            name: status.status.value in {"healthy", "degraded"}
            for name, status in health.items()
        }
        return status_map or {"gateway": False}
    except Exception as exc:
        logger.error("Failed to check API connections: %s", exc)
        return {"gateway": False}


async def check_queue_depths() -> Dict[str, int]:
    """Check queue depths for each agent."""
    queue_dir = Path(".hive-mind/enrichment/queue")
    enrichment_count = len(list(queue_dir.glob("*.json"))) if queue_dir.exists() else 0
    shadow_dir = Path(".hive-mind/shadow_mode_emails")
    approval_count = 0
    
    if shadow_dir.exists():
        for file_path in shadow_dir.glob("*.json"):
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("status", "pending") == "pending":
                    approval_count += 1
            except Exception as exc:
                logger.warning("Failed to parse approval queue item %s: %s", file_path, exc)
    
    return {
        "enrichment_queue": enrichment_count,
        "approval_queue": approval_count,
    }


async def check_error_rates() -> Dict[str, float]:
    """Calculate error rates for the last 24 hours."""
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(hours=24)
    
    total_events = 0
    error_events = 0
    warning_count = 0
    
    audit_file = Path(".hive-mind/integration_audit.json")
    if audit_file.exists():
        try:
            with open(audit_file, encoding="utf-8") as f:
                payload = json.load(f)
            for entry in payload.get("entries", []):
                ts = _parse_iso(entry.get("timestamp"))
                if ts and ts >= cutoff:
                    total_events += 1
                    if not entry.get("success", False):
                        error_events += 1
        except Exception as exc:
            logger.warning("Failed to inspect integration audit for error rates: %s", exc)
    
    frontend_log = Path(".hive-mind/frontend_errors.jsonl")
    if frontend_log.exists():
        try:
            with open(frontend_log, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = _parse_iso(event.get("timestamp"))
                    if ts and ts >= cutoff:
                        warning_count += 1
        except Exception as exc:
            logger.warning("Failed to inspect frontend error log: %s", exc)
    
    error_rate = (error_events / total_events * 100) if total_events else 0.0
    return {
        "error_rate_percent": round(error_rate, 2),
        "warning_count": warning_count,
        "total_events": total_events,
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
        logger.error("Error getting deal outcomes: %s", e)
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
        logger.error("Error analyzing deal patterns: %s", e)
        return {}


def update_icp_weights(patterns: Dict[str, Any]) -> bool:
    """Update ICP scoring weights based on patterns."""
    try:
        from core.self_learning_icp import icp_memory
        # Weights are updated automatically when deals are recorded
        # This function just triggers a save
        icp_memory._save_weights()
        logger.info("✓ ICP weights updated (%s traits)", len(icp_memory.weights))
        return True
    except Exception as e:
        logger.error("Error updating ICP weights: %s", e)
        return False


async def get_tomorrow_meetings() -> list:
    """Get meetings scheduled for tomorrow."""
    now_utc = datetime.now(timezone.utc)
    tomorrow_start = (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = tomorrow_start + timedelta(days=1)
    
    data = await _gateway_execute(
        integration="google_calendar",
        action="get_events",
        params={
            "start": tomorrow_start.isoformat(),
            "end": tomorrow_end.isoformat(),
            "limit": 200,
        },
    )
    return _extract_records(data, ["events", "meetings", "items", "results"])


async def generate_meeting_prep(meeting: Dict[str, Any]) -> Dict[str, Any]:
    """Generate meeting prep brief."""
    meeting_id = meeting.get("id")
    contact_id = meeting.get("contact_id") or meeting.get("contactId")
    
    if not contact_id:
        return {
            "meeting_id": meeting_id,
            "status": "skipped",
            "reason": "missing_contact_id",
        }
    
    try:
        from core.call_prep_agent import get_call_prep_agent
        
        call_prep_agent = get_call_prep_agent()
        update_ghl = os.getenv("ENVIRONMENT", "development") == "production"
        prep = await call_prep_agent.prepare_contact_for_call(
            contact_id=str(contact_id),
            update_ghl=update_ghl,
        )
        return {
            "meeting_id": meeting_id,
            "status": "prepared",
            "contact_id": contact_id,
            "summary": prep.summary,
            "confidence_score": prep.confidence_score,
            "ghl_updated": update_ghl,
        }
    except Exception as exc:
        logger.error("Meeting prep generation failed for meeting %s: %s", meeting_id, exc)
        return {
            "meeting_id": meeting_id,
            "status": "failed",
            "contact_id": contact_id,
            "error": str(exc),
        }


def _extract_records(payload: Any, keys: List[str]) -> List[Dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


async def _gateway_execute(integration: str, action: str, params: Dict[str, Any]) -> Any:
    start = time.time()
    error_code = None
    error_message = None
    output: Any = None
    status = "failure"
    try:
        from core.unified_integration_gateway import get_gateway
        
        gateway = get_gateway()
        result = await gateway.execute(
            integration=integration,
            action=action,
            params=params,
            agent="SCHEDULER",
        )
        if not result.success:
            error_code = "GATEWAY_EXECUTION_FAILED"
            error_message = result.error
            logger.warning(
                "Gateway execution failed for %s.%s: %s",
                integration,
                action,
                result.error,
            )
            return None
        output = result.data
        status = "success"
        return result.data
    except Exception as exc:
        error_code = "GATEWAY_EXECUTION_EXCEPTION"
        error_message = str(exc)
        logger.error("Gateway execution error for %s.%s: %s", integration, action, exc)
        return None
    finally:
        try:
            emit_tool_trace(
                agent="SCHEDULER",
                tool_name=f"Inngest.{integration}.{action}",
                tool_input=params,
                tool_output=output,
                retrieved_context_refs=[],
                status=status,
                duration_ms=(time.time() - start) * 1000,
                error_code=error_code,
                error_message=error_message,
            )
        except Exception as trace_exc:
            logger.debug("Failed to emit scheduler trace: %s", trace_exc)


def _parse_iso(value: Any) -> Any:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _emit_scheduler_summary_trace(function_name: str, output: Dict[str, Any]) -> None:
    try:
        emit_tool_trace(
            agent="SCHEDULER",
            tool_name=f"Inngest.{function_name}",
            tool_input={},
            tool_output=output,
            retrieved_context_refs=[],
            status="success",
            duration_ms=0,
        )
    except Exception as exc:
        logger.debug("Failed to emit scheduler summary trace for %s: %s", function_name, exc)


# =============================================================================
# FASTAPI INTEGRATION
# =============================================================================

def get_inngest_serve(app):
    """Register Inngest functions on a FastAPI app.

    In inngest v0.5+, serve() takes the FastAPI app and modifies it in-place.
    """
    serve(
        app,
        client=inngest_client,
        functions=[
            pipeline_scan,
            daily_health_check,
            weekly_icp_analysis,
            meeting_prep_trigger,
            daily_decay_detection,
        ],
        serve_origin=os.getenv("INNGEST_SERVE_ORIGIN"),
        serve_path="/inngest",
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
