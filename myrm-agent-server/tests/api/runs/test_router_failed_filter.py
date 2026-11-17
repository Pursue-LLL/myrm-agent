"""Unified Runs Hub failed filter: `status=error` selects every failed run, whichever source ended it.

[INPUT]
- app.api.runs.router: the cron, kanban and shell fetchers behind GET /runs
- myrm_agent_harness.toolkits.cron::InMemoryCronStore (POS: the store the cron fetcher reads through the manager)

[OUTPUT]
- Fails when a failed run hides from the Failed filter: a circuit break, a timeout
- Fails when a filter on one status selects another status's runs

[POS]
tests/api/runs/test_router_failed_filter.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.cron import (
    CronJob,
    CronRunRecord,
    InMemoryCronStore,
    JobType,
    Schedule,
    ScheduleKind,
)
from myrm_agent_harness.toolkits.cron import (
    RunStatus as CronRunStatus,
)
from myrm_agent_harness.toolkits.kanban.types import TaskStatus as KanbanStatus

from app.api.runs.router import _fetch_background_shell_runs, _fetch_cron_runs, _fetch_kanban_runs
from app.api.runs.schemas import RunStatus, RunStopReason
from app.api.runs.stop_reason import to_run_stop_reason

_STARTED = datetime(2026, 1, 1, tzinfo=UTC)
_CRON_PATCH = "app.core.cron.adapters.setup.get_cron_manager"
_SHELL_PATCH = "app.services.agent.shell_background_tasks.list_shell_background_tasks"
_KANBAN_PATCH = "app.services.kanban.KanbanService.get_instance"


async def _cron_store_holding_one_run_of_every_status() -> InMemoryCronStore:
    store = InMemoryCronStore()
    await store.save_job(
        CronJob(
            id="job",
            name="Digest",
            job_type=JobType.ROUTER,
            schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000),
            command="__probe__",
        )
    )
    for minute, status in enumerate(CronRunStatus):
        started = _STARTED + timedelta(minutes=minute)
        await store.save_run(
            CronRunRecord(
                id=status.value,
                job_id="job",
                started_at=started,
                finished_at=started + timedelta(seconds=5),
                duration_ms=5_000,
                status=status,
            )
        )
    return store


async def _cron_statuses_listed_for(status_filter: RunStatus | None) -> list[str]:
    """The statuses the Hub lists for a filter, with the cron manager answered by a real store."""
    store = await _cron_store_holding_one_run_of_every_status()
    manager = SimpleNamespace(list_runs=store.list_runs, list_jobs=store.list_jobs)
    with patch(_CRON_PATCH, return_value=manager):
        items, available = await _fetch_cron_runs(status_filter, 10)
    assert available is True
    return sorted(item.status for item in items)


class TestCronRuns:
    async def test_the_failed_filter_selects_errors_and_circuit_breaks(self) -> None:
        assert await _cron_statuses_listed_for("error") == ["circuit_break", "error"]

    async def test_a_circuit_break_filter_selects_only_circuit_breaks(self) -> None:
        assert await _cron_statuses_listed_for("circuit_break") == ["circuit_break"]

    async def test_a_skipped_filter_selects_only_skipped_runs(self) -> None:
        assert await _cron_statuses_listed_for("skipped") == ["skipped"]

    async def test_no_filter_lists_every_run(self) -> None:
        assert await _cron_statuses_listed_for(None) == ["circuit_break", "error", "ok", "skipped"]

    @pytest.mark.parametrize("status_filter", ["running", "cancelled", "timed_out"])
    async def test_a_status_no_cron_run_has_lists_nothing_and_asks_no_store(self, status_filter: RunStatus) -> None:
        manager = MagicMock()
        manager.list_runs = AsyncMock(return_value=[])

        with patch(_CRON_PATCH, return_value=manager):
            items, available = await _fetch_cron_runs(status_filter, 10)

        assert (items, available) == ([], True)
        manager.list_runs.assert_not_called()


def _kanban_task(task_id: str, status: KanbanStatus, error: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        task_id=task_id,
        status=status,
        created_at=_STARTED,
        completed_at=_STARTED + timedelta(minutes=1),
        title=task_id,
        description=None,
        error=error,
        agent_id=None,
        progress_note=None,
    )


async def _kanban_ids_listed_for(status_filter: RunStatus | None) -> list[str]:
    tasks = [
        _kanban_task("done", KanbanStatus.COMPLETED),
        _kanban_task("crashed", KanbanStatus.FAILED, "boom"),
        _kanban_task("slow", KanbanStatus.FAILED, "execution timed out after 300s"),
        _kanban_task("stopped", KanbanStatus.FAILED, "cancelled by the user"),
    ]
    service = MagicMock()
    service.list_boards = AsyncMock(return_value=[SimpleNamespace(board_id="board", name="__background_tasks__")])
    service.store.list_tasks = AsyncMock(return_value=tasks)
    with patch(_KANBAN_PATCH, return_value=service):
        items, available = await _fetch_kanban_runs(status_filter, 10)
    assert available is True
    return [item.id.removeprefix("kanban:") for item in items]


class TestKanbanRuns:
    async def test_the_failed_filter_selects_errors_and_timeouts_but_not_cancellations(self) -> None:
        assert await _kanban_ids_listed_for("error") == ["crashed", "slow"]

    async def test_a_timeout_filter_selects_only_timeouts(self) -> None:
        assert await _kanban_ids_listed_for("timed_out") == ["slow"]

    async def test_a_cancelled_filter_selects_only_cancellations(self) -> None:
        assert await _kanban_ids_listed_for("cancelled") == ["stopped"]


def _shell_task(task_id: str, status: str) -> SimpleNamespace:
    return SimpleNamespace(
        task_id=task_id,
        status=status,
        created_at=_STARTED.timestamp(),
        completed_at=_STARTED.timestamp() + 60,
        prompt=task_id,
        result_preview=None,
    )


class TestShellRuns:
    @pytest.mark.parametrize(("status_filter", "expected"), [("error", ["crashed"]), ("cancelled", ["stopped"])])
    async def test_a_filter_selects_the_tasks_that_ended_that_way(self, status_filter: RunStatus, expected: list[str]) -> None:
        tasks = [_shell_task("done", "completed"), _shell_task("crashed", "failed"), _shell_task("stopped", "cancelled")]

        with patch(_SHELL_PATCH, return_value=tasks):
            items, available = await _fetch_background_shell_runs(status_filter)

        assert available is True
        assert [item.id.removeprefix("shell:") for item in items] == expected


class TestStopReasonParsing:
    def test_no_stop_reason_stays_none(self) -> None:
        assert to_run_stop_reason(None) is None

    def test_the_stored_shape_becomes_the_response_model(self) -> None:
        stored: dict[str, object] = {
            "code": "iteration_limit_reached",
            "category": "limit",
            "message": "Iteration limit reached",
            "detail": {"limit": 50},
        }

        assert to_run_stop_reason(stored) == RunStopReason(
            code="iteration_limit_reached",
            category="limit",
            message="Iteration limit reached",
            detail={"limit": 50},
        )
