#!/usr/bin/env python3
"""
Slack MCP Configuration
=======================
Configuration and environment management for Slack MCP server.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class SlackConfig:
    """Slack configuration from environment variables."""
    
    # Bot token (xoxb-...)
    bot_token: str = ""
    
    # Signing secret for webhook verification
    signing_secret: str = ""
    
    # Default channels
    default_channel: str = "#revops-alerts"
    approval_channel: str = "#revops-approvals"
    incident_channel: str = "#revops-incidents"
    
    # Timeouts
    default_approval_timeout_minutes: int = 30
    critical_approval_timeout_minutes: int = 10
    
    # Escalation
    escalation_user_ids: list = None  # Slack user IDs for escalation
    
    # Rate limits
    max_messages_per_minute: int = 20
    max_approvals_per_hour: int = 50
    
    @classmethod
    def from_env(cls) -> 'SlackConfig':
        """Load configuration from environment variables."""
        escalation_ids = os.getenv("SLACK_ESCALATION_USER_IDS", "")
        
        return cls(
            bot_token=os.getenv("SLACK_BOT_TOKEN", ""),
            signing_secret=os.getenv("SLACK_SIGNING_SECRET", ""),
            default_channel=os.getenv("SLACK_DEFAULT_CHANNEL", "#revops-alerts"),
            approval_channel=os.getenv("SLACK_APPROVAL_CHANNEL", "#revops-approvals"),
            incident_channel=os.getenv("SLACK_INCIDENT_CHANNEL", "#revops-incidents"),
            default_approval_timeout_minutes=int(os.getenv("SLACK_APPROVAL_TIMEOUT", "30")),
            critical_approval_timeout_minutes=int(os.getenv("SLACK_CRITICAL_TIMEOUT", "10")),
            escalation_user_ids=escalation_ids.split(",") if escalation_ids else [],
            max_messages_per_minute=int(os.getenv("SLACK_RATE_LIMIT_MSG", "20")),
            max_approvals_per_hour=int(os.getenv("SLACK_RATE_LIMIT_APPROVALS", "50"))
        )
    
    @property
    def is_configured(self) -> bool:
        """Check if Slack is properly configured."""
        return bool(self.bot_token)
    
    def validate(self) -> list:
        """Validate configuration and return list of issues."""
        issues = []
        
        if not self.bot_token:
            issues.append("SLACK_BOT_TOKEN not set")
        elif not self.bot_token.startswith("xoxb-"):
            issues.append("SLACK_BOT_TOKEN should start with 'xoxb-'")
        
        if not self.signing_secret:
            issues.append("SLACK_SIGNING_SECRET not set (required for webhooks)")
        
        if not self.approval_channel.startswith("#"):
            issues.append("SLACK_APPROVAL_CHANNEL should start with '#'")
        
        return issues


# Global config instance
_config: Optional[SlackConfig] = None


def get_config() -> SlackConfig:
    """Get or create global config instance."""
    global _config
    if _config is None:
        _config = SlackConfig.from_env()
    return _config


# Environment variable template for .env file
ENV_TEMPLATE = """
# Slack MCP Configuration
# =======================

# Bot OAuth Token (from Slack App > OAuth & Permissions)
# Required scopes: chat:write, chat:write.public, commands, incoming-webhook
SLACK_BOT_TOKEN=xoxb-your-bot-token

# Signing Secret (from Slack App > Basic Information > App Credentials)
SLACK_SIGNING_SECRET=your-signing-secret

# Channel Configuration
SLACK_DEFAULT_CHANNEL=#revops-alerts
SLACK_APPROVAL_CHANNEL=#revops-approvals
SLACK_INCIDENT_CHANNEL=#revops-incidents

# Timeout Configuration (minutes)
SLACK_APPROVAL_TIMEOUT=30
SLACK_CRITICAL_TIMEOUT=10

# Escalation User IDs (comma-separated Slack user IDs)
SLACK_ESCALATION_USER_IDS=U12345678,U87654321

# Rate Limits
SLACK_RATE_LIMIT_MSG=20
SLACK_RATE_LIMIT_APPROVALS=50
"""


if __name__ == "__main__":
    config = get_config()
    print("Slack MCP Configuration")
    print("=" * 40)
    print(f"Bot Token: {'✅ Set' if config.bot_token else '❌ Not set'}")
    print(f"Signing Secret: {'✅ Set' if config.signing_secret else '❌ Not set'}")
    print(f"Default Channel: {config.default_channel}")
    print(f"Approval Channel: {config.approval_channel}")
    print(f"Configured: {config.is_configured}")
    
    issues = config.validate()
    if issues:
        print("\nConfiguration Issues:")
        for issue in issues:
            print(f"  ⚠️ {issue}")
    else:
        print("\n✅ Configuration valid")
