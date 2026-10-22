# agent 服务模块


---

## 架构概述

Agent 业务域。提供 Agent CRUD 管理、流式执行（General / FastSearch / Deep Research）、Web 搜索服务，以及统一的 Agent 执行网关（并发控制、超时保护、可观测性）。

本层同时承担 Saved Agent 运行时契约的单一事实源职责。前端设置页、聊天配置面板、Web/Channel/Cron 入口和 DB 自定义子 Agent 都通过这里持久化和读取同一份配置，避免字段在不同入口之间漂移。

Harness 工具层级 SSOT：`myrm-agent-harness/.../tool_management/tool_layers.py` 与 [tool_management/_ARCH.md](myrm-agent-harness/src/myrm_agent_harness/agent/tool_management/_ARCH.md)。

## Tool loading dual-track

| Track | When | CORE file/bash | Primary SSOT |
| --- | --- | --- | --- |
| **General** | Default saved agent; Web non-fast; **Channel/IM**; Cron/Kanban | On | `tool_mount.resolve_agent_mount` → harness `get_meta_tools` |
| **Search/Fast** | Web chat `action_mode=fast` only | UECD read-only (`FileAccessMode.SPILL_AND_UPLOADS`) | `params/converter.py` + `tool_mount.resolve_agent_mount(WEB_FAST)` |
| **Cron narrow** | Job `tools_allowed` without baseline | Optional off | `core/cron/adapters/tools_policy.py` |

Design notes:

- `DEFAULT_ENABLED_BUILTIN_TOOLS` excludes `file_ops` / `code_execute` by design; baseline IDs are stripped on persist and forced at runtime on General track.
- `tool_mount.resolve_agent_mount` is the server execution layer for harness CORE meta mount.
- **Channel/IM binds General agents only** (`SqlTopicManager.bind_topic` rejects `prompt_mode=search`; `resolve_topic` / `get_all_topics` purge legacy Search binds; IM `/bind` + Settings API). Search/Fast is Web `action_mode=fast`.
- Saved agents with `prompt_mode=search` (Quick Search presets) are Web UI personas; non-fast Web chat still loads General CORE tools with search-oriented prompts.
- Sub-agent readonly: harness `WorkspacePolicy.READ_ONLY_SANDBOX` + `delegate_task(readonly=True)`; separate from General CORE.

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
| `builtin_specs/` | ✅ 核心 | 预置智能体规格与 builtin 工具 SSOT（types + core/search/extended/vertical 分段；`builtin_initializer` 自动初始化 / `builtin_tool_ids` 工具 ID 清单 / `builtin_tool_validation` DTO validators） | [_ARCH.md](builtin_specs/_ARCH.md) |
| `goals/` | ✅ 核心 | Goal 域：会话级 Goal 注册表 + draft 生成 + headless 流触发 + WAIT/orphan 恢复 | [_ARCH.md](goals/_ARCH.md) |
| `profile/` | ✅ 核心 | Agent Profile 域：配置解析（`profile_resolver`）+ builtin 工具标志映射 + 快照回滚服务 | [_ARCH.md](profile/_ARCH.md) |
| `background_job/` | ✅ 核心 | 后台 bash 任务域：启动 reconcile + finish 闭环 WebUI 通知 | [_ARCH.md](background_job/_ARCH.md) |
| `tool_mount/` | ✅ 核心 | Meta-tool mount SSOT — `resolve_agent_mount` / `apply_ptc_meta_mount` | [_ARCH.md](tool_mount/_ARCH.md) |
| `marketplace/` | ✅ 核心 | Agent Marketplace 导入/导出与包契约 SSOT | [_ARCH.md](marketplace/_ARCH.md) |
| `params/` | ✅ 核心 | HTTP 请求 → `GeneralAgentParams` 转换层 | [_ARCH.md](params/_ARCH.md) |
| `readiness/` | ✅ 核心 | Per-agent 配置就绪预检（6 维度 ready/warning/blocked + Settings deep link） | [_ARCH.md](readiness/_ARCH.md) |
| `stream_session/` | ✅ 核心 | General Agent SSE 流式会话编排 | [_ARCH.md](stream_session/_ARCH.md) |
| `streaming_support/` | ✅ 核心 | SSE 格式化、Failover、内容收集、Multiplexer | [_ARCH.md](streaming_support/_ARCH.md) |
| `adaptive_wakeup/` | ✅ 核心 | 后台长任务与子智能体完成自适应唤醒宿主驱动器与有界轮次熔断保护服务（`service.py`） | - |

> **API 边界**：预置智能体模板实例化（`instantiate-template`）在 `app/api/agents/templates.py`，不在本 services 层。

---

## 根目录文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `gateway.py` | ✅ 核心 | Agent 执行网关 — 并发/内存压力熔断/排队与执行超时/优雅排空/活跃会话元数据；**`reserve_session` / `release_session`**（persist 前预占，`reserved_only`→`execute_stream`）；**`release_if_reserved_only`**（turn 在 `execute_stream` 接管前退出时清理残留预占，避免 chat 永久 busy；返回是否确实释放了残留预占）；互斥 busy 经 SSE **`error_type:AgentBusyError`**（HTTP 200，非 HTTP 409）；`interrupt()` / `interrupt_session`；`ActiveSessionInfo` 弱引用 + `current_message_id`；**`is_session_active` / `active_session_ids`**（执行中会话的单点只读视图，Catchup 与 session map 据此判定 running/working） |
| `confidence_approval_flow.py` | ✅ 核心 | 多信号风控审批流 — 基于置信度 + 2 个客观确定性信号（diff 变化范围、历史成功率）的智能审批。高分且全部风控信号绿灯时静默自动合并，任何红灯或 runtime failure 修复即降级人工 Diff Review。`ApprovalResult.risk_signals` 记录降级原因；risk_signals / runtime evidence 持久化为 `reason_code`、`remediation` 和审核证据供前端展示 |
| `agent_service.py` | ✅ 核心 | Agent CRUD。WebUI mutable 变更前委托 `ProfileSnapshotService`；`update_agent` 返回 `AgentUpdateOutcome`（含 `snapshot_saved`）。MCP 变更后 POOLED 单元由 `compute_execution_fingerprint` 在下一 turn 重建。创建/更新/删除/回滚后失效 `AgentProfileResolver` 缓存并热重载 CommandRegistry。 |
| `mcp_runtime_prepare.py` | ✅ 核心 | MCP 配置 secret/OAuth 注入 SSOT；factory build 共用 | ✅ |
| `moa_preset_resolver.py` | ✅ 核心 | Agent Profile 顾问自动激活与会话级 MoA preset 解析：支持 manual/always/risk_triggered 声明式激活策略，结合显式请求、REASONING tier 与高危工具触发条件动态生效，presets.{default,review,fast} 独立 ref 池与参数模板 | ✅ |
| `mcp_surface_mode.py` | ✅ 辅助 | `engine_params.mcp_surface_mode` 归一化（obsolete `catalog_invoke` → `auto`） | ✅ |
| `external_cli_gate.py` | ✅ 核心 | Local persist gate：`external_cli` ∈ `enabled_builtin_tools` 时要求 Settings CLI backend 或本地 auto-detect；与 runtime `_resolve_external_agent_cfgs` 同源 |
| `builtin_agent_specs.py` | ✅ 门面 | 聚合 `_BUILTIN_AGENTS`（27 段规格 tuple）+ re-export 类型/工具常量；实现位于 `builtin_specs/` |
| `approval_payload.py` | ✅ 辅助 | LangGraph interrupt → ApprovalRegistry payload SSOT（nested payload 优先，flat semantic DOM HITL 字段回退） |
| `streaming.py` | ✅ 核心 | General Agent / Deep Research Harness 流式桥接（Gateway + SSE 事件转换）；`PhaseWaiter` 通用阶段暂停/恢复门控（Clarification + Plan Confirmation HITL）；browser takeover 事件在服务端直出 `live_assist_url`（approval_required + browser_takeover_requested 同源签名链接）；finally 中检测 interrupt 类事件（approval/clarification）并发布 `awaiting_approval` session_status 激活侧边栏 per-chat 注意力指示；POOLED 路径经 `finalize_agent_session` 释放 execution cache | ✅ |
| `swarm_fission_resume.py` | ✅ 核心 | Swarm Fission 流式包装器：拦截 `swarm_fission` 事件，调用 Harness `execute_swarm_fission`，发射带 `failed_count`/`partial_success` 的 `tasks_steps`，再以 `Command(resume=...)` 恢复父 Agent | ✅ |
| `fission_config.py` | ✅ 辅助 | 从 Agent `engine_params.max_parallel_fission` 解析并发上限（默认 3，上限 5），供 Web/Channel/Kanban/FastSearch 统一传入 `execute_swarm_fission` |
| `steering/` | ✅ 核心 | Steering 域：会话级 SteeringToken 注册表 + 政策模式引用队列（去重/上限/信封/计数器），域唯一入口 `steering/__init__.py` | [_ARCH.md](steering/_ARCH.md) |
| `wakeup_handler.py` | ✅ 核心 | **Idle Wakeup & Event-Driven Continuation** 的 Server 层实现（`AsyncWakeupHandler`）。Headless 续跑在 `convert_to_general_agent_params` 之后将 `channel_name` 置为 **`headless_wakeup`**（`delivery_provenance` 映射 `async_wake_consumer`），并在 `memory_channel_id` 缺省时 **固定回写 `web_chat`**，避免记忆命名空间随投递标签漂移；`_run_headless_agent` 投递流式执行前必须通过 `app.core.utils.chat_utils.convert_chat_history` 将历史转为 LangChain 消息。 |
| `shell_background_tasks.py` | ✅ 核心 | registry + Store 合并 REST 门面；`task_id=shell:{job_id}`；`list_shell_background_tasks` / `cancel_shell_background_task` / `find_shell_background_task` / `write_shell_background_stdin`。 |
| `context_compaction_telemetry.py` | ✅ 核心 | Context 压缩遥测分发器。配置来自 `settings.control_plane` + `settings.context_compaction_telemetry`（`ContextCompactionTelemetryConfig.from_settings()`）；读取 Harness `TaskMetrics` 快照，有界队列 + 批量 flush + 背压保护异步上报 Control Plane（`events` 契约，`X-Telemetry-Subject` 头）。 |
| `context_guard_service.py` | ✅ 核心 | Context Guard 入站防线：超大 prompt（>16,000 字符或 >8,000 token 压力）透明外溢到「Agent 实际运行的工作区」的 `.myrm/spillover/`（新会话尚无 DB 行，走 JIT 路径 `params.workspace_resolve.default_chat_workspace_path`；无可用工作区或 chat_id 非法则原样放行，交网关体积兜底），开头的 `[use skill]` 标签保持在引用块之前；`sweep_all_workspaces` 清扫各 chat 工作区的过期外溢文件 | ✅ |
| `search.py` | ✅ 辅助 | Web 搜索服务封装 | ✅ |
| `browser_skill_binding.py` | ✅ 辅助 | `enable_browser` 时合并 peripheral prebuilt `browser-automation` skill（`is_core:false`）；由 `AgentFactory.create_general_agent` 调用，覆盖 Web/Cron/Channel/Kanban 全入口 | ✅ |
| `platform_config.py` | ✅ 核心 | WebUI 平台级模型/检索配置 SSOT：`load_platform_model_config` / `load_llm_from_model_config` / `load_platform_llm`（wire-aware）/ `webui_model_preflight_warning` / `resolve_xai_search_config`；`require_platform_embedding_config` embedding 配置结构检查，`verify_platform_embedding_ready` 结构检查 + 真实探活（供 Memory A/B 评测入口 fail-fast，缺失或不可用即抛 `ConfigIncompleteError`） | ✅ |
| `session_access_service.py` | ✅ 核心 | 会话目录 grant 持久化：bootstrap/resume/persist/revoke · 云卷部署边界 gate · resume 与 path-ASK 统一验证链 | ✅ |
| `runtime_context.py` | ✅ 核心 | `build_agent_runtime_context` — 统一注入 `user_id`（`SINGLE_TENANT_USER_ID`，harness `skill_manage` / `skill_market` 安装卸载强制要求）+ `execution_mode` + `disabled_skill_roots` 至全部 agent 入口（Web/IM/Cron/Kanban/Wakeup/Eval/Goal stream/Timeout auto-resume/Offline recovery/OpenAI-compatible API/Voice） | ✅ |
| `oauth_refresher.py` | ✅ 核心 | OAuth2 token 自动刷新（DB 持久化 + AES 加密 + per-issuer 并发锁防 stampede + Double-Checked Locking + 共享 `oauth_credentials_lock` 合并写回防跨 issuer 丢失更新，写回前校验 issuer 仍存在防止复活已断开集成；交换请求作为独立 task 屏蔽调用方取消，避免单次使用的 refresh token 轮换后无人保存）；支持 Google Workspace / xAI 及任何标准 refresh_token 授权的 issuer；失败记忆：被供应商永久拒绝的 refresh token 按指纹记住、不再重试（重新登录得到新 token 即解除），瞬时失败有 30s 冷却，避免故障期每次 LLM 调用都打到上游；refresh 失败时发布 `OAUTH_REAUTH_REQUIRED` 事件（仅供应商以 400/401 加 OAuth 错误体拒绝该授权或缺少 refresh_token 时；403 这类套餐/权益拦截、网关/代理返回的无 OAuth 错误体的 4xx 与超时、限流、5xx 同按瞬时失败冷却；per-issuer 300s 去重）；`is_refresh_rejected` 只读查询失败记忆（无 I/O、不触发刷新），供凭证列表标出需重新登录的授权 | ✅ |
| `oauth_token_policy.py` | ✅ 核心 | OAuth 令牌寿命与刷新失败的纯函数策略（无 I/O、无模块状态）：`TOKEN_REFRESH_LEAD_S` 提前量、`jwt_expiry` / `resolve_expires_at`（新签发访问令牌的到期时间）、`credential_expiry` / `is_refresh_due`（已存凭证是否到期）、`is_renewable`（凭证带 refresh_token 与 token_url 即可自行续期，访问令牌到期不代表连接失效）、`classify_refresh_failure`（仅 400/401 且带 OAuth 错误体判需重新授权，其余含 403 重试可愈）、`refresh_token_fingerprint`（refresh token 的不可逆标识）；由 `oauth_refresher`、xAI 设备码登录与 `provider_oauth_tokens` 共用，三者对「何时过期、哪些失败可重试」口径一致 | ✅ |
| `provider_oauth_tokens.py` | ✅ 核心 | 订阅（provider OAuth）令牌的 LLM 调用托管：`PROVIDER_OAUTH_ISSUERS` 登记哪些 provider 的令牌来自订阅存储；`refresh_provider_oauth_credentials` 在配置加载时续期到期令牌（等待预算 2s，不拖垮 3s 期限的就绪探针）；`resolve_oauth_marker` 把 WebUI 发来的占位 key 换成已存的新鲜令牌并校验目标主机仍是签发主机（`/verify`、`/check-reachability`、`/speed-test` 使用，预算 10s）；`freshen_api_key` 是 harness api-key refresher 的钩子（仅处理本模块签发过的 key，自带 API Key 的用户不触碰令牌存储）；订阅不可用时抛 `ProviderOAuthUnavailableError` | ✅ |
| `llm_access.py` | ✅ 辅助 | WebUI 配置驱动的 LLM 实例解析（`get_llm_for_user` / `get_optional_llm_for_user`）；`api.dependencies` re-export | ✅ |
| `skill_instance_resolver.py` | ✅ 核心 | Agent profile `skill_configs.instance_name` → runtime `default_skill_instances` map（singleton / `default` / explicit）；`resolve_runtime_skill_instance_bindings` 为 factory SSOT；`validate_agent_skill_config_instances` + `serialize_agent_skill_configs` 在 Agent create/update 时校验并序列化 instance 绑定（400 / JSON persist）；`factory.py` 消费 | ✅ |
| `browser_snapshot.py` | ✅ 辅助 | Browser snapshot payload SSOT（WebUI 与 mobile remote 路由共用）；`chat_id` 必填，委托 harness `capture_browser_view_update_data` | ✅ |
| `resolve_enable_web_fetch.py` | ✅ 辅助 | 从 `agent_security_raw.capabilities` 推导 `enable_web_fetch`（bool 门控 web_fetch_tool Turn1 bind）；Web/Channel/Cron/Kanban/Eval/Voice 全入口共享 | ✅ |
| `template_utils.py` | ✅ 辅助 | Agent 模板实例化共享工具（`PREBUILT_AGENTS_DIR` / `resolve_i18n` / `ensure_skills_enabled`），API templates router 与 onboarding presets 复用 | ✅ |
| `session_credential_assembler.py` | ✅ 核心 | 统一会话凭据组装——`assemble_session_credentials` / `session_credentials_scope` / `user_config_session_credentials_scope` 注入 `EphemeralUserCredential`；`XAI_ISSUER` 规范 xAI issuer key | ✅ |
| `agent_assembler_service.py` | ✅ 核心 | 模块化能力拼装服务 — 针对 6 大类积木（大脑/人设/工具/技能/记忆/沙箱）提供依赖合法性体检、预制积木卡片库以及即时微沙箱演练试跑 | ✅ |
| `agent_avatar_service.py` | ✅ 核心 | 智能体头像生成与锁定服务 — 提供纯确定性多风格 SVG 种子算法（Dice Roll）、AI 描述词生图代理与头像锁定缓存持久化 | ✅ |
| `agent_multiplexer_service.py` | ✅ 核心 | 智能体会话多路复用服务 — 聚合 Harness AgentSessionMultiplexer 提供多路复用会话查询、注册、互视日志快照与动态指令注入通道 | ✅ |
| `topology_pruning_service.py` | ✅ 核心 | 模型能力阶梯感知拓扑修剪服务 — 聚合 Harness ModelTierAdaptiveTopologyPruner，提供基于模型智能水平的任务拓扑自适应折叠与 Token/轮次节省估算 | ✅ |
| `agent_handoff_service.py` | ✅ 核心 | 跨智能体移交与对话内任务委派服务 — 统一治理内存与持久化 In-Chat 任务移交卡片、BkashJosi 五阶段编排生命周期状态机、人权审批闸门与行内直通 PR / 采纳 Action | ✅ |
| `device_mesh_service.py` | ✅ 核心 | 边缘硬件设备网格调度服务 — 聚合 Harness EdgeDeviceMeshScheduler 提供边缘节点注册、Token 握手配对、心跳遥测与命令派发能力 | ✅ |
| `todo_store_service.py` | ✅ 核心 | 跨进程/跨插件共享 Todo 计划声明存储与安全 HUD 投影服务 — 统一治理会话级 Todo 计划池、双向 C0/C1 控制字符剥离与只读 HUD 投射 | ✅ |
| `agent_hierarchy_service.py` | ✅ 核心 | 智能体创建层级树与血统溯源服务 — 维护 Agent 创建者血统元数据、执行环路检测与破环防御（Cycle-breaker）、构建递归多层森林树 | ✅ |
| `ralph_workflow_service.py` | ✅ 核心 | Ralph 式 Fresh-Agent 多轮循环管理服务 — 聚合 Harness RalphFreshAgentLoopCoordinator，实现每轮启动无历史全新子 Agent、五字段交接归档与 Min-3-Round 阻断防御 | ✅ |
| `infra_quota_service.py` | ✅ 核心 | 每用户/组织多 Agent 基础设施配额治理服务 — 统一治理活跃 Agent、临时 DB、并发沙箱与持久 Volume 磁盘四维配额池、准入门禁拦截与 Doctor 调优建议 | ✅ |
| `advisor_channel_service.py` | ✅ 核心 | 双模型军师实时异步独立审查频道服务 — 聚合 Harness DualModelAdvisorEngine，提供单步审查评估、三级干预分流判定（aside/concern/blocker）与会话级审查历史归档 | ✅ |
| `subagent_hub_service.py` | ✅ 核心 | 子代理实时监管抽屉服务 — 聚合 Harness SubagentSupervisionCoordinator 与 Checkpoint 存储，统一治理会话级并发 Worker 花名册概览、Live Transcript 执行轨迹缓冲与 Steer/Kill/Revive 干预调度 | ✅ |
| `conflict_gate_service.py` | ✅ 核心 | 多 Bot 并行产出冲突对账与合并前拦截门服务 — 聚合 Harness ParallelWorkConflictDetector，提供多 Worker 并发写集指纹碰撞检测、合并门禁阻断与四策略对账解决调度 | ✅ |
| `mcp_scope_gate_service.py` | ✅ 核心 | 数字员工 MCP 工具作用域隔离门禁服务 — 聚合 Harness EmployeeScopedMcpDiscoveryGate，提供 Profile 级 MCP 白名单策略管理、动态发现候选集裁剪与调用鉴权门禁 | ✅ |
| `agent_operations_service.py` | ✅ 核心 | Agent-Owned 多智能体协同操作服务 — 聚合 Harness AgentOwnedOperationsFabric，提供每会话隔离的 Agent 执行上下文治理、能力白名单解析、操作级错误隔离堆栈与 List-form 花名册 | ✅ |
| `durable_dispatch_service.py` | ✅ 核心 | Hermes Fabric 确定性远程分发与持久化对等日志服务 — 聚合 Harness DurableRemoteDispatchEngine 与 DurableDispatchJournal，提供每会话隔离的契约分发、执行前 Fail-Closed 策略重核验、有界证据准入与崩溃后幂等自愈恢复 | ✅ |
| `report_fifo_service.py` | ✅ 核心 | Subagent 主动回报唤醒与严格有序结算 FIFO 队列服务 — 聚合 Harness SubagentReportWakeupCoordinator 与 OrderedSettlementFifoQueue，提供每会话隔离的命名实例注册、next-step 阶段性回报唤醒、critical 紧急置顶与 urgent_interrupt 打断标记、summary_rollup 自然语言批量摘要聚合、严格 Report-before-Settlement 保序队列与父 Step 边界批量排空，支持会话结束资源清理 cleanup_chat | ✅ |
| `failure_facts_service.py` | ✅ 核心 | Subagent 脱敏结构化失败事实与安全归因诊断服务 — 聚合 Harness SubagentDiagnosticProtocol 与 SafeFailureSanitizer，提供每会话隔离的错误自动归因、单行安全诊断 Header 格式化、敏感凭证与绝对路径安全脱敏、4096 字节有界截断、确定性自愈建议推导与会话历史清理 cleanup_chat | ✅ |
| `debate_workroom_service.py` | ✅ 核心 | 多智能体动态协同工作间与辩论流任务看板联动服务 — 聚合 Harness MultiAgentDebateManager 与 DebateKanbanBridge，提供工作间辩论室生命周期治理、Leader 任务自动拆解、专员辩论质询与反驳论证、防无限车轮战自动收敛控制与 Kanban 任务双向状态绑定同步 | ✅ |
| `external_agent_bridge_service.py` | ✅ 核心 | 多源异构 Agent 外部进程桥接与 CLI 工具适配器服务 — 聚合 Harness ExternalCliAgentAdapter 与 StreamCleaner，提供外部 CLI 进程管理、健康探针校验、任务执行调度与不可篡改的 SHA-256 凭证归档 | ✅ |
| `debate_synthesis_service.py` | ✅ 核心 | 分层 Leader 自动任务分治、专员调研质询与决策权衡对比矩阵收敛服务 — 聚合 Harness HierarchicalDebateSynthesisEngine，提供三段式咨询工作流生命周期、Leader 自动子任务 DAG 拆解、专员提案提交、交叉辩论推进与多维度决策对比矩阵加权综合评分收敛 | ✅ |
| `agent_teams_service.py` | ✅ 核心 | Durable Agent Teams 隐式 Root Lead 会话与扁平具名成员名册、CAS 版本化共享任务板与持久对等邮箱服务 — 聚合 Harness DurableAgentTeamEngine、TaskGraphEngine 与 DurablePeerMailbox，提供会话自组网、任务拓扑 CAS 乐观更新与无冲突认领、断电冷恢复对等发信与边沿事件变更监听 | ✅ |
| `subagent_scaling_service.py` | ✅ 核心 | 子任务并发与工具预算弹性扩容及无损平滑迁移服务 — 聚合 Harness ConfigUpgradeMigrator 与 SubagentWatermarkGuard，提供旧版默认配置无损平滑提升升级、80% 动态自适应水位预警心跳监控、会话预警列表与一键扩容/解除支持 | ✅ |
| `review_loop_service.py` | ✅ 核心 | 多视角并发子智能体评审与有界自愈复审闭环服务 — 聚合 Harness MultiPerspectiveReviewPipeline 与 BoundedReviewLoopExecutor，提供三视角并行聚焦会诊、会话隔离评审环管理、Worker 自动自愈修复推进、收敛检测与有界轮次熔断 | ✅ |
| `bot_mode_service.py` | ✅ 核心 | 具名智能体工位花名册、Bot-to-Bot @mention 寻址投递信箱中继服务 — 聚合 Harness NamedBotRoster 与 InterBotMailboxRelay，提供会话隔离的 AI 同事工位注册、@mention 扫描分发、收件箱管理与清理 | ✅ |
| `squad_composition_service.py` | ✅ 核心 | 总编排智能体自动组队、Model 留白两阶段向导与动态算力预算切分服务 — 聚合 Harness SquadBlueprintComposer 与 SquadBudgetAllocator，提供 Phase-1 高层目标自动拆解蓝图与 SOUL prompt 生成、Phase-2 模型留白用户延迟选型绑定与活跃战队物化治理 | ✅ |
| `failure_policy_service.py` | ✅ 核心 | 子智能体 mid-task 失败 per-role 重启/升级/跳过声明式策略与自愈裁决服务 — 聚合 Harness SubagentFailurePolicyEngine，提供会话级角色声明式策略注册、mid-task 故障自愈裁决、重试上限熔断与审计历史追溯 | ✅ |
| `workspace_blueprint_service.py` | ✅ 核心 | 按项目/工作区自动复用团队 Blueprint 绑定与解析服务 — 聚合 Harness WorkspaceBlueprintStore，提供持久化/内存会话双模工作区团队蓝图绑定、自动复用决策判定与 LRU 推荐 | ✅ |
| `scope_guardrails_service.py` | ✅ 核心 | Orchestrator 越权防护与安全建队模式收敛审核服务 — 聚合 Harness ScopeGuardrailsEngine，提供会话级最小特权安全模式配置、高危越权工具自动裁剪拦截与扇出上限治理 | ✅ |
| `autonomous_loop_service.py` | ✅ 核心 | Goal/Kanban 驱动自主编排循环与步数看门狗服务 — 聚合 Harness AutonomousLoopController，提供会话隔离的自主巡航生命周期治理、安全看门狗步数配额、人工审批门禁与状态审计 | ✅ |
| `creator_mode_service.py` | ✅ 核心 | 自然语言创造模式预设合成、沙盒防御校验与多端漫游服务 — 聚合 Harness AgentPresetSynthesizer、DefensiveSandboxVerifier 与 UnifiedProfileRoamingGateway，提供意图编译、沙箱正反向防御检验与 Profile 漫游自愈 | ✅ |
| `tri_role_service.py` | ✅ 核心 | 规划-执行-可扩展评估三权分立与跨会话工件无损交接管线服务 — 聚合 Harness TriRolePipelineCoordinator，提供离散阶段状态机、独立客观评估准则核验与 Manifest 跨会话导出恢复 | ✅ |
| `skill_bundle_service.py` | ✅ 核心 | 技能包清单化一键批量加载与运行时生命周期预热管理器服务 — 聚合 Harness SkillBundleLifecycleManager，提供场景化技能包注册、多维度依赖与环境预热诊断探针及会话一键批量装载 | ✅ |
| `multi_bot_focus_service.py` | ✅ 核心 | 多Bot协同会话Mention焦点动态绑定与长会话防抖压实引擎服务 — 聚合 Harness MultiBotFocusAndCompactionGuard，提供视口焦点跟踪计算、滞后防抖压实评估与废弃流式卡片扫描清理 | ✅ |
| `mcp_payload_summarizer_service.py` | ✅ 核心 | 重 Payload MCP/大文档获取专用子 Agent 预置与结构化摘要防污染引擎服务 — 聚合 Harness HeavyMcpPayloadSummarizer 与 McpContaminationDoctor，提供重型 Payload 压缩摘要提取与直接注入污染审计诊断 | ✅ |
| `coding_wave_service.py` | ✅ 核心 | 编码型 Agent Profile 可选预置与多阶段 Wave 波次流水线编排服务 — 聚合 Harness CodingAgentWaveEngine，提供全栈开发波次流水线状态机、严格门禁校验与 orchestration_progress.json 导出 | ✅ |
| `subagent_lifecycle_service.py` | ✅ 核心 | 原生 Subagent 细粒度生命周期管控工具链服务 — 聚合 Harness SubagentLifecycleManager，提供会话隔离的 spawn、wait、list、send_input、kill 原子原语及审计历史治理 | ✅ |
| `mixed_fleet_service.py` | ✅ 核心 | 混合舰队预置服务 — 聚合 Harness MixedFleetCoordinator，提供本地记忆脑 Local Brain 与远端 24/7 执行器 Remote Executor 的心跳监控、结构化交接工件流转与状态同步 | ✅ |
| `zero_token_contract_service.py` | ✅ 核心 | 舰队可视化零 Token 契约服务 — 聚合 Harness ZeroTokenContractGuard，提供确定性运行时事件状态机镜像、Doctor 拦截与会话零 Token 审计报告 | ✅ |
| `cross_surface_bridge_service.py` | ✅ 核心 | 跨界面智能体活动对话汇入桥服务 — 聚合 Harness CrossSurfaceActivityBridge，管理外部来源（Tauri/CLI/Cron/Remote Office Clone）事件汇入、有界最近活动瀑布流与只读 presence 节点状态 | ✅ |
| `multi_lane_service.py` | ✅ 核心 | Pi Harness v2 会话内多 Lane 并行执行与共享追加树服务 — 聚合 Harness MultiLaneSessionCoordinator，提供会话隔离的多 Lane 创建、操作派发/完成/取消、单 Lane 互斥防乱序与共享 append-only tree 节点管理 | ✅ |
| `session_fork_service.py` | ✅ 核心 | Pi Harness v2 确定性子会话派生与安全重放重接服务 — 聚合 Harness DeterministicSessionForkManager，提供纯确定性 childSessionId 派生、Safe Replay 自动 reattach 杜绝 twin 孪生子会话污染、以及基于 branch 或 tree 的节点复制与父子血统检索 | ✅ |
| `token_budget_governance_service.py` | ✅ 核心 | 单模型多 Agent 共享上下文 Token 预算治理服务 — 聚合 Harness SharedTokenBudgetGovernor，管理共享模型全局与分角色 Token 配额、扇出前预算预检、Routing Overhead 与 Execution Payload 区分核算及 Doctor Nudge 智能预警 | ✅ |
| `pipeline_integrity_service.py` | ✅ 核心 | 开源可 inspect 工作流 · Handoff/Approval/Delivery 断点 Lint 与 Doctor 告警诊断服务 — 聚合 Harness PipelineIntegrityDoctor，提供完整流水线断点 Lint 分析、交接元数据/审批门禁/交付产物/验证步骤四类 Gap 诊断、决策链审查与一键 Auto-Heal 自动补全自愈 | ✅ |
| `specialist_summoning_service.py` | ✅ 核心 | 对话流自然语言/@召唤子专家协同与上下文结构化汇聚服务 — 聚合 Harness SpecialistSummoningCoordinator，提供垂直领域专家名册、输入框 @ 显式召唤与自然语言关键词意图感知、轻量独立沙箱子会话执行、以及结构化产物工件卡回流与会话历史治理 | ✅ |
| `swarm_mesh_service.py` | ✅ 核心 | SwarmForge 动态 Agent 集群拓扑编排器与多智能体网格通信服务 — 聚合 Harness SwarmTopologyOrchestrator，提供声明式五大拓扑（Star/Tree/Mesh/Pipeline/Ring）布局构建、动态平滑无损拓扑切换、弹性扩缩容、单节点角色/状态带上下文热迁移、P2P 单播/组播/广播消息总线投递与共享黑板乐观版本自增治理 | ✅ |
| `workspace_inheritance_service.py` | ✅ 核心 | 工作区上下文继承与提示词编织服务 — 聚合 Harness SubagentWorkspaceInheritanceEnricher，提供工作区分层规范发现（.rules > AGENTS.md > README.md）、Token 预算感知差分紧凑裁剪、角色自适应 Prompt 模板编织与审计留痕追溯 | ✅ |
| `replay_dedup_service.py` | ✅ 核心 | 多智能体历史工具调用回放合并与状态机同步增强服务 — 聚合 Harness ToolReplayHistoryMerger 与 SubagentStatusHarmonizer，提供连续等幂/只读工具调用紧凑批处理聚合与 Token 节省核算、写操作绝对隔离保护、单调递增子智能体状态机流转管理、以及心跳租约看门狗防假死自愈 | ✅ |
| `cloud_edge_relay_service.py` | ✅ 核心 | 云端-本地混合沙箱双向工件接力与网络受限爬取调度服务 — 聚合 Harness HybridArtifactSyncEngine 与 CloudEdgeEgressRelayCoordinator，提供 CAS 乐观版本校验与 Append-Only 链式工件增量同步、全文聚合、溯源时间线、以及本地网络出口受限爬取 SSRF 安全接力调度 | ✅ |
| `virtual_room_service.py` | ✅ 核心 | 多人多 Agent 实时协作虚拟空间、文件系统级协同与能力借用服务 — 聚合 Harness VirtualCoDevRoomManager，提供房间全生命周期管理、VFS 细粒度行块租约写锁与冲突实时拦截、零凭据 Agent 借用与代理执行、沙箱服务 Live 端口中继以及组织持久化审计事件记忆 | ✅ |
| `swarm_offload_service.py` | ✅ 核心 | 高并发子智能体集群调度与透明云沙箱算力卸载服务 — 聚合 Harness SwarmOffloadDispatcher 与 ResourceWatermarkMonitor，提供 10-15 并发子智能体批次高吞吐调度、宿主机 CPU/内存/并发任务实时水位监控与超限自动云端分流 | ✅ |
| `visual_timeline_service.py` | ✅ 核心 | 多智能体可视化时间轴与单 Agent 节点精准 Cherry-Pick 撤销服务 — 聚合 Harness TimelineJournal 与 CherryPickRollbackEngine，提供多维活动日志记录、时间轴查询过滤与外科手术式精准原子撤销 | ✅ |
| `clean_code_pipeline_service.py` | ✅ 核心 | Clean-Code 装配流水线与架构依赖关系 Lint 检查服务 — 聚合 Harness CleanCodeAssemblyPipelineEngine 与 ArchitectureDependencyLinter，提供五阶段单向步进流转、AST 静态分层依赖守卫与自动 DIP 重构推导 | ✅ |
| `fusen_service.py` | ✅ 核心 | 多智能体轻量级 Fusen 便签看板与共享状态同步服务 — 聚合 Harness FusenSharedBoard，提供无中心便签发布/解决、亚毫秒级阻塞判定、多维条件过滤与自动 TTL 过期清理 | ✅ |
| `vertical_presets_service.py` | ✅ 核心 | 五大垂直角色 Persona 预设与单 Bot 隔离沙箱测试服务 — 聚合 Harness PresetsCatalog、SubBotSandboxTester 与 A2AFlowInspector，提供 5 大垂直角色预置与自定义注册、单 Agent 隔离沙箱测试、A2A 交互追踪与循环检测 | ✅ |
| `council_service.py` | ✅ 核心 | 高阶决策多模型审议委员会与交叉仲裁共识服务 — 聚合 Harness CouncilDeliberationPipeline 与 ConsensusSynthesizer，管理多模型会话生命周期、盲审方案提交、匿名交叉质询与反驳答辩推进、置信度加权共识裁决合成 | ✅ |
| `kanban_dispatcher_service.py` | ✅ 核心 | 可视化看板多智能体工作流分发与任务卡片交接服务 — 聚合 Harness KanbanWorkflowDispatcher，管理五泳道卡片生命周期、智能体自动认领与交接流转、阻塞高亮与会话隔离看板流转 | ✅ |
| `cli_passthrough_service.py` | ✅ 核心 | 外部 CLI 子代理适配桥梁与官方订阅无感穿透调度服务 — 聚合 Harness CliProfileBundleRegistry 与 CliPassthroughScheduler，提供 Claude Code/Codex/Cursor CLI 探测与 BYOS 订阅复用、委派前如实隐私披露门禁、工作区文件访问边界防越权继承与不可篡改 SHA-256 出站账本记录 | ✅ |
| `dag_orchestrator_service.py` | ✅ 核心 | DAG 可视化编排、多拓扑校验、Cold Resume 断点恢复与双向驳回服务 — 聚合 Harness DagTopologyPlanner 与 ColdResumeEngine，提供拓扑无环/不可达节点校验、就绪节点并行执行推演、离线断点持久化与零冗余冷恢复、以及级联驳回重做机制 | ✅ |
| `kanban_queue_service.py` | ✅ 核心 | 多智能体持久任务看板队列与 12 路大规模并行 Dogfooding 运行器服务 — 聚合 Harness PersistentKanbanQueueManager 与 MassiveParallelBatchRunner，提供 5 态生命周期状态机、9 大协同工具、4 小时僵死心跳自动回收、Swarm 4 阶段拓扑与 `[swarm:blackboard]` 共享黑板、自动 Triage 细化与 Fan-out 分解、Git Worktree 隔离与防失控热熔断、Goal-Mode 验收标准循环、12 路并行调度与 `--resume` 检查点恢复、以及 HuggingFace JSONL 轨迹导出 | ✅ |
| `diamond_graph_service.py` | ✅ 核心 | 钻石拓扑编排器与盲审对抗审计服务 — 聚合 Harness DiamondGraphOrchestrator 与 BlindedAdversarialAuditor，管理会话隔离的 3-Tier 钻石工作流（Fan-out/Reduce/Synthesize）、假依赖静态修剪（False-Dependency Pruning）、Dead-Node Census 哨兵健康统计与即时重试、确定性 0-Token 规约、以及 CoT 物理隔离盲审与不可篡改现实锚点硬校验 | ✅ |
| `coauthoring_ledger_service.py` | ✅ 核心 | 人机多方围绕单一动态文档协同编辑的状态机账本与冲突仲裁服务 — 聚合 Harness LiveDocumentCoAuthoringLedger 与 CoAuthoringConflictArbitrator，管理会话隔离的文档块生命周期、块级租约读写互斥锁、携带语义意图的原子增量变更、不可变 Delta 审计追溯与贡献度大盘、以及人类优先/时间戳/隔离暂存提议的冲突仲裁与提议合并采纳 | ✅ |
| `socket_mesh_service.py` | ✅ 核心 | 基于 Unix Socket / 命名管道的极简去中心化同机多 Agent 协同网格服务 — 聚合 Harness MeshRegistry 与 SocketMeshNode，管理项目隔离的零 Broker 点对点自发现、跨平台 IPC 端点解析、原子信封协议（Prompt/Response/Ping/Pong）、防环路 Hops 严格拦截、异步 Pending Reply Future 跟踪与审计日志沉淀 | ✅ |
| `bot_forge_service.py` | ✅ 核心 | 对话式智能体与团队工厂、确定性创建流水线与建造者权限安全边界服务 — 聚合 Harness VerifiedCreationPipeline 与 BuilderSafetyEnvelope，管理会话隔离的 Agent 规格设计、权限衰减边界门禁、防递归繁衍防护、名称唯一性与语义重叠检测、Zero-model 干跑核验、原子化事务回滚与提示词克隆人设清洗 | ✅ |
| `external_bundle_service.py` | ✅ 核心 | 异构外部第三方 Agent 容器化收编与子代理 Profile Bundle 调度桥接服务 — 聚合 Harness ExternalAgentBundleRegistry 与 ExternalSubagentMultiplexer，管理官方（Claude Code/Codex/Gemini CLI）与自定义 Bundle 规范、工作区沙箱目录严格边界校验、破除单一 backend 全局排他锁的高并发无锁多路复用调度、以及运行实例流式日志清洗重塑与终止回收 | ✅ |
| `kanban_orchestrator_service.py` | ✅ 核心 | 多智能体持久化任务看板调度中枢与卡片 DAG 依赖拓扑分发服务 — 聚合 Harness KanbanCardLifecycleDispatcher 与 KanbanTaskDagEngine，管理多智能体持久看板、无环 DAG 依赖拓扑校验、卡片前置依赖完成自动解锁级联 Auto-Unblock Cascade、卡片沙箱隔离 tasks/{card_id}、工件原子挂载与人机一体拖拽干预 | ✅ |
| `fleet_router_service.py` | ✅ 核心 | 跨机分布式舰队 Profile Rail 全景导航轨、多网关拓扑自愈、离线缓冲与跨机工件中继服务 — 聚合 Harness MultiGatewayConnectionPool、HostGatewayContextInjector 与 CrossGatewayArtifactRelayService，管理 Darwin/Linux/Cloud 多机分布式网关节点注册、心跳遥测与健康自感知、断网离线指令 FIFO 排队缓冲与自愈排空 Auto-Healing Flush、Agent 宿主拓扑上下文自动注入、以及 SHA-256 跨网关安全工件中继校验 | ✅ |
| `graph_triage_service.py` | ✅ 核心 | 图工程自适应适用性评估门禁与并发 Token 预算熔断服务 — 聚合 Harness GraphApplicabilityTriageGate、PredictiveBudgetGuard 与 ElasticConcurrencyReducer，提供任务模式准入/拦截评估、扇出前置 Token 与花费预算核算、硬上限门禁校验、实时多档位弹性自适应并发节流（Healthy/Warning/Critical/Exhausted）以及危急状态提前局部优雅归约报告生成 | ✅ |
| `orthogonal_reviewer_service.py` | ✅ 核心 | 正交双视角审查门禁与零偏见盲审子代理服务 — 聚合 Harness OrthogonalReviewArbiter、IntentAlignmentReviewer 与 BlindCleanContextReviewer，提供意图一致性单项审查、全新盲态上下文代码审查、双审报告语义去重与缺陷综合仲裁、准入阻断判定与一键自动修复闭环 | ✅ |
| `delegation_transcript_service.py` | ✅ 核心 | 子 Agent 实时透明 Live Transcript 与后台委派任务持久化恢复服务 — 聚合 Harness SubagentLiveTranscriptEmitter、PersistentDelegationLedger、SmartApprovalGate 与 MoAReasoningEffortGovernor，提供后台任务生命周期与检查点管理、实时事件流订阅与推送、单次命令绑定 Smart Approvals 与 /deny 交互反馈、进程重启孤儿任务自愈恢复、以及 MoA 动态角色推理强度与 Token 预算分配 | ✅ |









---

## AgentGateway

所有 Agent 执行（General / FastSearch / Deep Research / Headless Wakeup）都经过 `AgentGateway`：

- **全局并发控制**：`Semaphore(AGENT_MAX_CONCURRENT)` 防止服务器过载。后台异步唤醒任务（Headless）同样受此保护，防止与前台活跃会话抢占资源导致 OOM 或 429 限流。
- **内存压力熔断**：实现 `PressureSubscriber` 协议，订阅 Harness `MemoryPressureMonitor`。当压力 ≥ CRITICAL 时，阻塞新 Agent 执行（已运行的不受影响），直到压力降至 WARNING/NORMAL 或 `queue_timeout` 到期。
- **排队超时**：等待超过 `AGENT_QUEUE_TIMEOUT` 秒抛 `AgentQueueTimeout`；异常携带 `reason`（`memory_pressure` / `user_limit` / `global_limit` 三态）与 `active_sessions` 占用者快照，供 `stream_finalize` 渲染结构化 SSE 错误（`error_kind=concurrency_limit` + `diagnostic_result` 含 i18n 用户文案与 resolution_steps）
- **执行看门狗**：idle 静默判定 — 事件流每次产出事件即续期 deadline（分层阈值：默认 `AGENT_EXECUTION_TIMEOUT`、fission 2x、goal 3600s）；静默间隙超过阈值或总时长超过硬顶 `AGENT_EXECUTION_HARD_CEILING`(3600s) 抛 `AgentExecutionTimeout`（活跃流不因总时长被杀）
- **中断支持**：`interrupt()` 信号全部运行中 Agent 停止；`interrupt_session(chat_id)` 单会话停止；`get_active_message_id(chat_id)` 供 chat cancel 同步 harness `CancellationRegistry`
- **优雅排空**：`begin_drain(timeout=120)` 进入 draining 状态 → 拒绝新 turn（`AgentDrainingError`）→ 等待 `_active_sessions` 清空或超时 → 超时后 `interrupt_all()` 强制中断。`cancel_drain()` 撤销排空重新接受请求。`lifespan._shutdown()` 和 `POST /shutdown` API 均在关闭组件前先 drain；CP 销毁沙箱前通过 `POST /api/v1/system/drain` 触发（休眠不 drain：回收器只休眠无在途工作的沙箱），`DELETE /api/v1/system/drain` 取消
- **活跃会话追踪**：`ActiveSessionInfo` 元数据（chatId、agentType、agentId、elapsedSeconds、current_message_id），`get_active_sessions()` 和 `get_available_slots()` 供 Multi-Pane 工作台和 Fleet Overview 使用
- **API 端点**：`GET /agents/active-sessions`（Multi-Pane 状态）、`POST /api/agent/interrupt`（远程中断）、`POST /agents/chats/{chat_id}/cancel`（scoped pair 单 chat 取消：interrupt + registry）

环境变量配置：`AGENT_MAX_CONCURRENT`(20), `AGENT_MAX_PER_USER`(3), `AGENT_QUEUE_TIMEOUT`(10s), `AGENT_EXECUTION_TIMEOUT`(300s, idle 阈值), `AGENT_EXECUTION_HARD_CEILING`(3600s, 总时长硬顶)

---

## Saved Agent 运行时契约

业务层统一管理以下关键字段，并保证它们可以跨入口稳定读写：

- `agent_type`（`individual` | `team`，团队型 Agent 运行时自动注入 Leader Operating Protocol + 成员名册）
- `skill_configs`（per-skill `is_core` + optional `instance_name` for multi-instance skills；save 时 server 校验 instance 存在）
- `skill_ids`
- `mounted_skill_ids`（legacy DB column；Agent execution runtime 与产品 UI 不读；skill evolution CoW 仍通过 `evolution_review/disk_content.py` 维护）
- `mcp_ids`
- `mcp_tool_selections`（per-MCP-server 工具白名单 `{server_name: [tool_name, ...]}`，由前端智能体编辑器管理，注入 `MCPConfig.tool_include` 实现工具级最小权限）
- `enabled_builtin_tools`
- `subagent_ids`
- `security_overrides`
- `default_security_preset`（per-agent 默认会话安全预设 hitl/accept_edits/explore；前端绑定/切换该 Agent 及进入任意聊天时按默认重置会话 `security_preset`（无默认回落 hitl），后端仅透出字段不套运行时逻辑，Cron/渠道无人值守保持 fail-closed）
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
