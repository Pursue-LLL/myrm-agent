"""BatchDirectory REST API + service integration tests.

Exercises the full stack (router -> BatchDirectoryService -> KanbanService ->
SqlAlchemyKanbanStore -> SQLite) without mocks for orchestration, and covers
project finalization + notification dispatch paths.

Covers:
- create project (auto board, one Kanban task per directory)
- list / get project with aggregated progress
- cancel (archive non-terminal tasks) and delete
- maybe_finalize terminal detection + SystemNotification
- dispatcher_event_hook scheduling
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.kanban.types import TaskStatus

from app.api.batch_directory.router import router as batch_directory_router
from app.api.kanban.router import router as kanban_router
from app.services.batch_directory import BatchDirectoryService
from app.services.kanban import KanbanService


@pytest.fixture(autouse=True)
def _reset_singletons() -> None:
    """Ensure each test gets fresh KanbanService/BatchDirectoryService singletons."""
    KanbanService._instance = None
    BatchDirectoryService._instance = None
    yield
    KanbanService._instance = None
    BatchDirectoryService._instance = None


@pytest.fixture
def client(tmp_path) -> TestClient:
    app = FastAPI()
    app.include_router(batch_directory_router, prefix="/api/v1")
    app.include_router(kanban_router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c


def _create_project(
    client: TestClient,
    directories: list[str],
    name: str = "Batch Test",
    *,
    board_id: str | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "name": name,
        "prompt": "Analyze the codebase and report.",
        "directories": directories,
        "concurrency": 2,
        "notify_enabled": True,
        "artifact_patterns": ["**/test_*.py"],
    }
    if board_id is not None:
        body["board_id"] = board_id
    resp = client.post("/api/v1/batch-directories", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCreateProject:
    def test_create_project_creates_board_and_tasks(self, client, tmp_path) -> None:
        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()

        project = _create_project(client, [str(dir_a), str(dir_b)])

        assert project["status"] == "running"
        assert project["total_tasks"] == 2
        assert len(project["created_task_ids"]) == 2
        assert project["board_id"]
        assert len(project["failed_directories"]) == 0

        # 详情页任务可见
        resp = client.get(f"/api/v1/batch-directories/{project['project_id']}")
        assert resp.status_code == 200
        detail = resp.json()
        assert len(detail["tasks"]) == 2
        assert {t["workspace_path"] for t in detail["tasks"]} == {
            str(dir_a),
            str(dir_b),
        }

    def test_create_project_with_existing_board(self, client, tmp_path) -> None:
        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        board_resp = client.post("/api/v1/kanban/boards", json={"name": "Target Board"})
        assert board_resp.status_code == 201
        board_id = board_resp.json()["board_id"]

        project = _create_project(client, [str(dir_a)], name="Into Board", board_id=board_id)
        assert project["board_id"] == board_id

    def test_create_project_rejects_missing_directory(self, client, tmp_path) -> None:
        resp = client.post(
            "/api/v1/batch-directories",
            json={
                "name": "Bad",
                "prompt": "p",
                "directories": [str(tmp_path / "nope")],
            },
        )
        assert resp.status_code == 400

    def test_create_project_rejects_missing_name(self, client, tmp_path) -> None:
        resp = client.post(
            "/api/v1/batch-directories",
            json={"name": " ", "prompt": "p", "directories": [str(tmp_path)]},
        )
        assert resp.status_code == 400


class TestListGetProjects:
    def test_list_projects_aggregates_statuses(self, client, tmp_path) -> None:
        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        project = _create_project(client, [str(dir_a), str(dir_b)], name="Agg Test")

        resp = client.get("/api/v1/batch-directories")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        item = next(i for i in body["items"] if i["project_id"] == project["project_id"])
        assert item["total_tasks"] == 2
        assert item["completed_tasks"] == 0
        assert item["artifact_patterns"] == ["**/test_*.py"]

    def test_get_missing_project_returns_404(self, client) -> None:
        resp = client.get("/api/v1/batch-directories/does-not-exist")
        assert resp.status_code == 404


class TestCancelDelete:
    def test_cancel_project_archives_tasks(self, client, tmp_path) -> None:
        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])

        resp = client.post(f"/api/v1/batch-directories/{project['project_id']}/cancel")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "cancelled"
        assert len(body["cancelled_task_ids"]) == 1

        # 任务已归档
        detail = client.get(f"/api/v1/batch-directories/{project['project_id']}").json()
        assert detail["tasks"][0]["status"] == TaskStatus.ARCHIVED.value

    def test_cancel_missing_project_returns_404(self, client) -> None:
        resp = client.post("/api/v1/batch-directories/does-not-exist/cancel")
        assert resp.status_code == 404

    def test_delete_project(self, client, tmp_path) -> None:
        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])

        resp = client.delete(f"/api/v1/batch-directories/{project['project_id']}")
        assert resp.status_code == 204

        resp = client.get(f"/api/v1/batch-directories/{project['project_id']}")
        assert resp.status_code == 404

    def test_delete_missing_project_returns_404(self, client) -> None:
        resp = client.delete("/api/v1/batch-directories/does-not-exist")
        assert resp.status_code == 404


class TestFinalize:
    @pytest.mark.asyncio
    async def test_maybe_finalize_success_sends_notification(self, client, tmp_path) -> None:
        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        project = _create_project(client, [str(dir_a), str(dir_b)])
        project_id = project["project_id"]
        task_ids = project["created_task_ids"]

        # 直接把任务标记为完成
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        async with get_session() as session:
            for task_id in task_ids:
                task = await session.get(KanbanTaskModel, task_id)
                assert task is not None
                task.status = TaskStatus.COMPLETED.value
                task.result = "ok"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        with patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            await service.maybe_finalize(project_id)
            mock_notify.assert_awaited_once()
            kwargs = mock_notify.await_args.kwargs
            assert kwargs["meta_data"]["status"] == "completed"
            assert kwargs["meta_data"]["completed"] == 2

        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["status"] == "completed"
        assert detail["completed_tasks"] == 2
        assert detail["finished_at"] is not None

    @pytest.mark.asyncio
    async def test_maybe_finalize_partial_failure_marks_failed(self, client, tmp_path) -> None:
        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        project = _create_project(client, [str(dir_a), str(dir_b)])
        project_id = project["project_id"]
        task_ids = project["created_task_ids"]

        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        async with get_session() as session:
            for task_id in task_ids:
                task = await session.get(KanbanTaskModel, task_id)
                assert task is not None
                task.status = TaskStatus.FAILED.value
                task.error = "boom"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        with patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            await service.maybe_finalize(project_id)
            mock_notify.assert_awaited_once()
            assert mock_notify.await_args.kwargs["meta_data"]["status"] == "failed"
            assert mock_notify.await_args.kwargs["meta_data"]["failed"] == 2

        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["status"] == "failed"
        assert detail["failed_tasks"] == 2

    @pytest.mark.asyncio
    async def test_maybe_finalize_skips_when_tasks_pending(self, client, tmp_path) -> None:
        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        project = _create_project(client, [str(dir_a), str(dir_b)])
        project_id = project["project_id"]

        service = BatchDirectoryService.get_instance()
        with patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            await service.maybe_finalize(project_id)
            mock_notify.assert_not_awaited()

        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["status"] == "running"


class TestDispatcherHook:
    @pytest.mark.asyncio
    async def test_hook_schedules_finalize_for_batch_task(self, tmp_path) -> None:
        from app.database.connection import get_session
        from app.database.models.batch_directory import BatchDirectoryProjectModel

        project_id = "b-hook"
        async with get_session() as session:
            session.add(
                BatchDirectoryProjectModel(
                    id=project_id,
                    name="Hook Test",
                    prompt="p",
                    status="running",
                    concurrency=1,
                    notify_enabled=False,
                    directories_json=[],
                )
            )
            await session.commit()

        from app.services.batch_directory.service import BatchDirectoryService

        service = BatchDirectoryService.get_instance()

        class FakeTask:
            metadata = {"batch_project_id": project_id}

        with patch.object(
            BatchDirectoryService,
            "maybe_finalize",
            new_callable=AsyncMock,
        ) as mock_finalize:
            service.dispatcher_event_hook("task_completed", FakeTask())
            await asyncio_sleep_zero()
            mock_finalize.assert_awaited_once_with(project_id)

    def test_hook_ignores_non_final_events(self) -> None:
        from app.services.batch_directory.service import BatchDirectoryService

        service = BatchDirectoryService.get_instance()

        class FakeTask:
            metadata = {"batch_project_id": "b-x"}

        with patch.object(
            BatchDirectoryService,
            "maybe_finalize",
            new_callable=AsyncMock,
        ) as mock_finalize:
            service.dispatcher_event_hook("task_updated", FakeTask())
            mock_finalize.assert_not_awaited()

    def test_hook_ignores_tasks_without_batch_meta(self) -> None:
        from app.services.batch_directory.service import BatchDirectoryService

        service = BatchDirectoryService.get_instance()

        class FakeTask:
            metadata = {}

        with patch.object(
            BatchDirectoryService,
            "maybe_finalize",
            new_callable=AsyncMock,
        ) as mock_finalize:
            service.dispatcher_event_hook("task_completed", FakeTask())
            mock_finalize.assert_not_awaited()


async def asyncio_sleep_zero() -> None:
    """Yield control so scheduled asyncio task (created inside a running loop)
    actually runs. In pytest-asyncio async tests a running loop is available."""
    import asyncio

    await asyncio.sleep(0)
