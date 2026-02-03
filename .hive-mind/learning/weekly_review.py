#!/usr/bin/env python3
"""
Weekly Review Generator
=======================
Automatically generates weekly performance review for Alpha Swarm.

Usage:
    python .hive-mind/learning/weekly_review.py
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Any


class WeeklyReviewGenerator:
    """Generates weekly performance reviews."""
    
    def __init__(self):
        """Initialize review generator."""
        self.data_dir = Path(__file__).parent.parent
        self.events_file = self.data_dir / "campaign_events.jsonl"
        self.feedback_file = self.data_dir / "feedback_history.jsonl"
        self.review_dir = self.data_dir / "reviews"
        self.review_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_review(self, weeks_ago: int = 0) -> Dict[str, Any]:
        """
        Generate review for specified week.
        
        Args:
            weeks_ago: 0 for current week, 1 for last week, etc.
        
        Returns:
            Review data dictionary
        """
        # Calculate date range
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday() + (weeks_ago * 7))
        week_end = week_start + timedelta(days=6)
        
        print(f"\n📊 Generating Weekly Review")
        print(f"Week: {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}\n")
        
        # Collect metrics
        metrics = self._collect_metrics(week_start, week_end)
        
        # Generate insights
        insights = self._generate_insights(metrics)
        
        # Create action items
        action_items = self._generate_action_items(metrics, insights)
        
        # Compile review
        review = {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "generated_at": datetime.now().isoformat(),
            "metrics": metrics,
            "insights": insights,
            "action_items": action_items
        }
        
        # Save review
        self._save_review(review)
        
        # Print summary
        self._print_review(review)
        
        return review
    
    def _collect_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Collect metrics for date range."""
        
        metrics = {
            "leads_harvested": 0,
            "leads_enriched": 0,
            "campaigns_sent": 0,
            "emails_opened": 0,
            "emails_clicked": 0,
            "emails_replied": 0,
            "meetings_booked": 0,
            "unsubscribes": 0,
            "bounces": 0,
            "open_rate": 0.0,
            "click_rate": 0.0,
            "reply_rate": 0.0,
            "meeting_rate": 0.0,
            "cost_estimate": 0.0
        }
        
        # Load events
        if not self.events_file.exists():
            return metrics
        
        event_counts = defaultdict(int)
        
        with open(self.events_file) as f:
            for line in f:
                try:
                    event = json.loads(line)
                    event_time = datetime.fromisoformat(event['timestamp'])
                    
                    if start_date <= event_time <= end_date:
                        event_type = event['event_type']
                        event_counts[event_type] += 1
                except:
                    continue
        
        # Calculate metrics
        metrics["campaigns_sent"] = event_counts.get("sent", 0)
        metrics["emails_opened"] = event_counts.get("opened", 0)
        metrics["emails_clicked"] = event_counts.get("clicked", 0)
        metrics["emails_replied"] = event_counts.get("replied", 0)
        metrics["meetings_booked"] = event_counts.get("meeting_booked", 0)
        metrics["unsubscribes"] = event_counts.get("unsubscribed", 0)
        metrics["bounces"] = event_counts.get("bounced", 0)
        
        # Calculate rates
        if metrics["campaigns_sent"] > 0:
            metrics["open_rate"] = (metrics["emails_opened"] / metrics["campaigns_sent"]) * 100
            metrics["click_rate"] = (metrics["emails_clicked"] / metrics["campaigns_sent"]) * 100
            metrics["reply_rate"] = (metrics["emails_replied"] / metrics["campaigns_sent"]) * 100
            metrics["meeting_rate"] = (metrics["meetings_booked"] / metrics["campaigns_sent"]) * 100
        
        # Estimate costs (Clay enrichment at $3/lead)
        metrics["cost_estimate"] = metrics["leads_enriched"] * 3
        
        return metrics
    
    def _generate_insights(self, metrics: Dict[str, Any]) -> List[Dict[str, str]]:
        """Generate insights from metrics."""
        
        insights = []
        
        # Performance insights
        if metrics["reply_rate"] > 10:
            insights.append({
                "type": "success",
                "category": "performance",
                "insight": f"Excellent reply rate of {metrics['reply_rate']:.1f}% (target: 8%)",
                "recommendation": "Analyze successful campaigns and replicate patterns"
            })
        elif metrics["reply_rate"] < 5:
            insights.append({
                "type": "warning",
                "category": "performance",
                "insight": f"Low reply rate of {metrics['reply_rate']:.1f}% (target: 8%)",
                "recommendation": "Review messaging, targeting, and personalization"
            })
        
        # Engagement insights
        if metrics["open_rate"] > 50:
            insights.append({
                "type": "success",
                "category": "engagement",
                "insight": f"Strong open rate of {metrics['open_rate']:.1f}%",
                "recommendation": "Subject lines are working well - document patterns"
            })
        elif metrics["open_rate"] < 35:
            insights.append({
                "type": "warning",
                "category": "engagement",
                "insight": f"Low open rate of {metrics['open_rate']:.1f}%",
                "recommendation": "Test new subject line variations"
            })
        
        # Quality insights
        if metrics["unsubscribes"] > metrics["campaigns_sent"] * 0.02:
            insights.append({
                "type": "alert",
                "category": "quality",
                "insight": f"High unsubscribe rate: {(metrics['unsubscribes']/metrics['campaigns_sent']*100):.1f}%",
                "recommendation": "URGENT: Review messaging tone and targeting"
            })
        
        # Conversion insights
        if metrics["meeting_rate"] > 3:
            insights.append({
                "type": "success",
                "category": "conversion",
                "insight": f"Great meeting booking rate: {metrics['meeting_rate']:.1f}%",
                "recommendation": "Scale up campaigns with this approach"
            })
        
        return insights
    
    def _generate_action_items(
        self, 
        metrics: Dict[str, Any], 
        insights: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """Generate action items based on metrics and insights."""
        
        action_items = []
        
        # Based on insights
        for insight in insights:
            if insight["type"] == "alert":
                action_items.append({
                    "priority": "high",
                    "action": insight["recommendation"],
                    "category": insight["category"]
                })
            elif insight["type"] == "warning":
                action_items.append({
                    "priority": "medium",
                    "action": insight["recommendation"],
                    "category": insight["category"]
                })
        
        # Standard actions
        action_items.append({
            "priority": "medium",
            "action": "Update agent training with this week's learnings",
            "category": "training"
        })
        
        action_items.append({
            "priority": "low",
            "action": "Review and update ICP criteria if needed",
            "category": "targeting"
        })
        
        return action_items
    
    def _save_review(self, review: Dict[str, Any]):
        """Save review to file."""
        
        week_start = datetime.fromisoformat(review["week_start"])
        filename = f"weekly_review_{week_start.strftime('%Y%m%d')}.json"
        filepath = self.review_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(review, f, indent=2)
        
        print(f"💾 Review saved: {filepath}\n")
    
    def _print_review(self, review: Dict[str, Any]):
        """Print review summary."""
        
        metrics = review["metrics"]
        
        print("=" * 60)
        print("📊 WEEKLY PERFORMANCE SUMMARY")
        print("=" * 60)
        
        print("\n📈 KEY METRICS:")
        print(f"  Campaigns Sent:    {metrics['campaigns_sent']}")
        print(f"  Open Rate:         {metrics['open_rate']:.1f}%")
        print(f"  Click Rate:        {metrics['click_rate']:.1f}%")
        print(f"  Reply Rate:        {metrics['reply_rate']:.1f}%")
        print(f"  Meetings Booked:   {metrics['meetings_booked']}")
        print(f"  Estimated Cost:    ${metrics['cost_estimate']:.2f}")
        
        print("\n💡 INSIGHTS:")
        for i, insight in enumerate(review["insights"], 1):
            icon = "✅" if insight["type"] == "success" else "⚠️" if insight["type"] == "warning" else "🚨"
            print(f"  {icon} {insight['insight']}")
            print(f"     → {insight['recommendation']}")
        
        print("\n🎯 ACTION ITEMS:")
        for i, item in enumerate(review["action_items"], 1):
            priority_icon = "🔴" if item["priority"] == "high" else "🟡" if item["priority"] == "medium" else "🟢"
            print(f"  {priority_icon} [{item['priority'].upper()}] {item['action']}")
        
        print("\n" + "=" * 60)


def main():
    """Generate weekly review."""
    
    generator = WeeklyReviewGenerator()
    
    # Generate review for current week
    review = generator.generate_review(weeks_ago=0)
    
    print("\n✅ Weekly review complete!")
    print(f"📁 Saved to: .hive-mind/reviews/")


if __name__ == "__main__":
    main()
