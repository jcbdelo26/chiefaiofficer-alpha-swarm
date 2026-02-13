"""
Alert system for SDR automation.
Sends notifications for critical events, warnings, and info.
"""

import json
import os
import sys
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """An alert notification."""
    alert_id: str
    level: str
    title: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    source: str = "system"
    acknowledged: bool = False
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.alert_id:
            self.alert_id = str(uuid.uuid4())


ALERTS_DIR = Path(".hive-mind/alerts")

# Use force_terminal=True with utf-8 to avoid Windows cp1252 emoji crashes
_is_windows = sys.platform == "win32"
console = Console(force_terminal=not _is_windows)

# ASCII-safe fallback for Windows, emoji for Linux/Railway
if _is_windows:
    LEVEL_STYLES = {
        AlertLevel.INFO.value: ("blue", "[i]"),
        AlertLevel.WARNING.value: ("yellow", "[!]"),
        AlertLevel.CRITICAL.value: ("red bold", "[!!!]")
    }
else:
    LEVEL_STYLES = {
        AlertLevel.INFO.value: ("blue", "ℹ️"),
        AlertLevel.WARNING.value: ("yellow", "⚠️"),
        AlertLevel.CRITICAL.value: ("red bold", "🚨")
    }


def send_alert(
    level: AlertLevel | str,
    title: str,
    message: str,
    metadata: Optional[dict[str, Any]] = None,
    source: str = "system",
    console_output: bool = True,
    slack_webhook: bool = True
) -> Alert:
    """
    Send an alert notification.
    
    Args:
        level: Alert severity (info, warning, critical)
        title: Short alert title
        message: Detailed alert message
        metadata: Additional context data
        source: Component that generated the alert
        console_output: Whether to print to console
        slack_webhook: Whether to attempt Slack notification
    
    Returns:
        The created Alert object
    """
    level_str = level.value if isinstance(level, AlertLevel) else level
    
    alert = Alert(
        alert_id=str(uuid.uuid4()),
        level=level_str,
        title=title,
        message=message,
        metadata=metadata or {},
        source=source
    )
    
    _save_alert(alert)
    
    if console_output:
        _print_alert(alert)
    
    if slack_webhook and level_str in (AlertLevel.CRITICAL.value, AlertLevel.WARNING.value):
        _send_slack_webhook(alert)
    
    return alert


def _save_alert(alert: Alert) -> Path:
    """Save alert to filesystem."""
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    if alert.level == AlertLevel.CRITICAL.value:
        filename = f"critical_{ts}_{alert.alert_id[:8]}.json"
    elif alert.level == AlertLevel.WARNING.value:
        filename = f"warning_{ts}_{alert.alert_id[:8]}.json"
    else:
        filename = f"info_{ts}_{alert.alert_id[:8]}.json"
    
    filepath = ALERTS_DIR / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(alert), f, indent=2)
    
    return filepath


def _print_alert(alert: Alert) -> None:
    """Print alert to console with rich formatting."""
    style, emoji = LEVEL_STYLES.get(alert.level, ("white", "[*]"))

    try:
        title_text = Text(f"{emoji} {alert.title}", style=style)

        content = Text()
        content.append(alert.message)

        if alert.metadata:
            content.append("\n\nMetadata:\n", style="dim")
            for key, value in alert.metadata.items():
                content.append(f"  {key}: ", style="dim")
                content.append(f"{value}\n")

        content.append(f"\nSource: {alert.source}", style="dim")
        content.append(f"\nTime: {alert.created_at}", style="dim")

        border_style = style.split()[0] if style else "white"
        panel = Panel(
            content,
            title=title_text,
            border_style=border_style,
            padding=(0, 1)
        )

        console.print(panel)
    except UnicodeEncodeError:
        # Fallback for environments that can't render Rich panels
        print(f"[{alert.level.upper()}] {alert.title}: {alert.message} (source={alert.source})")


def _send_slack_webhook(alert: Alert) -> bool:
    """
    Send alert to Slack webhook.
    
    Placeholder implementation - requires SLACK_WEBHOOK_URL env var.
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    
    if not webhook_url:
        return False
    
    try:
        import requests
        
        emoji_map = {
            AlertLevel.INFO.value: ":information_source:",
            AlertLevel.WARNING.value: ":warning:",
            AlertLevel.CRITICAL.value: ":rotating_light:"
        }
        
        color_map = {
            AlertLevel.INFO.value: "#36a64f",
            AlertLevel.WARNING.value: "#ffcc00",
            AlertLevel.CRITICAL.value: "#ff0000"
        }
        
        emoji = emoji_map.get(alert.level, ":bell:")
        color = color_map.get(alert.level, "#808080")
        
        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"{emoji} {alert.title}",
                    "text": alert.message,
                    "fields": [
                        {"title": "Level", "value": alert.level.upper(), "short": True},
                        {"title": "Source", "value": alert.source, "short": True}
                    ],
                    "footer": f"Alert ID: {alert.alert_id}",
                    "ts": int(datetime.now(timezone.utc).timestamp())
                }
            ]
        }
        
        if alert.metadata:
            for key, value in list(alert.metadata.items())[:5]:
                payload["attachments"][0]["fields"].append({
                    "title": key,
                    "value": str(value)[:100],
                    "short": True
                })
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        return response.status_code == 200
        
    except Exception as e:
        try:
            console.print(f"[dim]Slack webhook failed: {e}[/dim]")
        except UnicodeEncodeError:
            print(f"Slack webhook failed: {e}")
        return False


def get_alerts(
    level: Optional[str] = None,
    limit: int = 50,
    unacknowledged_only: bool = False
) -> list[Alert]:
    """
    Retrieve alerts from the filesystem.
    
    Args:
        level: Filter by alert level
        limit: Maximum number of alerts to return
        unacknowledged_only: Only return unacknowledged alerts
    
    Returns:
        List of Alert objects, most recent first
    """
    if not ALERTS_DIR.exists():
        return []
    
    alerts = []
    
    pattern = "*.json"
    if level:
        pattern = f"{level}_*.json"
    
    files = sorted(ALERTS_DIR.glob(pattern), reverse=True)
    
    for filepath in files[:limit * 2]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                alert = Alert(**data)
                
                if unacknowledged_only and alert.acknowledged:
                    continue
                
                alerts.append(alert)
                
                if len(alerts) >= limit:
                    break
        except Exception:
            continue
    
    return alerts


def acknowledge_alert(alert_id: str, acknowledged_by: str = "system") -> bool:
    """
    Mark an alert as acknowledged.
    
    Args:
        alert_id: The alert ID to acknowledge
        acknowledged_by: Who acknowledged it
    
    Returns:
        True if alert was found and acknowledged
    """
    if not ALERTS_DIR.exists():
        return False
    
    for filepath in ALERTS_DIR.glob("*.json"):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if data.get("alert_id") == alert_id:
                data["acknowledged"] = True
                data["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
                data["acknowledged_by"] = acknowledged_by
                
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                
                return True
        except Exception:
            continue
    
    return False


def send_critical(title: str, message: str, metadata: Optional[dict[str, Any]] = None, source: str = "system", **kwargs) -> Alert:
    """Convenience function for critical alerts."""
    return send_alert(AlertLevel.CRITICAL, title, message, metadata, source, **kwargs)


def send_warning(title: str, message: str, metadata: Optional[dict[str, Any]] = None, source: str = "system", **kwargs) -> Alert:
    """Convenience function for warning alerts."""
    return send_alert(AlertLevel.WARNING, title, message, metadata, source, **kwargs)


def send_info(title: str, message: str, metadata: Optional[dict[str, Any]] = None, source: str = "system", **kwargs) -> Alert:
    """Convenience function for info alerts."""
    return send_alert(AlertLevel.INFO, title, message, metadata, source, **kwargs)
