"""
Configuration loader for SDR automation rules.
"""

from pathlib import Path
from typing import Any, Optional

import yaml


CONFIG_PATH = Path(__file__).parent.parent / "config" / "sdr_rules.yaml"

_cached_rules: Optional[dict[str, Any]] = None


def load_sdr_rules(force_reload: bool = False) -> dict[str, Any]:
    """
    Load and parse sdr_rules.yaml configuration.
    
    Args:
        force_reload: If True, bypass cache and reload from disk
        
    Returns:
        Parsed configuration dictionary
    """
    global _cached_rules
    
    if _cached_rules is not None and not force_reload:
        return _cached_rules
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        _cached_rules = yaml.safe_load(f)
    
    return _cached_rules


def get_objection_action(objection_type: str) -> dict[str, Any]:
    """
    Get the configured action for a specific objection type.
    
    Args:
        objection_type: One of: not_interested, bad_timing, already_have_solution,
                       need_more_info, pricing_objection, technical_question,
                       positive_interest
    
    Returns:
        Dict with action, escalation, and automation fields
    """
    rules = load_sdr_rules()
    objection_matrix = rules.get("objection_matrix", {})
    
    if objection_type not in objection_matrix:
        return {
            "action": "unknown",
            "escalation": "always",
            "automation": "none"
        }
    
    return objection_matrix[objection_type]


def get_escalation_triggers() -> dict[str, list[dict[str, Any]]]:
    """
    Get all configured escalation triggers grouped by urgency.
    
    Returns:
        Dict with keys: immediate, standard, deferred
        Each contains a list of trigger configurations
    """
    rules = load_sdr_rules()
    return rules.get("escalation_triggers", {})


def get_compliance_rules() -> dict[str, Any]:
    """
    Get all compliance rules (CAN-SPAM, LinkedIn ToS, GDPR, Brand Safety).
    
    Returns:
        Dict with keys: can_spam, linkedin_tos, gdpr, brand_safety
    """
    rules = load_sdr_rules()
    return rules.get("compliance", {})


def get_sla_targets() -> dict[str, Any]:
    """
    Get SLA targets for response times and processes.
    
    Returns:
        Dict with keys: response_time, process
    """
    rules = load_sdr_rules()
    return rules.get("sla_targets", {})


def get_exception_policies() -> dict[str, Any]:
    """
    Get exception handling policies for system failures and data quality issues.
    
    Returns:
        Dict with keys: system_failures, data_quality
    """
    rules = load_sdr_rules()
    return rules.get("exception_policies", {})
