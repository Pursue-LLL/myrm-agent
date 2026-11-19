"""数据库迁移：Harness 有状态迁移引擎的接入、迁移与索引语句清单、遗留数据修复的冻结 SQL 常量。

[INPUT]
myrm_agent_harness.utils.db.migration_engine::StatefulMigrationEngine/MigrationStatement (POS: 有状态迁移引擎)
sqlalchemy.ext.asyncio::AsyncEngine (POS: 异步 SQLAlchemy 引擎)
app.database.migrations._migration_statements_1..3::MIGRATION_STATEMENTS_1..3 (POS: 迁移语句清单的三段)
app.database.migrations._index_statements_1..2::INDEX_STATEMENTS_1..2 (POS: 索引语句清单的两段)
app.database.migrations._sql_constants::九条冻结 SQL 常量 (POS: 遗留数据修复语句，原样再导出)
app.database.repositories.conversation_recall.sql::CONVERSATION_RECALL_SCHEMA_SQL/CONVERSATION_RECALL_BOOTSTRAP_SQL/CONVERSATION_RECALL_SEGMENT_BOOTSTRAP_SQL (POS: 会话召回的表与 FTS5 DDL，ensure_raw_sql_schema 内按需导入)

[OUTPUT]
MIGRATION_STATEMENTS / INDEX_STATEMENTS（各段按顺序拼成的完整清单，版本号即下标） / run_migrations(engine) / create_indexes(engine) / has_pending_migrations(engine)（是否还有待执行的迁移，决定是否需要迁移前快照） / ensure_raw_sql_schema(engine)（保底创建不在 ORM 里的 FTS5 虚拟表、触发器与日志表） / 九条冻结 SQL 常量（定义见 _sql_constants.py，原样再导出）

[POS]
Server 层 SQLite 有状态迁移入口，追加式维护 schema 演进。两条清单拆成按文件序号首尾相接的段，每段不超过 400 行；
运行函数留在本文件，因为测试按名字替换 MIGRATION_STATEMENTS / INDEX_STATEMENTS，运行函数必须在同一模块里读取它们。
"""

import logging

from myrm_agent_harness.utils.db.migration_engine import (
    MigrationStatement,
    StatefulMigrationEngine,
)
from sqlalchemy.ext.asyncio import AsyncEngine

from ._index_statements_1 import INDEX_STATEMENTS_1
from ._index_statements_2 import INDEX_STATEMENTS_2
from ._migration_statements_1 import MIGRATION_STATEMENTS_1
from ._migration_statements_2 import MIGRATION_STATEMENTS_2
from ._migration_statements_3 import MIGRATION_STATEMENTS_3
from ._sql_constants import (
    BACKFILL_LEGACY_WAKEUP_NOTICE_SQL,
    CLEAR_BUILTIN_SEARCH_MEMORY_POLICY_SQL,
    CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL,
    NORMALIZE_RETIRED_PROMPT_MODES_SQL,
    PAUSE_STALLED_ONCE_CRON_JOBS_SQL,
    REARM_STALLED_CRON_JOBS_SQL,
    REJECT_LEGACY_TOOL_STUCK_APPROVALS_SQL,
    STRIP_RETIRED_RESPONSE_LOCALE_POLICY_FROM_SNAPSHOTS_SQL,
    STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL,
)

__all__ = [
    "BACKFILL_LEGACY_WAKEUP_NOTICE_SQL",
    "CLEAR_BUILTIN_SEARCH_MEMORY_POLICY_SQL",
    "CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL",
    "INDEX_STATEMENTS",
    "MIGRATION_STATEMENTS",
    "NORMALIZE_RETIRED_PROMPT_MODES_SQL",
    "PAUSE_STALLED_ONCE_CRON_JOBS_SQL",
    "REARM_STALLED_CRON_JOBS_SQL",
    "REJECT_LEGACY_TOOL_STUCK_APPROVALS_SQL",
    "STRIP_RETIRED_RESPONSE_LOCALE_POLICY_FROM_SNAPSHOTS_SQL",
    "STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL",
    "create_indexes",
    "ensure_raw_sql_schema",
    "has_pending_migrations",
    "run_migrations",
]

logger = logging.getLogger(__name__)

# 数据库迁移语句，按顺序执行；版本号就是列表下标，只在末尾追加，已发布的语句不删、不改、不挪位
# （tests/database/test_migration_list_append_only.py 固定了本列表与 INDEX_STATEMENTS 中已发布语句的摘要）。
# 新语句追加在最后一段的末尾；最后一段接近 400 行时新开下一个文件，并在这里按顺序加入。
MIGRATION_STATEMENTS: list[str] = [*MIGRATION_STATEMENTS_1, *MIGRATION_STATEMENTS_2, *MIGRATION_STATEMENTS_3]

# 创建索引的SQL语句列表，追加规则同上。
INDEX_STATEMENTS: list[str] = [*INDEX_STATEMENTS_1, *INDEX_STATEMENTS_2]


def _migration_engine(engine: AsyncEngine) -> StatefulMigrationEngine:
    return StatefulMigrationEngine(
        engine=engine,
        table_name="_schema_migrations",
        baseline_check_sql="SELECT 1 FROM sqlite_master WHERE type='table' AND name='chats'",
        slow_threshold_ms=100.0,
    )


def _migration_statements() -> list[MigrationStatement]:
    return [MigrationStatement(version=i, sql=stmt) for i, stmt in enumerate(MIGRATION_STATEMENTS)]


async def has_pending_migrations(engine: AsyncEngine) -> bool:
    """Whether ``run_migrations`` would still do work; a start with nothing pending needs no pre-migration snapshot."""
    return await _migration_engine(engine).has_pending(_migration_statements())


async def run_migrations(engine: AsyncEngine) -> None:
    """运行数据库迁移 (Zero-Ops Stateful Migration Engine)

    采用状态化迁移引擎，自动维护 _schema_migrations 表，
    提供精准计时、慢查询捕获和基线平滑升级能力。
    """
    report = await _migration_engine(engine).run_migrations(_migration_statements())

    if report.failed_count > 0:
        logger.error(
            "❌ FATAL: Database migration failed at version %d.\nSQL: %s\nError: %s",
            report.failed_version,
            report.failed_sql,
            report.error_message,
        )
        raise RuntimeError(f"Database migration failed at version {report.failed_version}: {report.error_message}")

    if report.applied_count > 0:
        summary = f"Database migrations done: {report.applied_count} applied, {report.skipped_count} skipped in {report.total_duration_ms:.1f}ms."
        if report.slowest_migrations:
            slow_str = ", ".join([f"V{m[0]}: {m[2]:.1f}ms" for m in report.slowest_migrations[:3]])
            summary += f" (Slowest: {slow_str})"
        logger.info(summary)
    elif report.baselined:
        logger.info("Database migrations baselined for existing database.")
    else:
        logger.debug(
            "Database migrations verified: all %d skipped in %.1fms.",
            report.skipped_count,
            report.total_duration_ms,
        )


async def create_indexes(engine: AsyncEngine) -> None:
    """创建数据库索引 (Zero-Ops Stateful Migration Engine)

    采用状态化迁移引擎，自动维护 _schema_indexes 表。
    """
    indexes = [MigrationStatement(version=i, sql=stmt) for i, stmt in enumerate(INDEX_STATEMENTS)]

    index_engine = StatefulMigrationEngine(
        engine=engine,
        table_name="_schema_indexes",
        baseline_check_sql="SELECT 1 FROM sqlite_master WHERE type='table' AND name='chats'",
        slow_threshold_ms=100.0,
        sync_user_version=False,
    )

    report = await index_engine.run_migrations(indexes)

    if report.failed_count > 0:
        logger.error(
            "❌ FATAL: Database index creation failed at version %d.\nSQL: %s\nError: %s",
            report.failed_version,
            report.failed_sql,
            report.error_message,
        )
        raise RuntimeError(f"Database index creation failed at version {report.failed_version}: {report.error_message}")

    if report.applied_count > 0:
        summary = f"Database indexes created: {report.applied_count} applied, {report.skipped_count} skipped in {report.total_duration_ms:.1f}ms."
        if report.slowest_migrations:
            slow_str = ", ".join([f"V{m[0]}: {m[2]:.1f}ms" for m in report.slowest_migrations[:3]])
            summary += f" (Slowest: {slow_str})"
        logger.info(summary)
    elif report.baselined:
        logger.info("Database indexes baselined for existing database.")
    else:
        logger.debug(
            "Database indexes verified: all %d skipped in %.1fms.",
            report.skipped_count,
            report.total_duration_ms,
        )

    # 在 baselined 的情况下（例如全新初始化或首个迁移），非 ORM 定义的结构（如 FTS5 和部分日志表）
    # 可能由于迁移被跳过而未创建，因此需要在此处做保底检查并创建。
    await ensure_raw_sql_schema(engine)


async def ensure_raw_sql_schema(engine: AsyncEngine) -> None:
    """Ensure raw SQL tables and triggers (not in ORM) exist."""
    from sqlalchemy import text

    from app.database.repositories.conversation_recall.sql import (
        CONVERSATION_RECALL_BOOTSTRAP_SQL,
        CONVERSATION_RECALL_SCHEMA_SQL,
        CONVERSATION_RECALL_SEGMENT_BOOTSTRAP_SQL,
    )

    raw_sql = [
        # System Health History
        """CREATE TABLE IF NOT EXISTS system_health_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            overall_status VARCHAR(10) NOT NULL,
            overall_score INTEGER NOT NULL,
            component_reports JSON NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_system_health_timestamp ON system_health_history(timestamp DESC)",
        # FTS5 Virtual Table
        """CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            content,
            content=messages,
            content_rowid=rowid,
            tokenize='trigram'
        )""",
        """CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
        END""",
        """CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.rowid, old.content);
        END""",
        """CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.rowid, old.content);
            INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
        END""",
        *CONVERSATION_RECALL_SCHEMA_SQL,
        CONVERSATION_RECALL_BOOTSTRAP_SQL,
        CONVERSATION_RECALL_SEGMENT_BOOTSTRAP_SQL,
    ]
    try:
        async with engine.begin() as conn:
            for sql in raw_sql:
                await conn.execute(text(sql))
        logger.debug("Raw SQL schema verification completed.")
    except Exception as e:
        logger.error("Failed to ensure raw SQL schema: %s", e)
