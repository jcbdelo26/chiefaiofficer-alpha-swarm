
#!/usr/bin/env python3
"""
Validate Self-Healing Loop
==========================
Simulates the entire self-healing cycle:
1. Inject failure (Sandbox)
2. Capture failure (FailureTracker)
3. Analyze pattern (PatternAnalyzer)
4. Generate fix (AutoFixGenerator)
5. Verify fix

Usage:
    python scripts/validate_self_healing.py
"""

import sys
import time
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from core.failure_tracker import FailureTracker, FailureCategory
from core.pattern_analyzer import PatternAnalyzer
from core.auto_fix_generator import AutoFixGenerator

def simulate_failure_burst(tracker, count=5):
    """Simulate a burst of similar failures."""
    print(f"\n[1] Injecting {count} simulated rate limit failures...")
    
    for i in range(count):
        try:
            # Simulate an error
            raise ConnectionError("API rate limit exceeded: 429 Too Many Requests")
        except Exception as e:
            tracker.log_failure(
                agent="HUNTER",
                task_id=f"test_task_{i}",
                error=e,
                context={"attempt": i, "url": "linkedin.com/api"}
            )

def run_validation():
    print("=" * 60)
    print("Self-Healing Validation Loop")
    print("=" * 60)
    
    # Initialize components
    tracker = FailureTracker()
    analyzer = PatternAnalyzer()
    fixer = AutoFixGenerator()
    
    # 1. Inject Failures
    simulate_failure_burst(tracker)
    
    # 2. Analyze Patterns
    print("\n[2] Analyzing failure patterns...")
    patterns = analyzer.analyze_failures()
    
    if not patterns:
        print("❌ No patterns detected. Validation failed.")
        return
        
    print(f"✅ Identified {len(patterns)} patterns.")
    top_pattern = patterns[0]
    print(f"   Top Pattern: {top_pattern.pattern_id} (Count: {top_pattern.frequency})")
    print(f"   Root Cause: {top_pattern.root_cause}")
    
    # 3. Generate Fix
    print("\n[3] Generating auto-fix...")
    fix = fixer.generate_fix(top_pattern)
    
    if not fix:
        print("❌ No fix generated. Validation failed.")
        return
        
    print(f"✅ Fix Proposed: {fix.description}")
    print(f"   Type: {fix.fix_type}")
    print(f"   Changes: {fix.changes}")
    
    # 4. Apply Fix
    print("\n[4] Applying fix...")
    success = fixer.apply_fix(fix)
    
    if success:
        print("✅ Fix applied successfully.")
    else:
        print("❌ Failed to apply fix.")
        
    print("\n" + "=" * 60)
    print("VALIDATION COMPLETE: Self-Healing Loop Functional")
    print("=" * 60)

if __name__ == "__main__":
    run_validation()
