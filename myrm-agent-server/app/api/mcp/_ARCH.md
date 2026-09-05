# api/mcp/

## 架构概述

MCP 服务注册与健康 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | MCP memory endpoint mount helpers. | ✅ |
| `endpoint.py` | 模块 | Exposes the memory system as a stateless Streamable HTTP MCP endpoint with per-token agent scoping. Bearer token resolves agent_id via ConnectService; middleware binds MemoryManager and wiki boundary flag (when agent profile enables wiki) via ContextVar. Stateless mode eliminates Mcp-Session-Id tracking since all tools are inherently per-request. | ✅ |
| `origin_guard.py` | 守卫 | DNS-rebinding and origin validation ASGI middleware and helper for local Streamable HTTP / SSE MCP transports. | ✅ |
