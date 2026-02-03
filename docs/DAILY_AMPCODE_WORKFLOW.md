# 📅 Daily Ampcode Workflow for Production Readiness

**Goal**: Complete Agent Manager implementation and achieve production readiness in 14 days

**Your Assets**:
- ✅ Unified Agent Registry (implemented)
- ✅ Production Checklist (created)
- ✅ Production Validator (created)
- ✅ Implementation Roadmap
- ✅ Ampcode Prompts (ready to use)

**Method**: One focused task per day, using Ampcode prompts from `AMPCODE_PROMPTS_AGENT_MANAGER.md`

---

## 📊 Week 1: Core Implementation

### **Day 1 (Today) - Agent Discovery**

**Goal**: Complete agent discovery functionality

**Ampcode Commands**:
```
@AMPCODE_PROMPTS_AGENT_MANAGER.md

Use Prompt 1 to implement the discover_agents() method in @core/agent_manager.py

Requirements:
- Scan execution/ and revenue_coordination/ directories
- Extract agent metadata from docstrings
- Auto-register discovered agents
- Return list of agent IDs

Test after completion:
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.registry.discover_agents('./execution'))"
```

**Validation**:
```bash
# Should discover all 11 agents
python execution/production_checklist.py
```

**Expected Output**:
- ✅ `discover_agents()` function complete
- ✅ Auto-discovers 11 agents from both swarms
- ✅ Test passes

**Time Estimate**: 2 hours

---

### **Day 2 - Health Checks**

**Goal**: Implement comprehensive agent health checking

**Ampcode Commands**:
```
@AMPCODE_PROMPTS_AGENT_MANAGER.md

Use Prompt 2 to implement agent_health_check() in @core/agent_manager.py

Requirements:
- Check if agent is registered
- Verify MCP server connectivity (if applicable)
- Test agent dependencies
- Return detailed health status with MCP server details

Include timeout handling (5 seconds max) and detailed error messages.
```

**Validation**:
```bash
# Test health check
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.registry.agent_health_check('hunter'))"

# Run full checklist
python execution/production_checklist.py --verbose
```

**Expected Output**:
- ✅ Health check returns MCP server status
- ✅ Dependency validation works
- ✅ Timeout handling implemented

**Time Estimate**: 2 hours

---

### **Day 3 - Context Monitoring (FIC)**

**Goal**: Implement Frequent Intentional Compaction to keep agents in "smart zone"

**Ampcode Commands**:
```
@AMPCODE_PROMPTS_AGENT_MANAGER.md

Use Prompt 3 to implement monitor_context_usage() in @core/agent_manager.py

This is critical for preventing agent degradation in production.

Requirements:
- Track context window usage per agent
- Calculate smart zone (<40%), warning (40-70%), dumb (>70%)
- Recommend compaction strategies (RPI, semantic anchor, checkpoint)
- Store history in .hive-mind/context_history/

Return context percentage, zone, and recommendation.
```

**Validation**:
```bash
# Test context monitoring
python -c "from core.agent_manager import AgentManager; am = AgentManager(); print(am.context_manager.monitor_context_usage('crafter'))"
```

**Expected Output**:
- ✅ Context usage tracking active
- ✅ Zone detection working (smart/warning/dumb)
- ✅ Compaction recommendations generated

**Time Estimate**: 3 hours

---

### **Day 4 - Workflow System (Part 1)**

**Goal**: Implement workflow creation and execution

**Ampcode Commands**:
```
@AMPCODE_PROMPTS_AGENT_MANAGER.md

Use Prompt 4 to implement create_workflow() and execute_workflow() in @core/agent_manager.py

Requirements:
- create_workflow(): Validate agents, check dependencies, save to .hive-mind/workflows/
- execute_workflow(): Load definition, initialize agents, execute steps, handle errors
- Support retry (up to 3 times per step)
- Track progress and allow resume from last successful step

Use the workflow definition format from the prompt.
```

**Validation**:
```bash
# Test workflow creation
python -c "
from core.agent_manager import AgentManager
am = AgentManager()
wf_id = am.create_workflow('test_workflow', [
    {'agent': 'hunter', 'action': 'scrape', 'inputs': ['url'], 'outputs': ['leads']}
])
print(f'Created workflow: {wf_id}')
"
```

**Expected Output**:
- ✅ Workflows saved to `.hive-mind/workflows/`
- ✅ Step execution with handoffs works
- ✅ Error retry logic implemented

**Time Estimate**: 4 hours

---

### **Day 5 - Pattern Detection**

**Goal**: Implement learning pattern identification for self-annealing

**Ampcode Commands**:
```
@AMPCODE_PROMPTS_AGENT_MANAGER.md

Use Prompt 5 to implement identify_patterns() in @core/agent_manager.py

This enables the swarm to learn from rejections and failures.

Requirements:
- Group learnings by similarity (fuzzy matching)
- Find patterns occurring >= min_occurrences times
- Suggest systematic fixes
- Calculate confidence scores
- Return patterns sorted by confidence

Example patterns: "tier1_leads_reject_price_mentions", "competitor_comparisons_fail"
```

**Validation**:
```bash
# Test pattern detection
python -c "
from core.agent_manager import AgentManager
am = AgentManager()
patterns = am.learning_manager.identify_patterns(event_type='campaign_rejection', min_occurrences=3)
print(f'Found {len(patterns)} patterns')
for p in patterns:
    print(f'  - {p[\"pattern\"]}: {p[\"confidence\"]*100:.1f}% confidence')
"
```

**Expected Output**:
- ✅ Pattern clustering works
- ✅ Confidence calculation correct
- ✅ Directive update suggestions generated

**Time Estimate**: 3 hours

---

### **Day 6 - MCP Server Creation**

**Goal**: Expose Agent Manager via MCP for AI agent access

**Ampcode Commands**:
```
@AMPCODE_PROMPTS_AGENT_MANAGER.md

Use Prompt 6 to create the Agent Manager MCP Server

Requirements:
- Create mcp-servers/agent-manager-mcp/server.py
- Implement 11 MCP tools (register_agent, initialize_agent, create_handoff, etc.)
- Create README.md with integration examples
- Add __init__.py for package structure

This allows Claude and other AI agents to orchestrate the swarm.
```

**Validation**:
```bash
# Test MCP server
cd mcp-servers/agent-manager-mcp
python server.py &

# In another terminal, test a tool
# (This would be via MCP client in production)
```

**Expected Output**:
- ✅ MCP server running
- ✅ All 11 tools implemented
- ✅ README documentation complete

**Time Estimate**: 3 hours

---

### **Day 7 - Testing & Week 1 Validation**

**Goal**: Comprehensive test suite and Week 1 validation

**Ampcode Commands**:
```
@AMPCODE_PROMPTS_AGENT_MANAGER.md

Use Prompt 7 to create tests/test_agent_manager.py

Requirements:
- Test all 6 manager classes (Registry, Lifecycle, State, Handoff, Context, Learning)
- >80% code coverage
- Use pytest fixtures for temp .hive-mind
- Mock external dependencies (MCP servers, file I/O)

Create comprehensive tests for:
- Agent registration and discovery
- Health checks
- Workflow creation and execution
- Context monitoring
- Learning pattern detection
```

**Validation**:
```bash
# Run test suite
pytest tests/test_agent_manager.py -v --cov=core.agent_manager

# Run production checklist
python execution/production_checklist.py --verbose

# Should show significant progress
```

**Expected Output**:
- ✅ 40+ tests passing
- ✅ >80% code coverage
- ✅ Production checklist score >70%

**Time Estimate**: 4 hours

**🎉 Week 1 Complete! Core Agent Manager implemented.**

---

## 📊 Week 2: Production Workflows & Deployment

### **Day 8 - Unified Workflows**

**Goal**: Create production-ready cross-swarm workflows

**Ampcode Commands**:
```
@AMPCODE_PROMPTS_AGENT_MANAGER.md

Use Prompt 8 to create execution/unified_workflows.py

Implement these 4 workflows:
1. lead_to_campaign_workflow - LinkedIn → Campaign (uses 9 agents)
2. real_time_engagement_workflow - PIPER → SCOUT → OPERATOR
3. document_enrichment_workflow - Parser → Enricher → Segmentor
4. self_annealing_workflow - Learn from failures

Each workflow should:
- Use Agent Manager for orchestration
- Include error handling
- Support resume from failures
- Log progress
- Have CLI interface
```

**Validation**:
```bash
# Test in sandbox mode (no real API calls)
python execution/unified_workflows.py lead_to_campaign --mode sandbox --input test_url

# Test in staging mode (real APIs, no sends)
python execution/unified_workflows.py lead_to_campaign --mode staging --input "https://linkedin.com/in/example"
```

**Expected Output**:
- ✅ All 4 workflows executable
- ✅ Cross-swarm handoffs working
- ✅ Error recovery functional

**Time Estimate**: 6 hours

---

### **Day 9 - Agent Manager Dashboard**

**Goal**: Web dashboard for real-time monitoring

**Ampcode Commands**:
```
@AMPCODE_PROMPTS_AGENT_MANAGER.md

Use Prompt 9 to create dashboard/agent_manager_dashboard.py

Requirements:
- Flask web app with 5 pages (Home, Agents, Workflows, Learnings, Health)
- Real-time updates via polling (every 2 seconds)
- Charts with Chart.js for analytics
- Dark mode, glassmorphism design
- Premium aesthetics (not MVP!)

API endpoints:
- GET /api/agents - List all agents
- GET /api/agents/<id>/state - Agent state
- POST /api/agents/<id>/start - Start agent
- POST /api/workflows/<id>/execute - Execute workflow
- GET /api/health - System health
```

**Validation**:
```bash
# Start dashboard
python dashboard/agent_manager_dashboard.py

# Open browser to http://localhost:5000
# Should see all agents, workflows, and health status
```

**Expected Output**:
- ✅ Dashboard running on port 5000
- ✅ Real-time agent status visible
- ✅ Workflow execution monitoring works

**Time Estimate**: 6 hours

---

### **Day 10 - Development Utilities**

**Goal**: Accelerate future development with code generation tools

**Ampcode Commands**:
```
@AMPCODE_PROMPTS_AGENT_MANAGER.md

Use Prompt 10 to create execution/agent_dev_utils.py

Implement these utilities:
1. Code Generation: generate_agent_wrapper(), generate_mcp_tools(), generate_handoff_validator()
2. Testing: create_test_fixtures(), simulate_workflow(), replay_handoff()
3. Documentation: generate_agent_docs(), generate_mermaid_diagrams(), generate_changelog()
4. Debugging: trace_workflow(), analyze_failure(), export_debug_bundle()

Each should have CLI interface and comprehensive docstrings.
```

**Validation**:
```bash
# Test agent wrapper generation
python execution/agent_dev_utils.py generate-agent --id test_agent --type enrichment

# Test documentation generation
python execution/agent_dev_utils.py generate-docs --agent hunter

# Test diagram generation
python execution/agent_dev_utils.py generate-diagram --scope workflow
```

**Expected Output**:
- ✅ Code generation tools working
- ✅ Documentation auto-generation functional
- ✅ Debugging tools available

**Time Estimate**: 5 hours

---

### **Day 11 - Docker Deployment Setup**

**Goal**: Containerize the swarm for production deployment

**Ampcode Commands**:
```
Create Docker deployment configuration for production.

Requirements:
1. Create Dockerfiles:
   - alpha-swarm.Dockerfile (HUNTER, ENRICHER, SEGMENTOR, CRAFTER, GATEKEEPER)
   - revenue-swarm.Dockerfile (QUEEN, SCOUT, OPERATOR, PIPER, COACH)
   - agent-manager.Dockerfile (orchestration layer)
   
2. Create docker-compose.yml:
   - All MCP servers as services
   - Shared volume for .hive-mind
   - Environment variable injection from .env
   - Health checks using Agent Manager health_check()
   - Restart policies (unless-stopped)
   - Network isolation for security
   
3. Create .dockerignore to exclude .hive-mind, .env, __pycache__

Reference: @docs/IMPLEMENTATION_ROADMAP.md Scale Phase 1

Base image: python:3.11-slim
Include: requirements.txt installation
Expose: ports 5000 (dashboard), MCP server ports
```

**Validation**:
```bash
# Build images
docker-compose build

# Test locally
docker-compose up -d

# Check health
docker-compose ps
curl http://localhost:5000/api/health
```

**Expected Output**:
- ✅ All services build successfully
- ✅ Containers start and stay healthy
- ✅ Inter-container communication works

**Time Estimate**: 4 hours

---

### **Day 12 - CI/CD Pipeline**

**Goal**: Automated testing and deployment

**Ampcode Commands**:
```
Create GitHub Actions workflow for CI/CD.

Requirements:
Create .github/workflows/production-deploy.yml:

1. On push to main:
   - Run production_checklist.py
   - Run validate_production_readiness.py
   - Run pytest (all tests)
   - Build Docker images
   - Push to container registry (optional)

2. On tag (v*.*.*):
   - All above steps
   - Deploy to staging
   - Run integration tests via Agent Manager
   - Health check all agents
   - Deploy to production (if all pass)
   - Rollback on failure

Include environment secrets for:
- SUPABASE_URL, SUPABASE_KEY
- GHL_API_KEY, CLAY_API_KEY, INSTANTLY_API_KEY
- ANTHROPIC_API_KEY

Reference: @docs/IMPLEMENTATION_ROADMAP.md Scale Phase 2
```

**Validation**:
```bash
# Test workflow locally with act (GitHub Actions locally)
act -j test

# Or push to GitHub and check Actions tab
git add .github/workflows/production-deploy.yml
git commit -m "Add CI/CD pipeline"
git push
```

**Expected Output**:
- ✅ Workflow runs on push
- ✅ All tests pass in CI
- ✅ Deployment process defined

**Time Estimate**: 3 hours

---

### **Day 13 - Production Hardening**

**Goal**: Circuit breakers, retry logic, and monitoring

**Ampcode Commands**:
```
Harden the system for production.

Task 1: Add circuit breakers to API calls

Requirements:
- Add circuit breaker pattern to:
  * execution/hunter_scrape_followers.py (LinkedIn API)
  * execution/enricher_clay_waterfall.py (Clay API)
  * mcp-servers/ghl-mcp/server.py (GHL API)

Circuit breaker logic:
- Open circuit after 3 consecutive failures
- Half-open after 60 seconds
- Log all state transitions to .hive-mind/logs/circuit_breaker.log

Reference: @docs/IMPLEMENTATION_ROADMAP.md Day 6-7

---

Task 2: Ensure all API calls have retry with exponential backoff

Requirements:
- All API calls in execution/*.py should have:
  * Retry with exponential backoff (1s, 2s, 4s, 8s, max 30s)
  * Max 5 retries
  * Specific exception handling for rate limits vs errors
  * Log each retry attempt

Use Python's tenacity library or implement custom retry decorator.
```

**Validation**:
```bash
# Test circuit breaker
python -c "
from execution.hunter_scrape_followers import test_circuit_breaker
test_circuit_breaker()
"

# Run production validator
python execution/validate_production_readiness.py --mode production
```

**Expected Output**:
- ✅ Circuit breakers on all external APIs
- ✅ Retry logic with exponential backoff
- ✅ Increased resilience to failures

**Time Estimate**: 5 hours

---

### **Day 14 - Final Validation & Launch Prep**

**Goal**: Complete validation and prepare for production

**Morning Task - Final Validation**:
```bash
# Run complete validation suite
python execution/validate_production_readiness.py --mode production --verbose

# Run production checklist
python execution/production_checklist.py --verbose --export json

# Run all tests
pytest tests/ -v --cov

# Check Agent Manager dashboard
python dashboard/agent_manager_dashboard.py &
# Open http://localhost:5000 and verify all agents healthy
```

**Afternoon Task - Documentation & Handoff**:

**Ampcode Commands**:
```
Create production deployment documentation.

Requirements:
Create docs/PRODUCTION_DEPLOYMENT_GUIDE.md:

Include:
1. Prerequisites checklist
2. Environment setup instructions
3. Database migration steps (Supabase schema)
4. Docker deployment commands
5. Health check procedures
6. Monitoring setup (dashboard, alerts)
7. Rollback procedures
8. Troubleshooting common issues
9. Contact information for support

Also create docs/RUNBOOK.md:
- Daily operations procedures
- How to add new agents
- How to create new workflows
- Emergency response procedures
- Performance tuning guide
```

**Final Checklist**:
```bash
# Should all pass:
✅ Production readiness score: 95%+
✅ All blocking issues resolved
✅ Docker containers building and running
✅ Agent Manager dashboard accessible
✅ All 4 unified workflows working
✅ Tests passing (>80% coverage)
✅ Documentation complete
✅ CI/CD pipeline functional
```

**Expected Output**:
- ✅ Production-ready system
- ✅ Complete documentation
- ✅ Deployment plan ready

**Time Estimate**: 6 hours

**🎉 Week 2 Complete! Production ready!**

---

## 📈 Progress Tracking

Use this table to track your daily progress:

| Day | Date | Task | Status | Blockers | Score |
|-----|------|------|--------|----------|-------|
| 1 | ___ | Agent Discovery | ⬜ | | |
| 2 | ___ | Health Checks | ⬜ | | |
| 3 | ___ | Context Monitoring | ⬜ | | |
| 4 | ___ | Workflow System | ⬜ | | |
| 5 | ___ | Pattern Detection | ⬜ | | |
| 6 | ___ | MCP Server | ⬜ | | |
| 7 | ___ | Testing | ⬜ | | 70%+ |
| 8 | ___ | Unified Workflows | ⬜ | | |
| 9 | ___ | Dashboard | ⬜ | | |
| 10 | ___ | Dev Utilities | ⬜ | | |
| 11 | ___ | Docker Setup | ⬜ | | |
| 12 | ___ | CI/CD Pipeline | ⬜ | | |
| 13 | ___ | Hardening | ⬜ | | |
| 14 | ___ | Final Validation | ⬜ | | 95%+ |

**Status Key**: ⬜ Not Started | 🔵 In Progress | ✅ Complete | ⚠️ Blocked

---

## 🚨 Daily Standup Template

Use this at the start of each day:

```
📅 Day [X] Standup
==================

✅ Yesterday:
- [What you completed]
- [What worked well]

🎯 Today:
- [Task from daily workflow]
- [Expected outcome]

🚧 Blockers:
- [Any blockers]
- [Help needed]

📊 Current Score:
- Production Readiness: [X]%
- Tests Passing: [X]/[Y]
- Agents Functional: [X]/11
```

---

## 💡 Pro Tips

### **For Ampcode Efficiency**:
1. Always reference files with `@` syntax: `@core/agent_manager.py`
2. Copy prompts exactly from `AMPCODE_PROMPTS_AGENT_MANAGER.md`
3. Test immediately after each implementation
4. Run `production_checklist.py` daily to track progress

### **For Debugging**:
1. Check `.hive-mind/logs/` for detailed logs
2. Use `--verbose` flag on validation scripts
3. Test in sandbox mode first, then staging, then production
4. Use Agent Manager dashboard for real-time monitoring

### **For Staying Motivated**:
1. Celebrate each day's completion ✅
2. Track your production readiness score improving
3. Remember: 14 days to a production-ready AI swarm!
4. You're building something revolutionary 🚀

---

## 🆘 If You Get Stuck

**Stuck on Day X?**

1. Re-read the prompt from `AMPCODE_PROMPTS_AGENT_MANAGER.md`
2. Run validation to identify specific issue:
   ```bash
   python execution/production_checklist.py --verbose
   ```
3. Check reference files mentioned in the prompt
4. Review existing implementations in `execution/` for patterns
5. Ask Ampcode: "I'm stuck on [specific issue]. Here's my current code: @file. What's wrong?"

**Behind Schedule?**

- Days 1-7 are critical (Agent Manager core)
- Days 8-10 can be parallelized if needed
- Days 11-12 (Docker/CI) can be deferred for MVP
- Day 14 is flexible buffer time

---

**Start NOW**: Begin Day 1 (Agent Discovery) immediately! Every function you complete brings you closer to a production-ready revenue swarm.

Good luck! 🚀
