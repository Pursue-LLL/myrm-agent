# api/chats/

## 架构概述

聊天会话 CRUD、流式与分支 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 挂载 `chat/` 子路由 | ✅ |
| `test_fixtures.py` | 测试 | local-only Chrome E2E seed（citation + Kanban closure + IN_REVIEW + RevertFiles 四 variant + chat share） | ✅ |
| `test_fixtures_chat_share.py` | 测试 | Chat Share 生命周期 Chrome E2E seed（chat + user/assistant 消息，公开分享页可渲染） | ✅ |
| `test_fixtures_context_retention.py` | 测试 | context retention Chrome E2E seed（compacted summary + pins + snapshot bookmarks） | ✅ |
| `test_fixtures_clarify_refresh.py` | 测试 | clarify refresh HITL hydrate seed（pending/answered/regenerate_sibling/structured_form） | ✅ |
| `test_fixtures_file_edit_batch.py` | 测试 | file_edit batch live/read_ui + workspace-only seed | ✅ |
| `test_fixtures_evicted.py` | 测试 | UECD evicted LiveTerminal seed | ✅ |
| `chat/` | 子模块 | 单会话消息、搜索、分支、turn 等子路由 | [chat/_ARCH.md](chat/_ARCH.md) |

## 依赖

- `app.services.chat.chat_service` — 会话/消息持久化
- `app.services.agent.agent_service` — E2E seed 选取 agent scope
