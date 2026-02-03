"""
Reporting module for SDR automation.
Reads from events.jsonl and queue files to generate daily/weekly/monthly reports.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from collections import defaultdict

import yaml


PROJECT_ROOT = Path(__file__).parent.parent
HIVE_MIND = PROJECT_ROOT / ".hive-mind"
EVENTS_FILE = HIVE_MIND / "events.jsonl"
CONFIG_DIR = PROJECT_ROOT / "config"


def load_events(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    event_types: Optional[list[str]] = None
) -> list[dict[str, Any]]:
    """
    Load events from events.jsonl with optional filtering.
    
    Args:
        start_date: Filter events on or after this date
        end_date: Filter events before this date
        event_types: Filter to specific event types
    
    Returns:
        List of event dicts
    """
    events = []
    
    if not EVENTS_FILE.exists():
        return events
    
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    
                    # Parse timestamp
                    ts_str = event.get("timestamp", "")
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        
                        # Apply date filters
                        if start_date and ts < start_date:
                            continue
                        if end_date and ts >= end_date:
                            continue
                    
                    # Apply event type filter
                    if event_types and event.get("event_type") not in event_types:
                        continue
                    
                    events.append(event)
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception:
        pass
    
    return events


def load_sla_targets() -> dict[str, Any]:
    """Load SLA targets from sdr_rules.yaml."""
    rules_file = CONFIG_DIR / "sdr_rules.yaml"
    
    if not rules_file.exists():
        return {}
    
    try:
        with open(rules_file, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        return rules.get("sla_targets", {})
    except Exception:
        return {}


def load_performance_targets() -> dict[str, Any]:
    """Load outreach performance targets from sdr_rules.yaml."""
    rules_file = CONFIG_DIR / "sdr_rules.yaml"
    
    if not rules_file.exists():
        return {}
    
    try:
        with open(rules_file, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        return rules.get("outreach_performance", {})
    except Exception:
        return {}


def load_queue_file(filename: str) -> dict[str, Any]:
    """Load a queue JSON file as fallback when events are sparse."""
    queue_path = HIVE_MIND / filename
    
    if not queue_path.exists():
        return {}
    
    try:
        with open(queue_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def daily_report(date: datetime) -> dict[str, Any]:
    """
    Generate daily report for a specific date.
    
    Returns dict with:
        - leads_scraped: by source
        - enrichment: success rate
        - emails: sent/delivered/opened
        - replies: by sentiment
        - meetings_booked: count
    """
    # Normalize to start/end of day in UTC
    start = datetime(date.year, date.month, date.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    
    # Load all events for the day
    events = load_events(start_date=start, end_date=end)
    
    report = {
        "date": date.strftime("%Y-%m-%d"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leads_scraped": _count_leads_scraped(events, start),
        "enrichment": _calc_enrichment_stats(events, start),
        "emails": _calc_email_stats(events),
        "replies": _count_replies_by_sentiment(events),
        "meetings_booked": _count_meetings(events),
    }
    
    return report


def _count_leads_scraped(events: list[dict], date: datetime) -> dict[str, int]:
    """Count leads scraped by source from lead_segmented events."""
    by_source = defaultdict(int)
    total = 0
    
    # From events
    for event in events:
        if event.get("event_type") == "lead_segmented":
            source = event.get("payload", {}).get("source", "unknown")
            by_source[source] += 1
            total += 1
    
    # Fallback to scraped directory if no events
    if total == 0:
        scraped_dir = HIVE_MIND / "scraped"
        if scraped_dir.exists():
            date_str = date.strftime("%Y-%m-%d")
            for f in scraped_dir.glob(f"*{date_str}*.json"):
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                        count = len(data) if isinstance(data, list) else 1
                        source = f.stem.split("_")[1] if "_" in f.stem else "unknown"
                        by_source[source] += count
                        total += count
                except Exception:
                    pass
    
    return {"total": total, "by_source": dict(by_source)}


def _calc_enrichment_stats(events: list[dict], date: datetime) -> dict[str, Any]:
    """Calculate enrichment success rate from enrichment events."""
    completed = 0
    failed = 0
    
    for event in events:
        if event.get("event_type") == "enrichment_completed":
            completed += 1
        elif event.get("event_type") == "enrichment_failed":
            failed += 1
    
    # Fallback to enriched directory if no events
    if completed == 0 and failed == 0:
        enriched_dir = HIVE_MIND / "enriched"
        if enriched_dir.exists():
            date_str = date.strftime("%Y-%m-%d")
            for f in enriched_dir.glob(f"*{date_str}*.json"):
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                        if isinstance(data, list):
                            for lead in data:
                                if lead.get("email"):
                                    completed += 1
                                else:
                                    failed += 1
                except Exception:
                    pass
    
    total = completed + failed
    success_rate = round(completed / max(total, 1) * 100, 1)
    
    return {
        "completed": completed,
        "failed": failed,
        "total": total,
        "success_rate": success_rate
    }


def _calc_email_stats(events: list[dict]) -> dict[str, int]:
    """Calculate email stats from email events (placeholder if no events)."""
    sent = 0
    delivered = 0
    opened = 0
    
    for event in events:
        event_type = event.get("event_type", "")
        if event_type == "campaign_sent":
            sent += event.get("payload", {}).get("count", 1)
        elif event_type == "email_delivered":
            delivered += 1
        elif event_type == "email_opened":
            opened += 1
    
    # If no events, check outbox for queued emails
    if sent == 0:
        outbox_dir = HIVE_MIND / "outbox"
        if outbox_dir.exists():
            for f in outbox_dir.glob("*.json"):
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                        sent += len(data.get("leads", [])) if isinstance(data, dict) else 1
                except Exception:
                    pass
    
    return {
        "sent": sent,
        "delivered": delivered if delivered else sent,  # Assume delivered if no tracking
        "opened": opened,
        "open_rate": round(opened / max(sent, 1) * 100, 1)
    }


def _count_replies_by_sentiment(events: list[dict]) -> dict[str, Any]:
    """Count replies by sentiment from reply_classified events."""
    by_sentiment = defaultdict(int)
    total = 0
    
    for event in events:
        if event.get("event_type") == "reply_classified":
            payload = event.get("payload", {})
            objection_type = payload.get("objection_type", "unknown")
            
            # Map objection types to sentiment
            if objection_type in ["positive_interest", "buying_signals"]:
                sentiment = "positive"
            elif objection_type in ["not_interested", "already_have_solution"]:
                sentiment = "negative"
            else:
                sentiment = "neutral"
            
            by_sentiment[sentiment] += 1
            total += 1
    
    # Fallback to replies directory
    if total == 0:
        replies_dir = HIVE_MIND / "replies"
        if replies_dir.exists():
            for f in replies_dir.glob("*.json"):
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                        sentiment = data.get("sentiment", "neutral")
                        by_sentiment[sentiment] += 1
                        total += 1
                except Exception:
                    pass
    
    return {"total": total, "by_sentiment": dict(by_sentiment)}


def _count_meetings(events: list[dict]) -> int:
    """Count meetings booked from meeting events."""
    count = 0
    
    for event in events:
        if event.get("event_type") == "meeting_booked":
            count += 1
    
    return count


def weekly_report(week_start: datetime) -> dict[str, Any]:
    """
    Generate weekly report starting from week_start.
    
    Returns dict with:
        - icp_tier_distribution
        - conversion_funnel
        - ae_approval_trends
        - performance_vs_targets
    """
    # Normalize to start of week (Monday)
    days_since_monday = week_start.weekday()
    start = datetime(week_start.year, week_start.month, week_start.day, tzinfo=timezone.utc) - timedelta(days=days_since_monday)
    end = start + timedelta(days=7)
    
    events = load_events(start_date=start, end_date=end)
    sla_targets = load_sla_targets()
    perf_targets = load_performance_targets()
    
    report = {
        "week_start": start.strftime("%Y-%m-%d"),
        "week_end": (end - timedelta(days=1)).strftime("%Y-%m-%d"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "icp_tier_distribution": _calc_icp_distribution(events, start),
        "conversion_funnel": _calc_conversion_funnel(events),
        "ae_approval_trends": _calc_ae_approval_trends(events),
        "performance_vs_targets": _calc_performance_vs_targets(events, perf_targets),
    }
    
    return report


def _calc_icp_distribution(events: list[dict], start: datetime) -> dict[str, Any]:
    """Calculate ICP tier distribution from segmented outputs."""
    by_tier = defaultdict(int)
    total = 0
    
    for event in events:
        if event.get("event_type") == "lead_segmented":
            tier = event.get("payload", {}).get("tier", "unknown")
            tier_str = f"tier_{tier}" if isinstance(tier, int) else str(tier)
            by_tier[tier_str] += 1
            total += 1
    
    # Fallback to segmented directory
    if total == 0:
        segmented_dir = HIVE_MIND / "segmented"
        if segmented_dir.exists():
            for f in segmented_dir.glob("*.json"):
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                        if isinstance(data, list):
                            for lead in data:
                                tier = lead.get("icp_tier", "unknown")
                                by_tier[str(tier)] += 1
                                total += 1
                except Exception:
                    pass
    
    # Calculate percentages
    distribution = {}
    for tier, count in by_tier.items():
        distribution[tier] = {
            "count": count,
            "percentage": round(count / max(total, 1) * 100, 1)
        }
    
    return {"total": total, "distribution": distribution}


def _calc_conversion_funnel(events: list[dict]) -> dict[str, int]:
    """Calculate conversion funnel from events."""
    funnel = {
        "scraped": 0,
        "enriched": 0,
        "segmented": 0,
        "campaigns_created": 0,
        "emails_sent": 0,
        "replies": 0,
        "meetings": 0
    }
    
    for event in events:
        event_type = event.get("event_type", "")
        if event_type == "scrape_completed":
            funnel["scraped"] += event.get("payload", {}).get("count", 1)
        elif event_type == "enrichment_completed":
            funnel["enriched"] += 1
        elif event_type == "lead_segmented":
            funnel["segmented"] += 1
        elif event_type == "campaign_created":
            funnel["campaigns_created"] += 1
        elif event_type == "campaign_sent":
            funnel["emails_sent"] += event.get("payload", {}).get("count", 1)
        elif event_type == "reply_classified":
            funnel["replies"] += 1
        elif event_type == "meeting_booked":
            funnel["meetings"] += 1
    
    return funnel


def _calc_ae_approval_trends(events: list[dict]) -> dict[str, Any]:
    """Calculate AE approval/rejection trends from Gatekeeper queue."""
    approved = 0
    rejected = 0
    rejection_reasons = defaultdict(int)
    
    for event in events:
        event_type = event.get("event_type", "")
        if event_type == "campaign_approved":
            approved += 1
        elif event_type == "campaign_rejected":
            rejected += 1
            reason = event.get("payload", {}).get("reason", "unspecified")
            rejection_reasons[reason] += 1
    
    # Fallback to review_queue.json
    if approved == 0 and rejected == 0:
        queue_data = load_queue_file("review_queue.json")
        approved = len(queue_data.get("approved", []))
        rejected = len(queue_data.get("rejected", []))
        for item in queue_data.get("rejected", []):
            reason = item.get("rejection_reason", "unspecified")
            rejection_reasons[reason] += 1
    
    total = approved + rejected
    approval_rate = round(approved / max(total, 1) * 100, 1)
    
    return {
        "approved": approved,
        "rejected": rejected,
        "total_reviewed": total,
        "approval_rate": approval_rate,
        "top_rejection_reasons": dict(rejection_reasons)
    }


def _calc_performance_vs_targets(events: list[dict], targets: dict) -> dict[str, Any]:
    """Compare performance against SLA targets."""
    # Calculate actual metrics
    emails_sent = sum(1 for e in events if e.get("event_type") == "campaign_sent")
    emails_opened = sum(1 for e in events if e.get("event_type") == "email_opened")
    replies = sum(1 for e in events if e.get("event_type") == "reply_classified")
    positive_replies = sum(
        1 for e in events
        if e.get("event_type") == "reply_classified"
        and e.get("payload", {}).get("objection_type") == "positive_interest"
    )
    
    actual = {
        "open_rate": round(emails_opened / max(emails_sent, 1), 3),
        "reply_rate": round(replies / max(emails_sent, 1), 3),
        "positive_reply_ratio": round(positive_replies / max(replies, 1), 3)
    }
    
    # Compare against targets
    comparison = {}
    for metric in ["open_rate", "reply_rate", "positive_reply_ratio"]:
        target_config = targets.get(metric, {})
        target = target_config.get("target", 0)
        minimum = target_config.get("minimum", 0)
        
        actual_val = actual.get(metric, 0)
        
        if actual_val >= target:
            status = "exceeds"
        elif actual_val >= minimum:
            status = "meets"
        else:
            status = "below"
        
        comparison[metric] = {
            "actual": actual_val,
            "target": target,
            "minimum": minimum,
            "status": status
        }
    
    return comparison


def monthly_report(month_start: datetime) -> dict[str, Any]:
    """
    Generate monthly report for a specific month.
    
    Returns dict with:
        - roi_analysis (placeholder)
        - campaign_performance_comparison
        - compliance_audit_results
        - system_health_summary
    """
    # Normalize to start of month
    start = datetime(month_start.year, month_start.month, 1, tzinfo=timezone.utc)
    
    # Get end of month
    if month_start.month == 12:
        end = datetime(month_start.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(month_start.year, month_start.month + 1, 1, tzinfo=timezone.utc)
    
    events = load_events(start_date=start, end_date=end)
    
    report = {
        "month": start.strftime("%Y-%m"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "roi_analysis": _placeholder_roi_analysis(),
        "campaign_performance": _calc_campaign_performance(events),
        "compliance_audit": _calc_compliance_audit(events),
        "system_health": _calc_system_health(events),
    }
    
    return report


def _placeholder_roi_analysis() -> dict[str, Any]:
    """Placeholder for ROI analysis - requires revenue integration."""
    return {
        "status": "placeholder",
        "note": "ROI analysis requires CRM revenue data integration",
        "leads_generated": 0,
        "estimated_pipeline_value": 0,
        "cost_per_lead": 0,
        "meetings_booked": 0,
        "estimated_meeting_value": 0
    }


def _calc_campaign_performance(events: list[dict]) -> dict[str, Any]:
    """Calculate campaign performance comparison."""
    campaigns = defaultdict(lambda: {
        "sent": 0, "opened": 0, "replied": 0, "meetings": 0
    })
    
    for event in events:
        event_type = event.get("event_type", "")
        campaign_id = event.get("payload", {}).get("campaign_id", "unknown")
        
        if event_type == "campaign_sent":
            campaigns[campaign_id]["sent"] += event.get("payload", {}).get("count", 1)
        elif event_type == "email_opened":
            campaigns[campaign_id]["opened"] += 1
        elif event_type == "reply_classified":
            campaigns[campaign_id]["replied"] += 1
        elif event_type == "meeting_booked":
            campaigns[campaign_id]["meetings"] += 1
    
    # Calculate performance metrics for each campaign
    performance = {}
    for campaign_id, stats in campaigns.items():
        if stats["sent"] > 0:
            performance[campaign_id] = {
                **stats,
                "open_rate": round(stats["opened"] / stats["sent"] * 100, 1),
                "reply_rate": round(stats["replied"] / stats["sent"] * 100, 1),
                "meeting_rate": round(stats["meetings"] / stats["sent"] * 100, 1)
            }
    
    return {
        "campaign_count": len(performance),
        "campaigns": performance
    }


def _calc_compliance_audit(events: list[dict]) -> dict[str, Any]:
    """Count compliance_failed events by type."""
    by_type = defaultdict(int)
    total_violations = 0
    
    for event in events:
        if event.get("event_type") == "compliance_failed":
            violation_type = event.get("payload", {}).get("violation_type", "unknown")
            by_type[violation_type] += 1
            total_violations += 1
    
    return {
        "total_violations": total_violations,
        "by_type": dict(by_type),
        "status": "clean" if total_violations == 0 else "needs_review"
    }


def _calc_system_health(events: list[dict]) -> dict[str, Any]:
    """Calculate system health summary - retry counts, error rates."""
    retries = 0
    errors = 0
    sla_breaches = 0
    
    error_types = defaultdict(int)
    
    for event in events:
        event_type = event.get("event_type", "")
        
        if event_type == "retry_scheduled":
            retries += 1
        elif event_type == "system_error":
            errors += 1
            error_category = event.get("payload", {}).get("category", "unknown")
            error_types[error_category] += 1
        elif event_type in ["enrichment_failed", "scrape_failed"]:
            errors += 1
            error_types[event_type] += 1
        elif event_type == "sla_breach":
            sla_breaches += 1
    
    total_events = len(events)
    error_rate = round(errors / max(total_events, 1) * 100, 2)
    
    # Determine health status
    if error_rate < 1 and sla_breaches == 0:
        status = "healthy"
    elif error_rate < 5 and sla_breaches < 3:
        status = "degraded"
    else:
        status = "critical"
    
    return {
        "status": status,
        "total_events": total_events,
        "retry_count": retries,
        "error_count": errors,
        "error_rate_percent": error_rate,
        "sla_breaches": sla_breaches,
        "error_breakdown": dict(error_types)
    }
