#!/usr/bin/env python3
"""
Export top priority contacts for manual enrichment.
These are Tier 1/2 contacts missing company data.
"""
import requests
import os
import json
from dotenv import load_dotenv
load_dotenv()

headers = {
    'Authorization': f'Bearer {os.getenv("GHL_PROD_API_KEY")}',
    'Version': '2021-07-28'
}

r = requests.get(
    f'https://services.leadconnectorhq.com/contacts/?locationId={os.getenv("GHL_LOCATION_ID")}&limit=50',
    headers=headers
)

contacts = r.json().get('contacts', [])

print("=" * 80)
print("TOP 10 CONTACTS FOR MANUAL ENRICHMENT")
print("=" * 80)
print()
print("Add Company Name and Job Title to these contacts in GHL dashboard:")
print()

needs_enrichment = []
for c in contacts:
    if not c.get('companyName') and c.get('email'):
        needs_enrichment.append(c)

# Export top 10
for i, c in enumerate(needs_enrichment[:10], 1):
    email = c.get('email', 'N/A')
    name = f"{c.get('firstName', '')} {c.get('lastName', '')}".strip() or 'Unknown'
    ghl_id = c.get('id')
    
    print(f"{i}. {name}")
    print(f"   Email:    {email}")
    print(f"   GHL ID:   {ghl_id}")
    print(f"   Company:  [ADD THIS]")
    print(f"   Title:    [ADD THIS]")
    print()

print("=" * 80)
print("INSTRUCTIONS:")
print("=" * 80)
print("""
1. Go to GHL Dashboard > Contacts
2. Search for each email above
3. Click on the contact
4. Add Company Name and Job Title
5. Save

Alternatively, you can do a quick LinkedIn search for each email
to find their current company and title.

After enriching at least 5 contacts, run:
  python execution/check_enrichment_status.py
""")
