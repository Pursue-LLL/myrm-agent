"""Integration: _list_agent_tasks() → real KanbanService + SQLite (no mocks on query path).

Validates the full pipeline:
  POST seed task → KanbanService.store → _list_agent_tasks() → REST response

Covers the core bug fix: voice-spawned tasks are visible in the WebUI panel,
alongside btw-spawned tasks. Non-persistent tasks are correctly filtered.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.kanban.types import TaskPriority, TaskStatus

from app.core.channel_bridge.background_task_handler import (
    ChannelBackgroundTaskHandler,
    _SYSTEM_BOARD_NAME,
)
from app.core.channel_bridge.persistent_background import (
    BACKGROUND_SOURCE_BTW,
    BACKGROUND_SOURCE_VOICE,
)


def _build_app():
    from fastapi import FastAPI

    from app.api.background_tasks.router import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/background-tasks")
    return app


@pytest.fixture
def _handler():
    """Provide a real ChannelBackgroundTaskHandler and ensure singleton cleanup."""
    import app.core.channel_bridge.setup as setup_mod

    handler = ChannelBackgroundTaskHandler()
    old = setup_mod._background_task_handler
    setup_mod._background_task_handler = handler
    yield handler
    setup_mod._background_task_handler = old


@pytest.fixture
async def _board_id(_handler: ChannelBackgroundTaskHandler) -> str:
    return await _handler._ensure_system_board()


async def _seed_kanban_task(
    board_id: str,
    *,
    title: str,
    background_source: str,
    chat_id: str | None = None,
    status: TaskStatus = TaskStatus.READY,
) -> str:
    from app.services.kanban import KanbanService

    svc = KanbanService.get_instance()
    task = await svc.add_task(
        board_id=board_id,
        title=title,
        description=f"Integration test: {title}",
        priority=TaskPriority.NORMAL,
        initial_status=status,
    )
    task.metadata = task.metadata or {}
    task.metadata["background_source"] = background_source
    if chat_id:
        task.metadata["chat_id"] = chat_id
    await svc.store.save_task(task)
    return task.task_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_shows_btw_and_voice_tasks(
    _handler: ChannelBackgroundTaskHandler,
    _board_id: str,
) -> None:
    """Both btw and voice background tasks appear in the panel list."""
    btw_id = await _seed_kanban_task(
        _board_id,
        title="BTW research",
        background_source=BACKGROUND_SOURCE_BTW,
        chat_id="chat-btw-111",
    )
    voice_id = await _seed_kanban_task(
        _board_id,
        title="Voice lookup",
        background_source=BACKGROUND_SOURCE_VOICE,
        chat_id="chat-voice-222",
    )

    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/background-tasks")
        assert resp.status_code == 200
        data = resp.json()
        tasks = data["tasks"]

    task_ids = {t["task_id"] for t in tasks if t["kind"] == "agent"}
    assert btw_id in task_ids, f"btw task {btw_id} missing from panel"
    assert voice_id in task_ids, f"voice task {voice_id} missing from panel"

    btw_row = next(t for t in tasks if t["task_id"] == btw_id)
    assert btw_row["chat_id"] == "chat-btw-111"

    voice_row = next(t for t in tasks if t["task_id"] == voice_id)
    assert voice_row["chat_id"] == "chat-voice-222"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_filters_non_persistent_tasks(
    _handler: ChannelBackgroundTaskHandler,
    _board_id: str,
) -> None:
    """Tasks without background_source metadata are excluded from the panel."""
    from app.services.kanban import KanbanService

    svc = KanbanService.get_instance()
    non_bg = await svc.add_task(
        board_id=_board_id,
        title="Regular kanban task",
        description="Not a background task",
        priority=TaskPriority.NORMAL,
        initial_status=TaskStatus.READY,
    )
    non_bg.metadata = {"some_key": "some_value"}
    await svc.store.save_task(non_bg)

    btw_id = await _seed_kanban_task(
        _board_id,
        title="Real background",
        background_source=BACKGROUND_SOURCE_BTW,
    )

    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/background-tasks")
        assert resp.status_code == 200
        data = resp.json()
        tasks = data["tasks"]

    agent_ids = {t["task_id"] for t in tasks if t["kind"] == "agent"}
    assert btw_id in agent_ids
    assert non_bg.task_id not in agent_ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_board_settings_max_concurrent(
    _handler: ChannelBackgroundTaskHandler,
    _board_id: str,
) -> None:
    """System board max_concurrent_tasks matches handler constant."""
    from app.core.channel_bridge.background_task_handler import MAX_CONCURRENT_TASKS
    from app.services.kanban import KanbanService

    svc = KanbanService.get_instance()
    boards = await svc.list_boards()
    sys_board = next(b for b in boards if b.name == _SYSTEM_BOARD_NAME)

    assert sys_board.settings is not None
    assert sys_board.settings.max_concurrent_tasks == MAX_CONCURRENT_TASKS


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_task_status_maps_to_timed_out(
    _handler: ChannelBackgroundTaskHandler,
    _board_id: str,
) -> None:
    """FAILED task with 'timed out' error maps to 'timed_out' status in panel."""
    task_id = await _seed_kanban_task(
        _board_id,
        title="Timed out task",
        background_source=BACKGROUND_SOURCE_BTW,
        status=TaskStatus.READY,
    )
    from app.services.kanban import KanbanService

    svc = KanbanService.get_instance()
    task = await svc.store.get_task(task_id)
    assert task is not None
    task.status = TaskStatus.FAILED
    task.error = "Task timed out after 300s"
    await svc.store.save_task(task)

    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/background-tasks")
        assert resp.status_code == 200
        data = resp.json()

    row = next(t for t in data["tasks"] if t["task_id"] == task_id)
    assert row["status"] == "timed_out"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_completed_task_without_events_has_no_preview(
    _handler: ChannelBackgroundTaskHandler,
    _board_id: str,
) -> None:
    """COMPLETED task without result_preview events returns null preview."""
    task_id = await _seed_kanban_task(
        _board_id,
        title="Quick completed",
        background_source=BACKGROUND_SOURCE_VOICE,
        status=TaskStatus.READY,
    )
    from app.services.kanban import KanbanService

    svc = KanbanService.get_instance()
    task = await svc.store.get_task(task_id)
    assert task is not None
    task.status = TaskStatus.COMPLETED
    await svc.store.save_task(task)

    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/background-tasks")
        assert resp.status_code == 200
        data = resp.json()

    row = next(t for t in data["tasks"] if t["task_id"] == task_id)
    assert row["status"] == "completed"
    assert row["result_preview"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_agent_task_via_rest(
    _handler: ChannelBackgroundTaskHandler,
    _board_id: str,
) -> None:
    """Cancel an agent task via REST API — verifies handler integration."""
    from app.channels.types import InboundMessage

    msg = InboundMessage(
        channel="webui",
        sender_id="test-user",
        chat_id="chat-cancel-test",
        content="",
        user_id="test-user",
    )
    task_id = await _handler.spawn_background(msg, "Long research task")

    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(f"/api/v1/background-tasks/{task_id}/cancel")
        assert resp.status_code == 200
        result = resp.json()
        assert result["message"] == "Background task cancelled"

        list_resp = await client.get("/api/v1/background-tasks")
        assert list_resp.status_code == 200
        tasks = list_resp.json()["tasks"]
        row = next((t for t in tasks if t["task_id"] == task_id), None)
        assert row is not None
        assert row["status"] == "cancelled"
