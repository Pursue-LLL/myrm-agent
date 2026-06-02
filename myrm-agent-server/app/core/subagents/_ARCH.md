# app/core/subagents 模块架构


---

## 架构概述

子 Agent 在 Server 侧的横切能力：将 Harness 的 `ModelResolver` 与业务层模型解析（LiteLLM / complexity router）衔接，实现按任务复杂度路由子 Agent 所用模型。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `resolver.py` | ✅ 核心 | `SubagentModelResolver`：实现 Harness `ModelResolver`，按复杂度与会话信息解析 `BaseChatModel` | ✅（见文件头 INPUT/OUTPUT/POS） |

---

## 依赖关系

**内部依赖**：
- `app.core.channel_bridge.model_resolver`：业务层统一模型配置解析

**外部（框架）依赖**：
- `myrm_agent_harness.agent.sub_agents.types::ModelResolver`
- `myrm_agent_harness.toolkits.llms.routing.complexity_router::route_task`

**被依赖**：
- `app/ai_agents/` 等装配子 Agent 的流程（通过 Harness 回调/解析链间接使用）
