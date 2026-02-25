#!/usr/bin/env python3
"""
Hunter Agent - LinkedIn Event Attendee Scraper
==============================================
Scrapes attendees from LinkedIn events.

Usage:
    python execution/hunter_scrape_events.py --url "https://linkedin.com/events/12345"
    python execution/hunter_scrape_events.py --url "event_url" --limit 100
"""

import os
import sys
import json
import uuid
import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from ratelimit import limits, sleep_and_retry
from tenacity import retry, stop_after_attempt, wait_exponential
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


@dataclass
class EventAttendee:
    """Normalized event attendee from LinkedIn."""
    lead_id: str
    source_type: str
    source_id: str
    source_url: str
    source_name: str
    event_date: Optional[str]
    captured_at: str
    batch_id: str
    linkedin_url: str
    linkedin_id: str
    name: str
    first_name: str
    last_name: str
    title: str
    company: str
    location: str
    registration_status: str  # registered, attended, interested
    engagement_action: str
    scraper_version: str = "1.0.0"


class LinkedInEventScraper:
    """Scrapes attendees from LinkedIn events."""
    
    REQUESTS_PER_MINUTE = 5
    
    def __init__(self):
        self.cookie = os.getenv("LINKEDIN_COOKIE")
        self.batch_id = str(uuid.uuid4())
        
        if not self.cookie:
            raise ValueError("LINKEDIN_COOKIE not set")
    
    @sleep_and_retry
    @limits(calls=5, period=60)
    def _rate_limited_request(self, url: str, headers: dict) -> Dict[str, Any]:
        """Rate-limited HTTP request."""
        import requests
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 429:
            console.print("[yellow]Rate limited. Waiting 5 minutes...[/yellow]")
            time.sleep(300)
            raise Exception("Rate limited")
        
        return {
            "status": response.status_code,
            "data": response.json() if "application/json" in response.headers.get("content-type", "") else None,
            "text": response.text
        }
    
    def fetch_event_attendees(self, event_url: str, event_name: str = "", limit: int = 100) -> List[EventAttendee]:
        """
        Fetch attendees from a LinkedIn event.
        
        Note: Full implementation requires browser automation.
        This scaffold shows the expected data flow.
        """
        console.print(f"\n[bold blue]🕵️ HUNTER: Scraping event attendees[/bold blue]")
        console.print(f"[dim]Event: {event_url}[/dim]")
        
        # Extract event ID from URL
        event_id = event_url.rstrip("/").split("/")[-1]
        if not event_id.isdigit():
            # Handle format like /events/event-name-12345/
            parts = event_url.split("-")
            event_id = parts[-1].rstrip("/") if parts else event_id
        
        attendees = []
        
        try:
            headers = {
                "Cookie": f"li_at={self.cookie}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            # LinkedIn Voyager API for event attendees
            # NOTE: Actual implementation requires browser automation
            api_url = f"https://www.linkedin.com/voyager/api/events/{event_id}/attendees"
            
            console.print(f"[yellow]Note: Full event scraping requires browser automation.[/yellow]")
            console.print(f"[yellow]This scaffold shows the expected data flow.[/yellow]")
            console.print(f"[dim]Would scrape up to {limit} attendees from event {event_id}[/dim]")
            
            # In production, iterate through paginated attendee results
            # For now, return empty list with proper structure logged
            
            return attendees
            
        except Exception as e:
            console.print(f"[red]Error scraping event: {e}[/red]")
            raise
    
    def _normalize_attendee(self, raw: Dict[str, Any], event_url: str, event_name: str, event_date: str = None) -> EventAttendee:
        """Normalize raw attendee data to our schema."""
        
        full_name = raw.get("name", "")
        name_parts = full_name.split(" ", 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""
        
        headline = raw.get("headline", "")
        title = ""
        company = ""
        if " at " in headline:
            parts = headline.split(" at ", 1)
            title = parts[0].strip()
            company = parts[1].strip()
        else:
            title = headline
        
        return EventAttendee(
            lead_id=str(uuid.uuid4()),
            source_type="event_attendee",
            source_id=event_url.split("/")[-1],
            source_url=event_url,
            source_name=event_name or "LinkedIn Event",
            event_date=event_date,
            captured_at=datetime.utcnow().isoformat(),
            batch_id=self.batch_id,
            linkedin_url=raw.get("publicIdentifier", ""),
            linkedin_id=raw.get("entityUrn", "").split(":")[-1],
            name=full_name,
            first_name=first_name,
            last_name=last_name,
            title=title,
            company=company,
            location=raw.get("location", ""),
            registration_status=raw.get("status", "registered"),
            engagement_action="registered"
        )
    
    def save_attendees(self, attendees: List[EventAttendee], output_dir: Optional[Path] = None) -> Path:
        """Save scraped attendees to JSON file."""
        
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / ".hive-mind" / "scraped"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"event_attendees_{self.batch_id[:8]}_{timestamp}.json"
        output_path = output_dir / filename
        
        attendees_data = [asdict(a) for a in attendees]
        
        with open(output_path, "w") as f:
            json.dump({
                "batch_id": self.batch_id,
                "scraped_at": datetime.utcnow().isoformat(),
                "source_type": "event_attendee",
                "lead_count": len(attendees),
                "leads": attendees_data
            }, f, indent=2)
        
        console.print(f"[green]✅ Saved {len(attendees)} attendees to {output_path}[/green]")
        
        return output_path


def main():
    parser = argparse.ArgumentParser(description="Scrape LinkedIn event attendees")
    parser.add_argument("--url", required=True, help="LinkedIn event URL")
    parser.add_argument("--name", default="", help="Event name for context")
    parser.add_argument("--limit", type=int, default=100, help="Max attendees to scrape")
    
    args = parser.parse_args()
    
    try:
        scraper = LinkedInEventScraper()
        attendees = scraper.fetch_event_attendees(args.url, args.name, args.limit)
        
        if attendees:
            output_path = scraper.save_attendees(attendees)
            console.print(f"\n[bold green]✅ Event scraping complete![/bold green]")
            console.print(f"Next step: python execution/enricher_waterfall.py --input {output_path}")
        else:
            console.print("\n[yellow]No attendees scraped. Full implementation requires browser automation.[/yellow]")
            
    except Exception as e:
        console.print(f"[red]❌ Event scraping failed: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
