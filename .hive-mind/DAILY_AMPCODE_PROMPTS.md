# 🚀 Daily Ampcode Prompts - 7-Day Production Sprint
**Chief AI Officer Alpha Swarm - Accelerated Production Readiness**

**Goal:** Production-ready in 7 days (compressed from 4 weeks)  
**Method:** Daily focused prompts for Ampcode to execute

---

## 📋 How to Use This Guide

**Each Day:**
1. Copy the day's prompt
2. Paste into Ampcode
3. Let Ampcode execute all tasks
4. Review results at end of day
5. Move to next day

**Important:** Each prompt is self-contained and actionable. Ampcode will handle all implementation.

---

## 🎯 DAY 1: Environment Setup & API Validation
**Date:** [Insert Date]  
**Focus:** Get all infrastructure working  
**Time:** 2-3 hours

### **Ampcode Prompt for Day 1:**

```
TASK: Day 1 - Environment Setup & API Validation for chiefaiofficer-alpha-swarm

OBJECTIVE: Set up testing environment and validate all API connections are working.

ACTIONS:
1. Create testing directories:
   - .hive-mind/testing/
   - .hive-mind/testing/sandbox-leads/
   - .hive-mind/testing/test-results/
   - .hive-mind/knowledge/
   - .hive-mind/knowledge/customers/
   - .hive-mind/knowledge/messaging/

2. Run API connection tests:
   - Execute: python execution/test_connections.py
   - Review .hive-mind/connection_test.json
   - Document any failures

3. Fix critical API issues:
   - If LinkedIn cookie expired: Guide me to refresh it
   - If any API key invalid: Guide me to update it
   - Priority: Supabase, GoHighLevel, Clay, Anthropic

4. Create test lead data file (.hive-mind/testing/test-leads.json) with 5 test leads using my email variants (chris+test1@chiefaiofficer.com, etc.)

5. Generate Day 1 completion report:
   - API Status: Which are working/failing
   - Blockers: What needs my attention
   - Next Steps: What's ready for Day 2

SUCCESS CRITERIA:
- ✅ All directories created
- ✅ API test run completed
- ✅ At least 4/6 APIs working (Supabase, GHL, Clay, Anthropic minimum)
- ✅ Test data file created
- ✅ Clear report of status

DELIVERABLE: Save completion report to .hive-mind/testing/day1_report.md
```

---

## 🎯 DAY 2: Business Context Training
**Date:** [Insert Date]  
**Focus:** Train agents on ChiefAIOfficer.com business  
**Time:** 2-3 hours

### **Ampcode Prompt for Day 2:**

```
TASK: Day 2 - Business Context Training for chiefaiofficer-alpha-swarm

OBJECTIVE: Document business context and train agents on ICP, messaging, and value props.

CONTEXT: ChiefAIOfficer.com helps B2B companies (51-500 employees, $5M-$100M revenue) automate revenue operations using AI agents. Target roles: VP Sales, CRO, RevOps Directors.

ACTIONS:
1. Create ICP document (.hive-mind/knowledge/customers/icp.json):
   - Tier 1: 100-500 employees, $20M-$100M, B2B SaaS/Tech, strong buying signals
   - Tier 2: 51-100 employees, $5M-$20M, Professional Services/B2B
   - Tier 3: 20-50 employees, $1M-$5M, Startups/SMB
   - Include: company_size, revenue, industry, pain_points, buying_signals, messaging_focus

2. Create messaging templates (.hive-mind/knowledge/messaging/templates.json):
   - Template 1: Pain point discovery (subject + body)
   - Template 2: Value proposition (subject + body)
   - Use variables: {first_name}, {company}, {title}, {pain_point}, {industry}
   - Tone: Professional, conversational, helpful (not salesy)

3. Create company profile (.hive-mind/knowledge/company/profile.md):
   - Mission: Automate B2B revenue operations with AI
   - Value Prop: AI-powered agents for lead gen, enrichment, outreach
   - Competitive Advantage: Self-improving, integrated, cost-effective
   - Target Pain Points: Manual RevOps, poor data quality, inefficient lead gen

4. Create agent training script (.hive-mind/knowledge/train_agents.py):
   - Function: train_crafter_agent() - loads ICP, templates, company profile
   - Function: train_segmentor_agent() - loads ICP criteria
   - Save trained contexts to .hive-mind/knowledge/

5. Test that training worked:
   - Run: python .hive-mind/knowledge/train_agents.py
   - Verify: Agent contexts saved successfully
   - Document: What agents now "know" about the business

SUCCESS CRITERIA:
- ✅ ICP document complete with 3 tiers
- ✅ Messaging templates created (2+ templates)
- ✅ Company profile documented
- ✅ Agent training script working
- ✅ Agents successfully trained

DELIVERABLE: Save completion report to .hive-mind/testing/day2_report.md
```

---

## 🎯 DAY 3: Component Testing
**Date:** [Insert Date]  
**Focus:** Test each agent individually  
**Time:** 3-4 hours

### **Ampcode Prompt for Day 3:**

```
TASK: Day 3 - Component Testing for chiefaiofficer-alpha-swarm

OBJECTIVE: Test each agent (ENRICHER, SEGMENTOR, CRAFTER, GATEKEEPER) individually with test data.

ACTIONS:
1. Test ENRICHER Agent:
   - Input: .hive-mind/testing/test-leads.json
   - Run: python execution/enricher_clay_waterfall.py --input .hive-mind/testing/test-leads.json --test-mode
   - Expected: Enriched data with company info, contact details
   - Verify: Success rate >80%, API costs tracked
   - Document: Results in .hive-mind/testing/enricher_test_results.json

2. Test SEGMENTOR Agent:
   - Input: Enriched leads from step 1
   - Run: python execution/segmentor_classify.py --input enriched_leads.json --test-mode
   - Expected: Leads classified into Tier 1/2/3
   - Verify: Segmentation matches ICP criteria, scoring applied
   - Document: Results in .hive-mind/testing/segmentor_test_results.json

3. Test CRAFTER Agent (GHL version):
   - Input: Segmented leads from step 2
   - Run: python execution/crafter_campaign_ghl.py --test-mode
   - Expected: Personalized email campaigns generated
   - Verify: >90% personalization, no hallucinations, professional tone
   - Document: Sample campaigns in .hive-mind/testing/sample_campaigns.json

4. Test GATEKEEPER Agent:
   - Input: Generated campaigns from step 3
   - Run: python execution/gatekeeper_review.py --campaign-id "test-campaign-001" --test-mode
   - Expected: Campaign queued for review
   - Verify: Review dashboard accessible, approval workflow works
   - Document: Results in .hive-mind/testing/gatekeeper_test_results.json

5. Quality Assurance Check:
   - Review all test outputs
   - Check for errors, hallucinations, poor quality
   - Calculate success rates for each agent
   - Identify any issues that need fixing

SUCCESS CRITERIA:
- ✅ ENRICHER: >80% success rate
- ✅ SEGMENTOR: >85% accuracy
- ✅ CRAFTER: >90% personalization, 0 hallucinations
- ✅ GATEKEEPER: Workflow functional
- ✅ All test results documented

DELIVERABLE: Save completion report to .hive-mind/testing/day3_report.md with success rates and issues found
```

---

## 🎯 DAY 4: End-to-End Workflow Testing
**Date:** [Insert Date]  
**Focus:** Test complete workflows from start to finish  
**Time:** 3-4 hours

### **Ampcode Prompt for Day 4:**

```
TASK: Day 4 - End-to-End Workflow Testing for chiefaiofficer-alpha-swarm

OBJECTIVE: Test complete workflows (Lead Harvesting + Campaign Creation) from start to finish.

ACTIONS:
1. Create workflow orchestration script (execution/run_workflow.py):
   - Workflow 1: lead-harvesting (scrape → normalize → enrich → segment → store)
   - Workflow 2: campaign-creation (select segment → generate → review → send)
   - Include: Error handling, logging, progress tracking
   - Test mode: Uses test data, doesn't send real emails

2. Test Lead Harvesting Workflow:
   - Input: Test LinkedIn profile URL or test lead data
   - Run: python execution/run_workflow.py --workflow lead-harvesting --test-mode
   - Expected Flow:
     * Step 1: Data normalized ✓
     * Step 2: Enriched with Clay ✓
     * Step 3: Segmented into tiers ✓
     * Step 4: Stored in Supabase ✓
     * Step 5: Contact created in GHL ✓
   - Verify: Each step completes, data flows correctly
   - Document: End-to-end success rate, time taken, costs

3. Test Campaign Creation Workflow:
   - Input: Segmented leads from step 2
   - Run: python execution/run_workflow.py --workflow campaign-creation --test-mode
   - Expected Flow:
     * Step 1: Segment selected (Tier 3 for testing) ✓
     * Step 2: Campaigns generated (personalized) ✓
     * Step 3: Queued for GATEKEEPER review ✓
     * Step 4: (Test mode: doesn't actually send) ✓
   - Verify: Campaigns are high quality, approval gate works
   - Document: Campaign quality scores, personalization metrics

4. Integration Testing:
   - Test data flow between agents
   - Verify no data loss or corruption
   - Check error handling (what happens if API fails?)
   - Test rollback/recovery mechanisms

5. Performance Benchmarking:
   - Measure: Time per lead (target: <2 min end-to-end)
   - Measure: Cost per lead (target: <$5)
   - Measure: Success rate (target: >80%)
   - Compare: Manual vs automated (speed, quality, cost)

SUCCESS CRITERIA:
- ✅ Both workflows execute successfully
- ✅ End-to-end success rate >80%
- ✅ No data corruption or loss
- ✅ Error handling works
- ✅ Performance meets targets

DELIVERABLE: Save completion report to .hive-mind/testing/day4_report.md with workflow diagrams and metrics
```

---

## 🎯 DAY 5: Production Configuration & Safety Gates
**Date:** [Insert Date]  
**Focus:** Configure for production, implement safety checks  
**Time:** 3-4 hours

### **Ampcode Prompt for Day 5:**

```
TASK: Day 5 - Production Configuration & Safety Gates for chiefaiofficer-alpha-swarm

OBJECTIVE: Configure system for production use and implement safety/quality gates.

ACTIONS:
1. Implement Quality Gates (.hive-mind/safety/quality_gates.py):
   - check_campaign_quality(): Verify personalization >90%, no hallucinations, professional tone
   - check_lead_quality(): Verify required fields, valid email, company size >20
   - check_compliance(): CAN-SPAM, GDPR, unsubscribe link present
   - Return: Pass/Fail with specific reasons

2. Create Pre-Send Checklist (execution/pre_send_checklist.py):
   - Quality checks: Personalization, hallucinations, tone, CTA
   - Compliance checks: CAN-SPAM, GDPR, opt-out mechanism
   - Targeting checks: ICP match, no duplicates, no unsubscribed
   - Technical checks: Email deliverability, links working, tracking enabled
   - Approval checks: AE reviewed (Tier 1), auto-approved (Tier 2-3)

3. Implement Emergency Stop (execution/emergency_stop.py):
   - Function: Immediately pause all active campaigns
   - Function: Stop all scheduled sends
   - Function: Alert team (log to file, could add Slack/email later)
   - Function: Log incident with timestamp and reason
   - Function: Require manual review to restart

4. Configure GHL Email Settings:
   - Document: Steps to configure sending email in GHL
   - Document: How to set default "From" email
   - Document: How to verify email deliverability
   - Create: Setup checklist for GHL email configuration

5. Create Production Readiness Checklist:
   - [ ] All API connections working
   - [ ] Business context documented
   - [ ] Agents trained
   - [ ] All tests passing
   - [ ] Quality gates implemented
   - [ ] Safety mechanisms in place
   - [ ] GHL email configured
   - [ ] Monitoring in place
   - [ ] Emergency stop tested

SUCCESS CRITERIA:
- ✅ Quality gates implemented and tested
- ✅ Pre-send checklist working
- ✅ Emergency stop functional
- ✅ GHL configuration documented
- ✅ Production readiness checklist complete

DELIVERABLE: Save completion report to .hive-mind/testing/day5_report.md with safety gate test results
```

---

## 🎯 DAY 6: Monitoring & First Real Campaign
**Date:** [Insert Date]  
**Focus:** Set up monitoring, run first real campaign (small batch)  
**Time:** 3-4 hours

### **Ampcode Prompt for Day 6:**

```
TASK: Day 6 - Monitoring Setup & First Real Campaign for chiefaiofficer-alpha-swarm

OBJECTIVE: Implement monitoring dashboard and run first real campaign with 10-20 real leads.

ACTIONS:
1. Create Health Monitor (execution/health_monitor.py):
   - Function: check_api_health() - Test all API connections
   - Function: check_recent_metrics() - Get last 24h performance
   - Function: generate_summary() - Daily summary report
   - Run with: --summary 1 (last 1 day)
   - Output: Console summary + .hive-mind/health_reports/

2. Create Performance Dashboard (execution/dashboard.py):
   - If streamlit available: Create interactive dashboard
   - If not: Create simple CLI dashboard
   - Metrics: Campaigns sent, open rate, reply rate, meetings booked
   - Charts: Daily sends, performance over time
   - Recent: Last 20 campaigns

3. Implement Weekly Review Generator:
   - Already created: .hive-mind/learning/weekly_review.py
   - Test run: python .hive-mind/learning/weekly_review.py
   - Verify: Generates review with metrics, insights, action items
   - Output: .hive-mind/reviews/weekly_review_[date].json

4. First Real Campaign (SMALL BATCH):
   - Select: 10-20 Tier 3 leads (lowest risk)
   - Source: LinkedIn connections, existing contacts, or manual list
   - Process:
     * Enrich leads with Clay
     * Segment (should be Tier 3)
     * Generate personalized campaigns
     * MANUAL REVIEW: Review each email before sending
     * Send via GHL
   - Monitor: Track opens, replies, unsubscribes closely

5. Real-Time Monitoring:
   - Watch: First 24 hours closely
   - Check: Open rates (target >40%)
   - Check: Reply rates (target >5%)
   - Check: Unsubscribe rates (must be <2%)
   - Check: Any negative feedback
   - Document: All results in detail

SUCCESS CRITERIA:
- ✅ Health monitor working
- ✅ Dashboard accessible
- ✅ Weekly review generator tested
- ✅ First campaign sent (10-20 leads)
- ✅ No major issues (unsubscribes <2%, no complaints)

DELIVERABLE: Save completion report to .hive-mind/testing/day6_report.md with first campaign results
```

---

## 🎯 DAY 7: Optimization & Scale Planning
**Date:** [Insert Date]  
**Focus:** Analyze results, optimize, plan for scale  
**Time:** 3-4 hours

### **Ampcode Prompt for Day 7:**

```
TASK: Day 7 - Optimization & Scale Planning for chiefaiofficer-alpha-swarm

OBJECTIVE: Analyze Day 6 campaign results, optimize based on learnings, and create scale plan.

ACTIONS:
1. Analyze Day 6 Campaign Results:
   - Collect metrics: Opens, clicks, replies, meetings, unsubscribes
   - Calculate rates: Open rate, reply rate, meeting rate, unsubscribe rate
   - Compare to targets: Open >40%, Reply >5%, Unsubscribe <2%
   - Identify: What worked well, what didn't
   - Extract: Patterns from successful vs unsuccessful emails

2. Implement Self-Annealing (.hive-mind/learning/self_anneal.py):
   - Function: analyze_campaign_performance(campaign_id)
   - Extract: Success patterns (reply rate >10%)
   - Extract: Failure patterns (reply rate <3%)
   - Extract: Messaging issues (unsubscribe rate >2%)
   - Update: Agent training with learnings
   - Save: Learnings to .hive-mind/knowledge/learnings/

3. Update Agent Training:
   - Based on Day 6 results:
     * What subject lines worked best?
     * What messaging resonated?
     * What caused unsubscribes?
   - Update: Messaging templates with successful patterns
   - Update: ICP criteria if needed
   - Retrain: Agents with new context
   - Test: Verify improvements

4. Create 30-Day Scale Plan (.hive-mind/SCALE_PLAN.md):
   - Week 1 (Days 8-14): 50-100 leads/week (Tier 3 only)
   - Week 2 (Days 15-21): 100-200 leads/week (Tier 2-3)
   - Week 3 (Days 22-28): 200-300 leads/week (All tiers, Tier 1 manual review)
   - Week 4 (Days 29-30): 300+ leads/week (Optimized, automated)
   - Include: Daily targets, quality gates, review schedule

5. Create Continuous Improvement Playbook:
   - Daily: Health check (10 min)
   - Weekly: Performance review, agent retraining (1 hour)
   - Monthly: Deep optimization sprint (1 day)
   - Document: Specific actions for each cadence
   - Create: Templates for reviews and reports

6. Production Readiness Final Check:
   - Review: All 7 days of work
   - Verify: All systems operational
   - Test: Emergency stop works
   - Document: Known issues and workarounds
   - Create: Runbook for common operations

SUCCESS CRITERIA:
- ✅ Day 6 results analyzed thoroughly
- ✅ Self-annealing implemented
- ✅ Agents retrained with learnings
- ✅ 30-day scale plan created
- ✅ Continuous improvement playbook ready
- ✅ System production-ready

DELIVERABLE: Save completion report to .hive-mind/testing/day7_report.md with scale plan and final production readiness assessment
```

---

## 📊 Daily Progress Tracker

| Day | Focus | Status | Blockers | Notes |
|-----|-------|--------|----------|-------|
| 1 | Environment & APIs | ✅ | - | APIs connected, test data created |
| 2 | Business Training | ✅ | - | ICP, templates, company profile done |
| 3 | Component Testing | ✅ | - | All agents pass (80%+ enrichment, 100% personalization) |
| 4 | E2E Workflows | ✅ | - | Both workflows pass, 0.45s per pipeline |
| 3-4 | Core Framework | ✅ | - | Context Manager, Grounding Chain, Feedback Collector - 4/4 tests pass |
| 5 | Safety & Config | ⬜ | | |
| 6 | First Campaign | ⬜ | | |
| 7 | Optimize & Scale | ⬜ | | |

---

## 🎯 Quick Daily Routine (After Day 7)

**Copy this prompt for daily optimization:**

```
TASK: Daily Optimization & Monitoring for chiefaiofficer-alpha-swarm

DATE: [Insert Date]

ACTIONS:
1. Morning Health Check (10 min):
   - Run: python execution/health_monitor.py --summary 1
   - Review: API status, yesterday's metrics
   - Check: Any alerts or issues

2. Review Yesterday's Campaigns (15 min):
   - Open: .hive-mind/campaign_events.jsonl
   - Check: Open rates, reply rates, unsubscribes
   - Identify: Any issues or patterns

3. Quality Spot Check (10 min):
   - Review: 2-3 recent campaigns
   - Verify: Personalization quality, no hallucinations
   - Check: Professional tone, clear CTA

4. Update Learnings (10 min):
   - Document: What worked well
   - Document: What didn't work
   - Update: .hive-mind/knowledge/learnings/daily_log.md

5. Plan Today's Work (5 min):
   - Decide: How many leads to process today
   - Select: Which tier to focus on
   - Set: Quality and quantity goals

DELIVERABLE: 5-minute summary of status and today's plan
```

---

## 🚨 Emergency Prompts

### **If Something Breaks:**

```
URGENT: Emergency Troubleshooting for chiefaiofficer-alpha-swarm

ISSUE: [Describe the problem]

ACTIONS:
1. Run emergency stop: python execution/emergency_stop.py
2. Check API health: python execution/test_connections.py
3. Review recent logs: .hive-mind/campaign_events.jsonl
4. Identify root cause
5. Implement fix
6. Test fix thoroughly
7. Document incident and resolution
8. Resume operations only when safe

DELIVERABLE: Incident report with root cause and fix
```

### **If Results Are Poor:**

```
TASK: Campaign Performance Troubleshooting for chiefaiofficer-alpha-swarm

ISSUE: [Low open rate / Low reply rate / High unsubscribes]

ACTIONS:
1. Analyze last 20 campaigns in detail
2. Identify patterns in poor performers
3. Review messaging templates
4. Check targeting (ICP match?)
5. Verify personalization quality
6. Test new messaging variations
7. Retrain agents with corrections
8. Run small test batch (10 leads)
9. Measure improvement

DELIVERABLE: Analysis report with specific fixes implemented
```

---

## ✅ Success Metrics

**After 7 Days, You Should Have:**

- ✅ All APIs connected and working
- ✅ Business context fully documented
- ✅ Agents trained on your ICP and messaging
- ✅ All components tested individually
- ✅ End-to-end workflows tested
- ✅ Safety gates implemented
- ✅ Monitoring dashboard operational
- ✅ First real campaign completed (10-20 leads)
- ✅ Results analyzed and optimizations made
- ✅ 30-day scale plan created
- ✅ **System production-ready for real leads**

**Target Metrics:**
- Open Rate: >40%
- Reply Rate: >5%
- Unsubscribe Rate: <2%
- Cost per Lead: <$5
- Time per Lead: <2 min

---

## 📝 Notes for Ampcode

**When using these prompts:**
1. Each prompt is self-contained
2. Ampcode should execute all actions autonomously
3. Ampcode should create all files/scripts mentioned
4. Ampcode should run all tests and document results
5. Ampcode should flag anything that needs human input
6. Each day builds on the previous day's work

**Human Input Required:**
- Day 1: Providing fresh API keys if needed
- Day 2: Confirming business context details
- Day 6: Reviewing first campaign before sending
- Day 7: Approving scale plan

**Everything Else:** Ampcode handles automatically!

---

**Last Updated:** 2026-01-17T21:38:09+08:00  
**Version:** 1.0 - 7-Day Production Sprint
