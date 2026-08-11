"""Board settings persistence completeness: every ``BoardSettings`` field must
round-trip through the ORM mapping functions so saved boards reload with all
nine settings intact.

The dataclass-coverage test fails fast if the harness ever adds a new
``BoardSettings`` field that the server layer forgets to persist.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime

import pytest
from myrm_agent_harness.toolkits.kanban.types import BoardSettings, KanbanBoard

from app.core.kanban.adapters.sqlalchemy_mapping import (
    apply_board_to_model,
    board_to_domain,
    board_to_model,
)
from app.database.models.kanban import KanbanBoardModel

_SETTINGS = BoardSettings(
    max_concurrent_tasks=7,
    heartbeat_interval_seconds=45,
    zombie_timeout_seconds=300,
    max_retries_per_task=5,
    auto_block_after_consecutive_failures=9,
    specify_max_tokens=8000,
    auto_specify_on_create=True,
    default_workdir="/work/board-a",
    block_recurrence_limit=4,
)

_NOW = datetime.now(UTC)


def _make_model() -> KanbanBoardModel:
    model = KanbanBoardModel(
        id="b-roundtrip",
        name="Roundtrip",
        max_concurrent_tasks=_SETTINGS.max_concurrent_tasks,
        heartbeat_interval_seconds=_SETTINGS.heartbeat_interval_seconds,
        zombie_timeout_seconds=_SETTINGS.zombie_timeout_seconds,
        max_retries_per_task=_SETTINGS.max_retries_per_task,
        auto_block_after_consecutive_failures=_SETTINGS.auto_block_after_consecutive_failures,
        specify_max_tokens=_SETTINGS.specify_max_tokens,
        auto_specify_on_create=_SETTINGS.auto_specify_on_create,
        default_workdir=_SETTINGS.default_workdir,
        block_recurrence_limit=_SETTINGS.block_recurrence_limit,
        created_at=_NOW,
        updated_at=_NOW,
    )
    return model


def _make_domain() -> KanbanBoard:
    return KanbanBoard(
        board_id="b-roundtrip",
        name="Roundtrip",
        settings=_SETTINGS,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _assert_settings_roundtrip(actual: BoardSettings) -> None:
    for field in fields(BoardSettings):
        assert getattr(actual, field.name) == getattr(
            _SETTINGS, field.name
        ), f"BoardSettings.{field.name} was lost in mapping"


class TestBoardSettingsRoundtrip:
    def test_board_to_domain_carries_all_settings_fields(self) -> None:
        domain = board_to_domain(_make_model())
        _assert_settings_roundtrip(domain.settings)

    def test_board_to_model_carries_all_settings_fields(self) -> None:
        model = board_to_model(_make_domain())
        _assert_settings_roundtrip(
            board_to_domain(model).settings
        )

    def test_apply_board_to_model_carries_all_settings_fields(self) -> None:
        model = _make_model()
        domain = KanbanBoard(
            board_id="b-roundtrip",
            name="Roundtrip",
            settings=BoardSettings(block_recurrence_limit=9, max_concurrent_tasks=2),
            created_at=_NOW,
            updated_at=_NOW,
        )
        apply_board_to_model(domain, model)
        assert model.block_recurrence_limit == 9
        assert model.max_concurrent_tasks == 2

    def test_model_columns_cover_all_board_settings_fields(self) -> None:
        """Fail fast if the harness adds a BoardSettings field the server forgets."""
        setting_names = {f.name for f in fields(BoardSettings)}
        column_names = {c.name for c in KanbanBoardModel.__table__.columns}
        missing = sorted(setting_names - column_names)
        assert not missing, (
            "BoardSettings fields not persisted by KanbanBoardModel: "
            f"{missing}. Add the ORM column + mapping + migration entry."
        )

    def test_migration_statement_adds_missing_column(self) -> None:
        """The append-only migration entry for legacy DBs is present and keeps default."""
        from app.database.migrations import MIGRATION_STATEMENTS

        assert (
            "ALTER TABLE kanban_boards ADD COLUMN block_recurrence_limit "
            "INTEGER NOT NULL DEFAULT 2" in MIGRATION_STATEMENTS
        )


class TestLegacyBoardMigration:
    """Old databases (table created before the ORM column existed) must gain the
    column via the append-only ALTER migration — with the default value applied
    to pre-existing rows."""

    @pytest.mark.asyncio
    async def test_legacy_table_gets_column_with_default(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.database.migrations import MIGRATION_STATEMENTS

        alter = next(
            s
            for s in MIGRATION_STATEMENTS
            if s.startswith("ALTER TABLE kanban_boards ADD COLUMN block_recurrence_limit")
        )
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "CREATE TABLE kanban_boards ("
                        "id VARCHAR(32) PRIMARY KEY,"
                        "name VARCHAR(255) NOT NULL,"
                        "max_concurrent_tasks INTEGER NOT NULL DEFAULT 3)"
                    )
                )
                await conn.execute(text(alter))
                await conn.execute(
                    text("INSERT INTO kanban_boards (id, name) VALUES ('b-legacy', 'Legacy')")
                )
            async with engine.connect() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT block_recurrence_limit FROM kanban_boards "
                            "WHERE id = 'b-legacy'"
                        )
                    )
                ).first()
                assert row is not None
                assert row[0] == 2
        finally:
            await engine.dispose()
