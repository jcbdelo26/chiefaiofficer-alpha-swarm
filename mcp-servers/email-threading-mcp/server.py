#!/usr/bin/env python3
"""
Email Threading MCP Server
===========================
Model Context Protocol server for email thread parsing and context extraction.

Tools:
- parse_thread: Extract email thread history from raw email
- extract_context: Get conversation context and key information
- detect_intent: Classify email intent (scheduling, objection, interest, etc.)
- maintain_thread: Preserve threading headers for replies
- summarize_thread: Generate concise thread summary
- extract_action_items: Pull out action items from thread

Integration:
- Syncs with ghl-mcp for CRM updates
- Logs parsed threads to .hive-mind/threads/
"""

import os
import sys
import re
import json
import hashlib
import email
from email import policy
from email.parser import BytesParser, Parser
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("email-threading-mcp")

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure threads directory exists
THREADS_DIR = PROJECT_ROOT / ".hive-mind" / "threads"
THREADS_DIR.mkdir(parents=True, exist_ok=True)


class EmailIntent(Enum):
    """Classification of email intent."""
    SCHEDULING_REQUEST = "scheduling_request"
    SCHEDULING_CONFIRM = "scheduling_confirm"
    SCHEDULING_RESCHEDULE = "scheduling_reschedule"
    SCHEDULING_CANCEL = "scheduling_cancel"
    INTEREST_HIGH = "interest_high"
    INTEREST_MEDIUM = "interest_medium"
    INTEREST_LOW = "interest_low"
    OBJECTION = "objection"
    QUESTION = "question"
    FOLLOW_UP = "follow_up"
    OUT_OF_OFFICE = "out_of_office"
    UNSUBSCRIBE = "unsubscribe"
    NOT_INTERESTED = "not_interested"
    REFERRAL = "referral"
    UNKNOWN = "unknown"


@dataclass
class EmailMessage:
    """Parsed email message."""
    message_id: str
    subject: str
    from_email: str
    from_name: str
    to_emails: List[str]
    cc_emails: List[str]
    date: str
    body_text: str
    body_html: Optional[str] = None
    in_reply_to: Optional[str] = None
    references: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ThreadContext:
    """Extracted thread context."""
    thread_id: str
    subject: str
    participants: List[str]
    message_count: int
    first_message_date: str
    last_message_date: str
    primary_sender: str
    primary_recipient: str
    detected_intent: str
    intent_confidence: float
    key_topics: List[str]
    mentioned_dates: List[str]
    mentioned_times: List[str]
    action_items: List[str]
    sentiment: str
    urgency: str
    summary: str


@dataclass
class ThreadingHeaders:
    """Headers needed for proper email threading."""
    message_id: str
    in_reply_to: str
    references: str
    subject: str


class EmailThreadingMCP:
    """
    Email Threading MCP Server implementation.
    Provides email parsing, context extraction, and intent detection.
    """
    
    # Intent detection patterns
    INTENT_PATTERNS = {
        EmailIntent.SCHEDULING_REQUEST: [
            r"(?:can we|could we|let's|shall we)\s+(?:schedule|set up|book|arrange|find time)",
            r"(?:available|free)\s+(?:for a call|to meet|to chat|next week)",
            r"what(?:'s| is) your availability",
            r"when (?:are you|would you be) (?:available|free)",
            r"(?:pick|choose|select) a time",
            r"calendly|cal\.com|schedule.*link",
            r"your availability",
            r"(?:are you|you) (?:available|free)",
            r"set up a (?:time|call|meeting)",
        ],
        EmailIntent.SCHEDULING_CONFIRM: [
            r"(?:confirmed|booked|scheduled|set) for",
            r"(?:see|talk to|meet) you (?:on|at)",
            r"looking forward to (?:our|the) (?:call|meeting|chat)",
            r"calendar invite (?:sent|attached)",
            r"you're all set for",
        ],
        EmailIntent.SCHEDULING_RESCHEDULE: [
            r"(?:need to|have to|would like to) reschedule",
            r"(?:can we|could we) (?:move|push|change) (?:the|our)",
            r"something (?:came up|urgent)",
            r"conflict (?:with|on)",
            r"(?:won't|can't) make (?:it|the|our)",
        ],
        EmailIntent.SCHEDULING_CANCEL: [
            r"(?:need to|have to) cancel",
            r"(?:won't|can't) be able to (?:make|attend)",
            r"(?:canceling|cancelling) (?:the|our)",
            r"not (?:going to|able to) (?:work|happen)",
        ],
        EmailIntent.INTEREST_HIGH: [
            r"(?:very|really|extremely) interested",
            r"(?:exactly|just) what (?:we|I|we've been) (?:need|looking for)",
            r"(?:love|excited) to (?:learn|hear|see) more",
            r"(?:want|need) to (?:move forward|proceed|get started)",
            r"sign (?:me|us) up",
            r"this is exactly",
            r"we've been looking for",
        ],
        EmailIntent.OBJECTION: [
            r"(?:too|very) expensive",
            r"(?:budget|price|cost) (?:is|seems) (?:too|a bit)",
            r"not (?:the right|a good) (?:time|fit)",
            r"(?:already|currently) (?:using|have|work with)",
            r"(?:need to|have to) (?:think about|consider|discuss)",
            r"(?:concern|worried|hesitant) about",
            r"concerned about",
            r"i'm concerned",
        ],
        EmailIntent.NOT_INTERESTED: [
            r"not interested",
            r"(?:please|kindly) (?:remove|take) me (?:off|from)",
            r"(?:don't|do not) (?:contact|email) (?:me|us)",
            r"not (?:a fit|for us|what we need)",
            r"(?:pass|passing) on this",
            r"isn't a fit",
            r"not a fit",
        ],
        EmailIntent.OUT_OF_OFFICE: [
            r"out of (?:the )?office",
            r"(?:on|away on) (?:vacation|holiday|leave|PTO)",
            r"(?:limited|no) access to email",
            r"(?:back|return|returning) (?:on|by)",
            r"automatic reply",
        ],
        EmailIntent.UNSUBSCRIBE: [
            r"unsubscribe",
            r"(?:stop|remove) (?:sending|these)",
            r"opt[- ]?out",
        ],
        EmailIntent.REFERRAL: [
            r"(?:you should|try) (?:talk|reach out|connect) (?:to|with)",
            r"(?:colleague|coworker|teammate) (?:who|that)",
            r"(?:cc'ing|copying|looping in)",
            r"better person to (?:talk|speak) (?:to|with)",
        ],
        EmailIntent.QUESTION: [
            r"^(?:what|how|when|where|why|who|which|can you|could you|do you)",
            r"\?\s*$",
            r"(?:wondering|curious) (?:if|about|whether)",
            r"(?:can you|could you) (?:tell|explain|clarify)",
        ],
    }
    
    # Sentiment patterns
    POSITIVE_PATTERNS = [
        r"(?:thanks|thank you|appreciate)",
        r"(?:great|excellent|wonderful|fantastic|amazing)",
        r"(?:looking forward|excited|eager)",
        r"(?:happy|glad|pleased) to",
    ]
    
    NEGATIVE_PATTERNS = [
        r"(?:unfortunately|regret|sorry)",
        r"(?:disappointed|frustrated|upset)",
        r"(?:problem|issue|concern)",
        r"(?:can't|won't|don't|unable)",
    ]
    
    # Date/time extraction patterns
    DATE_PATTERNS = [
        r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?\b",
        r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
        r"\b(?:today|tomorrow|next week|this week|next month)\b",
    ]
    
    TIME_PATTERNS = [
        r"\b\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm|a\.m\.|p\.m\.)\b",
        r"\b(?:morning|afternoon|evening)\b",
        r"\b(?:noon|midnight)\b",
    ]
    
    def __init__(self):
        self._thread_cache: Dict[str, List[EmailMessage]] = {}
        logger.info("Email Threading MCP Server initialized")
    
    def parse_thread(
        self,
        raw_email: str,
        format: str = "raw"
    ) -> Dict[str, Any]:
        """
        Parse an email thread from raw email content.
        
        Args:
            raw_email: Raw email content (RFC 5322 format or plain text)
            format: "raw" for RFC 5322, "text" for plain forwarded text
        
        Returns:
            Parsed thread with all messages
        """
        if format == "raw":
            messages = self._parse_raw_email(raw_email)
        else:
            messages = self._parse_text_thread(raw_email)
        
        if not messages:
            return {
                "success": False,
                "error": "Could not parse email content",
                "messages": []
            }
        
        # Generate thread ID from first message
        thread_id = self._generate_thread_id(messages[0])
        
        # Cache the thread
        self._thread_cache[thread_id] = messages
        
        # Save to hive-mind
        self._save_thread(thread_id, messages)
        
        return {
            "success": True,
            "thread_id": thread_id,
            "message_count": len(messages),
            "messages": [m.to_dict() for m in messages],
            "subject": messages[0].subject if messages else "",
            "participants": list(set(
                [m.from_email for m in messages] + 
                [e for m in messages for e in m.to_emails]
            ))
        }
    
    def _parse_raw_email(self, raw_email: str) -> List[EmailMessage]:
        """Parse RFC 5322 format email."""
        try:
            if isinstance(raw_email, bytes):
                msg = BytesParser(policy=policy.default).parsebytes(raw_email)
            else:
                msg = Parser(policy=policy.default).parsestr(raw_email)
            
            messages = []
            
            # Parse main message
            main_msg = self._extract_message(msg)
            if main_msg:
                messages.append(main_msg)
            
            # Look for quoted/forwarded content in body
            body = main_msg.body_text if main_msg else ""
            quoted = self._extract_quoted_messages(body)
            messages.extend(quoted)
            
            return messages
            
        except Exception as e:
            logger.error(f"Error parsing raw email: {e}")
            return []
    
    def _extract_message(self, msg) -> Optional[EmailMessage]:
        """Extract EmailMessage from email.message.Message object."""
        try:
            # Get body
            body_text = ""
            body_html = None
            
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/plain":
                        body_text = part.get_content()
                    elif content_type == "text/html":
                        body_html = part.get_content()
            else:
                body_text = msg.get_content()
            
            # Parse from header
            from_header = msg.get("From", "")
            from_name, from_email = self._parse_email_address(from_header)
            
            # Parse to header
            to_header = msg.get("To", "")
            to_emails = self._parse_email_list(to_header)
            
            # Parse cc header
            cc_header = msg.get("Cc", "")
            cc_emails = self._parse_email_list(cc_header)
            
            # Parse references
            references = msg.get("References", "").split()
            
            return EmailMessage(
                message_id=msg.get("Message-ID", self._generate_message_id()),
                subject=msg.get("Subject", ""),
                from_email=from_email,
                from_name=from_name,
                to_emails=to_emails,
                cc_emails=cc_emails,
                date=msg.get("Date", datetime.now().isoformat()),
                body_text=body_text,
                body_html=body_html,
                in_reply_to=msg.get("In-Reply-To"),
                references=references,
                headers={k: v for k, v in msg.items()}
            )
        except Exception as e:
            logger.error(f"Error extracting message: {e}")
            return None
    
    def _parse_text_thread(self, text: str) -> List[EmailMessage]:
        """Parse forwarded/plain text email thread."""
        messages = []
        
        # Split by common forwarding patterns
        patterns = [
            r"-{3,}\s*(?:Original Message|Forwarded message)\s*-{3,}",
            r"(?:On|From:).*(?:wrote|sent):",
            r">{3,}",
        ]
        
        # Split text into message chunks
        chunks = [text]
        for pattern in patterns:
            new_chunks = []
            for chunk in chunks:
                parts = re.split(pattern, chunk, flags=re.IGNORECASE)
                new_chunks.extend(parts)
            chunks = new_chunks
        
        for i, chunk in enumerate(chunks):
            chunk = chunk.strip()
            if len(chunk) < 10:
                continue
            
            # Try to extract metadata from chunk
            from_match = re.search(r"From:\s*(.+?)(?:\n|$)", chunk)
            to_match = re.search(r"To:\s*(.+?)(?:\n|$)", chunk)
            subject_match = re.search(r"Subject:\s*(.+?)(?:\n|$)", chunk)
            date_match = re.search(r"(?:Date|Sent):\s*(.+?)(?:\n|$)", chunk)
            
            # Clean body (remove metadata lines)
            body = chunk
            for match in [from_match, to_match, subject_match, date_match]:
                if match:
                    body = body.replace(match.group(0), "")
            
            from_email = ""
            from_name = ""
            if from_match:
                from_name, from_email = self._parse_email_address(from_match.group(1))
            
            to_emails = []
            if to_match:
                to_emails = self._parse_email_list(to_match.group(1))
            
            messages.append(EmailMessage(
                message_id=self._generate_message_id(),
                subject=subject_match.group(1) if subject_match else "",
                from_email=from_email,
                from_name=from_name,
                to_emails=to_emails,
                cc_emails=[],
                date=date_match.group(1) if date_match else "",
                body_text=body.strip(),
            ))
        
        return messages
    
    def _extract_quoted_messages(self, body: str) -> List[EmailMessage]:
        """Extract quoted messages from email body."""
        messages = []
        
        # Look for "On <date>, <name> wrote:" patterns
        pattern = r"On\s+(.+?),\s*(.+?)\s+(?:wrote|sent):\s*\n([\s\S]+?)(?=(?:On\s+.+?,\s*.+?\s+(?:wrote|sent):)|$)"
        
        for match in re.finditer(pattern, body, re.IGNORECASE):
            date_str = match.group(1).strip()
            from_str = match.group(2).strip()
            quoted_body = match.group(3).strip()
            
            # Remove quote markers
            quoted_body = re.sub(r"^>\s*", "", quoted_body, flags=re.MULTILINE)
            
            from_name, from_email = self._parse_email_address(from_str)
            
            messages.append(EmailMessage(
                message_id=self._generate_message_id(),
                subject="",
                from_email=from_email,
                from_name=from_name,
                to_emails=[],
                cc_emails=[],
                date=date_str,
                body_text=quoted_body,
            ))
        
        return messages
    
    def extract_context(
        self,
        thread_id: Optional[str] = None,
        messages: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Extract context from an email thread.
        
        Args:
            thread_id: ID of cached thread
            messages: List of message dicts (if not using cache)
        
        Returns:
            ThreadContext with extracted information
        """
        # Get messages
        if thread_id and thread_id in self._thread_cache:
            msg_list = self._thread_cache[thread_id]
        elif messages:
            msg_list = [EmailMessage(**m) if isinstance(m, dict) else m for m in messages]
        else:
            return {"success": False, "error": "No thread_id or messages provided"}
        
        if not msg_list:
            return {"success": False, "error": "Empty message list"}
        
        # Extract participants
        participants = list(set(
            [m.from_email for m in msg_list] + 
            [e for m in msg_list for e in m.to_emails]
        ))
        
        # Detect intent from latest message
        latest = msg_list[0]  # Assuming reverse chronological
        intent, confidence = self._detect_intent(latest.body_text)
        
        # Extract topics
        all_text = " ".join(m.body_text for m in msg_list)
        topics = self._extract_topics(all_text)
        
        # Extract dates and times
        dates = self._extract_dates(all_text)
        times = self._extract_times(all_text)
        
        # Extract action items
        action_items = self._extract_action_items(all_text)
        
        # Analyze sentiment
        sentiment = self._analyze_sentiment(latest.body_text)
        
        # Assess urgency
        urgency = self._assess_urgency(latest.body_text)
        
        # Generate summary
        summary = self._generate_summary(msg_list)
        
        context = ThreadContext(
            thread_id=thread_id or self._generate_thread_id(msg_list[0]),
            subject=msg_list[0].subject,
            participants=participants,
            message_count=len(msg_list),
            first_message_date=msg_list[-1].date if msg_list else "",
            last_message_date=msg_list[0].date if msg_list else "",
            primary_sender=msg_list[0].from_email,
            primary_recipient=msg_list[0].to_emails[0] if msg_list[0].to_emails else "",
            detected_intent=intent.value,
            intent_confidence=confidence,
            key_topics=topics,
            mentioned_dates=dates,
            mentioned_times=times,
            action_items=action_items,
            sentiment=sentiment,
            urgency=urgency,
            summary=summary,
        )
        
        return {
            "success": True,
            "context": asdict(context)
        }
    
    def detect_intent(
        self,
        text: str,
        include_confidence: bool = True
    ) -> Dict[str, Any]:
        """
        Detect the intent of an email message.
        
        Args:
            text: Email body text
            include_confidence: Include confidence scores for all intents
        
        Returns:
            Primary intent and optionally all scores
        """
        primary_intent, confidence = self._detect_intent(text)
        
        result = {
            "success": True,
            "primary_intent": primary_intent.value,
            "confidence": confidence,
            "is_scheduling_related": primary_intent.value.startswith("scheduling_"),
        }
        
        if include_confidence:
            all_scores = self._get_all_intent_scores(text)
            result["all_intents"] = {k.value: v for k, v in all_scores.items()}
        
        return result
    
    def _detect_intent(self, text: str) -> Tuple[EmailIntent, float]:
        """Detect primary intent with confidence score."""
        text_lower = text.lower()
        
        scores = {}
        for intent, patterns in self.INTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = re.findall(pattern, text_lower, re.IGNORECASE)
                score += len(matches)
            scores[intent] = score
        
        if not any(scores.values()):
            return EmailIntent.UNKNOWN, 0.0
        
        max_intent = max(scores, key=scores.get)
        max_score = scores[max_intent]
        total_score = sum(scores.values())
        
        confidence = max_score / total_score if total_score > 0 else 0
        
        return max_intent, round(confidence, 2)
    
    def _get_all_intent_scores(self, text: str) -> Dict[EmailIntent, float]:
        """Get normalized scores for all intents."""
        text_lower = text.lower()
        
        scores = {}
        for intent, patterns in self.INTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = re.findall(pattern, text_lower, re.IGNORECASE)
                score += len(matches)
            scores[intent] = score
        
        total = sum(scores.values()) or 1
        return {k: round(v / total, 2) for k, v in scores.items()}
    
    def maintain_thread(
        self,
        original_message_id: str,
        original_references: List[str],
        original_subject: str,
        is_reply: bool = True
    ) -> Dict[str, Any]:
        """
        Generate proper threading headers for a reply.
        
        Args:
            original_message_id: Message-ID of email being replied to
            original_references: References header from original
            original_subject: Subject of original email
            is_reply: True for reply, False for forward
        
        Returns:
            ThreadingHeaders for the new message
        """
        # Generate new message ID
        new_message_id = self._generate_message_id()
        
        # Build references chain
        references = original_references.copy() if original_references else []
        if original_message_id and original_message_id not in references:
            references.append(original_message_id)
        
        # Format subject
        subject = original_subject
        if is_reply and not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        elif not is_reply and not subject.lower().startswith("fwd:"):
            subject = f"Fwd: {subject}"
        
        headers = ThreadingHeaders(
            message_id=new_message_id,
            in_reply_to=original_message_id,
            references=" ".join(references),
            subject=subject,
        )
        
        return {
            "success": True,
            "headers": asdict(headers),
            "header_lines": {
                "Message-ID": new_message_id,
                "In-Reply-To": original_message_id,
                "References": " ".join(references),
                "Subject": subject,
            }
        }
    
    def summarize_thread(
        self,
        thread_id: Optional[str] = None,
        messages: Optional[List[Dict]] = None,
        max_length: int = 200
    ) -> Dict[str, Any]:
        """
        Generate a concise summary of an email thread.
        
        Args:
            thread_id: ID of cached thread
            messages: List of message dicts
            max_length: Maximum summary length
        
        Returns:
            Thread summary
        """
        if thread_id and thread_id in self._thread_cache:
            msg_list = self._thread_cache[thread_id]
        elif messages:
            msg_list = [EmailMessage(**m) if isinstance(m, dict) else m for m in messages]
        else:
            return {"success": False, "error": "No thread data"}
        
        summary = self._generate_summary(msg_list, max_length)
        
        return {
            "success": True,
            "summary": summary,
            "message_count": len(msg_list),
            "participants": list(set(m.from_email for m in msg_list)),
        }
    
    def extract_action_items(
        self,
        text: str
    ) -> Dict[str, Any]:
        """
        Extract action items from email text.
        
        Args:
            text: Email body text
        
        Returns:
            List of action items
        """
        items = self._extract_action_items(text)
        
        return {
            "success": True,
            "action_items": items,
            "count": len(items),
        }
    
    def _extract_action_items(self, text: str) -> List[str]:
        """Extract action items from text."""
        items = []
        
        patterns = [
            r"(?:please|kindly|could you|can you|would you)\s+(.+?)(?:\.|$)",
            r"(?:need to|have to|must|should)\s+(.+?)(?:\.|$)",
            r"(?:action item|todo|to-do|task):\s*(.+?)(?:\.|$)",
            r"(?:^|\n)\s*[-•*]\s*(.+?)(?:\n|$)",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                item = match.strip()
                if len(item) > 10 and len(item) < 200:
                    items.append(item)
        
        return list(set(items))[:10]  # Dedupe and limit
    
    def _extract_topics(self, text: str) -> List[str]:
        """Extract key topics from text."""
        # Simple keyword extraction
        words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        
        # Count frequencies
        freq = {}
        for word in words:
            if len(word) > 3:
                freq[word] = freq.get(word, 0) + 1
        
        # Return top topics
        sorted_topics = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [t[0] for t in sorted_topics[:5]]
    
    def _extract_dates(self, text: str) -> List[str]:
        """Extract mentioned dates."""
        dates = []
        for pattern in self.DATE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(matches)
        return list(set(dates))[:5]
    
    def _extract_times(self, text: str) -> List[str]:
        """Extract mentioned times."""
        times = []
        for pattern in self.TIME_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            times.extend(matches)
        return list(set(times))[:5]
    
    def _analyze_sentiment(self, text: str) -> str:
        """Analyze sentiment of text."""
        text_lower = text.lower()
        
        positive_score = sum(
            len(re.findall(p, text_lower)) 
            for p in self.POSITIVE_PATTERNS
        )
        
        negative_score = sum(
            len(re.findall(p, text_lower)) 
            for p in self.NEGATIVE_PATTERNS
        )
        
        if positive_score > negative_score + 1:
            return "positive"
        elif negative_score > positive_score + 1:
            return "negative"
        return "neutral"
    
    def _assess_urgency(self, text: str) -> str:
        """Assess urgency level."""
        text_lower = text.lower()
        
        high_urgency = [
            r"urgent", r"asap", r"immediately", r"today", r"right away",
            r"critical", r"emergency", r"!!!",
        ]
        
        medium_urgency = [
            r"soon", r"this week", r"by (?:friday|end of week)",
            r"important", r"priority",
        ]
        
        high_score = sum(1 for p in high_urgency if re.search(p, text_lower))
        medium_score = sum(1 for p in medium_urgency if re.search(p, text_lower))
        
        if high_score >= 2:
            return "high"
        elif high_score >= 1 or medium_score >= 2:
            return "medium"
        return "low"
    
    def _generate_summary(
        self,
        messages: List[EmailMessage],
        max_length: int = 200
    ) -> str:
        """Generate thread summary."""
        if not messages:
            return ""
        
        latest = messages[0]
        intent, _ = self._detect_intent(latest.body_text)
        
        # Build summary
        parts = [
            f"{len(messages)} message thread",
            f"from {latest.from_name or latest.from_email}",
        ]
        
        if intent != EmailIntent.UNKNOWN:
            intent_desc = intent.value.replace("_", " ")
            parts.append(f"- {intent_desc}")
        
        summary = " ".join(parts)
        
        # Add first sentence of latest message if room
        first_sentence = re.split(r'[.!?]', latest.body_text)[0].strip()
        if len(summary) + len(first_sentence) < max_length:
            summary += f": \"{first_sentence[:100]}...\""
        
        return summary[:max_length]
    
    def _parse_email_address(self, addr: str) -> Tuple[str, str]:
        """Parse 'Name <email>' format."""
        addr = addr.strip()
        
        # Check for "Name <email>" format
        match = re.match(r'^"?([^"<]*)"?\s*<([^<>]+@[^<>]+)>$', addr)
        if match:
            name = match.group(1).strip()
            email_addr = match.group(2).strip()
            return name, email_addr
        
        # Check for plain email
        if re.match(r'^[^<>]+@[^<>]+$', addr):
            return "", addr
        
        # Fallback
        return "", addr
    
    def _parse_email_list(self, header: str) -> List[str]:
        """Parse comma-separated email list."""
        emails = []
        for addr in header.split(","):
            _, email = self._parse_email_address(addr)
            if email and "@" in email:
                emails.append(email)
        return emails
    
    def _generate_thread_id(self, message: EmailMessage) -> str:
        """Generate thread ID from message."""
        seed = f"{message.subject}:{message.from_email}:{message.date}"
        return hashlib.md5(seed.encode()).hexdigest()[:12]
    
    def _generate_message_id(self) -> str:
        """Generate unique message ID."""
        import uuid
        return f"<{uuid.uuid4()}@caio-swarm.local>"
    
    def _save_thread(self, thread_id: str, messages: List[EmailMessage]):
        """Save thread to hive-mind storage."""
        thread_file = THREADS_DIR / f"{thread_id}.json"
        
        data = {
            "thread_id": thread_id,
            "saved_at": datetime.now().isoformat(),
            "message_count": len(messages),
            "messages": [m.to_dict() for m in messages],
        }
        
        thread_file.write_text(json.dumps(data, indent=2))
        logger.info(f"Saved thread {thread_id} with {len(messages)} messages")
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Return MCP tool definitions."""
        return [
            {
                "name": "parse_thread",
                "description": "Parse an email thread from raw content",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "raw_email": {"type": "string", "description": "Raw email content"},
                        "format": {"type": "string", "enum": ["raw", "text"], "default": "raw"}
                    },
                    "required": ["raw_email"]
                }
            },
            {
                "name": "extract_context",
                "description": "Extract context and key information from email thread",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "thread_id": {"type": "string"},
                        "messages": {"type": "array", "items": {"type": "object"}}
                    }
                }
            },
            {
                "name": "detect_intent",
                "description": "Detect intent of an email (scheduling, objection, interest, etc.)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Email body text"},
                        "include_confidence": {"type": "boolean", "default": True}
                    },
                    "required": ["text"]
                }
            },
            {
                "name": "maintain_thread",
                "description": "Generate proper threading headers for reply/forward",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "original_message_id": {"type": "string"},
                        "original_references": {"type": "array", "items": {"type": "string"}},
                        "original_subject": {"type": "string"},
                        "is_reply": {"type": "boolean", "default": True}
                    },
                    "required": ["original_message_id", "original_subject"]
                }
            },
            {
                "name": "summarize_thread",
                "description": "Generate concise summary of email thread",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "thread_id": {"type": "string"},
                        "messages": {"type": "array"},
                        "max_length": {"type": "integer", "default": 200}
                    }
                }
            },
            {
                "name": "extract_action_items",
                "description": "Extract action items from email text",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"}
                    },
                    "required": ["text"]
                }
            }
        ]


async def main():
    """Demo the email threading MCP."""
    server = EmailThreadingMCP()
    
    print("=" * 60)
    print("Email Threading MCP Server")
    print("=" * 60)
    
    # Demo intent detection
    print("\n[Intent Detection Demo]")
    
    test_emails = [
        ("Can we schedule a call for next Tuesday at 2pm?", "scheduling_request"),
        ("Thanks, I'm confirmed for Thursday at 10am!", "scheduling_confirm"),
        ("We need to reschedule - something came up", "scheduling_reschedule"),
        ("This is exactly what we've been looking for!", "interest_high"),
        ("The pricing seems a bit high for our budget", "objection"),
        ("I'll be out of office until January 30th", "out_of_office"),
        ("Please remove me from your mailing list", "unsubscribe"),
    ]
    
    for text, expected in test_emails:
        result = server.detect_intent(text, include_confidence=False)
        status = "[OK]" if result["primary_intent"] == expected else "[X]"
        print(f"  {status} '{text[:40]}...' -> {result['primary_intent']}")
    
    # Demo context extraction
    print("\n[Context Extraction Demo]")
    
    sample_thread = """
    From: John Smith <john@example.com>
    To: sales@company.com
    Subject: Re: Meeting Request
    Date: Mon, 21 Jan 2026 14:30:00 -0500
    
    Hi there,
    
    Yes, I'm very interested in learning more! Can we schedule a call for 
    next Tuesday at 2pm EST? Please send me a calendar invite.
    
    Looking forward to it!
    John
    
    ---Original Message---
    From: sales@company.com
    To: john@example.com
    Subject: Meeting Request
    
    Hi John,
    
    I wanted to follow up on our previous conversation about your RevOps needs.
    Would you be available for a quick call this week?
    
    Best,
    Sales Team
    """
    
    result = server.parse_thread(sample_thread, format="text")
    print(f"  Parsed {result['message_count']} messages")
    
    context = server.extract_context(thread_id=result['thread_id'])
    if context['success']:
        ctx = context['context']
        print(f"  Intent: {ctx['detected_intent']} ({ctx['intent_confidence']})")
        print(f"  Sentiment: {ctx['sentiment']}")
        print(f"  Urgency: {ctx['urgency']}")
        print(f"  Mentioned dates: {ctx['mentioned_dates']}")
        print(f"  Mentioned times: {ctx['mentioned_times']}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
