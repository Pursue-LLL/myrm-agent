"""``import_memories(skip_duplicates=False)`` writes every entry through the real write path.

A restore that replaces the store must land each backed-up memory, including two with the same content;
the default import still drops the repeat and what the store already holds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import MemoryType, SemanticMemory

_CONTENT = "Prefers TypeScript strict mode in every new service"


def _twins() -> dict[str, list[dict[str, object]]]:
    entry = SemanticMemory(content=_CONTENT).model_dump(mode="json", exclude={"embedding"})
    return {"semantic": [dict(entry), dict(entry)]}


@pytest.mark.slow
@pytest.mark.asyncio
async def test_skipping_duplicates_keeps_one_of_two_identical_entries(tmp_path: Path) -> None:
    manager = await create_local_memory_manager(tmp_path / "mem", None)
    try:
        counts = await manager.import_memories(_twins())

        assert counts == {"semantic": 1}
        assert await manager.count_memories(MemoryType.SEMANTIC) == 1
    finally:
        await manager.close()


@pytest.mark.slow
@pytest.mark.asyncio
async def test_not_skipping_duplicates_writes_every_entry(tmp_path: Path) -> None:
    manager = await create_local_memory_manager(tmp_path / "mem", None)
    try:
        counts = await manager.import_memories(_twins(), skip_duplicates=False)

        assert counts == {"semantic": 2}
        assert await manager.count_memories(MemoryType.SEMANTIC) == 2
    finally:
        await manager.close()


@pytest.mark.slow
@pytest.mark.asyncio
async def test_not_skipping_duplicates_writes_what_the_store_already_holds(tmp_path: Path) -> None:
    manager = await create_local_memory_manager(tmp_path / "mem", None)
    try:
        await manager.import_memories(_twins())

        counts = await manager.import_memories(_twins(), skip_duplicates=False)

        assert counts == {"semantic": 2}
        assert await manager.count_memories(MemoryType.SEMANTIC) == 3
    finally:
        await manager.close()
