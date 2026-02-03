
"""
Run Failure Campaign
====================
Execute all failure scenarios to stress-test the system and populate the FailureTracker.
Generates a comprehensive report of system resilience.
"""

import pytest
import sys
import json
from pathlib import Path
from datetime import datetime

def run_campaign():
    print("=" * 60)
    print("Failure Injection Campaign")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # 1. Run all failure tests
    print("\n[1] Executing Failure Scenarios...")
    
    scenarios = [
        "tests/failure_scenarios/test_api_failures.py",
        "tests/failure_scenarios/test_data_quality.py",
        "tests/failure_scenarios/test_logic_failures.py",
        "tests/failure_scenarios/test_resource_limits.py"
    ]
    
    results = {}
    total_passed = 0
    total_failed = 0
    
    for scenario in scenarios:
        print(f"  -> Running {scenario}...")
        exit_code = pytest.main([scenario, "-v", "-q", "--disable-warnings"])
        
        status = "PASSED" if exit_code == 0 else "FAILED"
        if exit_code == 0:
            total_passed += 1
        else:
            total_failed += 1
            
        results[scenario] = status
        print(f"     Status: {status}")

    # 2. Analyze collected failures
    print("\n[2] Analyzing Impact...")
    try:
        from core.failure_tracker import FailureTracker
        from core.pattern_analyzer import PatternAnalyzer
        
        tracker = FailureTracker()
        analyzer = PatternAnalyzer()
        
        stats = tracker.get_stats()
        print(f"  -> Failures Logged: {stats['total']}")
        print(f"  -> By Category: {stats['by_category']}")
        
        patterns = analyzer.analyze_failures()
        print(f"  -> Patterns Detected: {len(patterns)}")
        
        for p in patterns:
            print(f"     - {p.pattern_id} (Count: {p.frequency})")
            
    except ImportError:
        print("  -> Core modules not found, skipping analysis.")
    except Exception as e:
        print(f"  -> Analysis failed: {e}")

    # 3. Generate Report
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_scenarios": len(scenarios),
            "passed": total_passed,
            "failed": total_failed,
            "resilience_score": (total_passed / len(scenarios)) * 100
        },
        "details": results
    }
    
    report_path = Path(".tmp/failure_campaign_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        
    print("\n" + "=" * 60)
    print(f"CAMPAIGN COMPLETE. Score: {report['summary']['resilience_score']:.1f}%")
    print(f"Report saved to: {report_path}")
    print("=" * 60)

if __name__ == "__main__":
    run_campaign()
