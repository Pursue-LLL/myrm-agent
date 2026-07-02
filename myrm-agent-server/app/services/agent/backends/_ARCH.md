# services/agent/backends/

## 架构概述

Agent Profile/Secret 持久化后端。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Database-backed agent backend implementations. | ✅ |
| `mcp_oauth_store.py` | 模块 | MCP OAuth token encrypted persistence. | ✅ |
| `mcp_secret_auth.py` | 模块 | MCP secret-aware authentication provider. | ✅ |
| `profile_backend.py` | 模块 | Database-backed AgentProfileBackend；`enabled_builtin_tools` 写路径与 `agent_repo` 共用 `persist_enabled_builtin_tools` | ✅ |
| `secret_backend.py` | 模块 | Database-backed implementation of AgentSecretBackend. | ✅ |
