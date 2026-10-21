"""Each disposal step on its own: it reports or swallows its own failures and never blocks the steps after it."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from langgraph.checkpoint.base import BaseCheckpointSaver
from myrm_agent_harness.agent.security.approval_flow import AllowlistEntry, get_allowlist

from app.platform_utils import _reset_checkpointer_for_testing
from app.services.chat import chat_disposal
from app.services.chat.chat_disposal import ChatFilesRemoval
from tests.services.chat.disposal_support import (
    CHAT_ID,
    OWNER,
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
    await grant_and_checkpoint(checkpointer)

    await chat_disposal.dispose_permanently_deleted_chats({CHAT_ID: SANDBOX_DIR})

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

    await chat_disposal.dispose_permanently_deleted_chats({CHAT_ID: SANDBOX_DIR})

    assert not await is_stored(checkpointer, CHAT_ID)
    assert not is_granted()
    spies.memory_purge.assert_awaited_once_with(CHAT_ID)
    spies.workspace.assert_awaited_once_with([CHAT_ID])
