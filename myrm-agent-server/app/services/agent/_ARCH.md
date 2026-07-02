# agent 服务模块


---

## 架构概述

Agent 业务域。提供 Agent CRUD 管理、流式执行（General / FastSearch / Deep Research）、Web 搜索服务，以及统一的 Agent 执行网关（并发控制、超时保护、可观测性）。

本层同时承担 Saved Agent 运行时契约的单一事实源职责。前端设置页、聊天配置面板、Web/Channel/Cron 入口和 DB 自定义子 Agent 都通过这里持久化和读取同一份配置，避免字段在不同入口之间漂移。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `gateway.py` | ✅ 核心 | Agent 执行网关 — 全局/Per-User 并发控制、**内存压力熔断**（订阅 `MemoryPressureMonitor`，CRITICAL/EMERGENCY 级别时阻塞新任务直到恢复或队列超时）、排队超时、执行超时、活跃会话元数据追踪（Multi-Pane 状态 API）、结构化日志、会话级互斥（AgentBusyError 409）。`interrupt()` / `interrupt_session(chat_id)` 中断运行中 stream。`ActiveSessionInfo` 持有 `BaseAgent` 弱引用及 `current_message_id`（供 chat 级 cancel 同步 `CancellationRegistry`），供子 Agent 控制 API 获取 `SubagentManager` 实例 |
| `confidence_approval_flow.py` | ✅ 核心 | 多信号风控审批流 — 基于置信度 + 2 个客观确定性信号（diff 变化范围、历史成功率）的智能审批。高分且全部风控信号绿灯时静默自动合并，任何红灯或 runtime failure 修复即降级人工 Diff Review。`ApprovalResult.risk_signals` 记录降级原因；risk_signals / runtime evidence 持久化为 `reason_code`、`remediation` 和审核证据供前端展示 |
| `agent_service.py` | ✅ 核心 | Agent CRUD。WebUI mutable 变更前委托 `ProfileSnapshotService`；`update_agent` 返回 `AgentUpdateOutcome`（含 `snapshot_saved`）。创建/更新/删除/回滚后失效 `AgentProfileResolver` 缓存并热重载 CommandRegistry。 |
| `profile_snapshot_service.py` | ✅ 核心 | Agent 配置快照与回滚专用服务 — `save_profile_snapshot` / `list_profile_snapshots` / `count_profile_snapshots` / `rollback_profile` / `rollback_profile_to_snapshot`。含完整 mutable 字段 diff 检测（`has_mutable_diff`）、pre-rollback 保险快照、10 条 retention 裁剪。由 `AgentService` 委托，供 WebUI 时光机 API 使用。 |
| `templates.py` | ✅ 核心 | 预置智能体模板市场 API — 提供基于 YAML 种子的原子化实例化（`instantiate-template`），在克隆模板的同时强一致性自动 Enable 所需依赖技能（如 `prebuilt_skill_ids`），供 WebUI /templates 端点实现快速 Onboarding，解决空白画布冷启动痛点。 |
| `profile_resolver.py` | ✅ 核心 | 统一智能体配置解析服务 — 提供 `ResolvedAgentProfile` 数据类、带 TTL 缓存的 `AgentProfileResolver` 全局单例、`DEFAULT_ENABLED_BUILTIN_TOOLS`（`web_search`+`memory` only，不含 kanban）和 `resolve_builtin_tool_flags()` 统一映射函数（含 `enable_kanban` ← `kanban`、`enable_render_ui` ← `render_ui`、`enable_planning` ← `planning`、`enable_task_tracking` ← `task_tracking`、`enable_answer_tool` ← `answer_tool`）。Kanban LLM bind 模式由 `general_agent/kanban_tool_mode.py` 解析（chat 默认 orchestrator 8，TaskRunner worker 5）。消除 Web/Channel/Cron/Kanban/Eval/Voice 六入口的重复 agent profile 解析和工具 flag 映射逻辑，统一返回 `subagent_ids`、`enabled_builtin_tools`、`mcp_tool_selections`、`workspace_policy`、`memory_policy`、`engine_params`、`model_kwargs`、`session_policy`、`notify_targets`、`built_in` 等完整运行时契约。 |
| `builtin_initializer.py` | ✅ 核心 | Built-in Agent 自动初始化 — 服务启动时（lifespan Phase 1b）幂等创建 24 个预置智能体（4 核心 + 2 搜索 + 5 扩展 + 13 垂直领域）到数据库，使用定制 SVG 几何符号视觉标识（`icon:{id}` 格式）。搜索智能体走统一 SkillAgent 路径，提示词由 `prompt_mode="search"` 单一提供（system_prompt 留空避免重复注入），享有记忆 + PWA 断连恢复能力 |
| `streaming.py` | ✅ 核心 | General Agent / Deep Research Harness 流式桥接（Gateway + SSE 事件转换） |
| `stream_session/orchestrator.py` | ✅ 核心 | General Agent 流式会话主编排（setup + session 装配） |
| `stream_session/stream_session_types.py` | ✅ 核心 | `AgentStreamSession` 会话上下文数据类 |
| `stream_session/stream_disconnect.py` | ✅ 核心 | PWA 断连宽限与 Offline Durable Guardian |
| `stream_session/stream_chunks.py` | ✅ 核心 | SSE 预检编排（SessionCredentialAssembler 凭据注入、Vision fallback） |
| `stream_session/stream_loop.py` | ✅ 核心 | Agent 主流 SSE 循环 |
| `stream_session/stream_finalize.py` | ✅ 核心 | 流错误处理与会话 teardown |
| `stream_session/stream_pump.py` | ✅ 核心 | GlobalStreamRegistry buffer pump (支持 multiplexed 响应) |
| `stream_session/stream_generator.py` | ✅ 门面 | stream_session 对外 re-export |
| `stream_session/stream_lane_factory.py` | ✅ 核心 | Deep Research / Fast Lane SSE 工厂 |
| `stream_session/reconnect.py` | ✅ 辅助 | SSE Last-Event-ID 重连 |
| `stream_session/risk_gate.py` | ✅ 辅助 | 流式输入 risk 拦截 |
| `streaming_support/sse_helpers.py` | ✅ 核心 | SSE 格式化与审批/压缩辅助 |
| `streaming_support/stream_collector.py` | ✅ 核心 | 流内容收集与 assistant 持久化 |
| `streaming_support/multiplexer.py` | ✅ 核心 | WorkspaceMultiplexer (SSE 多路复用器) |
| `llm_access.py` | ✅ 辅助 | WebUI 配置驱动的 LLM 实例解析（`get_llm_for_user` / `get_optional_llm_for_user`）；`api.dependencies` re-export | ✅ |
| `params/` | ✅ 核心 | Agent 参数转换层 |
| `swarm_fission_resume.py` | ✅ 核心 | Swarm Fission 流式包装器：拦截 `swarm_fission` 事件，调用 Harness `execute_swarm_fission`，发射带 `failed_count`/`partial_success` 的 `tasks_steps`，再以 `Command(resume=...)` 恢复父 Agent |
| `fission_config.py` | ✅ 辅助 | 从 Agent `engine_params.max_parallel_fission` 解析并发上限（默认 3，上限 5），供 Web/Channel/Kanban/FastSearch 统一传入 `execute_swarm_fission` |
| `steering_registry.py` | ✅ 核心 | 会话级 Steering 令牌注册表 — 通过 chat_id 管理运行中的 SteeringToken，使 HTTP API 能在运行时注入引导消息。与 CancellationRegistry 对称设计。 |
| `wakeup_handler.py` | ✅ 核心 | **Idle Wakeup & Event-Driven Continuation** 的 Server 层实现（`AsyncWakeupHandler`）。Headless 续跑在 `convert_to_general_agent_params` 之后将 `channel_name` 置为 **`headless_wakeup`**（`delivery_provenance` 映射 `async_wake_consumer`），并在 `memory_channel_id` 缺省时 **固定回写 `web_chat`**，避免记忆命名空间随投递标签漂移；`_run_headless_agent` 投递流式执行前必须通过 `app.core.utils.chat_utils.convert_chat_history` 将历史转为 LangChain 消息。 |
| `context_compaction_telemetry.py` | ✅ 核心 | Context 压缩遥测分发器。配置来自 `settings.control_plane` + `settings.context_compaction_telemetry`（`ContextCompactionTelemetryConfig.from_settings()`）；读取 Harness `TaskMetrics` 快照，有界队列 + 批量 flush + 背压保护异步上报 Control Plane（`events` 契约，`X-Telemetry-Subject` 头）。 |
| `search.py` | ✅ 辅助 | Web 搜索服务封装 |
| `routing_advisor.py` | ✅ 核心 | 智能路由顾问 — 根据历史事件提供高危模型的降级建议 |
| `goal_registry.py` | ✅ 核心 | 会话级 Goal 句柄全局注册表。`ServerGoalManager` 扩展 harness `GoalManager`，semantic judge 通过 `platform_config.build_platform_litellm_kwargs()` 读 WebUI 默认模型（无 env fallback）。 |
| `platform_config.py` | ✅ 核心 | WebUI 平台级模型/检索配置；`build_platform_litellm_kwargs()`、`webui_model_preflight_warning()`、`resolve_xai_search_config()`；业务禁止读进程 env |
| `session_credential_assembler.py` | ✅ 核心 | 统一会话凭证装配 + `session_credentials_scope` / `user_config_session_credentials_scope`；Web / Channel / Cron / Kanban / Wakeup / approval-timeout resume |
| `outbound_notify/` | ✅ 辅助 | Agent 主动出站通知 — 类型、target 解析、rate limit、`bus.send_tracked` 可靠投递、`channel_notify_tool`（Turn1，notify_targets 配置时）；前端 recipient 从 `/channels/manage/pairings` 选择 | ✅ |

---

## AgentGateway

所有 Agent 执行（General / FastSearch / Deep Research / Headless Wakeup）都经过 `AgentGateway`：

- **全局并发控制**：`Semaphore(AGENT_MAX_CONCURRENT)` 防止服务器过载。后台异步唤醒任务（Headless）同样受此保护，防止与前台活跃会话抢占资源导致 OOM 或 429 限流。
- **内存压力熔断**：实现 `PressureSubscriber` 协议，订阅 Harness `MemoryPressureMonitor`。当压力 ≥ CRITICAL 时，阻塞新 Agent 执行（已运行的不受影响），直到压力降至 WARNING/NORMAL 或 `queue_timeout` 到期。超时时错误消息携带压力级别信息，精确传递到前端 SSE。
- **排队超时**：等待超过 `AGENT_QUEUE_TIMEOUT` 秒抛 `AgentQueueTimeout`
- **执行超时**：执行超过 `AGENT_EXECUTION_TIMEOUT` 秒抛 `AgentExecutionTimeout`
- **中断支持**：`interrupt()` 信号全部运行中 Agent 停止；`interrupt_session(chat_id)` 单会话停止；`get_active_message_id(chat_id)` 供 chat cancel 同步 harness `CancellationRegistry`
- **活跃会话追踪**：`ActiveSessionInfo` 元数据（chatId、agentType、elapsedSeconds、current_message_id），`get_active_sessions()` 和 `get_available_slots()` 供 Multi-Pane 工作台使用
- **API 端点**：`GET /agents/active-sessions`（Multi-Pane 状态）、`POST /api/agent/interrupt`（远程中断）、`POST /agents/chats/{chat_id}/cancel`（scoped pair 单 chat 取消：interrupt + registry）

环境变量配置：`AGENT_MAX_CONCURRENT`(20), `AGENT_MAX_PER_USER`(3), `AGENT_QUEUE_TIMEOUT`(10s), `AGENT_EXECUTION_TIMEOUT`(300s)

---

## Saved Agent 运行时契约

业务层统一管理以下关键字段，并保证它们可以跨入口稳定读写：

- `agent_type`（`individual` | `team`，团队型 Agent 运行时自动注入 Leader Operating Protocol + 成员名册）
- `skill_ids`
- `mcp_ids`
- `mcp_tool_selections`（per-MCP-server 工具白名单 `{server_name: [tool_name, ...]}`，由前端智能体编辑器管理，注入 `MCPConfig.tool_include` 实现工具级最小权限）
- `enabled_builtin_tools`
- `subagent_ids`
- `security_overrides`
- `personality_style`
- `allow_discovery`（是否允许被其他智能体动态发现并委派）
- `max_iterations`
- `workspace_policy`
- `memory_policy`
- `engine_params`
- `session_policy`（per-agent IM 会话策略覆盖：mode/daily_reset_hour/idle_minutes，存储在 metadata 中，优先于全局 personalSettings.sessionPolicy）
- `suggestion_prompts`（前端空白状态启发式提示，智能体自定义优先于默认提示池）

读取路径：

- 设置页编辑器 → Agent CRUD API → `AgentService`
- 聊天配置面板保存/更新 → Agent CRUD API → `AgentService`
- Web / Channel / Cron 运行时读取 → `AgentProfileResolver`
- DB 自定义子 Agent 转运行时 subagent 配置 → `app/ai_agents/subagent_catalog.py`

---

## 依赖关系

### 内部依赖
- `app/ai_agents/`：AgentFactory、GeneralAgentParams
- `app/database/`：Agent 模型和 Schema
- `myrm_agent_harness/`：WebSearchTools

### 被依赖方
- `app/api/agents/`：Agent API 路由
- `app/api/integrations/search.py`：搜索 API
