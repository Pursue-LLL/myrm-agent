"""Pins the archive policy to the real ORM schema so a rename or a new secret column cannot go unnoticed."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import Table

import app.database.models  # noqa: F401  (registers every table on Base.metadata)
from app.database.models import Base
from app.services.instance_archive import stage_db, table_policy
from app.services.instance_archive.table_policy import (
    CARRIED_SENSITIVE_CONFIG_KEYS,
    EPHEMERAL_TABLES,
    HOST_BOUND_TABLES,
    IDENTITY_TABLES,
    SECRET_TABLES,
)

_TABLES: dict[str, Table] = dict(Base.metadata.tables)
_SECRET_LOOKING = re.compile(r"secret|token|password|passwd|api_key|credential|private_key|cookie|webhook", re.I)

# Secret-looking columns outside the host-bound / secret / ephemeral tables, reviewed one by one:
# usage counters carry no secret; share-link columns are scrubbed by scrub_sensitive_surface.
_REVIEWED_COLUMNS = {
    ("chats", "compacted_tokens_saved"),
    ("chats", "total_tokens"),
    ("chats", "share_token_fingerprint"),
    ("chats", "share_token_expires_at"),
    ("chats", "share_token_protected"),
    ("cron_runs", "usage_input_tokens"),
    ("cron_runs", "usage_output_tokens"),
    ("cron_runs", "usage_total_tokens"),
    ("kanban_boards", "specify_max_tokens"),
    ("kanban_task_runs", "token_usage"),
}


@pytest.mark.parametrize(
    "tables", [HOST_BOUND_TABLES, SECRET_TABLES, EPHEMERAL_TABLES, IDENTITY_TABLES], ids=lambda t: f"{len(t)} tables"
)
def test_every_classified_table_exists(tables: frozenset[str]) -> None:
    assert tables <= set(_TABLES), sorted(tables - set(_TABLES))


def test_table_classes_do_not_overlap() -> None:
    groups = [HOST_BOUND_TABLES, SECRET_TABLES, EPHEMERAL_TABLES, IDENTITY_TABLES]
    for i, first in enumerate(groups):
        for second in groups[i + 1 :]:
            assert not first & second


def test_secret_looking_columns_are_classified_or_reviewed() -> None:
    classified = HOST_BOUND_TABLES | SECRET_TABLES | EPHEMERAL_TABLES
    unreviewed = {
        (table.name, column.name)
        for table in _TABLES.values()
        if table.name not in classified
        for column in table.columns
        if _SECRET_LOOKING.search(column.name)
    } - _REVIEWED_COLUMNS
    assert not unreviewed, f"Classify these in table_policy or review them here: {sorted(unreviewed)}"


def test_columns_the_scrub_and_graft_rely_on_exist() -> None:
    def columns(table: str) -> set[str]:
        return {c.name for c in _TABLES[table].columns}

    assert {"share_token_fingerprint", "share_token_expires_at", "share_token_protected"} <= columns("chats")
    assert table_policy._INCOGNITO_COLUMNS <= columns("chats")
    assert stage_db._LISTED_CHAT_COLUMNS <= columns("chats")
    assert {"config_key", "config_value", "is_encrypted"} <= columns("user_configs")
    assert {"status", "command"} <= columns("cron_jobs")
    assert all("user_id" in columns(table) for table in IDENTITY_TABLES)
    for table, column in stage_db._PATH_COLUMNS:
        assert column in columns(table), (table, column)
    for table in stage_db._SUMMARY_TABLES:
        assert table in _TABLES


def test_carried_sensitive_keys_are_really_sensitive() -> None:
    from app.services.config.encryption import is_sensitive_config

    assert all(is_sensitive_config(key) for key in CARRIED_SENSITIVE_CONFIG_KEYS)
