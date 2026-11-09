"""Seeds of the consolidation real-flow tests: memories with a stated arrival, written below a manager.

[INPUT]
- toolkits.memory._internal.storage::store_episodics_batch, store_semantics_batch (POS: Vector persistence without a store stamp)
- toolkits.memory._internal.store_stamp::STORED_TS_KEY (POS: Payload key of the store stamp)
- toolkits.memory.manager::MemoryManager (POS: Unified memory manager facade)
- toolkits.memory.strategies.consolidation_models::ConsolidationResponse (POS: Structured consolidation output)
- toolkits.vector.base::VectorDocument (POS: Vector store document contract)

[OUTPUT]
- BASE, HORIZON, GLOBAL, NewManager, at: the clock and scope the seeds are laid out on
- semantic, episodic: a memory created ``offset_s`` seconds after ``BASE`` that reached the store at ``stored_s`` (default: when it was created); a semantic one can state its importance, confidence, metadata and pin
- seed, seed_undecodable: write them below a manager with an explicit stamp, the way the store lays them out
- llm_returning: a chat model that answers every consolidation call with one response

[POS]
Harness pytest-only seeds shared by the consolidation cursor tests. ``seed`` writes through the plain persistence
functions, which stamp nothing, so a memory's arrival is exactly what the test states; the manager write path,
which stamps, is what the tests of the stamp itself drive.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from myrm_agent_harness.toolkits.memory._internal.storage import store_episodics_batch, store_semantics_batch
from myrm_agent_harness.toolkits.memory._internal.store_stamp import STORED_TS_KEY
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import ConsolidationResponse
from myrm_agent_harness.toolkits.memory.types import AnyMemory, EpisodicMemory, MemoryScope, SemanticMemory
from myrm_agent_harness.toolkits.vector.base import VectorDocument

# Memories are seeded far in the past so the one-hour soft lock never gates a run.
BASE = datetime.now(UTC).replace(microsecond=0) - timedelta(days=30)
HORIZON = BASE + timedelta(days=1)

NewManager = Callable[..., MemoryManager]
# Memories written below a manager (not through it) carry the scope the manager would have bound.
GLOBAL = MemoryScope(primary_namespace="global", namespaces=["global"])


def at(offset_s: int) -> datetime:
    return BASE + timedelta(seconds=offset_s)


def semantic(
    content: str,
    offset_s: int,
    *,
    stored_s: int | None = None,
    tags: list[str] | None = None,
    correction_of: str | None = None,
    importance: float = 0.5,
    confidence: float = 1.0,
    metadata: dict[str, str | int | float | bool] | None = None,
    pinned: bool = False,
) -> SemanticMemory:
    return SemanticMemory(
        content=content,
        user_id="u1",
        scope=GLOBAL,
        created_at=at(offset_s),
        stored_at=at(offset_s if stored_s is None else stored_s),
        tags=tags or [],
        correction_of=correction_of,
        importance=importance,
        confidence=confidence,
        metadata=metadata or {},
        pinned=pinned,
    )


def episodic(content: str, offset_s: int, *, stored_s: int | None = None) -> EpisodicMemory:
    return EpisodicMemory(
        content=content,
        user_id="u1",
        scope=GLOBAL,
        created_at=at(offset_s),
        stored_at=at(offset_s if stored_s is None else stored_s),
    )


async def seed(manager: MemoryManager, memories: Sequence[AnyMemory]) -> None:
    vector, embedding = manager._vec()
    semantics = [m for m in memories if isinstance(m, SemanticMemory)]
    episodics = [m for m in memories if isinstance(m, EpisodicMemory)]
    if semantics:
        await store_semantics_batch(semantics, vector, manager.config, embedding, None)
    if episodics:
        await store_episodics_batch(episodics, vector, manager.config, embedding, None)


async def seed_undecodable(manager: MemoryManager, offset_s: int) -> str:
    """Store a document whose importance lies outside the model's 0-1 range, so decoding it raises; return its id."""
    vector, _ = manager._vec()
    document = VectorDocument(
        content="private note",
        vector=[1.0, 0.5, 0.5, 0.5],
        metadata={
            "user_id": "u1",
            "primary_namespace": "global",
            "importance": 8.0,
            STORED_TS_KEY: at(offset_s).timestamp(),
        },
        created_at=at(offset_s),
        updated_at=at(offset_s),
    )
    await vector.upsert(manager.config.semantic_collection, [document])
    return document.id


def llm_returning(response: ConsolidationResponse) -> MagicMock:
    structured = AsyncMock()
    structured.ainvoke = AsyncMock(return_value=response)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm
