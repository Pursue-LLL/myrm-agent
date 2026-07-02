# Repositories 模块架构

## 架构概述

`app/database/repositories` 负责领域数据仓储层（Repository Pattern）。
该模块封装了所有底层数据库（如 SQLAlchemy）的操作细节，隔离业务服务层（Service）与持久化框架之间的耦合。业务层仅通过本模块定义的接口获取领域模型，实现真正的 DDD。Agent 领域仓储同时承载 Saved Agent 运行时字段的读写落库。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|---|
| `chat_repo.py` | 核心 | 提供 Chat 和 Message 实体 CRUD、compaction CAS 与 sibling group 持久化，并委托消息级 FTS5 检索。 | ✅ |
| `chat_message_search_repo.py` | 辅助 | 聊天消息全文检索仓储，封装消息级 FTS5 查询、active message 过滤与 Conversation Recall 排除策略。 | ✅ |
| `conversation_recall_repo.py` | 核心 | Conversation Recall 会话级索引仓储，编排索引写入、scope/fork/exclusion/health 查询。 | ✅ |
| `conversation_recall_lookup_repo.py` | 辅助 | Conversation Recall 只读可见性查找仓储，按 scope/exclusion/lineage 策略为 semantic 命中补齐源消息证据。 | ✅ |
| `conversation_recall_sql.py` | 核心 | Conversation Recall SQLite/FTS5 SQL 契约，定义 schema、bootstrap、rebuild 和参数化过滤片段。 | ✅ |
| `conversation_recall_types.py` | 辅助 | Conversation Recall DTO 与 SQLAlchemy row mapper，集中维护仓储返回值转换。 | ✅ |
| `agent_repo.py` | 核心 | Agent 领域仓储；ORM ↔ AgentProfile；`enabled_builtin_tools` 写路径经 `persist_enabled_builtin_tools` 校验 | ✅ |
| `uow.py` | 核心 | 全局工作单元模式 (UnitOfWork)，管理异步会话上下文与多仓储原子事务 | ✅ |

## 模块依赖

- 依赖 `app.database.models`：进行 ORM 对象的构建与映射。
- 依赖 `sqlalchemy.ext.asyncio`：底层数据库会话执行。
- `chat_repo.py` 依赖 `chat_message_search_repo.py`：将消息级全文检索 SQL 从 Chat/Message CRUD 仓储中分离。
