# 🖥️ Agent Manager Terminal Command Cheat Sheet

**Quick Reference**: Essential terminal commands for Agent Manager operations

---

## 📋 **Basic Validation Commands**

### Check Production Readiness
```bash
# Quick check (non-verbose)
python execution/production_checklist.py

# Detailed check with all details
python execution/production_checklist.py --verbose

# Export results to JSON
python execution/production_checklist.py --export json
# Output: .hive-mind/reports/production_readiness.json
```

### Full Production Validation
```bash
# Complete validation (5 levels)
python execution/validate_production_readiness.py

# Staging mode validation
python execution/validate_production_readiness.py --mode staging

# Skip API tests (for offline validation)
python execution/validate_production_readiness.py --skip-api-tests
```

---

## 🤖 **Agent Manager Core Operations**

### Test Agent Discovery
```bash
# Discover agents in execution directory
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.registry.discover_agents('./execution'))"

# Discover all agents
python -c "from core.agent_manager import AgentManager; am = AgentManager(); agents = am.registry.list_agents(); print(f'Found {len(agents)} agents')"
```

### Check Agent Health
```bash
# Check single agent
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.registry.agent_health_check('hunter'))"

# Check all agents
python -c "
from core.agent_manager import AgentManager
am = AgentManager()
for agent_id in ['hunter', 'enricher', 'segmentor', 'crafter', 'gatekeeper']:
    health = am.registry.agent_health_check(agent_id)
    print(f'{agent_id}: {health}')
"
```

### Monitor Context Usage
```bash
# Check context for single agent
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.context_manager.monitor_context_usage('crafter'))"

# Get context analytics
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.context_manager.get_context_analytics('crafter', '7d'))"
```

### View Learning Patterns
```bash
# Identify patterns from learnings
python -c "
from core.agent_manager import AgentManager
am = AgentManager()
patterns = am.learning_manager.identify_patterns(event_type='campaign_rejection', min_occurrences=3)
for p in patterns:
    print(f'{p[\"pattern\"]}: {p[\"confidence\"]*100:.1f}% confidence')
"
```

---

## 🔄 **Unified Agent Registry Commands**

### List All Agents
```bash
# View all registered agents
python -c "from execution.unified_agent_registry import UnifiedAgentRegistry; r = UnifiedAgentRegistry(); r.print_status()"

# List by swarm
python -c "
from execution.unified_agent_registry import UnifiedAgentRegistry, AgentSwarm
r = UnifiedAgentRegistry()
alpha = r.list_agents(swarm=AgentSwarm.ALPHA)
print(f'Alpha Swarm: {len(alpha)} agents')
revenue = r.list_agents(swarm=AgentSwarm.REVENUE)
print(f'Revenue Swarm: {len(revenue)} agents')
"
```

### Initialize Agents
```bash
# Initialize all agents
python -c "from execution.unified_agent_registry import UnifiedAgentRegistry; r = UnifiedAgentRegistry(); results = r.initialize_all(); print(results)"

# Initialize specific swarm
python -c "from execution.unified_agent_registry import UnifiedAgentRegistry, AgentSwarm; r = UnifiedAgentRegistry(); r.initialize_all(swarm=AgentSwarm.ALPHA)"

# Get agent instance
python -c "from execution.unified_agent_registry import UnifiedAgentRegistry; r = UnifiedAgentRegistry(); hunter = r.get_agent('hunter'); print(type(hunter))"
```

### Check Agent Status
```bash
# Get status of all agents
python -c "
from execution.unified_agent_registry import UnifiedAgentRegistry
r = UnifiedAgentRegistry()
status = r.get_status()
import json
print(json.dumps(status, indent=2))
"
```

---

## 🔄 **Workflow Commands**

### Create Workflow
```bash
# Create simple test workflow
python -c "
from core.agent_manager import AgentManager
am = AgentManager()
wf_id = am.create_workflow(
    name='test_workflow',
    steps=[
        {'agent': 'hunter', 'action': 'scrape_linkedin', 'inputs': ['url'], 'outputs': ['leads']},
        {'agent': 'enricher', 'action': 'enrich_data', 'inputs': ['leads'], 'outputs': ['enriched']}
    ]
)
print(f'Created workflow: {wf_id}')
"
```

### Execute Unified Workflows
```bash
# Run lead to campaign workflow (sandbox mode - no API calls)
python execution/unified_workflows.py lead_to_campaign --mode sandbox --input test_url

# Run in staging mode (real APIs, no sends)
python execution/unified_workflows.py lead_to_campaign --mode staging --input "https://linkedin.com/in/example"

# Run in production mode (REAL SENDS!)
python execution/unified_workflows.py lead_to_campaign --mode production --input "https://linkedin.com/in/example"

# Real-time engagement workflow
python execution/unified_workflows.py real_time_engagement --mode staging --visitor-id visitor_123

# Document enrichment workflow
python execution/unified_workflows.py document_enrichment --mode staging --document path/to/doc.pdf

# Self-annealing workflow
python execution/unified_workflows.py self_annealing --mode production --time-period 7d
```

### Check Workflow Status
```bash
# Get workflow state
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.get_workflow_state('workflow_id_here'))"

# List all workflows
python -c "
from pathlib import Path
import json
workflows_dir = Path('.hive-mind/workflows')
if workflows_dir.exists():
    for wf_file in workflows_dir.glob('*.json'):
        with open(wf_file) as f:
            wf = json.load(f)
            print(f'{wf[\"workflow_id\"]}: {wf[\"name\"]}')
"
```

---

## 🚀 **Pipeline Operations**

### Run Main Pipeline
```bash
# Sandbox mode (mock data, no API calls)
python execution/run_pipeline.py --mode sandbox --limit 10

# Staging mode (real APIs, no sends)
python execution/run_pipeline.py --mode staging --source competitor_gong --limit 20

# Production mode (REAL SENDS!)
python execution/run_pipeline.py --mode production --segment tier_2 --limit 10

# Specific source
python execution/run_pipeline.py --mode staging --source competitor_gong --limit 50
```

### Pipeline Validation
```bash
# Validate pipeline configuration
python execution/pipeline_validator.py

# Validate specific stage
python execution/pipeline_validator.py --stage enrichment
```

---

## 🏥 **Health & Monitoring Commands**

### System Health Check
```bash
# Run health check on all systems
python execution/health_check.py

# Verbose output
python execution/health_check.py --verbose

# Export to JSON
python execution/health_check.py --export json
```

### Generate Daily Report
```bash
# Generate report for last 24 hours
python execution/generate_daily_report.py

# Custom time range
python execution/generate_daily_report.py --days 7

# Export to HTML
python execution/generate_daily_report.py --format html
```

### Check Self-Annealing Status
```bash
# Get annealing status
python -c "from core.self_annealing import SelfAnnealingEngine; e = SelfAnnealingEngine(); print(e.get_annealing_status())"

# View Q-table
python -c "
from pathlib import Path
import json
q_table_path = Path('.hive-mind/q_table.json')
if q_table_path.exists():
    with open(q_table_path) as f:
        print(json.dumps(json.load(f), indent=2))
"
```

---

## 🧪 **Testing Commands**

### Run All Tests
```bash
# Run full test suite
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=core --cov=execution

# Run specific test file
pytest tests/test_agent_manager.py -v

# Run specific test
pytest tests/test_agent_manager.py::test_agent_registration -v
```

### Test API Connections
```bash
# Test all API connections
python execution/test_connections.py

# Test specific service
python execution/test_connections.py --service supabase
python execution/test_connections.py --service ghl
python execution/test_connections.py --service clay
```

### Generate Test Data
```bash
# Generate sample data for testing
python execution/generate_sample_data.py

# Generate test data for specific scenario
python execution/generate_test_data.py --scenario edge_cases
```

---

## 🛠️ **Development Utilities**

### Generate Agent Wrapper
```bash
# Generate new agent wrapper
python execution/agent_dev_utils.py generate-agent --id revenue_analyst --type analytics

# Generate with custom spec
python execution/agent_dev_utils.py generate-agent --id custom_agent --spec agent_spec.json
```

### Generate Test Fixtures
```bash
# Create test fixtures for agent
python execution/agent_dev_utils.py create-fixtures --agent scout --scenario happy_path

# Create edge case fixtures
python execution/agent_dev_utils.py create-fixtures --agent hunter --scenario edge_cases
```

### Generate Documentation
```bash
# Generate agent documentation
python execution/agent_dev_utils.py generate-docs --agent hunter

# Generate architecture diagram
python execution/agent_dev_utils.py generate-diagram --scope all

# Generate workflow diagram
python execution/agent_dev_utils.py generate-diagram --scope workflow --workflow lead_to_campaign

# Generate changelog
python execution/agent_dev_utils.py generate-changelog --since v1.0.0
```

### Debugging Tools
```bash
# Trace workflow execution
python execution/agent_dev_utils.py trace-workflow --workflow-id workflow_123

# Analyze failure
python execution/agent_dev_utils.py analyze-failure --event-id event_456

# Create debug bundle
python execution/agent_dev_utils.py export-debug --workflow-id workflow_123
# Output: debug_bundle_<timestamp>.zip
```

---

## 🎯 **RPI (Research-Plan-Implement) Commands**

### Run RPI Phases
```bash
# Research phase
python execution/rpi_research.py --target "Acme Corp" --context "competitor_intel"

# Plan phase
python execution/rpi_plan.py --research-id research_123

# Implement phase
python execution/rpi_implement.py --plan-id plan_456
```

---

## 📊 **Dashboard Commands**

### Launch Agent Manager Dashboard
```bash
# Start dashboard on default port (5000)
python dashboard/agent_manager_dashboard.py

# Start on custom port
python dashboard/agent_manager_dashboard.py --port 8080

# Start in production mode
python dashboard/agent_manager_dashboard.py --mode production

# Access at: http://localhost:5000
```

### Launch GATEKEEPER Dashboard
```bash
# Start GATEKEEPER (AE approval dashboard)
python execution/gatekeeper_queue.py

# Access at: http://localhost:5001
```

---

## 🐳 **Docker Commands**

### Build and Run Containers
```bash
# Build all images
docker-compose build

# Build specific service
docker-compose build agent-manager

# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d agent-manager

# View logs
docker-compose logs -f agent-manager

# Check status
docker-compose ps

# Stop all
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

### Container Health Checks
```bash
# Check health of all containers
docker-compose ps

# Exec into container
docker-compose exec agent-manager /bin/bash

# View container logs
docker-compose logs agent-manager --tail 100 -f
```

---

## 📁 **File Management Commands**

### View Hive Mind State
```bash
# List pipeline runs
ls -lh .hive-mind/pipeline_runs/

# View recent events
tail -n 50 .hive-mind/events.jsonl | jq .

# Check campaigns
ls -lh .hive-mind/campaigns/

# View learnings
cat .hive-mind/learnings.json | jq .

# Check Q-table
cat .hive-mind/q_table.json | jq .
```

### Clean Temporary Data
```bash
# Clean old pipeline runs (>30 days)
find .hive-mind/pipeline_runs -type f -mtime +30 -delete

# Clean sandbox data
rm -rf .hive-mind/sandbox/*

# Clean logs (keep last 7 days)
find .hive-mind/logs -type f -mtime +7 -delete
```

---

## 🔐 **Security & Compliance Commands**

### GDPR Operations
```bash
# Export user data
python execution/gdpr_export.py --email user@example.com

# Delete user data
python execution/gdpr_delete.py --email user@example.com --confirm

# List data subjects
python execution/gdpr_export.py --list
```

### Check Security Configuration
```bash
# Verify .env is in .gitignore
grep -q "^.env$" .gitignore && echo "✅ .env protected" || echo "❌ WARNING: .env not in .gitignore"

# Check for hardcoded credentials
grep -r "your_.*_api_key" .env && echo "⚠️  Placeholder credentials found" || echo "✅ Real credentials configured"

# Validate rate limits
python -c "import os; print(f'LinkedIn: {os.getenv(\"LINKEDIN_RATE_LIMIT\")}/min, Clay: {os.getenv(\"CLAY_RATE_LIMIT\")}/min')"
```

---

## 🚨 **Emergency Commands**

### Stop All Operations
```bash
# Stop Docker containers
docker-compose down

# Kill all Python processes (CAUTION!)
pkill -f "python execution"

# Pause all scheduled jobs
# (Implementation depends on scheduler used)
```

### Rollback Operations
```bash
# Restore from backup
cp .hive-mind/backups/latest/* .hive-mind/

# Reset to last checkpoint
python -c "from core.agent_manager import AgentManager; am = AgentManager(); am.restore_checkpoint('checkpoint_name')"
```

### Emergency Health Check
```bash
# Quick system check
python -c "
from execution.unified_agent_registry import UnifiedAgentRegistry
r = UnifiedAgentRegistry()
status = r.get_status()
errors = [k for k, v in status.items() if v['status'] == 'error']
if errors:
    print(f'⚠️  Agents in error: {errors}')
else:
    print('✅ All agents operational')
"
```

---

## 📈 **Quick Status Checks**

### One-Line Status Commands
```bash
# Production readiness score
python execution/production_checklist.py 2>/dev/null | grep "Production Readiness Score"

# Count registered agents
python -c "from execution.unified_agent_registry import UnifiedAgentRegistry; r = UnifiedAgentRegistry(); print(f'{len(r.agents)} agents')"

# Last pipeline run
ls -lt .hive-mind/pipeline_runs/ | head -2 | tail -1

# Recent errors
tail -100 .hive-mind/logs/*.log | grep ERROR | tail -10

# Context health (all agents)
python -c "
from core.agent_manager import AgentManager
am = AgentManager()
for agent in ['hunter', 'enricher', 'segmentor', 'crafter']:
    ctx = am.context_manager.monitor_context_usage(agent)
    print(f'{agent}: {ctx[\"zone\"]}, {ctx[\"context_used\"]}')
"
```

---

## 💡 **Pro Tips**

### Create Bash Aliases
Add to your `.bashrc` or `.zshrc`:

```bash
# Agent Manager Aliases
alias am-check='python execution/production_checklist.py'
alias am-validate='python execution/validate_production_readiness.py'
alias am-health='python execution/health_check.py'
alias am-dashboard='python dashboard/agent_manager_dashboard.py'
alias am-status='python -c "from execution.unified_agent_registry import UnifiedAgentRegistry; UnifiedAgentRegistry().print_status()"'

# Pipeline Aliases
alias pipeline-sandbox='python execution/run_pipeline.py --mode sandbox --limit 10'
alias pipeline-staging='python execution/run_pipeline.py --mode staging --limit 20'
alias pipeline-validate='python execution/pipeline_validator.py'

# Quick checks
alias check-score='python execution/production_checklist.py 2>/dev/null | grep "Production Readiness Score"'
alias check-agents='python -c "from execution.unified_agent_registry import UnifiedAgentRegistry; UnifiedAgentRegistry().print_status()"'
```

### Watch Commands (Auto-refresh)
```bash
# Watch agent status (refresh every 2 seconds)
watch -n 2 'python -c "from execution.unified_agent_registry import UnifiedAgentRegistry; UnifiedAgentRegistry().print_status()"'

# Watch pipeline runs
watch -n 5 'ls -lt .hive-mind/pipeline_runs/ | head -10'

# Watch logs
tail -f .hive-mind/logs/*.log
```

---

## 🔄 **Daily Operations Routine**

### Morning Startup
```bash
# 1. Check system health
python execution/health_check.py

# 2. View agent status
python execution/unified_agent_registry.py

# 3. Check for errors
tail -100 .hive-mind/logs/*.log | grep ERROR

# 4. Start dashboard
python dashboard/agent_manager_dashboard.py &
```

### End of Day
```bash
# 1. Generate daily report
python execution/generate_daily_report.py

# 2. Check production readiness
python execution/production_checklist.py --export json

# 3. Backup .hive-mind
tar -czf "backups/hive-mind-$(date +%Y%m%d).tar.gz" .hive-mind/

# 4. Review learnings
cat .hive-mind/learnings.json | jq .
```

---

**💾 Save this file for quick reference!**

For more details, see:
- `docs/DAILY_AMPCODE_WORKFLOW.md` - Day-by-day implementation guide
- `docs/AGENT_MANAGER_INTEGRATION_GUIDE.md` - Full API reference
- `docs/IMPLEMENTATION_ROADMAP.md` - Production deployment plan
