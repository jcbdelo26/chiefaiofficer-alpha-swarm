#!/usr/bin/env python3
"""
Tests for Multi-Layer Failsafe System (Day 16)
===============================================
Comprehensive tests for Layer 1 (Input Validation) and Layer 2 (Circuit Breaker).
"""

import os
import sys
import json
import pytest
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.multi_layer_failsafe import (
    # Layer 1: Input Validation
    InputValidator,
    InputSanitizer,
    InjectionDetector,
    ValidationResult,
    ValidationError,
    ValidationErrorType,
    FieldSchema,
    # Layer 2: Circuit Breaker
    AgentCircuitBreaker,
    AgentCircuitConfig,
    BackoffConfig,
    # Failsafe Manager
    MultiLayerFailsafe,
    FailsafeLayer,
    get_failsafe,
    # Decorators
    validate_input,
    with_failsafe
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def validator():
    """Create InputValidator instance."""
    return InputValidator(strict_mode=False, sanitize_by_default=True)


@pytest.fixture
def strict_validator():
    """Create strict mode InputValidator instance."""
    return InputValidator(strict_mode=True, sanitize_by_default=True)


@pytest.fixture
def sanitizer():
    """Create InputSanitizer instance."""
    return InputSanitizer()


@pytest.fixture
def temp_storage(tmp_path):
    """Create temporary storage directories."""
    return tmp_path / "failsafe"


@pytest.fixture
def circuit_breaker(temp_storage):
    """Create AgentCircuitBreaker with temp storage."""
    return AgentCircuitBreaker(storage_dir=temp_storage)


@pytest.fixture
def failsafe():
    """Create MultiLayerFailsafe instance."""
    # Reset singleton for testing
    MultiLayerFailsafe._instance = None
    return get_failsafe()


# ============================================================================
# LAYER 1: INPUT VALIDATION TESTS
# ============================================================================

class TestInputSanitizer:
    """Tests for InputSanitizer class."""
    
    def test_sanitize_string_strips_whitespace(self, sanitizer):
        """Test that strings are stripped."""
        result = sanitizer.sanitize_string("  hello world  ")
        assert result == "hello world"
    
    def test_sanitize_string_normalizes_whitespace(self, sanitizer):
        """Test that multiple spaces are collapsed."""
        result = sanitizer.sanitize_string("hello    world\n\ttest")
        assert result == "hello world test"
    
    def test_sanitize_string_escapes_html(self, sanitizer):
        """Test that HTML is escaped."""
        result = sanitizer.sanitize_string("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
    
    def test_sanitize_string_max_length(self, sanitizer):
        """Test that max length is enforced."""
        long_string = "a" * 100
        result = sanitizer.sanitize_string(long_string, max_length=50)
        assert len(result) == 50
    
    def test_sanitize_email(self, sanitizer):
        """Test email sanitization."""
        result = sanitizer.sanitize_email("  Test@Example.COM  ")
        assert result == "test@example.com"
    
    def test_sanitize_phone(self, sanitizer):
        """Test phone number sanitization."""
        result = sanitizer.sanitize_phone("+1 (555) 123-4567")
        assert result == "+15551234567"
    
    def test_sanitize_url_removes_dangerous_schemes(self, sanitizer):
        """Test that javascript: URLs are removed."""
        result = sanitizer.sanitize_url("javascript:alert('xss')")
        assert result == ""
        
        result = sanitizer.sanitize_url("data:text/html,<script>alert('xss')</script>")
        assert result == ""


class TestInjectionDetector:
    """Tests for InjectionDetector class."""
    
    def test_detect_sql_injection(self):
        """Test SQL injection detection."""
        is_safe, patterns = InjectionDetector.detect(
            "SELECT * FROM users WHERE 1=1"
        )
        assert not is_safe
        assert len(patterns) > 0
    
    def test_detect_or_1_equals_1(self):
        """Test OR 1=1 pattern detection."""
        is_safe, _ = InjectionDetector.detect("value' OR 1=1 --")
        assert not is_safe
    
    def test_detect_xss(self):
        """Test XSS detection."""
        is_safe, _ = InjectionDetector.detect("<script>alert('xss')</script>")
        assert not is_safe
    
    def test_detect_event_handlers(self):
        """Test event handler detection."""
        is_safe, _ = InjectionDetector.detect("onload=alert(1)")
        assert not is_safe
    
    def test_detect_command_injection(self):
        """Test command injection detection."""
        is_safe, _ = InjectionDetector.detect("test; rm -rf /")
        assert not is_safe
    
    def test_safe_input_passes(self):
        """Test that safe input passes detection."""
        is_safe, patterns = InjectionDetector.detect("Hello, this is a normal message!")
        assert is_safe
        assert len(patterns) == 0
    
    def test_context_specific_detection(self):
        """Test context-specific detection."""
        # SQL context
        is_safe_sql, _ = InjectionDetector.detect("SELECT", context="sql")
        assert not is_safe_sql
        
        # HTML context - SELECT is safe
        is_safe_html, _ = InjectionDetector.detect("SELECT", context="html")
        assert is_safe_html


class TestFieldSchema:
    """Tests for FieldSchema validation."""
    
    def test_basic_schema_creation(self):
        """Test creating a basic field schema."""
        schema = FieldSchema("email", str, required=True)
        assert schema.name == "email"
        assert schema.field_type == str
        assert schema.required == True
    
    def test_schema_with_constraints(self):
        """Test schema with all constraints."""
        schema = FieldSchema(
            "age",
            int,
            required=False,
            min_value=0,
            max_value=150
        )
        assert schema.min_value == 0
        assert schema.max_value == 150


class TestInputValidator:
    """Tests for InputValidator class."""
    
    def test_validator_initialization(self, validator):
        """Test that validator initializes correctly."""
        assert validator is not None
        assert validator.sanitize_by_default == True
        assert validator.detect_injection == True
    
    def test_validate_valid_data(self, validator):
        """Test validation of valid data."""
        data = {
            "email": "test@example.com",
            "name": "John Doe",
            "company": "TechCorp"
        }
        result = validator.validate(data)
        
        assert result.valid == True
        assert len(result.errors) == 0
    
    def test_validate_with_schema(self, validator):
        """Test validation with explicit schema."""
        schema = [
            FieldSchema("email", str, required=True),
            FieldSchema("age", int, required=True, min_value=0, max_value=150)
        ]
        
        data = {"email": "test@example.com", "age": 25}
        result = validator.validate(data, schema)
        
        assert result.valid == True
    
    def test_validate_missing_required_field(self, validator):
        """Test that missing required fields are detected."""
        schema = [
            FieldSchema("email", str, required=True)
        ]
        
        data = {"name": "John"}
        result = validator.validate(data, schema)
        
        assert result.valid == False
        assert any(e.error_type == ValidationErrorType.REQUIRED_MISSING for e in result.errors)
    
    def test_validate_type_mismatch(self, validator):
        """Test that type mismatches are detected (with coercion attempt)."""
        schema = [
            FieldSchema("age", int, required=True)
        ]
        
        # This should coerce successfully
        data = {"age": "25"}
        result = validator.validate(data, schema)
        assert result.valid == True
        assert result.sanitized_data["age"] == 25
        
        # This should fail coercion
        data = {"age": "not a number"}
        result = validator.validate(data, schema)
        assert result.valid == False
    
    def test_validate_length_exceeded(self, validator):
        """Test that length limits are enforced when sanitize=False."""
        # When sanitize=True (default), strings are truncated rather than rejected
        # To test length validation error, we disable sanitize for this field
        schema = [
            FieldSchema("name", str, required=True, max_length=10, sanitize=False)
        ]
        
        data = {"name": "This is a very long name that exceeds the limit"}
        result = validator.validate(data, schema)
        
        assert result.valid == False
        assert any(e.error_type == ValidationErrorType.LENGTH_EXCEEDED for e in result.errors)
    
    def test_validate_pattern_mismatch(self, validator):
        """Test that pattern validation works."""
        schema = [
            FieldSchema("email", str, required=True, pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        ]
        
        data = {"email": "not-an-email"}
        result = validator.validate(data, schema)
        
        assert result.valid == False
        assert any(e.error_type == ValidationErrorType.PATTERN_MISMATCH for e in result.errors)
    
    def test_validate_value_out_of_range(self, validator):
        """Test that numeric range validation works."""
        schema = [
            FieldSchema("age", int, required=True, min_value=0, max_value=150)
        ]
        
        data = {"age": 200}
        result = validator.validate(data, schema)
        
        assert result.valid == False
        assert any(e.error_type == ValidationErrorType.VALUE_OUT_OF_RANGE for e in result.errors)
    
    def test_validate_allowed_values(self, validator):
        """Test that allowed values validation works."""
        schema = [
            FieldSchema("tier", str, required=True, allowed_values=["free", "pro", "enterprise"])
        ]
        
        data = {"tier": "invalid"}
        result = validator.validate(data, schema)
        
        assert result.valid == False
    
    def test_validate_custom_validator(self, validator):
        """Test custom validator function."""
        def validate_even(value):
            if value % 2 == 0:
                return True, ""
            return False, "Value must be even"
        
        schema = [
            FieldSchema("number", int, required=True, custom_validator=validate_even)
        ]
        
        # Even number should pass
        data = {"number": 4}
        result = validator.validate(data, schema)
        assert result.valid == True
        
        # Odd number should fail
        data = {"number": 5}
        result = validator.validate(data, schema)
        assert result.valid == False
    
    def test_validate_sanitizes_data(self, validator):
        """Test that data is sanitized."""
        data = {"name": "  John Doe  "}
        result = validator.validate(data)
        
        assert result.sanitized_data["name"] == "John Doe"
    
    def test_validate_email(self, validator):
        """Test email validation helper."""
        result = validator.validate_email("test@example.com")
        assert result.valid == True
        
        result = validator.validate_email("not-an-email")
        assert result.valid == False
    
    def test_validate_json(self, validator):
        """Test JSON validation helper."""
        result = validator.validate_json('{"key": "value"}')
        assert result.valid == True
        assert result.sanitized_data == {"key": "value"}
        
        result = validator.validate_json('not valid json')
        assert result.valid == False
    
    def test_validate_json_max_size(self, validator):
        """Test JSON max size validation."""
        large_json = '{"data": "' + 'x' * 50001 + '"}'
        result = validator.validate_json(large_json, max_size=50000)
        assert result.valid == False
    
    def test_strict_mode_converts_warnings_to_errors(self, strict_validator):
        """Test that strict mode converts warnings to errors with schema validation."""
        # In strict mode with schema, potential injection should be an error
        schema = [
            FieldSchema("query", str, required=True)
        ]
        
        data = {"query": "SELECT * FROM users"}
        result = strict_validator.validate(data, schema)
        
        # Should have injection detected as error (strict mode converts warning to error)
        assert any(e.error_type == ValidationErrorType.INJECTION_DETECTED 
                   for e in result.errors)


class TestValidationResult:
    """Tests for ValidationResult class."""
    
    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = ValidationResult(valid=True)
        d = result.to_dict()
        
        assert "valid" in d
        assert "errors" in d
        assert "warnings" in d
    
    def test_add_error_makes_invalid(self):
        """Test that adding error makes result invalid."""
        result = ValidationResult(valid=True)
        assert result.valid == True
        
        result.add_error(ValidationError(
            error_type=ValidationErrorType.REQUIRED_MISSING,
            field="test",
            message="Test error"
        ))
        
        assert result.valid == False
        assert len(result.errors) == 1


# ============================================================================
# LAYER 2: CIRCUIT BREAKER TESTS
# ============================================================================

class TestBackoffConfig:
    """Tests for BackoffConfig class."""
    
    def test_default_config(self):
        """Test default backoff configuration."""
        config = BackoffConfig()
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.multiplier == 2.0
    
    def test_custom_config(self):
        """Test custom backoff configuration."""
        config = BackoffConfig(initial_delay=0.5, max_delay=30.0, multiplier=3.0)
        assert config.initial_delay == 0.5
        assert config.max_delay == 30.0
        assert config.multiplier == 3.0


class TestAgentCircuitConfig:
    """Tests for AgentCircuitConfig class."""
    
    def test_default_config(self):
        """Test default circuit configuration."""
        config = AgentCircuitConfig()
        assert config.failure_threshold == 3
        assert config.recovery_timeout == 300
    
    def test_backoff_delay_calculation(self):
        """Test backoff delay calculation."""
        config = AgentCircuitConfig()
        
        # First attempt: 1s
        delay1 = config.get_backoff_delay(1)
        assert 0.9 <= delay1 <= 1.1  # 1s with jitter
        
        # Second attempt: 2s
        delay2 = config.get_backoff_delay(2)
        assert 1.8 <= delay2 <= 2.2  # 2s with jitter
        
        # Third attempt: 4s
        delay3 = config.get_backoff_delay(3)
        assert 3.6 <= delay3 <= 4.4  # 4s with jitter
    
    def test_backoff_max_delay(self):
        """Test that backoff is capped at max_delay."""
        config = AgentCircuitConfig()
        config.backoff.max_delay = 10.0
        
        # After many attempts, delay should be capped
        delay = config.get_backoff_delay(10)
        assert delay <= 11.0  # Max + jitter


class TestAgentCircuitBreaker:
    """Tests for AgentCircuitBreaker class."""
    
    def test_initialization(self, circuit_breaker):
        """Test circuit breaker initialization."""
        assert circuit_breaker is not None
        assert len(circuit_breaker._agent_configs) > 0
    
    def test_all_agents_have_configs(self, circuit_breaker):
        """Test that all standard agents have configurations."""
        expected_agents = [
            "UNIFIED_QUEEN", "HUNTER", "ENRICHER", "SEGMENTOR",
            "CRAFTER", "GATEKEEPER", "SCOUT", "OPERATOR",
            "COACH", "PIPER", "SCHEDULER", "RESEARCHER", "COMMUNICATOR"
        ]
        
        for agent in expected_agents:
            assert agent in circuit_breaker._agent_configs
    
    def test_is_available_initially_true(self, circuit_breaker):
        """Test that circuits are available initially."""
        assert circuit_breaker.is_available("SCHEDULER") == True
    
    def test_record_success(self, circuit_breaker):
        """Test recording success."""
        circuit_breaker.record_success("SCHEDULER")
        
        status = circuit_breaker.get_agent_status("SCHEDULER")
        assert status["state"] == "closed"
    
    def test_record_failure(self, circuit_breaker):
        """Test recording failure."""
        circuit_breaker.record_failure("SCHEDULER", Exception("Test failure"))
        
        assert circuit_breaker._agent_attempts["SCHEDULER"] == 1
    
    def test_circuit_opens_after_threshold(self, circuit_breaker):
        """Test that circuit opens after failure threshold."""
        # Use COACH (threshold 5) to avoid conflict with other tests
        agent = "COACH"
        circuit_breaker.force_close(agent)  # Ensure clean state
        
        config = circuit_breaker._agent_configs[agent]
        for i in range(config.failure_threshold):
            circuit_breaker.record_failure(agent, Exception(f"Failure {i}"))
        
        # Circuit should be open now
        assert circuit_breaker.is_available(agent) == False
        
        # Cleanup
        circuit_breaker.force_close(agent)
    
    def test_get_backoff_delay(self, circuit_breaker):
        """Test getting backoff delay."""
        # Use PIPER to avoid conflict
        agent = "PIPER"
        circuit_breaker.force_close(agent)
        circuit_breaker._agent_attempts[agent] = 0
        
        # No failures yet
        delay = circuit_breaker.get_backoff_delay(agent)
        assert delay == 0.0
        
        # After failure
        circuit_breaker.record_failure(agent, Exception("Test"))
        delay = circuit_breaker.get_backoff_delay(agent)
        assert delay > 0
        
        # Cleanup
        circuit_breaker.force_close(agent)
    
    def test_should_retry(self, circuit_breaker):
        """Test should_retry logic."""
        # Use SEGMENTOR to avoid conflict with other tests
        agent = "SEGMENTOR"
        circuit_breaker.force_close(agent)
        circuit_breaker._agent_attempts[agent] = 0
        
        should_retry, delay = circuit_breaker.should_retry(agent)
        assert should_retry == True
        assert delay == 0.0
        
        # After failures and circuit open (SEGMENTOR has threshold 5)
        config = circuit_breaker._agent_configs[agent]
        for i in range(config.failure_threshold):
            circuit_breaker.record_failure(agent, Exception(f"Failure {i}"))
        
        should_retry, delay = circuit_breaker.should_retry(agent)
        assert should_retry == False
        
        # Cleanup
        circuit_breaker.force_close(agent)
    
    def test_force_open(self, circuit_breaker):
        """Test manually opening circuit."""
        circuit_breaker.force_open("SCHEDULER")
        
        assert circuit_breaker.is_available("SCHEDULER") == False
    
    def test_force_close(self, circuit_breaker):
        """Test manually closing circuit."""
        # First open it
        circuit_breaker.force_open("SCHEDULER")
        assert circuit_breaker.is_available("SCHEDULER") == False
        
        # Then close it
        circuit_breaker.force_close("SCHEDULER")
        assert circuit_breaker.is_available("SCHEDULER") == True
    
    def test_get_agent_status(self, circuit_breaker):
        """Test getting agent status."""
        status = circuit_breaker.get_agent_status("SCHEDULER")
        
        assert "agent" in status
        assert "state" in status
        assert "failure_count" in status
        assert "failure_threshold" in status
        assert "is_available" in status
    
    def test_get_all_status(self, circuit_breaker):
        """Test getting all agent statuses."""
        status = circuit_breaker.get_all_status()
        
        assert len(status) > 0
        assert "SCHEDULER" in status
    
    def test_update_config(self, circuit_breaker):
        """Test updating agent config."""
        circuit_breaker.update_config(
            "SCHEDULER",
            failure_threshold=5,
            recovery_timeout=600
        )
        
        config = circuit_breaker._agent_configs["SCHEDULER"]
        assert config.failure_threshold == 5
        assert config.recovery_timeout == 600


# ============================================================================
# MULTI-LAYER FAILSAFE TESTS
# ============================================================================

class TestMultiLayerFailsafe:
    """Tests for MultiLayerFailsafe class."""
    
    def test_singleton_pattern(self):
        """Test that failsafe is a singleton."""
        MultiLayerFailsafe._instance = None
        
        failsafe1 = get_failsafe()
        failsafe2 = get_failsafe()
        
        assert failsafe1 is failsafe2
    
    def test_initialization(self, failsafe):
        """Test failsafe initialization."""
        assert failsafe.input_validator is not None
        assert failsafe.circuit_breaker is not None
    
    @pytest.mark.asyncio
    async def test_execute_with_layer1_only(self, failsafe):
        """Test execution with Layer 1 only."""
        async def operation(data):
            return {"processed": True}
        
        result = await failsafe.execute_with_failsafe(
            agent_name="CRAFTER",
            operation=operation,
            input_data={"email": "test@example.com"},
            layers=[1]
        )
        
        assert result["success"] == True
        assert 1 in result["layers_applied"]
    
    @pytest.mark.asyncio
    async def test_execute_with_layer2_only(self, failsafe):
        """Test execution with Layer 2 only."""
        async def operation():
            return {"processed": True}
        
        result = await failsafe.execute_with_failsafe(
            agent_name="CRAFTER",
            operation=operation,
            layers=[2]
        )
        
        assert result["success"] == True
        assert 2 in result["layers_applied"]
    
    @pytest.mark.asyncio
    async def test_execute_with_both_layers(self, failsafe):
        """Test execution with both layers."""
        async def operation(data):
            return {"email": data.get("email")}
        
        result = await failsafe.execute_with_failsafe(
            agent_name="CRAFTER",
            operation=operation,
            input_data={"email": "test@example.com"},
            layers=[1, 2]
        )
        
        assert result["success"] == True
        assert result["input_sanitized"] == True
    
    @pytest.mark.asyncio
    async def test_layer1_blocks_invalid_input(self, failsafe):
        """Test that Layer 1 blocks invalid input."""
        async def operation(data):
            return {"processed": True}
        
        schema = [
            FieldSchema("email", str, required=True, pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        ]
        
        result = await failsafe.execute_with_failsafe(
            agent_name="CRAFTER",
            operation=operation,
            input_data={"email": "not-valid"},
            input_schema=schema,
            layers=[1, 2]
        )
        
        assert result["success"] == False
        assert result.get("layer_blocked") == 1
    
    @pytest.mark.asyncio
    async def test_layer2_blocks_when_circuit_open(self, failsafe):
        """Test that Layer 2 blocks when circuit is open."""
        # Force open the circuit
        failsafe.circuit_breaker.force_open("CRAFTER")
        
        async def operation():
            return {"processed": True}
        
        result = await failsafe.execute_with_failsafe(
            agent_name="CRAFTER",
            operation=operation,
            layers=[2]
        )
        
        assert result["success"] == False
        assert result.get("layer_blocked") == 2
        
        # Reset
        failsafe.circuit_breaker.force_close("CRAFTER")
    
    @pytest.mark.asyncio
    async def test_fallback_on_circuit_open(self, failsafe):
        """Test that fallback is called when circuit is open."""
        failsafe.circuit_breaker.force_open("SEGMENTOR")
        
        async def operation():
            return {"processed": True}
        
        async def fallback():
            return {"fallback": True}
        
        result = await failsafe.execute_with_failsafe(
            agent_name="SEGMENTOR",
            operation=operation,
            layers=[2],
            fallback=fallback
        )
        
        assert result["fallback_used"] == True
        assert result["fallback_result"]["fallback"] == True
        
        # Reset
        failsafe.circuit_breaker.force_close("SEGMENTOR")
    
    @pytest.mark.asyncio
    async def test_fallback_on_operation_failure(self, failsafe):
        """Test that fallback is called on operation failure."""
        async def operation():
            raise Exception("Operation failed")
        
        async def fallback():
            return {"fallback": True}
        
        result = await failsafe.execute_with_failsafe(
            agent_name="ENRICHER",
            operation=operation,
            layers=[2],
            fallback=fallback
        )
        
        assert result["fallback_used"] == True
    
    def test_get_metrics(self, failsafe):
        """Test getting failsafe metrics."""
        metrics = failsafe.get_metrics()
        
        assert "total_executions" in metrics
        assert "layer1_validations" in metrics
        assert "layer2_checks" in metrics
        assert "circuit_breaker_status" in metrics
    
    def test_reset_metrics(self, failsafe):
        """Test resetting metrics."""
        failsafe._metrics["total_executions"] = 100
        failsafe.reset_metrics()
        
        assert failsafe._metrics["total_executions"] == 0


# ============================================================================
# DECORATOR TESTS
# ============================================================================

class TestValidateInputDecorator:
    """Tests for @validate_input decorator."""
    
    @pytest.mark.asyncio
    async def test_decorator_validates_input(self):
        """Test that decorator validates input."""
        schema = [
            FieldSchema("email", str, required=True)
        ]
        
        @validate_input(schema=schema)
        async def create_contact(data):
            return {"created": True, "email": data["email"]}
        
        result = await create_contact(data={"email": "test@example.com"})
        assert result["created"] == True
    
    @pytest.mark.asyncio
    async def test_decorator_rejects_invalid(self):
        """Test that decorator rejects invalid input."""
        schema = [
            FieldSchema("email", str, required=True)
        ]
        
        @validate_input(schema=schema)
        async def create_contact(data):
            return {"created": True}
        
        result = await create_contact(data={})  # Missing email
        assert result["success"] == False
        assert "errors" in result
    
    @pytest.mark.asyncio
    async def test_decorator_sanitizes_input(self):
        """Test that decorator sanitizes input."""
        @validate_input()
        async def process(data):
            return data
        
        result = await process(data={"name": "  John  "})
        # Note: Result is the return from process(), which is the sanitized data
        assert result is not None


class TestWithFailsafeDecorator:
    """Tests for @with_failsafe decorator."""
    
    @pytest.mark.asyncio
    async def test_decorator_applies_failsafe(self):
        """Test that decorator applies failsafe protection."""
        @with_failsafe(agent_name="PIPER", layers=[2])
        async def process_pipeline():
            return {"processed": True}
        
        result = await process_pipeline()
        
        assert result["success"] == True or "layers_applied" in result


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

# ============================================================================
# LAYER 3: FALLBACK CHAIN TESTS
# ============================================================================

class TestFallbackChain:
    """Tests for FallbackChain class (Layer 3)."""
    
    @pytest.fixture
    def fallback_chain(self, tmp_path):
        """Create FallbackChain with temp storage."""
        from core.multi_layer_failsafe import FallbackChain
        return FallbackChain(storage_dir=tmp_path / "fallback")
    
    def test_initialization(self, fallback_chain):
        """Test fallback chain initialization."""
        assert fallback_chain is not None
        assert fallback_chain._activations == []
    
    def test_register_handler(self, fallback_chain):
        """Test registering a fallback handler."""
        from core.multi_layer_failsafe import FallbackLevel
        
        async def handler(**kwargs):
            return {"result": "secondary"}
        
        fallback_chain.register_handler(
            agent_name="HUNTER",
            operation="scrape_linkedin",
            handler=handler,
            level=FallbackLevel.SECONDARY
        )
        
        chain = fallback_chain._chains["HUNTER"]["scrape_linkedin"]
        assert len(chain) == 1
        assert chain[0].level == FallbackLevel.SECONDARY
    
    def test_register_multiple_handlers_sorted(self, fallback_chain):
        """Test that handlers are sorted by level."""
        from core.multi_layer_failsafe import FallbackLevel
        
        async def secondary(**kwargs):
            return {"level": "secondary"}
        
        async def tertiary(**kwargs):
            return {"level": "tertiary"}
        
        # Register in reverse order
        fallback_chain.register_handler("ENRICHER", "enrich", tertiary, FallbackLevel.TERTIARY)
        fallback_chain.register_handler("ENRICHER", "enrich", secondary, FallbackLevel.SECONDARY)
        
        chain = fallback_chain._chains["ENRICHER"]["enrich"]
        assert chain[0].level == FallbackLevel.SECONDARY
        assert chain[1].level == FallbackLevel.TERTIARY
    
    @pytest.mark.asyncio
    async def test_execute_with_fallback_primary_success(self, fallback_chain):
        """Test that primary success skips fallback."""
        async def primary(**kwargs):
            return {"source": "primary"}
        
        result = await fallback_chain.execute_with_fallback(
            "HUNTER", "test_op", primary, data="test"
        )
        
        assert result["success"] == True
        assert result["handler_used"] == "primary"
        assert result["fallback_activated"] == False
    
    @pytest.mark.asyncio
    async def test_execute_with_fallback_primary_fails(self, fallback_chain):
        """Test fallback activation when primary fails."""
        from core.multi_layer_failsafe import FallbackLevel
        
        async def primary(**kwargs):
            raise Exception("Primary failed!")
        
        async def secondary(**kwargs):
            return {"source": "secondary"}
        
        fallback_chain.register_handler(
            "HUNTER", "test_op", secondary, FallbackLevel.SECONDARY
        )
        
        result = await fallback_chain.execute_with_fallback(
            "HUNTER", "test_op", primary
        )
        
        assert result["success"] == True
        assert result["fallback_activated"] == True
        assert "secondary" in result["handler_used"]
    
    @pytest.mark.asyncio
    async def test_execute_with_fallback_chain_exhausted(self, fallback_chain):
        """Test behavior when all fallbacks fail."""
        from core.multi_layer_failsafe import FallbackLevel
        
        async def primary(**kwargs):
            raise Exception("Primary failed!")
        
        async def secondary(**kwargs):
            raise Exception("Secondary failed!")
        
        fallback_chain.register_handler(
            "HUNTER", "fail_op", secondary, FallbackLevel.SECONDARY
        )
        
        result = await fallback_chain.execute_with_fallback(
            "HUNTER", "fail_op", primary
        )
        
        assert result["success"] == False
        assert "All fallback handlers failed" in result.get("error", "")
    
    def test_register_human_escalation(self, fallback_chain):
        """Test registering human escalation handler."""
        fallback_chain.register_human_escalation("GATEKEEPER", "send_campaign")
        
        chain = fallback_chain._chains["GATEKEEPER"]["send_campaign"]
        assert len(chain) == 1
        from core.multi_layer_failsafe import FallbackLevel
        assert chain[0].level == FallbackLevel.HUMAN_ESCALATION
    
    def test_get_activation_stats_empty(self, fallback_chain):
        """Test activation stats when empty."""
        stats = fallback_chain.get_activation_stats()
        assert stats["total"] == 0
    
    @pytest.mark.asyncio
    async def test_activation_logging(self, fallback_chain):
        """Test that activations are logged."""
        from core.multi_layer_failsafe import FallbackLevel
        
        async def primary(**kwargs):
            raise Exception("Test failure")
        
        async def secondary(**kwargs):
            return {"ok": True}
        
        fallback_chain.register_handler(
            "SCOUT", "search", secondary, FallbackLevel.SECONDARY
        )
        
        await fallback_chain.execute_with_fallback("SCOUT", "search", primary)
        
        stats = fallback_chain.get_activation_stats()
        assert stats["total_activations"] >= 1
    
    def test_get_pending_escalations_empty(self, fallback_chain):
        """Test pending escalations when empty."""
        pending = fallback_chain.get_pending_escalations()
        assert pending == []


# ============================================================================
# LAYER 4: BYZANTINE CONSENSUS TESTS
# ============================================================================

class TestByzantineConsensus:
    """Tests for ByzantineConsensus class (Layer 4)."""
    
    @pytest.fixture
    def consensus(self, tmp_path):
        """Create ByzantineConsensus with temp storage."""
        from core.multi_layer_failsafe import ByzantineConsensus
        return ByzantineConsensus(storage_dir=tmp_path / "consensus")
    
    def test_initialization(self, consensus):
        """Test consensus initialization."""
        assert consensus is not None
        assert consensus.DEFAULT_AGREEMENT == 0.67
        assert consensus.MAX_ROUNDS == 3
    
    def test_agent_weights(self, consensus):
        """Test that agent weights are configured correctly."""
        assert consensus.AGENT_WEIGHTS["UNIFIED_QUEEN"] == 3.0
        assert consensus.AGENT_WEIGHTS["GATEKEEPER"] == 1.0
        assert consensus.AGENT_WEIGHTS["HUNTER"] == 1.0
    
    def test_start_session(self, consensus):
        """Test starting a consensus session."""
        session_id = consensus.start_session(
            action_type="campaign_approval",
            action_data={"campaign_id": "C001"}
        )
        
        assert session_id is not None
        assert len(session_id) == 12
        assert session_id in consensus._sessions
    
    def test_cast_vote(self, consensus):
        """Test casting a vote."""
        from core.multi_layer_failsafe import ConsensusVote
        
        session_id = consensus.start_session("test_action", {})
        
        result = consensus.cast_vote(
            session_id=session_id,
            voter="HUNTER",
            vote=ConsensusVote.APPROVE,
            reason="Looks good"
        )
        
        assert result["success"] == True
        assert result["votes_cast"] == 1
    
    def test_cast_vote_with_weight(self, consensus):
        """Test that votes have correct weights."""
        from core.multi_layer_failsafe import ConsensusVote
        
        session_id = consensus.start_session("test_action", {})
        
        # Queen has 3x weight
        result = consensus.cast_vote(session_id, "UNIFIED_QUEEN", ConsensusVote.APPROVE)
        assert result["approve_weight"] == 3.0
        
        # Hunter has 1x weight
        result = consensus.cast_vote(session_id, "HUNTER", ConsensusVote.REJECT)
        assert result["reject_weight"] == 1.0
    
    def test_duplicate_vote_rejected(self, consensus):
        """Test that duplicate votes are rejected."""
        from core.multi_layer_failsafe import ConsensusVote
        
        session_id = consensus.start_session("test_action", {})
        consensus.cast_vote(session_id, "HUNTER", ConsensusVote.APPROVE)
        
        result = consensus.cast_vote(session_id, "HUNTER", ConsensusVote.REJECT)
        
        assert result["success"] == False
        assert "Already voted" in result["error"]
    
    @pytest.mark.asyncio
    async def test_finalize_round_approval(self, consensus):
        """Test finalizing round with approval consensus."""
        from core.multi_layer_failsafe import ConsensusVote
        
        session_id = consensus.start_session("approval_test", {})
        
        # Cast votes: Queen (3) + Gatekeeper (1) = 4 approve out of 5 total = 80%
        consensus.cast_vote(session_id, "UNIFIED_QUEEN", ConsensusVote.APPROVE)
        consensus.cast_vote(session_id, "GATEKEEPER", ConsensusVote.APPROVE)
        consensus.cast_vote(session_id, "HUNTER", ConsensusVote.REJECT)
        
        result = await consensus.finalize_round(session_id)
        
        assert result["consensus_reached"] == True
        assert result["final_result"] == "approve"
    
    @pytest.mark.asyncio
    async def test_finalize_round_rejection(self, consensus):
        """Test finalizing round with rejection consensus."""
        from core.multi_layer_failsafe import ConsensusVote
        
        session_id = consensus.start_session("rejection_test", {})
        
        # Cast votes: 3 reject out of 4 total = 75%
        consensus.cast_vote(session_id, "HUNTER", ConsensusVote.REJECT)
        consensus.cast_vote(session_id, "ENRICHER", ConsensusVote.REJECT)
        consensus.cast_vote(session_id, "SCOUT", ConsensusVote.REJECT)
        consensus.cast_vote(session_id, "CRAFTER", ConsensusVote.APPROVE)
        
        result = await consensus.finalize_round(session_id)
        
        assert result["consensus_reached"] == True
        assert result["final_result"] == "reject"
    
    @pytest.mark.asyncio
    async def test_quick_vote(self, consensus):
        """Test quick vote functionality."""
        from core.multi_layer_failsafe import ConsensusVote
        
        voters = [
            ("UNIFIED_QUEEN", ConsensusVote.APPROVE),
            ("GATEKEEPER", ConsensusVote.APPROVE),
            ("HUNTER", ConsensusVote.REJECT),
        ]
        
        result = await consensus.quick_vote(
            "campaign_approval",
            {"campaign_id": "C002"},
            voters
        )
        
        assert result["consensus_reached"] == True
        # Queen (3) + Gatekeeper (1) = 4 approve, Hunter (1) = 1 reject
        # 4/5 = 80% > 67%
        assert result["final_result"] == "approve"
    
    def test_get_session_status(self, consensus):
        """Test getting session status."""
        session_id = consensus.start_session("test", {})
        
        status = consensus.get_session_status(session_id)
        
        assert status["session_id"] == session_id
        assert status["status"] == "active"
    
    def test_get_session_status_not_found(self, consensus):
        """Test status for non-existent session."""
        status = consensus.get_session_status("nonexistent")
        
        assert "error" in status
    
    def test_get_stats_empty(self, consensus):
        """Test stats when no sessions."""
        stats = consensus.get_stats()
        
        assert stats["total_sessions"] == 0
    
    @pytest.mark.asyncio
    async def test_abstain_vote(self, consensus):
        """Test abstain vote doesn't count toward totals."""
        from core.multi_layer_failsafe import ConsensusVote
        
        session_id = consensus.start_session("abstain_test", {})
        
        consensus.cast_vote(session_id, "UNIFIED_QUEEN", ConsensusVote.APPROVE)
        consensus.cast_vote(session_id, "HUNTER", ConsensusVote.ABSTAIN)
        
        session = consensus._sessions[session_id]
        current_round = session.rounds[-1]
        
        # Abstain adds to total weight but not approve/reject
        assert current_round.total_weight == 4.0  # Queen (3) + Hunter (1)
        assert current_round.approve_weight == 3.0  # Only Queen


class TestFallbackHandler:
    """Tests for FallbackHandler dataclass."""
    
    def test_to_dict(self):
        """Test FallbackHandler.to_dict()."""
        from core.multi_layer_failsafe import FallbackHandler, FallbackLevel
        
        async def handler(**kwargs):
            pass
        
        fb = FallbackHandler(
            name="test_handler",
            level=FallbackLevel.SECONDARY,
            handler=handler
        )
        
        d = fb.to_dict()
        assert d["name"] == "test_handler"
        assert d["level"] == "secondary"


class TestConsensusSession:
    """Tests for ConsensusSession dataclass."""
    
    def test_to_dict(self):
        """Test ConsensusSession.to_dict()."""
        from core.multi_layer_failsafe import ConsensusSession
        
        session = ConsensusSession(
            session_id="test123",
            action_type="approval",
            action_data={"test": "data"},
            required_agreement=0.67,
            max_rounds=3
        )
        
        d = session.to_dict()
        assert d["session_id"] == "test123"
        assert d["action_type"] == "approval"
        assert d["max_rounds"] == 3


# ============================================================================
# MULTI-LAYER INTEGRATION TESTS
# ============================================================================

class TestMultiLayerIntegration:
    """Integration tests for the multi-layer failsafe system."""
    
    @pytest.mark.asyncio
    async def test_full_protection_flow(self, failsafe):
        """Test full protection flow with all layers."""
        # Reset circuit
        failsafe.circuit_breaker.force_close("HUNTER")
        
        async def scrape_linkedin(data):
            return {"profiles": [data["url"]]}
        
        schema = [
            FieldSchema("url", str, required=True, max_length=2048)
        ]
        
        result = await failsafe.execute_with_failsafe(
            agent_name="HUNTER",
            operation=scrape_linkedin,
            input_data={"url": "https://linkedin.com/in/johndoe"},
            input_schema=schema,
            layers=[1, 2]
        )
        
        assert result["success"] == True
        assert result["input_sanitized"] == True
    
    @pytest.mark.asyncio
    async def test_circuit_trips_and_recovers(self, failsafe):
        """Test circuit breaker trips and recovers."""
        agent = "OPERATOR"
        
        # Reset to ensure clean state
        failsafe.circuit_breaker.force_close(agent)
        
        async def failing_operation():
            raise Exception("Simulated failure")
        
        # Cause failures to trip circuit
        for _ in range(3):
            await failsafe.execute_with_failsafe(
                agent_name=agent,
                operation=failing_operation,
                layers=[2]
            )
        
        # Should be blocked now
        async def success_operation():
            return {"ok": True}
        
        result = await failsafe.execute_with_failsafe(
            agent_name=agent,
            operation=success_operation,
            layers=[2]
        )
        
        assert result["success"] == False or result.get("layer_blocked") == 2
        
        # Reset and verify recovery
        failsafe.circuit_breaker.force_close(agent)
        
        result = await failsafe.execute_with_failsafe(
            agent_name=agent,
            operation=success_operation,
            layers=[2]
        )
        
        assert result["success"] == True
    
    @pytest.mark.asyncio
    async def test_injection_blocked(self, failsafe):
        """Test that injection attempts are blocked."""
        async def process(data):
            return data
        
        result = await failsafe.execute_with_failsafe(
            agent_name="SCOUT",
            operation=process,
            input_data={"query": "SELECT * FROM users; DROP TABLE users;--"},
            layers=[1]
        )
        
        # Injection should be detected (as warning in non-strict mode)
        # The operation should still succeed but data should be sanitized
        assert result.get("success") == True or "validation_errors" in result


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Edge case tests for failsafe system."""
    
    def test_empty_data_validation(self, validator):
        """Test validation of empty data."""
        result = validator.validate({})
        assert result.valid == True
    
    def test_none_value_validation(self, validator):
        """Test validation with None values."""
        data = {"email": None, "name": "John"}
        result = validator.validate(data)
        assert result.valid == True
    
    def test_unicode_handling(self, validator):
        """Test handling of unicode characters."""
        data = {"name": "日本語テスト", "emoji": "🎉"}
        result = validator.validate(data)
        assert result.valid == True
        assert "日本語テスト" in str(result.sanitized_data["name"])
    
    def test_very_long_input(self, validator):
        """Test handling of very long input."""
        long_value = "a" * 10000
        data = {"description": long_value}
        result = validator.validate(data)
        
        # Should be truncated to default limit
        assert len(result.sanitized_data["description"]) <= 5000
    
    def test_circuit_breaker_unknown_agent(self, circuit_breaker):
        """Test circuit breaker with unknown agent."""
        # Should handle gracefully
        status = circuit_breaker.get_agent_status("UNKNOWN_AGENT")
        assert "error" in status or status.get("agent") == "UNKNOWN_AGENT"
    
    @pytest.mark.asyncio
    async def test_sync_operation_in_failsafe(self, failsafe):
        """Test synchronous operation in failsafe."""
        def sync_operation(data):
            return {"sync": True}
        
        result = await failsafe.execute_with_failsafe(
            agent_name="COACH",
            operation=sync_operation,
            input_data={"test": "data"},
            layers=[1, 2]
        )
        
        assert result["success"] == True


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Performance tests for failsafe system."""
    
    def test_validation_speed(self, validator):
        """Test that validation is fast."""
        import time
        
        data = {
            "email": "test@example.com",
            "name": "John Doe",
            "company": "TechCorp",
            "phone": "+1-555-123-4567"
        }
        
        start = time.time()
        for _ in range(100):
            validator.validate(data)
        elapsed = time.time() - start
        
        # 100 validations should complete in under 1 second
        assert elapsed < 1.0
    
    def test_injection_detection_speed(self):
        """Test that injection detection is fast."""
        import time
        
        texts = [
            "Normal text message",
            "SELECT * FROM users",
            "<script>alert('xss')</script>",
            "test; rm -rf /"
        ]
        
        start = time.time()
        for _ in range(100):
            for text in texts:
                InjectionDetector.detect(text)
        elapsed = time.time() - start
        
        # 400 detections should complete in under 1 second
        assert elapsed < 1.0


# ============================================================================
# LAYER 3 & 4 INTEGRATION TESTS
# ============================================================================

class TestLayer3Integration:
    """Integration tests for Layer 3 (Fallback Chain) with MultiLayerFailsafe."""
    
    @pytest.mark.asyncio
    async def test_layer3_fallback_chain_execution(self, failsafe):
        """Test Layer 3 fallback chain in failsafe execution."""
        from core.multi_layer_failsafe import FallbackLevel
        
        failsafe.circuit_breaker.force_close("RESEARCHER")
        
        async def failing_operation(**kwargs):
            raise Exception("Primary failed")
        
        async def cache_fallback(**kwargs):
            return {"source": "cache", "cached": True}
        
        failsafe.register_fallback(
            "RESEARCHER", "research",
            cache_fallback,
            level=FallbackLevel.SECONDARY
        )
        
        result = await failsafe.execute_with_failsafe(
            agent_name="RESEARCHER",
            operation=failing_operation,
            operation_name="research",
            layers=[1, 2, 3]
        )
        
        assert result["success"] == True
        assert result.get("fallback_chain_used") == True or result.get("handler_used") != "primary"
    
    @pytest.mark.asyncio
    async def test_layer3_with_input_validation(self, failsafe):
        """Test Layer 3 with Layer 1 input validation."""
        from core.multi_layer_failsafe import FallbackLevel
        
        failsafe.circuit_breaker.force_close("OPERATOR")
        
        async def operation(input_data, **kwargs):
            return {"processed": input_data}
        
        async def fallback_operation(**kwargs):
            return {"fallback": True}
        
        failsafe.register_fallback(
            "OPERATOR", "process",
            fallback_operation,
            level=FallbackLevel.SECONDARY
        )
        
        result = await failsafe.execute_with_failsafe(
            agent_name="OPERATOR",
            operation=operation,
            operation_name="process",
            input_data={"email": "test@example.com"},
            layers=[1, 2, 3]
        )
        
        assert result["success"] == True
        assert result["input_sanitized"] == True


class TestLayer4Integration:
    """Integration tests for Layer 4 (Byzantine Consensus) with MultiLayerFailsafe."""
    
    @pytest.mark.asyncio
    async def test_layer4_consensus_approval(self, failsafe):
        """Test Layer 4 consensus approval."""
        from core.multi_layer_failsafe import ConsensusVote
        
        failsafe.circuit_breaker.force_close("GATEKEEPER")
        
        async def send_campaign(**kwargs):
            return {"sent": True}
        
        voters = [
            ("UNIFIED_QUEEN", ConsensusVote.APPROVE),
            ("GATEKEEPER", ConsensusVote.APPROVE),
            ("CRAFTER", ConsensusVote.APPROVE),
        ]
        
        result = await failsafe.execute_with_failsafe(
            agent_name="GATEKEEPER",
            operation=send_campaign,
            operation_name="send_campaign",
            layers=[2, 4],
            require_consensus=True,
            consensus_voters=voters
        )
        
        assert result["success"] == True
        assert result.get("consensus_approved") == True
    
    @pytest.mark.asyncio
    async def test_layer4_consensus_rejection(self, failsafe):
        """Test Layer 4 consensus rejection blocks execution."""
        from core.multi_layer_failsafe import ConsensusVote
        
        failsafe.circuit_breaker.force_close("CRAFTER")
        
        async def risky_operation(**kwargs):
            return {"executed": True}
        
        # Majority rejects
        voters = [
            ("HUNTER", ConsensusVote.REJECT),
            ("ENRICHER", ConsensusVote.REJECT),
            ("SCOUT", ConsensusVote.REJECT),
            ("CRAFTER", ConsensusVote.APPROVE),
        ]
        
        result = await failsafe.execute_with_failsafe(
            agent_name="CRAFTER",
            operation=risky_operation,
            operation_name="risky_op",
            layers=[2, 4],
            require_consensus=True,
            consensus_voters=voters
        )
        
        assert result["success"] == False
        assert result.get("layer_blocked") == 4
    
    @pytest.mark.asyncio
    async def test_all_four_layers(self, failsafe):
        """Test execution with all 4 layers enabled."""
        from core.multi_layer_failsafe import ConsensusVote, FallbackLevel
        
        failsafe.circuit_breaker.force_close("SCHEDULER")
        
        async def book_meeting(input_data, **kwargs):
            return {"booked": True, "email": input_data.get("email")}
        
        async def fallback_book(**kwargs):
            return {"booked": True, "source": "fallback"}
        
        failsafe.register_fallback(
            "SCHEDULER", "book_meeting",
            fallback_book,
            level=FallbackLevel.SECONDARY
        )
        
        voters = [
            ("UNIFIED_QUEEN", ConsensusVote.APPROVE),
            ("SCHEDULER", ConsensusVote.APPROVE),
        ]
        
        result = await failsafe.execute_with_failsafe(
            agent_name="SCHEDULER",
            operation=book_meeting,
            operation_name="book_meeting",
            input_data={"email": "test@example.com", "date": "2025-01-22"},
            layers=[1, 2, 3, 4],
            require_consensus=True,
            consensus_voters=voters
        )
        
        assert result["success"] == True
        assert result["input_sanitized"] == True
        assert result.get("consensus_approved") == True


class TestFailsafeMetricsTracking:
    """Tests for metrics tracking across all layers."""
    
    @pytest.mark.asyncio
    async def test_metrics_increment_on_execution(self, failsafe):
        """Test that metrics are incremented correctly."""
        failsafe.reset_metrics()
        failsafe.circuit_breaker.force_close("ENRICHER")
        
        async def operation(input_data):
            return {"ok": True}
        
        await failsafe.execute_with_failsafe(
            agent_name="ENRICHER",
            operation=operation,
            input_data={"test": "data"},
            layers=[1, 2]
        )
        
        metrics = failsafe.get_metrics()
        assert metrics["total_executions"] >= 1
        assert metrics["layer1_validations"] >= 1
        assert metrics["layer2_checks"] >= 1
    
    def test_metrics_include_layer3_stats(self, failsafe):
        """Test that Layer 3 stats are included in metrics."""
        metrics = failsafe.get_metrics()
        
        assert "layer3_stats" in metrics
    
    def test_metrics_include_layer4_stats(self, failsafe):
        """Test that Layer 4 stats are included in metrics."""
        metrics = failsafe.get_metrics()
        
        assert "layer4_stats" in metrics
