"""Unit tests for Unified Runs Hub API (app.api.runs)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.runs.router import (
    _fetch_background_shell_runs,
    _fetch_cron_runs,
    _fetch_kanban_runs,
    _kanban_task_to_run_status,
    _truncate,
)
from app.api.runs.schemas import UnifiedRunResponse


def _run(**kwargs: object) -> UnifiedRunResponse:
    defaults: dict[str, object] = {
        "id": "cron:1",
        "source": "cron",
        "status": "ok",
        "title": "Daily digest",
        "started_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "has_execution_steps": False,
    }
    defaults.update(kwargs)
    return UnifiedRunResponse(**defaults)


@pytest.fixture
def client() -> TestClient:
    from app.api.runs.router import router as runs_router

    app = FastAPI()
    app.include_router(runs_router, prefix="/api/v1")
    with TestClient(app) as test_client:
        yield test_client


class TestHelpers:
    def test_truncate_short_text(self) -> None:
        assert _truncate("hello", 10) == "hello"

    def test_truncate_long_text(self) -> None:
        assert _truncate("abcdefghij", 5) == "abcde..."

    def test_kanban_task_to_run_status(self) -> None:
        assert _kanban_task_to_run_status("running", None) == "running"
        assert _kanban_task_to_run_status("completed", None) == "ok"
        assert _kanban_task_to_run_status("failed", None) == "error"
        assert _kanban_task_to_run_status("failed", "task timed out") == "timed_out"
        assert _kanban_task_to_run_status("failed", "user cancelled run") == "cancelled"
        assert _kanban_task_to_run_status("blocked", "execution timed out") == "timed_out"
        assert _kanban_task_to_run_status("archived", None) == "cancelled"
        assert _kanban_task_to_run_status("unknown", "boom") == "error"


class TestFetchCronRuns:
    @pytest.mark.asyncio
    async def test_unavailable_when_manager_missing(self) -> None:
        with patch("app.core.cron.adapters.setup.get_cron_manager", return_value=None):
            items, available = await _fetch_cron_runs(None, 10)
        assert items == []
        assert available is False

    @pytest.mark.asyncio
    async def test_maps_execution_steps_flag(self) -> None:
        run_row = SimpleNamespace(
            id="run-1",
            job_id="job-1",
            status="ok",
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
            duration_ms=1000,
            error=None,
            output="done",
            metadata={"progressSteps": [{"tool_name": "search"}]},
        )
        job = SimpleNamespace(id="job-1", name="Digest", agent_id="agent-1")
        mgr = MagicMock()
        mgr.list_runs = AsyncMock(return_value=[run_row])
        mgr.list_jobs = AsyncMock(return_value=[job])

        with patch("app.core.cron.adapters.setup.get_cron_manager", return_value=mgr):
            items, available = await _fetch_cron_runs(None, 10)

        assert available is True
        assert len(items) == 1
        assert items[0].has_execution_steps is True
        assert items[0].job_id == "job-1"

    @pytest.mark.asyncio
    async def test_applies_status_filter(self) -> None:
        mgr = MagicMock()
        mgr.list_runs = AsyncMock(return_value=[])
        mgr.list_jobs = AsyncMock(return_value=[])

        with patch("app.core.cron.adapters.setup.get_cron_manager", return_value=mgr):
            await _fetch_cron_runs("error", 10)

        mgr.list_runs.assert_awaited_once()
        assert mgr.list_runs.await_args.kwargs["status"] == "error"

    @pytest.mark.asyncio
    async def test_running_filter_skips_cron_query(self) -> None:
        mgr = MagicMock()
        mgr.list_runs = AsyncMock(return_value=[])

        with patch("app.core.cron.adapters.setup.get_cron_manager", return_value=mgr):
            items, available = await _fetch_cron_runs("running", 10)

        assert items == []
        assert available is True
        mgr.list_runs.assert_not_called()


class TestFetchKanbanRuns:
    @pytest.mark.asyncio
    async def test_unavailable_when_service_missing(self) -> None:
        with patch("app.services.kanban.KanbanService.get_instance", return_value=None):
            items, available = await _fetch_kanban_runs(None, 10)
        assert items == []
        assert available is False

    @pytest.mark.asyncio
    async def test_empty_when_system_board_missing_is_available(self) -> None:
        svc = MagicMock()
        svc.list_boards = AsyncMock(return_value=[SimpleNamespace(board_id="b1", name="other")])
        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            items, available = await _fetch_kanban_runs(None, 10)
        assert items == []
        assert available is True


class TestListUnifiedRunsEndpoint:
    @patch("app.api.runs.router._fetch_background_shell_runs", new_callable=AsyncMock)
    @patch("app.api.runs.router._fetch_kanban_runs", new_callable=AsyncMock)
    @patch("app.api.runs.router._fetch_cron_runs", new_callable=AsyncMock)
    def test_merges_sources(
        self,
        mock_cron: AsyncMock,
        mock_kanban: AsyncMock,
        mock_background: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_cron.return_value = ([_run(id="cron:1")], True)
        mock_kanban.return_value = ([_run(id="kanban:1", source="kanban")], True)
        mock_background.return_value = ([_run(id="shell:1", source="background")], True)

        response = client.get("/api/v1/runs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["degraded"] is False
        assert data["failed_sources"] == []

    @patch("app.api.runs.router._fetch_background_shell_runs", new_callable=AsyncMock)
    @patch("app.api.runs.router._fetch_kanban_runs", new_callable=AsyncMock)
    @patch("app.api.runs.router._fetch_cron_runs", new_callable=AsyncMock)
    def test_marks_degraded_when_cron_unavailable(
        self,
        mock_cron: AsyncMock,
        mock_kanban: AsyncMock,
        mock_background: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_cron.return_value = ([], False)
        mock_kanban.return_value = ([_run(id="kanban:1", source="kanban")], True)
        mock_background.return_value = ([], True)

        response = client.get("/api/v1/runs")
        data = response.json()
        assert data["degraded"] is True
        assert data["failed_sources"] == ["cron"]
        assert data["total"] == 1

    @patch("app.api.runs.router._fetch_kanban_runs", new_callable=AsyncMock)
    @patch("app.api.runs.router._fetch_cron_runs", new_callable=AsyncMock)
    def test_kanban_collect_exception(
        self,
        mock_cron: AsyncMock,
        mock_kanban: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_cron.return_value = ([], True)
        mock_kanban.side_effect = RuntimeError("kanban down")

        response = client.get("/api/v1/runs")
        data = response.json()
        assert data["degraded"] is True
        assert "kanban" in data["failed_sources"]

    @patch("app.api.runs.router._fetch_cron_runs", new_callable=AsyncMock)
    def test_source_filter_only_fetches_cron(self, mock_cron: AsyncMock, client: TestClient) -> None:
        mock_cron.return_value = ([_run()], True)

        response = client.get("/api/v1/runs", params={"source": "cron"})
        assert response.status_code == 200
        mock_cron.assert_awaited_once()

    @patch("app.api.runs.router._fetch_background_shell_runs", new_callable=AsyncMock)
    @patch("app.api.runs.router._fetch_kanban_runs", new_callable=AsyncMock)
    @patch("app.api.runs.router._fetch_cron_runs", new_callable=AsyncMock)
    def test_collect_exception_marks_failed_source(
        self,
        mock_cron: AsyncMock,
        mock_kanban: AsyncMock,
        mock_background: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_cron.side_effect = RuntimeError("cron down")
        mock_kanban.return_value = ([], True)
        mock_background.return_value = ([], True)

        response = client.get("/api/v1/runs")
        data = response.json()
        assert data["degraded"] is True
        assert "cron" in data["failed_sources"]


class TestFetchBackgroundShellRuns:
    @pytest.mark.asyncio
    async def test_maps_running_task(self) -> None:
        task = SimpleNamespace(
            task_id="t1",
            status="running",
            created_at=1_700_000_000.0,
            completed_at=None,
            prompt="run tests",
            result_preview=None,
        )
        with patch(
            "app.services.agent.shell_background_tasks.list_shell_background_tasks",
            return_value=[task],
        ):
            items, available = await _fetch_background_shell_runs(None)

        assert available is True
        assert len(items) == 1
        assert items[0].status == "running"
        assert items[0].source == "background"

    @pytest.mark.asyncio
    async def test_filters_by_status_and_maps_terminal_states(self) -> None:
        tasks = [
            SimpleNamespace(
                task_id="t1",
                status="completed",
                created_at=1_700_000_000.0,
                completed_at=1_700_000_100.0,
                prompt="done",
                result_preview="ok",
            ),
            SimpleNamespace(
                task_id="t2",
                status="failed",
                created_at=1_700_000_000.0,
                completed_at=1_700_000_200.0,
                prompt="bad",
                result_preview=None,
            ),
            SimpleNamespace(
                task_id="t3",
                status="cancelled",
                created_at=1_700_000_000.0,
                completed_at=1_700_000_300.0,
                prompt="stop",
                result_preview=None,
            ),
        ]
        with patch(
            "app.services.agent.shell_background_tasks.list_shell_background_tasks",
            return_value=tasks,
        ):
            items, available = await _fetch_background_shell_runs("ok")

        assert available is True
        assert len(items) == 1
        assert items[0].status == "ok"


class TestFetchKanbanRunsTasks:
    @pytest.mark.asyncio
    async def test_lists_background_board_tasks(self) -> None:
        from myrm_agent_harness.toolkits.kanban.types import TaskStatus as KanbanStatus

        task = SimpleNamespace(
            task_id="k1",
            status=KanbanStatus.COMPLETED,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
            title="Auto task",
            description="desc",
            error=None,
            agent_id="agent-1",
        )
        board = SimpleNamespace(board_id="board-1", name="__background_tasks__")
        svc = MagicMock()
        svc.list_boards = AsyncMock(return_value=[board])
        svc.store.list_tasks = AsyncMock(return_value=[task])

        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            items, available = await _fetch_kanban_runs(None, 10)

        assert available is True
        assert len(items) == 1
        assert items[0].source == "kanban"
        assert items[0].status == "ok"

    @pytest.mark.asyncio
    async def test_maps_failed_timeout_to_timed_out(self) -> None:
        from myrm_agent_harness.toolkits.kanban.types import TaskStatus as KanbanStatus

        task = SimpleNamespace(
            task_id="k-timeout",
            status=KanbanStatus.FAILED,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
            title="Timed out task",
            description=None,
            error="execution timed out after 300s",
            agent_id=None,
        )
        board = SimpleNamespace(board_id="board-1", name="__background_tasks__")
        svc = MagicMock()
        svc.list_boards = AsyncMock(return_value=[board])
        svc.store.list_tasks = AsyncMock(return_value=[task])

        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            items, available = await _fetch_kanban_runs(None, 10)

        assert available is True
        assert len(items) == 1
        assert items[0].status == "timed_out"

    @pytest.mark.asyncio
    async def test_skips_archived_and_triage(self) -> None:
        from myrm_agent_harness.toolkits.kanban.types import TaskStatus as KanbanStatus

        task = SimpleNamespace(
            task_id="k2",
            status=KanbanStatus.ARCHIVED,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            completed_at=None,
            title="Archived",
            description=None,
            error=None,
            agent_id=None,
        )
        board = SimpleNamespace(board_id="board-1", name="__background_tasks__")
        svc = MagicMock()
        svc.list_boards = AsyncMock(return_value=[board])
        svc.store.list_tasks = AsyncMock(return_value=[task])

        with patch("app.services.kanban.KanbanService.get_instance", return_value=svc):
            items, available = await _fetch_kanban_runs(None, 10)

        assert available is True
        assert items == []


class TestListUnifiedRunsPagination:
    @patch("app.api.runs.router._fetch_background_shell_runs", new_callable=AsyncMock)
    @patch("app.api.runs.router._fetch_kanban_runs", new_callable=AsyncMock)
    @patch("app.api.runs.router._fetch_cron_runs", new_callable=AsyncMock)
    def test_pagination(
        self,
        mock_cron: AsyncMock,
        mock_kanban: AsyncMock,
        mock_background: AsyncMock,
        client: TestClient,
    ) -> None:
        runs = [
            _run(
                id=f"cron:{idx}",
                started_at=datetime(2026, 1, idx + 1, tzinfo=timezone.utc),
            )
            for idx in range(5)
        ]
        mock_cron.return_value = (runs, True)
        mock_kanban.return_value = ([], True)
        mock_background.return_value = ([], True)

        response = client.get("/api/v1/runs", params={"limit": 2, "offset": 1})
        data = response.json()
        assert response.status_code == 200
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["has_more"] is True
