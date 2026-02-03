---
description: Lead harvesting workflow from LinkedIn sources through enrichment and segmentation
---

# Lead Harvesting Workflow

This workflow scrapes LinkedIn sources, enriches leads, and segments them for campaign creation.

## Prerequisites
- Virtual environment activated (`.venv`)
- API credentials configured in `.env`
- Connection test passed

## Workflow Steps

### Step 1: Choose Source Type

Select one of the following source types:
- `--company gong` - Competitor followers (Gong, Clari, Chorus)
- `--url <linkedin_event_url>` - Event attendees
- `--url <linkedin_group_url>` - Group members  
- `--url <linkedin_post_url>` - Post engagers

### Step 2: Run Scraper

```powershell
# Example: Scrape Gong followers
python execution\hunter_scrape_followers.py --company gong --limit 100
```

Output: `.hive-mind/scraped/followers_<batch_id>_<timestamp>.json`

### Step 3: Enrich Leads

```powershell
# Enrich the scraped batch
python execution\enricher_clay_waterfall.py --input .hive-mind\scraped\<latest_file>.json
```

Output: `.hive-mind/enriched/enriched_<timestamp>.json`

### Step 4: Segment & Score

```powershell
# Classify and score leads
python execution\segmentor_classify.py --input .hive-mind\enriched\<latest_file>.json
```

Output: `.hive-mind/segmented/segmented_<timestamp>.json`

### Step 5: Review Output

Check the segmentation summary for:
- Tier distribution (how many Tier 1, 2, 3, 4, DQ)
- Average ICP score
- Campaign recommendations

### Step 6: Sync to GHL (Optional)

```powershell
# Push leads to GoHighLevel CRM
python execution\ghl_sync_leads.py --input .hive-mind\segmented\<latest_file>.json
```

## Expected Output

Each lead will have:
- ICP score (0-100)
- ICP tier (tier_1, tier_2, tier_3, tier_4, disqualified)
- Segment tags
- Recommended campaign type
- Personalization hooks

## Error Handling

If scraping fails:
1. Check LinkedIn session validity: `python execution\test_connections.py`
2. Check rate limit status in logs
3. Wait and retry if rate limited

If enrichment fails:
1. Check Clay API credits
2. Review error logs in `.hive-mind/errors/`
3. Try fallback enrichment
