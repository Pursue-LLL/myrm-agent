"""Every way a chat can end must tear down the same state, and a chat that is not in the trash must survive.

The entry points (permanent delete, empty trash, the two auto-purges) are exercised against a real schema, a real
checkpointer and the real approval allowlist; the slower collaborators (memory vector store, workspaces, runtime caches)
are recorded by spies. One parametrised scenario table keeps the entry points from drifting apart.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

import pytest
import pytest_asyncio
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from app.services.agent.gateway import get_agent_gateway
from app.services.chat import chat_retention
from app.services.chat.chat_bound_rows import CHAT_BOUND_TABLES, ChatBoundTable
from app.services.chat.chat_service import ChatService
from tests.services.chat.disposal_support import (
    CHAT_ID,
    SANDBOX_DIR,
    SANDBOX_ROOT,
    Spies,
    grant_and_checkpoint,
    install_spies,
    installed_checkpointer,
    is_granted,
    is_stored,
    point_event_log_at_scratch,
    write_event_log,
)
from tests.support.real_schema_db import seed_row


@pytest.fixture
def spies(monkeypatch: pytest.MonkeyPatch) -> Spies:
    return install_spies(monkeypatch)


@pytest.fixture(autouse=True)
def event_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return point_event_log_at_scratch(tmp_path, monkeypatch)


@pytest_asyncio.fixture
async def checkpointer() -> AsyncIterator[BaseCheckpointSaver[str]]:
    async with installed_checkpointer() as saver:
        yield saver


async def _seed_chat(
    db: AsyncSession,
    chat_id: str = CHAT_ID,
    *,
    trashed_for: timedelta | None = None,
    incognito: bool = False,
    idle_for: timedelta = timedelta(0),
    source: str = "web",
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add(
        Chat(
            id=chat_id,
            title="disposal",
            source=source,
            is_incognito=incognito,
            sandbox_base_dir=f"{SANDBOX_ROOT}/{chat_id}",
            created_at=now - idle_for,
            updated_at=now - idle_for,
            deleted_at=None if trashed_for is None else now - trashed_for,
        )
    )
    await db.flush()
    db.add(
        Message(id=f"m-{chat_id}", chat_id=chat_id, role="user", content="hello", sent_at=datetime.now(UTC), sent_timezone="UTC")
    )
    connection = await db.connection()
    for bound in CHAT_BOUND_TABLES:
        await seed_row(connection, bound.table, **{bound.chat_column: chat_id})
    await db.commit()


async def _count(db: AsyncSession, model: type[Chat] | type[Message]) -> int:
    db.expire_all()
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def _bound_row_count(db: AsyncSession, bound: ChatBoundTable) -> int:
    db.expire_all()
    return (await db.execute(text(f"SELECT COUNT(*) FROM {bound.table}"))).scalar_one()


@dataclass(frozen=True)
class Entry:
    """One way a chat ends: how it is staged and which call ends it."""

    name: str
    stage: Callable[[AsyncSession], Awaitable[None]]
    run: Callable[[], Awaitable[object]]


ENTRIES = [
    Entry(
        "permanent_delete",
        partial(_seed_chat, trashed_for=timedelta(minutes=5)),
        lambda: ChatService.permanently_delete_chat(CHAT_ID),
    ),
    Entry("empty_trash", partial(_seed_chat, trashed_for=timedelta(minutes=5)), ChatService.empty_trash),
    Entry("trash_auto_purge", partial(_seed_chat, trashed_for=timedelta(days=31)), chat_retention.purge_expired_trash),
    Entry(
        "incognito_auto_purge",
        partial(_seed_chat, incognito=True, idle_for=timedelta(hours=2)),
        chat_retention.purge_idle_incognito_chats,
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ENTRIES, ids=[e.name for e in ENTRIES])
async def test_every_entry_point_tears_down_the_same_state(
    entry: Entry,
    db_session: AsyncSession,
    checkpointer: BaseCheckpointSaver[str],
    spies: Spies,
    event_logs: Path,
) -> None:
    await entry.stage(db_session)
    await grant_and_checkpoint(checkpointer)
    own_log = write_event_log(event_logs, CHAT_ID)
    other_log = write_event_log(event_logs, "another-chat")
    assert await is_stored(checkpointer, CHAT_ID)
    assert is_granted()

    await entry.run()

    assert not own_log.exists(), "the event log holds the full prompts of the deleted chat"
    assert other_log.exists()
    assert await _count(db_session, Chat) == 0
    assert await _count(db_session, Message) == 0
    for bound in CHAT_BOUND_TABLES:
        assert await _bound_row_count(db_session, bound) == 0, f"{bound.table} kept the rows of the deleted chat"
    assert not await is_stored(checkpointer, CHAT_ID)
    assert not await is_stored(checkpointer, f"chat_{CHAT_ID}")
    assert not is_granted()
    spies.runtime_pool.assert_awaited_once_with(CHAT_ID)
    spies.execution_cache.assert_awaited_once_with(CHAT_ID)
    spies.ephemeral_delta.assert_called_once_with(CHAT_ID)
    spies.memory_purge.assert_awaited_once_with(CHAT_ID)
    spies.retry_queue.assert_awaited_once_with(CHAT_ID)
    spies.worktree.assert_awaited_once_with(SANDBOX_DIR, CHAT_ID)
    spies.workspace.assert_awaited_once_with([CHAT_ID])


@pytest.mark.asyncio
async def test_emptying_the_trash_cleans_the_workspaces_of_all_chats_in_one_call(
    db_session: AsyncSession,
    checkpointer: BaseCheckpointSaver[str],
    spies: Spies,
) -> None:
    """Workspace cleanup scans the shared artifact vault, so it must not run once per chat."""
    chat_ids = ["trash-a", "trash-b", "trash-c"]
    for chat_id in chat_ids:
        await _seed_chat(db_session, chat_id, trashed_for=timedelta(minutes=5))

    assert await ChatService.empty_trash() == 3

    spies.workspace.assert_awaited_once()
    workspace_call = spies.workspace.await_args
    assert workspace_call is not None
    assert sorted(workspace_call.args[0]) == chat_ids
    assert spies.worktree.await_count == 3
    assert sorted(call.args[0] for call in spies.memory_purge.await_args_list) == chat_ids


@pytest.mark.asyncio
async def test_permanent_delete_of_a_chat_outside_the_trash_changes_nothing(
    db_session: AsyncSession,
    checkpointer: BaseCheckpointSaver[str],
    spies: Spies,
    event_logs: Path,
) -> None:
    """A stale trash view must not wipe the history of a chat that was restored meanwhile."""
    await _seed_chat(db_session)
    await grant_and_checkpoint(checkpointer)
    own_log = write_event_log(event_logs, CHAT_ID)

    assert await ChatService.permanently_delete_chat(CHAT_ID) is False

    assert own_log.exists()
    assert await _count(db_session, Chat) == 1
    assert await _count(db_session, Message) == 1
    for bound in CHAT_BOUND_TABLES:
        assert await _bound_row_count(db_session, bound) == 1, f"{bound.table} lost the rows of a chat outside the trash"
    assert await is_stored(checkpointer, CHAT_ID)
    assert is_granted()
    spies.memory_purge.assert_not_awaited()
    spies.workspace.assert_not_awaited()


@pytest.mark.asyncio
async def test_permanent_delete_removes_the_recall_index_of_the_chat(
    db_session: AsyncSession,
    spies: Spies,
) -> None:
    await _seed_chat(db_session, trashed_for=timedelta(minutes=1))
    await db_session.execute(text("INSERT INTO conversation_recall_documents (chat_id) VALUES (:chat_id)"), {"chat_id": CHAT_ID})
    await db_session.commit()

    assert await ChatService.permanently_delete_chat(CHAT_ID) is True

    remaining: int = (await db_session.execute(text("SELECT COUNT(*) FROM conversation_recall_documents"))).scalar_one()
    assert remaining == 0


@pytest.mark.asyncio
async def test_focus_flush_clears_the_conversation_state_but_keeps_the_chat(
    db_session: AsyncSession,
    checkpointer: BaseCheckpointSaver[str],
    spies: Spies,
) -> None:
    await _seed_chat(db_session)
    await grant_and_checkpoint(checkpointer)

    assert await ChatService.focus_flush_session(CHAT_ID) is True

    assert not await is_stored(checkpointer, CHAT_ID)
    assert not is_granted()
    assert await _count(db_session, Chat) == 1
    spies.workspace.assert_not_awaited()
    spies.memory_purge.assert_not_awaited()


@pytest.mark.asyncio
async def test_soft_delete_stops_runtime_work_but_keeps_everything_restorable(
    db_session: AsyncSession,
    checkpointer: BaseCheckpointSaver[str],
    spies: Spies,
) -> None:
    await _seed_chat(db_session)
    await grant_and_checkpoint(checkpointer)

    assert await ChatService.delete_chat(CHAT_ID) is True

    spies.runtime_pool.assert_awaited_once_with(CHAT_ID)
    spies.execution_cache.assert_awaited_once_with(CHAT_ID)
    spies.ephemeral_delta.assert_called_once_with(CHAT_ID)
    spies.retry_queue.assert_awaited_once_with(CHAT_ID)
    spies.memory_purge.assert_not_awaited()
    spies.workspace.assert_not_awaited()
    assert await is_stored(checkpointer, CHAT_ID)
    assert is_granted()


@pytest.mark.asyncio
async def test_incognito_auto_purge_spares_imported_transcripts(
    db_session: AsyncSession,
    checkpointer: BaseCheckpointSaver[str],
    spies: Spies,
) -> None:
    """Imported agent transcripts are hidden through ``is_incognito`` but belong to no incognito session."""
    await _seed_chat(db_session, incognito=True, idle_for=timedelta(hours=2), source="external:claude_code")

    assert await chat_retention.purge_idle_incognito_chats() == 0

    assert await _count(db_session, Chat) == 1
    assert await _count(db_session, Message) == 1
    spies.memory_purge.assert_not_awaited()


@pytest.mark.asyncio
async def test_incognito_auto_purge_waits_for_the_running_turn_to_end(
    db_session: AsyncSession,
    checkpointer: BaseCheckpointSaver[str],
    spies: Spies,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A long task keeps the chat idle for hours; the purge must not delete the conversation under the agent."""
    await _seed_chat(db_session, incognito=True, idle_for=timedelta(hours=2))
    gateway = get_agent_gateway()
    monkeypatch.setattr(gateway, "active_session_ids", lambda: frozenset({CHAT_ID}))

    assert await chat_retention.purge_idle_incognito_chats() == 0
    assert await _count(db_session, Chat) == 1

    monkeypatch.setattr(gateway, "active_session_ids", lambda: frozenset())

    assert await chat_retention.purge_idle_incognito_chats() == 1
    assert await _count(db_session, Chat) == 0
