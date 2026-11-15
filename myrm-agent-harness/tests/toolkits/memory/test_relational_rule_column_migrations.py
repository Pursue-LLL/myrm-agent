"""A rule database written by an older release opens, loses its dead rule columns and keeps every rule.

Rules are ordered by age, not by a ``priority``, and no rule field is a keyword trigger: ``priority`` and
``trigger_keywords`` were written by older releases and never read, so opening a database drops both columns.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.types import RuleSource, ToolRulePriority
from tests.support.relational_records import make_rule

# The rule table of the release that dropped ``priority`` but still kept a keyword column.
WITH_KEYWORDS_DDL = """
CREATE TABLE procedural_rules (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    trigger_text TEXT NOT NULL,
    action_text TEXT NOT NULL,
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

# A rule table that still has the integer priority column next to the keyword column.
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
DEAD_COLUMNS = {"priority", "trigger_keywords"}

DDLS = pytest.mark.parametrize(
    "ddl",
    [WITH_KEYWORDS_DDL, WITH_PRIORITY_DDL, BEFORE_SCOPES_DDL],
    ids=["with_keywords", "with_priority", "before_scopes"],
)
FULL_DDLS = pytest.mark.parametrize(
    "ddl", [WITH_KEYWORDS_DDL, WITH_PRIORITY_DDL], ids=["with_keywords", "with_priority"]
)


def seed_rules(path: Path, ddl: str) -> None:
    """Two rules that carry keywords; where the table has a priority, the older rule wears the higher one.

    That is the way a rule the user has since replaced would look.
    """
    priority_column, priority_mark = (", priority", ", ?") if "priority INTEGER" in ddl else ("", "")
    connection = sqlite3.connect(path)
    try:
        connection.execute(ddl)
        connection.executemany(
            f"""INSERT INTO procedural_rules
               (id, user_id, content, trigger_text, action_text, trigger_keywords, source, metadata,
                created_at, updated_at{priority_column})
               VALUES (?, 'default', ?, 'reply style', ?, ?, 'user_explicit', ?, ?, ?{priority_mark})""",
            [
                (
                    "r-old",
                    "When: reply style → Do: Reply in English.",
                    "Reply in English.",
                    '["deploy", "release"]',
                    '{"note": "kept"}',
                    OLD_CREATED_AT,
                    OLD_CREATED_AT,
                    *([100] if priority_mark else []),
                ),
                (
                    "r-new",
                    "When: reply style → Do: Reply in German.",
                    "Reply in German.",
                    "[]",
                    None,
                    NEW_CREATED_AT,
                    NEW_CREATED_AT,
                    *([0] if priority_mark else []),
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


def schema_state(path: Path) -> tuple[int, list[tuple[object, ...]]]:
    """The schema change counter and every schema entry: equal before and after means no DDL ran."""
    connection = sqlite3.connect(path)
    try:
        counter = connection.execute("PRAGMA schema_version").fetchone()[0]
        entries = connection.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()
        return counter, entries
    finally:
        connection.close()


def integrity(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        connection.close()


@DDLS
async def test_an_old_database_loses_the_dead_columns_and_keeps_every_rule(tmp_path: Path, ddl: str) -> None:
    path = tmp_path / "memory.db"
    seed_rules(path, ddl)

    store = SQLiteRelationalStore(str(path))
    try:
        rules = await store.list_rules()
        assert await store.count_rules() == 2
    finally:
        await store.close()

    assert not DEAD_COLUMNS & rule_columns(path)
    assert integrity(path) == "ok"
    assert sorted(
        ((rule.id, rule.action, rule.created_at, rule.source, rule.metadata, rule.is_active) for rule in rules),
        key=lambda row: row[0],
    ) == [
        ("r-new", "Reply in German.", datetime(2026, 3, 1, tzinfo=UTC), RuleSource.USER_EXPLICIT, {}, True),
        (
            "r-old",
            "Reply in English.",
            datetime(2026, 1, 1, tzinfo=UTC),
            RuleSource.USER_EXPLICIT,
            {"note": "kept"},
            True,
        ),
    ]


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


@FULL_DDLS
async def test_the_other_rule_columns_survive_the_drop(tmp_path: Path, ddl: str) -> None:
    path = tmp_path / "memory.db"
    seed_rules(path, ddl)
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


@FULL_DDLS
async def test_a_migrated_database_takes_new_rules_and_opens_again_unchanged(tmp_path: Path, ddl: str) -> None:
    path = tmp_path / "memory.db"
    seed_rules(path, ddl)

    first = SQLiteRelationalStore(str(path))
    try:
        await first.create_rule(make_rule("reply style", "Reply in French."))
    finally:
        await first.close()
    state_after_first_open = schema_state(path)

    second = SQLiteRelationalStore(str(path))
    try:
        listed = [rule.action for rule in await second.list_rules()]
    finally:
        await second.close()

    assert not DEAD_COLUMNS & rule_columns(path)
    assert schema_state(path) == state_after_first_open
    assert listed == ["Reply in French.", "Reply in German.", "Reply in English."]


async def test_a_new_database_is_created_without_the_dead_columns(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"

    store = SQLiteRelationalStore(str(path))
    try:
        await store.create_rule(make_rule())
    finally:
        await store.close()

    assert not DEAD_COLUMNS & rule_columns(path)
