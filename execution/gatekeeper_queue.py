#!/usr/bin/env python3
"""
Gatekeeper Agent - Campaign Review Queue & Dashboard
====================================================
Manages the AE review queue and provides dashboard for campaign approval.

Features:
- Queue campaigns for AE review
- Approve/reject campaigns
- Track review metrics
- Web dashboard interface
- Approval Engine integration
- SMS/Email escalation via NotificationManager

Usage:
    python execution/gatekeeper_queue.py --input campaigns.json
    python execution/gatekeeper_queue.py --serve  # Start dashboard
"""

import os
import sys
import json
import uuid
import argparse
import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict, field
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from core.approval_engine import (
    ApprovalEngine, 
    ApprovalPolicy, 
    ApprovalRequest, 
    ApprovalResult
)
from core.notifications import NotificationManager

console = Console()


class ReviewStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    EXPIRED = "expired"


class UrgencyLevel(Enum):
    NORMAL = "normal"
    URGENT = "urgent"
    CRITICAL = "critical"


@dataclass
class ReviewItem:
    """Campaign review item."""
    review_id: str
    campaign_id: str
    campaign_name: str
    campaign_type: str
    lead_count: int
    avg_icp_score: float
    segment: str
    email_preview: Dict[str, str]
    status: str
    queued_at: str
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    edits: Optional[Dict[str, Any]] = None
    expires_at: Optional[str] = None
    # Context Engineering: Semantic anchors for informed review
    semantic_anchors: List[str] = field(default_factory=list)
    tier: str = ""
    rpi_workflow: bool = False
    # Enhanced fields for approval engine integration
    urgency: str = "normal"
    approval_request_id: Optional[str] = None
    approval_source: Optional[str] = None  # slack, sms, email, dashboard
    escalation_level: int = 0
    deadline: Optional[str] = None
    notification_sent_at: Optional[str] = None
    sms_sent_at: Optional[str] = None
    email_fallback_sent_at: Optional[str] = None


@dataclass
class ReviewQueue:
    """Review queue state."""
    pending: List[ReviewItem] = field(default_factory=list)
    approved: List[ReviewItem] = field(default_factory=list)
    rejected: List[ReviewItem] = field(default_factory=list)
    total_queued: int = 0
    avg_review_time_hours: float = 0.0


# NotificationManager removed - imported from core.notifications



class GatekeeperQueue:
    """
    Manages the campaign review queue.
    
    All campaigns must pass through this gate before being sent.
    AEs can approve, reject, or edit campaigns.
    """
    
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        base_path = Path(__file__).parent.parent / ".hive-mind"
        
        if test_mode:
            self.queue_path = base_path / "testing" / "test_review_queue.json"
        else:
            self.queue_path = base_path / "review_queue.json"
        
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue = self._load_queue()
        
        # Load learnings for self-annealing
        self.learnings_path = base_path / "learnings.json"
    
    def _load_queue(self) -> ReviewQueue:
        """Load queue from disk."""
        if self.queue_path.exists():
            try:
                with open(self.queue_path) as f:
                    data = json.load(f)
                
                pending = [ReviewItem(**item) for item in data.get("pending", [])]
                approved = [ReviewItem(**item) for item in data.get("approved", [])]
                rejected = [ReviewItem(**item) for item in data.get("rejected", [])]
                
                return ReviewQueue(
                    pending=pending,
                    approved=approved,
                    rejected=rejected,
                    total_queued=data.get("total_queued", 0),
                    avg_review_time_hours=data.get("avg_review_time_hours", 0.0)
                )
            except Exception as e:
                console.print(f"[yellow]Failed to load queue: {e}[/yellow]")
        
        return ReviewQueue()
    
    def _save_queue(self):
        """Save queue to disk."""
        data = {
            "pending": [asdict(item) for item in self.queue.pending],
            "approved": [asdict(item) for item in self.queue.approved[-100:]],  # Keep last 100
            "rejected": [asdict(item) for item in self.queue.rejected[-100:]],
            "total_queued": self.queue.total_queued,
            "avg_review_time_hours": self.queue.avg_review_time_hours,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        with open(self.queue_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def queue_campaign(self, campaign: Dict[str, Any]) -> ReviewItem:
        """Queue a campaign for AE review."""
        
        # Extract email preview from first sequence step
        sequence = campaign.get("sequence", [])
        email_preview = {}
        if sequence:
            first_step = sequence[0]
            email_preview = {
                "subject_a": first_step.get("subject_a", ""),
                "subject_b": first_step.get("subject_b", ""),
                "body": first_step.get("body", first_step.get("body_a", ""))[:500] + "..."
            }
        
        # Extract semantic anchors from RPI workflow (Context Engineering)
        semantic_anchors = campaign.get("semantic_anchors", [])
        tier = campaign.get("tier", "")
        rpi_workflow = campaign.get("rpi_workflow", False) or bool(semantic_anchors)
        
        review_item = ReviewItem(
            review_id=str(uuid.uuid4()),
            campaign_id=campaign.get("campaign_id", str(uuid.uuid4())),
            campaign_name=campaign.get("name", f"{tier}_{campaign.get('template', 'campaign')}"),
            campaign_type=campaign.get("campaign_type", campaign.get("template", "unknown")),
            lead_count=campaign.get("lead_count", 0),
            avg_icp_score=campaign.get("avg_icp_score", 0),
            segment=campaign.get("segment", tier),
            email_preview=email_preview,
            status=ReviewStatus.PENDING.value,
            queued_at=datetime.now(timezone.utc).isoformat(),
            semantic_anchors=semantic_anchors,
            tier=tier,
            rpi_workflow=rpi_workflow
        )
        
        self.queue.pending.append(review_item)
        self.queue.total_queued += 1
        self._save_queue()
        
        return review_item
    
    def queue_campaigns_from_file(self, input_file: Path) -> List[ReviewItem]:
        """Queue campaigns from a JSON file."""
        
        console.print(f"\n[bold blue]* GATEKEEPER: Queuing campaigns for review[/bold blue]")
        
        with open(input_file) as f:
            data = json.load(f)
        
        campaigns = data.get("campaigns", [])
        queued = []
        
        for campaign in campaigns:
            item = self.queue_campaign(campaign)
            queued.append(item)
            console.print(f"[dim]Queued: {item.campaign_name}[/dim]")
        
        console.print(f"\n[green][OK] Queued {len(queued)} campaigns for review[/green]")
        
        return queued
    
    def approve(self, review_id: str, reviewer: str = "AE") -> Optional[ReviewItem]:
        """Approve a campaign."""
        
        for i, item in enumerate(self.queue.pending):
            if item.review_id == review_id:
                item.status = ReviewStatus.APPROVED.value
                item.reviewed_at = datetime.now(timezone.utc).isoformat()
                item.reviewed_by = reviewer
                
                self.queue.approved.append(item)
                self.queue.pending.pop(i)
                self._save_queue()
                self._update_avg_review_time(item)
                
                console.print(f"[green][OK] Approved: {item.campaign_name}[/green]")
                return item
        
        console.print(f"[red]Review ID not found: {review_id}[/red]")
        return None
    
    def reject(self, review_id: str, reason: str, reviewer: str = "AE") -> Optional[ReviewItem]:
        """Reject a campaign."""
        
        for i, item in enumerate(self.queue.pending):
            if item.review_id == review_id:
                item.status = ReviewStatus.REJECTED.value
                item.reviewed_at = datetime.now(timezone.utc).isoformat()
                item.reviewed_by = reviewer
                item.rejection_reason = reason
                
                self.queue.rejected.append(item)
                self.queue.pending.pop(i)
                self._save_queue()
                self._update_avg_review_time(item)
                self._record_rejection_learning(item, reason)
                
                console.print(f"[yellow][X] Rejected: {item.campaign_name}[/yellow]")
                console.print(f"[dim]   Reason: {reason}[/dim]")
                return item
        
        console.print(f"[red]Review ID not found: {review_id}[/red]")
        return None
    
    def edit(self, review_id: str, edits: Dict[str, Any], reviewer: str = "AE") -> Optional[ReviewItem]:
        """Edit a campaign before approval."""
        
        for item in self.queue.pending:
            if item.review_id == review_id:
                item.status = ReviewStatus.EDITED.value
                item.edits = edits
                item.reviewed_by = reviewer
                
                # Apply edits to preview
                if "subject" in edits:
                    item.email_preview["subject_a"] = edits["subject"]
                if "body" in edits:
                    item.email_preview["body"] = edits["body"][:500] + "..."
                
                self._save_queue()
                console.print(f"[blue]** Edited: {item.campaign_name}[/blue]")
                return item
        
        console.print(f"[red]Review ID not found: {review_id}[/red]")
        return None
    
    def _update_avg_review_time(self, item: ReviewItem):
        """Update average review time metric."""
        
        if item.queued_at and item.reviewed_at:
            try:
                queued = datetime.fromisoformat(item.queued_at)
                reviewed = datetime.fromisoformat(item.reviewed_at)
                hours = (reviewed - queued).total_seconds() / 3600
                
                # Rolling average
                total_reviewed = len(self.queue.approved) + len(self.queue.rejected)
                if total_reviewed > 0:
                    self.queue.avg_review_time_hours = (
                        (self.queue.avg_review_time_hours * (total_reviewed - 1) + hours) / total_reviewed
                    )
            except Exception:
                pass
    
    def _record_rejection_learning(self, item: ReviewItem, reason: str):
        """Record rejection for self-annealing."""
        
        learning = {
            "type": "campaign_rejection",
            "campaign_type": item.campaign_type,
            "segment": item.segment,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Load existing learnings
        learnings = {"learnings": []}
        if self.learnings_path.exists():
            try:
                with open(self.learnings_path) as f:
                    learnings = json.load(f)
            except Exception:
                pass
        
        learnings["learnings"].append(learning)
        
        # Keep last 1000 learnings
        learnings["learnings"] = learnings["learnings"][-1000:]
        
        with open(self.learnings_path, "w") as f:
            json.dump(learnings, f, indent=2)
    
    def get_pending(self) -> List[ReviewItem]:
        """Get all pending reviews."""
        return self.queue.pending
    
    def get_stats(self) -> Dict[str, Any]:
        """Get review queue statistics."""
        
        total_reviewed = len(self.queue.approved) + len(self.queue.rejected)
        
        return {
            "pending_count": len(self.queue.pending),
            "approved_count": len(self.queue.approved),
            "rejected_count": len(self.queue.rejected),
            "total_queued": self.queue.total_queued,
            "approval_rate": len(self.queue.approved) / max(1, total_reviewed),
            "avg_review_time_hours": round(self.queue.avg_review_time_hours, 2),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    
    def print_queue(self):
        """Print the review queue."""
        
        # Stats panel
        stats = self.get_stats()
        stats_text = f"""
Pending: {stats['pending_count']} | Approved: {stats['approved_count']} | Rejected: {stats['rejected_count']}
Approval Rate: {stats['approval_rate']:.0%} | Avg Review Time: {stats['avg_review_time_hours']:.1f}h
        """
        console.print(Panel(stats_text.strip(), title="* Queue Statistics"))
        
        # Pending table
        if self.queue.pending:
            table = Table(title="Pending Reviews")
            table.add_column("ID", style="dim")
            table.add_column("Campaign", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Leads", style="yellow")
            table.add_column("ICP Score", style="magenta")
            table.add_column("Queued", style="dim")
            
            for item in self.queue.pending[:10]:
                table.add_row(
                    item.review_id[:8],
                    item.campaign_name[:30],
                    item.campaign_type[:15],
                    str(item.lead_count),
                    f"{item.avg_icp_score:.0f}",
                    item.queued_at[:16]
                )
            
            console.print(table)
        else:
            console.print("[dim]No pending reviews[/dim]")


class EnhancedGatekeeperQueue(GatekeeperQueue):
    """
    Enhanced Gatekeeper with Approval Engine integration and notification management.
    
    Features:
    - Urgency-based routing (normal, urgent, critical)
    - Integration with ApprovalEngine for policy-based handling
    - SMS/Email escalation via NotificationManager
    - Timeout handling with auto-escalation
    - Dashboard integration points
    """
    
    def __init__(self, test_mode: bool = False):
        super().__init__(test_mode)
        self.approval_engine = ApprovalEngine()
        self.notification_manager = NotificationManager()
        self.websocket_callbacks: List[Callable] = []
        self.approval_stats = {
            "submitted": 0,
            "auto_approved": 0,
            "manually_approved": 0,
            "rejected": 0,
            "escalated": 0,
            "timed_out": 0,
            "by_source": {"slack": 0, "sms": 0, "email": 0, "dashboard": 0}
        }
    
    def calculate_urgency(self, item: ReviewItem) -> str:
        """
        Calculate urgency based on context.
        
        - Critical: Blocking action, high-value leads, tier1
        - Urgent: <30min deadline, tier2 with high ICP
        - Normal: Everything else
        """
        if item.deadline:
            try:
                deadline = datetime.fromisoformat(item.deadline)
                time_remaining = deadline - datetime.now(timezone.utc)
                
                if time_remaining < timedelta(minutes=0):
                    return UrgencyLevel.CRITICAL.value
                elif time_remaining < timedelta(minutes=30):
                    return UrgencyLevel.URGENT.value
            except ValueError:
                pass
        
        # Tier-based urgency
        if item.tier == "tier1" and item.lead_count >= 50:
            return UrgencyLevel.CRITICAL.value
        
        if item.tier == "tier1" or (item.tier == "tier2" and item.avg_icp_score >= 80):
            return UrgencyLevel.URGENT.value
        
        # High value based on ICP and lead count
        if item.avg_icp_score >= 90 and item.lead_count >= 100:
            return UrgencyLevel.CRITICAL.value
        
        return UrgencyLevel.NORMAL.value
    
    async def submit_for_review(
        self,
        item: ReviewItem,
        urgency: Optional[str] = None
    ) -> str:
        """
        Submit item for review and route to appropriate approval path.
        
        Returns the review_id.
        """
        # Calculate urgency if not provided
        if urgency:
            item.urgency = urgency
        else:
            item.urgency = self.calculate_urgency(item)
        
        # Submit to approval engine
        approval_result = await self.route_to_approval_engine(item)
        item.approval_request_id = approval_result.request_id
        
        # Check if auto-approved by policy
        if approval_result.auto_approved and approval_result.approved:
            self.approval_stats["auto_approved"] += 1
            item.status = ReviewStatus.APPROVED.value
            item.reviewed_at = datetime.now(timezone.utc).isoformat()
            item.reviewed_by = "auto_policy"
            self.queue.approved.append(item)
        else:
            self.queue.pending.append(item)
            self.queue.total_queued += 1
            
            # Send notifications based on urgency
            await self._send_urgency_based_notifications(item)
        
        self._save_queue()
        self.approval_stats["submitted"] += 1
        
        # Notify dashboard via WebSocket
        await self._notify_websocket("item_added", item)
        
        return item.review_id
    
    async def route_to_approval_engine(self, item: ReviewItem) -> ApprovalResult:
        """Route through approval engine for policy-based handling."""
        # Map campaign type to action type for approval engine
        action_type = "send_email" if item.campaign_type in ["email_sequence", "email"] else "bulk_email"
        
        # Use the existing approval engine's request_approval method
        result = await self.approval_engine.request_approval(
            action_type=action_type,
            agent_name="gatekeeper",
            parameters={
                "campaign_id": item.campaign_id,
                "campaign_name": item.campaign_name,
                "lead_count": item.lead_count,
                "avg_icp_score": item.avg_icp_score,
                "tier": item.tier,
            },
            context={
                "rpi_workflow": item.rpi_workflow,
                "urgency": item.urgency,
                "segment": item.segment,
            }
        )
        
        return result
    
    async def _send_urgency_based_notifications(self, item: ReviewItem):
        """Send notifications based on urgency level."""
        urgency = item.urgency
        
        if urgency == UrgencyLevel.CRITICAL.value:
            # Critical: Slack + SMS + Email + escalation chain
            await self.notification_manager.escalate(item, level=3)
            item.notification_sent_at = datetime.now(timezone.utc).isoformat()
            item.sms_sent_at = datetime.now(timezone.utc).isoformat()
            item.email_fallback_sent_at = datetime.now(timezone.utc).isoformat()
            
        elif urgency == UrgencyLevel.URGENT.value:
            # Urgent: Slack + SMS
            await self.notification_manager.escalate(item, level=2)
            item.notification_sent_at = datetime.now(timezone.utc).isoformat()
            item.sms_sent_at = datetime.now(timezone.utc).isoformat()
            
        else:
            # Normal: Slack only
            await self.notification_manager.send_slack_notification(item)
            item.notification_sent_at = datetime.now(timezone.utc).isoformat()
    
    async def check_and_escalate_timeouts(self):
        """Check pending items and escalate as needed."""
        now = datetime.now(timezone.utc)
        
        for item in self.get_pending():
            try:
                queued_at = datetime.fromisoformat(item.queued_at)
                # Ensure queued_at is timezone-aware
                if queued_at.tzinfo is None:
                    queued_at = queued_at.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            
            time_waiting = now - queued_at
            
            # 4+ hours: Auto-reject with notification
            if time_waiting > timedelta(hours=4):
                await self.auto_reject_with_notification(
                    item, 
                    "Approval timeout exceeded (4+ hours)"
                )
                self.approval_stats["timed_out"] += 1
                continue
            
            # 2+ hours: Send email fallback if not already sent
            if time_waiting > timedelta(hours=2) and not item.email_fallback_sent_at:
                contacts = self.notification_manager.escalation_contacts.get("level2", [])
                for contact in contacts:
                    email = contact.get("email")
                    if email:
                        await self.notification_manager.send_email_fallback(email, item)
                item.email_fallback_sent_at = datetime.now(timezone.utc).isoformat()
                self._save_queue()
            
            # 30+ min for urgent items: Send SMS if not already sent
            if (time_waiting > timedelta(minutes=30) and 
                item.urgency == UrgencyLevel.URGENT.value and 
                not item.sms_sent_at):
                contacts = self.notification_manager.escalation_contacts.get("level2", [])
                for contact in contacts:
                    phone = contact.get("phone")
                    if phone:
                        msg = f"OVERDUE: Campaign '{item.campaign_name}' awaiting approval for {int(time_waiting.total_seconds() / 60)}min"
                        await self.notification_manager.send_sms_alert(phone, msg)
                item.sms_sent_at = datetime.now(timezone.utc).isoformat()
                self._save_queue()
    
    async def auto_reject_with_notification(self, item: ReviewItem, reason: str):
        """Auto-reject an item and notify stakeholders."""
        # Update item status
        item.status = ReviewStatus.EXPIRED.value
        item.reviewed_at = datetime.now(timezone.utc).isoformat()
        item.reviewed_by = "system_timeout"
        item.rejection_reason = reason
        
        # Move from pending to rejected
        self.queue.pending = [i for i in self.queue.pending if i.review_id != item.review_id]
        self.queue.rejected.append(item)
        self._save_queue()
        
        # Update approval engine
        if item.approval_request_id:
            try:
                await self.approval_engine.process_approval(
                    item.approval_request_id,
                    approved=False,
                    approver="system_timeout",
                    reason=reason
                )
            except (ValueError, KeyError):
                pass
        
        # Send notifications
        await self.notification_manager.send_slack_notification(item, channel="#approvals-alerts")
        
        # Notify dashboard
        await self._notify_websocket("item_rejected", item)
        
        console.print(f"[yellow][TIMEOUT] Auto-rejected: {item.campaign_name} - {reason}[/yellow]")
    
    async def handle_approval_response(
        self,
        review_id: str,
        approved: bool,
        approver: str,
        reason: str = "",
        edits: Optional[Dict] = None,
        source: str = "dashboard"
    ) -> Optional[ReviewItem]:
        """
        Handle approval response from any channel (Slack, SMS, Email, Dashboard).
        
        Args:
            review_id: The review ID
            approved: Whether the item is approved
            approver: Who approved/rejected
            reason: Reason for rejection (if rejected)
            edits: Optional edits to apply before approval
            source: Source channel (slack, sms, email, dashboard)
        
        Returns:
            The updated ReviewItem or None if not found
        """
        # Find the item
        item = None
        for i in self.queue.pending:
            if i.review_id == review_id:
                item = i
                break
        
        if not item:
            console.print(f"[red]Review ID not found: {review_id}[/red]")
            return None
        
        # Track approval source
        item.approval_source = source
        self.approval_stats["by_source"][source] = self.approval_stats["by_source"].get(source, 0) + 1
        
        if approved:
            # Apply edits if provided
            if edits:
                if "subject" in edits:
                    item.email_preview["subject_a"] = edits["subject"]
                if "body" in edits:
                    item.email_preview["body"] = edits["body"][:500] + "..."
                item.edits = edits
            
            # Update in approval engine
            if item.approval_request_id:
                try:
                    await self.approval_engine.process_approval(
                        item.approval_request_id,
                        approved=True,
                        approver=approver,
                        reason=reason or "Approved"
                    )
                except (ValueError, KeyError):
                    pass
            
            result = self.approve(review_id, approver)
            if result:
                self.approval_stats["manually_approved"] += 1
                await self._notify_websocket("item_approved", result)
            return result
        else:
            # Rejection
            if item.approval_request_id:
                try:
                    await self.approval_engine.process_approval(
                        item.approval_request_id,
                        approved=False,
                        approver=approver,
                        reason=reason
                    )
                except (ValueError, KeyError):
                    pass
            
            result = self.reject(review_id, reason, approver)
            if result:
                self.approval_stats["rejected"] += 1
                await self._notify_websocket("item_rejected", result)
            return result
    
    def register_websocket_callback(self, callback: Callable):
        """Register a callback for WebSocket notifications."""
        self.websocket_callbacks.append(callback)
    
    async def _notify_websocket(self, event_type: str, item: ReviewItem):
        """Notify all registered WebSocket callbacks."""
        # console.print(f"[debug] Notifying {len(self.websocket_callbacks)} callbacks for {event_type}")
        for callback in self.websocket_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_type, asdict(item))
                else:
                    result = callback(event_type, asdict(item))
                    if asyncio.iscoroutine(result) or (hasattr(result, '__await__') and not isinstance(result, (str, bytes))):
                        await result
            except Exception as e:
                console.print(f"[yellow]WebSocket callback error: {e}[/yellow]")
    
    def get_enhanced_stats(self) -> Dict[str, Any]:
        """Get enhanced statistics including approval engine and notification stats."""
        base_stats = self.get_stats()
        
        return {
            **base_stats,
            "approval_stats": self.approval_stats,
            "notification_stats": self.notification_manager.get_stats(),
            "pending_by_urgency": {
                "normal": len([i for i in self.queue.pending if i.urgency == "normal"]),
                "urgent": len([i for i in self.queue.pending if i.urgency == "urgent"]),
                "critical": len([i for i in self.queue.pending if i.urgency == "critical"])
            },
            "approval_engine_pending": len(self.approval_engine.get_pending_requests())
        }


# Simple web dashboard using Flask
def create_dashboard_app():
    """Create Flask dashboard app."""
    try:
        from flask import Flask, render_template_string, request, jsonify, redirect, url_for
    except ImportError:
        console.print("[yellow]Flask not installed. Install with: pip install flask[/yellow]")
        return None
    
    app = Flask(__name__)
    gatekeeper = GatekeeperQueue()
    
    DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>* GATEKEEPER - Campaign Review Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 30px;
        }
        h1 { 
            font-size: 2rem; 
            background: linear-gradient(90deg, #00d4ff, #7c3aed);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 24px;
            text-align: center;
        }
        .stat-card h3 { color: #888; font-size: 0.9rem; margin-bottom: 10px; }
        .stat-card .value { font-size: 2.5rem; font-weight: bold; }
        .pending .value { color: #fbbf24; }
        .approved .value { color: #34d399; }
        .rejected .value { color: #f87171; }
        .rate .value { color: #60a5fa; }
        
        .review-list { margin-top: 20px; }
        .review-card {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 16px;
            transition: all 0.3s ease;
        }
        .review-card:hover {
            background: rgba(255,255,255,0.06);
            transform: translateY(-2px);
        }
        .review-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }
        .campaign-name { font-size: 1.2rem; font-weight: 600; color: #fff; }
        .campaign-meta { display: flex; gap: 20px; color: #888; font-size: 0.9rem; }
        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .badge-tier1 { background: #34d399; color: #000; }
        .badge-tier2 { background: #60a5fa; color: #000; }
        .badge-tier3 { background: #fbbf24; color: #000; }
        
        .email-preview {
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            padding: 16px;
            margin: 16px 0;
            font-family: monospace;
            font-size: 0.9rem;
        }
        .email-preview .subject { color: #60a5fa; margin-bottom: 10px; }
        .email-preview .body { color: #a0a0a0; white-space: pre-wrap; }
        
        .actions { display: flex; gap: 12px; margin-top: 16px; }
        .btn {
            padding: 10px 24px;
            border-radius: 8px;
            border: none;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        .btn-approve { background: #34d399; color: #000; }
        .btn-approve:hover { background: #2dd4bf; transform: scale(1.05); }
        .btn-reject { background: #f87171; color: #000; }
        .btn-reject:hover { background: #fb7185; }
        .btn-edit { background: #60a5fa; color: #000; }
        .btn-edit:hover { background: #818cf8; }
        
        .empty-state {
            text-align: center;
            padding: 60px;
            color: #666;
        }
        .empty-state h2 { margin-bottom: 10px; }
        
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: rgba(0,0,0,0.8);
            z-index: 1000;
        }
        .modal-content {
            background: #1a1a2e;
            max-width: 500px;
            margin: 100px auto;
            padding: 30px;
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .modal-content h2 { margin-bottom: 20px; }
        .modal-content textarea {
            width: 100%;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.2);
            background: rgba(0,0,0,0.3);
            color: #fff;
            font-size: 1rem;
            margin-bottom: 16px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>* GATEKEEPER</h1>
            <span>Campaign Review Dashboard</span>
        </header>
        
        <div class="stats">
            <div class="stat-card pending">
                <h3>PENDING</h3>
                <div class="value">{{ stats.pending_count }}</div>
            </div>
            <div class="stat-card approved">
                <h3>APPROVED</h3>
                <div class="value">{{ stats.approved_count }}</div>
            </div>
            <div class="stat-card rejected">
                <h3>REJECTED</h3>
                <div class="value">{{ stats.rejected_count }}</div>
            </div>
            <div class="stat-card rate">
                <h3>APPROVAL RATE</h3>
                <div class="value">{{ (stats.approval_rate * 100)|round|int }}%</div>
            </div>
        </div>
        
        <h2>Pending Reviews</h2>
        <div class="review-list">
            {% if pending %}
                {% for item in pending %}
                <div class="review-card">
                    <div class="review-header">
                        <div>
                            <span class="campaign-name">{{ item.campaign_name }}</span>
                            <span class="badge badge-{{ item.segment.split('_')[0] if '_' in item.segment else 'tier3' }}">
                                {{ item.segment }}
                            </span>
                        </div>
                        <div class="campaign-meta">
                            <span>{{ item.lead_count }} leads</span>
                            <span>ICP: {{ item.avg_icp_score|round|int }}</span>
                            <span>{{ item.campaign_type }}</span>
                        </div>
                    </div>
                    
                    <div class="email-preview">
                        <div class="subject">Subject A: {{ item.email_preview.subject_a }}</div>
                        <div class="subject">Subject B: {{ item.email_preview.subject_b }}</div>
                        <div class="body">{{ item.email_preview.body }}</div>
                    </div>
                    
                    {% if item.semantic_anchors %}
                    <div class="semantic-anchors" style="background: rgba(124, 58, 237, 0.1); border: 1px solid rgba(124, 58, 237, 0.3); border-radius: 8px; padding: 12px; margin: 16px 0;">
                        <div style="color: #a78bfa; font-weight: 600; font-size: 0.85rem; margin-bottom: 8px;">* Context (from RPI workflow)</div>
                        {% for anchor in item.semantic_anchors %}
                        <div style="color: #e0e0e0; font-size: 0.85rem; padding: 4px 0;">• {{ anchor }}</div>
                        {% endfor %}
                    </div>
                    {% endif %}
                    
                    <div class="actions">
                        <form action="/approve/{{ item.review_id }}" method="POST" style="display:inline;">
                            <button type="submit" class="btn btn-approve">* Approve</button>
                        </form>
                        <button class="btn btn-reject" onclick="showRejectModal('{{ item.review_id }}')">* Reject</button>
                        <button class="btn btn-edit">* Edit</button>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <div class="empty-state">
                    <h2>* All caught up!</h2>
                    <p>No campaigns pending review.</p>
                </div>
            {% endif %}
        </div>
    </div>
    
    <div id="rejectModal" class="modal">
        <div class="modal-content">
            <h2>Reject Campaign</h2>
            <form id="rejectForm" method="POST">
                <textarea name="reason" placeholder="Reason for rejection..." rows="4" required></textarea>
                <button type="submit" class="btn btn-reject">Confirm Reject</button>
                <button type="button" class="btn" onclick="hideRejectModal()">Cancel</button>
            </form>
        </div>
    </div>
    
    <script>
        function showRejectModal(reviewId) {
            document.getElementById('rejectModal').style.display = 'block';
            document.getElementById('rejectForm').action = '/reject/' + reviewId;
        }
        function hideRejectModal() {
            document.getElementById('rejectModal').style.display = 'none';
        }
    </script>
</body>
</html>
    """
    
    @app.route('/')
    def dashboard():
        stats = gatekeeper.get_stats()
        pending = gatekeeper.get_pending()
        return render_template_string(DASHBOARD_HTML, stats=stats, pending=[asdict(p) for p in pending])
    
    @app.route('/approve/<review_id>', methods=['POST'])
    def approve(review_id):
        gatekeeper.approve(review_id)
        return redirect(url_for('dashboard'))
    
    @app.route('/reject/<review_id>', methods=['POST'])
    def reject(review_id):
        reason = request.form.get('reason', 'No reason provided')
        gatekeeper.reject(review_id, reason)
        return redirect(url_for('dashboard'))
    
    @app.route('/api/stats')
    def api_stats():
        return jsonify(gatekeeper.get_stats())
    
    @app.route('/api/pending')
    def api_pending():
        return jsonify([asdict(p) for p in gatekeeper.get_pending()])
    
    # === HANDOFF QUEUE ROUTES ===
    
    from core.handoff_queue import HandoffQueue
    handoff_queue = HandoffQueue()
    
    HANDOFF_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>* HANDOFFS - Escalation Queue</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 30px;
        }
        h1 { 
            font-size: 2rem; 
            background: linear-gradient(90deg, #f59e0b, #ef4444);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .nav-link {
            color: #60a5fa;
            text-decoration: none;
            font-size: 0.9rem;
        }
        .nav-link:hover { text-decoration: underline; }
        .stats {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 24px;
            text-align: center;
        }
        .stat-card h3 { color: #888; font-size: 0.9rem; margin-bottom: 10px; }
        .stat-card .value { font-size: 2.5rem; font-weight: bold; }
        .pending .value { color: #fbbf24; }
        .acknowledged .value { color: #60a5fa; }
        .closed .value { color: #34d399; }
        .overdue .value { color: #f87171; }
        .critical .value { color: #ef4444; }
        
        .handoff-list { margin-top: 20px; }
        .handoff-card {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 12px;
            transition: all 0.3s ease;
        }
        .handoff-card:hover {
            background: rgba(255,255,255,0.06);
            transform: translateY(-2px);
        }
        .handoff-card.priority-critical { border-left: 4px solid #ef4444; }
        .handoff-card.priority-block { border-left: 4px solid #ef4444; }
        .handoff-card.priority-high { border-left: 4px solid #f59e0b; }
        .handoff-card.priority-medium { border-left: 4px solid #3b82f6; }
        .handoff-card.priority-low { border-left: 4px solid #6b7280; }
        
        .handoff-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        .handoff-trigger { font-size: 1.1rem; font-weight: 600; color: #fff; }
        .handoff-meta { display: flex; gap: 16px; color: #888; font-size: 0.85rem; }
        
        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        .badge-critical { background: #ef4444; color: #fff; }
        .badge-block { background: #ef4444; color: #fff; }
        .badge-high { background: #f59e0b; color: #000; }
        .badge-medium { background: #3b82f6; color: #fff; }
        .badge-low { background: #6b7280; color: #fff; }
        
        .sla-countdown {
            font-size: 0.9rem;
            padding: 4px 10px;
            border-radius: 6px;
        }
        .sla-ok { background: rgba(34, 197, 94, 0.2); color: #22c55e; }
        .sla-warning { background: rgba(245, 158, 11, 0.2); color: #f59e0b; }
        .sla-breach { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
        
        .lead-info {
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
            padding: 12px;
            margin: 12px 0;
            font-size: 0.9rem;
        }
        .lead-info .label { color: #888; }
        .lead-info .value { color: #fff; margin-left: 8px; }
        
        .reply-snippet {
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            padding: 12px;
            margin: 12px 0;
            font-family: monospace;
            font-size: 0.85rem;
            color: #a0a0a0;
            white-space: pre-wrap;
        }
        
        .actions { display: flex; gap: 10px; margin-top: 12px; }
        .btn {
            padding: 8px 20px;
            border-radius: 6px;
            border: none;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 0.9rem;
        }
        .btn-ack { background: #3b82f6; color: #fff; }
        .btn-ack:hover { background: #2563eb; }
        .btn-close { background: #22c55e; color: #000; }
        .btn-close:hover { background: #16a34a; }
        
        .empty-state {
            text-align: center;
            padding: 60px;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>* HANDOFFS</h1>
            <div>
                <a href="/" class="nav-link">← Back to Campaigns</a>
                <span style="color:#666;margin:0 10px;">|</span>
                <span>Escalation Queue</span>
            </div>
        </header>
        
        <div class="stats">
            <div class="stat-card pending">
                <h3>PENDING</h3>
                <div class="value">{{ stats.pending_count }}</div>
            </div>
            <div class="stat-card acknowledged">
                <h3>IN PROGRESS</h3>
                <div class="value">{{ stats.acknowledged_count }}</div>
            </div>
            <div class="stat-card closed">
                <h3>CLOSED</h3>
                <div class="value">{{ stats.closed_count }}</div>
            </div>
            <div class="stat-card overdue">
                <h3>OVERDUE</h3>
                <div class="value">{{ stats.overdue_count }}</div>
            </div>
            <div class="stat-card critical">
                <h3>CRITICAL</h3>
                <div class="value">{{ stats.by_priority.critical }}</div>
            </div>
        </div>
        
        <h2>Pending Handoffs</h2>
        <div class="handoff-list">
            {% if handoffs %}
                {% for h in handoffs %}
                <div class="handoff-card priority-{{ h.priority }}">
                    <div class="handoff-header">
                        <div>
                            <span class="handoff-trigger">{{ h.trigger }}</span>
                            <span class="badge badge-{{ h.priority }}">{{ h.priority }}</span>
                        </div>
                        <div class="handoff-meta">
                            <span>→ {{ h.destination }}</span>
                            <span class="sla-countdown {{ h.sla_status }}">SLA: {{ h.sla_remaining }}</span>
                        </div>
                    </div>
                    
                    <div class="lead-info">
                        <span class="label">Lead:</span><span class="value">{{ h.lead_name or h.lead_email or h.lead_id }}</span>
                        {% if h.lead_company %}<span class="label" style="margin-left:20px;">Company:</span><span class="value">{{ h.lead_company }}</span>{% endif %}
                        {% if h.lead_title %}<span class="label" style="margin-left:20px;">Title:</span><span class="value">{{ h.lead_title }}</span>{% endif %}
                    </div>
                    
                    {% if h.reply_snippet %}
                    <div class="reply-snippet">"{{ h.reply_snippet }}"</div>
                    {% endif %}
                    
                    <div class="actions">
                        <form action="/handoffs/acknowledge/{{ h.handoff_id }}" method="POST" style="display:inline;">
                            <button type="submit" class="btn btn-ack">* Acknowledge</button>
                        </form>
                        <form action="/handoffs/close/{{ h.handoff_id }}" method="POST" style="display:inline;">
                            <button type="submit" class="btn btn-close">* Close</button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <div class="empty-state">
                    <h2>* No pending handoffs!</h2>
                    <p>All escalations have been handled.</p>
                </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
    """
    
    @app.route('/handoffs')
    def handoffs_dashboard():
        from datetime import datetime, timezone
        stats = handoff_queue.get_stats()
        pending = handoff_queue.get_pending()
        
        # Sort by priority (critical/block first, then high, medium, low)
        priority_order = {"critical": 0, "block": 0, "high": 1, "medium": 2, "low": 3}
        sorted_pending = sorted(pending, key=lambda t: priority_order.get(t.get("priority", "low"), 99))
        
        # Calculate SLA countdown for each
        now = datetime.now(timezone.utc)
        for h in sorted_pending:
            try:
                sla_due = datetime.fromisoformat(h["sla_due_at"].replace("Z", "+00:00"))
                diff = sla_due - now
                total_seconds = diff.total_seconds()
                
                if total_seconds < 0:
                    h["sla_status"] = "sla-breach"
                    h["sla_remaining"] = "OVERDUE"
                elif total_seconds < 300:  # < 5 min
                    h["sla_status"] = "sla-warning"
                    mins = int(total_seconds / 60)
                    h["sla_remaining"] = f"{mins}m left"
                elif total_seconds < 3600:  # < 1 hour
                    h["sla_status"] = "sla-warning"
                    mins = int(total_seconds / 60)
                    h["sla_remaining"] = f"{mins}m left"
                else:
                    h["sla_status"] = "sla-ok"
                    hours = int(total_seconds / 3600)
                    mins = int((total_seconds % 3600) / 60)
                    h["sla_remaining"] = f"{hours}h {mins}m left"
            except Exception:
                h["sla_status"] = "sla-ok"
                h["sla_remaining"] = "N/A"
        
        return render_template_string(HANDOFF_HTML, stats=stats, handoffs=sorted_pending)
    
    @app.route('/handoffs/acknowledge/<handoff_id>', methods=['POST'])
    def acknowledge_handoff(handoff_id):
        handoff_queue.acknowledge(handoff_id)
        return redirect(url_for('handoffs_dashboard'))
    
    @app.route('/handoffs/close/<handoff_id>', methods=['POST'])
    def close_handoff(handoff_id):
        handoff_queue.close(handoff_id)
        return redirect(url_for('handoffs_dashboard'))
    
    @app.route('/api/handoffs')
    def api_handoffs():
        return jsonify(handoff_queue.get_pending())
    
    @app.route('/api/handoffs/stats')
    def api_handoff_stats():
        return jsonify(handoff_queue.get_stats())
    
    # === REPORTS ROUTES ===
    
    from datetime import datetime, timedelta
    from core.reporting import daily_report, weekly_report, monthly_report
    
    REPORTS_INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>* REPORTS - Alpha Swarm Analytics</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 30px;
        }
        h1 { 
            font-size: 2rem; 
            background: linear-gradient(90deg, #00d4ff, #7c3aed);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .nav-link { color: #60a5fa; text-decoration: none; }
        .nav-link:hover { text-decoration: underline; }
        
        .report-cards {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 24px;
            margin-top: 30px;
        }
        .report-card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 32px;
            text-align: center;
            transition: all 0.3s ease;
        }
        .report-card:hover {
            background: rgba(255,255,255,0.1);
            transform: translateY(-4px);
        }
        .report-card h2 { font-size: 1.5rem; margin-bottom: 12px; }
        .report-card p { color: #888; margin-bottom: 20px; }
        .report-card a {
            display: inline-block;
            padding: 12px 28px;
            background: linear-gradient(90deg, #3b82f6, #7c3aed);
            color: #fff;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
        }
        .report-card a:hover { opacity: 0.9; }
        
        .daily { border-top: 4px solid #34d399; }
        .weekly { border-top: 4px solid #60a5fa; }
        .monthly { border-top: 4px solid #a78bfa; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>* REPORTS</h1>
            <a href="/" class="nav-link">← Back to Dashboard</a>
        </header>
        
        <div class="report-cards">
            <div class="report-card daily">
                <h2>* Daily Report</h2>
                <p>Leads scraped, enrichment rates, emails sent, replies received</p>
                <a href="/reports/daily">View Today</a>
            </div>
            <div class="report-card weekly">
                <h2>* Weekly Report</h2>
                <p>ICP distribution, conversion funnel, AE approval trends</p>
                <a href="/reports/weekly">View This Week</a>
            </div>
            <div class="report-card monthly">
                <h2>* Monthly Report</h2>
                <p>ROI analysis, campaign comparison, compliance audit</p>
                <a href="/reports/monthly">View This Month</a>
            </div>
        </div>
    </div>
</body>
</html>
    """
    
    DAILY_REPORT_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>* Daily Report - {{ report.date }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 30px;
        }
        h1 { font-size: 1.8rem; color: #34d399; }
        .nav-link { color: #60a5fa; text-decoration: none; }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-box {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        .stat-box h3 { color: #888; font-size: 0.85rem; margin-bottom: 8px; }
        .stat-box .value { font-size: 2rem; font-weight: bold; }
        .stat-box.green .value { color: #34d399; }
        .stat-box.blue .value { color: #60a5fa; }
        .stat-box.yellow .value { color: #fbbf24; }
        .stat-box.purple .value { color: #a78bfa; }
        
        .section {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
        }
        .section h2 { margin-bottom: 16px; font-size: 1.2rem; }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        th { color: #888; font-weight: 600; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>* Daily Report: {{ report.date }}</h1>
            <a href="/reports" class="nav-link">← Back to Reports</a>
        </header>
        
        <div class="stats-grid">
            <div class="stat-box green">
                <h3>LEADS SCRAPED</h3>
                <div class="value">{{ report.leads_scraped.total }}</div>
            </div>
            <div class="stat-box blue">
                <h3>ENRICHMENT RATE</h3>
                <div class="value">{{ report.enrichment.success_rate }}%</div>
            </div>
            <div class="stat-box yellow">
                <h3>EMAILS SENT</h3>
                <div class="value">{{ report.emails.sent }}</div>
            </div>
            <div class="stat-box purple">
                <h3>MEETINGS BOOKED</h3>
                <div class="value">{{ report.meetings_booked }}</div>
            </div>
        </div>
        
        <div class="section">
            <h2>** Leads by Source</h2>
            <table>
                <tr><th>Source</th><th>Count</th></tr>
                {% for source, count in report.leads_scraped.by_source.items() %}
                <tr><td>{{ source }}</td><td>{{ count }}</td></tr>
                {% else %}
                <tr><td colspan="2">No data</td></tr>
                {% endfor %}
            </table>
        </div>
        
        <div class="section">
            <h2>* Enrichment Stats</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Completed</td><td>{{ report.enrichment.completed }}</td></tr>
                <tr><td>Failed</td><td>{{ report.enrichment.failed }}</td></tr>
                <tr><td>Success Rate</td><td>{{ report.enrichment.success_rate }}%</td></tr>
            </table>
        </div>
        
        <div class="section">
            <h2>* Email Stats</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Sent</td><td>{{ report.emails.sent }}</td></tr>
                <tr><td>Delivered</td><td>{{ report.emails.delivered }}</td></tr>
                <tr><td>Opened</td><td>{{ report.emails.opened }}</td></tr>
                <tr><td>Open Rate</td><td>{{ report.emails.open_rate }}%</td></tr>
            </table>
        </div>
        
        <div class="section">
            <h2>* Replies by Sentiment</h2>
            <table>
                <tr><th>Sentiment</th><th>Count</th></tr>
                {% for sentiment, count in report.replies.by_sentiment.items() %}
                <tr><td>{{ sentiment }}</td><td>{{ count }}</td></tr>
                {% else %}
                <tr><td colspan="2">No replies</td></tr>
                {% endfor %}
            </table>
        </div>
    </div>
</body>
</html>
    """
    
    WEEKLY_REPORT_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>* Weekly Report - {{ report.week_start }} to {{ report.week_end }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 30px;
        }
        h1 { font-size: 1.8rem; color: #60a5fa; }
        .nav-link { color: #60a5fa; text-decoration: none; }
        
        .section {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
        }
        .section h2 { margin-bottom: 16px; font-size: 1.2rem; }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        th { color: #888; font-weight: 600; }
        
        .status-exceeds { color: #34d399; }
        .status-meets { color: #fbbf24; }
        .status-below { color: #f87171; }
        
        .funnel-bar {
            height: 24px;
            background: linear-gradient(90deg, #3b82f6, #7c3aed);
            border-radius: 4px;
            margin: 4px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>* Weekly Report: {{ report.week_start }} to {{ report.week_end }}</h1>
            <a href="/reports" class="nav-link">← Back to Reports</a>
        </header>
        
        <div class="section">
            <h2>* ICP Tier Distribution</h2>
            <table>
                <tr><th>Tier</th><th>Count</th><th>Percentage</th></tr>
                {% for tier, data in report.icp_tier_distribution.distribution.items() %}
                <tr>
                    <td>{{ tier }}</td>
                    <td>{{ data.count }}</td>
                    <td>{{ data.percentage }}%</td>
                </tr>
                {% else %}
                <tr><td colspan="3">No data</td></tr>
                {% endfor %}
            </table>
        </div>
        
        <div class="section">
            <h2>* Conversion Funnel</h2>
            <table>
                <tr><th>Stage</th><th>Count</th><th>Visual</th></tr>
                {% set max_val = [report.conversion_funnel.scraped, report.conversion_funnel.enriched, report.conversion_funnel.segmented, 1]|max %}
                <tr>
                    <td>Scraped</td>
                    <td>{{ report.conversion_funnel.scraped }}</td>
                    <td><div class="funnel-bar" style="width: {{ (report.conversion_funnel.scraped / max_val * 100)|int }}%"></div></td>
                </tr>
                <tr>
                    <td>Enriched</td>
                    <td>{{ report.conversion_funnel.enriched }}</td>
                    <td><div class="funnel-bar" style="width: {{ (report.conversion_funnel.enriched / max_val * 100)|int }}%"></div></td>
                </tr>
                <tr>
                    <td>Segmented</td>
                    <td>{{ report.conversion_funnel.segmented }}</td>
                    <td><div class="funnel-bar" style="width: {{ (report.conversion_funnel.segmented / max_val * 100)|int }}%"></div></td>
                </tr>
                <tr>
                    <td>Campaigns Created</td>
                    <td>{{ report.conversion_funnel.campaigns_created }}</td>
                    <td><div class="funnel-bar" style="width: {{ (report.conversion_funnel.campaigns_created / max_val * 100)|int }}%"></div></td>
                </tr>
                <tr>
                    <td>Emails Sent</td>
                    <td>{{ report.conversion_funnel.emails_sent }}</td>
                    <td><div class="funnel-bar" style="width: {{ (report.conversion_funnel.emails_sent / max_val * 100)|int }}%"></div></td>
                </tr>
                <tr>
                    <td>Replies</td>
                    <td>{{ report.conversion_funnel.replies }}</td>
                    <td><div class="funnel-bar" style="width: {{ (report.conversion_funnel.replies / max_val * 100)|int }}%"></div></td>
                </tr>
                <tr>
                    <td>Meetings</td>
                    <td>{{ report.conversion_funnel.meetings }}</td>
                    <td><div class="funnel-bar" style="width: {{ (report.conversion_funnel.meetings / max_val * 100)|int }}%"></div></td>
                </tr>
            </table>
        </div>
        
        <div class="section">
            <h2>[OK] AE Approval Trends</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Approved</td><td>{{ report.ae_approval_trends.approved }}</td></tr>
                <tr><td>Rejected</td><td>{{ report.ae_approval_trends.rejected }}</td></tr>
                <tr><td>Approval Rate</td><td>{{ report.ae_approval_trends.approval_rate }}%</td></tr>
            </table>
            {% if report.ae_approval_trends.top_rejection_reasons %}
            <h3 style="margin-top: 16px; font-size: 1rem;">Top Rejection Reasons</h3>
            <table>
                <tr><th>Reason</th><th>Count</th></tr>
                {% for reason, count in report.ae_approval_trends.top_rejection_reasons.items() %}
                <tr><td>{{ reason }}</td><td>{{ count }}</td></tr>
                {% endfor %}
            </table>
            {% endif %}
        </div>
        
        <div class="section">
            <h2>* Performance vs Targets</h2>
            <table>
                <tr><th>Metric</th><th>Actual</th><th>Target</th><th>Minimum</th><th>Status</th></tr>
                {% for metric, data in report.performance_vs_targets.items() %}
                <tr>
                    <td>{{ metric }}</td>
                    <td>{{ data.actual }}</td>
                    <td>{{ data.target }}</td>
                    <td>{{ data.minimum }}</td>
                    <td class="status-{{ data.status }}">{{ data.status|upper }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>
</body>
</html>
    """
    
    MONTHLY_REPORT_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>* Monthly Report - {{ report.month }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 30px;
        }
        h1 { font-size: 1.8rem; color: #a78bfa; }
        .nav-link { color: #60a5fa; text-decoration: none; }
        
        .section {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
        }
        .section h2 { margin-bottom: 16px; font-size: 1.2rem; }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        th { color: #888; font-weight: 600; }
        
        .health-healthy { color: #34d399; }
        .health-degraded { color: #fbbf24; }
        .health-critical { color: #f87171; }
        
        .placeholder {
            background: rgba(251, 191, 36, 0.1);
            border: 1px dashed #fbbf24;
            border-radius: 8px;
            padding: 16px;
            color: #fbbf24;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>* Monthly Report: {{ report.month }}</h1>
            <a href="/reports" class="nav-link">← Back to Reports</a>
        </header>
        
        <div class="section">
            <h2>* ROI Analysis</h2>
            {% if report.roi_analysis.status == 'placeholder' %}
            <div class="placeholder">
                {{ report.roi_analysis.note }}
            </div>
            {% else %}
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Leads Generated</td><td>{{ report.roi_analysis.leads_generated }}</td></tr>
                <tr><td>Pipeline Value</td><td>${{ report.roi_analysis.estimated_pipeline_value }}</td></tr>
                <tr><td>Cost per Lead</td><td>${{ report.roi_analysis.cost_per_lead }}</td></tr>
            </table>
            {% endif %}
        </div>
        
        <div class="section">
            <h2>* Campaign Performance</h2>
            <p style="color: #888; margin-bottom: 12px;">{{ report.campaign_performance.campaign_count }} campaigns this month</p>
            <table>
                <tr><th>Campaign</th><th>Sent</th><th>Open Rate</th><th>Reply Rate</th><th>Meetings</th></tr>
                {% for campaign_id, data in report.campaign_performance.campaigns.items() %}
                <tr>
                    <td>{{ campaign_id[:8] }}...</td>
                    <td>{{ data.sent }}</td>
                    <td>{{ data.open_rate }}%</td>
                    <td>{{ data.reply_rate }}%</td>
                    <td>{{ data.meetings }}</td>
                </tr>
                {% else %}
                <tr><td colspan="5">No campaign data</td></tr>
                {% endfor %}
            </table>
        </div>
        
        <div class="section">
            <h2>** Compliance Audit</h2>
            <table>
                <tr><th>Status</th><th>Total Violations</th></tr>
                <tr>
                    <td class="health-{{ 'healthy' if report.compliance_audit.status == 'clean' else 'critical' }}">
                        {{ report.compliance_audit.status|upper }}
                    </td>
                    <td>{{ report.compliance_audit.total_violations }}</td>
                </tr>
            </table>
            {% if report.compliance_audit.by_type %}
            <h3 style="margin-top: 16px; font-size: 1rem;">Violations by Type</h3>
            <table>
                <tr><th>Type</th><th>Count</th></tr>
                {% for vtype, count in report.compliance_audit.by_type.items() %}
                <tr><td>{{ vtype }}</td><td>{{ count }}</td></tr>
                {% endfor %}
            </table>
            {% endif %}
        </div>
        
        <div class="section">
            <h2>* System Health</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr>
                    <td>Status</td>
                    <td class="health-{{ report.system_health.status }}">{{ report.system_health.status|upper }}</td>
                </tr>
                <tr><td>Total Events</td><td>{{ report.system_health.total_events }}</td></tr>
                <tr><td>Retry Count</td><td>{{ report.system_health.retry_count }}</td></tr>
                <tr><td>Error Count</td><td>{{ report.system_health.error_count }}</td></tr>
                <tr><td>Error Rate</td><td>{{ report.system_health.error_rate_percent }}%</td></tr>
                <tr><td>SLA Breaches</td><td>{{ report.system_health.sla_breaches }}</td></tr>
            </table>
            {% if report.system_health.error_breakdown %}
            <h3 style="margin-top: 16px; font-size: 1rem;">Error Breakdown</h3>
            <table>
                <tr><th>Error Type</th><th>Count</th></tr>
                {% for etype, count in report.system_health.error_breakdown.items() %}
                <tr><td>{{ etype }}</td><td>{{ count }}</td></tr>
                {% endfor %}
            </table>
            {% endif %}
        </div>
    </div>
</body>
</html>
    """
    
    @app.route('/reports')
    def reports_index():
        return render_template_string(REPORTS_INDEX_HTML)
    
    @app.route('/reports/daily')
    def reports_daily():
        date_str = request.args.get('date')
        if date_str:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            date = datetime.now()
        report = daily_report(date)
        return render_template_string(DAILY_REPORT_HTML, report=report)
    
    @app.route('/reports/weekly')
    def reports_weekly():
        date_str = request.args.get('date')
        if date_str:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            date = datetime.now()
        report = weekly_report(date)
        return render_template_string(WEEKLY_REPORT_HTML, report=report)
    
    @app.route('/reports/monthly')
    def reports_monthly():
        date_str = request.args.get('date')
        if date_str:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            date = datetime.now()
        report = monthly_report(date)
        return render_template_string(MONTHLY_REPORT_HTML, report=report)
    
    @app.route('/api/reports/daily')
    def api_reports_daily():
        date_str = request.args.get('date')
        if date_str:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            date = datetime.now()
        return jsonify(daily_report(date))
    
    @app.route('/api/reports/weekly')
    def api_reports_weekly():
        date_str = request.args.get('date')
        if date_str:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            date = datetime.now()
        return jsonify(weekly_report(date))
    
    @app.route('/api/reports/monthly')
    def api_reports_monthly():
        date_str = request.args.get('date')
        if date_str:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            date = datetime.now()
        return jsonify(monthly_report(date))
    
    return app


def run_test_mode(input_file: Path, campaign_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Run gatekeeper in test mode to verify workflow without affecting production.
    
    Args:
        input_file: Path to campaigns JSON file
        campaign_id: Optional specific campaign ID to test
        
    Returns:
        Test results dictionary
    """
    console.print(f"\n[bold yellow]* TEST MODE: Running gatekeeper workflow simulation[/bold yellow]")
    
    base_path = Path(__file__).parent.parent / ".hive-mind" / "testing"
    base_path.mkdir(parents=True, exist_ok=True)
    results_path = base_path / "gatekeeper_test_results.json"
    
    results = {
        "test_mode": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "input_file": str(input_file),
        "campaign_id_filter": campaign_id,
        "steps": [],
        "success": True,
        "errors": []
    }
    
    try:
        # Step 1: Initialize test queue
        gatekeeper = GatekeeperQueue(test_mode=True)
        results["steps"].append({
            "step": "initialize_test_queue",
            "status": "success",
            "queue_path": str(gatekeeper.queue_path)
        })
        console.print(f"[green]*[/green] Test queue initialized at {gatekeeper.queue_path}")
        
        # Step 2: Queue campaigns from input file
        with open(input_file) as f:
            data = json.load(f)
        
        campaigns = data.get("campaigns", [])
        
        # Filter by campaign_id if specified
        if campaign_id:
            campaigns = [c for c in campaigns if c.get("campaign_id") == campaign_id]
            if not campaigns:
                results["errors"].append(f"Campaign ID '{campaign_id}' not found in input file")
                results["success"] = False
                console.print(f"[red]*[/red] Campaign ID '{campaign_id}' not found")
        
        queued_items = []
        for campaign in campaigns:
            item = gatekeeper.queue_campaign(campaign)
            queued_items.append(item)
        
        results["steps"].append({
            "step": "queue_campaigns",
            "status": "success",
            "campaigns_queued": len(queued_items),
            "campaign_ids": [item.campaign_id for item in queued_items]
        })
        console.print(f"[green]*[/green] Queued {len(queued_items)} campaigns to test queue")
        
        # Step 3: Simulate approval workflow
        approved_items = []
        rejected_items = []
        
        for item in queued_items:
            # Simulate approval (approve first half, reject second half for testing)
            if len(approved_items) < len(queued_items) // 2 + 1:
                result = gatekeeper.approve(item.review_id, reviewer="TEST_MODE")
                if result:
                    approved_items.append(result)
            else:
                result = gatekeeper.reject(
                    item.review_id, 
                    reason="Test rejection - simulated workflow",
                    reviewer="TEST_MODE"
                )
                if result:
                    rejected_items.append(result)
        
        results["steps"].append({
            "step": "simulate_approval_workflow",
            "status": "success",
            "approved_count": len(approved_items),
            "rejected_count": len(rejected_items),
            "approved_ids": [item.campaign_id for item in approved_items],
            "rejected_ids": [item.campaign_id for item in rejected_items]
        })
        console.print(f"[green]*[/green] Simulated workflow: {len(approved_items)} approved, {len(rejected_items)} rejected")
        
        # Step 4: Verify dashboard accessibility
        dashboard_accessible = False
        try:
            from flask import Flask
            dashboard_accessible = True
            results["steps"].append({
                "step": "verify_dashboard_accessibility",
                "status": "success",
                "flask_available": True,
                "dashboard_would_be_accessible": True
            })
            console.print(f"[green]*[/green] Dashboard would be accessible (Flask is installed)")
        except ImportError:
            results["steps"].append({
                "step": "verify_dashboard_accessibility",
                "status": "warning",
                "flask_available": False,
                "dashboard_would_be_accessible": False,
                "note": "Flask not installed - dashboard requires 'pip install flask'"
            })
            console.print(f"[yellow]![/yellow] Dashboard requires Flask: pip install flask")
        
        # Step 5: Get final queue stats
        stats = gatekeeper.get_stats()
        results["steps"].append({
            "step": "final_queue_stats",
            "status": "success",
            "stats": stats
        })
        console.print(f"[green]*[/green] Final stats: {stats['pending_count']} pending, {stats['approved_count']} approved, {stats['rejected_count']} rejected")
        
    except Exception as e:
        results["success"] = False
        results["errors"].append(str(e))
        console.print(f"[red]*[/red] Test failed: {e}")
    
    results["completed_at"] = datetime.now(timezone.utc).isoformat()
    
    # Save results
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    
    console.print(f"\n[bold]Test results saved to:[/bold] {results_path}")
    
    # Summary
    if results["success"]:
        console.print(Panel(
            f"[green]All workflow steps completed successfully![/green]\n\n"
            f"• Test queue: {gatekeeper.queue_path}\n"
            f"• Results: {results_path}\n"
            f"• Dashboard accessible: {'Yes' if dashboard_accessible else 'No (install Flask)'}\n\n"
            f"[dim]Production queue was not affected.[/dim]",
            title="* TEST MODE COMPLETE",
            border_style="green"
        ))
    else:
        console.print(Panel(
            f"[red]Test completed with errors:[/red]\n\n"
            f"• Errors: {', '.join(results['errors'])}\n\n"
            f"[dim]Production queue was not affected.[/dim]",
            title="* TEST MODE FAILED",
            border_style="red"
        ))
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Gatekeeper - Campaign Review Queue")
    parser.add_argument("--input", type=Path, help="Input campaigns JSON file to queue")
    parser.add_argument("--serve", action="store_true", help="Start dashboard server")
    parser.add_argument("--port", type=int, default=5000, help="Dashboard port")
    parser.add_argument("--approve", help="Approve a review by ID")
    parser.add_argument("--reject", help="Reject a review by ID")
    parser.add_argument("--reason", default="", help="Rejection reason")
    parser.add_argument("--status", action="store_true", help="Show queue status")
    parser.add_argument("--test-mode", action="store_true", 
                        help="Run in test mode - uses test queue and simulates workflow")
    parser.add_argument("--campaign-id", type=str, 
                        help="Specific campaign ID to process (used with --test-mode)")
    
    args = parser.parse_args()
    
    # Handle test mode
    if args.test_mode:
        if not args.input:
            console.print("[red]Error: --test-mode requires --input file[/red]")
            sys.exit(1)
        run_test_mode(args.input, args.campaign_id)
        return
    
    gatekeeper = GatekeeperQueue()
    
    if args.serve:
        app = create_dashboard_app()
        if app:
            console.print(f"\n[bold green]* GATEKEEPER Dashboard starting...[/bold green]")
            console.print(f"[dim]Open http://localhost:{args.port} in your browser[/dim]")
            app.run(host='0.0.0.0', port=args.port, debug=True)
        return
    
    if args.input:
        gatekeeper.queue_campaigns_from_file(args.input)
    
    if args.approve:
        gatekeeper.approve(args.approve)
    
    if args.reject:
        gatekeeper.reject(args.reject, args.reason or "Rejected via CLI")
    
    if args.status or (not args.input and not args.approve and not args.reject and not args.serve):
        gatekeeper.print_queue()


if __name__ == "__main__":
    main()
