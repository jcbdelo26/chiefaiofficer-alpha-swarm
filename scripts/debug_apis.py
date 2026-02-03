#!/usr/bin/env python3
"""Debug API connections with detailed output."""

import os
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

def main():
    print("=== API Debug ===")
    print()
    
    api_key = os.getenv('GHL_API_KEY', '')
    loc_id = os.getenv('GHL_LOCATION_ID', '')
    inst_key = os.getenv('INSTANTLY_API_KEY', '')
    li_cookie = os.getenv('LINKEDIN_COOKIE', '')
    
    print(f"GHL Key length: {len(api_key)}")
    print(f"Location ID: {loc_id}")
    print()
    
    # Test GHL
    print("[1] Testing GoHighLevel...")
    if api_key and loc_id:
        headers = {'Authorization': f'Bearer {api_key}', 'Version': '2021-07-28'}
        try:
            r = requests.get(f'https://services.leadconnectorhq.com/locations/{loc_id}', headers=headers, timeout=15)
            print(f"    Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                name = data.get('location', {}).get('name', 'Unknown')
                print(f"    SUCCESS: Connected to {name}")
            else:
                print(f"    Response: {r.text[:300]}")
        except Exception as e:
            print(f"    Error: {e}")
    else:
        print("    Missing credentials")
    print()
    
    # Test Instantly
    print("[2] Testing Instantly...")
    if inst_key:
        try:
            r = requests.get(f'https://api.instantly.ai/api/v1/account/list?api_key={inst_key}', timeout=15)
            print(f"    Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"    SUCCESS: {len(data)} account(s) found")
            else:
                print(f"    Response: {r.text[:300]}")
        except Exception as e:
            print(f"    Error: {e}")
    else:
        print("    Missing INSTANTLY_API_KEY")
    print()
    
    # Test LinkedIn
    print("[3] Testing LinkedIn...")
    print(f"    Cookie length: {len(li_cookie)} chars")
    if len(li_cookie) < 100:
        print("    WARNING: Cookie seems too short. Should be 200+ chars")
        print("    Make sure you copied the full li_at value from browser cookies")
    if li_cookie:
        headers = {
            'Cookie': f'li_at={li_cookie}',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        try:
            r = requests.get('https://www.linkedin.com/voyager/api/me', headers=headers, timeout=15)
            print(f"    Status: {r.status_code}")
            if r.status_code == 200:
                print("    SUCCESS: Session valid")
            elif r.status_code == 401:
                print("    Cookie expired - need fresh cookie from browser")
            elif r.status_code == 403:
                print("    Access forbidden - cookie may be invalid or incomplete")
        except Exception as e:
            print(f"    Error: {e}")
    else:
        print("    Missing LINKEDIN_COOKIE")
    
    print()
    print("=== Debug Complete ===")

if __name__ == "__main__":
    main()
