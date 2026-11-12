"""Insights a consolidation cycle draws: the closure check on what the model states, and their persistence.

[INPUT]
- strategies.consolidation_closure::facts_of (POS: the numbers and identifiers a text states)
- strategies.consolidation_models::{CONSOLIDATION_INSIGHT_TAG, UndoJournal} (POS: marker of an insight and the cycle's undo journal)
- strategies.consolidation_undo::CycleWrites (POS: the write gateway that journals what a cycle changes)
- strategies.lineage::origin_chat_ids (POS: the chats a set of memories derives from)
- memory.manager::MemoryManager (POS: unified memory manager facade)
- memory.types::{AnyMemory, SemanticMemory} (POS: memory records)

[OUTPUT]
- validated_insights: The insights that state nothing the analyzed memories do not, and how many were turned away
- persist_insights: Store insights as tagged implicit-preference memories through the cycle's write gateway

[POS]
An insight is a durable observation the model drew from the memories it read. It is stored as a memory and later
feeds preference facets and wiki summaries, so a number or identifier no analyzed memory states never reaches the
store. A stored insight takes the scope of the group it was drawn from and derives from the chats of every memory
in that group.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory.strategies.consolidation_closure import facts_of
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import CONSOLIDATION_INSIGHT_TAG, UndoJournal
from myrm_agent_harness.toolkits.memory.strategies.consolidation_undo import CycleWrites
from myrm_agent_harness.toolkits.memory.strategies.lineage import origin_chat_ids
from myrm_agent_harness.toolkits.memory.types import SemanticMemory

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager
    from myrm_agent_harness.toolkits.memory.types import AnyMemory

logger = logging.getLogger(__name__)

_MIN_INSIGHT_LENGTH = 10
_INSIGHT_IMPORTANCE = 0.6


def validated_insights(insights: Sequence[str], memories: Sequence[AnyMemory]) -> tuple[list[str], int]:
    """The insights stating no number or identifier absent from ``memories``, and how many were turned away."""
    if not insights:
        return [], 0
    window_facts = facts_of(*(memory.content for memory in memories))
    kept = [insight for insight in insights if facts_of(insight).beyond(window_facts).is_empty]
    if rejected := len(insights) - len(kept):
        logger.info(
            "Consolidation dropped %d insight(s): each states a number or identifier no analyzed memory states",
            rejected,
        )
    return kept, rejected


async def persist_insights(
    manager: MemoryManager, insights: Sequence[str], sources: Sequence[AnyMemory], journal: UndoJournal
) -> None:
    """Persist insights of one group as SemanticMemory with implicit preference type.

    ``sources`` are the group's memories: an insight derives from the chats of all of them and takes the scope of
    the first. It is written through the cycle's write gateway, so ``journal`` records it for undo.
    """
    if not manager.has_vector:
        return

    writes = CycleWrites(manager, journal)
    chat_ids = origin_chat_ids(sources)
    stored = 0
    for text in insights:
        text = text.strip()
        if len(text) < _MIN_INSIGHT_LENGTH:
            continue
        mem = SemanticMemory(
            user_id=manager.user_id if manager.user_id is not None else "default",
            content=text,
            importance=_INSIGHT_IMPORTANCE,
            confidence=0.8,
            preference_type="implicit",
            preference_strength=0.6,
            tags=[CONSOLIDATION_INSIGHT_TAG],
            source_chat_id=chat_ids[0] if chat_ids else None,
            source_chat_ids=chat_ids,
            scope=sources[0].scope.model_copy(deep=True),
        )
        try:
            await writes.store(mem)
            stored += 1
        except Exception as e:
            logger.warning("Failed to persist consolidation insight: %s", e)

    if stored:
        logger.info("Persisted %d consolidation insights as implicit preferences", stored)


__all__ = ["persist_insights", "validated_insights"]
