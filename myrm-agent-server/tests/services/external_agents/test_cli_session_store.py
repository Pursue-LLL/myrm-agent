"""ChatCliSessionStore against the real chat table: durable home of an external agent's CLI session ids."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from myrm_agent_harness.toolkits.acp.types import CliSessionRecord
from sqlalchemy import select, update

from app.database.models.chat import Chat
from app.platform_utils import get_session_factory
from app.services.external_agents.cli_session_store import ChatCliSessionStore

_LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)


async def _create_chat(*, incognito: bool = False) -> str:
    chat_id = f"cli-store-{uuid.uuid4().hex[:10]}"
    async with get_session_factory()() as db:
        db.add(Chat(id=chat_id, title="cli sessions", is_incognito=incognito, updated_at=_LONG_AGO))
        await db.commit()
    return chat_id


async def _stored_column(chat_id: str) -> dict[str, dict[str, str]] | None:
    async with get_session_factory()() as db:
        return (await db.execute(select(Chat.external_cli_sessions).where(Chat.id == chat_id))).scalar_one()


async def _updated_at(chat_id: str) -> datetime:
    async with get_session_factory()() as db:
        return (await db.execute(select(Chat.updated_at).where(Chat.id == chat_id))).scalar_one()


async def test_a_new_store_instance_loads_what_a_previous_one_saved() -> None:
    """The server restarted: the store of the next process is a new object over the same chat row."""
    chat_id = await _create_chat()
    record = CliSessionRecord("cli-abc", "/work/project")

    await ChatCliSessionStore(chat_id).save("claude-chat", record)

    assert await ChatCliSessionStore(chat_id).load("claude-chat") == record


async def test_saving_again_replaces_the_session_of_that_name_only() -> None:
    chat_id = await _create_chat()
    store = ChatCliSessionStore(chat_id)
    await store.save("claude-chat", CliSessionRecord("cli-1", "/work"))
    await store.save("codex-chat", CliSessionRecord("cli-x", "/work"))

    await store.save("claude-chat", CliSessionRecord("cli-2", "/other"))

    assert await store.load("claude-chat") == CliSessionRecord("cli-2", "/other")
    assert await store.load("codex-chat") == CliSessionRecord("cli-x", "/work")


async def test_a_chat_that_does_not_exist_stores_and_loads_nothing() -> None:
    store = ChatCliSessionStore(f"missing-{uuid.uuid4().hex[:10]}")

    await store.save("claude-chat", CliSessionRecord("cli-1", "/work"))

    assert await store.load("claude-chat") is None


async def test_an_incognito_chat_stores_nothing() -> None:
    chat_id = await _create_chat(incognito=True)
    store = ChatCliSessionStore(chat_id)

    await store.save("claude-chat", CliSessionRecord("cli-1", "/work"))

    assert await store.load("claude-chat") is None
    assert not await _stored_column(chat_id)


async def test_saving_a_session_is_not_chat_activity() -> None:
    """The chat list orders by ``updated_at``; bookkeeping must not float a chat to the top."""
    chat_id = await _create_chat()
    store = ChatCliSessionStore(chat_id)

    await store.save("claude-chat", CliSessionRecord("cli-1", "/work"))

    assert (await _updated_at(chat_id)).replace(tzinfo=UTC) == _LONG_AGO


@pytest.mark.parametrize(
    "entry",
    [
        {"cwd": "/work"},
        {"cli_session_id": "", "cwd": "/work"},
        {"cli_session_id": 7, "cwd": "/work"},
        {"cli_session_id": "cli-1", "cwd": None},
        "not-an-entry",
    ],
)
async def test_an_unreadable_stored_entry_loads_as_no_session(entry: object) -> None:
    chat_id = await _create_chat()
    async with get_session_factory()() as db:
        await db.execute(update(Chat).where(Chat.id == chat_id).values(external_cli_sessions={"claude-chat": entry}))
        await db.commit()

    assert await ChatCliSessionStore(chat_id).load("claude-chat") is None


async def test_concurrent_saves_of_different_sessions_both_survive() -> None:
    """Two backends of one chat finishing together read-modify-write the same JSON column."""
    chat_id = await _create_chat()
    store = ChatCliSessionStore(chat_id)

    await asyncio.gather(
        *(store.save(f"agent-{index}", CliSessionRecord(f"cli-{index}", "/work")) for index in range(5)),
    )

    assert sorted(await _stored_column(chat_id) or {}) == [f"agent-{index}" for index in range(5)]
