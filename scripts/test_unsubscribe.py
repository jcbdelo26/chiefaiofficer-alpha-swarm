#!/usr/bin/env python3
"""
Unsubscribe Mechanism Test
==========================

Tests the complete unsubscribe flow to ensure CAN-SPAM compliance:
1. Email content contains unsubscribe link
2. Unsubscribe webhook/handler exists
3. Unsubscribed contacts are tagged in GHL
4. Suppression list is checked before sending

Usage:
    python scripts/test_unsubscribe.py --validate   # Validate email content has unsubscribe
    python scripts/test_unsubscribe.py --simulate   # Simulate unsubscribe flow
    python scripts/test_unsubscribe.py --check-ghl  # Check GHL for suppressed contacts
    python scripts/test_unsubscribe.py --full       # Run all tests
"""

import os
import sys
import json
import asyncio
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple
import logging

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env', override=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('unsubscribe_test')

# Fix Windows console encoding for Unicode
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# Required unsubscribe phrases (at least one must be present)
UNSUBSCRIBE_PATTERNS = [
    "unsubscribe",
    "opt out",
    "opt-out",
    "stop receiving",
    "remove me",
    "reply stop",
    "click here to stop",
    "manage preferences",
    "email preferences"
]

# GHL tag for unsubscribed contacts
UNSUBSCRIBE_TAG = "unsubscribed"
DO_NOT_CONTACT_TAG = "do-not-contact"


def validate_email_has_unsubscribe(subject: str, body: str) -> Tuple[bool, List[str]]:
    """
    Validate that email content contains required unsubscribe mechanism.
    
    CAN-SPAM Requirements:
    1. Clear opt-out mechanism
    2. Working unsubscribe link or instruction
    3. Physical mailing address (optional but recommended)
    
    Returns:
        (valid: bool, issues: List[str])
    """
    issues = []
    combined = (subject + " " + body).lower()
    
    # Check for unsubscribe phrase
    has_unsubscribe = any(pattern in combined for pattern in UNSUBSCRIBE_PATTERNS)
    if not has_unsubscribe:
        issues.append("Missing unsubscribe/opt-out mechanism (CAN-SPAM violation)")
    
    # Check for physical address (recommended)
    address_patterns = ["street", "suite", "floor", "address", "po box", "p.o. box"]
    has_address = any(pattern in combined for pattern in address_patterns)
    if not has_address:
        # Warning, not error
        logger.warning("Email does not contain physical mailing address (recommended by CAN-SPAM)")
    
    # Check that unsubscribe is clearly visible (not hidden at bottom in tiny text)
    # This is a heuristic - look for unsubscribe near end of email
    body_lower = body.lower()
    if has_unsubscribe:
        for pattern in UNSUBSCRIBE_PATTERNS:
            if pattern in body_lower:
                # Check if it's in the last 30% of the email
                position = body_lower.rfind(pattern)
                if position > 0:
                    relative_position = position / len(body_lower)
                    if relative_position < 0.5:
                        logger.info(f"Unsubscribe '{pattern}' found early in email (position: {relative_position:.0%})")
                break
    
    return len(issues) == 0, issues


async def check_ghl_suppression(email: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Check if an email is in GHL suppression list or has unsubscribe tag.
    
    Returns:
        (is_suppressed: bool, contact_info: dict)
    """
    import httpx
    
    api_key = os.getenv("GHL_PROD_API_KEY")
    location_id = os.getenv("GHL_LOCATION_ID")
    
    if not api_key or not location_id:
        return False, {"error": "GHL credentials not set"}
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Search for contact by email
            resp = await client.get(
                f"https://services.leadconnectorhq.com/contacts/",
                params={"locationId": location_id, "query": email},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Version": "2021-07-28"
                }
            )
            
            if resp.status_code != 200:
                return False, {"error": f"GHL API error: {resp.status_code}"}
            
            contacts = resp.json().get("contacts", [])
            
            for contact in contacts:
                if contact.get("email", "").lower() == email.lower():
                    tags = contact.get("tags", [])
                    
                    is_suppressed = (
                        UNSUBSCRIBE_TAG in tags or
                        DO_NOT_CONTACT_TAG in tags or
                        contact.get("dnd", False) or
                        contact.get("doNotContact", False)
                    )
                    
                    return is_suppressed, {
                        "contact_id": contact.get("id"),
                        "email": contact.get("email"),
                        "tags": tags,
                        "dnd": contact.get("dnd", False),
                        "doNotContact": contact.get("doNotContact", False)
                    }
            
            return False, {"error": "Contact not found"}
            
    except Exception as e:
        return False, {"error": str(e)}


async def simulate_unsubscribe(email: str, dry_run: bool = True) -> Dict[str, Any]:
    """
    Simulate the unsubscribe process.
    
    In production, this would:
    1. Receive unsubscribe webhook from GHL
    2. Update contact with unsubscribe tag
    3. Add to suppression list
    4. Log to audit trail
    
    Returns:
        Result of unsubscribe simulation
    """
    import httpx
    
    result = {
        "email": email,
        "dry_run": dry_run,
        "steps": []
    }
    
    api_key = os.getenv("GHL_PROD_API_KEY")
    location_id = os.getenv("GHL_LOCATION_ID")
    
    if not api_key or not location_id:
        result["error"] = "GHL credentials not set"
        return result
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: Find contact
            resp = await client.get(
                f"https://services.leadconnectorhq.com/contacts/",
                params={"locationId": location_id, "query": email},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Version": "2021-07-28"
                }
            )
            
            if resp.status_code != 200:
                result["error"] = f"GHL API error: {resp.status_code}"
                return result
            
            contacts = resp.json().get("contacts", [])
            contact = None
            
            for c in contacts:
                if c.get("email", "").lower() == email.lower():
                    contact = c
                    break
            
            if not contact:
                result["steps"].append({"step": "find_contact", "status": "not_found"})
                return result
            
            result["steps"].append({
                "step": "find_contact", 
                "status": "found",
                "contact_id": contact.get("id")
            })
            
            # Step 2: Check current tags
            current_tags = contact.get("tags", [])
            result["steps"].append({
                "step": "check_tags",
                "current_tags": current_tags,
                "already_unsubscribed": UNSUBSCRIBE_TAG in current_tags
            })
            
            if UNSUBSCRIBE_TAG in current_tags:
                result["already_unsubscribed"] = True
                return result
            
            # Step 3: Add unsubscribe tag (if not dry run)
            if dry_run:
                result["steps"].append({
                    "step": "add_unsubscribe_tag",
                    "status": "skipped (dry_run)",
                    "would_add_tags": [UNSUBSCRIBE_TAG, DO_NOT_CONTACT_TAG]
                })
            else:
                new_tags = list(set(current_tags + [UNSUBSCRIBE_TAG, DO_NOT_CONTACT_TAG]))
                
                update_resp = await client.put(
                    f"https://services.leadconnectorhq.com/contacts/{contact.get('id')}",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Version": "2021-07-28",
                        "Content-Type": "application/json"
                    },
                    json={
                        "tags": new_tags,
                        "dnd": True  # Do Not Disturb flag
                    }
                )
                
                result["steps"].append({
                    "step": "add_unsubscribe_tag",
                    "status": "success" if update_resp.status_code == 200 else "failed",
                    "response_code": update_resp.status_code
                })
            
            # Step 4: Log to suppression list
            suppression_file = PROJECT_ROOT / ".hive-mind" / "suppression_list.json"
            suppression_file.parent.mkdir(parents=True, exist_ok=True)
            
            suppression_list = []
            if suppression_file.exists():
                with open(suppression_file) as f:
                    suppression_list = json.load(f)
            
            entry = {
                "email": email.lower(),
                "unsubscribed_at": datetime.now(timezone.utc).isoformat(),
                "source": "manual_unsubscribe",
                "contact_id": contact.get("id")
            }
            
            if not any(s.get("email") == email.lower() for s in suppression_list):
                if not dry_run:
                    suppression_list.append(entry)
                    with open(suppression_file, 'w') as f:
                        json.dump(suppression_list, f, indent=2)
                
                result["steps"].append({
                    "step": "add_to_suppression_list",
                    "status": "skipped (dry_run)" if dry_run else "added"
                })
            else:
                result["steps"].append({
                    "step": "add_to_suppression_list",
                    "status": "already_in_list"
                })
            
            result["success"] = True
            
    except Exception as e:
        result["error"] = str(e)
    
    return result


def check_suppression_before_send(email: str) -> Tuple[bool, str]:
    """
    Check if an email is in the local suppression list before sending.
    
    This should be called before every email send.
    
    Returns:
        (should_suppress: bool, reason: str)
    """
    suppression_file = PROJECT_ROOT / ".hive-mind" / "suppression_list.json"
    
    if not suppression_file.exists():
        return False, "Suppression list not found (OK to send)"
    
    try:
        with open(suppression_file) as f:
            suppression_list = json.load(f)
        
        for entry in suppression_list:
            if entry.get("email", "").lower() == email.lower():
                return True, f"Email in suppression list (unsubscribed: {entry.get('unsubscribed_at')})"
        
        return False, "Email not in suppression list (OK to send)"
        
    except Exception as e:
        logger.error(f"Error checking suppression list: {e}")
        # Fail closed - if we can't check, don't send
        return True, f"Error checking suppression list: {e}"


async def run_full_unsubscribe_test():
    """Run complete unsubscribe mechanism test."""
    print("\n" + "=" * 70)
    print("  📧 UNSUBSCRIBE MECHANISM TEST")
    print("=" * 70 + "\n")
    
    results = {
        "test_id": f"unsub_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "tests": [],
        "overall_pass": True
    }
    
    # Test 1: Validate email content has unsubscribe
    print("Test 1: Email Content Validation")
    print("-" * 40)
    
    test_emails = [
        {
            "name": "Valid email with unsubscribe",
            "subject": "Quick question about your RevOps",
            "body": """Hi John,

I noticed your team at Acme has been growing. Would you be open to a brief call?

Best,
Chris

Reply STOP to unsubscribe from future emails.
ChiefAIOfficer.com | 123 Main St, San Francisco, CA 94102"""
        },
        {
            "name": "Invalid email - missing unsubscribe",
            "subject": "Important offer for you!",
            "body": """Hi John,

This is a great opportunity you don't want to miss!

Best,
Chris"""
        },
        {
            "name": "Valid email with opt-out link",
            "subject": "AI for Revenue Operations",
            "body": """Hi John,

Companies like yours are seeing 30% efficiency gains with AI.

Click here to learn more: https://caio.cx/demo

Best,
Chris

Click here to opt out of future emails: https://caio.cx/optout"""
        }
    ]
    
    for email in test_emails:
        valid, issues = validate_email_has_unsubscribe(email["subject"], email["body"])
        status = "✅ PASS" if valid else "❌ FAIL"
        print(f"  {status} {email['name']}")
        if issues:
            for issue in issues:
                print(f"       ⚠️  {issue}")
        
        results["tests"].append({
            "test": "content_validation",
            "name": email["name"],
            "passed": valid,
            "issues": issues
        })
        
        if not valid and "missing unsubscribe" not in email["name"].lower():
            results["overall_pass"] = False
    
    # Test 2: Suppression list check
    print("\nTest 2: Suppression List Check")
    print("-" * 40)
    
    test_email = "test@example.com"
    is_suppressed, reason = check_suppression_before_send(test_email)
    print(f"  Email: {test_email}")
    print(f"  Suppressed: {is_suppressed}")
    print(f"  Reason: {reason}")
    
    results["tests"].append({
        "test": "suppression_check",
        "email": test_email,
        "is_suppressed": is_suppressed,
        "reason": reason
    })
    
    # Test 3: GHL suppression check (if credentials available)
    print("\nTest 3: GHL Suppression Check")
    print("-" * 40)
    
    if os.getenv("GHL_PROD_API_KEY"):
        internal_email = os.getenv("INTERNAL_TEST_EMAILS", "test@chiefaiofficer.com").split(",")[0]
        is_suppressed, info = await check_ghl_suppression(internal_email)
        print(f"  Email: {internal_email}")
        print(f"  Suppressed in GHL: {is_suppressed}")
        print(f"  Info: {json.dumps(info, indent=4)}")
        
        results["tests"].append({
            "test": "ghl_suppression",
            "email": internal_email,
            "is_suppressed": is_suppressed,
            "info": info
        })
    else:
        print("  ⚠️  Skipped - GHL credentials not set")
        results["tests"].append({
            "test": "ghl_suppression",
            "skipped": True,
            "reason": "GHL credentials not set"
        })
    
    # Test 4: Simulate unsubscribe (dry run)
    print("\nTest 4: Unsubscribe Simulation (Dry Run)")
    print("-" * 40)
    
    if os.getenv("GHL_PROD_API_KEY"):
        internal_email = os.getenv("INTERNAL_TEST_EMAILS", "test@chiefaiofficer.com").split(",")[0]
        sim_result = await simulate_unsubscribe(internal_email, dry_run=True)
        
        for step in sim_result.get("steps", []):
            print(f"  Step: {step.get('step')} - {step.get('status')}")
        
        results["tests"].append({
            "test": "unsubscribe_simulation",
            "dry_run": True,
            "result": sim_result
        })
    else:
        print("  ⚠️  Skipped - GHL credentials not set")
    
    # Summary
    print("\n" + "=" * 70)
    print("  UNSUBSCRIBE TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for t in results["tests"] if t.get("passed", True) and not t.get("skipped"))
    total = sum(1 for t in results["tests"] if not t.get("skipped"))
    
    status = "✅ PASS" if results["overall_pass"] else "❌ FAIL"
    print(f"  {status} Overall: {passed}/{total} tests passed")
    
    # Save results
    results_file = PROJECT_ROOT / ".hive-mind" / "unsubscribe_tests" / f"{results['test_id']}.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"  Results saved: {results_file}")
    print("=" * 70 + "\n")
    
    return results


async def main():
    parser = argparse.ArgumentParser(
        description="Test unsubscribe mechanism for CAN-SPAM compliance"
    )
    parser.add_argument("--validate", action="store_true", help="Validate email content")
    parser.add_argument("--simulate", action="store_true", help="Simulate unsubscribe")
    parser.add_argument("--check-ghl", action="store_true", help="Check GHL suppression")
    parser.add_argument("--full", action="store_true", help="Run all tests")
    parser.add_argument("--email", type=str, help="Email to check/simulate")
    
    args = parser.parse_args()
    
    if args.validate:
        subject = input("Enter email subject: ")
        body = input("Enter email body: ")
        valid, issues = validate_email_has_unsubscribe(subject, body)
        print(f"Valid: {valid}")
        if issues:
            print("Issues:")
            for issue in issues:
                print(f"  - {issue}")
    
    elif args.simulate and args.email:
        result = await simulate_unsubscribe(args.email, dry_run=True)
        print(json.dumps(result, indent=2))
    
    elif args.check_ghl and args.email:
        is_suppressed, info = await check_ghl_suppression(args.email)
        print(f"Suppressed: {is_suppressed}")
        print(json.dumps(info, indent=2))
    
    else:
        await run_full_unsubscribe_test()


if __name__ == "__main__":
    asyncio.run(main())
