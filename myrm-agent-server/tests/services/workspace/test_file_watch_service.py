"""Tests for workspace file watch service."""

from __future__ import annotations

import asyncio
import os

import pytest

from app.services.event.app_event_bus import AppEventType, get_event_bus
from app.services.workspace import file_watch_service as fws_module
from app.services.workspace.file_watch_service import WorkspaceFileWatchService


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def watch_service():
    service = WorkspaceFileWatchService(debounce_seconds=0.05)
    fws_module._service = service
    try:
        yield service
    finally:
        await service.release_all()
        fws_module._service = None


@pytest.mark.anyio
async def test_acquire_emits_workspace_file_changed(watch_service: WorkspaceFileWatchService, tmp_path):
    workspace = str(tmp_path)
    queue = get_event_bus().subscribe()

    await watch_service.acquire(workspace)
    (tmp_path / "new.txt").write_text("hello", encoding="utf-8")

    event = await asyncio.wait_for(queue.get(), timeout=3.0)
    assert event.event_type == AppEventType.WORKSPACE_FILE_CHANGED
    assert event.data["workspace_path"] == os.path.realpath(workspace)

    get_event_bus().unsubscribe(queue)
    await watch_service.release(workspace)


@pytest.mark.anyio
async def test_release_stops_emitting(watch_service: WorkspaceFileWatchService, tmp_path):
    workspace = str(tmp_path)
    queue = get_event_bus().subscribe()

    await watch_service.acquire(workspace)
    while not queue.empty():
        queue.get_nowait()
    await watch_service.release(workspace)
    await asyncio.sleep(0.2)
    (tmp_path / "after_release.txt").write_text("noop", encoding="utf-8")

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.3)

    get_event_bus().unsubscribe(queue)


@pytest.mark.anyio
async def test_refcount_requires_multiple_release(watch_service: WorkspaceFileWatchService, tmp_path):
    workspace = str(tmp_path)
    queue = get_event_bus().subscribe()

    await watch_service.acquire(workspace)
    await watch_service.acquire(workspace)
    await watch_service.release(workspace)

    (tmp_path / "still_watched.txt").write_text("x", encoding="utf-8")
    event = await asyncio.wait_for(queue.get(), timeout=3.0)
    assert event.event_type == AppEventType.WORKSPACE_FILE_CHANGED

    await watch_service.release(workspace)
    get_event_bus().unsubscribe(queue)
