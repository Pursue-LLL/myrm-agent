# desktop_control/

## Overview

Server-side desktop control gate: wires `ForegroundPermissionCallback` into harness `DesktopSession`,
handles per-app first approval (persisted under chat workspace volume), and emits SSE approval cards.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `gate.py` | Core | `DesktopControlGate` callback + `DesktopApprovalRegistry` + resolve helper. Empty `app_name` is fail-closed (never preapproved). Persists always-approved apps to `{workspace}/.agent/desktop_control/approved_apps.json` | ✅ |

## Dependencies

- `myrm_agent_harness.toolkits.computer_use` (ForegroundPermissionCallback, ExecutionMode)
- `myrm_agent_harness.utils.runtime.progress_sink` (SSE emit during tool execution)
- `app.ai_agents.general_agent.tool_setup` (session wiring)
- `app.api.webui.router` (`POST /webui/desktop/approval/resolve`)
