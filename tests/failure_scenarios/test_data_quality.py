
"""
Data Quality Scenarios
======================
Test agent resilience against malformed, missing, or corrupted data.
"""

import pytest
import json
from core.failure_tracker import FailureTracker, FailureCategory

class TestDataQuality:
    
    def setup_method(self):
        self.tracker = FailureTracker()

    def test_missing_required_fields(self):
        """Verify system handles leads with missing emails."""
        malformed_lead = {
            "first_name": "John",
            "company": "NoEmail Corp"
            # Missing email
        }
        
        try:
            if "email" not in malformed_lead:
                raise ValueError("Validation Failed: Missing required field 'email'")
        except Exception as e:
            failure_id = self.tracker.log_failure(
                agent="SEGMENTOR",
                task_id="test_missing_email",
                error=e,
                context={"lead": malformed_lead}
            )
            
        failure = self.tracker.get_failure(failure_id)
        assert failure.category == FailureCategory.VALIDATION_ERROR.value
        assert "Missing required field" in failure.error_message

    def test_invalid_email_format(self):
        """Verify system rejects invalid email formats."""
        bad_lead = {"email": "john.smthexample.com"} # Missing @
        
        try:
            if "@" not in bad_lead["email"]:
                raise ValueError(f"Invalid email format: {bad_lead['email']}")
        except Exception as e:
            failure_id = self.tracker.log_failure(
                agent="HUNTER",
                task_id="test_invalid_email",
                error=e,
                context={"email": bad_lead["email"]}
            )
            
        failure = self.tracker.get_failure(failure_id)
        assert failure.category == FailureCategory.VALIDATION_ERROR.value

    def test_utf8_encoding_handling(self):
        """Verify system handles special characters in names/companies."""
        # This shouldn't fail, but we test that it doesn't
        complex_lead = {
            "name": "José Nuñez",
            "company": "Café & Téch"
        }
        
        try:
            json_str = json.dumps(complex_lead)
            parsed = json.loads(json_str)
            assert parsed["name"] == "José Nuñez"
        except Exception as e:
            self.tracker.log_failure(
                agent="SYSTEM",
                task_id="test_encoding",
                error=e,
                context=complex_lead
            )
            pytest.fail(f"Encoding failed: {e}")
