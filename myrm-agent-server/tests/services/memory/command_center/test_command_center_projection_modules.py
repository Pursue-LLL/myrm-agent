"""Unit tests for the command-center projection modules split out of the aggregation service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.toolkits.memory import MemoryStatus, MemoryType
from sqlalchemy import select
from sqlalchemy.dialects import sqlite

from app.database.models.memory import SharedContextModel
from app.schemas.memory.command_center import (
    MemoryCommandCostProfile,
    MemoryCommandInfluenceItem,
    MemoryCommandInfluenceRef,
    MemoryCommandTimelineEvent,
)
from app.services.memory.command_center.command_center_health import health_status
from app.services.memory.command_center.command_center_memory_scan import (
    ALL_MEMORY_TYPES,
    count_memories_by_type,
    list_archived_memory_ids,
)
from app.services.memory.command_center.command_center_projection_utils import (
    MemoryTelemetry,
    read_memory_telemetry,
    restrict_to_context_ids,
)
from app.services.memory.command_center.command_center_replay import build_replay, build_replay_events, build_waterfall
from app.services.memory.command_center.command_center_trace import TRACE_RUN_LIMIT, TRACE_SOURCE, build_trace_runs

_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _sql(statement: object) -> str:
    return str(statement.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[attr-defined]


def _trace_event(
    event_id: str,
    *,
    trace_id: str,
    status: str = "success",
    offset_s: int = 0,
    **metadata: str | int | float | bool | None,
) -> MemoryCommandTimelineEvent:
    return MemoryCommandTimelineEvent(
        id=event_id,
        kind="recall",
        status=status,
        occurred_at=_NOW + timedelta(seconds=offset_s),
        title=f"title-{event_id}",
        description="d",
        source=TRACE_SOURCE,
        metadata={"trace_id": trace_id, **metadata},
    )


class TestHealthStatus:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (None, "unknown"),
            (100, "healthy"),
            (80, "healthy"),
            (79, "degraded"),
            (55, "degraded"),
            (54, "critical"),
            (0, "critical"),
        ],
    )
    def test_thresholds(self, score: int | None, expected: str) -> None:
        assert health_status(score) == expected


class TestReadMemoryTelemetry:
    def test_missing_telemetry_uses_defaults(self) -> None:
        assert read_memory_telemetry({}) == MemoryTelemetry()
        assert read_memory_telemetry({"memory_telemetry": "garbage"}) == MemoryTelemetry()

    def test_reads_numeric_fields(self) -> None:
        parsed = read_memory_telemetry(
            {
                "memory_telemetry": {
                    "injected_memory_tokens": 120,
                    "retrieval_ms": 30.5,
                    "construction_ms": 4,
                    "injection_overhead_ms": 2.5,
                    "cache_aligned": False,
                }
            }
        )
        assert parsed == MemoryTelemetry(
            injected_tokens=120, retrieval_ms=30.5, construction_ms=4.0, injection_ms=2.5, cache_aligned=False
        )

    def test_malformed_values_fall_back_and_zero_injection_uses_default(self) -> None:
        parsed = read_memory_telemetry(
            {
                "memory_telemetry": {
                    "injected_memory_tokens": "many",
                    "retrieval_ms": True,
                    "injection_overhead_ms": 0,
                    "cache_aligned": "yes",
                }
            }
        )
        assert parsed == MemoryTelemetry()


class TestRestrictToContextIds:
    def test_none_keeps_the_global_view(self) -> None:
        statement = select(SharedContextModel)
        assert restrict_to_context_ids(statement, SharedContextModel.id, None) is statement

    def test_ids_filter_with_in_clause(self) -> None:
        sql = _sql(restrict_to_context_ids(select(SharedContextModel), SharedContextModel.id, {"ctx-1"}))
        assert "shared_contexts.id IN ('ctx-1')" in sql

    def test_empty_set_matches_nothing(self) -> None:
        sql = _sql(restrict_to_context_ids(select(SharedContextModel), SharedContextModel.id, set()))
        assert "WHERE 0 = 1" in sql or "WHERE false" in sql.lower()


class TestBuildTraceRuns:
    def test_ignores_events_from_other_sources(self) -> None:
        other = _trace_event("e0", trace_id="t0").model_copy(update={"source": "memory_operation_ledger"})
        assert build_trace_runs([other]) == []

    def test_groups_by_trace_and_orders_runs_newest_first(self) -> None:
        events = [
            _trace_event("a1", trace_id="old", offset_s=0),
            _trace_event("b1", trace_id="new", offset_s=60),
            _trace_event("a2", trace_id="old", offset_s=5),
        ]
        runs = build_trace_runs(events)
        assert [run.trace_id for run in runs] == ["new", "old"]
        assert len(runs[1].steps) == 2
        assert runs[1].id == "trace-run:old"

    def test_event_without_trace_id_forms_its_own_run(self) -> None:
        event = _trace_event("solo", trace_id="x").model_copy(update={"metadata": {}})
        runs = build_trace_runs([event])
        assert runs[0].trace_id == "solo"

    def test_caps_the_number_of_runs(self) -> None:
        events = [_trace_event(f"e{i}", trace_id=f"t{i}", offset_s=i) for i in range(TRACE_RUN_LIMIT + 3)]
        assert len(build_trace_runs(events)) == TRACE_RUN_LIMIT

    def test_run_status_prefers_error_then_warning_and_maps_unknown_to_warning(self) -> None:
        errored = build_trace_runs([_trace_event("a", trace_id="t", status="error"), _trace_event("b", trace_id="t")])
        assert errored[0].status == "error"
        unknown = build_trace_runs([_trace_event("c", trace_id="u", status="mystery")])
        assert unknown[0].status == "warning"
        assert unknown[0].steps[0].status == "warning"
        skipped = build_trace_runs([_trace_event("d", trace_id="v", status="skipped")])
        assert skipped[0].status == "skipped"

    def test_steps_follow_step_index_and_metadata_overrides(self) -> None:
        events = [
            _trace_event("late", trace_id="t", offset_s=1, step_index=2, step_phase="rerank", duration_ms=12.5, result_count=4),
            _trace_event("early", trace_id="t", offset_s=2, step_index=1, message_id="m1", chat_id="c1", query_preview="q"),
        ]
        run = build_trace_runs(events)[0]
        assert [step.id for step in run.steps] == ["early", "late"]
        assert run.steps[1].phase == "rerank"
        assert run.steps[1].duration_ms == 12.5
        assert run.duration_ms == 12.5
        assert run.result_count == 4
        assert (run.message_id, run.chat_id, run.query_preview) == ("m1", "c1", "q")


def _ref(memory_id: str) -> MemoryCommandInfluenceRef:
    return MemoryCommandInfluenceRef(
        memory_id=memory_id, memory_type="semantic", content_preview="p", reason="memory_search_tool"
    )


def _influence(chat_id: str | None, refs: int, *, offset_s: int = 0) -> MemoryCommandInfluenceItem:
    return MemoryCommandInfluenceItem(
        id=f"message:{chat_id}",
        chat_id=chat_id,
        message_id=f"m-{chat_id}",
        occurred_at=_NOW + timedelta(seconds=offset_s),
        answer_preview="answer",
        influence_refs=[_ref(f"r{i}") for i in range(refs)],
    )


def _chat_event(event_id: str, chat_id: str, *, offset_s: int, influence: int = 0) -> MemoryCommandTimelineEvent:
    return MemoryCommandTimelineEvent(
        id=event_id,
        kind="recall",
        status="success",
        occurred_at=_NOW + timedelta(seconds=offset_s),
        title="t",
        description="event summary",
        source="memory_operation_ledger",
        target_kind="chat",
        target_id=chat_id,
        influence_count=influence,
    )


class TestReplayProjection:
    def test_overlay_merges_influence_and_chat_events(self) -> None:
        overlays = build_replay(
            [_chat_event("e1", "chat-a", offset_s=30, influence=2), _chat_event("e2", "chat-b", offset_s=5)],
            [_influence("chat-a", 1, offset_s=10), _influence(None, 3)],
        )
        by_chat = {overlay.chat_id: overlay for overlay in overlays}
        assert set(by_chat) == {"chat-a", "chat-b"}
        assert by_chat["chat-a"].event_count == 2
        assert by_chat["chat-a"].influence_count == 3
        assert by_chat["chat-a"].last_event_at == _NOW + timedelta(seconds=30)
        assert by_chat["chat-b"].message_id is None
        assert overlays[0].chat_id == "chat-a"

    def test_replay_events_are_capped_and_keep_order(self) -> None:
        timeline = [_chat_event(f"e{i}", "c", offset_s=i) for i in range(30)]
        events = build_replay_events(timeline)
        assert len(events) == 24
        assert events[0].id == "e0"

    def test_waterfall_counts_phases_and_marks_recall_evidence(self) -> None:
        timeline = [_chat_event("e1", "c", offset_s=1)]
        influence = [_influence("c", 2)]
        steps = build_waterfall(timeline, influence, MemoryCommandCostProfile(estimated_memory_tokens=50))
        by_phase = {step.phase: step for step in steps}
        assert by_phase["recall"].evidence_count == 2
        assert by_phase["cite"].event_count == 2
        assert by_phase["inject"].event_count == 1
        assert by_phase["scan"].event_count == 0


class _Mem:
    def __init__(self, memory_id: str, status: MemoryStatus = MemoryStatus.ACTIVE) -> None:
        self.id = memory_id
        self.status = status


class TestMemoryScan:
    @pytest.mark.asyncio
    async def test_count_degrades_failed_types_to_zero(self) -> None:
        manager = MagicMock()

        async def _count(memory_type: MemoryType) -> int:
            if memory_type == MemoryType.CLAIM:
                raise RuntimeError("boom")
            return 3

        manager.count_memories = AsyncMock(side_effect=_count)
        counts = await count_memories_by_type(manager)
        assert set(counts) == {memory_type.value for memory_type in ALL_MEMORY_TYPES}
        assert counts[MemoryType.CLAIM.value] == 0
        assert counts[MemoryType.PROFILE.value] == 3

    @pytest.mark.asyncio
    async def test_archived_ids_only_include_archived_status(self) -> None:
        manager = MagicMock()
        manager.list_memories = AsyncMock(
            side_effect=lambda memory_type, **_: (
                [_Mem("sem-archived", MemoryStatus.ARCHIVED), _Mem("sem-active")] if memory_type == MemoryType.SEMANTIC else []
            )
        )
        assert await list_archived_memory_ids(manager) == {"sem-archived"}

    @pytest.mark.asyncio
    async def test_archived_scan_survives_a_failing_type(self) -> None:
        manager = MagicMock()

        async def _list(memory_type: MemoryType, **_: object) -> list[_Mem]:
            if memory_type == MemoryType.SEMANTIC:
                raise RuntimeError("store offline")
            return [_Mem("epi-archived", MemoryStatus.ARCHIVED)]

        manager.list_memories = AsyncMock(side_effect=_list)
        assert await list_archived_memory_ids(manager) == {"epi-archived"}
