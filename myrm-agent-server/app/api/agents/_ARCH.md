# api/agents/

## 架构概述

Agent 产品 HTTP 层：用户自定义智能体 CRUD、GeneralAgent 流式对话入口、子 Agent 预设、Provider 配置、OpenAPI 服务发现与沟通风格目录。上级：[../_ARCH.md](../_ARCH.md) · 流式核心：[general_agent/_ARCH.md](general_agent/_ARCH.md) · 沟通风格目录：[personality/_ARCH.md](personality/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | AI Agent API 模块 | ✅ |
| `agent.py` | 核心 | Agent 核心 CRUD、快照/回滚、Avatar 上传、文件服务。创建与更新前，档案里模型会读的文字（`system_prompt`、`description`、建议提示词、命令绑定的指令）经 `reject_if_risky` 过闸，命中返回 400 `risk_held`、不落库；责任单元的 `responsibility_scope` / `acceptance_criteria` 只用于治理展示，不过闸。 | ✅ |
| `_agent_response.py` | 内部 | AgentProfile → AgentResponse 序列化工具函数（被 agent/portability/templates 共享）。 | ✅ |
| `agent_extras.py` | 核心 | Agent 辅助端点：Secrets CRUD、使用统计、动作空间 ASCS 评估与 Turn1 技能目录预览（元数据经 `runtime_metadata.skill_to_runtime_metadata` 适配，技能可用性与 Agent runtime 共用 `requirements_availability` 判定）。 | ✅ |
| `agent_portability.py` | 核心 | Agent 可移植性：克隆、Marketplace 跨沙箱分发（导出/导入）。专家之间交换只走 Agent Plugins ZIP（`/plugins/export`、`/plugins/import`），JSON 导入导出与工作区文件束已退役。 | ✅ |
| `agent_history.py` | 模块 | Get the version history of an agent's profile. | ✅ |
| `ai_build.py` | 模块 | AI-driven agent config generator: accepts a natural-language intent, streams a complete AgentCreate-compatible JSON (name, prompt, skills, MCPs, tools); without a usable model it refuses with 422 `{message, error_code: model_not_configured}` so the client can localize it; the intent is screened by the risk gate before the model is resolved (400 `risk_held`); the skill catalog offered to the model lists the installed skills whose dependencies are met (`Skill.available`) | ✅ |
| `generate_prompt.py` | 模块 | Thin API for the agent editor: resolves the user's default model and streams a draft system prompt; the intent and the existing prompt to refine are screened by the risk gate first (400 `risk_held`) | ✅ |
| `openapi_services.py` | 模块 | OpenAPI Services API. | ✅ |
| `providers.py` | 模块 | Agent provider configuration endpoints for deletion impact analysis and batch operations | ✅ |
| `subagents.py` | 模块 | Subagent REST：list / cancel-all / steer / cancel；registry merge via harness session_tree；steer 的消息先过风险闸门（`reject_if_risky`，命中 400 `risk_held`，不送达子智能体）。 | ✅ |
| `suggestions.py` | 模块 | Generate follow-up question suggestions using the filter model. The prompt treats the conversation as untrusted data, forbids suggesting permission grants, approvals, credential sharing or destructive commands, and lets the model answer `[]` when the last message only closes the conversation (a valid reply that offers nothing). The reply is validated like user input (strict JSON-string array, or an unmistakable marked list that is not a reasoning trace; labels 3–120 visible chars, no hidden/control characters, distinct, at most 3) because a click sends the label as the user's own message; the call has a fixed cost envelope (`max_tokens` 1024 with the thinking-model output floor off, last 6 messages each masked then clipped to head 1000 + tail 500 chars); a reply that carries no usable label is logged by its length only. | ✅ |
| `fleet_overview.py` | 模块 | Agent Fleet Overview — 按 agent_id 聚合月度 Token/Cost、Cron 数、待审批数（goal 审批 + kanban IN_REVIEW 按 agent 分组）、实时运行状态的 KPI 端点，供 /agents 页面 Fleet 视图使用。零新表，纯读聚合。 | ✅ |
| `templates.py` | 模块 | Agent template catalog and factory. | ✅ |
| `subagent_presets/` | 子包 | 只读子代理预设目录 `GET /agents/subagent-presets`：返回 Agent 编辑器可绑定的内置专家元数据（id/名称/描述/依赖 builtin tool），不返回 system prompt。 | ✅ |
| `personality/` | 子包 | 通信风格目录（只读）：`GET /agents/personalities` 返回 17 个预置风格的中英双语名称/描述/示例回复、GUI 图标标识与分类。目录本体在 `ai_agents/personality_templates.py`，本子包只做序列化，前端不再维护第二份风格清单。 | ✅ |
| `profile_audit.py` | 模块 | Agent Profile security audit: POST /{agent_id}/audit — deterministic risk scoring via harness profile_audit engine. | ✅ |
| `readiness.py` | 模块 | Per-agent readiness dry-run: GET /{agent_id}/readiness + POST /{agent_id}/readiness/invalidate — 6-dimension config readiness check. | ✅ |
| `governance.py` | 模块 | Responsibility-unit governance: GET /governance/overview（孤儿/重叠只读巡检，零 LLM）+ POST /governance/merge/dry-run + POST /governance/merge/execute（快照→并配置→重绑定时/渠道→删来源复用级联）。 | ✅ |
| `recovery.py` | 模块 | Agent profile startup recovery: GET /agents/{agent_id}/recovery/health（组件健康探针）+ POST /agents/{agent_id}/recovery/rollback（回滚到 last-known-good 快照）+ GET /agents/{agent_id}/recovery/diagnostics（导出排障诊断包）。 | ✅ |







