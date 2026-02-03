# Calendar Coordination Directive

## Purpose
Ensure all calendar operations maintain data integrity, respect business rules, and provide seamless scheduling experiences for prospects and AEs.

---

## Core Principles

### 1. Never Double-Book
- **ALWAYS** check availability before proposing times
- Use mutex lock when creating events
- Verify slot is still available immediately before booking

### 2. Respect Working Hours
- Default: 9 AM - 6 PM in recipient's timezone
- No meetings before 8 AM or after 7 PM
- Account for timezone differences

### 3. Buffer Requirements
- Minimum 15 minutes between meetings
- 30-minute buffer for important prospects (Tier 1)
- No back-to-back-to-back meetings

---

## Scheduling Flow

```
1. DETECT scheduling intent in email
   └→ Email Threading MCP: detect_intent()

2. CHECK AE calendar availability
   └→ Google Calendar MCP: get_availability()

3. PROPOSE 3 time options
   └→ Follow Time Proposal Format below

4. WAIT for prospect response
   └→ Monitor for confirmation/reschedule

5. CREATE calendar event
   └→ Google Calendar MCP: create_event()
   └→ Include Zoom link, meeting brief link

6. SEND confirmation
   └→ GHL: send_email() with calendar details
```

---

## Time Proposal Format

When proposing times, always offer **3 options**:

```
I have a few times that work well:

Option 1: Tuesday, January 28th at 10:00 AM EST
Option 2: Wednesday, January 29th at 2:00 PM EST  
Option 3: Thursday, January 30th at 11:00 AM EST

Which works best for you? Or if none of these work, 
feel free to share a few times that do.
```

### Rules:
- Spread options across different days
- Vary morning/afternoon
- Always include timezone
- Offer flexibility for alternatives

---

## Timezone Handling

### Detection Priority:
1. Prospect's stated timezone
2. Prospect's company HQ location
3. Prospect's email domain TLD (.co.uk → GMT)
4. Default to ET (Eastern Time)

### Conversion Rules:
- Always store in UTC internally
- Display in prospect's local time in emails
- Include AE's timezone in parentheses

### Example:
```
Tuesday at 2:00 PM your time (11:00 AM PT for our team)
```

---

## Meeting Types

### Discovery Call (30 min)
- First meeting with prospect
- Zoom link required
- Pre-meeting brief generated night before

### Demo (45-60 min)
- Product demonstration
- Screen share required
- Technical requirements sent in advance

### Follow-Up (30 min)
- Post-demo discussion
- Decision-maker may be different
- Prep notes from previous meeting

---

## Rescheduling Protocol

When prospect requests reschedule:

1. **Acknowledge** immediately
2. **Offer** 3 new times within 1 week
3. **Update** calendar and CRM
4. **Notify** AE of change
5. **Regenerate** meeting brief if needed

### Response Template:
```
No problem at all! Here are some alternative times:

[3 new options]

Let me know what works best, and I'll get the invite updated.
```

---

## Cancellation Protocol

When prospect cancels:

1. **Acknowledge** graciously
2. **Offer** to reschedule
3. **Update** CRM with cancellation reason
4. **Queue** follow-up for 1 week later
5. **Do NOT** remove from pipeline immediately

### Response Template:
```
Understood! Thanks for letting me know.

When things settle down, I'd love to reconnect. 
Should I reach out in a week or two to find a better time?
```

---

## Integration Points

| System | Purpose | MCP Tool |
|--------|---------|----------|
| Google Calendar | Availability, events | google-calendar-mcp |
| Email Threading | Intent detection | email-threading-mcp |
| GHL | CRM updates, emails | ghl-mcp |
| Zoom | Meeting links | unified-gateway (zoom) |

---

## Guardrails

### Rate Limits
- Max 100 calendar API calls/hour
- Max 20 event creations/day per AE

### Prohibited Actions
- Booking meetings on weekends (unless prospect requests)
- Scheduling less than 2 hours in advance
- Booking more than 90 days out

### Required Approvals
- Any meeting > 2 hours → AE approval
- Any meeting before 8 AM or after 7 PM → AE approval
- Any weekend meeting → AE approval

---

## Logging Requirements

All calendar operations must log to `.hive-mind/calendar_audit.json`:
- Event ID
- Action (create/update/delete)
- Participants
- Original proposed times
- Final booked time
- Reschedule count
