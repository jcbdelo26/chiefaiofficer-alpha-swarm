# Deployment Checklist

## Overview

This checklist covers the complete deployment process for the Unified Swarm system. Follow all steps in order for staging deployments, and ensure all items are checked for production deployments.

---

## Pre-Deployment

### Environment Preparation

- [ ] All feature branches merged to main
- [ ] Version number updated in configuration
- [ ] Changelog updated with release notes

### Testing

- [ ] All unit tests passing (`python -m pytest tests/ -v`)
- [ ] Integration tests passing
- [ ] End-to-end tests passing
- [ ] No critical or high-severity issues in test results

### Compliance & Security

- [ ] Compliance report generated and reviewed
- [ ] Security scan completed (no critical vulnerabilities)
- [ ] All secrets stored in environment variables (not in code)
- [ ] API keys validated and not expired

### Configuration

- [ ] Environment variables configured for target environment:
  - [ ] `OPENAI_API_KEY`
  - [ ] `ANTHROPIC_API_KEY`
  - [ ] `SLACK_WEBHOOK_URL`
  - [ ] `DEPLOY_TARGET_HOST`
  - [ ] `GOOGLE_CLIENT_ID` (if using Google integrations)
  - [ ] `GOOGLE_CLIENT_SECRET` (if using Google integrations)
  - [ ] `GOHIGHLEVEL_API_KEY` (if using GoHighLevel)
- [ ] Rate limits configured appropriately
- [ ] Circuit breakers configured with proper thresholds
- [ ] Timeout values set appropriately

### Backup

- [ ] Database backup taken
- [ ] Current deployment state backed up
- [ ] Backup verified and restorable

---

## Deployment

### Pre-Flight

- [ ] Deployment script reviewed: `scripts/deploy_unified_swarm.ps1`
- [ ] Dry run completed successfully:
  ```powershell
  .\scripts\deploy_unified_swarm.ps1 -Environment staging -DryRun
  ```
- [ ] Team notified of upcoming deployment

### Blue-Green Deployment

- [ ] Blue deployment started
- [ ] Container/service started successfully
- [ ] Logs show no startup errors
- [ ] Memory and CPU usage within expected ranges

### Health Checks

- [ ] Health endpoint responding (HTTP 200)
- [ ] All dependent services reachable
- [ ] Database connections established
- [ ] Cache connections established (if applicable)
- [ ] External API connections verified

### Smoke Tests

- [ ] Core API endpoints responding correctly
- [ ] Authentication working
- [ ] Basic workflow execution successful
- [ ] Agent communication verified

### Traffic Switch

- [ ] Traffic gradually shifted to blue deployment
- [ ] No error spike during traffic switch
- [ ] Latency within acceptable range
- [ ] Green deployment stopped (kept in standby)

---

## Post-Deployment

### Monitoring Activation

- [ ] Monitoring dashboards showing data
- [ ] Metrics collection verified
- [ ] Custom metrics appearing correctly

### Alerts Configuration

- [ ] Error rate alerts configured
- [ ] Latency alerts configured
- [ ] Resource utilization alerts configured
- [ ] Alert channels verified (Slack, email, etc.)

### Verification

- [ ] Audit trail logging verified
- [ ] All scheduled tasks running
- [ ] Background workers operational
- [ ] Performance baseline established

### Documentation

- [ ] Deployment documented in team channel
- [ ] Known issues documented
- [ ] Runbook updated if needed

---

## Rollback Procedure

### Trigger Conditions

Initiate rollback if any of the following occur:

- [ ] Error rate exceeds 5% for more than 5 minutes
- [ ] P95 latency exceeds 2x baseline for more than 5 minutes
- [ ] Critical functionality not working
- [ ] Data integrity issues detected
- [ ] Security vulnerability discovered post-deploy

### Rollback Steps

1. **Alert Team**
   - [ ] Notify team in Slack/Teams channel
   - [ ] Document reason for rollback

2. **Execute Rollback**
   ```powershell
   .\scripts\rollback.ps1 -Environment production -Force
   ```
   - [ ] Rollback script executed
   - [ ] Previous version restored
   - [ ] Traffic switched to previous version

3. **Verify Rollback**
   - [ ] Health checks passing on rolled-back version
   - [ ] Error rates normalized
   - [ ] Latency normalized

### Post-Rollback Actions

- [ ] Root cause analysis initiated
- [ ] Incident report created
- [ ] Fix developed and tested
- [ ] New deployment scheduled after fix

---

## Quick Reference Commands

### Staging Deployment
```powershell
# Dry run first
.\scripts\deploy_unified_swarm.ps1 -Environment staging -DryRun

# Actual deployment
.\scripts\deploy_unified_swarm.ps1 -Environment staging
```

### Production Deployment
```powershell
# Dry run first
.\scripts\deploy_unified_swarm.ps1 -Environment production -DryRun

# Actual deployment (requires confirmation)
.\scripts\deploy_unified_swarm.ps1 -Environment production
```

### Skip Tests (use with caution)
```powershell
.\scripts\deploy_unified_swarm.ps1 -Environment staging -SkipTests
```

### Deploy Specific Version
```powershell
.\scripts\deploy_unified_swarm.ps1 -Environment staging -Version "1.2.3"
```

### Rollback
```powershell
# Interactive (with confirmation)
.\scripts\rollback.ps1 -Environment production

# Force rollback (no confirmation)
.\scripts\rollback.ps1 -Environment production -Force
```

---

## Contact Information

| Role | Contact |
|------|---------|
| Deployment Lead | @deployment-lead |
| On-Call Engineer | @oncall |
| Platform Team | #platform-team |

---

## Revision History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-01-22 | 1.0 | Initial checklist | System |
