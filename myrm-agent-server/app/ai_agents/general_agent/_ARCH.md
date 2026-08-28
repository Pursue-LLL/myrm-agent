# ai_agents/general_agent 模块架构


---

## 架构概述

通用对话 Agent。提供通用 AI 对话能力，包含专用中间件（引用规则、工具选择）和业务工具集成。通过 `prompt_mode` 支持多模式运行（full/lean/naked/search），其中 search 模式实现快速搜索功能，无需独立的 FastSearchAgent；Fast Turn1 为 web_search + web_fetch + UECD 只读 file_read + answer_tool（+ memory），browser 仅 profile `browser` 开关 opt-in。
历史会话召回在 GeneralAgent、Custom 与 Ephemeral JIT 子 Agent 均通过 `memory_search_tool(corpus=sessions)` ACL 启用（用户设置 `memoryEnableConversationSearch`，默认关闭；无痕模式禁用 sessions corpus）。Harness 只消费 Protocol，不感知数据库或产品身份语义。
LLM 装配阶段尊重用户在 WebUI 选择的主模型；不支持工具调用或 provider 报错时，由 harness `stream_recovery` 在运行时切换至备用模型（需用户配置 fallback）。
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
| `agent.py` | ✅ 核心 | GeneralAgent 门面：`release_pooled_session()` 释放 per-turn 资源但不关闭池化 SkillAgent/Browser；`close()` 全量 teardown | ✅ |
| `mount_resolver.py` | ✅ 核心 | 渠道与 Profile 工具物理挂载解析器（`resolve_agent_mount`）：对齐 IM 渠道安全边界，剥离 Browser/Desktop/CLI 物理实例化与桌面控制提示词，根除 Token 浪费与工具幻觉被拒。 | ✅ |
| `factory.py` | ✅ 核心 | Agent 实例组装工厂…Org Model Policy：build 时薄委托 `services/org_model_policy/enforce.enforce_org_model_policy()` 检查 primary/fallback 及 **`moa_overlay.reference_model_selections`**（fail-closed sandbox；无 policy 则放行）。LLM 后处理：`apply_lite_context_downgrade` → `apply_lite_managed_fallback`。系统提示词装配支持挂载工作区（`session_access_roots`）稳定字典序排序注入 `[Mounted Workspace Directories]`。经 `mount_resolver` 裁决物理工具挂载与 Prompt 注入。 | ✅ |
| `active_tool_groups.py` | ✅ 核心 | GeneralAgent enable 标志 → harness `TOOL_GROUP_MAP` 组名列表（Gap + `AgentRuntimeSpec.tool_groups`）。 | ❌ |
| `kanban_tool_mode.py` | ✅ 辅助 | 解析 `KanbanToolMode`：TaskRunner 强制 worker（6）；chat 默认 orchestrator（3）；board CRUD 仅 REST/GUI | ❌ |
| `stream_pipeline.py` | ✅ 核心 | 执行流水线：POOLED 路径经 `coalesced_acquire` 复用 `BuiltExecutionUnit`；acquire 后 emit `turn_prewarm_*_clear`（agent：`still_warming`；memory：`brief_pending` 时 dismiss waiting）；`guard_turn` 串行同 chat；按 `channel_name` 解析 delivery banner → browser checkpoint → `SkillAgent.run`。当 `context["goal_provider"]` 存在时注入 `on_goal_terminal`/`on_loop_restart` 回调与相关 learnings 充实（回调注入只依赖 goal_provider，不再依赖 memory_manager；`on_goal_terminal` 传入 `privacy_deep_scan` 启用 learnings 深度 PII 扫描） | ✅ |
| `config_builders.py` | ✅ 核心 | 分离出的配置构建器，包含运行时执行、隐私路由、环境变量解析。 | ✅ |
| `callbacks.py` | ✅ 核心 | 会话清理与持久化回调：`make_commitment_extraction_callback`、`make_correction_propagation_callback`（两阶段隐式反馈检测 → 结构化纠错提案 → 双目标路由 PendingMemory/SharedContext）、`make_loaded_skills_persist_callback`（turn-end 写入 `Chat.session_loaded_skill_names`）、`make_notes_persist` / `make_notes_load`、`make_summary_persist_with_wiki_archive`（compaction persist 后 Wiki 归档，绑 `on_summary_persist`）。 | ✅ |
| `tool_setup.py` | ✅ 核心 | 工具初始化混入（ToolSetupMixin）；GeneralAgent 工具装配；`_create_memory_tools` 绑定 `memory_search_tool` sessions/wiki ACL；`factory.py` 条件挂载 `skill_market_tool` / `skill_manage_tool`。 | ✅ |
| `external_agents.py` | ✅ 核心 | 外部 Agent 委托层（ExternalAgentsMixin）。RuntimePool 初始化、CLI/ACP/SDK 后端注册、本地自动检测（请求热路径 `detect(include_version=False)`）、直接委托流式转发。挂载 `invoke_acp_agent_tool` 时注入 `external_agent_workdir`（与 executor workspace 对齐）与 `session_scope=chat_id`。`needs_runtime_pool()` / `should_mount_invoke_acp_agent_tool()` 门控；chat scope 经 `runtime_pool_registry` 复用 pool + Facade turn lock。RuntimePool fingerprint 对齐 `RuntimeConfig` 关键字段（含 `env/cwd/timeout/maxResponseChars/permissionMode/maxTurns`）。 | ✅ |
| `external_agents_runtime_config.py` | ✅ 核心 | 外部 Agent 配置归一化层。集中 `_default_cli_args` / `_auth_mode` / `_cfg_int`、RuntimeConfig 对齐指纹、本地 auto-detect 配置解析、RuntimePool backend 注册，供 `external_agents.py` 复用。 | ✅ |
| `blueprint_materializer.py` | ✅ 核心 | JIT 虚拟子 Agent 即时物化器，将会话级 `ephemeral_subagents`（含 display_name/theme_color）转换为 `SubagentConfig`。 | ✅ |
| `compression_intent.py` | ✅ 核心 | 从 query + 最近 HumanMessage + 历史 ToolMessage 生成聚焦文件、模块、目标提示、失败工具调用 ID，供 harness 压缩策略消费。 | ✅ |
| `goal_learnings.py` | ✅ 核心 | Goal 终态回调工厂：`build_goal_terminal_callback` 在 Goal 终态时提取 learnings 存入 SemanticMemory（`memory_manager` 可选，memory 关闭时跳过提取但 dequeue 仍执行），`deep_scan=True` 时 learnings 经 LLM 深度 PII 假名化后入库（对齐会话记忆隐私承诺）；发布 `GOAL_TERMINAL` ServerEventBus 事件（触发 IM 通知），并 dequeue 下一个排队 Goal。`retrieve_relevant_learnings` 为新 Goal 检索历史经验。 | ✅ |
| `checkpoint_helpers.py` | ✅ 辅助 | Browser checkpoint 生命周期辅助函数 | ✅ |
| `llm_factory.py` | ✅ 辅助 | LLM 实例工厂（main/lite/fallback/safety_fallback；ManagedLLM 包装 main/lite；**stream_fallback_llm** 供 StreamExecutor；`apply_lite_context_downgrade` 返回 effective lite cfg；`apply_lite_managed_fallback` 在 downgrade 后包装 lite） | ✅ |
| `mcp_vault_handler.py` | ✅ 辅助 | Server 层 MCP 大结果 vault spill handler 工厂。`build_mcp_vault_handler(workspace_root)` 返回 `OversizedResultHandler` 闭包，在 `factory.py` 注入到 MCP 配置，使 harness `_timeout_wrapper` 将超量结果持久化至 ArtifactVault 而非截断丢弃。 | ✅ |
| `agent_middlewares/citation_rules_middleware.py` | ✅ 辅助 | 引用规则中间件；naked/lean 模式跳过注入 |
| `agent_middlewares/tool_selection_middleware.py` | ✅ 核心 | 工具约束中间件 — tool_choice 状态机 + 收敛保护 |
| `tools/_tool_layer_bootstrap.py` | ✅ 核心 | Server 专属工具向 harness `_TOOL_LAYERS` 注册（x_search、channel_notify、image/video/tts media 工具） |
| `tools/x_search_provider.py` | ✅ 辅助 | xAI Live Search API 客户端；skill 绑定后 eager tool 工厂在 `services/integrations/tools/x_live_search.py` |

---

## 依赖关系

- `myrm_agent_harness/agent/`：Agent 基础实现
- `app/ai_agents/prompts/`：共享提示词
- `app/ai_agents/agent_middlewares/`：共享中间件
- `app/services/chat/conversation_search_service.py`：当前 Agent 运行绑定的历史会话召回 Provider。

## 边界约束

- `compression_intent` 的生成属于 server 业务语义：依赖当前 query、最近用户轮次和产品对“任务重点”的理解。
- harness 只负责消费标准化的 `compression_intent` 并执行通用压缩，不负责推断业务目标。
- harness 的 `conversation_search/` 模块只定义 Protocol/DTO、formatter 与单元测试工厂；产品 Turn1 经 `memory_search_tool(corpus=sessions)` ACL。Server 负责 DB/FTS5/Agent 身份过滤与摘要读取。
- control plane 不生成语义型压缩意图，只负责调度、隔离、资源和运行基础设施。
