
import os
import sys
import json
import logging
from datetime import datetime
from typing import List, Dict, Literal
import pytz
import requests
from pathlib import Path
from dotenv import load_dotenv

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

# Configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = "C0ABLF59154"  # Dani's Approval Channel
SHADOW_LOG_DIR = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
EST_TIMEZONE = pytz.timezone('US/Eastern')
START_HOUR = 12
END_HOUR = 23

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Priority Classification
Priority = Literal["hot", "warm", "low"]

def classify_priority(email_data: Dict) -> Priority:
    """
    Classify email priority based on tier and company size.
    
    Rules:
    - HOT: Tier 1 + Company size > 50 employees
    - WARM: Tier 2 OR Tier 1 with smaller company
    - LOW: Tier 3 (can be auto-approved)
    """
    tier = email_data.get("tier", "tier_3").lower()
    recipient_data = email_data.get("recipient_data", {})
    
    # Try to parse employee count
    employees_raw = recipient_data.get("employees", "0")
    try:
        if isinstance(employees_raw, str):
            # Handle ranges like "51-200"
            employees_raw = employees_raw.split("-")[0].replace(",", "").strip()
        employees = int(employees_raw) if employees_raw else 0
    except (ValueError, TypeError):
        employees = 0
    
    # Classification logic
    if tier == "tier_1" and employees >= 50:
        return "hot"
    elif tier in ["tier_1", "tier_2"]:
        return "warm"
    else:
        return "low"

def get_pending_details() -> List[Dict]:
    """Return a list of dicts with basic info on pending emails, including priority."""
    if not SHADOW_LOG_DIR.exists():
        return []
    
    pending_items = []
    for f in SHADOW_LOG_DIR.glob("*.json"):
        try:
            with open(f, 'r') as fp:
                data = json.load(fp)
                if data.get("status") in ["approved", "rejected"]:
                    continue
                
                # Extract key "at a glance" info
                company = data.get("recipient_data", {}).get("company") or "Unknown Corp"
                tier = data.get("tier", "tier_3")
                tier_display = tier.replace("_", " ").title()
                subject = data.get("subject", "No Subject")
                employees = data.get("recipient_data", {}).get("employees", "N/A")
                
                # Classify priority
                priority = classify_priority(data)
                
                pending_items.append({
                    "email_id": f.stem,
                    "company": company,
                    "tier": tier,
                    "tier_display": tier_display,
                    "subject": subject,
                    "employees": employees,
                    "priority": priority,
                    "filepath": str(f)
                })
        except Exception as e:
            logger.warning(f"Error reading {f}: {e}")
            continue
    
    return pending_items

def send_hot_alert(hot_items: List[Dict]):
    """Send immediate Slack alert for HOT priority leads."""
    if not SLACK_BOT_TOKEN or not hot_items:
        return
    
    token = os.getenv("DASHBOARD_AUTH_TOKEN", "REDACTED_TOKEN")
    dashboard_url = f"https://caio-swarm-dashboard-production.up.railway.app/sales?token={token}"
    count = len(hot_items)
    
    # Build urgent message
    preview_text = ""
    for item in hot_items[:5]:
        preview_text += f"• 🔴 *{item['company']}* ({item['employees']} employees) — {item['subject'][:35]}...\n"
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 {count} HOT LEAD{'S' if count > 1 else ''} — Immediate Review Required",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"High-value targets identified. These are Tier 1 leads at companies with 50+ employees.\n\n{preview_text}"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔥 Review Now", "emoji": True},
                    "url": dashboard_url,
                    "style": "danger"
                }
            ]
        }
    ]
    
    _send_to_slack(blocks, f"🚨 {count} HOT LEADS need immediate review")

def send_batch_alert(warm_items: List[Dict], low_items: List[Dict]):
    """Send batch notification for WARM and LOW priority leads."""
    if not SLACK_BOT_TOKEN:
        return
    
    token = os.getenv("DASHBOARD_AUTH_TOKEN", "REDACTED_TOKEN")
    dashboard_url = f"https://caio-swarm-dashboard-production.up.railway.app/sales?token={token}"
    warm_count = len(warm_items)
    low_count = len(low_items)
    total = warm_count + low_count
    
    if total == 0:
        return
    
    # Build summary
    warm_text = ""
    for item in warm_items[:3]:
        warm_text += f"• 🟡 *{item['company']}* ({item['tier_display']}): {item['subject'][:30]}...\n"
    if warm_count > 3:
        warm_text += f"_+ {warm_count - 3} more warm leads..._\n"
    
    low_text = f"\n🟢 *{low_count} Low Priority* leads queued for auto-processing." if low_count > 0 else ""
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🦅 {total} Emails Awaiting Review",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Warm Queue ({warm_count}):*\n{warm_text}{low_text}"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔎 Review Dashboard", "emoji": True},
                    "url": dashboard_url,
                    "style": "primary"
                }
            ]
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"<!date^{int(datetime.now().timestamp())}^Posted {{date}} at {{time}}|Posted just now>"}
            ]
        }
    ]
    
    _send_to_slack(blocks, f"{total} emails pending approval")

def _send_to_slack(blocks: List[Dict], fallback_text: str):
    """Helper to send blocks to Slack."""
    payload = {
        "channel": SLACK_CHANNEL_ID,
        "blocks": blocks,
        "text": fallback_text
    }
    
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post("https://slack.com/api/chat.postMessage", json=payload, headers=headers, timeout=10)
        response_data = response.json()
        
        if not response_data.get("ok"):
            logger.error(f"Slack API Error: {response_data.get('error')}")
        else:
            logger.info("Slack notification sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send Slack notification: {e}")

def main():
    """Main execution logic with priority-based routing."""
    # 1. Check Time Window
    now_est = datetime.now(EST_TIMEZONE)
    current_hour = now_est.hour
    
    logger.info(f"Current EST Time: {now_est.strftime('%Y-%m-%d %H:%M:%S')} (Hour: {current_hour})")
    
    # HOT leads can trigger outside window, others respect window
    force_all = os.getenv("FORCE_NOTIFY") == "true"
    inside_window = START_HOUR <= current_hour < END_HOUR
    
    # 2. Get and classify pending emails
    pending_items = get_pending_details()
    
    hot_items = [e for e in pending_items if e["priority"] == "hot"]
    warm_items = [e for e in pending_items if e["priority"] == "warm"]
    low_items = [e for e in pending_items if e["priority"] == "low"]
    
    logger.info(f"Priority breakdown: HOT={len(hot_items)}, WARM={len(warm_items)}, LOW={len(low_items)}")
    
    # 3. HOT leads always trigger immediately (regardless of time window)
    if hot_items:
        logger.info(f"🔥 Sending IMMEDIATE alert for {len(hot_items)} HOT leads")
        send_hot_alert(hot_items)
    
    # 4. WARM/LOW only notify during window
    if inside_window or force_all:
        if warm_items or low_items:
            logger.info(f"📬 Sending batch alert for {len(warm_items)} WARM + {len(low_items)} LOW leads")
            send_batch_alert(warm_items, low_items)
    else:
        logger.info(f"Outside notification window. Skipping WARM/LOW alerts.")
    
    if not pending_items:
        logger.info("No pending emails. Skipping all alerts.")

if __name__ == "__main__":
    main()
