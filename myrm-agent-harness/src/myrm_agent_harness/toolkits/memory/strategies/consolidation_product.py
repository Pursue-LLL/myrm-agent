"""The memory a merge creates, with the scope, age and chat lineage it inherits from its sources.

[INPUT]
- strategies.consolidation_models::{CONSOLIDATION_SOURCE_KEY, MergeOp} (POS: marker of a merged memory and the merge operation)
- strategies.lineage::origin_chat_ids (POS: the chats a set of memories derives from)
- memory.types::{AnyMemory, SemanticMemory} (POS: memory records)

[OUTPUT]
- build_merge_product: The semantic memory a merge writes for its sources

[POS]
A merge folds its sources into one memory that carries on what they were: it stays visible where they were visible
(the scope of the first source), is as old as the oldest of them and as recently updated as the latest (a merge of
year-old notes is a year-old note, not new knowledge, and recall labels its age by these stamps), expires when the
longest-lived source would have (open-ended when any source has no validity window), records the full ids of its
sources and derives from the chats of all of them. Rating and access counts are not inherited: they measure how a
memory was used, and nobody has used the merged one yet.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timedelta

from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import CONSOLIDATION_SOURCE_KEY, MergeOp
from myrm_agent_harness.toolkits.memory.strategies.lineage import origin_chat_ids
from myrm_agent_harness.toolkits.memory.types import AnyMemory, SemanticMemory

_DAY = timedelta(days=1)


def _validity_days(created_at: datetime, sources: Sequence[AnyMemory]) -> int | None:
    """Days from ``created_at`` until the longest-lived source would have expired; ``None`` when one has no window."""
    ends: list[datetime] = []
    for source in sources:
        window = source.expected_valid_days
        if window is None or window <= 0:
            return None
        ends.append(source.created_at + timedelta(days=window))
    return math.ceil((max(ends) - created_at) / _DAY)


def build_merge_product(op: MergeOp, sources: Sequence[AnyMemory]) -> SemanticMemory:
    """The memory ``op`` writes; ``sources`` are the memories named by ``op.source_ids``, in that order."""
    created_at = min(source.created_at for source in sources)
    chat_ids = origin_chat_ids(sources)
    return SemanticMemory(
        content=op.merged_content,
        importance=op.importance,
        confidence=0.9,
        source_chat_id=chat_ids[0] if chat_ids else None,
        source_chat_ids=chat_ids,
        scope=sources[0].scope.model_copy(deep=True),
        created_at=created_at,
        updated_at=max(source.updated_at for source in sources),
        expected_valid_days=_validity_days(created_at, sources),
        metadata={CONSOLIDATION_SOURCE_KEY: ",".join(op.source_ids)},
    )


__all__ = ["build_merge_product"]
