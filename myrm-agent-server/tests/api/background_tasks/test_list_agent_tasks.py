"""Tests for ``_list_agent_tasks()`` in background_tasks/router.py.

Verifies the Kanban-direct query path that replaced the old
``handler.list_background()`` approach, ensuring:
- Only tasks with ``is_persistent_background`` metadata are returned.
- ``chat_id`` is correctly populated from task metadata.
- ``result_preview`` is populated for terminal tasks from event payloads.
- Tasks are sorted newest-first.
- Empty board returns empty list.
- Non-persistent tasks are filtered out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import TaskEvent, TaskEventKind, TaskStatus


@dataclass
class _FakeTask:
    task_id: str
    board_id: str = "sys-bg"
    title: str = "task"
    description: str = ""
    status: str = TaskStatus.RUNNING
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


def _make_btw_task(
    task_id: str,
    *,
    status: str = TaskStatus.RUNNING,
    chat_id: str | None = None,
    error: str = "",
    created_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> _FakeTask:
    meta: dict[str, Any] = {"background_source": "btw"}
    if chat_id:
        meta["chat_id"] = chat_id
    return _FakeTask(
        task_id=task_id,
        status=status,
        error=error,
        metadata=meta,
        created_at=created_at or datetime.now(UTC),
        completed_at=completed_at,
    )


def _make_voice_task(
    task_id: str,
    *,
    status: str = TaskStatus.RUNNING,
    chat_id: str | None = None,
) -> _FakeTask:
    meta: dict[str, Any] = {"background_source": "voice"}
    if chat_id:
        meta["chat_id"] = chat_id
    return _FakeTask(
        task_id=task_id,
        status=status,
        metadata=meta,
    )


def _make_non_persistent_task(task_id: str) -> _FakeTask:
    return _FakeTask(task_id=task_id, metadata={"some_key": "val"})


def _mock_handler() -> MagicMock:
    handler = MagicMock()
    handler._ensure_system_board = AsyncMock(return_value="sys-bg")
    return handler


def _mock_store(tasks: list[_FakeTask], events: list[TaskEvent] | None = None) -> MagicMock:
    store = MagicMock()
    store.list_tasks = AsyncMock(return_value=tasks)
    store.list_events = AsyncMock(return_value=events or [])
    return store


def _mock_svc(store: MagicMock) -> MagicMock:
    svc = MagicMock()
    svc.store = store
    return svc


@pytest.fixture
def _patches():
    """Patch the three lazy imports used inside ``_list_agent_tasks``."""
    with (
        patch("app.api.background_tasks.router.get_background_task_handler") as mock_get_handler,
        patch("app.services.kanban.KanbanService.get_instance") as mock_get_svc,
    ):
        yield mock_get_handler, mock_get_svc


@pytest.mark.asyncio
async def test_empty_board_returns_empty(_patches: tuple[MagicMock, MagicMock]) -> None:
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = _mock_handler()
    store = _mock_store([])
    mock_get_svc.return_value = _mock_svc(store)

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    assert result == []


@pytest.mark.asyncio
async def test_no_handler_returns_empty(_patches: tuple[MagicMock, MagicMock]) -> None:
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = None

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    assert result == []


@pytest.mark.asyncio
async def test_filters_non_persistent_tasks(_patches: tuple[MagicMock, MagicMock]) -> None:
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = _mock_handler()

    btw = _make_btw_task("t1")
    non = _make_non_persistent_task("t2")
    voice = _make_voice_task("t3")
    store = _mock_store([btw, non, voice])
    mock_get_svc.return_value = _mock_svc(store)

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    ids = {r.task_id for r in result}
    assert ids == {"t1", "t3"}
    assert "t2" not in ids


@pytest.mark.asyncio
async def test_chat_id_populated(_patches: tuple[MagicMock, MagicMock]) -> None:
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = _mock_handler()

    task = _make_btw_task("t1", chat_id="chat-abc-123")
    store = _mock_store([task])
    mock_get_svc.return_value = _mock_svc(store)

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    assert len(result) == 1
    assert result[0].chat_id == "chat-abc-123"


@pytest.mark.asyncio
async def test_chat_id_none_when_absent(_patches: tuple[MagicMock, MagicMock]) -> None:
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = _mock_handler()

    task = _make_btw_task("t1")
    store = _mock_store([task])
    mock_get_svc.return_value = _mock_svc(store)

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    assert len(result) == 1
    assert result[0].chat_id is None


@pytest.mark.asyncio
async def test_result_preview_from_events(_patches: tuple[MagicMock, MagicMock]) -> None:
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = _mock_handler()

    task = _make_btw_task("t1", status=TaskStatus.COMPLETED, completed_at=datetime.now(UTC))
    events = [
        TaskEvent(
            event_id=1,
            task_id="t1",
            kind=TaskEventKind.COMPLETED,
            payload={"result_preview": "Research complete: found 3 papers"},
        ),
    ]
    store = _mock_store([task], events)
    mock_get_svc.return_value = _mock_svc(store)

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    assert len(result) == 1
    assert result[0].result_preview == "Research complete: found 3 papers"


@pytest.mark.asyncio
async def test_result_preview_none_for_running(_patches: tuple[MagicMock, MagicMock]) -> None:
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = _mock_handler()

    task = _make_btw_task("t1", status=TaskStatus.RUNNING)
    store = _mock_store([task])
    mock_get_svc.return_value = _mock_svc(store)

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    assert len(result) == 1
    assert result[0].result_preview is None


@pytest.mark.asyncio
async def test_sorted_newest_first(_patches: tuple[MagicMock, MagicMock]) -> None:
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = _mock_handler()

    now = datetime.now(UTC)
    old = _make_btw_task("old", created_at=now - timedelta(hours=1))
    new = _make_btw_task("new", created_at=now)
    mid = _make_btw_task("mid", created_at=now - timedelta(minutes=30))
    store = _mock_store([old, new, mid])
    mock_get_svc.return_value = _mock_svc(store)

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    assert [r.task_id for r in result] == ["new", "mid", "old"]


@pytest.mark.asyncio
async def test_status_mapping_running(_patches: tuple[MagicMock, MagicMock]) -> None:
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = _mock_handler()

    task = _make_btw_task("t1", status=TaskStatus.RUNNING)
    store = _mock_store([task])
    mock_get_svc.return_value = _mock_svc(store)

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    assert result[0].status == "running"


@pytest.mark.asyncio
async def test_status_mapping_failed_timeout(_patches: tuple[MagicMock, MagicMock]) -> None:
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = _mock_handler()

    task = _make_btw_task("t1", status=TaskStatus.FAILED, error="Task timed out after 300s")
    store = _mock_store([task])
    mock_get_svc.return_value = _mock_svc(store)

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    assert result[0].status == "timed_out"


@pytest.mark.asyncio
async def test_status_mapping_failed_cancelled(_patches: tuple[MagicMock, MagicMock]) -> None:
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = _mock_handler()

    task = _make_btw_task("t1", status=TaskStatus.FAILED, error="Cancelled by user")
    store = _mock_store([task])
    mock_get_svc.return_value = _mock_svc(store)

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    assert result[0].status == "cancelled"


@pytest.mark.asyncio
async def test_voice_task_visible(_patches: tuple[MagicMock, MagicMock]) -> None:
    """Voice-spawned tasks must appear in the panel (the core bug fix)."""
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = _mock_handler()

    task = _make_voice_task("v1", chat_id="voice-chat-uuid")
    store = _mock_store([task])
    mock_get_svc.return_value = _mock_svc(store)

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    assert len(result) == 1
    assert result[0].task_id == "v1"
    assert result[0].chat_id == "voice-chat-uuid"


@pytest.mark.asyncio
async def test_kind_is_agent(_patches: tuple[MagicMock, MagicMock]) -> None:
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = _mock_handler()

    task = _make_btw_task("t1")
    store = _mock_store([task])
    mock_get_svc.return_value = _mock_svc(store)

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    assert result[0].kind == "agent"


@pytest.mark.asyncio
async def test_result_preview_truncated_to_100(_patches: tuple[MagicMock, MagicMock]) -> None:
    mock_get_handler, mock_get_svc = _patches
    mock_get_handler.return_value = _mock_handler()

    long_text = "A" * 200
    task = _make_btw_task("t1", status=TaskStatus.COMPLETED, completed_at=datetime.now(UTC))
    events = [
        TaskEvent(
            event_id=1,
            task_id="t1",
            kind=TaskEventKind.COMPLETED,
            payload={"result_preview": long_text},
        ),
    ]
    store = _mock_store([task], events)
    mock_get_svc.return_value = _mock_svc(store)

    from app.api.background_tasks.router import _list_agent_tasks

    result = await _list_agent_tasks()
    assert result[0].result_preview is not None
    assert len(result[0].result_preview) == 100
