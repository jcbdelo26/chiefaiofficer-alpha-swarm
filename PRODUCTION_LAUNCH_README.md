# ChiefAIOfficer-Beta-Swarm Production Launch

## Quick Start

Run the master launch sequence:

```bash
python execution/production_launch_sequence.py --status
```

---

## 4-Priority Launch Sequence

### Priority #1: Simulation Harness (READY)

**Purpose:** Prove the swarm works by processing 1000 synthetic leads

**Command:**
```bash
python execution/priority_1_simulation_harness.py --leads 1000
```

**What it does:**
- Generates realistic synthetic leads
- Runs through: HUNTER → ENRICHER → SEGMENTOR → CRAFTER → GATEKEEPER
- Tracks success rate, tier distribution, confidence scores
- Saves detailed results to `.hive-mind/simulations/`

**Success criteria:** >90% success rate

---

### Priority #2: API Key Setup (NEEDS INPUT)

**Purpose:** Verify all API connections are working

**Command:**
```bash
python execution/priority_2_api_key_setup.py --test-connections
```

**Current Status:**

| Integration | Status | Action Required |
|-------------|--------|-----------------|
| GHL_PROD_API_KEY | MISSING | See below |
| GHL_LOCATION_ID | SET | None |
| SUPABASE_URL | SET | None |
| SUPABASE_KEY | SET | None |
| RB2B_API_KEY | MISSING | See below |
| CLAY_API_KEY | SET | None |
| SLACK_WEBHOOK_URL | SET | None |

### How to Get Missing API Keys

#### GoHighLevel Production API Key

1. Log into GoHighLevel at https://app.gohighlevel.com
2. Go to **Settings** → **Integrations** → **API Keys**
3. Create a new API key with full permissions
4. Add to your `.env` file:
```
GHL_PROD_API_KEY=your_key_here
```

#### RB2B API Key

1. Log into RB2B at https://app.rb2b.com
2. Go to **Settings** → **Integrations**
3. Generate an API key
4. Add to your `.env` file:
```
RB2B_API_KEY=your_key_here
```

---

### Priority #3: AI vs Human Comparison

**Purpose:** Compare AI decisions against human AE decisions

**Commands:**
```bash
# Generate 100 sample decisions for review
python execution/priority_3_ai_vs_human_comparison.py --generate-queue 100

# Start interactive review session
python execution/priority_3_ai_vs_human_comparison.py --review

# Analyze results
python execution/priority_3_ai_vs_human_comparison.py --analyze
```

**Success criteria:** >75% agreement rate with 50+ reviews

---

### Priority #4: Parallel Mode

**Purpose:** Go live with AE approving every AI decision

**Commands:**
```bash
# Show dashboard
python execution/priority_4_parallel_mode.py --dashboard

# Start approval session
python execution/priority_4_parallel_mode.py --approve

# Execute approved actions
python execution/priority_4_parallel_mode.py --execute
```

**Autonomy levels:**
1. **SHADOW** - AI decides, no action taken
2. **PARALLEL** - AI decides, AE must approve (current)
3. **ASSISTED** - AI decides, AE can override
4. **AUTONOMOUS** - AI decides and executes

---

## Files Created

| File | Purpose |
|------|---------|
| `execution/priority_1_simulation_harness.py` | Generate and process synthetic leads |
| `execution/priority_2_api_key_setup.py` | Verify API connections |
| `execution/priority_3_ai_vs_human_comparison.py` | Compare AI vs human decisions |
| `execution/priority_4_parallel_mode.py` | Production approval workflow |
| `execution/production_launch_sequence.py` | Master controller for all priorities |

---

## What You Need To Do

### Step 1: Get the missing API keys

You need to provide:
1. **GHL_PROD_API_KEY** - Your GoHighLevel production API key
2. **RB2B_API_KEY** - Your RB2B API key

Add these to your `.env` file in the project root.

### Step 2: Run the full sequence

```bash
python execution/production_launch_sequence.py --run-all --leads 100
```

### Step 3: Review AI decisions

```bash
python execution/priority_3_ai_vs_human_comparison.py --review
```

### Step 4: Go live in Parallel Mode

```bash
python execution/priority_4_parallel_mode.py --dashboard
```

---

## Architecture Applied from Vercel Lead Agent

The following patterns from Vercel's Lead Agent are now integrated:

| Pattern | File | Status |
|---------|------|--------|
| Intent Layer | `core/intent_interpreter.py` | Implemented |
| Durable Workflows | `core/durable_workflow.py` | Implemented |
| Confidence Scoring | `core/confidence_replanning.py` | Implemented |
| Bounded Tools | `core/bounded_tools.py` | Implemented |

---

## Contact

When you have the API keys ready, run the launch sequence and the swarm will be production-ready.
