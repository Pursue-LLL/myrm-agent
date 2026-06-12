# agent-config-panel/

## Overview

Agent profile editing UI: skills, MCP, built-in tools, browser options, security overrides.

## File Index

| File | Role | Description |
|------|------|-------------|
| `AgentConfigEditDialog.tsx` | Core | Full-screen/sheet editor; persists `enabled_builtin_tools` (incl. `render_ui`) to server metadata |
| `AgentConfigPanel.tsx` | Core | Panel shell and preset shortcuts |
| `AgentConfigCards.tsx` | Core | Summary cards for active agent |
| `AgentBrickCard.tsx` | Core | Compact agent brick with tool badges |

## Built-in tools

Tool IDs are defined in `@/store/chat/types/builtinTools.ts` and must stay in sync with server `resolve_builtin_tool_flags()` in `profile_resolver.py`.
