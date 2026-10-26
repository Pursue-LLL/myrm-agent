# services/external_agents/

## 架构概述

外部 CLI 委托运行时生命周期（Server 业务层）。与 `api/external_agents/`（订阅鉴权 HTTP）和 `ai_agents/general_agent/external_agents.py`（装配 Mixin）分工：`RuntimePool` 按 **chat** 复用（`--resume`），`guard_turn` 串行化同 chat 的 `run_turn`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 Registry / Facade | — |
| `runtime_pool_registry.py` | 核心 | `ChatRuntimePoolRegistry` + `ChatScopedRuntimePoolFacade`（只暴露 harness `DelegationPool` 协议的 4 个成员，不做 `__getattr__` 透传：`prompt` / `get` 一旦透传就会绕过回合锁）+ `close_external_agent_pool_for_chat`：acquire/release、per-chat turn lock（run_turn 串行，cancel lock-exempt）、fingerprint 变更 defer、idle 驱逐（持 turn lock 的在途委托不驱逐，`guard_turn` 退出重置 idle 计时）、`ensure_tracked`（facade 每个委托 turn 先确认自己的池仍登记在册，被驱逐则重新登记）、删 chat 即时 close、服务关闭 `close_all`；所有 pool 关闭走 `close_runtime_pool_bounded`（带上限、不抛，`close_all` / idle 驱逐并发关闭） | ✅ |

## 删 chat 接线

`services/chat/chat_disposal.py` 在 soft-delete / permanent-delete / empty-trash 时调用 `close_external_agent_pool_for_chat(chat_id)`，立即释放 CLI 子进程，不等 idle 600s。

## 回收与关闭

- **idle 驱逐**：仅在 `acquire` 时机性触发（无后台 reaper）；持 turn lock 的 chat 视为在途委托，不驱逐也不丢弃其 lock，避免长委托期间 CLI 子进程被 SIGTERM、同 chat 串行性失效、`--resume` 会话 id 丢失。idle 计时在 `acquire` / `release` / 每个 `guard_turn` 退出时刷新，因此「超过 idle 窗口的长回合」结束后不会被立刻驱逐。
- **驱逐后重新登记**：执行单元缓存（`ChatAgentExecutionCache`，1800s）比 idle 驱逐（600s）活得久，缓存命中的旧单元不会再 `acquire`。其 facade 握着的池被驱逐后是“已关闭但可复用”的：下一次 `run_turn` 会懒重建后端，这些进程不在 registry 里，`close_chat` / `close_all` 看不到，成为孤儿。因此 `ChatScopedRuntimePoolFacade.run_turn` 在持有 turn lock 后调用 `ensure_tracked`：已登记则无锁直通；未登记则以 `config_fingerprint` 重新登记；registry 已有另一个池时以 registry 为准。快速路径不拿 registry `_lock`，委托 turn 不会排在别的 chat 的慢关闭后面；持 turn lock 期间该池不参与 idle 驱逐，检查与使用之间没有竞态。
- **配置变更**：fingerprint 变化且回合在途时 defer，回合结束后的下一次 `acquire` 再替换。
- **服务关闭**：`app/server/shutdown.py::safe_close_external_agent_pools` 由 lifespan `_shutdown` 调用 `close_all`（此时 Gateway 已 drain，在途回合已结束），不依赖 CLI 子进程随父进程退出。

- **关闭有上限**：`RuntimePool.close_all` 自身没有上限，而 registry 在持有 `_lock` 时关闭 pool，任何一个关闭不返回的 backend 都会冻结所有 chat 的 `acquire` / `release` / 删 chat。因此 registry 的 4 个关闭点（配置变更替换、`close_chat`、`close_all`、idle 驱逐）与 `GeneralAgent.release_pooled_session` / `close` 的 ephemeral 路径统一走 `close_runtime_pool_bounded`：`asyncio.timeout(10s)`，超时或异常只记 warning（`runtime_pool_close_timeout` / `runtime_pool_close_failed`）不抛出，取消照常传播；`close_all` 与 idle 驱逐对多个 pool 并发关闭，最坏耗时是一个上限而不是每个 pool 一个。这个 10s 是兜底：harness 层 `AcpRuntime` 在其下对 `session/close` 另有 4s 内层上限（且只向声明了 `sessionCapabilities.close` 的 agent 发送），使传输层收尾（终止子进程）先于外层上限完成。超过外层上限后失联的子进程不再被跟踪，随服务进程退出。

## 依赖

- `myrm_agent_harness.toolkits.acp.runtime.pool` — harness Integration 层，无反向依赖
