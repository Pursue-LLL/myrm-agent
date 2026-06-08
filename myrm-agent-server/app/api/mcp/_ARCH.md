# api/mcp/

## 架构概述

记忆系统 Streamable HTTP MCP 端点（挂载于 `/mcp`）。Bearer Token 鉴权 via ConnectService；lifespan 手动管理 session manager。

上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `endpoint.py` | 核心 | `setup_mcp_endpoint` / `shutdown_mcp_endpoint` + Token ASGI 中间件 | ✅ |
