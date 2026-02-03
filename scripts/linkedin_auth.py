#!/usr/bin/env python3
"""
LinkedIn Enhanced Authentication
=================================
Uses multiple cookies for proper LinkedIn API access.
LinkedIn requires both li_at AND JSESSIONID for Voyager API.
"""

import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path, override=True)


def get_linkedin_session():
    """
    Create a properly authenticated LinkedIn session.
    Requires LINKEDIN_COOKIE (li_at) in .env
    """
    li_at = os.getenv('LINKEDIN_COOKIE', '')
    
    if not li_at:
        print("ERROR: LINKEDIN_COOKIE not set in .env")
        return None
    
    # Create session with browser-like headers
    session = requests.Session()
    
    # Set cookies
    session.cookies.set('li_at', li_at, domain='.linkedin.com')
    
    # Browser-like headers
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'application/vnd.linkedin.normalized+json+2.1',
        'Accept-Language': 'en-US,en;q=0.9',
        'x-li-lang': 'en_US',
        'x-li-track': '{"clientVersion":"1.13.8765","mpVersion":"1.13.8765","osName":"web","timezoneOffset":8,"timezone":"Asia/Manila","deviceFormFactor":"DESKTOP","mpName":"voyager-web","displayDensity":1,"displayWidth":1920,"displayHeight":1080}',
        'x-restli-protocol-version': '2.0.0',
    })
    
    return session


def get_csrf_token(session):
    """Get CSRF token from LinkedIn by making initial request."""
    try:
        # First, visit the main page to get JSESSIONID
        response = session.get('https://www.linkedin.com/feed/', timeout=15)
        
        # Get JSESSIONID from cookies
        jsessionid = session.cookies.get('JSESSIONID', domain='.linkedin.com')
        
        if jsessionid:
            # Remove quotes if present
            jsessionid = jsessionid.strip('"')
            session.headers['csrf-token'] = jsessionid
            return jsessionid
        
        return None
    except Exception as e:
        print(f"Error getting CSRF token: {e}")
        return None


def validate_linkedin_session():
    """Validate LinkedIn session with proper authentication."""
    print("=" * 60)
    print("LinkedIn Enhanced Authentication")
    print("=" * 60)
    
    session = get_linkedin_session()
    if not session:
        return False
    
    li_at = os.getenv('LINKEDIN_COOKIE', '')
    print(f"\n[1] Cookie Check")
    print(f"    li_at length: {len(li_at)} chars")
    print(f"    Starts with 'AQ': {li_at.startswith('AQ')}")
    
    print(f"\n[2] Getting CSRF Token...")
    csrf = get_csrf_token(session)
    if csrf:
        print(f"    CSRF Token: {csrf[:20]}...")
    else:
        print("    WARNING: Could not get CSRF token")
    
    print(f"\n[3] Testing API Access...")
    
    # Test different endpoints
    endpoints = [
        ('Profile (me)', 'https://www.linkedin.com/voyager/api/me'),
        ('Mini Profile', 'https://www.linkedin.com/voyager/api/identity/profiles/me'),
    ]
    
    for name, url in endpoints:
        try:
            response = session.get(url, timeout=15)
            status = response.status_code
            
            if status == 200:
                print(f"    {name}: ✅ SUCCESS")
                try:
                    data = response.json()
                    if 'miniProfile' in str(data) or 'firstName' in str(data):
                        print(f"        Profile data received!")
                except:
                    pass
                return True
            elif status == 403:
                print(f"    {name}: ❌ 403 Forbidden")
            elif status == 401:
                print(f"    {name}: ❌ 401 Unauthorized (cookie expired)")
            else:
                print(f"    {name}: ❌ {status}")
                
        except Exception as e:
            print(f"    {name}: ERROR - {e}")
    
    return False


def test_public_profile():
    """Test scraping a public profile (doesn't require auth)."""
    print(f"\n[4] Testing Public Profile Access...")
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    })
    
    # Test with a public profile
    try:
        response = session.get(
            'https://www.linkedin.com/in/williamhgates/',
            timeout=15
        )
        if response.status_code == 200 and 'Bill Gates' in response.text:
            print("    Public profiles: ✅ Accessible")
            return True
        else:
            print(f"    Public profiles: ❌ Status {response.status_code}")
    except Exception as e:
        print(f"    Public profiles: ERROR - {e}")
    
    return False


def main():
    """Run all LinkedIn validation tests."""
    api_works = validate_linkedin_session()
    public_works = test_public_profile()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if api_works:
        print("✅ LinkedIn Voyager API: Working")
        print("   You can use full scraping capabilities")
    else:
        print("❌ LinkedIn Voyager API: Not working")
        print("   Cookie may be expired or LinkedIn is blocking")
    
    if public_works:
        print("✅ Public Profile Access: Working")
        print("   Can scrape public profiles without auth")
    else:
        print("❌ Public Profile Access: Blocked")
        print("   Your IP may be rate-limited")
    
    print("\n" + "=" * 60)
    print("ALTERNATIVES IF COOKIE AUTH FAILS:")
    print("=" * 60)
    print("""
1. PROXYCURL API (Recommended - $0.01/profile)
   - No cookie needed, uses their infrastructure
   - Add to .env: PROXYCURL_API_KEY=your_key
   - Sign up: https://nubela.co/proxycurl/
   
2. APOLLO.IO (You may already have this)
   - Can search LinkedIn profiles via Apollo
   - Add to .env: APOLLO_API_KEY=your_key
   
3. CLAY (Already integrated)
   - Clay can enrich LinkedIn URLs
   - Use Clay's LinkedIn enrichment instead
   
4. PHANTOMBUSTER ($69/mo)
   - Browser automation for LinkedIn
   - Handles cookies automatically
   
5. MANUAL COOKIE ROTATION
   - Use different browser/device each day
   - Rotate through 2-3 LinkedIn accounts
""")


if __name__ == "__main__":
    main()
