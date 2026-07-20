"""Unit tests for get_taste_summary() — preference facets aggregation.

Validates that the taste summary API correctly:
1. Reads profile attributes (reply_style, technical_depth, proactivity)
2. Aggregates active/provisional facets by category into keyword lists
3. Builds natural-language summary from aggregated keywords
4. Handles edge cases (no strategy, empty facets, exceptions)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.memory.operations.crud.preferences import (
    _build_taste_summary,
    get_taste_summary,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@dataclass
class FakeFacet:
    key: str = ""
    value: str = ""
    category: object = None
    lifecycle: object = None
    user_forgotten: bool = False
    id: str = "test-id"
    stability: float = 0.8
    cue: object = None
    evidence_count: int = 1
    memory_ids: list[str] = field(default_factory=list)
    first_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    user_pinned: bool = False


def _make_manager(
    facets: list[FakeFacet] | None = None,
    profile_attrs: dict[str, str | None] | None = None,
    strategy_available: bool = True,
) -> MagicMock:
    manager = MagicMock()

    attrs = profile_attrs or {}

    async def mock_get_profile(attr_name: str) -> str | None:
        return attrs.get(attr_name)

    manager.get_profile_attribute = AsyncMock(side_effect=mock_get_profile)

    if strategy_available and facets is not None:
        store = MagicMock()
        store.list_all = AsyncMock(return_value=facets)
        strategy = MagicMock()
        strategy._store = store
        manager._preference_strategy = strategy
    elif not strategy_available:
        manager._preference_strategy = None
    else:
        store = MagicMock()
        store.list_all = AsyncMock(return_value=[])
        strategy = MagicMock()
        strategy._store = store
        manager._preference_strategy = strategy

    return manager


# ── Tests: _build_taste_summary ───────────────────────────────────────


class TestBuildTasteSummary:
    def test_all_empty(self) -> None:
        assert _build_taste_summary([], [], [], []) == ""

    def test_style_only(self) -> None:
        result = _build_taste_summary(["concise", "formal"], [], [], [])
        assert result == "Style: concise, formal"

    def test_all_categories(self) -> None:
        result = _build_taste_summary(
            ["concise"],
            ["Python", "TypeScript"],
            ["any type"],
            ["ship v2"],
        )
        assert "Style: concise" in result
        assert "Prefers: Python, TypeScript" in result
        assert "Avoids: any type" in result
        assert "Goals: ship v2" in result

    def test_truncates_at_5(self) -> None:
        long_list = [f"item{i}" for i in range(10)]
        result = _build_taste_summary(long_list, [], [], [])
        assert "item4" in result
        assert "item5" not in result


# ── Tests: get_taste_summary ──────────────────────────────────────────


class TestGetTasteSummary:
    @pytest.mark.asyncio
    async def test_no_strategy_returns_profile_only(self) -> None:
        manager = _make_manager(
            strategy_available=False,
            profile_attrs={"reply_style": "concise", "cognitive_depth": "deep", "proactivity": "high"},
        )

        with patch(
            "app.services.memory.operations.crud.preferences.get_crud_memory_manager",
            return_value=manager,
        ):
            result = await get_taste_summary(manager=manager)

        assert result.reply_style == "concise"
        assert result.technical_depth == "deep"
        assert result.proactivity == "high"
        assert result.style_keywords == []
        assert result.preference_keywords == []
        assert result.avoid_keywords == []
        assert result.current_goals == []
        assert result.memory_count == 0

    @pytest.mark.asyncio
    async def test_facets_aggregated_by_category(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
            PreferenceCategory,
            PreferenceLifecycle,
        )

        facets = [
            FakeFacet(key="code_style", value="concise", category=PreferenceCategory.STYLE, lifecycle=PreferenceLifecycle.ACTIVE),
            FakeFacet(key="lang", value="Python", category=PreferenceCategory.TOOLING, lifecycle=PreferenceLifecycle.ACTIVE),
            FakeFacet(key="no_any", value="avoid any type", category=PreferenceCategory.VETO, lifecycle=PreferenceLifecycle.PROVISIONAL),
            FakeFacet(key="goal", value="ship v2", category=PreferenceCategory.GOAL, lifecycle=PreferenceLifecycle.ACTIVE),
            FakeFacet(key="identity", value="backend dev", category=PreferenceCategory.IDENTITY, lifecycle=PreferenceLifecycle.ACTIVE),
        ]
        manager = _make_manager(facets=facets, strategy_available=True)

        result = await get_taste_summary(manager=manager)

        assert "concise" in result.style_keywords
        assert "Python" in result.preference_keywords
        assert "backend dev" in result.preference_keywords
        assert "avoid any type" in result.avoid_keywords
        assert "ship v2" in result.current_goals
        assert result.memory_count == 5

    @pytest.mark.asyncio
    async def test_forgotten_facets_excluded(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
            PreferenceCategory,
            PreferenceLifecycle,
        )

        facets = [
            FakeFacet(key="a", value="active", category=PreferenceCategory.STYLE, lifecycle=PreferenceLifecycle.ACTIVE, user_forgotten=False),
            FakeFacet(key="b", value="forgotten", category=PreferenceCategory.STYLE, lifecycle=PreferenceLifecycle.ACTIVE, user_forgotten=True),
        ]
        manager = _make_manager(facets=facets, strategy_available=True)

        result = await get_taste_summary(manager=manager)

        assert "active" in result.style_keywords
        assert "forgotten" not in result.style_keywords
        assert result.memory_count == 1

    @pytest.mark.asyncio
    async def test_candidate_and_dropped_excluded(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
            PreferenceCategory,
            PreferenceLifecycle,
        )

        facets = [
            FakeFacet(key="a", value="active_val", category=PreferenceCategory.STYLE, lifecycle=PreferenceLifecycle.ACTIVE),
            FakeFacet(key="b", value="candidate_val", category=PreferenceCategory.STYLE, lifecycle=PreferenceLifecycle.CANDIDATE),
            FakeFacet(key="c", value="dropped_val", category=PreferenceCategory.STYLE, lifecycle=PreferenceLifecycle.DROPPED),
        ]
        manager = _make_manager(facets=facets, strategy_available=True)

        result = await get_taste_summary(manager=manager)

        assert "active_val" in result.style_keywords
        assert "candidate_val" not in result.style_keywords
        assert "dropped_val" not in result.style_keywords
        assert result.memory_count == 1

    @pytest.mark.asyncio
    async def test_empty_value_uses_key(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
            PreferenceCategory,
            PreferenceLifecycle,
        )

        facets = [
            FakeFacet(key="Python", value="", category=PreferenceCategory.TOOLING, lifecycle=PreferenceLifecycle.ACTIVE),
        ]
        manager = _make_manager(facets=facets, strategy_available=True)

        result = await get_taste_summary(manager=manager)

        assert "Python" in result.preference_keywords

    @pytest.mark.asyncio
    async def test_empty_key_and_value_skipped(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
            PreferenceCategory,
            PreferenceLifecycle,
        )

        facets = [
            FakeFacet(key="", value="", category=PreferenceCategory.STYLE, lifecycle=PreferenceLifecycle.ACTIVE),
        ]
        manager = _make_manager(facets=facets, strategy_available=True)

        result = await get_taste_summary(manager=manager)

        assert result.style_keywords == []
        assert result.memory_count == 1

    @pytest.mark.asyncio
    async def test_profile_exception_does_not_break_facets(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
            PreferenceCategory,
            PreferenceLifecycle,
        )

        manager = MagicMock()
        manager.get_profile_attribute = AsyncMock(side_effect=RuntimeError("DB error"))

        facets = [
            FakeFacet(key="x", value="test_val", category=PreferenceCategory.STYLE, lifecycle=PreferenceLifecycle.ACTIVE),
        ]
        store = MagicMock()
        store.list_all = AsyncMock(return_value=facets)
        strategy = MagicMock()
        strategy._store = store
        manager._preference_strategy = strategy

        result = await get_taste_summary(manager=manager)

        assert result.reply_style is None
        assert "test_val" in result.style_keywords

    @pytest.mark.asyncio
    async def test_facets_exception_does_not_break_profile(self) -> None:
        manager = MagicMock()

        async def mock_get_profile(attr_name: str) -> str | None:
            return {"reply_style": "brief", "cognitive_depth": None, "proactivity": None}.get(attr_name)

        manager.get_profile_attribute = AsyncMock(side_effect=mock_get_profile)

        store = MagicMock()
        store.list_all = AsyncMock(side_effect=RuntimeError("Store broken"))
        strategy = MagicMock()
        strategy._store = store
        manager._preference_strategy = strategy

        result = await get_taste_summary(manager=manager)

        assert result.reply_style == "brief"
        assert result.style_keywords == []
        assert result.memory_count == 0

    @pytest.mark.asyncio
    async def test_summary_generated_from_keywords(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
            PreferenceCategory,
            PreferenceLifecycle,
        )

        facets = [
            FakeFacet(key="s", value="concise", category=PreferenceCategory.STYLE, lifecycle=PreferenceLifecycle.ACTIVE),
            FakeFacet(key="v", value="verbose code", category=PreferenceCategory.VETO, lifecycle=PreferenceLifecycle.ACTIVE),
        ]
        manager = _make_manager(facets=facets, strategy_available=True)

        result = await get_taste_summary(manager=manager)

        assert "Style: concise" in result.summary
        assert "Avoids: verbose code" in result.summary
