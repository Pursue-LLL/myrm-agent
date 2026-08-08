# api/openai_compat/

## 架构概述

OpenAI 兼容 `/v1` 聚合路由（Agent API）。上级文档：[../_ARCH.md](../_ARCH.md)。

此端点仅用于 **Agent 执行**（记忆、工具、技能），不提供 LLM 直通代理。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | OpenAI-compatible API endpoints. | ✅ |
| `auth.py` | 模块 | Strict Bearer token auth (SHA-256 hash vs database) | ✅ |
| `completions.py` | 模块 | Agent-only `/v1/chat/completions` (streaming + non-streaming)；端点入口用 `is_safe_session_id` 白名单拒绝非法 `chat_id`（400，防路径穿越，流式/非流式统一提前拒绝） | ✅ |
| `models.py` | 模块 | Lists configured agents as OpenAI-compatible model objects | ✅ |
| `router.py` | 路由 | Aggregates all OpenAI-compatible sub-routers under the /v1 prefix | ✅ |
| `types.py` | 模块 | Type definitions for OpenAI-compatible endpoint request/response serialization | ✅ |
