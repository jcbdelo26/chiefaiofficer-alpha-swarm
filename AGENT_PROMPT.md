# Paste This Into Your AI Agent (Claude/GPT/Gemini)

---

## SYSTEM CONTEXT

I'm setting up an AI B2B sales swarm (ChiefAIOfficer-Alpha-Swarm) for production launch. The technical implementation is complete. I need help completing the human configuration steps.

**Project Location:** D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm
**Current State:** Shadow Mode (APIs connected, emails logged not sent)
**My Role:** Non-technical GTM engineer

## COMPLETED (Don't Touch)
- ✅ All API connections verified (GHL, Supabase, Clay, Slack, Anthropic, OpenAI)
- ✅ Config fixed (shadow mode enabled, writes blocked)
- ✅ Kill switch implemented (EMERGENCY_STOP env var)
- ✅ Canary test system ready
- ✅ Unsubscribe compliance tested
- ✅ Approval queue wired

## WHAT I NEED HELP WITH

### 1. Add to my .env file:
```
EMERGENCY_STOP=false
CANARY_MODE=false  
INTERNAL_TEST_EMAILS=my-email@company.com
```

### 2. Create email templates in templates/email_templates/:
- tier1_first_touch.md (for VPs at 51-500 employee B2B SaaS)
- tier2_first_touch.md (for Directors/Managers)
- tier3_first_touch.md (for general prospects)

Each needs: subject line, body with {{first_name}}, {{company}} placeholders, unsubscribe footer, physical address.

### 3. Create exclusion lists:
- .hive-mind/exclusions/competitors.json (competitor domains)
- .hive-mind/exclusions/customers.json (current customer emails/domains)

### 4. Create config/approvers.json with:
- My name, email, Slack handle, phone
- Timezone and coverage hours
- SLA for approvals (30 min standard, 5 min for hot leads)

### 5. Confirm email limits:
- 150/day, 20/hour, 3000/month
- Should I adjust for Week 1?

### 6. Check domain health:
Run: `python -c "from core.ghl_guardrails import get_email_guard; g = get_email_guard(); print(g.get_status())"`
Tell me if score is >70

## VERIFICATION COMMANDS (After Setup)
```powershell
cd D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm
python scripts/deploy_shadow_mode.py --verify
chcp 65001 && python scripts/canary_test.py --full
chcp 65001 && python scripts/test_unsubscribe.py --full
```

## DO NOT MODIFY
- config/production.json (already configured correctly)
- core/*.py files (production-hardened)
- Any test files

Help me complete these configuration steps one at a time.

---

# After Pasting Above, Tell Your Agent:

"Let's start with Task 1. I need to add the emergency controls to my .env file. Guide me through what to add."

Then proceed through Tasks 2-6 sequentially.
