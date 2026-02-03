# 🚀 Chief AI Officer Swarm: Production Readiness Guide

**Role:** GTM Engineer / Operations Lead
**Goal:** Transition valid "Beta" code into a bulletproof "Live" Revenue Operations System.

---

## 🏗️ 1. System Architecture Assessment

Your swarm is built on a **Microservices Architecture (MCP)**. Unlike a monolithic script, each agent runs as an isolated server. This makes it robust but requires careful orchestration.

### The "System Two" Logic (The Brain)
You asked about Vercel's "Lead Agent" and "System Two" thinking. In your swarm, this is implemented via **The Reasoning Loop**:
1.  **Fast System (System 1)**: `Hunter` and `Enricher` gather data instantly.
2.  **Slow System (System 2)**: The `Orchestrator` & `Reasoning Bank`.
    *   *Before* sending an email, the system checks `.hive-mind/reasoning_bank.json`.
    *   It asks: *"Have we failed with this pattern before?"*
    *   It verifies: *"Does this match the Success Patterns in our Golden Set?"*

**Your Job**: Verify that "System 2" is actually blocking bad decisions. You do this by checking the `Audit Logs` (`.hive-mind/audit/`) to see *why* a decision was made.

### active Core Components
| Component | Function | Status |
|-----------|----------|--------|
| **Orchestrator-MCP** | The "Queen". Routes tasks and manages state. | ✅ Ready |
| **GHL-MCP** | manage CRM contacts/deals. **Idempotent** (safe to retry). | ✅ Ready |
| **Enricher-MCP** | Clay/RB2B waterfall. Adds data context. | ✅ Ready |
| **Crafter** (Internal) | Writes emails using "System 2" templates. | ✅ Ready |
| **Unified Guardrails** |The "Brakes". circuit breakers, rate limits. | ✅ Ready |

---

## 🔑 2. Required Inputs (The Keys to the Kingdom)

To go fully live, you must populate the `.env` file with these **Production Credentials**.
*Do not use personal accounts. Create dedicated "Service Accounts" for the swarm.*

### 🟥 Critical (System Will Not Start)
| Service | Env Variable | Purpose |
|---------|--------------|---------|
| **GoHighLevel** | `GHL_PROD_API_KEY` | Read/Write leads to CRM. |
| **GoHighLevel** | `GHL_LOCATION_ID` | The specific sub-account to operate in. |
| **Supabase** | `SUPABASE_URL` | Long-term memory storage. |
| **Supabase** | `SUPABASE_KEY` | Database access. |
| **Clay** | `CLAY_API_KEY` | Data enrichment waterfall. |
| **Instantly** | `INSTANTLY_API_KEY` | Email sending (Campaigns). |

### 🟨 Operational (Highly Recommended)
| Service | Env Variable | Purpose |
|---------|--------------|---------|
| **RB2B** | `RB2B_WEBHOOK_SECRET` | Validating incoming visitor leads. |
| **RB2B** | `RB2B_API_KEY` | Fetching visitor profiles. |
| **Slack** | `SLACK_WEBHOOK_URL` | Sending alerts to your team. |
| **Slack** | `SLACK_BOT_TOKEN` | Allowing "Click to Approve" from Slack. |

---

## 📅 3. The 3-Day "Go-Live" Plan

Follow this exact sequence to ensure a crash-free launch.

### Day 1: The "Silent" Run (Shadow Mode)
**Objective**: Connect to real data, but disable all "Write" actions (Emails/CRM updates).

1.  **Configure**: Set `mode: "shadow"` in `config/production.json`.
2.  **Run**: Execute `scripts/deploy_shadow_mode.py` (ask Ampcode to build this if missing).
3.  **Feed**: Upload `data/initial_batch.csv` (10 real leads).
4.  **Verify**:
    *   Check `.hive-mind/shadow_logs/emails.json`.
    *   *System 2 Check*: Read the logs. Did it disqualify the competitors? Did it personalize the emails correctly?
    *   **Metric**: 10/10 leads processed without crashing.

### Day 2: The "Chaos" Simulation
**Objective**: Prove the system can handle failures (API outages, bad data).

1.  **Configure**: Set `failure_injection: { enabled: true, rate: 0.1 }` in `config/production.json`.
2.  **Run**: `python scripts/run_failure_campaign.py`.
3.  **Monitor**: Watch the `FailureTracker`.
4.  **Verify**:
    *   Did the **Circuit Breaker** trip when GHL "failed"? (It should stop sending requests).
    *   Did the **Auto-Fix** propose a solution?
    *   **Metric**: System survives 1 hour of chaos without a hard crash.

### Day 3: Controlled Live Fire
**Objective**: Process live traffic with human oversight gaps.

1.  **Configure**: Set `mode: "assisted"` (Human approval required for *sending* only).
2.  **Connect**: Enable the **RB2B Webhook** source.
3.  **Wait**: Let organic traffic flow in.
4.  **Act**:
    *   Approve the first 5 leads via Slack.
    *   Reject 1 lead intentionally to test the "Feedback Loop".
    *   Check if the system *learns* (updates `reasoning_bank.json`) from your rejection.

---

## 🛡️ 4. Bulletproofing Checklist

Before you sleep at night, ensure these 3 things are active:

1.  **[ ] Health Monitor**: Run `scripts/health_monitor.py` in the background. It will Slack you if the swarm dies.
2.  **[ ] Cost Guardrail**: Set a daily spend limit in Clay (e.g., $50). The agent *will* burn cash if you don't cap it.
3.  **[ ] The "Red Button"**: Know exactly how to stop the swarm.
    *   *Command*: `STOP_SWARM=1 python scripts/emergency_stop.py`
    *   *(Create this script specifically for your Ops team)*

---

### 🧠 "System Two" Note for GTM Engineers
The "Lead Agent" magic isn't in the *doing*, it's in the *wait*.
*   **System 1**: "I see a lead, I email a lead." (Bad, Dangerous)
*   **System 2**: "I see a lead. Who are they? Are they a competitor? check the news about them. Okay, draft an email. Wait, is the tone right? Okay, queue for approval."

Your `ChiefAIOfficer-Swarm` is designed as **System 2**. Trust the latency. If it takes 2 minutes to process a lead, that is a *good* thing. It means it's thinking.
