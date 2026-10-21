"""Tests for MemoryEconomicsService production wiring, backward model scan, and pinned exemption."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.toolkits.memory import MemoryType

from app.database.models.chat import Message
from app.services.memory.command_center.command_center import MemoryCommandCenterService
from app.services.memory.command_center.command_center_economics import MemoryEconomicsService


@pytest.mark.asyncio
async def test_get_pinned_memory_ids_collection() -> None:
    mock_db = AsyncMock()
    mock_manager = AsyncMock()

    class MockMemory:
        def __init__(self, mem_id: str, pinned: bool = False, is_pinned: bool = False) -> None:
            self.id = mem_id
            self.pinned = pinned
            self.is_pinned = is_pinned

    def mock_list(mem_type: MemoryType, **kwargs: object) -> list[MockMemory]:
        if mem_type == MemoryType.SEMANTIC:
            return [MockMemory("sem_pinned_01", pinned=True), MockMemory("sem_unpinned_02", pinned=False)]
        elif mem_type == MemoryType.EPISODIC:
            return [MockMemory("epi_pinned_03", is_pinned=True)]
        elif mem_type == MemoryType.PROCEDURAL:
            return [MockMemory("proc_pinned_04", pinned=True)]
        return []

    mock_manager.list_memories.side_effect = mock_list
    service = MemoryCommandCenterService(mock_db, memory_manager=mock_manager)

    pinned_ids = await service.get_pinned_memory_ids()
    assert pinned_ids == {"sem_pinned_01", "epi_pinned_03", "proc_pinned_04"}


@pytest.mark.asyncio
async def test_backward_model_rate_scan_with_trailing_user_message() -> None:
    mock_db = AsyncMock()
    now = datetime.now(UTC)

    # Preceding message is assistant with deepseek model
    msg_assistant = Message(
        id="msg_asst_01",
        chat_id="sess_scan",
        role="assistant",
        content="Assistant generated reply",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        extra_data={
            "model": "deepseek-reasoner",
            "usage": {"prompt_tokens": 800, "cached_tokens": 600, "completion_tokens": 100},
            "memory_telemetry": {
                "injected_memory_tokens": 100,
                "retrieval_ms": 10.0,
                "construction_ms": 20.0,
                "cache_aligned": True,
            },
            "injected_memory_ids": ["mem_dormant_01"],
            "citations": [],
        },
    )

    # Trailing message is user input without any model metadata
    msg_user = Message(
        id="msg_user_02",
        chat_id="sess_scan",
        role="user",
        content="Next user instruction",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        extra_data={},
    )

    mock_result = MagicMock()
    # Query returns 3 assistant messages (to trigger parasitic >= 3 threshold) followed by trailing user message
    mock_result.scalars.return_value.all.return_value = [msg_assistant, msg_assistant, msg_assistant, msg_user]
    mock_db.execute.return_value = mock_result

    service = MemoryEconomicsService(mock_db)
    previews = {"mem_dormant_01": ("Dormant rule", "semantic")}
    dashboard = await service.build_economics_dashboard(
        influence=[],
        session_id="sess_scan",
        memory_previews=previews,
        limit_turns=10,
    )

    # Even though messages[-1] has no model, backward scan successfully finds deepseek
    assert len(dashboard.parasitic_memories) == 1
    wasted = dashboard.parasitic_memories[0].wasted_tokens_estimated
    expected_savings = round((wasted / 1_000_000.0) * 0.28, 4)
    assert dashboard.estimated_cost_savings_usd == expected_savings
