"""Tests for the consolidation run itself (run_consolidation).

Covers:
- soft-lock, insufficient memories, LLM failure and out-of-range answers
- no-ops and full success (rubric filter, insights, undo journal, completion hook, refusal count)
- circuit breaker and total failure leaving the stamp unmoved
- the named-entity guard around merges and corrections
"""

from __future__ import annotations

import logging
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
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import _PROFILE_KEY_LAST_CONSOLIDATED
from myrm_agent_harness.toolkits.memory.strategies.consolidation_undo import _UNDO_KEY
from tests.support.consolidation_manager import make_manager, make_manager_holding, semantic_doc


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
        manager = make_manager_holding(semantic_doc("s-1", "solo"))
        stats = await run_consolidation(manager, _make_llm(ConsolidationResponse()), ConsolidationConfig())
        assert stats.total_processed == 0
        manager._rel_store.set_profile.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_failure_returns_error_stats(self) -> None:
        manager = make_manager_holding(semantic_doc("s-1", "a"), semantic_doc("s-2", "b"))
        structured = AsyncMock()
        structured.ainvoke = AsyncMock(side_effect=RuntimeError("llm down"))
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        stats = await run_consolidation(manager, llm, ConsolidationConfig())
        assert stats.errors == 1
        assert stats.input_count == 2

    @pytest.mark.asyncio
    async def test_out_of_range_importance_fails_the_run_before_anything_is_written(self) -> None:
        manager = make_manager_holding(semantic_doc("s-1", "a"), semantic_doc("s-2", "b"))
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
        manager = make_manager_holding(semantic_doc("s-1", "a"), semantic_doc("s-2", "b"))
        stats = await run_consolidation(
            manager,
            _make_llm(ConsolidationResponse(operations=[], insights=[])),
            ConsolidationConfig(),
        )
        assert stats.merged == 0
        assert stats.insights == ()

    @pytest.mark.asyncio
    async def test_full_success_with_rubric_filter_insights_and_complete(self) -> None:
        manager = make_manager_holding(semantic_doc("s-1", "a"), semantic_doc("s-2", "b"))
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
        assert stats.rejected == 1  # ...and counted as turned away
        assert stats.insights == ("cross-cutting insight",)
        assert stats.input_count == 2
        written_keys = [call.args[0] for call in manager._rel_store.set_profile.await_args_list]
        assert _PROFILE_KEY_LAST_CONSOLIDATED in written_keys
        assert _UNDO_KEY in written_keys  # the merge demoted two memories, so there is a cycle to undo
        on_complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_hook_error_is_non_fatal(self) -> None:
        manager = make_manager_holding(semantic_doc("s-1", "a"), semantic_doc("s-2", "b"))
        response = ConsolidationResponse(operations=[], insights=["only insight"])
        on_complete = AsyncMock(side_effect=RuntimeError("hook failed"))
        stats = await run_consolidation(manager, _make_llm(response), ConsolidationConfig(), on_complete=on_complete)
        assert stats.insights == ("only insight",)
        on_complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_hook_triggered_even_without_insights(self) -> None:
        manager = make_manager_holding(semantic_doc("s-1", "a"), semantic_doc("s-2", "b"))
        response = ConsolidationResponse(operations=[], insights=[])
        on_complete = AsyncMock()
        stats = await run_consolidation(manager, _make_llm(response), ConsolidationConfig(), on_complete=on_complete)
        assert stats.insights == ()
        on_complete.assert_awaited_once_with(stats)

    @pytest.mark.asyncio
    async def test_complete_hook_error_is_non_fatal_when_nothing_needed_applying(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        manager = make_manager_holding(semantic_doc("s-1", "a"), semantic_doc("s-2", "b"))
        on_complete = AsyncMock(side_effect=RuntimeError("hook failed"))

        with caplog.at_level(logging.WARNING, logger="myrm_agent_harness.toolkits.memory.strategies"):
            stats = await run_consolidation(
                manager, _make_llm(ConsolidationResponse()), ConsolidationConfig(), on_complete=on_complete
            )

        assert (stats.input_count, stats.errors) == (2, 0)
        on_complete.assert_awaited_once_with(stats)
        assert "Consolidation complete hook failed (non-fatal): hook failed" in caplog.text
        written_keys = [call.args[0] for call in manager._rel_store.set_profile.await_args_list]
        assert _PROFILE_KEY_LAST_CONSOLIDATED in written_keys  # a failing hook does not hold the stamp

    @pytest.mark.asyncio
    async def test_complete_hook_is_not_called_under_the_soft_lock(self) -> None:
        manager = make_manager()
        manager._rel_store.get_profile = AsyncMock(return_value=(datetime.now(UTC) - timedelta(minutes=5)).isoformat())
        on_complete = AsyncMock()

        await run_consolidation(
            manager,
            _make_llm(ConsolidationResponse()),
            ConsolidationConfig(soft_lock_hours=1.0),
            on_complete=on_complete,
        )

        on_complete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_complete_hook_is_not_called_when_no_namespace_holds_two_memories(self) -> None:
        manager = make_manager_holding(semantic_doc("s-1", "solo"))
        on_complete = AsyncMock()

        await run_consolidation(
            manager, _make_llm(ConsolidationResponse()), ConsolidationConfig(), on_complete=on_complete
        )

        on_complete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_complete_hook_is_not_called_when_the_model_fails(self) -> None:
        manager = make_manager_holding(semantic_doc("s-1", "a"), semantic_doc("s-2", "b"))
        llm = _make_llm(ConsolidationResponse())
        llm.with_structured_output.return_value.ainvoke = AsyncMock(side_effect=RuntimeError("llm down"))
        on_complete = AsyncMock()

        await run_consolidation(manager, llm, ConsolidationConfig(), on_complete=on_complete)

        on_complete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_insights_stating_what_no_memory_states_never_reach_the_store_or_the_hook(self) -> None:
        manager = make_manager_holding(
            semantic_doc("s-1", "Rent is 4500 yuan a month"), semantic_doc("s-2", "Utilities are 300 yuan a month")
        )
        response = ConsolidationResponse(
            insights=["Housing is the largest monthly cost", "Rent and utilities come to 4800 yuan a month"]
        )
        on_complete = AsyncMock()

        stats = await run_consolidation(manager, _make_llm(response), ConsolidationConfig(), on_complete=on_complete)

        assert stats.insights == ("Housing is the largest monthly cost",)
        assert stats.rejected == 1
        on_complete.assert_awaited_once_with(stats)
        assert [call.args[0].content for call in manager.store.await_args_list] == [
            "Housing is the largest monthly cost"
        ]

    @pytest.mark.asyncio
    async def test_the_refusal_count_is_logged_whether_or_not_anything_was_applied(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        unknown_source = MergeOp(source_ids=["s-1", "ghost"], merged_content="a", accuracy_score=0.95)

        with caplog.at_level(logging.INFO, logger="myrm_agent_harness.toolkits.memory.strategies"):
            manager = make_manager_holding(semantic_doc("s-1", "a"), semantic_doc("s-2", "b"))
            await run_consolidation(
                manager, _make_llm(ConsolidationResponse(operations=[unknown_source])), ConsolidationConfig()
            )
            manager = make_manager_holding(semantic_doc("s-1", "a"), semantic_doc("s-2", "b"))
            both = ConsolidationResponse(
                operations=[unknown_source, UpdateContentOp(memory_id="s-2", new_content="b2", importance=0.7)]
            )
            await run_consolidation(manager, _make_llm(both), ConsolidationConfig())

        assert "no operations needed (input=2, enriched=0, rejected=1)" in caplog.text
        assert "Consolidation complete: input=2, enriched=0, merged=0, corrected=0, updated=1" in caplog.text
        assert "rejected=1, insights=0" in caplog.text

    @pytest.mark.asyncio
    async def test_circuit_breaker_aborts_batch_and_skips_timestamp(self) -> None:
        manager = make_manager_holding(*(semantic_doc(f"s-{i}", f"content {i}") for i in range(1, 6)))
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
        manager = make_manager_holding(semantic_doc("s-1", "a"), semantic_doc("s-2", "b"))
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
        manager = make_manager_holding(
            semantic_doc("s-1", "Postgres runs on port 5433 at 127.0.0.1"),
            semantic_doc("s-2", "Database user is postgres with local password"),
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
        manager = make_manager_holding(semantic_doc("s-1", "A simple note"), semantic_doc("s-2", "Another simple note"))
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
        assert stats.rejected == 1
        manager.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_consolidation_rejects_missing_entity_in_correct_op(self) -> None:
        manager = make_manager_holding(
            semantic_doc("s-1", "Postgres runs on port 5433 at 127.0.0.1"),
            semantic_doc("s-2", "Database user is postgres"),
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
        assert stats.rejected == 1
        manager.correct_memory.assert_not_called()
