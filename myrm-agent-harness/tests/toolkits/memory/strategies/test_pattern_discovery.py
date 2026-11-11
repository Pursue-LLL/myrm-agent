"""Tests for cross-cycle pattern discovery strategy."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import (
    _compute_memory_set_hash,
    get_recent_patterns,
    increment_consolidation_count,
    run_pattern_discovery,
    should_run_pattern_discovery,
)
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery_models import (
    DiscoveredPattern,
    PatternDiscoveryResponse,
    PatternDurability,
    PatternReport,
)
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery_prompts import _build_discovery_prompt


@pytest.fixture
def mock_manager() -> AsyncMock:
    manager = AsyncMock()
    manager.has_relational = True
    manager.has_vector = True
    manager.has_graph = False
    manager._vector = AsyncMock()
    manager._graph = None
    manager._config = MagicMock()
    manager._config.episodic_collection = "episodic"
    return manager


@pytest.fixture
def mock_llm() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def sample_pattern() -> DiscoveredPattern:
    return DiscoveredPattern(
        title="Late night coding",
        description="User tends to code after 11 PM",
        evidence_summary="Multiple sessions at 23:00-02:00",
        durability=PatternDurability.ESTABLISHED,
        confidence=0.85,
        actionable_suggestion="Consider scheduling breaks",
    )


def _make_memory(mem_id: str, content: str = "test") -> MagicMock:
    mem = MagicMock()
    mem.id = mem_id
    mem.content = content
    mem.memory_type = "semantic"
    mem.created_at = datetime(2026, 5, 1, tzinfo=UTC)
    mem.source_chat_id = None
    mem.source_chat_ids = []
    return mem


class TestPatternDurability:
    def test_values(self):
        assert PatternDurability.EMERGING == "emerging"
        assert PatternDurability.ESTABLISHED == "established"
        assert PatternDurability.DECLINING == "declining"


class TestDiscoveredPattern:
    def test_defaults(self):
        p = DiscoveredPattern(
            title="Test",
            description="Desc",
            evidence_summary="Evidence",
        )
        assert p.durability == PatternDurability.EMERGING
        assert p.confidence == 0.7
        assert p.actionable_suggestion == ""

    def test_full(self, sample_pattern: DiscoveredPattern):
        assert sample_pattern.confidence == 0.85
        assert sample_pattern.durability == PatternDurability.ESTABLISHED


class TestPatternReport:
    def test_empty_report(self):
        r = PatternReport()
        assert r.has_patterns is False
        assert r.skipped is False

    def test_skipped_report(self):
        r = PatternReport(skipped=True, skip_reason="not mature")
        assert r.skipped is True
        assert r.has_patterns is False

    def test_with_patterns(self, sample_pattern: DiscoveredPattern):
        r = PatternReport(patterns=(sample_pattern,))
        assert r.has_patterns is True
        assert len(r.patterns) == 1

    def test_to_dict(self, sample_pattern: DiscoveredPattern):
        r = PatternReport(
            patterns=(sample_pattern,),
            meta_observation="trajectory",
            memory_count=100,
            insight_count=5,
        )
        d = r.to_dict()
        assert len(d["patterns"]) == 1
        assert d["meta_observation"] == "trajectory"
        assert d["memory_count"] == 100
        assert d["insight_count"] == 5
        assert d["skipped"] is False


class TestShouldRunPatternDiscovery:
    @pytest.mark.asyncio
    async def test_no_relational(self, mock_manager: AsyncMock):
        mock_manager.has_relational = False
        assert await should_run_pattern_discovery(mock_manager) is False

    @pytest.mark.asyncio
    async def test_no_vector(self, mock_manager: AsyncMock):
        mock_manager.has_vector = False
        assert await should_run_pattern_discovery(mock_manager) is False

    @pytest.mark.asyncio
    async def test_below_memory_threshold(self, mock_manager: AsyncMock):
        mock_manager.count_memories = AsyncMock(return_value=10)
        assert await should_run_pattern_discovery(mock_manager) is False

    @pytest.mark.asyncio
    async def test_below_consolidation_threshold(self, mock_manager: AsyncMock, bookkeeping_rows: dict[str, str]):
        mock_manager.count_memories = AsyncMock(return_value=60)
        bookkeeping_rows["_system.consolidation_count"] = "1"
        assert await should_run_pattern_discovery(mock_manager) is False

    @pytest.mark.asyncio
    async def test_all_conditions_met(self, mock_manager: AsyncMock, bookkeeping_rows: dict[str, str]):
        mock_manager.count_memories = AsyncMock(return_value=60)
        bookkeeping_rows["_system.consolidation_count"] = "5"
        assert await should_run_pattern_discovery(mock_manager) is True

    @pytest.mark.asyncio
    async def test_no_consolidation_count(self, mock_manager: AsyncMock, bookkeeping_rows: dict[str, str]):
        mock_manager.count_memories = AsyncMock(return_value=60)
        assert bookkeeping_rows == {}
        assert await should_run_pattern_discovery(mock_manager) is False


class TestIncrementConsolidationCount:
    @pytest.mark.asyncio
    async def test_increment_from_zero(self, mock_manager: AsyncMock, bookkeeping_rows: dict[str, str]):
        await increment_consolidation_count(mock_manager)
        assert bookkeeping_rows == {"_system.consolidation_count": "1"}

    @pytest.mark.asyncio
    async def test_increment_existing(self, mock_manager: AsyncMock, bookkeeping_rows: dict[str, str]):
        bookkeeping_rows["_system.consolidation_count"] = "3"
        await increment_consolidation_count(mock_manager)
        assert bookkeeping_rows == {"_system.consolidation_count": "4"}

    @pytest.mark.asyncio
    async def test_skip_no_relational(self, mock_manager: AsyncMock, bookkeeping_rows: dict[str, str]):
        mock_manager.has_relational = False
        await increment_consolidation_count(mock_manager)
        assert bookkeeping_rows == {}


class TestComputeMemorySetHash:
    def test_deterministic(self):
        memories = [_make_memory("a"), _make_memory("b"), _make_memory("c")]
        h1 = _compute_memory_set_hash(memories)
        h2 = _compute_memory_set_hash(memories)
        assert h1 == h2

    def test_order_independent(self):
        m1 = [_make_memory("a"), _make_memory("b")]
        m2 = [_make_memory("b"), _make_memory("a")]
        assert _compute_memory_set_hash(m1) == _compute_memory_set_hash(m2)

    def test_different_sets_different_hash(self):
        m1 = [_make_memory("a"), _make_memory("b")]
        m2 = [_make_memory("a"), _make_memory("c")]
        assert _compute_memory_set_hash(m1) != _compute_memory_set_hash(m2)

    def test_hash_length(self):
        h = _compute_memory_set_hash([_make_memory("x")])
        assert len(h) == 16


class TestBuildDiscoveryPrompt:
    def test_basic_prompt(self):
        memories = [_make_memory("1", "I like Python")]
        prompt = _build_discovery_prompt(memories, [], [], "2026-05-19")
        assert "2026-05-19" in prompt
        assert "I like Python" in prompt
        assert "Recent Memories" in prompt

    def test_with_insights_and_claims(self):
        memories = [_make_memory("1", "content")]
        insights = ["insight one"]
        claims = ["claim one"]
        prompt = _build_discovery_prompt(memories, insights, claims, "2026-05-19")
        assert "Consolidation Insights" in prompt
        assert "insight one" in prompt
        assert "Knowledge Claims" in prompt
        assert "claim one" in prompt

    def test_memory_content_truncated(self):
        long_content = "x" * 500
        memories = [_make_memory("1", long_content)]
        prompt = _build_discovery_prompt(memories, [], [], "2026-05-19")
        assert len(long_content) > 200
        assert "x" * 200 in prompt


class TestRunPatternDiscovery:
    @pytest.mark.asyncio
    async def test_skip_immature(self, mock_manager: AsyncMock, mock_llm: AsyncMock):
        mock_manager.count_memories = AsyncMock(return_value=10)
        report = await run_pattern_discovery(mock_manager, mock_llm)
        assert report.skipped is True
        assert "mature" in report.skip_reason

    @pytest.mark.asyncio
    async def test_skip_unchanged_hash(
        self, mock_manager: AsyncMock, mock_llm: AsyncMock, bookkeeping_rows: dict[str, str]
    ):
        memories = [_make_memory(f"m{i}") for i in range(60)]
        mock_manager.count_memories = AsyncMock(return_value=60)
        mock_manager.list_memories = AsyncMock(return_value=memories)

        bookkeeping_rows["_system.consolidation_count"] = "5"
        bookkeeping_rows["_system.pattern_discovery_memory_hash"] = _compute_memory_set_hash(memories + memories)

        report = await run_pattern_discovery(mock_manager, mock_llm)
        assert report.skipped is True
        assert "unchanged" in report.skip_reason
        mock_llm.with_structured_output.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_discovery(
        self, mock_manager: AsyncMock, mock_llm: AsyncMock, bookkeeping_rows: dict[str, str]
    ):
        memories = [_make_memory(f"m{i}") for i in range(60)]
        mock_manager.count_memories = AsyncMock(return_value=60)
        mock_manager.list_memories = AsyncMock(return_value=memories)
        bookkeeping_rows["_system.consolidation_count"] = "5"
        mock_manager.search = AsyncMock(return_value=[])

        pattern_response = PatternDiscoveryResponse(
            patterns=[
                DiscoveredPattern(
                    title="Late night coding",
                    description="User codes late",
                    evidence_summary="11PM sessions",
                    confidence=0.9,
                ),
            ],
            meta_observation="Active developer",
        )
        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(return_value=pattern_response)
        mock_llm.with_structured_output = MagicMock(return_value=structured_llm)

        report = await run_pattern_discovery(mock_manager, mock_llm)
        assert report.skipped is False
        assert report.has_patterns is True
        assert len(report.patterns) == 1
        assert report.patterns[0].title == "Late night coding"
        assert report.meta_observation == "Active developer"
        mock_manager.store.assert_awaited_once()
        assert bookkeeping_rows["_system.pattern_discovery_memory_hash"] == _compute_memory_set_hash(
            memories + memories
        )

    @pytest.mark.asyncio
    async def test_low_confidence_filtered(
        self, mock_manager: AsyncMock, mock_llm: AsyncMock, bookkeeping_rows: dict[str, str]
    ):
        memories = [_make_memory(f"m{i}") for i in range(60)]
        mock_manager.count_memories = AsyncMock(return_value=60)
        mock_manager.list_memories = AsyncMock(return_value=memories)
        bookkeeping_rows["_system.consolidation_count"] = "5"
        mock_manager.search = AsyncMock(return_value=[])

        pattern_response = PatternDiscoveryResponse(
            patterns=[
                DiscoveredPattern(
                    title="Low confidence",
                    description="Weak",
                    evidence_summary="Maybe",
                    confidence=0.3,
                ),
            ],
        )
        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(return_value=pattern_response)
        mock_llm.with_structured_output = MagicMock(return_value=structured_llm)

        report = await run_pattern_discovery(mock_manager, mock_llm)
        assert report.has_patterns is False
        mock_manager.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_failure(self, mock_manager: AsyncMock, mock_llm: AsyncMock, bookkeeping_rows: dict[str, str]):
        memories = [_make_memory(f"m{i}") for i in range(60)]
        mock_manager.count_memories = AsyncMock(return_value=60)
        mock_manager.list_memories = AsyncMock(return_value=memories)
        bookkeeping_rows["_system.consolidation_count"] = "5"
        mock_manager.search = AsyncMock(return_value=[])

        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM error"))
        mock_llm.with_structured_output = MagicMock(return_value=structured_llm)

        report = await run_pattern_discovery(mock_manager, mock_llm)
        assert report.skipped is True
        assert "LLM call failed" in report.skip_reason


class TestGetRecentPatterns:
    @pytest.mark.asyncio
    async def test_no_vector(self, mock_manager: AsyncMock):
        mock_manager.has_vector = False
        assert await get_recent_patterns(mock_manager) == []

    @pytest.mark.asyncio
    async def test_with_results(self, mock_manager: AsyncMock):
        doc = MagicMock()
        doc.content = "[established] Late coding: User codes late"
        mock_manager._vector.scroll = AsyncMock(return_value=([doc], None))
        result = await get_recent_patterns(mock_manager, limit=3)
        assert len(result) == 1
        assert "Late coding" in result[0]

    @pytest.mark.asyncio
    async def test_empty_content_filtered(self, mock_manager: AsyncMock):
        doc = MagicMock()
        doc.content = ""
        mock_manager._vector.scroll = AsyncMock(return_value=([doc], None))
        result = await get_recent_patterns(mock_manager)
        assert result == []

    @pytest.mark.asyncio
    async def test_scroll_failure(self, mock_manager: AsyncMock):
        mock_manager._vector.scroll = AsyncMock(side_effect=RuntimeError("fail"))
        result = await get_recent_patterns(mock_manager)
        assert result == []
