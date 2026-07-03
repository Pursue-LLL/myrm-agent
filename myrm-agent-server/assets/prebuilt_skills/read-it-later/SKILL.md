---
name: read-it-later
description: >-
  Autonomous knowledge ingestion pipeline: pull unread items from a third-party
  read-it-later service (via MCP), fetch article content, ingest into the wiki
  knowledge base, and write back a summary with a processed tag. Designed for
  cron scheduling with zero user intervention.
version: 1.0.0
category: productivity
tags:
  - read-it-later
  - knowledge-base
  - ingestion
  - cron
  - automation
  - wiki
allowed-tools: web_fetch_tool wiki_ingest_tool wiki_query_tool wiki_compile_tool memory_save_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Pull — retrieve unprocessed items from the configured MCP read-it-later source"
    - "Phase 2: Fetch — download full article content for each URL"
    - "Phase 3: Ingest — store content into the wiki knowledge base with metadata"
    - "Phase 4: Write-back — update the source item with a summary and mark as processed"
  potential_traps:
    - description: "Anti-bot pages returning empty or garbled content"
      mitigation: "Use web_fetch_tool with stealth mode; skip and log failures without blocking other items"
      severity: medium
    - description: "Duplicate ingestion on retry after partial failure"
      mitigation: "Always check for processed tag before ingestion; skip items already tagged"
      severity: medium
    - description: "Extremely long articles consuming excessive tokens"
      mitigation: "Summarize articles over 10,000 words instead of ingesting verbatim"
      severity: low
  success_criteria: "All unprocessed items fetched, ingested into wiki, and marked as processed in the source"
  estimated_duration_seconds: 300
---

# Read-it-Later Autonomous Ingestion

## Overview

Turn your bookmarking habit into a compounding knowledge base. This skill runs
on a schedule (typically daily via cron), pulls unread items from your preferred
read-it-later service through MCP, fetches and extracts the core content, ingests
it into your personal wiki, and writes a summary back to the source.

The result: articles you save today become searchable knowledge tomorrow — recalled
automatically in future conversations without you ever needing to re-read them.

## Phase 1: Pull Unprocessed Items

### Source Discovery

Use the configured MCP service to list items from the designated task group or tag:

1. Call the MCP list/query endpoint to retrieve items from the read-it-later group
2. **Filter out already-processed items** — skip any item that already has a
   "digested" / "已内化" tag or equivalent processed marker
3. Collect the remaining items' URLs and titles

### Idempotency Rules

- Never process an item that already bears the processed tag
- If an item has no URL, skip it with a log note
- Cap at 10 items per run to avoid excessive token consumption

## Phase 2: Fetch Article Content

For each unprocessed URL:

1. Use `web_fetch_tool` to retrieve the full article content
   - The tool automatically handles anti-bot measures with multi-layer fallback
   - For paywalled content, extract whatever is publicly available
2. If fetching fails after retries, log the failure and continue to the next item
3. Extract the core article text — strip navigation, ads, and boilerplate

### Content Quality Check

Before ingestion, verify the fetched content is meaningful:
- If the content is less than 100 characters, mark as "fetch failed" and skip
- If the content appears to be an error page or login wall, skip with a note

## Phase 3: Ingest into Knowledge Base

For each successfully fetched article:

1. Use `wiki_ingest_tool` with:
   - `source`: the cleaned article text (not the URL, to avoid re-fetching)
   - `filename`: a readable name derived from the article title
   - `folder_path`: "Read-it-Later/{YYYY-MM}" for chronological organization
2. After ingestion, use `memory_save_tool` to record a brief memory note:
   - Key takeaways (2-3 bullet points)
   - Source URL for attribution
   - Date of ingestion

### Folder Organization

```
wiki/raw/Read-it-Later/
├── 2026-07/
│   ├── rust-async-runtime-internals.md
│   ├── llm-agent-design-patterns.md
│   └── distributed-systems-consensus.md
└── 2026-06/
    └── ...
```

## Phase 4: Write-back to Source

After successful ingestion, update the source item via MCP:

1. Write a brief summary (3-5 sentences) into the item's description or notes field
2. Add the processed tag ("digested" or "已内化") to prevent re-processing
3. Optionally mark the item's status as completed if the service supports it

### Write-back Format

```
AI Summary (auto-generated):
[3-5 sentence summary of the article's key points]

Ingested: {date} | Wiki: Read-it-Later/{folder}/{filename}
```

## Error Handling

| Situation | Action |
|-----------|--------|
| MCP service unavailable | Abort run gracefully; next cron tick will retry |
| Single URL fetch fails | Skip item, continue with others, log failure |
| Wiki ingestion fails | Skip item, continue with others, log failure |
| Write-back fails | Log warning; item will be re-processed next run (safe due to idempotency) |

## Completion Report

After processing all items, output a brief summary:

```
Read-it-Later Ingestion Complete:
- Processed: {n} items
- Skipped (already done): {m} items
- Failed: {k} items (see logs)
- New wiki articles: {n} added to Read-it-Later/{month}/
```

## Cron Scheduling

Recommended cron configuration for daily ingestion:

```yaml
schedule: "0 6 * * *"           # Every day at 6:00 AM
job_type: agent
skill: read-it-later
delivery:
  channel: silent               # No notification unless errors occur
```

The ingestion runs as an agent job with full MCP access, enabling seamless
interaction with the configured read-it-later service.
