"""
Simple alerting system for Alpha Swarm.
Sends alerts to Slack and logs to file.
No external dependencies beyond requests.
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime
from pathlib import Path

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / ".tmp" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Load environment variables
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")
ALERT_EMAIL = os.getenv("ALERT_EMAIL")


def send_slack_alert(level: str, message: str) -> bool:
    """
    Send alert to Slack channel.
    
    Args:
        level: info, warning, or error
        message: Alert message
        
    Returns:
        True if sent successfully
    """
    if not SLACK_WEBHOOK:
        print("⚠️ No Slack webhook configured - logging to file only")
        return False
    
    emoji = {
        "info": "ℹ️",
        "warning": "⚠️", 
        "error": "🚨"
    }.get(level, "📢")
    
    color = {
        "info": "#36a64f",  # green
        "warning": "#ffcc00",  # yellow
        "error": "#ff0000"  # red
    }.get(level, "#808080")
    
    payload = {
        "text": f"{emoji} *Alpha Swarm Alert*",
        "attachments": [{
            "color": color,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Level:* {level.upper()} | *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        }
                    ]
                }
            ]
        }]
    }
    
    try:
        response = requests.post(
            SLACK_WEBHOOK,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        response.raise_for_status()
        print(f"✓ Slack alert sent: {level.upper()}")
        return True
    except requests.exceptions.Timeout:
        print(f"✗ Slack timeout - alert not sent")
        return False
    except requests.exceptions.RequestException as e:
        print(f"✗ Slack error: {e}")
        return False


def log_alert(level: str, message: str, channel: str):
    """
    Log alert to file for audit trail.
    """
    log_file = LOG_DIR / "alerts.log"
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level.upper(),
        "channel": channel,
        "message": message
    }
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    print(f"✓ Logged to {log_file}")


def get_recent_alerts(count: int = 10) -> list:
    """
    Get recent alerts from log file.
    """
    log_file = LOG_DIR / "alerts.log"
    
    if not log_file.exists():
        return []
    
    alerts = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                alerts.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    
    return alerts[-count:]


def main():
    parser = argparse.ArgumentParser(description="Alpha Swarm Alert System")
    parser.add_argument(
        "--level",
        choices=["info", "warning", "error"],
        default="info",
        help="Alert severity level"
    )
    parser.add_argument(
        "--message",
        required=False,
        help="Alert message"
    )
    parser.add_argument(
        "--channel",
        choices=["slack", "email", "all", "log"],
        default="slack",
        help="Alert channel"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List recent alerts"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send test alert"
    )
    
    args = parser.parse_args()
    
    # List recent alerts
    if args.list:
        alerts = get_recent_alerts()
        print(f"\n📋 Recent Alerts ({len(alerts)}):\n")
        for alert in alerts:
            print(f"  [{alert['level']}] {alert['timestamp'][:19]} - {alert['message'][:60]}...")
        return
    
    # Test mode
    if args.test:
        message = "🧪 Test alert from Alpha Swarm - system is operational"
        args.message = message
        args.level = "info"
    
    # Require message if not listing or testing
    if not args.message:
        parser.error("--message is required unless using --list or --test")
    
    # Send to appropriate channels
    if args.channel in ["slack", "all"]:
        send_slack_alert(args.level, args.message)
    
    # Always log
    log_alert(args.level, args.message, args.channel)
    
    # Print confirmation
    print(f"\n{args.level.upper()}: {args.message}")


if __name__ == "__main__":
    main()
