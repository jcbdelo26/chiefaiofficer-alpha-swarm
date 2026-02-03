#!/usr/bin/env python3
"""
Production Configuration Loader
================================

Loads production.json and resolves environment variable references.
Provides a unified interface for all agents to access production settings.

Usage:
    from config.production_config import get_production_config, is_production_mode
    
    config = get_production_config()
    if config.email_behavior.actually_send:
        # Send real emails
    else:
        # Shadow mode - log only
"""

import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

logger = logging.getLogger("production_config")

CONFIG_DIR = Path(__file__).parent
PRODUCTION_CONFIG_PATH = CONFIG_DIR / "production.json"
SANDBOX_CONFIG_PATH = CONFIG_DIR / "sandbox.json"


@dataclass
class APIConfig:
    """Configuration for an external API."""
    enabled: bool
    base_url: Optional[str]
    api_key: Optional[str]
    timeout_seconds: int = 30
    retry_attempts: int = 3
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmailBehavior:
    """Email sending behavior configuration."""
    actually_send: bool
    shadow_mode: bool
    log_to_file: bool
    log_path: str
    require_approval: bool
    max_daily_sends: int


@dataclass
class FailureTrackerConfig:
    """Failure tracking configuration."""
    enabled: bool
    log_path: str
    alert_threshold: int
    alert_window_minutes: int
    slack_alerts: bool
    agents: Dict[str, Dict[str, Any]]


@dataclass
class ProductionConfig:
    """Complete production configuration."""
    mode: str
    external_apis_enabled: bool
    
    # API configurations
    ghl: APIConfig
    rb2b: APIConfig
    instantly: APIConfig
    clay: APIConfig
    supabase: APIConfig
    slack: APIConfig
    twilio: APIConfig
    
    # Behaviors
    email_behavior: EmailBehavior
    failure_tracker: FailureTrackerConfig
    
    # Guardrails
    guardrails: Dict[str, Any]
    
    # Rollout phase
    rollout_phase: str
    
    # Raw config for advanced access
    raw: Dict[str, Any]


def _resolve_env_var(env_var_name: str, default: Optional[str] = None) -> Optional[str]:
    """Resolve an environment variable, with optional default."""
    value = os.getenv(env_var_name)
    if value is None and default is not None:
        return default
    return value


def _load_api_config(api_data: Dict[str, Any]) -> APIConfig:
    """Load an API configuration, resolving env vars."""
    if not api_data.get("enabled", False):
        return APIConfig(enabled=False, base_url=None, api_key=None)
    
    # Resolve API key from environment variable
    api_key = None
    if "api_key_env" in api_data:
        api_key = _resolve_env_var(api_data["api_key_env"])
    
    # Collect extra fields
    extra = {}
    for key, value in api_data.items():
        if key.endswith("_env") and key != "api_key_env":
            resolved_key = key.replace("_env", "")
            extra[resolved_key] = _resolve_env_var(value)
        elif key not in ("enabled", "base_url", "api_key_env", "timeout_seconds", "retry_attempts"):
            extra[key] = value
    
    return APIConfig(
        enabled=api_data.get("enabled", False),
        base_url=api_data.get("base_url"),
        api_key=api_key,
        timeout_seconds=api_data.get("timeout_seconds", 30),
        retry_attempts=api_data.get("retry_attempts", 3),
        extra=extra
    )


def _load_email_behavior(data: Dict[str, Any]) -> EmailBehavior:
    """Load email behavior configuration."""
    return EmailBehavior(
        actually_send=data.get("actually_send", False),
        shadow_mode=data.get("shadow_mode", True),
        log_to_file=data.get("log_to_file", True),
        log_path=data.get("log_path", ".hive-mind/production_emails/"),
        require_approval=data.get("require_approval", True),
        max_daily_sends=data.get("max_daily_sends", 0)
    )


def _load_failure_tracker(data: Dict[str, Any]) -> FailureTrackerConfig:
    """Load failure tracker configuration."""
    return FailureTrackerConfig(
        enabled=data.get("enabled", True),
        log_path=data.get("log_path", ".hive-mind/failures/"),
        alert_threshold=data.get("alert_threshold", 5),
        alert_window_minutes=data.get("alert_window_minutes", 15),
        slack_alerts=data.get("slack_alerts", True),
        agents=data.get("agents", {})
    )


def load_production_config() -> ProductionConfig:
    """
    Load and parse the production configuration.
    
    Returns:
        ProductionConfig with all settings resolved
    """
    if not PRODUCTION_CONFIG_PATH.exists():
        raise FileNotFoundError(f"Production config not found: {PRODUCTION_CONFIG_PATH}")
    
    with open(PRODUCTION_CONFIG_PATH, 'r') as f:
        raw = json.load(f)
    
    apis = raw.get("external_apis", {})
    
    return ProductionConfig(
        mode=raw.get("mode", "production"),
        external_apis_enabled=raw.get("external_apis_enabled", True),
        
        ghl=_load_api_config(apis.get("ghl", {})),
        rb2b=_load_api_config(apis.get("rb2b", {})),
        instantly=_load_api_config(apis.get("instantly", {})),
        clay=_load_api_config(apis.get("clay", {})),
        supabase=_load_api_config(apis.get("supabase", {})),
        slack=_load_api_config(apis.get("slack", {})),
        twilio=_load_api_config(apis.get("twilio", {})),
        
        email_behavior=_load_email_behavior(raw.get("email_behavior", {})),
        failure_tracker=_load_failure_tracker(raw.get("failure_tracker", {})),
        
        guardrails=raw.get("guardrails", {}),
        rollout_phase=raw.get("rollout_phase", {}).get("current", "shadow"),
        
        raw=raw
    )


# Singleton instance
_config_instance: Optional[ProductionConfig] = None


def get_production_config() -> ProductionConfig:
    """Get the singleton production configuration instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = load_production_config()
    return _config_instance


def is_production_mode() -> bool:
    """Check if running in production mode."""
    config = get_production_config()
    return config.mode == "production" and config.external_apis_enabled


def is_shadow_mode() -> bool:
    """Check if running in shadow mode (no actual sends)."""
    config = get_production_config()
    return config.email_behavior.shadow_mode or not config.email_behavior.actually_send


def get_rollout_phase() -> str:
    """Get the current rollout phase."""
    config = get_production_config()
    return config.rollout_phase


def validate_required_env_vars() -> Dict[str, bool]:
    """
    Validate that all required environment variables are set.
    
    Returns:
        Dict mapping variable name to whether it's set
    """
    config = get_production_config()
    required = config.raw.get("environment_variables_required", [])
    
    results = {}
    for var in required:
        value = os.getenv(var)
        results[var] = value is not None and len(value) > 0
    
    return results


def get_missing_env_vars() -> List[str]:
    """Get list of missing required environment variables."""
    validation = validate_required_env_vars()
    return [var for var, is_set in validation.items() if not is_set]


def print_config_status():
    """Print configuration status for debugging."""
    config = get_production_config()
    missing = get_missing_env_vars()
    
    print("=" * 60)
    print("PRODUCTION CONFIGURATION STATUS")
    print("=" * 60)
    print(f"Mode: {config.mode}")
    print(f"Rollout Phase: {config.rollout_phase}")
    print(f"External APIs Enabled: {config.external_apis_enabled}")
    print(f"Shadow Mode: {is_shadow_mode()}")
    print()
    
    print("API Status:")
    print(f"  GHL: {'[OK]' if config.ghl.enabled and config.ghl.api_key else '[MISSING]'}")
    print(f"  RB2B: {'[OK]' if config.rb2b.enabled and config.rb2b.api_key else '[MISSING]'}")
    print(f"  Instantly: {'[OK]' if config.instantly.enabled and config.instantly.api_key else '[MISSING]'}")
    print(f"  Clay: {'[OK]' if config.clay.enabled and config.clay.api_key else '[MISSING]'}")
    print()
    
    print("Email Behavior:")
    print(f"  Actually Send: {config.email_behavior.actually_send}")
    print(f"  Shadow Mode: {config.email_behavior.shadow_mode}")
    print(f"  Require Approval: {config.email_behavior.require_approval}")
    print()
    
    print("Failure Tracker:")
    print(f"  Enabled: {config.failure_tracker.enabled}")
    print(f"  Agents Tracked: {len(config.failure_tracker.agents)}")
    print()
    
    if missing:
        print("[WARNING] Missing Environment Variables:")
        for var in missing:
            print(f"   - {var}")
    else:
        print("[OK] All required environment variables are set")
    
    print("=" * 60)


if __name__ == "__main__":
    print_config_status()
