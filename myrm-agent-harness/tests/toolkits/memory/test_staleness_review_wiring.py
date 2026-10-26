"""A maintenance cycle runs the staleness review through the manager's chat model.

The reviewer takes a ``(system, user) -> text`` callable; the manager owns a chat model.
These tests run the whole cycle on a real manager with a real ``BaseChatModel``
subclass, so the adapter, the shared mirror-aware vector store and the metadata
write-back are exercised together: a decision must reach the stored memory without
re-dating it, and a reviewed memory must leave the review queue. The model is handed
in both ways a caller can: as the dedup model (which consolidation falls back to) and
as the consolidation model alone, which is how the memory guardian builds its manager.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import MemoryType, SemanticMemory

_AGE_DAYS = 200


@pytest.mark.asyncio
@pytest.mark.parametrize("consolidation_only", [False, True], ids=["dedup-model", "consolidation-model-only"])
async def test_cycle_applies_a_chat_models_decisions_without_redating_memories(
    tmp_path: Path, consolidation_only: bool
) -> None:
    ids = [str(uuid4()) for _ in range(4)]
    review = json.dumps(
        [
            {"id": ids[0], "action": "remove", "reason": "outdated"},
            {"id": ids[1], "action": "extend", "reason": "stable", "extend_by_days": 90},
            {"id": ids[2], "action": "keep", "reason": "still true"},
            {"id": ids[3], "action": "keep", "reason": "still true"},
        ]
    )
    model = FakeListChatModel(responses=[review])
    manager = await create_local_memory_manager(
        tmp_path / "mem",
        None,
        dedup_llm=None if consolidation_only else model,
        consolidation_llm=model if consolidation_only else None,
    )
    try:
        created = datetime.now(UTC) - timedelta(days=_AGE_DAYS)
        for n, memory_id in enumerate(ids):
            await manager.store(
                SemanticMemory(
                    id=memory_id,
                    user_id="sandbox_user",
                    content=f"studying topic number {n} this month",
                    expected_valid_days=30,
                    created_at=created,
                )
            )

        first = await manager.run_maintenance_cycle(force=True)
        second = await manager.run_maintenance_cycle(force=True)

        remaining = {m.id: m for m in await manager.list_memories(MemoryType.SEMANTIC, limit=10)}
        assert (first.staleness_reviewed, first.staleness_removed, first.staleness_extended) == (4, 1, 1)
        assert set(remaining) == set(ids[1:])
        assert remaining[ids[1]].expected_valid_days == _AGE_DAYS + 90
        assert remaining[ids[2]].expected_valid_days == _AGE_DAYS + 30
        assert all(abs((m.created_at - created).total_seconds()) < 1 for m in remaining.values())
        assert second.staleness_reviewed == 0
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_maintenance_shares_the_manager_vector_store(tmp_path: Path) -> None:
    """Maintenance writes must go through the same mirror-aware store as every other consumer."""
    manager = await create_local_memory_manager(tmp_path / "mem", None)
    try:
        assert manager._maintenance_service._vector is manager._vector
    finally:
        await manager.close()
