"""Composition invariants of ``MemoryManager`` and the sparse-mirror write contract.

- A sparse-authoritative manager whose vector backend is not the BM25 mirror
  wrapper rejects semantic/episodic writes with the public ``MemoryError``
  (single and batch), so callers catching ``MemoryError`` see the failure.
- ``MemoryManager`` is composed from the core and its mixins. A member name
  defined by two of them is resolved silently by MRO order and shadows the
  other definition, so every member name must have exactly one defining base.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest

from myrm_agent_harness.toolkits.memory._manager import MemoryManager
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.manager import MemoryError
from myrm_agent_harness.toolkits.memory.types import AnyMemory, EpisodicMemory, SemanticMemory


def _semantic() -> SemanticMemory:
    return SemanticMemory(id=str(uuid4()), user_id="u1", content="User prefers dark mode")


def _episodic() -> EpisodicMemory:
    return EpisodicMemory(id=str(uuid4()), user_id="u1", content="Deploy rollback after the cache incident")


async def _store(manager: MemoryManager, memory: AnyMemory) -> object:
    return await manager.store(memory, _bypass_approval=True)


async def _store_batch(manager: MemoryManager, memory: AnyMemory) -> object:
    return await manager.store_batch([memory], _bypass_approval=True)


class TestSparseWriteWithoutMirror:
    @pytest.mark.parametrize(
        ("make_memory", "write"),
        [
            pytest.param(_semantic, _store, id="semantic-single"),
            pytest.param(_semantic, _store_batch, id="semantic-batch"),
            pytest.param(_episodic, _store, id="episodic-single"),
            pytest.param(_episodic, _store_batch, id="episodic-batch"),
        ],
    )
    @pytest.mark.asyncio
    async def test_write_raises_memory_error(
        self,
        memory_config: MemoryConfig,
        mock_vector_store,
        make_memory: Callable[[], AnyMemory],
        write: Callable[[MemoryManager, AnyMemory], Awaitable[object]],
    ) -> None:
        manager = MemoryManager(
            config=memory_config,
            user_id="u1",
            vector=mock_vector_store,
            sparse_authoritative=True,
        )

        with pytest.raises(MemoryError, match="Vector \\+ Embedding backends required"):
            await write(manager, make_memory())

        mock_vector_store.upsert.assert_not_called()


class TestManagerComposition:
    def test_each_member_is_defined_by_exactly_one_base(self) -> None:
        defined_by: dict[str, list[str]] = {}
        for base in MemoryManager.__mro__[1:]:
            if base is object:
                continue
            for name in vars(base):
                if name.startswith("__") and name.endswith("__"):
                    continue
                defined_by.setdefault(name, []).append(base.__name__)

        shadowed = {name: owners for name, owners in defined_by.items() if len(owners) > 1}
        assert shadowed == {}
