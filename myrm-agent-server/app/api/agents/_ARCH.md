# api/agents/

## 架构概述

Agent 产品 HTTP 层：用户自定义智能体 CRUD、GeneralAgent 流式对话入口、子 Agent 预设、Provider 配置与 OpenAPI 服务发现。上级：[../_ARCH.md](../_ARCH.md) · 流式核心：[general_agent/_ARCH.md](general_agent/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | AI Agent API 模块 | ✅ |
| `agent.py` | 核心 | Agent 核心 CRUD、快照/回滚、Avatar 上传、文件服务。 | ✅ |
| `_agent_response.py` | 内部 | AgentProfile → AgentResponse 序列化工具函数（被 agent/portability/templates 共享）。 | ✅ |
| `agent_extras.py` | 核心 | Agent 辅助端点：Secrets CRUD、使用统计、动作空间 ASCS 评估。 | ✅ |
| `agent_portability.py` | 核心 | Agent 可移植性：导出/导入/克隆/Marketplace 级跨沙箱分发。 | ✅ |
| `agent_history.py` | 模块 | Get the version history of an agent's profile. | ✅ |
| `ai_build.py` | 模块 | AI-driven agent config generator: accepts a natural-language intent, streams a complete AgentCreate-compatible JSON (name, prompt, skills, MCPs, tools) | ✅ |
| `generate_prompt.py` | 模块 | Thin API for the agent editor: resolves the user's default model and streams a draft system prompt | ✅ |
| `media.py` | 模块 | Request to test media generation configuration connectivity. | ✅ |
| `openapi_services.py` | 模块 | OpenAPI Services API. | ✅ |
| `providers.py` | 模块 | Agent provider configuration endpoints for deletion impact analysis and batch operations | ✅ |
| `subagents.py` | 模块 | Subagent REST：list / cancel-all / steer / cancel / resume；registry merge via harness session_tree。 | ✅ |
| `suggestions.py` | 模块 | Generate follow-up question suggestions using the filter model. | ✅ |
| `fleet_overview.py` | 模块 | Agent Fleet Overview — 按 agent_id 聚合月度 Token/Cost、Cron 数、待审批数、实时运行状态的 KPI 端点，供 /agents 页面 Fleet 视图使用。零新表，纯读聚合。 | ✅ |
| `templates.py` | 模块 | Agent template catalog and factory. | ✅ |
| `profile_audit.py` | 模块 | Agent Profile security audit: POST /{agent_id}/audit — deterministic risk scoring via harness profile_audit engine. | ✅ |
| `readiness.py` | 模块 | Per-agent readiness dry-run: GET /{agent_id}/readiness + POST /{agent_id}/readiness/invalidate — 6-dimension config readiness check. | ✅ |
