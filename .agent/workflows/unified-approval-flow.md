---
description: GATEKEEPER routing rules with auto-approve, manual review, and escalation procedures
triggers:
  - type: event
    source: approval_requested
  - type: manual
    command: /approval-flow
agents:
  - GATEKEEPER
  - QUEEN
---

# Unified Approval Flow Workflow

## Overview
This workflow defines the GATEKEEPER agent's decision logic for routing approvals. It determines which actions can be auto-approved, which require manual review, and how to handle timeouts and escalations.

## Prerequisites
- [ ] Slack Bot configured for approval notifications
- [ ] SMS gateway configured (Twilio/similar)
- [ ] Email SMTP configured
- [ ] Approval queue initialized (`.hive-mind/approval_queue.json`)

---

## Approval Categories

### Category 1: ALWAYS_APPROVE (Auto-approved if template match ≥ 90%)
```yaml
actions:
  - external_email_send
  - calendar_invite_create
  - crm_stage_change
  - opportunity_close_lost
  - follow_up_sequence_trigger
  - meeting_reminder_send
  - brief_delivery
```

**Conditions for Auto-Approval:**
- Template match score ≥ 90%
- No manual flag on contact
- No sensitive keywords detected
- Within daily action limits

---

### Category 2: SMART_APPROVAL (Auto-approve under specific conditions)
```yaml
actions:
  - follow_up_email
  - scheduling_response
  - meeting_reschedule
  - reminder_email
  - nurture_sequence_email
```

**Smart Approval Logic:**
```python
def evaluate_smart_approval(action):
    conditions = [
        template_match >= 0.90,           # High template match
        no_custom_content_added,          # No freeform text
        contact_not_flagged,              # Not marked for review
        within_rate_limits,               # Under daily caps
        no_sensitive_keywords,            # No pricing/legal terms
        similar_actions_approved > 3      # Pattern established
    ]
    return all(conditions)
```

---

### Category 3: MANUAL_REVIEW (Always requires human approval)
```yaml
actions:
  - first_outreach_to_new_lead
  - custom_email_content
  - discount_offer
  - contract_discussion
  - competitor_mention
  - escalation_request
```

**Manual Review Triggers:**
- Template match < 90%
- Contact flagged for review
- High-value lead (Tier 1)
- Custom content detected
- Sensitive keywords present

---

### Category 4: NEVER_AUTO_APPROVE (Strict manual gate)
```yaml
actions:
  - pricing_discussion
  - contract_terms
  - legal_commitments
  - bulk_email_send (>10 recipients)
  - data_export
  - account_deletion
  - api_credential_change
```

**Security Notes:**
- These actions are logged with enhanced audit trails
- Require explicit approval with reason
- Two-approver option for high-risk items

---

## Workflow Steps

// turbo-all

### Step 1: GATEKEEPER Receives Approval Request
```bash
python execution/gatekeeper_review.py --request "$REQUEST_ID"
```

**Request Schema:**
```json
{
  "request_id": "APR-12345",
  "timestamp": "2026-01-23T14:30:00Z",
  "requesting_agent": "COMMUNICATOR",
  "action_type": "external_email_send",
  "target": {
    "contact_email": "john@acmecorp.com",
    "contact_name": "John Smith",
    "ghl_contact_id": "GHL-67890"
  },
  "content": {
    "subject": "Following up on our conversation",
    "body": "Hi John, ...",
    "template_id": "follow_up_v2",
    "template_match_score": 0.94
  },
  "context": {
    "previous_emails": 3,
    "last_contact": "2026-01-20",
    "lead_score": 85,
    "sales_stage": "qualified"
  },
  "priority": "normal",
  "timeout_minutes": 30
}
```

**Handoff:** → Step 2 (Category Routing)

---

### Step 2: GATEKEEPER Routes by Category
```bash
python execution/gatekeeper_review.py --categorize "$REQUEST_ID"
```

**Routing Decision Tree:**
```
                    ┌─────────────────┐
                    │ Receive Request │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
            ┌───────┤ Check Category  ├───────┐
            │       └────────┬────────┘       │
            │                │                │
            ▼                ▼                ▼
    ┌───────────┐    ┌───────────┐    ┌───────────┐
    │ALWAYS_APPR│    │SMART_APPR │    │MANUAL/NEVR│
    └─────┬─────┘    └─────┬─────┘    └─────┬─────┘
          │                │                │
          ▼                ▼                ▼
    ┌───────────┐    ┌───────────┐    ┌───────────┐
    │Template ≥ │    │Evaluate   │    │Queue for  │
    │90%?       │    │Conditions │    │Human      │
    └─────┬─────┘    └─────┬─────┘    └───────────┘
          │                │
          ▼                ▼
    ┌───────────┐    ┌───────────┐
    │AUTO-APPRV │    │Pass All?  │
    └───────────┘    └─────┬─────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
        ┌───────────┐            ┌───────────┐
        │AUTO-APPRV │            │QUEUE MANUL│
        └───────────┘            └───────────┘
```

**Handoff:** 
- Auto-approved → Step 6 (Execute)
- Manual review → Step 3 (Notification)

---

### Step 3: GATEKEEPER Sends Manual Review Notification
```bash
python execution/gatekeeper_notify.py --request "$REQUEST_ID" --channel "primary"
```

**Notification Priority Channels:**

#### Primary: Slack DM
```json
{
  "channel": "slack_dm",
  "recipient": "@head_of_sales",
  "timeout_minutes": 30,
  "message_format": "block_kit",
  "interactive": true
}
```

**Slack Block Kit Message:**
```
🚪 GATEKEEPER: Approval Required

📧 **Action:** Send Email
👤 **To:** John Smith (Acme Corp)
📊 **Lead Score:** 85 | **Stage:** Qualified

**Preview:**
> Following up on our conversation about AI automation...

[✅ Approve] [❌ Reject] [✏️ Edit]

⏰ Timeout in: 28 minutes
```

#### Secondary: SMS (Urgent)
```json
{
  "channel": "sms",
  "recipient": "+1234567890",
  "trigger": "timeout_approaching",
  "timeout_minutes": 10
}
```

**SMS Message:**
```
[CAIO] Approval pending for John Smith (Acme). 
Reply Y to approve, N to reject.
Expires in 10 min.
```

#### Tertiary: Email Fallback
```json
{
  "channel": "email",
  "recipient": "sales@company.com",
  "trigger": "all_channels_timeout",
  "timeout_minutes": 120
}
```

**Handoff:** → Step 4 (Wait for Response)

---

### Step 4: GATEKEEPER Waits for Approval Response
```bash
python execution/gatekeeper_wait.py --request "$REQUEST_ID" --timeout "$TIMEOUT"
```

**Response Handling:**
| Response | Action |
|----------|--------|
| ✅ Approve | Execute action immediately |
| ❌ Reject | Log reason, notify agent |
| ✏️ Edit | Open edit interface, re-queue |
| 🕐 Timeout | Escalate to next channel |

**Timeout Escalation Chain:**
1. Slack DM (30 min) → SMS
2. SMS (10 min) → Secondary Approver Slack
3. Secondary Slack (30 min) → Email
4. Email (120 min) → Auto-reject with log

**Handoff:** → Step 5 (Process Response) or Step 4b (Escalate)

---

### Step 4b: GATEKEEPER Escalates on Timeout
```bash
python execution/gatekeeper_escalate.py --request "$REQUEST_ID" --reason "timeout"
```

**Escalation Logic:**
```python
def escalate(request):
    # Try next channel in chain
    channels = ["slack_primary", "sms", "slack_secondary", "email"]
    current = get_current_channel(request)
    next_channel = channels[channels.index(current) + 1]
    
    if next_channel == "email":
        # Final escalation - include all context
        send_detailed_email(request)
    else:
        notify(request, channel=next_channel)
    
    log_escalation(request, reason="timeout", from=current, to=next_channel)
```

**Escalation Limits:**
- Max 4 escalation attempts
- After final timeout → Auto-reject + Alert

**Handoff:** → Step 4 (new channel) or Step 5 (final rejection)

---

### Step 5: GATEKEEPER Processes Approval Response
```bash
python execution/gatekeeper_process.py --request "$REQUEST_ID" --response "$RESPONSE"
```

**Approval Processing:**
```json
{
  "request_id": "APR-12345",
  "response": "approved",
  "approver": "chris@company.com",
  "approval_channel": "slack",
  "approval_timestamp": "2026-01-23T14:45:00Z",
  "notes": "",
  "modifications": null
}
```

**Rejection Processing:**
```json
{
  "request_id": "APR-12345",
  "response": "rejected",
  "approver": "chris@company.com",
  "rejection_reason": "incorrect_personalization",
  "feedback": "Company name is wrong in paragraph 2",
  "action": "return_to_crafter"
}
```

**Self-Annealing on Rejection:**
- Log rejection reason to ReasoningBank
- Update template effectiveness scores
- Train on correction patterns

**Handoff:** → Step 6 (Execute) or → CRAFTER (if edited/rejected)

---

### Step 6: GATEKEEPER Executes Approved Action
```bash
python execution/gatekeeper_execute.py --request "$REQUEST_ID" --approval "$APPROVAL_ID"
```

**Execution Steps:**
1. Validate approval is still valid (not expired)
2. Verify action hasn't already been executed
3. Execute via appropriate agent
4. Log to audit trail
5. Notify requesting agent

**Audit Log Entry:**
```json
{
  "audit_id": "AUD-98765",
  "request_id": "APR-12345",
  "action_type": "external_email_send",
  "target": "john@acmecorp.com",
  "approval_type": "manual",
  "approver": "chris@company.com",
  "execution_timestamp": "2026-01-23T14:46:00Z",
  "result": "success",
  "grounding_evidence": ["template_match_0.94", "manual_approval"]
}
```

**Handoff:** → QUEEN (logging)

---

### Step 7: QUEEN Updates Learning System
```bash
python execution/unified_queen_orchestrator.py --log_approval \
  --request_id "$REQUEST_ID" \
  --outcome "$OUTCOME"
```

**Tracked Metrics:**
| Metric | Description |
|--------|-------------|
| `auto_approval_rate` | % of requests auto-approved |
| `manual_approval_rate` | % of manual requests approved |
| `rejection_rate` | % of requests rejected |
| `avg_approval_time` | Time from request to decision |
| `escalation_rate` | % that required escalation |
| `timeout_rate` | % that hit final timeout |

**Self-Annealing Updates:**
- Increase auto-approval threshold for consistently approved templates
- Flag frequently rejected patterns for template improvement
- Adjust timeout durations based on response patterns

---

## Approval Queue Management

### Queue Location
`.hive-mind/approval_queue.json`

### Queue Schema
```json
{
  "pending": [
    {
      "request_id": "APR-12345",
      "queued_at": "2026-01-23T14:30:00Z",
      "expires_at": "2026-01-23T15:00:00Z",
      "current_channel": "slack_primary",
      "escalation_count": 0,
      "priority": "normal"
    }
  ],
  "approved": [...],
  "rejected": [...],
  "expired": [...]
}
```

### Queue Housekeeping
```bash
# Run daily at midnight
python execution/gatekeeper_housekeeping.py --clean_expired --archive_old
```

- Archive approved/rejected after 7 days
- Permanently delete expired after 30 days
- Generate daily queue report

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Auto-Approval Rate | > 70% |
| Manual Approval Rate | > 90% (of reviewed) |
| Average Approval Time | < 15 minutes |
| Escalation Rate | < 10% |
| Timeout Rate | < 2% |
| False Positive (auto-approve wrong) | < 1% |

---

## Failure Handling

| Scenario | Action |
|----------|--------|
| All channels fail | Queue for next business day |
| Approver on vacation | Route to backup approver |
| High queue volume | Batch similar requests |
| System overload | Pause non-critical, prioritize urgent |
| Conflicting approvals | Latest approval wins, log conflict |

---

## Configuration

### Environment Variables
```env
APPROVAL_TIMEOUT_SLACK=30
APPROVAL_TIMEOUT_SMS=10
APPROVAL_TIMEOUT_EMAIL=120
AUTO_APPROVE_THRESHOLD=0.90
MAX_ESCALATIONS=4
PRIMARY_APPROVER=chris@company.com
SECONDARY_APPROVER=backup@company.com
```

### Approver Settings
```json
{
  "approvers": {
    "primary": {
      "name": "Chris Daigle",
      "email": "chris@company.com",
      "slack": "@chris",
      "phone": "+1234567890",
      "working_hours": "09:00-18:00",
      "timezone": "Asia/Manila"
    },
    "secondary": {
      "name": "Backup Approver",
      "email": "backup@company.com",
      "slack": "@backup",
      "phone": "+0987654321",
      "working_hours": "09:00-18:00",
      "timezone": "Asia/Manila"
    }
  },
  "outside_hours_behavior": "queue_until_morning"
}
```

---

## Sensitive Keyword Detection

### Always Flag for Manual Review
```python
SENSITIVE_KEYWORDS = [
    # Pricing
    "discount", "pricing", "cost", "fee", "investment", "$", 
    
    # Legal/Contract
    "contract", "agreement", "terms", "liability", "indemnify",
    
    # Commitments
    "guarantee", "promise", "commit", "deadline", "penalty",
    
    # Competitor
    "competitor", "alternative", "versus", "vs",
    
    # Urgency/Pressure
    "limited time", "expires", "act now", "last chance"
]
```

### Detection Integration
```bash
python execution/gatekeeper_review.py --detect_sensitive --content "$EMAIL_BODY"
```
