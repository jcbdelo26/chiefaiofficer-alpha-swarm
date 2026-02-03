# GoHighLevel Webhook Integration - Hot Lead Detection

## Overview

This guide connects your GHL account to the Beta Swarm's **Hot Lead Detector**, which automatically alerts your AE/Head of Sales when warm or hot leads engage.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  GoHighLevel    │────▶│  Webhook Server  │────▶│ Hot Lead        │
│  (Conversations)│     │  /webhooks/ghl   │     │ Detector        │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                        ┌─────────────────────────────────┼─────────────────┐
                        ▼                                 ▼                 ▼
                   ┌─────────┐                     ┌───────────┐     ┌───────────┐
                   │  Slack  │                     │    SMS    │     │   Email   │
                   │  #sales │                     │  (Twilio) │     │  Fallback │
                   └─────────┘                     └───────────┘     └───────────┘
```

## Step 1: Start the Webhook Server

```bash
cd chiefaiofficer-alpha-swarm

# Option A: Direct run
python webhooks/webhook_server.py --port 5000

# Option B: With ngrok for local testing
ngrok http 5000
# Note the https URL (e.g., https://abc123.ngrok.io)
```

## Step 2: Configure GHL Webhooks

1. Log into GoHighLevel: https://app.gohighlevel.com
2. Navigate to **Settings → Integrations → Webhooks**
3. Click **Add Webhook**
4. Configure:

| Field | Value |
|-------|-------|
| **Webhook URL** | `https://your-domain.com/webhooks/ghl` |
| **Events** | See table below |

### Required GHL Webhook Events

| Event | Purpose |
|-------|---------|
| `InboundMessage` | SMS/chat messages from leads |
| `email.replied` | Email replies |
| `ContactReply` | Any reply to outreach |
| `AppointmentBooked` | Meeting scheduled |
| `OpportunityStageUpdate` | Pipeline changes |

## Step 3: Configure Environment Variables

Add to your `.env` file:

```bash
# Webhook Server
WEBHOOK_PORT=5000
GHL_WEBHOOK_SECRET=your_ghl_webhook_secret  # Optional but recommended

# Notifications (required for alerts)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/xxx/xxx

# SMS Alerts (for hot leads)
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_FROM_NUMBER=+1234567890
ESCALATION_PHONE_L2=+1234567890  # AE phone
ESCALATION_PHONE_L3=+1234567890  # Head of Sales phone

# Email Fallback
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
ESCALATION_EMAIL_L2=ae@company.com
ESCALATION_EMAIL_L3=hos@company.com
```

## Step 4: Test the Integration

```bash
# Simulate a hot lead reply
curl -X POST http://localhost:5000/webhooks/ghl \
  -H "Content-Type: application/json" \
  -d '{
    "type": "email.replied",
    "contactId": "test_123",
    "contact": {
      "id": "test_123",
      "email": "prospect@acme.com",
      "firstName": "John",
      "lastName": "Doe",
      "companyName": "Acme Corp"
    },
    "body": "This looks great! How do we get started? We need this ASAP."
  }'
```

Expected response:
```json
{
  "status": "received",
  "event_id": "evt_abc123",
  "event_type": "email.replied",
  "hot_lead_detected": true,
  "alert_id": "hot_12345678"
}
```

## Step 5: View Hot Lead Alerts

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /alerts/hot-leads` | List recent hot lead alerts |
| `GET /alerts/hot-leads/stats` | Detection statistics |
| `GET /queue/pending` | Pending webhook events |

### Example: Get Recent Alerts

```bash
curl http://localhost:5000/alerts/hot-leads?limit=10
```

## Hot Lead Detection Criteria

### Temperature Classification

| Temperature | Score | Triggers | SLA |
|-------------|-------|----------|-----|
| 🔥 **HOT** | ≥0.8 | Very positive + High intent + Urgency | 5 min |
| 🟡 **WARM** | ≥0.5 | Positive + Medium intent OR Meeting request | 30 min |
| 🔵 **COOL** | ≥0.2 | Some interest, nurture | 4 hrs |
| ⚪ **COLD** | <0.2 | No interest | N/A |

### Scoring Factors

| Factor | Points |
|--------|--------|
| Very positive sentiment | +0.4 |
| Positive sentiment | +0.2 |
| HIGH_INTENT buying signal | +0.4 |
| MEDIUM_INTENT buying signal | +0.2 |
| Urgency detected (ASAP, now, urgent) | +0.2 |

### Keywords That Trigger Alerts

**High Intent:**
- "how do we start", "next steps", "pricing", "demo", "pilot"

**Meeting Request:**
- "schedule", "calendar", "call", "15 minutes", "availability"

**Urgency:**
- "asap", "urgent", "immediately", "today", "this week"

## Notification Escalation

| Level | Channel | When |
|-------|---------|------|
| 1 | Slack `#approvals` | All warm/hot leads |
| 2 | Slack + SMS | Hot leads |
| 3 | Slack + SMS + Email | Hot leads (fallback) |

## Running as a Service (Production)

### Option A: Systemd (Linux)

```bash
sudo nano /etc/systemd/system/webhook-server.service
```

```ini
[Unit]
Description=Alpha Swarm Webhook Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/chiefaiofficer-alpha-swarm
ExecStart=/usr/bin/python3 webhooks/webhook_server.py
Restart=always
Environment=WEBHOOK_PORT=5000

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable webhook-server
sudo systemctl start webhook-server
```

### Option B: Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "webhooks/webhook_server.py"]
```

## Troubleshooting

### No alerts being sent?

1. Check `SLACK_WEBHOOK_URL` is configured
2. Verify GHL is sending webhooks: `GET /queue/pending`
3. Check logs: `tail -f logs/webhook_server.log`

### Webhook signature errors?

1. Verify `GHL_WEBHOOK_SECRET` matches GHL settings
2. Or temporarily disable verification for testing

### Hot leads not detected?

1. Check the message body is being extracted correctly
2. Verify sentiment analysis: test with known positive phrases
3. Review detection stats: `GET /alerts/hot-leads/stats`
