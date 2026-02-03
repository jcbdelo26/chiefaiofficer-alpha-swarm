#!/usr/bin/env python3
"""
Tests for Day 22 AIDefence PII Enhancements
- Response system (BLOCK/SANITIZE/WARN/LOG)
- Self-learning (false positive/negative tracking)
- Agent I/O integration
"""

import pytest
import asyncio
from pathlib import Path
import json
import shutil

from core.aidefence import (
    AIDefence,
    PIIDetector,
    PIIType,
    PIIResponse,
    PIIBlockedError,
    with_pii_protection
)


@pytest.fixture
def temp_learning_dir(tmp_path):
    """Create temporary learning directory."""
    learning_dir = tmp_path / "aidefence"
    learning_dir.mkdir(parents=True, exist_ok=True)
    yield learning_dir
    # Cleanup
    if learning_dir.exists():
        shutil.rmtree(learning_dir)


@pytest.fixture
def pii_detector(temp_learning_dir):
    """Create PII detector with temp learning dir."""
    return PIIDetector(learning_dir=temp_learning_dir)


# =============================================================================
# RESPONSE SYSTEM TESTS
# =============================================================================

def test_pii_response_block_api_key(pii_detector):
    """Test BLOCK response for API keys."""
    text = "My API key: sk-abcdefghijklmnopqrstuvwxyz123456"
    pii_scan = pii_detector.scan(text)
    response = pii_detector.determine_pii_response(pii_scan)
    assert response == PIIResponse.BLOCK


def test_pii_response_block_password(pii_detector):
    """Test BLOCK response for passwords."""
    text = "password: MySuperSecretPass123!@#"
    pii_scan = pii_detector.scan(text)
    response = pii_detector.determine_pii_response(pii_scan)
    assert response == PIIResponse.BLOCK


def test_pii_response_sanitize_ssn(pii_detector):
    """Test SANITIZE response for SSN."""
    text = "My SSN is 123-45-6789"
    pii_scan = pii_detector.scan(text)
    response = pii_detector.determine_pii_response(pii_scan)
    assert response == PIIResponse.SANITIZE


def test_pii_response_sanitize_credit_card(pii_detector):
    """Test SANITIZE response for credit card."""
    text = "Card number: 4532015112830366"
    pii_scan = pii_detector.scan(text)
    response = pii_detector.determine_pii_response(pii_scan)
    assert response == PIIResponse.SANITIZE


def test_pii_response_warn_email(pii_detector):
    """Test WARN response for email."""
    text = "Contact me at john@example.com"
    pii_scan = pii_detector.scan(text)
    response = pii_detector.determine_pii_response(pii_scan)
    assert response == PIIResponse.WARN


def test_pii_response_warn_phone(pii_detector):
    """Test WARN response for phone."""
    text = "Call me at 555-123-4567"
    pii_scan = pii_detector.scan(text)
    response = pii_detector.determine_pii_response(pii_scan)
    assert response == PIIResponse.WARN


def test_pii_response_log_no_pii(pii_detector):
    """Test LOG response when no PII detected."""
    text = "This is a clean message"
    pii_scan = pii_detector.scan(text)
    response = pii_detector.determine_pii_response(pii_scan)
    assert response == PIIResponse.LOG


@pytest.mark.asyncio
async def test_handle_pii_detection_block(pii_detector):
    """Test handle_pii_detection blocks critical PII."""
    text = "API key: sk-abcdefghijklmnopqrstuvwxyz123456"
    pii_scan = pii_detector.scan(text)
    
    allow, processed, action = await pii_detector.handle_pii_detection(text, pii_scan)
    
    assert allow == False
    assert processed == ""
    assert "BLOCKED" in action


@pytest.mark.asyncio
async def test_handle_pii_detection_sanitize(pii_detector):
    """Test handle_pii_detection sanitizes high PII."""
    text = "My SSN is 123-45-6789"
    pii_scan = pii_detector.scan(text)
    
    allow, processed, action = await pii_detector.handle_pii_detection(text, pii_scan)
    
    assert allow == True
    assert "[SSN_REDACTED]" in processed
    assert "SANITIZED" in action


@pytest.mark.asyncio
async def test_handle_pii_detection_warn(pii_detector):
    """Test handle_pii_detection warns on medium PII."""
    text = "Email: test@example.com"
    pii_scan = pii_detector.scan(text)
    
    allow, processed, action = await pii_detector.handle_pii_detection(text, pii_scan)
    
    assert allow == True
    assert processed == text  # Not redacted
    assert "WARNED" in action


# =============================================================================
# SELF-LEARNING TESTS
# =============================================================================

def test_report_false_positive(pii_detector, temp_learning_dir):
    """Test false positive reporting."""
    pii_detector.report_false_positive(
        text="Call me at extension 12345",
        pii_type=PIIType.PHONE,
        value="12345",
        reason="Internal extension, not a phone number"
    )
    
    # Verify saved
    fp_path = temp_learning_dir / "false_positives.json"
    assert fp_path.exists()
    
    with open(fp_path) as f:
        fps = json.load(f)
    
    assert len(fps) == 1
    assert fps[0]["pii_type"] == "phone"
    assert fps[0]["value"] == "12345"
    assert "extension" in fps[0]["reason"]


def test_report_false_negative(pii_detector, temp_learning_dir):
    """Test false negative reporting."""
    pii_detector.report_false_negative(
        text="My employee ID is EMP-12345",
        pii_type=PIIType.PASSPORT,
        value="EMP-12345",
        reason="Should detect employee IDs as sensitive"
    )
    
    # Verify saved
    fn_path = temp_learning_dir / "false_negatives.json"
    assert fn_path.exists()
    
    with open(fn_path) as f:
        fns = json.load(f)
    
    assert len(fns) == 1
    assert fns[0]["pii_type"] == "passport"
    assert fns[0]["value"] == "EMP-12345"


def test_get_learning_stats_empty(pii_detector):
    """Test learning stats when no feedback."""
    stats = pii_detector.get_learning_stats()
    assert stats["false_positives"] == 0
    assert stats["false_negatives"] == 0


def test_get_learning_stats_with_data(pii_detector):
    """Test learning stats with feedback data."""
    # Add some feedback
    pii_detector.report_false_positive(
        "test1", PIIType.PHONE, "12345", "reason1"
    )
    pii_detector.report_false_positive(
        "test2", PIIType.EMAIL, "test@test.com", "reason2"
    )
    pii_detector.report_false_negative(
        "test3", PIIType.SSN, "123-45-6789", "reason3"
    )
    
    stats = pii_detector.get_learning_stats()
    assert stats["false_positives"] == 2
    assert stats["false_negatives"] == 1


# =============================================================================
# AGENT I/O INTEGRATION TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_with_pii_protection_blocks_critical():
    """Test decorator blocks critical PII."""
    
    @with_pii_protection()
    async def process_input(text: str) -> str:
        return f"Processed: {text}"
    
    # Should block API key
    with pytest.raises(PIIBlockedError):
        await process_input("My API key: sk-abcdefghijklmnopqrstuvwxyz123456")


@pytest.mark.asyncio
async def test_with_pii_protection_sanitizes_input():
    """Test decorator sanitizes high PII in input."""
    
    @with_pii_protection()
    async def process_input(text: str) -> str:
        return f"Processed: {text}"
    
    # Should sanitize SSN
    result = await process_input("My SSN is 123-45-6789")
    assert "[SSN_REDACTED]" in result


@pytest.mark.asyncio
async def test_with_pii_protection_sanitizes_output():
    """Test decorator sanitizes PII in output."""
    
    @with_pii_protection()
    async def generate_output() -> str:
        return "User email: john@example.com, SSN: 123-45-6789"
    
    result = await generate_output()
    assert "[EMAIL_REDACTED]" in result
    assert "[SSN_REDACTED]" in result


@pytest.mark.asyncio
async def test_with_pii_protection_allows_clean_input():
    """Test decorator allows clean input."""
    
    @with_pii_protection()
    async def process_input(text: str) -> str:
        return f"Processed: {text}"
    
    result = await process_input("This is a clean message with no PII")
    assert "Processed: This is a clean message" in result


@pytest.mark.asyncio
async def test_with_pii_protection_no_block_mode():
    """Test decorator with block_on_critical=False."""
    
    @with_pii_protection(block_on_critical=False)
    async def process_input(text: str) -> str:
        return f"Processed: {text}"
    
    # Should not raise, but should sanitize
    result = await process_input("API key: sk-abcdefghijklmnopqrstuvwxyz123456")
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in result  # Should be redacted


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

def test_aidefence_with_pii_response_system():
    """Test AIDefence integration with PII response system."""
    aidefence = AIDefence()
    
    # Test with critical PII
    text = "My password: SuperSecret123!"
    analysis = aidefence.analyze(text, scan_pii=True)
    
    assert analysis.pii_scan is not None
    assert analysis.pii_scan.has_pii
    assert analysis.pii_scan.risk_level in ["high", "critical"]
    
    # Test response determination
    response = aidefence.pii_detector.determine_pii_response(analysis.pii_scan)
    assert response in [PIIResponse.BLOCK, PIIResponse.SANITIZE]


def test_multiple_pii_types_in_text(pii_detector):
    """Test handling multiple PII types in same text."""
    text = "Contact: john@example.com, Phone: 555-123-4567, SSN: 123-45-6789"
    pii_scan = pii_detector.scan(text)
    
    assert pii_scan.has_pii
    assert len(pii_scan.matches) >= 3
    
    # Should be high or critical risk
    assert pii_scan.risk_level in ["high", "critical"]
    
    # Response should be SANITIZE or BLOCK
    response = pii_detector.determine_pii_response(pii_scan)
    assert response in [PIIResponse.SANITIZE, PIIResponse.BLOCK]


@pytest.mark.asyncio
async def test_end_to_end_pii_protection_flow():
    """Test complete PII protection flow."""
    
    @with_pii_protection()
    async def agent_process(user_input: str) -> str:
        # Simulate agent processing
        return f"Agent response based on: {user_input}"
    
    # Test 1: Clean input
    result1 = await agent_process("What's the weather today?")
    assert "weather" in result1
    
    # Test 2: Input with email (should warn but allow)
    result2 = await agent_process("My email is test@example.com")
    assert result2  # Should process
    
    # Test 3: Input with SSN (should sanitize)
    result3 = await agent_process("My SSN is 123-45-6789")
    assert "[SSN_REDACTED]" in result3
    
    # Test 4: Input with API key (should block)
    with pytest.raises(PIIBlockedError):
        await agent_process("My API key: sk-abcdefghijklmnopqrstuvwxyz123456")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
