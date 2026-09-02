---
name: x-live-search
description: >-
  Search X (Twitter) posts, profiles, and threads via xAI Live Search API.
  Returns tweet content with inline citations. Requires an xAI provider in Settings.
version: 1.0.0
category: research
oauth_issuer: xai
tags:
  - x
  - twitter
  - social
  - search
  - xai
allowed-tools: bash_code_execute_tool web_fetch_tool
contract:
  steps:
    - "Phase 1: Verify — confirm xAI provider is configured in Settings → Models & Providers or Credentials"
    - "Phase 2: Query — formulate a precise X search query (handles, dates, topic)"
    - "Phase 3: Execute — run the search helper script via bash_code_execute_tool"
    - "Phase 4: Summarize — cite sources from the output citations"
  potential_traps:
    - description: "xAI provider not configured"
      mitigation: "Guide user to add xAI provider in Settings → Models & Providers before searching"
      severity: high
    - description: "Using allowed_handles and excluded_handles together"
      mitigation: "Pick one filter mode only — they are mutually exclusive"
      severity: medium
  verification_steps:
    - step_id: xai_provider
      description: "xAI provider API key is available for this session"
      validation_method: "Running search script returns results without credential error"
      is_required: true
  success_criteria: "Relevant X posts retrieved with citation-backed summary"
  estimated_duration_seconds: 120
---

# X Live Search

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Overview

Dedicated X/Twitter search via xAI's Live Search API. Use for current discussions, reactions, and trending topics on X — not for general web pages (use `web_search_tool` instead).

Credentials are automatically injected into the sandbox environment (`XAI_API_KEY`) at runtime — **never** ask the user to paste keys into chat.

## Prerequisites

1. Add an xAI provider in **Settings → Models & Providers** (API key + `https://api.x.ai/v1` base URL) or connect via **Settings → Integrations → Credentials**.
2. Enable this skill on the agent profile.

## Helper Script Usage

Run the bundled search script in the sandbox via `bash_code_execute_tool`:

```bash
python3 .claude/skills/x-live-search/scripts/search.py --query "DeepSeek release"
```

### Advanced Filtering

Filter by specific X handles (max 10):
```bash
python3 .claude/skills/x-live-search/scripts/search.py --query "AI announcements" --handles elonmusk sama
```

Exclude specific handles (max 10):
```bash
python3 .claude/skills/x-live-search/scripts/search.py --query "CUDA" --exclude-handles spammer1
```

Date range filtering (`YYYY-MM-DD`):
```bash
python3 .claude/skills/x-live-search/scripts/search.py --query "LLM reasoning" --from-date 2026-08-01 --to-date 2026-08-31
```

## Notes

- Do not use `--handles` and `--exclude-handles` in the same command.
- Prefer citations from script output when summarizing claims.
