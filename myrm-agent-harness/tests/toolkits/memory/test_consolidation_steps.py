"""Tests for the steps a consolidation run is composed of.

Covers:
- _build_user_prompt: source_error, plain content
- _build_id_map: short-id collision extension
- _persist_insights: skips and store-error tolerance
- execute_operations: MergeOp demote failure, UpdateContentOp protected memory
- _enrich_with_similar candidate search + error fallback
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory.strategies.consolidation import (
    MergeOp,
    UpdateContentOp,
    _enrich_with_similar,
    _persist_insights,
    execute_operations,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import UndoJournal
from myrm_agent_harness.toolkits.memory.strategies.consolidation_prompts import (
    _SYSTEM_PROMPT,
    _build_id_map,
    _build_user_prompt,
)
from myrm_agent_harness.toolkits.memory.types import ClaimMemory, MemoryType, ProceduralMemory, SemanticMemory
from tests.support.consolidation_manager import make_manager


class TestBuildUserPrompt:
    def test_source_error_follows_the_content(self) -> None:
        mem = SemanticMemory(content="user prefers Rust", source_error="failed extraction attempt")
        prompt = _build_user_prompt([mem], "2026-08-15", _build_id_map([mem]))
        assert "  user prefers Rust\n  source_error: failed extraction attempt" in prompt
        assert "type=semantic" in prompt
        assert "## Memories to analyze" in prompt

    def test_the_prompt_does_not_ask_about_rules(self) -> None:
        assert "procedural" not in _SYSTEM_PROMPT

    def test_plain_content_line(self) -> None:
        mem = SemanticMemory(content="plain fact here")
        prompt = _build_user_prompt([mem], "2026-08-15", _build_id_map([mem]))
        assert "  plain fact here" in prompt
        assert prompt.endswith("Analyze these memories and output a JSON object with operations and insights.")

    def test_new_tag_applied(self) -> None:
        mem = SemanticMemory(content="fresh fact")
        id_map = _build_id_map([mem])
        prompt = _build_user_prompt([mem], "2026-08-15", id_map, new_ids=frozenset({mem.id}))
        assert " [NEW]" in prompt

    def test_memory_without_importance_confidence(self) -> None:
        minimal = SimpleNamespace(
            id="minimal-1",
            content="bare memory",
            created_at=datetime.now(UTC),
            memory_type=MemoryType.EPISODIC,
        )
        prompt = _build_user_prompt([minimal], "2026-08-15", _build_id_map([minimal]))
        assert "type=episodic" in prompt
        assert "importance" not in prompt
        assert "confidence" not in prompt

    def test_correction_of_emits_corrects_marker(self) -> None:
        original = SemanticMemory(content="original fact", id="orig-12345678")
        correction = SemanticMemory(content="corrected fact", id="corr-12345678", correction_of=original.id)
        id_map = _build_id_map([original, correction])
        prompt = _build_user_prompt([original, correction], "2026-08-15", id_map)
        assert "corrects:orig-123" in prompt


class TestPersistInsights:
    @pytest.mark.asyncio
    async def test_no_vector_skips(self) -> None:
        manager = make_manager()
        manager.has_vector = False
        await _persist_insights(manager, ["an insight"], [], UndoJournal())
        manager.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_short_insight_skipped(self) -> None:
        manager = make_manager()
        manager.store = AsyncMock()
        await _persist_insights(manager, ["too short"], [], UndoJournal())
        manager.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_store_error_is_tolerated(self) -> None:
        manager = make_manager()
        manager.store = AsyncMock(side_effect=RuntimeError("store down"))
        await _persist_insights(manager, ["this is a sufficiently long insight"], [], UndoJournal())
        manager.store.assert_awaited_once()


class TestBuildIdMap:
    def test_short_id_collision_extends(self) -> None:
        # First 8 chars identical -> second id must be extended to avoid collision.
        mem_a = SimpleNamespace(
            id="abcdefgh1111",
            content="a",
            created_at=datetime.now(UTC),
            memory_type=MemoryType.SEMANTIC,
        )
        mem_b = SimpleNamespace(
            id="abcdefgh2222",
            content="b",
            created_at=datetime.now(UTC),
            memory_type=MemoryType.SEMANTIC,
        )
        id_map = _build_id_map([mem_a, mem_b])
        assert id_map["abcdefgh"] == "abcdefgh1111"
        assert id_map["abcdefgh2222"] == "abcdefgh2222"
        assert len(id_map) == 2


class TestExecuteOperationsExtraBranches:
    @pytest.mark.asyncio
    async def test_merge_demote_failure_is_tolerated(self) -> None:
        """A failing demote must not abort the merge or bump errors."""
        manager = make_manager()
        manager.update_memory = AsyncMock(side_effect=RuntimeError("demote failed"))
        id_map = {"m1": "m1", "m2": "m2"}
        ops = [MergeOp(source_ids=["m1", "m2"], merged_content="merged", importance=0.8)]
        stats = await execute_operations(ops, manager, id_map)
        assert stats.merged == 1
        assert stats.errors == 0

    @pytest.mark.asyncio
    async def test_update_content_protected_memory_skipped(self) -> None:
        """A protected memory is refused by the manager guard and counted as a skip, not an error."""
        from myrm_agent_harness.toolkits.memory._internal.storage import MemoryProtectedError

        manager = make_manager()
        manager.update_memory = AsyncMock(side_effect=MemoryProtectedError("protected"))
        ops = [UpdateContentOp(memory_id="mem-1", new_content="new", importance=0.3)]
        stats = await execute_operations(ops, manager)
        assert stats.updated == 0
        assert stats.errors == 0
        manager.update_memory.assert_awaited_once_with(
            "mem-1", importance=0.3, confidence=None, content="new", metadata=None, allow_protected=False
        )
        assert stats.undo.change_count == 0  # a refused write leaves nothing to undo

    @pytest.mark.asyncio
    async def test_update_content_applies(self) -> None:
        manager = make_manager()
        manager.get_memory = AsyncMock(return_value=SemanticMemory(content="old"))
        ops = [UpdateContentOp(memory_id="mem-1", new_content="new", importance=0.3)]
        stats = await execute_operations(ops, manager)
        manager.update_memory.assert_awaited_once()
        assert stats.updated == 1


class TestEnrichWithSimilar:
    def _search_result(self, memory: SemanticMemory) -> SimpleNamespace:
        return SimpleNamespace(memory=memory)

    @pytest.mark.asyncio
    async def test_no_candidates_returns_alone(self) -> None:
        manager = make_manager()
        manager.search = AsyncMock(return_value=[])
        base = SemanticMemory(content="base")
        result = await _enrich_with_similar(base, manager)
        assert result == [base]

    @pytest.mark.asyncio
    async def test_candidates_filter_self_and_truncate(self) -> None:
        manager = make_manager()
        base = SemanticMemory(content="base")
        same = SemanticMemory(content="base", id=base.id)
        other = SemanticMemory(content="other")
        manager.search = AsyncMock(return_value=[self._search_result(same), self._search_result(other)])
        result = await _enrich_with_similar(base, manager, max_similar=1)
        assert result == [base, other]

    @pytest.mark.asyncio
    async def test_claims_and_rules_never_join(self) -> None:
        manager = make_manager()
        base = SemanticMemory(content="base")
        claim = ClaimMemory(content="compiled", claim_key="k", title="t", claim_text="compiled knowledge")
        rule = ProceduralMemory(content="When: asked → Do: answer", trigger="asked", action="answer")
        other = SemanticMemory(content="other")
        manager.search = AsyncMock(
            return_value=[self._search_result(claim), self._search_result(rule), self._search_result(other)]
        )
        assert await _enrich_with_similar(base, manager) == [base, other]

    @pytest.mark.asyncio
    async def test_search_error_returns_alone(self) -> None:
        manager = make_manager()
        manager.search = AsyncMock(side_effect=RuntimeError("search down"))
        base = SemanticMemory(content="base")
        assert await _enrich_with_similar(base, manager) == [base]
