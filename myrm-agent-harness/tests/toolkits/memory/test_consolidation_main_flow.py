"""Tests for the consolidation run itself (run_consolidation).

Covers:
- soft-lock, insufficient memories, LLM failure and out-of-range answers
- no-ops and full success (rubric filter, insights, completion hook)
- circuit breaker and total failure leaving the stamp unmoved
- the named-entity guard around merges and corrections
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.memory.config import ConsolidationConfig
from myrm_agent_harness.toolkits.memory.strategies.consolidation import (
    ConsolidationResponse,
    CorrectOp,
    MergeOp,
    UpdateContentOp,
    run_consolidation,
)
from tests.support.consolidation_manager import make_manager, semantic_doc


def _make_llm(response: ConsolidationResponse) -> MagicMock:
    structured = AsyncMock()
    structured.ainvoke = AsyncMock(return_value=response)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


class TestRunConsolidation:
    @pytest.mark.asyncio
    async def test_soft_lock_skips(self) -> None:
        manager = make_manager()
        manager._rel_store.get_profile = AsyncMock(return_value=(datetime.now(UTC) - timedelta(minutes=5)).isoformat())
        config = ConsolidationConfig(soft_lock_hours=1.0)
        stats = await run_consolidation(manager, _make_llm(ConsolidationResponse()), config)
        assert stats.total_processed == 0
        manager._vec_store.scroll.assert_not_called()

    @pytest.mark.asyncio
    async def test_insufficient_memories_skips(self) -> None:
        manager = make_manager()
        manager._vec_store.scroll = AsyncMock(side_effect=[([semantic_doc("s-1", "solo")], None), ([], None)])
        stats = await run_consolidation(manager, _make_llm(ConsolidationResponse()), ConsolidationConfig())
        assert stats.total_processed == 0
        manager._rel_store.set_profile.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_failure_returns_error_stats(self) -> None:
        manager = make_manager()
        manager._vec_store.scroll = AsyncMock(
            side_effect=[
                ([semantic_doc("s-1", "a"), semantic_doc("s-2", "b")], None),
                ([], None),
            ]
        )
        structured = AsyncMock()
        structured.ainvoke = AsyncMock(side_effect=RuntimeError("llm down"))
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        stats = await run_consolidation(manager, llm, ConsolidationConfig())
        assert stats.errors == 1
        assert stats.input_count == 2

    @pytest.mark.asyncio
    async def test_out_of_range_importance_fails_the_run_before_anything_is_written(self) -> None:
        manager = make_manager()
        manager._vec_store.scroll = AsyncMock(
            side_effect=[
                ([semantic_doc("s-1", "a"), semantic_doc("s-2", "b")], None),
                ([], None),
            ]
        )
        update = {"action": "update_content", "memory_id": "s-1", "new_content": "better", "importance": 8}
        structured = AsyncMock()
        structured.ainvoke = AsyncMock(return_value={"operations": [update], "insights": []})
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        stats = await run_consolidation(manager, llm, ConsolidationConfig())
        assert stats.errors == 1
        manager.update_memory.assert_not_called()
        manager._rel_store.set_profile.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_operations_returns_empty(self) -> None:
        manager = make_manager()
        manager._vec_store.scroll = AsyncMock(
            side_effect=[
                ([semantic_doc("s-1", "a"), semantic_doc("s-2", "b")], None),
                ([], None),
            ]
        )
        stats = await run_consolidation(
            manager,
            _make_llm(ConsolidationResponse(operations=[], insights=[])),
            ConsolidationConfig(),
        )
        assert stats.merged == 0
        assert stats.insights == ()

    @pytest.mark.asyncio
    async def test_full_success_with_rubric_filter_insights_and_complete(self) -> None:
        manager = make_manager()
        manager._vec_store.scroll = AsyncMock(
            side_effect=[
                ([semantic_doc("s-1", "a"), semantic_doc("s-2", "b")], None),
                ([], None),
            ]
        )
        response = ConsolidationResponse(
            operations=[
                MergeOp(
                    source_ids=["s-1", "s-2"],
                    merged_content="merged",
                    accuracy_score=0.9,
                    importance=0.8,
                ),
                CorrectOp(
                    memory_id="s-1",
                    corrected_content="corrected",
                    accuracy_score=0.2,
                    importance=0.2,
                ),
            ],
            insights=["cross-cutting insight"],
        )
        on_complete = AsyncMock()
        stats = await run_consolidation(manager, _make_llm(response), ConsolidationConfig(), on_complete=on_complete)
        assert stats.merged == 1
        assert stats.corrected == 0  # low-scoring op filtered out by rubric
        assert stats.insights == ("cross-cutting insight",)
        assert stats.input_count == 2
        manager.add_event.assert_awaited()
        manager._rel_store.set_profile.assert_awaited()
        on_complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_hook_error_is_non_fatal(self) -> None:
        manager = make_manager()
        manager._vec_store.scroll = AsyncMock(
            side_effect=[
                ([semantic_doc("s-1", "a"), semantic_doc("s-2", "b")], None),
                ([], None),
            ]
        )
        response = ConsolidationResponse(operations=[], insights=["only insight"])
        on_complete = AsyncMock(side_effect=RuntimeError("hook failed"))
        stats = await run_consolidation(manager, _make_llm(response), ConsolidationConfig(), on_complete=on_complete)
        assert stats.insights == ("only insight",)
        on_complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_hook_triggered_even_without_insights(self) -> None:
        manager = make_manager()
        manager._vec_store.scroll = AsyncMock(
            side_effect=[
                ([semantic_doc("s-1", "a"), semantic_doc("s-2", "b")], None),
                ([], None),
            ]
        )
        response = ConsolidationResponse(operations=[], insights=[])
        on_complete = AsyncMock()
        stats = await run_consolidation(manager, _make_llm(response), ConsolidationConfig(), on_complete=on_complete)
        assert stats.insights == ()
        on_complete.assert_awaited_once_with(stats)

    @pytest.mark.asyncio
    async def test_circuit_breaker_aborts_batch_and_skips_timestamp(self) -> None:
        manager = make_manager()
        manager._vec_store.scroll = AsyncMock(
            side_effect=[
                ([semantic_doc(f"s-{i}", f"content {i}") for i in range(1, 6)], None),
                ([], None),
            ]
        )
        manager.update_memory = AsyncMock(side_effect=RuntimeError("db write failure"))
        response = ConsolidationResponse(
            operations=[
                UpdateContentOp(memory_id=f"s-{i}", new_content=f"updated content {i}", importance=0.8)
                for i in range(1, 6)
            ],
            insights=[],
        )
        stats = await run_consolidation(manager, _make_llm(response), ConsolidationConfig())
        assert stats.aborted is True
        assert stats.errors == 3
        assert manager.update_memory.await_count == 3
        manager._rel_store.set_profile.assert_not_called()

    @pytest.mark.asyncio
    async def test_total_failure_skips_timestamp(self) -> None:
        manager = make_manager()
        manager._vec_store.scroll = AsyncMock(
            side_effect=[
                ([semantic_doc("s-1", "a"), semantic_doc("s-2", "b")], None),
                ([], None),
            ]
        )
        manager.update_memory = AsyncMock(side_effect=RuntimeError("db write failure"))
        response = ConsolidationResponse(
            operations=[
                UpdateContentOp(memory_id="s-1", new_content="updated content", importance=0.8),
            ],
            insights=[],
        )
        stats = await run_consolidation(manager, _make_llm(response), ConsolidationConfig())
        assert stats.aborted is False
        assert stats.errors == 1
        assert stats.updated == 0
        manager._rel_store.set_profile.assert_not_called()

    @pytest.mark.asyncio
    async def test_consolidation_auto_patches_missing_port_via_named_entity_guard(self) -> None:
        manager = make_manager()
        manager._vec_store.scroll = AsyncMock(
            side_effect=[
                (
                    [
                        semantic_doc("s-1", "Postgres runs on port 5433 at 127.0.0.1"),
                        semantic_doc("s-2", "Database user is postgres with local password"),
                    ],
                    None,
                ),
                ([], None),
            ]
        )
        # LLM tries to merge s-1 and s-2, but drops port 5433
        response = ConsolidationResponse(
            operations=[
                MergeOp(
                    source_ids=["s-1", "s-2"],
                    merged_content="Postgres database runs at 127.0.0.1 with user postgres",
                    accuracy_score=0.95,
                    importance=0.8,
                    reasoning="Merged postgres credentials and endpoint",
                )
            ],
            insights=[],
        )
        stats = await run_consolidation(manager, _make_llm(response), ConsolidationConfig())
        # NamedEntityGuard automatically self-heals by patching the missing port 5433
        assert stats.merged == 1
        assert stats.guard_patched == 1
        stored = [call.args[0] for call in manager.store.call_args_list]
        assert any("5433" in m.content for m in stored)

    @pytest.mark.asyncio
    async def test_consolidation_rejects_insufficient_or_empty_source_ids(self) -> None:
        manager = make_manager()
        manager._vec_store.scroll = AsyncMock(
            side_effect=[
                ([semantic_doc("s-1", "A simple note")], None),
                ([], None),
            ]
        )
        # LLM hallucinates an invalid/empty source merge
        response = ConsolidationResponse(
            operations=[
                MergeOp(
                    source_ids=["non-existent-1"],
                    merged_content="Hallucinated merge content",
                    accuracy_score=0.95,
                    importance=0.8,
                    reasoning="Invalid source ids",
                )
            ],
            insights=[],
        )
        stats = await run_consolidation(manager, _make_llm(response), ConsolidationConfig())
        assert stats.merged == 0
        assert stats.guard_patched == 0

    @pytest.mark.asyncio
    async def test_consolidation_rejects_missing_entity_in_correct_op(self) -> None:
        manager = make_manager()
        manager._vec_store.scroll = AsyncMock(
            side_effect=[
                ([semantic_doc("s-1", "Postgres runs on port 5433 at 127.0.0.1")], None),
                ([], None),
            ]
        )
        # CorrectOp drops the critical port (no auto-healing for CorrectOp)
        response = ConsolidationResponse(
            operations=[
                CorrectOp(
                    memory_id="s-1",
                    corrected_content="Postgres runs at 127.0.0.1",
                    accuracy_score=0.95,
                    importance=0.8,
                    reasoning="Dropped port",
                )
            ],
            insights=[],
        )
        stats = await run_consolidation(manager, _make_llm(response), ConsolidationConfig())
        assert stats.corrected == 0
