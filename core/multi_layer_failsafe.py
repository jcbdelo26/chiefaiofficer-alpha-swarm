#!/usr/bin/env python3
"""
Multi-Layer Failsafe System - Beta Swarm
=========================================
Day 16 Implementation: Enterprise-grade multi-layer protection system.

Layer Architecture:
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                         MULTI-LAYER FAILSAFE                             │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  Layer 1: INPUT VALIDATION                                               │
    │  ├── Type checking (strict & coerced)                                   │
    │  ├── Sanitization (trim, normalize, escape)                             │
    │  ├── Length limits (per-field configurable)                             │
    │  └── Encoding validation (UTF-8, ASCII, detect injection)               │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  Layer 2: CIRCUIT BREAKER (Enhanced)                                     │
    │  ├── Per-agent circuit breakers                                         │
    │  ├── 3-failure trip (configurable)                                      │
    │  ├── Exponential backoff (1-60s)                                        │
    │  ├── Auto-reset after 5min                                              │
    │  └── Half-open test before full recovery                                │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  Layer 3: FALLBACK CHAIN (Day 17)                                        │
    │  Layer 4: BYZANTINE CONSENSUS (Day 17)                                   │
    └─────────────────────────────────────────────────────────────────────────┘

Integration:
    - Wraps existing core/circuit_breaker.py
    - Integrates with core/unified_guardrails.py
    - Provides decorators and context managers

Usage:
    from core.multi_layer_failsafe import (
        FailsafeLayer,
        InputValidator,
        AgentCircuitBreaker,
        with_failsafe,
        validate_input
    )
    
    # Decorator usage
    @with_failsafe(agent_name="SCHEDULER", layers=[1, 2])
    async def book_meeting(data: dict):
        pass
    
    # Manual usage
    validator = InputValidator()
    result = validator.validate(data, schema)
    if not result.valid:
        handle_errors(result.errors)
"""

import os
import sys
import re
import json
import html
import asyncio
import functools
import logging
import math
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable, Union, TypeVar, Type
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import existing circuit breaker
from core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitBreakerError,
    CircuitState,
    get_registry as get_base_registry
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("multi-layer-failsafe")


# ============================================================================
# LAYER 1: INPUT VALIDATION
# ============================================================================

class ValidationErrorType(Enum):
    """Types of validation errors."""
    TYPE_MISMATCH = "type_mismatch"
    REQUIRED_MISSING = "required_missing"
    LENGTH_EXCEEDED = "length_exceeded"
    LENGTH_TOO_SHORT = "length_too_short"
    PATTERN_MISMATCH = "pattern_mismatch"
    ENCODING_INVALID = "encoding_invalid"
    SANITIZATION_FAILED = "sanitization_failed"
    INJECTION_DETECTED = "injection_detected"
    VALUE_OUT_OF_RANGE = "value_out_of_range"
    CUSTOM_VALIDATION = "custom_validation"


@dataclass
class ValidationError:
    """Single validation error."""
    error_type: ValidationErrorType
    field: str
    message: str
    expected: Optional[str] = None
    actual: Optional[str] = None
    severity: str = "error"  # error, warning


@dataclass
class ValidationResult:
    """Result of input validation."""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    sanitized_data: Optional[Dict[str, Any]] = None
    validated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def add_error(self, error: ValidationError):
        """Add an error to the result."""
        if error.severity == "warning":
            self.warnings.append(error)
        else:
            self.errors.append(error)
            self.valid = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "valid": self.valid,
            "errors": [asdict(e) for e in self.errors],
            "warnings": [asdict(w) for w in self.warnings],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "validated_at": self.validated_at
        }


@dataclass
class FieldSchema:
    """Schema for a single field."""
    name: str
    field_type: Type  # str, int, float, bool, list, dict
    required: bool = True
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    pattern: Optional[str] = None  # Regex pattern
    allowed_values: Optional[List[Any]] = None
    sanitize: bool = True
    custom_validator: Optional[Callable[[Any], Tuple[bool, str]]] = None


class InjectionDetector:
    """Detects potential injection attacks in input."""
    
    # SQL injection patterns
    SQL_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE)\b)",
        r"(--|;|'|\"|\\x00|\\n|\\r)",
        r"(\bOR\b\s*\b1\b\s*=\s*\b1\b)",
        r"(\bAND\b\s*\b1\b\s*=\s*\b1\b)",
        r"(\bUNION\b\s*\bSELECT\b)",
    ]
    
    # XSS patterns
    XSS_PATTERNS = [
        r"<script[^>]*>",
        r"javascript:",
        r"on\w+\s*=",
        r"<iframe[^>]*>",
        r"<object[^>]*>",
        r"<embed[^>]*>",
    ]
    
    # Command injection patterns
    COMMAND_PATTERNS = [
        r"[|;&`$]",
        r"\$\([^)]*\)",
        r"`[^`]*`",
        r">\s*/dev/",
    ]
    
    @classmethod
    def detect(cls, value: str, context: str = "general") -> Tuple[bool, List[str]]:
        """
        Detect potential injection attacks.
        
        Args:
            value: String value to check
            context: Context for detection (sql, html, command, general)
        
        Returns:
            (is_safe, list of detected patterns)
        """
        if not isinstance(value, str):
            return True, []
        
        detected = []
        
        # Check SQL injection
        if context in ["sql", "general"]:
            for pattern in cls.SQL_PATTERNS:
                if re.search(pattern, value, re.IGNORECASE):
                    detected.append(f"SQL injection pattern: {pattern}")
        
        # Check XSS
        if context in ["html", "general"]:
            for pattern in cls.XSS_PATTERNS:
                if re.search(pattern, value, re.IGNORECASE):
                    detected.append(f"XSS pattern: {pattern}")
        
        # Check command injection
        if context in ["command", "general"]:
            for pattern in cls.COMMAND_PATTERNS:
                if re.search(pattern, value):
                    detected.append(f"Command injection pattern: {pattern}")
        
        return len(detected) == 0, detected


class InputSanitizer:
    """Sanitizes input data."""
    
    @staticmethod
    def sanitize_string(value: str, 
                       strip: bool = True,
                       normalize_whitespace: bool = True,
                       escape_html: bool = True,
                       max_length: Optional[int] = None) -> str:
        """Sanitize a string value."""
        if not isinstance(value, str):
            return str(value)
        
        result = value
        
        # Strip leading/trailing whitespace
        if strip:
            result = result.strip()
        
        # Normalize internal whitespace
        if normalize_whitespace:
            result = re.sub(r'\s+', ' ', result)
        
        # Escape HTML entities
        if escape_html:
            result = html.escape(result)
        
        # Enforce max length
        if max_length and len(result) > max_length:
            result = result[:max_length]
        
        return result
    
    @staticmethod
    def sanitize_email(value: str) -> str:
        """Sanitize email address."""
        if not isinstance(value, str):
            return ""
        
        result = value.strip().lower()
        # Basic email normalization
        result = re.sub(r'\s+', '', result)
        return result
    
    @staticmethod
    def sanitize_phone(value: str) -> str:
        """Sanitize phone number - keep only digits and + for intl."""
        if not isinstance(value, str):
            return ""
        
        # Keep only digits and leading +
        result = re.sub(r'[^\d+]', '', value.strip())
        # Ensure + only at start
        if '+' in result[1:]:
            result = result[0] + result[1:].replace('+', '')
        return result
    
    @staticmethod
    def sanitize_url(value: str) -> str:
        """Sanitize URL."""
        if not isinstance(value, str):
            return ""
        
        result = value.strip()
        # Remove dangerous schemes
        if result.lower().startswith('javascript:'):
            return ""
        if result.lower().startswith('data:'):
            return ""
        return result


class InputValidator:
    """
    Layer 1: Input Validation
    
    Provides type checking, sanitization, length limits, and encoding validation.
    """
    
    # Default length limits by field type
    DEFAULT_LIMITS = {
        "email": {"min": 5, "max": 254},
        "name": {"min": 1, "max": 100},
        "title": {"min": 1, "max": 200},
        "description": {"min": 0, "max": 5000},
        "phone": {"min": 7, "max": 20},
        "url": {"min": 10, "max": 2048},
        "id": {"min": 1, "max": 64},
        "json_field": {"min": 0, "max": 50000},
        "default": {"min": 0, "max": 1000}
    }
    
    # Email pattern
    EMAIL_PATTERN = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    # URL pattern
    URL_PATTERN = r'^https?://[^\s<>\"\']+$'
    
    def __init__(self, 
                 strict_mode: bool = False,
                 sanitize_by_default: bool = True,
                 detect_injection: bool = True):
        """
        Initialize InputValidator.
        
        Args:
            strict_mode: If True, any warning becomes an error
            sanitize_by_default: If True, sanitize all string inputs
            detect_injection: If True, check for injection attacks
        """
        self.strict_mode = strict_mode
        self.sanitize_by_default = sanitize_by_default
        self.detect_injection = detect_injection
        self.sanitizer = InputSanitizer()
        
        logger.info(f"InputValidator initialized (strict={strict_mode})")
    
    def validate(self, 
                 data: Dict[str, Any], 
                 schema: Optional[List[FieldSchema]] = None,
                 field_limits: Optional[Dict[str, Dict[str, int]]] = None) -> ValidationResult:
        """
        Validate input data against schema.
        
        Args:
            data: Input data dictionary
            schema: List of field schemas (optional)
            field_limits: Custom field length limits (optional)
        
        Returns:
            ValidationResult with errors, warnings, and sanitized data
        """
        result = ValidationResult(valid=True)
        sanitized = {}
        
        if schema:
            # Schema-based validation
            for field_schema in schema:
                field_name = field_schema.name
                value = data.get(field_name)
                
                # Check required
                if field_schema.required and value is None:
                    result.add_error(ValidationError(
                        error_type=ValidationErrorType.REQUIRED_MISSING,
                        field=field_name,
                        message=f"Required field '{field_name}' is missing"
                    ))
                    continue
                
                if value is None:
                    sanitized[field_name] = None
                    continue
                
                # Validate and sanitize field
                field_result, sanitized_value = self._validate_field(
                    field_name, value, field_schema, field_limits
                )
                
                for error in field_result.errors:
                    result.add_error(error)
                for warning in field_result.warnings:
                    if self.strict_mode:
                        warning.severity = "error"
                        result.add_error(warning)
                    else:
                        result.warnings.append(warning)
                
                sanitized[field_name] = sanitized_value
        else:
            # Basic validation without schema
            for field_name, value in data.items():
                field_result, sanitized_value = self._validate_basic(
                    field_name, value, field_limits
                )
                
                for error in field_result.errors:
                    result.add_error(error)
                for warning in field_result.warnings:
                    result.warnings.append(warning)
                
                sanitized[field_name] = sanitized_value
        
        result.sanitized_data = sanitized
        return result
    
    def _validate_field(self, 
                        field_name: str, 
                        value: Any, 
                        schema: FieldSchema,
                        field_limits: Optional[Dict] = None) -> Tuple[ValidationResult, Any]:
        """Validate a single field against its schema."""
        result = ValidationResult(valid=True)
        sanitized = value
        
        # Type checking
        if not isinstance(value, schema.field_type):
            # Try type coercion
            try:
                if schema.field_type == str:
                    sanitized = str(value)
                elif schema.field_type == int:
                    sanitized = int(value)
                elif schema.field_type == float:
                    sanitized = float(value)
                elif schema.field_type == bool:
                    if isinstance(value, str):
                        sanitized = value.lower() in ('true', '1', 'yes')
                    else:
                        sanitized = bool(value)
                else:
                    raise ValueError("Cannot coerce")
            except (ValueError, TypeError):
                result.add_error(ValidationError(
                    error_type=ValidationErrorType.TYPE_MISMATCH,
                    field=field_name,
                    message=f"Expected {schema.field_type.__name__}, got {type(value).__name__}",
                    expected=schema.field_type.__name__,
                    actual=type(value).__name__
                ))
                return result, value
        
        # String-specific validation
        if schema.field_type == str and isinstance(sanitized, str):
            # Sanitize if enabled
            if schema.sanitize and self.sanitize_by_default:
                sanitized = self.sanitizer.sanitize_string(
                    sanitized, 
                    max_length=schema.max_length
                )
            
            # Encoding validation
            try:
                sanitized.encode('utf-8')
            except UnicodeEncodeError:
                result.add_error(ValidationError(
                    error_type=ValidationErrorType.ENCODING_INVALID,
                    field=field_name,
                    message="Invalid UTF-8 encoding"
                ))
            
            # Injection detection
            if self.detect_injection:
                is_safe, patterns = InjectionDetector.detect(sanitized)
                if not is_safe:
                    result.add_error(ValidationError(
                        error_type=ValidationErrorType.INJECTION_DETECTED,
                        field=field_name,
                        message=f"Potential injection detected: {patterns[0]}",
                        severity="error" if self.strict_mode else "warning"
                    ))
            
            # Length validation
            actual_len = len(sanitized)
            if schema.min_length and actual_len < schema.min_length:
                result.add_error(ValidationError(
                    error_type=ValidationErrorType.LENGTH_TOO_SHORT,
                    field=field_name,
                    message=f"Length {actual_len} is less than minimum {schema.min_length}",
                    expected=str(schema.min_length),
                    actual=str(actual_len)
                ))
            
            if schema.max_length and actual_len > schema.max_length:
                result.add_error(ValidationError(
                    error_type=ValidationErrorType.LENGTH_EXCEEDED,
                    field=field_name,
                    message=f"Length {actual_len} exceeds maximum {schema.max_length}",
                    expected=str(schema.max_length),
                    actual=str(actual_len)
                ))
            
            # Pattern validation
            if schema.pattern:
                if not re.match(schema.pattern, sanitized):
                    result.add_error(ValidationError(
                        error_type=ValidationErrorType.PATTERN_MISMATCH,
                        field=field_name,
                        message=f"Value does not match required pattern",
                        expected=schema.pattern
                    ))
        
        # Numeric validation
        if schema.field_type in (int, float) and isinstance(sanitized, (int, float)):
            if schema.min_value is not None and sanitized < schema.min_value:
                result.add_error(ValidationError(
                    error_type=ValidationErrorType.VALUE_OUT_OF_RANGE,
                    field=field_name,
                    message=f"Value {sanitized} is less than minimum {schema.min_value}",
                    expected=f">= {schema.min_value}",
                    actual=str(sanitized)
                ))
            
            if schema.max_value is not None and sanitized > schema.max_value:
                result.add_error(ValidationError(
                    error_type=ValidationErrorType.VALUE_OUT_OF_RANGE,
                    field=field_name,
                    message=f"Value {sanitized} exceeds maximum {schema.max_value}",
                    expected=f"<= {schema.max_value}",
                    actual=str(sanitized)
                ))
        
        # Allowed values
        if schema.allowed_values and sanitized not in schema.allowed_values:
            result.add_error(ValidationError(
                error_type=ValidationErrorType.VALUE_OUT_OF_RANGE,
                field=field_name,
                message=f"Value not in allowed values: {schema.allowed_values}",
                expected=str(schema.allowed_values),
                actual=str(sanitized)
            ))
        
        # Custom validator
        if schema.custom_validator:
            try:
                is_valid, message = schema.custom_validator(sanitized)
                if not is_valid:
                    result.add_error(ValidationError(
                        error_type=ValidationErrorType.CUSTOM_VALIDATION,
                        field=field_name,
                        message=message
                    ))
            except Exception as e:
                result.add_error(ValidationError(
                    error_type=ValidationErrorType.CUSTOM_VALIDATION,
                    field=field_name,
                    message=f"Custom validator error: {e}"
                ))
        
        return result, sanitized
    
    def _validate_basic(self, 
                        field_name: str, 
                        value: Any,
                        field_limits: Optional[Dict] = None) -> Tuple[ValidationResult, Any]:
        """Basic validation without schema."""
        result = ValidationResult(valid=True)
        sanitized = value
        
        if isinstance(value, str):
            # Determine limit type by field name
            limit_type = "default"
            field_lower = field_name.lower()
            
            if "email" in field_lower:
                limit_type = "email"
            elif "name" in field_lower or "first" in field_lower or "last" in field_lower:
                limit_type = "name"
            elif "title" in field_lower:
                limit_type = "title"
            elif "desc" in field_lower:
                limit_type = "description"
            elif "phone" in field_lower:
                limit_type = "phone"
            elif "url" in field_lower or "link" in field_lower:
                limit_type = "url"
            elif "id" in field_lower:
                limit_type = "id"
            
            # Get limits
            custom_limits = (field_limits or {}).get(field_name, {})
            limits = {**self.DEFAULT_LIMITS.get(limit_type, self.DEFAULT_LIMITS["default"]), **custom_limits}
            
            # Sanitize
            if self.sanitize_by_default:
                sanitized = self.sanitizer.sanitize_string(value, max_length=limits.get("max"))
            
            # Check length
            if len(sanitized) < limits.get("min", 0):
                result.add_error(ValidationError(
                    error_type=ValidationErrorType.LENGTH_TOO_SHORT,
                    field=field_name,
                    message=f"Too short (min: {limits['min']})"
                ))
            
            if len(sanitized) > limits.get("max", float('inf')):
                result.add_error(ValidationError(
                    error_type=ValidationErrorType.LENGTH_EXCEEDED,
                    field=field_name,
                    message=f"Too long (max: {limits['max']})"
                ))
            
            # Injection detection
            if self.detect_injection:
                is_safe, _ = InjectionDetector.detect(sanitized)
                if not is_safe:
                    result.add_error(ValidationError(
                        error_type=ValidationErrorType.INJECTION_DETECTED,
                        field=field_name,
                        message="Potential injection detected",
                        severity="warning"
                    ))
        
        return result, sanitized
    
    def validate_email(self, email: str) -> ValidationResult:
        """Validate email address."""
        result = ValidationResult(valid=True)
        
        if not email:
            result.add_error(ValidationError(
                error_type=ValidationErrorType.REQUIRED_MISSING,
                field="email",
                message="Email is required"
            ))
            return result
        
        sanitized = self.sanitizer.sanitize_email(email)
        
        if not re.match(self.EMAIL_PATTERN, sanitized):
            result.add_error(ValidationError(
                error_type=ValidationErrorType.PATTERN_MISMATCH,
                field="email",
                message="Invalid email format"
            ))
        
        result.sanitized_data = {"email": sanitized}
        return result
    
    def validate_json(self, json_str: str, max_size: int = 50000) -> ValidationResult:
        """Validate JSON string."""
        result = ValidationResult(valid=True)
        
        if len(json_str) > max_size:
            result.add_error(ValidationError(
                error_type=ValidationErrorType.LENGTH_EXCEEDED,
                field="json",
                message=f"JSON exceeds max size of {max_size}"
            ))
            return result
        
        try:
            parsed = json.loads(json_str)
            result.sanitized_data = parsed
        except json.JSONDecodeError as e:
            result.add_error(ValidationError(
                error_type=ValidationErrorType.ENCODING_INVALID,
                field="json",
                message=f"Invalid JSON: {e}"
            ))
        
        return result


# ============================================================================
# LAYER 2: CIRCUIT BREAKER (Enhanced Per-Agent)
# ============================================================================

@dataclass
class BackoffConfig:
    """Configuration for exponential backoff."""
    initial_delay: float = 1.0
    max_delay: float = 60.0
    multiplier: float = 2.0
    jitter: float = 0.1  # Random factor to prevent thundering herd


@dataclass
class AgentCircuitConfig:
    """Configuration for per-agent circuit breaker."""
    failure_threshold: int = 3
    recovery_timeout: int = 300  # 5 minutes (auto-reset)
    half_open_max_calls: int = 2
    backoff: BackoffConfig = field(default_factory=BackoffConfig)
    
    def get_backoff_delay(self, attempt: int) -> float:
        """Calculate backoff delay for given attempt number."""
        delay = self.backoff.initial_delay * (self.backoff.multiplier ** (attempt - 1))
        delay = min(delay, self.backoff.max_delay)
        
        # Add jitter
        import random
        jitter_range = delay * self.backoff.jitter
        delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0.1, delay)


class AgentCircuitBreaker:
    """
    Layer 2: Enhanced Per-Agent Circuit Breaker
    
    Wraps the base CircuitBreakerRegistry with:
    - Per-agent configuration
    - 3-failure trip (default)
    - Exponential backoff (1-60s)
    - Auto-reset after 5min
    - Half-open test before full recovery
    """
    
    # Default configs for all 12 agents
    DEFAULT_AGENT_CONFIGS = {
        "UNIFIED_QUEEN": AgentCircuitConfig(failure_threshold=5, recovery_timeout=180),
        "HUNTER": AgentCircuitConfig(failure_threshold=3, recovery_timeout=300),
        "ENRICHER": AgentCircuitConfig(failure_threshold=3, recovery_timeout=300),
        "SEGMENTOR": AgentCircuitConfig(failure_threshold=5, recovery_timeout=180),
        "CRAFTER": AgentCircuitConfig(failure_threshold=5, recovery_timeout=180),
        "GATEKEEPER": AgentCircuitConfig(failure_threshold=3, recovery_timeout=300),
        "SCOUT": AgentCircuitConfig(failure_threshold=3, recovery_timeout=300),
        "OPERATOR": AgentCircuitConfig(failure_threshold=3, recovery_timeout=300),
        "COACH": AgentCircuitConfig(failure_threshold=5, recovery_timeout=180),
        "PIPER": AgentCircuitConfig(failure_threshold=5, recovery_timeout=180),
        "SCHEDULER": AgentCircuitConfig(failure_threshold=3, recovery_timeout=300),
        "RESEARCHER": AgentCircuitConfig(failure_threshold=5, recovery_timeout=180),
        "COMMUNICATOR": AgentCircuitConfig(failure_threshold=3, recovery_timeout=300),
    }
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize per-agent circuit breaker system."""
        self.storage_dir = storage_dir or PROJECT_ROOT / ".hive-mind" / "failsafe"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Base registry for core circuit breaker functionality
        self._base_registry = get_base_registry()
        
        # Agent-specific tracking
        self._agent_attempts: Dict[str, int] = defaultdict(int)
        self._agent_last_attempt: Dict[str, datetime] = {}
        self._agent_configs: Dict[str, AgentCircuitConfig] = {}
        
        # Load configs
        self._load_configs()
        
        # Register agent breakers
        self._register_agent_breakers()
        
        logger.info(f"AgentCircuitBreaker initialized for {len(self.DEFAULT_AGENT_CONFIGS)} agents")
    
    def _load_configs(self):
        """Load agent configs from storage or use defaults."""
        config_file = self.storage_dir / "agent_circuit_configs.json"
        
        if config_file.exists():
            try:
                with open(config_file) as f:
                    data = json.load(f)
                for agent_name, config_data in data.items():
                    backoff = BackoffConfig(**config_data.get("backoff", {}))
                    self._agent_configs[agent_name] = AgentCircuitConfig(
                        failure_threshold=config_data.get("failure_threshold", 3),
                        recovery_timeout=config_data.get("recovery_timeout", 300),
                        half_open_max_calls=config_data.get("half_open_max_calls", 2),
                        backoff=backoff
                    )
            except Exception as e:
                logger.error(f"Failed to load configs: {e}")
        
        # Fill in defaults for missing agents
        for agent_name, default_config in self.DEFAULT_AGENT_CONFIGS.items():
            if agent_name not in self._agent_configs:
                self._agent_configs[agent_name] = default_config
    
    def _save_configs(self):
        """Save agent configs to storage."""
        config_file = self.storage_dir / "agent_circuit_configs.json"
        
        data = {}
        for agent_name, config in self._agent_configs.items():
            data[agent_name] = {
                "failure_threshold": config.failure_threshold,
                "recovery_timeout": config.recovery_timeout,
                "half_open_max_calls": config.half_open_max_calls,
                "backoff": asdict(config.backoff)
            }
        
        with open(config_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def _register_agent_breakers(self):
        """Register circuit breakers for all agents."""
        for agent_name, config in self._agent_configs.items():
            breaker_name = f"agent_{agent_name.lower()}"
            self._base_registry.register(
                name=breaker_name,
                failure_threshold=config.failure_threshold,
                recovery_timeout=config.recovery_timeout,
                half_open_max_calls=config.half_open_max_calls
            )
    
    def get_breaker_name(self, agent_name: str) -> str:
        """Get circuit breaker name for an agent."""
        return f"agent_{agent_name.lower()}"
    
    def is_available(self, agent_name: str) -> bool:
        """Check if agent's circuit is available (not open)."""
        breaker_name = self.get_breaker_name(agent_name)
        return self._base_registry.is_available(breaker_name)
    
    def record_success(self, agent_name: str):
        """Record successful agent operation."""
        breaker_name = self.get_breaker_name(agent_name)
        self._base_registry.record_success(breaker_name)
        
        # Reset attempt counter
        self._agent_attempts[agent_name] = 0
        
        logger.debug(f"Agent {agent_name} success recorded")
    
    def record_failure(self, agent_name: str, error: Optional[Exception] = None):
        """Record agent failure with backoff tracking."""
        breaker_name = self.get_breaker_name(agent_name)
        self._base_registry.record_failure(breaker_name, error)
        
        # Increment attempt counter
        self._agent_attempts[agent_name] += 1
        self._agent_last_attempt[agent_name] = datetime.now()
        
        logger.warning(f"Agent {agent_name} failure #{self._agent_attempts[agent_name]}")
    
    def get_backoff_delay(self, agent_name: str) -> float:
        """Get recommended backoff delay for agent."""
        config = self._agent_configs.get(agent_name, AgentCircuitConfig())
        attempts = self._agent_attempts.get(agent_name, 0)
        
        if attempts == 0:
            return 0.0
        
        return config.get_backoff_delay(attempts)
    
    def should_retry(self, agent_name: str) -> Tuple[bool, float]:
        """
        Check if agent should retry and get delay.
        
        Returns:
            (should_retry, delay_seconds)
        """
        if not self.is_available(agent_name):
            # Circuit is open
            time_until_retry = self._base_registry.get_time_until_retry(
                self.get_breaker_name(agent_name)
            )
            return False, time_until_retry or 0.0
        
        # Check if we should back off
        last_attempt = self._agent_last_attempt.get(agent_name)
        if last_attempt:
            elapsed = (datetime.now() - last_attempt).total_seconds()
            backoff = self.get_backoff_delay(agent_name)
            
            if elapsed < backoff:
                return True, backoff - elapsed
        
        return True, 0.0
    
    def get_agent_status(self, agent_name: str) -> Dict[str, Any]:
        """Get detailed status for an agent's circuit breaker."""
        breaker_name = self.get_breaker_name(agent_name)
        breaker = self._base_registry.get_breaker(breaker_name)
        
        if not breaker:
            return {"error": f"No breaker for agent {agent_name}"}
        
        config = self._agent_configs.get(agent_name, AgentCircuitConfig())
        
        return {
            "agent": agent_name,
            "breaker_name": breaker_name,
            "state": breaker.state.value,
            "failure_count": breaker.failure_count,
            "failure_threshold": config.failure_threshold,
            "recovery_timeout": config.recovery_timeout,
            "current_attempts": self._agent_attempts.get(agent_name, 0),
            "current_backoff": self.get_backoff_delay(agent_name),
            "is_available": self.is_available(agent_name),
            "time_until_retry": self._base_registry.get_time_until_retry(breaker_name)
        }
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all agent circuit breakers."""
        return {
            agent_name: self.get_agent_status(agent_name)
            for agent_name in self._agent_configs.keys()
        }
    
    def force_open(self, agent_name: str):
        """Manually open an agent's circuit."""
        breaker_name = self.get_breaker_name(agent_name)
        self._base_registry.force_open(breaker_name)
        logger.info(f"Manually opened circuit for {agent_name}")
    
    def force_close(self, agent_name: str):
        """Manually close (reset) an agent's circuit."""
        breaker_name = self.get_breaker_name(agent_name)
        self._base_registry.force_close(breaker_name)
        self._agent_attempts[agent_name] = 0
        logger.info(f"Manually closed circuit for {agent_name}")
    
    def update_config(self, agent_name: str, 
                      failure_threshold: Optional[int] = None,
                      recovery_timeout: Optional[int] = None,
                      backoff_initial: Optional[float] = None,
                      backoff_max: Optional[float] = None):
        """Update configuration for an agent."""
        if agent_name not in self._agent_configs:
            self._agent_configs[agent_name] = AgentCircuitConfig()
        
        config = self._agent_configs[agent_name]
        
        if failure_threshold is not None:
            config.failure_threshold = failure_threshold
        if recovery_timeout is not None:
            config.recovery_timeout = recovery_timeout
        if backoff_initial is not None:
            config.backoff.initial_delay = backoff_initial
        if backoff_max is not None:
            config.backoff.max_delay = backoff_max
        
        self._save_configs()
        
        # Re-register breaker with new config
        breaker_name = self.get_breaker_name(agent_name)
        breaker = self._base_registry.get_breaker(breaker_name)
        if breaker:
            breaker.failure_threshold = config.failure_threshold
            breaker.recovery_timeout_seconds = config.recovery_timeout
            breaker.half_open_max_calls = config.half_open_max_calls
        
        logger.info(f"Updated circuit config for {agent_name}")


# ============================================================================
# LAYER 3: FALLBACK CHAIN
# ============================================================================

class FallbackLevel(Enum):
    """Levels in the fallback chain."""
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"
    HUMAN_ESCALATION = "human_escalation"


@dataclass
class FallbackHandler:
    """A handler in the fallback chain."""
    name: str
    level: FallbackLevel
    handler: Callable
    timeout_seconds: float = 30.0
    enabled: bool = True
    success_count: int = 0
    failure_count: int = 0
    last_used: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "level": self.level.value,
            "enabled": self.enabled,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "timeout_seconds": self.timeout_seconds,
            "last_used": self.last_used.isoformat() if self.last_used else None
        }


@dataclass
class FallbackActivation:
    """Record of a fallback activation."""
    activation_id: str
    agent_name: str
    operation: str
    primary_error: str
    level_activated: Union[FallbackLevel, str]
    handler_used: str
    success: bool
    duration_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def __post_init__(self):
        """Ensure level_activated is a FallbackLevel enum."""
        if isinstance(self.level_activated, str):
            self.level_activated = FallbackLevel(self.level_activated)
    
    def to_dict(self) -> Dict[str, Any]:
        level_value = self.level_activated.value if isinstance(self.level_activated, FallbackLevel) else self.level_activated
        return {
            "activation_id": self.activation_id,
            "agent_name": self.agent_name,
            "operation": self.operation,
            "primary_error": self.primary_error,
            "level_activated": level_value,
            "handler_used": self.handler_used,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp
        }



class FallbackChain:
    """
    Layer 3: Fallback Chain
    
    Implements: primary → secondary → tertiary → human escalation
    Logs all activations for audit and self-annealing.
    
    Features:
    - Priority-ordered fallback handlers
    - Timeout per handler
    - Activation logging
    - Success/failure tracking per handler
    - Human escalation as last resort
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or PROJECT_ROOT / ".hive-mind" / "failsafe" / "fallback"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Handlers by agent and operation
        self._chains: Dict[str, Dict[str, List[FallbackHandler]]] = defaultdict(lambda: defaultdict(list))
        
        # Activation log
        self._activations: List[FallbackActivation] = []
        
        # Human escalation queue
        self._escalation_queue: List[Dict[str, Any]] = []
        
        # Load persisted state
        self._load_state()
        
        logger.info("FallbackChain initialized")
    
    def _load_state(self):
        """Load persisted activation log."""
        log_file = self.storage_dir / "activations.json"
        if log_file.exists():
            try:
                with open(log_file) as f:
                    data = json.load(f)
                # Keep last 1000 activations
                self._activations = [
                    FallbackActivation(**a) 
                    for a in data.get("activations", [])[-1000:]
                ]
            except Exception as e:
                logger.error(f"Failed to load fallback state: {e}")
    
    def _save_state(self):
        """Persist activation log."""
        log_file = self.storage_dir / "activations.json"
        data = {
            "activations": [a.to_dict() for a in self._activations[-1000:]],
            "updated_at": datetime.now().isoformat()
        }
        with open(log_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def register_handler(self, 
                        agent_name: str, 
                        operation: str,
                        handler: Callable,
                        level: FallbackLevel = FallbackLevel.SECONDARY,
                        name: Optional[str] = None,
                        timeout: float = 30.0):
        """
        Register a fallback handler for an agent operation.
        
        Args:
            agent_name: Name of the agent
            operation: Operation name
            handler: Async callable to handle fallback
            level: Fallback level (SECONDARY, TERTIARY, or HUMAN_ESCALATION)
            name: Handler name (auto-generated if not provided)
            timeout: Timeout in seconds
        """
        handler_name = name or f"{agent_name}_{operation}_{level.value}"
        
        fallback = FallbackHandler(
            name=handler_name,
            level=level,
            handler=handler,
            timeout_seconds=timeout
        )
        
        # Insert in order by level
        chain = self._chains[agent_name][operation]
        chain.append(fallback)
        chain.sort(key=lambda h: list(FallbackLevel).index(h.level))
        
        logger.info(f"Registered fallback handler: {handler_name} at {level.value}")
    
    def register_human_escalation(self,
                                  agent_name: str,
                                  operation: str,
                                  escalation_handler: Optional[Callable] = None):
        """
        Register human escalation as the final fallback.
        
        Args:
            agent_name: Name of the agent
            operation: Operation name
            escalation_handler: Custom handler (default: queue for human review)
        """
        async def default_escalation(**kwargs):
            """Default: Queue for human review."""
            self._escalation_queue.append({
                "agent": agent_name,
                "operation": operation,
                "data": kwargs,
                "queued_at": datetime.now().isoformat(),
                "status": "pending"
            })
            self._save_escalation_queue()
            return {"escalated": True, "queue_position": len(self._escalation_queue)}
        
        handler = escalation_handler or default_escalation
        self.register_handler(
            agent_name, 
            operation, 
            handler,
            level=FallbackLevel.HUMAN_ESCALATION,
            name=f"{agent_name}_{operation}_human_escalation",
            timeout=60.0  # Longer timeout for human escalation
        )
    
    def _save_escalation_queue(self):
        """Save escalation queue to disk."""
        queue_file = self.storage_dir / "escalation_queue.json"
        with open(queue_file, "w") as f:
            json.dump({
                "queue": self._escalation_queue,
                "updated_at": datetime.now().isoformat()
            }, f, indent=2)
    
    async def execute_with_fallback(self,
                                   agent_name: str,
                                   operation: str,
                                   primary_handler: Callable,
                                   **kwargs) -> Dict[str, Any]:
        """
        Execute operation with fallback chain.
        
        Args:
            agent_name: Name of the agent
            operation: Operation name
            primary_handler: Primary async callable
            **kwargs: Arguments for handlers
        
        Returns:
            Result dict with success/error and handler used
        """
        start_time = datetime.now()
        activation_id = hashlib.md5(
            f"{agent_name}_{operation}_{start_time.isoformat()}".encode()
        ).hexdigest()[:12]
        
        result = {
            "success": False,
            "agent": agent_name,
            "operation": operation,
            "activation_id": activation_id,
            "handler_used": "primary",
            "fallback_activated": False
        }
        
        # Try primary handler
        try:
            if asyncio.iscoroutinefunction(primary_handler):
                primary_result = await asyncio.wait_for(
                    primary_handler(**kwargs),
                    timeout=30.0
                )
            else:
                primary_result = primary_handler(**kwargs)
            
            result["success"] = True
            result["result"] = primary_result
            return result
            
        except asyncio.TimeoutError as e:
            primary_error = "Primary handler timeout"
            logger.warning(f"[FallbackChain] {agent_name}/{operation}: {primary_error}")
        except Exception as e:
            primary_error = str(e)
            logger.warning(f"[FallbackChain] {agent_name}/{operation}: Primary failed - {e}")
        
        # Primary failed, try fallback chain
        result["fallback_activated"] = True
        result["primary_error"] = primary_error
        
        chain = self._chains.get(agent_name, {}).get(operation, [])
        
        for handler in chain:
            if not handler.enabled:
                continue
            
            try:
                logger.info(f"[FallbackChain] Trying {handler.level.value}: {handler.name}")
                
                if asyncio.iscoroutinefunction(handler.handler):
                    handler_result = await asyncio.wait_for(
                        handler.handler(**kwargs),
                        timeout=handler.timeout_seconds
                    )
                else:
                    handler_result = handler.handler(**kwargs)
                
                # Success
                handler.success_count += 1
                handler.last_used = datetime.now()
                
                result["success"] = True
                result["result"] = handler_result
                result["handler_used"] = handler.name
                result["level_used"] = handler.level.value
                
                # Log activation
                duration = (datetime.now() - start_time).total_seconds() * 1000
                self._log_activation(
                    activation_id, agent_name, operation, primary_error,
                    handler.level, handler.name, True, duration
                )
                
                return result
                
            except asyncio.TimeoutError:
                handler.failure_count += 1
                logger.warning(f"[FallbackChain] {handler.name} timeout")
            except Exception as e:
                handler.failure_count += 1
                logger.warning(f"[FallbackChain] {handler.name} failed: {e}")
        
        # All fallbacks failed
        duration = (datetime.now() - start_time).total_seconds() * 1000
        self._log_activation(
            activation_id, agent_name, operation, primary_error,
            FallbackLevel.HUMAN_ESCALATION, "none", False, duration
        )
        
        result["error"] = "All fallback handlers failed"
        return result
    
    def _log_activation(self, activation_id: str, agent_name: str, operation: str,
                       primary_error: str, level: FallbackLevel, handler: str,
                       success: bool, duration_ms: float):
        """Log a fallback activation."""
        activation = FallbackActivation(
            activation_id=activation_id,
            agent_name=agent_name,
            operation=operation,
            primary_error=primary_error,
            level_activated=level,
            handler_used=handler,
            success=success,
            duration_ms=duration_ms
        )
        self._activations.append(activation)
        self._save_state()
        
        logger.info(f"[FallbackChain] Activation logged: {activation_id} "
                   f"level={level.value} success={success}")
    
    def get_activation_stats(self) -> Dict[str, Any]:
        """Get statistics on fallback activations."""
        if not self._activations:
            return {"total": 0}
        
        total = len(self._activations)
        successful = sum(1 for a in self._activations if a.success)
        
        by_level = defaultdict(int)
        by_agent = defaultdict(int)
        
        for a in self._activations:
            level_value = a.level_activated.value if isinstance(a.level_activated, FallbackLevel) else a.level_activated
            by_level[level_value] += 1
            by_agent[a.agent_name] += 1
        
        return {
            "total_activations": total,
            "successful": successful,
            "success_rate": successful / total if total > 0 else 0,
            "by_level": dict(by_level),
            "by_agent": dict(by_agent),
            "escalation_queue_size": len(self._escalation_queue)
        }
    
    def get_pending_escalations(self) -> List[Dict[str, Any]]:
        """Get pending human escalations."""
        return [e for e in self._escalation_queue if e.get("status") == "pending"]
    
    def resolve_escalation(self, index: int, resolution: str, resolved_by: str):
        """Mark an escalation as resolved."""
        if 0 <= index < len(self._escalation_queue):
            self._escalation_queue[index]["status"] = "resolved"
            self._escalation_queue[index]["resolution"] = resolution
            self._escalation_queue[index]["resolved_by"] = resolved_by
            self._escalation_queue[index]["resolved_at"] = datetime.now().isoformat()
            self._save_escalation_queue()


# ============================================================================
# LAYER 4: BYZANTINE CONSENSUS
# ============================================================================

class ConsensusVote(Enum):
    """Types of consensus votes."""
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


@dataclass
class VoteRecord:
    """Record of a single vote."""
    voter: str
    vote: ConsensusVote
    weight: float
    reason: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ConsensusRound:
    """A single round of consensus voting."""
    round_number: int
    votes: List[VoteRecord] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    result: Optional[ConsensusVote] = None
    total_weight: float = 0.0
    approve_weight: float = 0.0
    reject_weight: float = 0.0


@dataclass
class ConsensusSession:
    """A complete consensus session."""
    session_id: str
    action_type: str
    action_data: Dict[str, Any]
    required_agreement: float  # e.g., 0.67 for 2/3
    max_rounds: int
    rounds: List[ConsensusRound] = field(default_factory=list)
    final_result: Optional[ConsensusVote] = None
    escalated: bool = False
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "action_type": self.action_type,
            "required_agreement": self.required_agreement,
            "max_rounds": self.max_rounds,
            "rounds": len(self.rounds),
            "final_result": self.final_result.value if self.final_result else None,
            "escalated": self.escalated,
            "started_at": self.started_at,
            "completed_at": self.completed_at
        }


class ByzantineConsensus:
    """
    Layer 4: Byzantine Consensus
    
    Implements fault-tolerant consensus for critical decisions.
    
    Features:
    - 2/3 agreement required for approval
    - Queen gets 3x voting weight
    - Maximum 3 rounds of voting
    - Escalation to human if no consensus
    - Audit trail of all votes
    """
    
    # Agent voting weights (Queen gets 3x)
    AGENT_WEIGHTS = {
        "UNIFIED_QUEEN": 3.0,
        "HUNTER": 1.0,
        "ENRICHER": 1.0,
        "SEGMENTOR": 1.0,
        "CRAFTER": 1.0,
        "GATEKEEPER": 1.0,
        "SCOUT": 1.0,
        "OPERATOR": 1.0,
        "COACH": 1.0,
        "PIPER": 1.0,
        "SCHEDULER": 1.0,
        "RESEARCHER": 1.0,
        "COMMUNICATOR": 1.0,
    }
    
    # Default required agreement (2/3)
    DEFAULT_AGREEMENT = 0.67
    
    # Maximum rounds before escalation
    MAX_ROUNDS = 3
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or PROJECT_ROOT / ".hive-mind" / "failsafe" / "consensus"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Active sessions
        self._sessions: Dict[str, ConsensusSession] = {}
        
        # Completed sessions (audit trail)
        self._history: List[ConsensusSession] = []
        
        # Escalation callback
        self._escalation_handler: Optional[Callable] = None
        
        # Load history
        self._load_history()
        
        logger.info("ByzantineConsensus initialized")
    
    def _load_history(self):
        """Load consensus history."""
        history_file = self.storage_dir / "consensus_history.json"
        if history_file.exists():
            try:
                with open(history_file) as f:
                    data = json.load(f)
                # Keep last 500 sessions
                for session_data in data.get("sessions", [])[-500:]:
                    self._history.append(ConsensusSession(
                        session_id=session_data["session_id"],
                        action_type=session_data["action_type"],
                        action_data=session_data.get("action_data", {}),
                        required_agreement=session_data.get("required_agreement", 0.67),
                        max_rounds=session_data.get("max_rounds", 3),
                        final_result=ConsensusVote(session_data["final_result"]) if session_data.get("final_result") else None,
                        escalated=session_data.get("escalated", False),
                        started_at=session_data.get("started_at", ""),
                        completed_at=session_data.get("completed_at")
                    ))
            except Exception as e:
                logger.error(f"Failed to load consensus history: {e}")
    
    def _save_history(self):
        """Save consensus history."""
        history_file = self.storage_dir / "consensus_history.json"
        sessions = []
        for s in self._history[-500:]:
            sessions.append({
                **s.to_dict(),
                "action_data": s.action_data
            })
        
        with open(history_file, "w") as f:
            json.dump({
                "sessions": sessions,
                "updated_at": datetime.now().isoformat()
            }, f, indent=2)
    
    def set_escalation_handler(self, handler: Callable):
        """Set the handler for consensus escalation."""
        self._escalation_handler = handler
    
    def start_session(self,
                     action_type: str,
                     action_data: Dict[str, Any],
                     required_agreement: float = None,
                     max_rounds: int = None) -> str:
        """
        Start a new consensus session.
        
        Args:
            action_type: Type of action requiring consensus
            action_data: Data about the action
            required_agreement: Fraction required (default 0.67)
            max_rounds: Maximum voting rounds (default 3)
        
        Returns:
            Session ID
        """
        session_id = hashlib.md5(
            f"{action_type}_{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]
        
        session = ConsensusSession(
            session_id=session_id,
            action_type=action_type,
            action_data=action_data,
            required_agreement=required_agreement or self.DEFAULT_AGREEMENT,
            max_rounds=max_rounds or self.MAX_ROUNDS
        )
        
        self._sessions[session_id] = session
        
        logger.info(f"[ByzantineConsensus] Started session {session_id} for {action_type}")
        return session_id
    
    def cast_vote(self,
                  session_id: str,
                  voter: str,
                  vote: ConsensusVote,
                  reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Cast a vote in a consensus session.
        
        Args:
            session_id: Session ID
            voter: Agent name
            vote: APPROVE, REJECT, or ABSTAIN
            reason: Optional reason for vote
        
        Returns:
            Result dict with current state
        """
        session = self._sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        
        if session.final_result is not None:
            return {"success": False, "error": "Session already completed"}
        
        # Get or create current round
        if not session.rounds:
            session.rounds.append(ConsensusRound(round_number=1))
        
        current_round = session.rounds[-1]
        
        # Check if voter already voted this round
        if any(v.voter == voter for v in current_round.votes):
            return {"success": False, "error": "Already voted this round"}
        
        # Get voter weight
        weight = self.AGENT_WEIGHTS.get(voter, 1.0)
        
        # Record vote
        vote_record = VoteRecord(
            voter=voter,
            vote=vote,
            weight=weight,
            reason=reason
        )
        current_round.votes.append(vote_record)
        current_round.total_weight += weight
        
        if vote == ConsensusVote.APPROVE:
            current_round.approve_weight += weight
        elif vote == ConsensusVote.REJECT:
            current_round.reject_weight += weight
        
        logger.info(f"[ByzantineConsensus] {voter} voted {vote.value} "
                   f"(weight={weight}) in session {session_id}")
        
        return {
            "success": True,
            "session_id": session_id,
            "round": current_round.round_number,
            "votes_cast": len(current_round.votes),
            "total_weight": current_round.total_weight,
            "approve_weight": current_round.approve_weight,
            "reject_weight": current_round.reject_weight
        }
    
    async def finalize_round(self, session_id: str) -> Dict[str, Any]:
        """
        Finalize the current voting round and check for consensus.
        
        Args:
            session_id: Session ID
        
        Returns:
            Result with consensus outcome or next steps
        """
        session = self._sessions.get(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        
        if not session.rounds:
            return {"success": False, "error": "No votes cast"}
        
        current_round = session.rounds[-1]
        current_round.completed_at = datetime.now().isoformat()
        
        total = current_round.total_weight
        approve = current_round.approve_weight
        reject = current_round.reject_weight
        
        result = {
            "session_id": session_id,
            "round": current_round.round_number,
            "total_weight": total,
            "approve_weight": approve,
            "reject_weight": reject,
            "approve_ratio": approve / total if total > 0 else 0,
            "reject_ratio": reject / total if total > 0 else 0,
            "required_agreement": session.required_agreement
        }
        
        # Check for consensus
        approve_ratio = approve / total if total > 0 else 0
        reject_ratio = reject / total if total > 0 else 0
        
        if approve_ratio >= session.required_agreement:
            # Consensus reached: APPROVE
            current_round.result = ConsensusVote.APPROVE
            session.final_result = ConsensusVote.APPROVE
            session.completed_at = datetime.now().isoformat()
            
            result["consensus_reached"] = True
            result["final_result"] = "approve"
            
            self._complete_session(session)
            
        elif reject_ratio >= session.required_agreement:
            # Consensus reached: REJECT
            current_round.result = ConsensusVote.REJECT
            session.final_result = ConsensusVote.REJECT
            session.completed_at = datetime.now().isoformat()
            
            result["consensus_reached"] = True
            result["final_result"] = "reject"
            
            self._complete_session(session)
            
        elif current_round.round_number >= session.max_rounds:
            # Max rounds reached, escalate
            session.escalated = True
            session.completed_at = datetime.now().isoformat()
            
            result["consensus_reached"] = False
            result["escalated"] = True
            
            # Trigger escalation
            await self._escalate(session)
            self._complete_session(session)
            
        else:
            # No consensus, start new round
            new_round = ConsensusRound(round_number=current_round.round_number + 1)
            session.rounds.append(new_round)
            
            result["consensus_reached"] = False
            result["next_round"] = new_round.round_number
        
        logger.info(f"[ByzantineConsensus] Round {current_round.round_number} finalized: "
                   f"approve={approve_ratio:.2f} reject={reject_ratio:.2f}")
        
        return result
    
    async def _escalate(self, session: ConsensusSession):
        """Handle escalation when no consensus reached."""
        logger.warning(f"[ByzantineConsensus] Escalating session {session.session_id} - "
                      f"no consensus after {len(session.rounds)} rounds")
        
        if self._escalation_handler:
            try:
                await self._escalation_handler(session)
            except Exception as e:
                logger.error(f"[ByzantineConsensus] Escalation handler error: {e}")
        else:
            # Default: Save to escalation file
            escalation_file = self.storage_dir / "escalations.json"
            escalations = []
            if escalation_file.exists():
                with open(escalation_file) as f:
                    escalations = json.load(f).get("escalations", [])
            
            escalations.append({
                "session_id": session.session_id,
                "action_type": session.action_type,
                "action_data": session.action_data,
                "rounds": len(session.rounds),
                "timestamp": datetime.now().isoformat(),
                "status": "pending"
            })
            
            with open(escalation_file, "w") as f:
                json.dump({"escalations": escalations}, f, indent=2)
    
    def _complete_session(self, session: ConsensusSession):
        """Move session to history."""
        if session.session_id in self._sessions:
            del self._sessions[session.session_id]
        
        self._history.append(session)
        self._save_history()
    
    async def quick_vote(self,
                        action_type: str,
                        action_data: Dict[str, Any],
                        voters: List[Tuple[str, ConsensusVote]]) -> Dict[str, Any]:
        """
        Quick consensus with all votes provided at once.
        
        Args:
            action_type: Type of action
            action_data: Action data
            voters: List of (agent_name, vote) tuples
        
        Returns:
            Consensus result
        """
        session_id = self.start_session(action_type, action_data)
        
        for voter, vote in voters:
            self.cast_vote(session_id, voter, vote)
        
        return await self.finalize_round(session_id)
    
    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """Get status of a consensus session."""
        session = self._sessions.get(session_id)
        if not session:
            # Check history
            for s in self._history:
                if s.session_id == session_id:
                    return {**s.to_dict(), "status": "completed"}
            return {"error": "Session not found"}
        
        current_round = session.rounds[-1] if session.rounds else None
        
        return {
            **session.to_dict(),
            "status": "active",
            "current_round": current_round.round_number if current_round else 0,
            "votes_this_round": len(current_round.votes) if current_round else 0
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get consensus system statistics."""
        total = len(self._history)
        if total == 0:
            return {"total_sessions": 0}
        
        approved = sum(1 for s in self._history if s.final_result == ConsensusVote.APPROVE)
        rejected = sum(1 for s in self._history if s.final_result == ConsensusVote.REJECT)
        escalated = sum(1 for s in self._history if s.escalated)
        
        return {
            "total_sessions": total,
            "approved": approved,
            "rejected": rejected,
            "escalated": escalated,
            "approval_rate": approved / total if total > 0 else 0,
            "escalation_rate": escalated / total if total > 0 else 0,
            "active_sessions": len(self._sessions)
        }


# ============================================================================
# FAILSAFE LAYER MANAGER
# ============================================================================

class FailsafeLayer(Enum):
    """Available failsafe layers."""
    INPUT_VALIDATION = 1
    CIRCUIT_BREAKER = 2
    FALLBACK_CHAIN = 3
    BYZANTINE_CONSENSUS = 4


class MultiLayerFailsafe:
    """
    Multi-Layer Failsafe System
    
    Coordinates all failsafe layers for comprehensive protection.
    
    Layers:
    1. Input Validation - Type checking, sanitization, injection detection
    2. Circuit Breaker - Per-agent with backoff and auto-reset
    3. Fallback Chain - Primary → Secondary → Human escalation
    4. Byzantine Consensus - 2/3 agreement voting for critical decisions
    """
    
    _instance: Optional['MultiLayerFailsafe'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        
        # Layer 1: Input Validation
        self.input_validator = InputValidator(
            strict_mode=False,
            sanitize_by_default=True,
            detect_injection=True
        )
        
        # Layer 2: Circuit Breaker
        self.circuit_breaker = AgentCircuitBreaker()
        
        # Layer 3: Fallback Chain
        self.fallback_chain = FallbackChain()
        
        # Layer 4: Byzantine Consensus
        self.byzantine_consensus = ByzantineConsensus()
        
        # Metrics
        self._metrics = {
            "layer1_validations": 0,
            "layer1_failures": 0,
            "layer2_checks": 0,
            "layer2_trips": 0,
            "layer3_activations": 0,
            "layer3_escalations": 0,
            "layer4_sessions": 0,
            "layer4_escalations": 0,
            "total_executions": 0,
            "blocked_executions": 0
        }
        
        logger.info("MultiLayerFailsafe initialized (all 4 layers)")
    
    async def execute_with_failsafe(
        self,
        agent_name: str,
        operation: Callable,
        input_data: Optional[Dict[str, Any]] = None,
        input_schema: Optional[List[FieldSchema]] = None,
        layers: List[int] = None,
        fallback: Optional[Callable] = None,
        operation_name: Optional[str] = None,
        require_consensus: bool = False,
        consensus_voters: Optional[List[Tuple[str, ConsensusVote]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute an operation with multi-layer failsafe protection.
        
        Args:
            agent_name: Name of the agent executing
            operation: Async callable to execute
            input_data: Input data to validate
            input_schema: Schema for input validation
            layers: List of layer numbers to apply (default: [1, 2])
            fallback: Fallback function if execution fails
            operation_name: Name of the operation (for fallback chain)
            require_consensus: If True, requires Byzantine consensus (Layer 4)
            consensus_voters: List of (agent, vote) for quick consensus
            **kwargs: Additional arguments for the operation
        
        Returns:
            Result dictionary with success/error status
        """
        layers = layers or [1, 2]
        operation_name = operation_name or operation.__name__ if hasattr(operation, '__name__') else "operation"
        self._metrics["total_executions"] += 1
        
        result = {
            "success": False,
            "agent": agent_name,
            "layers_applied": layers,
            "started_at": datetime.now().isoformat()
        }
        
        # Layer 1: Input Validation
        if 1 in layers and input_data:
            self._metrics["layer1_validations"] += 1
            
            validation = self.input_validator.validate(input_data, input_schema)
            
            if not validation.valid:
                self._metrics["layer1_failures"] += 1
                self._metrics["blocked_executions"] += 1
                
                result["error"] = "Input validation failed"
                result["validation_errors"] = [asdict(e) for e in validation.errors]
                result["layer_blocked"] = 1
                
                logger.warning(f"Layer 1 blocked {agent_name}: validation failed")
                return result
            
            # Use sanitized data
            input_data = validation.sanitized_data
            result["input_sanitized"] = True
        
        # Layer 2: Circuit Breaker
        if 2 in layers:
            self._metrics["layer2_checks"] += 1
            
            if not self.circuit_breaker.is_available(agent_name):
                self._metrics["layer2_trips"] += 1
                self._metrics["blocked_executions"] += 1
                
                status = self.circuit_breaker.get_agent_status(agent_name)
                
                result["error"] = f"Circuit breaker OPEN for {agent_name}"
                result["circuit_status"] = status
                result["layer_blocked"] = 2
                
                # Try Layer 3 fallback chain if available
                if 3 in layers and self.fallback_chain:
                    self._metrics["layer3_activations"] += 1
                    fallback_result = await self.fallback_chain.execute_with_fallback(
                        agent_name, operation_name, operation,
                        input_data=input_data, **kwargs
                    )
                    if fallback_result.get("success"):
                        result["success"] = True
                        result["result"] = fallback_result.get("result")
                        result["fallback_chain_used"] = True
                        result["fallback_handler"] = fallback_result.get("handler_used")
                        return result
                
                # Try simple fallback if provided
                if fallback:
                    try:
                        fallback_result = await fallback(**kwargs) if asyncio.iscoroutinefunction(fallback) else fallback(**kwargs)
                        result["fallback_used"] = True
                        result["fallback_result"] = fallback_result
                    except Exception as e:
                        result["fallback_error"] = str(e)
                
                logger.warning(f"Layer 2 blocked {agent_name}: circuit open")
                return result
            
            # Check backoff
            should_retry, delay = self.circuit_breaker.should_retry(agent_name)
            if delay > 0:
                logger.info(f"Backing off {agent_name} for {delay:.1f}s")
                await asyncio.sleep(delay)
        
        # Layer 4: Byzantine Consensus (if required)
        if 4 in layers and require_consensus:
            self._metrics["layer4_sessions"] += 1
            
            if consensus_voters:
                consensus_result = await self.byzantine_consensus.quick_vote(
                    operation_name,
                    {"agent": agent_name, "input_data": input_data, **kwargs},
                    consensus_voters
                )
            else:
                # Start a session and wait for votes
                session_id = self.byzantine_consensus.start_session(
                    operation_name,
                    {"agent": agent_name, "input_data": input_data, **kwargs}
                )
                result["consensus_session_id"] = session_id
                result["error"] = "Awaiting consensus votes"
                result["layer_blocked"] = 4
                return result
            
            if not consensus_result.get("consensus_reached"):
                self._metrics["layer4_escalations"] += 1
                result["error"] = "Consensus not reached"
                result["consensus_result"] = consensus_result
                result["layer_blocked"] = 4
                return result
            
            if consensus_result.get("final_result") == "reject":
                result["error"] = "Consensus rejected operation"
                result["consensus_result"] = consensus_result
                result["layer_blocked"] = 4
                return result
            
            result["consensus_approved"] = True
        
        # Execute operation (with Layer 3 fallback chain if enabled)
        if 3 in layers:
            self._metrics["layer3_activations"] += 1
            
            fallback_result = await self.fallback_chain.execute_with_fallback(
                agent_name, operation_name, operation,
                input_data=input_data, **kwargs
            )
            
            if fallback_result.get("success"):
                # Record success for circuit breaker
                if 2 in layers:
                    self.circuit_breaker.record_success(agent_name)
                
                result["success"] = True
                result["result"] = fallback_result.get("result")
                result["handler_used"] = fallback_result.get("handler_used")
                if fallback_result.get("fallback_activated"):
                    result["fallback_chain_used"] = True
                result["completed_at"] = datetime.now().isoformat()
            else:
                # All handlers failed
                if 2 in layers:
                    self.circuit_breaker.record_failure(agent_name, Exception(fallback_result.get("error", "Unknown")))
                
                self._metrics["layer3_escalations"] += 1
                result["error"] = fallback_result.get("error", "All handlers failed")
                result["fallback_chain_exhausted"] = True
                result["completed_at"] = datetime.now().isoformat()
            
            return result
        
        # Direct execution (without Layer 3)
        try:
            if input_data:
                op_result = await operation(input_data, **kwargs) if asyncio.iscoroutinefunction(operation) else operation(input_data, **kwargs)
            else:
                op_result = await operation(**kwargs) if asyncio.iscoroutinefunction(operation) else operation(**kwargs)
            
            # Record success for circuit breaker
            if 2 in layers:
                self.circuit_breaker.record_success(agent_name)
            
            result["success"] = True
            result["result"] = op_result
            result["completed_at"] = datetime.now().isoformat()
            
        except Exception as e:
            # Record failure for circuit breaker
            if 2 in layers:
                self.circuit_breaker.record_failure(agent_name, e)
            
            result["error"] = str(e)
            result["error_type"] = type(e).__name__
            result["completed_at"] = datetime.now().isoformat()
            
            # Try fallback
            if fallback:
                try:
                    fallback_result = await fallback(**kwargs) if asyncio.iscoroutinefunction(fallback) else fallback(**kwargs)
                    result["fallback_used"] = True
                    result["fallback_result"] = fallback_result
                except Exception as fe:
                    result["fallback_error"] = str(fe)
            
            logger.error(f"Operation failed for {agent_name}: {e}")
        
        return result
    
    def register_fallback(self, agent_name: str, operation: str, 
                         handler: Callable, level: FallbackLevel = FallbackLevel.SECONDARY,
                         name: str = None, timeout: float = 30.0):
        """Register a fallback handler for an agent operation."""
        self.fallback_chain.register_handler(
            agent_name, operation, handler, level, name, timeout
        )
    
    def register_human_escalation(self, agent_name: str, operation: str):
        """Register human escalation for an operation."""
        self.fallback_chain.register_human_escalation(agent_name, operation)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get failsafe system metrics."""
        metrics = {
            **self._metrics,
            "circuit_breaker_status": self.circuit_breaker.get_all_status(),
            "layers_available": [1, 2, 3, 4],
            "timestamp": datetime.now().isoformat()
        }
        
        # Add Layer 3 stats
        if self.fallback_chain:
            metrics["layer3_stats"] = self.fallback_chain.get_activation_stats()
        
        # Add Layer 4 stats
        if self.byzantine_consensus:
            metrics["layer4_stats"] = self.byzantine_consensus.get_stats()
        
        return metrics
    
    def reset_metrics(self):
        """Reset metrics counters."""
        for key in self._metrics:
            self._metrics[key] = 0



# ============================================================================
# DECORATORS
# ============================================================================

def validate_input(schema: List[FieldSchema] = None, 
                   strict: bool = False):
    """
    Decorator to validate input data before function execution.
    
    Usage:
        @validate_input(schema=[
            FieldSchema("email", str, required=True, pattern=r"^..."),
            FieldSchema("name", str, max_length=100)
        ])
        async def create_contact(data: dict): ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Find input data in args or kwargs
            data = kwargs.get('data') or kwargs.get('input_data') or (args[0] if args else {})
            
            if not isinstance(data, dict):
                data = {}
            
            validator = InputValidator(strict_mode=strict)
            result = validator.validate(data, schema)
            
            if not result.valid:
                return {
                    "success": False,
                    "error": "Validation failed",
                    "errors": [asdict(e) for e in result.errors]
                }
            
            # Replace data with sanitized version
            if 'data' in kwargs:
                kwargs['data'] = result.sanitized_data
            elif 'input_data' in kwargs:
                kwargs['input_data'] = result.sanitized_data
            elif args:
                args = (result.sanitized_data,) + args[1:]
            
            return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            data = kwargs.get('data') or kwargs.get('input_data') or (args[0] if args else {})
            
            if not isinstance(data, dict):
                data = {}
            
            validator = InputValidator(strict_mode=strict)
            result = validator.validate(data, schema)
            
            if not result.valid:
                return {
                    "success": False,
                    "error": "Validation failed",
                    "errors": [asdict(e) for e in result.errors]
                }
            
            if 'data' in kwargs:
                kwargs['data'] = result.sanitized_data
            elif 'input_data' in kwargs:
                kwargs['input_data'] = result.sanitized_data
            elif args:
                args = (result.sanitized_data,) + args[1:]
            
            return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def with_failsafe(agent_name: str,
                  layers: List[int] = None,
                  input_schema: List[FieldSchema] = None,
                  fallback: Callable = None):
    """
    Decorator to wrap function with multi-layer failsafe protection.
    
    Usage:
        @with_failsafe(
            agent_name="SCHEDULER",
            layers=[1, 2],
            input_schema=[FieldSchema("email", str, required=True)]
        )
        async def book_meeting(data: dict): ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            failsafe = MultiLayerFailsafe()
            
            # Extract input data
            data = kwargs.get('data') or kwargs.get('input_data') or (args[0] if args else None)
            
            return await failsafe.execute_with_failsafe(
                agent_name=agent_name,
                operation=func,
                input_data=data if isinstance(data, dict) else None,
                input_schema=input_schema,
                layers=layers or [1, 2],
                fallback=fallback,
                **kwargs
            )
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, run in event loop
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(async_wrapper(*args, **kwargs))
            finally:
                loop.close()
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# ============================================================================
# GLOBAL ACCESS
# ============================================================================

_failsafe_instance: Optional[MultiLayerFailsafe] = None


def get_failsafe() -> MultiLayerFailsafe:
    """Get the global MultiLayerFailsafe instance."""
    global _failsafe_instance
    if _failsafe_instance is None:
        _failsafe_instance = MultiLayerFailsafe()
    return _failsafe_instance


# ============================================================================
# CLI / DEMO
# ============================================================================

async def demo():
    """Demonstrate multi-layer failsafe system."""
    print("\n" + "=" * 60)
    print("🛡️  MULTI-LAYER FAILSAFE DEMO (Day 16 + Day 17)")
    print("=" * 60)
    
    # Reset singleton to get fresh instance
    MultiLayerFailsafe._instance = None
    failsafe = get_failsafe()
    
    # Demo 1: Input Validation (Layer 1)
    print("\n📋 Demo 1: Input Validation (Layer 1)")
    print("-" * 40)
    
    validator = failsafe.input_validator
    
    # Valid input
    valid_data = {
        "email": "test@example.com",
        "name": "John Doe",
        "company": "TechCorp"
    }
    result = validator.validate(valid_data)
    print(f"  Valid input: {result.valid} ({len(result.errors)} errors)")
    
    # Invalid input
    invalid_data = {
        "email": "not-an-email",
        "name": "",
        "description": "<script>alert('xss')</script>"
    }
    result = validator.validate(invalid_data)
    print(f"  Invalid input: {result.valid} ({len(result.errors)} errors)")
    for err in result.errors:
        print(f"    - {err.field}: {err.message}")
    
    # Demo 2: Circuit Breaker (Layer 2)
    print("\n⚡ Demo 2: Circuit Breaker (Layer 2)")
    print("-" * 40)
    
    circuit = failsafe.circuit_breaker
    
    # Check initial status
    circuit.force_close("SCHEDULER")  # Ensure clean state
    status = circuit.get_agent_status("SCHEDULER")
    print(f"  SCHEDULER initial state: {status['state']}")
    
    # Simulate failures
    print("  Simulating 3 failures...")
    for i in range(3):
        circuit.record_failure("SCHEDULER", Exception(f"Test failure {i+1}"))
    
    status = circuit.get_agent_status("SCHEDULER")
    print(f"  SCHEDULER after failures: {status['state']} (failures: {status['failure_count']})")
    print(f"  Available: {circuit.is_available('SCHEDULER')}")
    
    # Reset
    circuit.force_close("SCHEDULER")
    print(f"  SCHEDULER after reset: {circuit.get_agent_status('SCHEDULER')['state']}")
    
    # Demo 3: Fallback Chain (Layer 3)
    print("\n🔄 Demo 3: Fallback Chain (Layer 3)")
    print("-" * 40)
    
    fallback = failsafe.fallback_chain
    
    # Register fallback handlers
    async def secondary_handler(**kwargs):
        return {"source": "secondary", "data": kwargs}
    
    async def tertiary_handler(**kwargs):
        return {"source": "tertiary", "data": kwargs}
    
    fallback.register_handler(
        "HUNTER", "scrape_linkedin", 
        secondary_handler, 
        level=FallbackLevel.SECONDARY
    )
    fallback.register_handler(
        "HUNTER", "scrape_linkedin", 
        tertiary_handler, 
        level=FallbackLevel.TERTIARY
    )
    
    # Test with failing primary
    async def failing_primary(**kwargs):
        raise Exception("Primary failed!")
    
    result = await fallback.execute_with_fallback(
        "HUNTER", "scrape_linkedin", failing_primary,
        url="https://linkedin.com/in/johndoe"
    )
    
    print(f"  Primary failed, fallback activated: {result.get('fallback_activated')}")
    print(f"  Handler used: {result.get('handler_used')}")
    print(f"  Success: {result.get('success')}")
    
    # Get stats
    stats = fallback.get_activation_stats()
    print(f"  Total activations: {stats.get('total_activations', 0)}")
    
    # Demo 4: Byzantine Consensus (Layer 4)
    print("\n🗳️  Demo 4: Byzantine Consensus (Layer 4)")
    print("-" * 40)
    
    consensus = failsafe.byzantine_consensus
    
    # Quick vote simulation with Queen having 3x weight
    voters = [
        ("UNIFIED_QUEEN", ConsensusVote.APPROVE),  # Weight: 3
        ("GATEKEEPER", ConsensusVote.APPROVE),     # Weight: 1
        ("HUNTER", ConsensusVote.REJECT),          # Weight: 1
        ("ENRICHER", ConsensusVote.APPROVE),       # Weight: 1
    ]
    
    print(f"  Total voters: {len(voters)}")
    print(f"  Weights: Queen=3, Others=1 each")
    print(f"  Required agreement: 67% (2/3)")
    
    result = await consensus.quick_vote(
        "campaign_approval",
        {"campaign_id": "C001", "type": "outbound"},
        voters
    )
    
    total_weight = 3 + 1 + 1 + 1  # 6
    approve_weight = 3 + 1 + 1    # 5 (Queen + Gatekeeper + Enricher)
    print(f"  Approve weight: {approve_weight}/{total_weight} = {approve_weight/total_weight:.0%}")
    print(f"  Consensus reached: {result.get('consensus_reached')}")
    print(f"  Final result: {result.get('final_result')}")
    
    # Demo 5: Full 4-Layer Execution
    print("\n🔒 Demo 5: Full 4-Layer Execution")
    print("-" * 40)
    
    async def enrichment_operation(data: dict):
        return {"enriched": True, "email": data.get("email")}
    
    # Register fallback for this operation
    async def cache_fallback(**kwargs):
        return {"cached": True, "source": "cache"}
    
    failsafe.register_fallback(
        "ENRICHER", "enrich_lead",
        cache_fallback,
        level=FallbackLevel.SECONDARY
    )
    
    result = await failsafe.execute_with_failsafe(
        agent_name="ENRICHER",
        operation=enrichment_operation,
        operation_name="enrich_lead",
        input_data={"email": "test@example.com", "name": "Test"},
        layers=[1, 2, 3]
    )
    
    print(f"  Execution success: {result['success']}")
    print(f"  Layers applied: {result['layers_applied']}")
    print(f"  Handler used: {result.get('handler_used', 'primary')}")
    
    # Demo 6: Metrics
    print("\n📊 Demo 6: System Metrics")
    print("-" * 40)
    
    metrics = failsafe.get_metrics()
    print(f"  Layers available: {metrics['layers_available']}")
    print(f"  Total executions: {metrics['total_executions']}")
    print(f"  Layer 1 validations: {metrics['layer1_validations']}")
    print(f"  Layer 2 checks: {metrics['layer2_checks']}")
    print(f"  Layer 3 activations: {metrics.get('layer3_activations', 0)}")
    print(f"  Layer 4 sessions: {metrics.get('layer4_sessions', 0)}")
    
    if metrics.get('layer3_stats'):
        print(f"  Layer 3 stats: {metrics['layer3_stats']}")
    if metrics.get('layer4_stats'):
        print(f"  Layer 4 stats: {metrics['layer4_stats']}")
    
    print("\n" + "=" * 60)
    print("✅ MULTI-LAYER FAILSAFE DEMO COMPLETE (ALL 4 LAYERS)")
    print("=" * 60)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Multi-Layer Failsafe System")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--status", action="store_true", help="Show system status")
    parser.add_argument("--metrics", action="store_true", help="Show metrics")
    
    args = parser.parse_args()
    
    if args.demo:
        asyncio.run(demo())
    elif args.status:
        failsafe = get_failsafe()
        status = failsafe.circuit_breaker.get_all_status()
        print(json.dumps(status, indent=2))
    elif args.metrics:
        failsafe = get_failsafe()
        metrics = failsafe.get_metrics()
        print(json.dumps(metrics, indent=2, default=str))
    else:
        asyncio.run(demo())


if __name__ == "__main__":
    main()
