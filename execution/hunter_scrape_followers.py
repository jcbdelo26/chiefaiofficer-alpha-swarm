#!/usr/bin/env python3
"""
Hunter Agent - LinkedIn Follower Scraper
=========================================
Scrapes followers from competitor LinkedIn company pages.

Architecture Notes (for AI agents reading this):
- This scraper uses LinkedIn's undocumented Voyager API via li_at cookie.
- The cookie expires every ~30 days and requires manual rotation.
- All 4 scrapers (followers, events, posts, groups) share this pattern.
- The pipeline MUST work with test-data fallback in all modes.
- Full scraping requires Proxycurl ($0.01/profile) or Playwright browser automation.

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


# ── Custom Exceptions ──────────────────────────────────────────────
class ScraperUnavailableError(Exception):
    """Raised when the scraper cannot operate (session expired, no cookie, etc.)."""
    pass


class ScraperTimeoutError(Exception):
    """Raised when a scraper operation exceeds the hard timeout."""
    pass


# ── Data Model ─────────────────────────────────────────────────────
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
    scraper_version: str = "2.0.0"


# ── Constants ──────────────────────────────────────────────────────
# Hard timeout: no single scraper call should ever block the pipeline
# beyond this limit. This is the backstop against infinite hangs.
SCRAPER_HARD_TIMEOUT_SECONDS = 30

# Session health check timeout (fast fail)
SESSION_CHECK_TIMEOUT_SECONDS = 10

# Rate limit: 5 requests per minute (LinkedIn's observed threshold)
REQUESTS_PER_MINUTE = 5

# Retry: max 2 attempts with bounded backoff (worst case: ~20s)
MAX_RETRY_ATTEMPTS = 2
RETRY_MAX_WAIT_SECONDS = 10


class LinkedInFollowerScraper:
    """
    Scrapes followers from LinkedIn company pages.
    
    IMPORTANT: This scraper validates the LinkedIn session BEFORE
    attempting any API calls. If the session is invalid, it raises
    ScraperUnavailableError immediately (fail-fast, no retry loop).
    """
    
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
        self._session_validated = False
        
        if not self.cookie:
            raise ValueError(
                "LINKEDIN_COOKIE not set. Add li_at cookie to .env. "
                "Alternative: use Proxycurl (PROXYCURL_API_KEY) for cookie-free scraping."
            )
    
    def validate_session(self) -> bool:
        """
        Pre-flight session health check. Calls /voyager/api/me to verify
        the LinkedIn cookie is alive. Returns True if valid, raises
        ScraperUnavailableError if expired/invalid.
        
        This MUST be called before any scraping operation.
        """
        import requests
        
        console.print("[dim]Validating LinkedIn session...[/dim]")
        
        headers = {
            "Cookie": f"li_at={self.cookie}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "x-restli-protocol-version": "2.0.0",
        }
        
        try:
            response = requests.get(
                "https://www.linkedin.com/voyager/api/me",
                headers=headers,
                timeout=SESSION_CHECK_TIMEOUT_SECONDS
            )
            
            if response.status_code == 200:
                console.print("[green]✅ LinkedIn session valid[/green]")
                self._session_validated = True
                return True
            elif response.status_code == 401:
                raise ScraperUnavailableError(
                    "LinkedIn session EXPIRED (401). Rotate the li_at cookie in .env "
                    "and run: python execution/health_monitor.py --update-linkedin-rotation"
                )
            elif response.status_code == 403:
                raise ScraperUnavailableError(
                    "LinkedIn session BLOCKED (403). Account may be rate-limited or restricted. "
                    "Wait 24h or use Proxycurl as alternative."
                )
            else:
                raise ScraperUnavailableError(
                    f"LinkedIn session check failed with status {response.status_code}. "
                    "Cookie may be invalid."
                )
                
        except requests.exceptions.Timeout:
            raise ScraperUnavailableError(
                f"LinkedIn session check timed out after {SESSION_CHECK_TIMEOUT_SECONDS}s. "
                "LinkedIn may be unreachable."
            )
        except requests.exceptions.ConnectionError:
            raise ScraperUnavailableError(
                "Cannot connect to LinkedIn. Check network connectivity."
            )
    
    @sleep_and_retry
    @limits(calls=REQUESTS_PER_MINUTE, period=60)
    def _rate_limited_request(self, url: str) -> Dict[str, Any]:
        """
        Rate-limited request wrapper.
        
        IMPORTANT: No blocking sleeps. If rate-limited (429), raise immediately
        and let tenacity handle the backoff with bounded limits.
        """
        import requests
        
        headers = {
            "Cookie": f"li_at={self.cookie}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        }
        
        response = requests.get(url, headers=headers, timeout=SCRAPER_HARD_TIMEOUT_SECONDS)
        
        if response.status_code == 429:
            # DO NOT sleep(300) here — raise immediately and let tenacity retry
            console.print("[yellow]⚠️ Rate limited (429). Backing off...[/yellow]")
            raise Exception("Rate limited by LinkedIn (429). Tenacity will retry with backoff.")
        
        if response.status_code == 401:
            raise ScraperUnavailableError("Session expired mid-scrape (401). Get new li_at cookie.")
        
        return {
            "status": response.status_code,
            "data": response.json() if response.headers.get("content-type", "").startswith("application/json") else None,
            "text": response.text
        }
    
    @retry(
        stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=2, max=RETRY_MAX_WAIT_SECONDS)
    )
    def fetch_followers(self, company_url: str, company_name: str, limit: int = 100) -> List[ScrapedLead]:
        """
        Fetch followers from a LinkedIn company page.
        
        Pre-conditions:
        - validate_session() MUST be called first (enforced here)
        - LINKEDIN_COOKIE must be valid
        
        Note: This is a simplified implementation. Real LinkedIn scraping
        requires browser automation (Selenium/Playwright) due to heavy JavaScript.
        """
        # Enforce session validation
        if not self._session_validated:
            self.validate_session()
        
        console.print(f"\n[bold blue]🕵️ HUNTER: Scraping followers from {company_name}[/bold blue]")
        
        # Extract company ID from URL
        company_id = company_url.rstrip("/").split("/")[-1]
        
        scraped_leads = []
        
        try:
            # NOTE: The Voyager API scaffold below shows the expected data flow.
            # Real scraping requires Playwright browser automation or Proxycurl API.
            console.print(f"[yellow]Note: Full scraping requires browser automation or Proxycurl.[/yellow]")
            console.print(f"[dim]Would scrape up to {limit} followers from {company_url}[/dim]")
            
            # Store batch metadata
            self.batch_id = str(uuid.uuid4())
            
            # Return empty — caller (pipeline) should fall back to test data
            if not scraped_leads:
                raise ScraperUnavailableError(
                    f"Scraper scaffold returned 0 leads for {company_name}. "
                    "Real scraping requires Proxycurl or Playwright. "
                    "Pipeline should use test data fallback."
                )
            
            return scraped_leads
            
        except ScraperUnavailableError:
            raise  # Don't retry scaffold failures
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
            console.print("[yellow]Full implementation requires browser automation or Proxycurl.[/yellow]")
            
    except ScraperUnavailableError as e:
        console.print(f"[yellow]⚠️ Scraper unavailable: {e}[/yellow]")
        console.print("[yellow]Pipeline will use test data fallback.[/yellow]")
    except Exception as e:
        console.print(f"[red]❌ Scraping failed: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
