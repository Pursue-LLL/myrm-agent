# api/agents/general_agent/

## 架构概述

GeneralAgent 流式对话、重连与离线 durable 任务 HTTP 层。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | General Agent package. | ✅ |
| `active_sessions.py` | 模块 | General Agent API — autonomous decision-making agent with streaming SSE. | ✅ |
| `clarify.py` | 模块 | General Agent API — autonomous decision-making agent with streaming SSE. | ✅ |
| `media_config.py` | 模块 | General Agent API — autonomous decision-making agent with streaming SSE. | ✅ |
| `streaming.py` | 模块 | General Agent API — HTTP/SSE transport for streaming agent execution. | ✅ |
| `suggestions.py` | 模块 | General Agent API — autonomous decision-making agent with streaming SSE. | ✅ |
