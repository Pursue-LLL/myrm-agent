# conversation_recall 子包架构

## 架构概述

Conversation Recall 索引仓储子包。集中维护 SQLite/FTS5 DDL、DTO 转换、索引读写与可见性查找，供 `services/chat` 与 `database/migrations` 消费。召回读取的可见性条件由 `sql.py` 的 `visible_document_sql` 一处定义：检索、最近列表与展开窗口经 `filter_sql` 带上它，窗口原文的查询模板直接用 `visible_document_sql`，调用方不手写排除条件；管理页列表（`list_documents`）不读这个条件，按 id 取回（`fetch_prior_chat_document`）把排除标志交给调用方判定。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `repo/` | 核心 | Conversation Recall 索引读写仓储，按关注点拆 3 个 mixin（writes / search / queries）+ `store`（组合，全静态方法、无实例状态）：bootstrap、scope/fork/exclusion/health 查询、FTS5 搜索与损坏自愈、消息/片段写入与重建。见 [repo/_ARCH.md](repo/_ARCH.md) | ✅ |
| `lookup_repo.py` | 辅助 | 只读可见性查找：`fetch_message_window` expand、`fetch_prior_chat_document` mention、`fetch_window_context`（片段窗口所在的存储原文，查找与截取都在 SQLite 里做，长对话不整段出库；`WindowContext` 带窗口在其中的起点；范围与 agent 过滤由放行命中的搜索负责，可见性（被排除、网页无痕）是搜索之后会话还能翻转的状态，所以三处来源统一再查一次，模型读不到的会话返回 None） | ✅ |
| `sql.py` | 核心 | SQLite/FTS5 SQL 契约：schema、bootstrap、rebuild、`visible_document_sql`（模型能读的会话：没被用户排除，且不是网页无痕会话；转写导入借用无痕标志只为不进侧边栏，仍可读。无痕标志建索引之后还能改，所以查询时从 `chats` 读，不抄进索引）、`filter_sql`（可见性条件排在最前，没有参数能关掉它，调用方接在 `WHERE` 或 `AND` 之后）；snippet 高亮标记 `HIGHLIGHT_OPEN` / `HIGHLIGHT_CLOSE` 是 Unicode 非字符，普通对话文本里没有，不会与用户自己写的 `<mark>` 混淆 | ✅ |
| `types.py` | 辅助 | DTO 与 SQLAlchemy row mapper；`recall_row` 把 FTS 高亮标记换成两种读法：`snippet`（标记变成界面用的 `<mark>`）与 `window`（去掉标记，模型读的纯文本）；存储文本本身含标记字符时，窗口在原文里找不到，模型得不到片段 | ✅ |
| `__init__.py` | 门面 | 对外 re-export 公共 API | ✅ |

## 模块依赖

- 依赖 `app.database.models.chat`：Chat/Message/ConversationFork ORM
- 被 `app.services.chat.conversation_recall_index_service` 与 `conversation_search_service` 消费
- 被 `app.database.migrations.ensure_raw_sql_schema` 引用 schema SQL
