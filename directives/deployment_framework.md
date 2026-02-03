# 🚀 Production Deployment Framework

> Autonomous deployment and operation framework for Alpha Swarm daily revenue operations

---

## Overview

This framework defines how to deploy Alpha Swarm for production use without over-engineering. It balances automation with reliability.

---

## 1. Deployment Architecture

### Simplified Production Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PRODUCTION ENVIRONMENT                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐      │
│  │   SCHEDULER      │    │   ALPHA SWARM    │    │   MONITORING     │      │
│  │   (Windows Task  │───▶│   (Python +      │───▶│   (Logs +        │      │
│  │   Scheduler)     │    │   Claude-Flow)   │    │   Alerts)        │      │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘      │
│           │                       │                       │                 │
│           ▼                       ▼                       ▼                 │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │                    EXTERNAL SERVICES                              │      │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐    │      │
│  │  │LinkedIn│  │  Clay  │  │  GHL   │  │Instantly│  │  RB2B  │    │      │
│  │  └────────┘  └────────┘  └────────┘  └────────┘  └────────┘    │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why This is NOT Over-Engineered

| We USE | We AVOID |
|--------|----------|
| Windows Task Scheduler | Kubernetes |
| File-based state | Redis/databases |
| Python scripts | Microservices |
| JSON logs | ELK Stack |
| Email/Slack alerts | PagerDuty |
| Local file storage | Cloud object storage |

**Philosophy**: Start simple, add complexity only when proven necessary.

---

## 2. Scheduler Configuration

### Windows Task Scheduler Setup

Create scheduled tasks for each workflow phase:

```powershell
# Create daily scraping task (5:00 AM PST / 9:00 PM PHT)
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument '-ExecutionPolicy Bypass -File "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm\scripts\daily_scrape.ps1"'
$trigger = New-ScheduledTaskTrigger -Daily -At 9:00PM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName "AlphaSwarm-DailyScrape" -Action $action -Trigger $trigger -Settings $settings

# Create enrichment task (7:00 AM PST / 11:00 PM PHT)
$action2 = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument '-ExecutionPolicy Bypass -File "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm\scripts\daily_enrich.ps1"'
$trigger2 = New-ScheduledTaskTrigger -Daily -At 11:00PM
Register-ScheduledTask -TaskName "AlphaSwarm-DailyEnrich" -Action $action2 -Trigger $trigger2 -Settings $settings

# Create campaign generation task (8:00 AM PST / 12:00 AM PHT next day)
$action3 = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument '-ExecutionPolicy Bypass -File "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm\scripts\daily_campaign.ps1"'
$trigger3 = New-ScheduledTaskTrigger -Daily -At 12:00AM
Register-ScheduledTask -TaskName "AlphaSwarm-DailyCampaign" -Action $action3 -Trigger $trigger3 -Settings $settings

# Create self-annealing task (4:00 PM PST / 8:00 AM PHT)
$action4 = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument '-ExecutionPolicy Bypass -File "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm\scripts\daily_anneal.ps1"'
$trigger4 = New-ScheduledTaskTrigger -Daily -At 8:00AM
Register-ScheduledTask -TaskName "AlphaSwarm-DailyAnneal" -Action $action4 -Trigger $trigger4 -Settings $settings
```

---

## 3. Daily Workflow Scripts

### 3.1 Daily Scrape Script

```powershell
# scripts/daily_scrape.ps1
$ErrorActionPreference = "Stop"
$ProjectRoot = "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
$LogFile = "$ProjectRoot\.tmp\logs\scrape_$(Get-Date -Format 'yyyy-MM-dd').log"

# Activate virtual environment
& "$ProjectRoot\.venv\Scripts\Activate.ps1"

try {
    Write-Output "$(Get-Date) - Starting daily scrape" | Tee-Object -Append $LogFile
    
    # Scrape competitor followers (rotate through list)
    $dayOfWeek = (Get-Date).DayOfWeek.value__
    $competitors = @("gong", "clari", "chorus", "hubspot", "salesloft")
    $todayTarget = $competitors[$dayOfWeek % $competitors.Count]
    
    python "$ProjectRoot\execution\hunter_scrape_followers.py" `
        --company $todayTarget `
        --limit 100 `
        2>&1 | Tee-Object -Append $LogFile
    
    # Check for events (Wednesdays only)
    if ($dayOfWeek -eq 3) {
        python "$ProjectRoot\execution\hunter_scrape_events.py" `
            --category "AI RevOps" `
            --limit 50 `
            2>&1 | Tee-Object -Append $LogFile
    }
    
    Write-Output "$(Get-Date) - Daily scrape complete" | Tee-Object -Append $LogFile
    
} catch {
    Write-Output "$(Get-Date) - ERROR: $_" | Tee-Object -Append $LogFile
    # Send alert
    python "$ProjectRoot\execution\send_alert.py" --level error --message "Daily scrape failed: $_"
    exit 1
}
```

### 3.2 Daily Enrichment Script

```powershell
# scripts/daily_enrich.ps1
$ErrorActionPreference = "Stop"
$ProjectRoot = "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
$LogFile = "$ProjectRoot\.tmp\logs\enrich_$(Get-Date -Format 'yyyy-MM-dd').log"

& "$ProjectRoot\.venv\Scripts\Activate.ps1"

try {
    Write-Output "$(Get-Date) - Starting enrichment" | Tee-Object -Append $LogFile
    
    # Get unenriched leads from today's scrape
    $scrapedFile = "$ProjectRoot\.hive-mind\scraped\latest.json"
    
    if (Test-Path $scrapedFile) {
        python "$ProjectRoot\execution\enricher_clay_waterfall.py" `
            --input $scrapedFile `
            --output "$ProjectRoot\.hive-mind\enriched\$(Get-Date -Format 'yyyy-MM-dd').json" `
            2>&1 | Tee-Object -Append $LogFile
        
        # Segment and score
        python "$ProjectRoot\execution\segmentor_classify.py" `
            --input "$ProjectRoot\.hive-mind\enriched\$(Get-Date -Format 'yyyy-MM-dd').json" `
            2>&1 | Tee-Object -Append $LogFile
    } else {
        Write-Output "$(Get-Date) - No scraped data to enrich" | Tee-Object -Append $LogFile
    }
    
    Write-Output "$(Get-Date) - Enrichment complete" | Tee-Object -Append $LogFile
    
} catch {
    Write-Output "$(Get-Date) - ERROR: $_" | Tee-Object -Append $LogFile
    python "$ProjectRoot\execution\send_alert.py" --level error --message "Enrichment failed: $_"
    exit 1
}
```

### 3.3 Daily Campaign Script

```powershell
# scripts/daily_campaign.ps1
$ErrorActionPreference = "Stop"
$ProjectRoot = "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
$LogFile = "$ProjectRoot\.tmp\logs\campaign_$(Get-Date -Format 'yyyy-MM-dd').log"

& "$ProjectRoot\.venv\Scripts\Activate.ps1"

try {
    Write-Output "$(Get-Date) - Generating campaigns" | Tee-Object -Append $LogFile
    
    # Generate campaigns for segmented leads
    python "$ProjectRoot\execution\crafter_campaign.py" `
        --segment tier1_competitors `
        --max-leads 25 `
        2>&1 | Tee-Object -Append $LogFile
    
    python "$ProjectRoot\execution\crafter_campaign.py" `
        --segment tier2_events `
        --max-leads 50 `
        2>&1 | Tee-Object -Append $LogFile
    
    # Queue for AE review
    python "$ProjectRoot\execution\gatekeeper_queue.py" `
        --action queue-pending `
        2>&1 | Tee-Object -Append $LogFile
    
    # Notify AE team
    python "$ProjectRoot\execution\send_alert.py" `
        --level info `
        --channel slack `
        --message "New campaigns ready for review in GATEKEEPER dashboard"
    
    Write-Output "$(Get-Date) - Campaigns queued for review" | Tee-Object -Append $LogFile
    
} catch {
    Write-Output "$(Get-Date) - ERROR: $_" | Tee-Object -Append $LogFile
    python "$ProjectRoot\execution\send_alert.py" --level error --message "Campaign generation failed: $_"
    exit 1
}
```

### 3.4 Daily Self-Annealing Script

```powershell
# scripts/daily_anneal.ps1
$ErrorActionPreference = "Stop"
$ProjectRoot = "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
$LogFile = "$ProjectRoot\.tmp\logs\anneal_$(Get-Date -Format 'yyyy-MM-dd').log"

& "$ProjectRoot\.venv\Scripts\Activate.ps1"

try {
    Write-Output "$(Get-Date) - Running self-annealing" | Tee-Object -Append $LogFile
    
    # Pull metrics from Instantly
    python "$ProjectRoot\execution\instantly_sync_metrics.py" `
        2>&1 | Tee-Object -Append $LogFile
    
    # Run SPARC self-annealing
    python "$ProjectRoot\execution\sparc_coordinator.py" `
        --self-anneal `
        2>&1 | Tee-Object -Append $LogFile
    
    # Check for drift
    python "$ProjectRoot\execution\drift_detector.py" `
        --check-all `
        2>&1 | Tee-Object -Append $LogFile
    
    # Generate daily summary
    python "$ProjectRoot\execution\generate_daily_report.py" `
        --output "$ProjectRoot\.tmp\reports\daily_$(Get-Date -Format 'yyyy-MM-dd').md" `
        2>&1 | Tee-Object -Append $LogFile
    
    Write-Output "$(Get-Date) - Self-annealing complete" | Tee-Object -Append $LogFile
    
} catch {
    Write-Output "$(Get-Date) - ERROR: $_" | Tee-Object -Append $LogFile
    python "$ProjectRoot\execution\send_alert.py" --level warning --message "Self-annealing issues: $_"
    # Don't exit 1 - self-annealing failures are non-critical
}
```

---

## 4. Monitoring & Alerting

### Simple Alert System

```python
# execution/send_alert.py
"""
Simple alerting to Slack and email.
No external dependencies beyond requests.
"""

import os
import json
import argparse
import requests
from datetime import datetime

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")
ALERT_EMAIL = os.getenv("ALERT_EMAIL")

def send_slack_alert(level: str, message: str):
    """Send alert to Slack channel."""
    if not SLACK_WEBHOOK:
        print("No Slack webhook configured")
        return
    
    emoji = {"info": "ℹ️", "warning": "⚠️", "error": "🚨"}.get(level, "📢")
    
    payload = {
        "text": f"{emoji} *Alpha Swarm Alert*\n{message}",
        "attachments": [{
            "color": {"info": "good", "warning": "warning", "error": "danger"}.get(level, "info"),
            "fields": [
                {"title": "Level", "value": level.upper(), "short": True},
                {"title": "Time", "value": datetime.now().isoformat(), "short": True}
            ]
        }]
    }
    
    try:
        response = requests.post(SLACK_WEBHOOK, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Slack alert: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", choices=["info", "warning", "error"], default="info")
    parser.add_argument("--message", required=True)
    parser.add_argument("--channel", choices=["slack", "email", "all"], default="slack")
    args = parser.parse_args()
    
    if args.channel in ["slack", "all"]:
        send_slack_alert(args.level, args.message)
    
    # Log to file regardless
    log_path = os.path.join(os.path.dirname(__file__), "..", ".tmp", "logs", "alerts.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"{datetime.now().isoformat()} | {args.level.upper()} | {args.message}\n")

if __name__ == "__main__":
    main()
```

### Health Check Dashboard

Create a simple status page:

```python
# execution/health_check.py
"""
Quick health check for all system components.
Run manually or via scheduled task for monitoring.
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
HIVE_MIND = PROJECT_ROOT / ".hive-mind"

def check_system_health():
    """Check all system components and return status."""
    
    health = {
        "timestamp": datetime.now().isoformat(),
        "overall": "healthy",
        "components": {}
    }
    
    # Check recent scraping
    scraped_dir = HIVE_MIND / "scraped"
    if scraped_dir.exists():
        latest_scrape = max(scraped_dir.glob("*.json"), key=os.path.getmtime, default=None)
        if latest_scrape:
            age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(latest_scrape))
            health["components"]["scraping"] = {
                "status": "healthy" if age < timedelta(hours=24) else "stale",
                "last_run": datetime.fromtimestamp(os.path.getmtime(latest_scrape)).isoformat(),
                "age_hours": age.total_seconds() / 3600
            }
    
    # Check enrichment
    enriched_dir = HIVE_MIND / "enriched"
    if enriched_dir.exists():
        latest_enrich = max(enriched_dir.glob("*.json"), key=os.path.getmtime, default=None)
        if latest_enrich:
            age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(latest_enrich))
            health["components"]["enrichment"] = {
                "status": "healthy" if age < timedelta(hours=24) else "stale",
                "last_run": datetime.fromtimestamp(os.path.getmtime(latest_enrich)).isoformat()
            }
    
    # Check learnings are accumulating
    learnings_file = HIVE_MIND / "learnings.json"
    if learnings_file.exists():
        with open(learnings_file) as f:
            learnings = json.load(f)
        health["components"]["learnings"] = {
            "status": "healthy",
            "count": len(learnings.get("learnings", [])),
            "last_updated": learnings.get("updated_at", "never")
        }
    
    # Check Q-table has data
    q_table_file = HIVE_MIND / "q_table.json"
    if q_table_file.exists():
        with open(q_table_file) as f:
            q_table = json.load(f)
        health["components"]["rl_engine"] = {
            "status": "healthy" if len(q_table) > 0 else "untrained",
            "states_learned": len(q_table),
        }
    
    # Determine overall health
    component_statuses = [c.get("status") for c in health["components"].values()]
    if "error" in component_statuses:
        health["overall"] = "error"
    elif "stale" in component_statuses or "untrained" in component_statuses:
        health["overall"] = "degraded"
    
    return health

if __name__ == "__main__":
    health = check_system_health()
    print(json.dumps(health, indent=2))
```

---

## 5. Backup & Recovery

### Daily Backup Script

```powershell
# scripts/daily_backup.ps1
$ProjectRoot = "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
$BackupRoot = "D:\Backups\alpha-swarm"
$Date = Get-Date -Format "yyyy-MM-dd"

# Create backup directory
New-Item -ItemType Directory -Force -Path "$BackupRoot\$Date"

# Backup critical state files
Copy-Item "$ProjectRoot\.hive-mind\learnings.json" "$BackupRoot\$Date\" -Force
Copy-Item "$ProjectRoot\.hive-mind\q_table.json" "$BackupRoot\$Date\" -Force
Copy-Item "$ProjectRoot\.hive-mind\reasoning_bank.json" "$BackupRoot\$Date\" -Force
Copy-Item "$ProjectRoot\.hive-mind\sparc_config.json" "$BackupRoot\$Date\" -Force

# Backup enriched data (compressed)
Compress-Archive -Path "$ProjectRoot\.hive-mind\enriched\*" -DestinationPath "$BackupRoot\$Date\enriched.zip" -Force

# Rotate old backups (keep 30 days)
Get-ChildItem $BackupRoot -Directory | Where-Object { $_.CreationTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Recurse -Force

Write-Output "Backup complete: $BackupRoot\$Date"
```

---

## 6. Auto-Claude Integration Point

### When to Use Auto-Claude

```yaml
use_auto_claude_for:
  - Creating new execution scripts
  - Modifying templates/SOPs
  - Building new MCP server tools
  - Fixing bugs in existing scripts
  - Adding new features to agents
  
use_claude_flow_for:
  - Runtime agent orchestration
  - Production workflow execution
  - MCP tool routing
  - State management
  
manual_tasks:
  - Initial API credential setup
  - AE dashboard review
  - Weekly strategy reviews
  - ICP criteria updates
```

### Auto-Claude Workflow for New Features

```bash
# In Auto-Claude app:
# 1. Create spec for new feature
cd apps/backend
python spec_runner.py --interactive

# 2. Run autonomous build
python run.py --spec 001

# 3. Review and merge to Alpha Swarm
python run.py --spec 001 --review
python run.py --spec 001 --merge

# 4. Test in Alpha Swarm
cd D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm
python -m pytest tests/
```

---

## 7. Go-Live Checklist

### Pre-Production Validation

```yaml
validation_gates:
  - name: API Connections
    test: python execution/test_connections.py
    criteria: All APIs return 200
    
  - name: Scraping Safety
    test: Manual scrape of 10 profiles
    criteria: No LinkedIn blocks
    
  - name: Enrichment Pipeline
    test: Enrich 5 test leads
    criteria: >80% success rate
    
  - name: ICP Scoring
    test: Score 20 known leads
    criteria: >85% match with AE assessment
    
  - name: Campaign Generation
    test: Generate 3 sample campaigns
    criteria: AE approves all 3
    
  - name: GATEKEEPER Dashboard
    test: AE logs in and reviews
    criteria: Can approve/reject
    
  - name: Scheduler
    test: Run all 4 daily scripts manually
    criteria: All complete without error
    
  - name: Alerts
    test: Trigger test alert
    criteria: Received in Slack
```

### Production Launch Sequence

```
Week 1: Pilot Mode
├── Day 1-2: Shadow mode (run but don't send)
├── Day 3-4: 10% of normal volume
├── Day 5: 25% of normal volume
└── Review at end of week

Week 2: Ramp Up
├── Day 1-3: 50% of normal volume
├── Day 4-5: 75% of normal volume
└── Review at end of week

Week 3+: Full Production
├── 100% automated operation
├── Daily AE reviews
├── Weekly optimization
└── Monthly strategy review
```

---

*Framework Version: 1.0*
*Created: 2026-01-14*
*Owner: Alpha Swarm Operations*
