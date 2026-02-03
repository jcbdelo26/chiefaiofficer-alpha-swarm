#!/usr/bin/env python3
"""
Trigger Regeneration of Pending Emails
======================================
This script initializes the WebsiteIntentMonitor and triggers the
regeneration of all pending emails in the dashboard queue using
the new MessagingStrategy templates.

Usage:
    python execution/trigger_regeneration.py
"""

import sys
import asyncio
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("trigger_regeneration")

async def main():
    try:
        from core.website_intent_monitor import get_website_monitor
        
        logger.info("🚀 Initializing Website Intent Monitor...")
        monitor = get_website_monitor()
        
        logger.info("🔄 Triggering regeneration of active queue...")
        monitor.regenerate_active_queue()
        
        logger.info("✅ Regeneration task completed successfully.")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"❌ Failed to trigger regeneration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
