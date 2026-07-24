# streaming_support 模块架构

Agent 流式传输辅助工具层，供 orchestrator、reconnect 与 API 流式路由复用。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `sse_helpers.py` | 核心 | SSE 格式化、审批/澄清 HITL 超时调度（900s no_answer auto-resume）、压缩耗尽检测、错误 chunk 生成 | ✅ |
| `sse_failover_emitter.py` | 核心 | harness `FailoverEmitter` 协议的 SSE 适配器：把模型故障转移/恢复事件桥接成 `model_failover` / `model_recovery` SSE chunk，并通过 race-style merge 与主 chunk 流交错输出 | ✅ |
| `stream_collector.py` | 核心 | 流内容收集器；memory citation 持久化；`message_end` 指标归档（usage/cost/tokenEconomics/`stream_ttft_ms`→`streamTtftMs`）；`kanban_add_task`/`cron_manage` 成功结果写入 extra_data；`clarification_required`→`extra_data.clarification`；`status.phase=plan_confirm|clarify`→`planConfirmation`/`clarification.answered`；`ui_update`/`data_update` 深合并；跨轮次 `data_update` 排队并在流式阶段即时写回宿主消息，finalize 再次兜底 | ✅ |
| `stream_collector_helpers.py` | 辅助 | `StreamContentCollector` 纯函数：tool 结果解析、UI data 深合并、HITL clarification/planConfirm 持久化 payload 构建、string-keyed dict 规范化 | ✅ |
| `citation_persistence.py` | 辅助 | finalize 阶段 citation fallback：当 collector 未写入 `citedMemoryIds` 时，从 harness `MemoryManager.last_cited_memory_ids` 回填 | ✅ |
| `multiplexer.py` | 核心 | `WorkspaceMultiplexer` — 全局 SSE 事件总线，单连接多会话广播，绕过浏览器 6 连接限制 | ✅ |

## 依赖关系

- `app/schemas/streaming.py` — SSE 信封类型
- `app/services/agent/params/` — Agent 参数类型
- `myrm_agent_harness.toolkits.llms.fallback` — `FailoverEmitter` Protocol / `with_failover_emitter` 上下文管理器
