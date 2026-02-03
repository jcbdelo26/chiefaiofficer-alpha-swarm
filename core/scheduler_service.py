
import time
import logging
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import the logic from existing scripts
from core.approval_notifier import main as check_approval_queue
from core.nurture_engine import process_nurture_queue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [SCHEDULER] - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

NOTIFICATION_INTERVAL = 10800  # 3 hours
NURTURE_INTERVAL = 3600  # 1 hour
EMAIL_QUEUE_INTERVAL = 3600  # 1 hour (runs frequently to clear queue)

# Import queue processor
from execution.process_email_queue import process_queue

def run_scheduler():
    logger.info("🚀 Unified Scheduler Service Started")
    logger.info(f"Notifications: Every {NOTIFICATION_INTERVAL/3600} hours")
    logger.info(f"Nurture Queue: Every {NURTURE_INTERVAL/3600} hour(s)")
    logger.info(f"Email Queue: Every {EMAIL_QUEUE_INTERVAL/60} minutes")
    
    last_notification = 0
    last_nurture = 0
    last_email_queue = 0
    
    while True:
        current_time = time.time()
        
        # Check if it's time for notification check
        if current_time - last_notification >= NOTIFICATION_INTERVAL:
            try:
                logger.info("📬 Running notification check...")
                check_approval_queue()
                last_notification = current_time
                logger.info("Notification check complete.")
            except Exception as e:
                logger.error(f"❌ Notification error: {e}")
        
        # Check if it's time for nurture queue processing
        if current_time - last_nurture >= NURTURE_INTERVAL:
            try:
                logger.info("🌱 Processing nurture queue...")
                process_nurture_queue()
                last_nurture = current_time
                logger.info(f"Nurture queue complete. Processed {len(processed)} items.")
            except Exception as e:
                logger.error(f"❌ Nurture queue error: {e}")

        # Check if it's time for email queue processing
        if current_time - last_email_queue >= EMAIL_QUEUE_INTERVAL:
             try:
                 logger.info("📨 Processing email queue...")
                 # Run async function in sync wrapper if needed, or just use asyncio.run
                 import asyncio
                 asyncio.run(process_queue())
                 last_email_queue = current_time
                 logger.info("Email queue processing complete.")
             except Exception as e:
                 logger.error(f"❌ Email queue error: {e}")
        
        # Sleep for a shorter interval to check conditions
        time.sleep(300)  # Check every 5 minutes

if __name__ == "__main__":
    run_scheduler()
