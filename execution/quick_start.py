"""
Quick Start Script for Production Ramp-Up
Guides you through the setup process step-by-step.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
HIVE_MIND = PROJECT_ROOT / ".hive-mind"

# Load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)
except:
    pass


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_step(num: int, text: str):
    """Print a step."""
    print(f"\n  [{num}] {text}")


def check_env_var(name: str, description: str) -> bool:
    """Check if an environment variable is set."""
    value = os.getenv(name, "")
    if value and value != f"your_{name.lower()}" and not value.startswith("your_"):
        print(f"    ✅ {name}: Configured")
        return True
    else:
        print(f"    ❌ {name}: Not configured - {description}")
        return False


def check_prerequisites():
    """Check all prerequisites for production."""
    print_header("🔍 PREREQUISITE CHECK")
    
    # Core APIs
    print("\n  Core APIs:")
    results = {
        "instantly": check_env_var("INSTANTLY_API_KEY", "Get from Instantly.ai → Settings → API"),
        "ghl": check_env_var("GHL_API_KEY", "Get from GoHighLevel → Settings → API"),
        "ghl_location": check_env_var("GHL_LOCATION_ID", "Your GHL location ID"),
        "slack": check_env_var("SLACK_WEBHOOK_URL", "Create at api.slack.com → Apps"),
    }
    
    # AI APIs
    print("\n  AI APIs:")
    results["anthropic"] = check_env_var("ANTHROPIC_API_KEY", "Get from console.anthropic.com")
    results["openai"] = check_env_var("OPENAI_API_KEY", "Get from platform.openai.com")
    
    # Summary
    configured = sum(results.values())
    total = len(results)
    
    print(f"\n  📊 Status: {configured}/{total} APIs configured")
    
    if configured < 4:
        print("\n  ⚠️  Minimum required: INSTANTLY, GHL, GHL_LOCATION, and one AI API")
        return False
    
    return True


def check_data_status():
    """Check what data has been ingested."""
    print_header("📊 DATA STATUS")
    
    checks = [
        (".hive-mind/knowledge/campaigns/_summary.json", "Campaign Analytics"),
        (".hive-mind/knowledge/templates/_summary.json", "Email Templates"),
        (".hive-mind/knowledge/deals/_summary.json", "GHL Deals"),
        (".hive-mind/knowledge/voice_samples/voice_patterns.json", "Voice Patterns"),
        (".hive-mind/icp_calibration.json", "ICP Calibration"),
    ]
    
    ingested = 0
    for path, name in checks:
        full_path = PROJECT_ROOT / path
        if full_path.exists():
            print(f"    ✅ {name}: Available")
            ingested += 1
        else:
            print(f"    ⏳ {name}: Not yet ingested")
    
    print(f"\n  📊 Data Status: {ingested}/{len(checks)} sources ready")
    
    return ingested >= 3


def check_system_health():
    """Run quick health check."""
    print_header("🏥 SYSTEM HEALTH")
    
    try:
        from execution.health_check import run_full_health_check
        health = run_full_health_check()
        
        status_emoji = {
            "healthy": "✅",
            "degraded": "⚠️",
            "initializing": "🔄",
            "error": "❌"
        }
        
        print(f"\n  Overall: {status_emoji.get(health['overall'], '❓')} {health['overall'].upper()}")
        
        for component in health["components"]:
            emoji = status_emoji.get(component["status"], "❓")
            print(f"    {emoji} {component['component']}: {component['status']}")
        
        return health["overall"] in ["healthy", "initializing"]
    except Exception as e:
        print(f"    ❌ Could not run health check: {e}")
        return False


def get_next_action(prereqs_ok: bool, data_ok: bool, health_ok: bool) -> str:
    """Determine the next recommended action."""
    if not prereqs_ok:
        return """
  🎯 NEXT ACTION: Configure APIs
  
  1. Open .env file
  2. Add your API keys
  3. Run this script again
  
  Need help getting API keys? I can guide you through each platform.
"""
    
    if not data_ok:
        return """
  🎯 NEXT ACTION: Ingest Historical Data
  
  Run:
    python execution\\run_full_ingestion.py --full
  
  This will import:
  - Campaign analytics from Instantly
  - Email templates for voice training
  - Deal data from GoHighLevel
"""
    
    if not health_ok:
        return """
  🎯 NEXT ACTION: Review System Health
  
  Some components need attention. Run:
    python execution\\health_check.py
  
  Then check the logs:
    Get-Content .tmp\\logs\\*.log -Tail 50
"""
    
    return """
  🎯 NEXT ACTION: Ready for Production!
  
  Your system is configured. Next steps:
  
  1. Generate AE validation template:
     python execution\\icp_calibrate.py --generate-template
  
  2. Start the dashboard:
     .\\scripts\\start_dashboard.ps1
  
  3. Install scheduler (run as Admin):
     .\\scripts\\setup_scheduler.ps1 -Install
  
  4. Begin pilot with shadow mode:
     $env:SHADOW_MODE = "true"
     .\\scripts\\daily_scrape.ps1
"""


def show_quick_commands():
    """Show useful commands."""
    print_header("⚡ QUICK COMMANDS")
    
    commands = [
        ("Check prerequisites", "python execution\\quick_start.py"),
        ("Run full ingestion", "python execution\\run_full_ingestion.py --full"),
        ("Health check", "python execution\\health_check.py"),
        ("Generate AE template", "python execution\\icp_calibrate.py --generate-template"),
        ("Start dashboard", ".\\scripts\\start_dashboard.ps1"),
        ("Install scheduler", ".\\scripts\\setup_scheduler.ps1 -Install"),
        ("Test alerts", "python execution\\send_alert.py --test"),
        ("Daily report", "python execution\\generate_daily_report.py --print"),
    ]
    
    for name, cmd in commands:
        print(f"  {name}:")
        print(f"    {cmd}")
        print()


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║   🚀 ALPHA SWARM QUICK START                                             ║
║                                                                          ║
║   Production Readiness Assessment                                        ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
    """)
    
    # Run checks
    prereqs_ok = check_prerequisites()
    data_ok = check_data_status()
    health_ok = check_system_health()
    
    # Determine next action
    next_action = get_next_action(prereqs_ok, data_ok, health_ok)
    print_header("🎯 RECOMMENDED ACTION")
    print(next_action)
    
    # Show commands
    show_quick_commands()
    
    # Summary
    print_header("📋 SUMMARY")
    status = []
    if prereqs_ok:
        status.append("✅ APIs configured")
    else:
        status.append("❌ APIs need configuration")
    
    if data_ok:
        status.append("✅ Data ingested")
    else:
        status.append("⏳ Data needs ingestion")
    
    if health_ok:
        status.append("✅ System healthy")
    else:
        status.append("🔄 System initializing")
    
    for s in status:
        print(f"  {s}")
    
    overall_ready = prereqs_ok and data_ok and health_ok
    print(f"\n  {'🟢 PRODUCTION READY' if overall_ready else '🟡 SETUP IN PROGRESS'}")
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()
