"""Manager and document doubles of the consolidation unit tests.

[INPUT]
- toolkits.memory._internal.storage::doc_to_semantic (POS: Vector document to memory converter)
- toolkits.memory._internal.store_stamp::STORED_TS_KEY (POS: Payload key of the store stamp)
- toolkits.memory.strategies.consolidation_models::{ConsolidationBatch, ConsolidationOp} (POS: One namespace group's proposals and the operation union)
- toolkits.memory.types::{AnyMemory, SemanticMemory} (POS: Memory type definitions)
- toolkits.vector.base::VectorDocument (POS: Vector store document contract)

[OUTPUT]
- make_manager: a memory-manager double with async primitives, plain backend accessors and an empty vector and relational store behind it
- make_manager_serving: the same double whose ``get_memory`` serves the given memories by id
- make_manager_holding: the same double with documents in its store: the window reads them and ``get_memory`` serves each by id
- batches_of: one namespace group, the memories the model read and the operations it proposed, as the executor takes them
- semantic_doc: the vector document of a semantic memory that was created, and reached the store, a number of days ago

[POS]
Harness pytest-only doubles shared by the consolidation unit tests (the run, the cursor and the steps it is
composed of), so a test states the manager it runs against and not how a mock is wired.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from myrm_agent_harness.toolkits.memory._internal.storage import doc_to_semantic
from myrm_agent_harness.toolkits.memory._internal.store_stamp import STORED_TS_KEY
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import ConsolidationBatch, ConsolidationOp
from myrm_agent_harness.toolkits.memory.types import AnyMemory, SemanticMemory
from myrm_agent_harness.toolkits.vector.base import VectorDocument


def make_manager() -> AsyncMock:
    """Manager mock with async primitives and non-async backend accessors."""
    manager = AsyncMock()
    manager.user_id = "test-user"
    manager.namespaces = ["test-ns"]
    manager._namespaces = ["test-ns"]
    manager.has_vector = True
    manager.has_relational = True
    manager.config.semantic_collection = "test_semantic"
    manager.config.episodic_collection = "test_episodic"

    vector = AsyncMock()
    vector.scroll = AsyncMock(return_value=([], None))
    manager._vec = MagicMock(return_value=(vector, MagicMock()))
    manager._vec_store = vector

    relational = AsyncMock()
    relational.get_profile = AsyncMock(return_value=None)
    relational.set_profile = AsyncMock()
    manager._rel = MagicMock(return_value=relational)
    manager._rel_store = relational

    manager.search = AsyncMock(return_value=[])
    manager.add_event = AsyncMock()
    manager.store = AsyncMock(return_value=MagicMock(id="stored-id"))
    manager.get_memory = AsyncMock(return_value=SemanticMemory(content="old content"))
    manager.update_memory = AsyncMock()
    manager.correct_memory = AsyncMock(return_value=MagicMock(id="corrected-id"))
    return manager


def make_manager_serving(*memories: AnyMemory) -> AsyncMock:
    """Manager double whose ``get_memory`` serves ``memories`` by id: the store copy the apply step re-reads."""
    manager = make_manager()
    served = {memory.id: memory for memory in memories}
    manager.get_memory = AsyncMock(side_effect=served.get)
    return manager


def make_manager_holding(*docs: VectorDocument) -> AsyncMock:
    """Manager double whose store holds ``docs``: the candidate window reads them and ``get_memory`` serves each.

    What the model read and what the apply step finds then agree, as they do in a store nobody writes to meanwhile.
    """
    manager = make_manager_serving(*(doc_to_semantic(doc) for doc in docs))
    manager._vec_store.scroll = AsyncMock(side_effect=[(list(docs), None), ([], None)])
    return manager


def batches_of(memories: Sequence[AnyMemory], *operations: ConsolidationOp) -> list[ConsolidationBatch]:
    """One namespace group: the memories the model read and the operations it proposed for them."""
    return [ConsolidationBatch(memories=memories, operations=list(operations))]


def semantic_doc(mem_id: str, content: str, *, days_ago: int = 2) -> VectorDocument:
    created_at = datetime.now(UTC) - timedelta(days=days_ago)
    return VectorDocument(
        id=mem_id,
        content=content,
        metadata={"user_id": "test-user", "importance": 0.8, "confidence": 0.9, STORED_TS_KEY: created_at.timestamp()},
        created_at=created_at,
    )
