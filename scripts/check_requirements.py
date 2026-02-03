#!/usr/bin/env python3
"""
CAIO RevOps Swarm - Requirements Checker
=========================================
Run this script to verify all dependencies and credentials are properly configured.
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def check_python_version():
    """Check Python version."""
    version = sys.version_info
    if version.major == 3 and version.minor >= 10:
        return True, f"Python {version.major}.{version.minor}.{version.micro}"
    return False, f"Python {version.major}.{version.minor} (need 3.10+)"

def check_env_file():
    """Check if .env file exists."""
    env_path = PROJECT_ROOT / ".env"
    example_path = PROJECT_ROOT / ".env.example"
    
    if env_path.exists():
        return True, ".env file found"
    elif example_path.exists():
        return False, ".env missing - copy from .env.example"
    return False, ".env missing - no template found"

def check_env_variables():
    """Check required environment variables."""
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    
    required = {
        "GHL_API_KEY": "GoHighLevel API key",
        "SUPABASE_URL": "Supabase project URL",
        "SUPABASE_KEY": "Supabase API key",
    }
    
    optional = {
        "CLAY_API_KEY": "Clay enrichment",
        "PROXYCURL_API_KEY": "LinkedIn enrichment",
        "GOOGLE_CREDENTIALS_PATH": "Google Calendar/Gmail",
    }
    
    missing_required = []
    missing_optional = []
    
    for var, desc in required.items():
        if not os.getenv(var):
            missing_required.append(f"{var} ({desc})")
    
    for var, desc in optional.items():
        if not os.getenv(var):
            missing_optional.append(f"{var} ({desc})")
    
    if missing_required:
        return False, f"Missing required: {', '.join(missing_required)}"
    
    if missing_optional:
        return True, f"Optional missing: {', '.join(missing_optional[:2])}"
    
    return True, "All environment variables set"

def check_directories():
    """Check required directories exist."""
    dirs = [
        ".hive-mind",
        ".hive-mind/knowledge",
        "credentials",
    ]
    
    missing = []
    for d in dirs:
        path = PROJECT_ROOT / d
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
    
    return True, "Directories ready"

def check_core_modules():
    """Check core modules can be imported."""
    try:
        from core.unified_guardrails import UnifiedGuardrails
        from core.unified_integration_gateway import get_gateway
        from core.unified_health_monitor import HealthMonitor
        return True, "Core modules OK"
    except ImportError as e:
        return False, f"Import error: {e}"

def check_dependencies():
    """Check Python dependencies."""
    missing = []
    
    packages = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("dotenv", "python-dotenv"),
        ("websockets", "WebSockets"),
    ]
    
    for module, name in packages:
        try:
            __import__(module)
        except ImportError:
            missing.append(name)
    
    if missing:
        return False, f"Missing packages: {', '.join(missing)}"
    return True, "All packages installed"

def main():
    """Run all checks."""
    print("\n" + "=" * 60)
    print("  CAIO RevOps Swarm - Requirements Check")
    print("=" * 60 + "\n")
    
    checks = [
        ("Python Version", check_python_version),
        ("Environment File", check_env_file),
        ("Directories", check_directories),
        ("Dependencies", check_dependencies),
        ("Core Modules", check_core_modules),
        ("Environment Variables", check_env_variables),
    ]
    
    all_passed = True
    
    for name, check_fn in checks:
        try:
            passed, message = check_fn()
        except Exception as e:
            passed, message = False, str(e)
        
        icon = "[OK]" if passed else "[FAIL]"
        print(f"  {icon} {name}: {message}")
        
        if not passed:
            all_passed = False
    
    print("\n" + "-" * 60)
    
    if all_passed:
        print("  [OK] All checks passed! Ready to start.")
        print("\n  Run: powershell scripts/start_local.ps1")
        print("  Or:  python -m uvicorn dashboard.health_app:app --port 8080")
    else:
        print("  [FAIL] Some checks failed. Please fix issues above.")
        print("\n  Common fixes:")
        print("    1. Copy .env.example to .env and add your API keys")
        print("    2. Run: pip install -r requirements.txt")
    
    print("\n" + "=" * 60 + "\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
