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
| `project_roadmap_middleware.py` | ✅ 核心 | 项目路线图注入（从 DB 加载 project milestones，首次 LLM 调用注入 `<project_roadmap>` SystemMessage） |
| `widget_capability_middleware.py` | ✅ 辅助 | Widget 能力声明注入；naked 模式跳过 |

---

## 框架层中间件

| 中间件 | 路径 | 说明 |
|------|------|------|
| `workspace_rules_middleware` | `myrm_agent_harness.agent.workspace_rules` | Workspace 上下文注入（实时读取项目规则文件，沙箱快照按对话线程取一次，KV Cache 位置优化） |
| `memory_context_middleware` | `myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware` | Stable：`<user_memory_context>` SystemMessage；Learned：`<<<UNTRUSTED_DATA>>>` HumanMessage（wrap_untrusted，对齐 SecurityBoundary）；Stable+Learned 共享统一预算 |
| `proactive_pack_middleware` | `myrm_agent_harness.agent.middlewares.memory_context.proactive_pack_middleware` | 当轮知识包：把 server 按问题检索的片段（运行上下文键 `PROACTIVE_PACK_CONTEXT_KEY`）包成不可信数据信封，追加到最后一条 HumanMessage 的尾部；随记忆开关（无 memory manager 或 `RecallMode.TOOLS` 不注入）；不写入线程，不动 System 与此前历史；工厂里先于会话覆盖 deltas 挂载 |
| `ephemeral_delta_middleware` | `myrm_agent_harness.agent.middlewares.memory_context.ephemeral_delta_middleware` | 会话覆盖 deltas：把会话级覆盖（`toolkits.memory.ephemeral_delta` 的共享存储）追加到最后一条 HumanMessage 的尾部，只改尾部，不动 System 前缀；在 `memory_context_middleware` 之后运行 |
| `two_layer_context_middleware` | `myrm_agent_harness.agent.middlewares.memory_context.two_layer_context_middleware` | 两层注入的第一层：`TwoLayerContextInjector` 按节奏生成 `<base_context>`（会话笔记摘要，笔记摘要未就绪时取最近至多 6 条对话的摘录），追加到最后一条 HumanMessage 的尾部；图片块原样保留，文字问题上的旧块被替换而不叠加；第二层辩证块在实时路径关闭；在会话覆盖 deltas 之后运行，默认开（`MYRM_TWO_LAYER_CONTEXT_LIVE=0` 关闭） |

`__init__.py` 从框架层导入 `memory_context_middleware`、`ephemeral_delta_middleware`、`two_layer_context_middleware`、`proactive_pack_middleware` 与 `PROACTIVE_PACK_CONTEXT_KEY` 并统一导出。`workspace_rules_middleware` 由 `GeneralAgent` 直接从框架层导入。

## 中间件注入顺序

```
System Prompt (固定, 跨用户缓存)              ← KV Cache ✅
user_instructions (用户指令, 同用户稳定)        ← KV Cache ✅
project_scoped_workspace (项目作用域边界, 同项目稳定) ← KV Cache ✅
workspace_context (工作区规则与沙箱快照, 同对话线程稳定) ← KV Cache ✅
project_roadmap (项目路线图, 同项目稳定)       ← KV Cache ✅
Stable `<user_memory_context>` (System, 同用户稳定) ← KV Cache ✅；可选 Learned(`<<<UNTRUSTED_DATA>>>` Human advisory)
对话消息...                                   ← 每轮变化
当轮最后一条用户消息的尾部：知识包片段 → 会话覆盖 deltas → `<base_context>`（两层注入，默认开） ← 只改这一条，此前内容逐字节不变
```

---

## 依赖关系

- `langchain.agents.middleware`：中间件基类
- `myrm_agent_harness.agent.workspace_rules`：Workspace 规则中间件（框架层）
- `myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware`：记忆中间件（框架层）
- `myrm_agent_harness.toolkits.memory.manager`：MemoryManager（memory_context_middleware 依赖）
- 被 `general_agent/` 使用
