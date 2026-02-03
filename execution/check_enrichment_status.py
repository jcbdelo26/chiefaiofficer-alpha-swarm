#!/usr/bin/env python3
"""Check if GHL contacts have been enriched."""
import requests
import os
from dotenv import load_dotenv
load_dotenv()

headers = {
    'Authorization': f'Bearer {os.getenv("GHL_PROD_API_KEY")}',
    'Version': '2021-07-28'
}

r = requests.get(
    f'https://services.leadconnectorhq.com/contacts/?locationId={os.getenv("GHL_LOCATION_ID")}&limit=15',
    headers=headers
)

contacts = r.json().get('contacts', [])
print("=" * 70)
print("GHL CONTACT ENRICHMENT STATUS")
print("=" * 70)

enriched = 0
missing = 0

for c in contacts:
    company = c.get('companyName', '')
    title = c.get('title', '')
    name = f"{c.get('firstName', '')} {c.get('lastName', '')}"
    
    status = "✅" if company else "❌"
    if company:
        enriched += 1
    else:
        missing += 1
    
    print(f"{status} {name[:20]:<20} | Company: {company[:25] if company else 'MISSING':<25} | Title: {title[:20] if title else 'MISSING'}")

print("=" * 70)
print(f"Enriched: {enriched}/{len(contacts)} ({100*enriched/len(contacts):.0f}%)")
print(f"Missing:  {missing}/{len(contacts)}")
