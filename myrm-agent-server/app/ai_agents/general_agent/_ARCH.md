# ai_agents/general_agent 模块架构


---

## 架构概述

通用对话 Agent。提供通用 AI 对话能力，包含专用中间件（引用规则、工具选择）和业务工具集成。通过 `prompt_mode` 支持多模式运行（full/lean/naked/search），其中 search 模式实现快速搜索功能，无需独立的 FastSearchAgent。
历史会话召回在 Server 层装配为 `conversation_search_tool` 工具，Harness 只消费 Protocol，不感知数据库或产品身份语义。
LLM 装配阶段会优先选择支持 function calling 的主模型，避免工具链在不支持工具调用的模型上静默失效。
当前实现会优先消费渠道入口已经解析好的正式身份契约：
- `memory_channel_id`
- `memory_conversation_id`
- `memory_task_id`
- `memory_shared_context_ids`

这些字段由 Control Plane / 渠道入口预先解析后再下传给记忆装配层，分别映射到
`channel/conversation/task/agent` 作用域；仅当入口未提供时，才回退到运行时本地值。
其中 `task_id` 可以直接表达 thread/topic 边界，因此群组 topic、论坛线程、reply thread
不会在 GeneralAgent 这里退化成普通会话。这样 GeneralAgent 负责消费 binding，而不是重新发明外部身份边界。
如果 AgentProfile 定义了正式的 `memory_policy`，GeneralAgent 会把该策略随 binding 一并下传，
由 Harness 统一决定 recall 可见 scope 和私有记忆写入目标，避免在 API、渠道入口、Agent 运行时多处重复拼装策略。
如果入口解析到 Shared Context 绑定，GeneralAgent 只消费 `memory_shared_context_ids`；
Server memory adapter 会将其追加为 `shared:<context_id>` recall namespace，私有写入仍保持在 agent/channel/conversation/task 边界内。
同时，GeneralAgent 会在 server 业务层基于当前 query 和最近的人类消息生成
`compression_intent`，并把 `engine_params`（如 `max_tool_calls`、`max_bash_calls`）随运行时 context 一并下传给 harness 的上下文压缩与工具调用限额策略。
这样可以把“当前用户真正关注哪些文件、模块、目标，以及哪些工具调用刚失败过”保留在业务侧，
不把聊天语义耦合进通用框架。

`_build_runtime_context` 同时将 `workspaces_storage_root` 设为规范化后的 **`database.harness_dir`**，供 Harness `setup_workspace` 与惰性 `WorkspaceService` 对齐同一聚合目录。
---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `agent.py` | ✅ 核心 | GeneralAgent 门面：`_build_runtime_context` 写入 `compression_intent`、`workspaces_storage_root`（规范化 `database.harness_dir`）、`engine_params`、`prompt_mode` 等 Harness 契约字段；懒加载底层引擎。 | ✅ |
| `factory.py` | ✅ 核心 | Agent 实例组装工厂，将所有组件构建为 LangGraph 引擎。`_build_session_cleanup_callback` 组合 commitment extraction 和 correction propagation 两个会话清理回调。通过 AgentExtension 模式注册功能模块。Action Space Opt-In: 根据 UserSkillConfig 传递 `allowed_prebuilt_ids` 白名单给 `create_skill_backend`，根据 `enabled_builtin_tools` 控制 `enable_file_tools`/`enable_bash`/`enable_wiki`，MCP 技能自动注入 PTC 依赖。从 `enable_xxx` 布尔标志推导 `AgentRuntimeSpec.tool_groups` 用于 skill 条件激活过滤。 | ✅ |
| `stream_pipeline.py` | ✅ 核心 | 执行流水线：按 `GeneralAgent.channel_name` 解析 `(channel_label, ingress_label)`，**INFO 记录 `general_agent_delivery_labels`**，再 `apply_delivery_banner` → 处理查询 / 外部委托 / browser checkpoint / `SkillAgent.run` 推流 | ✅ |
| `config_builders.py` | ✅ 核心 | 分离出的配置构建器，包含运行时执行、隐私路由、环境变量解析。 | ✅ |
| `callbacks.py` | ✅ 核心 | 独立的回调函数（commitment extraction、correction propagation）与状态维护逻辑。`make_correction_propagation_callback` 在会话结束时检测纠错信号并自动创建 SharedContext 写入提案。 | ✅ |
| `tool_setup.py` | ✅ 核心 | 工具初始化混入（ToolSetupMixin）。搜索、图片/视频、`_setup_x_live_search_tool`（x-live-search skill → deferred `x_search_tool`，不依赖 enable_web_search）、定时任务、记忆、浏览器、local_browser、交互式澄清、A2UI 等。继承 ExternalAgentsMixin。 | ✅ |
| `external_agents.py` | ✅ 核心 | 外部 Agent 委托层（ExternalAgentsMixin）。RuntimePool 初始化、CLI/ACP/SDK 后端注册、本地自动检测、直接委托流式转发。`_auth_mode` 将前端 `authMode` 贯通到 `RuntimeConfig.auth_mode`（默认 subscription，用自有订阅登录态）；TOKEN_USAGE 事件附带 `auth_mode`/`billable`，订阅委托零计费可见。支持 Deferred 延迟加载。 | ✅ |
| `blueprint_materializer.py` | ✅ 核心 | JIT 虚拟子 Agent 即时物化器，将会话级 `ephemeral_subagents`（含 display_name/theme_color）转换为 `SubagentConfig`。 | ✅ |
| `compression_intent.py` | ✅ 核心 | 从 query + 最近 HumanMessage + 历史 ToolMessage 生成聚焦文件、模块、目标提示、失败工具调用 ID，供 harness 压缩策略消费。 | ✅ |
| `goal_learnings.py` | ✅ 核心 | Goal 终态回调工厂：`build_goal_terminal_callback` 在 Goal 终态时提取 learnings 存入 SemanticMemory，发布 `GOAL_TERMINAL` EventBus 事件（触发 IM 通知），并 dequeue 下一个排队 Goal。`retrieve_relevant_learnings` 为新 Goal 检索历史经验。 | ✅ |
| `conversation_search_setup.py` | ✅ 辅助 | 将 Server 会话历史召回 Provider 绑定到当前 Agent 运行并追加 `conversation_search_tool` 工具。 | ✅ |
| `checkpoint_helpers.py` | ✅ 辅助 | Browser checkpoint 生命周期辅助函数 | ✅ |
| `llm_factory.py` | ✅ 辅助 | LLM 实例工厂（main/filter/fallback/safety_fallback LLM 创建；主模型会优先切换到支持 function calling 的候选模型） | ✅ |
| `agent_middlewares/citation_rules_middleware.py` | ✅ 辅助 | 引用规则中间件；naked/lean 模式跳过注入 |
| `agent_middlewares/tool_selection_middleware.py` | ✅ 核心 | 工具约束中间件 — tool_choice 状态机 + 收敛保护 |
| `tools/_tool_layer_bootstrap.py` | ✅ 核心 | Server 专属工具向 harness _TOOL_LAYERS 的动态注册入口（4 个 SDK 依赖工具） |
| `tools/x_search_provider.py` | ✅ 辅助 | xAI Live Search API 客户端；deferred tool 工厂在 `services/integrations/tools/x_live_search.py` |

---

## 依赖关系

- `myrm_agent_harness/agent/`：Agent 基础实现
- `app/ai_agents/prompts/`：共享提示词
- `app/ai_agents/agent_middlewares/`：共享中间件
- `app/services/chat/conversation_search_service.py`：当前 Agent 运行绑定的历史会话召回 Provider。

## 边界约束

- `compression_intent` 的生成属于 server 业务语义：依赖当前 query、最近用户轮次和产品对“任务重点”的理解。
- harness 只负责消费标准化的 `compression_intent` 并执行通用压缩，不负责推断业务目标。
- harness 的 `conversation_search_tool` 只定义 Protocol/DTO 与工具格式；Server 负责 DB/FTS5/Agent 身份过滤与摘要读取。
- control plane 不生成语义型压缩意图，只负责调度、隔离、资源和运行基础设施。
