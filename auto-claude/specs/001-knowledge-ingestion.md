# Knowledge Ingestion Pipeline

> Build comprehensive data ingestion scripts for production readiness

---

## Goal

Create a robust knowledge ingestion pipeline that imports historical data from Instantly, GoHighLevel, and Clay to bootstrap the Alpha Swarm's learning capabilities.

---

## Requirements

### Functional Requirements
- [ ] Import historical campaign data from Instantly API
- [ ] Import won/lost deal data from GoHighLevel CRM
- [ ] Import enrichment history from Clay
- [ ] Store ingested data in `.hive-mind/knowledge/`
- [ ] Generate baseline metrics for RL engine
- [ ] Create voice profile from successful email templates

### Non-Functional Requirements
- [ ] Handle API rate limits gracefully
- [ ] Support incremental ingestion (don't re-import existing)
- [ ] Provide progress feedback during import
- [ ] Log all ingestion activities

---

## Context

### Relevant Files
| File | Relevance |
|------|-----------|
| `execution/enricher_clay_waterfall.py` | Clay API patterns |
| `execution/test_connections.py` | API connection patterns |
| `.env.template` | API credentials needed |
| `directives/production_context.md` | What to ingest |

### Background
The Alpha Swarm needs historical data to:
1. Train the RL engine with real outcomes
2. Calibrate ICP scoring with actual deal data
3. Learn Chris's voice from successful templates
4. Establish performance baselines

### API Documentation
- Instantly: https://developer.instantly.ai/
- GoHighLevel: https://highlevel.stoplight.io/
- Clay: https://docs.clay.com/

---

## Technical Approach

### Proposed Solution
Create modular ingestion scripts that can run independently or together:

```
execution/
├── ingest_instantly_templates.py   # Email templates
├── ingest_instantly_analytics.py   # Campaign metrics
├── ingest_ghl_deals.py             # Won/lost deals
├── ingest_ghl_contacts.py          # Historical contacts
├── ingest_clay_history.py          # Enrichment data
└── run_full_ingestion.py           # Orchestrator
```

### Data Flow
```
Instantly API → ingest_instantly_*.py → .hive-mind/knowledge/templates/
                                      → .hive-mind/knowledge/campaigns/

GHL API → ingest_ghl_*.py → .hive-mind/knowledge/deals/
                          → .hive-mind/knowledge/contacts/

Clay API → ingest_clay_history.py → .hive-mind/knowledge/enrichment/
```

### Output Schema

#### Campaign Data
```json
{
  "campaign_id": "string",
  "name": "string",
  "emails_sent": 1000,
  "opens": 450,
  "open_rate": 0.45,
  "replies": 80,
  "reply_rate": 0.08,
  "positive_replies": 40,
  "meetings_booked": 15,
  "segment": "competitor_displacement",
  "template_used": "template_id",
  "date_range": ["2025-01-01", "2025-12-31"]
}
```

#### Deal Data
```json
{
  "deal_id": "string",
  "status": "won|lost",
  "value": 50000,
  "source": "scraping|inbound|referral",
  "icp_score_at_creation": 85,
  "days_to_close": 45,
  "rejection_reason": "null|string",
  "contact": {
    "title": "VP Sales",
    "company_size": 150,
    "industry": "SaaS"
  }
}
```

---

## Constraints

### Do NOT
- Store raw API responses (extract only needed fields)
- Modify existing `.hive-mind` data
- Re-import data that already exists
- Expose credentials in logs

### Must Follow
- Rate limiting patterns from existing scripts
- JSON storage format for consistency
- Logging to `.tmp/logs/ingestion_*.log`

---

## Acceptance Criteria

### Test Cases
1. **Given** valid Instantly API key, **When** ingestion runs, **Then** templates are saved to knowledge/templates/
2. **Given** valid GHL API key, **When** ingestion runs, **Then** deals are saved with ICP data
3. **Given** partial previous run, **When** ingestion runs again, **Then** only new data is imported
4. **Given** API rate limit hit, **When** error occurs, **Then** script waits and retries

### Validation
- [ ] All API connections verified
- [ ] Sample data imported successfully
- [ ] No duplicate records
- [ ] Progress logged to file
- [ ] Error handling tested

---

## Implementation Priority

1. `ingest_instantly_analytics.py` - Campaign metrics (most critical)
2. `ingest_ghl_deals.py` - Won/lost outcomes
3. `ingest_instantly_templates.py` - Voice training
4. `run_full_ingestion.py` - Orchestrator
5. `ingest_clay_history.py` - Enrichment baseline

---

*Spec Created: 2026-01-15*
*Author: Alpha Swarm Team*
*Priority: High*
