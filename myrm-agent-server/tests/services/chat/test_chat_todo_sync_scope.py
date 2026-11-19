"""Chats of one project share its workspace directory; each keeps its own todo list there.

[INPUT]
- app.services.chat.chat_todo_sync::resolve_session_todo_store, sync_workspace_todos_for_active_branch
- myrm_agent_harness.agent.meta_tools.progress.storage (POS: per-chat todo lists in the workspace)

[OUTPUT]
- Cases proving the sync follows the workspace a chat runs in and never touches another chat's list.
- Cases proving a failure to read the database or the list is skipped over with a WARNING, not dropped silently.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoItem, TodoStatus, TodoStore
from myrm_agent_harness.agent.meta_tools.progress.storage import (
    read_todos_sync_from_workspace,
    write_todos_sync_to_workspace,
)

from app.database.dto import MessageDTO
from app.services.chat.chat_todo_sync import resolve_session_todo_store, sync_workspace_todos_for_active_branch

_CHAT_A = "chat-a"
_CHAT_B = "chat-b"
_GET_ALL_MESSAGES = "app.services.chat.chat_service.ChatService.get_all_messages"
_GET_CHAT_METADATA = "app.services.chat.chat_service.ChatService.get_chat_metadata"
_SYNC_LOGGER = "app.services.chat.chat_todo_sync"
_READ_TODOS = f"{_SYNC_LOGGER}.read_todos_sync_from_workspace"
_LOCKED = "database is locked"


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    """What the sync logged at WARNING or above: the level an operator sees in production."""
    return [r.getMessage() for r in caplog.records if r.name == _SYNC_LOGGER and r.levelno >= logging.WARNING]


def _list(goal: str, step_id: str, status: TodoStatus = TodoStatus.PENDING) -> TodoStore:
    return TodoStore(goal=goal, todos=[TodoItem(id=step_id, content=f"{goal} step", status=status)], revision=1)


def _message_with(chat_id: str, store: TodoStore) -> MessageDTO:
    now = datetime.now(UTC)
    return MessageDTO(
        id=f"msg-{chat_id}",
        chat_id=chat_id,
        role="assistant",
        content="",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        extra_data={"tool_result_details": store.model_dump()},
        is_active=True,
    )


@pytest.fixture
def project_workspace(tmp_path: Path) -> Iterator[str]:
    """Every chat of this project runs in the project's own directory, not in a sandbox of its own."""
    root = tmp_path / "project"
    root.mkdir()
    chat = SimpleNamespace(project_id="project-1", workspace_dir=None)
    project = SimpleNamespace(workspace_path=str(root))
    with (
        patch(_GET_CHAT_METADATA, new=AsyncMock(return_value=chat)),
        patch("app.services.project.project_service.ProjectService.get_project", new=AsyncMock(return_value=project)),
    ):
        yield str(root)


@pytest.mark.asyncio
async def test_a_rewind_realigns_the_list_in_the_workspace_the_chat_runs_in(project_workspace: str) -> None:
    write_todos_sync_to_workspace(project_workspace, _list("Later plan", "late", TodoStatus.COMPLETED), _CHAT_A)
    earlier = _list("Earlier plan", "early")

    with patch(_GET_ALL_MESSAGES, new=AsyncMock(return_value=[_message_with(_CHAT_A, earlier)])):
        await sync_workspace_todos_for_active_branch(_CHAT_A)

    synced = read_todos_sync_from_workspace(project_workspace, _CHAT_A)
    assert synced is not None
    assert [item.id for item in synced.todos] == ["early"]


@pytest.mark.asyncio
async def test_a_rewind_to_the_start_leaves_other_chats_lists_alone(project_workspace: str) -> None:
    write_todos_sync_to_workspace(project_workspace, _list("A's plan", "a1"), _CHAT_A)
    write_todos_sync_to_workspace(project_workspace, _list("B's plan", "b1"), _CHAT_B)

    with patch(_GET_ALL_MESSAGES, new=AsyncMock(return_value=[])):
        await sync_workspace_todos_for_active_branch(_CHAT_A)

    assert read_todos_sync_from_workspace(project_workspace, _CHAT_A) is None
    kept = read_todos_sync_from_workspace(project_workspace, _CHAT_B)
    assert kept is not None and kept.goal == "B's plan"


@pytest.mark.asyncio
async def test_a_session_key_names_the_same_list_as_the_chat_id(project_workspace: str) -> None:
    write_todos_sync_to_workspace(project_workspace, _list("Later plan", "late"), _CHAT_A)

    with patch(_GET_ALL_MESSAGES, new=AsyncMock(return_value=[_message_with(_CHAT_A, _list("Earlier", "early"))])):
        await sync_workspace_todos_for_active_branch(f"chat_{_CHAT_A}")

    synced = read_todos_sync_from_workspace(project_workspace, _CHAT_A)
    assert synced is not None
    assert [item.id for item in synced.todos] == ["early"]


@pytest.mark.asyncio
async def test_the_plan_fallback_reads_the_chats_own_list(project_workspace: str) -> None:
    write_todos_sync_to_workspace(project_workspace, _list("A's plan", "a1"), _CHAT_A)
    write_todos_sync_to_workspace(project_workspace, _list("B's plan", "b1"), _CHAT_B)

    with patch(_GET_ALL_MESSAGES, new=AsyncMock(return_value=[])):
        first = await resolve_session_todo_store(_CHAT_A)
        second = await resolve_session_todo_store(_CHAT_B)
        neither = await resolve_session_todo_store("chat-c")

    assert first is not None and first.goal == "A's plan"
    assert second is not None and second.goal == "B's plan"
    assert neither is None


@pytest.mark.asyncio
async def test_a_failure_finding_the_workspace_skips_the_sync_and_is_warned_about(
    project_workspace: str, caplog: pytest.LogCaptureFixture
) -> None:
    write_todos_sync_to_workspace(project_workspace, _list("Later plan", "late"), _CHAT_A)

    with (
        patch(_GET_CHAT_METADATA, new=AsyncMock(side_effect=sqlite3.OperationalError(_LOCKED))),
        patch(_GET_ALL_MESSAGES, new=AsyncMock(return_value=[])),
        caplog.at_level(logging.WARNING, logger=_SYNC_LOGGER),
    ):
        await sync_workspace_todos_for_active_branch(_CHAT_A)

    kept = read_todos_sync_from_workspace(project_workspace, _CHAT_A)
    assert kept is not None and kept.goal == "Later plan"
    assert _warnings(caplog) == [f"Failed to resolve workspace root for chat {_CHAT_A}: {_LOCKED}"]


@pytest.mark.asyncio
async def test_a_failure_reading_the_branch_is_warned_about_and_the_workspace_list_still_answers(
    project_workspace: str, caplog: pytest.LogCaptureFixture
) -> None:
    write_todos_sync_to_workspace(project_workspace, _list("A's plan", "a1"), _CHAT_A)

    with (
        patch(_GET_ALL_MESSAGES, new=AsyncMock(side_effect=sqlite3.OperationalError(_LOCKED))),
        caplog.at_level(logging.WARNING, logger=_SYNC_LOGGER),
    ):
        store = await resolve_session_todo_store(_CHAT_A)

    assert store is not None and store.goal == "A's plan"
    assert _warnings(caplog) == [f"Failed to fold todo state from conversation branch {_CHAT_A}: {_LOCKED}"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("project_workspace")
async def test_a_failure_reading_the_workspace_list_is_warned_about_and_no_plan_is_served(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        patch(_GET_ALL_MESSAGES, new=AsyncMock(return_value=[])),
        patch(_READ_TODOS, side_effect=PermissionError("denied")),
        caplog.at_level(logging.WARNING, logger=_SYNC_LOGGER),
    ):
        store = await resolve_session_todo_store(_CHAT_A)

    assert store is None
    assert _warnings(caplog) == [f"Failed to read fallback workspace todos for session {_CHAT_A}: denied"]
