"""
Unified GoHighLevel Outreach Client
Handles all email outreach: cold, warm, re-engagement, and ghost recovery.
Consolidates all sending through GHL (replacing Instantly).
"""

import os
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any
from pathlib import Path


class OutreachType(Enum):
    """Types of outreach campaigns."""
    COLD = "cold"
    WARM = "warm"
    REENGAGEMENT = "reengagement"
    GHOST_RECOVERY = "ghost_recovery"


@dataclass
class EmailTemplate:
    """Email template with performance tracking."""
    id: str
    name: str
    subject: str
    body: str
    type: OutreachType
    performance_score: float = 0.0
    opens: int = 0
    clicks: int = 0
    replies: int = 0
    sends: int = 0
    
    def update_score(self):
        """Calculate performance score based on engagement."""
        if self.sends == 0:
            self.performance_score = 0.0
            return
        open_rate = self.opens / self.sends
        click_rate = self.clicks / self.sends
        reply_rate = self.replies / self.sends
        self.performance_score = (open_rate * 0.3) + (click_rate * 0.3) + (reply_rate * 0.4)


@dataclass
class OutreachConfig:
    """Configuration for outreach limits and scheduling."""
    monthly_limit: int = 3000
    daily_limit: int = 150
    min_delay_seconds: int = 60
    working_hours_start: int = 8
    working_hours_end: int = 18
    timezone: str = "America/Los_Angeles"
    
    def is_within_working_hours(self) -> bool:
        """Check if current time is within working hours."""
        now = datetime.now()
        return self.working_hours_start <= now.hour < self.working_hours_end
    
    def next_send_window(self) -> datetime:
        """Get next available send window."""
        now = datetime.now()
        if self.is_within_working_hours():
            return now
        if now.hour >= self.working_hours_end:
            next_day = now + timedelta(days=1)
            return next_day.replace(hour=self.working_hours_start, minute=0, second=0)
        return now.replace(hour=self.working_hours_start, minute=0, second=0)


@dataclass
class SequenceConfig:
    """Configuration for email sequences."""
    name: str
    type: OutreachType
    emails: int
    days: int
    delays: List[int] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.delays:
            self.delays = self._calculate_delays()
    
    def _calculate_delays(self) -> List[int]:
        """Calculate delay days between emails."""
        if self.emails <= 1:
            return [0]
        interval = self.days // (self.emails - 1)
        return [i * interval for i in range(self.emails)]


SEQUENCE_TYPES = {
    "cold_outbound": SequenceConfig(
        name="Cold Outbound",
        type=OutreachType.COLD,
        emails=5,
        days=14,
        delays=[0, 3, 6, 10, 14]
    ),
    "warm_nurture": SequenceConfig(
        name="Warm Nurture",
        type=OutreachType.WARM,
        emails=3,
        days=7,
        delays=[0, 3, 7]
    ),
    "ghost_recovery": SequenceConfig(
        name="Ghost Recovery",
        type=OutreachType.GHOST_RECOVERY,
        emails=3,
        days=10,
        delays=[0, 4, 10]
    ),
    "meeting_reminder": SequenceConfig(
        name="Meeting Reminder",
        type=OutreachType.WARM,
        emails=2,
        days=1,
        delays=[0, 1]
    )
}


@dataclass
class UsageStats:
    """Track email sending usage."""
    sends_this_month: int = 0
    month: str = ""
    daily_sends: Dict[str, int] = field(default_factory=dict)
    last_send_time: Optional[str] = None
    
    def __post_init__(self):
        if not self.month:
            self.month = datetime.now().strftime("%Y-%m")
    
    def reset_if_new_month(self):
        """Reset counters if new month."""
        current_month = datetime.now().strftime("%Y-%m")
        if self.month != current_month:
            self.sends_this_month = 0
            self.month = current_month
            self.daily_sends = {}
    
    def get_today_sends(self) -> int:
        """Get sends for today."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.daily_sends.get(today, 0)
    
    def record_send(self, count: int = 1):
        """Record a send."""
        self.reset_if_new_month()
        today = datetime.now().strftime("%Y-%m-%d")
        self.sends_this_month += count
        self.daily_sends[today] = self.daily_sends.get(today, 0) + count
        self.last_send_time = datetime.now().isoformat()


class GHLOutreachClient:
    """
    Unified GoHighLevel Outreach Client.
    Handles all email outreach through GHL API.
    """
    
    BASE_URL = "https://services.leadconnectorhq.com"
    
    def __init__(self, api_key: str, location_id: str, config: Optional[OutreachConfig] = None):
        self.api_key = api_key
        self.location_id = location_id
        self.config = config or OutreachConfig()
        self.usage_file = Path(".hive-mind/ghl_usage.json")
        self.usage = self._load_usage()
        self._templates: Dict[str, EmailTemplate] = {}
        self._session: Optional[aiohttp.ClientSession] = None
    
    def _load_usage(self) -> UsageStats:
        """Load usage stats from file."""
        self.usage_file.parent.mkdir(parents=True, exist_ok=True)
        if self.usage_file.exists():
            try:
                data = json.loads(self.usage_file.read_text())
                stats = UsageStats(**data)
                stats.reset_if_new_month()
                return stats
            except (json.JSONDecodeError, TypeError):
                pass
        return UsageStats()
    
    def _save_usage(self):
        """Save usage stats to file."""
        self.usage_file.parent.mkdir(parents=True, exist_ok=True)
        self.usage_file.write_text(json.dumps(asdict(self.usage), indent=2))
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Version": "2021-07-28"
            })
        return self._session
    
    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make API request to GHL."""
        session = await self._get_session()
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            async with session.request(method, url, json=data) as response:
                result = await response.json()
                if response.status >= 400:
                    raise Exception(f"GHL API error: {response.status} - {result}")
                return result
        except aiohttp.ClientError as e:
            raise Exception(f"GHL request failed: {e}")
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current usage statistics."""
        self.usage.reset_if_new_month()
        return {
            "sends_this_month": self.usage.sends_this_month,
            "monthly_limit": self.config.monthly_limit,
            "monthly_remaining": self.config.monthly_limit - self.usage.sends_this_month,
            "sends_today": self.usage.get_today_sends(),
            "daily_limit": self.config.daily_limit,
            "daily_remaining": self.config.daily_limit - self.usage.get_today_sends(),
            "last_send": self.usage.last_send_time,
            "month": self.usage.month
        }
    
    def can_send(self, count: int = 1) -> tuple[bool, str]:
        """Check if we can send emails within limits."""
        self.usage.reset_if_new_month()
        
        monthly_remaining = self.config.monthly_limit - self.usage.sends_this_month
        if count > monthly_remaining:
            return False, f"Monthly limit reached ({self.usage.sends_this_month}/{self.config.monthly_limit})"
        
        daily_remaining = self.config.daily_limit - self.usage.get_today_sends()
        if count > daily_remaining:
            return False, f"Daily limit reached ({self.usage.get_today_sends()}/{self.config.daily_limit})"
        
        if not self.config.is_within_working_hours():
            next_window = self.config.next_send_window()
            return False, f"Outside working hours. Next window: {next_window.strftime('%Y-%m-%d %H:%M')}"
        
        return True, "OK"
    
    def track_send(self, contact_id: str, template_id: str, count: int = 1):
        """Log send for rate limiting."""
        self.usage.record_send(count)
        self._save_usage()
        
        if template_id in self._templates:
            self._templates[template_id].sends += count
    
    async def send_email(
        self,
        contact_id: str,
        template: EmailTemplate,
        personalization: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Send single email to contact."""
        can_send, reason = self.can_send(1)
        if not can_send:
            return {"success": False, "error": reason}
        
        subject = template.subject
        body = template.body
        
        if personalization:
            for key, value in personalization.items():
                subject = subject.replace(f"{{{{{key}}}}}", value)
                body = body.replace(f"{{{{{key}}}}}", value)
        
        try:
            result = await self._request("POST", f"/conversations/messages", {
                "type": "Email",
                "contactId": contact_id,
                "subject": subject,
                "html": body,
                "emailFrom": self.location_id
            })
            
            self.track_send(contact_id, template.id)
            
            return {
                "success": True,
                "message_id": result.get("id"),
                "contact_id": contact_id,
                "template": template.name
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def send_campaign(
        self,
        contacts: List[str],
        template: EmailTemplate,
        outreach_type: OutreachType,
        personalization_map: Optional[Dict[str, Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Send campaign to multiple contacts with throttling."""
        can_send, reason = self.can_send(len(contacts))
        if not can_send:
            return {
                "success": False,
                "error": reason,
                "sent": 0,
                "failed": len(contacts)
            }
        
        results = {"sent": 0, "failed": 0, "errors": []}
        
        for i, contact_id in enumerate(contacts):
            personalization = (personalization_map or {}).get(contact_id, {})
            
            result = await self.send_email(contact_id, template, personalization)
            
            if result.get("success"):
                results["sent"] += 1
            else:
                results["failed"] += 1
                results["errors"].append({
                    "contact_id": contact_id,
                    "error": result.get("error")
                })
            
            if i < len(contacts) - 1:
                await asyncio.sleep(self.config.min_delay_seconds)
        
        results["success"] = results["failed"] == 0
        results["outreach_type"] = outreach_type.value
        return results
    
    async def schedule_sequence(
        self,
        contact_id: str,
        sequence_id: str,
        delay_days: int = 0
    ) -> Dict[str, Any]:
        """Schedule a follow-up sequence for contact."""
        if sequence_id not in SEQUENCE_TYPES:
            return {"success": False, "error": f"Unknown sequence: {sequence_id}"}
        
        sequence = SEQUENCE_TYPES[sequence_id]
        start_date = datetime.now() + timedelta(days=delay_days)
        
        try:
            result = await self._request("POST", f"/contacts/{contact_id}/workflow", {
                "workflowId": sequence_id,
                "startDate": start_date.isoformat()
            })
            
            return {
                "success": True,
                "contact_id": contact_id,
                "sequence": sequence.name,
                "emails": sequence.emails,
                "duration_days": sequence.days,
                "start_date": start_date.isoformat()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_email_stats(self, contact_id: str) -> Dict[str, Any]:
        """Get email engagement stats for contact."""
        try:
            result = await self._request("GET", f"/contacts/{contact_id}/tasks")
            
            stats = {
                "contact_id": contact_id,
                "emails_sent": 0,
                "opens": 0,
                "clicks": 0,
                "replies": 0,
                "last_opened": None,
                "last_clicked": None,
                "last_replied": None
            }
            
            messages = result.get("messages", [])
            for msg in messages:
                if msg.get("type") == "Email":
                    stats["emails_sent"] += 1
                    if msg.get("opened"):
                        stats["opens"] += 1
                        stats["last_opened"] = msg.get("openedAt")
                    if msg.get("clicked"):
                        stats["clicks"] += 1
                        stats["last_clicked"] = msg.get("clickedAt")
                    if msg.get("replied"):
                        stats["replies"] += 1
                        stats["last_replied"] = msg.get("repliedAt")
            
            return stats
        except Exception as e:
            return {"contact_id": contact_id, "error": str(e)}
    
    async def create_workflow_trigger(
        self,
        contact_id: str,
        workflow_id: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Trigger a GHL workflow for contact."""
        try:
            result = await self._request("POST", f"/contacts/{contact_id}/workflow/{workflow_id}", {
                "eventData": data or {}
            })
            
            return {
                "success": True,
                "contact_id": contact_id,
                "workflow_id": workflow_id,
                "triggered_at": datetime.now().isoformat()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def pause_contact_sequences(self, contact_id: str) -> Dict[str, Any]:
        """Pause all sequences for contact (on reply)."""
        try:
            result = await self._request("DELETE", f"/contacts/{contact_id}/workflow")
            
            return {
                "success": True,
                "contact_id": contact_id,
                "paused_at": datetime.now().isoformat()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_templates(self) -> List[Dict[str, Any]]:
        """List available email templates."""
        try:
            result = await self._request("GET", f"/locations/{self.location_id}/templates")
            templates = result.get("templates", [])
            
            return [{
                "id": t.get("id"),
                "name": t.get("name"),
                "subject": t.get("subject"),
                "type": t.get("type", "general")
            } for t in templates]
        except Exception as e:
            return self._get_default_templates()
    
    def _get_default_templates(self) -> List[Dict[str, Any]]:
        """Return default template definitions."""
        return [
            {
                "id": "cold_initial",
                "name": "Cold Outreach - Initial",
                "subject": "Quick question about {{company}}",
                "type": OutreachType.COLD.value
            },
            {
                "id": "cold_followup",
                "name": "Cold Outreach - Follow Up",
                "subject": "Following up - {{company}}",
                "type": OutreachType.COLD.value
            },
            {
                "id": "warm_nurture",
                "name": "Warm Nurture",
                "subject": "Thought you'd find this valuable",
                "type": OutreachType.WARM.value
            },
            {
                "id": "ghost_recovery",
                "name": "Ghost Recovery",
                "subject": "Should I close your file?",
                "type": OutreachType.GHOST_RECOVERY.value
            },
            {
                "id": "meeting_reminder",
                "name": "Meeting Reminder",
                "subject": "Looking forward to our call tomorrow",
                "type": OutreachType.WARM.value
            }
        ]
    
    def register_template(self, template: EmailTemplate):
        """Register a template for tracking."""
        self._templates[template.id] = template
    
    def get_sequence_info(self, sequence_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a sequence type."""
        if sequence_id not in SEQUENCE_TYPES:
            return None
        seq = SEQUENCE_TYPES[sequence_id]
        return {
            "id": sequence_id,
            "name": seq.name,
            "type": seq.type.value,
            "emails": seq.emails,
            "duration_days": seq.days,
            "delays": seq.delays
        }
    
    def list_sequences(self) -> List[Dict[str, Any]]:
        """List all available sequence types."""
        return [self.get_sequence_info(sid) for sid in SEQUENCE_TYPES]


async def main():
    """Test demonstration of GHL Outreach Client."""
    print("=" * 60)
    print("GHL Outreach Client - Test Demonstration")
    print("=" * 60)
    
    api_key = os.getenv("GHL_API_KEY", "test_api_key")
    location_id = os.getenv("GHL_LOCATION_ID", "test_location")
    
    client = GHLOutreachClient(api_key, location_id)
    
    print("\n1. Usage Statistics:")
    print("-" * 40)
    stats = client.get_usage_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    print("\n2. Can Send Check:")
    print("-" * 40)
    can_send_1, reason_1 = client.can_send(1)
    print(f"   Can send 1 email: {can_send_1} ({reason_1})")
    can_send_100, reason_100 = client.can_send(100)
    print(f"   Can send 100 emails: {can_send_100} ({reason_100})")
    
    print("\n3. Available Sequences:")
    print("-" * 40)
    for seq in client.list_sequences():
        print(f"   {seq['id']}:")
        print(f"      Name: {seq['name']}")
        print(f"      Type: {seq['type']}")
        print(f"      Emails: {seq['emails']} over {seq['duration_days']} days")
        print(f"      Delays: {seq['delays']}")
    
    print("\n4. Default Templates:")
    print("-" * 40)
    templates = client._get_default_templates()
    for t in templates:
        print(f"   {t['id']}: {t['name']} ({t['type']})")
    
    print("\n5. Template Registration & Tracking:")
    print("-" * 40)
    test_template = EmailTemplate(
        id="test_cold",
        name="Test Cold Outreach",
        subject="Quick question about {{company}}",
        body="<p>Hi {{first_name}},</p><p>I noticed {{company}} is growing...</p>",
        type=OutreachType.COLD
    )
    client.register_template(test_template)
    print(f"   Registered template: {test_template.name}")
    
    test_template.opens = 45
    test_template.clicks = 12
    test_template.replies = 8
    test_template.sends = 100
    test_template.update_score()
    print(f"   Performance score: {test_template.performance_score:.2%}")
    
    print("\n6. Simulated Send (no actual API call):")
    print("-" * 40)
    client.track_send("contact_123", "test_cold", 1)
    print(f"   Tracked 1 send for contact_123")
    new_stats = client.get_usage_stats()
    print(f"   Updated sends today: {new_stats['sends_today']}")
    print(f"   Updated monthly sends: {new_stats['sends_this_month']}")
    
    print("\n7. Configuration:")
    print("-" * 40)
    print(f"   Monthly limit: {client.config.monthly_limit}")
    print(f"   Daily limit: {client.config.daily_limit}")
    print(f"   Min delay: {client.config.min_delay_seconds}s")
    print(f"   Working hours: {client.config.working_hours_start}:00 - {client.config.working_hours_end}:00")
    print(f"   Timezone: {client.config.timezone}")
    print(f"   Within working hours: {client.config.is_within_working_hours()}")
    
    await client.close()
    
    print("\n" + "=" * 60)
    print("Test demonstration complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
