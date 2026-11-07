"""Edge-case unit tests for pattern discovery strategy branches.

Complements ``test_pattern_discovery.py`` (schema/prompt alignment) by covering
the strategy's decision paths that do not need a real LLM: maturity-gate
variants, consolidation counter, LLM failure degradation, confidence filtering,
ProceduralRule promotion criteria, and the recent-pattern read helper.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import (
    _PROFILE_KEY_CONSOLIDATION_COUNT,
    _is_promotable_to_rule,
    get_recent_patterns,
    increment_consolidation_count,
    run_pattern_discovery,
    should_run_pattern_discovery,
)
from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery_models import (
    DiscoveredPattern,
    PatternDiscoveryResponse,
    PatternDurability,
)
from myrm_agent_harness.toolkits.memory.types import SemanticMemory


def _mature_manager(**overrides: object) -> AsyncMock:
    """Manager stub that passes the maturity gate by default."""
    manager = AsyncMock()
    manager.has_relational = True
    manager.has_vector = True
    manager.has_graph = False
    manager.count_memories = AsyncMock(side_effect=lambda mt: 60)
    manager.search = AsyncMock(return_value=[])
    manager.add_event = AsyncMock()
    manager.store = AsyncMock(return_value=SimpleNamespace(id="stored-rule"))
    for key, value in overrides.items():
        setattr(manager, key, value)
    return manager


def _memories(count: int) -> list[SemanticMemory]:
    return [SemanticMemory(content=f"reference note {i}: design rationale", tags=["reference"]) for i in range(count)]


def _structured_llm(response: object, *, raises: BaseException | None = None) -> MagicMock:
    """LLM stub whose synchronous ``with_structured_output`` returns an awaitable.

    ``run_pattern_discovery`` calls ``llm.with_structured_output(...)``
    synchronously and then awaits ``structured.ainvoke(...)``, so the outer mock
    must be sync while the inner ``ainvoke`` is a real AsyncMock.
    """
    llm = MagicMock()
    structured = AsyncMock()
    structured.ainvoke = AsyncMock(return_value=response) if raises is None else AsyncMock(side_effect=raises)
    llm.with_structured_output = MagicMock(return_value=structured)
    return llm


class TestShouldRunPatternDiscovery:
    @pytest.mark.asyncio
    async def test_skips_without_vector(self) -> None:
        manager = _mature_manager(has_vector=False)
        assert await should_run_pattern_discovery(manager) is False

    @pytest.mark.asyncio
    async def test_skips_without_relational(self) -> None:
        manager = _mature_manager(has_relational=False)
        assert await should_run_pattern_discovery(manager) is False

    @pytest.mark.asyncio
    async def test_skips_when_consolidation_count_low(self, bookkeeping_rows: dict[str, str]) -> None:
        bookkeeping_rows[_PROFILE_KEY_CONSOLIDATION_COUNT] = "5"
        assert await should_run_pattern_discovery(_mature_manager()) is True

        bookkeeping_rows[_PROFILE_KEY_CONSOLIDATION_COUNT] = "2"
        assert await should_run_pattern_discovery(_mature_manager()) is False

    @pytest.mark.asyncio
    async def test_passes_when_mature(self, bookkeeping_rows: dict[str, str]) -> None:
        bookkeeping_rows[_PROFILE_KEY_CONSOLIDATION_COUNT] = "5"
        assert await should_run_pattern_discovery(_mature_manager()) is True


class TestIncrementConsolidationCount:
    @pytest.mark.asyncio
    async def test_skips_without_relational(self, bookkeeping_rows: dict[str, str]) -> None:
        await increment_consolidation_count(_mature_manager(has_relational=False))
        assert bookkeeping_rows == {}

    @pytest.mark.asyncio
    async def test_increments_existing_count(self, bookkeeping_rows: dict[str, str]) -> None:
        bookkeeping_rows[_PROFILE_KEY_CONSOLIDATION_COUNT] = "5"
        await increment_consolidation_count(_mature_manager())
        assert bookkeeping_rows == {_PROFILE_KEY_CONSOLIDATION_COUNT: "6"}

    @pytest.mark.asyncio
    async def test_starts_at_one_when_no_count(self, bookkeeping_rows: dict[str, str]) -> None:
        await increment_consolidation_count(_mature_manager())
        assert bookkeeping_rows == {_PROFILE_KEY_CONSOLIDATION_COUNT: "1"}


class TestRunPatternDiscoveryLLMFailure:
    @pytest.mark.asyncio
    async def test_llm_exception_becomes_skipped_report(self, bookkeeping_rows: dict[str, str]) -> None:
        bookkeeping_rows[_PROFILE_KEY_CONSOLIDATION_COUNT] = "5"
        memories = _memories(5)
        manager = _mature_manager()
        manager.list_memories = AsyncMock(return_value=memories)
        llm = _structured_llm(None, raises=RuntimeError("provider down"))

        report = await run_pattern_discovery(manager, llm)

        assert report.skipped is True
        assert "LLM call failed" in report.skip_reason
        # Two MemoryType passes (SEMANTIC + EPISODIC) each list the 5 memories.
        assert report.memory_count == 10
        assert report.duration_ms > 0


class TestRunPatternDiscoveryFiltering:
    @pytest.mark.asyncio
    async def test_low_confidence_patterns_filtered_out(self, bookkeeping_rows: dict[str, str]) -> None:
        bookkeeping_rows[_PROFILE_KEY_CONSOLIDATION_COUNT] = "5"
        memories = _memories(5)
        manager = _mature_manager()
        manager.list_memories = AsyncMock(return_value=memories)
        response = PatternDiscoveryResponse(
            patterns=[
                _pattern(title="kept", confidence=0.8),
                _pattern(title="dropped", confidence=0.4),
                _pattern(title="boundary", confidence=0.5),
            ]
        )
        report = await run_pattern_discovery(manager, _structured_llm(response))

        titles = [p.title for p in report.patterns]
        assert titles == ["kept", "boundary"]


def _pattern(*, title: str, confidence: float) -> object:
    return DiscoveredPattern(
        title=title,
        description="desc",
        evidence_summary="evidence",
        confidence=confidence,
        actionable_suggestion="suggestion",
    )


class TestIsPromotableToRule:
    def test_established_high_confidence_with_suggestion_promotes(self) -> None:
        pattern = _pattern(title="habit", confidence=0.9)
        pattern.durability = PatternDurability.ESTABLISHED
        assert _is_promotable_to_rule(pattern) is True

    def test_emerging_never_promotes(self) -> None:
        pattern = _pattern(title="new", confidence=0.95)
        assert _is_promotable_to_rule(pattern) is False

    def test_low_confidence_never_promotes(self) -> None:
        pattern = _pattern(title="weak", confidence=0.7)
        pattern.durability = PatternDurability.ESTABLISHED
        assert _is_promotable_to_rule(pattern) is False

    def test_empty_suggestion_never_promotes(self) -> None:
        pattern = DiscoveredPattern(
            title="no-action",
            description="knowledge evolution",
            evidence_summary="evidence",
            confidence=0.95,
            actionable_suggestion="   ",
        )
        pattern.durability = PatternDurability.ESTABLISHED
        assert _is_promotable_to_rule(pattern) is False


class TestGetRecentPatterns:
    @pytest.mark.asyncio
    async def test_returns_empty_without_vector(self) -> None:
        manager = _mature_manager(has_vector=False)
        assert await get_recent_patterns(manager) == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_scroll_fails(self) -> None:
        class _BrokenVector:
            async def scroll(self, *_args: object, **_kwargs: object) -> object:
                raise RuntimeError("vector down")

        manager = _mature_manager()
        manager._vector = _BrokenVector()
        assert await get_recent_patterns(manager) == []

    @pytest.mark.asyncio
    async def test_returns_scrolled_contents(self) -> None:
        class _FakeVector:
            async def scroll(self, *_args: object, **_kwargs: object) -> tuple[list[object], object]:
                return [SimpleNamespace(content="pattern a"), SimpleNamespace(content="pattern b")], None

        manager = _mature_manager()
        manager._vector = _FakeVector()
        assert await get_recent_patterns(manager, limit=2) == ["pattern a", "pattern b"]
