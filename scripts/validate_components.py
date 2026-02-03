#!/usr/bin/env python3
"""
Component Validation Script
============================
Validates all core components of the chiefaiofficer-alpha-swarm.
"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    print("=" * 60)
    print("COMPONENT VALIDATION")
    print("=" * 60)
    
    results = {}
    
    # 1. Test GHL Execution Gateway
    print("\n[1] GHL Execution Gateway")
    try:
        from core.ghl_execution_gateway import GHLExecutionGateway
        from core.agent_permissions import get_permission_guard
        
        guard = get_permission_guard()
        guard.register_agent_by_role_name('test_ghl_master', 'GHL_MASTER')
        guard.register_agent_by_role_name('test_hunter', 'HUNTER')
        
        gateway = GHLExecutionGateway()
        print("    Gateway initialized: OK")
        print(f"    System operational: {gateway.orchestrator.is_operational()}")
        results['gateway'] = 'PASS'
    except Exception as e:
        print(f"    ERROR: {e}")
        results['gateway'] = 'FAIL'

    # 2. Test Circuit Breakers
    print("\n[2] Circuit Breakers")
    try:
        from core.circuit_breaker import get_registry
        registry = get_registry()
        status = registry.get_status()
        for name, s in status.items():
            state_icon = "OK" if s["state"] == "closed" else "OPEN"
            print(f"    [{state_icon}] {name}: {s['state']}")
        results['circuit_breakers'] = 'PASS'
    except Exception as e:
        print(f"    ERROR: {e}")
        results['circuit_breakers'] = 'FAIL'

    # 3. Test GHL Guardrails
    print("\n[3] GHL Guardrails (Email Limits)")
    try:
        from core.ghl_guardrails import GHLGuardrails
        guardrails = GHLGuardrails()
        status = guardrails.get_email_status()
        print(f"    Monthly: {status['monthly']['sent']}/{status['monthly']['limit']}")
        print(f"    Daily: {status['daily']['sent']}/{status['daily']['limit']}")
        print(f"    Hourly: {status['hourly']['sent']}/{status['hourly']['limit']}")
        results['guardrails'] = 'PASS'
    except Exception as e:
        print(f"    ERROR: {e}")
        results['guardrails'] = 'FAIL'

    # 4. Test Agent Permissions
    print("\n[4] Agent Permissions")
    try:
        from core.agent_permissions import get_permission_guard, Permission
        guard = get_permission_guard()
        
        # Test permission checks
        hunter_can_send = guard.check_permission('test_hunter', Permission.SEND_EMAIL)
        ghl_can_send = guard.check_permission('test_ghl_master', Permission.SEND_EMAIL)
        
        print(f"    HUNTER can send email: {hunter_can_send} (expected: False)")
        print(f"    GHL_MASTER can send email: {ghl_can_send} (expected: True)")
        
        if not hunter_can_send and ghl_can_send:
            results['permissions'] = 'PASS'
        else:
            results['permissions'] = 'FAIL'
    except Exception as e:
        print(f"    ERROR: {e}")
        results['permissions'] = 'FAIL'

    # 5. Test ICP Configuration
    print("\n[5] ICP Configuration")
    try:
        with open(".hive-mind/knowledge/customers/icp.json") as f:
            icp = json.load(f)
        tiers = icp.get("ideal_customer_profiles", {})
        for tier_key, tier_data in tiers.items():
            print(f"    {tier_key}: {tier_data.get('tier_name')} ({tier_data.get('priority')})")
        results['icp'] = 'PASS'
    except Exception as e:
        print(f"    ERROR: {e}")
        results['icp'] = 'FAIL'

    # 6. Test Messaging Templates
    print("\n[6] Messaging Templates")
    try:
        with open(".hive-mind/knowledge/messaging/templates.json") as f:
            templates = json.load(f)
        template_list = templates.get("email_templates", [])
        for t in template_list:
            print(f"    - {t.get('template_id')}: {t.get('name')}")
        results['templates'] = 'PASS'
    except Exception as e:
        print(f"    ERROR: {e}")
        results['templates'] = 'FAIL'

    # 7. Test Lead Data
    print("\n[7] Test Lead Data")
    try:
        with open(".hive-mind/testing/test-leads.json") as f:
            leads = json.load(f)
        lead_list = leads.get("test_leads", [])
        print(f"    Total test leads: {len(lead_list)}")
        for lead in lead_list:
            print(f"    - Tier {lead['tier']}: {lead['first_name']} {lead['last_name']} ({lead['title']})")
        results['test_leads'] = 'PASS'
    except Exception as e:
        print(f"    ERROR: {e}")
        results['test_leads'] = 'FAIL'

    # 8. Test Company Profile
    print("\n[8] Company Profile")
    try:
        with open(".hive-mind/knowledge/company/profile.json") as f:
            profile = json.load(f)
        print(f"    Company: {profile.get('company_name')}")
        print(f"    Tagline: {profile.get('tagline')}")
        results['company_profile'] = 'PASS'
    except Exception as e:
        print(f"    ERROR: {e}")
        results['company_profile'] = 'FAIL'

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v == 'PASS')
    total = len(results)
    
    for component, status in results.items():
        icon = "[PASS]" if status == 'PASS' else "[FAIL]"
        print(f"    {icon} {component}")
    
    print(f"\n    Total: {passed}/{total} components validated")
    print("=" * 60)
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
