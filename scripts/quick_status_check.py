"""
Quick Production Status Check
==============================
Simplified validation without full Agent Manager dependency
"""

import json
from pathlib import Path
from datetime import datetime

def check_production_status():
    """Quick production status check"""
    
    print("\n" + "="*60)
    print("🎯 QUICK PRODUCTION STATUS CHECK")
    print("="*60 + "\n")
    
    base_dir = Path(__file__).parent.parent
    hive_mind = base_dir / ".hive-mind"
    
    checks = []
    
    # 1. Check API connections
    connection_file = hive_mind / "connection_test.json"
    if connection_file.exists():
        with open(connection_file, 'r') as f:
            conn_data = json.load(f)
        
        all_pass = conn_data.get("all_required_pass", False)
        required = conn_data.get("required_services", {})
        
        if all_pass:
            checks.append(("✅", "API Connections", f"All {len(required)} services connected"))
        else:
            failed = [k for k, v in required.items() if v.get("status") != "pass"]
            checks.append(("❌", "API Connections", f"{len(failed)} services failed: {', '.join(failed)}"))
    else:
        checks.append(("⚠️", "API Connections", "Not tested - Run: python execution/test_connections.py"))
    
    # 2. Check framework components
    framework_components = [
        ("core/context_manager.py", "Context Manager"),
        ("core/grounding_chain.py", "Grounding Chain"),
        ("core/feedback_collector.py", "Feedback Collector")
    ]
    
    missing = []
    for file_path, name in framework_components:
        if not (base_dir / file_path).exists():
            missing.append(name)
    
    if not missing:
        checks.append(("✅", "Framework Integration", "All 3 components present"))
    elif len(missing) == 3:
        checks.append(("❌", "Framework Integration", "Not started - See: .hive-mind/WEEK_1_DAY_3-4_FRAMEWORK.md"))
    else:
        checks.append(("⚠️", "Framework Integration", f"{len(missing)} missing: {', '.join(missing)}"))
    
    # 3. Check workflows
    workflows_dir = base_dir / ".agent" / "workflows"
    if workflows_dir.exists():
        workflow_files = list(workflows_dir.glob("*.md"))
        if len(workflow_files) >= 3:
            checks.append(("✅", "Workflows", f"{len(workflow_files)} workflows defined"))
        else:
            checks.append(("⚠️", "Workflows", f"Only {len(workflow_files)} workflows (expected ≥3)"))
    else:
        checks.append(("⚠️", "Workflows", "No workflows directory"))
    
    # 4. Check data directories
    required_dirs = ["scraped", "enriched", "campaigns", "knowledge"]
    missing_dirs = [d for d in required_dirs if not (hive_mind / d).exists()]
    
    if not missing_dirs:
        checks.append(("✅", "Data Directories", "All directories present"))
    else:
        checks.append(("⚠️", "Data Directories", f"{len(missing_dirs)} missing: {', '.join(missing_dirs)}"))
    
    # 5. Check .env file
    env_file = base_dir / ".env"
    gitignore = base_dir / ".gitignore"
    
    if env_file.exists():
        if gitignore.exists():
            with open(gitignore, 'r') as f:
                if ".env" in f.read():
                    checks.append(("✅", "Security", ".env file secured"))
                else:
                    checks.append(("⚠️", "Security", ".env not in .gitignore"))
        else:
            checks.append(("⚠️", "Security", "No .gitignore file"))
    else:
        checks.append(("❌", "Security", "No .env file"))
    
    # 6. Check monitoring
    monitoring_files = [
        "execution/health_monitor.py",
        "dashboard/kpi_dashboard.py"
    ]
    
    missing_monitoring = [f for f in monitoring_files if not (base_dir / f).exists()]
    
    if not missing_monitoring:
        checks.append(("✅", "Monitoring", "Infrastructure in place"))
    else:
        checks.append(("⚠️", "Monitoring", f"{len(missing_monitoring)} components missing"))
    
    # Print results
    for icon, check_name, message in checks:
        print(f"{icon} {check_name:25} {message}")
    
    # Calculate score
    passed = sum(1 for icon, _, _ in checks if icon == "✅")
    total = len(checks)
    score = (passed / total * 100) if total > 0 else 0
    
    print("\n" + "="*60)
    print(f"📊 READINESS SCORE: {score:.1f}%")
    print(f"   Passed: {passed}/{total}")
    print("="*60 + "\n")
    
    # Recommendations
    print("📋 NEXT STEPS:\n")
    
    for icon, check_name, message in checks:
        if icon in ["❌", "⚠️"]:
            print(f"  • {check_name}: {message}")
    
    print("\n" + "="*60)
    print("📚 DOCUMENTATION:")
    print("  • Full Guide: .hive-mind/AGENT_MANAGER_PRODUCTION_SUPPORT.md")
    print("  • Quick Ref: .hive-mind/AGENT_MANAGER_COMMANDS_QUICK_REF.md")
    print("  • Week 1 Guide: .hive-mind/WEEK_1_IMPLEMENTATION_GUIDE.md")
    print("="*60 + "\n")
    
    return score

if __name__ == "__main__":
    check_production_status()
