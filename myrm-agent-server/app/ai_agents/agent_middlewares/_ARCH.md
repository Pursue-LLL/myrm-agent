# ai_agents/agent_middlewares 模块架构


---

## 架构概述

AI Agents 共享中间件。为 GeneralAgent 提供可复用的 LangGraph Agent 中间件。
命名为 `agent_middlewares` 而非 `middlewares`，避免与 FastAPI HTTP 中间件混淆。

---

## 文件清单

| 文件 | 地位 | 职责|
|------|------|------|
| `user_instructions_middleware.py` | ✅ 核心 | 用户指令注入（首次 LLM 调用，标记检测去重，优化缓存） |
| `self_update_prompt_middleware.py` | ✅ 核心 | 智能体自更新指导注入（仅对自定义 Agent 注入 `<self_update>` 指导消息，防变砖、防幻觉，持久化同步） |
| `widget_capability_middleware.py` | ✅ 辅助 | Widget 能力声明注入；naked 模式跳过 |

---

## 框架层中间件

| 中间件 | 路径 | 说明 |
|------|------|------|
| `workspace_rules_middleware` | `myrm_agent_harness.agent.workspace_rules` | Workspace 规则注入（扫描 `.myrm/rules/*.md`，KV Cache 位置优化） |
| `memory_context_middleware` | `myrm_agent_harness.agent.middlewares.memory_context_middleware` | Stable：`<user_memory_context>` SystemMessage；Learned：`<<<UNTRUSTED_DATA>>>` HumanMessage（wrap_untrusted，对齐 SecurityBoundary）；Stable+Learned 共享统一预算 |

`__init__.py` 从框架层导入 `memory_context_middleware` 并统一导出。`workspace_rules_middleware` 由 `GeneralAgent` 直接从框架层导入。

## 中间件注入顺序

```
System Prompt (固定, 跨用户缓存)              ← KV Cache ✅
user_instructions (用户指令, 同用户稳定)        ← KV Cache ✅
self_update (智能体自更新指导词, 同 Agent 稳定)  ← KV Cache ✅ (高效率二级缓存)
workspace_context (工作区规则, 同workspace稳定) ← KV Cache ✅
Stable `<user_memory_context>` (System, 同用户稳定) ← KV Cache ✅；可选 Learned(`<<<UNTRUSTED_DATA>>>` Human advisory)
对话消息...                                   ← 每轮变化
```

---

## 依赖关系

- `langchain.agents.middleware`：中间件基类
- `myrm_agent_harness.agent.workspace_rules`：Workspace 规则中间件（框架层）
- `myrm_agent_harness.agent.middlewares.memory_context_middleware`：记忆中间件（框架层）
- `myrm_agent_harness.toolkits.memory.manager`：MemoryManager（memory_context_middleware 依赖）
- 被 `general_agent/` 使用
