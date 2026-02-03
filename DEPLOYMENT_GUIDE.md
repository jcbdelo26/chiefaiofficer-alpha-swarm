# Unified CAIO RevOps Swarm - Deployment Guide

## Quick Start Decision Tree

```
Are you a developer setting up for the first time?
├── YES → Start with LOCAL deployment (Option 1)
└── NO → Are you deploying for the whole sales team?
    ├── YES → Use DOCKER CLOUD deployment (Option 2)
    └── NO → Use ONE-CLICK deploy (Option 3)
```

---

## Option 1: Local Development (Recommended First)

**Best for**: Initial setup, testing, customization  
**Time**: ~1 hour  
**Requirements**: Windows/Mac/Linux, Python 3.11+

### Step 1: Clone and Setup
```powershell
# Navigate to project
cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.\.venv\Scripts\Activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Credentials
```powershell
# Copy example env file
copy .env.example .env

# Edit with your API keys
notepad .env
```

Required environment variables:
```env
# GoHighLevel
GHL_API_KEY=your_ghl_api_key
GHL_LOCATION_ID=your_location_id

# Google (for Calendar/Gmail)
GOOGLE_CREDENTIALS_PATH=./credentials/google_credentials.json

# Enrichment
CLAY_API_KEY=your_clay_key
PROXYCURL_API_KEY=your_proxycurl_key

# Database
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

### Step 3: Start the System
```powershell
# Terminal 1: Start Health Dashboard
uvicorn dashboard.health_app:app --port 8080

# Terminal 2: Start MCP Servers
python scripts/start_mcp_servers.py

# Terminal 3: Start Queen Orchestrator (when ready)
python execution/unified_queen_orchestrator.py
```

### Step 4: Access Dashboard
Open browser: http://localhost:8080

---

## Option 2: Docker Cloud Deployment

**Best for**: Team access, always-on operation  
**Time**: 2-4 hours  
**Requirements**: Docker, Cloud VM (DigitalOcean/AWS/Azure)

### Architecture
```
┌─────────────────────────────────────────────────────┐
│                    CLOUD VM                          │
│  ┌─────────────────────────────────────────────┐    │
│  │              Docker Compose                  │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐       │    │
│  │  │ Queen   │ │Dashboard│ │ MCP     │       │    │
│  │  │Orchestr.│ │ :8080   │ │ Servers │       │    │
│  │  └─────────┘ └─────────┘ └─────────┘       │    │
│  │  ┌─────────────────────────────────┐       │    │
│  │  │         Redis (Queue)           │       │    │
│  │  └─────────────────────────────────┘       │    │
│  └─────────────────────────────────────────────┘    │
│                        │                             │
│                   nginx:443                          │
└────────────────────────┼────────────────────────────┘
                         │
                    HTTPS/WSS
                         │
              ┌──────────┴──────────┐
              │   Sales Team        │
              │   (Browser Access)  │
              └─────────────────────┘
```

### Deploy to DigitalOcean (Recommended)

#### 1. Create Droplet
- Size: 2 vCPU, 4GB RAM ($24/month)
- Image: Ubuntu 22.04
- Enable backups

#### 2. Setup Server
```bash
# SSH into server
ssh root@your-server-ip

# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Docker Compose
apt install docker-compose -y

# Clone repository (or upload)
git clone https://your-repo-url/chiefaiofficer-alpha-swarm.git
cd chiefaiofficer-alpha-swarm

# Create .env file with production values
nano .env

# Start everything
docker-compose up -d

# View logs
docker-compose logs -f
```

#### 3. Setup Domain & SSL
```bash
# Install Caddy (automatic HTTPS)
apt install caddy -y

# Edit Caddyfile
nano /etc/caddy/Caddyfile
```

Add:
```
revops.yourdomain.com {
    reverse_proxy localhost:8080
}
```

```bash
systemctl restart caddy
```

#### 4. Access
- Dashboard: https://revops.yourdomain.com
- Health API: https://revops.yourdomain.com/api/health

---

## Option 3: One-Click Deploy (For Non-Technical Users)

**Best for**: AEs, Head of Sales, quick team rollout  
**Time**: 30 minutes  
**Requirements**: Just a browser and API keys

### Railway.app Deployment (Recommended)

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/caio-swarm)

1. Click "Deploy on Railway"
2. Connect your GitHub account
3. Enter environment variables when prompted
4. Click Deploy
5. Access your dashboard URL

### Render.com Deployment

1. Fork the repository to your GitHub
2. Go to render.com → New → Web Service
3. Connect your forked repo
4. Set environment variables
5. Deploy

---

## For Your Head of Sales: Recommended Path

### Week 1-2: You Run It Locally
- You manage the system
- Sales team sees results in GHL
- Collect feedback on what works

### Week 3: Deploy to Cloud
- Set up Docker on cloud VM
- Give Head of Sales dashboard access
- Train on interpreting metrics

### Week 4+: Full Team Access
- AEs can view their pipeline metrics
- Automated reports via email/Slack
- Self-service for common operations

---

## Daily RevOps Integration

### How the System Fits Your Workflow

```
┌────────────────────────────────────────────────────────────────┐
│                    YOUR DAILY REVOPS FLOW                       │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  6:00 AM   Pipeline Scan (Automated)                           │
│            └→ SCOUT scans GHL for overnight activity           │
│            └→ COACH scores warm leads                          │
│            └→ Slack: "3 hot leads need follow-up"              │
│                                                                 │
│  8:00 AM   Morning Brief (Automated)                           │
│            └→ Email summary of pipeline status                 │
│            └→ Today's meeting briefs generated                 │
│            └→ Recommended actions for each AE                  │
│                                                                 │
│  9:00 AM   AE Workflow Starts                                  │
│            └→ AE opens GHL, sees prioritized task list         │
│            └→ CRAFTER has pre-drafted follow-ups               │
│            └→ AE reviews, approves via GATEKEEPER              │
│                                                                 │
│  Throughout Day                                                 │
│            └→ SCHEDULER handles booking requests               │
│            └→ COMMUNICATOR drafts email responses              │
│            └→ All actions logged, visible in dashboard         │
│                                                                 │
│  8:00 PM   Meeting Prep (Automated)                            │
│            └→ RESEARCHER generates briefs for tomorrow         │
│            └→ Sent to AE inbox by 10 PM                        │
│                                                                 │
│  End of Week                                                    │
│            └→ Self-annealing reviews what worked               │
│            └→ System improves for next week                    │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### What Each Person Sees

| Role | Primary Interface | Key Metrics |
|------|------------------|-------------|
| **AE** | GHL + Slack notifications | My pipeline, tasks, meeting briefs |
| **Head of Sales** | Dashboard + Weekly reports | Team metrics, conversion rates |
| **You (Admin)** | Full dashboard + logs | System health, agent performance |

---

## Security Considerations

### For Cloud Deployment
- [ ] Use environment variables (never commit API keys)
- [ ] Enable HTTPS (Caddy does this automatically)
- [ ] Set up firewall (only ports 80, 443, 22)
- [ ] Use strong passwords for all services
- [ ] Enable 2FA on cloud provider account
- [ ] Regular backups (daily minimum)

### API Key Management
```bash
# Never do this:
GHL_API_KEY=abc123  # In code

# Always do this:
GHL_API_KEY=${GHL_API_KEY}  # From environment
```

---

## Cost Estimate

| Component | Local | Cloud (Basic) | Cloud (Production) |
|-----------|-------|---------------|-------------------|
| Compute | $0 | $24/mo (DO) | $96/mo (4 vCPU) |
| Database | $0 (SQLite) | $0 (Supabase free) | $25/mo |
| Domain | N/A | $12/yr | $12/yr |
| SSL | N/A | Free (Caddy) | Free |
| **Total** | **$0** | **~$25/mo** | **~$130/mo** |

---

## Next Steps

1. **Today**: Start with local deployment, get familiar
2. **This Week**: Complete remaining roadmap tasks
3. **Next Week**: Test with real leads in your pipeline
4. **Week 3**: Deploy to cloud, give team access
5. **Week 4**: Full production rollout

---

## Support & Troubleshooting

### Common Issues

**"API rate limit exceeded"**
- Check dashboard for which integration
- Adjust rate limits in `core/unified_integration_gateway.py`

**"Circuit breaker OPEN"**
- An integration is failing repeatedly
- Check logs, fix underlying issue
- Reset via dashboard or `gateway.reset_circuit("integration_name")`

**"Permission denied"**
- Check `core/agent_action_permissions.json`
- Ensure agent has required permissions

### Getting Help
- Check `.hive-mind/learnings.json` for self-diagnosed issues
- Review audit logs at `.hive-mind/integration_audit.json`
- Dashboard shows real-time health status
