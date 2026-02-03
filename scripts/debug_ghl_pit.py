
import requests
import json
import os

# Private Integration Token provided by user
PIT_TOKEN = "pit-0aa0ea7f-921e-4aed-be09-0feff81e09e6"
LOCATION_ID = "FgaFLGYrbGZSBVprTkhR" # From previous valid .env state

def test_v2_connection():
    print(f"\n📡 Testing V2 API (Private Integration)...")
    
    # V2 Endpoint
    url = f"https://services.leadconnectorhq.com/locations/{LOCATION_ID}"
    
    headers = {
        "Authorization": f"Bearer {PIT_TOKEN}",
        "Content-Type": "application/json",
        "Version": "2021-07-28"
    }
    
    try:
        print(f"Connecting to: {url}")
        resp = requests.get(url, headers=headers, timeout=10)
        
        print(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print("✅ SUCCESS! Connected via V2 API.")
            print(f"Response: {json.dumps(data, indent=2)}")
            return True
        else:
            print(f"❌ FAILED. Response: {resp.text}")
            return False
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

if __name__ == "__main__":
    test_v2_connection()
