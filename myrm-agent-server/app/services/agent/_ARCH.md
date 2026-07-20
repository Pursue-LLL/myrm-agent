# agent 服务模块


---

## 架构概述

Agent 业务域。提供 Agent CRUD 管理、流式执行（General / FastSearch / Deep Research）、Web 搜索服务，以及统一的 Agent 执行网关（并发控制、超时保护、可观测性）。

本层同时承担 Saved Agent 运行时契约的单一事实源职责。前端设置页、聊天配置面板、Web/Channel/Cron 入口和 DB 自定义子 Agent 都通过这里持久化和读取同一份配置，避免字段在不同入口之间漂移。

---

## 子模块

| 模块 | 地位 | 职责 | 文档 |
|------|------|------|------|
| `backends/` | ✅ 核心 | Agent Profile/Secret/MCP OAuth 持久化后端 | [_ARCH.md](backends/_ARCH.md) |
| `evolution/` | ✅ 核心 | 技能进化调度（stream 完成触发 + 后台 monitor + 技能免疫） | [_ARCH.md](evolution/_ARCH.md) |
| `execution_cache/` | ✅ 核心 | Chat 级 `BuiltExecutionUnit` 池（POOLED / EPHEMERAL） | [_ARCH.md](execution_cache/_ARCH.md) |
| `outbound_notify/` | ✅ 辅助 | Agent 主动出站 Channel 通知 | [_ARCH.md](outbound_notify/_ARCH.md) |
| `memory_brief_telemetry/` | ✅ 核心 | Memory Brief CP 遥测（契约、dropped 落盘、metrics、flush、dispatcher） | [_ARCH.md](memory_brief_telemetry/_ARCH.md) |
| `memory_guardian_guard_telemetry/` | ✅ 核心 | Memory Guardian 守卫不可用 CP 遥测（dispatcher + pending 落盘） | [_ARCH.md](memory_guardian_guard_telemetry/_ARCH.md) |
| `builtin_specs/` | ✅ 核心 | 预置智能体规格数据（types + core/search/extended/vertical 分段） | [_ARCH.md](builtin_specs/_ARCH.md) |
| `marketplace/` | ✅ 核心 | Agent Marketplace 导入/导出与包契约 SSOT | [_ARCH.md](marketplace/_ARCH.md) |
| `params/` | ✅ 核心 | HTTP 请求 → `GeneralAgentParams` 转换层 | [_ARCH.md](params/_ARCH.md) |
| `stream_session/` | ✅ 核心 | General Agent SSE 流式会话编排 | [_ARCH.md](stream_session/_ARCH.md) |
| `streaming_support/` | ✅ 核心 | SSE 格式化、Failover、内容收集、Multiplexer | [_ARCH.md](streaming_support/_ARCH.md) |

> **API 边界**：预置智能体模板实例化（`instantiate-template`）在 `app/api/agents/templates.py`，不在本 services 层。

---

## 根目录文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `gateway.py` | ✅ 核心 | Agent 执行网关 — 全局/Per-User 并发控制、**内存压力熔断**（订阅 `MemoryPressureMonitor`，CRITICAL/EMERGENCY 级别时阻塞新任务直到恢复或队列超时）、排队超时、执行超时、活跃会话元数据追踪（Multi-Pane 状态 API）、结构化日志、会话级互斥（AgentBusyError 409）。`interrupt()` / `interrupt_session(chat_id)` 中断运行中 stream。`ActiveSessionInfo` 持有 `BaseAgent` 弱引用及 `current_message_id`（供 chat 级 cancel 同步 `CancellationRegistry`），供子 Agent 控制 API 获取 `SubagentManager` 实例 |
| `confidence_approval_flow.py` | ✅ 核心 | 多信号风控审批流 — 基于置信度 + 2 个客观确定性信号（diff 变化范围、历史成功率）的智能审批。高分且全部风控信号绿灯时静默自动合并，任何红灯或 runtime failure 修复即降级人工 Diff Review。`ApprovalResult.risk_signals` 记录降级原因；risk_signals / runtime evidence 持久化为 `reason_code`、`remediation` 和审核证据供前端展示 |
| `agent_service.py` | ✅ 核心 | Agent CRUD。WebUI mutable 变更前委托 `ProfileSnapshotService`；`update_agent` 返回 `AgentUpdateOutcome`（含 `snapshot_saved`）。创建/更新/删除/回滚后失效 `AgentProfileResolver` 缓存并热重载 CommandRegistry。 |
| `profile_snapshot_service.py` | ✅ 核心 | Agent 配置快照与回滚专用服务 — `save_profile_snapshot` / `list_profile_snapshots` / `count_profile_snapshots` / `rollback_profile` / `rollback_profile_to_snapshot`。含完整 mutable 字段 diff 检测（`has_mutable_diff`，含 `cron_post_run_verify` DB 列）、pre-rollback 保险快照、10 条 retention 裁剪；`updates_from_snapshot_data` 回滚时写回该列。由 `AgentService` 委托，供 WebUI 时光机 API 使用。 |
| `profile_resolver.py` | ✅ 核心 | 统一智能体配置解析 — `resolve_builtin_tool_flags()`（strip deploy 不兼容工具 + `enable_computer_use`/`enable_external_cli` 双保险 deploy gate）+ `apply_agent_baseline_tool_flags()`；TTL 缓存 | ✅ |
| `builtin_tool_ids.py` | ✅ 核心 | `enabled_builtin_tools` SSOT：17 canonical IDs（15 UI 可切换 + 2 Agent 基线无开关）；`strip_deploy_incompatible_builtin_tools()` 按 deploy 剔除 `computer_use`（VNC）与 `external_cli`（仅 local/Tauri）；`external_cli` ON + UserConfig 有 CLI backend → Turn1 挂载 `delegate_to_agent_tool`；`cron` 开启 → Turn1 eager（`enable_cron_eager`）；关闭则不加载；`structured_clarify` 开启 → 挂载 `ask_question_tool`（默认 ON）；`DEFAULT_ENABLED_BUILTIN_TOOLS=(web_search, memory, structured_clarify)`；`normalize` 静默剥离 baseline ID；`persist_enabled_builtin_tools` DB 写校验 |
| `builtin_tool_validation.py` | ✅ 辅助 | Pydantic `RequiredBuiltinTools` / `OptionalBuiltinTools` validators for DTO/API models |
| `builtin_agent_specs.py` | ✅ 门面 | 聚合 `_BUILTIN_AGENTS`（26 段规格 tuple）+ re-export 类型/工具常量；实现位于 `builtin_specs/` |
| `builtin_initializer.py` | ✅ 核心 | Built-in Agent 自动初始化 — lifespan Phase 1b 幂等创建 26 个预置智能体（从 `builtin_agent_specs` 导入规格）；`suggestion_prompts` 仅在 DB 值为空时填充（保护用户自定义）；re-export `_BUILTIN_AGENTS`/`_TOOL_*` 保持外部导入兼容 |
| `approval_payload.py` | ✅ 辅助 | LangGraph interrupt → ApprovalRegistry payload SSOT（nested payload 优先，flat semantic DOM HITL 字段回退） |
| `streaming.py` | ✅ 核心 | General Agent / Deep Research Harness 流式桥接（Gateway + SSE 事件转换）；`PhaseWaiter` 通用阶段暂停/恢复门控（Clarification + Plan Confirmation HITL）；POOLED 路径经 `finalize_agent_session` 释放 execution cache | ✅ |
| `swarm_fission_resume.py` | ✅ 核心 | Swarm Fission 流式包装器：拦截 `swarm_fission` 事件，调用 Harness `execute_swarm_fission`，发射带 `failed_count`/`partial_success` 的 `tasks_steps`，再以 `Command(resume=...)` 恢复父 Agent | ✅ |
| `fission_config.py` | ✅ 辅助 | 从 Agent `engine_params.max_parallel_fission` 解析并发上限（默认 3，上限 5），供 Web/Channel/Kanban/FastSearch 统一传入 `execute_swarm_fission` |
| `steering_registry.py` | ✅ 核心 | 会话级 Steering 令牌注册表 — 通过 chat_id 管理运行中的 SteeringToken，使 HTTP API 能在运行时注入引导消息。与 CancellationRegistry 对称设计。 |
| `wakeup_handler.py` | ✅ 核心 | **Idle Wakeup & Event-Driven Continuation** 的 Server 层实现（`AsyncWakeupHandler`）。Headless 续跑在 `convert_to_general_agent_params` 之后将 `channel_name` 置为 **`headless_wakeup`**（`delivery_provenance` 映射 `async_wake_consumer`），并在 `memory_channel_id` 缺省时 **固定回写 `web_chat`**，避免记忆命名空间随投递标签漂移；`_run_headless_agent` 投递流式执行前必须通过 `app.core.utils.chat_utils.convert_chat_history` 将历史转为 LangChain 消息。 |
| `background_job_finish_handler.py` | ✅ 核心 | Harness 后台 bash 自然退出时的 WebUI 闭环：Store finish 幂等 → locale 双语完成消息 → `append_message` → `goal_wait_background_resume` → `SYSTEM_NOTIFICATION` SSE。 |
| `background_job_startup.py` | ✅ 核心 | 启动 configure `BackgroundJobStore`（harness_dir/.myrm/background_jobs.db）并 reconcile orphaned running 行。 |
| `goal_wait_orphan_recovery.py` | ✅ 核心 | 启动时在 Store reconcile 之后：WAIT + orphaned background pid → NEEDS_HUMAN_REVIEW + goal_needs_review SSE（对称 `pause_orphaned_active_goals`）。 |
| `goal_wait_background_resume.py` | ✅ 核心 | background job finish 匹配 wait_on_background_pid → exit_wait → `trigger_goal_stream_with_failure_policy(needs_human_review)`；前端 refreshActiveGoal 同步 Card |
| `shell_background_tasks.py` | ✅ 核心 | registry + Store 合并 REST 门面；`task_id=shell:{job_id}`；`list_shell_background_tasks` / `cancel_shell_background_task` / `find_shell_background_task`。 |
| `context_compaction_telemetry.py` | ✅ 核心 | Context 压缩遥测分发器。配置来自 `settings.control_plane` + `settings.context_compaction_telemetry`（`ContextCompactionTelemetryConfig.from_settings()`）；读取 Harness `TaskMetrics` 快照，有界队列 + 批量 flush + 背压保护异步上报 Control Plane（`events` 契约，`X-Telemetry-Subject` 头）。 |
| `search.py` | ✅ 辅助 | Web 搜索服务封装 | ✅ |
| `routing_advisor.py` | ✅ 核心 | 智能路由顾问 — 根据历史事件提供高危模型的降级建议 | ✅ |
| `browser_skill_binding.py` | ✅ 辅助 | `enable_browser` 时合并 peripheral prebuilt `browser-automation` skill（`is_core:false`）；由 `AgentFactory.create_general_agent` 调用，覆盖 Web/Cron/Channel/Kanban 全入口 | ✅ |
| `goal_registry.py` | ✅ 核心 | 会话级 Goal 句柄全局注册表。`ServerGoalManager` 扩展 harness `GoalManager`，semantic judge 通过 `platform_config.build_platform_litellm_kwargs()` 读 WebUI 默认模型（无 env fallback）。 | ✅ |
| `goal_stream_trigger.py` | ✅ 辅助 | Goal 队列 dequeue / bg WAIT resume / loop_restart 统一 unattended headless stream；`handle_unattended_goal_stream_failure` SSOT（setup + runtime → NEEDS_HUMAN_REVIEW 或 keep ACTIVE + SSE）；`publish_goal_needs_review_notification` 供 orphan WAIT 恢复复用 | ✅ |
| `goal_draft.py` | ✅ 辅助 | Goal 创建前 draft — 从 objective 生成 constraints / acceptance_criteria（Server lite LLM） | ✅ |
| `platform_config.py` | ✅ 核心 | WebUI 平台级模型/检索配置 | ✅ |
| `session_credential_assembler.py` | ✅ 核心 | 统一会话凭证装配 + `session_credentials_scope` / `user_config_session_credentials_scope`；Web / Channel / Cron / Kanban / Wakeup / approval-timeout resume | ✅ |
| `oauth_refresher.py` | ✅ 核心 | OAuth2 token 自动刷新（DB 持久化 + AES 加密 + 并发锁防 stampede + Double-Checked Locking）；refresh 失败时发布 `OAUTH_REAUTH_REQUIRED` 事件（仅 4xx/missing_refresh_token，per-issuer 300s 去重）| ✅ |
| `llm_access.py` | ✅ 辅助 | WebUI 配置驱动的 LLM 实例解析（`get_llm_for_user` / `get_optional_llm_for_user`）；`api.dependencies` re-export | ✅ |

---

## AgentGateway

所有 Agent 执行（General / FastSearch / Deep Research / Headless Wakeup）都经过 `AgentGateway`：

- **全局并发控制**：`Semaphore(AGENT_MAX_CONCURRENT)` 防止服务器过载。后台异步唤醒任务（Headless）同样受此保护，防止与前台活跃会话抢占资源导致 OOM 或 429 限流。
- **内存压力熔断**：实现 `PressureSubscriber` 协议，订阅 Harness `MemoryPressureMonitor`。当压力 ≥ CRITICAL 时，阻塞新 Agent 执行（已运行的不受影响），直到压力降至 WARNING/NORMAL 或 `queue_timeout` 到期。超时时错误消息携带压力级别信息，精确传递到前端 SSE。
- **排队超时**：等待超过 `AGENT_QUEUE_TIMEOUT` 秒抛 `AgentQueueTimeout`
- **执行超时**：执行超过 `AGENT_EXECUTION_TIMEOUT` 秒抛 `AgentExecutionTimeout`
- **中断支持**：`interrupt()` 信号全部运行中 Agent 停止；`interrupt_session(chat_id)` 单会话停止；`get_active_message_id(chat_id)` 供 chat cancel 同步 harness `CancellationRegistry`
- **活跃会话追踪**：`ActiveSessionInfo` 元数据（chatId、agentType、agentId、elapsedSeconds、current_message_id），`get_active_sessions()` 和 `get_available_slots()` 供 Multi-Pane 工作台和 Fleet Overview 使用
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

Memory Brief 遥测链（仅 sandbox Control Plane 场景）：

`stream_loop` / `stream_finalize` → `memory_brief_telemetry`（`enqueue_memory_brief_status_telemetry`）→ `flush.py` → Control Plane；契约见 `contract.py`；dropped 落盘与失败指数退避重试窗口见 `dropped_store.py`。

### 被依赖方
- `app/api/agents/`：Agent API 路由
- `app/api/integrations/search.py`：搜索 API
