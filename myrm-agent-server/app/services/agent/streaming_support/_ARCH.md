# streaming_support 模块架构

Agent 流式传输辅助工具。从 API 层下沉至 services，供 orchestrator 与 reconnect 等模块复用。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `sse_helpers.py` | 核心 | SSE 格式化、审批超时调度、压缩耗尽检测、错误 chunk 生成 | ✅ |
| `sse_failover_emitter.py` | 核心 | harness `FailoverEmitter` 协议的 SSE 适配器：把模型故障转移/恢复事件桥接成 `model_failover` / `model_recovery` SSE chunk，并通过 race-style merge 与主 chunk 流交错输出 | ✅ |
| `stream_collector.py` | 核心 | 流内容收集器，用于 assistant 消息持久化与 sibling group 追踪 | ✅ |

## 依赖关系

- `app/schemas/streaming.py` — SSE 信封类型
- `app/services/agent/params/` — Agent 参数类型
- `myrm_agent_harness.toolkits.llms.fallback` — `FailoverEmitter` Protocol / `with_failover_emitter` 上下文管理器
