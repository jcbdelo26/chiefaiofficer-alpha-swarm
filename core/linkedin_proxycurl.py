"""
LinkedIn Data Access - Multiple Provider Support
=================================================
Reliable LinkedIn data access without cookies.

RECOMMENDED ALTERNATIVES (since Proxycurl is shutting down):

1. APOLLO.IO (Best for Sales Teams)
   - 50 free credits/month, then ~$49/mo
   - Email finder + LinkedIn enrichment
   - Add: APOLLO_API_KEY=xxx
   - Docs: https://apolloio.github.io/apollo-api-docs/

2. PEOPLE DATA LABS (Best for Enrichment)
   - $0.05-0.10 per record
   - Deep professional data
   - Add: PDL_API_KEY=xxx  
   - Docs: https://docs.peopledatalabs.com/

3. CLEARBIT (Enterprise)
   - Contact sales for pricing
   - Best data quality
   - Add: CLEARBIT_API_KEY=xxx

4. CLAY (Already Integrated!)
   - Use Clay's LinkedIn enrichment
   - Works via existing Clay credits
   - No additional setup needed

5. PHANTOMBUSTER ($69/mo)
   - Browser automation
   - Handles cookies automatically
   - Good for bulk scraping

CURRENT RECOMMENDATION: Use Clay for LinkedIn enrichment
since it's already configured and working.
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('linkedin_proxycurl')


@dataclass
class LinkedInProfile:
    """Structured LinkedIn profile data."""
    linkedin_url: str
    first_name: str
    last_name: str
    full_name: str
    headline: str
    summary: Optional[str]
    city: Optional[str]
    country: Optional[str]
    
    # Current company
    company_name: Optional[str]
    company_linkedin_url: Optional[str]
    job_title: Optional[str]
    
    # Additional data
    industry: Optional[str]
    connections: Optional[int]
    follower_count: Optional[int]
    
    # Experience summary
    experience_count: int
    education_count: int
    
    # Raw data for enrichment
    raw_data: Dict[str, Any]
    
    # Metadata
    scraped_at: str
    source: str = "proxycurl"


class ProxycurlClient:
    """
    Client for Proxycurl LinkedIn API.
    
    Usage:
        client = ProxycurlClient()
        profile = client.get_profile("https://linkedin.com/in/johndoe")
    """
    
    BASE_URL = "https://nubela.co/proxycurl/api"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('PROXYCURL_API_KEY', '')
        
        if not self.api_key:
            logger.warning("PROXYCURL_API_KEY not set. Add it to .env for LinkedIn access.")
        
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        })
    
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)
    
    def get_profile(self, linkedin_url: str) -> Optional[LinkedInProfile]:
        """
        Get LinkedIn profile data.
        
        Args:
            linkedin_url: Full LinkedIn profile URL
            
        Returns:
            LinkedInProfile or None if failed
        """
        if not self.is_configured():
            logger.error("Proxycurl not configured. Set PROXYCURL_API_KEY in .env")
            return None
        
        try:
            response = self.session.get(
                f"{self.BASE_URL}/v2/linkedin",
                params={
                    'linkedin_profile_url': linkedin_url,
                    'use_cache': 'if-present',
                    'skills': 'include',
                    'inferred_salary': 'include',
                    'personal_email': 'include',
                    'personal_contact_number': 'include',
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_profile(linkedin_url, data)
            elif response.status_code == 404:
                logger.warning(f"Profile not found: {linkedin_url}")
                return None
            elif response.status_code == 401:
                logger.error("Invalid Proxycurl API key")
                return None
            elif response.status_code == 429:
                logger.warning("Rate limited by Proxycurl. Wait and retry.")
                return None
            else:
                logger.error(f"Proxycurl error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching profile: {e}")
            return None
    
    def _parse_profile(self, linkedin_url: str, data: Dict) -> LinkedInProfile:
        """Parse raw Proxycurl response into structured profile."""
        
        # Get current job
        experiences = data.get('experiences', [])
        current_job = None
        for exp in experiences:
            if exp.get('ends_at') is None:  # Current position
                current_job = exp
                break
        
        return LinkedInProfile(
            linkedin_url=linkedin_url,
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            full_name=data.get('full_name', ''),
            headline=data.get('headline', ''),
            summary=data.get('summary'),
            city=data.get('city'),
            country=data.get('country_full_name'),
            company_name=current_job.get('company') if current_job else None,
            company_linkedin_url=current_job.get('company_linkedin_profile_url') if current_job else None,
            job_title=current_job.get('title') if current_job else None,
            industry=data.get('industry'),
            connections=data.get('connections'),
            follower_count=data.get('follower_count'),
            experience_count=len(experiences),
            education_count=len(data.get('education', [])),
            raw_data=data,
            scraped_at=datetime.now().isoformat(),
        )
    
    def get_company(self, linkedin_url: str) -> Optional[Dict]:
        """Get LinkedIn company data."""
        if not self.is_configured():
            return None
        
        try:
            response = self.session.get(
                f"{self.BASE_URL}/linkedin/company",
                params={
                    'url': linkedin_url,
                    'use_cache': 'if-present',
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Company lookup failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching company: {e}")
            return None
    
    def search_person(
        self,
        first_name: str = None,
        last_name: str = None,
        company: str = None,
        title: str = None,
    ) -> Optional[List[str]]:
        """
        Search for LinkedIn profiles.
        Returns list of LinkedIn URLs.
        """
        if not self.is_configured():
            return None
        
        params = {}
        if first_name:
            params['first_name'] = first_name
        if last_name:
            params['last_name'] = last_name
        if company:
            params['current_company_name'] = company
        if title:
            params['current_role_title'] = title
        
        try:
            response = self.session.get(
                f"{self.BASE_URL}/search/person",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                return [r.get('linkedin_profile_url') for r in data.get('results', [])]
            else:
                return None
                
        except Exception as e:
            logger.error(f"Search error: {e}")
            return None
    
    def get_credits(self) -> Optional[int]:
        """Check remaining API credits."""
        if not self.is_configured():
            return None
        
        try:
            response = self.session.get(f"{self.BASE_URL}/credit-balance")
            if response.status_code == 200:
                return response.json().get('credit_balance')
            return None
        except:
            return None


def main():
    """Demo the Proxycurl client."""
    print("=" * 60)
    print("LinkedIn via Proxycurl - Setup Guide")
    print("=" * 60)
    
    client = ProxycurlClient()
    
    if client.is_configured():
        print("\n[OK] PROXYCURL_API_KEY is configured!")
        
        credits = client.get_credits()
        if credits is not None:
            print(f"[OK] Remaining credits: {credits}")
        
        # Test with a public profile
        print("\nTesting profile lookup...")
        profile = client.get_profile("https://www.linkedin.com/in/williamhgates/")
        
        if profile:
            print(f"[OK] Successfully fetched: {profile.full_name}")
            print(f"     Headline: {profile.headline}")
            print(f"     Company: {profile.company_name}")
        else:
            print("[WARN] Could not fetch test profile")
    else:
        print("\n[NOT CONFIGURED] PROXYCURL_API_KEY not found in .env")
        print()
        print("To set up Proxycurl:")
        print("1. Sign up at: https://nubela.co/proxycurl/")
        print("2. Get your API key from the dashboard")
        print("3. Add to .env: PROXYCURL_API_KEY=your_key_here")
        print()
        print("Benefits:")
        print("- No cookie management needed")
        print("- 99.9% reliability")
        print("- ~$0.01 per profile lookup")
        print("- Includes email and phone when available")
    
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
