"""Existing databases lose ``chats.sandbox_base_dir``; fresh databases never keep it and the migrations stay idempotent."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.database import migrations
from app.database.models import Base, Chat

_DROP = "ALTER TABLE chats DROP COLUMN sandbox_base_dir"
_FULL_LIST = list(migrations.MIGRATION_STATEMENTS)
# An upgrading database already recorded every statement that precedes the drop.
_RELEASED = _FULL_LIST[: _FULL_LIST.index(_DROP)]


async def _chat_columns(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        return {row[1] for row in await conn.execute(text("PRAGMA table_info(chats)"))}


@pytest.mark.asyncio
async def test_an_upgrading_database_loses_the_column_and_keeps_its_chats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upgrading.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # The shape of an upgrading database: the table still carries the column the models no longer map.
            await conn.execute(text("ALTER TABLE chats ADD COLUMN sandbox_base_dir VARCHAR(1024)"))
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", _RELEASED)
        await migrations.run_migrations(engine)
        assert "sandbox_base_dir" in await _chat_columns(engine)

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as session:
            session.add(Chat(id="legacy-chat", title="Kept title", workspace_dir="/work/repo"))
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE chats SET sandbox_base_dir = '/work/repo' WHERE id = 'legacy-chat'"))

        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", _FULL_LIST)
        await migrations.run_migrations(engine)

        assert "sandbox_base_dir" not in await _chat_columns(engine)
        async with sessions() as session:
            chat = (await session.execute(select(Chat).where(Chat.id == "legacy-chat"))).scalar_one()
        assert (chat.title, chat.workspace_dir) == ("Kept title", "/work/repo")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_new_database_never_keeps_the_column_and_migrations_stay_idempotent(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await migrations.run_migrations(engine)
        await migrations.run_migrations(engine)

        assert "sandbox_base_dir" not in await _chat_columns(engine)
    finally:
        await engine.dispose()
