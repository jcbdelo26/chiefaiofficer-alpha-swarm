#!/usr/bin/env python3
"""
Feedback Collector
==================
Collects feedback signals from campaigns and updates learnings for RL training.

Sources:
- GoHighLevel webhooks (email events, meetings, calls, pipeline changes)
- Manual feedback (AE approvals, rejections)

Usage:
    from core.feedback_collector import FeedbackCollector, FeedbackType
    
    collector = FeedbackCollector()
    collector.record_feedback(FeedbackType.MEETING_BOOKED, lead_id="lead_001", campaign_id="camp_001")
    signals = collector.export_for_training()
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


PROJECT_ROOT = Path(__file__).parent.parent
FEEDBACK_FILE = PROJECT_ROOT / ".hive-mind" / "feedback_history.json"


class FeedbackType(Enum):
    """Types of feedback signals from campaigns."""
    OPEN = "open"
    CLICK = "click"
    REPLY_POSITIVE = "reply_positive"
    REPLY_NEGATIVE = "reply_negative"
    REPLY_NEUTRAL = "reply_neutral"
    MEETING_BOOKED = "meeting_booked"
    MEETING_NO_SHOW = "meeting_no_show"
    UNSUBSCRIBE = "unsubscribe"
    BOUNCE = "bounce"
    AE_APPROVED = "ae_approved"
    AE_REJECTED = "ae_rejected"


REWARD_MAP: dict[FeedbackType, float] = {
    FeedbackType.MEETING_BOOKED: 1.0,
    FeedbackType.REPLY_POSITIVE: 0.7,
    FeedbackType.REPLY_NEUTRAL: 0.2,
    FeedbackType.OPEN: 0.1,
    FeedbackType.CLICK: 0.15,
    FeedbackType.AE_APPROVED: 0.5,
    FeedbackType.REPLY_NEGATIVE: -0.3,
    FeedbackType.MEETING_NO_SHOW: -0.4,
    FeedbackType.UNSUBSCRIBE: -0.5,
    FeedbackType.AE_REJECTED: -0.6,
    FeedbackType.BOUNCE: -0.2,
}


@dataclass
class FeedbackEvent:
    """A single feedback event from a campaign."""
    id: str
    type: FeedbackType
    timestamp: str
    lead_id: str
    campaign_id: str
    agent_output_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    processed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp,
            "lead_id": self.lead_id,
            "campaign_id": self.campaign_id,
            "agent_output_id": self.agent_output_id,
            "metadata": self.metadata,
            "processed": self.processed,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FeedbackEvent":
        return cls(
            id=d["id"],
            type=FeedbackType(d["type"]),
            timestamp=d["timestamp"],
            lead_id=d["lead_id"],
            campaign_id=d["campaign_id"],
            agent_output_id=d.get("agent_output_id"),
            metadata=d.get("metadata", {}),
            processed=d.get("processed", False),
        )


@dataclass
class LearningSignal:
    """A learning signal extracted from feedback for RL training."""
    feedback_id: str
    category: str
    pattern: str
    reward: float
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LearningSignal":
        return cls(**d)


class FeedbackCollector:
    """
    Collects and processes feedback from multiple sources.
    
    Integrates with:
    - GoHighLevel for email engagement, meetings, and pipeline
    - Manual AE feedback
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or FEEDBACK_FILE
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.events: list[FeedbackEvent] = []
        self.signals: list[LearningSignal] = []
        self._load_state()

    def record_feedback(
        self,
        type: FeedbackType,
        lead_id: str,
        campaign_id: str,
        agent_output_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> FeedbackEvent:
        """
        Record a feedback event.
        
        Args:
            type: The feedback type
            lead_id: Associated lead ID
            campaign_id: Associated campaign ID
            agent_output_id: Optional link to the agent output that generated this
            metadata: Additional context
            
        Returns:
            The created FeedbackEvent
        """
        event = FeedbackEvent(
            id=str(uuid.uuid4()),
            type=type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            lead_id=lead_id,
            campaign_id=campaign_id,
            agent_output_id=agent_output_id,
            metadata=metadata or {},
            processed=False,
        )
        
        self.events.append(event)
        
        signal = self.extract_learning_signal(event)
        if signal:
            self.signals.append(signal)
            event.processed = True
        
        self._save_state()
        return event

    def process_ghl_email_webhook(self, payload: dict[str, Any]) -> Optional[FeedbackEvent]:
        """
        Parse and process a GoHighLevel email webhook payload.
        
        GHL email webhook types:
        - email.sent
        - email.delivered
        - email.opened
        - email.clicked
        - email.replied
        - email.bounced
        - email.unsubscribed
        """
        event_type_map = {
            "email.opened": FeedbackType.OPEN,
            "email.clicked": FeedbackType.CLICK,
            "email.bounced": FeedbackType.BOUNCE,
            "email.unsubscribed": FeedbackType.UNSUBSCRIBE,
        }
        
        ghl_event = payload.get("event", payload.get("type", ""))
        contact_id = payload.get("contact_id", payload.get("contactId", "unknown"))
        campaign_id = payload.get("campaign_id", payload.get("campaignId", "unknown"))
        
        if ghl_event == "email.replied":
            sentiment = payload.get("sentiment", payload.get("reply_sentiment", "neutral"))
            if sentiment in ("positive", "interested"):
                feedback_type = FeedbackType.REPLY_POSITIVE
            elif sentiment in ("negative", "not_interested", "angry"):
                feedback_type = FeedbackType.REPLY_NEGATIVE
            else:
                feedback_type = FeedbackType.REPLY_NEUTRAL
        elif ghl_event in event_type_map:
            feedback_type = event_type_map[ghl_event]
        elif ghl_event in ("email.sent", "email.delivered"):
            return None
        else:
            return None
        
        return self.record_feedback(
            type=feedback_type,
            lead_id=contact_id,
            campaign_id=campaign_id,
            metadata={
                "source": "ghl",
                "raw_event": ghl_event,
                "payload": payload,
            },
        )

    def process_ghl_webhook(self, payload: dict[str, Any]) -> Optional[FeedbackEvent]:
        """
        Parse and process a GoHighLevel webhook payload.
        
        GHL webhook types:
        - appointment.booked
        - appointment.no_show
        - opportunity.stage_changed
        - contact.reply
        """
        ghl_event = payload.get("event", payload.get("type", ""))
        contact_id = payload.get("contact_id", payload.get("contactId", "unknown"))
        campaign_id = payload.get("campaign_id", payload.get("campaignId", "unknown"))
        
        if ghl_event in ("appointment.booked", "AppointmentBooked", "calendar.booked"):
            feedback_type = FeedbackType.MEETING_BOOKED
        elif ghl_event in ("appointment.no_show", "AppointmentNoShow", "calendar.no_show"):
            feedback_type = FeedbackType.MEETING_NO_SHOW
        elif ghl_event in ("contact.reply", "ContactReply"):
            sentiment = payload.get("sentiment", "neutral")
            if sentiment == "positive":
                feedback_type = FeedbackType.REPLY_POSITIVE
            elif sentiment == "negative":
                feedback_type = FeedbackType.REPLY_NEGATIVE
            else:
                feedback_type = FeedbackType.REPLY_NEUTRAL
        else:
            return None
        
        return self.record_feedback(
            type=feedback_type,
            lead_id=contact_id,
            campaign_id=campaign_id,
            metadata={
                "source": "ghl",
                "raw_event": ghl_event,
                "payload": payload,
            },
        )

    def extract_learning_signal(self, feedback: FeedbackEvent) -> Optional[LearningSignal]:
        """
        Convert a feedback event into a learning signal for RL training.
        """
        reward = REWARD_MAP.get(feedback.type, 0.0)
        
        category = self._categorize_feedback(feedback.type)
        pattern = self._extract_pattern(feedback)
        
        return LearningSignal(
            feedback_id=feedback.id,
            category=category,
            pattern=pattern,
            reward=reward,
            applied=False,
        )

    def _categorize_feedback(self, feedback_type: FeedbackType) -> str:
        """Categorize feedback into high-level categories."""
        positive_types = {
            FeedbackType.MEETING_BOOKED,
            FeedbackType.REPLY_POSITIVE,
            FeedbackType.AE_APPROVED,
            FeedbackType.OPEN,
            FeedbackType.CLICK,
        }
        negative_types = {
            FeedbackType.REPLY_NEGATIVE,
            FeedbackType.UNSUBSCRIBE,
            FeedbackType.BOUNCE,
            FeedbackType.MEETING_NO_SHOW,
            FeedbackType.AE_REJECTED,
        }
        
        if feedback_type in positive_types:
            return "positive"
        elif feedback_type in negative_types:
            return "negative"
        else:
            return "neutral"

    def _extract_pattern(self, feedback: FeedbackEvent) -> str:
        """Extract a pattern identifier from feedback."""
        parts = [
            feedback.type.value,
            feedback.metadata.get("source", "manual"),
        ]
        
        if "icp_tier" in feedback.metadata:
            parts.append(f"tier_{feedback.metadata['icp_tier']}")
        
        if "template_id" in feedback.metadata:
            parts.append(feedback.metadata["template_id"])
        
        return ":".join(parts)

    def get_feedback_by_campaign(self, campaign_id: str) -> list[FeedbackEvent]:
        """Retrieve all feedback events for a campaign."""
        return [e for e in self.events if e.campaign_id == campaign_id]

    def get_feedback_by_lead(self, lead_id: str) -> list[FeedbackEvent]:
        """Retrieve all feedback events for a lead."""
        return [e for e in self.events if e.lead_id == lead_id]

    def calculate_campaign_rewards(self) -> dict[str, dict[str, Any]]:
        """
        Aggregate rewards per campaign.
        
        Returns:
            Dict mapping campaign_id to reward statistics
        """
        campaign_data: dict[str, list[float]] = {}
        
        for event in self.events:
            if event.campaign_id not in campaign_data:
                campaign_data[event.campaign_id] = []
            reward = REWARD_MAP.get(event.type, 0.0)
            campaign_data[event.campaign_id].append(reward)
        
        results = {}
        for campaign_id, rewards in campaign_data.items():
            results[campaign_id] = {
                "total_reward": sum(rewards),
                "avg_reward": sum(rewards) / len(rewards) if rewards else 0.0,
                "event_count": len(rewards),
                "positive_count": sum(1 for r in rewards if r > 0),
                "negative_count": sum(1 for r in rewards if r < 0),
            }
        
        return results

    def export_for_training(self) -> list[dict[str, Any]]:
        """
        Export state-action-reward tuples for RL training.
        
        Returns:
            List of training samples with state, action, reward, next_state
        """
        training_data = []
        
        for event in self.events:
            state = {
                "lead_id": event.lead_id,
                "campaign_id": event.campaign_id,
                "icp_tier": event.metadata.get("icp_tier", "unknown"),
                "template_id": event.metadata.get("template_id", "unknown"),
                "source": event.metadata.get("source", "unknown"),
            }
            
            action = event.metadata.get("action", event.metadata.get("template_id", "send_email"))
            reward = REWARD_MAP.get(event.type, 0.0)
            
            training_data.append({
                "feedback_id": event.id,
                "state": state,
                "action": action,
                "reward": reward,
                "next_state": None,
                "done": event.type in {
                    FeedbackType.MEETING_BOOKED,
                    FeedbackType.UNSUBSCRIBE,
                    FeedbackType.BOUNCE,
                },
                "timestamp": event.timestamp,
            })
        
        return training_data

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of collected feedback."""
        type_counts = {}
        for event in self.events:
            type_name = event.type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        total_reward = sum(REWARD_MAP.get(e.type, 0.0) for e in self.events)
        
        return {
            "total_events": len(self.events),
            "total_signals": len(self.signals),
            "total_reward": round(total_reward, 2),
            "avg_reward": round(total_reward / len(self.events), 3) if self.events else 0.0,
            "type_breakdown": type_counts,
            "processed_count": sum(1 for e in self.events if e.processed),
        }

    def _save_state(self):
        """Save feedback history to disk."""
        state = {
            "events": [e.to_dict() for e in self.events],
            "signals": [s.to_dict() for s in self.signals],
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def _load_state(self):
        """Load feedback history from disk."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            
            self.events = [FeedbackEvent.from_dict(e) for e in state.get("events", [])]
            self.signals = [LearningSignal.from_dict(s) for s in state.get("signals", [])]
        except Exception as e:
            print(f"Warning: Failed to load feedback history: {e}")


def main():
    """Test scenarios for FeedbackCollector."""
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    console.print("\n[bold blue]Feedback Collector Test Scenarios[/bold blue]\n")
    
    collector = FeedbackCollector()
    
    console.print("[dim]1. Recording direct feedback events...[/dim]")
    
    collector.record_feedback(
        type=FeedbackType.MEETING_BOOKED,
        lead_id="lead_001",
        campaign_id="camp_tier1_001",
        agent_output_id="output_001",
        metadata={"icp_tier": "tier1", "template_id": "pain_discovery"},
    )
    
    collector.record_feedback(
        type=FeedbackType.REPLY_POSITIVE,
        lead_id="lead_002",
        campaign_id="camp_tier1_001",
        metadata={"icp_tier": "tier1", "template_id": "pain_discovery"},
    )
    
    collector.record_feedback(
        type=FeedbackType.REPLY_NEGATIVE,
        lead_id="lead_003",
        campaign_id="camp_tier2_001",
        metadata={"icp_tier": "tier2", "template_id": "case_study"},
    )
    
    collector.record_feedback(
        type=FeedbackType.UNSUBSCRIBE,
        lead_id="lead_004",
        campaign_id="camp_tier3_001",
        metadata={"icp_tier": "tier3"},
    )
    
    collector.record_feedback(
        type=FeedbackType.AE_APPROVED,
        lead_id="lead_005",
        campaign_id="camp_tier1_002",
        metadata={"ae_id": "ae_john", "comment": "Great personalization"},
    )
    
    collector.record_feedback(
        type=FeedbackType.AE_REJECTED,
        lead_id="lead_006",
        campaign_id="camp_tier2_002",
        metadata={"ae_id": "ae_jane", "reason": "Wrong industry angle"},
    )
    
    console.print("[dim]2. Processing Instantly webhook...[/dim]")
    
    instantly_payloads = [
        {"event_type": "email_opened", "lead_email": "user@company.com", "campaign_id": "camp_001"},
        {"event_type": "email_clicked", "lead_email": "user@company.com", "campaign_id": "camp_001"},
        {"event_type": "email_replied", "lead_email": "user@company.com", "campaign_id": "camp_001", "sentiment": "positive"},
        {"event_type": "email_bounced", "lead_email": "bad@invalid.com", "campaign_id": "camp_002"},
    ]
    
    for payload in instantly_payloads:
        event = collector.process_instantly_webhook(payload)
        if event:
            console.print(f"  Instantly: {payload['event_type']} -> {event.type.value}")
    
    console.print("[dim]3. Processing GHL webhook...[/dim]")
    
    ghl_payloads = [
        {"event": "appointment.booked", "contact_id": "contact_001", "campaign_id": "ghl_camp_001"},
        {"event": "appointment.no_show", "contact_id": "contact_002", "campaign_id": "ghl_camp_001"},
        {"event": "contact.reply", "contact_id": "contact_003", "campaign_id": "ghl_camp_002", "sentiment": "negative"},
    ]
    
    for payload in ghl_payloads:
        event = collector.process_ghl_webhook(payload)
        if event:
            console.print(f"  GHL: {payload['event']} -> {event.type.value}")
    
    console.print("\n[bold]4. Feedback Summary[/bold]")
    summary = collector.get_summary()
    
    table = Table(title="Feedback Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Total Events", str(summary["total_events"]))
    table.add_row("Total Signals", str(summary["total_signals"]))
    table.add_row("Total Reward", str(summary["total_reward"]))
    table.add_row("Avg Reward", str(summary["avg_reward"]))
    table.add_row("Processed", str(summary["processed_count"]))
    
    console.print(table)
    
    console.print("\n[bold]5. Campaign Rewards[/bold]")
    campaign_rewards = collector.calculate_campaign_rewards()
    
    rewards_table = Table(title="Campaign Reward Breakdown")
    rewards_table.add_column("Campaign", style="cyan")
    rewards_table.add_column("Total", style="green")
    rewards_table.add_column("Avg", style="yellow")
    rewards_table.add_column("Events", style="blue")
    
    for campaign_id, data in list(campaign_rewards.items())[:5]:
        rewards_table.add_row(
            campaign_id,
            f"{data['total_reward']:.2f}",
            f"{data['avg_reward']:.3f}",
            str(data['event_count']),
        )
    
    console.print(rewards_table)
    
    console.print("\n[bold]6. Training Data Export[/bold]")
    training_data = collector.export_for_training()
    console.print(f"  Exported {len(training_data)} training samples")
    
    if training_data:
        sample = training_data[0]
        console.print(f"  Sample: state={sample['state']}, action={sample['action']}, reward={sample['reward']}")
    
    console.print("\n[bold]7. Lead Feedback Lookup[/bold]")
    lead_feedback = collector.get_feedback_by_lead("lead_001")
    console.print(f"  Lead 'lead_001' has {len(lead_feedback)} feedback events")
    
    console.print("\n[green]All test scenarios completed![/green]")


if __name__ == "__main__":
    main()
