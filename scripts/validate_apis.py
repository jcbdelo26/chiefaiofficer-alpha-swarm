#!/usr/bin/env python3
"""
Comprehensive API Validator
===========================
Tests multiple endpoints for each service to diagnose connection issues.
"""

import os
import sys
import requests
from pathlib import Path

# Force reload of .env
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path, override=True)

print("=" * 70)
print("  COMPREHENSIVE API VALIDATION")
print("=" * 70)
print(f"\nLoading .env from: {env_path}")
print()

# =============================================================================
# GOHIGHLEVEL VALIDATION
# =============================================================================
def validate_gohighlevel():
    print("[1] GoHighLevel API Validation")
    print("-" * 50)
    
    api_key = os.getenv('GHL_API_KEY', '')
    loc_id = os.getenv('GHL_LOCATION_ID', '')
    
    print(f"    API Key: {len(api_key)} chars")
    print(f"    Key starts with: {api_key[:50]}..." if len(api_key) > 50 else f"    Key: {api_key}")
    print(f"    Location ID: {loc_id}")
    
    if not api_key:
        print("    ERROR: GHL_API_KEY is empty")
        return False
    
    if loc_id == 'your_ghl_location_id' or not loc_id:
        print("    ERROR: GHL_LOCATION_ID is placeholder or empty")
        print("    Get it from: GHL > Settings > Business Profile")
        return False
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Version': '2021-07-28'
    }
    
    # Test multiple endpoints
    endpoints = [
        ('Location Info', f'https://services.leadconnectorhq.com/locations/{loc_id}'),
        ('Contacts', f'https://services.leadconnectorhq.com/contacts/?locationId={loc_id}&limit=1'),
        ('Calendars', f'https://services.leadconnectorhq.com/calendars/?locationId={loc_id}'),
    ]
    
    for name, url in endpoints:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            status = "OK" if r.status_code == 200 else f"FAIL ({r.status_code})"
            print(f"    {name}: {status}")
            if r.status_code == 401:
                print(f"        -> Invalid JWT token. Regenerate in GHL > Settings > API Keys")
            elif r.status_code == 403:
                print(f"        -> Permission denied. Check API key scopes")
        except Exception as e:
            print(f"    {name}: ERROR - {e}")
    
    print()
    return True


# =============================================================================
# INSTANTLY VALIDATION
# =============================================================================
def validate_instantly():
    print("[2] Instantly API Validation")
    print("-" * 50)
    
    api_key = os.getenv('INSTANTLY_API_KEY', '')
    
    print(f"    API Key: {len(api_key)} chars")
    print(f"    Key: {api_key[:20]}..." if len(api_key) > 20 else f"    Key: {api_key}")
    
    if not api_key:
        print("    ERROR: INSTANTLY_API_KEY is empty")
        return False
    
    # Detect API version based on key format
    is_v2 = api_key.endswith('==') or '==' in api_key
    
    if is_v2:
        # V2 API uses Bearer token
        print("    Detected: V2 API (Base64 key)")
        headers = {'Authorization': f'Bearer {api_key}'}
        try:
            r = requests.get('https://api.instantly.ai/api/v2/accounts', headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                items = data.get('items', [])
                print(f"    Accounts: OK ({len(items)} account(s) found)")
                if items:
                    print(f"    Primary: {items[0].get('email', 'N/A')}")
                return True
            else:
                print(f"    Accounts: FAIL ({r.status_code})")
                print(f"        -> {r.text[:100]}")
        except Exception as e:
            print(f"    Error: {e}")
    else:
        # V1 API uses query param
        print("    Detected: V1 API")
        try:
            r = requests.get(f'https://api.instantly.ai/api/v1/account/list?api_key={api_key}', timeout=15)
            if r.status_code == 200:
                data = r.json()
                print(f"    Accounts: OK ({len(data)} found)")
                return True
            else:
                print(f"    Accounts: FAIL ({r.status_code})")
        except Exception as e:
            print(f"    Error: {e}")
    
    print()
    print("    TROUBLESHOOTING:")
    print("    1. Go to https://app.instantly.ai")
    print("    2. Click Settings > Integrations > API Keys")
    print("    3. Use Version 2 API key")
    print()
    return False


# =============================================================================
# LINKEDIN VALIDATION
# =============================================================================
def validate_linkedin():
    print("[3] LinkedIn Session Validation")
    print("-" * 50)
    
    cookie = os.getenv('LINKEDIN_COOKIE', '')
    
    print(f"    Cookie length: {len(cookie)} chars")
    
    if not cookie:
        print("    ERROR: LINKEDIN_COOKIE is empty")
        return False
    
    if len(cookie) < 100:
        print("    WARNING: Cookie seems too short!")
        print("    The li_at cookie should be 200-400 characters")
        print()
        print("    HOW TO GET THE CORRECT COOKIE:")
        print("    1. Open Chrome/Edge and go to linkedin.com (make sure you're logged in)")
        print("    2. Press F12 to open Developer Tools")
        print("    3. Go to 'Application' tab (not 'Network')")
        print("    4. In left sidebar: Storage > Cookies > https://www.linkedin.com")
        print("    5. Find 'li_at' in the Name column")
        print("    6. Click on it and copy the ENTIRE Value (very long string)")
        print("    7. Paste into .env WITHOUT quotes")
        print()
        return False
    
    # Check if cookie looks valid
    if not cookie.startswith('AQ'):
        print("    WARNING: LinkedIn li_at cookies typically start with 'AQ'")
    
    headers = {
        'Cookie': f'li_at={cookie}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'x-li-lang': 'en_US',
        'x-restli-protocol-version': '2.0.0',
    }
    
    # Test the API
    try:
        r = requests.get(
            'https://www.linkedin.com/voyager/api/me',
            headers=headers,
            timeout=15
        )
        print(f"    API Status: {r.status_code}")
        
        if r.status_code == 200:
            print("    SUCCESS: LinkedIn session is valid!")
            return True
        elif r.status_code == 401:
            print("    Cookie expired - need to get fresh cookie from browser")
        elif r.status_code == 403:
            print("    Access forbidden - possible causes:")
            print("        - Cookie is incomplete (missing characters)")
            print("        - LinkedIn has rate-limited this session")
            print("        - Cookie was invalidated by LinkedIn")
        else:
            print(f"    Response: {r.text[:200]}")
            
    except Exception as e:
        print(f"    ERROR: {e}")
    
    print()
    return False


# =============================================================================
# CLAY VALIDATION  
# =============================================================================
def validate_clay():
    print("[4] Clay API Validation")
    print("-" * 50)
    
    api_key = os.getenv('CLAY_API_KEY', '')
    print(f"    API Key: {len(api_key)} chars")
    
    if not api_key:
        print("    WARNING: CLAY_API_KEY is empty (optional)")
        return False
    
    # Clay doesn't have a simple health endpoint, so we just verify key exists
    print("    Key configured: YES")
    print("    (Full validation requires actual API call with credits)")
    print()
    return True


# =============================================================================
# RB2B VALIDATION
# =============================================================================
def validate_rb2b():
    print("[5] RB2B API Validation")
    print("-" * 50)
    
    api_key = os.getenv('RB2B_API_KEY', '')
    print(f"    API Key: {len(api_key)} chars")
    
    if not api_key:
        print("    WARNING: RB2B_API_KEY is empty (optional)")
        return False
    
    print("    Key configured: YES")
    print()
    return True


# =============================================================================
# MAIN
# =============================================================================
def main():
    results = {
        'GoHighLevel': validate_gohighlevel(),
        'Instantly': validate_instantly(),
        'LinkedIn': validate_linkedin(),
        'Clay': validate_clay(),
        'RB2B': validate_rb2b(),
    }
    
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    
    for service, status in results.items():
        icon = "PASS" if status else "FAIL"
        print(f"    [{icon}] {service}")
    
    print()
    
    # Check if .env might have caching issues
    print("TIP: If you just updated .env and values seem stale,")
    print("     try closing and reopening your terminal/IDE.")
    print()


if __name__ == "__main__":
    main()
