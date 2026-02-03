import os
from dotenv import load_dotenv
from supabase import create_client, Client
import sys

# Load env
load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

if not url or not key:
    print("Error: SUPABASE_URL or SUPABASE_KEY not found in .env")
    sys.exit(1)

try:
    print(f"Connecting to Supabase at {url}...")
    supabase: Client = create_client(url, key)
    
    # Try to select from one of the new tables
    print("Checking 'icp_learning' table...")
    response = supabase.table("icp_learning").select("*").limit(1).execute()
    print("✅ 'icp_learning' table accessible.")
    
    print("Checking 'icp_weights' table...")
    response = supabase.table("icp_weights").select("*").limit(1).execute()
    print("✅ 'icp_weights' table accessible.")

    print("Checking 'icp_reports' table...")
    response = supabase.table("icp_reports").select("*").limit(1).execute()
    print("✅ 'icp_reports' table accessible.")
    
    print("\nSUCCESS: All new ICP tables are accessible and ready!")
    
except Exception as e:
    print(f"\n❌ FAILED: {str(e)}")
    print("Make sure the tables were created in the 'public' schema.")
    sys.exit(1)
