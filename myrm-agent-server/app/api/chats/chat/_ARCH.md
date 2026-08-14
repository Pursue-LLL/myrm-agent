# api/chats/chat/

## 架构概述

单会话消息与流式子路由。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 挂载子路由；**优先**挂载 `../test_fixtures`（E2E seed 路由） | ✅ |
| `catchup.py` | 模块 | Get catchup briefs for all chats with unread activity. | ✅ |
| `compaction.py` | 模块 | 压缩摘要、归档只读、context pins/branches CRUD、snapshot bookmark fork | ✅ |
| `copilot.py` | 模块 | Co-Pilot API：run-digest GET、advisor ask/messages/clear | ✅ |
| `core.py` | 模块 | 会话 CRUD 核心：列表（分页/来源/项目过滤）、元数据、`GET /recall/search`（@chat SSOT）、`GET /recall/entries`、创建/更新、Fission 拓扑、session-skills PATCH、active-moa-preset PATCH、session-access-roots revoke PATCH；PATCH workspace 在 project 已绑定时 409 | ✅ |
| `fork.py` | 模块 | Fork conversation from specific message index. | ✅ |
| `rewind.py` | 模块 | Rewind conversation to before a user message; optional `scope` (conversation/files/both) reverts file snapshots and returns reverted-file details. | ✅ |
| `handoff.py` | 模块 | Web→Channel handoff API. | ✅ |
| `messages.py` | 模块 | Message search (FTS5), paginated loading, focus-flush, export (metadata + messages + agentInfo + toolCallDetails + usageSummary + toolSummary). | ✅ |
| `sandbox.py` | 模块 | Chat sandbox session management (enable/disable/merge/status/diff). Git worktree isolation for agent experimentation. | ✅ |
| `title.py` | 模块 | if not chat_id.strip(): | ✅ |
| `trash.py` | 模块 | Chat trash (recycle bin) API endpoints. | ✅ |
| `share.py` | 模块 | Conversation share API：创建/撤销时间受限只读公开链接（支持可选密码）；公开页（`/public/chat-share/{token}`，GET+POST）密码门表单 **POST body 提交（CWE-598：密码不进 URL）**，GET 兼容旧 `?p=` query；cloud 用 public URL，local/desktop 前端回退客户端 HTML export | ✅ |
| `turn.py` | 模块 | Turn lifecycle: retry, regenerate, sibling switch, truncate-after (edit-resend), undo, rewind. | ✅ |
| `memory_extract.py` | 模块 | `POST /{chat_id}/memory/retry-extract` — 对最近一轮 user/assistant 重新调度 memory extract；incognito / 无效 turn → 400；chat 不存在 → 404；返回 `scheduled` / `already_in_flight` | ✅ |
