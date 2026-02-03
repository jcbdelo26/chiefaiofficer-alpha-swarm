
#!/usr/bin/env python3
"""
Weekly Self-Review
==================
Generates a weekly markdown report analyzing system performance, failures, and improvements.
Intended to be run by cron/scheduler every Sunday.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import sys
sys.path.append(str(Path(__file__).parent.parent))

from core.pattern_analyzer import PatternAnalyzer

class WeeklyReviewGenerator:
    """Generates the weekly self-review report."""
    
    def __init__(self, metrics_dir: str = ".hive-mind/metrics"):
        self.metrics_dir = Path(metrics_dir)
        self.output_dir = Path(".hive-mind/reviews")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.analyzer = PatternAnalyzer()
        
    def generate_report(self) -> Path:
        """Generate the markdown report."""
        
        # Gather data
        metrics = self._gather_weekly_metrics()
        patterns = self.analyzer.analyze_failures()
        
        # Build Report
        report_date = datetime.now().strftime("%Y-%m-%d")
        content = f"# 🤖 Weekly Swarm Self-Review: {report_date}\n\n"
        
        # Section 1: Executive Summary
        content += "## 1. Executive Summary\n"
        avg_health = sum(m['system_health_score'] for m in metrics) / len(metrics) if metrics else 100
        content += f"- **System Health Score**: {avg_health:.1f}/100\n"
        content += f"- **Total Failures**: {sum(m['failures']['total'] for m in metrics) if metrics else 0}\n"
        content += f"- **Self-Healing Rate**: {metrics[-1]['failures'].get('resolution_rate', 0)*100:.1f}% (Last 24h)\n\n"
        
        # Section 2: Top Failure Patterns
        content += "## 2. Top Failure Patterns\n"
        if patterns:
            for p in patterns[:3]:
                content += f"### {p.pattern_id.replace('_', ' ').title()}\n"
                content += f"- **Frequency**: {p.frequency}\n"
                content += f"- **Root Cause**: {p.root_cause}\n"
                content += f"- **Status**: {'Auto-Fixed' if 'fix' in str(p.suggested_fix) else 'Requires Attention'}\n\n"
        else:
            content += "*No significant failure patterns detected this week.*\n\n"
            
        # Section 3: Recommendations
        content += "## 3. Recommended Actions\n"
        content += self._generate_recommendations(patterns)
        
        # Save Report
        filename = f"weekly_review_{report_date}.md"
        output_path = self.output_dir / filename
        with open(output_path, 'w') as f:
            f.write(content)
            
        return output_path
        
    def _gather_weekly_metrics(self) -> List[Dict]:
        """Load all metrics files from the last 7 days."""
        metrics = []
        # Simply load all for now (simulated)
        for f in self.metrics_dir.glob("metrics_*.json"):
            try:
                with open(f) as fp:
                    metrics.append(json.load(fp))
            except:
                pass
        return metrics

    def _generate_recommendations(self, patterns: List) -> str:
        """Auto-generate recommendations based on patterns."""
        if not patterns:
            return "- ✅ Maintain current operational parameters.\n"
            
        recs = ""
        for p in patterns[:3]:
            if "rate_limit" in p.pattern_id:
                recs += f"- ⚠️ **ACTION**: Increase backoff configuration for {p.affected_agents[0]} due to rate limits.\n"
            elif "validation" in p.pattern_id:
                recs += f"- 📝 **ACTION**: Update input validation templates to catch '{p.pattern_id}'.\n"
            elif "resource" in p.pattern_id:
                recs += "- 🚀 **ACTION**: Scale up worker resources or optimize context window usage.\n"
                
        return recs

if __name__ == "__main__":
    generator = WeeklyReviewGenerator()
    report_path = generator.generate_report()
    print(f"Weekly review generated: {report_path}")
