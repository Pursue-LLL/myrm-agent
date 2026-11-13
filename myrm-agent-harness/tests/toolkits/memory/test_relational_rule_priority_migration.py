"""A rule database that still has a ``priority`` column opens, loses the column and orders rules by age."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.types import ToolRulePriority
from tests.support.relational_records import make_rule

# A rule table that still has the integer priority column.
WITH_PRIORITY_DDL = """
CREATE TABLE procedural_rules (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    trigger_text TEXT NOT NULL,
    action_text TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    trigger_keywords TEXT,
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

# The table before rules had a scope, tool fields or a lock.
BEFORE_SCOPES_DDL = """
CREATE TABLE procedural_rules (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    trigger_text TEXT NOT NULL,
    action_text TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    trigger_keywords TEXT,
    source TEXT NOT NULL DEFAULT 'user_extracted',
    metadata TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

OLD_CREATED_AT = "2026-01-01T00:00:00+00:00"
NEW_CREATED_AT = "2026-03-01T00:00:00+00:00"

DDLS = pytest.mark.parametrize("ddl", [WITH_PRIORITY_DDL, BEFORE_SCOPES_DDL], ids=["with_priority", "before_scopes"])


def seed_rules(path: Path, ddl: str) -> None:
    """The older rule wears the higher priority, the way a rule the user has since replaced would."""
    connection = sqlite3.connect(path)
    try:
        connection.execute(ddl)
        connection.executemany(
            """INSERT INTO procedural_rules
               (id, user_id, content, trigger_text, action_text, priority, created_at, updated_at)
               VALUES (?, 'default', ?, 'reply style', ?, ?, ?, ?)""",
            [
                (
                    "r-old",
                    "When: reply style → Do: Reply in English.",
                    "Reply in English.",
                    100,
                    OLD_CREATED_AT,
                    OLD_CREATED_AT,
                ),
                (
                    "r-new",
                    "When: reply style → Do: Reply in German.",
                    "Reply in German.",
                    0,
                    NEW_CREATED_AT,
                    NEW_CREATED_AT,
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def rule_columns(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {str(row[1]) for row in connection.execute("PRAGMA table_info(procedural_rules)")}
    finally:
        connection.close()


@DDLS
async def test_an_old_database_loses_the_priority_column_and_keeps_every_rule(tmp_path: Path, ddl: str) -> None:
    path = tmp_path / "memory.db"
    seed_rules(path, ddl)

    store = SQLiteRelationalStore(str(path))
    try:
        rules = await store.list_rules()
        assert await store.count_rules() == 2
    finally:
        await store.close()

    assert "priority" not in rule_columns(path)
    assert {(rule.id, rule.action, rule.created_at) for rule in rules} == {
        ("r-old", "Reply in English.", datetime(2026, 1, 1, tzinfo=UTC)),
        ("r-new", "Reply in German.", datetime(2026, 3, 1, tzinfo=UTC)),
    }


@DDLS
async def test_an_old_database_lists_the_newer_rule_first_whatever_priority_the_older_one_had(
    tmp_path: Path, ddl: str
) -> None:
    path = tmp_path / "memory.db"
    seed_rules(path, ddl)

    store = SQLiteRelationalStore(str(path))
    try:
        assert [rule.id for rule in await store.list_rules()] == ["r-new", "r-old"]
    finally:
        await store.close()


async def test_the_other_rule_columns_survive_the_drop(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    seed_rules(path, WITH_PRIORITY_DDL)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE procedural_rules SET is_user_locked = 1, tool_name = 'shell', tool_rule_priority = 'critical',"
            " access_count = 4, expected_valid_days = 30 WHERE id = 'r-old'"
        )
        connection.commit()
    finally:
        connection.close()

    store = SQLiteRelationalStore(str(path))
    try:
        kept = await store.get_rule("r-old")
    finally:
        await store.close()

    assert kept is not None
    assert (
        kept.is_user_locked,
        kept.tool_name,
        kept.tool_rule_priority,
        kept.access_count,
        kept.expected_valid_days,
    ) == (
        True,
        "shell",
        ToolRulePriority.CRITICAL,
        4,
        30,
    )


async def test_a_migrated_database_takes_new_rules_and_opens_again_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    seed_rules(path, WITH_PRIORITY_DDL)

    first = SQLiteRelationalStore(str(path))
    try:
        await first.create_rule(make_rule("reply style", "Reply in French."))
    finally:
        await first.close()
    columns_after_first_open = rule_columns(path)

    second = SQLiteRelationalStore(str(path))
    try:
        listed = [rule.action for rule in await second.list_rules()]
    finally:
        await second.close()

    assert "priority" not in columns_after_first_open
    assert rule_columns(path) == columns_after_first_open
    assert listed == ["Reply in French.", "Reply in German.", "Reply in English."]


async def test_a_new_database_is_created_without_the_priority_column(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"

    store = SQLiteRelationalStore(str(path))
    try:
        await store.create_rule(make_rule())
    finally:
        await store.close()

    assert "priority" not in rule_columns(path)
