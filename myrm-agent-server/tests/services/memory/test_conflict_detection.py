"""Tests for Memory Command Center conflict scanning (Server layer).

Validates build_conflicts() correctly identifies:
- correction: memories that corrected older ones (keep_new chain)
- supersession: memories that have been superseded (keep_old chain)
- claim: active claim nodes from Claim Graph (merge evidence)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.toolkits.memory import MemoryType

from app.services.memory.command_center_insights import MemoryCommandCenterInsights


@dataclass
class FakeMemory:
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    correction_of: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@pytest.fixture
def insights() -> MemoryCommandCenterInsights:
    mock_manager = AsyncMock()
    mock_db = MagicMock()
    mock_ledger = MagicMock()
    return MemoryCommandCenterInsights(
        db=mock_db,
        memory_manager=mock_manager,
        ledger=mock_ledger,
    )


class TestBuildConflicts:
    """Tests for conflict detection across memory types."""

    @pytest.mark.asyncio
    async def test_detects_correction_conflict(self, insights: MemoryCommandCenterInsights) -> None:
        """Memory with correction_of triggers correction conflict item."""
        correcting = FakeMemory(
            id="mem-new",
            content="User now prefers Rust over Python",
            correction_of="mem-old",
        )
        insights._memory_manager.list_memories = AsyncMock(return_value=[correcting])

        items = await insights.build_conflicts()

        correction_items = [i for i in items if i.kind == "correction"]
        assert len(correction_items) >= 1
        assert correction_items[0].related_memory_id == "mem-old"
        assert correction_items[0].status == "resolved"

    @pytest.mark.asyncio
    async def test_detects_supersession_conflict(self, insights: MemoryCommandCenterInsights) -> None:
        """Memory with corrected=True metadata triggers supersession conflict."""
        superseded = FakeMemory(
            id="mem-old",
            content="User prefers Python",
            metadata={"corrected": True},
        )
        insights._memory_manager.list_memories = AsyncMock(return_value=[superseded])

        items = await insights.build_conflicts()

        supersession_items = [i for i in items if i.kind == "supersession"]
        assert len(supersession_items) >= 1
        assert supersession_items[0].memory_id == "mem-old"
        assert supersession_items[0].status == "resolved"

    @pytest.mark.asyncio
    async def test_detects_claim_node(self, insights: MemoryCommandCenterInsights) -> None:
        """CLAIM type memories are surfaced as active claim conflicts for review."""
        claim = FakeMemory(
            id="claim-001",
            content="Prefers functional programming",
        )
        semantic = FakeMemory(
            id="sem-001",
            content="Some memory",
        )

        async def mock_list_memories(memory_type: MemoryType, limit: int = 80) -> list[FakeMemory]:
            if memory_type == MemoryType.CLAIM:
                return [claim]
            return [semantic]

        insights._memory_manager.list_memories = mock_list_memories  # type: ignore[assignment]

        items = await insights.build_conflicts()

        claim_items = [i for i in items if i.kind == "claim"]
        assert len(claim_items) >= 1
        assert claim_items[0].memory_id == "claim-001"
        assert claim_items[0].status == "active"

    @pytest.mark.asyncio
    async def test_empty_memories_no_conflicts(self, insights: MemoryCommandCenterInsights) -> None:
        """No memories means no conflicts."""
        insights._memory_manager.list_memories = AsyncMock(return_value=[])

        items = await insights.build_conflicts()
        assert items == []

    @pytest.mark.asyncio
    async def test_normal_memory_no_conflict(self, insights: MemoryCommandCenterInsights) -> None:
        """Normal memory without correction/supersession flags generates no conflict."""
        normal = FakeMemory(
            id="mem-normal",
            content="User likes dark mode",
            metadata={},
        )
        insights._memory_manager.list_memories = AsyncMock(return_value=[normal])

        items = await insights.build_conflicts()

        correction_or_supersession = [i for i in items if i.kind in ("correction", "supersession")]
        assert len(correction_or_supersession) == 0

    @pytest.mark.asyncio
    async def test_max_8_items_cap(self, insights: MemoryCommandCenterInsights) -> None:
        """Conflicts are capped at 8 items for UI performance."""
        many_claims = [FakeMemory(id=f"claim-{i}", content=f"Claim {i}") for i in range(20)]

        async def mock_list_memories(memory_type: MemoryType, limit: int = 80) -> list[FakeMemory]:
            if memory_type == MemoryType.CLAIM:
                return many_claims
            return []

        insights._memory_manager.list_memories = mock_list_memories  # type: ignore[assignment]

        items = await insights.build_conflicts()
        assert len(items) <= 8

    @pytest.mark.asyncio
    async def test_handles_list_memories_exception(self, insights: MemoryCommandCenterInsights) -> None:
        """Graceful handling when memory listing fails."""
        insights._memory_manager.list_memories = AsyncMock(side_effect=RuntimeError("DB down"))

        items = await insights.build_conflicts()
        assert items == []
