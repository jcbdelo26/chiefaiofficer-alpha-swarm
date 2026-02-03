#!/usr/bin/env python3
"""
Email Queue Processor
=====================
Runs periodically to process emails that were approved but queued due to rate limits.
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from core.ghl_outreach import GHLOutreachClient, OutreachConfig, EmailTemplate, OutreachType

async def process_queue():
    """Found approved but unsent emails and try to send them."""
    print(f"[{datetime.now()}] Starting Email Queue Processor...")
    
    # 1. Load Config
    config_path = PROJECT_ROOT / "config" / "production.json"
    project_config = {}
    if config_path.exists():
        with open(config_path) as f:
            project_config = json.load(f)
    
    email_limits = project_config.get("guardrails", {}).get("email_limits", {})
    outreach_config = OutreachConfig(
        monthly_limit=email_limits.get("monthly_limit", 3000),
        daily_limit=email_limits.get("daily_limit", 30),
        min_delay_seconds=email_limits.get("min_delay_seconds", 60)
    )
    
    # Check if sending is enabled
    if not project_config.get("email_behavior", {}).get("actually_send", False):
        print("Sending disabled in config. Exiting.")
        return

    # 2. Initialize Client
    api_key = os.getenv("GHL_PROD_API_KEY") or os.getenv("GHL_API_KEY")
    location_id = os.getenv("GHL_LOCATION_ID")
    
    if not api_key or not location_id:
        print("GHL credentials missing. Exiting.")
        return
        
    client = GHLOutreachClient(api_key, location_id, config=outreach_config)
    
    # 3. Find Queued Emails
    shadow_log = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
    queued_emails = []
    
    if shadow_log.exists():
        # Sort by timestamp to send oldest first
        files = sorted(shadow_log.glob("*.json"), key=os.path.getmtime)
        for f in files:
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    # Criteria: Approved AND (queued flag OR (not sent AND not rejected))
                    if data.get("status") == "approved":
                        if data.get("queued_for_send") or (not data.get("sent_via_ghl") and not data.get("send_error")):
                            queued_emails.append((f, data))
            except Exception:
                pass
    
    print(f"Found {len(queued_emails)} emails in queue.")
    
    # 4. Process Queue
    sent_count = 0
    error_count = 0
    limit_hit = False
    
    for email_file, data in queued_emails:
        if limit_hit:
            break
            
        print(f"Attempting to send: {data.get('subject')} to {data.get('to')}")
        
        # Check limits first
        can_send, reason = client.can_send(1)
        if not can_send:
            print(f"Limit reached: {reason}. Stopping.")
            limit_hit = True
            break
            
        try:
            # Construct temp template
            temp_template = EmailTemplate(
                id=f"queued_{data.get('email_id')}",
                name="Queued Dashboard Email",
                subject=data.get("subject", ""),
                body=data.get("body", ""),
                type=OutreachType.WARM
            )
            
            contact_id = data.get("contact_id")
            if not contact_id:
                print("Missing contact_id, skipping.")
                error_count += 1
                continue
                
            result = await client.send_email(contact_id, temp_template)
            
            if result.get("success"):
                data["sent_via_ghl"] = True
                data["ghl_message_id"] = result.get("message_id")
                data["queued_for_send"] = False
                data["sent_at"] = datetime.now().isoformat()
                if "send_error" in data:
                    del data["send_error"]
                
                # Save update
                with open(email_file, "w") as fp:
                    json.dump(data, fp, indent=2)
                
                print(f"SENT successfully: {result.get('message_id')}")
                sent_count += 1
                
                # Sleep to be safe (min interval)
                await asyncio.sleep(2) 
            else:
                error = result.get("error")
                print(f"Failed: {error}")
                if "limit reached" in str(error):
                    limit_hit = True
                    break
                else:
                    error_count += 1
                    
        except Exception as e:
            print(f"Exception processing email: {e}")
            error_count += 1
            
    await client.close()
    print(f"Queue processing complete. Sent: {sent_count}, Errors: {error_count}, Limit Hit: {limit_hit}")

if __name__ == "__main__":
    asyncio.run(process_queue())
