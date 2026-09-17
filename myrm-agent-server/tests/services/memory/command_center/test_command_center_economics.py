"""Tests for MemoryEconomicsService and Omri et al. 2026 telemetry in server."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.models.chat import Message
from app.services.memory.command_center.command_center_economics import (
    MemoryEconomicsService,
    classify_roi_grade,
    estimate_memory_tokens_safe,
)


def test_estimate_memory_tokens_safe_accuracy() -> None:
    # Legacy split() would return 1 for CJK sentence
    cjk_text = "我喜欢使用Python与FastAPI开发高性能AI智能体系统。"
    legacy_split_tokens = len(cjk_text.split())
    assert legacy_split_tokens == 1

    # Our safe estimator properly accounts for CJK characters
    safe_tokens = estimate_memory_tokens_safe(cjk_text)
    assert safe_tokens > 20

    # Code and English words
    code_text = "def build_cost_profile(influence: list[Item]) -> CostProfile:"
    code_tokens = estimate_memory_tokens_safe(code_text)
    assert code_tokens >= 8

    # Empty string safety
    assert estimate_memory_tokens_safe("") == 0


def test_classify_roi_grade() -> None:
    assert classify_roi_grade(65.0) == "optimal"
    assert classify_roi_grade(35.0) == "healthy"
    assert classify_roi_grade(15.0) == "diluted"
    assert classify_roi_grade(4.0) == "critical"


@pytest.mark.asyncio
async def test_build_economics_dashboard_with_turns() -> None:
    mock_db = AsyncMock()

    now = datetime.now(UTC)
    # Create 2 mock turns with valid Message schema
    msg1 = Message(
        id="msg_001",
        chat_id="sess_100",
        role="assistant",
        content="Testing memory turn 1",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        extra_data={
            "usage": {"prompt_tokens": 1000, "cached_tokens": 800, "completion_tokens": 150},
            "memory_telemetry": {
                "injected_memory_tokens": 200,
                "retrieval_ms": 45.0,
                "construction_ms": 120.0,
                "cache_aligned": True,
            },
            "injected_memory_ids": ["mem_useful_1", "mem_stale_1"],
            "citations": [{"id": "mem_useful_1", "content": "Keep functions under 400 lines", "type": "procedural"}],
        },
    )
    msg2 = Message(
        id="msg_002",
        chat_id="sess_100",
        role="assistant",
        content="Testing memory turn 2",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        extra_data={
            "usage": {"prompt_tokens": 1200, "cached_tokens": 900, "completion_tokens": 200},
            "memory_telemetry": {
                "injected_memory_tokens": 200,
                "retrieval_ms": 35.0,
                "construction_ms": 80.0,
                "cache_aligned": True,
            },
            "injected_memory_ids": ["mem_useful_1", "mem_stale_1", "mem_profile_exempt"],
            "citations": [
                {"id": "mem_useful_1", "content": "Keep functions under 400 lines", "type": "procedural"},
                {"id": "mem_profile_exempt", "content": "User prefers Python 3.12 PEP8", "type": "profile"},
            ],
        },
    )
    msg3 = Message(
        id="msg_003",
        chat_id="sess_100",
        role="assistant",
        content="Testing memory turn 3",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        extra_data={
            "usage": {"prompt_tokens": 1100, "cached_tokens": 900, "completion_tokens": 180},
            "memory_telemetry": {
                "injected_memory_tokens": 200,
                "retrieval_ms": 40.0,
                "construction_ms": 70.0,
                "cache_aligned": True,
            },
            "injected_memory_ids": ["mem_useful_1", "mem_stale_1", "mem_profile_exempt"],
            "citations": [{"id": "mem_useful_1", "content": "Keep functions under 400 lines", "type": "procedural"}],
        },
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [msg3, msg2, msg1]
    mock_db.execute.return_value = mock_result

    service = MemoryEconomicsService(mock_db)
    dashboard = await service.build_economics_dashboard(
        influence=[],
        session_id="sess_100",
        limit_turns=10,
    )

    # Validate cost profile
    cost = dashboard.cost_profile
    assert cost.prompt_tokens == 3300
    assert cost.cached_tokens == 2600
    assert cost.cache_friendly is True
    assert cost.retrieval_ms == 40.0  # (45 + 35 + 40) / 3
    assert cost.cache_preservation_score > 0.7

    # Validate turn trajectories
    assert len(dashboard.turn_trajectories) == 3

    # Validate parasitic memory identification:
    # mem_stale_1 was injected in 3 turns but cited in 0 turns -> parasitic
    # mem_profile_exempt is type "profile" -> whitelisted/exempt even if unreferenced in msg1/msg3
    assert len(dashboard.parasitic_memories) == 1
    assert dashboard.parasitic_memories[0].memory_id == "mem_stale_1"
    assert dashboard.parasitic_memories[0].injected_turns_count == 3
    assert dashboard.parasitic_memories[0].cited_turns_count == 0
    assert dashboard.parasitic_memories[0].suggested_action == "archive"

    # Validate recommendations and savings estimate
    assert any("沉睡记忆" in r for r in dashboard.recommendations)


@pytest.mark.asyncio
async def test_pinned_memory_is_exempt_from_parasitic() -> None:
    """Ensure pinned memories are strictly exempted from parasitic marking even if uncited."""
    mock_db = AsyncMock()
    now = datetime.now(UTC)

    # 3 turns with an uncited memory that is pinned
    msg = Message(
        id="msg_pinned",
        chat_id="sess_pin",
        role="assistant",
        content="Testing pinned exemption",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        extra_data={
            "usage": {"prompt_tokens": 1000, "cached_tokens": 800, "completion_tokens": 100},
            "memory_telemetry": {"injected_memory_tokens": 150, "retrieval_ms": 20.0, "pinned_memory_ids": ["mem_pinned_rule_1"]},
            "injected_memory_ids": ["mem_pinned_rule_1"],
            "citations": [],
        },
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [msg, msg, msg]
    mock_db.execute.return_value = mock_result

    service = MemoryEconomicsService(mock_db)
    dashboard = await service.build_economics_dashboard(
        influence=[],
        session_id="sess_pin",
        limit_turns=10,
    )

    # mem_pinned_rule_1 was injected 3 times and cited 0 times, but is pinned -> 0 parasitic memories!
    assert len(dashboard.parasitic_memories) == 0


@pytest.mark.asyncio
async def test_archived_memory_is_exempt_from_parasitic() -> None:
    """Ensure already archived memories are strictly excluded from parasitic recommendations."""
    mock_db = AsyncMock()
    now = datetime.now(UTC)

    # 3 turns with an uncited memory that was subsequently archived
    msg = Message(
        id="msg_archived",
        chat_id="sess_arch",
        role="assistant",
        content="Testing archived exemption",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        extra_data={
            "usage": {"prompt_tokens": 1000, "cached_tokens": 800, "completion_tokens": 100},
            "memory_telemetry": {"injected_memory_tokens": 150, "retrieval_ms": 20.0},
            "injected_memory_ids": ["mem_old_stale_archived"],
            "citations": [],
        },
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [msg, msg, msg]
    mock_db.execute.return_value = mock_result

    service = MemoryEconomicsService(mock_db)

    # 1. Without passing archived_memory_ids, mem_old_stale_archived is detected as parasitic
    unfiltered = await service.build_economics_dashboard(
        influence=[],
        session_id="sess_arch",
        limit_turns=10,
    )
    assert len(unfiltered.parasitic_memories) == 1
    assert unfiltered.parasitic_memories[0].memory_id == "mem_old_stale_archived"

    # 2. When archived_memory_ids includes mem_old_stale_archived, it is strictly filtered out!
    filtered = await service.build_economics_dashboard(
        influence=[],
        session_id="sess_arch",
        archived_memory_ids=["mem_old_stale_archived"],
        limit_turns=10,
    )
    assert len(filtered.parasitic_memories) == 0


@pytest.mark.asyncio
async def test_archived_memory_in_turn_telemetry_is_exempt() -> None:
    """Ensure memories recorded as archived in turn metadata are automatically exempted."""
    mock_db = AsyncMock()
    now = datetime.now(UTC)

    msg = Message(
        id="msg_turn_arch",
        chat_id="sess_turn_arch",
        role="assistant",
        content="Testing turn telemetry archived exemption",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        extra_data={
            "usage": {"prompt_tokens": 1000, "cached_tokens": 800, "completion_tokens": 100},
            "memory_telemetry": {
                "injected_memory_tokens": 150,
                "retrieval_ms": 20.0,
                "archived_memory_ids": ["mem_forgotten_in_turn"],
            },
            "injected_memory_ids": ["mem_forgotten_in_turn"],
            "citations": [],
        },
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [msg, msg, msg]
    mock_db.execute.return_value = mock_result

    service = MemoryEconomicsService(mock_db)
    dashboard = await service.build_economics_dashboard(
        influence=[],
        session_id="sess_turn_arch",
        limit_turns=10,
    )

    assert len(dashboard.parasitic_memories) == 0


@pytest.mark.asyncio
async def test_parasitic_memory_resolves_real_preview_and_accurate_tokens() -> None:
    mock_db = AsyncMock()
    now = datetime.now(UTC)

    msg = Message(
        id="msg_parasitic_prev",
        chat_id="sess_parasitic_prev",
        role="assistant",
        content="Testing real preview resolution for parasitic memory",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        extra_data={
            "usage": {"prompt_tokens": 1000, "cached_tokens": 800, "completion_tokens": 100},
            "memory_telemetry": {
                "injected_memory_tokens": 150,
                "retrieval_ms": 20.0,
                "injection_overhead_ms": 2.4,
            },
            "injected_memory_ids": ["mem_uncited_long_sql"],
            "citations": [],
        },
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [msg, msg, msg]
    mock_db.execute.return_value = mock_result

    service = MemoryEconomicsService(mock_db)
    previews = {
        "mem_uncited_long_sql": (
            "SELECT * FROM order_events WHERE status = 'failed' AND retry_count > 3",
            "episodic",
        )
    }
    dashboard = await service.build_economics_dashboard(
        influence=[],
        session_id="sess_parasitic_prev",
        memory_previews=previews,
        limit_turns=10,
    )

    assert len(dashboard.parasitic_memories) == 1
    item = dashboard.parasitic_memories[0]
    assert item.memory_id == "mem_uncited_long_sql"
    assert item.memory_type == "episodic"
    assert "SELECT * FROM order_events" in item.content_preview
    assert item.wasted_tokens_estimated >= 30
    assert dashboard.cost_profile.injection_overhead_ms == 2.4


@pytest.mark.asyncio
async def test_build_economics_dashboard_model_adaptive_rate() -> None:
    mock_db = AsyncMock()
    now = datetime.now(UTC)
    msg = Message(
        id="msg_deepseek_01",
        chat_id="sess_deepseek",
        role="assistant",
        content="DeepSeek output",
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        extra_data={
            "model": "deepseek-chat",
            "usage": {"prompt_tokens": 500, "cached_tokens": 400, "completion_tokens": 50},
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
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [msg, msg, msg]
    mock_db.execute.return_value = mock_result

    service = MemoryEconomicsService(mock_db)
    previews = {"mem_dormant_01": ("Some dormant memory snippet", "semantic")}
    dashboard = await service.build_economics_dashboard(
        influence=[],
        session_id="sess_deepseek",
        memory_previews=previews,
        limit_turns=10,
    )
    assert len(dashboard.parasitic_memories) == 1
    # DeepSeek rate is 0.28 per 1M tokens instead of standard 3.0
    wasted = dashboard.parasitic_memories[0].wasted_tokens_estimated
    expected_savings = round((wasted / 1_000_000.0) * 0.28, 4)
    assert dashboard.estimated_cost_savings_usd == expected_savings


@pytest.mark.asyncio
async def test_get_active_memory_previews_procedural() -> None:
    from myrm_agent_harness.toolkits.memory import MemoryType

    from app.services.memory.command_center.command_center import MemoryCommandCenterService

    mock_db = AsyncMock()
    mock_manager = AsyncMock()

    class MockRule:
        id = "rule_001"
        status = "active"
        content = ""
        trigger = "User requests refactor"
        action = "Run tests before and after"

    mock_manager.list_memories.side_effect = lambda mem_type, **kw: [MockRule()] if mem_type == MemoryType.PROCEDURAL else []

    service = MemoryCommandCenterService(mock_db, memory_manager=mock_manager)
    previews = await service.get_active_memory_previews()

    assert "rule_001" in previews
    preview_text, mem_type = previews["rule_001"]
    assert mem_type == "procedural"
    assert preview_text == "User requests refactor -> Run tests before and after"
