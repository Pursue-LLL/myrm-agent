---
name: notion-workspace
description: >-
  Manage Notion workspaces via the Notion API: create pages, update databases,
  query content, and organize knowledge bases. Requires a Notion integration token.
version: 1.0.0
category: productivity
tags:
  - notion
  - productivity
  - knowledge-base
  - notes
  - database
allowed-tools: web_fetch_tool bash_code_execute_tool file_write_tool
contract:
  steps:
    - "Phase 1: Connect — verify Notion API token and workspace access"
    - "Phase 2: Discover — list accessible pages and databases"
    - "Phase 3: Execute — perform the requested CRUD operations"
    - "Phase 4: Confirm — verify changes and report results"
  potential_traps:
    - description: "API token not configured or missing permissions"
      mitigation: "Check NOTION_API_KEY env var first; guide user through integration setup if missing"
      severity: high
    - description: "Overwriting existing content without backup"
      mitigation: "Read existing content before updating; confirm destructive changes with user"
      severity: high
  verification_steps:
    - step_id: api_access
      description: "Notion API token is configured and has access to target workspace"
      validation_method: "GET https://api.notion.com/v1/users/me returns 200"
      is_required: true
  success_criteria: "Requested Notion operations completed successfully with verification"
  estimated_duration_seconds: 300
---

# Notion Workspace

## Overview

Notion is a comprehensive workspace for notes, databases, wikis, and project management. This skill provides structured workflows for managing Notion content via the official API.

## Prerequisites

The user needs a Notion integration token:

1. Go to https://www.notion.so/my-integrations
2. Create a new integration (or use existing)
3. Copy the Internal Integration Token
4. Set as environment variable: `NOTION_API_KEY=secret_xxx`
5. Share target pages/databases with the integration (click "..." → "Connections" → add integration)

## API Basics

All requests go to `https://api.notion.com/v1/` with headers:

```
Authorization: Bearer $NOTION_API_KEY
Notion-Version: 2022-06-28
Content-Type: application/json
```

## Common Operations

### Search Workspace

```bash
curl -X POST 'https://api.notion.com/v1/search' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{"query": "search term", "page_size": 10}'
```

### Read a Page

```bash
curl 'https://api.notion.com/v1/pages/PAGE_ID' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28"
```

### Query a Database

```bash
curl -X POST 'https://api.notion.com/v1/databases/DB_ID/query' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{"filter": {"property": "Status", "status": {"equals": "In Progress"}}}'
```

### Create a Page

```bash
curl -X POST 'https://api.notion.com/v1/pages' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{
    "parent": {"database_id": "DB_ID"},
    "properties": {
      "Name": {"title": [{"text": {"content": "New Item"}}]},
      "Status": {"status": {"name": "Not started"}}
    }
  }'
```

### Append Content to Page

```bash
curl -X PATCH 'https://api.notion.com/v1/blocks/BLOCK_ID/children' \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{
    "children": [
      {"type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "New content"}}]}}
    ]
  }'
```

## Workflow Patterns

### Daily Journal
1. Search for today's journal page
2. If not exists, create under journal database
3. Append today's entries

### Meeting Notes
1. Create page in meetings database
2. Set properties (date, attendees, project)
3. Add structured content (agenda, notes, action items)

### Knowledge Base Update
1. Search for existing topic page
2. Read current content
3. Append or update sections
4. Update metadata (last-modified, tags)

### Task Management
1. Query tasks database with filters (assigned to me, due this week)
2. Update status on completed items
3. Create new tasks from action items

## Property Types Reference

| Property Type | JSON Key | Example Value |
|--------------|----------|---------------|
| Title | `title` | `[{"text": {"content": "text"}}]` |
| Rich text | `rich_text` | `[{"text": {"content": "text"}}]` |
| Number | `number` | `42` |
| Select | `select` | `{"name": "Option"}` |
| Multi-select | `multi_select` | `[{"name": "Tag1"}, {"name": "Tag2"}]` |
| Date | `date` | `{"start": "2024-01-15"}` |
| Checkbox | `checkbox` | `true` |
| Status | `status` | `{"name": "In Progress"}` |
| URL | `url` | `"https://example.com"` |
