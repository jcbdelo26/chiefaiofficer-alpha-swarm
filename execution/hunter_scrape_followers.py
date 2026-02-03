#!/usr/bin/env python3
"""
Hunter Agent - LinkedIn Follower Scraper
=========================================
Scrapes followers from competitor LinkedIn company pages.

Usage:
    python execution/hunter_scrape_followers.py --url "https://linkedin.com/company/gong"
    python execution/hunter_scrape_followers.py --company "gong" --limit 100
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

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Rate limiting
from ratelimit import limits, sleep_and_retry
from tenacity import retry, stop_after_attempt, wait_exponential

# Rich console output
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


@dataclass
class ScrapedLead:
    """Normalized lead from LinkedIn scraping."""
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
    company_linkedin_url: Optional[str]
    location: str
    connection_degree: int
    profile_image_url: Optional[str]
    engagement_action: str
    engagement_content: Optional[str]
    engagement_timestamp: Optional[str]
    raw_html: Optional[str]
    scraper_version: str = "1.0.0"


class LinkedInFollowerScraper:
    """Scrapes followers from LinkedIn company pages."""
    
    # Rate limit: 5 requests per minute
    REQUESTS_PER_MINUTE = 5
    
    # Pre-defined competitors
    COMPETITORS = {
        "gong": {
            "url": "https://linkedin.com/company/gabordi",
            "name": "Gong"
        },
        "clari": {
            "url": "https://linkedin.com/company/clari",
            "name": "Clari"
        },
        "chorus": {
            "url": "https://linkedin.com/company/chorus-ai",
            "name": "Chorus.ai"
        },
        "people.ai": {
            "url": "https://linkedin.com/company/people-ai",
            "name": "People.ai"
        },
        "outreach": {
            "url": "https://linkedin.com/company/outabordi",
            "name": "Outreach"
        }
    }
    
    def __init__(self):
        self.cookie = os.getenv("LINKEDIN_COOKIE")
        self.session_id = "primary"
        self.batch_id = str(uuid.uuid4())
        self.leads: List[ScrapedLead] = []
        
        if not self.cookie:
            raise ValueError("LINKEDIN_COOKIE not set. Add li_at cookie to .env")
    
    @sleep_and_retry
    @limits(calls=5, period=60)
    def _rate_limited_request(self, url: str) -> Dict[str, Any]:
        """Rate-limited request wrapper."""
        import requests
        
        headers = {
            "Cookie": f"li_at={self.cookie}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 429:
            console.print("[yellow]Rate limited. Waiting...[/yellow]")
            time.sleep(300)  # Wait 5 minutes
            raise Exception("Rate limited")
        
        if response.status_code == 401:
            raise Exception("Session expired. Get new li_at cookie.")
        
        return {
            "status": response.status_code,
            "data": response.json() if response.headers.get("content-type", "").startswith("application/json") else None,
            "text": response.text
        }
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=60))
    def fetch_followers(self, company_url: str, company_name: str, limit: int = 100) -> List[ScrapedLead]:
        """
        Fetch followers from a LinkedIn company page.
        
        Note: This is a simplified implementation. Real LinkedIn scraping
        requires browser automation (Selenium/Playwright) due to heavy JavaScript.
        """
        console.print(f"\n[bold blue]🕵️ HUNTER: Scraping followers from {company_name}[/bold blue]")
        
        # Extract company ID from URL
        company_id = company_url.rstrip("/").split("/")[-1]
        
        # LinkedIn Voyager API endpoint (internal API)
        # NOTE: This requires valid session and may not work without browser context
        followers_url = f"https://www.linkedin.com/voyager/api/graphql?queryId=voyagerOrganizationDashFollowerCard.95c89b3f9ca2c6f2d4f6c8c9c8c9c8c9&variables=(companyId:{company_id},count:{limit},start:0)"
        
        scraped_leads = []
        
        try:
            # In a real implementation, use Selenium/Playwright here
            # For now, we'll create a mock flow to show the structure
            
            console.print(f"[yellow]Note: Full scraping requires browser automation.[/yellow]")
            console.print(f"[yellow]This scaffold shows the expected data flow.[/yellow]")
            
            # Placeholder: In production, iterate through paginated results
            # response = self._rate_limited_request(followers_url)
            # followers_data = response.get("data", {}).get("elements", [])
            
            # For demonstration, log that we would scrape here
            console.print(f"[dim]Would scrape up to {limit} followers from {company_url}[/dim]")
            
            # Store batch metadata
            self.batch_id = str(uuid.uuid4())
            
            return scraped_leads
            
        except Exception as e:
            console.print(f"[red]Error scraping followers: {e}[/red]")
            raise
    
    def _normalize_profile(self, raw_profile: Dict[str, Any], company_name: str, company_url: str) -> ScrapedLead:
        """Normalize LinkedIn profile data to our schema."""
        
        # Parse name
        full_name = raw_profile.get("name", "")
        name_parts = full_name.split(" ", 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""
        
        # Parse headline (usually "Title at Company")
        headline = raw_profile.get("headline", "")
        title = ""
        company = ""
        if " at " in headline:
            parts = headline.split(" at ", 1)
            title = parts[0].strip()
            company = parts[1].strip()
        else:
            title = headline
        
        return ScrapedLead(
            lead_id=str(uuid.uuid4()),
            source_type="competitor_follower",
            source_id=company_url.split("/")[-1],
            source_url=company_url,
            source_name=company_name,
            captured_at=datetime.utcnow().isoformat(),
            batch_id=self.batch_id,
            linkedin_url=raw_profile.get("publicIdentifier", ""),
            linkedin_id=raw_profile.get("entityUrn", "").split(":")[-1],
            name=full_name,
            first_name=first_name,
            last_name=last_name,
            title=title,
            company=company,
            company_linkedin_url=raw_profile.get("companyUrl"),
            location=raw_profile.get("location", ""),
            connection_degree=raw_profile.get("distance", 0),
            profile_image_url=raw_profile.get("profilePicture"),
            engagement_action="followed",
            engagement_content=None,
            engagement_timestamp=None,
            raw_html=None
        )
    
    def save_leads(self, leads: List[ScrapedLead], output_dir: Optional[Path] = None) -> Path:
        """Save scraped leads to JSON file."""
        
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / ".hive-mind" / "scraped"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"followers_{self.batch_id[:8]}_{timestamp}.json"
        output_path = output_dir / filename
        
        # Convert to dicts
        leads_data = [asdict(lead) for lead in leads]
        
        with open(output_path, "w") as f:
            json.dump({
                "batch_id": self.batch_id,
                "scraped_at": datetime.utcnow().isoformat(),
                "source_type": "competitor_follower",
                "lead_count": len(leads),
                "leads": leads_data
            }, f, indent=2)
        
        console.print(f"[green]✅ Saved {len(leads)} leads to {output_path}[/green]")
        
        return output_path


def main():
    parser = argparse.ArgumentParser(description="Scrape LinkedIn company followers")
    parser.add_argument("--url", help="LinkedIn company URL")
    parser.add_argument("--company", choices=list(LinkedInFollowerScraper.COMPETITORS.keys()),
                        help="Pre-defined competitor name")
    parser.add_argument("--limit", type=int, default=100, help="Max followers to scrape")
    
    args = parser.parse_args()
    
    if not args.url and not args.company:
        parser.error("Either --url or --company is required")
    
    scraper = LinkedInFollowerScraper()
    
    if args.company:
        competitor = scraper.COMPETITORS[args.company]
        company_url = competitor["url"]
        company_name = competitor["name"]
    else:
        company_url = args.url
        company_name = company_url.split("/")[-1]
    
    try:
        leads = scraper.fetch_followers(company_url, company_name, args.limit)
        
        if leads:
            output_path = scraper.save_leads(leads)
            console.print(f"\n[bold green]✅ Scraping complete![/bold green]")
            console.print(f"Next step: Run enrichment with:")
            console.print(f"  python execution/enricher_clay_waterfall.py --input {output_path}")
        else:
            console.print("\n[yellow]No leads scraped. This may be expected for the scaffold.[/yellow]")
            console.print("[yellow]Full implementation requires browser automation.[/yellow]")
            
    except Exception as e:
        console.print(f"[red]❌ Scraping failed: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
