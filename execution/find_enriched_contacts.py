#!/usr/bin/env python3
"""Find contacts that already have company data."""
import requests
import os
from dotenv import load_dotenv
load_dotenv()

headers = {
    'Authorization': f'Bearer {os.getenv("GHL_PROD_API_KEY")}',
    'Version': '2021-07-28'
}

r = requests.get(
    f'https://services.leadconnectorhq.com/contacts/?locationId={os.getenv("GHL_LOCATION_ID")}&limit=100',
    headers=headers
)

contacts = r.json().get('contacts', [])

print("CONTACTS WITH COMPANY DATA (Ready for Email Generation)")
print("=" * 70)

has_company = []
for c in contacts:
    if c.get('companyName') and c.get('email'):
        has_company.append(c)

if has_company:
    for i, c in enumerate(has_company[:10], 1):
        print(f"{i}. {c.get('firstName', '')} {c.get('lastName', '')} | {c.get('companyName')} | {c.get('email')}")
    print(f"\nTotal with company data: {len(has_company)}")
else:
    print("No contacts have company data yet.")
    print("\nCONTACTS NEEDING ENRICHMENT:")
    print("-" * 70)
    for i, c in enumerate(contacts[:10], 1):
        name = f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
        email = c.get('email', 'No email')
        print(f"{i}. {name:<25} | {email}")
