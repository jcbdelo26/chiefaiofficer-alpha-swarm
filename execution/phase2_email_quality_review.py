#!/usr/bin/env python3
"""
Phase 2: Email Quality Review
=============================

Exports email samples for Dani to review and score.
Records feedback for agent training.

Usage:
    python execution/phase2_email_quality_review.py --export
    python execution/phase2_email_quality_review.py --record-scores
    python execution/phase2_email_quality_review.py --status
"""

import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

REPORTS_DIR = PROJECT_ROOT / ".hive-mind" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

REVIEW_FILE = REPORTS_DIR / "emails_for_quality_review.json"
SCORES_FILE = REPORTS_DIR / "email_review_scores.json"

# Quality criteria
QUALITY_CRITERIA = [
    {
        "name": "personalization",
        "description": "How well is the email personalized to the recipient?",
        "weight": 0.25
    },
    {
        "name": "subject_line",
        "description": "Is the subject line compelling and relevant?",
        "weight": 0.20
    },
    {
        "name": "value_proposition",
        "description": "Is the value proposition clear and compelling?",
        "weight": 0.25
    },
    {
        "name": "cta",
        "description": "Is the call-to-action appropriate and clear?",
        "weight": 0.15
    },
    {
        "name": "professional_tone",
        "description": "Is the tone professional and appropriate?",
        "weight": 0.15
    }
]


def export_emails_for_review(limit: int = 20):
    """Export pending and recent emails for quality review."""
    print("\n" + "="*60)
    print("  Phase 2: Email Quality Review Export")
    print("="*60)
    
    shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
    gatekeeper_dir = PROJECT_ROOT / ".hive-mind" / "gatekeeper_queue"
    
    emails = []
    
    # Collect from shadow_mode_emails - prioritize blog_intent emails
    if shadow_dir.exists():
        # First get blog_intent emails (from website intent monitor)
        blog_intent_files = sorted(shadow_dir.glob("blog_intent_*.json"), reverse=True)
        other_files = sorted([f for f in shadow_dir.glob("*.json") if not f.name.startswith("blog_intent")], reverse=True)
        all_files = blog_intent_files + other_files
        
        for f in all_files[:limit]:
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    emails.append({
                        "source": "shadow_mode_emails",
                        "file": f.name,
                        "email_id": data.get("email_id", f.stem),
                        "to": data.get("to"),
                        "recipient_name": data.get("recipient_data", {}).get("name"),
                        "recipient_company": data.get("recipient_data", {}).get("company"),
                        "recipient_title": data.get("recipient_data", {}).get("title"),
                        "subject": data.get("subject"),
                        "body": data.get("body"),
                        "context": data.get("context", {}),
                        "priority": data.get("priority"),
                        "status": data.get("status"),
                        "created_at": data.get("created_at")
                    })
            except Exception as e:
                print(f"  Warning: Could not read {f.name}: {e}")
    
    # Collect from gatekeeper_queue
    if gatekeeper_dir.exists():
        for f in sorted(gatekeeper_dir.glob("*.json"), reverse=True)[:limit]:
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    
                    # Check if already in list
                    email_id = data.get("queue_id", f.stem)
                    if any(e["email_id"] == email_id for e in emails):
                        continue
                    
                    emails.append({
                        "source": "gatekeeper_queue",
                        "file": f.name,
                        "email_id": email_id,
                        "to": data.get("visitor", {}).get("email"),
                        "recipient_name": data.get("visitor", {}).get("name"),
                        "recipient_company": data.get("visitor", {}).get("company"),
                        "recipient_title": data.get("visitor", {}).get("title"),
                        "subject": data.get("email", {}).get("subject"),
                        "body": data.get("email", {}).get("body"),
                        "context": data.get("context", {}),
                        "priority": data.get("priority"),
                        "status": "pending",
                        "created_at": data.get("created_at")
                    })
            except Exception as e:
                print(f"  Warning: Could not read {f.name}: {e}")
    
    if not emails:
        print("\n  No emails found to review.")
        print("  Run: python execution/diagnose_email_pipeline.py --test-visitor")
        return
    
    # Create review document
    review_doc = {
        "title": "CAIO Swarm Email Quality Review",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": "Dani Apgar",
        "instructions": """
REVIEW INSTRUCTIONS
===================

Score each email from 1-5 on each criterion:
  1 = Poor - Needs significant improvement
  2 = Below Average - Has notable issues
  3 = Average - Acceptable but room for improvement
  4 = Good - Meets expectations
  5 = Excellent - Exceeds expectations

CRITERIA:
- Personalization: How well does the email reference the recipient's specific situation?
- Subject Line: Is it compelling, relevant, and likely to get opened?
- Value Proposition: Is the benefit to the recipient clear and compelling?
- CTA: Is the call-to-action clear, appropriate, and easy to act on?
- Professional Tone: Is the email professional while still being conversational?

PASS THRESHOLD: Average score >= 3.5/5

Please also note any specific feedback for agent training.
        """,
        "criteria": QUALITY_CRITERIA,
        "emails": emails[:limit],
        "scoring_template": {
            "email_id": "",
            "personalization": 0,
            "subject_line": 0,
            "value_proposition": 0,
            "cta": 0,
            "professional_tone": 0,
            "notes": ""
        }
    }
    
    # Save review document
    with open(REVIEW_FILE, "w") as f:
        json.dump(review_doc, f, indent=2)
    
    print(f"\n  Exported {len(emails)} emails for review")
    print(f"  Review file: {REVIEW_FILE}")
    
    # Also create a markdown version for easy reading
    md_file = REPORTS_DIR / "emails_for_review.md"
    with open(md_file, "w") as f:
        f.write("# CAIO Swarm Email Quality Review\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n")
        f.write(f"**Emails:** {len(emails)}\n")
        f.write(f"**Reviewer:** Dani Apgar\n\n")
        f.write("---\n\n")
        
        for i, email in enumerate(emails, 1):
            f.write(f"## Email {i}: {email.get('email_id', 'Unknown')}\n\n")
            f.write(f"**To:** {email.get('to')}\n")
            f.write(f"**Recipient:** {email.get('recipient_name')} - {email.get('recipient_title')} at {email.get('recipient_company')}\n")
            f.write(f"**Priority:** {email.get('priority')}\n")
            f.write(f"**Intent Score:** {email.get('context', {}).get('intent_score', 'N/A')}\n\n")
            
            f.write(f"### Subject\n\n")
            f.write(f"> {email.get('subject', 'No subject')}\n\n")
            
            f.write(f"### Body\n\n")
            f.write(f"```\n{email.get('body', 'No body')}\n```\n\n")
            
            if email.get('context', {}).get('warm_connections'):
                f.write(f"### Warm Connections\n\n")
                for conn in email['context']['warm_connections']:
                    f.write(f"- {conn.get('type')}: {conn.get('shared')} (via {conn.get('team_member')})\n")
                f.write("\n")
            
            f.write(f"### Score (1-5)\n\n")
            f.write(f"| Criterion | Score | Notes |\n")
            f.write(f"|-----------|-------|-------|\n")
            f.write(f"| Personalization | __ | |\n")
            f.write(f"| Subject Line | __ | |\n")
            f.write(f"| Value Proposition | __ | |\n")
            f.write(f"| CTA | __ | |\n")
            f.write(f"| Professional Tone | __ | |\n\n")
            
            f.write("---\n\n")
    
    print(f"  Markdown file: {md_file}")
    
    print("""
  NEXT STEPS:
  1. Open the markdown file and review each email
  2. Score each criterion from 1-5
  3. Run: python execution/phase2_email_quality_review.py --record-scores
  4. Or manually create email_review_scores.json with your scores
    """)


def record_scores():
    """Interactive score recording."""
    print("\n" + "="*60)
    print("  Record Email Quality Scores")
    print("="*60)
    
    if not REVIEW_FILE.exists():
        print("\n  No review file found. Run --export first.")
        return
    
    with open(REVIEW_FILE) as f:
        review = json.load(f)
    
    emails = review.get("emails", [])
    scores = []
    
    print(f"\n  {len(emails)} emails to score. Enter scores 1-5 for each criterion.")
    print("  Press Ctrl+C to stop early.\n")
    
    try:
        for i, email in enumerate(emails, 1):
            print(f"\n  === Email {i}/{len(emails)} ===")
            print(f"  To: {email.get('to')}")
            print(f"  Subject: {email.get('subject', 'No subject')[:60]}")
            print(f"  Company: {email.get('recipient_company')}")
            print(f"  Preview: {email.get('body', '')[:100]}...")
            
            email_scores = {"email_id": email.get("email_id")}
            
            for criterion in QUALITY_CRITERIA:
                while True:
                    try:
                        score = int(input(f"    {criterion['name']} (1-5): "))
                        if 1 <= score <= 5:
                            email_scores[criterion['name']] = score
                            break
                        else:
                            print("      Please enter 1-5")
                    except ValueError:
                        print("      Please enter a number 1-5")
            
            notes = input("    Notes (optional): ").strip()
            email_scores["notes"] = notes
            
            scores.append(email_scores)
            
    except KeyboardInterrupt:
        print("\n\n  Stopped early.")
    
    if not scores:
        print("  No scores recorded.")
        return
    
    # Calculate average
    all_scores = []
    for s in scores:
        for criterion in QUALITY_CRITERIA:
            if criterion['name'] in s:
                all_scores.append(s[criterion['name']])
    
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
    
    result = {
        "reviewer": "Dani Apgar",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "emails_reviewed": len(scores),
        "average_score": round(avg_score, 2),
        "pass_threshold": 3.5,
        "passed": avg_score >= 3.5,
        "scores": scores
    }
    
    with open(SCORES_FILE, "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"\n  Scores saved to: {SCORES_FILE}")
    print(f"  Average score: {avg_score:.2f}/5")
    print(f"  Status: {'PASS' if avg_score >= 3.5 else 'NEEDS IMPROVEMENT'}")


def show_status():
    """Show quality review status."""
    print("\n" + "="*60)
    print("  Email Quality Review Status")
    print("="*60)
    
    if SCORES_FILE.exists():
        with open(SCORES_FILE) as f:
            data = json.load(f)
        
        print(f"\n  Reviewer: {data.get('reviewer', 'Unknown')}")
        print(f"  Reviewed: {data.get('reviewed_at', 'Unknown')}")
        print(f"  Emails Reviewed: {data.get('emails_reviewed', 0)}")
        print(f"  Average Score: {data.get('average_score', 0)}/5")
        print(f"  Pass Threshold: {data.get('pass_threshold', 3.5)}/5")
        
        if data.get('passed'):
            print("\n  [PASS] Email quality meets Phase 2 target!")
        else:
            print("\n  [NEEDS IMPROVEMENT] Email quality below target")
            
            # Show lowest-scoring criteria
            if data.get('scores'):
                criteria_totals = {c['name']: [] for c in QUALITY_CRITERIA}
                for score in data['scores']:
                    for c in QUALITY_CRITERIA:
                        if c['name'] in score:
                            criteria_totals[c['name']].append(score[c['name']])
                
                print("\n  Criterion Averages:")
                for name, scores in criteria_totals.items():
                    if scores:
                        avg = sum(scores) / len(scores)
                        status = "[OK]" if avg >= 3.5 else "[LOW]"
                        print(f"    {name}: {avg:.1f}/5 {status}")
    else:
        print("\n  No review scores found.")
        
        if REVIEW_FILE.exists():
            print("  Review file exists - scores pending from Dani.")
            print("\n  Options:")
            print("  1. Dani reviews emails_for_review.md and scores manually")
            print("  2. Run: python execution/phase2_email_quality_review.py --record-scores")
        else:
            print("  Run --export first to generate review file.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Phase 2 Email Quality Review")
    parser.add_argument("--export", action="store_true", help="Export emails for review")
    parser.add_argument("--record-scores", action="store_true", help="Record review scores interactively")
    parser.add_argument("--status", action="store_true", help="Show review status")
    parser.add_argument("--limit", type=int, default=20, help="Number of emails to export")
    args = parser.parse_args()
    
    if args.export:
        export_emails_for_review(limit=args.limit)
    elif args.record_scores:
        record_scores()
    elif args.status:
        show_status()
    else:
        show_status()
        print("\n  Use --export, --record-scores, or --status")


if __name__ == "__main__":
    main()
