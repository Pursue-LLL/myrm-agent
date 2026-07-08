# stream_session 模块架构

General Agent SSE 流式会话的服务层实现。HTTP 路由装饰器保留在 `app/api/agents/general_agent/streaming.py`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `orchestrator.py` | 核心 | 流式会话主编排：持久化用户消息、参数转换、Goal/Steering 注册、装配 `AgentStreamSession` | ✅ |
| `stream_session_types.py` | 核心 | `AgentStreamSession` 数据类与断连宽限常量 | ✅ |
| `stream_disconnect.py` | 核心 | PWA 断连宽限与 Offline Durable Guardian 注册 | ✅ |
| `stream_chunks.py` | 核心 | SSE 预检编排（凭据、Vision fallback、entitlement gap）+ `generate_cancellable_stream` 生成器主体;`BaseException` 兜底捕获 → `yield_stream_exception_chunks`,`finally` 调 `finalize_agent_stream_session` | ✅ |
| `stream_loop.py` | 核心 | Agent 主流 SSE 循环;cancel 分支调 `kill_session_jobs(chat_id)` 释放后台 bash 任务;检测 `tool_approval_request`/`approval_intercepted` 并通过 `WorkspaceMultiplexer` 广播 `awaiting_approval`/`generating` 会话状态 | ✅ |
| `stream_finalize.py` | 核心 | 流错误处理与会话 teardown;`asyncio.CancelledError` 分支调 `kill_session_jobs(chat_id)` 覆盖 SSE 硬断;finalize 末尾 fire-and-forget 触发 `trigger_skill_evolution`（普通对话按 tool_steps 门控，DW 直接传 collector content） | ✅ |
| `stream_pump.py` | 核心 | 将 chunk 泵入 `GlobalStreamRegistry` buffer 并返回 `StreamingResponse` | ✅ |
| `stream_generator.py` | 门面 | 对外 re-export：`AgentStreamSession`、`build_disconnect_checker`、`generate_cancellable_stream`、`launch_buffered_stream` | ✅ |
| `stream_lane_factory.py` | 核心 | Dynamic Workflow / Deep Research / Fast Lane / Consensus SSE 工厂 | ✅ |
| `reconnect.py` | 辅助 | Last-Event-ID SSE 重连 | ✅ |
| `risk_gate.py` | 辅助 | 流式输入 risk 拦截 | ✅ |
| `entitlement_gap_preflight.py` | 辅助 | 用户消息 entitlement gap 预检 → 早期 capability_gap SSE（不改 Turn1 工具绑定） | ✅ |

## 依赖关系

- `app/services/agent/params/` — 请求参数转换
- `app/services/agent/streaming_support/` — SSE 辅助与内容收集
- `app/services/agent/streaming.py` — Harness 流式桥接
- `app/services/agent/evolution/engine.py` — skill evolution 后台触发
- `myrm_agent_harness.agent.streaming.stream_buffer` — 全局流 buffer
