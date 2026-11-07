"""Oldest-first window of memories a consolidation run has not covered yet.

[INPUT]
- memory._internal.storage::doc_to_episodic, doc_to_semantic (POS: Vector document to memory converters)
- memory.manager::MemoryManager (POS: unified memory manager facade)
- memory.types::AnyMemory, EpisodicMemory, SemanticMemory (POS: memory data models)
- strategies.consolidation_models::{CONSOLIDATION_EVENT_TYPE, CONSOLIDATION_INSIGHT_TAG, CONSOLIDATION_SOURCE_KEY} (POS: markers of consolidation's own output)

[OUTPUT]
- CandidateWindow: The memories of one run and the time the covered-through stamp may advance to
- fetch_candidate_window: Read the next oldest-first window of uncovered memories

[POS]
Selects what a consolidation run analyzes. The stamp is a covered-through mark: every memory created at or before
it was analyzed or deliberately skipped. The window therefore walks forward in creation order and never past a
point some source was not read to, so a backlog larger than one run is drained batch by batch. The only memories
it skips are consolidation's own output and documents that cannot be decoded, and such a document never hides its
neighbours. An unreadable source, or a batch in which nothing decodes, holds the stamp instead of letting it jump
over memories the run could not see.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory._internal.storage import doc_to_episodic, doc_to_semantic
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    CONSOLIDATION_EVENT_TYPE,
    CONSOLIDATION_INSIGHT_TAG,
    CONSOLIDATION_SOURCE_KEY,
)
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, SemanticMemory

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
    if isinstance(memory, EpisodicMemory):
        return memory.event_type == CONSOLIDATION_EVENT_TYPE
    if isinstance(memory, SemanticMemory):
        return CONSOLIDATION_INSIGHT_TAG in memory.tags or CONSOLIDATION_SOURCE_KEY in memory.metadata
    return False


async def _scroll_oldest_first(
    manager: MemoryManager, collection: str, since: datetime | None, limit: int
) -> list[VectorDocument]:
    """The first ``limit`` documents of the manager's scope created after ``since``, oldest first."""
    vector, _ = manager._vec()
    filters: FilterDict = {"primary_namespace": manager.namespaces}
    if manager.user_id is not None:
        filters["user_id"] = manager.user_id
    if since is not None:
        filters["_created_ts"] = {"gt": since.timestamp()}
    documents, _ = await vector.scroll(collection, limit=limit, filters=filters, order_by=("_created_ts", "asc"))
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
    """Return the oldest ``max_count`` memories created after ``since`` that a run should analyze.

    ``horizon`` is the run's start: when every source was read to its end, nothing created before it can
    be missing, so the stamp may advance to it. A source holding more than ``max_count`` documents is read
    only up to the last one kept, so the window must stop at the earliest such point (``bound``); otherwise
    a later memory from another source would be analyzed while an earlier one this source did not show
    would be skipped for good. The point is taken from the documents read, not from those that decoded, so a
    document that cannot be decoded still marks where the source was cut. When none of a source's documents
    decodes, the converter is more likely broken than the data, and the stamp holds.
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
                documents = await _scroll_oldest_first(manager, collection, since, max_count + 1)
            except Exception as exc:
                logger.warning("Consolidation fetch from %s failed: %s", collection, exc)
                readable = False
                continue
            if len(documents) > max_count:
                documents = documents[:max_count]
                cut = documents[-1].created_at
                bound = cut if bound is None else min(bound, cut)
            memories = _decode(collection, documents, to_memory)
            if documents and not memories:
                readable = False
            candidates.extend(memory for memory in memories if not _is_consolidation_product(memory))

    if manager.has_relational:
        try:
            rules = await manager._rel().list_rules(active_only=True, namespaces=manager.namespaces)
        except Exception as exc:
            logger.warning("Consolidation fetch procedural rules failed: %s", exc)
            readable = False
        else:
            candidates.extend(rule for rule in rules if since is None or rule.created_at > since)

    pool = sorted((m for m in candidates if bound is None or m.created_at <= bound), key=lambda m: m.created_at)
    window = pool[:max_count]
    if len(pool) > max_count:
        covered_through = window[-1].created_at
    else:
        covered_through = horizon if bound is None else bound
    # A memory stamped ahead of the clock must not push the stamp into the future, where it would be ignored.
    return CandidateWindow(memories=window, advance_to=min(covered_through, horizon) if readable else None)


__all__ = ["CandidateWindow", "fetch_candidate_window"]
