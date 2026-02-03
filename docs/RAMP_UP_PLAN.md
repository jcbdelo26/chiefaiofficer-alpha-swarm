# 🚀 Alpha Swarm Production Ramp-Up Plan

> Collaborative roadmap to full operational status

---

## Overview

This document outlines the phased approach to ramping up the Alpha Swarm into full production. Each phase has specific goals, code tasks, and validation criteria.

**Timeline:** 3 weeks to full production
**Daily Commitment:** 1-2 hours setup + monitoring

---

## Phase 1: Foundation (Days 1-3)

### Goal
Get all APIs connected and data flowing.

### Day 1: API Configuration

**Your Tasks:**
1. Get API keys from each platform:
   - [ ] Instantly.ai → Settings → API Keys
   - [ ] GoHighLevel → Settings → API Tokens
   - [ ] Slack → Create App → Incoming Webhooks
   - [ ] Anthropic → Console → API Keys

2. Update `.env` file with real values

3. Run connection test:
   ```powershell
   python execution\test_connections.py
   ```

**My Tasks:**
- Create any missing connection test scripts
- Fix any API integration issues you encounter

### Day 2: Data Ingestion

**Your Tasks:**
1. Run full ingestion:
   ```powershell
   python execution\run_full_ingestion.py --full
   ```

2. Review what was imported:
   ```powershell
   # Check campaigns
   Get-Content ".hive-mind\knowledge\campaigns\_summary.json"
   
   # Check deals
   Get-Content ".hive-mind\knowledge\deals\_summary.json"
   
   # Check baselines
   Get-Content ".hive-mind\knowledge\campaigns\_baselines.json"
   ```

**My Tasks:**
- Adjust ingestion scripts based on your API responses
- Handle any edge cases in data processing

### Day 3: Voice Training

**Your Tasks:**
1. Export 5-10 of Chris's best email samples
2. Save them to: `.hive-mind\knowledge\voice_samples\chris_emails.json`

**Format:**
```json
{
  "voice_samples": [
    {
      "type": "outbound_email",
      "subject": "Example subject line",
      "body": "Full email body...",
      "outcome": "booked_meeting",
      "notes": "Why this worked"
    }
  ]
}
```

**My Tasks:**
- Create voice analysis script to extract patterns
- Update CRAFTER templates with voice learning

---

## Phase 2: Calibration (Days 4-7)

### Goal
Tune ICP scoring and validate with real humans.

### Day 4: AE Validation Setup

**Your Tasks:**
1. Generate validation template:
   ```powershell
   python execution\icp_calibrate.py --generate-template --num-leads 50
   ```

2. Share `.tmp\ae_validation_template.json` with your AE

3. Brief AE on the task:
   - Review each lead
   - Mark disagreements
   - Provide reasons

### Day 5-6: AE Review Period

**Your Tasks:**
- Check in with AE on progress
- Answer any questions about tier definitions

**Tier Definitions for AE:**
| Tier | Score | Treatment |
|------|-------|-----------|
| Tier 1 VIP | 85-100 | 1:1 personalized, AE direct |
| Tier 2 High | 70-84 | Personalized sequence |
| Tier 3 Standard | 50-69 | Semi-personalized batch |
| Tier 4 Nurture | 30-49 | Nurture drip only |
| DQ | 0-29 | Do not contact |

### Day 7: Apply Calibration

**Your Tasks:**
1. Run calibration with AE feedback:
   ```powershell
   python execution\icp_calibrate.py --calibrate \
       --feedback .tmp\ae_validation_template.json
   ```

2. Review updated weights:
   ```powershell
   python execution\icp_calibrate.py --show-weights
   ```

**My Tasks:**
- Analyze calibration results
- Suggest weight adjustments if needed

---

## Phase 3: Automation (Days 8-10)

### Goal
Set up scheduled automation and dashboard.

### Day 8: Dashboard Launch

**Your Tasks:**
1. Start dashboard:
   ```powershell
   .\scripts\start_dashboard.ps1
   ```

2. Open http://localhost:5000

3. Test the interface:
   - View sample campaign
   - Try approve/reject
   - Check analytics page

**My Tasks:**
- Fix any dashboard issues
- Add features you request

### Day 9: Scheduler Setup

**Your Tasks:**
1. Open PowerShell as Administrator
2. Install scheduled tasks:
   ```powershell
   .\scripts\setup_scheduler.ps1 -Install
   ```
3. Verify:
   ```powershell
   .\scripts\setup_scheduler.ps1 -Status
   ```

### Day 10: Shadow Mode Testing

**Your Tasks:**
1. Enable shadow mode:
   ```powershell
   $env:SHADOW_MODE = "true"
   ```

2. Manually trigger each workflow:
   ```powershell
   .\scripts\daily_scrape.ps1
   .\scripts\daily_enrich.ps1
   .\scripts\daily_campaign.ps1
   ```

3. Review results:
   ```powershell
   python execution\health_check.py
   python execution\generate_daily_report.py --print
   ```

**My Tasks:**
- Troubleshoot any workflow issues
- Optimize based on results

---

## Phase 4: Pilot (Days 11-17)

### Goal
Run at 25% capacity with real sends.

### Day 11: Pilot Launch

**Your Tasks:**
1. Disable shadow mode:
   ```powershell
   $env:SHADOW_MODE = "false"
   ```

2. Configure pilot limits in scripts (I'll help with this)

3. Notify AE team: "Pilot starting - extra review attention needed"

### Daily During Pilot

**Morning Routine (8 AM):**
```powershell
# Check overnight alerts
python execution\send_alert.py --list

# Health check
python execution\health_check.py

# Open dashboard
.\scripts\start_dashboard.ps1
```

**AE Review Session (10 AM):**
- Review all pending campaigns
- Approve or reject with reasons
- Note any patterns

**End of Day (6 PM):**
```powershell
python execution\generate_daily_report.py --print
```

### Day 17: Pilot Review

**Metrics to Evaluate:**
- Campaigns generated: Target 5-10/day
- AE approval rate: Target >70%
- Enrichment success: Target >85%
- Any system errors?

**Decision:**
- ✅ Metrics met → Move to 50%
- ⚠️ Some issues → Fix and extend pilot
- ❌ Major issues → Roll back and debug

---

## Phase 5: Full Production (Days 18+)

### Goal
Scale to 100% capacity.

### Week 3: Ramp Schedule

| Day | Capacity | Daily Leads |
|-----|----------|-------------|
| 18 | 25% | ~25 |
| 19 | 50% | ~50 |
| 20 | 75% | ~75 |
| 21+ | 100% | ~100 |

### Weekly Cadence

**Monday:** Plan week, review metrics
**Tuesday-Thursday:** Normal operations
**Friday:** Self-annealing session

```powershell
# Friday Self-Annealing
python execution\sparc_coordinator.py --self-anneal
python execution\icp_calibrate.py --calibrate
```

---

## Collaborative Workflow

### How We Work Together

**When you encounter issues:**
1. Describe what happened
2. Share relevant log output
3. I'll diagnose and provide fixes

**When you want improvements:**
1. Describe the desired behavior
2. I'll create an Auto-Claude spec
3. You review and approve
4. I implement and test

**Daily Check-ins (Suggested):**
- Share health check output
- Report any errors
- Request improvements

### Communication Template

```
📊 Daily Status:
- Health Check: [healthy/degraded/error]
- Campaigns Generated: [X]
- Pending Review: [X]
- Issues: [none/describe]

🎯 Requests:
- [Any improvements needed]

📣 Questions:
- [Any questions]
```

---

## Success Metrics

### Week 1 Goals
- [ ] All APIs connected
- [ ] Historical data imported
- [ ] AE validation complete
- [ ] ICP calibrated

### Week 2 Goals
- [ ] Dashboard running
- [ ] Scheduler active
- [ ] Shadow mode tested
- [ ] Pilot launched

### Week 3 Goals
- [ ] 100% capacity reached
- [ ] <5 errors/week
- [ ] >70% AE approval rate
- [ ] Self-annealing active

### Long-term Targets
| Metric | Target | Stretch |
|--------|--------|---------|
| Leads/day | 100 | 200 |
| Enrichment rate | 85% | 95% |
| AE approval | 70% | 85% |
| Reply rate | 8% | 12% |
| Meetings/week | 5 | 10 |

---

## Emergency Procedures

### If System Goes Down

```powershell
# Check health
python execution\health_check.py

# Check logs
Get-Content .tmp\logs\*.log -Tail 100

# Restart dashboard
.\scripts\start_dashboard.ps1
```

### If Bad Campaigns Go Out

1. Pause in Instantly immediately
2. Review what went wrong
3. Update directives
4. Add to learnings:
   ```powershell
   # Document the issue
   python execution\send_alert.py --level error --message "Campaign issue: [describe]"
   ```

### Rollback Scheduler

```powershell
.\scripts\setup_scheduler.ps1 -Uninstall
```

---

## Next Immediate Step

**Right now, let's start with Day 1:**

1. Do you have your API keys ready for:
   - Instantly.ai
   - GoHighLevel
   - Slack webhook
   - Anthropic

2. If yes, let's configure and test connections
3. If no, I can show you where to get each one

---

*Created: 2026-01-15*
*Version: 1.0*
