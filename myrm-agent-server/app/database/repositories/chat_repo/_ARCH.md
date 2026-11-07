# app/database/repositories/chat_repo 子包架构

Chat / Message 仓储。类不持有实例状态：43 个方法全部是 `@staticmethod`，`db: AsyncSession` 由调用方传入；按实体拆成 4 个 mixin。`app.database.repositories.chat_repo` 导入路径不变，测试里 25 处 `patch("...chat_repo.ChatRepository.<method>")` 仍然命中同一个类对象。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 导出 `ChatRepository` 与 `SiblingDetail`（原模块对外面） | — |
| `common.py` | 辅助 | logger、`_DTO_COMPUTED_FIELDS` / `_INCOGNITO_BLANKED_FIELDS`、`_answers_of_turn` 过滤条件 | — |
| `chats.py` | 核心 | 聊天列表/详情、创建/更新、置顶、回收站生命周期、compaction CAS | ✅ |
| `messages.py` | 核心 | 消息 CRUD、分页、FTS 搜索、extra-data 读写、FTS 命中 chat 解析 | ✅ |
| `siblings.py` | 核心 | assistant sibling 选择/计数/详情（`SiblingDetail`、`_SiblingGroupInfo`） | ✅ |
| `routing.py` | 核心 | turn routing-tier 读取（`routingTier` 历史与动量窗口） | ✅ |
| `store.py` | 核心 | `ChatRepository(ChatsMixin, MessagesMixin, SiblingsMixin, RoutingMixin)`，无 `__init__`、无实例状态 | — |

## 说明

- 跨模块调用使用 mixin 限定：`MessagesMixin._fts_matching_chat_ids` / `MessagesMixin.get_last_user_message` / `SiblingsMixin._batch_sibling_counts`（均为同一 staticmethod，原实现不依赖多态）。
- `_answers_of_turn` 同时被 siblings 与 routing 使用，收敛到 `common.py`，避免两个业务模块互相 import。
- 消息级 FTS5 SQL 仍委托 `app/database/repositories/chat_message_search_repo.py`（既有边界）。

## 依赖关系

- 上游：`app.database.dto`、`app.database.models`、`app.database.repositories.chat_message_search_repo`
- 下游：`app/api/chats/chat/**`、`app/api/agent/**`、`app/services/chat/**`
