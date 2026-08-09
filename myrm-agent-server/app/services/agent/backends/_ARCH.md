# services/agent/backends/

## 架构概述

Agent Profile/Secret 持久化后端。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 公共导出（MCP OAuth / secret backends；Agent profile CRUD 经 `AgentRepository`） | ✅ |
| `mcp_oauth_store.py` | 核心 | MCP OAuth token 加密持久化；跨 server 原子写（全局 persist lock）+ 断开防复活守卫（save_token 写回前校验 server 仍存在，in-flight 刷新不复活已断开 server） | ✅ |
| `mcp_secret_auth.py` | 核心 | MCP secret-aware 认证 Provider | ✅ |
| `secret_backend.py` | 核心 | Database-backed `AgentSecretBackend` | ✅ |
| `mcp_elicitation_handler.py` | 核心 | MCP Elicitation (MRTR) → ApprovalRegistry 桥接。`build_mcp_elicitation_handler` 工厂返回符合 harness 协议的 async handler，通过 `ApprovalRegistry` 创建审批记录并推送 SSE 事件到前端，`asyncio.Event` 挂起等待用户决策；`resolve_pending_elicitation` 由 approval resolve API 调用以唤醒挂起的 handler。 | ✅ |
