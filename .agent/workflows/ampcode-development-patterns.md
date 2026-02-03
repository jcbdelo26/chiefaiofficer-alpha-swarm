---
description: Ampcode prompting patterns for systematic Beta Swarm development
---

# Ampcode Development Patterns

This workflow contains prompting instructions, meta-prompts, and coding patterns
to guide Ampcode sessions for consistent, high-quality development.

---

## 🎯 SESSION INITIALIZATION PROMPTS

### Start of Day Prompt
```
Read DAILY_PROMPT_CHEATSHEET.md and identify which day we're on. 
Show me:
1. What was completed yesterday
2. Today's specific tasks
3. Any dependencies or blockers
4. Estimated complexity (low/medium/high)

Then wait for my confirmation before starting implementation.
```

### Context Loading Prompt
```
Before implementing [FEATURE], analyze:
1. Check existing agents in execution/ for patterns to follow
2. Check existing tests in tests/ for testing patterns
3. Check .hive-mind/learnings.json for relevant learnings
4. Check mcp-servers/ for any MCP dependencies

Summarize what you found before proceeding.
```

---

## 🏗️ IMPLEMENTATION PROMPTS

### New Agent Creation
```
Create [AGENT_NAME] agent following the Beta Swarm pattern:

1. File: execution/[agent_name]_agent.py
2. Structure:
   - Docstring with architecture diagram
   - Dataclasses for state management
   - Manager classes for persistence
   - Main agent class
   - Demo/CLI function
3. Include:
   - Graceful MCP fallback (try/except imports)
   - Storage in .hive-mind/[agent_name]/
   - Logging with agent-specific logger
   - Type hints throughout
4. Tests: tests/test_[agent_name]_agent.py with 25+ tests

Follow patterns from scheduler_agent.py and communicator_agent.py.
```

### Enhancement to Existing Agent
```
Enhance [AGENT_NAME] with [FEATURE]:

1. First show me the current structure (view_file_outline)
2. Identify where to add new functionality
3. List all methods that need modification
4. Implement changes with minimal disruption to existing code
5. Add tests for new functionality only
6. Update docstrings to reflect changes
```

### MCP Server Integration
```
Integrate [MCP_NAME] into [AGENT_NAME]:

1. Check mcp-servers/[mcp-name]/server.py for available methods
2. Create graceful fallback if MCP unavailable
3. Add mock mode for testing without real API
4. Document which agent methods use this MCP
5. Add integration tests with mocked MCP
```

---

## 🧪 TESTING PROMPTS

### Test Suite Creation
```
Create comprehensive tests for [MODULE]:

1. Fixtures: reusable setup for common test scenarios
2. Unit tests: each public method
3. Integration tests: multi-step workflows
4. Edge cases: empty input, invalid data, errors
5. Async tests: use @pytest.mark.asyncio

Target: 80%+ code coverage, 25+ tests minimum.
```

### Test-Driven Fix
```
Test [FEATURE] is failing:

1. Show me the failing test output
2. Identify root cause (not symptoms)
3. Fix the issue minimally
4. Verify all related tests still pass
5. Add regression test if this was a gap
```

---

## 📊 QUALITY PROMPTS

### Code Review Prompt
```
Review [FILE] for:

1. Pattern consistency with other agents
2. Error handling completeness
3. Logging coverage (info, warning, error)
4. Type hint completeness
5. Docstring quality
6. Test coverage gaps

Provide specific improvement recommendations.
```

### Refactoring Prompt
```
Refactor [COMPONENT] to improve [ASPECT]:

1. First, show me current implementation
2. Explain what makes it suboptimal
3. Show proposed changes
4. List all files affected
5. Ensure backward compatibility
6. Update tests if needed
```

### Performance Audit
```
Analyze [AGENT] for performance issues:

1. Identify blocking I/O operations
2. Find unnecessary file reads/writes
3. Check for N+1 query patterns
4. Suggest caching opportunities
5. Recommend async optimizations
```

---

## 🔄 ITERATION PROMPTS

### Daily Completion
```
Mark Day [N] as complete:

1. Update DAILY_PROMPT_CHEATSHEET.md with completion details
2. Add learnings to .hive-mind/learnings.json
3. Summarize:
   - Files created/modified
   - Test count and pass rate
   - Key features implemented
   - Dependencies introduced
4. Show what's next (Day N+1)
```

### Progress Check
```
Show current Beta Swarm status:

1. Which days are complete (1-current)
2. Test coverage by component
3. Agent integration status (which agents talk to which)
4. MCP server usage status
5. Any technical debt accumulated
```

### Blocker Resolution
```
I'm blocked on [ISSUE]:

1. First, understand the exact error/blocker
2. Check if this pattern exists elsewhere in codebase
3. Search for similar issues in learnings.json
4. Propose 2-3 solution approaches
5. Implement the safest option
6. Document the fix for future reference
```

---

## 📁 FILE ORGANIZATION PATTERNS

### Storage Pattern
```
All persistent data goes to .hive-mind/:

.hive-mind/
├── [agent_name]/           # Per-agent storage
│   ├── state/             # Runtime state
│   ├── cache/             # Cached data with TTL
│   ├── queue/             # Task queue (inter-agent)
│   └── patterns/          # Learned patterns
├── threads/               # Email thread cache
├── outbox/                # Pending notifications
└── learnings.json         # System-wide learnings
```

### Inter-Agent Communication
```
Agents communicate via task queues:

1. Producer writes to: .hive-mind/[target_agent]/queue/task_[id].json
2. Consumer polls: queue directory for .json files
3. After processing: move to processed/ or error/
4. Schema: {task_id, source_agent, payload, created_at, status}
```

---

## 🛡️ GUARDRAIL PATTERNS

### Input Validation
```
Every public method should:

1. Validate required parameters are not None
2. Validate types match expected
3. Sanitize string inputs (strip, length limit)
4. Log validation failures at warning level
5. Return typed error response, not exceptions
```

### Error Handling
```
Standard error handling pattern:

try:
    result = await risky_operation()
    return {"success": True, "data": result}
except SpecificError as e:
    logger.error(f"Operation failed: {e}")
    return {"success": False, "error": str(e), "error_type": "specific"}
except Exception as e:
    logger.exception("Unexpected error")
    return {"success": False, "error": "Internal error", "error_type": "unknown"}
```

### Rate Limiting
```
For external API calls:

1. Track calls per minute/hour
2. Implement exponential backoff on 429
3. Log rate limit hits
4. Queue excess requests for later
5. Surface rate limit status in metrics
```

---

## 🎨 PROMPT TEMPLATES BY TASK TYPE

### Quick Fix (5-10 min)
```
Fix [specific bug] in [file]:
- Here's the error: [paste error]
- Expected behavior: [description]
- Make minimal changes to fix.
```

### Medium Task (30-60 min)
```
Implement [feature] for [agent]:

Requirements:
- [Requirement 1]
- [Requirement 2]

Constraints:
- Must be backward compatible
- Must have tests
- Follow existing patterns
```

### Major Feature (2+ hours)
```
Day [N]: [Feature Name]

Follow the task from DAILY_PROMPT_CHEATSHEET.md:
[Paste the day's requirements]

Implementation plan:
1. Create/modify files (list them)
2. Add tests
3. Update documentation
4. Mark day complete

Start with step 1, show progress after each step.
```

---

## 🔍 DEBUGGING PROMPTS

### Test Failure
```
These tests are failing: [test names]
Output: [paste test output]

1. Analyze failure reason
2. Check if it's test issue or code issue
3. Fix root cause
4. Verify fix doesn't break other tests
```

### Import Error
```
Getting import error for [module]:
[paste error]

1. Check if module exists
2. Check if dependencies installed
3. Check sys.path includes project root
4. Fix the import chain
```

### Runtime Error
```
Agent [name] crashes when [action]:
[paste traceback]

1. Identify the failing line
2. Check input data that caused failure
3. Add defensive check
4. Add test case for this scenario
```

---

## 📈 CONTINUOUS IMPROVEMENT

### After Each Session
```
Before ending this session:

1. Summarize what was accomplished
2. List any technical debt introduced
3. Note any learnings for hive-mind
4. Identify what should be done next session
5. Update any relevant documentation
```

### Weekly Review Prompt
```
Weekly Beta Swarm review:

1. Days completed this week
2. Total test count and coverage
3. Agent capabilities matrix
4. Integration gaps
5. Recommended priorities for next week
```

---

## 🚀 META PROMPTS

### When Starting Fresh
```
I'm continuing Beta Swarm development. 

1. Read DAILY_PROMPT_CHEATSHEET.md to understand current state
2. Read last 3 entries in .hive-mind/learnings.json
3. Check tests/test_*.py for overall test health
4. Summarize what's done and what's next
```

### When Stuck
```
I've been trying [approach] but it's not working.

Don't just try harder. Instead:
1. Step back and understand the actual goal
2. Look at how similar features work elsewhere
3. Consider if we're overcomplicating this
4. Propose a simpler alternative approach
```

### When Feature Creeping
```
Stop. Before adding more features:

1. Is this in the day's requirements?
2. Is this blocking something else?
3. Can this wait until a later day?
4. What's the minimal viable implementation?

Focus on completing the day's scope first.
```

---

## 📋 QUICK REFERENCE COMMANDS

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_[agent]_agent.py -v

# Run with coverage
python -m pytest tests/ --cov=execution --cov-report=html

# Demo an agent
python execution/[agent]_agent.py --demo

# Check agent metrics
python execution/[agent]_agent.py --metrics
```

---

## 💡 KEY REMINDERS

1. **Always check existing patterns first** - Don't reinvent
2. **Minimal changes** - Don't refactor unnecessarily
3. **Tests are mandatory** - No feature without tests
4. **Document learnings** - Update hive-mind
5. **Stay in scope** - Complete the day's task fully before extras
6. **Graceful degradation** - Always have fallback for external deps
7. **Log meaningfully** - Future you will thank present you
