# services/agent/backends 模块架构


## 架构概述

Agent 服务后端实现。提供 Secret 管理和 Agent Profile 持久化的数据库实现。
Agent Profile 类型和通用存储后端位于 `myrm_agent_harness.backends.profiles`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 DatabaseSecretBackend, MCPSecretAuthProvider, DatabaseMCPOAuthTokenStore | — |
| `secret_backend.py` | 核心 | Agent Secret 加密管理后端 (AES-256-GCM) | ⚠️ 待补 |
| `mcp_secret_auth.py` | 核心 | MCP 密钥认证提供者，解析 `{{secret:KEY}}` 模板引用，实现 harness 层 MCPAuthProvider 协议 | — |
| `mcp_oauth_store.py` | 核心 | MCP OAuth token 加密持久化，实现 harness 层 MCPOAuthTokenStore 协议。支持 stampede-safe 刷新，同时持久化 OAuth server 配置（token_endpoint/client_id/client_secret）供 token refresh 使用 | ✅ |
| `profile_backend.py` | 核心 | Agent Profile 持久化后端，负责 ORM ↔ AgentProfile 转换与 metadata 读写（含 `engine_params`） | ⚠️ 待补 |
