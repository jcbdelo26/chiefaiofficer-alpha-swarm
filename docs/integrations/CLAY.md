# Clay Integration

## Current Status: REMOVED FROM MAIN PIPELINE

Clay was removed from the lead enrichment pipeline in favor of Apollo.io People Match (primary) + BetterContact (fallback).

### Remaining Usage
- **RB2B visitor enrichment only**: Webhook at `/webhooks/clay` receives RB2B visitor data enriched by Clay
- Config: `config/production.json` → `external_apis.clay`
- API key env var: `CLAY_API_KEY`

### Why Removed
- Apollo People Match provides sufficient enrichment for the pipeline
- BetterContact handles fallback/waterfall scenarios
- Clay's per-credit pricing was not cost-effective for bulk pipeline enrichment

### If Re-enabling
- Original enricher stub was at `execution/enricher_clay_waterfall.py` (deleted — see `execution/enricher_waterfall.py`)
- Clay API: `https://api.clay.com/v1`
- Rate limit: 500/hour
