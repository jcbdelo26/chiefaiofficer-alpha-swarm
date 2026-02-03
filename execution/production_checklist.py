#!/usr/bin/env python3
"""
Production Readiness Checklist
================================
Tracks production readiness using Agent Manager.
Validates all systems before deployment.

Usage:
    python execution/production_checklist.py
    python execution/production_checklist.py --verbose
    python execution/production_checklist.py --export json
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
import argparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.unified_agent_registry import UnifiedAgentRegistry, AgentSwarm
from dotenv import load_dotenv

load_dotenv()


@dataclass
class CheckResult:
    """Result of a single check."""
    name: str
    passed: bool
    message: str
    critical: bool = False
    details: Dict[str, Any] = None


class ProductionChecklist:
    """
    Production readiness validation.
    
    Categories:
    1. Agent Manager - Core orchestration
    2. Infrastructure - Databases, MCP servers
    3. Workflows - Unified workflows
    4. Compliance - Rate limits, GDPR
    5. Security - API keys, credentials
    6. Monitoring - Logging, health checks
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.registry = UnifiedAgentRegistry()
        self.results: List[CheckResult] = []
        
    def run_all_checks(self) -> Dict[str, Any]:
        """Run all production readiness checks."""
        print("🚀 Running Production Readiness Checks...\n")
        
        # Category 1: Agent Manager
        self._check_agent_manager()
        
        # Category 2: Infrastructure
        self._check_infrastructure()
        
        # Category 3: Workflows
        self._check_workflows()
        
        # Category 4: Compliance
        self._check_compliance()
        
        # Category 5: Security
        self._check_security()
        
        # Category 6: Monitoring
        self._check_monitoring()
        
        return self._generate_report()
    
    def _check_agent_manager(self):
        """Check Agent Manager implementation."""
        print("📋 Category 1: Agent Manager")
        print("-" * 50)
        
        # Check 1.1: Core module exists
        agent_manager_path = Path(__file__).parent.parent / "core" / "agent_manager.py"
        self._add_check(
            "Agent Manager Core",
            agent_manager_path.exists(),
            f"Found at {agent_manager_path}" if agent_manager_path.exists() else "NOT FOUND",
            critical=True
        )
        
        # Check 1.2: Unified Agent Registry works
        try:
            agents = self.registry.list_agents()
            self._add_check(
                "Unified Agent Registry",
                len(agents) >= 11,
                f"Registered {len(agents)} agents (expected 11+)",
                critical=True,
                details={"agent_count": len(agents)}
            )
        except Exception as e:
            self._add_check(
                "Unified Agent Registry",
                False,
                f"Error: {str(e)}",
                critical=True
            )
        
        # Check 1.3: MCP server exists
        mcp_path = Path(__file__).parent.parent / "mcp-servers" / "agent-manager-mcp"
        self._add_check(
            "Agent Manager MCP Server",
            mcp_path.exists(),
            f"Found at {mcp_path}" if mcp_path.exists() else "NOT CREATED (use Prompt 6)",
            critical=False
        )
        
        print()
    
    def _check_infrastructure(self):
        """Check infrastructure readiness."""
        print("🏗️  Category 2: Infrastructure")
        print("-" * 50)
        
        # Check 2.1: Supabase configuration
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        supabase_configured = bool(supabase_url and supabase_key)
        
        self._add_check(
            "Supabase Configuration",
            supabase_configured,
            f"URL: {supabase_url[:30]}..." if supabase_configured else "NOT CONFIGURED",
            critical=True
        )
        
        # Check 2.2: .hive-mind directory
        hive_mind_path = Path(__file__).parent.parent / ".hive-mind"
        required_dirs = ["campaigns", "enriched", "scraped", "pipeline_runs", "workflows"]
        missing_dirs = [d for d in required_dirs if not (hive_mind_path / d).exists()]
        
        self._add_check(
            ".hive-mind Directory Structure",
            len(missing_dirs) == 0,
            f"All directories present" if len(missing_dirs) == 0 else f"Missing: {', '.join(missing_dirs)}",
            critical=True,
            details={"missing": missing_dirs}
        )
        
        # Check 2.3: MCP servers directory
        mcp_servers_path = Path(__file__).parent.parent / "mcp-servers"
        expected_servers = ["ghl-mcp", "instantly-mcp", "supabase-mcp"]
        existing_servers = [d.name for d in mcp_servers_path.iterdir() if d.is_dir() and not d.name.startswith("_")]
        
        self._add_check(
            "MCP Servers Present",
            len(existing_servers) >= 3,
            f"Found: {', '.join(existing_servers)}",
            critical=False,
            details={"servers": existing_servers}
        )
        
        print()
    
    def _check_workflows(self):
        """Check workflow definitions."""
        print("🔄 Category 3: Workflows")
        print("-" * 50)
        
        # Check 3.1: Workflow directory
        workflows_path = Path(__file__).parent.parent / ".hive-mind" / "workflows"
        self._add_check(
            "Workflows Directory",
            workflows_path.exists(),
            f"Found at {workflows_path}" if workflows_path.exists() else "NOT FOUND",
            critical=False
        )
        
        # Check 3.2: Key execution scripts
        execution_path = Path(__file__).parent
        key_scripts = {
            "run_pipeline.py": "Main pipeline orchestrator",
            "unified_workflows.py": "Unified workflow definitions (CREATE with Prompt 8)",
            "rpi_research.py": "RPI Research phase",
            "rpi_plan.py": "RPI Plan phase",
            "rpi_implement.py": "RPI Implement phase"
        }
        
        for script, description in key_scripts.items():
            script_path = execution_path / script
            self._add_check(
                f"Script: {script}",
                script_path.exists(),
                description if script_path.exists() else "NOT FOUND",
                critical=(script == "run_pipeline.py")
            )
        
        print()
    
    def _check_compliance(self):
        """Check compliance configuration."""
        print("⚖️  Category 4: Compliance")
        print("-" * 50)
        
        # Check 4.1: Rate limiting configured
        linkedin_limit = os.getenv("LINKEDIN_RATE_LIMIT")
        clay_limit = os.getenv("CLAY_RATE_LIMIT")
        
        self._add_check(
            "Rate Limiting Configured",
            bool(linkedin_limit and clay_limit),
            f"LinkedIn: {linkedin_limit}/min, Clay: {clay_limit}/min" if linkedin_limit else "NOT CONFIGURED",
            critical=True
        )
        
        # Check 4.2: GDPR utilities
        gdpr_delete = Path(__file__).parent / "gdpr_delete.py"
        gdpr_export = Path(__file__).parent / "gdpr_export.py"
        
        self._add_check(
            "GDPR Utilities",
            gdpr_delete.exists() and gdpr_export.exists(),
            "Delete and Export scripts present" if (gdpr_delete.exists() and gdpr_export.exists()) else "MISSING",
            critical=True
        )
        
        # Check 4.3: Audit logging
        event_log_path = Path(__file__).parent.parent / ".hive-mind" / "events.jsonl"
        self._add_check(
            "Audit Log Active",
            event_log_path.exists(),
            f"Logging to {event_log_path}" if event_log_path.exists() else "NOT INITIALIZED",
            critical=False
        )
        
        print()
    
    def _check_security(self):
        """Check security configuration."""
        print("🔒 Category 5: Security")
        print("-" * 50)
        
        # Check 5.1: Required API keys
        required_keys = {
            "GHL_API_KEY": "GoHighLevel",
            "CLAY_API_KEY": "Clay Enrichment",
            "INSTANTLY_API_KEY": "Instantly Outreach",
            "ANTHROPIC_API_KEY": "Anthropic Claude",
            "SUPABASE_KEY": "Supabase"
        }
        
        missing_keys = []
        for key, service in required_keys.items():
            value = os.getenv(key)
            configured = bool(value and value != f"your_{key.lower()}")
            
            if not configured:
                missing_keys.append(service)
            
            if self.verbose:
                self._add_check(
                    f"API Key: {service}",
                    configured,
                    "Configured ✓" if configured else "MISSING",
                    critical=True
                )
        
        if not self.verbose:
            self._add_check(
                "API Keys Configured",
                len(missing_keys) == 0,
                f"All {len(required_keys)} keys configured" if len(missing_keys) == 0 else f"Missing: {', '.join(missing_keys)}",
                critical=True,
                details={"missing": missing_keys}
            )
        
        # Check 5.2: .env file not in git
        gitignore_path = Path(__file__).parent.parent / ".gitignore"
        gitignore_contains_env = False
        if gitignore_path.exists():
            with open(gitignore_path, 'r') as f:
                gitignore_contains_env = '.env' in f.read()
        
        self._add_check(
            ".env in .gitignore",
            gitignore_contains_env,
            "Protected ✓" if gitignore_contains_env else "WARNING: .env may be exposed",
            critical=True
        )
        
        print()
    
    def _check_monitoring(self):
        """Check monitoring setup."""
        print("📊 Category 6: Monitoring")
        print("-" * 50)
        
        # Check 6.1: Health check script
        health_check_path = Path(__file__).parent / "health_check.py"
        self._add_check(
            "Health Check Script",
            health_check_path.exists(),
            "Present ✓" if health_check_path.exists() else "NOT FOUND",
            critical=False
        )
        
        # Check 6.2: Daily report generator
        report_gen_path = Path(__file__).parent / "generate_daily_report.py"
        self._add_check(
            "Daily Report Generator",
            report_gen_path.exists(),
            "Present ✓" if report_gen_path.exists() else "NOT FOUND",
            critical=False
        )
        
        # Check 6.3: Logs directory
        logs_path = Path(__file__).parent.parent / ".hive-mind" / "logs"
        self._add_check(
            "Logs Directory",
            logs_path.exists(),
            f"Present at {logs_path}" if logs_path.exists() else "NOT CREATED",
            critical=False
        )
        
        # Check 6.4: Dashboard
        dashboard_path = Path(__file__).parent.parent / "dashboard" / "agent_manager_dashboard.py"
        self._add_check(
            "Agent Manager Dashboard",
            dashboard_path.exists(),
            "Present ✓ (CREATE with Prompt 9)" if dashboard_path.exists() else "NOT CREATED (use Prompt 9)",
            critical=False
        )
        
        print()
    
    def _add_check(self, name: str, passed: bool, message: str, critical: bool = False, details: Dict = None):
        """Add a check result."""
        result = CheckResult(
            name=name,
            passed=passed,
            message=message,
            critical=critical,
            details=details or {}
        )
        self.results.append(result)
        
        # Print result
        icon = "✅" if passed else ("❌" if critical else "⚠️")
        print(f"  {icon} {name}: {message}")
    
    def _generate_report(self) -> Dict[str, Any]:
        """Generate final report."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        critical_failed = sum(1 for r in self.results if not r.passed and r.critical)
        
        score = int((passed / total) * 100) if total > 0 else 0
        
        print("\n" + "=" * 50)
        print("📊 PRODUCTION READINESS REPORT")
        print("=" * 50)
        print(f"Total Checks: {total}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} ❌")
        print(f"Critical Failures: {critical_failed} 🚨")
        print(f"\nProduction Readiness Score: {score}%")
        print("=" * 50)
        
        # Production readiness determination
        if critical_failed > 0:
            status = "🚨 NOT READY - Critical issues must be resolved"
            print(f"\n{status}\n")
            print("Critical Issues:")
            for result in self.results:
                if not result.passed and result.critical:
                    print(f"  ❌ {result.name}: {result.message}")
        elif score >= 90:
            status = "✅ PRODUCTION READY"
            print(f"\n{status}\n")
        elif score >= 70:
            status = "⚠️  READY FOR STAGING - Fix non-critical issues before production"
            print(f"\n{status}\n")
        else:
            status = "❌ NOT READY - More work needed"
            print(f"\n{status}\n")
        
        # Next steps
        print("\n📋 Next Steps:")
        if critical_failed > 0:
            print("1. Fix all critical issues listed above")
            print("2. Re-run this checklist: python execution/production_checklist.py")
        elif score < 100:
            print("1. Address remaining non-critical issues")
            print("2. Use Ampcode prompts from AMPCODE_PROMPTS_AGENT_MANAGER.md")
            print("3. Re-validate before production deployment")
        else:
            print("1. Run final validation: python execution/validate_production_readiness.py")
            print("2. Deploy to staging environment")
            print("3. Run integration tests")
        
        return {
            "timestamp": datetime.now().isoformat(),
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "critical_failures": critical_failed,
            "score": score,
            "status": status,
            "results": [asdict(r) for r in self.results]
        }


def main():
    """Run production checklist."""
    parser = argparse.ArgumentParser(description="Production Readiness Checklist")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--export", "-e", choices=["json", "html"], help="Export format")
    args = parser.parse_args()
    
    checklist = ProductionChecklist(verbose=args.verbose)
    report = checklist.run_all_checks()
    
    # Export if requested
    if args.export == "json":
        output_path = Path(__file__).parent.parent / ".hive-mind" / "reports" / "production_readiness.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📄 Report exported to: {output_path}")
    
    # Exit code based on readiness
    sys.exit(0 if report["critical_failures"] == 0 else 1)


if __name__ == "__main__":
    main()
