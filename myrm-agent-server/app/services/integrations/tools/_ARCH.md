# services/integrations/tools/

## 架构概述

Skill-gated integration tool factories. Credentials come from session context, not static config.
`x_live_search.py` registers via `tool_setup._setup_x_live_search_tool` on skill_ids only (independent of Agent Web Search).

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `x_live_search.py` | 模块 | x-live-search prebuilt skill LangChain tool factory (xAI credentials via session_credential_assembler). Registered by `tool_setup._setup_x_live_search_tool` on skill_ids only | ✅ |
