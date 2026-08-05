# agent/

## Overview

Server-side agent runtime helpers that bridge harness framework APIs with session and channel context.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `tool_description_locale.py` | Core | `resolve_agent_params_locale` for `GeneralAgentParams.locale`; `resolve_tool_description_locale` for harness LLM tool description SSOT (`memory_*`, `web_search_tool`). | ✅ |

## Dependencies

- `myrm_agent_harness.utils.locale::resolve_locale` (POS: shared locale string handling)
