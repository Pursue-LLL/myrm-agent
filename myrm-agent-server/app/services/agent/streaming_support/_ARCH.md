# streaming_support 模块架构

Agent 流式传输辅助工具层，供 orchestrator、reconnect 与 API 流式路由复用。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `sse_helpers.py` | 核心 | SSE 格式化、审批/澄清/目录 HITL 超时调度（900s auto-resume，resume 前经 `build_agent_runtime_context` 注入 execution_mode + disabled_skill_roots）、压缩耗尽检测、错误 chunk 生成 | ✅ |
| `sse_failover_emitter.py` | 核心 | harness `FailoverEmitter` 协议的 SSE 适配器：把模型故障转移/恢复事件桥接成 `model_failover` / `model_recovery` SSE chunk，并通过 race-style merge 与主 chunk 流交错输出 | ✅ |
| `stream_collector.py` | 核心 | 流内容收集器；memory citation 持久化；`tasks_steps` 按 `tool_call_id` merge；`tool_evicted_ref` 绑定 progressStep（tool_call_id 优先）并持久化 `evicted_stored_chars/evicted_total_lines/evicted_storage_truncated`，支持分 stream（`stdout`→`evicted_file_ref` 系、`stderr`→`evicted_stderr_file_ref` 系，stderr 认领不受 stdout 已认领影响）；先于 step 到达的 evicted 引用进入 pending 队列，`tasks_steps`/`message_end` 阶段按 step 认领且 stdout+stderr 不互相覆盖；`message_end` 指标归档（usage/cost/tokenEconomics/`stream_ttft_ms`→`streamTtftMs`）；`kanban_add_task`/`cron_manage` 成功结果写入 extra_data；`clarification_required`→`extra_data.clarification`；`status.phase=plan_confirm|clarify`→`planConfirmation`/`clarification.answered`；`ui_update`/`data_update` 深合并；跨轮次 `data_update` 排队并在流式阶段即时写回宿主消息，finalize 再次兜底；reasoning 落库前执行 sanitize+scrub，且采用字符预算上限并在截断时写入 `reasoningTruncated/reasoningCharLimit` 元数据；**restart 协议**：凡会使 LLM 从头重跑本轮的恢复（failover STATUS `model_failover`/`safety_fallback_active`、`transient_retry`、`empty_response_recovery`、`tool_call_retry`、`vision_fallback_recovery`、`media_rejected_recovery`、`context_compaction` 等 `restart:true` STATUS、`model_escalated` 事件）均通过 `_discard_draft` 幂等清空已收集的 content/reasoning 废稿（主模型失败前流出的部分内容会被 fallback 从头重跑覆盖，持久化不能拼接废稿+完整回答）；failover STATUS 与 `model_failover` SSE 双通道合并为单条 progress step（`_append_failover_step` 按 `model_failover*` 前缀或 `safety_fallback_active` 去重并取更完整的 from→to 标签）；`model_escalated` 事件同样持久化 `model_escalated` progress step（from→to 标签），与实时展示一致；`_sync_run_digest` 推送 RunDigest 至 `RunDigestStore` | ✅ | 
| `stream_collector_helpers.py` | 辅助 | `StreamContentCollector` 纯函数：tool 结果解析、UI data 深合并、HITL clarification/directoryRequest/planConfirm 持久化 payload 构建、string-keyed dict 规范化 | ✅ |
| `citation_persistence.py` | 辅助 | finalize 阶段 citation fallback：当 collector 未写入 `citedMemoryIds` 时，从 harness `MemoryManager.last_cited_memory_ids` 回填 | ✅ |
| `multiplexer.py` | 核心 | `WorkspaceMultiplexer` — 全局 SSE 事件总线，单连接多会话广播，绕过浏览器 6 连接限制 | ✅ |

## 依赖关系

- `app/schemas/streaming.py` — SSE 信封类型
- `app/services/agent/params/` — Agent 参数类型
- `myrm_agent_harness.toolkits.llms.fallback` — `FailoverEmitter` Protocol / `with_failover_emitter` 上下文管理器
