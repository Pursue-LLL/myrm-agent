# services/agent/backends/

## 架构概述

Agent Profile/Secret 持久化后端。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 公共导出（MCP OAuth / secret backends；Agent profile CRUD 经 `AgentRepository`） | ✅ |
| `mcp_oauth_store.py` | 核心 | MCP OAuth token 加密持久化 | ✅ |
| `mcp_secret_auth.py` | 核心 | MCP secret-aware 认证 Provider | ✅ |
| `secret_backend.py` | 核心 | Database-backed `AgentSecretBackend` | ✅ |
