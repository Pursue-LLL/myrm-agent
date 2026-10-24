"""Every ORM column must be reachable from the schema a database can actually get.

A model field that exists only in `create_all()` works on a fresh database and breaks every
older one with `no such column` — exactly how `channel_pairings.role` turned the scheduler
health endpoint into a 51002 and the AppLayout banner into "scheduler stopped".

The rule this test enforces: for a table that has a `CREATE TABLE` in the migration
statements (i.e. it predates some deployments), each ORM column must appear either in that
`CREATE TABLE` or in an `ALTER TABLE ... ADD COLUMN` somewhere in
`MIGRATION_STATEMENTS` or `INDEX_STATEMENTS` (both lists are executed).

Tables without a `CREATE TABLE` statement are skipped: `create_all()` creates them whole,
so there is no older schema to migrate.

[POS]
Schema-integrity gate for model/migration drift.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import JSON, Boolean, Column, Integer, MetaData, String, Table

from app.database import migrations
from app.database.models import Base

_CREATE_TABLE = re.compile(
    r"CREATE TABLE (?:IF NOT EXISTS )?([a-zA-Z_]\w*)\s*\((.*?)\n\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_ADD_COLUMN = re.compile(
    r"ALTER TABLE ([a-zA-Z_]\w*)\s+ADD COLUMN ([a-zA-Z_]\w*)",
    re.IGNORECASE,
)


def _statement_text() -> str:
    statements = [*migrations.MIGRATION_STATEMENTS, *migrations.INDEX_STATEMENTS]
    return "\n".join(str(statement) for statement in statements)


def _schema_sources(statements: str) -> tuple[dict[str, str], dict[str, set[str]]]:
    created = {
        match.group(1).lower(): match.group(2).lower()
        for match in _CREATE_TABLE.finditer(statements)
    }
    added: dict[str, set[str]] = {}
    for match in _ADD_COLUMN.finditer(statements):
        added.setdefault(match.group(1).lower(), set()).add(match.group(2).lower())
    return created, added


def _declared_columns(create_body: str) -> set[str]:
    """Column names that are actually *defined* in a CREATE TABLE body.

    A plain substring search would accept a column that merely appears inside another
    column's DEFAULT or a table constraint, which would hide a real gap. A definition
    starts a line with the name followed by a type.
    """
    declared: set[str] = set()
    for line in create_body.splitlines():
        match = re.match(r"\s*([a-zA-Z_]\w*)\s+[a-zA-Z]", line)
        if match:
            declared.add(match.group(1).lower())
    return declared


def _missing_columns(statements: str, metadata: MetaData) -> dict[str, list[str]]:
    created, added = _schema_sources(statements)
    missing: dict[str, list[str]] = {}
    for table_name, table in metadata.tables.items():
        key = table_name.lower()
        if key not in created:
            continue
        available = _declared_columns(created[key]) | added.get(key, set())
        gaps = sorted(column.name for column in table.columns if column.name.lower() not in available)
        if gaps:
            missing[table_name] = gaps
    return missing


def test_every_model_column_is_reachable_on_an_existing_database() -> None:
    missing = _missing_columns(_statement_text(), Base.metadata)

    assert not missing, (
        "Model columns with no CREATE TABLE / ALTER TABLE source. Fresh databases get them "
        "from create_all(), older ones die on `no such column`:\n"
        + "\n".join(f"  - {table}: {', '.join(columns)}" for table, columns in missing.items())
        + "\nAppend `ALTER TABLE <table> ADD COLUMN <column> ...` to MIGRATION_STATEMENTS "
        "(append-only) instead of relying on create_all()."
    )


def test_detector_flags_a_column_without_any_ddl() -> None:
    """Self-check: the gate must fail on the exact shape of the channel_pairings bug."""
    metadata = MetaData()
    Table(
        "demo_pairings",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("role", String(20), nullable=False),
    )
    statements = "CREATE TABLE IF NOT EXISTS demo_pairings (\n    id INTEGER\n)"

    assert _missing_columns(statements, metadata) == {"demo_pairings": ["role"]}


def test_detector_accepts_a_column_added_by_alter() -> None:
    """Self-check: one ALTER is enough, and the match is case-insensitive."""
    metadata = MetaData()
    Table(
        "demo_pairings",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("role", String(20), nullable=False),
        Column("enabled", Boolean, nullable=False),
        Column("payload", JSON, nullable=True),
    )
    statements = (
        "CREATE TABLE IF NOT EXISTS demo_pairings (\n    id INTEGER\n)\n"
        "alter table DEMO_PAIRINGS add column role VARCHAR(20)\n"
        "ALTER TABLE demo_pairings ADD COLUMN enabled BOOLEAN\n"
        "ALTER TABLE demo_pairings ADD COLUMN payload JSON\n"
    )

    assert _missing_columns(statements, metadata) == {}


@pytest.mark.parametrize("table_name", ["channel_pairings", "agents", "kanban_boards"])
def test_previously_broken_tables_are_still_covered(table_name: str) -> None:
    """The three tables involved in the scheduler-banner incident stay explicitly covered."""
    missing = _missing_columns(_statement_text(), Base.metadata)

    assert table_name not in missing
