# api/chats/chat/

## 架构概述

本目录模块说明。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | from fastapi import APIRouter | ✅ |
| `catchup.py` | 模块 | Get catchup briefs for all chats with unread activity. | ✅ |
| `compaction.py` | 模块 | Compact chat context by generating a persistent summary. | ✅ |
| `core.py` | 模块 | 获取聊天历史列表（支持分页、来源和项目过滤） | ✅ |
| `fork.py` | 模块 | Fork conversation from specific message index. | ✅ |
| `handoff.py` | 模块 | Web→Channel handoff API. Enables the frontend to migrate an active conversation to an IM channel (Telegram, WeChat, Feishu, etc.). """ | ✅ |
| `messages.py` | 模块 | Full-text search across all chat messages using FTS5. | ✅ |
| `title.py` | 模块 | if not chat_id.strip(): | ✅ |
| `trash.py` | 模块 | Chat trash (recycle bin) API endpoints. | ✅ |
| `turn.py` | 模块 | Delete the last assistant turn so the original query can be re-sent. | ✅ |
