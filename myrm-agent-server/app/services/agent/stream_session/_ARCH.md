# stream_session 模块架构

General Agent SSE 流式会话的服务层实现。HTTP 路由装饰器保留在 `app/api/agents/general_agent/streaming.py`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `orchestrator.py` | 核心 | 流式会话主编排：持久化用户消息、参数转换、Goal/Steering 注册、装配 `AgentStreamSession`；Memory Brief 预检结果写入 `memory_brief_status`（ready/skipped） | ✅ |
| `stream_session_types.py` | 核心 | `AgentStreamSession` 数据类与断连宽限常量 | ✅ |
| `stream_disconnect.py` | 核心 | PWA 断连宽限与 Offline Durable Guardian 注册 | ✅ |
| `memory_brief.py` | 核心 | 发送后首 token 前的记忆简报预计算（同源 snapshot + 预览 payload） | ✅ |
| `_memory_status_helpers.py` | 辅助 | Memory brief 状态组装 SSOT：统一构建 `memory_brief_status`（`ready/skipped` + `source(preflight/runtime_fallback)` + `injection`）供 `stream_loop` 与 `stream_finalize` 复用，避免双实现漂移；injection 校验复用 harness 公共契约，并导出 brief 状态契约供前端同构测试；内置 Prometheus 观测（含 `not_applied` 原因聚合）与 unknown 枚举告警 | ✅ |
| `stream_chunks.py` | 核心 | SSE 预检编排（凭据、Vision fallback、entitlement gap）+ `generate_cancellable_stream` 生成器主体;`BaseException` 兜底捕获 → `yield_stream_exception_chunks`,`finally` 调 `finalize_agent_stream_session` | ✅ |
| `stream_loop.py` | 核心 | Agent 主流 SSE 循环;首 token 前发射 `memory_brief` 预览事件（若预计算成功）;`message_end` 总是尝试读取 harness memory telemetry（budget/injection）并注入 `memory_brief_snapshot_id` 与 `memory_brief_status`，并上报 stream 阶段状态观测；当预检状态缺失但有 runtime injection 时降级输出 `skipped + source=runtime_fallback + injection`，避免 resume 场景诊断断链；cancel 分支调 `kill_session_jobs(chat_id)` 释放后台 bash 任务;检测 `tool_approval_request`/`approval_intercepted` 并通过 `WorkspaceMultiplexer` 广播 `awaiting_approval`/`generating` 会话状态;routing_tier=reasoning 时通过 `workflow_escalation` 检测并发射 `workflow_suggestion` 非阻塞建议事件 | ✅ |
| `workflow_escalation.py` | 辅助 | 纯规则 DW Engine 建议检测器：多目标/可拆分结构识别（0 LLM 调用） | ✅ |
| `stream_finalize.py` | 核心 | 流错误处理与会话 teardown;致命异常（MyrmLLMError/AgentExecutionTimeout/Resume fail/通用 Exception）设置 `session.had_fatal_error`；`asyncio.CancelledError` 分支调 `kill_session_jobs(chat_id)` 覆盖 SSE 硬断;持久化阶段总是尝试读取 harness memory telemetry 并写入 `memoryBriefSnapshotId`/`memoryBriefStatus`（含 `injection` 语义），并上报 persist 阶段状态观测；当缺少预检状态但 runtime injection 存在时持久化 `skipped + source=runtime_fallback + injection`，`memoryBudget` 保持独立于 citations 持久化；归一化后的 `memoryBriefStatus` 额外进入 server→control-plane 聚合遥测队列（批量上报）;finalize 末尾 fire-and-forget 触发 `trigger_skill_evolution`（普通对话按 tool_steps 门控，DW 直接传 collector content） | ✅ |
| `stream_pump.py` | 核心 | 将 chunk 泵入 `GlobalStreamRegistry` buffer 并返回 `StreamingResponse`；离线长任务完成/失败时创建 SystemNotification（`stream_had_error` chunk 检测 + `session.had_fatal_error` 语义标志双保险分流 success/error 类型） | ✅ |
| `stream_generator.py` | 门面 | 对外 re-export：`AgentStreamSession`、`build_disconnect_checker`、`generate_cancellable_stream`、`launch_buffered_stream` | ✅ |
| `stream_lane_factory.py` | 核心 | Dynamic Workflow / Deep Research / Fast Lane / Consensus SSE 工厂；DR 完成回调经 `resolve_wiki_vault_path()` 写 raw + `get_wiki_archiver()` 入队编译 | ✅ |
| `reconnect.py` | 辅助 | Last-Event-ID SSE 重连 | ✅ |
| `risk_gate.py` | 辅助 | 流式输入 risk 拦截 | ✅ |
| `entitlement_gap_preflight.py` | 辅助 | 用户消息 entitlement gap 预检 → 早期 capability_gap SSE（不改 Turn1 工具绑定） | ✅ |

## 依赖关系

- `app/services/agent/params/` — 请求参数转换
- `app/services/agent/streaming_support/` — SSE 辅助与内容收集
- `app/services/agent/streaming.py` — Harness 流式桥接
- `app/services/agent/evolution/engine.py` — skill evolution 后台触发
- `app/services/wiki/vault_resolver.py` + `vault_service.py` — Deep Research vault 与 API 共用 wiki 路径与 archiver
- `myrm_agent_harness.agent.streaming.stream_buffer` — 全局流 buffer
