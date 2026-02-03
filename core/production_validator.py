"""
Production Validator - Agent Manager Extension
==============================================
Validates production readiness using Agent Manager coordination

Author: Chris Daigle (Chiefaiofficer.com)
Version: 1.0.0
Date: 2026-01-19
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict

from core.agent_manager import AgentManager, AgentStatus

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Production validation result"""
    check_name: str
    status: str  # pass, fail, warning
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


class ProductionValidator:
    """
    Validates production readiness across all agents
    
    Integrates with Agent Manager to coordinate validation checks
    """
    
    def __init__(self, agent_manager: AgentManager):
        self.am = agent_manager
        self.results: List[ValidationResult] = []
        self.data_dir = Path(__file__).parent.parent / ".hive-mind"
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_all(self) -> Dict[str, Any]:
        """
        Run all production readiness checks
        
        Returns:
            Comprehensive validation report
        """
        logger.info("🔍 Starting production readiness validation...")
        
        self.results = []
        
        # 1. Agent Health Checks
        self._validate_agent_health()
        
        # 2. API Connectivity
        self._validate_api_connections()
        
        # 3. Framework Integration
        self._validate_framework_integration()
        
        # 4. Workflow Functionality
        self._validate_workflows()
        
        # 5. Data Integrity
        self._validate_data_integrity()
        
        # 6. Security & Compliance
        self._validate_security()
        
        # 7. Performance Benchmarks
        self._validate_performance()
        
        # 8. Monitoring & Alerts
        self._validate_monitoring()
        
        # Generate report
        report = self._generate_report()
        
        # Save results
        self._save_results(report)
        
        return report
    
    def _validate_agent_health(self):
        """Validate all agents are healthy and operational"""
        logger.info("Checking agent health...")
        
        agents = self.am.registry.list_agents()
        
        if not agents:
            self.results.append(ValidationResult(
                check_name="agent_registry",
                status="fail",
                message="No agents registered",
                details={"expected_min": 5, "actual": 0}
            ))
            return
        
        healthy_count = 0
        unhealthy_agents = []
        
        for agent in agents:
            health = self.am.registry.agent_health_check(agent.agent_id)
            
            if health.get("healthy"):
                healthy_count += 1
            else:
                unhealthy_agents.append({
                    "agent_id": agent.agent_id,
                    "error": health.get("error", "Unknown")
                })
        
        if unhealthy_agents:
            self.results.append(ValidationResult(
                check_name="agent_health",
                status="fail",
                message=f"{len(unhealthy_agents)} agents unhealthy",
                details={"unhealthy_agents": unhealthy_agents}
            ))
        else:
            self.results.append(ValidationResult(
                check_name="agent_health",
                status="pass",
                message=f"All {healthy_count} agents healthy",
                details={"total_agents": healthy_count}
            ))
    
    def _validate_api_connections(self):
        """Validate all required API connections"""
        logger.info("Checking API connections...")
        
        # Check for connection test results
        connection_test_file = self.data_dir / "connection_test.json"
        
        if not connection_test_file.exists():
            self.results.append(ValidationResult(
                check_name="api_connections",
                status="fail",
                message="No connection test results found",
                details={"action": "Run: python execution/test_connections.py"}
            ))
            return
        
        with open(connection_test_file, 'r') as f:
            connection_data = json.load(f)
        
        required_services = connection_data.get("required_services", {})
        all_pass = connection_data.get("all_required_pass", False)
        
        if all_pass:
            self.results.append(ValidationResult(
                check_name="api_connections",
                status="pass",
                message="All required API connections verified",
                details=required_services
            ))
        else:
            failed_services = [
                k for k, v in required_services.items()
                if not v.get("status") == "pass"
            ]
            
            self.results.append(ValidationResult(
                check_name="api_connections",
                status="fail",
                message=f"{len(failed_services)} API connections failed",
                details={"failed_services": failed_services}
            ))
    
    def _validate_framework_integration(self):
        """Validate core framework components are integrated"""
        logger.info("Checking framework integration...")
        
        required_components = [
            ("core/context_manager.py", "Context Manager"),
            ("core/grounding_chain.py", "Grounding Chain"),
            ("core/feedback_collector.py", "Feedback Collector")
        ]
        
        missing_components = []
        
        for file_path, component_name in required_components:
            full_path = Path(__file__).parent.parent / file_path
            if not full_path.exists():
                missing_components.append(component_name)
        
        if missing_components:
            self.results.append(ValidationResult(
                check_name="framework_integration",
                status="warning",
                message=f"{len(missing_components)} components not integrated",
                details={
                    "missing": missing_components,
                    "action": "See: .hive-mind/WEEK_1_DAY_3-4_FRAMEWORK.md"
                }
            ))
        else:
            self.results.append(ValidationResult(
                check_name="framework_integration",
                status="pass",
                message="All core framework components integrated"
            ))
    
    def _validate_workflows(self):
        """Validate critical workflows are functional"""
        logger.info("Checking workflows...")
        
        # Check for workflow definitions
        workflows_dir = Path(__file__).parent.parent / ".agent" / "workflows"
        
        if not workflows_dir.exists():
            self.results.append(ValidationResult(
                check_name="workflows",
                status="warning",
                message="No workflows directory found",
                details={"action": "Create .agent/workflows/"}
            ))
            return
        
        workflow_files = list(workflows_dir.glob("*.md"))
        
        if len(workflow_files) < 3:
            self.results.append(ValidationResult(
                check_name="workflows",
                status="warning",
                message=f"Only {len(workflow_files)} workflows defined",
                details={
                    "expected_min": 3,
                    "found": [f.stem for f in workflow_files]
                }
            ))
        else:
            self.results.append(ValidationResult(
                check_name="workflows",
                status="pass",
                message=f"{len(workflow_files)} workflows defined",
                details={"workflows": [f.stem for f in workflow_files]}
            ))
    
    def _validate_data_integrity(self):
        """Validate data storage and integrity"""
        logger.info("Checking data integrity...")
        
        # Check .hive-mind structure
        required_dirs = [
            "scraped",
            "enriched",
            "campaigns",
            "knowledge"
        ]
        
        missing_dirs = []
        
        for dir_name in required_dirs:
            dir_path = self.data_dir / dir_name
            if not dir_path.exists():
                missing_dirs.append(dir_name)
        
        if missing_dirs:
            self.results.append(ValidationResult(
                check_name="data_integrity",
                status="warning",
                message=f"{len(missing_dirs)} data directories missing",
                details={"missing": missing_dirs}
            ))
        else:
            self.results.append(ValidationResult(
                check_name="data_integrity",
                status="pass",
                message="All data directories present"
            ))
    
    def _validate_security(self):
        """Validate security and compliance"""
        logger.info("Checking security...")
        
        # Check .env file exists and has required keys
        env_file = Path(__file__).parent.parent / ".env"
        
        if not env_file.exists():
            self.results.append(ValidationResult(
                check_name="security",
                status="fail",
                message=".env file not found",
                details={"action": "Create .env from .env.template"}
            ))
            return
        
        # Check for sensitive data in git
        gitignore = Path(__file__).parent.parent / ".gitignore"
        
        if gitignore.exists():
            with open(gitignore, 'r') as f:
                gitignore_content = f.read()
            
            if ".env" in gitignore_content:
                self.results.append(ValidationResult(
                    check_name="security",
                    status="pass",
                    message="Security configuration valid"
                ))
            else:
                self.results.append(ValidationResult(
                    check_name="security",
                    status="warning",
                    message=".env not in .gitignore",
                    details={"action": "Add .env to .gitignore"}
                ))
        else:
            self.results.append(ValidationResult(
                check_name="security",
                status="warning",
                message="No .gitignore found"
            ))
    
    def _validate_performance(self):
        """Validate performance benchmarks"""
        logger.info("Checking performance...")
        
        # Check for performance test results
        perf_file = self.data_dir / "performance_benchmarks.json"
        
        if not perf_file.exists():
            self.results.append(ValidationResult(
                check_name="performance",
                status="warning",
                message="No performance benchmarks recorded",
                details={"action": "Run performance tests"}
            ))
        else:
            self.results.append(ValidationResult(
                check_name="performance",
                status="pass",
                message="Performance benchmarks available"
            ))
    
    def _validate_monitoring(self):
        """Validate monitoring and alerting"""
        logger.info("Checking monitoring...")
        
        # Check for monitoring setup
        monitoring_files = [
            "execution/health_monitor.py",
            "dashboard/kpi_dashboard.py"
        ]
        
        missing_monitoring = []
        
        for file_path in monitoring_files:
            full_path = Path(__file__).parent.parent / file_path
            if not full_path.exists():
                missing_monitoring.append(file_path)
        
        if missing_monitoring:
            self.results.append(ValidationResult(
                check_name="monitoring",
                status="warning",
                message=f"{len(missing_monitoring)} monitoring components missing",
                details={"missing": missing_monitoring}
            ))
        else:
            self.results.append(ValidationResult(
                check_name="monitoring",
                status="pass",
                message="Monitoring infrastructure in place"
            ))
    
    def _generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive validation report"""
        
        total_checks = len(self.results)
        passed = sum(1 for r in self.results if r.status == "pass")
        failed = sum(1 for r in self.results if r.status == "fail")
        warnings = sum(1 for r in self.results if r.status == "warning")
        
        # Calculate readiness score
        readiness_score = (passed / total_checks * 100) if total_checks > 0 else 0
        
        # Determine overall status
        if failed > 0:
            overall_status = "NOT_READY"
        elif warnings > 2:
            overall_status = "NEEDS_ATTENTION"
        elif readiness_score >= 90:
            overall_status = "PRODUCTION_READY"
        else:
            overall_status = "PARTIALLY_READY"
        
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": overall_status,
            "readiness_score": round(readiness_score, 1),
            "summary": {
                "total_checks": total_checks,
                "passed": passed,
                "failed": failed,
                "warnings": warnings
            },
            "results": [asdict(r) for r in self.results],
            "recommendations": self._generate_recommendations()
        }
        
        return report
    
    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        for result in self.results:
            if result.status == "fail":
                recommendations.append(
                    f"🔴 CRITICAL: {result.check_name} - {result.message}"
                )
            elif result.status == "warning":
                recommendations.append(
                    f"🟡 WARNING: {result.check_name} - {result.message}"
                )
        
        if not recommendations:
            recommendations.append("✅ All checks passed! System is production ready.")
        
        return recommendations
    
    def _save_results(self, report: Dict[str, Any]):
        """Save validation results"""
        output_file = self.data_dir / "production_validation.json"
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"📊 Validation report saved to: {output_file}")
        
        # Also save human-readable version
        self._save_markdown_report(report)
    
    def _save_markdown_report(self, report: Dict[str, Any]):
        """Save human-readable markdown report"""
        output_file = self.data_dir / "PRODUCTION_VALIDATION_REPORT.md"
        
        content = f"""# 🎯 Production Readiness Validation Report

**Generated:** {report['timestamp']}  
**Overall Status:** {report['overall_status']}  
**Readiness Score:** {report['readiness_score']}%

---

## 📊 Summary

- **Total Checks:** {report['summary']['total_checks']}
- **Passed:** ✅ {report['summary']['passed']}
- **Failed:** ❌ {report['summary']['failed']}
- **Warnings:** ⚠️ {report['summary']['warnings']}

---

## 🔍 Detailed Results

"""
        
        for result in self.results:
            status_icon = {
                "pass": "✅",
                "fail": "❌",
                "warning": "⚠️"
            }.get(result.status, "❓")
            
            content += f"### {status_icon} {result.check_name}\n\n"
            content += f"**Status:** {result.status.upper()}  \n"
            content += f"**Message:** {result.message}  \n"
            
            if result.details:
                content += f"**Details:**\n```json\n{json.dumps(result.details, indent=2)}\n```\n"
            
            content += "\n---\n\n"
        
        content += "## 📋 Recommendations\n\n"
        
        for rec in report['recommendations']:
            content += f"- {rec}\n"
        
        content += f"\n---\n\n**Report saved:** `.hive-mind/production_validation.json`\n"
        
        with open(output_file, 'w') as f:
            f.write(content)
        
        logger.info(f"📄 Markdown report saved to: {output_file}")


def main():
    """Run production validation"""
    from core.agent_manager import AgentManager
    
    # Initialize Agent Manager
    am = AgentManager()
    
    # Create validator
    validator = ProductionValidator(am)
    
    # Run validation
    report = validator.validate_all()
    
    # Print summary
    print("\n" + "="*60)
    print("🎯 PRODUCTION READINESS VALIDATION")
    print("="*60)
    print(f"\nOverall Status: {report['overall_status']}")
    print(f"Readiness Score: {report['readiness_score']}%")
    print(f"\nPassed: {report['summary']['passed']}")
    print(f"Failed: {report['summary']['failed']}")
    print(f"Warnings: {report['summary']['warnings']}")
    print("\n" + "="*60)
    print("\n📋 Recommendations:\n")
    
    for rec in report['recommendations']:
        print(f"  {rec}")
    
    print(f"\n📊 Full report: .hive-mind/PRODUCTION_VALIDATION_REPORT.md\n")
    
    return report


if __name__ == "__main__":
    main()
