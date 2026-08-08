# database 模块架构


---

## 架构概述

数据库模块。提供 SQLAlchemy 异步 ORM、数据库连接管理、模型定义和数据库迁移。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `models/` | ✅ 核心 | SQLAlchemy ORM 模型包，按业务域拆分为子模块（chat/agent/memory/config/agent_event/cron/channel/media/security/skill/notification/message_filter），`chat.py` 的 `Chat` 含会话级 JSON：`ephemeral_subagents`、`session_loaded_skill_names`（已加载技能名 SSOT，供 harness rehydrate）；`memory.py` 包含 Shared Context 上下文/绑定/写入提案、记忆操作账本、导入 dry-run 审查会话模型、导入批次账本和导入条目账本，`agent.py` 包含 Agent 基础配置（含 `mcp_tool_selections` per-server 工具白名单 JSON 列）与 WebUI rollback 快照 (`AgentProfileSnapshot`)，`agent_history.py` 为乐观锁审计与 Prompt 浏览，`__init__.py` 统一 re-export |
| `repositories/` | ✅ 核心 | 领域仓储层（Repository Pattern），封装 Agent/Chat 等聚合的读写与 ORM 映射 | ✅ |
| `operations/` | ✅ 辅助 | 数据库运维工具子包：备份工厂、容灾恢复、SQLite 忙/锁检测、FastAPI 异常处理器、遗留数据清理 |
| `connection.py` | ✅ 核心 | 数据库连接管理（异步会话工厂）；`get_db` 提供的会话生命周期与单次 HTTP 请求一致；`init_database` 在 `run_migrations` 前通过 `get_sqlite_backup_manager()` 执行 fail-closed pre-migration safety snapshot：备份失败时阻断迁移（raise），由上层 lifespan 3 级恢复体系兜底 |
| `factory.py` | ✅ 核心 | SQLite 数据库引擎和会话工厂创建。`PRAGMA foreign_keys=ON` + WAL + 异步连接池（`SQLITE_POOL_SIZE` 默认 5 / `max_overflow` 默认 10，dev stack 注入 8/8）+ `PRAGMA busy_timeout`（`get_sqlite_busy_timeout_ms()` / `SQLITE_BUSY_TIMEOUT_MS`，dev stack 注入 15s）+ mmap。`begin` 事件执行 `BEGIN IMMEDIATE` 抢占写锁；锁竞争等待由 SQLite busy handler 在 aiosqlite worker 线程完成，**不阻塞 asyncio 事件循环**（早期实现用 `time.sleep` 重试，会在并行 E2E 写竞争时冻结事件循环导致 API 全线变慢）。Sandbox 模式下 `settings.database.sqlite_path` 指向 CP 挂载卷 |
| `migrations.py` | ✅ 核心 | 数据库迁移引擎集成。使用 Harness 层的 `StatefulMigrationEngine` 执行版本化 SQL 迁移。支持精准计时 (`duration_ms`)、基线平滑升级 (Baseline)、慢查询捕获和结构化失败报告。状态持久化在 `_schema_migrations` 和 `_schema_indexes` 表中 |
| `allowlist_store.py` | ✅ 核心 | DBAllowlistStore — allowlist database persistence (AllowlistStore Protocol). All methods accept `user_id` param per protocol. Provides load/save/remove operations with UUID primary keys |
| `dto.py` | ✅ 核心 | 数据传输对象（DTO）定义 |

---

## Sandbox 模式

- 所有部署模式统一使用 SQLite（存储在沙箱持久化卷 `/persistent/data/myrm.db`）。

---

## SQLite 观测

- 环境变量：`SQLITE_POOL_SIZE`、`SQLITE_BUSY_TIMEOUT_MS`（解析与上下限见 `factory.py`）。
- HTTP：`app/main.py` 调用 `register_database_operational_handlers(app)`。SQLite 忙/锁 → **503**，`code=51005`；`Retry-After` 由 `sqlite_busy_retry_after_seconds()` 换算，与 `PRAGMA busy_timeout` 同源，秒数上限 60。
- 契约测试：`tests/database/test_db_operational_handlers.py`（ASGI 传输层集成验证）。
- 脚本均在仓库 `myrm-agent-server/` 下执行：`uv run python scripts/sqlite_pool_smoke.py`、`uv run python scripts/sqlite_write_contention_smoke.py`。输出为**本机单次运行**测量值，非 SLA，也不覆盖全部 API 路径。

## 🔍 SQLite 高级特性与调优
- **WAL 并发调优**: `factory.py` 中通过 SQLAlchemy `begin` 事件拦截，禁用默认事务，使用 `BEGIN IMMEDIATE` 配合随机抖动重试（Jitter Retry 20-150ms），彻底解决多 Agent 并发写入导致的护航效应（Convoy Effect）卡死问题。
- **FTS5 虚拟表**: `migrations.py` 中创建了基于 `External Content` 模式的 `messages_fts` 虚拟表（使用 SQLite 隐式整数 `rowid` 作为 `content_rowid`），并建立 `INSERT/UPDATE/DELETE` 触发器，实现底层零冗余自动同步。Conversation Recall 的 raw SQL 契约位于 `repositories/conversation_recall/sql.py`，提供 `conversation_recall_documents` 会话摘要索引与 `conversation_recall_segments` 消息段 FTS5 索引，支持 `trigram` 中文分词、scope/fork/exclusion 查询、精准 message_id 证据和不含文本的健康指标。
- **Baseline Migration**: `StatefulMigrationEngine` 通过 `baseline_check_sql` 检测已存在数据库，自动标记所有迁移为已执行（baselined），支持旧数据库平滑升级。
