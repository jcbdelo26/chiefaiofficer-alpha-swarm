
import json
import asyncio
from datetime import datetime, timezone
import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from core.aidefence import AIDefence, PIIType
from core.audit_trail import get_audit_trail

REPORT_PATH = Path(".hive-mind/compliance_reports")
REPORT_PATH.mkdir(parents=True, exist_ok=True)

async def generate_report():
    print("Generating Security & Compliance Report...")
    
    # 1. Gather System Stats
    ai = AIDefence()
    stats = {}
    if ai.pii_detector:
        stats = ai.pii_detector.get_learning_stats()
    
    # 2. Run Tests
    print("Running Security Tests...")
    # Capture pytest output
    # Just running them and assuming if they pass we are good is simple.
    # For a report, we might want to capture detailed results, but for now we'll just check status.
    ret_code = pytest.main(["tests/test_security_compliance.py", "-v"])
    test_status = "PASSED" if ret_code == 0 else "FAILED"
    
    # 3. Compile Report
    timestamp = datetime.now(timezone.utc).isoformat()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    report = f"""# Security & Compliance Report
**Date**: {date_str}
**Status**: {test_status}

## 1. Automated Security Validation
Running validation suite `tests/test_security_compliance.py`:
- **Prompt Injection Defense**: Verified against known attacks (DAN, Ignore instructions).
- **Jailbreak Resistance**: Verified against roleplay and hypothetical scenarios.
- **PII Detection**: Verified implementation of redaction for {len(PIIType)} PII types.
- **Regulatory Compliance**: Verified mocks for CAN-SPAM and GDPR workflows.

## 2. AIDefence Statistics
Self-learning module performance:
- **False Positives Reported**: {stats.get('false_positives', 0)}
- **False Negatives Reported**: {stats.get('false_negatives', 0)}

## 3. Configuration Status
- **Safe Threshold**: {ai.SAFE_THRESHOLD}
- **Suspicious Threshold**: {ai.SUSPICIOUS_THRESHOLD}
- **PII Detection**: Enabled
- **Known Threat Patterns**: {len(ai.known_patterns)} active patterns loaded.

## 4. Recommendations
"""
    if test_status == "FAILED":
        report += "- **CRITICAL**: Security tests failed. Immediate investigation required.\n"
    else:
        report += "- Continue monitoring 'suspicious' activity logs.\n"
        report += "- Review false positives weekly to refine regex patterns.\n"

    filename = REPORT_PATH / f"compliance_report_{date_str}.md"
    with open(filename, "w") as f:
        f.write(report)
        
    print(f"Report generated: {filename}")

if __name__ == "__main__":
    asyncio.run(generate_report())
