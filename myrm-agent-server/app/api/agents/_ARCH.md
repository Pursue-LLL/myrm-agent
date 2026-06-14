# api/agents/

## 架构概述

Agent 产品 HTTP 层：用户自定义智能体 CRUD、GeneralAgent 流式对话入口、子 Agent 预设、Provider 配置、Harness Task-Adaptive 桥与 OpenAPI 服务发现。上级：[../_ARCH.md](../_ARCH.md) · 流式核心：[general_agent/_ARCH.md](general_agent/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | AI Agent API 模块 | ✅ |
| `agent.py` | 模块 | 用户自定义智能体 HTTP 入口。GUI-first 配置 SSOT 的 API 层。 | ✅ |
| `agent_history.py` | 模块 | Get the version history of an agent's profile. | ✅ |
| `ai_build.py` | 模块 | AI-driven agent config generator: accepts a natural-language intent, streams a complete AgentCreate-compatible JSON (name, prompt, skills, MCPs, tools) | ✅ |
| `generate_prompt.py` | 模块 | Thin API for the agent editor: resolves the user's default model and streams a draft system prompt | ✅ |
| `harness_router.py` | 模块 | Harness integration APIs for Task-Adaptive Context. | ✅ |
| `media.py` | 模块 | Request to test media generation configuration connectivity. | ✅ |
| `openapi_services.py` | 模块 | OpenAPI Services API. | ✅ |
| `providers.py` | 模块 | Agent provider configuration endpoints for deletion impact analysis and batch operations | ✅ |
| `routing_api.py` | 模块 | Get health analysis for a specific provider based on recent event logs. | ✅ |
| `session.py` | 模块 | Cancel an active agent request by message ID. | ✅ |
| `subagents.py` | 模块 | Attach persisted teammate mailbox rows onto subagent list entries. | ✅ |
| `suggestions.py` | 模块 | Generate follow-up question suggestions using the filter model. | ✅ |
| `templates.py` | 模块 | Agent template catalog and factory. | ✅ |
