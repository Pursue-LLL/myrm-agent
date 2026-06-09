# api/mcp/

## 架构概述

MCP 服务注册与健康 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | MCP memory endpoint mount helpers. | ✅ |
| `endpoint.py` | 模块 | Exposes the memory system as a Streamable HTTP MCP endpoint that external agents (Claude Code, Cursor, etc.) can connect to. | ✅ |
