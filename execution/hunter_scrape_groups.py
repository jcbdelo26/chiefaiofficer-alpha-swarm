#!/usr/bin/env python3
"""
Hunter Agent - LinkedIn Group Member Scraper
=============================================
Scrapes members from LinkedIn groups.

Usage:
    python execution/hunter_scrape_groups.py --url "https://linkedin.com/groups/12345"
    python execution/hunter_scrape_groups.py --url "group_url" --limit 100
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
from rich.console import Console
from rich.progress import Progress

console = Console()


@dataclass
class GroupMember:
    """Normalized group member from LinkedIn."""
    lead_id: str
    source_type: str
    source_id: str
    source_url: str
    source_name: str
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
    member_since: Optional[str]
    member_role: str  # member, admin, moderator
    activity_level: str  # active, moderate, passive
    engagement_action: str
    scraper_version: str = "1.0.0"


class LinkedInGroupScraper:
    """Scrapes members from LinkedIn groups."""
    
    # Pre-defined target groups
    TARGET_GROUPS = {
        "revenue-collective": {
            "url": "https://linkedin.com/groups/12345",
            "name": "Revenue Collective",
            "members": "15K+"
        },
        "revops-coop": {
            "url": "https://linkedin.com/groups/12346",
            "name": "RevOps Co-op",
            "members": "8K+"
        },
        "sales-operations": {
            "url": "https://linkedin.com/groups/12347",
            "name": "Sales Operations Professionals",
            "members": "45K+"
        },
        "modern-sales-pros": {
            "url": "https://linkedin.com/groups/12348",
            "name": "Modern Sales Pros",
            "members": "25K+"
        },
        "saas-sales-leaders": {
            "url": "https://linkedin.com/groups/12349",
            "name": "SaaS Sales Leaders",
            "members": "12K+"
        }
    }
    
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
            "data": response.json() if "application/json" in response.headers.get("content-type", "") else None
        }
    
    def fetch_group_members(self, group_url: str, group_name: str = "", limit: int = 100) -> List[GroupMember]:
        """
        Fetch members from a LinkedIn group.
        
        Note: Full implementation requires browser automation and group membership.
        This scaffold shows the expected data flow.
        """
        console.print(f"\n[bold blue]🕵️ HUNTER: Scraping group members[/bold blue]")
        console.print(f"[dim]Group: {group_url}[/dim]")
        
        # Extract group ID from URL
        group_id = group_url.rstrip("/").split("/")[-1]
        
        members = []
        
        try:
            headers = {
                "Cookie": f"li_at={self.cookie}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            console.print(f"[yellow]Note: Full group scraping requires browser automation.[/yellow]")
            console.print(f"[yellow]You must be a member of the group to scrape members.[/yellow]")
            console.print(f"[dim]Would scrape up to {limit} members from group {group_id}[/dim]")
            
            # In production:
            # 1. Use Selenium/Playwright to navigate to group
            # 2. Access Members tab
            # 3. Scroll and extract member profiles
            # 4. Handle pagination
            
            return members
            
        except Exception as e:
            console.print(f"[red]Error scraping group: {e}[/red]")
            raise
    
    def _normalize_member(self, raw: Dict[str, Any], group_url: str, group_name: str) -> GroupMember:
        """Normalize raw member data to our schema."""
        
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
        
        # Determine activity level based on available signals
        activity_level = "passive"
        if raw.get("recent_posts", 0) > 5:
            activity_level = "active"
        elif raw.get("recent_posts", 0) > 0:
            activity_level = "moderate"
        
        return GroupMember(
            lead_id=str(uuid.uuid4()),
            source_type="group_member",
            source_id=group_url.split("/")[-1],
            source_url=group_url,
            source_name=group_name or "LinkedIn Group",
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
            member_since=raw.get("memberSince"),
            member_role=raw.get("role", "member"),
            activity_level=activity_level,
            engagement_action="joined"
        )
    
    def save_members(self, members: List[GroupMember], output_dir: Optional[Path] = None) -> Path:
        """Save scraped members to JSON file."""
        
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / ".hive-mind" / "scraped"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"group_members_{self.batch_id[:8]}_{timestamp}.json"
        output_path = output_dir / filename
        
        members_data = [asdict(m) for m in members]
        
        with open(output_path, "w") as f:
            json.dump({
                "batch_id": self.batch_id,
                "scraped_at": datetime.utcnow().isoformat(),
                "source_type": "group_member",
                "lead_count": len(members),
                "leads": members_data
            }, f, indent=2)
        
        console.print(f"[green]✅ Saved {len(members)} members to {output_path}[/green]")
        
        return output_path


def main():
    parser = argparse.ArgumentParser(description="Scrape LinkedIn group members")
    parser.add_argument("--url", help="LinkedIn group URL")
    parser.add_argument("--group", choices=list(LinkedInGroupScraper.TARGET_GROUPS.keys()),
                        help="Pre-defined target group")
    parser.add_argument("--name", default="", help="Group name for context")
    parser.add_argument("--limit", type=int, default=100, help="Max members to scrape")
    
    args = parser.parse_args()
    
    if not args.url and not args.group:
        parser.error("Either --url or --group is required")
    
    try:
        scraper = LinkedInGroupScraper()
        
        if args.group:
            group_info = scraper.TARGET_GROUPS[args.group]
            group_url = group_info["url"]
            group_name = group_info["name"]
        else:
            group_url = args.url
            group_name = args.name
        
        members = scraper.fetch_group_members(group_url, group_name, args.limit)
        
        if members:
            output_path = scraper.save_members(members)
            console.print(f"\n[bold green]✅ Group scraping complete![/bold green]")
            console.print(f"Next step: python execution/enricher_waterfall.py --input {output_path}")
        else:
            console.print("\n[yellow]No members scraped. Full implementation requires browser automation.[/yellow]")
            
    except Exception as e:
        console.print(f"[red]❌ Group scraping failed: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
