"""A maintenance cycle on a keyword-mode manager (no embedding) is safe to run.

Background maintenance also runs for installs without an embedding model. The cycle must
complete without errors, must not consolidate (merging needs dense similarity), and must
leave stored memories untouched even when an LLM is wired and memories are past their TTL.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import MemoryType, SemanticMemory


@pytest.mark.slow
@pytest.mark.asyncio
async def test_forced_cycle_completes_without_consolidating_or_losing_memories(tmp_path: Path) -> None:
    manager = await create_local_memory_manager(tmp_path / "mem", None, dedup_llm=FakeListChatModel(responses=["[]"]))
    try:
        expired = datetime.now(UTC) - timedelta(days=120)
        for n in range(4):
            await manager.store(
                SemanticMemory(
                    id=str(uuid4()),
                    user_id="sandbox_user",
                    content=f"studying topic number {n} this month",
                    expected_valid_days=30,
                    created_at=expired,
                )
            )

        report = await manager.run_maintenance_cycle(force=True)

        assert not manager.has_vector
        assert report.skipped is False
        assert report.consolidation_errors == 0
        assert (report.consolidation_merged, report.consolidation_corrected, report.consolidation_updated) == (0, 0, 0)
        assert (report.forgotten_count, report.archived_count, report.staleness_removed) == (0, 0, 0)
        assert len(await manager.list_memories(MemoryType.SEMANTIC, limit=10)) == 4
    finally:
        await manager.close()
