# Alpha Swarm Operations Runbook

> Operational guide for daily management, troubleshooting, and maintenance

---

## Table of Contents

1. [System Start/Stop](#system-startstop)
2. [Daily Operations Checklist](#daily-operations-checklist)
3. [API Key Rotation](#api-key-rotation)
4. [Safe Mode](#safe-mode)
5. [Log Locations](#log-locations)
6. [Troubleshooting Guide](#troubleshooting-guide)
7. [Common Issues and Solutions](#common-issues-and-solutions)
8. [Emergency Procedures](#emergency-procedures)

---

## System Start/Stop

### Starting the System

#### Full System Start

```powershell
# Navigate to project directory
cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Verify environment
python execution\health_check.py

# Start all scheduled tasks (if not using Task Scheduler)
.\scripts\start_system.ps1
```

#### Start Individual Components

```powershell
# Start scraping workflow
.\scripts\daily_scrape.ps1

# Start enrichment workflow
.\scripts\daily_enrich.ps1

# Start campaign generation
.\scripts\daily_campaign.ps1

# Start self-annealing
.\scripts\daily_anneal.ps1
```

#### Using Windows Task Scheduler

The system is designed to run via Windows Task Scheduler. Tasks should be configured as:

| Task Name | Script | Schedule | Account |
|-----------|--------|----------|---------|
| AlphaSwarm-Scrape | `scripts\daily_scrape.ps1` | 9:00 PM daily | System |
| AlphaSwarm-Enrich | `scripts\daily_enrich.ps1` | 11:00 PM daily | System |
| AlphaSwarm-Campaign | `scripts\daily_campaign.ps1` | 12:00 AM daily | System |
| AlphaSwarm-Anneal | `scripts\daily_anneal.ps1` | 8:00 AM daily | System |
| AlphaSwarm-HealthCheck | `execution\health_check.py` | Every 4 hours | System |

### Stopping the System

#### Graceful Stop (Recommended)

```powershell
# Stop scheduled tasks via Task Scheduler
schtasks /End /TN "AlphaSwarm-Scrape"
schtasks /End /TN "AlphaSwarm-Enrich"
schtasks /End /TN "AlphaSwarm-Campaign"
schtasks /End /TN "AlphaSwarm-Anneal"
```

#### Emergency Stop

```powershell
# Kill all Python processes (use with caution)
Get-Process python | Stop-Process -Force

# Or use safe mode instead
$env:SAFE_MODE = "true"
```

#### Disable Scheduled Tasks

```powershell
# Disable all Alpha Swarm tasks
schtasks /Change /TN "AlphaSwarm-Scrape" /Disable
schtasks /Change /TN "AlphaSwarm-Enrich" /Disable
schtasks /Change /TN "AlphaSwarm-Campaign" /Disable
schtasks /Change /TN "AlphaSwarm-Anneal" /Disable
```

#### Re-enable Scheduled Tasks

```powershell
schtasks /Change /TN "AlphaSwarm-Scrape" /Enable
schtasks /Change /TN "AlphaSwarm-Enrich" /Enable
schtasks /Change /TN "AlphaSwarm-Campaign" /Enable
schtasks /Change /TN "AlphaSwarm-Anneal" /Enable
```

---

## Daily Operations Checklist

### Morning (8:00 AM)

- [ ] **Check Slack/Email for overnight alerts**
  - Look for: API failures, rate limits, critical errors
  
- [ ] **Run health check**
  ```powershell
  python execution\health_check.py
  ```
  - Verify: All services green
  - Action: Address any red/yellow items

- [ ] **Review GATEKEEPER dashboard**
  - Location: GHL → Workflows → AE Review Queue
  - Action: Approve/reject pending campaigns
  - Target: Clear queue before 10:00 AM

- [ ] **Check overnight scraping results**
  ```powershell
  # View scraping summary
  Get-Content ".hive-mind\state\daily_metrics.json" | ConvertFrom-Json
  ```
  - Expected: 100+ leads scraped
  - Alert if: <50 leads

### Midday (12:00 PM)

- [ ] **Verify enrichment completion**
  - Check Clay dashboard for pending rows
  - Expected: <10 rows in "pending" status
  
- [ ] **Monitor campaign sends**
  - Check Instantly dashboard
  - Verify: Campaigns sending as scheduled
  - Watch: Bounce rates, spam reports

### Afternoon (4:00 PM)

- [ ] **Review reply escalations**
  - Check Slack #alpha-swarm-replies channel
  - Action: Route positive replies to AE
  - Action: Handle negative replies per objection matrix

- [ ] **Spot-check lead quality**
  - Review 5-10 random enriched leads
  - Verify: ICP scores match manual assessment
  - Flag: Any obvious misclassifications

### End of Day (6:00 PM)

- [ ] **Generate daily report**
  ```powershell
  python execution\generate_daily_report.py --print
  ```
  
- [ ] **Review metrics vs targets**
  | Metric | Target | Action if Below |
  |--------|--------|-----------------|
  | Leads scraped | 100+ | Check scraping logs |
  | Enrichment rate | 85%+ | Check Clay status |
  | ICP match | 60%+ | Review ICP criteria |
  | AE approval | 70%+ | Review campaign templates |

- [ ] **Log any manual interventions**
  - Document in: `.hive-mind/operational_log.md`

### Weekly (Friday)

- [ ] **Team review of weekly metrics**
  ```powershell
  python execution\generate_daily_report.py --weekly --print
  ```

- [ ] **ICP validation (AE spot-check)**
  - Sample: 50 random leads from the week
  - Record: Accuracy rate
  - Update: ICP weights if needed

- [ ] **Template performance review**
  - Compare: A/B variant open/reply rates
  - Action: Sunset underperformers
  - Action: Scale winners

- [ ] **Review self-annealing logs**
  ```powershell
  Get-Content ".hive-mind\annealing\weekly_summary.json" | ConvertFrom-Json
  ```

- [ ] **Backup state files**
  ```powershell
  .\scripts\backup_state.ps1
  ```

---

## API Key Rotation

### When to Rotate

- **Scheduled**: Every 90 days
- **Immediate**: If key is compromised or exposed
- **After incidents**: If API shows unauthorized access

### Rotation Procedure

#### 1. GoHighLevel API Key

```powershell
# Step 1: Generate new key in GHL
# Settings → Integrations → API Keys → Create New

# Step 2: Update .env file
$envContent = Get-Content ".env"
$envContent = $envContent -replace "GHL_API_KEY=.*", "GHL_API_KEY=new_key_here"
$envContent | Set-Content ".env"

# Step 3: Test new key
python -c "from execution.ghl_client import test_connection; test_connection()"

# Step 4: Revoke old key in GHL dashboard
```

#### 2. Instantly API Key

```powershell
# Step 1: Generate new key in Instantly
# Settings → Integrations → API → Generate New Key

# Step 2: Update .env
$envContent = Get-Content ".env"
$envContent = $envContent -replace "INSTANTLY_API_KEY=.*", "INSTANTLY_API_KEY=new_key_here"
$envContent | Set-Content ".env"

# Step 3: Test
python -c "from execution.instantly_client import test_connection; test_connection()"

# Step 4: Delete old key in Instantly
```

#### 3. Clay API Key

```powershell
# Step 1: Generate in Clay → Settings → API

# Step 2: Update .env
$envContent = Get-Content ".env"
$envContent = $envContent -replace "CLAY_API_KEY=.*", "CLAY_API_KEY=new_key_here"
$envContent | Set-Content ".env"

# Step 3: Test
python -c "from execution.clay_client import test_connection; test_connection()"
```

#### 4. Slack Webhook

```powershell
# Step 1: Create new webhook at api.slack.com/apps

# Step 2: Update .env
$envContent = Get-Content ".env"
$envContent = $envContent -replace "SLACK_WEBHOOK_URL=.*", "SLACK_WEBHOOK_URL=new_url_here"
$envContent | Set-Content ".env"

# Step 3: Test
python execution\send_alert.py --test
```

### Post-Rotation Verification

```powershell
# Run full health check after rotation
python execution\health_check.py --full

# Verify each service
python execution\test_connections.py --all
```

---

## Safe Mode

### What is Safe Mode?

Safe Mode prevents any external API calls or data modifications. Use when:
- Debugging issues
- During maintenance windows
- After detecting anomalies
- Before major configuration changes

### Enabling Safe Mode

```powershell
# Method 1: Environment variable (current session)
$env:SAFE_MODE = "true"

# Method 2: .env file (persistent)
Add-Content ".env" "SAFE_MODE=true"

# Method 3: Using script
.\scripts\enable_safe_mode.ps1
```

### Safe Mode Behavior

| Component | Normal Mode | Safe Mode |
|-----------|-------------|-----------|
| Scraping | Active | Disabled |
| Enrichment | Active | Disabled |
| Campaign sends | Active | Disabled |
| GHL writes | Active | Disabled |
| Health checks | Active | **Active** |
| Log collection | Active | **Active** |
| Alerts | Active | **Active** |

### Disabling Safe Mode

```powershell
# Method 1: Environment variable
$env:SAFE_MODE = "false"
Remove-Item Env:SAFE_MODE

# Method 2: .env file
$content = Get-Content ".env" | Where-Object { $_ -notmatch "SAFE_MODE" }
$content | Set-Content ".env"

# Method 3: Using script
.\scripts\disable_safe_mode.ps1
```

### Verification

```powershell
# Check current safe mode status
python -c "from config import is_safe_mode; print(f'Safe Mode: {is_safe_mode()}')"
```

---

## Log Locations

### Log Directory Structure

```
chiefaiofficer-alpha-swarm/
├── logs/                           # Main log directory
│   ├── scraper/                    # Hunter agent logs
│   │   ├── 2026-01-15.log
│   │   └── errors.log
│   ├── enricher/                   # Enricher agent logs
│   │   ├── 2026-01-15.log
│   │   └── clay_responses.log
│   ├── campaign/                   # Crafter agent logs
│   │   ├── 2026-01-15.log
│   │   └── instantly_sync.log
│   ├── gatekeeper/                 # AE review logs
│   │   └── approvals.log
│   ├── orchestrator/               # Alpha Queen logs
│   │   ├── 2026-01-15.log
│   │   └── workflow_state.log
│   └── system/                     # System-level logs
│       ├── health_check.log
│       ├── alerts.log
│       └── errors.log
│
├── .hive-mind/                     # State and memory
│   ├── state/
│   │   ├── daily_metrics.json
│   │   ├── weekly_metrics.json
│   │   └── pipeline_state.json
│   ├── annealing/
│   │   ├── weekly_summary.json
│   │   └── learnings.json
│   └── operational_log.md
```

### Viewing Logs

```powershell
# View today's scraper log
Get-Content "logs\scraper\$(Get-Date -Format 'yyyy-MM-dd').log" -Tail 50

# View all errors from today
Get-Content "logs\system\errors.log" | Where-Object { $_ -match (Get-Date -Format 'yyyy-MM-dd') }

# Search logs for specific term
Select-String -Path "logs\*\*.log" -Pattern "ERROR"

# View enrichment failures
Select-String -Path "logs\enricher\*.log" -Pattern "failed|error" -CaseSensitive:$false
```

### Log Retention

| Log Type | Retention | Rotation |
|----------|-----------|----------|
| Daily logs | 30 days | Daily |
| Error logs | 90 days | Size (10MB) |
| State files | 365 days | Manual |
| Annealing | 365 days | Weekly |

### Log Cleanup

```powershell
# Manual cleanup of old logs
.\scripts\cleanup_logs.ps1 -DaysToKeep 30

# Check log disk usage
Get-ChildItem -Path "logs" -Recurse | Measure-Object -Property Length -Sum
```

---

## Troubleshooting Guide

### Diagnostic Commands

```powershell
# Full system health check
python execution\health_check.py --verbose

# Test all API connections
python execution\test_connections.py --all

# Check environment variables
python -c "from dotenv import dotenv_values; print(dotenv_values('.env'))"

# View current pipeline state
Get-Content ".hive-mind\state\pipeline_state.json" | ConvertFrom-Json

# Check if processes are running
Get-Process python -ErrorAction SilentlyContinue

# View scheduled task status
Get-ScheduledTask | Where-Object { $_.TaskName -like "AlphaSwarm*" }
```

### Diagnostic Flowchart

```
Problem Detected
       │
       ▼
   ┌───────────────────────────────────────┐
   │ Run: python execution\health_check.py │
   └───────────────────────────────────────┘
       │
       ▼
   All Green? ──Yes──► Check logs for warnings
       │
       No
       │
       ▼
   ┌─────────────────────────────────────┐
   │ Identify failing component          │
   │ - API Connection?                   │
   │ - Authentication?                   │
   │ - Rate Limit?                       │
   │ - Data Quality?                     │
   └─────────────────────────────────────┘
       │
       ▼
   See "Common Issues" section below
```

---

## Common Issues and Solutions

### 1. LinkedIn Scraping Blocked

**Symptoms:**
- Zero leads scraped
- Log shows: "Access denied", "Rate limited", "Session expired"

**Solutions:**

```powershell
# Step 1: Check session status
python execution\check_linkedin_session.py

# Step 2: Rotate session
python execution\rotate_linkedin_session.py

# Step 3: Reduce rate
# Edit config/sdr_rules.yaml
# linkedin_tos:
#   rate_limits:
#     profiles_per_hour: 50  # Reduce from 100

# Step 4: Wait 24 hours if hard-blocked
$env:SAFE_MODE = "true"
```

**Prevention:**
- Never exceed 500 profiles/day
- Use proxy rotation
- Maintain natural access patterns

---

### 2. Clay Enrichment Failing

**Symptoms:**
- Leads stuck in "pending" status
- Log shows: "Provider error", "Quota exceeded"

**Solutions:**

```powershell
# Step 1: Check Clay dashboard for provider status

# Step 2: Check quota
python -c "from execution.clay_client import get_quota; print(get_quota())"

# Step 3: If quota exceeded, wait for reset or upgrade plan

# Step 4: Retry failed rows
python execution\retry_failed_enrichments.py
```

**Prevention:**
- Monitor quota daily
- Set alerts at 80% usage
- Have fallback providers configured

---

### 3. GHL API Rate Limited

**Symptoms:**
- Contact creation failing
- Log shows: "429 Too Many Requests"

**Solutions:**

```powershell
# Step 1: Verify rate limit hit
Select-String -Path "logs\*\*.log" -Pattern "429"

# Step 2: Implement backoff (automatic in client)
# Check: execution\ghl_client.py has exponential backoff

# Step 3: Reduce batch size
# Edit config: GHL_BATCH_SIZE=25 (from 50)

# Step 4: Queue and retry
python execution\retry_ghl_queue.py
```

**Prevention:**
- Use batching (50 records max)
- Implement request queuing
- Monitor API usage in GHL dashboard

---

### 4. Instantly Campaign Not Sending

**Symptoms:**
- Leads added but no emails sent
- Campaign shows "Paused" or "Error"

**Solutions:**

```powershell
# Step 1: Check campaign status in Instantly dashboard

# Step 2: Verify mailbox health
# Instantly → Mailboxes → Check warmup status

# Step 3: Check for bounce threshold
# If >5% bounces, campaign auto-pauses

# Step 4: Restart campaign
python execution\restart_instantly_campaign.py --campaign-id=xxx
```

**Prevention:**
- Verify emails before adding to campaign
- Use gradual warmup for new mailboxes
- Monitor deliverability daily

---

### 5. ICP Scoring Wrong

**Symptoms:**
- Low-quality leads marked Tier 1
- High-quality leads marked Tier 3
- AE rejection rate >30%

**Solutions:**

```powershell
# Step 1: Sample recent leads
python execution\audit_icp_scoring.py --sample=50

# Step 2: Review scoring weights
Get-Content ".hive-mind\annealing\icp_weights.json"

# Step 3: Adjust weights in Clay formula
# See: docs/integrations/CLAY.md

# Step 4: Reprocess with new weights
python execution\reprocess_icp_scores.py
```

**Prevention:**
- Weekly AE validation of 50 leads
- Incorporate rejection feedback
- Self-annealing adjustments

---

### 6. Alerts Not Sending

**Symptoms:**
- No Slack notifications
- Errors not reported

**Solutions:**

```powershell
# Step 1: Test alert manually
python execution\send_alert.py --test

# Step 2: Verify webhook URL
$env:SLACK_WEBHOOK_URL

# Step 3: Check Slack app permissions

# Step 4: Regenerate webhook if needed
# See: API Key Rotation → Slack Webhook
```

---

### 7. Disk Space Low

**Symptoms:**
- Scripts failing with "No space left"
- Log files not rotating

**Solutions:**

```powershell
# Step 1: Check disk usage
Get-PSDrive -PSProvider FileSystem

# Step 2: Clean old logs
.\scripts\cleanup_logs.ps1 -DaysToKeep 14

# Step 3: Archive old state files
.\scripts\archive_state.ps1

# Step 4: Clear temp files
Remove-Item ".tmp\*" -Recurse -Force
```

---

### 8. Memory/CPU High

**Symptoms:**
- System slow/unresponsive
- Processes hanging

**Solutions:**

```powershell
# Step 1: Check resource usage
Get-Process python | Select-Object CPU, WorkingSet64

# Step 2: Kill stuck processes
Get-Process python | Where-Object { $_.CPU -gt 100 } | Stop-Process

# Step 3: Reduce batch sizes in config

# Step 4: Enable safe mode temporarily
$env:SAFE_MODE = "true"
```

---

## Emergency Procedures

### Complete System Halt

Use when: Critical security issue, major malfunction, or compliance emergency.

```powershell
# 1. Stop all processes immediately
Get-Process python | Stop-Process -Force

# 2. Disable scheduled tasks
Get-ScheduledTask | Where-Object { $_.TaskName -like "AlphaSwarm*" } | Disable-ScheduledTask

# 3. Enable safe mode
Add-Content ".env" "SAFE_MODE=true"

# 4. Send emergency alert
python execution\send_alert.py --level=critical --message="SYSTEM HALTED: [reason]"

# 5. Notify team via Slack/phone
```

### Data Breach Response

Use when: Unauthorized access detected or data exposure suspected.

```powershell
# 1. Halt system (see above)

# 2. Rotate ALL API keys immediately
# See: API Key Rotation section

# 3. Audit access logs
Select-String -Path "logs\*\*.log" -Pattern "unauthorized|access|breach"

# 4. Document timeline
# Record: What happened, when, what data affected

# 5. Follow company incident response procedure
```

### GDPR Data Request Emergency

Use when: Subject access request (SAR) or deletion request received.

```powershell
# For access request (30-day deadline)
python execution\gdpr_access_request.py --email="subject@example.com"

# For deletion request (24-hour target)
python execution\gdpr_deletion_request.py --email="subject@example.com"

# Log the request
python execution\log_gdpr_request.py --type="deletion" --email="subject@example.com"
```

### Recovery from Backup

Use when: Data corruption or accidental deletion.

```powershell
# 1. Stop system
$env:SAFE_MODE = "true"

# 2. List available backups
Get-ChildItem "backups\" -Directory

# 3. Restore state files
Copy-Item "backups\2026-01-14\.hive-mind\*" ".hive-mind\" -Recurse -Force

# 4. Verify integrity
python execution\verify_state.py

# 5. Restart with caution
$env:SAFE_MODE = "false"
python execution\health_check.py
```

---

## Support Contacts

| Issue Type | Contact | Response Time |
|------------|---------|---------------|
| System emergency | @devops-oncall | 15 min |
| API issues | Vendor support | Varies |
| AE escalation | @sales-team | 1 hour |
| Security | @security-team | Immediate |

---

*Runbook Version: 1.0*
*Last Updated: 2026-01-15*
*Owner: Alpha Swarm Operations Team*
*Review Frequency: Monthly*
