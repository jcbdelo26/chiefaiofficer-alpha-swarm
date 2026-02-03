#!/usr/bin/env python3
"""Quick Supabase connection test."""
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')

print(f"URL: {'SET' if url else 'MISSING'}")
print(f"KEY: {'SET' if key else 'MISSING'}")

if url and key:
    print(f"Connecting to: {url[:40]}...")
    
    from supabase import create_client
    client = create_client(url, key)
    
    try:
        result = client.table('leads').select('id').limit(1).execute()
        print("SUCCESS: Connected to Supabase!")
        print(f"leads table accessible: {len(result.data)} rows returned")
    except Exception as e:
        print(f"Error: {e}")
else:
    print("Missing credentials in .env")
