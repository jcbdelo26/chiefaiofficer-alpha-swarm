#!/usr/bin/env python3
"""
Test All API Connections
========================
Simple, Windows-compatible API connection tester.
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()


def test_supabase():
    """Test Supabase connection."""
    try:
        from supabase import create_client
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        if not url or not key:
            return False, "Missing SUPABASE_URL or SUPABASE_KEY"
        
        client = create_client(url, key)
        result = client.table('leads').select('id').limit(1).execute()
        return True, "Connected - leads table accessible"
    except Exception as e:
        return False, str(e)[:100]


def test_gohighlevel():
    """Test GoHighLevel connection."""
    try:
        import requests
        api_key = os.getenv('GHL_API_KEY')
        loc_id = os.getenv('GHL_LOCATION_ID')
        
        if not api_key or not loc_id:
            return False, "Missing GHL_API_KEY or GHL_LOCATION_ID"
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Version': '2021-07-28'
        }
        
        url = f'https://services.leadconnectorhq.com/locations/{loc_id}'
        r = requests.get(url, headers=headers, timeout=15)
        
        if r.status_code == 200:
            data = r.json()
            name = data.get('location', {}).get('name', 'Unknown')
            return True, f"Connected to: {name}"
        else:
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:100]


def test_instantly():
    """Test Instantly connection."""
    try:
        import requests
        api_key = os.getenv('INSTANTLY_API_KEY')
        
        if not api_key:
            return False, "Missing INSTANTLY_API_KEY"
        
        url = f'https://api.instantly.ai/api/v1/account/list?api_key={api_key}'
        r = requests.get(url, timeout=15)
        
        if r.status_code == 200:
            data = r.json()
            count = len(data) if isinstance(data, list) else 1
            return True, f"Connected - {count} account(s) found"
        else:
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:100]


def test_linkedin():
    """Test LinkedIn session."""
    try:
        import requests
        cookie = os.getenv('LINKEDIN_COOKIE')
        
        if not cookie:
            return False, "Missing LINKEDIN_COOKIE"
        
        headers = {
            'Cookie': f'li_at={cookie}',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        r = requests.get('https://www.linkedin.com/voyager/api/me', headers=headers, timeout=15)
        
        if r.status_code == 200:
            return True, "Session valid"
        elif r.status_code == 401:
            return False, "Session expired - refresh cookie"
        else:
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:100]


def test_clay():
    """Test Clay API key presence."""
    api_key = os.getenv('CLAY_API_KEY')
    if api_key:
        return True, "API key configured"
    return False, "Missing CLAY_API_KEY"


def test_rb2b():
    """Test RB2B API key presence."""
    api_key = os.getenv('RB2B_API_KEY')
    if api_key:
        return True, "API key configured"
    return False, "Missing RB2B_API_KEY"


def main():
    print("=" * 60)
    print("  CHIEF AI OFFICER - API CONNECTION TEST")
    print("=" * 60)
    print()
    
    tests = [
        ("Supabase", test_supabase),
        ("GoHighLevel", test_gohighlevel),
        ("Instantly", test_instantly),
        ("LinkedIn", test_linkedin),
        ("Clay", test_clay),
        ("RB2B", test_rb2b),
    ]
    
    results = {}
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        print(f"Testing {name}...")
        success, message = test_fn()
        results[name] = {"success": success, "message": message}
        
        status = "PASS" if success else "FAIL"
        print(f"  [{status}] {message}")
        print()
        
        if success:
            passed += 1
        else:
            failed += 1
    
    print("=" * 60)
    print(f"  RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    # Save results
    output = {
        "tested_at": datetime.utcnow().isoformat(),
        "passed": passed,
        "failed": failed,
        "results": results
    }
    
    output_path = Path(__file__).parent.parent / ".hive-mind" / "api_test_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to: {output_path}")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
