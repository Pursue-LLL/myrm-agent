# api/chats/chat/

## 架构概述

单会话消息与流式子路由。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 挂载子路由；**优先**挂载 `../test_fixtures`（E2E seed 路由） | ✅ |
| `catchup.py` | 模块 | Catchup inbox: `GET /catchup` lists non-trashed, non-incognito web chats holding something the user has not seen (`Chat.last_read_at` is the user's last presence; an active agent reply newer than it, a running turn, a pending approval, or a failed/cancelled turn from `RunDigestStore.terminal_failures()` newer than it). A chat whose `last_read_at` is NULL counts as read until a turn is running, blocked or failed. `status` priority: `waiting_for_approval` > `running` (`AgentGateway.active_session_ids`) > `error`/`stopped` > `completed`. Each brief is bounded (`catchup_brief`: prompt/reply previews, files, tool counts, `needs_from_user` code) and typed by `CatchupItem`. `updated_at` carries an explicit UTC offset (the stored naive UTC would be read as local time by a browser). `POST /{chat_id}/read` stamps presence with `utcnow` and pins `updated_at` so reading never reorders the sidebar; 404 for an unknown chat. | ✅ |
| `compaction.py` | 模块 | 压缩摘要、归档只读、context pins/branches CRUD、snapshot bookmark fork | ✅ |
| `copilot.py` | 模块 | Co-Pilot API：run-digest GET、advisor ask/messages/clear（提问先过风控闸门，被拦返回 400 `risk_held`，既不入线程也不调模型） | ✅ |
| `core.py` | 模块 | 会话 CRUD 核心：列表（分页/来源/项目过滤）、元数据、`GET /recall/search`（@chat SSOT）、`GET /recall/entries`、创建/更新、Fission 拓扑、session-skills PATCH、active-moa-preset PATCH；PATCH workspace 在 project 已绑定时 409 | ✅ |
| `session_access_roots.py` | 路由 | 会话目录授权端点：`POST /{chat_id}/session-access-roots`（桌面拖拽授权；沙箱模式、可写危险根等被服务端拒绝的授权答 403）与 `PATCH`（撤销） | ✅ |
| `fork.py` | 模块 | Fork conversation from specific message index. | ✅ |
| `handoff.py` | 模块 | Web→Channel handoff API. | ✅ |
| `import_session.py` | 模块 | 跨工具（Claude Code / Codex / Hermes）历史会话纯净转录本导入与即刻续聊 API，支持文件上传与文本流解析，自动脱敏并保持静态 Prompt Cache 前缀；转录自带的 cwd 不可信，过宽或不存在时丢弃（回到会话自己的沙箱工作区），显式 `target_workspace` 过宽则 400 | ✅ |
| `rewind.py` | 模块 | Rewind conversation to before a user message; optional `scope` (conversation/files/both) reverts file snapshots and returns reverted-file details. | ✅ |
| `messages.py` | 模块 | Message search (FTS5), paginated loading, focus-flush, turn outline (`GET /{chat_id}/outline`), export (metadata + messages without the system's wake notices + agentInfo + toolCallDetails + usageSummary + toolSummary + full-structure secret redaction). | ✅ |
| `export_helpers.py` | 模块 | Chat export 数据载荷聚合（工具统计/工具详情/智能体元数据）与凭据脱敏。 | ✅ |
| `sandbox.py` | 模块 | Chat sandbox session management (enable/disable/merge/status/diff). Git worktree isolation for agent experimentation. `disable` explicitly discards the sandbox worktree (force-remove even when dirty). `merge` rolls the merge back on conflict (abort) and reports the conflicting file count. | ✅ |
| `title.py` | 模块 | if not chat_id.strip(): | ✅ |
| `trash.py` | 模块 | Chat trash (recycle bin) API endpoints. | ✅ |
| `share/` | 子包 | 会话分享（时间受限只读公开链接，支持可选密码）：`manage.py` 创建/撤销/状态、`public.py` 公开页与密码门；详见 [share/_ARCH.md](share/_ARCH.md) | ✅ |
| `turn.py` | 模块 | Turn lifecycle: regenerate（`instruction` 引导文本先过风控闸门，被拦返回 400 `risk_held`，上一轮回答保持活动；它随后作为 `regenerate_instruction` 进入聊天流，那里再单独过一次闸）, sibling switch/list, truncate-after (edit-resend). 无 HTTP retry/undo：WebUI 的回退走 `rewind.py`（按消息 id 定位 + 确认），IM `/retry`·`/undo` 与压缩耗尽回滚直接调用 `ChatService.retry_last_turn`/`undo_last_turn`。 | ✅ |
| `trajectory.py` | 模块 | `GET /{chat_id}/trajectory` — 抽取多轮执行轨迹（包含 tool_calls、参数、耗时、Token 与错误分类），供前端跨会话时序瀑布流与双轨 Diff 对比消费。 | ✅ |
| `replay.py` | 模块 | `POST /{chat_id}/replay` — 会话重放与确定性验证接口，计算工具调用序列对齐率、Jaccard指数与确定性得分（0.0 ~ 1.0）。 | ✅ |
| `export_pack.py` | 模块 | `HEAD & GET /{chat_id}/export-pack` — 会话事件日志、子Agent日志与工件文件的自包含流式 ZIP 导出管道，原生支持 `redact_secrets` 动态脱敏、O(1) 内存分块与 SHA256 清单。 | ✅ |
| `memory_extract.py` | 模块 | `POST /{chat_id}/memory/retry-extract` — 对最近一轮 user/assistant 重新调度 memory extract；incognito / 无效 turn → 400；chat 不存在 → 404；返回 `scheduled` / `already_in_flight` | ✅ |
| `thought_control.py` | 路由 | 思考链提前收敛与主动停止干预控制端点（`POST /{chat_id}/stop-thinking`），遏制长思考死循环与无限推理，强制提前作答 | ✅ |
| `zero_replay.py` | 路由 | 基于单次原子状态快照与零事件重放 Live SSE 订阅的前后端无缝重连协议端点（`GET /{chat_id}/atomic-snapshot`, `GET /{chat_id}/live-stream`, `POST /{chat_id}/snapshot-state`, `POST /{chat_id}/live-event`），彻底解决重连回放闪烁与时序错乱 | ✅ |
| `command_matrix.py` | 路由 | 系统指令矩阵目录（`GET /commands/matrix`）与基于会话状态机的情境感知智能推荐芯片端点（`POST /{chat_id}/commands/suggest`） | ✅ |
| `embed_bridge.py` | 路由 | 网站与第三方系统可嵌入小部件及宿主上下文双向通信桥端点（`POST /chats/embed/validate-origin`, `POST/GET /{chat_id}/embed/policy`, `POST/GET /{chat_id}/embed/inject-context`, `POST /{chat_id}/embed/generate-snippet`） | ✅ |
| `swarm_hud.py` | 路由 | 多智能体蜂群并发协同、记忆规则唤醒 HUD 与方案风险清单核验端点（`POST/GET /{chat_id}/swarm/config`, `POST/GET /{chat_id}/swarm/tasks`, `POST/GET/PATCH /{chat_id}/swarm/recalled-rules`, `POST/GET/PATCH /{chat_id}/swarm/risks`） | ✅ |

