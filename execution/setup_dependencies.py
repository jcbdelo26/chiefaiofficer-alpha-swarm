#!/usr/bin/env python3
"""
Setup Missing Dependencies
==========================
Installs missing Python packages required for API connections.

Usage:
    python execution/setup_dependencies.py
"""

import subprocess
import sys
from pathlib import Path

# Required packages for API connections
REQUIRED_PACKAGES = {
    'anthropic': 'anthropic>=0.8.0',
    'supabase': 'supabase>=2.0.0',
    'redis': 'redis>=5.0.0',
    'schedule': 'schedule>=1.2.0',
    'requests': 'requests>=2.31.0',
    'python-dotenv': 'python-dotenv>=1.0.0',
}

def check_package(package_name):
    """Check if a package is installed."""
    try:
        __import__(package_name.replace('-', '_'))
        return True
    except ImportError:
        return False

def install_package(package_spec):
    """Install a package using pip."""
    try:
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', package_spec
        ])
        return True
    except subprocess.CalledProcessError:
        return False

def main():
    print("=" * 60)
    print("Chief AI Officer Alpha Swarm - Dependency Setup")
    print("=" * 60)
    print()
    
    missing_packages = []
    
    # Check which packages are missing
    print("🔍 Checking installed packages...\n")
    for package_name, package_spec in REQUIRED_PACKAGES.items():
        if check_package(package_name):
            print(f"  ✅ {package_name} - already installed")
        else:
            print(f"  ❌ {package_name} - missing")
            missing_packages.append((package_name, package_spec))
    
    if not missing_packages:
        print("\n✅ All required packages are installed!")
        return 0
    
    print(f"\n📦 Found {len(missing_packages)} missing package(s)")
    print("\nInstalling missing packages...\n")
    
    # Install missing packages
    failed = []
    for package_name, package_spec in missing_packages:
        print(f"Installing {package_name}...")
        if install_package(package_spec):
            print(f"  ✅ {package_name} installed successfully")
        else:
            print(f"  ❌ {package_name} installation failed")
            failed.append(package_name)
    
    print("\n" + "=" * 60)
    if failed:
        print(f"⚠️  {len(failed)} package(s) failed to install:")
        for package in failed:
            print(f"  - {package}")
        print("\nTry installing manually:")
        print(f"  pip install {' '.join(REQUIRED_PACKAGES[p] for p in failed)}")
        return 1
    else:
        print("✅ All packages installed successfully!")
        print("\nNext steps:")
        print("  1. Update API keys in .env file")
        print("  2. Run: python execution/test_connections.py")
        return 0

if __name__ == "__main__":
    sys.exit(main())
