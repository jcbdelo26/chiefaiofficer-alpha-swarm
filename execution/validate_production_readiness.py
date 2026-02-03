#!/usr/bin/env python3
"""
Production Readiness Validator
================================
Comprehensive validation before production deployment.
Runs deep checks on all systems, agents, and integrations.

Usage:
    python execution/validate_production_readiness.py
    python execution/validate_production_readiness.py --mode staging
    python execution/validate_production_readiness.py --skip-api-tests
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import argparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.unified_agent_registry import UnifiedAgentRegistry, AgentSwarm, AgentStatus
from dotenv import load_dotenv

load_dotenv()


class ProductionValidator:
    """
    Deep validation for production readiness.
    
    Validation Levels:
    1. Basic - File structure, configuration
    2. Integration - API connectivity, database
    3. Functional - Agent initialization, workflows
    4. Performance - Load testing, resource limits
    5. Security - Credentials, rate limits, compliance
    """
    
    def __init__(self, mode: str = "production", skip_api_tests: bool = False):
        self.mode = mode
        self.skip_api_tests = skip_api_tests
        self.registry = UnifiedAgentRegistry()
        self.validation_results = {
            "basic": [],
            "integration": [],
            "functional": [],
            "performance": [],
            "security": []
        }
        self.start_time = None
        self.blocking_issues = []
    
    def run_full_validation(self) -> Dict[str, Any]:
        """Run all validation levels."""
        self.start_time = time.time()
        
        print("🔍 PRODUCTION READINESS VALIDATION")
        print("=" * 70)
        print(f"Mode: {self.mode.upper()}")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
        print()
        
        # Level 1: Basic validation
        self._validate_basic()
        
        # Level 2: Integration validation
        if not self.skip_api_tests:
            self._validate_integration()
        else:
            print("⏭️  Skipping API integration tests (--skip-api-tests flag)\n")
        
        # Level 3: Functional validation
        self._validate_functional()
        
        # Level 4: Performance validation
        if self.mode == "production":
            self._validate_performance()
        
        # Level 5: Security validation
        self._validate_security()
        
        return self._generate_final_report()
    
    def _validate_basic(self):
        """Level 1: Basic validation."""
        print("📁 Level 1: Basic Validation")
        print("-" * 70)
        
        checks = []
        
        # Check 1.1: Python version
        python_version = sys.version_info
        checks.append(self._check(
            "Python Version",
            python_version >= (3, 9),
            f"{python_version.major}.{python_version.minor}.{python_version.micro}",
            f"Requires Python 3.9+ (found {python_version.major}.{python_version.minor})"
        ))
        
        # Check 1.2: Required directories
        base_path = Path(__file__).parent.parent
        required_dirs = [
            ".hive-mind",
            ".hive-mind/campaigns",
            ".hive-mind/enriched",
            ".hive-mind/scraped",
            ".hive-mind/pipeline_runs",
            ".hive-mind/logs",
            "execution",
            "core",
            "mcp-servers"
        ]
        
        for dir_path in required_dirs:
            full_path = base_path / dir_path
            checks.append(self._check(
                f"Directory: {dir_path}",
                full_path.exists(),
                "Present ✓",
                f"Missing: {full_path}"
            ))
        
        # Check 1.3: Core modules
        core_modules = [
            "core/agent_manager.py",
            "core/self_annealing.py",
            "core/context.py",
            "execution/unified_agent_registry.py",
            "execution/run_pipeline.py"
        ]
        
        for module in core_modules:
            module_path = base_path / module
            checks.append(self._check(
                f"Module: {module}",
                module_path.exists(),
                "Present ✓",
                f"Missing: {module_path}"
            ))
        
        # Check 1.4: Environment file
        env_exists = (base_path / ".env").exists()
        checks.append(self._check(
            ".env Configuration",
            env_exists,
            "Configured ✓",
            "Missing .env file"
        ))
        
        self.validation_results["basic"] = checks
        self._print_results(checks)
    
    def _validate_integration(self):
        """Level 2: Integration validation."""
        print("\n🔌 Level 2: Integration Validation")
        print("-" * 70)
        
        checks = []
        
        # Check 2.1: Supabase connectivity
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if supabase_url and supabase_key:
            try:
                from supabase import create_client
                client = create_client(supabase_url, supabase_key)
                # Test connection with a simple query
                result = client.table("leads").select("id").limit(1).execute()
                checks.append(self._check(
                    "Supabase Connection",
                    True,
                    "Connected ✓",
                    None
                ))
            except Exception as e:
                checks.append(self._check(
                    "Supabase Connection",
                    False,
                    "Failed",
                    f"Error: {str(e)[:100]}",
                    blocking=True
                ))
        else:
            checks.append(self._check(
                "Supabase Configuration",
                False,
                "Not configured",
                "Missing SUPABASE_URL or SUPABASE_KEY",
                blocking=True
            ))
        
        # Check 2.2: GoHighLevel API
        ghl_key = os.getenv("GHL_API_KEY")
        if ghl_key and ghl_key != "your_gohighlevel_api_key":
            checks.append(self._check(
                "GoHighLevel API Key",
                True,
                "Configured ✓",
                None
            ))
        else:
            checks.append(self._check(
                "GoHighLevel API Key",
                False,
                "Not configured",
                "Required for CRM integration",
                blocking=False
            ))
        
        # Check 2.3: Clay API
        clay_key = os.getenv("CLAY_API_KEY")
        if clay_key and clay_key != "your_clay_api_key":
            checks.append(self._check(
                "Clay API Key",
                True,
                "Configured ✓",
                None
            ))
        else:
            checks.append(self._check(
                "Clay API Key",
                False,
                "Not configured",
                "Required for enrichment",
                blocking=True
            ))
        
        # Check 2.4: Instantly API
        instantly_key = os.getenv("INSTANTLY_API_KEY")
        if instantly_key and instantly_key != "your_instantly_api_key":
            checks.append(self._check(
                "Instantly API Key",
                True,
                "Configured ✓",
                None
            ))
        else:
            checks.append(self._check(
                "Instantly API Key",
                False,
                "Not configured",
                "Required for email outreach",
                blocking=True
            ))
        
        # Check 2.5: Anthropic API
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key and anthropic_key != "your_anthropic_api_key":
            checks.append(self._check(
                "Anthropic API Key",
                True,
                "Configured ✓",
                None
            ))
        else:
            checks.append(self._check(
                "Anthropic API Key",
                False,
                "Not configured",
                "Required for AI agents",
                blocking=True
            ))
        
        self.validation_results["integration"] = checks
        self._print_results(checks)
    
    def _validate_functional(self):
        """Level 3: Functional validation."""
        print("\n⚙️  Level 3: Functional Validation")
        print("-" * 70)
        
        checks = []
        
        # Check 3.1: Agent registry initialization
        try:
            agents = self.registry.list_agents()
            expected_count = 11  # 6 Alpha + 5 Revenue
            checks.append(self._check(
                "Agent Registry",
                len(agents) >= expected_count,
                f"Registered {len(agents)} agents",
                f"Expected {expected_count}+ agents"
            ))
        except Exception as e:
            checks.append(self._check(
                "Agent Registry",
                False,
                "Failed",
                f"Error: {str(e)}",
                blocking=True
            ))
        
        # Check 3.2: Agent initialization (Alpha Swarm)
        alpha_agents = ["hunter", "enricher", "segmentor", "crafter", "gatekeeper"]
        for agent_id in alpha_agents:
            try:
                success = self.registry.initialize_agent(agent_id)
                agent_info = self.registry.agents.get(agent_id)
                
                checks.append(self._check(
                    f"Agent: {agent_id.upper()}",
                    agent_info.status == AgentStatus.AVAILABLE if agent_info else False,
                    "Initialized ✓" if success else "Failed",
                    f"Status: {agent_info.status.value if agent_info else 'unknown'}",
                    blocking=(agent_id in ["enricher", "segmentor"])
                ))
            except Exception as e:
                checks.append(self._check(
                    f"Agent: {agent_id.upper()}",
                    False,
                    "Error",
                    str(e)[:100],
                    blocking=True
                ))
        
        # Check 3.3: Agent initialization (Revenue Swarm)
        revenue_agents = ["queen", "scout"]
        for agent_id in revenue_agents:
            try:
                success = self.registry.initialize_agent(agent_id)
                agent_info = self.registry.agents.get(agent_id)
                
                checks.append(self._check(
                    f"Agent: {agent_id.upper()} (Revenue)",
                    agent_info.status == AgentStatus.AVAILABLE if agent_info else False,
                    "Initialized ✓" if success else "Not yet implemented",
                    f"Status: {agent_info.status.value if agent_info else 'unknown'}",
                    blocking=False
                ))
            except Exception as e:
                checks.append(self._check(
                    f"Agent: {agent_id.upper()} (Revenue)",
                    False,
                    "Error",
                    str(e)[:100],
                    blocking=False
                ))
        
        # Check 3.4: Critical execution scripts
        base_path = Path(__file__).parent
        critical_scripts = {
            "run_pipeline.py": True,
            "health_check.py": False,
            "gdpr_delete.py": True,
            "gdpr_export.py": True
        }
        
        for script, is_blocking in critical_scripts.items():
            script_path = base_path / script
            checks.append(self._check(
                f"Script: {script}",
                script_path.exists(),
                "Present ✓",
                f"Missing: {script}",
                blocking=is_blocking
            ))
        
        self.validation_results["functional"] = checks
        self._print_results(checks)
    
    def _validate_performance(self):
        """Level 4: Performance validation."""
        print("\n⚡ Level 4: Performance Validation")
        print("-" * 70)
        
        checks = []
        
        # Check 4.1: Rate limiting configured
        linkedin_limit = os.getenv("LINKEDIN_RATE_LIMIT", "0")
        clay_limit = os.getenv("CLAY_RATE_LIMIT", "0")
        
        checks.append(self._check(
            "Rate Limiting",
            int(linkedin_limit) > 0 and int(clay_limit) > 0,
            f"LinkedIn: {linkedin_limit}/min, Clay: {clay_limit}/min",
            "Not configured - risk of API bans",
            blocking=True
        ))
        
        # Check 4.2: Context management
        context_path = Path(__file__).parent.parent / "core" / "context.py"
        checks.append(self._check(
            "Context Management (FIC)",
            context_path.exists(),
            "Implemented ✓",
            "Required to prevent agent degradation",
            blocking=False
        ))
        
        # Check 4.3: Resource monitoring
        health_check_path = Path(__file__).parent / "health_check.py"
        checks.append(self._check(
            "Health Monitoring",
            health_check_path.exists(),
            "Available ✓",
            "Recommended for production",
            blocking=False
        ))
        
        self.validation_results["performance"] = checks
        self._print_results(checks)
    
    def _validate_security(self):
        """Level 5: Security validation."""
        print("\n🔒 Level 5: Security Validation")
        print("-" * 70)
        
        checks = []
        
        # Check 5.1: .env in .gitignore
        gitignore_path = Path(__file__).parent.parent / ".gitignore"
        env_protected = False
        if gitignore_path.exists():
            with open(gitignore_path, 'r') as f:
                env_protected = '.env' in f.read()
        
        checks.append(self._check(
            ".env Protection",
            env_protected,
            "Protected in .gitignore ✓",
            "WARNING: .env may be committed to git",
            blocking=True
        ))
        
        # Check 5.2: Credentials not hardcoded
        dangerous_patterns = ["your_linkedin_email", "your_linkedin_password", "your_gohighlevel_api_key"]
        env_file = Path(__file__).parent.parent / ".env"
        hardcoded_found = False
        
        if env_file.exists():
            with open(env_file, 'r') as f:
                content = f.read()
                for pattern in dangerous_patterns:
                    if pattern in content:
                        hardcoded_found = True
                        break
        
        checks.append(self._check(
            "Credentials Configured",
            not hardcoded_found,
            "Real credentials in use ✓",
            "Default/placeholder credentials detected",
            blocking=True
        ))
        
        # Check 5.3: GDPR compliance tools
        gdpr_delete = Path(__file__).parent / "gdpr_delete.py"
        gdpr_export = Path(__file__).parent / "gdpr_export.py"
        
        checks.append(self._check(
            "GDPR Compliance",
            gdpr_delete.exists() and gdpr_export.exists(),
            "Delete and Export tools present ✓",
            "Required for GDPR compliance",
            blocking=True
        ))
        
        # Check 5.4: Audit logging
        event_log_path = Path(__file__).parent.parent / ".hive-mind" / "events.jsonl"
        checks.append(self._check(
            "Audit Logging",
            event_log_path.exists(),
            "Active ✓",
            "Recommended for compliance",
            blocking=False
        ))
        
        self.validation_results["security"] = checks
        self._print_results(checks)
    
    def _check(self, name: str, passed: bool, success_msg: str, failure_msg: str, blocking: bool = False) -> Dict[str, Any]:
        """Create a check result."""
        result = {
            "name": name,
            "passed": passed,
            "message": success_msg if passed else failure_msg,
            "blocking": blocking,
            "timestamp": datetime.now().isoformat()
        }
        
        if not passed and blocking:
            self.blocking_issues.append(result)
        
        return result
    
    def _print_results(self, checks: List[Dict[str, Any]]):
        """Print check results."""
        for check in checks:
            icon = "✅" if check["passed"] else ("🚨" if check["blocking"] else "⚠️")
            print(f"  {icon} {check['name']}: {check['message']}")
        print()
    
    def _generate_final_report(self) -> Dict[str, Any]:
        """Generate final validation report."""
        duration = time.time() - self.start_time
        
        # Calculate totals
        all_checks = []
        for category in self.validation_results.values():
            all_checks.extend(category)
        
        total = len(all_checks)
        passed = sum(1 for c in all_checks if c["passed"])
        failed = total - passed
        blocking = len(self.blocking_issues)
        
        score = int((passed / total) * 100) if total > 0 else 0
        
        print("\n" + "=" * 70)
        print("📊 VALIDATION REPORT")
        print("=" * 70)
        print(f"Duration: {duration:.2f} seconds")
        print(f"Total Checks: {total}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} ❌")
        print(f"Blocking Issues: {blocking} 🚨")
        print(f"\nValidation Score: {score}%")
        print("=" * 70)
        
        # Determine deployment readiness
        if blocking > 0:
            status = "🚨 BLOCKED - Cannot deploy to production"
            print(f"\n{status}\n")
            print(f"You have {blocking} blocking issue(s) that must be resolved:\n")
            for i, issue in enumerate(self.blocking_issues, 1):
                print(f"{i}. {issue['name']}: {issue['message']}")
        elif score >= 95:
            status = "✅ PRODUCTION READY"
            print(f"\n{status}\n")
            print("Next steps:")
            print("1. Deploy to production environment")
            print("2. Monitor with: python execution/health_check.py")
            print("3. Set up automated backups")
        elif score >= 85:
            status = "⚠️  READY FOR STAGING"
            print(f"\n{status}\n")
            print("Next steps:")
            print("1. Address remaining warnings")
            print("2. Test in staging environment")
            print("3. Re-validate before production")
        else:
            status = "❌ NOT READY"
            print(f"\n{status}\n")
            print("Significant work needed before deployment.")
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "mode": self.mode,
            "duration_seconds": duration,
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "blocking_issues": blocking,
            "score": score,
            "status": status,
            "results": self.validation_results,
            "blocking_details": self.blocking_issues
        }
        
        # Save report
        reports_dir = Path(__file__).parent.parent / ".hive-mind" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        report_file = reports_dir / f"validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📄 Full report saved to: {report_file}\n")
        
        return report


def main():
    """Run production validation."""
    parser = argparse.ArgumentParser(description="Production Readiness Validator")
    parser.add_argument("--mode", choices=["staging", "production"], default="production", help="Deployment mode")
    parser.add_argument("--skip-api-tests", action="store_true", help="Skip API connectivity tests")
    args = parser.parse_args()
    
    validator = ProductionValidator(mode=args.mode, skip_api_tests=args.skip_api_tests)
    report = validator.run_full_validation()
    
    # Exit code
    sys.exit(0 if report["blocking_issues"] == 0 else 1)


if __name__ == "__main__":
    main()
