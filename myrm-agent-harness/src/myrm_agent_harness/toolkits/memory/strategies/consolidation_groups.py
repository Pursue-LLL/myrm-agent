"""Namespace groups of a consolidation window, and the model's analysis of one group.

[INPUT]
- memory._internal.write_fence::{write_grant, within_write_grant} (POS: write-scope fence predicate)
- strategies.consolidation_insights::validated_insights (POS: closure check on the insights the model drew)
- strategies.consolidation_models::{ConsolidationBatch, ConsolidationResponse} (POS: one group's proposals and the structured model answer)
- strategies.consolidation_ops_filter::filter_and_guard_operations (POS: pre-apply checks of the proposed operations)
- strategies.consolidation_prompts::{_SYSTEM_PROMPT, _build_id_map, _build_user_prompt} (POS: prompts and short-id compression)
- memory.manager::MemoryManager (POS: unified memory manager facade)
- memory.types::AnyMemory (POS: memory records)

[OUTPUT]
- writable_groups: Split a window by primary namespace into the groups worth asking the model about
- analyze_group: One structured model call over one group, its operations and insights checked

[POS]
A namespace is the unit of visibility and of the write fence, so the model only ever compares memories that share
one: a merge, a rewrite or an insight can then draw only on what every reader of that namespace may see, and what it
writes stays inside it. A group is dropped before the model is called when it holds fewer than two memories, when the
window is one new memory with its neighbours and the new memory is not in the group (neighbours alone have nothing new
to compare), or when any of its memories lies outside the manager's write scope (a merged memory carries the scope of
its sources, so it could not be stored).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from myrm_agent_harness.toolkits.memory._internal.write_fence import within_write_grant, write_grant
from myrm_agent_harness.toolkits.memory.strategies.consolidation_insights import validated_insights
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    ConsolidationBatch,
    ConsolidationResponse,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_ops_filter import filter_and_guard_operations
from myrm_agent_harness.toolkits.memory.strategies.consolidation_prompts import (
    _SYSTEM_PROMPT,
    _build_id_map,
    _build_user_prompt,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from myrm_agent_harness.toolkits.memory.manager import MemoryManager
    from myrm_agent_harness.toolkits.memory.types import AnyMemory

logger = logging.getLogger(__name__)


def writable_groups(
    memories: Sequence[AnyMemory], manager: MemoryManager, new_ids: frozenset[str] | None = None
) -> list[list[AnyMemory]]:
    """Split ``memories`` by primary namespace, arrival order kept, and drop the groups not worth a model call.

    A group needs two memories to have anything to compare and, when the window is one new memory with its
    neighbours (``new_ids``), the new memory among them. Every memory of it must lie inside the manager's write
    scope: the memory a merge creates takes the scope of its sources, so the write fence would refuse it.
    """
    by_namespace: dict[str, list[AnyMemory]] = {}
    for memory in memories:
        by_namespace.setdefault(memory.scope.primary_namespace, []).append(memory)

    grant = write_grant(manager.scope, manager.namespaces)
    groups: list[list[AnyMemory]] = []
    for namespace, members in by_namespace.items():
        if len(members) < 2:
            continue
        if new_ids is not None and new_ids.isdisjoint(member.id for member in members):
            continue
        if not all(within_write_grant(member.scope.namespaces, grant) for member in members):
            logger.info(
                "Consolidation skipped namespace %s: its memories lie outside this manager's write scope", namespace
            )
            continue
        groups.append(members)
    return groups


async def analyze_group(
    memories: Sequence[AnyMemory], llm: BaseChatModel, today: str, new_ids: frozenset[str] | None
) -> ConsolidationBatch:
    """Ask the model about one group; keep the operations and insights that pass the checks needing no store access."""
    id_map = _build_id_map(memories)
    user_prompt = _build_user_prompt(memories, today, id_map, new_ids=new_ids)
    structured_llm = llm.with_structured_output(ConsolidationResponse)
    raw_response = await structured_llm.ainvoke(
        [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
    )
    if isinstance(raw_response, dict):
        response = ConsolidationResponse.model_validate(raw_response)
    elif isinstance(raw_response, ConsolidationResponse):
        response = raw_response
    else:
        raise TypeError(f"Unexpected response type from structured LLM: {type(raw_response)}")

    checked = filter_and_guard_operations(response.operations, memories, id_map)
    insights, rejected_insights = validated_insights(response.insights, memories)
    return ConsolidationBatch(
        memories=memories,
        operations=checked.operations,
        insights=insights,
        guard_patched=checked.guard_patched,
        rejected=checked.rejected + rejected_insights,
    )


__all__ = ["analyze_group", "writable_groups"]
