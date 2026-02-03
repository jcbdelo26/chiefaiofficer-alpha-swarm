# 🎯 Agent Manager Quick Reference
**Production Support Commands**

**Last Updated:** 2026-01-19

---

## 🚀 Quick Start

```powershell
# Navigate to project
cd "d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"

# Activate virtual environment (if using)
.\.venv\Scripts\Activate.ps1
```

---

## ✅ Production Validation

### Run Full Validation
```powershell
python core/production_validator.py
```

**Output:** `.hive-mind/PRODUCTION_VALIDATION_REPORT.md`

### Check Readiness Score
```powershell
python -c "from core.production_validator import ProductionValidator; from core.agent_manager import AgentManager; print(f'Readiness: {ProductionValidator(AgentManager()).validate_all()[\"readiness_score\"]}%')"
```

### View Validation Report
```powershell
code .hive-mind/PRODUCTION_VALIDATION_REPORT.md
```

---

## 🧪 Testing

### Run All Tests
```powershell
python core/test_orchestrator.py
```

**Output:** `.hive-mind/testing/TEST_REPORT.md`

### Run Quick Tests
```powershell
python -c "from core.test_orchestrator import TestOrchestrator; from core.agent_manager import AgentManager; TestOrchestrator(AgentManager()).run_all_tests('quick')"
```

### Test Specific Agent
```powershell
python -c "from core.test_orchestrator import TestOrchestrator; from core.agent_manager import AgentManager; print(TestOrchestrator(AgentManager()).test_agent('hunter'))"
```

### View Test Results
```powershell
code .hive-mind/testing/TEST_REPORT.md
```

---

## 📊 Monitoring

### Check System Health
```powershell
python execution/health_monitor.py --once
```

### View Health Log
```powershell
code .hive-mind/health_log.jsonl
```

### Generate KPI Dashboard
```powershell
python dashboard/kpi_dashboard.py --all
```

### View Dashboard
```powershell
code .hive-mind/kpi_report.html
```

---

## 🔍 Agent Management

### List All Agents
```powershell
python -c "from core.agent_manager import AgentManager; am = AgentManager(); agents = am.registry.list_agents(); print(f'Total Agents: {len(agents)}'); [print(f'  - {a.agent_id} ({a.agent_type})') for a in agents]"
```

### Check Agent Health
```powershell
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.registry.agent_health_check('hunter'))"
```

### Get Agent State
```powershell
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.state_manager.get_agent_state('hunter'))"
```

---

## 🔄 Learning & Improvement

### View Recent Learnings
```powershell
python -c "from core.agent_manager import AgentManager; am = AgentManager(); learnings = am.learning_manager.get_learnings(time_period='7d'); print(f'Learnings (7d): {len(learnings)}'); [print(f'  - {l.event_type}: {l.learning_data}') for l in learnings[:5]]"
```

### Identify Patterns
```powershell
python -c "from core.agent_manager import AgentManager; am = AgentManager(); patterns = am.learning_manager.identify_patterns(min_occurrences=3); print(f'Patterns Found: {len(patterns)}'); [print(f'  - {p}') for p in patterns]"
```

### Log Learning Event
```python
from core.agent_manager import AgentManager

am = AgentManager()
learning_id = am.learning_manager.log_learning(
    source_agent="crafter",
    event_type="campaign_success",
    learning_data={"reply_rate": 15.2, "template": "value_prop_v2"}
)
print(f"Logged: {learning_id}")
```

---

## 🔧 Development Helpers

### Validate Week 1 Progress
```powershell
# Check API connections
python execution/test_connections.py

# Check framework integration
python core/production_validator.py

# View progress
code .hive-mind/WEEK_1_QUICK_START_CHECKLIST.md
```

### Update LinkedIn Cookie
```powershell
# Update rotation timestamp
python execution/health_monitor.py --update-linkedin-rotation

# Test connection
python execution/test_connections.py
```

### Create Context Checkpoint
```python
from core.agent_manager import AgentManager

am = AgentManager()
am.context_manager.create_context_checkpoint(
    agent_id="crafter",
    checkpoint_name="pre_deployment_v1"
)
```

---

## 📋 Daily Workflow

### Morning Check (7:00 AM)
```powershell
# 1. Validate system
python core/production_validator.py

# 2. Check health
python execution/health_monitor.py --once

# 3. View dashboard
python dashboard/kpi_dashboard.py --all
code .hive-mind/kpi_report.html
```

### Weekly Review (Monday)
```powershell
# 1. Run full tests
python core/test_orchestrator.py

# 2. Validate production readiness
python core/production_validator.py

# 3. Review learnings
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.learning_manager.get_learnings(time_period='7d'))"

# 4. View reports
code .hive-mind/testing/TEST_REPORT.md
code .hive-mind/PRODUCTION_VALIDATION_REPORT.md
```

---

## 🚨 Troubleshooting

### System Not Ready
```powershell
# Check what's failing
python core/production_validator.py

# View detailed report
code .hive-mind/PRODUCTION_VALIDATION_REPORT.md

# Fix issues and re-validate
```

### Tests Failing
```powershell
# Run tests
python core/test_orchestrator.py

# View failures
code .hive-mind/testing/TEST_REPORT.md

# Test specific component
python -c "from core.test_orchestrator import TestOrchestrator; from core.agent_manager import AgentManager; print(TestOrchestrator(AgentManager()).test_agent('hunter'))"
```

### Agent Unhealthy
```powershell
# Check health
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.registry.agent_health_check('hunter'))"

# Restart agent
python -c "from core.agent_manager import AgentManager; am = AgentManager(); am.lifecycle.restart_agent('hunter')"
```

---

## 📁 Key Files

### Configuration
- `.env` - Environment variables and API keys
- `requirements.txt` - Python dependencies
- `.gitignore` - Git exclusions

### Documentation
- `.hive-mind/AGENT_MANAGER_PRODUCTION_SUPPORT.md` - This guide
- `.hive-mind/WEEK_1_IMPLEMENTATION_GUIDE.md` - Week 1 setup
- `.hive-mind/TESTING_TRAINING_IMPROVEMENT_FRAMEWORK.md` - Testing strategy
- `docs/AGENT_MANAGER_INTEGRATION_GUIDE.md` - Agent Manager details

### Core Components
- `core/agent_manager.py` - Central orchestration
- `core/production_validator.py` - Production validation
- `core/test_orchestrator.py` - Test coordination
- `core/context_manager.py` - Context management
- `core/grounding_chain.py` - Fact verification
- `core/feedback_collector.py` - Learning collection

### Execution
- `execution/test_connections.py` - API connection testing
- `execution/health_monitor.py` - Health monitoring
- `execution/rate_limiter.py` - Rate limiting

### Dashboard
- `dashboard/kpi_dashboard.py` - KPI visualization

### Data
- `.hive-mind/registry.json` - Agent registry
- `.hive-mind/connection_test.json` - Connection test results
- `.hive-mind/production_validation.json` - Validation results
- `.hive-mind/testing/test_results.json` - Test results
- `.hive-mind/learnings.json` - Learning database

---

## 🎯 Production Readiness Checklist

### Week 1 (Current)
- [x] API credentials configured (80%)
- [ ] Framework components integrated (0%)
- [ ] Webhooks configured (0%)
- [ ] Monitoring dashboard active (0%)

### Week 2
- [ ] All tests passing (≥95%)
- [ ] Production validation passing (≥90%)
- [ ] ICP validation complete
- [ ] Baseline metrics recorded

### Week 3
- [ ] Shadow mode deployment
- [ ] Comparison data collected
- [ ] Performance validated

### Week 4+
- [ ] Canary deployment (10%)
- [ ] Partial deployment (50%)
- [ ] Full deployment (100%)

---

## 🔗 Quick Links

**Documentation:**
- [Agent Manager Production Support](.hive-mind/AGENT_MANAGER_PRODUCTION_SUPPORT.md)
- [Week 1 Implementation Guide](.hive-mind/WEEK_1_IMPLEMENTATION_GUIDE.md)
- [Testing Framework](.hive-mind/TESTING_TRAINING_IMPROVEMENT_FRAMEWORK.md)

**Reports:**
- [Production Validation](.hive-mind/PRODUCTION_VALIDATION_REPORT.md)
- [Test Results](.hive-mind/testing/TEST_REPORT.md)
- [KPI Dashboard](.hive-mind/kpi_report.html)

**Code:**
- [Agent Manager](core/agent_manager.py)
- [Production Validator](core/production_validator.py)
- [Test Orchestrator](core/test_orchestrator.py)

---

**Version:** 1.0  
**Last Updated:** 2026-01-19
