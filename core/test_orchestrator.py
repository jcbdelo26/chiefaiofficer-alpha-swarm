"""
Test Orchestrator - Agent Manager Extension
============================================
Coordinates testing across all agents using Agent Manager

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

from core.agent_manager import AgentManager

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Individual test result"""
    test_name: str
    agent_id: str
    status: str  # pass, fail, skip
    duration_ms: float
    error: Optional[str] = None
    output: Optional[Dict[str, Any]] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


class TestOrchestrator:
    """
    Orchestrates testing across all agents
    
    Coordinates:
    - Unit tests for individual agents
    - Integration tests for workflows
    - End-to-end tests for complete pipelines
    - Performance benchmarks
    """
    
    def __init__(self, agent_manager: AgentManager):
        self.am = agent_manager
        self.test_results: List[TestResult] = []
        self.data_dir = Path(__file__).parent.parent / ".hive-mind" / "testing"
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def run_all_tests(self, test_mode: str = "full") -> Dict[str, Any]:
        """
        Run all test suites
        
        Args:
            test_mode: "quick", "full", or "comprehensive"
        
        Returns:
            Test results summary
        """
        logger.info(f"🧪 Running {test_mode} test suite...")
        
        self.test_results = []
        
        if test_mode in ["quick", "full", "comprehensive"]:
            self._run_unit_tests()
        
        if test_mode in ["full", "comprehensive"]:
            self._run_integration_tests()
        
        if test_mode == "comprehensive":
            self._run_e2e_tests()
            self._run_performance_tests()
        
        # Generate report
        report = self._generate_test_report()
        
        # Save results
        self._save_test_results(report)
        
        return report
    
    def test_agent(self, agent_id: str, test_data: Optional[Dict] = None) -> TestResult:
        """
        Test individual agent functionality
        
        Args:
            agent_id: Agent to test
            test_data: Optional test input data
        
        Returns:
            Test result
        """
        logger.info(f"Testing agent: {agent_id}")
        
        start_time = datetime.utcnow()
        
        try:
            # Get agent metadata
            agent = self.am.registry.get_agent(agent_id=agent_id)
            
            if not agent:
                return TestResult(
                    test_name=f"test_{agent_id}_exists",
                    agent_id=agent_id,
                    status="fail",
                    duration_ms=0,
                    error="Agent not registered"
                )
            
            # Test agent health
            health = self.am.registry.agent_health_check(agent_id)
            
            if not health.get("healthy"):
                return TestResult(
                    test_name=f"test_{agent_id}_health",
                    agent_id=agent_id,
                    status="fail",
                    duration_ms=0,
                    error=health.get("error", "Health check failed")
                )
            
            # Calculate duration
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return TestResult(
                test_name=f"test_{agent_id}_basic",
                agent_id=agent_id,
                status="pass",
                duration_ms=duration,
                output={"health": health}
            )
        
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return TestResult(
                test_name=f"test_{agent_id}_basic",
                agent_id=agent_id,
                status="fail",
                duration_ms=duration,
                error=str(e)
            )
    
    def test_workflow(self, workflow_id: str, test_data: Dict[str, Any]) -> List[TestResult]:
        """
        Test complete workflow
        
        Args:
            workflow_id: Workflow to test
            test_data: Test input data
        
        Returns:
            List of test results for each step
        """
        logger.info(f"Testing workflow: {workflow_id}")
        
        results = []
        
        # TODO: Implement workflow testing
        # - Load workflow definition
        # - Execute each step with test data
        # - Validate outputs
        # - Check handoffs
        
        return results
    
    def _run_unit_tests(self):
        """Run unit tests for all agents"""
        logger.info("Running unit tests...")
        
        agents = self.am.registry.list_agents()
        
        for agent in agents:
            result = self.test_agent(agent.agent_id)
            self.test_results.append(result)
    
    def _run_integration_tests(self):
        """Run integration tests for workflows"""
        logger.info("Running integration tests...")
        
        # Test critical workflows
        workflows = [
            "lead-harvesting",
            "rpi-campaign-creation",
            "sparc-implementation"
        ]
        
        for workflow_id in workflows:
            # Create test data
            test_data = self._create_test_data(workflow_id)
            
            # Test workflow
            results = self.test_workflow(workflow_id, test_data)
            self.test_results.extend(results)
    
    def _run_e2e_tests(self):
        """Run end-to-end tests"""
        logger.info("Running end-to-end tests...")
        
        # TODO: Implement E2E tests
        # - Test complete lead-to-campaign pipeline
        # - Verify data flow through all agents
        # - Check final outputs
    
    def _run_performance_tests(self):
        """Run performance benchmarks"""
        logger.info("Running performance tests...")
        
        # TODO: Implement performance tests
        # - Test agent response times
        # - Test throughput
        # - Test resource usage
    
    def _create_test_data(self, workflow_id: str) -> Dict[str, Any]:
        """Create test data for workflow"""
        
        # Load test fixtures
        fixtures_file = self.data_dir / f"{workflow_id}_fixtures.json"
        
        if fixtures_file.exists():
            with open(fixtures_file, 'r') as f:
                return json.load(f)
        
        # Return default test data
        return {
            "test_mode": True,
            "linkedin_url": "https://linkedin.com/in/test",
            "email": "test@example.com"
        }
    
    def _generate_test_report(self) -> Dict[str, Any]:
        """Generate test results report"""
        
        total_tests = len(self.test_results)
        passed = sum(1 for r in self.test_results if r.status == "pass")
        failed = sum(1 for r in self.test_results if r.status == "fail")
        skipped = sum(1 for r in self.test_results if r.status == "skip")
        
        # Calculate success rate
        success_rate = (passed / total_tests * 100) if total_tests > 0 else 0
        
        # Calculate average duration
        durations = [r.duration_ms for r in self.test_results if r.duration_ms > 0]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total_tests": total_tests,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "success_rate": round(success_rate, 1),
                "avg_duration_ms": round(avg_duration, 2)
            },
            "results": [asdict(r) for r in self.test_results],
            "failed_tests": [
                asdict(r) for r in self.test_results if r.status == "fail"
            ]
        }
        
        return report
    
    def _save_test_results(self, report: Dict[str, Any]):
        """Save test results"""
        output_file = self.data_dir / "test_results.json"
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"📊 Test results saved to: {output_file}")
        
        # Save markdown report
        self._save_markdown_report(report)
    
    def _save_markdown_report(self, report: Dict[str, Any]):
        """Save human-readable test report"""
        output_file = self.data_dir / "TEST_REPORT.md"
        
        content = f"""# 🧪 Test Results Report

**Generated:** {report['timestamp']}

---

## 📊 Summary

- **Total Tests:** {report['summary']['total_tests']}
- **Passed:** ✅ {report['summary']['passed']}
- **Failed:** ❌ {report['summary']['failed']}
- **Skipped:** ⏭️ {report['summary']['skipped']}
- **Success Rate:** {report['summary']['success_rate']}%
- **Average Duration:** {report['summary']['avg_duration_ms']}ms

---

## ❌ Failed Tests

"""
        
        if report['failed_tests']:
            for test in report['failed_tests']:
                content += f"### {test['test_name']}\n\n"
                content += f"**Agent:** {test['agent_id']}  \n"
                content += f"**Error:** {test.get('error', 'Unknown')}  \n\n"
        else:
            content += "✅ No failed tests!\n\n"
        
        content += "---\n\n"
        content += "**Full results:** `.hive-mind/testing/test_results.json`\n"
        
        with open(output_file, 'w') as f:
            f.write(content)
        
        logger.info(f"📄 Test report saved to: {output_file}")


def main():
    """Run test orchestrator"""
    from core.agent_manager import AgentManager
    
    # Initialize Agent Manager
    am = AgentManager()
    
    # Create test orchestrator
    orchestrator = TestOrchestrator(am)
    
    # Run tests
    report = orchestrator.run_all_tests(test_mode="full")
    
    # Print summary
    print("\n" + "="*60)
    print("🧪 TEST RESULTS")
    print("="*60)
    print(f"\nTotal Tests: {report['summary']['total_tests']}")
    print(f"Passed: ✅ {report['summary']['passed']}")
    print(f"Failed: ❌ {report['summary']['failed']}")
    print(f"Success Rate: {report['summary']['success_rate']}%")
    print("\n" + "="*60)
    
    if report['failed_tests']:
        print("\n❌ Failed Tests:\n")
        for test in report['failed_tests']:
            print(f"  - {test['test_name']}: {test.get('error', 'Unknown')}")
    
    print(f"\n📊 Full report: .hive-mind/testing/TEST_REPORT.md\n")
    
    return report


if __name__ == "__main__":
    main()
