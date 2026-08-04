# agent/

## Overview

Server-side agent runtime helpers that bridge harness framework APIs with session and channel context.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `tool_description_locale.py` | Core | Resolves BCP-47 locale for harness LLM tool description SSOT (`memory_*`, `web_search_tool`). | ✅ |

## Dependencies

- `myrm_agent_harness.utils.locale::resolve_locale` (POS: shared locale string handling)
