#!/usr/bin/env python3
"""
Production Environment Verification Script
===========================================
Verifies all required environment variables and API connections.

Usage:
    python execution/verify_production_env.py
    python execution/verify_production_env.py --verbose
    python execution/verify_production_env.py --test-connections
"""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

# Try to import aiohttp for async HTTP
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

# Try to import rich for pretty output
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class EnvVar:
    """Environment variable definition."""
    name: str
    required: bool = True
    description: str = ""
    test_endpoint: Optional[str] = None
    secret: bool = True


# Required environment variables from production.json
REQUIRED_VARS: List[EnvVar] = [
    EnvVar("GHL_PROD_API_KEY", True, "GoHighLevel Production API Key", "https://services.leadconnectorhq.com/locations/"),
    EnvVar("GHL_LOCATION_ID", True, "GoHighLevel Location ID"),
    EnvVar("SUPABASE_URL", True, "Supabase Project URL"),
    EnvVar("SUPABASE_KEY", True, "Supabase Anon Key"),
    EnvVar("CLAY_API_KEY", True, "Clay API Key", "https://api.clay.com/v1/tables"),
    EnvVar("SLACK_WEBHOOK_URL", True, "Slack Webhook URL"),
    EnvVar("RB2B_API_KEY", True, "RB2B API Key"),
    EnvVar("RB2B_WEBHOOK_SECRET", True, "RB2B Webhook Secret"),
]

OPTIONAL_VARS: List[EnvVar] = [
    EnvVar("SLACK_BOT_TOKEN", False, "Slack Bot Token for interactive approvals"),
    EnvVar("TWILIO_ACCOUNT_SID", False, "Twilio Account SID for SMS"),
    EnvVar("TWILIO_AUTH_TOKEN", False, "Twilio Auth Token"),
    EnvVar("TWILIO_FROM_NUMBER", False, "Twilio Phone Number"),
    EnvVar("ESCALATION_PHONE_L2", False, "AE Phone for Hot Lead Alerts"),
    EnvVar("ESCALATION_PHONE_L3", False, "VP Phone for Critical Escalations"),
    EnvVar("ESCALATION_EMAIL_L2", False, "AE Email"),
    EnvVar("ESCALATION_EMAIL_L3", False, "VP Email"),
    EnvVar("GOOGLE_CREDENTIALS_PATH", False, "Google OAuth Credentials Path", secret=False),
    EnvVar("GOOGLE_TOKEN_PATH", False, "Google Token Path", secret=False),
    EnvVar("ZOOM_API_KEY", False, "Zoom API Key"),
    EnvVar("ZOOM_API_SECRET", False, "Zoom API Secret"),
    EnvVar("PROXYCURL_API_KEY", False, "Proxycurl API Key for LinkedIn"),
]


@dataclass
class VerificationResult:
    """Result of environment verification."""
    var_name: str
    exists: bool
    value_preview: str = ""
    connected: Optional[bool] = None
    connection_error: Optional[str] = None
    required: bool = True


# =============================================================================
# VERIFICATION FUNCTIONS
# =============================================================================

def check_env_var(var: EnvVar) -> VerificationResult:
    """Check if an environment variable exists and has a value."""
    value = os.getenv(var.name)
    exists = value is not None and len(value) > 0
    
    # Create preview (masked for secrets)
    if exists and var.secret:
        preview = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "****"
    elif exists:
        preview = value[:50] + "..." if len(value) > 50 else value
    else:
        preview = "(not set)"
    
    return VerificationResult(
        var_name=var.name,
        exists=exists,
        value_preview=preview,
        required=var.required
    )


async def test_ghl_connection() -> Tuple[bool, str]:
    """Test GoHighLevel API connection."""
    if not AIOHTTP_AVAILABLE:
        return False, "aiohttp not installed"
    
    api_key = os.getenv("GHL_PROD_API_KEY")
    location_id = os.getenv("GHL_LOCATION_ID")
    
    if not api_key or not location_id:
        return False, "Missing API key or Location ID"
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Version": "2021-07-28"
            }
            url = f"https://services.leadconnectorhq.com/locations/{location_id}"
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    return True, "Connected"
                elif resp.status == 401:
                    return False, "401 Unauthorized - Check API key"
                elif resp.status == 404:
                    return False, "404 Not Found - Check Location ID"
                else:
                    return False, f"HTTP {resp.status}"
    except asyncio.TimeoutError:
        return False, "Connection timeout"
    except Exception as e:
        return False, str(e)


async def test_supabase_connection() -> Tuple[bool, str]:
    """Test Supabase connection."""
    if not AIOHTTP_AVAILABLE:
        return False, "aiohttp not installed"
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        return False, "Missing URL or Key"
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "apikey": key,
                "Authorization": f"Bearer {key}"
            }
            # Test with a simple health check
            test_url = f"{url}/rest/v1/"
            async with session.get(test_url, headers=headers, timeout=10) as resp:
                if resp.status in [200, 404]:  # 404 is OK - means connected but no default table
                    return True, "Connected"
                elif resp.status == 401:
                    return False, "401 Unauthorized - Check API key"
                else:
                    return False, f"HTTP {resp.status}"
    except asyncio.TimeoutError:
        return False, "Connection timeout"
    except Exception as e:
        return False, str(e)


async def test_slack_webhook() -> Tuple[bool, str]:
    """Test Slack webhook (dry run - doesn't actually send)."""
    if not AIOHTTP_AVAILABLE:
        return False, "aiohttp not installed"
    
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    
    if not webhook_url:
        return False, "Missing webhook URL"
    
    if not webhook_url.startswith("https://hooks.slack.com/"):
        return False, "Invalid webhook URL format"
    
    # We can't truly test without sending, so just validate format
    return True, "URL format valid (not tested)"


async def test_clay_connection() -> Tuple[bool, str]:
    """Test Clay API connection."""
    if not AIOHTTP_AVAILABLE:
        return False, "aiohttp not installed"
    
    api_key = os.getenv("CLAY_API_KEY")
    
    if not api_key:
        return False, "Missing API key"
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {api_key}"}
            async with session.get("https://api.clay.com/v1/tables", headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    return True, "Connected"
                elif resp.status == 401:
                    return False, "401 Unauthorized - Check API key"
                else:
                    return False, f"HTTP {resp.status}"
    except asyncio.TimeoutError:
        return False, "Connection timeout"
    except Exception as e:
        return False, str(e)


async def run_connection_tests() -> Dict[str, Tuple[bool, str]]:
    """Run all connection tests."""
    tests = {
        "GHL": test_ghl_connection(),
        "Supabase": test_supabase_connection(),
        "Slack": test_slack_webhook(),
        "Clay": test_clay_connection(),
    }
    
    results = {}
    for name, coro in tests.items():
        try:
            results[name] = await coro
        except Exception as e:
            results[name] = (False, str(e))
    
    return results


# =============================================================================
# OUTPUT FUNCTIONS
# =============================================================================

def print_results_rich(required_results: List[VerificationResult], 
                       optional_results: List[VerificationResult],
                       connection_results: Optional[Dict[str, Tuple[bool, str]]] = None):
    """Print results using rich library."""
    # Required variables table
    table = Table(title="Required Environment Variables")
    table.add_column("Variable", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Preview")
    
    for r in required_results:
        status = "✅ Set" if r.exists else "❌ Missing"
        style = "green" if r.exists else "red"
        table.add_row(r.var_name, f"[{style}]{status}[/{style}]", r.value_preview)
    
    console.print(table)
    console.print()
    
    # Optional variables table
    table2 = Table(title="Optional Environment Variables")
    table2.add_column("Variable", style="cyan")
    table2.add_column("Status")
    table2.add_column("Preview")
    
    for r in optional_results:
        status = "✅ Set" if r.exists else "⬜ Not set"
        style = "green" if r.exists else "dim"
        table2.add_row(r.var_name, f"[{style}]{status}[/{style}]", r.value_preview)
    
    console.print(table2)
    console.print()
    
    # Connection results
    if connection_results:
        table3 = Table(title="API Connection Tests")
        table3.add_column("Service", style="cyan")
        table3.add_column("Status", style="bold")
        table3.add_column("Details")
        
        for service, (success, msg) in connection_results.items():
            status = "✅ Connected" if success else "❌ Failed"
            style = "green" if success else "red"
            table3.add_row(service, f"[{style}]{status}[/{style}]", msg)
        
        console.print(table3)
        console.print()
    
    # Summary
    required_set = sum(1 for r in required_results if r.exists)
    required_total = len(required_results)
    optional_set = sum(1 for r in optional_results if r.exists)
    optional_total = len(optional_results)
    
    if required_set == required_total:
        console.print(Panel(
            f"[green]✅ All {required_total} required variables set[/green]\n"
            f"[dim]{optional_set}/{optional_total} optional variables set[/dim]",
            title="Environment Status",
            style="green"
        ))
    else:
        missing = [r.var_name for r in required_results if not r.exists]
        console.print(Panel(
            f"[red]❌ Missing {required_total - required_set} required variables:[/red]\n"
            f"[yellow]{', '.join(missing)}[/yellow]",
            title="Environment Status",
            style="red"
        ))


def print_results_plain(required_results: List[VerificationResult], 
                        optional_results: List[VerificationResult],
                        connection_results: Optional[Dict[str, Tuple[bool, str]]] = None):
    """Print results without rich library."""
    print("\n" + "=" * 60)
    print("REQUIRED ENVIRONMENT VARIABLES")
    print("=" * 60)
    
    for r in required_results:
        status = "✅" if r.exists else "❌"
        print(f"{status} {r.var_name}: {r.value_preview}")
    
    print("\n" + "=" * 60)
    print("OPTIONAL ENVIRONMENT VARIABLES")
    print("=" * 60)
    
    for r in optional_results:
        status = "✅" if r.exists else "⬜"
        print(f"{status} {r.var_name}: {r.value_preview}")
    
    if connection_results:
        print("\n" + "=" * 60)
        print("API CONNECTION TESTS")
        print("=" * 60)
        
        for service, (success, msg) in connection_results.items():
            status = "✅" if success else "❌"
            print(f"{status} {service}: {msg}")
    
    # Summary
    required_set = sum(1 for r in required_results if r.exists)
    required_total = len(required_results)
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if required_set == required_total:
        print(f"✅ All {required_total} required variables set")
    else:
        missing = [r.var_name for r in required_results if not r.exists]
        print(f"❌ Missing {required_total - required_set} required variables:")
        for m in missing:
            print(f"   - {m}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Verify production environment")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all details")
    parser.add_argument("--test-connections", "-t", action="store_true", help="Test API connections")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    # Check required variables
    required_results = [check_env_var(var) for var in REQUIRED_VARS]
    optional_results = [check_env_var(var) for var in OPTIONAL_VARS]
    
    # Test connections if requested
    connection_results = None
    if args.test_connections:
        if not AIOHTTP_AVAILABLE:
            print("Warning: aiohttp not installed, cannot test connections")
            print("Install with: pip install aiohttp")
        else:
            connection_results = asyncio.run(run_connection_tests())
    
    # Output
    if args.json:
        output = {
            "timestamp": datetime.now().isoformat(),
            "required": [
                {"name": r.var_name, "exists": r.exists, "preview": r.value_preview}
                for r in required_results
            ],
            "optional": [
                {"name": r.var_name, "exists": r.exists, "preview": r.value_preview}
                for r in optional_results
            ],
            "connections": connection_results,
            "all_required_set": all(r.exists for r in required_results)
        }
        print(json.dumps(output, indent=2))
    elif RICH_AVAILABLE:
        print_results_rich(required_results, optional_results, connection_results)
    else:
        print_results_plain(required_results, optional_results, connection_results)
    
    # Exit code
    all_required = all(r.exists for r in required_results)
    sys.exit(0 if all_required else 1)


if __name__ == "__main__":
    main()
