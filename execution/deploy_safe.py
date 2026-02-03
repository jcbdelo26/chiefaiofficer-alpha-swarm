
import subprocess
import sys
import webbrowser
import time
from pathlib import Path

def run_command(cmd, shell=True, check=True):
    try:
        # Use Popen to stream output if needed, but run is simpler for now
        result = subprocess.run(cmd, shell=shell, check=check, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error running command: {cmd}")
        print(f"Error Code: {e.returncode}")
        print(f"Output: {e.stdout}")
        print(f"Error: {e.stderr}")
        return None

def main():
    print("="*60)
    print("🚀 SAFE DEPLOYMENT PROTOCOL - Chief AI Officer Swarm")
    print("="*60)
    
    # 1. Check Directory
    cwd = Path.cwd()
    if not (cwd / "Procfile").exists():
        print("❌ Error: Procfile not found. Are you in the root directory?")
        sys.exit(1)

    # 2. Git Status Check
    print("\n🔍 1. checking Git Status...")
    status = run_command("git status --porcelain", check=False)
    if status:
        print("⚠️  Warning: You have uncommitted changes:")
        # Print first few lines
        lines = status.split('\n')
        for line in lines[:5]:
            print(f"   {line}")
        if len(lines) > 5:
            print(f"   ... and {len(lines)-5} more.")
            
        confirm = input("\n👉 Do you want to AUTO-COMMIT these changes ('msg: auto-deploy')? (y/n): ")
        if confirm.lower().startswith('y'):
            print("   Committing...")
            run_command('git add .')
            run_command('git commit -m "chore: auto-deploy via deploy_safe.py"')
            print("   ✅ Committed.")
        else:
            print("❌ Deployment aborted. Please commit your changes strictly.")
            sys.exit(1)
    else:
        print("✅ Git is clean.")

    # 3. Railway Check
    print("\n🚂 2. Verifying Railway Connection...")
    
    # Try different railway paths
    railway_cmd = "railway"
    
    # Check if 'railway' is in PATH
    if run_command("railway --version", check=False) is None:
        # Fallback to NPM global path
        npm_path = Path(r"C:\Users\ADMIN\AppData\Roaming\npm\railway.cmd")
        if npm_path.exists():
            railway_cmd = str(npm_path)
            print(f"   (Using detected path: {railway_cmd})")
        else:
            print("⚠️  Railway CLI not found in PATH or standard locations.")
            confirm = input("👉 Attempt deployment anyway? (y/n): ")
            if not confirm.lower().startswith('y'):
                sys.exit(1)
    else:
        print("✅ Railway CLI detected in PATH.")

    # 4. Deployment
    print("\n🚀 3. Triggering Production Deployment...")
    print(f"   Running: {railway_cmd} up --detach")
    
    # We allow this to stream or just run
    start_time = time.time()
    result = run_command(f"{railway_cmd} up --detach", check=False)
    
    if result is not None:
        print("\n✅ Deployment Initiated Successfully!")
        elapsed = time.time() - start_time
        print(f"   Command took {elapsed:.1f}s")
        
        print("\n🌐 Dashboard URL:")
        dash_url = "https://caio-swarm-dashboard-production.up.railway.app/sales?token=<REDACTED>"
        print(f"   {dash_url}")
        
        # open browser
        try:
            webbrowser.open(dash_url)
            print("   (Opened in default browser)")
        except:
            pass
            
    else:
        print("\n❌ Deployment Failed. Check logs above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
