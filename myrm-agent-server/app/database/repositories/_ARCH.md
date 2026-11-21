# Repositories 模块架构

## 架构概述

`app/database/repositories` 负责领域数据仓储层（Repository Pattern）。
该模块封装了所有底层数据库（如 SQLAlchemy）的操作细节，隔离业务服务层（Service）与持久化框架之间的耦合。业务层仅通过本模块定义的接口获取领域模型，实现真正的 DDD。Agent 领域仓储同时承载 Saved Agent 运行时字段的读写落库。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|---|
| `chat_repo/` | 核心 | Chat / Message 仓储，按实体拆 4 个 mixin（chats / messages / siblings / routing）+ `common`（常量与回合过滤条件）+ `store`（组合，全静态方法、无实例状态）：Chat/Message CRUD、compaction CAS、sibling group、路由档位历史、回收站生命周期；消息级 FTS5 委托 `chat_message_search_repo`。见 [chat_repo/_ARCH.md](chat_repo/_ARCH.md) | ✅ |
| `chat_message_search_repo.py` | 辅助 | 聊天消息全文检索仓储，封装消息级 FTS5 查询、active message 过滤与 Conversation Recall 排除策略。提供 `get_matching_chat_ids()` 供侧边栏 keyword 搜索接入 FTS。FTS 无命中（查询不足 3 个字符，或被 FTS 表达式压平）时按键入文本 `raw_query` 做子串回退，回退不读 FTS 表达式；`get_matching_chat_ids()` 的 FTS 查询失败时记 WARNING 后同样走回退，`search_messages_fts()` 失败则抛给服务层。回退命中的预览由 `substring_snippet()` 生成：窗口取 40 个 trigram 词元所跨的 42 个字符（宽度同 FTS5 `snippet()`），以第一处匹配为中心（匹配靠近文本首尾时贴边），窗口内每处匹配加 `<mark>`，文本在窗口外继续的一端加 `...`；FTS5 另有自己的取窗规则（起于前 40 个字符内的匹配从文本开头取、起点吸附到句号加空格之后、多处匹配另行打分，单处匹配时两条通道的起点最多相差约 20 个字符），并把相邻或重叠的匹配合成一个 `<mark>`；`LIKE` 只折叠 ASCII 大小写、`re` 折叠 Unicode 大小写，回退行总能定位到匹配，文本里没有 needle 时显示开头且不标；仓储不转义，界面显示前由服务层的 `_sanitize_snippet` 转义。 | ✅ |
| `like_pattern.py` | 辅助 | 聊天检索子串通道的查找文本与 LIKE 模式：`typed_needle(raw_query, *, keep_quotes=False)` 取键入文本的查找文本（去首尾空白；默认丢弃短语引号 `"`，它在键入查询里只是短语界定符，侧边栏搜标题与首条消息时传 `keep_quotes=True`，引号在那里是普通字符；没有可搜内容时返回 `None`），`like_contains_pattern()` 按它生成 `%…%`（`%`、`_` 与转义符按字面转义；没有可搜内容时同样返回 `None`，因为 `%%` 会命中所有行），`LIKE_ESCAPE_CLAUSE` 是每条使用该模式的 `LIKE` 必带的 `ESCAPE` 子句；侧边栏、消息搜索对话框、`@chat:` 选择器与模型会话检索四个入口共用 | ✅ |
| `channel_key_match.py` | 辅助 | 渠道会话键的边界匹配：`channel_key_extends`（会话键本身与以 `:` 续接的键：话题、智能体、纪元）与 `channel_key_epochs`（会话键本身与其重置纪元 `:e=`，不含同一对端的话题与智能体）。按键的段边界做索引范围比较，不用 `LIKE` 前缀（前缀会把 `u1` 与 `u10` 混为一谈，且 `_` 是通配符）；空闲重置、渠道预算的成本汇总与审计、预算面板的群组探测、最新渠道聊天的查找共用 | ✅ |
| `chat_history_sync_repo.py` | 辅助 | 聊天历史同步仓储：`load_branch` 读取压缩锚点之后的活跃消息有序 id 与压缩状态（不受历史条数上限约束，同刻时间戳以 id 定序）、`has_active_answer`（按 `request_message_id` 判断本回合回答已落库且活跃）、`store_token` 写 `Chat.history_sync_token`（不触碰 `updated_at`） | ✅ |
| `chat_cli_session_repo.py` | 辅助 | 外部 CLI Agent 会话记录仓储：`get` / `put` 读写 `Chat.external_cli_sessions`（harness session id → CLI 原生会话 id + 创建目录；记录只被覆盖，不删除）。`put` 跳过不存在与无痕 chat，不触碰 `updated_at`（续接记录是记账，不是会话活动）；读后写由调用方持 SQLite 写锁；非 dict 的存量值按“无会话”处理 | ✅ |
| `fission_repo.py` | 核心 | FissionTaskRecord 数据访问层（高并发子代理任务拓扑持久化） | ✅ |
| `channel_message_repo.py` | 核心 | 多渠道入站明细仓储（Channel Message Data Plane），提供原子写入、上下文按需拉取、知识学习候选集查询、30 天冷热生命周期滚动修剪以及当日配额调用计数（`get_daily_trigger_count`） | ✅ |
| `conversation_recall/` | 核心 | Conversation Recall 索引子包（`repo`/`lookup_repo`/`sql`/`types`）；对外经 `__init__.py` re-export | ✅ |
| `agent_repo/` | 核心 | Agent 领域仓储，按读写与映射拆 4 个 mixin（mapping / reads / create / update）+ `store`（组合，全静态方法、无实例状态）：ORM ↔ AgentProfile、分页列表/计数、创建/删除、更新（乐观并发）；mutation 后 `flush` + `refresh` 再映射。见 [agent_repo/_ARCH.md](agent_repo/_ARCH.md) | ✅ |
| `uow.py` | 核心 | 全局工作单元模式 (UnitOfWork)，管理异步会话上下文与多仓储原子事务；`write=True` 供读后写的工作单元在入口即取 SQLite 写锁（见 `factory.acquire_write_lock`） | ✅ |

## 模块依赖

- 依赖 `app.database.models`：进行 ORM 对象的构建与映射。
- 依赖 `sqlalchemy.ext.asyncio`：底层数据库会话执行。
- `chat_repo/messages.py` 依赖 `chat_message_search_repo.py`：将消息级全文检索 SQL 从 Chat/Message CRUD 仓储中分离。
