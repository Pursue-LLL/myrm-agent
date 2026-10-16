# streaming_support 模块架构

Agent 流式传输辅助工具层，供 orchestrator、reconnect 与 API 流式路由复用。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `sse_helpers.py` | 核心 | SSE 格式化与解析：错误 chunk 生成、压缩耗尽检测、审批超时 / 澄清 / 目录请求中断帧识别（纯解析，无调度副作用） | ✅ |
| `hitl_timeout.py` | 核心 | HITL 中断超时的武装与恢复 SSOT：`arm_interrupt_timeout`（审批 300s / 澄清 900s，优先级 clarify > approval；已停在中断但未武装的流（如计划确认、浏览器接管）立即 `reopen` 调度键，使其后的 resume 不被误判为已被超时处理）；两类超时回调共用 `_resume_after_timeout`：先 `gateway.reserve_session` 抢占会话（用户同时新开回合时放弃本次恢复并 `reopen`）→ 以 `Command(resume=…)` 经 gateway 运行续写（`finally` 释放未被流接管的预占）→ 澄清把已落库的卡片标记已答复并写入 `answerRecord`（`HitlAnswerRecord`：`by: user|timeout` + 续写值；先于持久化续写，续写里的新卡片保持未答复；标记落库失败只记警告，不丢续写）→ 持久化续写 → 武装下一个中断；运行失败时重开调度键，使人工回答仍可通过 | ✅ |
| `sse_failover_emitter.py` | 核心 | harness `FailoverEmitter` 协议的 SSE 适配器：把模型故障转移/恢复事件桥接成 `model_failover` / `model_recovery` SSE chunk，并通过 race-style merge 与主 chunk 流交错输出 | ✅ |
| `stream_collector.py` | 核心 | 流内容收集器（回复文本经 harness `AnswerDraft`：模型切换等恢复重放只丢最近一次工具步骤之后的在途段落，之前已落定的文字保留）；`async_user_message` 收集与 `resolve_async_user_message` 运行时决策确认态标记（同步更新内存中 `_async_user_messages` 的 `status: "resolved"` 与 `resolvedText`，确保流结束落库时原子持久化）；`tool_result_details` 捕获并落库入 `extra_data.tool_result_details` 供会话树分支状态折叠；memory citation 持久化；`tasks_steps` 按 `tool_call_id` merge；`tool_evicted_ref` 绑定 progressStep（tool_call_id 优先）并持久化 `evicted_stored_chars/evicted_total_lines/evicted_storage_truncated`，支持分 stream（`stdout`→`evicted_file_ref` 系、`stderr`→`evicted_stderr_file_ref` 系，stderr 认领不受 stdout 已认领影响）；先于 step 到达的 evicted 引用进入 pending 队列，`tasks_steps`/`message_end` 阶段按 step 认领且 stdout+stderr 不互相覆盖；`message_end` 指标归档（usage/cost/tokenEconomics/`stream_ttft_ms`→`streamTtftMs`）；`kanban_add_task`/`cron_manage` 成功结果写入 extra_data；`clarification_required`→`extra_data.clarification`；`status.phase=plan_confirm|clarify`→`planConfirmation`/`clarification.answered`（`clarify` / `resolved` 同时保留事件携带的 `answerRecord`）；reasoning 落库前执行 sanitize+scrub，且采用字符预算上限并在截断时写入 `reasoningTruncated/reasoningCharLimit` 元数据；**restart 协议**：凡会使 LLM 从头重跑本轮的恢复（failover STATUS `model_failover`/`safety_fallback_active`、`transient_retry`、`empty_response_recovery`、`tool_call_retry`、`vision_fallback_recovery`、`media_rejected_recovery`、`context_compaction` 等 `restart:true` STATUS、`model_escalated` 事件）均通过 `_discard_draft` 幂等清空已收集的 content/reasoning 废稿（主模型失败前流出的部分内容会被 fallback 从头重跑覆盖，持久化不能拼接废稿+完整回答）；failover STATUS 与 `model_failover` SSE 双通道合并为单条 progress step（`_append_failover_step` 按 `model_failover*` 前缀或 `safety_fallback_active` 去重并取更完整的 from→to 标签）；`model_escalated` 事件同样持久化 `model_escalated` progress step（from→to 标签），与实时展示一致；`_sync_run_digest` 推送 RunDigest 至 `RunDigestStore`；`tool_end` 携带 `skill_mutation_batch_id`（`ServerSkillManageBatchHook` 提交后经工具进度通道广播）时由 `mutation_batch_stream.link_batch_to_step` 关联到最新未关联批次的 skill_manage 步骤，随 `progressSteps` 落库 | ✅ | 
| `stream_collector_helpers.py` | 辅助 | `StreamContentCollector` 纯函数：tool 结果解析、HITL clarification/planConfirm 持久化 payload 构建、string-keyed dict 规范化 | ✅ |
| `citation_persistence.py` | 辅助 | finalize 阶段 citation fallback：当 collector 未写入 `citedMemoryIds` 时，从 harness `MemoryManager.last_cited_memory_ids` 回填 | ✅ |
| `multiplexer.py` | 核心 | `WorkspaceMultiplexer` — 全局 SSE 事件总线，单连接多会话广播，绕过浏览器 6 连接限制 | ✅ |

## 依赖关系

- `app/schemas/streaming.py` — SSE 信封类型
- `app/services/agent/params/` — Agent 参数类型
- `myrm_agent_harness.toolkits.llms.fallback` — `FailoverEmitter` Protocol / `with_failover_emitter` 上下文管理器
