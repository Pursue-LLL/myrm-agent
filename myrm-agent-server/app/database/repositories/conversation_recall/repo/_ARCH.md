# app/database/repositories/conversation_recall/repo 子包架构

Conversation Recall 索引仓储。类不持有实例状态：12 个方法全部是 `@staticmethod`，`db: AsyncSession` 由调用方传入；按读写关注点拆成 3 个 mixin。`app.database.repositories.conversation_recall.repo` 导入路径不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 保持原 `__all__`：3 个 SQL 常量、4 个行类型、`ConversationRecallRepository` | — |
| `store.py` | 核心 | `ConversationRecallRepository(WritesMixin, SearchMixin, QueriesMixin)`，无 `__init__`、无实例状态 | — |
| `writes.py` | 核心 | `bootstrap_missing` / `rebuild_chat` / `append_message` / `append_salient_tool_segment` / `set_excluded` / `delete_chat` | ✅ |
| `search.py` | 核心 | FTS5 `search`（含 degraded/rebuild 自愈与 LIKE 回退，回退按存储原文找，needle 先去掉 FTS 短语的引号；两条 `snippet()` 用 `..sql` 的高亮标记）、`list_documents`、行去重与时间排序 helper | ✅ |
| `queries.py` | 核心 | `get_context` / `get_lineage_chat_ids` / `recent` / `health` | ✅ |

## 说明

- `set_excluded` 内部调用 `WritesMixin.rebuild_chat(...)`（staticmethod，不依赖多态）。
- `search` 的三条语句（片段 FTS、整段 FTS、LIKE 回退）与 `recent` 的条件都来自 `..sql.filter_sql`，可见性在其中；新增读取语句同样从它取条件，不手写 `is_excluded`。`search` 的每条语句各自捕获异常并降级，条件写错只会表现为“搜到的变少”，所以 `tests/services/chat/test_conversation_recall_visibility.py` 同时核对该出现与不该出现的会话，并断言没有降级告警。
- logger 名称保持 `app.database.repositories.conversation_recall.repo`，避免影响日志过滤。

## 依赖关系

- 上游：`..sql`（SQL 常量）、`..types`（行类型与值转换）、`app.database.connection.get_db`
- 下游：`conversation_recall/__init__.py`（聚合出口）、`app/services/chat/conversation_{search,recall_index}_service.py`
