"""
Slack Interaction Handler
=========================

Handles interactive payloads from Slack Block Kit for approval workflows.
Includes signature verification, rate limiting, and comprehensive logging.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from collections import defaultdict
from typing import Dict, Any, Optional, Tuple

from core.approval_engine import get_approval_engine, ApprovalStatus

logger = logging.getLogger("slack_handler")


class SlackSecurityError(Exception):
    """Raised when Slack request security validation fails."""
    pass


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded."""
    pass


class RateLimiter:
    """Simple in-memory rate limiter using sliding window."""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def check_rate_limit(self, key: str) -> Tuple[bool, int]:
        """
        Check if request is allowed under rate limit.
        
        Returns:
            Tuple of (allowed: bool, remaining: int)
        """
        async with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            
            # Clean old entries
            self._requests[key] = [t for t in self._requests[key] if t > cutoff]
            
            current_count = len(self._requests[key])
            remaining = max(0, self.max_requests - current_count)
            
            if current_count >= self.max_requests:
                return False, 0
            
            self._requests[key].append(now)
            return True, remaining - 1


class SlackInteractionHandler:
    """
    Production-ready Slack interaction handler with security and rate limiting.
    """
    
    # Request timestamp tolerance (5 minutes)
    TIMESTAMP_TOLERANCE_SECONDS = 300
    
    def __init__(self, slack_client=None):
        """
        Initialize handler.
        
        Args:
            slack_client: Optional Slack WebClient for sending DMs.
                         If None, DM functionality will be disabled.
        """
        self.engine = get_approval_engine()
        self.signing_secret = os.environ.get("SLACK_SIGNING_SECRET")
        self.slack_client = slack_client
        self.rate_limiter = RateLimiter(max_requests=100, window_seconds=60)
        
        if not self.signing_secret:
            logger.warning(
                "SLACK_SIGNING_SECRET not set - signature verification disabled. "
                "This is insecure for production!"
            )
    
    def verify_signature(
        self,
        body: bytes,
        timestamp: str,
        signature: str
    ) -> None:
        """
        Verify Slack request signature using HMAC-SHA256.
        
        Args:
            body: Raw request body bytes
            timestamp: X-Slack-Request-Timestamp header value
            signature: X-Slack-Signature header value
            
        Raises:
            SlackSecurityError: If verification fails
        """
        if not self.signing_secret:
            logger.warning("Skipping signature verification - no signing secret configured")
            return
        
        if not timestamp or not signature:
            logger.error("Missing timestamp or signature headers")
            raise SlackSecurityError("Missing required security headers")
        
        # Validate timestamp freshness
        try:
            request_time = int(timestamp)
        except ValueError:
            logger.error(f"Invalid timestamp format: {timestamp}")
            raise SlackSecurityError("Invalid timestamp format")
        
        current_time = int(time.time())
        time_diff = abs(current_time - request_time)
        
        if time_diff > self.TIMESTAMP_TOLERANCE_SECONDS:
            logger.warning(
                f"Request timestamp too old: {time_diff}s (max {self.TIMESTAMP_TOLERANCE_SECONDS}s). "
                f"Possible replay attack or clock skew."
            )
            raise SlackSecurityError(
                f"Request expired (timestamp {time_diff}s old, max allowed {self.TIMESTAMP_TOLERANCE_SECONDS}s)"
            )
        
        # Compute expected signature
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected_sig = "v0=" + hmac.new(
            self.signing_secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(expected_sig, signature):
            logger.error("Signature verification failed - possible tampering or wrong secret")
            raise SlackSecurityError("Invalid request signature")
        
        logger.debug(f"Signature verified successfully for timestamp {timestamp}")

    async def handle_payload(
        self,
        payload: Dict[str, Any],
        raw_body: Optional[bytes] = None,
        timestamp: Optional[str] = None,
        signature: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a Slack interaction payload with full security validation.
        
        Args:
            payload: Decoded 'payload' form parameter from Slack
            raw_body: Raw request body bytes for signature verification
            timestamp: X-Slack-Request-Timestamp header
            signature: X-Slack-Signature header
            
        Returns:
            Dict containing the response to send back to Slack
            
        Raises:
            SlackSecurityError: If security validation fails
            RateLimitExceededError: If rate limit exceeded
        """
        # Extract user info early for logging
        user = payload.get("user", {})
        username = user.get("username", "unknown_slack_user")
        user_id = user.get("id", "unknown_id")
        approver_info = f"{username} ({user_id})"
        
        # Verify request signature if credentials provided
        if raw_body is not None and timestamp is not None and signature is not None:
            self.verify_signature(raw_body, timestamp, signature)
        elif self.signing_secret:
            logger.warning(
                f"Request from {approver_info} processed without signature verification - "
                "ensure verification happens at API gateway level"
            )
        
        # Check rate limit (per user)
        allowed, remaining = await self.rate_limiter.check_rate_limit(user_id)
        if not allowed:
            logger.warning(f"Rate limit exceeded for user {approver_info}")
            raise RateLimitExceededError(
                f"Rate limit exceeded. Please wait before making more requests."
            )
        
        logger.debug(f"Rate limit check passed for {approver_info}: {remaining} requests remaining")
        
        actions = payload.get("actions", [])
        if not actions:
            logger.debug(f"No actions in payload from {approver_info}")
            return {}
        
        # We assume one action per interaction for buttons
        action = actions[0]
        action_id = action.get("action_id", "")
        
        # Format: action_requestID (e.g., approve_req_123 or reject_req_123)
        parts = action_id.split("_", 1)
        if len(parts) != 2:
            logger.warning(f"Invalid action_id format '{action_id}' from {approver_info}")
            return self._create_error_response(
                payload.get("message", {}).get("blocks", []),
                "Invalid action format. Please contact support."
            )
        
        action_type, request_id = parts
        
        logger.info(
            f"Slack interaction received | action={action_type} | request_id={request_id} | "
            f"user={approver_info} | channel={payload.get('channel', {}).get('id', 'unknown')}"
        )
        
        response_blocks = []
        original_blocks = payload.get("message", {}).get("blocks", [])
        
        try:
            if action_type == "approve":
                req = await asyncio.to_thread(
                    self.engine.approve_request, request_id, approver_info, "Approved via Slack"
                )
                logger.info(
                    f"APPROVED | request_id={request_id} | approver={approver_info} | "
                    f"agent={getattr(req, 'agent_id', 'unknown')}"
                )
                response_blocks = self._create_result_blocks(
                    original_blocks, "Approved", "✅", approver_info
                )
                
                # Send confirmation DM
                await self._send_confirmation_dm(
                    user_id, request_id, "approved", req
                )
                
            elif action_type == "reject":
                req = await asyncio.to_thread(
                    self.engine.reject_request, request_id, approver_info, "Rejected via Slack"
                )
                logger.info(
                    f"REJECTED | request_id={request_id} | approver={approver_info} | "
                    f"agent={getattr(req, 'agent_id', 'unknown')}"
                )
                response_blocks = self._create_result_blocks(
                    original_blocks, "Rejected", "❌", approver_info
                )
                
                # Send confirmation DM
                await self._send_confirmation_dm(
                    user_id, request_id, "rejected", req
                )
                
            elif action_type == "view":
                logger.debug(f"View action for {request_id} by {approver_info}")
                return {}
                
            else:
                logger.warning(f"Unknown action type '{action_type}' from {approver_info}")
                return self._create_error_response(
                    original_blocks,
                    f"Unknown action: {action_type}"
                )
                
        except ValueError as e:
            error_msg = str(e)
            logger.warning(
                f"FAILED | request_id={request_id} | approver={approver_info} | "
                f"action={action_type} | error={error_msg}"
            )
            
            # Provide user-friendly error messages
            user_message = self._get_user_friendly_error(error_msg)
            response_blocks = self._create_error_blocks(original_blocks, user_message)
            
        except Exception as e:
            logger.exception(
                f"SYSTEM_ERROR | request_id={request_id} | approver={approver_info} | "
                f"action={action_type} | error={type(e).__name__}: {e}"
            )
            response_blocks = self._create_error_blocks(
                original_blocks,
                "An internal error occurred. Please try again or contact support."
            )

        return {
            "replace_original": True,
            "blocks": response_blocks,
            "text": f"Action processed: {action_type}"
        }
    
    def _get_user_friendly_error(self, error_msg: str) -> str:
        """Convert internal error messages to user-friendly versions."""
        error_lower = error_msg.lower()
        
        if "not found" in error_lower:
            return "This request no longer exists. It may have been cancelled or already processed."
        elif "already" in error_lower and ("approved" in error_lower or "rejected" in error_lower):
            return "This request has already been processed by another approver."
        elif "expired" in error_lower:
            return "This request has expired and can no longer be approved."
        elif "unauthorized" in error_lower or "permission" in error_lower:
            return "You don't have permission to approve this request."
        else:
            return error_msg

    async def _send_confirmation_dm(
        self,
        user_id: str,
        request_id: str,
        action: str,
        request: Any
    ) -> None:
        """
        Send a confirmation DM to the approver.
        
        Args:
            user_id: Slack user ID
            request_id: The approval request ID
            action: "approved" or "rejected"
            request: The approval request object
        """
        if not self.slack_client:
            logger.debug("Slack client not configured - skipping confirmation DM")
            return
        
        try:
            agent_id = getattr(request, 'agent_id', 'Unknown Agent')
            action_type = getattr(request, 'action_type', 'action')
            
            emoji = "✅" if action == "approved" else "❌"
            
            message = (
                f"{emoji} *Confirmation*\n\n"
                f"You have *{action}* the following request:\n"
                f"• *Request ID:* `{request_id}`\n"
                f"• *Agent:* {agent_id}\n"
                f"• *Action:* {action_type}\n"
                f"• *Time:* <!date^{int(time.time())}^{{date_short_pretty}} at {{time}}|now>"
            )
            
            # Run in thread to avoid blocking
            await asyncio.to_thread(
                self.slack_client.chat_postMessage,
                channel=user_id,
                text=message,
                mrkdwn=True
            )
            
            logger.debug(f"Confirmation DM sent to {user_id} for request {request_id}")
            
        except Exception as e:
            # Don't fail the main operation if DM fails
            logger.warning(
                f"Failed to send confirmation DM to {user_id} for request {request_id}: {e}"
            )

    def _create_result_blocks(
        self,
        original_blocks: list,
        status_text: str,
        emoji: str,
        approver: str
    ) -> list:
        """Creates updated blocks showing the decision."""
        new_blocks = []
        for block in original_blocks:
            if block.get("type") != "actions":
                new_blocks.append(block)
        
        # Add status section with timestamp
        new_blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"{emoji} *{status_text}* by {approver}\n"
                        f"<!date^{int(time.time())}^{{date_short_pretty}} at {{time}}|{time.strftime('%Y-%m-%d %H:%M:%S')}>"
                    )
                }
            ]
        })
        return new_blocks

    def _create_error_blocks(self, original_blocks: list, error_msg: str) -> list:
        """Creates updated blocks showing an error."""
        new_blocks = [b for b in original_blocks if b.get("type") != "actions"]
        new_blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"⚠️ *Error:* {error_msg}"
                }
            ]
        })
        return new_blocks
    
    def _create_error_response(self, original_blocks: list, error_msg: str) -> Dict[str, Any]:
        """Creates a full error response dict."""
        return {
            "replace_original": True,
            "blocks": self._create_error_blocks(original_blocks, error_msg),
            "text": f"Error: {error_msg}"
        }


# Singleton instance for convenience
_handler_instance: Optional[SlackInteractionHandler] = None


def get_slack_handler(slack_client=None) -> SlackInteractionHandler:
    """Get or create the singleton SlackInteractionHandler instance."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = SlackInteractionHandler(slack_client=slack_client)
    return _handler_instance
