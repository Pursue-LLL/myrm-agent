# services/external_agents/

## 架构概述

外部 CLI 委托运行时生命周期（Server 业务层）。与 `api/external_agents/`（订阅鉴权 HTTP）和 `ai_agents/general_agent/external_agents.py`（装配 Mixin）分工：`RuntimePool` 按 **chat** 复用（`--resume`），`guard_turn` 串行化同 chat 的 `run_turn`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 Registry / Facade | — |
| `runtime_pool_registry.py` | 核心 | `ChatRuntimePoolRegistry` + `ChatScopedRuntimePoolFacade` + `close_external_agent_pool_for_chat`：acquire/release、per-chat turn lock（run_turn 串行，cancel lock-exempt）、fingerprint 变更 defer、idle 驱逐（持 turn lock 的在途委托不驱逐，`guard_turn` 退出重置 idle 计时）、删 chat 即时 close、服务关闭 `close_all`；所有 pool 关闭走 `close_runtime_pool_bounded`（带上限、不抛，`close_all` / idle 驱逐并发关闭） | ✅ |

## 删 chat 接线

`services/chat/chat_disposal.py` 在 soft-delete / permanent-delete / empty-trash 时调用 `close_external_agent_pool_for_chat(chat_id)`，立即释放 CLI 子进程，不等 idle 600s。

## 回收与关闭

- **idle 驱逐**：仅在 `acquire` 时机性触发（无后台 reaper）；持 turn lock 的 chat 视为在途委托，不驱逐也不丢弃其 lock，避免长委托期间 CLI 子进程被 SIGTERM、同 chat 串行性失效、`--resume` 会话 id 丢失。idle 计时在 `acquire` / `release` / 每个 `guard_turn` 退出时刷新，因此「超过 idle 窗口的长回合」结束后不会被立刻驱逐。
- **配置变更**：fingerprint 变化且回合在途时 defer，回合结束后的下一次 `acquire` 再替换。
- **服务关闭**：`app/server/shutdown.py::safe_close_external_agent_pools` 由 lifespan `_shutdown` 调用 `close_all`（此时 Gateway 已 drain，在途回合已结束），不依赖 CLI 子进程随父进程退出。

- **关闭有上限**：`RuntimePool.close_all` 本身无上限（ACP agent 进程存活但不回应 `session/close` 时永不返回），而 registry 在持有 `_lock` 时关闭 pool，一次卡死会冻结所有 chat 的 `acquire` / `release` / 删 chat。因此 registry 的 4 个关闭点（配置变更替换、`close_chat`、`close_all`、idle 驱逐）与 `GeneralAgent.release_pooled_session` / `close` 的 ephemeral 路径统一走 `close_runtime_pool_bounded`：`asyncio.timeout(10s)`，超时或异常只记 warning（`runtime_pool_close_timeout` / `runtime_pool_close_failed`）不抛出，取消照常传播；`close_all` 与 idle 驱逐对多个 pool 并发关闭，最坏耗时是一个上限而不是每个 pool 一个。超时后失联的子进程不再被跟踪，随服务进程退出。harness 层 `AcpRuntime` 另有 4s 的 `session/close` 内层上限（且只向声明了 `sessionCapabilities.close` 的 agent 发送），保证正常的传输层收尾（终止子进程）先于这个 10s 外层上限完成，外层上限只做兜底。

## 依赖

- `myrm_agent_harness.toolkits.acp.runtime.pool` — harness Integration 层，无反向依赖
