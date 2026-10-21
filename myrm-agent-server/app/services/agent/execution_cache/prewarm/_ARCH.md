# prewarm 模块

---

## 架构概述

Chat turn1 冷启动优化：EmptyChat / MessageInput focus 触发后台并行预热（`execution_cache` agent build + memory brief snapshot），Send 路径 `join_for_turn` 复用缓存，`stream_pipeline` 经 `coalesced_acquire` 与 prewarm 共用一个 in-flight task。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `coordinator.py` | 核心 | `TurnPrewarmCoordinator`: ensure_warming / join_for_turn / coalesced_acquire / cancel_scope | ✅ |
| `brief_cache.py` | 核心 | scope+fingerprint TTL 缓存 memory brief preview/snapshot | ✅ |
| `params.py` | 辅助 | `resolve_prewarm_agent_params` — 无用户消息构建 GeneralAgentParams | ✅ |
| `types.py` | 辅助 | `TurnPrewarmJoinResult` | ✅ |

API：`app/api/agents/general_agent/prewarm.py` — `POST/DELETE /agents/chats/{chat_id}/prewarm`。

FE：`useChatTurnPrewarm.ts` module-level inflight dedupe — EmptyChat / MessageInput / AgentConfigPanel 共享单 POST；autoOnMount 不在 unmount 时 cancel（避免首条发送 EmptyChat→Chat 切换误杀 warm）。

Orchestrator：`stream_session/orchestrator.py` 在 send 路径调用 `join_for_turn`（默认 join 0.3s）。

`stream_pipeline.py`：`coalesced_acquire` 完成后 emit `turn_prewarm_*_clear` STATUS（agent 在 still_warming 时；memory 在 join 为 `brief_pending` 时无条件 dismiss waiting，避免 brief 超时/晚到导致 ProgressSteps 残留）。

测试：`tests/services/agent/execution_cache/test_turn_prewarm_coordinator.py` · `tests/api/agent/test_prewarm_api.py` · `tests/e2e/test_cdp_log_helpers.py` · Chrome E2E `tests/e2e/test_execution_cache_chrome_e2e.py`（`Turn prewarm requested` log 断言）。
