"""数据库迁移门面。

[OUTPUT]
MIGRATION_STATEMENTS / INDEX_STATEMENTS / run_migrations / create_indexes / ensure_raw_sql_schema /
BACKFILL_LEGACY_WAKEUP_NOTICE_SQL / CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL / REJECT_LEGACY_TOOL_STUCK_APPROVALS_SQL

[POS]
`app.database.migrations` 的唯一入口；账本按版本区间放在 schema/ 与 indexes/ 子包。
"""

from app.database.migrations.indexes import STATEMENTS as INDEX_STATEMENTS
from app.database.migrations.legacy_sql import (
    BACKFILL_LEGACY_WAKEUP_NOTICE_SQL,
    CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL,
    REJECT_LEGACY_TOOL_STUCK_APPROVALS_SQL,
)
from app.database.migrations.runner import create_indexes, ensure_raw_sql_schema, run_migrations
from app.database.migrations.schema import STATEMENTS as MIGRATION_STATEMENTS

__all__ = [
    "BACKFILL_LEGACY_WAKEUP_NOTICE_SQL",
    "CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL",
    "INDEX_STATEMENTS",
    "MIGRATION_STATEMENTS",
    "REJECT_LEGACY_TOOL_STUCK_APPROVALS_SQL",
    "create_indexes",
    "ensure_raw_sql_schema",
    "run_migrations",
]
