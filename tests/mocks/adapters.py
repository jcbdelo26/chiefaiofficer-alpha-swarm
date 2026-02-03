"""Mock adapters for all external integrations."""

from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone
from typing import Dict, Any, List


class MockGHLAdapter:
    """Mock GoHighLevel adapter."""
    def __init__(self):
        self.contacts = {}
        self.emails_sent = []
        
    async def execute(self, action: str, params: Dict) -> Dict:
        if action == "create_contact":
            contact_id = f"mock_contact_{len(self.contacts)}"
            self.contacts[contact_id] = params
            return {"success": True, "contact_id": contact_id}
        elif action == "send_email":
            self.emails_sent.append(params)
            return {"success": True, "email_id": f"email_{len(self.emails_sent)}"}
        return {"success": True, "action": action}


class MockGoogleCalendarAdapter:
    """Mock Google Calendar adapter."""
    def __init__(self):
        self.events = {}
        self.busy_slots = []
        
    async def get_availability(self, calendar_id: str, start: str, end: str) -> Dict:
        return {
            "success": True,
            "busy_slots": self.busy_slots,
            "free_slots": [{"start": start, "end": end}]
        }
    
    async def create_event(self, **kwargs) -> Dict:
        event_id = f"mock_event_{len(self.events)}"
        self.events[event_id] = kwargs
        return {
            "success": True,
            "event_id": event_id,
            "html_link": f"https://calendar.google.com/event?eid={event_id}"
        }

    async def execute(self, action: str, params: Dict) -> Dict:
        if action == "get_availability":
            return await self.get_availability(
                params.get("calendar_id", "primary"),
                params.get("start", ""),
                params.get("end", "")
            )
        elif action == "create_event":
            return await self.create_event(**params)
        return {"success": True, "action": action}


class MockSupabaseAdapter:
    """Mock Supabase adapter."""
    def __init__(self):
        self.tables = {}
    
    async def query(self, table: str, filters: Dict = None) -> List[Dict]:
        return self.tables.get(table, [])
    
    async def insert(self, table: str, data: Dict) -> Dict:
        if table not in self.tables:
            self.tables[table] = []
        data["id"] = f"row_{len(self.tables[table])}"
        self.tables[table].append(data)
        return {"success": True, "data": data}

    async def execute(self, action: str, params: Dict) -> Dict:
        if action == "query":
            result = await self.query(params.get("table", ""), params.get("filters"))
            return {"success": True, "data": result}
        elif action == "insert":
            return await self.insert(params.get("table", ""), params.get("data", {}))
        return {"success": True, "action": action}


class MockClayAdapter:
    """Mock Clay enrichment adapter."""
    async def enrich_contact(self, email: str) -> Dict:
        return {
            "success": True,
            "data": {
                "email": email,
                "company": "Mock Company Inc",
                "title": "VP of Sales",
                "linkedin_url": f"https://linkedin.com/in/{email.split('@')[0]}"
            }
        }

    async def execute(self, action: str, params: Dict) -> Dict:
        if action == "enrich_contact":
            return await self.enrich_contact(params.get("email", ""))
        return {"success": True, "action": action}


class MockIntegrationGateway:
    """Mock unified integration gateway."""
    def __init__(self):
        self.ghl = MockGHLAdapter()
        self.calendar = MockGoogleCalendarAdapter()
        self.supabase = MockSupabaseAdapter()
        self.clay = MockClayAdapter()
        self._adapters = {
            "ghl": self.ghl,
            "google_calendar": self.calendar,
            "supabase": self.supabase,
            "clay": self.clay
        }
    
    async def execute(self, integration: str, action: str, params: Dict, **kwargs) -> Dict:
        adapter = self._adapters.get(integration)
        if adapter:
            return await adapter.execute(action, params)
        return {"success": False, "error": f"Unknown integration: {integration}"}


def get_mock_gateway():
    """Get a mock gateway instance for testing."""
    return MockIntegrationGateway()


__all__ = [
    "MockGHLAdapter",
    "MockGoogleCalendarAdapter",
    "MockSupabaseAdapter",
    "MockClayAdapter",
    "MockIntegrationGateway",
    "get_mock_gateway",
]
