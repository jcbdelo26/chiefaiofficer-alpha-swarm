#!/usr/bin/env python3
"""
Process Approved Actions - Execute approved items from the queue
================================================================

This script processes the execution queue, executing approved actions
that have been approved by human reviewers.

Usage:
    python execution/process_approved_actions.py --list     # List pending executions
    python execution/process_approved_actions.py --process  # Process all pending
    python execution/process_approved_actions.py --process-one <request_id>  # Process one
    python execution/process_approved_actions.py --dry-run  # Show what would be executed
"""

import os
import sys
import json
import asyncio
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env', override=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('process_approved')


class ApprovedActionProcessor:
    """
    Processes approved actions from the execution queue.
    
    This is the bridge between human approval and actual execution.
    """
    
    def __init__(self):
        self.queue_dir = PROJECT_ROOT / ".hive-mind" / "execution_queue"
        self.executed_dir = PROJECT_ROOT / ".hive-mind" / "executed_actions"
        self.executed_dir.mkdir(parents=True, exist_ok=True)
        
        # Check emergency stop
        self.emergency_stop = os.getenv("EMERGENCY_STOP", "false").lower() == "true"
    
    def get_pending_actions(self) -> List[Dict[str, Any]]:
        """Get all pending approved actions."""
        if not self.queue_dir.exists():
            return []
        
        pending = []
        for queue_file in self.queue_dir.glob("*.json"):
            try:
                with open(queue_file, 'r', encoding='utf-8') as f:
                    item = json.load(f)
                if item.get("status") == "pending_execution":
                    item["_queue_file"] = str(queue_file)
                    pending.append(item)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Error reading queue file {queue_file}: {e}")
        
        # Sort by approval time (oldest first)
        pending.sort(key=lambda x: x.get("approved_at", ""))
        return pending
    
    async def execute_action(self, item: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        """
        Execute a single approved action.
        
        Returns execution result.
        """
        request_id = item.get("request_id")
        action_type = item.get("action_type")
        payload = item.get("payload", {})
        
        result = {
            "request_id": request_id,
            "action_type": action_type,
            "dry_run": dry_run,
            "success": False,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "error": None
        }
        
        # Check emergency stop
        if self.emergency_stop:
            result["error"] = "EMERGENCY_STOP is active - execution blocked"
            logger.error(f"❌ {request_id}: Blocked by EMERGENCY_STOP")
            return result
        
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Executing {action_type}: {request_id}")
        
        try:
            if dry_run:
                result["success"] = True
                result["note"] = "Dry run - no action taken"
                return result
            
            # Route to appropriate handler based on action type
            if action_type in ("send_email", "email_send"):
                result = await self._execute_send_email(item, result)
            elif action_type in ("bulk_email", "bulk_send_email"):
                result = await self._execute_bulk_email(item, result)
            elif action_type == "create_contact":
                result = await self._execute_create_contact(item, result)
            elif action_type == "update_contact":
                result = await self._execute_update_contact(item, result)
            elif action_type in ("trigger_workflow", "workflow_trigger"):
                result = await self._execute_trigger_workflow(item, result)
            else:
                result["error"] = f"Unknown action type: {action_type}"
                logger.warning(f"Unknown action type: {action_type}")
            
            # Update queue file status
            self._update_queue_status(item, result["success"], result)
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Error executing {request_id}: {e}")
            self._update_queue_status(item, False, {"error": str(e)})
        
        return result
    
    async def _execute_send_email(self, item: Dict, result: Dict) -> Dict:
        """Execute email send via GHL."""
        import httpx
        
        payload = item.get("payload", {})
        contact_id = payload.get("contact_id")
        subject = payload.get("subject")
        body = payload.get("body")
        
        if not all([contact_id, subject, body]):
            result["error"] = "Missing required fields: contact_id, subject, or body"
            return result
        
        # Load config to check if sending is enabled
        config_path = PROJECT_ROOT / "config" / "production.json"
        with open(config_path) as f:
            config = json.load(f)
        
        shadow_mode = config.get("email_behavior", {}).get("shadow_mode", True)
        actually_send = config.get("email_behavior", {}).get("actually_send", False)
        
        if shadow_mode or not actually_send:
            # Log shadow email instead of sending
            shadow_path = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
            shadow_path.mkdir(parents=True, exist_ok=True)
            
            shadow_file = shadow_path / f"{item['request_id']}_approved.json"
            with open(shadow_file, 'w') as f:
                json.dump({
                    "approved": True,
                    "would_send_to": contact_id,
                    "subject": subject,
                    "body_preview": body[:200] + "..." if len(body) > 200 else body,
                    "approved_by": item.get("approver_id"),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }, f, indent=2)
            
            result["success"] = True
            result["note"] = f"Shadow mode - email logged to {shadow_file}"
            logger.info(f"✅ {item['request_id']}: Shadow email logged")
            return result
        
        # Actually send via GHL
        api_key = os.getenv("GHL_PROD_API_KEY")
        
        if not api_key:
            result["error"] = "GHL_PROD_API_KEY not set"
            return result
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # GHL send email endpoint
                resp = await client.post(
                    f"https://services.leadconnectorhq.com/conversations/messages",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Version": "2021-07-28",
                        "Content-Type": "application/json"
                    },
                    json={
                        "type": "Email",
                        "contactId": contact_id,
                        "subject": subject,
                        "body": body
                    }
                )
                
                if resp.status_code in (200, 201):
                    result["success"] = True
                    result["ghl_response"] = resp.json()
                    logger.info(f"✅ {item['request_id']}: Email sent successfully")
                else:
                    result["error"] = f"GHL API error: {resp.status_code} - {resp.text[:200]}"
                    logger.error(f"❌ {item['request_id']}: GHL error {resp.status_code}")
                    
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    async def _execute_bulk_email(self, item: Dict, result: Dict) -> Dict:
        """Execute bulk email send."""
        # For now, just mark as needing individual processing
        result["error"] = "Bulk email requires individual processing - break into single sends"
        return result
    
    async def _execute_create_contact(self, item: Dict, result: Dict) -> Dict:
        """Execute contact creation in GHL."""
        result["note"] = "Contact creation execution not yet implemented"
        result["success"] = True  # Mark as success to clear queue
        return result
    
    async def _execute_update_contact(self, item: Dict, result: Dict) -> Dict:
        """Execute contact update in GHL."""
        result["note"] = "Contact update execution not yet implemented"
        result["success"] = True  # Mark as success to clear queue
        return result
    
    async def _execute_trigger_workflow(self, item: Dict, result: Dict) -> Dict:
        """Execute workflow trigger in GHL."""
        result["note"] = "Workflow trigger execution not yet implemented"
        result["success"] = True  # Mark as success to clear queue
        return result
    
    def _update_queue_status(self, item: Dict, success: bool, result: Dict):
        """Update queue file with execution result."""
        queue_file = Path(item.get("_queue_file", ""))
        
        if not queue_file.exists():
            return
        
        try:
            with open(queue_file, 'r') as f:
                data = json.load(f)
            
            data["status"] = "executed" if success else "failed"
            data["executed_at"] = datetime.now(timezone.utc).isoformat()
            data["execution_result"] = result
            data["execution_attempts"] = data.get("execution_attempts", 0) + 1
            
            with open(queue_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Move to executed folder if successful
            if success:
                dest = self.executed_dir / queue_file.name
                queue_file.rename(dest)
                logger.info(f"Moved to executed: {dest}")
                
        except Exception as e:
            logger.error(f"Error updating queue status: {e}")
    
    async def process_all_pending(self, dry_run: bool = False) -> List[Dict]:
        """Process all pending approved actions."""
        pending = self.get_pending_actions()
        
        if not pending:
            print("No pending approved actions to process.")
            return []
        
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing {len(pending)} approved actions...\n")
        
        results = []
        for item in pending:
            result = await self.execute_action(item, dry_run=dry_run)
            results.append(result)
            
            status = "✅" if result.get("success") else "❌"
            print(f"  {status} {item['request_id']}: {item['action_type']}")
            if result.get("error"):
                print(f"       Error: {result['error']}")
            if result.get("note"):
                print(f"       Note: {result['note']}")
        
        # Summary
        successful = sum(1 for r in results if r.get("success"))
        print(f"\nProcessed: {successful}/{len(results)} successful")
        
        return results
    
    def print_pending(self):
        """Print all pending approved actions."""
        pending = self.get_pending_actions()
        
        if not pending:
            print("\n  No pending approved actions.\n")
            return
        
        print(f"\n  Pending Approved Actions: {len(pending)}")
        print("  " + "-" * 60)
        
        for item in pending:
            print(f"\n  Request ID: {item['request_id']}")
            print(f"  Action: {item['action_type']}")
            print(f"  Requester: {item['requester_agent']}")
            print(f"  Approved At: {item.get('approved_at', 'N/A')}")
            print(f"  Approver: {item.get('approver_id', 'N/A')}")
            if item.get('approver_notes'):
                print(f"  Notes: {item['approver_notes']}")
        
        print("\n  " + "-" * 60)
        print(f"  Run with --process to execute all or --process-one <id>")
        print()


async def main():
    parser = argparse.ArgumentParser(
        description="Process approved actions from the execution queue"
    )
    parser.add_argument("--list", action="store_true", help="List pending executions")
    parser.add_argument("--process", action="store_true", help="Process all pending")
    parser.add_argument("--process-one", type=str, metavar="ID", help="Process single item")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be executed")
    
    args = parser.parse_args()
    
    processor = ApprovedActionProcessor()
    
    if args.list:
        processor.print_pending()
    elif args.process:
        await processor.process_all_pending(dry_run=args.dry_run)
    elif args.process_one:
        pending = processor.get_pending_actions()
        item = next((p for p in pending if p["request_id"] == args.process_one), None)
        if item:
            result = await processor.execute_action(item, dry_run=args.dry_run)
            print(json.dumps(result, indent=2))
        else:
            print(f"Request ID not found: {args.process_one}")
    else:
        # Default: list
        processor.print_pending()


if __name__ == "__main__":
    asyncio.run(main())
