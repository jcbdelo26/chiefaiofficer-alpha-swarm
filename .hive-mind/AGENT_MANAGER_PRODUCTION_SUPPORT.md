# 🎯 Agent Manager Production Support Guide
**Chief AI Officer Alpha Swarm + Revenue Swarm**

**Date:** 2026-01-19  
**Purpose:** How Agent Manager accelerates production readiness  
**Status:** Active Implementation

---

## 📋 Executive Summary

The **Agent Manager** serves as your central orchestration layer to coordinate testing, validation, deployment, and continuous improvement across both swarms. It provides the infrastructure needed to move from development to production systematically and safely.

### Key Capabilities for Production

1. **🧪 Testing Orchestration** - Coordinate all testing activities
2. **✅ Production Validation** - Pre-deployment readiness checks
3. **📊 Continuous Monitoring** - Real-time health and performance tracking
4. **🔄 Self-Annealing** - Automated learning and improvement
5. **🚀 Deployment Management** - Phased rollouts and rollback capabilities

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT MANAGER CORE                       │
│              (Production Support Layer)                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │  Production      │  │  Test            │               │
│  │  Validator       │  │  Orchestrator    │               │
│  └──────────────────┘  └──────────────────┘               │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │  Deployment      │  │  Improvement     │               │
│  │  Manager         │  │  Engine          │               │
│  └──────────────────┘  └──────────────────┘               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
    ┌─────────┐         ┌─────────┐         ┌─────────┐
    │ Testing │         │ Staging │         │  Prod   │
    │  Env    │         │  Env    │         │  Env    │
    └─────────┘         └─────────┘         └─────────┘
```

---

## 🧪 1. Testing Orchestration

### Overview

The **Test Orchestrator** coordinates all testing activities across agents using Agent Manager's registry and state management.

### Components Created

**File:** `core/test_orchestrator.py`

**Capabilities:**
- Unit testing for individual agents
- Integration testing for workflows
- End-to-end pipeline testing
- Performance benchmarking
- Automated test reporting

### Usage

```python
from core.agent_manager import AgentManager
from core.test_orchestrator import TestOrchestrator

# Initialize
am = AgentManager()
orchestrator = TestOrchestrator(am)

# Run all tests
report = orchestrator.run_all_tests(test_mode="full")

# Test specific agent
result = orchestrator.test_agent("hunter")

# Test workflow
results = orchestrator.test_workflow(
    workflow_id="lead-harvesting",
    test_data={"linkedin_url": "..."}
)
```

### Terminal Commands

```powershell
# Run full test suite
python core/test_orchestrator.py

# View test results
code .hive-mind/testing/TEST_REPORT.md

# Run specific test mode
python -c "from core.test_orchestrator import TestOrchestrator; from core.agent_manager import AgentManager; TestOrchestrator(AgentManager()).run_all_tests('quick')"
```

### Integration with Week 1 Framework

The Test Orchestrator integrates with your Week 1 implementation:

```python
# Test Context Manager
from core.context_manager import ContextManager

ctx = ContextManager()
# Test orchestrator validates context management

# Test Grounding Chain
from core.grounding_chain import GroundingChain

grounding = GroundingChain()
# Test orchestrator validates fact verification

# Test Feedback Collector
from core.feedback_collector import FeedbackCollector

feedback = FeedbackCollector()
# Test orchestrator validates feedback collection
```

---

## ✅ 2. Production Validation

### Overview

The **Production Validator** performs comprehensive pre-deployment checks using Agent Manager coordination.

### Components Created

**File:** `core/production_validator.py`

**Validation Checks:**

1. **Agent Health** - All agents operational
2. **API Connections** - All required services connected
3. **Framework Integration** - Core components integrated
4. **Workflows** - Critical workflows functional
5. **Data Integrity** - Storage structure valid
6. **Security** - Credentials secured, .gitignore configured
7. **Performance** - Benchmarks recorded
8. **Monitoring** - Health monitoring active

### Usage

```python
from core.agent_manager import AgentManager
from core.production_validator import ProductionValidator

# Initialize
am = AgentManager()
validator = ProductionValidator(am)

# Run all validations
report = validator.validate_all()

# Check specific validation
if report['overall_status'] == 'PRODUCTION_READY':
    print("✅ Ready to deploy!")
else:
    print("❌ Issues found:")
    for rec in report['recommendations']:
        print(f"  {rec}")
```

### Terminal Commands

```powershell
# Run production validation
python core/production_validator.py

# View validation report
code .hive-mind/PRODUCTION_VALIDATION_REPORT.md

# Check readiness score
python -c "from core.production_validator import ProductionValidator; from core.agent_manager import AgentManager; print(ProductionValidator(AgentManager()).validate_all()['readiness_score'])"
```

### Validation Criteria

**Production Ready Criteria:**
- ✅ All agents healthy (100%)
- ✅ All required APIs connected (6/6)
- ✅ Core framework integrated (3/3 components)
- ✅ Critical workflows defined (≥3)
- ✅ Data directories present
- ✅ Security configured (.env in .gitignore)
- ✅ Monitoring infrastructure in place

**Readiness Score Calculation:**
```
Readiness Score = (Passed Checks / Total Checks) × 100

Status Determination:
- 90-100%: PRODUCTION_READY
- 70-89%: PARTIALLY_READY
- <70% with failures: NOT_READY
- <70% with warnings: NEEDS_ATTENTION
```

---

## 📊 3. Continuous Monitoring

### Overview

Agent Manager provides real-time monitoring of agent health, performance, and context usage.

### Monitoring Functions

**From `core/agent_manager.py`:**

```python
# Monitor agent state
state = am.state_manager.get_agent_state("hunter")
print(f"Status: {state.status}")
print(f"Queue: {state.queue_size}")
print(f"Context: {state.context_window_used}")

# Monitor context usage
context_info = am.context_manager.monitor_context_usage("crafter")
if context_info['zone'] == 'warning':
    am.context_manager.trigger_compaction("crafter", strategy="rpi")

# Get workflow state
workflow_state = am.state_manager.get_workflow_state("lead-harvesting")
```

### Integration with Existing Monitoring

**Existing Files:**
- `execution/health_monitor.py` - API health monitoring
- `dashboard/kpi_dashboard.py` - KPI visualization
- `execution/rate_limiter.py` - Rate limit tracking

**Agent Manager Enhancement:**

```python
# Unified health check
def unified_health_check():
    """Check all system components"""
    
    # Agent health (via Agent Manager)
    agents = am.registry.list_agents()
    agent_health = {
        a.agent_id: am.registry.agent_health_check(a.agent_id)
        for a in agents
    }
    
    # API health (existing)
    from execution.health_monitor import HealthMonitor
    api_health = HealthMonitor().check_all()
    
    # Combine results
    return {
        "agents": agent_health,
        "apis": api_health,
        "timestamp": datetime.utcnow().isoformat()
    }
```

---

## 🔄 4. Self-Annealing Support

### Overview

Agent Manager's **Learning Manager** centralizes continuous improvement across both swarms.

### Learning Workflow

```python
# 1. Log learning event
learning_id = am.learning_manager.log_learning(
    source_agent="gatekeeper",
    event_type="campaign_rejection",
    learning_data={
        "reason": "tone_too_aggressive",
        "campaign_id": "camp_123",
        "tier": "tier1"
    }
)

# 2. Identify patterns
patterns = am.learning_manager.identify_patterns(
    event_type="campaign_rejection",
    min_occurrences=3
)

# 3. Apply learning
for pattern in patterns:
    if pattern['confidence'] > 0.8:
        am.learning_manager.apply_learning(
            learning_id=pattern['learning_id'],
            target_directive="directives/crafter.md"
        )

# 4. Suggest improvements
improvements = am.learning_manager.suggest_improvements(
    agent_id="crafter"
)
```

### Integration with Testing Framework

The Learning Manager integrates with your testing framework:

```python
# From TESTING_TRAINING_IMPROVEMENT_FRAMEWORK.md

# Phase 4: Continuous Improvement Loop
class SelfAnnealingEngine:
    def __init__(self, agent_manager):
        self.am = agent_manager
    
    def analyze_campaign_performance(self, campaign_id):
        # Get campaign metrics
        metrics = self.feedback_collector.analyze_campaign(campaign_id)
        
        # Extract insights
        if metrics["reply_rate"] > 10:
            # Log success pattern
            self.am.learning_manager.log_learning(
                source_agent="crafter",
                event_type="high_performance",
                learning_data={
                    "campaign_id": campaign_id,
                    "reply_rate": metrics["reply_rate"],
                    "pattern": "success"
                }
            )
```

---

## 🚀 5. Deployment Management

### Phased Deployment Strategy

Agent Manager supports gradual production rollout:

```python
class DeploymentManager:
    """Manages phased deployment to production"""
    
    def __init__(self, agent_manager):
        self.am = agent_manager
        self.deployment_phases = [
            {"name": "shadow", "traffic": 0, "duration": "3 days"},
            {"name": "canary", "traffic": 10, "duration": "2 days"},
            {"name": "partial", "traffic": 50, "duration": "2 days"},
            {"name": "full", "traffic": 100, "duration": "ongoing"}
        ]
    
    def deploy_phase(self, phase_name: str):
        """Deploy specific phase"""
        
        # Validate readiness
        validator = ProductionValidator(self.am)
        report = validator.validate_all()
        
        if report['overall_status'] != 'PRODUCTION_READY':
            raise Exception("System not ready for deployment")
        
        # Execute deployment
        phase = next(p for p in self.deployment_phases if p['name'] == phase_name)
        
        # Update agent configurations
        for agent in self.am.registry.list_agents():
            self._update_agent_traffic(agent.agent_id, phase['traffic'])
    
    def rollback(self):
        """Rollback to previous version"""
        
        # Restore previous state
        for agent in self.am.registry.list_agents():
            state = self.am.state_manager.restore_state(agent.agent_id)
            if state:
                self.am.state_manager.update_agent_state(
                    agent.agent_id,
                    AgentState(**state)
                )
```

### Deployment Checklist

**Pre-Deployment:**
- [ ] Run `python core/production_validator.py`
- [ ] Verify readiness score ≥ 90%
- [ ] Run `python core/test_orchestrator.py`
- [ ] Verify test success rate ≥ 95%
- [ ] Review `.hive-mind/PRODUCTION_VALIDATION_REPORT.md`
- [ ] Backup current state

**Deployment Phases:**

**Week 3: Shadow Mode (0% traffic)**
- Swarm runs in parallel with manual processes
- No production impact
- Collect comparison data

**Week 4: Canary (10% traffic)**
- Tier 3 leads only
- Monitor closely
- Ready to rollback

**Week 5: Partial (50% traffic)**
- Tier 2-3 leads
- Human review for Tier 1
- Performance validation

**Week 6+: Full (100% traffic)**
- All tiers automated
- Human spot-checks only
- Continuous monitoring

---

## 📋 Daily Operations Workflow

### Morning Routine (7:00 AM)

```powershell
# 1. Check system health
python core/production_validator.py

# 2. Review overnight activity
code .hive-mind/health_log.jsonl

# 3. Check KPI dashboard
python dashboard/kpi_dashboard.py --all

# 4. Review learnings
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.learning_manager.get_learnings(time_period='1d'))"
```

### Weekly Review (Monday)

```powershell
# 1. Run full test suite
python core/test_orchestrator.py

# 2. Validate production readiness
python core/production_validator.py

# 3. Review performance metrics
code .hive-mind/testing/TEST_REPORT.md
code .hive-mind/PRODUCTION_VALIDATION_REPORT.md

# 4. Apply learnings
python -c "from core.agent_manager import AgentManager; am = AgentManager(); patterns = am.learning_manager.identify_patterns(min_occurrences=3); print(patterns)"
```

### Monthly Optimization

```powershell
# 1. Comprehensive validation
python core/production_validator.py

# 2. Performance benchmarking
python core/test_orchestrator.py --mode comprehensive

# 3. Learning analysis
python -c "from core.agent_manager import AgentManager; am = AgentManager(); improvements = am.learning_manager.suggest_improvements(); print(improvements)"

# 4. Update directives
# Review and apply suggested improvements to directives/
```

---

## 🎯 Integration with Current Week 1 Progress

### Current Status (Day 1-2: 80% Complete)

**Completed:**
- ✅ GoHighLevel API integration
- ✅ LinkedIn cookie extraction
- ✅ Clay API setup
- ✅ Anthropic API setup
- ✅ Connection testing infrastructure

**Agent Manager Support:**

```python
# Validate API connections
from core.production_validator import ProductionValidator
from core.agent_manager import AgentManager

am = AgentManager()
validator = ProductionValidator(am)

# This checks your connection_test.json
report = validator.validate_all()

# Shows which APIs are connected
print(report['results'][1])  # API connections check
```

### Next Steps (Day 3-4: Framework Integration)

**To Complete:**
- [ ] Create `core/context_manager.py`
- [ ] Create `core/grounding_chain.py`
- [ ] Create `core/feedback_collector.py`
- [ ] Integrate into agents

**Agent Manager Support:**

```python
# Test framework integration
from core.test_orchestrator import TestOrchestrator

orchestrator = TestOrchestrator(am)

# This validates framework components exist
report = orchestrator.run_all_tests(test_mode="quick")

# Shows which components are integrated
print(report['summary'])
```

---

## 🔧 Ampcode Development Prompts

### Prompt 1: Complete Week 1 Day 3-4 with Agent Manager

```
Task: Complete Week 1 Day 3-4 Framework Integration with Agent Manager validation

Context:
I'm on Day 3-4 of Week 1 implementation. I need to create the core framework components and validate them using Agent Manager.

Requirements:
1. Create core/context_manager.py (per WEEK_1_DAY_3-4_FRAMEWORK.md)
2. Create core/grounding_chain.py (per WEEK_1_DAY_3-4_FRAMEWORK.md)
3. Create core/feedback_collector.py (per WEEK_1_DAY_3-4_FRAMEWORK.md)
4. Create tests for each component
5. Run validation using core/production_validator.py

Reference Files:
@.hive-mind/WEEK_1_DAY_3-4_FRAMEWORK.md
@core/production_validator.py
@core/test_orchestrator.py

Expected Output:
- All 3 framework components created
- Tests passing
- Production validation showing framework_integration: pass
```

### Prompt 2: Register All Agents with Agent Manager

```
Task: Discover and register all agents in both swarms

Context:
I have agents in execution/ (Alpha Swarm) and revenue_coordination/ (Revenue Swarm). I need to register them all with Agent Manager.

Requirements:
1. Scan execution/ for agent scripts
2. Scan revenue_coordination/ for agent scripts
3. Register each agent with capabilities
4. Create agent registry report

Use:
@core/agent_manager.py - AgentRegistry class
@execution/ - Alpha Swarm agents
@revenue_coordination/ - Revenue Swarm agents

Expected Output:
- .hive-mind/registry.json with all agents
- Agent capabilities documented
- Health check results for each agent
```

### Prompt 3: Create Production Deployment Plan

```
Task: Create production deployment plan using Agent Manager

Context:
I'm ready to move to production. I need a phased deployment plan coordinated by Agent Manager.

Requirements:
1. Create deployment_manager.py
2. Define deployment phases (shadow, canary, partial, full)
3. Create rollback procedures
4. Integrate with production_validator.py

Reference:
@core/agent_manager.py
@core/production_validator.py
@.hive-mind/TESTING_TRAINING_IMPROVEMENT_FRAMEWORK.md - Phase 3

Expected Output:
- core/deployment_manager.py
- Deployment runbook in docs/
- Rollback procedures documented
```

---

## 📊 Success Metrics

### Production Readiness Metrics

**Target for Production:**
- Readiness Score: ≥ 90%
- Test Success Rate: ≥ 95%
- Agent Health: 100%
- API Uptime: ≥ 99%
- Context Usage: < 70% (Smart Zone)

### Weekly Tracking

```json
{
  "week": 1,
  "readiness_score": 65,
  "test_success_rate": 85,
  "agent_health": 80,
  "api_uptime": 100,
  "blockers": [
    "Framework integration incomplete",
    "Workflows not tested"
  ]
}
```

---

## 🚨 Troubleshooting

### Common Issues

**Issue: Production validation fails**
```powershell
# Check specific validation
python core/production_validator.py

# Review report
code .hive-mind/PRODUCTION_VALIDATION_REPORT.md

# Fix issues and re-validate
```

**Issue: Tests failing**
```powershell
# Run tests with verbose output
python core/test_orchestrator.py

# Check test report
code .hive-mind/testing/TEST_REPORT.md

# Fix failing tests and re-run
```

**Issue: Agent not responding**
```powershell
# Check agent health
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.registry.agent_health_check('hunter'))"

# Restart agent
python -c "from core.agent_manager import AgentManager; am = AgentManager(); am.lifecycle.restart_agent('hunter')"
```

---

## 📚 Additional Resources

**Documentation:**
- `.hive-mind/TESTING_TRAINING_IMPROVEMENT_FRAMEWORK.md` - Testing strategy
- `.hive-mind/WEEK_1_IMPLEMENTATION_GUIDE.md` - Week 1 setup
- `docs/AGENT_MANAGER_INTEGRATION_GUIDE.md` - Agent Manager details
- `docs/AGENT_MANAGER_COMMANDS.md` - Command reference

**Scripts:**
- `core/agent_manager.py` - Core orchestration
- `core/production_validator.py` - Production validation
- `core/test_orchestrator.py` - Test coordination
- `execution/health_monitor.py` - Health monitoring
- `dashboard/kpi_dashboard.py` - KPI visualization

---

**Last Updated:** 2026-01-19  
**Version:** 1.0  
**Status:** Active Implementation
