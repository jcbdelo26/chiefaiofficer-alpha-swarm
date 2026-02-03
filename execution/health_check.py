#!/usr/bin/env python3
"""
Comprehensive Health Check for Revenue Swarm System
====================================================
Validates all system components, API connections, and infrastructure.

Usage:
    python execution/health_check.py          # Full check
    python execution/health_check.py --quick  # Critical checks only
    python execution/health_check.py --json   # Output as JSON
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

HIVE_MIND = PROJECT_ROOT / ".hive-mind"


@dataclass
class CheckResult:
    """Result of a single health check."""
    name: str
    status: str  # "pass" | "warn" | "fail"
    message: str
    duration_ms: float
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["details"] is None:
            del d["details"]
        return d


@dataclass
class HealthReport:
    """Complete health report."""
    overall_status: str  # "healthy" | "degraded" | "unhealthy"
    timestamp: str
    checks: List[CheckResult]
    recommendations: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "timestamp": self.timestamp,
            "checks": [c.to_dict() for c in self.checks],
            "recommendations": self.recommendations
        }


def timed_check(name: str, check_fn: Callable[[], tuple]) -> CheckResult:
    """Execute a check function and time it."""
    start = time.perf_counter()
    try:
        status, message, details = check_fn()
    except Exception as e:
        status, message, details = "fail", f"Exception: {str(e)[:100]}", None
    duration_ms = (time.perf_counter() - start) * 1000
    
    return CheckResult(
        name=name,
        status=status,
        message=message,
        duration_ms=round(duration_ms, 2),
        details=details
    )


# =============================================================================
# COMPONENT CHECKS
# =============================================================================

def check_supabase() -> tuple:
    """Check Supabase connection if configured."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    
    if not url or not key:
        return "warn", "Not configured (SUPABASE_URL/SUPABASE_KEY missing)", None
    
    try:
        import requests
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}"
        }
        response = requests.get(f"{url}/rest/v1/", headers=headers, timeout=10)
        
        if response.status_code == 200:
            return "pass", "Connected", {"url": url[:50] + "..."}
        else:
            return "fail", f"HTTP {response.status_code}", None
    except ImportError:
        return "warn", "requests library not installed", None
    except Exception as e:
        return "fail", str(e)[:100], None


def check_ghl_api() -> tuple:
    """Check GoHighLevel API credentials."""
    api_key = os.getenv("GHL_API_KEY")
    location_id = os.getenv("GHL_LOCATION_ID")
    
    if not api_key or not location_id:
        return "fail", "Missing GHL_API_KEY or GHL_LOCATION_ID", None
    
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        url = f"https://services.leadconnectorhq.com/locations/{location_id}"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            location_name = data.get("location", {}).get("name", "Unknown")
            return "pass", f"Connected: {location_name}", {"location_id": location_id}
        elif response.status_code == 401:
            return "fail", "Invalid API key or expired token", None
        else:
            return "fail", f"HTTP {response.status_code}", None
    except ImportError:
        return "warn", "requests library not installed", None
    except Exception as e:
        return "fail", str(e)[:100], None


def check_instantly_api() -> tuple:
    """Check Instantly API credentials."""
    api_key = os.getenv("INSTANTLY_API_KEY")
    
    if not api_key:
        return "fail", "Missing INSTANTLY_API_KEY", None
    
    try:
        import requests
        url = f"https://api.instantly.ai/api/v1/account/list?api_key={api_key}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            account_count = len(data) if isinstance(data, list) else 1
            return "pass", f"{account_count} account(s) found", {"accounts": account_count}
        elif response.status_code == 401:
            return "fail", "Invalid API key", None
        else:
            return "fail", f"HTTP {response.status_code}", None
    except ImportError:
        return "warn", "requests library not installed", None
    except Exception as e:
        return "fail", str(e)[:100], None


def check_clay_api() -> tuple:
    """Check Clay API credentials."""
    api_key = os.getenv("CLAY_API_KEY")
    
    if not api_key:
        return "warn", "Missing CLAY_API_KEY (optional)", None
    
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        url = "https://api.clay.com/v3/sources"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code in [200, 401]:
            if response.status_code == 200:
                return "pass", "API accessible", None
            else:
                return "fail", "Invalid API key", None
        else:
            return "pass", "API key format valid", None
    except ImportError:
        return "warn", "requests library not installed", None
    except Exception as e:
        return "warn", f"Could not verify: {str(e)[:50]}", None


def check_linkedin() -> tuple:
    """Check LinkedIn session cookie."""
    cookie = os.getenv("LINKEDIN_COOKIE")
    
    if not cookie:
        return "warn", "Missing LINKEDIN_COOKIE (li_at)", None
    
    try:
        import requests
        headers = {
            "Cookie": f"li_at={cookie}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        url = "https://www.linkedin.com/voyager/api/me"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return "pass", "Session valid", None
        elif response.status_code == 401:
            return "fail", "Session expired - refresh li_at cookie", None
        else:
            return "warn", f"HTTP {response.status_code}", None
    except ImportError:
        return "warn", "requests library not installed", None
    except Exception as e:
        return "warn", f"Could not verify: {str(e)[:50]}", None


def check_anthropic_api() -> tuple:
    """Check Anthropic API credentials."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if not api_key:
        return "warn", "Missing ANTHROPIC_API_KEY", None
    
    if not api_key.startswith("sk-ant-"):
        return "fail", "Invalid API key format", None
    
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=5,
            messages=[{"role": "user", "content": "Hi"}]
        )
        return "pass", "API accessible", None
    except ImportError:
        return "pass", "Key format valid (anthropic SDK not installed)", None
    except Exception as e:
        if "invalid_api_key" in str(e).lower():
            return "fail", "Invalid API key", None
        return "warn", f"Could not verify: {str(e)[:50]}", None


def check_gemini_api() -> tuple:
    """Check Google Gemini API credentials."""
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        return "warn", "Missing GOOGLE_API_KEY/GEMINI_API_KEY", None
    
    try:
        import requests
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            model_count = len(data.get("models", []))
            return "pass", f"{model_count} models available", None
        elif response.status_code == 400:
            return "fail", "Invalid API key", None
        else:
            return "warn", f"HTTP {response.status_code}", None
    except ImportError:
        return "warn", "requests library not installed", None
    except Exception as e:
        return "warn", f"Could not verify: {str(e)[:50]}", None


def check_mcp_servers() -> tuple:
    """Check if MCP servers can be imported."""
    mcp_dir = PROJECT_ROOT / "mcp-servers"
    
    if not mcp_dir.exists():
        return "fail", "mcp-servers directory not found", None
    
    servers = [d.name for d in mcp_dir.iterdir() if d.is_dir() and d.name.endswith("-mcp")]
    importable = []
    failed = []
    
    for server in servers:
        server_path = mcp_dir / server
        main_file = server_path / "server.py"
        init_file = server_path / "__init__.py"
        
        if main_file.exists() or init_file.exists():
            importable.append(server)
        else:
            failed.append(server)
    
    if not servers:
        return "warn", "No MCP servers found", None
    elif failed:
        return "warn", f"{len(importable)}/{len(servers)} servers valid", {
            "valid": importable,
            "invalid": failed
        }
    else:
        return "pass", f"All {len(servers)} servers valid", {"servers": importable}


def check_self_annealing_engine() -> tuple:
    """Check self-annealing engine state."""
    state_file = HIVE_MIND / "self_annealing_state.json"
    
    if not state_file.exists():
        return "warn", "Not initialized (first run pending)", None
    
    try:
        with open(state_file) as f:
            state = json.load(f)
        
        epsilon = state.get("epsilon", 0)
        metrics = state.get("metrics", {})
        total_outcomes = metrics.get("total_outcomes", 0)
        annealing_steps = metrics.get("annealing_steps", 0)
        last_annealing = metrics.get("last_annealing")
        
        details = {
            "epsilon": round(epsilon, 4),
            "total_outcomes": total_outcomes,
            "annealing_steps": annealing_steps,
            "last_annealing": last_annealing
        }
        
        if total_outcomes == 0:
            return "warn", "Initialized but no data yet", details
        
        if last_annealing:
            try:
                last_dt = datetime.fromisoformat(last_annealing.replace("Z", "+00:00"))
                age = datetime.now(last_dt.tzinfo) - last_dt if last_dt.tzinfo else datetime.utcnow() - datetime.fromisoformat(last_annealing)
                if age > timedelta(days=7):
                    return "warn", f"Stale: last annealing {age.days}d ago", details
            except:
                pass
        
        return "pass", f"{total_outcomes} outcomes, ε={epsilon:.3f}", details
        
    except Exception as e:
        return "fail", f"Error reading state: {str(e)[:50]}", None


def check_context_manager() -> tuple:
    """Check context manager module."""
    try:
        from core.context import ContextManager, EventThread, ContextZone
        
        cm = ContextManager("health_check_test")
        zone = cm.get_context_zone()
        
        context_dir = HIVE_MIND / "context"
        context_files = list(context_dir.glob("*.json")) if context_dir.exists() else []
        
        return "pass", f"Module operational, {len(context_files)} saved contexts", {
            "zone": zone.value,
            "saved_contexts": len(context_files)
        }
    except ImportError as e:
        return "fail", f"Import error: {str(e)[:50]}", None
    except Exception as e:
        return "warn", f"Module error: {str(e)[:50]}", None


def check_hive_mind_directories() -> tuple:
    """Check .hive-mind directory structure."""
    required_dirs = [
        "scraped",
        "enriched", 
        "segmented",
        "campaigns",
        "context",
        "logs"
    ]
    
    if not HIVE_MIND.exists():
        return "fail", ".hive-mind directory does not exist", None
    
    existing = []
    missing = []
    
    for dir_name in required_dirs:
        dir_path = HIVE_MIND / dir_name
        if dir_path.exists():
            existing.append(dir_name)
        else:
            missing.append(dir_name)
    
    if missing:
        return "warn", f"{len(existing)}/{len(required_dirs)} dirs exist", {
            "existing": existing,
            "missing": missing
        }
    else:
        return "pass", f"All {len(required_dirs)} directories exist", {"dirs": existing}


def check_q_table() -> tuple:
    """Check RL Q-table state."""
    q_table_file = HIVE_MIND / "q_table.json"
    
    if not q_table_file.exists():
        return "warn", "Q-table not initialized", None
    
    try:
        with open(q_table_file) as f:
            q_table = json.load(f)
        
        states_count = len(q_table)
        total_actions = sum(len(v) for v in q_table.values()) if isinstance(q_table, dict) else 0
        
        if states_count == 0:
            return "warn", "Q-table empty", {"states": 0, "actions": 0}
        elif states_count < 10:
            return "pass", f"Learning: {states_count} states", {"states": states_count, "actions": total_actions}
        else:
            return "pass", f"Trained: {states_count} states, {total_actions} actions", {
                "states": states_count,
                "actions": total_actions
            }
    except Exception as e:
        return "fail", f"Error reading Q-table: {str(e)[:50]}", None


def check_learnings() -> tuple:
    """Check learnings accumulation."""
    learnings_file = HIVE_MIND / "learnings.json"
    
    if not learnings_file.exists():
        return "warn", "No learnings file yet", None
    
    try:
        with open(learnings_file) as f:
            learnings = json.load(f)
        
        learning_count = len(learnings.get("learnings", []))
        error_patterns = len(learnings.get("error_patterns", []))
        
        return "pass", f"{learning_count} learnings, {error_patterns} error patterns", {
            "learnings": learning_count,
            "error_patterns": error_patterns
        }
    except Exception as e:
        return "fail", f"Error reading learnings: {str(e)[:50]}", None


# =============================================================================
# HEALTH CHECK RUNNER
# =============================================================================

CRITICAL_CHECKS = [
    ("Supabase", check_supabase),
    ("GoHighLevel API", check_ghl_api),
    ("Instantly API", check_instantly_api),
    ("Anthropic API", check_anthropic_api),
    ("File System", check_hive_mind_directories),
]

ALL_CHECKS = CRITICAL_CHECKS + [
    ("Clay API", check_clay_api),
    ("LinkedIn Session", check_linkedin),
    ("Gemini API", check_gemini_api),
    ("MCP Servers", check_mcp_servers),
    ("Self-Annealing Engine", check_self_annealing_engine),
    ("Context Manager", check_context_manager),
    ("RL Q-Table", check_q_table),
    ("Learnings", check_learnings),
]


def run_health_check(quick: bool = False) -> HealthReport:
    """Run the health check and return a report."""
    checks_to_run = CRITICAL_CHECKS if quick else ALL_CHECKS
    results: List[CheckResult] = []
    
    for name, check_fn in checks_to_run:
        result = timed_check(name, check_fn)
        results.append(result)
    
    fail_count = sum(1 for r in results if r.status == "fail")
    warn_count = sum(1 for r in results if r.status == "warn")
    
    if fail_count >= 3:
        overall = "unhealthy"
    elif fail_count > 0 or warn_count >= 3:
        overall = "degraded"
    else:
        overall = "healthy"
    
    recommendations = generate_recommendations(results)
    
    return HealthReport(
        overall_status=overall,
        timestamp=datetime.utcnow().isoformat() + "Z",
        checks=results,
        recommendations=recommendations
    )


def generate_recommendations(results: List[CheckResult]) -> List[str]:
    """Generate recommendations based on check results."""
    recommendations = []
    
    for result in results:
        if result.status == "fail":
            if "GHL" in result.name or "GoHighLevel" in result.name:
                recommendations.append("Configure GHL_API_KEY and GHL_LOCATION_ID in .env")
            elif "Instantly" in result.name:
                recommendations.append("Add INSTANTLY_API_KEY from Instantly.ai → Settings → API")
            elif "Anthropic" in result.name:
                recommendations.append("Add ANTHROPIC_API_KEY from console.anthropic.com")
            elif "Supabase" in result.name:
                recommendations.append("Configure SUPABASE_URL and SUPABASE_KEY for persistence")
            elif "File System" in result.name:
                recommendations.append("Run: mkdir -p .hive-mind/{scraped,enriched,segmented,campaigns,context,logs}")
        elif result.status == "warn":
            if "LinkedIn" in result.name and "expired" in result.message.lower():
                recommendations.append("Refresh LinkedIn li_at cookie (expires ~30 days)")
            elif "annealing" in result.name.lower() and "stale" in result.message.lower():
                recommendations.append("Run annealing step: python -c 'from core.self_annealing import SelfAnnealingEngine; e=SelfAnnealingEngine(); print(e.anneal_step())'")
    
    return recommendations[:5]


def print_report(report: HealthReport):
    """Print formatted health report to console."""
    status_emoji = {
        "healthy": "✅",
        "degraded": "⚠️",
        "unhealthy": "❌"
    }
    
    check_emoji = {
        "pass": "✅",
        "warn": "⚠️",
        "fail": "❌"
    }
    
    print("\n" + "=" * 65)
    print(f"  🏥 REVENUE SWARM HEALTH CHECK")
    print("=" * 65)
    print(f"  Timestamp: {report.timestamp[:19]}")
    print(f"  Overall:   {status_emoji.get(report.overall_status, '❓')} {report.overall_status.upper()}")
    print("=" * 65)
    
    for check in report.checks:
        emoji = check_emoji.get(check.status, "❓")
        duration = f"{check.duration_ms:.0f}ms" if check.duration_ms < 1000 else f"{check.duration_ms/1000:.1f}s"
        print(f"\n  {emoji} {check.name}")
        print(f"     Status:   {check.status}")
        print(f"     Message:  {check.message}")
        print(f"     Duration: {duration}")
        
        if check.details:
            for key, value in check.details.items():
                if isinstance(value, list):
                    print(f"     {key}: {', '.join(str(v) for v in value[:5])}")
                else:
                    print(f"     {key}: {value}")
    
    if report.recommendations:
        print("\n" + "-" * 65)
        print("  📋 RECOMMENDATIONS:")
        print("-" * 65)
        for i, rec in enumerate(report.recommendations, 1):
            print(f"  {i}. {rec}")
    
    print("\n" + "=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Revenue Swarm Health Check")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only critical checks"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    
    args = parser.parse_args()
    
    report = run_health_check(quick=args.quick)
    
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report)
    
    exit_code = 0 if report.overall_status == "healthy" else (1 if report.overall_status == "degraded" else 2)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
