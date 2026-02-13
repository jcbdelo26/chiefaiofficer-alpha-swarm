#!/usr/bin/env python3
"""
Hunter Agent - Lead Discovery via Apollo.io
============================================
Discovers ICP-matching leads at target companies using Apollo.io People Search.

Architecture Notes (for AI agents reading this):
- Primary: Apollo.io People Search (free) -> People Match (1 credit/reveal)
- Fallback: LinkedIn Voyager API via li_at cookie (rate-limited, unreliable)
- The pipeline MUST work with test-data fallback in all modes.
- Apollo covers 275M+ contacts — broader than LinkedIn scraping.

Provider History:
- LinkedIn cookie: blocked/rate-limited (403) since early 2026
- Proxycurl: REMOVED — sued by LinkedIn, shutting down Jul 2026
- Clay API v1: deprecated (404) since early 2026

Usage:
    python execution/hunter_scrape_followers.py --company "gong" --limit 10
    python execution/hunter_scrape_followers.py --url "https://linkedin.com/company/gong"
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
    Discovers ICP-matching leads at target companies.

    Strategy:
    1. Try Apollo.io People Search (free) + People Match (1 credit/reveal)
    2. If no Apollo key -> try LinkedIn Voyager API via li_at cookie
    3. If neither available -> raise ScraperUnavailableError (pipeline uses test data)
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
        self.apollo_key = os.getenv("APOLLO_API_KEY")
        self.session_id = "primary"
        self.batch_id = str(uuid.uuid4())
        self.leads: List[ScrapedLead] = []
        self._session_validated = False
        self._use_api_fallback = False

        if not self.cookie and not self.apollo_key:
            raise ValueError(
                "No scraping credentials configured. Set at least one of: "
                "LINKEDIN_COOKIE or APOLLO_API_KEY in .env"
            )
    
    def validate_session(self) -> bool:
        """
        Pre-flight session health check. Calls /voyager/api/me to verify
        the LinkedIn cookie is alive. If cookie fails, checks for API
        fallback providers (Proxycurl/Apollo). Returns True if any path
        is available. Raises ScraperUnavailableError only if ALL paths fail.
        """
        import requests

        # If no cookie, skip directly to API fallback check
        if not self.cookie:
            return self._check_api_fallback("No LinkedIn cookie configured")

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
                console.print("[green]LinkedIn session valid[/green]")
                self._session_validated = True
                return True
            elif response.status_code == 401:
                return self._check_api_fallback(
                    "LinkedIn session EXPIRED (401). Rotate li_at cookie in .env"
                )
            elif response.status_code == 403:
                return self._check_api_fallback(
                    "LinkedIn session BLOCKED (403). Account rate-limited or restricted"
                )
            else:
                return self._check_api_fallback(
                    f"LinkedIn session check failed with status {response.status_code}"
                )

        except requests.exceptions.Timeout:
            return self._check_api_fallback(
                f"LinkedIn session check timed out after {SESSION_CHECK_TIMEOUT_SECONDS}s"
            )
        except requests.exceptions.ConnectionError:
            return self._check_api_fallback("Cannot connect to LinkedIn")

    def _check_api_fallback(self, reason: str) -> bool:
        """Check if an API fallback provider is available when cookie fails."""
        if self.apollo_key:
            console.print(f"[yellow]{reason} -- falling back to Apollo.io API[/yellow]")
            self._use_api_fallback = True
            self._session_validated = True
            return True
        else:
            raise ScraperUnavailableError(
                f"{reason}. No API fallback available. "
                "Set APOLLO_API_KEY in .env for cookie-free lead discovery."
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
        Discover ICP-matching leads at a target company.

        Args:
            company_url: LinkedIn company URL (kept for backward compat, unused by Apollo)
            company_name: Company name for Apollo search
            limit: Max leads to return

        Routes to the best available provider:
        1. Apollo.io People Search + Match -- if APOLLO_API_KEY set
        2. LinkedIn Voyager API (cookie) -- if session validated
        """
        if not self._session_validated:
            self.validate_session()

        self.batch_id = str(uuid.uuid4())

        # If API fallback is active, use Apollo API instead of cookie scraping
        if self._use_api_fallback:
            if self.apollo_key:
                return self._fetch_via_apollo(company_name, limit)

        # Cookie-based LinkedIn Voyager scraping (scaffold)
        console.print(f"[dim]Cookie-based scrape of {company_name} (scaffold -- returns 0 leads)[/dim]")
        raise ScraperUnavailableError(
            f"Cookie-based scraper scaffold returned 0 leads for {company_name}. "
            "Pipeline will use test data fallback."
        )

    def _fetch_via_apollo(self, company_name: str, limit: int) -> List[ScrapedLead]:
        """Fetch leads via Apollo.io two-step flow: Search (free) -> Match (1 credit/lead).

        Step 1: api_search returns anonymized results with Apollo person IDs,
                first names, titles, and company matches. No credits consumed.
        Step 2: people/match by ID reveals full name, email, LinkedIn URL,
                and company details. Costs 1 credit per reveal.
        """
        import requests

        console.print(f"[dim]Apollo.io: searching people at {company_name}...[/dim]")

        headers = {
            "x-api-key": self.apollo_key,
            "Content-Type": "application/json",
        }

        # Step 1: Free search — find ICP-matching people at target company
        search_payload = {
            "q_organization_name": company_name,
            "per_page": min(limit, 25),
            "person_seniorities": ["vp", "c_suite", "director"],
            "person_titles": [
                "VP of Sales", "Head of Sales", "CRO", "Chief Revenue Officer",
                "VP of Business Development", "Sales Director", "Head of RevOps",
                "VP Marketing", "CMO", "Head of Growth",
            ],
        }

        try:
            search_resp = requests.post(
                "https://api.apollo.io/api/v1/mixed_people/api_search",
                headers=headers,
                json=search_payload,
                timeout=20,
            )

            if search_resp.status_code != 200:
                raise ScraperUnavailableError(
                    f"Apollo people search failed: {search_resp.status_code}"
                )

            search_data = search_resp.json()
            candidates = search_data.get("people") or []
            console.print(f"[dim]  Step 1: Found {len(candidates)} ICP candidates (free search)[/dim]")

            if not candidates:
                raise ScraperUnavailableError(f"Apollo search returned 0 candidates for {company_name}")

            # Step 2: Reveal top candidates via People Match (1 credit each)
            scraped = []
            reveal_count = min(len(candidates), limit)
            console.print(f"[dim]  Step 2: Revealing {reveal_count} contacts (1 credit each)...[/dim]")

            for candidate in candidates[:limit]:
                apollo_id = candidate.get("id")
                if not apollo_id:
                    continue

                try:
                    match_resp = requests.post(
                        "https://api.apollo.io/api/v1/people/match",
                        headers=headers,
                        json={"id": apollo_id},
                        timeout=15,
                    )

                    if match_resp.status_code == 402:
                        console.print("[red]Apollo credits exhausted — stopping reveals[/red]")
                        break
                    if match_resp.status_code != 200:
                        continue

                    person = match_resp.json().get("person") or match_resp.json()
                    name = person.get("name", "")
                    parts = name.split(None, 1)
                    org = person.get("organization") or {}

                    scraped.append(ScrapedLead(
                        lead_id=str(uuid.uuid4()),
                        source_type="apollo_search",
                        source_id=company_name.lower().replace(" ", "_"),
                        source_url=person.get("linkedin_url", ""),
                        source_name=company_name,
                        captured_at=datetime.utcnow().isoformat(),
                        batch_id=self.batch_id,
                        linkedin_url=person.get("linkedin_url", ""),
                        linkedin_id=person.get("id", ""),
                        name=name,
                        first_name=parts[0] if parts else "",
                        last_name=parts[1] if len(parts) > 1 else "",
                        title=person.get("title", ""),
                        company=org.get("name", company_name),
                        company_linkedin_url=org.get("linkedin_url"),
                        location=f"{person.get('city', '')}, {person.get('state', '')}".strip(", "),
                        connection_degree=0,
                        profile_image_url=person.get("photo_url"),
                        engagement_action="apollo_search",
                        engagement_content=None,
                        engagement_timestamp=None,
                        raw_html=None,
                    ))
                except requests.exceptions.RequestException:
                    continue

            console.print(f"[green]Apollo: {len(scraped)} leads revealed for {company_name}[/green]")

            if not scraped:
                raise ScraperUnavailableError(f"Apollo revealed 0 leads for {company_name}")
            return scraped

        except requests.exceptions.RequestException as e:
            raise ScraperUnavailableError(f"Apollo API request failed: {e}")

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
            console.print("\n[yellow]No leads scraped. Check APOLLO_API_KEY in .env[/yellow]")
            
    except ScraperUnavailableError as e:
        console.print(f"[yellow]⚠️ Scraper unavailable: {e}[/yellow]")
        console.print("[yellow]Pipeline will use test data fallback.[/yellow]")
    except Exception as e:
        console.print(f"[red]❌ Scraping failed: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
