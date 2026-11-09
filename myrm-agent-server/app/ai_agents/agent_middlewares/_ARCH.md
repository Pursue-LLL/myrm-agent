# ai_agents/agent_middlewares 模块架构


---

## 架构概述

AI Agents 共享中间件。为 GeneralAgent 提供可复用的 LangGraph Agent 中间件。
命名为 `agent_middlewares` 而非 `middlewares`，避免与 FastAPI HTTP 中间件混淆。

---

## 文件清单

| 文件 | 地位 | 职责|
|------|------|------|
| `user_instructions_middleware.py` | ✅ 核心 | 用户指令注入（每次模型调用把 context 里的指令作为 System 块插入请求副本，不写回线程状态；审批/计划确认的续跑请求不带指令，沿用 `before_agent` 记在图状态里的快照；在前 5 条消息的 System 消息里按 `<user_instructions` 标记去重，优化缓存）；必须先于 `memory_context_middleware` 挂载，见「中间件注入顺序」 |
| `project_roadmap_middleware.py` | ✅ 核心 | 项目路线图注入（从 DB 加载 project milestones，首次 LLM 调用注入 `<project_roadmap>` SystemMessage） |
| `widget_capability_middleware.py` | ✅ 辅助 | Widget 能力声明注入；是否挂载由 `mount_resolver.mount_widget_capability` 决定（只有 web_chat 渠道的 full / lean 模式挂） |

---

## 框架层中间件

| 中间件 | 路径 | 说明 |
|------|------|------|
| `workspace_rules_middleware` | `myrm_agent_harness.agent.workspace_rules` | Workspace 上下文注入（实时读取项目规则文件，沙箱快照按对话线程取一次，KV Cache 位置优化） |
| `memory_context_middleware` | `myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware` | `<user_memory_context>` SystemMessage：只含用户存储的记忆，存储值先把标签起始符改写为 `&lt;`，一份预算；已学习的事实不进块，由 `memory_search_tool` 检索；块只存在于请求里，每次模型调用按本轮记忆上下文（预取快照，或本轮读一次的 manager 上下文）重建，不写回线程状态，靠消息标记 `memory_context` 识别 |
| `proactive_pack_middleware` | `myrm_agent_harness.agent.middlewares.memory_context.proactive_pack_middleware` | 当轮知识包：把 server 按问题检索的片段（运行上下文键 `PROACTIVE_PACK_CONTEXT_KEY`）包成不可信数据信封，追加到最后一条 HumanMessage 的尾部；随记忆开关（无 memory manager 或 `RecallMode.TOOLS` 不注入）；不写入线程，不动 System 与此前历史；工厂里先于会话覆盖 deltas 挂载 |
| `ephemeral_delta_middleware` | `myrm_agent_harness.agent.middlewares.memory_context.ephemeral_delta_middleware` | 会话覆盖 deltas：把会话级覆盖（`toolkits.memory.ephemeral_delta` 的共享存储）追加到最后一条 HumanMessage 的尾部，只改尾部，不动 System 前缀；在 `memory_context_middleware` 之后运行 |

`__init__.py` 从框架层导入 `memory_context_middleware`、`ephemeral_delta_middleware`、`proactive_pack_middleware` 与 `PROACTIVE_PACK_CONTEXT_KEY` 并统一导出。`workspace_rules_middleware` 由 `GeneralAgent` 直接从框架层导入。

## 中间件注入顺序

```
System Prompt (固定, 跨用户缓存)              ← KV Cache ✅
user_instructions (用户指令, 同用户稳定)        ← KV Cache ✅
project_scoped_workspace (项目作用域边界, 同项目稳定) ← KV Cache ✅
workspace_context (工作区规则与沙箱快照, 同对话线程稳定) ← KV Cache ✅
project_roadmap (项目路线图, 同项目稳定)       ← KV Cache ✅
`<user_memory_context>` (System, 同用户稳定) ← KV Cache ✅
对话消息...                                   ← 每轮变化
当轮最后一条用户消息的尾部：知识包片段 → 会话覆盖 deltas ← 只改这一条，此前内容逐字节不变
```

**挂载顺序契约**：`user_instructions_middleware` 在前 5 条消息的 System 消息里按 `<user_instructions` 标记判断指令是否已注入，而记忆块的作用域说明里点名了 `<user_instructions>`。记忆中间件先于它挂载时，指令中间件会把记忆块当成自己的块，用户指令不再注入。工厂里 `user_instructions_middleware` 排在 `memory_context_middleware` 之前；`tests/ai_agents/general_agent/test_instructions_and_memory_block_order.py` 读工厂的挂载列表确认这个顺序，并在真实的 `create_agent` 图上检查每次模型调用里用户指令与记忆块各恰好出现一次。

---

## 依赖关系

- `langchain.agents.middleware`：中间件基类
- `myrm_agent_harness.agent.workspace_rules`：Workspace 规则中间件（框架层）
- `myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware`：记忆中间件（框架层）
- `myrm_agent_harness.toolkits.memory.manager`：MemoryManager（memory_context_middleware 依赖）
- 被 `general_agent/` 使用
