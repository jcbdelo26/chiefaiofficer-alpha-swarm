#!/usr/bin/env python3
"""Quick LinkedIn cookie check."""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv(Path(__file__).parent.parent / '.env', override=True)

li_at = os.getenv('LINKEDIN_COOKIE', '')

print("=== LinkedIn Cookie Analysis ===")
print(f"Length: {len(li_at)}")
print(f"Starts with AQ: {li_at.startswith('AQ')}")
print(f"Full value: {li_at}")
print()

# Check for common issues
if len(li_at) < 150:
    print("[ISSUE] Cookie is too short! Should be 150-400 chars.")
    print("        Make sure you copied the FULL value from DevTools.")
elif len(li_at) < 200:
    print("[WARNING] Cookie might be truncated. Expected 200-400 chars.")
else:
    print("[OK] Cookie length looks good.")

print()
print("=== API Test ===")

headers = {
    'Cookie': f'li_at={li_at}',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'x-restli-protocol-version': '2.0.0',
}

try:
    r = requests.get('https://www.linkedin.com/voyager/api/me', headers=headers, timeout=15)
    print(f"Status: {r.status_code}")
    
    if r.status_code == 200:
        print("Result: SUCCESS! LinkedIn API is working.")
    elif r.status_code == 403:
        print("Result: FORBIDDEN")
        print()
        print("Possible causes:")
        print("1. Cookie needs JSESSIONID companion cookie")
        print("2. LinkedIn detected automated access")
        print("3. Account may be temporarily restricted")
        print()
        print("RECOMMENDED: Use alternative services (see below)")
    elif r.status_code == 401:
        print("Result: UNAUTHORIZED - Cookie expired")
    else:
        print(f"Result: Unexpected status {r.status_code}")
        
except Exception as e:
    print(f"Error: {e}")

print()
print("=== ALTERNATIVES ===")
print("""
Since LinkedIn cookie auth is unreliable, consider these alternatives:

1. PROXYCURL ($0.01/profile) - RECOMMENDED
   - API-based, no cookies needed
   - Sign up: https://nubela.co/proxycurl/
   - Add: PROXYCURL_API_KEY=xxx to .env

2. CLAY ENRICHMENT (Already configured)
   - Use Clay's LinkedIn enrichment
   - Works via Clay credits, no cookie needed
   
3. APOLLO.IO
   - Search by email/name, get LinkedIn data
   - Add: APOLLO_API_KEY=xxx to .env

4. SALES NAVIGATOR API (Enterprise)
   - Official LinkedIn API for sales
   - Requires partnership application

For now, your swarm can still:
- Use GHL for CRM/outreach (WORKING)
- Use Clay for enrichment (WORKING)
- Use Instantly for email (WORKING)

LinkedIn scraping can be added later via Proxycurl.
""")
