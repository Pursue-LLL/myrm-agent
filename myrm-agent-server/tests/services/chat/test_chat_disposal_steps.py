"""Each disposal step on its own: it reports or swallows its own failures and never blocks the steps after it."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio
from langgraph.checkpoint.base import BaseCheckpointSaver
from myrm_agent_harness.agent.security.approval_flow import AllowlistEntry, get_allowlist
from myrm_agent_harness.toolkits.memory.ephemeral_delta.delta_store import EphemeralDeltaStore
from myrm_agent_harness.toolkits.memory.ephemeral_delta.models import EphemeralDeltaItem
from myrm_agent_harness.toolkits.memory.ephemeral_delta.sqlite_persistence import EphemeralDeltaSqlitePersistence

from app.platform_utils import _reset_checkpointer_for_testing
from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service
from app.services.chat import chat_disposal
from tests.services.chat.disposal_support import (
    CHAT_ID,
    OWNER,
    Spies,
    grant_and_checkpoint,
    install_spies,
    installed_checkpointer,
    is_granted,
    is_stored,
    point_event_log_at_scratch,
    write_event_log,
)


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


@pytest.mark.asyncio
async def test_clear_conversation_state_reports_an_incomplete_checkpoint_clear_yet_drops_the_grants(
    checkpointer: BaseCheckpointSaver[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await grant_and_checkpoint(checkpointer)
    delete_thread = checkpointer.adelete_thread

    async def flaky_delete_thread(thread_id: str) -> None:
        if thread_id == f"chat_{CHAT_ID}":
            raise OSError("disk I/O error")
        await delete_thread(thread_id)

    monkeypatch.setattr(checkpointer, "adelete_thread", flaky_delete_thread)

    assert await chat_disposal.clear_conversation_state(CHAT_ID) is False
    assert not is_granted()


@pytest.mark.asyncio
async def test_clear_conversation_state_without_a_checkpointer_is_not_an_error() -> None:
    _reset_checkpointer_for_testing()
    await get_allowlist().add(OWNER, AllowlistEntry(permission="shell_exec", tool_name="bash", session_id=CHAT_ID))

    assert await chat_disposal.clear_conversation_state(CHAT_ID) is False
    assert not is_granted()


@pytest.mark.asyncio
async def test_clear_conversation_state_is_idempotent(checkpointer: BaseCheckpointSaver[str]) -> None:
    await grant_and_checkpoint(checkpointer)

    assert await chat_disposal.clear_conversation_state(CHAT_ID) is True
    assert await chat_disposal.clear_conversation_state(CHAT_ID) is True


@pytest.mark.asyncio
async def test_remove_chat_files_cleans_every_workspace_in_one_batch(spies: Spies) -> None:
    await chat_disposal.remove_chat_files(["a", "b", "c"])

    spies.workspace.assert_awaited_once_with(["a", "b", "c"])


@pytest.mark.asyncio
async def test_remove_chat_files_swallows_a_failing_workspace_cleanup(spies: Spies) -> None:
    spies.workspace.side_effect = RuntimeError("vault scan unavailable")

    await chat_disposal.remove_chat_files([CHAT_ID])

    spies.workspace.assert_awaited_once_with([CHAT_ID])


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
    spies.ephemeral_delta.side_effect = RuntimeError("cache corrupted")
    await grant_and_checkpoint(checkpointer)

    await chat_disposal.dispose_permanently_deleted_chats([CHAT_ID])

    assert not await is_stored(checkpointer, CHAT_ID)
    assert not is_granted()
    spies.workspace.assert_awaited_once_with([CHAT_ID])


@pytest.mark.asyncio
async def test_remove_chat_event_log_deletes_only_that_chats_file(event_logs: Path) -> None:
    own_log = write_event_log(event_logs, CHAT_ID)
    other_log = write_event_log(event_logs, "another-chat")

    await chat_disposal.remove_chat_event_log(CHAT_ID)
    await chat_disposal.remove_chat_event_log(CHAT_ID)  # a chat that never logged is not an error

    assert not own_log.exists()
    assert other_log.exists()


@pytest.mark.asyncio
async def test_remove_chat_event_log_never_touches_files_outside_the_log_directory(event_logs: Path) -> None:
    outside = write_event_log(event_logs.parent, "outside")

    await chat_disposal.remove_chat_event_log("../outside")

    assert outside.exists()


@pytest.mark.asyncio
async def test_a_failing_event_log_removal_does_not_stop_the_remaining_disposal_steps(
    checkpointer: BaseCheckpointSaver[str],
    spies: Spies,
    event_logs: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_event_log(event_logs, CHAT_ID)
    monkeypatch.setattr(
        "myrm_agent_harness.agent.event_log.backends.file_backend.FileEventLogBackend.remove_session_log",
        AsyncMock(side_effect=PermissionError("log directory is read-only")),
    )
    await grant_and_checkpoint(checkpointer)

    await chat_disposal.dispose_permanently_deleted_chats([CHAT_ID])

    assert not await is_stored(checkpointer, CHAT_ID)
    assert not is_granted()
    spies.memory_purge.assert_awaited_once_with(CHAT_ID)
    spies.workspace.assert_awaited_once_with([CHAT_ID])


@pytest.mark.asyncio
async def test_clear_runtime_caches_forgets_the_wake_budget_and_stop_flag_of_the_chat(spies: Spies) -> None:
    service = get_adaptive_wakeup_service()
    service.record_user_stop(CHAT_ID)

    await chat_disposal.clear_runtime_caches(CHAT_ID)

    spies.runtime_pool.assert_awaited_once_with(CHAT_ID)
    assert not service.get_budget_state(CHAT_ID).is_user_stopped


@pytest.mark.asyncio
async def test_clear_runtime_caches_leaves_the_loop_running_while_the_delta_store_waits_for_its_lock(
    tmp_path: Path,
    spies: Spies,
) -> None:
    """A coroutine holding the write lock can only release it when the loop runs, so a clear that waits for the lock on
    the loop thread is refused once its timeout is over."""
    db_path = tmp_path / "memory.db"
    persistence = EphemeralDeltaSqlitePersistence(db_path)
    store = EphemeralDeltaStore(persistence=persistence)
    store.record_delta(CHAT_ID, EphemeralDeltaItem(delta_id="delta-1", target_key="name", content="Ada"))
    spies.ephemeral_delta.side_effect = store.clear

    async with aiosqlite.connect(db_path) as writer:
        await writer.execute("BEGIN IMMEDIATE")

        async def release_the_lock() -> None:
            await asyncio.sleep(0.3)
            await writer.commit()

        release = asyncio.create_task(release_the_lock())
        await chat_disposal.clear_runtime_caches(CHAT_ID)
        await release

    assert persistence.load_raw_deltas(CHAT_ID) == []
