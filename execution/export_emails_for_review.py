#!/usr/bin/env python3
"""Export shadow emails for Dani's review."""

import json
from pathlib import Path

shadow_dir = Path('.hive-mind/shadow_mode_emails')
emails = []

for f in sorted(shadow_dir.glob('*.json'), reverse=True)[:15]:
    try:
        with open(f) as fp:
            data = json.load(fp)
            # Skip canary/test emails
            if 'canary' in f.stem:
                continue
            emails.append({
                'file': f.name,
                'contact_id': data.get('contact_id', 'N/A'),
                'to': data.get('to', 'N/A'),
                'subject': data.get('subject', 'N/A'),
                'body_preview': data.get('body_preview', data.get('body', ''))[:200],
                'tier': data.get('tier', 'N/A'),
                'status': data.get('status', 'pending'),
                'company': data.get('recipient_data', {}).get('company') or data.get('contact_name', 'Unknown')
            })
    except Exception as e:
        print(f"Error reading {f}: {e}")

print("=" * 80)
print("PHASE 2 - EMAIL QUALITY REVIEW")
print("=" * 80)
print()

for i, e in enumerate(emails[:5], 1):
    print(f"EMAIL #{i}")
    print("-" * 40)
    print(f"Tier:    {e['tier']}")
    print(f"Company: {e['company']}")
    print(f"To:      {e['to']}")
    print(f"Subject: {e['subject']}")
    print(f"Preview: {e['body_preview'][:150]}...")
    print(f"File:    {e['file']}")
    print()

print("=" * 80)
print("REVIEW TEMPLATE")
print("=" * 80)
print("""
| Email # | Company | Subject Quality (1-5) | Personalization (1-5) | CTA Clarity (1-5) | Overall (1-5) | Feedback |
|---------|---------|----------------------:|----------------------:|------------------:|--------------:|----------|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |
| 4 | | | | | | |
| 5 | | | | | | |

**Average score must be ≥ 3.5 to proceed to Phase 3**
""")
