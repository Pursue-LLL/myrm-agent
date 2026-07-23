# tool_mount/

## Overview

Server SSOT for **when** harness meta tools (file + shell bundle) mount per product entry.

Harness `get_meta_tools(enable_file_tools, enable_shell_tools)` remains the factory; this module is the product decision layer.

## Mount matrix

| Surface | Meta file | Meta shell | SSOT |
| --- | --- | --- | --- |
| `WEB_CHAT`, `CHANNEL`, `KANBAN`, `VOICE`, `EVAL` | On | On | `resolve_agent_mount` |
| `WEB_FAST` | Off | Off | `resolve_agent_mount` |
| `CRON` unrestricted | On | On | `resolve_agent_mount` |
| `CRON` restricted | Allow-list | Allow-list | `tools_policy` intersect + `resolve_agent_mount(..., cron_job_tools_allowed=...)` |

## PTC

`apply_ptc_meta_mount` in factory: forces file+shell when MCP present **only if** shell was already enabled (respects Fast / Cron file-only).

## Files

| File | Role |
| --- | --- |
| `surfaces.py` | `ExecutionSurface` enum |
| `resolver.py` | `resolve_agent_mount`, `apply_ptc_meta_mount` |

Persist catalog ID `code_execute` remains in `builtin_tool_ids.AGENT_BASELINE_BUILTIN_TOOLS`; runtime flag is `enable_shell_tools`.
