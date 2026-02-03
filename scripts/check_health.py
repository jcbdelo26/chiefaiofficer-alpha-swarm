import requests
import time
import sys

url = "https://web-production-44810.up.railway.app/webhooks/rb2b/health"

print(f"Polling health check at {url}...")

start_time = time.time()
timeout = 180  # 3 minutes

while time.time() - start_time < timeout:
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            
            # Check if new fields exist (indicates new version deployed)
            if "icp_engine_enabled" in data:
                print("\n✅ New version deployed!")
                print(f"Status: {data}")
                
                if data.get("icp_engine_enabled"):
                    print("✅ ICP Engine is ENABLED")
                    sys.exit(0)
                else:
                    print(f"❌ ICP Engine DISABLED. Error: {data.get('icp_error')}")
                    sys.exit(1)
            else:
                print(".", end="", flush=True)  # Still old version
        else:
            print("!", end="", flush=True)  # Error status
            
    except Exception as e:
        print("x", end="", flush=True)  # Connection error
        
    time.sleep(5)

print("\n\n❌ Timeout: Deployment not updated in 3 minutes.")
sys.exit(1)
