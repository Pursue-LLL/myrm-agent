# stream_session 模块架构

General Agent SSE 流式会话的服务层实现。HTTP 路由装饰器保留在 `app/api/agents/general_agent/streaming.py`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `orchestrator.py` | 核心 | 流式会话主编排：入口 **`_reject_legacy_consensus_request`**（removed `consensus` → 400）；**`ChatSessionReservation.try_reserve` 在 persist 前**（零 TOCTOU）；busy → `agent_busy_streaming_response`；persist 后 **`apply_migration_bound_project`**；非 resume 路径经 `TurnPrewarmCoordinator.join_for_turn` 并行 join agent cache + memory brief；成功路径 `transfer_to_stream` + `launch_buffered_stream`；`finally` release 预占 | ✅ |
| `stream_session_types.py` | 核心 | `AgentStreamSession` 数据类与断连宽限常量；承载流式会话起点时钟与端到端 TTFT 采样值（`stream_started_at_monotonic` / `stream_ttft_ms`） | ✅ |
| `stream_disconnect.py` | 核心 | PWA 断连宽限与 Offline Durable Guardian 注册 | ✅ |
| `memory_brief.py` | 核心 | 发送后首 token 前的记忆简报预计算（同源 snapshot + 预览 payload） | ✅ |
| `_memory_status_helpers.py` | 辅助 | Memory brief 状态组装 SSOT：统一构建 `memory_brief_status`（`ready/skipped` + `source(preflight/runtime_fallback)` + `injection`）供 `stream_loop` 与 `stream_finalize` 复用，避免双实现漂移；injection 校验复用 harness 公共契约，并导出 brief 状态契约供前端同构测试；内置 Prometheus 观测（含 `not_applied` 原因聚合）与 unknown 枚举告警 | ✅ |
| `stream_chunks.py` | 核心 | SSE 预检编排（凭据、Vision fallback、**config gap / migration readiness gap / entitlement gap 三轨**；**turn prewarm** 等待态 STATUS `turn_prewarm_agent` / `turn_prewarm_memory`）+ `generate_cancellable_stream` 生成器主体;`BaseException` 兜底捕获 → `yield_stream_exception_chunks`,`finally` 调 `finalize_agent_stream_session` | ✅ |
| `stream_loop.py` | 核心 | Agent 主流 SSE 循环;路由 Fast Lane / Wiki Knowledge Lane / GeneralAgent;首 token 前发射 `memory_brief` 预览;`message_end` 注入 `stream_ttft_ms`、`turn_prewarm_hit` / `turn_prewarm_ms` 与 memory brief 遥测;检测 `clarification_required` / `directory_request_required` 挂起表单超时 | ✅ |
| `workflow_escalation.py` | 辅助 | 纯规则 DW Engine 建议检测器：多目标/可拆分结构识别（0 LLM 调用） | ✅ |
| `stream_finalize.py` | 核心 | 流错误处理与会话 teardown；`ConfigIncompleteError`（含 OpenAPI Turn1 加载失败 `openapi_load_failed` / 预算 `openapi_direct_budget_exceeded`）→ 用户可见 SSE error + resolution_steps；回合正常结束后清除 `InterruptedTurnMarker`（crash auto-continue write-ahead marker）；致命异常（MyrmLLMError/AgentExecutionTimeout/Resume fail/通用 Exception）设置 `session.had_fatal_error`；`asyncio.CancelledError` 分支调 `kill_session_jobs(chat_id)` 覆盖 SSE 硬断；当请求携带 `turn_capability_telemetry` 时，异常分支与 finalize 终态会写入 server authoritative `send_failed/send_completed`（HITL pending 不提前落终态，避免误判）；持久化阶段总是尝试读取 harness memory telemetry 并写入 `memoryBriefSnapshotId`/`memoryBriefStatus`（含 `injection` 语义），并持久化端到端 TTFT（`streamTtftMs`）；当缺少预检状态但 runtime injection 存在时持久化 `skipped + source=runtime_fallback + injection`，`memoryBudget` 保持独立于 citations 持久化；persist 前调用 `merge_memory_citation_fallback` 回填 `citedMemoryIds`；citations 去重保持首见顺序确保首屏与刷新后展示一致；归一化后的 `memoryBriefStatus` 额外以 `phase=persist` 进入 server→control-plane 聚合遥测队列（批量上报）；若请求携带 migration readiness anchor，则在 finalize 记录首轮执行结果（success/failed/no_output）回写导入账本用于 readiness↔首轮成功率对账；finalize 末尾在 profile `skill_manage` ON 时 fire-and-forget 触发 `trigger_skill_evolution`（普通对话按 tool_steps 门控，DW 直接传 collector content）；跨轮次 `data_update` 调用 `ui_artifact_patch.patch_ui_artifact_data_updates` 写回宿主消息；GA LangGraph resume 成功或 DR `status clarify/resolved` 后倒序扫描 assistant 行，将最新未答 `extra_data.clarification.answered=true` 写回 DB（与 ui_artifact_patch 同模式，不用 API message_id）；pending clarification 或 collector `clarification.answered=false` 时注册 900s no_answer auto-resume；pending directoryRequest 时注册 900s deny-grant auto-resume（优先级 clarify > directory > approval 300s） | ✅ |
| `turn_capability_terminal.py` | 辅助 | 单轮 Skill/MCP 覆写终态锚点：消费 `AgentRequest.turn_capability_telemetry`，服务端落库 `send_completed/send_failed`，并把流异常归一化到 `failure_reason` 枚举 | ✅ |
| `migration_readiness_anchor.py` | 辅助 | 迁移 readiness 双锚记录助手：消费 `migration_readiness_anchor`（import_batch_id），按 stream finalize 信号归类首轮结果（success/failed/no_output）；preflight 未写入 live 状态时 finalize 再 live-resolve 一次，永不用 anchor 快照作 truth；函数内 lazy import `get_session_factory`（与 conftest patch 一致） | ✅ |
| `migration_bound_project.py` | 辅助 | 迁移 vault bind 同窗 handoff：persist 后、convert 前消费 `migration_bound_project_id`，`move_chat_to_project` 写 SSOT；chat 已有 project_id 或 resume 时跳过 | ✅ |
| `migration_readiness_preflight.py` | 辅助 | 迁移 readiness 软门禁：anchor 携带 batch_id 时 live-resolve readiness，在 stream 早期对 warning/critical 发射 issue-aware `capability_gap`（含 settings_path）；生产仅 async `resolve_and_build_*`；函数内 lazy import `get_session_factory`；不阻断执行、不改 Turn1 工具绑定 | ✅ |
| `stream_pump.py` | 核心 | 将 chunk 泵入 `GlobalStreamRegistry` buffer；**multiplexed 成功 → JSON accepted**；非 multiplex → `StreamingResponse`；离线长任务 SystemNotification | ✅ |
| `session_reservation.py` | 辅助 | `ChatSessionReservation`：orchestrator persist 前 gateway 预占/early exit release/transfer 至 execute_stream | ✅ |
| `stream_busy.py` | 辅助 | `agent_busy_streaming_response`：HTTP 200 + SSE `{type:error, error_type:AgentBusyError, status_code:409}` SSOT | ✅ |
| `stream_generator.py` | 门面 | 对外 re-export：`AgentStreamSession`、`build_disconnect_checker`、`generate_cancellable_stream`、`launch_buffered_stream` | ✅ |
| `stream_lane_factory.py` | 核心 | Dynamic Workflow / Deep Research / Fast Lane SSE 工厂；DR 完成回调经 `resolve_wiki_vault_path(agent_id)` 写 raw + 编译入队 | ✅ |
| `moa_overlay_setup.py` | 辅助 | Agent-loop MoA overlay：解析 `engineParams.moa_overlay` reference 模型并构建 harness middleware；无可用 ref 时返回 None + `resolve_moa_overlay_skip_reason` 供 stream 发 `moa_overlay_skipped` SSE | ✅ |
| `lanes/` | 核心 | Chat 专用 lane 流（见 [lanes/_ARCH.md](lanes/_ARCH.md)） | ✅ |
| `reconnect.py` | 辅助 | Last-Event-ID SSE 重连 | ✅ |
| `risk_gate.py` | 辅助 | 流式输入 risk 拦截 | ✅ |
| `entitlement_gap_preflight.py` | 辅助 | Stream 早期 factual gap SSE（不改 Turn1 工具绑定）：render_ui profile ON 但渠道不可挂载 → `reason=surface_unavailable` + `display_message`；web_search profile ON 但 runtime 不可用 → `reason=not_configured|unreachable` + `settings_path=/settings/search`；substring enable-and-resend entitlement toasts removed | ✅ |

## 依赖关系

- `app/services/agent/params/` — 请求参数转换
- `app/services/agent/execution_cache/prewarm/` — turn1 冷启动预热（EmptyChat focus + send join）
- `app/services/agent/memory_brief_telemetry/` — sandbox Control Plane memory brief 状态批量遥测（`stream_loop` / `stream_finalize` enqueue；用户可见 SSE 契约见 `_memory_status_helpers.py`）
- `app/services/agent/streaming_support/` — SSE 辅助与内容收集
- `app/services/agent/streaming.py` — Harness 流式桥接
- `app/services/agent/evolution/engine.py` — skill evolution 后台触发
- `app/services/wiki/vault_resolver.py` + `vault_service.py` — Deep Research vault 与 API 共用 wiki 路径与 archiver
- `myrm_agent_harness.agent.streaming.stream_buffer` — 全局流 buffer
