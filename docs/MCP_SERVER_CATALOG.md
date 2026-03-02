---
title: MCP Server Catalog
version: "1.0"
last_updated: 2026-03-02
audience: [all-agents, engineers]
tags: [mcp, servers, tools, catalog, discovery]
canonical_for: [mcp-catalog, mcp-servers]
---

# CAIO Alpha Swarm — MCP Server Catalog

Complete catalog of all MCP (Model Context Protocol) servers in the swarm. Use this for tool discovery across servers.

**Total Servers**: 15 (14 production-ready + 1 stub)
**Total Tools**: ~98 exposed functions
**Location**: `mcp-servers/`

---

## Quick Reference

| Server | Type | Tools | Status | Key APIs |
|--------|------|------:|--------|----------|
| orchestrator-mcp | Orchestration | 5 | Production | Internal (5 agents) |
| enricher-mcp | Lead Enrichment | 5 | Production | Clay, RB2B, Exa |
| hunter-mcp | Lead Sourcing | 5 | Stub | LinkedIn API, Selenium |
| ghl-mcp | CRM + Calendar | 14 | Production | GoHighLevel V2 |
| instantly-mcp | Email Campaigns | 11 | Production | Instantly V2 |
| google-calendar-mcp | Calendar | 6 | Production | Google Calendar API |
| slack-mcp | Messaging | 6 | Production | Slack REST API |
| cache-mcp | Caching | 6 | Production | Internal (memory + disk) |
| context-mcp | Context Mgmt | 6 | Production | Internal (token budget) |
| debug-mcp | Debugging | 9 | Production | Playwright, SQLite |
| document-mcp | Doc Extraction | 5 | Production | Internal (PDF, images) |
| email-threading-mcp | Email Parsing | 6 | Production | Internal (stdlib email) |
| learning-mcp | ML/RL | 7 | Production | Internal (rl_engine) |
| supabase-mcp | Database | Multiple | Production | Supabase + pgvector |

---

## 1. orchestrator-mcp (Alpha Queen — Master Orchestrator)

**Path**: `mcp-servers/orchestrator-mcp/server.py`
**Purpose**: Coordinates all 5 pipeline agents, manages workflow state, routes tasks.

| Function | Parameters | Returns |
|----------|-----------|---------|
| `orchestrator_run_workflow` | `workflow_type`, `source_type`, `source_url`, `limit` | Workflow result dict |
| `orchestrator_swarm_status` | — | Agent status for all 5 agents |
| `orchestrator_dispatch_task` | `agent`, `task_type`, `params` | Task dispatch result |
| `orchestrator_query_hivemind` | `query_type`, `filters` | Knowledge query result |
| `orchestrator_get_metrics` | `time_range` (1h/24h/7d/30d) | System metrics dict |

**Agents Managed**: hunter, enricher, segmentor, crafter, gatekeeper
**Workflow Types**: `lead_harvesting`, `campaign_generation`, `full_pipeline`
**Dependencies**: `execution.fail_safe_manager`, `execution.rl_engine`

---

## 2. enricher-mcp (Lead Enrichment Waterfall)

**Path**: `mcp-servers/enricher-mcp/server.py`
**Purpose**: Enriches leads via Clay/RB2B/Exa waterfall.

| Function | Parameters | Returns |
|----------|-----------|---------|
| `enricher_enrich_lead` | `linkedin_url`, `name`, `company`, `email` | Enriched lead dict |
| `enricher_rb2b_match` | `linkedin_url`, `email`, `company` | RB2B match result |
| `enricher_company_intel` | `company_name`, `domain` | Company research dict |
| `enricher_detect_intent` | `company_name`, `domain`, `linkedin_url` | Intent signals |
| `enricher_batch_enrich` | `input_file`, `limit` | Batch results |

**API Keys Required**: `CLAY_API_KEY`, `RB2B_API_KEY`, `EXA_API_KEY`
**Dependencies**: `execution.enricher_waterfall.ClayEnricher`

---

## 3. hunter-mcp (LinkedIn Lead Sourcing)

**Path**: `mcp-servers/hunter-mcp/server.py`
**Purpose**: Scrapes LinkedIn for leads (company followers, event attendees, group members).
**Status**: STUB — tool definitions present, implementation delegates to linkedin-api/selenium.

| Function | Parameters | Returns |
|----------|-----------|---------|
| `hunter_scrape_followers` | `company_url`, `company_name`, `limit` | Normalized leads |
| `hunter_scrape_event` | `event_url`, `event_name`, `limit` | Event attendees |
| `hunter_scrape_group` | `group_url`, `group_name`, `limit` | Group members |
| `hunter_scrape_post` | `post_url`, `limit` | Post engagers |
| `hunter_status` | — | Service health |

**Health Check**: Yes (`hunter_status()`)
**Dependencies**: `linkedin-api>=2.0.0`, `selenium>=4.15.0`

---

## 4. ghl-mcp (GoHighLevel CRM + Calendar)

**Path**: `mcp-servers/ghl-mcp/server.py`
**Purpose**: Full CRM operations — contacts, opportunities, workflows, calendar.

| Function | Parameters | Returns |
|----------|-----------|---------|
| `ghl_create_contact` | `email`, `first_name`, `last_name`, `phone`, ... | Contact dict (idempotent) |
| `ghl_update_contact` | `contact_id`, `updates` | Updated contact |
| `ghl_get_contact` | `contact_id` or `email` | Contact dict |
| `ghl_add_tag` | `contact_id`, `tag` | Tag result |
| `ghl_create_opportunity` | `contact_id`, `title`, `value`, ... | Opportunity dict |
| `ghl_trigger_workflow` | `contact_id`, `workflow_id` | Workflow result |
| `ghl_bulk_create_contacts` | `contacts` (list) | Batch result |
| `ghl_get_calendars` | — | Calendar list |
| `ghl_get_free_slots` | `calendar_id`, `duration_minutes` | Available slots |
| `ghl_create_appointment` | `calendar_id`, `start`, `end`, `attendees`, ... | Appointment dict |
| `ghl_update_appointment` | `event_id`, `updates` | Updated appointment |
| `ghl_get_appointment` | `appointment_id` | Appointment dict |
| `ghl_delete_calendar_event` | `event_id` | Delete result |
| `ghl_get_calendar_events` | `calendar_id` | Event list |

**Features**: Async HTTP (aiohttp), idempotency keys, retry with backoff, rate limiting
**Dependencies**: `aiohttp`, `requests`, `calendar_client.py`

---

## 5. instantly-mcp (Instantly.ai Email Campaigns — V2)

**Path**: `mcp-servers/instantly-mcp/server.py`
**Purpose**: Email campaign lifecycle management via Instantly API V2.

| Function | Parameters | Returns |
|----------|-----------|---------|
| `instantly_create_campaign` | `name`, `subject`, `from_address`, ... | Campaign dict (idempotent) |
| `instantly_add_leads` | `campaign_id`, `leads` (list) | Add result |
| `instantly_get_analytics` | `campaign_id` | Metrics dict |
| `instantly_pause_campaign` | `campaign_id` | Pause result |
| `instantly_activate_campaign` | `campaign_id` | Activate result |
| `instantly_list_campaigns` | `limit`, `offset` | Campaign list |
| `instantly_get_lead_status` | `campaign_id`, `lead_email` | Lead status |
| `instantly_delete_campaign` | `campaign_id` | Delete result |
| `instantly_export_replies` | `campaign_id` | Reply export |
| `instantly_update_campaign` | `campaign_id`, `updates` | Updated campaign |
| `instantly_setup_webhooks` | `event_types`, `webhook_url` | Webhook config |

**API**: V2 (migrated from V1 on 2026-02-14), Bearer token auth
**Features**: Async HTTP, idempotency (24h expiry), A/B variant support
**Dependencies**: `aiohttp`, `requests`

---

## 6. google-calendar-mcp (Calendar with Guardrails)

**Path**: `mcp-servers/google-calendar-mcp/server.py`
**Purpose**: Google Calendar operations with scheduling safety guardrails.

| Function | Parameters | Returns |
|----------|-----------|---------|
| `get_availability` | `date_range`, `timezone` | Available slots |
| `create_event` | `title`, `start`, `end`, `attendees`, `zoom_link` | Created event |
| `update_event` | `event_id`, `updates` | Updated event |
| `delete_event` | `event_id` | Delete result |
| `get_events` | `calendar_id`, `time_min`, `time_max` | Event list |
| `find_available_slots` | `duration_minutes`, `days_ahead`, `timezone` | Meeting slots |

**Built-in Guardrails**: No double-booking, working hours (9-6), 15-min buffer, 100 req/hr rate limit, 90-day max lookahead, 30-min minimum notice
**Dependencies**: `google-api-python-client`, `google-auth-oauthlib`, `tzdata`

---

## 7. slack-mcp (Notifications + Approvals)

**Path**: `mcp-servers/slack-mcp/server.py`
**Purpose**: Slack messaging, alerts, and approval workflows via Block Kit.

| Function | Parameters | Returns |
|----------|-----------|---------|
| `send_approval_request` | `title`, `description`, `approval_data`, `required_approvers` | Approval result |
| `send_alert` | `message`, `channel`, `level` | Send result |
| `send_message` | `text`, `channel`, `thread_ts` | Message result |
| `update_message` | `ts`, `channel`, `text` | Update result |
| `get_channel_history` | `channel`, `limit` | Message list |
| `handle_interaction` | `payload` | Interaction result |

**Alert Levels**: info, warning, error, critical
**Channels**: `#revops-alerts` (default), `#revops-approvals`
**Env Vars**: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`
**Dependencies**: Slack REST API (direct, no SDK)

---

## 8. cache-mcp (Multi-Tier Caching)

**Path**: `mcp-servers/cache-mcp/server.py`
**Purpose**: LRU memory + compressed disk caching with TTL per data type.

| Function | Parameters | Returns |
|----------|-----------|---------|
| `cache_get` | `key`, `tier` (memory/disk/both) | Hit/miss + value |
| `cache_set` | `key`, `value`, `data_type`, `tier`, `ttl_seconds` | Set result |
| `cache_invalidate` | `key`/`pattern`/`data_type`, `tier` | Invalidation counts |
| `cache_stats` | — | Memory/disk stats + hit rates |
| `cache_warm` | `patterns` (list) | Warmed entry count |
| `health_check` | — | Status + entry counts |

**TTL Policy**: intent 24h, enrichment 7d, company 30d, contact 14d, api_response 1h, template 1d, default 6h
**Storage**: `.hive-mind/cache/` with gzip compression for payloads >1KB
**Health Check**: Yes

---

## 9. context-mcp (Token Efficiency + Budget)

**Path**: `mcp-servers/context-mcp/server.py`
**Purpose**: Token estimation, XML context compression, per-agent budget tracking.

| Function | Parameters | Returns |
|----------|-----------|---------|
| `compact_context` | `data`, `data_type`, `format` (xml/minimal), `keep_fields` | Compacted XML + savings |
| `estimate_tokens` | `content`, `content_type` | Token count + char count |
| `get_context_budget` | `agent_id` | Budget breakdown + utilization |
| `set_context_budget` | `agent_id`, `budget_tokens`, `used_tokens`, `reserved_tokens` | Updated budget |
| `prefetch_data` | `patterns`, `agent_id` | Registered patterns |
| `track_context_usage` | `agent_id`, `tokens_used`, `operation` | Usage update |

**Compression**: XML serialization achieves ~60% reduction vs JSON
**Storage**: `.hive-mind/context/context_state.json`
**Health Check**: Yes

---

## 10. debug-mcp (Full-Stack Error Correlation)

**Path**: `mcp-servers/debug-mcp/server.py`
**Purpose**: Cross-stack debugging — matches frontend errors to backend traces.

| Function | Parameters | Returns |
|----------|-----------|---------|
| `debug_get_correlated_errors` | — | Frontend-backend error matches |
| `debug_get_recent_errors` | — | Aggregated recent errors |
| `debug_get_error_context` | error_id | Full error context |
| `debug_trace_request` | correlation_id | Request trace through stack |
| `debug_get_circuit_breaker_status` | — | All circuit breaker states |
| `debug_search_logs` | query | Full-text log search |
| `debug_capture_ui_state` | — | Screenshot + DOM snapshot |
| `debug_get_console_errors` | — | Browser console errors |
| `debug_get_error_timeline` | — | Chronological error progression |

**Data Sources**: `.hive-mind/audit.db` (SQLite), `.hive-mind/retry_queue.jsonl`, `.hive-mind/frontend_errors.jsonl`, `.hive-mind/logs/`
**Dependencies**: `aiosqlite`, `playwright` (for UI capture)
**Health Check**: Yes

---

## 11. document-mcp (Agentic Document Extraction)

**Path**: `mcp-servers/document-mcp/server.py`
**Purpose**: Extracts structured data from PDF/images using schema templates.

| Function | Parameters | Returns |
|----------|-----------|---------|
| `parse_document` | `document_path`, `schema_type` (lead/competitive/event/none) | Markdown + regions + fields |
| `enrich_lead_from_document` | `lead_json`, `document_path` | Enriched lead dict |
| `extract_competitive_intel` | `document_path` | Competitive intelligence |
| `batch_parse_directory` | `directory_path`, `schema_type`, `max_documents` | Batch results |
| `get_document_chunks` | `document_id` | RAG-ready text chunks |

**Supported Formats**: PDF, JPG, PNG, TIFF
**Storage**: `.hive-mind/parsed_documents/`
**Dependencies**: `core.document_parser`, `execution.enricher_document_ai`

---

## 12. email-threading-mcp (Thread Parsing + Intent Detection)

**Path**: `mcp-servers/email-threading-mcp/server.py`
**Purpose**: Parses email threads, detects intent, extracts action items.

| Function | Parameters | Returns |
|----------|-----------|---------|
| `parse_thread` | `email_raw_content` | Parsed messages + headers + threading |
| `extract_context` | `email_content` | Conversation context + participants |
| `detect_intent` | `email_text` | Intent classification (14 types) |
| `maintain_thread` | `email_dict` | Preserved Message-ID/In-Reply-To/References |
| `summarize_thread` | `email_content` | Concise thread summary |
| `extract_action_items` | `email_text` | Parsed action items |

**Intent Types**: SCHEDULING_REQUEST/CONFIRM/RESCHEDULE/CANCEL, INTEREST_HIGH/MEDIUM/LOW, OBJECTION, QUESTION, FOLLOW_UP, OUT_OF_OFFICE, UNSUBSCRIBE, NOT_INTERESTED, REFERRAL, UNKNOWN
**Storage**: `.hive-mind/threads/`
**Dependencies**: `email` (stdlib), `python-dateutil`

---

## 13. learning-mcp (Reinforcement Learning Interface)

**Path**: `mcp-servers/learning-mcp/server.py`
**Purpose**: Q-table RL engine interface, failure pattern detection, workflow insights.

| Function | Parameters | Returns |
|----------|-----------|---------|
| `record_outcome` | `state`, `action`, `reward`, `metadata` | Outcome recorded + Q-value update |
| `get_q_value` | `state`, `action` | Q-value float |
| `update_q_table` | `state_hash`, `action`, `new_q_value` | Update result |
| `get_best_action` | `state` | Optimal action for state |
| `get_workflow_insights` | — | Workflow performance metrics |
| `get_failure_patterns` | — | Common failure patterns + frequency |
| `suggest_refinements` | `workflow_type` | AI-suggested improvements |

**Storage**: `.hive-mind/learning/`
**Dependencies**: `execution.rl_engine.RLEngine`, `core.event_log`
**Note**: Wraps the dormant RL engine (Phase 5 activation)

---

## 14. supabase-mcp (Unified Data Layer)

**Path**: `mcp-servers/supabase-mcp/server.py`
**Purpose**: Full CRUD on all tables + vector search via Supabase/pgvector.

**Tables**: leads, outcomes, q_table, campaigns, patterns, audit_log

**Features**: Retry with exponential backoff (3 retries: 1s, 2s, 4s), pgvector similarity search, dry-run mode, transient error detection
**Env Vars**: `SUPABASE_URL`, `SUPABASE_KEY`, `DRY_RUN`
**Dependencies**: `supabase>=0.10.0`

---

## Server Manifest Coverage

Individual `manifest.json` files exist for 6 servers:
- debug-mcp (9 tools), enricher-mcp (5), ghl-mcp (6), hunter-mcp (5), instantly-mcp (6), orchestrator-mcp (5)

No unified cross-server manifest exists. Server discovery relies on directory enumeration.

---

## Data Flow Through Servers

```
hunter-mcp (scrape leads)
    |
    v
enricher-mcp (Clay/RB2B/Exa)  <-- cache-mcp (API response caching)
    |
    v
orchestrator-mcp (route to segmentor -> crafter -> gatekeeper)
    |                                            |
    v                                            v
instantly-mcp (email campaigns)        slack-mcp (approval requests)
ghl-mcp (CRM sync + calendar)         debug-mcp (error correlation)
    |                                            |
    v                                            v
email-threading-mcp (reply parsing)    learning-mcp (record outcomes)
    |
    v
supabase-mcp (persist all data)   context-mcp (token budget optimization)
```

---

*Auto-generated. Review `mcp-servers/` for implementation details.*
