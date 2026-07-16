# api/chats/chat/

## 架构概述

单会话消息与流式子路由。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | from fastapi import APIRouter | ✅ |
| `catchup.py` | 模块 | Get catchup briefs for all chats with unread activity. | ✅ |
| `compaction.py` | 模块 | Compact chat context by generating a persistent summary. | ✅ |
| `core.py` | 模块 | 会话 CRUD 核心：列表（分页/来源/项目过滤）、元数据、创建/更新、Fission 拓扑、session-skills PATCH | ✅ |
| `fork.py` | 模块 | Fork conversation from specific message index. | ✅ |
| `handoff.py` | 模块 | Web→Channel handoff API. | ✅ |
| `messages.py` | 模块 | Message search (FTS5), paginated loading, focus-flush, export (metadata + messages + agentInfo + toolCallDetails + usageSummary + toolSummary). | ✅ |
| `sandbox.py` | 模块 | Chat sandbox session management (enable/disable/merge/status/diff). Git worktree isolation for agent experimentation. | ✅ |
| `title.py` | 模块 | if not chat_id.strip(): | ✅ |
| `trash.py` | 模块 | Chat trash (recycle bin) API endpoints. | ✅ |
| `turn.py` | 模块 | Turn lifecycle: retry, regenerate, sibling switch, truncate-after (edit-resend), undo. | ✅ |
