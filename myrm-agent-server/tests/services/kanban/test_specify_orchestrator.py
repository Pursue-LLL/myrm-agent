"""Unit tests for specify_orchestrator: run_specify_task, run_apply_spec, run_specify_all_triage."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.kanban.protocols import SpecifyOutcome
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskEventKind, TaskStatus

from app.services.kanban.specify_orchestrator import (
    run_apply_spec,
    run_specify_all_triage,
    run_specify_task,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _triage_task(task_id: str = "t1", board_id: str = "b1") -> KanbanTask:
    return KanbanTask(
        task_id=task_id, board_id=board_id, title="rough idea", status=TaskStatus.TRIAGE,
    )


def _mock_store(task: KanbanTask | None = None) -> AsyncMock:
    store = AsyncMock()
    store.get_task = AsyncMock(return_value=task)
    store.save_task = AsyncMock(side_effect=lambda t: t)
    store.append_event = AsyncMock()
    store.are_dependencies_met = AsyncMock(return_value=True)
    store.list_tasks = AsyncMock(return_value=[])
    return store


def _noop_wake(board_id: str) -> None:
    pass


def _noop_publish(board_id: str, task_id: str, action: str, *, title: str = "", status: str = "") -> None:
    pass


# ---------------------------------------------------------------------------
# run_specify_task
# ---------------------------------------------------------------------------


class TestRunSpecifyTask:
    @pytest.mark.asyncio
    async def test_returns_unavailable_when_no_specifier(self) -> None:
        store = _mock_store(_triage_task())
        outcome = await run_specify_task(
            "t1", store=store, specifier=None,
            wake_dispatcher=_noop_wake, publish_event=_noop_publish,
        )
        assert not outcome.ok
        assert outcome.reason == "specifier_unavailable"

    @pytest.mark.asyncio
    async def test_returns_unknown_task(self) -> None:
        store = _mock_store(None)
        specifier = AsyncMock()
        outcome = await run_specify_task(
            "missing", store=store, specifier=specifier,
            wake_dispatcher=_noop_wake, publish_event=_noop_publish,
        )
        assert not outcome.ok
        assert outcome.reason == "unknown_task"

    @pytest.mark.asyncio
    async def test_preview_does_not_persist(self) -> None:
        task = _triage_task()
        store = _mock_store(task)
        specifier = AsyncMock()
        specifier.specify = AsyncMock(return_value=SpecifyOutcome(
            task_id="t1", ok=True, reason="specified",
            new_title="Better Title", new_body="**Goal** ...",
            prompt_tokens=100, completion_tokens=200,
        ))
        outcome = await run_specify_task(
            "t1", store=store, specifier=specifier,
            wake_dispatcher=_noop_wake, publish_event=_noop_publish,
            persist=False,
        )
        assert outcome.ok
        assert outcome.new_title == "Better Title"
        store.save_task.assert_not_called()
        store.append_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_saves_and_emits_events(self) -> None:
        task = _triage_task()
        store = _mock_store(task)
        specifier = AsyncMock()
        specifier.specify = AsyncMock(return_value=SpecifyOutcome(
            task_id="t1", ok=True, reason="specified",
            new_title="Better Title", new_body="**Goal** ...",
            prompt_tokens=100, completion_tokens=200,
        ))
        wakes: list[str] = []
        publishes: list[tuple[str, str, str]] = []

        def wake(bid: str) -> None:
            wakes.append(bid)

        def publish(bid: str, tid: str, action: str, **kw: str) -> None:
            publishes.append((bid, tid, action))

        outcome = await run_specify_task(
            "t1", store=store, specifier=specifier,
            wake_dispatcher=wake, publish_event=publish,
            persist=True,
        )
        assert outcome.ok
        assert outcome.persisted
        store.save_task.assert_called_once()
        assert store.append_event.call_count == 2  # SPECIFIED + PROMOTED
        event_kinds = [call.args[1] for call in store.append_event.call_args_list]
        assert TaskEventKind.SPECIFIED in event_kinds
        assert TaskEventKind.PROMOTED in event_kinds
        assert wakes == ["b1"]
        assert len(publishes) == 1

    @pytest.mark.asyncio
    async def test_race_lost_when_task_status_changed(self) -> None:
        task = _triage_task()
        store = _mock_store(task)
        ready_task = KanbanTask(
            task_id="t1", board_id="b1", title="rough idea", status=TaskStatus.READY,
        )
        store.get_task = AsyncMock(side_effect=[task, ready_task])
        specifier = AsyncMock()
        specifier.specify = AsyncMock(return_value=SpecifyOutcome(
            task_id="t1", ok=True, reason="specified",
            new_title="X", new_body="Y",
        ))
        outcome = await run_specify_task(
            "t1", store=store, specifier=specifier,
            wake_dispatcher=_noop_wake, publish_event=_noop_publish,
            persist=True,
        )
        assert not outcome.ok
        assert outcome.reason == "race_lost"
        assert not outcome.persisted


# ---------------------------------------------------------------------------
# run_apply_spec
# ---------------------------------------------------------------------------


class TestRunApplySpec:
    @pytest.mark.asyncio
    async def test_unknown_task(self) -> None:
        store = _mock_store(None)
        outcome = await run_apply_spec(
            "missing", new_title=None, new_body="body",
            store=store, wake_dispatcher=_noop_wake, publish_event=_noop_publish,
        )
        assert not outcome.ok
        assert outcome.reason == "unknown_task"

    @pytest.mark.asyncio
    async def test_race_lost_when_not_triage(self) -> None:
        task = KanbanTask(task_id="t1", board_id="b1", title="x", status=TaskStatus.READY)
        store = _mock_store(task)
        outcome = await run_apply_spec(
            "t1", new_title="New", new_body="body",
            store=store, wake_dispatcher=_noop_wake, publish_event=_noop_publish,
        )
        assert not outcome.ok
        assert outcome.reason == "race_lost"

    @pytest.mark.asyncio
    async def test_successful_apply_persists(self) -> None:
        task = _triage_task()
        store = _mock_store(task)
        wakes: list[str] = []

        def wake(bid: str) -> None:
            wakes.append(bid)

        outcome = await run_apply_spec(
            "t1", new_title="Better Title", new_body="**Goal** ...",
            prompt_tokens=100, completion_tokens=200,
            store=store, wake_dispatcher=wake, publish_event=_noop_publish,
        )
        assert outcome.ok
        assert outcome.persisted
        assert outcome.reason == "applied_from_preview"
        assert outcome.new_title == "Better Title"
        store.save_task.assert_called_once()
        saved_task = store.save_task.call_args[0][0]
        assert saved_task.title == "Better Title"
        assert saved_task.description == "**Goal** ..."
        assert saved_task.status == TaskStatus.READY
        assert saved_task.metadata.get("original_title") == "rough idea"
        assert store.append_event.call_count == 2  # SPECIFIED + PROMOTED
        assert wakes == ["b1"]

    @pytest.mark.asyncio
    async def test_apply_backlog_when_deps_unmet(self) -> None:
        task = _triage_task()
        store = _mock_store(task)
        store.are_dependencies_met = AsyncMock(return_value=False)
        outcome = await run_apply_spec(
            "t1", new_title=None, new_body="body",
            store=store, wake_dispatcher=_noop_wake, publish_event=_noop_publish,
        )
        assert outcome.ok
        assert outcome.persisted
        saved_task = store.save_task.call_args[0][0]
        assert saved_task.status == TaskStatus.BACKLOG
        assert store.append_event.call_count == 1  # Only SPECIFIED, no PROMOTED


# ---------------------------------------------------------------------------
# run_specify_all_triage
# ---------------------------------------------------------------------------


class TestRunSpecifyAllTriage:
    @pytest.mark.asyncio
    async def test_empty_board_returns_empty(self) -> None:
        store = _mock_store()
        store.list_tasks = AsyncMock(return_value=[])

        async def specify_one(tid: str, p: bool, a: str) -> SpecifyOutcome:
            raise AssertionError("should not be called")

        result = await run_specify_all_triage(
            "b1", store=store, specify_one=specify_one,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_batch_continues_past_failures(self) -> None:
        t1 = _triage_task("t1")
        t2 = _triage_task("t2")
        store = _mock_store()
        store.list_tasks = AsyncMock(return_value=[t1, t2])

        call_log: list[str] = []

        async def specify_one(tid: str, p: bool, a: str) -> SpecifyOutcome:
            call_log.append(tid)
            if tid == "t1":
                return SpecifyOutcome(task_id=tid, ok=False, reason="llm_error:Timeout")
            return SpecifyOutcome(task_id=tid, ok=True, reason="specified", new_body="body")

        result = await run_specify_all_triage(
            "b1", store=store, specify_one=specify_one,
        )
        assert len(result) == 2
        assert not result[0].ok
        assert result[1].ok
        assert set(call_log) == {"t1", "t2"}
