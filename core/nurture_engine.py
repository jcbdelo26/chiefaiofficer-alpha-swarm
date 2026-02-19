"""
Nurture Sequence Engine for the Chief AI Officer Alpha Swarm

This engine generates appropriate follow-up emails based on lead segment:
- Re-engagement: For stale contacts (90+ days inactive)
- Win-back: For ghosted deals (Lost/Stalled)
- Follow-up: For non-responders (7+ days no reply)
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import pytz
from dotenv import load_dotenv
from core.email_signature import enforce_text_signature

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

EST_TIMEZONE = pytz.timezone('US/Eastern')
NURTURE_QUEUE_DIR = PROJECT_ROOT / ".hive-mind" / "nurture_queue"
SHADOW_EMAIL_DIR = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [NURTURE] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==============================================================================
# EMAIL TEMPLATES
# ==============================================================================

TEMPLATES = {
    "reengagement": {
        "subject": "{{first_name}}, it's been a while — quick update from ChiefAIOfficer",
        "body": """Hi {{first_name}},

I noticed it's been a few months since we last connected. A lot has changed in the AI RevOps space, and I wanted to share some quick wins we've seen with companies similar to {{company}}.

Would you be open to a 15-minute call to explore if any of these could move the needle for your team?

Best,
Chris

P.S. If timing isn't right, just reply "later" and I'll check back in a few months.

Reply STOP to unsubscribe."""
    },
    
    "winback": {
        "subject": "{{first_name}}, one more idea for {{company}}",
        "body": """Hi {{first_name}},

I know our last conversation didn't result in moving forward, and that's totally okay. Sometimes timing just isn't right.

I've been thinking about {{company}} and had one more idea that might be relevant now that Q1 is in full swing.

Worth a quick 10-minute chat?

No pressure either way.

Best,
Chris

Reply STOP to unsubscribe."""
    },
    
    "followup": {
        "subject": "Re: {{original_subject}}",
        "body": """Hi {{first_name}},

Just bubbling this up in case it got buried. Happy to jump on a quick call if helpful.

Let me know!

Chris

Reply STOP to unsubscribe."""
    }
}

def render_template(template_key: str, lead_data: Dict) -> Dict:
    """
    Render an email template with lead data.
    
    Returns: {"subject": str, "body": str}
    """
    template = TEMPLATES.get(template_key)
    if not template:
        logger.error(f"Unknown template: {template_key}")
        return None
    
    # Extract variables
    first_name = (lead_data.get("name", "") or "there").split()[0]
    company = lead_data.get("company") or "your company"
    original_subject = lead_data.get("original_subject", "my previous email")
    
    # Render
    subject = template["subject"].replace("{{first_name}}", first_name)
    subject = subject.replace("{{company}}", company)
    subject = subject.replace("{{original_subject}}", original_subject)
    
    body = template["body"].replace("{{first_name}}", first_name)
    body = body.replace("{{company}}", company)
    body = body.replace("{{original_subject}}", original_subject)
    body = enforce_text_signature(body)
    
    return {"subject": subject, "body": body}

def create_nurture_email(lead: Dict) -> Optional[Dict]:
    """
    Generate a nurture email for the given lead and save to shadow queue.
    
    Returns the created email data or None on failure.
    """
    segment = lead.get("segment") or lead.get("sequence_type")
    
    if not segment:
        logger.warning(f"No segment for lead {lead.get('id')}")
        return None
    
    # Map segment to template
    template_map = {
        "stale": "reengagement",
        "reengagement": "reengagement",
        "ghosted": "winback",
        "winback": "winback",
        "non_responder": "followup",
        "followup": "followup"
    }
    
    template_key = template_map.get(segment)
    if not template_key:
        logger.warning(f"Unknown segment: {segment}")
        return None
    
    # Render template
    rendered = render_template(template_key, lead)
    if not rendered:
        return None
    
    # Create email record
    email_id = f"nurture_{lead.get('id', 'unknown')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    email_data = {
        "email_id": email_id,
        "to": lead.get("email"),
        "subject": rendered["subject"],
        "body": rendered["body"],
        "tier": "tier_3",  # Nurture emails default to Tier 3 priority
        "angle": f"nurture_{template_key}",
        "segment": segment,
        "recipient_data": {
            "name": lead.get("name"),
            "company": lead.get("company"),
            "email": lead.get("email")
        },
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "source": "nurture_engine",
        "original_lead_id": lead.get("id")
    }
    
    # Save to shadow mode queue
    SHADOW_EMAIL_DIR.mkdir(parents=True, exist_ok=True)
    filepath = SHADOW_EMAIL_DIR / f"{email_id}.json"
    
    with open(filepath, 'w') as f:
        json.dump(email_data, f, indent=2)
    
    logger.info(f"Created nurture email: {email_id} ({template_key})")
    return email_data

def process_nurture_queue():
    """
    Process all pending items in the nurture queue.
    
    Reads from .hive-mind/nurture_queue/ and generates emails.
    """
    if not NURTURE_QUEUE_DIR.exists():
        logger.info("No nurture queue found.")
        return []
    
    processed = []
    
    for f in NURTURE_QUEUE_DIR.glob("*.json"):
        try:
            with open(f, 'r') as fp:
                lead = json.load(fp)
            
            if lead.get("status") == "processed":
                continue
            
            # Generate email
            email = create_nurture_email(lead)
            
            if email:
                # Mark as processed
                lead["status"] = "processed"
                lead["processed_at"] = datetime.now().isoformat()
                lead["generated_email_id"] = email["email_id"]
                
                with open(f, 'w') as fp:
                    json.dump(lead, fp, indent=2)
                
                processed.append(email)
            
        except Exception as e:
            logger.error(f"Error processing {f}: {e}")
            continue
    
    logger.info(f"Processed {len(processed)} nurture leads")
    return processed

def main():
    """Entry point for nurture engine."""
    logger.info("🌱 Nurture Engine Started")
    
    processed = process_nurture_queue()
    
    logger.info(f"✅ Generated {len(processed)} nurture emails")
    return processed

if __name__ == "__main__":
    main()
