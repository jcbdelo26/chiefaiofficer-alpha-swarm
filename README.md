# 👑 Chief AI Officer Alpha Swarm

> Autonomous LinkedIn Intelligence & Lead Generation System for Chiefaiofficer.com Revenue Operations

**Founder**: [Chris Daigle](https://www.linkedin.com/in/doctordaigle/) - CEO, Chiefaiofficer.com

---

## 🎯 Overview

The **Alpha Swarm** is an autonomous agent system that:
1. **Scrapes** LinkedIn for competitor followers, event attendees, group members, and post engagers
2. **Enriches** leads with deep context via Clay, RB2B, and Exa
3. **Segments** by source channel and ICP fit
4. **Creates** hyper-personalized campaigns
5. **Gates** through AE approval before execution

All powered by Claude-Flow orchestration and MCP tool servers.

---

## 🤖 Agent Architecture

```
                    👑 ALPHA QUEEN (Master Orchestrator)
                              │
        ┌─────────┬───────────┼───────────┬─────────┐
        ▼         ▼           ▼           ▼         ▼
    🕵️ HUNTER  💎 ENRICHER  📊 SEGMENTOR  ✍️ CRAFTER  🚪 GATEKEEPER
    (Scraping)  (Context)   (Channels)   (Campaigns) (AE Review)
```

| Agent | Role | MCP Server |
|-------|------|------------|
| 👑 ALPHA QUEEN | Master Orchestrator | `orchestrator-mcp` |
| 🕵️ HUNTER | LinkedIn Scraper | `hunter-mcp` |
| 💎 ENRICHER | Data Enrichment | `enricher-mcp` |
| 📊 SEGMENTOR | Lead Segmentation | Built-in |
| ✍️ CRAFTER | Campaign Creator | Built-in |
| 🚪 GATEKEEPER | AE Review Gate | Built-in |

---

## 🚀 Quick Start

### 1. Setup Environment

```powershell
# Run setup script
.\setup.ps1

# Or manually:
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure API Keys

Copy `.env.template` to `.env` and fill in your credentials:

```env
GHL_API_KEY=your_gohighlevel_key
GHL_LOCATION_ID=your_location_id
CLAY_API_KEY=your_clay_key
RB2B_API_KEY=your_rb2b_key
INSTANTLY_API_KEY=your_instantly_key
LINKEDIN_COOKIE=your_li_at_cookie
```

### 3. Test Connections

```powershell
python execution\test_connections.py
```

### 4. Run Your First Scrape

```powershell
# Scrape Gong followers
python execution\hunter_scrape_followers.py --company gong

# Enrich scraped leads
python execution\enricher_clay_waterfall.py --input .hive-mind\scraped\latest.json

# Segment and score
python execution\segmentor_classify.py --input .hive-mind\enriched\latest.json
```

---

## 📁 Project Structure

```
chiefaiofficer-alpha-swarm/
├── 📋 PRD.md                    # Product Requirements Document
├── 🗺️ ROADMAP.md                # 12-week implementation roadmap
├── 📖 CLAUDE.md                 # Claude agent instructions
├── 📖 GEMINI.md                 # Gemini agent instructions
│
├── 📁 directives/               # SOPs and business rules
│   ├── icp_criteria.md          # ICP scoring algorithm
│   ├── scraping_sop.md          # LinkedIn scraping rules
│   ├── enrichment_sop.md        # Enrichment pipeline
│   └── campaign_sop.md          # Campaign creation rules
│
├── 📁 execution/                # Python execution scripts
│   ├── test_connections.py      # API connection tester
│   ├── hunter_scrape_followers.py
│   ├── enricher_clay_waterfall.py
│   └── segmentor_classify.py
│
├── 📁 mcp-servers/              # MCP tool servers
│   ├── hunter-mcp/              # LinkedIn scraping
│   ├── enricher-mcp/            # Clay + RB2B
│   ├── ghl-mcp/                 # GoHighLevel CRM
│   ├── instantly-mcp/           # Email outreach
│   └── orchestrator-mcp/        # Coordination
│
├── 📁 .hive-mind/               # Persistent state
│   ├── scraped/                 # Raw scraped data
│   ├── enriched/                # Enriched leads
│   ├── segmented/               # Segmented leads
│   ├── campaigns/               # Generated campaigns
│   ├── reasoning_bank.json      # Self-annealing data
│   └── learnings.json           # Historical learnings
│
└── 📁 .agent/workflows/         # Workflow definitions
```

---

## 🔧 Tech Stack

| Platform | Purpose | Integration |
|----------|---------|-------------|
| **GoHighLevel** | CRM & Automation | API + Webhooks |
| **Clay** | Lead Enrichment | API |
| **RB2B** | Visitor Identification | API + Webhooks |
| **Instantly** | Email Outreach | API |
| **LinkedIn** | Data Source | Sales Navigator + Scraping |
| **Claude-Flow** | Agent Orchestration | MCP |

---

## 📊 Lead Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│ LINKEDIN SOURCES                                                        │
│ • Competitor Followers (Gong, Clari, Chorus)                           │
│ • Event Attendees (AI RevOps conferences)                              │
│ • Group Members (RevOps communities)                                    │
│ • Post Engagers (Commenters, Likers)                                   │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 🕵️ HUNTER: Scrape & Normalize                                          │
│ Output: Raw lead with source context                                    │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 💎 ENRICHER: Deep Context Building                                      │
│ • Contact data (Clay waterfall)                                        │
│ • Company intel (size, industry, tech stack)                           │
│ • Intent signals (hiring, funding, competitor usage)                   │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 📊 SEGMENTOR: Classify & Score                                          │
│ • ICP Score (0-100)                                                     │
│ • Tier Assignment (1-4 or DQ)                                          │
│ • Segment Tags (source, competitor, intent)                            │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ ✍️ CRAFTER: Campaign Generation                                         │
│ • Personalized email sequences                                          │
│ • Contextual subject lines                                              │
│ • A/B variants                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 🚪 GATEKEEPER: AE Review                                                │
│ • Campaign preview                                                      │
│ • One-click approve/reject                                              │
│ • Inline editing                                                        │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ INSTANTLY: Email Execution                                              │
│ • Approved campaigns pushed                                             │
│ • Sending scheduled                                                     │
│ • Metrics tracked                                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 ICP Criteria

**Target Profile**:
- **Company Size**: 51-500 employees
- **Industry**: B2B SaaS, Technology, Professional Services
- **Revenue**: $5M - $100M ARR
- **Title**: VP Sales, VP Revenue, CRO, RevOps Director
- **Tech Stack**: Using Salesforce/HubSpot + looking for AI

**ICP Scoring**:
| Score | Tier | Treatment |
|-------|------|-----------|
| 85-100 | Tier 1 | Personalized 1:1, AE direct |
| 70-84 | Tier 2 | Personalized sequence |
| 50-69 | Tier 3 | Semi-personalized batch |
| 30-49 | Tier 4 | Nurture sequence |
| 0-29 | DQ | Do not contact |

---

## 🚀 SPARC Methodology

The Alpha Swarm implements **SPARC** (Specifications, Pseudocode, Architecture, Refinement, Completion) for SDR automation:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      SPARC IMPLEMENTATION                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  📋 SPECIFICATIONS  →  🔄 PSEUDOCODE  →  🏗️ ARCHITECTURE               │
│  Goals & Criteria      Decision Trees     Agent Orchestration           │
│                                                                         │
│                        🔧 REFINEMENT  →  ✅ COMPLETION                  │
│                        RL Optimization     Deploy & Monitor             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### SPARC Quick Start

```powershell
# Initialize SPARC Coordinator
python execution\sparc_coordinator.py --init

# Check status
python execution\sparc_coordinator.py --status

# Run all phases
python execution\sparc_coordinator.py --run-all

# Test decision trees
python execution\sparc_coordinator.py --test-mode --sample-size 10

# Self-anneal from outcomes
python execution\sparc_coordinator.py --self-anneal
```

### SDR Automation Capabilities

| Capability | Agent | Automation Level |
|------------|-------|------------------|
| Lead Qualification | SEGMENTOR | Full |
| Initial Outreach | CRAFTER | Supervised |
| Follow-up Sequencing | Instantly | Full |
| Meeting Scheduling | GHL | Full |
| Objection Handling | CRAFTER | Partial |

See [directives/sparc_methodology.md](./directives/sparc_methodology.md) for complete SPARC documentation.

---

## 🔐 Safety & Compliance

1. **LinkedIn Rate Limiting**: Max 100 profiles/hour, 500/day
2. **Email Compliance**: CAN-SPAM compliant, working unsubscribe
3. **Data Retention**: GDPR compliant, deletion on request
4. **Human Approval**: All campaigns require AE sign-off

---

## 📈 Implementation Roadmap

See [ROADMAP.md](./ROADMAP.md) for detailed 12-week plan.

| Phase | Duration | Focus |
|-------|----------|-------|
| Phase 0 | Day 1 | Project Setup |
| Phase 1 | Week 1-2 | Foundation |
| Phase 2 | Week 3-4 | Core Scraping |
| Phase 3 | Week 5-6 | Intelligence |
| Phase 4 | Week 7-8 | Campaign Engine |
| Phase 5 | Week 9-10 | Human Loop |
| Phase 6 | Week 11-12 | Optimization |

---

## 📚 Documentation

- **[PRD.md](./PRD.md)** - Full product requirements
- **[ROADMAP.md](./ROADMAP.md)** - Step-by-step implementation
- **[CLAUDE.md](./CLAUDE.md)** - Claude agent configuration
- **[directives/](./directives/)** - Standard operating procedures

---

## 🤝 Contributing

This is a proprietary system for Chiefaiofficer.com. Contact Chris Daigle for access.

---

*Built with Claude-Flow | Powered by the 3-Layer Architecture*
