# Incident Response Playbook

**Last Updated**: 2026-03-03
**Scope**: Auth errors, webhook failures, Redis loss, EMERGENCY_STOP, common production issues

---

## 1. EMERGENCY_STOP Activation

### When to Activate
- Bounce rate > 10% across any batch
- Spam complaints received
- Domain blacklisted (check MXToolbox)
- Unsubscribe rate > 5%
- System sending to wrong recipients
- Any CAN-SPAM violation detected

### How to Activate

**Railway (production)**:
```
Railway Dashboard → Service → Variables → EMERGENCY_STOP = true → Redeploy
```

**Local**:
```bash
export EMERGENCY_STOP=true
```

### What It Blocks
ALL outbound paths are gated:
- `execution/operator_outbound.py` (outbound, cadence, revival)
- `execution/instantly_dispatcher.py`
- `execution/heyreach_dispatcher.py`
- `dashboard/health_app.py` (approval processing)
- `core/ghl_execution_gateway.py`

### Recovery
1. Investigate root cause (see sections below)
2. Fix the issue
3. Set `EMERGENCY_STOP=false` on Railway
4. Redeploy
5. Resume with small batch (2-3 emails) to verify fix

---

## 2. Authentication Errors (401/403)

### Dashboard Login Fails

**Symptoms**: 401 on `/api/*`, redirect to `/login`, "Authentication Required" on dashboard

**Diagnosis**:
```bash
python scripts/diagnose.py
# Or check directly:
curl -s https://caio-swarm-dashboard-production.up.railway.app/api/runtime/dependencies
```

**Common causes**:
| Cause | Fix |
|-------|-----|
| `DASHBOARD_AUTH_TOKEN` not set on Railway | Set in Railway env vars |
| `SESSION_SECRET_KEY` not set | Set in Railway env vars (required for production) |
| Cookie expired | Clear browser cookies, re-login |
| Token mismatch (local vs Railway) | Verify token matches between environments |

**Escalation**: If neither `SESSION_SECRET_KEY` nor `DASHBOARD_AUTH_TOKEN` is set, the app will crash with `RuntimeError` in production/staging.

### Webhook Auth Failures

**Symptoms**: 401/403 on `/webhooks/*` endpoints, events not processing

**Diagnosis**:
```bash
# Check webhook signature config
curl -s https://caio-swarm-dashboard-production.up.railway.app/api/runtime/dependencies | python -m json.tool
# Look for: webhook_signature_required, heyreach_unsigned_allowlist
```

**Fixes**:
| Issue | Fix |
|-------|-----|
| Instantly webhook signature mismatch | Verify `INSTANTLY_WEBHOOK_SECRET` matches Instantly dashboard |
| HeyReach bearer token mismatch | Set `HEYREACH_BEARER_TOKEN` on Railway, ensure matches HeyReach config |
| Unsigned allowlist enabled | Set `HEYREACH_UNSIGNED_ALLOWLIST=false` on Railway |

---

## 3. Webhook Failure Triage

### Events Not Processing

**Diagnosis**:
```bash
# Check webhook registration
python scripts/register_instantly_webhooks.py --list
python scripts/register_heyreach_webhooks.py --list
```

**Common causes**:
| Symptom | Cause | Fix |
|---------|-------|-----|
| No events at all | Webhooks not registered | Re-register via scripts above |
| Intermittent 500s | Payload schema mismatch | Check `webhooks/` handler logs |
| Timeout errors | Long processing blocking response | Check circuit breaker state |
| Duplicate events | No idempotency | Check `cadence_engine.py` idempotency keys |

### Instantly Webhook Issues

**Endpoints**: `/webhooks/instantly/open`, `/webhooks/instantly/reply`, `/webhooks/instantly/bounce`, `/webhooks/instantly/unsubscribe`

**Validation**: All require valid HMAC signature (`INSTANTLY_WEBHOOK_SECRET`).

### HeyReach Webhook Issues

**Endpoints**: `/webhooks/heyreach/*` (11 event types)

**Known issue (HR-05)**: Webhook payload field names not fully validated against real payloads. Schema validated against test harness but awaiting production traffic confirmation.

---

## 4. Redis Connection Loss

### Symptoms
- Dashboard shows empty email queue ("All caught up" when emails should be pending)
- `/api/health` shows Redis disconnected
- Shadow queue operations fail silently (falls back to filesystem)

### Diagnosis
```bash
# Check Redis health via API
curl -s https://caio-swarm-dashboard-production.up.railway.app/api/health | python -m json.tool
# Look for redis_connected field

# Check Upstash dashboard directly
# https://console.upstash.com/redis
```

### Graceful Degradation Path

The system is designed to survive Redis outages:

| Module | Behavior Without Redis |
|--------|----------------------|
| `core/shadow_queue.py` | Falls back to `.hive-mind/shadow_mode_emails/` filesystem |
| `core/state_store.py` | Falls back to local file storage |
| `core/rejection_memory.py` | Falls back to `.hive-mind/rejection_memory/` files |
| `core/feedback_loop.py` | Always writes to file; Redis is optional replication |
| Rate limiters | Fall back to in-memory counters (reset on restart) |
| Circuit breakers | Fall back to in-memory state |

**Warning**: Filesystem fallback means Railway and local are DISCONNECTED. Pipeline emails written locally will NOT appear on Railway dashboard until Redis is restored.

### Recovery
1. Check Upstash status page for outages
2. Verify `REDIS_URL` env var is correct on Railway
3. If Upstash is down: wait for recovery, data will auto-sync
4. If URL is wrong: fix env var, redeploy
5. After recovery: verify `/api/pending-emails` shows correct count

---

## 5. Domain Health Issues

### Bounce Rate Spike

**Threshold**: > 5% across any batch → pause sending

**Steps**:
1. Activate `EMERGENCY_STOP=true`
2. Check Instantly dashboard for domain health scores
3. Identify which domain(s) are affected
4. Check deliverability guard logs for blocked addresses
5. If domain blacklisted: remove from rotation in `config/production.json`
6. Resume with remaining healthy domains

### Domain Blacklisting

**Check**: https://mxtoolbox.com/blacklists.aspx

**If blacklisted**:
1. `EMERGENCY_STOP=true`
2. Remove affected domain from Instantly rotation
3. Submit delisting request to blacklist provider
4. Do NOT resume sending from that domain until delisted
5. Adjust `config/production.json` domain list

---

## 6. Common Production Issues

### Empty Pending Queue (Recurring)

**Root cause**: Almost always a local↔Railway filesystem disconnect. See CLAUDE.md "ARCHITECTURAL LAW" section.

**Quick fix**:
```bash
# Seed training emails directly on Railway (no local pipeline needed)
curl -X POST "https://caio-swarm-dashboard-production.up.railway.app/api/admin/seed_queue" \
  -H "X-Dashboard-Token: <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"count": 5}'
```

### Pipeline Fails Locally

**Common causes**:
| Error | Fix |
|-------|-----|
| `cp1252` encoding error | Ensure no emoji in production code (ASCII only) |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| Redis connection timeout | Check `REDIS_URL` env var, verify Upstash is reachable |
| Apollo API rate limit | Wait 1 hour, reduce batch size |

### Railway Deploy Fails

**Diagnosis**:
```bash
# Check Railway build logs
railway logs --latest
```

**Common causes**:
| Error | Fix |
|-------|-----|
| Missing dependency | Add to `requirements.txt` explicitly (see Pitfall #4 in CLAUDE.md) |
| `nul` file in repo | Already in `.railwayignore` — ensure it's not re-created |
| Health check timeout | Verify `health_app.py` starts within 60s |

---

## 7. Diagnostic Tools

| Tool | Command | Purpose |
|------|---------|---------|
| Diagnose script | `python scripts/diagnose.py` | Full system health check |
| Smoke test | `python scripts/deployed_full_smoke_checklist.py --base-url <URL> --token <TOKEN>` | Production smoke test |
| Auth parity | `python scripts/strict_auth_parity_smoke.py --base-url <URL> --token <TOKEN>` | Security hardening validation |
| Audit CLI | `python scripts/audit_cli.py` | Agentic engineering audit checks |
| Webhook list | `python scripts/register_instantly_webhooks.py --list` | Check registered webhooks |
| OPERATOR status | `python -m execution.operator_outbound --status` | Dispatch state + warmup schedule |

---

## 8. Escalation Matrix

| Severity | Example | Response Time | Action |
|----------|---------|---------------|--------|
| **P0 — Critical** | Sending to wrong recipients, domain blacklisted, data breach | Immediate | `EMERGENCY_STOP=true`, investigate, notify stakeholders |
| **P1 — High** | Bounce rate > 10%, Redis down, auth broken | < 1 hour | Pause sending, diagnose, fix |
| **P2 — Medium** | Single webhook failing, one domain unhealthy | < 4 hours | Monitor, fix in next maintenance window |
| **P3 — Low** | Deprecation warnings, non-critical test failures | Next sprint | Log in task.md, schedule fix |
