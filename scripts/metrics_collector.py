
#!/usr/bin/env python3
"""
Metrics Collector
=================
Collect and aggregate system metrics for the feedback loop.
Tracks failure rates, self-annealing performance, and test coverage.
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

import sys
sys.path.append(str(Path(__file__).parent.parent))

from core.failure_tracker import FailureTracker

class MetricsCollector:
    """Collects system health and performance metrics."""
    
    def __init__(self, storage_dir: str = ".hive-mind/metrics"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.tracker = FailureTracker()
        
    def collect_snapshot(self) -> Dict[str, Any]:
        """Capture a point-in-time snapshot of system metrics."""
        
        # 1. Failure Stats
        fail_stats = self.tracker.get_stats()
        
        # 2. Performance (stubbed - would come from benchmark_swarm.py results)
        perf_stats = self._get_performance_stats()
        
        # 3. Coverage (stubbed - would parse pytest output)
        coverage_stats = self._get_coverage_stats()
        
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "failures": fail_stats,
            "performance": perf_stats,
            "coverage": coverage_stats,
            "system_health_score": self._calculate_health_score(fail_stats, perf_stats)
        }
        
        self._save_snapshot(snapshot)
        return snapshot
        
    def _get_performance_stats(self) -> Dict[str, float]:
        """Load latest benchmark results."""
        bench_file = Path(".tmp/latest_benchmark.json")
        if bench_file.exists():
            try:
                with open(bench_file) as f:
                    return json.load(f).get("metrics", {})
            except:
                pass
        return {"avg_latency": 0.0, "throughput": 0.0}

    def _get_coverage_stats(self) -> Dict[str, float]:
        """Load latest coverage data."""
        # Stub
        return {"total_coverage": 85.0}

    def _calculate_health_score(self, failures: Dict, perf: Dict) -> float:
        """Calculate score 0-100 based on weighted metrics."""
        score = 100
        
        # Deduct for unresolved failures
        unresolved = failures.get("unresolved", 0)
        score -= (unresolved * 5)
        
        # Deduct for latency > 2s
        latency = perf.get("avg_latency", 0)
        if latency > 2.0:
            score -= 10
            
        return max(0, score)

    def _save_snapshot(self, snapshot: Dict):
        """Save daily metrics file."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        file_path = self.storage_dir / f"metrics_{date_str}.json"
        
        # Determine if we append or overwrite (daily file)
        # For simplicity, we'll just write one snapshot per execution for now
        # In prod, this would likely be a time-series DB or appended log
        with open(file_path, 'w') as f:
            json.dump(snapshot, f, indent=2)

if __name__ == "__main__":
    collector = MetricsCollector()
    snapshot = collector.collect_snapshot()
    print(f"Metrics collected: Health Score = {snapshot['system_health_score']}")
