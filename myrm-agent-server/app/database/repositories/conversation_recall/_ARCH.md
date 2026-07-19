# conversation_recall 子包架构

## 架构概述

Conversation Recall 索引仓储子包。集中维护 SQLite/FTS5 DDL、DTO 转换、索引读写与可见性查找，供 `services/chat` 与 `database/migrations` 消费。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `repo.py` | 核心 | 索引读写仓储：bootstrap、scope/fork/exclusion/health 查询 | ✅ |
| `lookup_repo.py` | 辅助 | 只读可见性查找：为 semantic 命中补齐 snippet/source_ref | ✅ |
| `sql.py` | 核心 | SQLite/FTS5 SQL 契约：schema、bootstrap、rebuild、filter_sql | ✅ |
| `types.py` | 辅助 | DTO 与 SQLAlchemy row mapper | ✅ |
| `__init__.py` | 门面 | 对外 re-export 公共 API | ✅ |

## 模块依赖

- 依赖 `app.database.models.chat`：Chat/Message/ConversationFork ORM
- 被 `app.services.chat.conversation_recall_index_service` 与 `conversation_search_service` 消费
- 被 `app.database.migrations.ensure_raw_sql_schema` 引用 schema SQL
