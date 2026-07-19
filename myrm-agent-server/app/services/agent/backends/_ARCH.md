# services/agent/backends/

## 架构概述

Agent Profile/Secret 持久化后端。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 公共导出（`profile_backend` 等按需直引子模块，非 barrel 全量 re-export） | ✅ |
| `mcp_oauth_store.py` | 核心 | MCP OAuth token 加密持久化 | ✅ |
| `mcp_secret_auth.py` | 核心 | MCP secret-aware 认证 Provider | ✅ |
| `profile_backend.py` | 核心 | Database-backed `AgentProfileBackend`；`enabled_builtin_tools` 写路径与 `agent_repo` 共用 `persist_enabled_builtin_tools` | ✅ |
| `secret_backend.py` | 核心 | Database-backed `AgentSecretBackend` | ✅ |
