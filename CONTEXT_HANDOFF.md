# Context Handoff: ChiefAIOfficer-Alpha-Swarm Production Launch

**Created:** 2026-01-26
**Purpose:** Continue production setup with a local AI agent (Claude, GPT, Gemini)
**Return to Ampcode for:** Major refactoring, complex debugging, multi-file architecture changes

---

## 📋 COPY THIS ENTIRE SECTION TO YOUR AI AGENT

```markdown
# CONTEXT: ChiefAIOfficer-Alpha-Swarm Production Launch

## Current State
You are helping with a B2B AI sales swarm that sends personalized outreach emails via GoHighLevel (GHL). The system is currently in **Shadow Mode** (live API connections, but emails are logged not sent).

### System Location
- **Project Path:** D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm
- **Config:** config/production.json
- **Environment:** .env (contains API keys)

### What's Already Working
- GHL API connected and verified (fetched 20+ real contacts)
- 6 active agents: UNIFIED_QUEEN, HUNTER, ENRICHER, SEGMENTOR, CRAFTER, OPERATOR
- LLM fallback chain: Claude → GPT-4o → GPT-4o-mini
- Guardrails: Rate limiting, circuit breakers, permission matrix
- Audit trail: SQLite with PII redaction
- Shadow mode: Emails logged to .hive-mind/shadow_mode_emails/
- Global kill switch: EMERGENCY_STOP env var
- Canary test system: scripts/canary_test.py
- Unsubscribe compliance test: scripts/test_unsubscribe.py

### Current Phase
- Day 33 of production rollout
- Rollout phase: "shadow" (no sends)
- shadow_mode: true
- actually_send: false
- block_production_writes: true

### API Credentials Status
| Credential | Status |
|------------|--------|
| GHL_PROD_API_KEY | ✅ SET |
| GHL_LOCATION_ID | ✅ SET |
| SUPABASE_URL/KEY | ✅ SET |
| CLAY_API_KEY | ✅ SET |
| SLACK_WEBHOOK_URL | ✅ SET |
| ANTHROPIC_API_KEY | ✅ SET |
| OPENAI_API_KEY | ✅ SET |
| RB2B_API_KEY | ❌ NOT SET (optional) |

---

## YOUR TASKS

### Task 1: Add Emergency Controls to .env

Open the `.env` file and add these lines at the bottom:

```bash
# =============================================================================
# EMERGENCY CONTROLS (Production Safety)
# =============================================================================
EMERGENCY_STOP=false
CANARY_MODE=false
INTERNAL_TEST_EMAILS=chris@chiefaiofficer.com
```

Replace `chris@chiefaiofficer.com` with the actual internal email for testing.

### Task 2: Create Email Templates

Create email templates in `templates/email_templates/` with this structure:

**File: templates/email_templates/tier1_first_touch.md**
```markdown
# Tier 1 First Touch Template

**Use For:** High-value prospects (VP+, 51-500 employees, B2B SaaS)
**Subject Line Options:**
1. {{first_name}}, AI is transforming RevOps at companies like {{company}}
2. Quick question about {{company}}'s revenue operations

**Body:**
Hi {{first_name}},

[YOUR APPROVED COPY HERE]

Best,
Chris Daigle
Chief AI Officer
https://caio.cx/ai-exec-briefing-call

Reply STOP to unsubscribe.
ChiefAIOfficer.com | [PHYSICAL ADDRESS]
```

Create similar files for:
- tier2_first_touch.md
- tier3_first_touch.md
- follow_up_1.md
- follow_up_2.md

### Task 3: Create Exclusion Lists

**File: .hive-mind/exclusions/competitors.json**
```json
{
  "competitors": [
    "competitor1.com",
    "competitor2.com"
  ],
  "notes": "Companies to NEVER contact - direct competitors"
}
```

**File: .hive-mind/exclusions/customers.json**
```json
{
  "current_customers": [
    "customer1@company.com",
    "customer2@company.com"
  ],
  "customer_domains": [
    "bigcustomer.com",
    "anothercustomer.com"
  ],
  "notes": "Existing customers - do not send cold outreach"
}
```

### Task 4: Create Approver Configuration

**File: config/approvers.json**
```json
{
  "approvers": [
    {
      "id": "primary_ae",
      "name": "YOUR NAME",
      "email": "your@email.com",
      "slack_handle": "@yourslack",
      "phone": "+1-555-123-4567",
      "timezone": "America/New_York",
      "coverage_hours": "9:00-18:00",
      "can_approve": ["tier1_emails", "tier2_emails", "bulk_campaigns"],
      "is_primary": true
    }
  ],
  "escalation_chain": [
    {"level": 1, "approver_id": "primary_ae", "sla_minutes": 30},
    {"level": 2, "approver_id": "primary_ae", "sla_minutes": 60, "method": "sms"},
    {"level": 3, "approver_id": "primary_ae", "sla_minutes": 120, "method": "phone"}
  ],
  "hot_lead_sla_minutes": 5
}
```

### Task 5: Confirm Sending Policy

Review and confirm these limits in `config/production.json`:

```json
"email_limits": {
    "monthly_limit": 3000,
    "daily_limit": 150,
    "hourly_limit": 20,
    "per_domain_hourly_limit": 5,
    "min_delay_seconds": 30
}
```

If you need to change them, edit the file directly.

### Task 6: Check Domain Health

Run this command to see current email status:
```powershell
cd D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm
python -c "from core.ghl_guardrails import get_email_guard; g = get_email_guard(); print(g.get_status())"
```

The domain health score should be >70. If it's lower, enable warmup mode:
```powershell
python -c "from core.ghl_guardrails import get_email_guard; g = get_email_guard(); g.enable_warmup_mode(14)"
```

---

## VERIFICATION COMMANDS

After completing the tasks, run these to verify:

### 1. Verify Configuration
```powershell
cd D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm
python scripts/deploy_shadow_mode.py --verify
```

### 2. Run Canary Test
```powershell
chcp 65001 && python scripts/canary_test.py --full
```

### 3. Run Unsubscribe Test
```powershell
chcp 65001 && python scripts/test_unsubscribe.py --full
```

### 4. Check Pending Approvals
```powershell
python execution/process_approved_actions.py --list
```

---

## NEXT PHASE: Moving to Parallel Mode

Once all human inputs are complete and tests pass:

### Step 1: Update config/production.json
Change:
```json
"rollout_phase": {
    "current": "parallel"
}
```

### Step 2: Run AI vs Human Comparison
```powershell
python execution/priority_3_ai_vs_human_comparison.py --generate-queue 50
```

### Step 3: AE Reviews Leads Blindly
The AE should review the generated leads without seeing AI scores.

### Step 4: Analyze Agreement
```powershell
python execution/priority_3_ai_vs_human_comparison.py --analyze
```

Target: >75% agreement between AI and human.

---

## KEY FILE LOCATIONS

| Purpose | Path |
|---------|------|
| Main config | config/production.json |
| Shadow logs | .hive-mind/shadow_mode_logs/ |
| Shadow emails | .hive-mind/shadow_mode_emails/ |
| Audit database | .hive-mind/audit.db |
| Approval queue | .hive-mind/approvals/ |
| Execution queue | .hive-mind/execution_queue/ |
| Hot lead alerts | .hive-mind/hot_lead_alerts/ |
| Canary test results | .hive-mind/canary_tests/ |
| Unsubscribe tests | .hive-mind/unsubscribe_tests/ |
| Suppression list | .hive-mind/suppression_list.json |
| Circuit breakers | .hive-mind/circuit_breakers.json |
| Email limits | .hive-mind/email_limits.json |

---

## WHEN TO RETURN TO AMPCODE

Come back to Ampcode for:
1. Complex multi-file refactoring
2. Debugging production issues across multiple components
3. Adding new agent capabilities
4. Architecture changes
5. Security audits
6. Performance optimization
7. Integration of new APIs (like RB2B)

For simple tasks (creating files, editing configs, running commands), use your local AI agent.

---

## EMERGENCY PROCEDURES

### Stop All Outbound Immediately
Set in `.env`:
```
EMERGENCY_STOP=true
```

### Enter Maintenance Mode
```powershell
python -c "from core.system_orchestrator import SystemOrchestrator; s=SystemOrchestrator(); s.enter_maintenance()"
```

### Check System Health
```powershell
python execution/health_check.py
```

---

## PRODUCTION LAUNCH SEQUENCE (Days 1-5)

### Day 1 (Today): Human Inputs ← YOU ARE HERE
- [ ] Add EMERGENCY_STOP to .env
- [ ] Create email templates
- [ ] Create exclusion lists
- [ ] Create approver config
- [ ] Confirm sending limits

### Day 2: Verification
- [ ] Run canary test
- [ ] Run unsubscribe test
- [ ] Verify all APIs connected
- [ ] Test Slack alerts

### Day 3: Parallel Mode
- [ ] Switch to parallel mode
- [ ] Generate 50 lead queue
- [ ] AE blind review
- [ ] Analyze agreement (>75%)

### Day 4: Assisted Mode (First Live Sends)
- [ ] Switch to assisted mode
- [ ] Set daily_limit to 10
- [ ] Send to internal addresses first
- [ ] Send to 3-5 real leads
- [ ] Verify delivery

### Day 5: Gradual Ramp
- [ ] Increase to 25/day
- [ ] Monitor deliverability
- [ ] Watch for complaints
- [ ] Review hot lead alerts
```

---

## 📋 END OF HANDOFF CONTEXT

Copy everything between the triple backticks above and paste into your AI agent (Claude, GPT, Gemini, etc.) to continue the setup process.

When you've completed all human inputs and the tests pass, return to Ampcode for the Day 3+ phases if you encounter any issues.
