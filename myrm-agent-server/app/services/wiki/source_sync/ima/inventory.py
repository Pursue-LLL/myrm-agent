"""Resumable inventory of the selected libraries and notes into the ledger.

[INPUT]
- .context::SyncContext (POS: client, ledger, resumable state, time budget)
- .identity (POS: stable item keys)

[OUTPUT]
- begin_generation / run_inventory

[POS]
Breadth-first walk of each library's folder tree (persisted queue) followed by the notes lane. Each complete
pass is a *generation*: rows a finished pass did not see are marked ``remote_deleted``, but only for containers
whose walk finished cleanly. The mark means "no longer listed under that library, folder and title": a rename or
a move reads like a deletion, and the file then arrives as a new row. Transient / rate-limit / auth failures
propagate so the slice stops with its cursor intact; a permanent failure only drops the affected container.
"""

from __future__ import annotations

import logging

from app.database.connection import get_session

from .client import NOTES_PAGE_LIMIT
from .context import SyncContext
from .errors import ImaAuthError, ImaPermanentError
from .identity import NOTES_LANE, kb_item_key, note_item_key
from .ledger import InventoryItem
from .models import MEDIA_NOTE, ImaEntry
from .state import ImaWalkTask

logger = logging.getLogger(__name__)

_MAX_FOLDER_DEPTH = 16
_MAX_INVENTORY_PAGES = 50_000
_MAX_NOTES = 20_000


async def begin_generation(ctx: SyncContext) -> None:
    state = ctx.state
    state.generation += 1
    state.phase = "inventory"
    state.queue = [ImaWalkTask(kb_id=kb.id, kb_name=kb.name) for kb in ctx.config.knowledge_bases]
    state.notes_start = 0 if ctx.config.include_notes else None
    state.failed_containers = []
    state.inventory_pages = 0
    state.generation_published = 0
    state.last_error_kind = ""


async def _record(ctx: SyncContext, items: list[InventoryItem]) -> None:
    async with get_session() as db:
        await ctx.ledger.upsert_inventory(db, items, generation=ctx.state.generation, raw_exists=ctx.raw_exists)
        await db.commit()


def _mark_container_failed(ctx: SyncContext, container_id: str) -> None:
    if container_id not in ctx.state.failed_containers:
        ctx.state.failed_containers.append(container_id)


def _drop_library(ctx: SyncContext, kb_id: str, *, kind: str) -> None:
    ctx.state.queue = [task for task in ctx.state.queue if task.kb_id != kb_id]
    _mark_container_failed(ctx, kb_id)
    ctx.state.last_error_kind = kind


def _kb_item(task: ImaWalkTask, entry: ImaEntry) -> InventoryItem:
    parent_id = entry.parent_folder_id or task.folder_id
    return InventoryItem(
        item_key=kb_item_key(task.kb_id, parent_id, entry.title),
        fallback_key=kb_item_key(task.kb_id, parent_id, entry.title, media_id=entry.media_id),
        container_id=task.kb_id,
        container_name=task.kb_name,
        remote_id=entry.media_id,
        title=entry.title,
        folder_path="/".join(task.folder_path),
        media_type=entry.media_type,
        remote_version=entry.media_id,
    )


async def _walk_libraries(ctx: SyncContext) -> None:
    state = ctx.state
    while state.queue and ctx.time_left() > 0:
        task = state.queue[0]
        try:
            page = await ctx.client.list_knowledge_page(task.kb_id, folder_id=task.folder_id, cursor=task.cursor)
        except ImaPermanentError as exc:
            logger.warning("ima library %s could not be listed: %s", task.kb_id, exc)
            _drop_library(ctx, task.kb_id, kind=exc.kind)
            continue

        await _record(ctx, [_kb_item(task, entry) for entry in page.items])
        state.inventory_pages += 1
        if state.inventory_pages > _MAX_INVENTORY_PAGES:
            logger.warning("ima inventory exceeded %d pages; stopping the walk", _MAX_INVENTORY_PAGES)
            for kb in ctx.config.knowledge_bases:
                _mark_container_failed(ctx, kb.id)
            state.queue = []
            break

        for folder in page.folders:
            if len(task.folder_path) >= _MAX_FOLDER_DEPTH:
                _mark_container_failed(ctx, task.kb_id)
                continue
            state.queue.append(
                ImaWalkTask(
                    kb_id=task.kb_id,
                    kb_name=task.kb_name,
                    folder_id=folder.folder_id,
                    folder_path=[*task.folder_path, folder.name],
                )
            )
        if page.is_end or not page.next_cursor or page.next_cursor == task.cursor:
            state.queue.pop(0)
        else:
            state.queue[0] = task.model_copy(update={"cursor": page.next_cursor})
        await ctx.persist_state()


async def _walk_notes(ctx: SyncContext) -> None:
    state = ctx.state
    while state.notes_start is not None and ctx.time_left() > 0:
        start = state.notes_start
        try:
            page = await ctx.client.list_notes_page(start=start)
        except ImaAuthError:
            # The key already listed libraries, so a rejection here means it lacks the notes permission.
            logger.warning("ima notes lane skipped: the API key has no notes permission")
            state.notes_start = None
            _mark_container_failed(ctx, NOTES_LANE)
            break
        except ImaPermanentError as exc:
            logger.warning("ima notes lane skipped: %s", exc)
            state.notes_start = None
            _mark_container_failed(ctx, NOTES_LANE)
            break

        await _record(
            ctx,
            [
                InventoryItem(
                    item_key=note_item_key(note.note_id),
                    container_id=NOTES_LANE,
                    container_name=NOTES_LANE,
                    remote_id=note.note_id,
                    title=note.title,
                    folder_path=note.folder_name,
                    media_type=MEDIA_NOTE,
                    remote_version=str(note.modify_time),
                )
                for note in page.notes
            ],
        )
        state.inventory_pages += 1
        finished = page.is_end or not page.notes or start + NOTES_PAGE_LIMIT >= _MAX_NOTES
        state.notes_start = None if finished else start + NOTES_PAGE_LIMIT
        await ctx.persist_state()


async def _finish(ctx: SyncContext) -> None:
    complete = [container for container in ctx.config.containers if container not in ctx.state.failed_containers]
    async with get_session() as db:
        await ctx.ledger.mark_remote_deleted(db, generation=ctx.state.generation, container_ids=complete)
        await db.commit()
    ctx.state.phase = "fetch"
    await ctx.persist_state(force=True)


async def run_inventory(ctx: SyncContext) -> None:
    """Advance the walk until it finishes or the time budget runs out; finishing flips the phase to ``fetch``."""
    await _walk_libraries(ctx)
    if not ctx.state.queue:
        await _walk_notes(ctx)
    if not ctx.state.queue and ctx.state.notes_start is None:
        await _finish(ctx)
