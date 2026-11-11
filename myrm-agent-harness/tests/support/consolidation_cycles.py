"""One consolidation cycle driven end to end, and the operations and undo calls a test states it with.

[INPUT]
- toolkits.memory.config::ConsolidationConfig (POS: Consolidation configuration)
- toolkits.memory.manager::MemoryManager (POS: Unified memory manager facade)
- toolkits.memory.strategies.consolidation::run_consolidation (POS: One consolidation cycle)
- toolkits.memory.strategies.consolidation_models::* (POS: Consolidation operations, responses and run statistics)
- toolkits.memory.strategies.consolidation_undo::{UndoResult, get_undo_summary, undo_last_consolidation} (POS: Exact undo of the latest consolidation cycle)
- support.consolidation_seeds::{llm_returning, seed, semantic} (POS: A chat model that answers every consolidation call with one response; seeded memories)

[OUTPUT]
- CONFIG: the consolidation config of a test that runs several cycles back to back (no soft lock)
- TEA, TEA_TOO: two facts that read as one, the pair a merge folds together
- run_cycle: one cycle through ``run_consolidation``, the call the idle worker makes, answered with the given operations
- merge, correct, rewrite: the operations a model proposes, named by the short ids of the memories they act on
- merged_pair: TEA and TEA_TOO seeded and folded by one cycle: both sources and the id of the memory the merge created
- store_fresh: memories written through the manager after a finished cycle, so the next cycle has something to analyze
- stored_insights: the insights the cycles have persisted, whether or not an undo journal knows them
- undo: what the settings card does: read the undoable cycle's summary and undo the cycle it names

[POS]
Harness pytest-only helpers shared by the consolidation undo tests, so a test states the operations of a cycle and
what it undoes, and not how a run is wired.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.config import ConsolidationConfig
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.consolidation import run_consolidation
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    CONSOLIDATION_INSIGHT_TAG,
    ConsolidationOp,
    ConsolidationResponse,
    ConsolidationStats,
    CorrectOp,
    MergeOp,
    UpdateContentOp,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_undo import (
    UndoResult,
    get_undo_summary,
    undo_last_consolidation,
)
from myrm_agent_harness.toolkits.memory.types import AnyMemory, MemoryType, SemanticMemory
from tests.support.consolidation_seeds import llm_returning, seed, semantic

# A test runs several cycles back to back, so the soft lock that spaces real runs apart is off.
CONFIG = ConsolidationConfig(soft_lock_hours=0.0)
TEA = "User drinks green tea every morning"
TEA_TOO = "User likes green tea early in the day"


async def run_cycle(
    manager: MemoryManager, *ops: ConsolidationOp, insights: tuple[str, ...] = ()
) -> ConsolidationStats:
    response = ConsolidationResponse(operations=list(ops), insights=list(insights))
    return await run_consolidation(manager, llm_returning(response), CONFIG)


def merge(first: AnyMemory, second: AnyMemory, text: str) -> MergeOp:
    return MergeOp(source_ids=[first.id[:8], second.id[:8]], merged_content=text)


def correct(memory: AnyMemory, text: str) -> CorrectOp:
    return CorrectOp(memory_id=memory.id[:8], corrected_content=text, accuracy_score=0.95)


def rewrite(memory: AnyMemory, text: str, importance: float) -> UpdateContentOp:
    return UpdateContentOp(memory_id=memory.id[:8], new_content=text, importance=importance)


async def merged_pair(manager: MemoryManager) -> tuple[SemanticMemory, SemanticMemory, str]:
    """Two facts folded by one cycle: both sources, and the id of the memory the merge created."""
    first, second = semantic(TEA, 1, importance=0.4), semantic(TEA_TOO, 2, importance=0.9)
    await seed(manager, [first, second])
    stats = await run_cycle(manager, merge(first, second, TEA))
    [merged_id] = stats.undo.created
    return first, second, merged_id


async def store_fresh(manager: MemoryManager, *texts: str) -> list[AnyMemory]:
    """Memories that reach the store after a finished cycle, so the next cycle has something to analyze."""
    return [await manager.store(SemanticMemory(content=text), _bypass_approval=True) for text in texts]


async def stored_insights(manager: MemoryManager) -> list[SemanticMemory]:
    memories = await manager.list_memories(MemoryType.SEMANTIC, tag_filter=CONSOLIDATION_INSIGHT_TAG)
    return [memory for memory in memories if isinstance(memory, SemanticMemory)]


async def undo(manager: MemoryManager) -> UndoResult:
    summary = await get_undo_summary(manager)
    assert summary is not None
    result = await undo_last_consolidation(manager, summary.cycle_id)
    assert result is not None
    return result
