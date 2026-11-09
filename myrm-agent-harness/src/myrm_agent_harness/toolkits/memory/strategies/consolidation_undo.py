"""Exact undo of the latest consolidation cycle: a write gateway that journals pre-images, and the one-slot journal.

[INPUT]
- memory.manager::MemoryManager (POS: unified memory manager facade)
- memory.types::{AnyMemory, EpisodicMemory, SemanticMemory} (POS: memory data models)
- strategies.bookkeeping::{delete_bookkeeping, read_bookkeeping, write_bookkeeping} (POS: Persistence of maintenance counters, hashes and timestamps)
- strategies.consolidation_models::{ConsolidationStats, PreImage, UndoJournal} (POS: Domain models of cross-session memory consolidation)

[OUTPUT]
- CycleWrites: the only way a cycle writes memories; it journals what each write is about to change
- UndoRecord, UndoSummary, UndoResult: the saved journal, what the settings card shows of it, and the outcome of undoing it
- save_undo: make a cycle's journal the one the user can undo
- get_undo_summary: describe the undoable cycle and how much of it the user has changed since
- undo_last_consolidation: restore the undoable cycle, once

[POS]
Consolidation merges, corrects and rewrites memories the user may want back. Reconstructing a change afterwards cannot
be exact, because the values it replaced are gone. So every write of a cycle passes through ``CycleWrites``, which notes
a memory's restorable fields just before the first write to it and the ids of the memories the cycle creates. The journal
holds numbers and names only: a rewritten memory carries its previous text in its own metadata. Only the latest cycle that
changed something can be undone, and only while it has not been replaced; a memory the user edited or deleted since is
left as the user made it, and so is a created one the user pinned.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel

from myrm_agent_harness.toolkits.memory.strategies.bookkeeping import (
    delete_bookkeeping,
    read_bookkeeping,
    write_bookkeeping,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import PreImage, UndoJournal
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, SemanticMemory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from myrm_agent_harness.toolkits.memory.manager import MemoryManager
    from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import ConsolidationStats
    from myrm_agent_harness.toolkits.memory.types import AnyMemory

logger = logging.getLogger(__name__)

_UNDO_KEY = "_system.last_consolidation_undo"
# ``update_memory`` keeps the text a rewrite replaced under this key; it is where an undo gets that text back.
_PREVIOUS_CONTENT_KEY = "previous_content"


class UndoRecord(UndoJournal):
    """A journal sealed at the end of its cycle: the one cycle the user can still undo."""

    cycle_id: str
    recorded_at: datetime
    merged: int
    corrected: int
    updated: int


class UndoSummary(BaseModel):
    """What the settings card shows of the undoable cycle; ``conflict_count`` memories were changed since."""

    cycle_id: str
    recorded_at: datetime
    merged: int
    corrected: int
    updated: int
    change_count: int
    conflict_count: int


class UndoResult(BaseModel):
    """Memories put back, memories left as the user made them, and memories that could not be put back."""

    rolled_back: int = 0
    skipped_conflict: int = 0
    errors: int = 0


class CycleWrites:
    """Every memory write of one cycle goes through here, so no branch can forget to record what it changes.

    The writes refuse user-protected memories, as every automated write must.
    """

    def __init__(self, manager: MemoryManager, journal: UndoJournal) -> None:
        self._manager = manager
        self._journal = journal

    @asynccontextmanager
    async def _touching(self, memory_id: str, *, rewrites: bool = False) -> AsyncIterator[AnyMemory | None]:
        """Note the memory's pre-image before the write in the block; a write that fails leaves no entry."""
        memory = await self._manager.get_memory(memory_id)
        fresh = False
        # Only semantic and episodic memories can be rewritten; the write itself fails for any other type.
        if isinstance(memory, SemanticMemory | EpisodicMemory) and memory_id not in self._journal.touched:
            self._journal.touched[memory_id] = PreImage(
                importance=memory.importance,
                confidence=memory.confidence if isinstance(memory, SemanticMemory) else None,
                status=memory.status,
                metadata_keys=sorted(memory.metadata),
                content_edited=rewrites,
            )
            fresh = True
        try:
            yield memory
        except Exception:
            if fresh:
                del self._journal.touched[memory_id]
            raise

    async def update_memory(
        self,
        memory_id: str,
        *,
        importance: float | None = None,
        confidence: float | None = None,
        content: str | None = None,
        metadata_patch: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        """Update fields in place; ``metadata_patch`` adds keys to the metadata instead of replacing it."""
        async with self._touching(memory_id, rewrites=content is not None) as memory:
            metadata = {**memory.metadata, **metadata_patch} if memory is not None and metadata_patch else None
            await self._manager.update_memory(
                memory_id,
                importance=importance,
                confidence=confidence,
                content=content,
                metadata=metadata,
                allow_protected=False,
            )

    async def correct_memory(self, memory_id: str, corrected_content: str) -> None:
        """Store the correction as a new memory and demote the original."""
        async with self._touching(memory_id):
            correction = await self._manager.correct_memory(memory_id, corrected_content, allow_protected=False)
        self._journal.created.append(correction.id)

    async def store(self, memory: SemanticMemory) -> None:
        """Store a memory the cycle creates; undoing the cycle deletes it."""
        stored = await self._manager.store(memory, _bypass_approval=True)
        # A write that hands back an existing memory (deduplication) created nothing, so there is nothing to delete.
        if stored.id == memory.id:
            self._journal.created.append(stored.id)


async def save_undo(manager: MemoryManager, stats: ConsolidationStats) -> None:
    """Make the cycle ``stats`` describes the one the user can undo, replacing the previous one.

    A cycle that changed nothing leaves the slot alone, so a quiet run does not take away the undo of an earlier real one.
    """
    if not stats.undo.change_count or not manager.has_relational:
        return
    record = UndoRecord(
        created=stats.undo.created,
        touched=stats.undo.touched,
        cycle_id=uuid4().hex,
        recorded_at=datetime.now(UTC),
        merged=stats.merged,
        corrected=stats.corrected,
        updated=stats.updated,
    )
    try:
        await write_bookkeeping(manager, _UNDO_KEY, record.model_dump_json())
    except Exception as exc:
        logger.warning("Failed to save the consolidation undo journal: %s", exc)


async def _load_undo(manager: MemoryManager) -> UndoRecord | None:
    """The undoable cycle, or ``None`` when there is none or its journal cannot be read."""
    if not manager.has_relational:
        return None
    raw = await read_bookkeeping(manager, _UNDO_KEY)
    if not raw:
        return None
    try:
        return UndoRecord.model_validate_json(raw)
    except ValueError:
        logger.warning("Consolidation undo journal cannot be read; ignored")
        return None


@dataclass(frozen=True, slots=True)
class _Plan:
    """What of a record can still be undone, and how many of its memories the user has changed or removed since."""

    delete: list[str]
    restore: list[tuple[AnyMemory, PreImage]]
    skipped: int


async def _plan(manager: MemoryManager, record: UndoRecord) -> _Plan:
    """Undoing a memory the user edited since would overwrite that edit, so such memories are left alone."""

    async def unchanged(memory_id: str) -> AnyMemory | None:
        memory = await manager.get_memory(memory_id)
        return memory if memory is not None and memory.updated_at <= record.recorded_at else None

    delete: list[str] = []
    restore: list[tuple[AnyMemory, PreImage]] = []
    skipped = 0
    for memory_id in record.created:
        if await unchanged(memory_id) is None:
            skipped += 1
        else:
            delete.append(memory_id)
    for memory_id, pre in record.touched.items():
        memory = await unchanged(memory_id)
        if memory is None:
            skipped += 1
        else:
            restore.append((memory, pre))
    return _Plan(delete, restore, skipped)


async def get_undo_summary(manager: MemoryManager) -> UndoSummary | None:
    """The undoable cycle as the settings card shows it, or ``None`` when there is nothing to undo."""
    record = await _load_undo(manager)
    if record is None:
        return None
    plan = await _plan(manager, record)
    return UndoSummary(
        cycle_id=record.cycle_id,
        recorded_at=record.recorded_at,
        merged=record.merged,
        corrected=record.corrected,
        updated=record.updated,
        change_count=record.change_count,
        conflict_count=plan.skipped,
    )


async def _restore(manager: MemoryManager, memory: AnyMemory, pre: PreImage) -> None:
    """Put one memory back as the cycle found it: the keys the cycle (or a later archive) added are dropped."""
    metadata = {key: value for key, value in memory.metadata.items() if key in pre.metadata_keys}
    content = None
    if pre.content_edited:
        content = str(memory.metadata[_PREVIOUS_CONTENT_KEY])
        metadata.pop(_PREVIOUS_CONTENT_KEY, None)
    await manager.update_memory(
        memory.id,
        importance=pre.importance,
        confidence=pre.confidence,
        status=pre.status,
        content=content,
        metadata=metadata,
    )


async def undo_last_consolidation(manager: MemoryManager, cycle_id: str) -> UndoResult | None:
    """Undo the saved cycle when it is ``cycle_id``; ``None`` when that cycle is no longer the saved one.

    The slot is consumed whatever the outcome, so one click is never replayed over memories it already restored; a newer
    cycle that saved its own journal while this undo ran keeps the slot.
    """
    record = await _load_undo(manager)
    if record is None or record.cycle_id != cycle_id:
        return None
    plan = await _plan(manager, record)
    result = UndoResult(skipped_conflict=plan.skipped)
    for memory_id in plan.delete:
        try:
            deleted = await manager.delete_memory(
                manager.config.semantic_collection, [memory_id], allow_protected=False
            )
        except Exception as exc:
            logger.warning("Consolidation undo failed to delete %s: %s: %s", memory_id, type(exc).__name__, exc)
            result.errors += 1
            continue
        if deleted:
            result.rolled_back += 1
        else:
            result.skipped_conflict += 1
    for memory, pre in plan.restore:
        try:
            await _restore(manager, memory, pre)
        except Exception as exc:
            logger.warning("Consolidation undo failed to restore %s: %s: %s", memory.id, type(exc).__name__, exc)
            result.errors += 1
        else:
            result.rolled_back += 1
    current = await _load_undo(manager)
    if current is not None and current.cycle_id == record.cycle_id:
        await delete_bookkeeping(manager, _UNDO_KEY)
    return result


__all__ = [
    "CycleWrites",
    "UndoRecord",
    "UndoResult",
    "UndoSummary",
    "get_undo_summary",
    "save_undo",
    "undo_last_consolidation",
]
