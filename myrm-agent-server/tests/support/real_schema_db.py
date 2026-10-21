"""A file-backed SQLite database with the server's complete schema, for tests that must not trust a hand-built one.

[INPUT]
- app.database.models::Base (POS: ORM metadata of every table)
- app.database.migrations::ensure_raw_sql_schema (POS: FTS5 tables, triggers and the raw-SQL tables)

[OUTPUT]
- create_real_schema_engine: build the schema in a fresh database file
- seed_row: insert one row, filling every required column the caller did not name

[POS]
Tests that assert what a deletion removes need the real table and column names; a miniature schema silently
agrees with a misspelled table. Foreign keys are enforced as in production.
"""

from __future__ import annotations

from itertools import count
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

from app.database.migrations import ensure_raw_sql_schema
from app.database.models import Base

_NUMERIC_TYPES = ("INT", "REAL", "NUM", "BOOL", "FLOAT")
_placeholder_serial = count(1)


async def create_real_schema_engine(db_path: Path) -> AsyncEngine:
    """Create the complete server schema in ``db_path`` and return an engine bound to it."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enforce_foreign_keys(dbapi_connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_raw_sql_schema(engine)
    return engine


async def seed_row(conn: AsyncConnection, table: str, **values: object) -> None:
    """Insert one row into ``table``; required columns that ``values`` omits get a unique placeholder."""
    columns = (await conn.execute(text(f"PRAGMA table_info({table})"))).fetchall()
    row: dict[str, object] = dict(values)
    for _, name, declared_type, not_null, default, _pk in columns:
        if name in row or not not_null or default is not None:
            continue
        serial = next(_placeholder_serial)
        row[name] = serial if any(kind in (declared_type or "").upper() for kind in _NUMERIC_TYPES) else f"x{serial}"
    column_list = ", ".join(row)
    placeholders = ", ".join(f":{name}" for name in row)
    await conn.execute(text(f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"), row)
