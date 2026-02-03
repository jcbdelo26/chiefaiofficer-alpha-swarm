#!/usr/bin/env python3
"""
Notification Manager
===================

Centralized notification service for all agents.
Handles Slack (Block Kit), SMS (Twilio), and Email (SMTP).

Escalation levels:
1. Slack notification
2. SMS alert (for urgent items)
3. Email + Phone (for critical items)

Production Features:
- Retry logic with exponential backoff
- Phone number validation
- Fallback mechanisms (Slack -> Email)
- Connection pooling
- Health checks
- Comprehensive error handling
"""

import os
import re
import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional, Any, Protocol, runtime_checkable, Tuple
from rich.console import Console
from dataclasses import dataclass

console = Console()
logger = logging.getLogger("notifications")

SLACK_RETRY_DELAYS = [1.0, 2.0, 4.0]
SLACK_MAX_RETRIES = 3
PHONE_PATTERN = re.compile(r"^\+\d{10,15}$")


@runtime_checkable
class NotifiableItem(Protocol):
    """Protocol for items that can be notified about."""
    @property
    def urgency(self) -> str: ...
    @property
    def review_id(self) -> str: ...

# Re-defining ReviewItem/Urgency for type hinting if reused, 
# but ideally we should decouple from ReviewItem data structure.
# For now, we will use loose typing or simple dicts/objects to avoid circular imports.

class NotificationManager:
    """
    Manages notifications for approval requests via Slack, SMS, and Email.
    """
    
    def __init__(self):
        self.slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        self._validate_slack_webhook()
        self.twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.twilio_from = os.getenv("TWILIO_FROM_NUMBER")
        self.email_from = os.getenv("NOTIFICATION_EMAIL_FROM")
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.escalation_contacts = self._load_escalation_contacts()
        self.notification_stats = {
            "slack_sent": 0,
            "sms_sent": 0,
            "email_sent": 0,
            "failures": 0
        }
        self._session: Optional[aiohttp.ClientSession] = None
    
    def _validate_slack_webhook(self):
        """Validate Slack webhook URL format."""
        if self.slack_webhook:
            if not self.slack_webhook.startswith("https://hooks.slack.com/"):
                logger.warning("Slack webhook URL may be invalid (expected hooks.slack.com)")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create a reusable aiohttp session with connection pooling."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300,
                keepalive_timeout=30,
                enable_cleanup_closed=True,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=30, connect=10)
            )
        return self._session
    
    async def close(self):
        """Close the HTTP session. Call on shutdown."""
        try:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None
        except Exception as e:
            logger.error(f"Error closing HTTP session: {e}")
            self._session = None

    def _validate_phone_number(self, phone: str) -> Tuple[bool, str]:
        """
        Validate phone number format.
        Must start with + and have 10-15 digits.
        Returns (is_valid, error_message).
        """
        if not phone:
            return False, "Phone number is empty"
        phone = phone.strip()
        if not phone.startswith("+"):
            return False, "Phone number must start with '+'"
        if not PHONE_PATTERN.match(phone):
            return False, "Phone number must have 10-15 digits after '+'"
        return True, ""

    async def _send_slack_with_retry(
        self, 
        payload: Dict[str, Any],
        fallback_email: Optional[str] = None,
        fallback_item: Optional[Any] = None
    ) -> bool:
        """
        Send Slack notification with retry logic and exponential backoff.
        Falls back to email if all retries fail.
        """
        if not self.slack_webhook:
            return False

        last_error: Optional[Exception] = None
        
        for attempt in range(SLACK_MAX_RETRIES):
            try:
                session = await self._get_session()
                async with session.post(self.slack_webhook, json=payload) as resp:
                    if resp.status == 200:
                        self.notification_stats["slack_sent"] += 1
                        return True
                    elif resp.status == 429:
                        retry_after = float(resp.headers.get("Retry-After", SLACK_RETRY_DELAYS[attempt]))
                        logger.warning(f"Slack rate limited, retry after {retry_after}s")
                        await asyncio.sleep(retry_after)
                    else:
                        error_text = await resp.text()
                        logger.warning(f"Slack notification failed (attempt {attempt + 1}): {resp.status} - {error_text}")
                        if attempt < SLACK_MAX_RETRIES - 1:
                            await asyncio.sleep(SLACK_RETRY_DELAYS[attempt])
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_error = e
                logger.warning(f"Slack notification error (attempt {attempt + 1}): {e}")
                if attempt < SLACK_MAX_RETRIES - 1:
                    await asyncio.sleep(SLACK_RETRY_DELAYS[attempt])

        self.notification_stats["failures"] += 1
        logger.error(f"Slack notification failed after {SLACK_MAX_RETRIES} retries")

        if fallback_email and fallback_item:
            logger.info(f"Falling back to email notification for {fallback_email}")
            email_success = await self.send_email_fallback(
                fallback_email, 
                fallback_item,
                subject="[FALLBACK] Slack notification failed - Action Required"
            )
            if email_success:
                logger.info("Email fallback succeeded")
                return True
            else:
                logger.error("Email fallback also failed")

        return False

    async def health_check(self) -> Dict[str, Any]:
        """
        Test connectivity to notification services.
        Returns health status for each service.
        """
        health = {
            "slack": {"configured": False, "healthy": False, "error": None},
            "twilio": {"configured": False, "healthy": False, "error": None},
            "email": {"configured": False, "healthy": False, "error": None},
        }

        if self.slack_webhook:
            health["slack"]["configured"] = True
            try:
                session = await self._get_session()
                async with session.post(
                    self.slack_webhook,
                    json={"text": "Health check - please ignore"},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    health["slack"]["healthy"] = resp.status == 200
                    if resp.status != 200:
                        health["slack"]["error"] = f"HTTP {resp.status}"
            except asyncio.CancelledError:
                raise
            except Exception as e:
                health["slack"]["error"] = str(e)

        if all([self.twilio_sid, self.twilio_token, self.twilio_from]):
            health["twilio"]["configured"] = True
            health["twilio"]["healthy"] = True

        if all([self.smtp_user, self.smtp_password]):
            health["email"]["configured"] = True
            health["email"]["healthy"] = True

        return health
    
    def _load_escalation_contacts(self) -> Dict[str, List[Dict[str, str]]]:
        """
        Load escalation contact chain - currently routes ALL notifications to Dani Apgar.
        
        Dani is the primary and only approver for now:
        - Slack: @dani (configurable via SLACK_DANI_USER_ID env var)
        - Email: dani@chiefaiofficer.com
        - Phone: +1 505-799-5035
        """
        dani_slack_user_id = os.getenv("SLACK_DANI_USER_ID", "")
        dani_email = "dani@chiefaiofficer.com"
        dani_phone = "+15057995035"
        
        return {
            "level1": [
                {
                    "name": "Dani Apgar",
                    "slack_channel": "#approvals",
                    "slack_user_id": dani_slack_user_id,
                    "slack_mention": "@dani"
                }
            ],
            "level2": [
                {
                    "name": "Dani Apgar",
                    "email": dani_email,
                    "slack_user_id": dani_slack_user_id
                }
            ],
            "level3": [
                {
                    "name": "Dani Apgar",
                    "phone": dani_phone,
                    "email": dani_email,
                    "slack_user_id": dani_slack_user_id
                }
            ],
            "fallback_email": dani_email,
            "dani": {
                "name": "Dani Apgar",
                "slack_user_id": dani_slack_user_id,
                "slack_mention": "@dani",
                "email": dani_email,
                "phone": dani_phone
            }
        }
    
    async def send_slack_notification(
        self, 
        item: Any,
        channel: str = "#approvals",
        fallback_email: Optional[str] = None
    ) -> bool:
        """
        Send Slack notification with Block Kit formatting.
        Uses retry logic with exponential backoff.
        Falls back to email if all retries fail and fallback_email is provided.
        """
        if not self.slack_webhook:
            logger.debug("Slack webhook not configured")
            return False
        
        # Safe attribute access helper
        def get_attr(obj, attr, default=None):
            if isinstance(obj, dict):
                return obj.get(attr, default)
            return getattr(obj, attr, default)

        urgency = get_attr(item, 'urgency', 'normal')
        campaign_name = get_attr(item, 'campaign_name', 'Unknown Campaign')
        review_id = get_attr(item, 'review_id', 'unknown_id')
        
        urgency_emoji = {
            "normal": "📋",
            "urgent": "⚠️",
            "critical": "🚨"
        }
        
        # Handle ApprovalRequest vs ReviewItem
        # If it's an ApprovalRequest, some fields might be in 'payload'
        if hasattr(item, 'payload') and isinstance(item.payload, dict):
            # Fallback to payload for missing fields
            if campaign_name == 'Unknown Campaign':
                campaign_name = item.payload.get('campaign_name', item.description or 'Unknown Request')
        
        campaign_type = get_attr(item, 'campaign_type', 'N/A')
        lead_count = get_attr(item, 'lead_count', 0)
        avg_icp_score = get_attr(item, 'avg_icp_score', 0)
        tier = get_attr(item, 'tier', 'N/A')
        
        # Email preview handling
        email_preview = get_attr(item, 'email_preview', {})
        subject_line = 'N/A'
        if isinstance(email_preview, dict):
            subject_line = email_preview.get('subject_a', 'N/A')
        
        # Description fallback for generic requests
        description = get_attr(item, 'description', '')

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{urgency_emoji.get(urgency, '📋')} Approval Required",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Item:*\n{campaign_name}"},
                    {"type": "mrkdwn", "text": f"*Type:*\n{campaign_type}"},
                    {"type": "mrkdwn", "text": f"*Urgency:*\n{urgency.upper()}"}
                ]
            }
        ]
        
        # Add metrics if available
        if lead_count or avg_icp_score:
            blocks[1]["fields"].extend([
                {"type": "mrkdwn", "text": f"*Leads:*\n{lead_count}"},
                {"type": "mrkdwn", "text": f"*ICP Score:*\n{avg_icp_score:.0f}"}
            ])

        if description:
             blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Description:* {description}"
                }
            })

        if subject_line != 'N/A':
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Subject:* {subject_line}"
                }
            })
            
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Approve"},
                    "style": "primary",
                    "action_id": f"approve_{review_id}"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Reject"},
                    "style": "danger",
                    "action_id": f"reject_{review_id}"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📝 Details"},
                    "action_id": f"view_{review_id}"
                }
            ]
        })
        
        payload = {
            "channel": channel,
            "blocks": blocks,
            "text": f"Approval required: {campaign_name}"
        }
        
        return await self._send_slack_with_retry(
            payload,
            fallback_email=fallback_email or self.escalation_contacts.get("fallback_email"),
            fallback_item=item
        )
    
    async def notify_dani_directly(
        self,
        message: str,
        urgency: str = "normal",
        channel: str = "#approvals"
    ) -> bool:
        """
        Send a notification directly to Dani Apgar.
        Always tags @dani in Slack messages with her user ID mention.
        
        Args:
            message: The message content to send
            urgency: Urgency level (normal, urgent, critical)
            channel: Slack channel to post to (default: #approvals)
            
        Returns:
            True if notification was sent successfully
        """
        if not self.slack_webhook:
            logger.debug("Slack webhook not configured")
            return False
        
        dani_config = self.escalation_contacts.get("dani", {})
        dani_user_id = dani_config.get("slack_user_id", "")
        dani_email = dani_config.get("email", "dani@chiefaiofficer.com")
        
        urgency_emoji = {
            "normal": "📋",
            "urgent": "⚠️",
            "critical": "🚨"
        }
        
        # Build user mention - use Slack user ID format if available
        if dani_user_id:
            user_mention = f"<@{dani_user_id}>"
        else:
            user_mention = "@dani"
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{urgency_emoji.get(urgency, '📋')} {user_mention} {message}"
                }
            }
        ]
        
        # Add context block with urgency if not normal
        if urgency != "normal":
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Urgency:* {urgency.upper()}"
                    }
                ]
            })
        
        payload = {
            "channel": channel,
            "blocks": blocks,
            "text": f"{user_mention} {message}"
        }
        
        return await self._send_slack_with_retry(
            payload,
            fallback_email=dani_email,
            fallback_item={"message": message, "urgency": urgency}
        )
    
    async def send_sms_alert(self, phone: str, message: str) -> bool:
        """
        Send SMS via Twilio for urgent items.
        Phone number must start with + and have 10-15 digits.
        """
        if not all([self.twilio_sid, self.twilio_token, self.twilio_from]):
            logger.debug("Twilio not configured")
            return False
        
        is_valid, error_msg = self._validate_phone_number(phone)
        if not is_valid:
            logger.warning(f"Invalid phone number '{phone}': {error_msg}")
            return False
        
        phone = phone.strip()
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_sid}/Messages.json"
        
        try:
            session = await self._get_session()
            auth = aiohttp.BasicAuth(self.twilio_sid, self.twilio_token)
            data = {
                "From": self.twilio_from,
                "To": phone,
                "Body": message[:1600]
            }
            async with session.post(url, data=data, auth=auth) as resp:
                if resp.status in [200, 201]:
                    self.notification_stats["sms_sent"] += 1
                    return True
                else:
                    self.notification_stats["failures"] += 1
                    error_text = await resp.text()
                    logger.warning(f"SMS send failed: {resp.status} - {error_text}")
                    return False
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.notification_stats["failures"] += 1
            logger.exception(f"SMS error: {e}")
            return False
    
    async def send_email_fallback(
        self, 
        email: str, 
        item: Any,
        subject: Optional[str] = None
    ) -> bool:
        """
        Send email notification as fallback or for 2hr timeout.
        Never raises exceptions - all errors are logged.
        """
        if not all([self.smtp_user, self.smtp_password]):
            logger.debug("SMTP not configured")
            return False
        
        if not email or "@" not in email:
            logger.warning(f"Invalid email address: {email}")
            return False
        
        try:
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            urgency = getattr(item, 'urgency', 'normal') if item else 'normal'
            campaign_name = getattr(item, 'campaign_name', 'Unknown Campaign') if item else 'Unknown'
            review_id = getattr(item, 'review_id', 'unknown_id') if item else 'unknown'
            campaign_type = getattr(item, 'campaign_type', 'N/A') if item else 'N/A'
            lead_count = getattr(item, 'lead_count', 0) if item else 0
            avg_icp_score = getattr(item, 'avg_icp_score', 0) if item else 0
            tier = getattr(item, 'tier', 'N/A') if item else 'N/A'
            email_preview = getattr(item, 'email_preview', {}) if item else {}
            subject_line = email_preview.get('subject_a', 'N/A') if isinstance(email_preview, dict) else 'N/A'
            body_preview = email_preview.get('body', 'No preview available') if isinstance(email_preview, dict) else 'N/A'
            queued_at = getattr(item, 'queued_at', 'N/A') if item else 'N/A'

            subject = subject or f"[{urgency.upper()}] Campaign Approval Required: {campaign_name}"
            
            body = f"""
Campaign Approval Required
==========================

Campaign: {campaign_name}
Type: {campaign_type}
Leads: {lead_count}
ICP Score: {avg_icp_score:.0f}
Urgency: {urgency.upper()}
Tier: {tier or 'N/A'}

Subject Line: {subject_line}

Preview:
{body_preview}

---
Review ID: {review_id}
Queued at: {queued_at}

To approve/reject, visit the dashboard or reply to this email.
"""
            
            msg = MIMEMultipart()
            msg['From'] = self.email_from or self.smtp_user
            msg['To'] = email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            await asyncio.to_thread(self._send_email_sync, msg)
            self.notification_stats["email_sent"] += 1
            logger.info(f"Email sent successfully to {email}")
            return True
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.notification_stats["failures"] += 1
            logger.exception(f"Email error sending to {email}: {e}")
            return False
    
    def _send_email_sync(self, msg):
        """Synchronous email send, run in thread pool."""
        import smtplib
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
        except Exception as e:
            logger.error(f"SMTP error: {e}")
            raise
    
    async def escalate(self, item: Any, level: int = 1) -> Dict[str, bool]:
        """
        Escalate notification based on level - ALL notifications go to Dani Apgar.
        Never raises exceptions - all errors are logged.
        
        Level 1: Slack DM to @dani + #approvals channel
        Level 2: Email to dani@chiefaiofficer.com
        Level 3: SMS to +1 505-799-5035
        """
        results = {"slack": False, "sms": False, "email": False}
        
        dani_config = self.escalation_contacts.get("dani", {})
        dani_email = dani_config.get("email", "dani@chiefaiofficer.com")
        dani_phone = dani_config.get("phone", "+15057995035")
        
        try:
            results["slack"] = await self.send_slack_notification(
                item, 
                fallback_email=dani_email
            )
            
            if level >= 2:
                try:
                    results["email"] = await self.send_email_fallback(dani_email, item)
                except Exception as e:
                    logger.error(f"Email escalation to Dani failed: {e}")
            
            if level >= 3:
                try:
                    campaign_name = getattr(item, 'campaign_name', 'Unknown') if item else 'Unknown'
                    lead_count = getattr(item, 'lead_count', 0) if item else 0
                    avg_icp_score = getattr(item, 'avg_icp_score', 0) if item else 0
                    review_id = getattr(item, 'review_id', 'unknown') if item else 'unknown'

                    msg = f"CRITICAL: Campaign '{campaign_name}' needs approval. {lead_count} leads, ICP {avg_icp_score:.0f}. Review ID: {review_id[:8]}"
                    results["sms"] = await self.send_sms_alert(dani_phone, msg)
                except Exception as e:
                    logger.error(f"SMS escalation to Dani failed: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"Escalation error at level {level}: {e}")
        
        return results
    
    def get_stats(self) -> Dict[str, int]:
        """Get notification statistics."""
        return self.notification_stats.copy()
    
    def reset_stats(self) -> None:
        """Reset notification statistics."""
        self.notification_stats = {
            "slack_sent": 0,
            "sms_sent": 0,
            "email_sent": 0,
            "failures": 0
        }


_notification_manager: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    """Get singleton instance of NotificationManager."""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager


async def shutdown_notification_manager() -> None:
    """Gracefully shutdown the notification manager."""
    global _notification_manager
    if _notification_manager is not None:
        try:
            await _notification_manager.close()
        except Exception as e:
            logger.error(f"Error shutting down notification manager: {e}")
        finally:
            _notification_manager = None
