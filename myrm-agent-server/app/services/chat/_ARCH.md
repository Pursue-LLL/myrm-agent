# chat 服务模块


---

## 架构概述

聊天业务域。提供聊天会话和消息的 CRUD 操作，包含分页、搜索、自动标题生成、沙箱清理联动和无损上下文压缩、智能会话专注与刷新 (Focus & Flush)。
消息写入统一使用增量追加模式（`append_message`），后端是消息的权威数据源。
Conversation Recall 通过会话摘要索引、消息段 SQLite/FTS5 索引与 `compacted_summary`，为 Agent 提供精确历史会话证据而不在检索路径调用 LLM。

**Mixin 组合模式**：`ChatService` 通过 Python Mixin 组合模式，各域方法定义在独立文件中（每个 < 410 行），ChatService 作为统一入口。消费者使用单一 import 路径。

**会话**：`ChatService` 所有写相关方法内部自动通过 `async with UnitOfWork() as uow:` 管理数据库会话与原子事务。API 层不再需要显式传递 `AsyncSession`，彻底隔离了业务事务与请求生命周期的直接耦合，保障强一致性。

**智能会话专注与刷新 (Focus & Flush)**：在不销毁底层沙箱环境（进程、依赖、文件系统）的前提下，通过数据库层面的**软删除** (`soft_delete_all_messages_for_chat`) 来清空当前会话的 LLM 上下文，同时清除 `compacted_summary` 与 ConversationRecall。实现零上下文重新出发，大幅节省 Token 并提升模型专注度。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `chat_service.py` | ✅ 核心 | ChatService 门面类，通过 Mixin 组合各域方法 | ✅ |
| `_base.py` | ✅ 基础 | `_ChatRepositoryPort` 协议 + `_ChatServiceBase` 基类（`_cr()` 访问器） | ✅ |
| `chat_crud.py` | ✅ 核心 | `_ChatCrudMixin`: Chat CRUD、软删除回收站 (trash/restore/permanent-delete/empty/auto-purge/batch-delete)、session flush、channel chat 管理、Pinned Threads (pin/unpin/reorder, max 9)、LangGraph checkpointer 清理 | ✅ |
| `chat_message.py` | ✅ 核心 | `_ChatMessageMixin`: 消息追加、分页查询、assistant 消息持久化、memory_recall_tool 引用证据与 retrieval trace 分步事件写入记忆操作账本 + 用量同步 | ✅ |
| `chat_history.py` | ✅ 核心 | `_ChatHistoryMixin`: Web/Channel 历史加载（含 compaction summary 注入）、FTS5 搜索 | ✅ |
| `chat_turn.py` | ✅ 核心 | `_ChatTurnMixin`: 重试/撤销/重新生成、兄弟消息切换、LLM 标题生成 | ✅ |
| `chat_compaction.py` | ✅ 核心 | `_ChatCompactionMixin`: compaction summary 更新、后台 drain 调度与 LLM 离线摘要 | ✅ |
| `chat_helpers.py` | ✅ 辅助 | 用于内部解耦的通用 DTO 和静态辅助函数（如消息过滤、Snippet清理）。 | ✅ |
| `compact_service.py` | ✅ 核心 | 无损上下文压缩（LLM 摘要 + 文件备份 + DB 持久化） | ✅ |
| `conversation_search_service.py` | ✅ 核心 | Agent 历史会话召回服务；组合会话级 FTS5 索引、统一可见性策略、预计算摘要、semantic evidence hydration 与可选语义记忆结果。 | ✅ |
| `conversation_recall_query.py` | ✅ 辅助 | Conversation Recall 查询规划；精确 FTS 优先，并在结果不足时提供无 LLM 的本地 OR/term 宽召回兜底。 | ✅ |
| `conversation_recall_index_service.py` | ✅ 核心 | Conversation Recall 索引生命周期服务；统一回填、重建、增量追加、排除/恢复、删除、健康检查和管理列表。 | ✅ |
| `conversation_fork_manager.py` | ✅ 核心 | 对话分支管理（checkpoint 克隆 + Fork 关系追踪 + 完整 Chat 元数据继承 + `compacted_before_id` ID 映射 + sandbox 隔离语义：父有活跃沙箱时子回退至原仓库根 + fork 失败时清理孤儿 checkpoint） | ✅ |
| `handoff.py` | ✅ 辅助 | 跨平台会话交接：将 Chat 的 channel_session_key 重绑定到目标渠道，支持 UNIQUE 冲突自动解决和 pairing 验证 | ✅ |
| `share_token.py` | ✅ 辅助 | 对话分享 HMAC+TTL 无状态签名 token 创建与验证 | ✅ |
| `share_renderer.py` | ✅ 辅助 | 对话分享只读 HTML 页面 SSR 渲染（Agent 身份卡片 + 消息历史 + OG metadata + XSS 防护） | ✅ |
| `sandbox_worktree.py` | ✅ 辅助 | Git worktree 生命周期管理：create/cleanup/merge/status，供 converter.py 和 sandbox API 共用 | ✅ |

---

## Mixin 组合结构

```
ChatService
  ├─ _ChatCrudMixin      (chat_crud.py)
  │    CRUD、trash (soft-delete/restore/permanent-delete/empty/batch-delete)、session、channel、ensure_default_workspace_dir、pin/unpin/reorder
  ├─ _ChatMessageMixin   (chat_message.py)
  │    append_message、ensure_chat_and_append_user_message、persist_assistant_message_safe
  ├─ _ChatHistoryMixin   (chat_history.py)
  │    load_web_chat_history、load_channel_history、search_messages
  ├─ _ChatTurnMixin      (chat_turn.py)
  │    retry_last_turn、regenerate_last_turn、undo_last_turn、switch_sibling、generate_chat_title
  └─ _ChatCompactionMixin (chat_compaction.py)
       update_compaction_summary、schedule_background_drain、flush_compaction_debt
```

所有 mixin 继承 `_ChatServiceBase`，通过 `_cr(uow)` 访问类型化的 repository。

---

## 消息持久化

### Web 端

| 方法 | 职责 |
|------|------|
| `ensure_chat_and_append_user_message()` | 确保 chat 存在并存储 user message（Agent 入口调用） |
| `load_web_chat_history()` | 从 DB 加载历史，返回框架层格式（带 `{ts}` 元数据） |
| `persist_assistant_message_safe()` | 流结束后存储 assistant message，把 `citedMemoryRefs` 与 `memoryRetrievalTraces` 旁路写入记忆操作账本，并旁路同步 `EventLogger` 的使用数据到 `Chat` 记录 |
| `search_messages()` | FTS5 全文搜索历史消息（snippet 高亮 + 分页 + trigram 中文分词 + since/until 时间范围过滤） |
| `ConversationSearchService.search()` | Agent 工具用历史会话召回；空查询返回最近会话，非空查询走消息段索引并返回精准 snippet + compacted_summary + source refs；semantic-only 命中必须回查 Server 索引补齐证据 |

### 频道端

| 方法 | 职责 |
|------|------|
| `get_or_create_channel_chat()` | 幂等获取/创建频道会话（唯一约束 + IntegrityError 重试） |
| `append_message()` | 增量追加单条消息，自动更新 Chat 元数据 |
| `load_channel_history()` | 加载历史消息为 ChannelHistoryEntry 格式 |

---

## 依赖关系

### 内部依赖
- `app/database/repositories/uow.py`：使用 UnitOfWork 管理整个跨领域实体（Chat/Message）的事务，确保失败自动回滚。
- `app/database/repositories/chat_repo.py`：Chat/Message CRUD、compaction CAS 与 sibling group 持久化仓储；消息级全文检索由其委托给 `chat_message_search_repo.py`。
- `app/database/repositories/conversation_recall_repo.py`：Conversation Recall 会话摘要与消息段索引仓储，编排索引写入、scope/fork/exclusion 查询和健康指标；SQL 契约与 DTO 转换分别由 `conversation_recall_sql.py`、`conversation_recall_types.py` 承担。
- `app/database/repositories/conversation_recall_lookup_repo.py`：Conversation Recall 只读可见性查找仓储，用于 semantic-only 命中按统一 scope/exclusion/lineage 策略补齐 snippet/source_ref。
- `app/services/chat/conversation_recall_index_service.py`：Conversation Recall 生命周期边界，供 ChatService、Compaction、Fork 与管理 API 统一调用。
- `app/database/`：Chat、Message 模型
- `app/services/infra/`：删除聊天时清理沙箱工作空间

### 被依赖方
- `app/api/chats/`：聊天 API 路由（含 `/compact`、`/share` 端点）
- `app/api/agents/general_agent/streaming.py`：Web Agent 统一入口（user message 持久化 + 历史加载，支持 fast/agent/deep_research/consensus 模式）
- `app/core/channel_bridge/agent_executor/`：频道 Agent 执行器（持久化 + 历史加载 + 流式出站）
- `app/core/channel_bridge/compact_handler.py`：IM `/compact` 命令业务实现（实现 CompactHandler 协议）
- `app/ai_agents/general_agent/conversation_search_setup.py`：将会话历史召回服务装配为 GeneralAgent `conversation_search_tool`（用户 opt-in `memoryEnableConversationSearch`）。

---

## 无损上下文压缩

### 设计原则

- **无损**：原始消息永不删除，UI 展示不受影响
- **持久化**：摘要存储在 Chat 记录的 `compacted_summary` 字段
- **增量**：多次压缩仅处理 `compacted_before_id` 之后的新消息
- **备份**：压缩前将完整上下文写入文件系统（JSONL 格式）
- **统一**：手动 `/compact` 和 Pipeline 自动摘要共用 `persist_compaction()`
- **质量**：使用框架层 `generate_structured_summary`，包含质量审计和重试机制

### 数据模型

Chat 表新增多个字段用于支撑高级功能：

| 字段 | 类型 | 说明 |
|------|------|------|
| `compacted_summary` | Text | LLM 生成的结构化摘要 |
| `compacted_before_id` | String | 最后一条被压缩消息的 ID（增量边界） |
| `compacted_at` | DateTime | 最后压缩时间 |
| `compacted_tokens_saved` | Integer | 累计节省的 token 数 |
| `ephemeral_subagents` | JSON | JIT 虚拟团队名册（用于会话恢复与子 Agent 隔离） |
| `session_loaded_skill_names` | JSON | 会话级已加载技能名 SSOT（压缩/历史裁剪后仍可用于 rehydrate） |
| `total_calls`, `total_tokens`, `total_usd` | Int/Float | O(1) 性能的 BYOK 大盘资源用量缓存，在持久化时旁路聚合更新 |
| `deleted_at` | DateTime(nullable) | 软删除时间戳。NULL=活跃，非NULL=已移入回收站。30天后由 `_db_maintenance_job` 自动永久删除 |

### 触发方式

| 入口 | 触发条件 | 说明 |
|------|----------|------|
| `POST /api/chats/{chat_id}/compact` | 用户手动调用 | Web API 端点 |
| IM `/compact` 命令 | 用户手动调用 | 通过 AgentRouter 处理 |
| Web 前端 `/compact` 斜杠命令 | 用户手动调用 | MessageInput 拦截，显示确认对话框（警告 Prompt Cache 清除） |
| Pipeline SummarizeProcessor | token 超阈值自动触发 | 通过 `on_summary_persist` 回调异步写入 DB |

### 压缩架构

```
框架层 (myrm-agent-harness)                     业务层 (app)
┌──────────────────────┐
│ generate_structured_ │                    ┌──────────────────┐
│ summary              │◀────────────────────│ compact_chat     │
│ - 质量审计           │                    │ - 事务内执行     │
│ - 重试机制           │                    │ - 使用调用方 db  │
│ - 增量合并           │                    └─────┬────────────┘
└──────────────────────┘                          │
                                                  ▼
                                         ┌─────────────────┐
                                         │ _do_persist_to_db│
                                         │ - 核心 DB 操作  │
                                         │ - 不自动 commit │
                                         └─────┬───────────┘
                                               │
                                    ┌──────────┴──────────┐
                                    │                     │
                            ┌───────▼────────┐    ┌──────▼─────────┐
                            │ compact_chat   │    │persist_compaction│
                            │ - 同步调用     │    │ - 异步回调     │
                            │ - 事务内 commit│    │ - 创建新 session│
                            └────────────────┘    └────────────────┘
                                                         ▲
                                                         │
                                              ┌──────────┴────────┐
                                              │ ContextPipeline   │
                                              │ Middleware        │
                                              └───────────────────┘
```

### 用户交互流程

**手动压缩（Web 前端）**:
1. 用户输入 `/compact`
2. 前端显示确认对话框（warning 样式）
3. 提示：手动压缩会清除 Prompt Cache，建议等待自动压缩
4. 用户确认后调用 `POST /api/chats/{chat_id}/compact`
5. 后端执行 `compact_chat()`，事务内完成
6. 前端重新加载消息列表，显示压缩结果

**自动压缩（Pipeline）**:
1. Pipeline 检测到 token 超过阈值（如 90%）
2. 调用 `generate_structured_summary()` 生成摘要
3. 通过 `persist_compaction()` 回调异步写入 DB
4. 创建独立 session，fire-and-forget 模式

**事务模型与并发安全**：
- **同步路径**（API/IM `/compact`）：使用调用方 session，单一事务，保证一致性。
- **异步路径**（Pipeline 自动触发）：创建新 session，fire-and-forget，不阻塞 Agent。
- **防并发控制**：在 `compact_chat` 层增加了内存 `asyncio.Lock`（基于 `chat_id`）。确保单一 Sandbox 内的同一会话不会出现并发的持久化归档覆盖或历史损坏。

**架构特点**：
- 手动 `/compact` 和自动压缩使用相同的算法和 prompt
- 摘要逻辑集中在框架层，强制使用 `with_structured_output` 获取结构化上下文摘要
- 业务层通过协议调用
- `_do_persist_to_db` 是 DB 操作核心，由两种路径共享

### Agent 历史加载

`load_web_chat_history` / `load_channel_history` 检测到 `compacted_summary` 时：
1. 注入摘要作为第一条 `assistant` 消息（`[Previous conversation summary]` 标记）
2. 仅加载 `compacted_before_id` 之后的消息
3. Agent 实际接收的上下文 = 摘要 + 最近消息
4. Pipeline 的 SummarizeProcessor 能检测此标记做增量合并
