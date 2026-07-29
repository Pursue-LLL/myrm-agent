"""SSE events for wiki ingest queue and compile circuit visibility.

[INPUT]
- app.services.wiki.memory_to_wiki::MemoryToWikiArchiver (POS: Memory→Wiki automatic archiving service)

[OUTPUT]
- wiki_ingest_event_bus: broadcast hub for scoped ingest snapshots
- build_wiki_ingest_snapshot: queue stats + compile_run DTO for SSE payloads
- publish_wiki_ingest_snapshot: push snapshot to subscribers for an agent scope
- prepare_snapshot: invalidates structural lint stats cache when vault tree fingerprint changes

[POS]
Server-side real-time wiki ingest visibility. Decouples compile worker progress from Settings polling; tree fingerprint changes drop `/wiki/stats` structural lint TTL cache.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)

ScopeKey = str


def normalize_agent_scope_key(agent_id: str | None) -> ScopeKey:
    return agent_id or "__default__"


def build_wiki_tree_fingerprint(archiver: MemoryToWikiArchiver) -> str:
    from myrm_agent_harness.toolkits.wiki.maintenance.stale_summary import (
        collect_stale_raw_files,
        collect_stale_raw_path_set,
    )

    summary = collect_stale_raw_files(archiver._structure)
    stale_paths = collect_stale_raw_path_set(archiver._structure)
    stats = archiver._queue.get_stats()
    payload = {
        "completed": stats.get("completed", 0),
        "failed": stats.get("failed", 0),
        "last_compile_time": summary.last_compile_time,
        "processing": stats.get("processing", 0),
        "stale_count": len(stale_paths),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def build_wiki_ingest_snapshot(
    archiver: MemoryToWikiArchiver,
    *,
    agent_id: str | None,
    tree_sync_required: bool = False,
) -> dict[str, object]:
    stats = archiver._queue.get_stats()
    compile_run = archiver._queue.get_compile_run()
    snapshot: dict[str, object] = {
        "agent_id": agent_id,
        "stats": stats,
        "compile_run": {
            "state": compile_run.state,
            "pause_reason": compile_run.pause_reason,
            "primary_error_kind": compile_run.primary_error_kind,
        },
    }
    if tree_sync_required:
        snapshot["tree_sync_required"] = True
    return snapshot


def _snapshot_fingerprint(snapshot: dict[str, object]) -> str:
    return json.dumps(snapshot, sort_keys=True, separators=(",", ":"))


@dataclass
class _ScopePollState:
    refs: int = 0
    poll_stop: asyncio.Event = field(default_factory=asyncio.Event)
    poll_task: asyncio.Task[None] | None = None
    archiver: MemoryToWikiArchiver | None = None
    agent_id: str | None = None


class WikiIngestEventBus:
    """Broadcast wiki ingest snapshots to SSE subscribers keyed by agent scope."""

    def __init__(
        self,
        *,
        poll_interval_seconds: float = 5.0,
    ) -> None:
        self._subscribers: dict[ScopeKey, set[asyncio.Queue[dict[str, object]]]] = {}
        self._scope_polls: dict[ScopeKey, _ScopePollState] = {}
        self._poll_interval_seconds = max(poll_interval_seconds, 1.0)
        self._last_fingerprint: dict[ScopeKey, str] = {}
        self._last_tree_fingerprint: dict[ScopeKey, str] = {}

    def subscribe(self, scope_key: ScopeKey) -> asyncio.Queue[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=32)
        self._subscribers.setdefault(scope_key, set()).add(queue)
        return queue

    def unsubscribe(self, scope_key: ScopeKey, queue: asyncio.Queue[dict[str, object]]) -> None:
        scope_subscribers = self._subscribers.get(scope_key)
        if not scope_subscribers:
            return
        scope_subscribers.discard(queue)
        if not scope_subscribers:
            self._subscribers.pop(scope_key, None)
            self._last_fingerprint.pop(scope_key, None)
            self._last_tree_fingerprint.pop(scope_key, None)

    def prepare_snapshot(
        self,
        scope_key: ScopeKey,
        archiver: MemoryToWikiArchiver,
        agent_id: str | None,
    ) -> dict[str, object]:
        tree_fingerprint = build_wiki_tree_fingerprint(archiver)
        previous_tree_fingerprint = self._last_tree_fingerprint.get(scope_key)
        tree_sync_required = (
            previous_tree_fingerprint is not None and tree_fingerprint != previous_tree_fingerprint
        )
        self._last_tree_fingerprint[scope_key] = tree_fingerprint
        if tree_sync_required:
            from app.services.wiki.structural_stats_cache import invalidate_structural_lint_cache

            invalidate_structural_lint_cache(archiver._structure)
        return build_wiki_ingest_snapshot(
            archiver,
            agent_id=agent_id,
            tree_sync_required=tree_sync_required,
        )

    async def emit(self, scope_key: ScopeKey, snapshot: dict[str, object]) -> None:
        try:
            fingerprint = _snapshot_fingerprint(snapshot)
        except TypeError as exc:
            logger.warning("Failed to fingerprint wiki ingest snapshot: %s", exc)
            return

        if self._last_fingerprint.get(scope_key) == fingerprint:
            return
        self._last_fingerprint[scope_key] = fingerprint

        subscribers = list(self._subscribers.get(scope_key, ()))
        if not subscribers:
            return

        dead: list[asyncio.Queue[dict[str, object]]] = []
        for queue in subscribers:
            try:
                queue.put_nowait(snapshot)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    overflow = dict(snapshot)
                    overflow["sync_required"] = True
                    queue.put_nowait(overflow)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    dead.append(queue)
            except Exception as exc:
                logger.error("Failed to emit wiki ingest snapshot: %s", exc)
                dead.append(queue)

        for queue in dead:
            self.unsubscribe(scope_key, queue)

    def _acquire_scope_poll(
        self,
        scope_key: ScopeKey,
        archiver: MemoryToWikiArchiver,
        agent_id: str | None,
    ) -> None:
        state = self._scope_polls.get(scope_key)
        if state is None:
            state = _ScopePollState()
            self._scope_polls[scope_key] = state
        state.refs += 1
        if state.refs == 1:
            state.archiver = archiver
            state.agent_id = agent_id
            state.poll_stop = asyncio.Event()
            state.poll_task = asyncio.create_task(self._scope_poll_loop(scope_key, state))

    async def _release_scope_poll(self, scope_key: ScopeKey) -> None:
        state = self._scope_polls.get(scope_key)
        if state is None:
            return
        state.refs -= 1
        if state.refs > 0:
            return
        state.poll_stop.set()
        if state.poll_task is not None:
            state.poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await state.poll_task
        self._scope_polls.pop(scope_key, None)

    async def _scope_poll_loop(self, scope_key: ScopeKey, state: _ScopePollState) -> None:
        while not state.poll_stop.is_set():
            archiver = state.archiver
            if archiver is not None:
                snapshot = self.prepare_snapshot(scope_key, archiver, state.agent_id)
                await self.emit(scope_key, snapshot)
            try:
                await asyncio.wait_for(state.poll_stop.wait(), timeout=self._poll_interval_seconds)
            except TimeoutError:
                continue

    async def stream_scope(
        self,
        scope_key: ScopeKey,
        archiver: MemoryToWikiArchiver,
        agent_id: str | None,
    ) -> AsyncGenerator[str, None]:
        queue = self.subscribe(scope_key)
        self._acquire_scope_poll(scope_key, archiver, agent_id)
        initial = self.prepare_snapshot(scope_key, archiver, agent_id)
        await self.emit(scope_key, initial)
        try:
            while True:
                event = await queue.get()
                yield f"event: ingest_snapshot\ndata: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await self._release_scope_poll(scope_key)
            self.unsubscribe(scope_key, queue)


wiki_ingest_event_bus = WikiIngestEventBus()


async def publish_wiki_ingest_snapshot(
    archiver: MemoryToWikiArchiver,
    *,
    agent_id: str | None,
) -> None:
    try:
        scope_key = normalize_agent_scope_key(agent_id)
        snapshot = wiki_ingest_event_bus.prepare_snapshot(scope_key, archiver, agent_id)
        await wiki_ingest_event_bus.emit(scope_key, snapshot)
    except Exception as exc:
        logger.warning("Failed to publish wiki ingest snapshot: %s", exc)


__all__ = [
    "WikiIngestEventBus",
    "build_wiki_ingest_snapshot",
    "build_wiki_tree_fingerprint",
    "normalize_agent_scope_key",
    "publish_wiki_ingest_snapshot",
    "wiki_ingest_event_bus",
]
