#!/usr/bin/env python3
"""
Tests for Email Threading MCP Server
=====================================
"""

import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "mcp-servers" / "email-threading-mcp"))

# Import from email-threading-mcp server
import importlib.util
spec = importlib.util.spec_from_file_location(
    "email_threading_server",
    PROJECT_ROOT / "mcp-servers" / "email-threading-mcp" / "server.py"
)
email_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(email_module)

EmailThreadingMCP = email_module.EmailThreadingMCP
EmailIntent = email_module.EmailIntent
EmailMessage = email_module.EmailMessage


class TestIntentDetection:
    """Test intent classification."""
    
    def setup_method(self):
        self.server = EmailThreadingMCP()
    
    def test_scheduling_request_detection(self):
        texts = [
            "Can we schedule a call for next Tuesday?",
            "What's your availability next week?",
            "I'd love to set up a time to chat",
            "Are you free for a call tomorrow?",
        ]
        for text in texts:
            result = self.server.detect_intent(text)
            assert result["primary_intent"] == "scheduling_request", f"Failed for: {text}"
    
    def test_scheduling_confirm_detection(self):
        texts = [
            "Great, I'm confirmed for Thursday at 10am!",
            "See you on Tuesday at 2pm",
            "Looking forward to our call tomorrow",
        ]
        for text in texts:
            result = self.server.detect_intent(text)
            assert result["primary_intent"] == "scheduling_confirm", f"Failed for: {text}"
    
    def test_scheduling_reschedule_detection(self):
        texts = [
            "I need to reschedule our call",
            "Can we move our meeting to next week?",
            "Something came up, can we find another time?",
        ]
        for text in texts:
            result = self.server.detect_intent(text)
            assert result["primary_intent"] == "scheduling_reschedule", f"Failed for: {text}"
    
    def test_interest_high_detection(self):
        texts = [
            "This is exactly what we've been looking for!",
            "I'm very interested in learning more",
            "We want to move forward with this",
        ]
        for text in texts:
            result = self.server.detect_intent(text)
            assert result["primary_intent"] == "interest_high", f"Failed for: {text}"
    
    def test_objection_detection(self):
        texts = [
            "The pricing seems too expensive for our budget",
            "I'm concerned about the implementation time",
            "We already have a solution we're using",
        ]
        for text in texts:
            result = self.server.detect_intent(text)
            assert result["primary_intent"] == "objection", f"Failed for: {text}"
    
    def test_out_of_office_detection(self):
        texts = [
            "I'm out of the office until January 30th",
            "I'll be on vacation next week with limited email access",
            "This is an automatic reply - I'm away on PTO",
        ]
        for text in texts:
            result = self.server.detect_intent(text)
            assert result["primary_intent"] == "out_of_office", f"Failed for: {text}"
    
    def test_not_interested_detection(self):
        texts = [
            "I'm not interested at this time",
            "Please remove me from your mailing list",
            "This isn't a fit for us, thanks",
        ]
        for text in texts:
            result = self.server.detect_intent(text)
            assert result["primary_intent"] == "not_interested", f"Failed for: {text}"
    
    def test_intent_confidence_included(self):
        result = self.server.detect_intent(
            "Can we schedule a call?",
            include_confidence=True
        )
        assert "all_intents" in result
        assert "confidence" in result
        assert result["confidence"] > 0
    
    def test_scheduling_related_flag(self):
        result = self.server.detect_intent("Let's schedule a meeting")
        assert result["is_scheduling_related"] is True
        
        result = self.server.detect_intent("The pricing is too high")
        assert result["is_scheduling_related"] is False


class TestThreadParsing:
    """Test email thread parsing."""
    
    def setup_method(self):
        self.server = EmailThreadingMCP()
    
    def test_parse_text_thread(self):
        thread = """
        From: john@example.com
        To: sales@company.com
        Subject: Meeting Request
        Date: Mon, 21 Jan 2026 10:00:00 -0500
        
        Hi, I'm interested in your product. Can we chat?
        
        Thanks,
        John
        """
        
        result = self.server.parse_thread(thread, format="text")
        
        assert result["success"] is True
        assert result["message_count"] >= 1
        assert "thread_id" in result
    
    def test_parse_thread_extracts_participants(self):
        thread = """
        From: john@example.com
        To: sales@company.com
        Subject: Re: Meeting
        
        Yes, let's do Tuesday at 2pm.
        
        ---Original Message---
        From: sales@company.com
        To: john@example.com
        Subject: Meeting
        
        When are you available?
        """
        
        result = self.server.parse_thread(thread, format="text")
        
        assert "participants" in result
    
    def test_thread_id_generation(self):
        thread = """
        From: test@example.com
        Subject: Test Subject
        Date: 2026-01-21
        
        Test body
        """
        
        result = self.server.parse_thread(thread, format="text")
        
        assert len(result["thread_id"]) == 12  # MD5 hash truncated


class TestContextExtraction:
    """Test context extraction from threads."""
    
    def setup_method(self):
        self.server = EmailThreadingMCP()
    
    def test_extract_context_detects_intent(self):
        thread = """
        From: john@example.com
        Subject: Meeting Request
        
        Hi, can we schedule a call for next Tuesday at 2pm EST?
        Please send me a calendar invite.
        
        Thanks,
        John
        """
        
        parse_result = self.server.parse_thread(thread, format="text")
        context_result = self.server.extract_context(thread_id=parse_result["thread_id"])
        
        assert context_result["success"] is True
        ctx = context_result["context"]
        assert ctx["detected_intent"] == "scheduling_request"
    
    def test_extract_context_finds_dates(self):
        thread = """
        From: john@example.com
        Subject: Meeting
        
        Let's meet on Tuesday, January 28th or Wednesday next week.
        """
        
        parse_result = self.server.parse_thread(thread, format="text")
        context_result = self.server.extract_context(thread_id=parse_result["thread_id"])
        
        ctx = context_result["context"]
        assert len(ctx["mentioned_dates"]) > 0
    
    def test_extract_context_finds_times(self):
        thread = """
        From: john@example.com
        Subject: Meeting
        
        How about 2:00 PM or 3:30 PM tomorrow afternoon?
        """
        
        parse_result = self.server.parse_thread(thread, format="text")
        context_result = self.server.extract_context(thread_id=parse_result["thread_id"])
        
        ctx = context_result["context"]
        assert len(ctx["mentioned_times"]) > 0
    
    def test_extract_context_analyzes_sentiment(self):
        # Positive
        thread = """
        From: john@example.com
        Subject: Great news!
        
        Thanks so much! This is exactly what we need. 
        I'm really excited to learn more about this.
        """
        
        parse_result = self.server.parse_thread(thread, format="text")
        context_result = self.server.extract_context(thread_id=parse_result["thread_id"])
        
        assert context_result["context"]["sentiment"] == "positive"
    
    def test_extract_context_assesses_urgency(self):
        # High urgency
        thread = """
        From: john@example.com
        Subject: URGENT
        
        We need to discuss this ASAP! Please call me immediately.
        """
        
        parse_result = self.server.parse_thread(thread, format="text")
        context_result = self.server.extract_context(thread_id=parse_result["thread_id"])
        
        assert context_result["context"]["urgency"] == "high"


class TestThreadMaintenance:
    """Test email threading header generation."""
    
    def setup_method(self):
        self.server = EmailThreadingMCP()
    
    def test_maintain_thread_reply(self):
        result = self.server.maintain_thread(
            original_message_id="<abc123@example.com>",
            original_references=["<xyz789@example.com>"],
            original_subject="Meeting Request",
            is_reply=True
        )
        
        assert result["success"] is True
        headers = result["headers"]
        
        assert headers["in_reply_to"] == "<abc123@example.com>"
        assert "<abc123@example.com>" in headers["references"]
        assert headers["subject"].startswith("Re:")
    
    def test_maintain_thread_forward(self):
        result = self.server.maintain_thread(
            original_message_id="<abc123@example.com>",
            original_references=[],
            original_subject="Meeting Request",
            is_reply=False
        )
        
        headers = result["headers"]
        assert headers["subject"].startswith("Fwd:")
    
    def test_maintain_thread_no_double_re(self):
        result = self.server.maintain_thread(
            original_message_id="<abc123@example.com>",
            original_references=[],
            original_subject="Re: Meeting Request",
            is_reply=True
        )
        
        headers = result["headers"]
        assert not headers["subject"].startswith("Re: Re:")


class TestActionItemExtraction:
    """Test action item extraction."""
    
    def setup_method(self):
        self.server = EmailThreadingMCP()
    
    def test_extract_action_items_please(self):
        text = """
        Please review the attached document before our call.
        Could you send me the latest pricing sheet?
        """
        
        result = self.server.extract_action_items(text)
        
        assert result["success"] is True
        assert result["count"] >= 1
    
    def test_extract_action_items_bullets(self):
        text = """
        Here's what we need:
        - Review the proposal
        - Get approval from finance
        - Schedule demo with technical team
        """
        
        result = self.server.extract_action_items(text)
        
        assert result["count"] >= 2


class TestSummaryGeneration:
    """Test thread summarization."""
    
    def setup_method(self):
        self.server = EmailThreadingMCP()
    
    def test_summarize_thread(self):
        thread = """
        From: john@example.com
        Subject: Product Demo
        
        Hi, I'd like to schedule a demo of your product.
        We're looking to improve our sales process.
        
        ---
        From: sales@company.com
        Subject: Re: Product Demo
        
        Great! Here are some available times...
        """
        
        parse_result = self.server.parse_thread(thread, format="text")
        summary_result = self.server.summarize_thread(thread_id=parse_result["thread_id"])
        
        assert summary_result["success"] is True
        assert len(summary_result["summary"]) > 0
        assert summary_result["message_count"] >= 1


class TestEmailAddressParsing:
    """Test email address parsing utilities."""
    
    def setup_method(self):
        self.server = EmailThreadingMCP()
    
    def test_parse_name_and_email(self):
        name, email = self.server._parse_email_address("John Smith <john@example.com>")
        assert name == "John Smith"
        assert email == "john@example.com"
    
    def test_parse_email_only(self):
        name, email = self.server._parse_email_address("john@example.com")
        assert name == ""
        assert email == "john@example.com"
    
    def test_parse_quoted_name(self):
        name, email = self.server._parse_email_address('"John Smith" <john@example.com>')
        assert "John" in name
        assert email == "john@example.com"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
