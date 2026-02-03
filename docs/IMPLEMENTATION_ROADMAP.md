# 🚀 Implementation Roadmap: Revenue Swarm Production

**Goal**: Get the unified swarm working with real data, harden it, then scale.

**Principle**: Validate before you scale. Bulletproof before you deploy.

---

## 📅 Week 1: Get It Working

### Day 1: Infrastructure Setup (Human Tasks)

#### Task 1.1: Create Supabase Project
- [ ] Go to [supabase.com](https://supabase.com)
- [ ] Sign up / Log in
- [ ] Click **New Project**
- [ ] Name: `chiefaiofficer-revops`
- [ ] Database Password: (save this somewhere secure)
- [ ] Region: Choose closest to you
- [ ] Wait 2 minutes for provisioning

**Capture these values:**
```
Project URL: https://____________.supabase.co
anon key: eyJ_______________________________
service_role key: eyJ_______________________ (for admin operations)
```

#### Task 1.2: Run Database Schema
- [ ] In Supabase Dashboard → **SQL Editor**
- [ ] Click **New Query**
- [ ] Open file: `mcp-servers/supabase-mcp/schema.sql`
- [ ] Copy ALL contents → Paste into SQL Editor
- [ ] Click **Run**
- [ ] Verify: Should see "Success. No rows returned"

#### Task 1.3: Configure Environment
- [ ] Open `.env` file in project root
- [ ] Add/update these values:

```env
# ============================================
# SUPABASE (Required - add these)
# ============================================
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=eyJ...your-anon-key...

# ============================================
# CRM - GoHighLevel (Required)
# ============================================
GHL_API_KEY=your-ghl-api-key
GHL_LOCATION_ID=your-location-id

# ============================================
# OUTREACH - Instantly (Required)
# ============================================
INSTANTLY_API_KEY=your-instantly-key

# ============================================
# ENRICHMENT - Clay (Required)
# ============================================
CLAY_API_KEY=your-clay-api-key

# ============================================
# SCRAPING - LinkedIn (Required)
# ============================================
# Get this from browser: DevTools → Application → Cookies → li_at
LINKEDIN_COOKIE=your-li_at-cookie-value

# ============================================
# AI - Choose one (Required)
# ============================================
ANTHROPIC_API_KEY=your-anthropic-key
# OR
GEMINI_API_KEY=your-gemini-key

# ============================================
# OPTIONAL SERVICES
# ============================================
EXA_API_KEY=your-exa-key
RB2B_API_KEY=your-rb2b-key
```

#### Task 1.4: Verify Credentials
After updating .env, tell Ampcode to run:
```
Run test_connections.py and show me the results
```

---

### Day 2: First Pipeline Run (Ampcode Assisted)

#### Task 2.1: Run Pipeline in Sandbox
```bash
python execution/run_pipeline.py --mode sandbox --limit 10
```
**Expected**: All 6 stages pass, 2 campaigns created

#### Task 2.2: Run Pipeline in Staging (Real APIs, No Sends)
```bash
python execution/run_pipeline.py --mode staging --source competitor_gong --limit 5
```
**Expected**: Real LinkedIn data scraped, enriched, segmented

#### Task 2.3: Review Output
- [ ] Check `.hive-mind/pipeline_runs/` for run reports
- [ ] Review campaign JSON files
- [ ] Verify ICP scoring looks correct
- [ ] Check segmentation tiers make sense

---

### Day 3: First Real Campaign (Human Review Required)

#### Task 3.1: Generate Real Campaigns
```bash
python execution/run_pipeline.py --mode staging --source competitor_gong --limit 20
```

#### Task 3.2: Human Review Checkpoint
- [ ] Review generated campaigns in `.hive-mind/pipeline_runs/`
- [ ] Check personalization quality
- [ ] Verify compliance (unsubscribe, physical address)
- [ ] Approve or reject each campaign

#### Task 3.3: Push to Instantly (If Approved)
```bash
python execution/run_pipeline.py --mode production --segment tier_2 --limit 10
```
**Note**: Tier 1 requires explicit AE approval via Gatekeeper

---

### Day 4-5: Iterate & Validate

#### Task 4.1: Monitor Self-Annealing
```bash
python core/self_annealing.py
```
Check: Is the Q-table learning from outcomes?

#### Task 4.2: Run Integration Tests
```bash
pytest tests/test_unified_integration.py -v
```
**Expected**: 17+ tests passing

#### Task 4.3: Validate Full Pipeline
```bash
python execution/pipeline_validator.py
```
**Expected**: All 7 stages pass

---

## 📅 Week 2: Harden

### Day 6-7: Error Handling & Retry Logic

#### Task 5.1: Add Circuit Breakers
Tell Ampcode:
```
Add circuit breaker pattern to:
- execution/hunter_scrape_followers.py (LinkedIn API)
- execution/enricher_clay_waterfall.py (Clay API)
- mcp-servers/ghl-mcp/server.py (GHL API)

Requirements:
- Open circuit after 3 consecutive failures
- Half-open after 60 seconds
- Log all state transitions
```

#### Task 5.2: Add Retry with Exponential Backoff
Tell Ampcode:
```
Ensure all API calls in execution/*.py have:
- Retry with exponential backoff (1s, 2s, 4s, 8s, max 30s)
- Max 5 retries
- Specific exception handling for rate limits vs errors
```

#### Task 5.3: Add Idempotency Keys
Verify GHL-MCP has idempotency:
```bash
python -c "from mcp-servers.ghl-mcp.server import IdempotencyManager; print('OK')"
```

---

### Day 8-9: Monitoring & Logging

#### Task 6.1: Structured Logging
Tell Ampcode:
```
Add structured JSON logging to:
- core/self_annealing.py
- execution/run_pipeline.py
- execution/unified_agent_registry.py

Format:
{
  "timestamp": "ISO8601",
  "level": "INFO|WARN|ERROR",
  "component": "agent_name",
  "action": "what_happened",
  "duration_ms": 123,
  "metadata": {}
}

Log to: .hive-mind/logs/{date}.jsonl
```

#### Task 6.2: Health Check Endpoint
Tell Ampcode:
```
Create execution/health_check.py that checks:
1. All MCP servers responding
2. Supabase connection working
3. API credentials valid (GHL, Instantly, Clay)
4. Self-annealing engine state
5. Context manager budget

Return JSON with overall health status
```

#### Task 6.3: Metrics Collection
Tell Ampcode:
```
Add metrics tracking to run_pipeline.py:
- Pipeline runs per day
- Success/failure rate by stage
- Average duration per stage
- Token usage estimation
- Cost per pipeline run

Store in Supabase: metrics table
```

---

### Day 10: Alerting

#### Task 7.1: Critical Alerts
Tell Ampcode:
```
Create core/alerts.py with alerting for:
- Pipeline failure (any stage)
- Spam rate > 1%
- Bounce rate > 5%
- API rate limit hit
- Self-annealing health degraded

Alert channels:
- Log to .hive-mind/alerts/
- Console output (for now)
- (Future: Slack webhook)
```

#### Task 7.2: Daily Summary Report
Tell Ampcode:
```
Create execution/generate_daily_report.py that:
1. Aggregates pipeline runs from last 24h
2. Calculates key metrics
3. Identifies top patterns from self-annealing
4. Generates markdown report
5. Saves to .hive-mind/reports/daily/
```

---

## 📅 Week 3+: Scale (Only After Bulletproofing)

### Prerequisites Checklist

Before scaling, verify ALL of these:

#### Agent Manager Architecture
- [ ] All 11 agents initialize without errors
- [ ] Agent handoffs working correctly
- [ ] Context compaction preventing "dumb zone"
- [ ] Self-annealing Q-table converging
- [ ] Pattern detection finding real patterns

#### Central Orchestration
- [ ] Pipeline runs 100% in sandbox mode
- [ ] Pipeline runs 95%+ in staging mode
- [ ] Error handling catches all edge cases
- [ ] Retry logic handles transient failures
- [ ] Idempotency prevents duplicates

#### Data Integrity
- [ ] Supabase schema handles all data types
- [ ] Lead deduplication working
- [ ] Suppression list syncing
- [ ] GDPR delete requests handled

#### Compliance
- [ ] CAN-SPAM compliant (unsubscribe, address)
- [ ] Bounce handling implemented
- [ ] Spam rate monitoring active
- [ ] Audit log capturing all operations

---

### Scale Phase 1: Docker (If Deploying to Server)

#### Task 8.1: Create Dockerfiles
Tell Ampcode:
```
Create Dockerfiles for:
1. mcp-servers/ghl-mcp/Dockerfile
2. mcp-servers/instantly-mcp/Dockerfile
3. mcp-servers/supabase-mcp/Dockerfile
4. execution/Dockerfile (main pipeline)

Base image: python:3.11-slim
Include: requirements.txt, .env handling
Health checks: included
```

#### Task 8.2: Docker Compose
Tell Ampcode:
```
Create docker-compose.yml with:
- All MCP servers as services
- Main pipeline service
- Shared volume for .hive-mind
- Environment variable injection
- Health check dependencies
- Restart policies
```

#### Task 8.3: Local Testing
```bash
docker-compose up --build
docker-compose run pipeline python execution/run_pipeline.py --mode sandbox
```

---

### Scale Phase 2: CI/CD (If Team > 1)

#### Task 9.1: GitHub Actions
Tell Ampcode:
```
Create .github/workflows/ci.yml:
- Run on: push to main, PR
- Steps: lint, typecheck, test
- Required: all tests pass
```

#### Task 9.2: Deploy Workflow
Tell Ampcode:
```
Create .github/workflows/deploy.yml:
- Triggered: manual or tag
- Build Docker images
- Push to container registry
- Deploy to staging/production
- Run health checks
- Rollback on failure
```

---

### Scale Phase 3: Kubernetes (If Productizing)

**Only consider K8s if:**
- You have 10+ concurrent users
- You need horizontal scaling
- You're offering this as a SaaS product

#### Task 10.1: K8s Manifests
Tell Ampcode:
```
Create k8s/ directory with:
- Namespace
- ConfigMaps for env vars
- Secrets for API keys
- Deployments for each MCP server
- Services for internal communication
- HPA for auto-scaling
- Ingress for external access
```

---

## 📋 Quick Reference: Commands

### Daily Operations
```bash
# Run pipeline (sandbox)
python execution/run_pipeline.py --mode sandbox --limit 10

# Run pipeline (staging - real APIs, no sends)
python execution/run_pipeline.py --mode staging --source competitor_gong --limit 20

# Run pipeline (production - real sends!)
python execution/run_pipeline.py --mode production --segment tier_2 --limit 10

# Check health
python execution/health_check.py

# Run tests
pytest tests/test_unified_integration.py -v

# Validate pipeline
python execution/pipeline_validator.py
```

### Debugging
```bash
# Test API connections
python execution/test_connections.py

# Check self-annealing status
python -c "from core.self_annealing import SelfAnnealingEngine; e = SelfAnnealingEngine(); print(e.get_annealing_status())"

# View recent pipeline runs
dir .hive-mind\pipeline_runs

# Check agent registry
python -c "from execution.unified_agent_registry import UnifiedAgentRegistry; r = UnifiedAgentRegistry(); print(r.get_status())"
```

---

## ✅ Success Criteria

### Week 1 Complete When:
- [ ] Supabase connected and schema deployed
- [ ] All API connections verified
- [ ] Pipeline runs successfully in sandbox
- [ ] Pipeline runs successfully in staging
- [ ] First real campaign reviewed and approved

### Week 2 Complete When:
- [ ] Circuit breakers on all external APIs
- [ ] Retry logic with exponential backoff
- [ ] Structured logging to .hive-mind/logs/
- [ ] Health check endpoint working
- [ ] Daily report generation working
- [ ] All 17+ integration tests passing

### Week 3+ Complete When:
- [ ] Dockerfiles for all services
- [ ] docker-compose working locally
- [ ] CI/CD pipeline (if team > 1)
- [ ] Production monitoring in place
- [ ] Runbook for common issues documented

---

## 🆘 Getting Help

When you're stuck, tell Ampcode:
```
I'm on Week [X], Day [Y], Task [Z].
The issue is: [describe what's happening]
Expected: [what should happen]
Actual: [what's actually happening]
```

Ampcode will help you debug and continue.

---

**Start now**: Complete Task 1.1 (Create Supabase Project), then tell me when done.
