"""Existing databases lose ``interrupted_turn_markers.pending_steering_messages``; fresh ones never keep it and the migrations stay idempotent."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.database import migrations
from app.database.models import Base, Chat, InterruptedTurnMarker

_ADD = "ALTER TABLE interrupted_turn_markers ADD COLUMN pending_steering_messages JSON"
_DROP = "ALTER TABLE interrupted_turn_markers DROP COLUMN pending_steering_messages"
_FULL_LIST = list(migrations.INDEX_STATEMENTS)
# An upgrading database already recorded every statement that precedes the drop.
_RELEASED = _FULL_LIST[: _FULL_LIST.index(_DROP)]


async def _marker_columns(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        return {row[1] for row in await conn.execute(text("PRAGMA table_info(interrupted_turn_markers)"))}


def test_the_drop_runs_after_the_statement_that_added_the_column() -> None:
    # Both statements share one list and one ledger, so the order in the list is the order of execution.
    assert _FULL_LIST.index(_ADD) < _FULL_LIST.index(_DROP)


@pytest.mark.asyncio
async def test_an_upgrading_database_loses_the_column_and_keeps_its_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upgrading.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # The shape of an upgrading database: the table still carries the column the models no longer map.
            await conn.execute(text(_ADD))
        monkeypatch.setattr(migrations, "INDEX_STATEMENTS", _RELEASED)
        await migrations.create_indexes(engine)
        assert "pending_steering_messages" in await _marker_columns(engine)

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as session:
            session.add(Chat(id="legacy-chat", title="Kept title"))
            await session.flush()
            session.add(
                InterruptedTurnMarker(
                    id="marker-1",
                    chat_id="legacy-chat",
                    user_message_id="msg-1",
                    action_mode="deep",
                    serialized_params={"message": "resume me"},
                )
            )
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE interrupted_turn_markers SET pending_steering_messages = '[\"old\"]' WHERE id = 'marker-1'")
            )

        monkeypatch.setattr(migrations, "INDEX_STATEMENTS", _FULL_LIST)
        await migrations.create_indexes(engine)

        assert "pending_steering_messages" not in await _marker_columns(engine)
        async with sessions() as session:
            marker = (await session.execute(select(InterruptedTurnMarker))).scalar_one()
        assert (marker.id, marker.user_message_id, marker.action_mode, marker.serialized_params) == (
            "marker-1",
            "msg-1",
            "deep",
            {"message": "resume me"},
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_database_that_never_had_the_column_skips_the_drop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'never_had_it.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        monkeypatch.setattr(migrations, "INDEX_STATEMENTS", _RELEASED)
        await migrations.create_indexes(engine)
        assert "pending_steering_messages" not in await _marker_columns(engine)

        monkeypatch.setattr(migrations, "INDEX_STATEMENTS", _FULL_LIST)
        await migrations.create_indexes(engine)

        assert "pending_steering_messages" not in await _marker_columns(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_new_database_never_keeps_the_column_and_migrations_stay_idempotent(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await migrations.create_indexes(engine)
        await migrations.create_indexes(engine)

        assert "pending_steering_messages" not in await _marker_columns(engine)
    finally:
        await engine.dispose()
