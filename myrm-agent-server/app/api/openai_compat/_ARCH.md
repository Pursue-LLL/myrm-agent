# api/openai_compat/

## 架构概述

本目录模块说明。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | OpenAI-compatible API endpoints. | ✅ |
| `auth.py` | 模块 | Dual-mode authentication for /v1/* endpoints | ✅ |
| `completions.py` | 模块 | Core implementation. Routes requests to either Agent execution (when model matches an agent ID) or LLM passthrough (when model matches a user-configured LLM). T | ✅ |
| `models.py` | 模块 | Returns both configured agents and user-configured LLM models as OpenAI-compatible model objects. Agents can be used with the Agent execution engine; LLM models | ✅ |
| `passthrough.py` | 模块 | LLM passthrough for the /v1/chat/completions endpoint. When the `model` field matches a user-configured LLM model (e.g. "claude-3.5-sonnet") rather than an Agen | ✅ |
| `router.py` | 路由 | Aggregates all OpenAI-compatible sub-routers under the /v1 prefix. """ | ✅ |
| `types.py` | 模块 | Type definitions for OpenAI-compatible endpoint request/response serialization. """ | ✅ |
