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
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from myrm_agent_harness.agent.security.approval_flow import AllowlistEntry, get_allowlist
from myrm_agent_harness.runtime.context.session.session_continuity import sync_checkpoint_messages
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from app.platform_utils import _reset_checkpointer_for_testing, set_checkpointer
from app.services.chat import chat_disposal, chat_retention
from app.services.chat.chat_bound_rows import CHAT_BOUND_TABLES, ChatBoundTable
from app.services.chat.chat_disposal import ChatFilesRemoval
from app.services.chat.chat_service import ChatService
from tests.support.real_schema_db import seed_row

CHAT_ID = "chat-disposal-1"
SANDBOX_ROOT = "/tmp/myrm-test-sandbox"
SANDBOX_DIR = f"{SANDBOX_ROOT}/{CHAT_ID}"
OWNER = "sandbox"


@dataclass
class Spies:
    runtime_pool: AsyncMock
    execution_cache: AsyncMock
    memory_purge: AsyncMock
    retry_queue: AsyncMock
    worktree: AsyncMock
    workspace: AsyncMock
    working_memory: MagicMock


@pytest.fixture
def spies(monkeypatch: pytest.MonkeyPatch) -> Spies:
    recorded = Spies(
        runtime_pool=AsyncMock(),
        execution_cache=AsyncMock(),
        memory_purge=AsyncMock(return_value={}),
        retry_queue=AsyncMock(),
        worktree=AsyncMock(return_value=True),
        workspace=AsyncMock(return_value={}),
        working_memory=MagicMock(),
    )
    monkeypatch.setattr(chat_disposal, "close_external_agent_pool_for_chat", recorded.runtime_pool)
    monkeypatch.setattr(chat_disposal, "close_execution_cache_for_chat_all_agents", recorded.execution_cache)
    manager = MagicMock(purge_by_source_chat_id=recorded.memory_purge)
    monkeypatch.setattr("app.core.memory.get_cascade_memory_manager", AsyncMock(return_value=manager))
    monkeypatch.setattr("app.services.memory.extract_retry.extract_retry_queue.clear_for_chat", recorded.retry_queue)
    monkeypatch.setattr("app.services.chat.sandbox_worktree.cleanup_sandbox_worktree", recorded.worktree)
    monkeypatch.setattr("app.services.infra.sandbox_cleanup.cleanup_chat_workspaces", recorded.workspace)
    monkeypatch.setattr(
        "app.services.memory.consolidation_service.ConsolidationService.clear_session_working_state",
        recorded.working_memory,
    )
    return recorded


@pytest.fixture(autouse=True)
def event_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the event log at a scratch directory so no test reads or deletes the real one."""
    log_dir = tmp_path / "event_logs"
    log_dir.mkdir()
    monkeypatch.setattr("app.config.settings.settings.database.event_log_dir", str(log_dir))
    return log_dir


def _write_event_log(log_dir: Path, session_id: str) -> Path:
    path = log_dir / f"{session_id}.jsonl"
    path.write_text('{"event_type": "llm_request", "data": {"prompt_preview": "[user] secret"}}\n', encoding="utf-8")
    return path


@pytest_asyncio.fixture
async def checkpointer() -> AsyncIterator[BaseCheckpointSaver[str]]:
    saver = MemorySaver()
    set_checkpointer(saver)
    yield saver
    _reset_checkpointer_for_testing()
    await get_allowlist().clear_session(OWNER, CHAT_ID)


async def _seed_chat(
    db: AsyncSession,
    chat_id: str = CHAT_ID,
    *,
    trashed_for: timedelta | None = None,
    incognito: bool = False,
    idle_for: timedelta = timedelta(0),
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add(
        Chat(
            id=chat_id,
            title="disposal",
            source="web",
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


async def _grant_and_checkpoint(saver: BaseCheckpointSaver[str]) -> None:
    await sync_checkpoint_messages(saver, CHAT_ID, [HumanMessage("question"), AIMessage("answer")])
    await get_allowlist().add(OWNER, AllowlistEntry(permission="shell_exec", tool_name="bash", session_id=CHAT_ID))


async def _is_stored(saver: BaseCheckpointSaver[str], thread_id: str) -> bool:
    return await saver.aget_tuple({"configurable": {"thread_id": thread_id}}) is not None


def _is_granted() -> bool:
    return get_allowlist().check(OWNER, "shell_exec", "bash", session_id=CHAT_ID)


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
    await _grant_and_checkpoint(checkpointer)
    own_log = _write_event_log(event_logs, CHAT_ID)
    other_log = _write_event_log(event_logs, "another-chat")
    assert await _is_stored(checkpointer, CHAT_ID)
    assert _is_granted()

    await entry.run()

    assert not own_log.exists(), "the event log holds the full prompts of the deleted chat"
    assert other_log.exists()
    assert await _count(db_session, Chat) == 0
    assert await _count(db_session, Message) == 0
    for bound in CHAT_BOUND_TABLES:
        assert await _bound_row_count(db_session, bound) == 0, f"{bound.table} kept the rows of the deleted chat"
    assert not await _is_stored(checkpointer, CHAT_ID)
    assert not await _is_stored(checkpointer, f"chat_{CHAT_ID}")
    assert not _is_granted()
    spies.runtime_pool.assert_awaited_once_with(CHAT_ID)
    spies.execution_cache.assert_awaited_once_with(CHAT_ID)
    spies.working_memory.assert_called_once_with(CHAT_ID)
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
    await _grant_and_checkpoint(checkpointer)
    own_log = _write_event_log(event_logs, CHAT_ID)

    assert await ChatService.permanently_delete_chat(CHAT_ID) is False

    assert own_log.exists()
    assert await _count(db_session, Chat) == 1
    assert await _count(db_session, Message) == 1
    for bound in CHAT_BOUND_TABLES:
        assert await _bound_row_count(db_session, bound) == 1, f"{bound.table} lost the rows of a chat outside the trash"
    assert await _is_stored(checkpointer, CHAT_ID)
    assert _is_granted()
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
    await _grant_and_checkpoint(checkpointer)

    assert await ChatService.focus_flush_session(CHAT_ID) is True

    assert not await _is_stored(checkpointer, CHAT_ID)
    assert not _is_granted()
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
    await _grant_and_checkpoint(checkpointer)

    assert await ChatService.delete_chat(CHAT_ID) is True

    spies.runtime_pool.assert_awaited_once_with(CHAT_ID)
    spies.execution_cache.assert_awaited_once_with(CHAT_ID)
    spies.working_memory.assert_called_once_with(CHAT_ID)
    spies.retry_queue.assert_awaited_once_with(CHAT_ID)
    spies.memory_purge.assert_not_awaited()
    spies.workspace.assert_not_awaited()
    assert await _is_stored(checkpointer, CHAT_ID)
    assert _is_granted()


# ── Individual steps ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_conversation_state_reports_an_incomplete_checkpoint_clear_yet_drops_the_grants(
    checkpointer: BaseCheckpointSaver[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _grant_and_checkpoint(checkpointer)
    delete_thread = checkpointer.adelete_thread

    async def flaky_delete_thread(thread_id: str) -> None:
        if thread_id == f"chat_{CHAT_ID}":
            raise OSError("disk I/O error")
        await delete_thread(thread_id)

    monkeypatch.setattr(checkpointer, "adelete_thread", flaky_delete_thread)

    assert await chat_disposal.clear_conversation_state(CHAT_ID) is False
    assert not _is_granted()


@pytest.mark.asyncio
async def test_clear_conversation_state_without_a_checkpointer_is_not_an_error() -> None:
    _reset_checkpointer_for_testing()
    await get_allowlist().add(OWNER, AllowlistEntry(permission="shell_exec", tool_name="bash", session_id=CHAT_ID))

    assert await chat_disposal.clear_conversation_state(CHAT_ID) is False
    assert not _is_granted()


@pytest.mark.asyncio
async def test_clear_conversation_state_is_idempotent(checkpointer: BaseCheckpointSaver[str]) -> None:
    await _grant_and_checkpoint(checkpointer)

    assert await chat_disposal.clear_conversation_state(CHAT_ID) is True
    assert await chat_disposal.clear_conversation_state(CHAT_ID) is True


@pytest.mark.asyncio
async def test_remove_chat_files_keeps_removing_the_workspace_when_the_worktree_fails(spies: Spies) -> None:
    spies.worktree.side_effect = RuntimeError("worktree busy")

    assert await chat_disposal.remove_chat_files({CHAT_ID: SANDBOX_DIR}) == ChatFilesRemoval(kept_worktrees=1)

    spies.workspace.assert_awaited_once_with([CHAT_ID])


@pytest.mark.asyncio
async def test_remove_chat_files_without_a_sandbox_skips_the_worktree(spies: Spies) -> None:
    assert await chat_disposal.remove_chat_files({CHAT_ID: None}) == ChatFilesRemoval()

    spies.worktree.assert_not_awaited()
    spies.workspace.assert_awaited_once_with([CHAT_ID])


@pytest.mark.asyncio
async def test_remove_chat_files_counts_removed_worktrees_and_cleans_all_workspaces_in_one_call(spies: Spies) -> None:
    removal = await chat_disposal.remove_chat_files({"a": f"{SANDBOX_ROOT}/a", "b": None, "c": f"{SANDBOX_ROOT}/c"})

    assert removal == ChatFilesRemoval(removed_worktrees=2)
    assert spies.worktree.await_count == 2
    spies.workspace.assert_awaited_once_with(["a", "b", "c"])


@pytest.mark.asyncio
async def test_remove_chat_files_leaves_a_worktree_with_unsaved_work_in_place(spies: Spies) -> None:
    """Safe mode: the worktree that refuses removal is reported as kept, and the other chats are still cleaned."""
    spies.worktree.side_effect = [False, True]

    removal = await chat_disposal.remove_chat_files({"dirty": f"{SANDBOX_ROOT}/dirty", "clean": f"{SANDBOX_ROOT}/clean"})

    assert removal == ChatFilesRemoval(removed_worktrees=1, kept_worktrees=1)
    assert [call.kwargs for call in spies.worktree.await_args_list] == [{}, {}]
    spies.workspace.assert_awaited_once_with(["dirty", "clean"])


@pytest.mark.asyncio
async def test_forget_chat_memories_survives_a_failing_vector_store(spies: Spies) -> None:
    spies.memory_purge.side_effect = RuntimeError("vector store unavailable")

    await chat_disposal.forget_chat_memories(CHAT_ID)

    spies.retry_queue.assert_awaited_once_with(CHAT_ID)


@pytest.mark.asyncio
async def test_a_failing_step_does_not_stop_the_remaining_disposal_steps(
    checkpointer: BaseCheckpointSaver[str],
    spies: Spies,
) -> None:
    spies.memory_purge.side_effect = RuntimeError("vector store unavailable")
    spies.working_memory.side_effect = RuntimeError("cache corrupted")
    spies.worktree.side_effect = RuntimeError("worktree busy")
    await _grant_and_checkpoint(checkpointer)

    await chat_disposal.dispose_permanently_deleted_chats({CHAT_ID: SANDBOX_DIR})

    assert not await _is_stored(checkpointer, CHAT_ID)
    assert not _is_granted()
    spies.workspace.assert_awaited_once_with([CHAT_ID])


@pytest.mark.asyncio
async def test_remove_chat_event_log_deletes_only_that_chats_file(event_logs: Path) -> None:
    own_log = _write_event_log(event_logs, CHAT_ID)
    other_log = _write_event_log(event_logs, "another-chat")

    await chat_disposal.remove_chat_event_log(CHAT_ID)
    await chat_disposal.remove_chat_event_log(CHAT_ID)  # a chat that never logged is not an error

    assert not own_log.exists()
    assert other_log.exists()


@pytest.mark.asyncio
async def test_remove_chat_event_log_never_touches_files_outside_the_log_directory(event_logs: Path) -> None:
    outside = _write_event_log(event_logs.parent, "outside")

    await chat_disposal.remove_chat_event_log("../outside")

    assert outside.exists()


@pytest.mark.asyncio
async def test_a_failing_event_log_removal_does_not_stop_the_remaining_disposal_steps(
    checkpointer: BaseCheckpointSaver[str],
    spies: Spies,
    event_logs: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_event_log(event_logs, CHAT_ID)
    monkeypatch.setattr(
        "myrm_agent_harness.agent.event_log.backends.file_backend.FileEventLogBackend.remove_session_log",
        AsyncMock(side_effect=PermissionError("log directory is read-only")),
    )
    await _grant_and_checkpoint(checkpointer)

    await chat_disposal.dispose_permanently_deleted_chats({CHAT_ID: SANDBOX_DIR})

    assert not await _is_stored(checkpointer, CHAT_ID)
    assert not _is_granted()
    spies.memory_purge.assert_awaited_once_with(CHAT_ID)
    spies.workspace.assert_awaited_once_with([CHAT_ID])
