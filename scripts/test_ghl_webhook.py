import requests
import json
import sys

# User's Railway URL from screenshot
url = "https://web-production-44810.up.railway.app/api/icp/ghl/outcome"

payload = {
  "type": "opportunity.stageChanged",
  "data": {
    "id": "test_opp_123",
    "contact_id": "test_contact_456",
    "name": "Test Deal for Validation",
    "stage": "closed won",
    "value": 10000,
    "contact": {
      "name": "Test User",
      "email": "test@example.com",
      "company": "Validation Corp"
    },
    "custom_fields": {
      "industry": "Technology",
      "company_size": "51-200",
      "job_title": "CTO",
      "lost_reason": ""
    }
  }
}

print(f"Sending test POST to {url}...")
try:
    response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
    print(f"Response Code: {response.status_code}")
    print(f"Response Body: {response.text}")
    
    if response.status_code == 200:
        print("\n✅ SUCCESS: Connection validated!")
    else:
        print(f"\n❌ FAILED: Server returned {response.status_code}")
        sys.exit(1)

except Exception as e:
    print(f"\n❌ FAILED: {str(e)}")
    sys.exit(1)
