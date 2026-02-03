#!/usr/bin/env python3
"""
Responder Agent - Objection Classification & Response Handling
==============================================================
Parses inbound replies, classifies objections, and generates response decisions.

Usage:
    python execution/responder_objections.py
    python execution/responder_objections.py --input .hive-mind/replies/replies.jsonl
    python execution/responder_objections.py --dry-run
"""

import sys
import json
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict, field
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from jinja2 import Environment, FileSystemLoader

from core.config import get_objection_action, load_sdr_rules
from core.event_log import log_event, EventType

console = Console(force_terminal=True, no_color=False, legacy_windows=True)


class ObjectionType(Enum):
    """Objection types from sdr_rules.yaml."""
    NOT_INTERESTED = "not_interested"
    BAD_TIMING = "bad_timing"
    ALREADY_HAVE_SOLUTION = "already_have_solution"
    NEED_MORE_INFO = "need_more_info"
    PRICING_OBJECTION = "pricing_objection"
    TECHNICAL_QUESTION = "technical_question"
    POSITIVE_INTEREST = "positive_interest"
    UNKNOWN = "unknown"


class AutomationLevel(Enum):
    """Automation levels for response handling."""
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class EscalationType(Enum):
    """Escalation trigger types."""
    NONE = "none"
    ALWAYS = "always"
    IF_ENTERPRISE = "if_enterprise"
    IF_TIER_1 = "if_tier_1"


@dataclass
class InboundReply:
    """Parsed inbound reply from .hive-mind/replies/replies.jsonl."""
    reply_id: str
    lead_id: str
    campaign_id: str
    email: str
    name: str
    company: str
    subject: str
    body: str
    received_at: str
    icp_tier: str = "unknown"
    employee_count: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class ActionDecision:
    """Output decision for handling an objection."""
    decision_id: str
    reply_id: str
    lead_id: str
    campaign_id: str
    
    objection_type: str
    action: str
    escalation: str
    automation: str
    recommended_response_template: str
    confidence: float
    
    keywords_matched: list = field(default_factory=list)
    should_escalate: bool = False
    escalation_reason: Optional[str] = None
    draft_response: Optional[str] = None
    
    classified_at: str = ""


OBJECTION_KEYWORDS = {
    ObjectionType.NOT_INTERESTED: [
        r"\bnot\s+interested\b",
        r"\bno\s+thanks?\b",
        r"\bremove\s+me\b",
        r"\bunsubscribe\b",
        r"\bstop\s+(?:emailing|contacting)\b",
        r"\bplease\s+don'?t\s+contact\b",
        r"\bnot\s+for\s+(?:us|me)\b",
        r"\bpass\b",
        r"\bnot\s+a\s+fit\b",
        r"\bno\s+need\b",
    ],
    ObjectionType.BAD_TIMING: [
        r"\bnot\s+(?:right\s+)?now\b",
        r"\bbad\s+timing\b",
        r"\bbusy\s+(?:right\s+now|at\s+the\s+moment)\b",
        r"\bmaybe\s+later\b",
        r"\breach\s+out\s+(?:in\s+)?(?:a\s+few\s+months?|next\s+(?:quarter|year))\b",
        r"\bQ[1-4]\b",
        r"\bnext\s+(?:quarter|year|month)\b",
        r"\bafter\s+(?:the\s+)?(?:holidays?|new\s+year)\b",
        r"\bwrapped\s+up\b",
        r"\bin\s+the\s+middle\s+of\b",
        r"\bcurrently\s+(?:focused|working)\s+on\b",
    ],
    ObjectionType.ALREADY_HAVE_SOLUTION: [
        r"\balready\s+(?:have|use|using)\b",
        r"\bwe\s+(?:use|have)\s+\w+\b",
        r"\bhappy\s+with\s+(?:our\s+)?(?:current|existing)\b",
        r"\bsatisfied\s+with\b",
        r"\block(?:ed)?\s+(?:in|into)\b",
        r"\bunder\s+contract\b",
        r"\bjust\s+(?:signed|implemented|deployed)\b",
        r"\bgong\b",
        r"\bclari\b",
        r"\bsalesforce\b",
        r"\bhubspot\b",
        r"\boutreach\b",
        r"\bsalesloft\b",
    ],
    ObjectionType.NEED_MORE_INFO: [
        r"\btell\s+me\s+more\b",
        r"\bmore\s+(?:info|information|details)\b",
        r"\bwhat\s+(?:is|does|can)\b",
        r"\bhow\s+does\s+(?:it|this)\s+work\b",
        r"\bcan\s+you\s+(?:explain|share|send)\b",
        r"\bsend\s+(?:me\s+)?(?:info|details|a\s+deck)\b",
        r"\bcase\s+stud(?:y|ies)\b",
        r"\broi\b",
        r"\bresources?\b",
        r"\bdocumentation\b",
    ],
    ObjectionType.PRICING_OBJECTION: [
        r"\bhow\s+much\b",
        r"\bpric(?:e|ing)\b",
        r"\bcost\b",
        r"\bbudget\b",
        r"\bexpensive\b",
        r"\btoo\s+(?:much|pricey)\b",
        r"\bafford\b",
        r"\binvestment\b",
        r"\bwhat'?s?\s+(?:the\s+)?(?:price|cost)\b",
        r"\bdiscount\b",
    ],
    ObjectionType.TECHNICAL_QUESTION: [
        r"\bintegrat(?:e|ion)\b",
        r"\bapi\b",
        r"\bsecurity\b",
        r"\bsso\b",
        r"\bsoc\s*2\b",
        r"\bgdpr\b",
        r"\bcompliance\b",
        r"\bdata\s+(?:privacy|protection|residency)\b",
        r"\bencryption\b",
        r"\buptime\b",
        r"\bsla\b",
        r"\btechnical\s+(?:requirements?|specs?)\b",
        r"\bsalesforce\s+integrat\b",
        r"\bcrm\s+(?:connect|integrat)\b",
    ],
    ObjectionType.POSITIVE_INTEREST: [
        r"\binterested\b",
        r"\blet'?s?\s+(?:chat|talk|connect|meet)\b",
        r"\bschedule\s+(?:a\s+)?(?:call|meeting|demo)\b",
        r"\bbook\s+(?:a\s+)?(?:time|meeting|call)\b",
        r"\bavailab(?:le|ility)\b",
        r"\bcalendar\b",
        r"\bsounds?\s+(?:good|great|interesting)\b",
        r"\bwould\s+(?:love|like)\s+to\s+(?:learn|see|hear)\b",
        r"\bthis\s+(?:looks?|sounds?)\s+(?:interesting|promising)\b",
        r"\byes\b",
        r"\bset\s+(?:up|something\s+up)\b",
        r"\bnext\s+steps?\b",
    ],
}

TEMPLATE_MAPPING = {
    "soft_breakup": "soft_breakup.j2",
    "schedule_future": "schedule_future.j2",
    "displacement_nurture": "displacement_nurture.j2",
    "send_resources": "send_resources.j2",
    "book_meeting": "book_meeting.j2",
    "value_framework": "value_framework.j2",
    "route_to_se": None,
    "unknown": None,
}


class ObjectionClassifier:
    """Rule-based objection classifier using keyword matching."""
    
    def __init__(self):
        self.compiled_patterns = {}
        for objection_type, patterns in OBJECTION_KEYWORDS.items():
            self.compiled_patterns[objection_type] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
    
    def classify(self, text: str) -> tuple[ObjectionType, float, list[str]]:
        """
        Classify text into an objection type.
        
        Returns: (objection_type, confidence, keywords_matched)
        """
        text_lower = text.lower()
        matches_by_type = {}
        
        for objection_type, patterns in self.compiled_patterns.items():
            matched_keywords = []
            for pattern in patterns:
                if pattern.search(text_lower):
                    matched_keywords.append(pattern.pattern)
            if matched_keywords:
                matches_by_type[objection_type] = matched_keywords
        
        if not matches_by_type:
            return ObjectionType.UNKNOWN, 0.0, []
        
        priority_order = [
            ObjectionType.NOT_INTERESTED,
            ObjectionType.POSITIVE_INTEREST,
            ObjectionType.PRICING_OBJECTION,
            ObjectionType.TECHNICAL_QUESTION,
            ObjectionType.ALREADY_HAVE_SOLUTION,
            ObjectionType.BAD_TIMING,
            ObjectionType.NEED_MORE_INFO,
        ]
        
        best_type = None
        best_matches = []
        
        for objection_type in priority_order:
            if objection_type in matches_by_type:
                matches = matches_by_type[objection_type]
                if not best_type or len(matches) > len(best_matches):
                    best_type = objection_type
                    best_matches = matches
        
        if not best_type:
            best_type = list(matches_by_type.keys())[0]
            best_matches = matches_by_type[best_type]
        
        confidence = min(0.5 + (len(best_matches) * 0.15), 0.95)
        
        return best_type, confidence, best_matches


class ObjectionResponder:
    """Handles objection classification and response generation."""
    
    def __init__(self, templates_dir: Optional[Path] = None):
        self.classifier = ObjectionClassifier()
        self.templates_dir = templates_dir or Path(__file__).parent.parent / "templates" / "objections"
        self.replies_path = Path(__file__).parent.parent / ".hive-mind" / "replies" / "replies.jsonl"
        self.decisions_dir = Path(__file__).parent.parent / ".hive-mind" / "decisions"
        self.outbox_path = Path(__file__).parent.parent / ".hive-mind" / "outbox" / "drafts.jsonl"
        
        if self.templates_dir.exists():
            self.jinja_env = Environment(loader=FileSystemLoader(str(self.templates_dir)))
        else:
            self.jinja_env = None
        
        self.decisions_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
    
    def load_replies(self, input_file: Optional[Path] = None) -> list[InboundReply]:
        """Load replies from JSONL file."""
        file_path = input_file or self.replies_path
        replies = []
        
        if not file_path.exists():
            console.print(f"[yellow]No replies file found at {file_path}[/yellow]")
            return replies
        
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    replies.append(InboundReply(**data))
                except (json.JSONDecodeError, TypeError) as e:
                    console.print(f"[yellow]Skipping malformed line: {e}[/yellow]")
        
        return replies
    
    def should_escalate(self, objection_type: str, reply: InboundReply) -> tuple[bool, Optional[str]]:
        """Determine if escalation is needed based on rules."""
        action_config = get_objection_action(objection_type)
        escalation = action_config.get("escalation", "none")
        
        if escalation == "none":
            return False, None
        elif escalation == "always":
            return True, "Always escalate this objection type"
        elif escalation == "if_enterprise":
            if reply.employee_count > 1000:
                return True, f"Enterprise account ({reply.employee_count} employees)"
            return False, None
        elif escalation == "if_tier_1":
            if reply.icp_tier == "tier_1":
                return True, f"Tier 1 account"
            return False, None
        
        return False, None
    
    def get_template_name(self, action: str) -> Optional[str]:
        """Get template filename for an action."""
        return TEMPLATE_MAPPING.get(action)
    
    def generate_draft_response(self, reply: InboundReply, template_name: str) -> Optional[str]:
        """Generate draft response using Jinja2 template."""
        if not self.jinja_env or not template_name:
            return None
        
        try:
            template = self.jinja_env.get_template(template_name)
            return template.render(
                name=reply.name.split()[0] if reply.name else "there",
                full_name=reply.name,
                company=reply.company,
                email=reply.email,
                original_subject=reply.subject,
                original_body=reply.body,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:
            console.print(f"[yellow]Template rendering failed: {e}[/yellow]")
            return None
    
    def classify_reply(self, reply: InboundReply) -> ActionDecision:
        """Classify a single reply and generate action decision."""
        text_to_classify = f"{reply.subject} {reply.body}"
        
        objection_type, confidence, keywords = self.classifier.classify(text_to_classify)
        
        action_config = get_objection_action(objection_type.value)
        action = action_config.get("action", "unknown")
        escalation = action_config.get("escalation", "none")
        automation = action_config.get("automation", "none")
        
        should_escalate, escalation_reason = self.should_escalate(objection_type.value, reply)
        
        template_name = self.get_template_name(action)
        
        draft_response = None
        if automation in ["full", "partial"] and template_name:
            draft_response = self.generate_draft_response(reply, template_name)
        
        import uuid
        decision = ActionDecision(
            decision_id=str(uuid.uuid4()),
            reply_id=reply.reply_id,
            lead_id=reply.lead_id,
            campaign_id=reply.campaign_id,
            objection_type=objection_type.value,
            action=action,
            escalation=escalation,
            automation=automation,
            recommended_response_template=template_name or "",
            confidence=confidence,
            keywords_matched=keywords,
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
            draft_response=draft_response,
            classified_at=datetime.now(timezone.utc).isoformat(),
        )
        
        log_event(
            EventType.REPLY_CLASSIFIED,
            {
                "reply_id": reply.reply_id,
                "lead_id": reply.lead_id,
                "objection_type": objection_type.value,
                "action": action,
                "confidence": confidence,
                "should_escalate": should_escalate,
            }
        )
        
        return decision
    
    def process_replies(self, input_file: Optional[Path] = None, dry_run: bool = False) -> list[ActionDecision]:
        """Process all replies and generate decisions."""
        console.print("\n[bold blue]📨 RESPONDER: Processing inbound replies[/bold blue]")
        
        replies = self.load_replies(input_file)
        
        if not replies:
            console.print("[yellow]No replies to process[/yellow]")
            return []
        
        decisions = []
        
        with Progress() as progress:
            task = progress.add_task("Classifying replies...", total=len(replies))
            
            for reply in replies:
                decision = self.classify_reply(reply)
                decisions.append(decision)
                progress.update(task, advance=1)
        
        if not dry_run:
            self.save_decisions(decisions)
            self.save_drafts(decisions)
        
        return decisions
    
    def save_decisions(self, decisions: list[ActionDecision]):
        """Save decisions to JSONL file."""
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        output_path = self.decisions_dir / f"objections_{date_str}.jsonl"
        
        with open(output_path, "a", encoding="utf-8") as f:
            for decision in decisions:
                f.write(json.dumps(asdict(decision)) + "\n")
        
        console.print(f"[green]✅ Saved {len(decisions)} decisions to {output_path}[/green]")
    
    def save_drafts(self, decisions: list[ActionDecision]):
        """Save draft responses to outbox."""
        drafts = [d for d in decisions if d.draft_response and d.automation in ["full", "partial"]]
        
        if not drafts:
            return
        
        with open(self.outbox_path, "a", encoding="utf-8") as f:
            for decision in drafts:
                draft_record = {
                    "decision_id": decision.decision_id,
                    "reply_id": decision.reply_id,
                    "lead_id": decision.lead_id,
                    "automation": decision.automation,
                    "objection_type": decision.objection_type,
                    "draft_response": decision.draft_response,
                    "created_at": decision.classified_at,
                    "status": "pending_review" if decision.automation == "partial" else "ready_to_send",
                }
                f.write(json.dumps(draft_record) + "\n")
        
        console.print(f"[green]✅ Saved {len(drafts)} drafts to {self.outbox_path}[/green]")
    
    def print_summary(self, decisions: list[ActionDecision]):
        """Print classification summary."""
        if not decisions:
            return
        
        type_counts = {}
        action_counts = {}
        escalation_count = 0
        
        for d in decisions:
            type_counts[d.objection_type] = type_counts.get(d.objection_type, 0) + 1
            action_counts[d.action] = action_counts.get(d.action, 0) + 1
            if d.should_escalate:
                escalation_count += 1
        
        console.print("\n[bold]📊 Classification Summary[/bold]")
        
        type_table = Table(title="Objection Types")
        type_table.add_column("Type", style="cyan")
        type_table.add_column("Count", style="green")
        type_table.add_column("Percentage", style="yellow")
        
        total = len(decisions)
        for obj_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            pct = (count / total * 100) if total > 0 else 0
            type_table.add_row(obj_type, str(count), f"{pct:.1f}%")
        
        console.print(type_table)
        
        action_table = Table(title="Recommended Actions")
        action_table.add_column("Action", style="cyan")
        action_table.add_column("Count", style="green")
        
        for action, count in sorted(action_counts.items(), key=lambda x: -x[1]):
            action_table.add_row(action, str(count))
        
        console.print(action_table)
        
        avg_confidence = sum(d.confidence for d in decisions) / len(decisions)
        console.print(f"\n[dim]Average confidence: {avg_confidence:.2f}[/dim]")
        console.print(f"[dim]Escalations needed: {escalation_count}[/dim]")
        
        full_auto = sum(1 for d in decisions if d.automation == "full")
        partial_auto = sum(1 for d in decisions if d.automation == "partial")
        console.print(f"[dim]Full automation: {full_auto} | Partial: {partial_auto}[/dim]")


def main():
    parser = argparse.ArgumentParser(description="Responder - Objection Classification")
    parser.add_argument("--input", type=Path, help="Input JSONL file with replies")
    parser.add_argument("--dry-run", action="store_true", help="Process without saving")
    
    args = parser.parse_args()
    
    try:
        responder = ObjectionResponder()
        decisions = responder.process_replies(args.input, args.dry_run)
        
        if decisions:
            responder.print_summary(decisions)
            
            if not args.dry_run:
                console.print("\n[bold green]✅ Objection processing complete![/bold green]")
            else:
                console.print("\n[yellow]Dry run - no files saved[/yellow]")
        
    except Exception as e:
        console.print(f"[red]❌ Processing failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
