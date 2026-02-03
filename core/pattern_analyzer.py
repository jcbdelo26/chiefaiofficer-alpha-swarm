#!/usr/bin/env python3
"""
Pattern Analyzer
================
Identify patterns in failures using clustering and semantic analysis.

Features:
- Failure clustering (similar errors grouped)
- Root cause extraction
- Pattern frequency analysis
- Hypothesis generation

Usage:
    from core.pattern_analyzer import PatternAnalyzer
    
    analyzer = PatternAnalyzer()
    patterns = analyzer.analyze_failures()
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass
import re

@dataclass
class FailurePattern:
    """Identified failure pattern."""
    pattern_id: str
    category: str
    frequency: int
    example_error: str
    root_cause: str
    affected_agents: List[str]
    suggested_fix: str

class PatternAnalyzer:
    """Analyze failures to identify patterns."""
    
    def __init__(self, failures_dir: Path = None):
        self.failures_dir = failures_dir or Path(".hive-mind/failures")
        self.reasoning_bank_file = Path(".hive-mind/reasoning_bank.json")
    
    def load_failures(self) -> List[Dict[str, Any]]:
        """Load all failure records."""
        failures_file = self.failures_dir / "all_failures.json"
        if not failures_file.exists():
            return []
        
        with open(failures_file) as f:
            data = json.load(f)
            return list(data.values())
    
    def _extract_error_signature(self, error_message: str) -> str:
        """
        Extract a normalized error signature for clustering.
        
        Example:
            "Rate limit exceeded for agent HUNTER" -> "rate_limit_exceeded"
        """
        # Lowercase and remove special chars
        sig = error_message.lower()
        sig = re.sub(r'[^\w\s]', ' ', sig)
        
        # Extract key terms
        key_terms = []
        
        # Common error patterns
        patterns = [
            (r'rate limit', 'rate_limit'),
            (r'timeout', 'timeout'),
            (r'connection', 'connection_error'),
            (r'validation', 'validation_error'),
            (r'missing.*field', 'missing_field'),
            (r'invalid.*format', 'invalid_format'),
            (r'not found', 'not_found'),
            (r'permission denied', 'permission_denied'),
            (r'memory', 'memory_error'),
            (r'context.*budget', 'context_budget')
        ]
        
        for pattern, term in patterns:
            if re.search(pattern, sig):
                key_terms.append(term)
        
        return '_'.join(key_terms) if key_terms else 'unknown_error'
    
    def cluster_failures(self, failures: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Cluster failures by error signature.
        
        Returns:
            Dict mapping signature -> list of failures
        """
        clusters = defaultdict(list)
        
        for failure in failures:
            sig = self._extract_error_signature(failure['error_message'])
            clusters[sig].append(failure)
        
        return dict(clusters)
    
    def identify_root_cause(self, cluster: List[Dict[str, Any]]) -> Tuple[str, str]:
        """
        Identify root cause and suggested fix for a cluster.
        
        Returns:
            (root_cause, suggested_fix)
        """
        # Analyze first failure in cluster
        example = cluster[0]
        error_msg = example['error_message'].lower()
        category = example['category']
        
        # Pattern matching for known root causes
        if 'rate limit' in error_msg:
            return (
                "API rate limit exceeded",
                "Add exponential backoff with retry logic. Consider implementing request batching."
            )
        
        elif 'timeout' in error_msg:
            return (
                "Request timeout",
                "Increase timeout threshold or optimize request payload. Consider async processing."
            )
        
        elif 'validation' in error_msg or 'invalid' in error_msg:
            return (
                "Data validation failure",
                "Add pre-validation before API call. Implement data normalization pipeline."
            )
        
        elif 'missing' in error_msg:
            return (
                "Missing required data",
                "Add null checks and default values. Improve input validation at ingestion."
            )
        
        elif 'context' in error_msg or 'memory' in error_msg:
            return (
                "Resource exhaustion",
                "Implement context cleanup. Consider reducing payload size or chunking."
            )
        
        elif category == 'api_error':
            return (
                "External API instability",
                "Implement circuit breaker pattern. Add fallback mechanisms."
            )
        
        else:
            return (
                "Unknown root cause - requires manual investigation",
                "Review error logs and stack traces. Consider adding instrumentation."
            )
    
    def analyze_failures(self) -> List[FailurePattern]:
        """
        Analyze all failures and identify patterns.
        
        Returns:
            List of identified patterns
        """
        failures = self.load_failures()
        
        if not failures:
            print("[PatternAnalyzer] No failures to analyze")
            return []
        
        # Cluster by signature
        clusters = self.cluster_failures(failures)
        
        patterns = []
        
        for sig, cluster in clusters.items():
            # Skip patterns with only 1 occurrence (likely outliers)
            if len(cluster) < 2:
                continue
            
            # Identify root cause
            root_cause, suggested_fix = self.identify_root_cause(cluster)
            
            # Extract affected agents
            affected_agents = list(set(f['agent_name'] for f in cluster))
            
            pattern = FailurePattern(
                pattern_id=sig,
                category=cluster[0]['category'],
                frequency=len(cluster),
                example_error=cluster[0]['error_message'],
                root_cause=root_cause,
                affected_agents=affected_agents,
                suggested_fix=suggested_fix
            )
            
            patterns.append(pattern)
        
        # Sort by frequency (most common first)
        patterns.sort(key=lambda p: p.frequency, reverse=True)
        
        return patterns
    
    def generate_report(self, patterns: List[FailurePattern]) -> str:
        """Generate a markdown report of identified patterns."""
        if not patterns:
            return "# Failure Analysis Report\n\nNo recurring patterns detected."
        
        report = "# Failure Analysis Report\n\n"
        report += f"**Total Patterns Identified**: {len(patterns)}\n\n"
        report += "---\n\n"
        
        for i, pattern in enumerate(patterns, 1):
            report += f"## Pattern {i}: {pattern.pattern_id.replace('_', ' ').title()}\n\n"
            report += f"**Frequency**: {pattern.frequency} occurrences\n\n"
            report += f"**Category**: {pattern.category}\n\n"
            report += f"**Affected Agents**: {', '.join(pattern.affected_agents)}\n\n"
            report += f"**Example Error**:\n```\n{pattern.example_error}\n```\n\n"
            report += f"**Root Cause**: {pattern.root_cause}\n\n"
            report += f"**Suggested Fix**: {pattern.suggested_fix}\n\n"
            report += "---\n\n"
        
        return report
    
    def save_patterns_to_reasoning_bank(self, patterns: List[FailurePattern]):
        """Save identified patterns to reasoning bank for learning."""
        # Load reasoning bank
        if self.reasoning_bank_file.exists():
            with open(self.reasoning_bank_file) as f:
                bank = json.load(f)
        else:
            bank = {"failures": [], "learnings": [], "patterns": []}
        
        # Add patterns
        for pattern in patterns:
            bank["patterns"].append({
                "pattern_id": pattern.pattern_id,
                "category": pattern.category,
                "frequency": pattern.frequency,
                "root_cause": pattern.root_cause,
                "suggested_fix": pattern.suggested_fix,
                "affected_agents": pattern.affected_agents
            })
        
        # Save
        with open(self.reasoning_bank_file, 'w') as f:
            json.dump(bank, f, indent=2)

# CLI interface
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze failure patterns")
    parser.add_argument('--analyze', action='store_true', help="Run pattern analysis")
    parser.add_argument('--output', type=str, default=".tmp/pattern_analysis_report.md", help="Output report file")
    
    args = parser.parse_args()
    
    if args.analyze:
        print("=" * 60)
        print("Pattern Analyzer")
        print("=" * 60)
        
        analyzer = PatternAnalyzer()
        patterns = analyzer.analyze_failures()
        
        print(f"Identified {len(patterns)} recurring patterns")
        
        # Generate report
        report = analyzer.generate_report(patterns)
        
        # Save report
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(report)
        
        print(f"Report saved to: {output_path}")
        
        # Save to reasoning bank
        analyzer.save_patterns_to_reasoning_bank(patterns)
        print("Patterns saved to reasoning bank")
        
        print("=" * 60)
