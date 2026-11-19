"""SQLite relational schema bootstrap: table DDL, legacy scope-column migration and indexes.

[INPUT]
- memory.relational._converters::now_iso (POS: timestamp converter)
- memory.relational._exact_fact_store::init_exact_fact_tables (POS: exact-fact FTS5 table bootstrap)
- Third-party: aiosqlite

[OUTPUT]
- init_relational_schema: Create or migrate the profile, procedural-rule and pending tables with their
  indexes (the pending table's unique index over open proposals included) and the exact-fact tables;
  returns whether FTS5 is supported.

[POS]
Schema bootstrap for SQLiteRelationalStore. Stateless: every function operates on the given connection.
Migrations only move forward: a ``priority`` or ``trigger_keywords`` column found on procedural_rules is dropped, so
a build that still reads or writes either column can no longer read, create or update rules in a database this code
has opened. Several stores may open one database together: a column step another connection applied between this
connection's column listing and its own statement counts as done. The one-time rename-and-copy migration of a
database that predates the scope columns is not covered: it assumes no other store migrates that database at the
same moment.
"""

from collections.abc import Mapping

import aiosqlite

from myrm_agent_harness.toolkits.memory.relational._converters import now_iso
from myrm_agent_harness.toolkits.memory.relational._exact_fact_store import init_exact_fact_tables

_OPEN_PROPOSAL_INDEX = "idx_pending_open_proposal"

# Columns older releases wrote on every rule and nothing read: rules are ordered by creation time and found by their
# trigger and action text. A database that still has one gets it dropped when opened.
_DEAD_RULE_COLUMNS = ("priority", "trigger_keywords")

# Columns a table written by an older release may lack, each with the definition its ADD COLUMN gives it.
_PROFILE_COLUMNS = {"source_chat_id": "TEXT"}
_RULE_COLUMNS = {
    "tool_name": "TEXT",
    "tool_rule_priority": "TEXT NOT NULL DEFAULT 'normal'",
    "access_count": "INTEGER NOT NULL DEFAULT 0",
    "last_accessed_at": "TEXT",
    "is_user_locked": "INTEGER NOT NULL DEFAULT 0",
    "expected_valid_days": "INTEGER",
}
_PENDING_COLUMNS = {
    "resolution_action": "TEXT NOT NULL DEFAULT 'store'",
    "target_memory_id": "TEXT",
    "target_content": "TEXT",
    "built_from_chats": "INTEGER NOT NULL DEFAULT 0",
}


async def _table_exists(conn: aiosqlite.Connection, table_name: str) -> bool:
    async with conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ) as cursor:
        return await cursor.fetchone() is not None


async def _table_columns(conn: aiosqlite.Connection, table_name: str) -> set[str]:
    async with conn.execute(f"PRAGMA table_info({table_name})") as cursor:
        rows = list(await cursor.fetchall())
    return {str(row[1]) for row in rows}


async def _change_column(conn: aiosqlite.Connection, table: str, column: str, statement: str, *, present: bool) -> None:
    """Run one ADD or DROP COLUMN that this connection's column listing says is due.

    SQLite has no ``IF NOT EXISTS`` for either. Another connection opening the same database can apply the same step
    between the listing and the statement, which then fails; that is harmless when the column is in the state the
    statement was after, and any other failure still surfaces.
    """
    try:
        await conn.execute(statement)
    except aiosqlite.OperationalError:
        if (column in await _table_columns(conn, table)) != present:
            raise


async def _align_columns(
    conn: aiosqlite.Connection,
    table: str,
    *,
    add: Mapping[str, str],
    drop: tuple[str, ...] = (),
) -> None:
    """Add the columns of ``add`` the table lacks and drop the columns of ``drop`` it still has."""
    present = await _table_columns(conn, table)
    for column, definition in add.items():
        if column not in present:
            await _change_column(
                conn, table, column, f"ALTER TABLE {table} ADD COLUMN {column} {definition}", present=True
            )
    for column in drop:
        if column in present:
            await _change_column(conn, table, column, f"ALTER TABLE {table} DROP COLUMN {column}", present=False)


async def _ensure_scope_schema(conn: aiosqlite.Connection) -> None:
    if await _table_exists(conn, "profiles"):
        profile_columns = await _table_columns(conn, "profiles")
        if "primary_namespace" not in profile_columns:
            await conn.execute("ALTER TABLE profiles RENAME TO profiles_legacy")
            await conn.execute(
                """
                CREATE TABLE profiles (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    primary_namespace TEXT NOT NULL DEFAULT '',
                    namespaces TEXT NOT NULL DEFAULT '[]',
                    agent_id TEXT,
                    channel_id TEXT,
                    conversation_id TEXT,
                    task_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """
            )
            await conn.execute(
                """
                INSERT INTO profiles (
                    id, user_id, key, value, primary_namespace, namespaces, created_at, updated_at
                )
                SELECT id, user_id, key, value, '', '[]', created_at, updated_at
                FROM profiles_legacy
            """
            )
            await conn.execute("DROP TABLE profiles_legacy")

    if await _table_exists(conn, "profiles"):
        await _align_columns(conn, "profiles", add=_PROFILE_COLUMNS)

    if await _table_exists(conn, "procedural_rules"):
        rule_columns = await _table_columns(conn, "procedural_rules")
        if "primary_namespace" not in rule_columns:
            await conn.execute("ALTER TABLE procedural_rules RENAME TO procedural_rules_legacy")
            await conn.execute(
                """
                CREATE TABLE procedural_rules (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    trigger_text TEXT NOT NULL,
                    action_text TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    source TEXT NOT NULL DEFAULT 'user_extracted',
                    metadata TEXT,
                    primary_namespace TEXT NOT NULL DEFAULT '',
                    namespaces TEXT NOT NULL DEFAULT '[]',
                    agent_id TEXT,
                    channel_id TEXT,
                    conversation_id TEXT,
                    task_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """
            )
            await conn.execute(
                """
                INSERT INTO procedural_rules (
                    id, user_id, content, trigger_text, action_text, is_active,
                    source, metadata, primary_namespace, namespaces, created_at, updated_at
                )
                SELECT id, user_id, content, trigger_text, action_text, is_active,
                       source, metadata, '', '[]', created_at, updated_at
                FROM procedural_rules_legacy
            """
            )
            await conn.execute("DROP TABLE procedural_rules_legacy")

    if await _table_exists(conn, "procedural_rules"):
        await _align_columns(conn, "procedural_rules", add=_RULE_COLUMNS, drop=_DEAD_RULE_COLUMNS)

    if await _table_exists(conn, "pending_records"):
        await _align_columns(conn, "pending_records", add=_PENDING_COLUMNS)


async def _ensure_open_proposal_uniqueness(conn: aiosqlite.Connection) -> None:
    """Keep one open proposal per memory type and content, so the queue itself turns an identical second one away.

    A database that predates the index may already hold identical open proposals, which the unique index cannot be
    built over: the oldest of each group stays open and the rest are closed as rejected, rows (and chat links) kept
    for the chat purge. Closing and indexing share the transaction of the init's final commit, so no writer can add a
    duplicate in between. An existing index means there is nothing to close; creating it still tolerates one that
    another connection opening the same database built meanwhile.
    """
    async with conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?", (_OPEN_PROPOSAL_INDEX,)
    ) as cursor:
        if await cursor.fetchone() is not None:
            return
    await conn.execute(
        """
        UPDATE pending_records SET status = 'rejected', resolved_at = ?
        WHERE status = 'pending' AND rowid NOT IN (
            SELECT MIN(rowid) FROM pending_records WHERE status = 'pending' GROUP BY memory_type, content
        )
        """,
        (now_iso(),),
    )
    await conn.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {_OPEN_PROPOSAL_INDEX} "
        "ON pending_records(memory_type, content) WHERE status = 'pending'"
    )


async def init_relational_schema(conn: aiosqlite.Connection) -> bool:
    """Create or migrate every relational table and index; return whether FTS5 is supported."""
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            primary_namespace TEXT NOT NULL DEFAULT '',
            namespaces TEXT NOT NULL DEFAULT '[]',
            agent_id TEXT,
            channel_id TEXT,
            conversation_id TEXT,
            task_id TEXT,
            source_chat_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS procedural_rules (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            trigger_text TEXT NOT NULL,
            action_text TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            source TEXT NOT NULL DEFAULT 'user_extracted',
            metadata TEXT,
            primary_namespace TEXT NOT NULL DEFAULT '',
            namespaces TEXT NOT NULL DEFAULT '[]',
            agent_id TEXT,
            channel_id TEXT,
            conversation_id TEXT,
            task_id TEXT,
            tool_name TEXT,
            tool_rule_priority TEXT NOT NULL DEFAULT 'normal',
            access_count INTEGER NOT NULL DEFAULT 0,
            last_accessed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_user_locked INTEGER NOT NULL DEFAULT 0,
            expected_valid_days INTEGER
        )
    """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_records (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            content TEXT NOT NULL,
            memory_data TEXT,
            source_chat_id TEXT,
            source_message_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            resolution_action TEXT NOT NULL DEFAULT 'store',
            target_memory_id TEXT,
            target_content TEXT,
            built_from_chats INTEGER NOT NULL DEFAULT 0
        )
    """
    )
    await _ensure_scope_schema(conn)
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS idx_profiles_user ON profiles(user_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_user_key_scope ON profiles(user_id, key, primary_namespace)",
        "CREATE INDEX IF NOT EXISTS idx_profiles_user_scope ON profiles(user_id, primary_namespace)",
        "CREATE INDEX IF NOT EXISTS idx_profiles_source_chat ON profiles(source_chat_id) WHERE source_chat_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_rules_user ON procedural_rules(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_rules_user_active ON procedural_rules(user_id, is_active)",
        "CREATE INDEX IF NOT EXISTS idx_rules_user_scope ON procedural_rules(user_id, primary_namespace)",
        "CREATE INDEX IF NOT EXISTS idx_rules_tool_name ON procedural_rules(tool_name) WHERE tool_name IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_pending_user ON pending_records(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_pending_user_status ON pending_records(user_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_pending_source_chat ON pending_records(source_chat_id) WHERE source_chat_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_pending_built_from_chats ON pending_records(built_from_chats) WHERE built_from_chats = 1",
    ):
        await conn.execute(idx_sql)
    await _ensure_open_proposal_uniqueness(conn)
    fts5_supported = await init_exact_fact_tables(conn)
    await conn.commit()
    return fts5_supported
