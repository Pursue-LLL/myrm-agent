"""Oldest-first window of memories a consolidation run has not covered yet.

[INPUT]
- memory._internal.storage::doc_to_episodic, doc_to_semantic (POS: Vector document to memory converters)
- memory._internal.store_stamp::{STORED_TS_KEY, stored_at_from_metadata} (POS: arrival stamp of a stored memory and its payload form)
- memory.manager::MemoryManager (POS: unified memory manager facade)
- memory.types::AnyMemory, SemanticMemory (POS: memory data models)
- strategies.consolidation_models::{CONSOLIDATION_INSIGHT_TAG, CONSOLIDATION_SOURCE_KEY} (POS: markers of consolidation's own output)

[OUTPUT]
- CandidateWindow: The memories of one run and the time the covered-through stamp may advance to
- fetch_candidate_window: Read the next oldest-first window of uncovered memories

[POS]
Selects what a consolidation run analyzes. The stamp is a covered-through mark over arrival order: every memory
stored at or before it was analyzed or deliberately skipped. Arrival is the store stamp, not ``created_at``, so a
memory approved late, imported with its source's timestamp or corrected is still seen. Only semantic and episodic
memories are read: a procedural rule takes effect through its trigger and action, which consolidation may not
rewrite, so a rule is never a candidate. The window walks forward in arrival order, never past the run's horizon and
never past a point some source was not read to, so a backlog larger than one run is drained batch by batch. The only
memories it skips are consolidation's own output, documents that cannot be decoded (one never hides its neighbours)
and, when a source is cut inside a group of documents stored before stamps existed that share one creation instant,
the rest of that group. An unreadable source, or a batch in which nothing decodes, holds the stamp instead of letting
it jump over memories the run could not see.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory._internal.storage import doc_to_episodic, doc_to_semantic
from myrm_agent_harness.toolkits.memory._internal.store_stamp import STORED_TS_KEY, stored_at_from_metadata
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    CONSOLIDATION_INSIGHT_TAG,
    CONSOLIDATION_SOURCE_KEY,
)
from myrm_agent_harness.toolkits.memory.types import SemanticMemory

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager
    from myrm_agent_harness.toolkits.memory.protocols.vector import FilterDict
    from myrm_agent_harness.toolkits.memory.types import AnyMemory
    from myrm_agent_harness.toolkits.vector.base import VectorDocument

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CandidateWindow:
    """One run's memories and where the covered-through stamp may advance once they are handled.

    ``advance_to`` is ``None`` when a source could not be read: the stamp must hold so the memories
    that source could not show stay uncovered for the next run.
    """

    memories: list[AnyMemory]
    advance_to: datetime | None


def _is_consolidation_product(memory: AnyMemory) -> bool:
    """Whether consolidation itself wrote this memory; feeding it back would make every run analyze the last one."""
    return isinstance(memory, SemanticMemory) and (
        CONSOLIDATION_INSIGHT_TAG in memory.tags or CONSOLIDATION_SOURCE_KEY in memory.metadata
    )


def _arrived_at(memory: AnyMemory) -> datetime:
    """When the memory reached the store: its stamp, or its creation time when it carries none."""
    return memory.stored_at or memory.created_at


def _without_split_instant(pool: list[AnyMemory], max_count: int) -> list[AnyMemory]:
    """The first ``max_count`` of an arrival-ordered pool that is longer, never cutting through one instant.

    The stamp is an instant, so memories that arrived at the same one must stay on the same side of it. Stamps never
    repeat within a process, but documents stamped from a shared creation time can share one. The cut moves back to
    the previous instant, or takes the whole instant when the first ``max_count`` all share it.
    """
    last = _arrived_at(pool[max_count - 1])
    if _arrived_at(pool[max_count]) != last:
        return pool[:max_count]
    before = [m for m in pool[:max_count] if _arrived_at(m) < last]
    return before or [m for m in pool if _arrived_at(m) == last]


async def _stamp_legacy_documents(manager: MemoryManager, collection: str) -> None:
    """Give documents stored before store stamps existed the stamp their creation time implies.

    The ordered read cannot see a document without a stamp, so the run would step over it.
    """
    vector, _ = manager._vec()
    await vector.backfill_payload_copy(collection, STORED_TS_KEY, "_created_ts")


async def _scroll_oldest_first(
    manager: MemoryManager, collection: str, since: datetime | None, horizon: datetime, limit: int
) -> list[VectorDocument]:
    """The first ``limit`` documents of the manager's scope stored after ``since`` and by ``horizon``, oldest first."""
    vector, _ = manager._vec()
    filters: FilterDict = {"primary_namespace": manager.namespaces}
    if manager.user_id is not None:
        filters["user_id"] = manager.user_id
    arrival: dict[str, str | int | float | bool] = {"lte": horizon.timestamp()}
    if since is not None:
        arrival["gt"] = since.timestamp()
    filters[STORED_TS_KEY] = arrival
    documents, _ = await vector.scroll(collection, limit=limit, filters=filters, order_by=(STORED_TS_KEY, "asc"))
    return documents


def _decode(
    collection: str, documents: list[VectorDocument], to_memory: Callable[[VectorDocument], AnyMemory]
) -> list[AnyMemory]:
    """Decode each document on its own, so one that cannot be decoded does not hide the rest of its source."""
    memories: list[AnyMemory] = []
    for document in documents:
        try:
            memories.append(to_memory(document))
        except Exception as exc:
            # The id and the failure type identify the document; its content is the user's, not a log line.
            logger.warning(
                "Consolidation skipped undecodable document %s in %s (%s)", document.id, collection, type(exc).__name__
            )
    return memories


async def fetch_candidate_window(
    manager: MemoryManager, since: datetime | None, max_count: int, horizon: datetime
) -> CandidateWindow:
    """Return the oldest ``max_count`` memories stored after ``since`` and by ``horizon`` that a run should analyze.

    ``horizon`` is the latest instant by which every write has finished: when every source was read to its end,
    nothing stored at or before it can be missing, so the stamp may advance to it. A source holding more than
    ``max_count`` documents is read only up to the last one kept, so the window must stop at the earliest such
    point (``bound``); otherwise a later memory from another source would be analyzed while an earlier one this
    source did not show would be skipped for good. The point is taken from the documents read, not from those that
    decoded, so a document that cannot be decoded still marks where the source was cut. When none of a source's
    documents decodes, the converter is more likely broken than the data, and the stamp holds.
    """
    candidates: list[AnyMemory] = []
    readable = True
    bound: datetime | None = None

    if manager.has_vector:
        config = manager.config
        sources: tuple[tuple[str, Callable[[VectorDocument], AnyMemory]], ...] = (
            (config.semantic_collection, doc_to_semantic),
            (config.episodic_collection, doc_to_episodic),
        )
        for collection, to_memory in sources:
            try:
                await _stamp_legacy_documents(manager, collection)
                documents = await _scroll_oldest_first(manager, collection, since, horizon, max_count + 1)
            except Exception as exc:
                logger.warning("Consolidation fetch from %s failed: %s", collection, exc)
                readable = False
                continue
            if len(documents) > max_count:
                documents = documents[:max_count]
                cut = stored_at_from_metadata(documents[-1].metadata)
                if cut is None:
                    logger.warning("Consolidation could not read the stamp that cuts %s", collection)
                    readable = False
                    continue
                bound = cut if bound is None else min(bound, cut)
            memories = _decode(collection, documents, to_memory)
            if documents and not memories:
                readable = False
            candidates.extend(memory for memory in memories if not _is_consolidation_product(memory))

    pool = sorted((m for m in candidates if bound is None or _arrived_at(m) <= bound), key=_arrived_at)
    if len(pool) > max_count:
        window = _without_split_instant(pool, max_count)
        covered_through = _arrived_at(window[-1])
    else:
        window = pool
        covered_through = horizon if bound is None else bound
    return CandidateWindow(memories=window, advance_to=covered_through if readable else None)


__all__ = ["CandidateWindow", "fetch_candidate_window"]
