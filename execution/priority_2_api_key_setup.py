#!/usr/bin/env python3
"""
Priority #2: Production API Key Setup & Verification
=====================================================
Verify all required API connections for live production.

Features:
- Check all required environment variables
- Test each API connection
- Generate setup instructions for missing keys
- Create production readiness report

Usage:
    python execution/priority_2_api_key_setup.py
    python execution/priority_2_api_key_setup.py --test-connections
"""

import os
import sys
import json
import asyncio
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import httpx

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()


class ConnectionStatus(Enum):
    """API connection status."""
    CONNECTED = "connected"
    MISSING_KEY = "missing_key"
    INVALID_KEY = "invalid_key"
    CONNECTION_ERROR = "connection_error"
    NOT_TESTED = "not_tested"


@dataclass
class APIConnection:
    """API connection configuration and status."""
    name: str
    env_var: str
    required: bool
    purpose: str
    setup_url: str
    test_endpoint: Optional[str] = None
    status: ConnectionStatus = ConnectionStatus.NOT_TESTED
    error_message: Optional[str] = None
    
    def has_key(self) -> bool:
        """Check if environment variable is set."""
        value = os.getenv(self.env_var)
        return value is not None and len(value) > 0 and value != "your_key_here"


# =============================================================================
# API CONFIGURATIONS
# =============================================================================

API_CONNECTIONS = [
    # Critical - Required for production
    APIConnection(
        name="GoHighLevel (Production)",
        env_var="GHL_PROD_API_KEY",
        required=True,
        purpose="CRM operations, email sending, contact management",
        setup_url="https://highlevel.com/developers",
        test_endpoint="https://services.leadconnectorhq.com/contacts/"
    ),
    APIConnection(
        name="GoHighLevel Location ID",
        env_var="GHL_LOCATION_ID",
        required=True,
        purpose="Identifies your GHL sub-account",
        setup_url="https://highlevel.com/developers"
    ),
    APIConnection(
        name="Supabase URL",
        env_var="SUPABASE_URL",
        required=True,
        purpose="Database for lead storage and audit trails",
        setup_url="https://supabase.com/dashboard"
    ),
    APIConnection(
        name="Supabase Key",
        env_var="SUPABASE_KEY",
        required=True,
        purpose="Authentication for Supabase database",
        setup_url="https://supabase.com/dashboard"
    ),
    
    # Important - Needed for full functionality
    APIConnection(
        name="RB2B API Key",
        env_var="RB2B_API_KEY",
        required=True,
        purpose="Website visitor identification",
        setup_url="https://rb2b.com/integrations"
    ),
    APIConnection(
        name="RB2B Webhook Secret",
        env_var="RB2B_WEBHOOK_SECRET",
        required=False,
        purpose="Secure webhook verification",
        setup_url="https://rb2b.com/integrations"
    ),
    APIConnection(
        name="Clay API Key",
        env_var="CLAY_API_KEY",
        required=True,
        purpose="Lead enrichment (email, company data)",
        setup_url="https://clay.com/integrations"
    ),
    APIConnection(
        name="Slack Webhook URL",
        env_var="SLACK_WEBHOOK_URL",
        required=True,
        purpose="Notifications and approval requests",
        setup_url="https://api.slack.com/apps"
    ),
    
    # Optional - Enhanced functionality
    APIConnection(
        name="OpenAI API Key",
        env_var="OPENAI_API_KEY",
        required=False,
        purpose="AI-powered email generation and analysis",
        setup_url="https://platform.openai.com/api-keys"
    ),
    APIConnection(
        name="LinkedIn Cookie",
        env_var="LINKEDIN_COOKIE",
        required=False,
        purpose="LinkedIn scraping (HUNTER agent)",
        setup_url="Manual extraction from browser"
    ),
    APIConnection(
        name="ProxyCurl API Key",
        env_var="PROXYCURL_API_KEY",
        required=False,
        purpose="LinkedIn data enrichment",
        setup_url="https://nubela.co/proxycurl"
    ),
]


# =============================================================================
# CONNECTION TESTERS
# =============================================================================

async def test_ghl_connection(api_key: str, location_id: str) -> Tuple[bool, str]:
    """Test GoHighLevel API connection."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://services.leadconnectorhq.com/locations/{location_id}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Version": "2021-07-28"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                return True, f"Connected to: {data.get('name', 'Unknown Location')}"
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                return False, f"HTTP {response.status_code}: {response.text[:100]}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"


async def test_supabase_connection(url: str, key: str) -> Tuple[bool, str]:
    """Test Supabase connection."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{url}/rest/v1/",
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}"
                },
                timeout=10.0
            )
            
            if response.status_code in [200, 404]:  # 404 is OK, just no tables
                return True, "Connected to Supabase"
            else:
                return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"


async def test_slack_webhook(webhook_url: str) -> Tuple[bool, str]:
    """Test Slack webhook (without sending)."""
    try:
        # Just verify URL format, don't actually send
        if "hooks.slack.com" in webhook_url:
            return True, "Webhook URL format valid"
        else:
            return False, "Invalid webhook URL format"
    except Exception as e:
        return False, f"Error: {str(e)}"


async def test_clay_connection(api_key: str) -> Tuple[bool, str]:
    """Test Clay API connection."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.clay.com/v1/me",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                return True, "Connected to Clay"
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"


async def test_openai_connection(api_key: str) -> Tuple[bool, str]:
    """Test OpenAI API connection."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                return True, "Connected to OpenAI"
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"


# =============================================================================
# MAIN CHECKER
# =============================================================================

class APIKeyChecker:
    """Check and verify all API connections."""
    
    def __init__(self):
        self.connections = API_CONNECTIONS.copy()
        self.results: Dict[str, Dict[str, Any]] = {}
    
    def check_environment_variables(self) -> Dict[str, Any]:
        """Check which environment variables are set."""
        results = {
            "total": len(self.connections),
            "set": 0,
            "missing_required": [],
            "missing_optional": [],
            "connections": []
        }
        
        for conn in self.connections:
            has_key = conn.has_key()
            
            if has_key:
                results["set"] += 1
                conn.status = ConnectionStatus.NOT_TESTED
            else:
                conn.status = ConnectionStatus.MISSING_KEY
                if conn.required:
                    results["missing_required"].append(conn.name)
                else:
                    results["missing_optional"].append(conn.name)
            
            results["connections"].append({
                "name": conn.name,
                "env_var": conn.env_var,
                "has_key": has_key,
                "required": conn.required,
                "purpose": conn.purpose
            })
        
        return results
    
    async def test_all_connections(self) -> Dict[str, Any]:
        """Test all API connections that have keys."""
        results = {
            "tested": 0,
            "connected": 0,
            "failed": 0,
            "details": []
        }
        
        console.print("\n[bold]Testing API connections...[/bold]\n")
        
        for conn in self.connections:
            if not conn.has_key():
                results["details"].append({
                    "name": conn.name,
                    "status": "skipped",
                    "reason": "No API key set"
                })
                continue
            
            results["tested"] += 1
            success = False
            message = ""
            
            # Test based on connection type
            if conn.env_var == "GHL_PROD_API_KEY":
                api_key = os.getenv("GHL_PROD_API_KEY")
                location_id = os.getenv("GHL_LOCATION_ID", "")
                if location_id:
                    success, message = await test_ghl_connection(api_key, location_id)
                else:
                    success, message = False, "GHL_LOCATION_ID not set"
            
            elif conn.env_var == "SUPABASE_URL":
                url = os.getenv("SUPABASE_URL")
                key = os.getenv("SUPABASE_KEY", "")
                if key:
                    success, message = await test_supabase_connection(url, key)
                else:
                    success, message = False, "SUPABASE_KEY not set"
            
            elif conn.env_var == "SLACK_WEBHOOK_URL":
                webhook = os.getenv("SLACK_WEBHOOK_URL")
                success, message = await test_slack_webhook(webhook)
            
            elif conn.env_var == "CLAY_API_KEY":
                api_key = os.getenv("CLAY_API_KEY")
                success, message = await test_clay_connection(api_key)
            
            elif conn.env_var == "OPENAI_API_KEY":
                api_key = os.getenv("OPENAI_API_KEY")
                success, message = await test_openai_connection(api_key)
            
            else:
                # Can't test, just mark as having key
                success = True
                message = "Key present (not tested)"
            
            if success:
                conn.status = ConnectionStatus.CONNECTED
                results["connected"] += 1
            else:
                conn.status = ConnectionStatus.INVALID_KEY
                conn.error_message = message
                results["failed"] += 1
            
            results["details"].append({
                "name": conn.name,
                "status": "connected" if success else "failed",
                "message": message
            })
            
            status_icon = "[green]OK[/green]" if success else "[red]FAIL[/red]"
            console.print(f"  {status_icon} {conn.name}: {message}")
        
        return results
    
    def generate_setup_instructions(self) -> str:
        """Generate setup instructions for missing keys."""
        missing = [c for c in self.connections if c.status == ConnectionStatus.MISSING_KEY and c.required]
        
        if not missing:
            return "All required API keys are configured!"
        
        instructions = "# Missing API Keys - Setup Instructions\n\n"
        
        for conn in missing:
            instructions += f"## {conn.name}\n\n"
            instructions += f"**Purpose:** {conn.purpose}\n\n"
            instructions += f"**Environment Variable:** `{conn.env_var}`\n\n"
            instructions += f"**Setup URL:** {conn.setup_url}\n\n"
            instructions += "**Steps:**\n"
            
            if "GHL" in conn.env_var:
                instructions += """
1. Log into GoHighLevel at https://app.gohighlevel.com
2. Go to Settings → Integrations → API Keys
3. Create a new API key with full permissions
4. Copy the key and add to your `.env` file:
   ```
   GHL_PROD_API_KEY=your_key_here
   GHL_LOCATION_ID=your_location_id
   ```
"""
            elif "SUPABASE" in conn.env_var:
                instructions += """
1. Log into Supabase at https://supabase.com/dashboard
2. Select your project (or create one)
3. Go to Settings → API
4. Copy the URL and anon/service key:
   ```
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your_anon_key
   ```
"""
            elif "RB2B" in conn.env_var:
                instructions += """
1. Log into RB2B at https://app.rb2b.com
2. Go to Settings → Integrations
3. Generate an API key
4. Add to your `.env` file:
   ```
   RB2B_API_KEY=your_key_here
   ```
"""
            elif "CLAY" in conn.env_var:
                instructions += """
1. Log into Clay at https://app.clay.com
2. Go to Settings → API
3. Generate an API key
4. Add to your `.env` file:
   ```
   CLAY_API_KEY=your_key_here
   ```
"""
            elif "SLACK" in conn.env_var:
                instructions += """
1. Go to https://api.slack.com/apps
2. Create a new app or select existing
3. Go to Incoming Webhooks → Add New Webhook
4. Select the channel for notifications
5. Copy the webhook URL:
   ```
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
   ```
"""
            instructions += "\n---\n\n"
        
        return instructions
    
    def print_report(self, env_results: Dict, connection_results: Optional[Dict] = None):
        """Print comprehensive status report."""
        console.print("\n")
        console.print(Panel("[bold blue]API KEY STATUS REPORT[/bold blue]", expand=False))
        
        # Environment variable status
        env_table = Table(title="Environment Variables", show_header=True)
        env_table.add_column("Integration", style="cyan")
        env_table.add_column("Variable", style="dim")
        env_table.add_column("Status", style="green")
        env_table.add_column("Required", style="yellow")
        
        for conn_info in env_results["connections"]:
            status = "[green]SET[/green]" if conn_info["has_key"] else "[red]MISSING[/red]"
            required = "Yes" if conn_info["required"] else "No"
            env_table.add_row(
                conn_info["name"],
                conn_info["env_var"],
                status,
                required
            )
        
        console.print(env_table)
        
        # Connection test results (if tested)
        if connection_results:
            console.print("\n")
            conn_table = Table(title="Connection Tests", show_header=True)
            conn_table.add_column("Integration", style="cyan")
            conn_table.add_column("Status", style="green")
            conn_table.add_column("Message", style="dim")
            
            for detail in connection_results["details"]:
                status_style = "green" if detail["status"] == "connected" else "red" if detail["status"] == "failed" else "yellow"
                status_icon = "OK" if detail["status"] == "connected" else "FAIL" if detail["status"] == "failed" else "SKIP"
                conn_table.add_row(
                    detail["name"],
                    f"[{status_style}]{status_icon} {detail['status']}[/{status_style}]",
                    detail.get("message", "")
                )
            
            console.print(conn_table)
        
        # Summary
        console.print("\n")
        summary_table = Table(title="Summary", show_header=False)
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Total Integrations", str(env_results["total"]))
        summary_table.add_row("Keys Configured", str(env_results["set"]))
        summary_table.add_row("Missing Required", str(len(env_results["missing_required"])))
        summary_table.add_row("Missing Optional", str(len(env_results["missing_optional"])))
        
        if connection_results:
            summary_table.add_row("Connections Tested", str(connection_results["tested"]))
            summary_table.add_row("Connections OK", str(connection_results["connected"]))
            summary_table.add_row("Connections Failed", str(connection_results["failed"]))
        
        console.print(summary_table)
        
        # Production readiness
        is_ready = len(env_results["missing_required"]) == 0
        if connection_results:
            is_ready = is_ready and connection_results["failed"] == 0
        
        if is_ready:
            console.print("\n[bold green]PRODUCTION READY[/bold green]")
            console.print("All required API keys are configured and connections are working.")
        else:
            console.print("\n[bold red]NOT PRODUCTION READY[/bold red]")
            if env_results["missing_required"]:
                console.print(f"\nMissing required keys: {', '.join(env_results['missing_required'])}")
            if connection_results and connection_results["failed"] > 0:
                failed = [d["name"] for d in connection_results["details"] if d["status"] == "failed"]
                console.print(f"Failed connections: {', '.join(failed)}")
    
    def save_report(self, output_path: Path):
        """Save detailed report to file."""
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "connections": [
                {
                    "name": c.name,
                    "env_var": c.env_var,
                    "required": c.required,
                    "has_key": c.has_key(),
                    "status": c.status.value,
                    "error": c.error_message
                }
                for c in self.connections
            ]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        
        console.print(f"\n[dim]Report saved to: {output_path}[/dim]")


# =============================================================================
# CLI
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Check and verify API connections")
    parser.add_argument("--test-connections", action="store_true", help="Test actual API connections")
    parser.add_argument("--show-instructions", action="store_true", help="Show setup instructions for missing keys")
    parser.add_argument("--output", type=str, help="Save report to file")
    
    args = parser.parse_args()
    
    checker = APIKeyChecker()
    
    # Check environment variables
    console.print("\n[bold]Checking environment variables...[/bold]")
    env_results = checker.check_environment_variables()
    
    # Test connections if requested
    connection_results = None
    if args.test_connections:
        connection_results = await checker.test_all_connections()
    
    # Print report
    checker.print_report(env_results, connection_results)
    
    # Show setup instructions if needed
    if args.show_instructions or env_results["missing_required"]:
        instructions = checker.generate_setup_instructions()
        if env_results["missing_required"]:
            console.print("\n")
            console.print(Panel("[bold yellow]SETUP INSTRUCTIONS[/bold yellow]", expand=False))
            console.print(Markdown(instructions))
    
    # Save report if requested
    if args.output:
        checker.save_report(Path(args.output))
    
    # Return exit code based on readiness
    if env_results["missing_required"]:
        console.print("\n[yellow]Next step:[/yellow] Configure missing API keys, then run Priority #3")
        return 1
    else:
        console.print("\n[green]Ready for Priority #3 (AI vs Human comparison)[/green]")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
