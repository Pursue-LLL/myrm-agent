# services/external_agents/

## 架构概述

外部 CLI 委托运行时生命周期（Server 业务层）。与 `api/external_agents/`（订阅鉴权 HTTP）和 `ai_agents/general_agent/external_agents.py`（装配 Mixin）分工：`RuntimePool` 按 **chat** 复用（`--resume`），`guard_turn` 串行化同 chat 的 `run_turn`；CLI 会话 id 落在 chat 行（`ChatCliSessionStore`），服务重启后同一 chat 仍续接同一个外部对话。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 Registry / Facade | — |
| `cli_session_store.py` | 核心 | `ChatCliSessionStore`：harness `CliSessionStore` 协议的 chat 行实现。`load` / `save` 经 `ChatCliSessionRepository` 读写 `chats.external_cli_sessions`（`save` 在 SQLite 写锁内读后写，并发的两个后端各自写自己的 session 名互不覆盖；不触碰 `updated_at`；不存在的 chat 与无痕 chat 不落库）；损坏的条目按“无会话”读出。异常原样上抛，由 harness 降级为新会话 | ✅ |
| `direct_delegate_stream.py` | 核心 | `stream_direct_delegate`：直连委托（`force_external_agent`）把 harness `RuntimeEvent` 翻译成前端 SSE 事件。外部工具调用是带 `tool_call_id` 的独立步骤（开始与结果更新同一步，每次更新重发步骤文本），失败带截断的错误文本；会话未被续接（`session_expired` / `session_workspace_changed`）发只有标题的已完成步骤，措辞由前端按语言给出；`MAX_TURNS` 是正常停止（无错误横幅），`CANCELLED` 与令牌取消以 `CANCELLED` 事件收尾（无 `MESSAGE_END`）。回合以 `aclosing` 关闭，客户端断开即终止外部进程；`on_token_cancelled` 让外部 Agent 静默时停止按钮同样即时生效 | ✅ |
| `runtime_pool_registry.py` | 核心 | `ChatRuntimePoolRegistry` + `ChatScopedRuntimePoolFacade`（只暴露 harness `DelegationPool` 协议的 4 个成员，不做 `__getattr__` 透传：`prompt` / `get` 一旦透传就会绕过回合锁；`run_turn` 以 `aclosing` 包住池的回合，关闭 facade 的生成器会先关掉池的回合再释放回合锁）+ `close_external_agent_pool_for_chat`：acquire/release、per-chat turn lock（run_turn 串行，cancel lock-exempt）、fingerprint 变更 defer、idle 回收（只释放常驻 ACP 进程，池与 CLI `--resume` 会话 id 保留；持 turn lock 的在途委托不回收，`guard_turn` 退出重置 idle 计时）、`ensure_tracked`（facade 每个委托 turn 先确认自己的池仍登记在册，被 close 摘出则重新登记）、删 chat 即时 close、服务关闭 `close_all`；所有 pool 关闭 / 释放带上限（带上限、不抛，`close_all` / idle 回收并发执行） | ✅ |

## 删 chat 接线

`services/chat/chat_disposal.py` 在 soft-delete / permanent-delete / empty-trash 时调用 `close_external_agent_pool_for_chat(chat_id)`，立即释放 CLI 子进程，不等 idle 600s。

## 回收与关闭

- **idle 回收（释放常驻进程）**：仅在 `acquire` 时机性触发（无后台 reaper），对空闲超过窗口的池调用 `RuntimePool.release_resident()`：只关闭常驻进程型（ACP）后端，池条目与 CLI 后端的 `--resume` 会话 id 保留。CLI 后端回合之间没有进程，整池关闭不释放任何资源（会话 id 另存在 chat 行里，丢的只是内存副本），所以同一个 chat 隔 >10 分钟再追问委托，仍续接同一个外部会话（能续接会话的 CLI：claude、codex）。不参与回收的 chat 有两类：持 turn lock 的在途委托（避免长委托期间 CLI 子进程被 SIGTERM、同 chat 串行性失效），以及正在调用 `acquire` 的 chat 自己（它在被使用，常驻进程不能在取用前被释放）。idle 计时在 `acquire` / `release` / 每个 `guard_turn` 退出时刷新，因此「超过 idle 窗口的长回合」结束后不会被立刻回收；已回收的池在再次被使用前不重复回收（`idle_released`）。回收期间条目被暂时摘出 `_entries`（持 registry `_lock`），此时到达的 turn 在 `ensure_tracked` 的慢路径等锁，回收完成后才继续，不会与 ACP 后端的关闭重叠；回收被取消时条目也会放回（`finally`），池不会失去登记。
- **关闭后重新登记**：池只在配置变更替换、`close_chat`（删 chat）、`close_all`（服务关闭）时被摘出登记并 close，而执行单元缓存（`ChatAgentExecutionCache`，1800s）里的旧单元仍可能握着该池的 facade。已关闭的 `RuntimePool` 仍可复用：下一次 `run_turn` 会懒重建后端，这些进程不在 registry 里，`close_chat` / `close_all` 看不到，成为孤儿。因此 `ChatScopedRuntimePoolFacade.run_turn` 在持有 turn lock 后调用 `ensure_tracked`：已登记则无锁直通；未登记则以 `config_fingerprint` 重新登记；registry 已有另一个池时以 registry 为准。快速路径不拿 registry `_lock`，委托 turn 不会排在别的 chat 的慢关闭后面；idle 回收不处理有在途 turn 的 chat，检查与使用之间没有竞态。
- **配置变更**：fingerprint 变化且回合在途时 defer，回合结束后的下一次 `acquire` 再替换。
- **服务关闭**：`app/server/shutdown.py::safe_close_external_agent_pools` 由 lifespan `_shutdown` 调用 `close_all`（此时 Gateway 已 drain，在途回合已结束），不依赖 CLI 子进程随父进程退出。

- **关闭有上限**：`RuntimePool.close_all` 自身没有上限，而 registry 在持有 `_lock` 时关闭 pool，任何一个关闭不返回的 backend 都会冻结所有 chat 的 `acquire` / `release` / 删 chat。因此 registry 的 3 个关闭点（配置变更替换、`close_chat`、`close_all`）与 `GeneralAgent.release_pooled_session` / `close` 的 ephemeral 路径统一走 `close_runtime_pool_bounded`，idle 回收的 `release_resident()` 走同一个 `_bounded`：`asyncio.timeout(10s)`，超时或异常只记 warning（`runtime_pool_{close,release}_timeout` / `runtime_pool_{close,release}_failed`）不抛出，取消照常传播；`close_all` 与 idle 回收对多个 pool 并发执行，最坏耗时是一个上限而不是每个 pool 一个。这个 10s 是兜底：harness 层 `AcpRuntime` 在其下对 `session/close` 另有 4s 内层上限（且只向声明了 `sessionCapabilities.close` 的 agent 发送），使传输层收尾（终止子进程）先于外层上限完成。超过外层上限后失联的子进程不再被跟踪，随服务进程退出。

## 会话持久化（服务重启后续接）

- **写入时机**：`CliRuntime` 在 CLI 自己宣布会话的那一刻就写 store（`CliSessionBook.persist`；Claude 的 `system/init`、Codex 的 `thread.started`），不等回合结束，被用户停止或超时杀掉的回合也不丢会话；未变化不重写；每个 chat 一个 `ChatCliSessionStore(chat_id)`，由 `external_agents._build_pool` 在有 chat scope 时注入 `RuntimePool(cli_session_store=…)`；无 chat scope 的临时池不落库，oneshot 私有后端不接触 store。
- **读取时机**：能续接会话的 CLI（claude、codex）在后端内存里没有该 session 的记录时读一次 chat 行（进程重启后的首个回合，或此前没产生过记录的回合）；已有记录且 id 不变的回合既不读也不写（续接沿用原 session id）。记录里带创建目录，与本回合启动目录不同就不续接，并发出“工作目录变了，已开新会话”的提示（Claude Code 按目录存放会话，v2.1.223 之前 `--resume` 只在当前项目目录里找 id，之后跨项目查找，按目录判断对新旧版本都安全）。
- **写锁等待**：CLI 宣布会话时直接 await store，harness 不设超时。`save` 遇到他人长期占着 SQLite 写锁时最多等一个 `busy_timeout`（默认 30 s，上限 60 s，网络共享存储降级时 ×3），随后异常上抛，harness 记 warning，回合不受影响（失败的记录在下一次宣布时重试写入）；对 `save` 的取消也不能提前结束这段等待，所以 harness 不加超时包装。
- **失效**：CLI 在宣布会话之前、没有任何输出就以正退出码拒绝续接（会话已过期或被清理）时，同一回合内改开新会话重试一次，并发出“上次会话已失效，已开新会话”的提示；新会话被宣布后覆盖旧记录，两次都失败则旧记录保留，记录从不被删除。取消 / 超时杀掉的进程不算失效。Claude Code 默认只保留 30 天会话，过期后走同一条失效路径。
- **配置变更替换池**不清记录（重启与不重启一致：上下文跟着 chat，直到 flush 或失效）。
- **上下文 flush**：`ChatService.focus_flush_session` 在清消息的同一事务里把 `external_cli_sessions` 置空，提交后 `chat_disposal.reset_external_agent_sessions` 关闭该 chat 的外部 Agent 池，两半缺一都会让下一回合续接已清掉的对话。
- **fork / 无痕**：fork（`ConversationForkManager`、`ContextBranchForkService`）显式构造新 chat，不继承；无痕 chat 不落库（服务重启后外部会话随之结束，与“不留痕”一致）。

## 依赖

- `myrm_agent_harness.toolkits.acp.runtime.pool` / `acp.types`（`CliSessionRecord`）— harness Integration 层，无反向依赖
- `app.database.repositories.chat_cli_session_repo` / `app.database.factory.acquire_write_lock` — `cli_session_store.py` 的持久化与写锁
- `myrm_agent_harness.api.AgentEventType` / `acp.types` / `utils.runtime.cancel_hook` — `direct_delegate_stream.py` 的事件词汇、错误码与令牌取消桥
