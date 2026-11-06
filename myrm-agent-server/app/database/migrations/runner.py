"""数据库迁移执行器。

[POS]
把 schema / index 语句交给状态化迁移引擎，并提供 raw SQL schema 保障。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.utils.db.migration_engine import (
    MigrationStatement,
    StatefulMigrationEngine,
)
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def run_migrations(engine: AsyncEngine) -> None:
    """运行数据库迁移 (Zero-Ops Stateful Migration Engine)

    采用状态化迁移引擎，自动维护 _schema_migrations 表，
    提供精准计时、慢查询捕获和基线平滑升级能力。
    """
    from app.database import migrations as migrations_module

    migrations = [
        MigrationStatement(version=i, sql=stmt)
        for i, stmt in enumerate(migrations_module.MIGRATION_STATEMENTS)
    ]

    migration_engine = StatefulMigrationEngine(
        engine=engine,
        table_name="_schema_migrations",
        baseline_check_sql="SELECT 1 FROM sqlite_master WHERE type='table' AND name='chats'",
        slow_threshold_ms=100.0,
    )

    report = await migration_engine.run_migrations(migrations)

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
    from app.database import migrations as migrations_module

    indexes = [
        MigrationStatement(version=i, sql=stmt)
        for i, stmt in enumerate(migrations_module.INDEX_STATEMENTS)
    ]

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
