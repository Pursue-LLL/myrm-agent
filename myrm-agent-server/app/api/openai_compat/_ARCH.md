# api/openai_compat/

## 架构概述

OpenAI 兼容 `/v1` 聚合路由（chat/completions 等）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | OpenAI-compatible API endpoints. | ✅ |
| `auth.py` | 模块 | Dual-mode authentication for /v1/* endpoints | ✅ |
| `completions.py` | 模块 | Core implementation. | ✅ |
| `models.py` | 模块 | Returns both configured agents and user-configured LLM models as OpenAI-compatible model objects. | ✅ |
| `passthrough.py` | 模块 | LLM passthrough with Combo multi-provider routing (priority/round_robin/random strategies), CredentialPool key failover, Vision Bridge guardrail, SSRF guard (deploy-mode-aware). | ✅ |
| `router.py` | 路由 | Aggregates all OpenAI-compatible sub-routers under the /v1 prefix | ✅ |
| `types.py` | 模块 | Type definitions for OpenAI-compatible endpoint request/response serialization | ✅ |
| `vision_bridge.py` | 模块 | Vision Bridge guardrail: intercepts image-bearing Passthrough requests destined for non-vision models, uses VisionFallbackEngine to describe images as text (fail-open) | ✅ |
