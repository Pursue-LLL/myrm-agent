---
name: x-live-search
description: >-
  Search X (Twitter) posts, profiles, and threads via xAI Live Search API.
  Returns tweet content with inline citations. Requires an xAI provider in Settings.
version: 1.0.0
category: research
tags:
  - x
  - twitter
  - social
  - search
  - xai
allowed-tools: x_search_tool web_fetch_tool
contract:
  steps:
    - "Phase 1: Verify — confirm xAI provider is configured in Settings → Models & Providers"
    - "Phase 2: Query — formulate a precise X search query (handles, dates, topic)"
    - "Phase 3: Execute — call x_search_tool with optional handle/date filters"
    - "Phase 4: Summarize — cite sources from inline citations"
  potential_traps:
    - description: "xAI provider not configured"
      mitigation: "Guide user to add xAI provider before searching"
      severity: high
    - description: "Using allowed_handles and excluded_handles together"
      mitigation: "Pick one filter mode only — they are mutually exclusive"
      severity: medium
  verification_steps:
    - step_id: xai_provider
      description: "xAI provider API key is available for this session"
      validation_method: "x_search_tool returns results without credential error"
      is_required: true
  success_criteria: "Relevant X posts retrieved with citation-backed summary"
  estimated_duration_seconds: 120
---

# X Live Search

## Overview

Dedicated X/Twitter search via xAI's Live Search API (`x_search_tool`). Use for current discussions, reactions, and trending topics on X — not for general web pages (use `web_search_tool` instead).

## Prerequisites

1. Add an xAI provider in **Settings → Models & Providers** (API key + `https://api.x.ai/v1` base URL).
2. Enable this skill on the agent profile.

## Tool Usage

Call `x_search_tool` with:

- `query` — what to search on X
- `allowed_handles` — optional, restrict to specific handles (max 10)
- `excluded_handles` — optional, exclude handles (max 10)
- `from_date` / `to_date` — optional, `YYYY-MM-DD` range

## Notes

- Do not use `allowed_handles` and `excluded_handles` in the same call.
- Prefer citations from tool output when summarizing claims.
