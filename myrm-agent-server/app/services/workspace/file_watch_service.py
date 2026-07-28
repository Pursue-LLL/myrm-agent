"""Workspace directory file watcher — publishes SSE events on vault changes.

[INPUT]
- watchdog.observers::Observer (POS: cross-platform recursive directory watch)
- myrm_agent_harness.agent.security.path_security::is_dangerous_path
- app.services.event.app_event_bus::get_event_bus, AppEvent, AppEventType

[OUTPUT]
- WorkspaceFileWatchService: refcounted watchdog per resolved workspace path
- get_workspace_file_watch_service: process singleton accessor

[POS]
Server-side workspace vault change detection for Web/SaaS file browser auto-refresh.
Clients register interest via POST /files/browse/watch; changes emit WORKSPACE_FILE_CHANGED SSE.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Callable
from typing import Final

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import ObservedWatch

from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS: Final[float] = 0.8
_MAX_WATCHED_PATHS: Final[int] = 32
_EPHEMERAL_SUFFIXES: Final[tuple[str, ...]] = (".swp", ".tmp", "~")


_IGNORED_DIR_NAMES: Final[frozenset[str]] = frozenset(
    {
        "node_modules",
        ".git",
        ".next",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".cache",
        ".DS_Store",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "egg-info",
        ".eggs",
    }
)


def _path_has_ignored_dir_component(path: str) -> bool:
    return any(part in _IGNORED_DIR_NAMES for part in os.path.normpath(path).split(os.sep))


def resolve_watchable_workspace_path(raw: str) -> str:
    """Expand, validate, and canonicalize a workspace path for watching."""
    from myrm_agent_harness.agent.security.path_security import is_dangerous_path

    trimmed = raw.strip()
    if not trimmed:
        raise ValueError("workspace path is required")

    resolved = os.path.realpath(os.path.expanduser(trimmed))
    if is_dangerous_path(resolved):
        raise ValueError(f"Access denied for path: {raw}")
    if not os.path.isdir(resolved):
        raise ValueError(f"Path is not a directory: {raw}")
    return resolved


class _DebouncedWorkspaceHandler(FileSystemEventHandler):
    def __init__(self, workspace_path: str, schedule_emit: Callable[[str], None]) -> None:
        super().__init__()
        self._workspace_path = workspace_path
        self._schedule_emit = schedule_emit

    def on_any_event(self, event: FileSystemEvent) -> None:
        src_path = event.src_path
        if any(src_path.endswith(suffix) for suffix in _EPHEMERAL_SUFFIXES):
            return
        if _path_has_ignored_dir_component(src_path):
            return
        self._schedule_emit(self._workspace_path)


class WorkspaceFileWatchService:
    """Reference-counted watchdog observer keyed by resolved workspace path."""

    def __init__(self, *, debounce_seconds: float = _DEBOUNCE_SECONDS) -> None:
        self._debounce_seconds = debounce_seconds
        self._async_lock = asyncio.Lock()
        self._thread_lock = threading.Lock()
        self._refs: dict[str, int] = {}
        self._observer: Observer | None = None
        self._watches: dict[str, ObservedWatch] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._debounce_tasks: dict[str, asyncio.Task[None]] = {}

    async def acquire(self, workspace_path: str) -> None:
        resolved = resolve_watchable_workspace_path(workspace_path)
        async with self._async_lock:
            self._loop = asyncio.get_running_loop()
            count = self._refs.get(resolved, 0)
            if count == 0 and len(self._refs) >= _MAX_WATCHED_PATHS:
                raise RuntimeError("Too many active workspace watches")
            self._refs[resolved] = count + 1
            if count == 0:
                await asyncio.to_thread(self._start_watch, resolved)

    async def release(self, workspace_path: str) -> None:
        resolved = resolve_watchable_workspace_path(workspace_path)
        async with self._async_lock:
            count = self._refs.get(resolved, 0)
            if count <= 0:
                return
            next_count = count - 1
            if next_count == 0:
                self._refs.pop(resolved, None)
                await asyncio.to_thread(self._stop_watch, resolved)
                self._cancel_debounce(resolved)
            else:
                self._refs[resolved] = next_count

    async def release_all(self) -> None:
        async with self._async_lock:
            paths = list(self._refs.keys())
            self._refs.clear()
            for path in paths:
                await asyncio.to_thread(self._stop_watch, path)
                self._cancel_debounce(path)

    def _start_watch(self, workspace_path: str) -> None:
        with self._thread_lock:
            observer = self._observer
            if observer is None:
                observer = Observer()
                observer.start()
                self._observer = observer

            if workspace_path in self._watches:
                return

            handler = _DebouncedWorkspaceHandler(workspace_path, self._schedule_emit)
            watch = observer.schedule(handler, workspace_path, recursive=True)
            self._watches[workspace_path] = watch
            logger.info("Started workspace file watch: %s", workspace_path)

    def _stop_watch(self, workspace_path: str) -> None:
        with self._thread_lock:
            watch = self._watches.pop(workspace_path, None)
            observer = self._observer
            if watch is None or observer is None:
                return
            observer.unschedule(watch)
            logger.info("Stopped workspace file watch: %s", workspace_path)
            if not self._watches:
                observer.stop()
                observer.join(timeout=5)
                self._observer = None

    def _schedule_emit(self, workspace_path: str) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(lambda: asyncio.create_task(self._debounce_emit(workspace_path)))

    async def _debounce_emit(self, workspace_path: str) -> None:
        self._cancel_debounce(workspace_path)

        async def _wait_and_emit() -> None:
            await asyncio.sleep(self._debounce_seconds)
            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.WORKSPACE_FILE_CHANGED,
                    data={"workspace_path": workspace_path},
                )
            )

        self._debounce_tasks[workspace_path] = asyncio.create_task(_wait_and_emit())

    def _cancel_debounce(self, workspace_path: str) -> None:
        task = self._debounce_tasks.pop(workspace_path, None)
        if task is not None and not task.done():
            task.cancel()


_service: WorkspaceFileWatchService | None = None


def get_workspace_file_watch_service() -> WorkspaceFileWatchService:
    global _service  # noqa: PLW0603
    if _service is None:
        _service = WorkspaceFileWatchService()
    return _service
