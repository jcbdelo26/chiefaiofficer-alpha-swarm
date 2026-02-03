---
model: opus
description: Research leads through parallel sub-agent analysis
---

# Lead Research Command

<context>
<purpose>Spawn parallel research agents to analyze lead sources, enrichment data, and segment patterns</purpose>
<output_dir>.hive-mind/research/</output_dir>
<format>Compact XML with GitHub permalinks</format>
</context>

## Execution Pattern

Spawn these sub-agents IN PARALLEL (single message):

```
Task("source-analyzer", "Trace lead sources through pipeline", "researcher")
Task("enrichment-mapper", "Map enrichment data fields from Clay/RB2B", "researcher")  
Task("segment-profiler", "Analyze existing segment patterns and criteria", "researcher")
```

## Sub-Agent Instructions

### Source Analyzer
<agent role="source-analyzer">
<scope>
- mcp-servers/hunter-mcp/
- execution/hunter_*.py
- .hive-mind/scraped/
</scope>
<task>
1. Identify all lead ingestion points
2. Document data flow: LinkedIn → Hunter → Enricher → Segmentor
3. Return file:line references for each pipeline stage
</task>
<output_format>
```xml
<sources>
  <source name="" file="" line="" permalink="">
    <fields>field1, field2, field3</fields>
    <downstream>next_processor</downstream>
  </source>
</sources>
```
</output_format>
</agent>

### Enrichment Mapper
<agent role="enrichment-mapper">
<scope>
- mcp-servers/enricher-mcp/
- execution/enrichment_*.py
- config/clay_*.json
- .hive-mind/enriched/
</scope>
<task>
1. Map Clay API fields to internal schema
2. Map RB2B visitor data integration
3. Document enrichment success/failure rates if available
</task>
<output_format>
```xml
<enrichment>
  <provider name="" config_file="" line="">
    <field_mapping>
      <external>company_size</external>
      <internal>employee_count</internal>
    </field_mapping>
  </provider>
</enrichment>
```
</output_format>
</agent>

### Segment Profiler
<agent role="segment-profiler">
<scope>
- execution/segmentor_*.py
- directives/icp_criteria.md
- .hive-mind/campaigns/
</scope>
<task>
1. Extract segment definitions (tier1, tier2, etc.)
2. Document scoring criteria and thresholds
3. Find segment distribution patterns
</task>
<output_format>
```xml
<segments>
  <segment name="tier1" defined_in="" line="">
    <criteria>employee_count >= 51 AND industry IN (B2B SaaS)</criteria>
    <score_range>80-100</score_range>
  </segment>
</segments>
```
</output_format>
</agent>

## Output Structure

Save consolidated research to:
```
.hive-mind/research/
├── {date}_lead_sources.xml
├── {date}_enrichment_map.xml
├── {date}_segment_patterns.xml
└── {date}_research_summary.md
```

## GitHub Permalinks

For persistence, include permalinks in this format:
```
https://github.com/{owner}/{repo}/blob/{commit_sha}/{path}#L{line}
```

Use `git rev-parse HEAD` to get current commit SHA.

## Completion Criteria

Research is complete when:
- [ ] All three sub-agents have returned structured output
- [ ] Each finding includes file:line reference
- [ ] Summary document synthesizes findings
- [ ] No evaluation or recommendations included (research only)
