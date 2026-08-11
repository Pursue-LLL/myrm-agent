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

from unittest.mock import AsyncMock, PropertyMock, patch

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

        project = _create_project(
            client, [str(dir_a)], name="Into Board", board_id=board_id
        )
        assert project["board_id"] == board_id

    @pytest.mark.asyncio
    async def test_create_project_rolls_back_when_any_task_creation_fails(
        self, client, tmp_path
    ) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel
        from app.services.kanban import KanbanService

        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()

        real_add_task = KanbanService.add_task
        captured: dict[str, str] = {}

        async def _flaky_add_task(self_, *args, **kwargs):
            if not captured:
                task = await real_add_task(self_, *args, **kwargs)
                captured["task_id"] = task.task_id
                captured["board_id"] = str(kwargs["board_id"])
                return task
            raise RuntimeError("board closed")

        with patch.object(KanbanService, "add_task", new=_flaky_add_task):
            resp = client.post(
                "/api/v1/batch-directories",
                json={
                    "name": "Atomic",
                    "prompt": "run",
                    "directories": [str(dir_a), str(dir_b)],
                },
            )

        # 任一目录建任务失败 → 整体失败，不创建半成品批次
        assert resp.status_code == 400
        assert "Failed to create batch tasks" in resp.json()["detail"]
        items = client.get("/api/v1/batch-directories").json()["items"]
        assert not any(p["board_id"] == captured["board_id"] for p in items)

        # 已建任务被回滚归档，不会残留为可执行任务
        async with get_session() as session:
            task = await session.get(KanbanTaskModel, captured["task_id"])
            assert task is not None
            assert task.status == TaskStatus.ARCHIVED.value

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
        item = next(
            i for i in body["items"] if i["project_id"] == project["project_id"]
        )
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

        # 有 active 任务时禁止删除；先取消（归档任务）再删除
        resp = client.delete(f"/api/v1/batch-directories/{project['project_id']}")
        assert resp.status_code == 400

        resp = client.post(f"/api/v1/batch-directories/{project['project_id']}/cancel")
        assert resp.status_code == 200

        resp = client.delete(f"/api/v1/batch-directories/{project['project_id']}")
        assert resp.status_code == 204

        resp = client.get(f"/api/v1/batch-directories/{project['project_id']}")
        assert resp.status_code == 404

    def test_delete_missing_project_returns_404(self, client) -> None:
        resp = client.delete("/api/v1/batch-directories/does-not-exist")
        assert resp.status_code == 404


class TestFinalize:
    @pytest.mark.asyncio
    async def test_maybe_finalize_success_sends_notification(
        self, client, tmp_path
    ) -> None:
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
            assert (
                kwargs["meta_data"]["action_url"]
                == f"/batch-directories/{project_id}"
            )

        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["status"] == "completed"
        assert detail["completed_tasks"] == 2
        assert detail["finished_at"] is not None

    @pytest.mark.asyncio
    async def test_maybe_finalize_partial_failure_marks_failed(
        self, client, tmp_path
    ) -> None:
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
    async def test_maybe_finalize_skips_when_tasks_pending(
        self, client, tmp_path
    ) -> None:
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

    @pytest.mark.asyncio
    async def test_hook_triggers_on_task_archived(self) -> None:
        """task_archived (LLM archive tool path) must also schedule finalize."""
        from app.services.batch_directory.service import BatchDirectoryService

        service = BatchDirectoryService.get_instance()

        class FakeTask:
            metadata = {"batch_project_id": "b-archived"}

        with patch.object(
            BatchDirectoryService,
            "maybe_finalize",
            new_callable=AsyncMock,
        ) as mock_finalize:
            service.dispatcher_event_hook("task_archived", FakeTask())
            await asyncio_sleep_zero()
            mock_finalize.assert_awaited_once_with("b-archived")


class TestCancelRunningExecution:
    @pytest.mark.asyncio
    async def test_cancel_project_cancels_running_task_before_archiving(
        self, client, tmp_path
    ) -> None:
        """RUNNING tasks are cancelled in the dispatcher before being archived."""
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]
        task_id = project["created_task_ids"][0]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_id)
            assert task is not None
            task.status = TaskStatus.RUNNING.value
            await session.commit()

        fake_kanban = AsyncMock()
        fake_kanban.cancel_task_execution = AsyncMock(return_value=True)
        fake_kanban.move_task = AsyncMock(return_value=None)
        service = BatchDirectoryService.get_instance()
        with patch.object(
            BatchDirectoryService,
            "kanban",
            new_callable=PropertyMock,
        ) as mock_prop:
            mock_prop.return_value = fake_kanban
            result = await service.cancel_project(project_id)

        fake_kanban.cancel_task_execution.assert_awaited_once_with(task_id)
        fake_kanban.move_task.assert_awaited_once_with(
            task_id,
            TaskStatus.ARCHIVED,
            result="",
            metadata={"cancelled_by": "batch_project"},
        )
        assert result["status"] == "cancelled"


class TestArtifactVerification:
    @pytest.mark.asyncio
    async def test_missing_artifacts_flagged_on_finalize(
        self, client, tmp_path
    ) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]
        task_id = project["created_task_ids"][0]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_id)
            assert task is not None
            task.status = TaskStatus.COMPLETED.value
            task.result = "done"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        with patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            new_callable=AsyncMock,
        ):
            await service.maybe_finalize(project_id)

        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["status"] == "completed"
        assert detail["tasks"][0]["artifact_status"] == "missing"
        assert detail["missing_artifact_directories"] == [str(dir_a)]

    @pytest.mark.asyncio
    async def test_matching_artifacts_verified(self, client, tmp_path) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        (dir_a / "test_foo.py").write_text("x", encoding="utf-8")
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]
        task_id = project["created_task_ids"][0]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_id)
            assert task is not None
            task.status = TaskStatus.COMPLETED.value
            task.result = "done"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        with patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            new_callable=AsyncMock,
        ):
            await service.maybe_finalize(project_id)

        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["tasks"][0]["artifact_status"] == "verified"
        assert detail["missing_artifact_directories"] == []

    @pytest.mark.asyncio
    async def test_failed_directory_listed_in_failed_directories(
        self, client, tmp_path
    ) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]
        task_id = project["created_task_ids"][0]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_id)
            assert task is not None
            task.status = TaskStatus.FAILED.value
            task.error = "boom"
            await session.commit()

        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["failed_directories"] == [str(dir_a)]
        assert detail["tasks"][0]["artifact_status"] == "not_specified"


class TestFinalizeIdempotency:
    @pytest.mark.asyncio
    async def test_second_finalize_does_not_resend_notification(
        self, client, tmp_path
    ) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]
        task_id = project["created_task_ids"][0]

        async with get_session() as session:
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
            await service.maybe_finalize(project_id)
            mock_notify.assert_awaited_once()  # 幂等：不重复通知

        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["status"] == "completed"


class TestArtifactPatternValidation:
    def test_create_project_rejects_absolute_artifact_pattern(
        self, client, tmp_path
    ) -> None:
        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        resp = client.post(
            "/api/v1/batch-directories",
            json={
                "name": "Abs",
                "prompt": "p",
                "directories": [str(dir_a)],
                "artifact_patterns": ["/etc/passwd"],
            },
        )
        assert resp.status_code == 422

    def test_create_project_rejects_traversal_artifact_pattern(
        self, client, tmp_path
    ) -> None:
        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        resp = client.post(
            "/api/v1/batch-directories",
            json={
                "name": "Traversal",
                "prompt": "p",
                "directories": [str(dir_a)],
                "artifact_patterns": ["../secret.txt"],
            },
        )
        assert resp.status_code == 422

    def test_create_project_rejects_empty_artifact_pattern(
        self, client, tmp_path
    ) -> None:
        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        resp = client.post(
            "/api/v1/batch-directories",
            json={
                "name": "Empty",
                "prompt": "p",
                "directories": [str(dir_a)],
                "artifact_patterns": ["  "],
            },
        )
        assert resp.status_code == 422

    def test_verify_artifact_patterns_never_raises_on_absolute_pattern(
        self, tmp_path
    ) -> None:
        """Absolute-path globs raise NotImplementedError; the runtime check must swallow it."""
        from app.services.batch_directory._helpers import _verify_artifact_patterns

        assert _verify_artifact_patterns(str(tmp_path), ["/etc/passwd"]) is False
        assert _verify_artifact_patterns(str(tmp_path), ["../escaped.txt"]) is False


class TestCancelInReview:
    @pytest.mark.asyncio
    async def test_cancel_project_rejects_in_review_task_before_archiving(
        self, client, tmp_path
    ) -> None:
        """IN_REVIEW tasks cannot be manually moved out; they must be rejected first."""
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]
        task_id = project["created_task_ids"][0]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_id)
            assert task is not None
            task.status = TaskStatus.IN_REVIEW.value
            await session.commit()

        fake_kanban = AsyncMock()
        fake_kanban.reject_task = AsyncMock(return_value=None)
        fake_kanban.move_task = AsyncMock(return_value=None)
        service = BatchDirectoryService.get_instance()
        with patch.object(
            BatchDirectoryService,
            "kanban",
            new_callable=PropertyMock,
        ) as mock_prop:
            mock_prop.return_value = fake_kanban
            result = await service.cancel_project(project_id)

        fake_kanban.reject_task.assert_awaited_once_with(
            task_id, reason="Batch project cancelled"
        )
        fake_kanban.move_task.assert_awaited_once_with(
            task_id,
            TaskStatus.ARCHIVED,
            result="",
            metadata={"cancelled_by": "batch_project"},
        )
        assert result["status"] == "cancelled"
        assert task_id in result["cancelled_task_ids"]


class TestRetryFailed:
    @pytest.mark.asyncio
    async def test_retry_failed_creates_new_tasks_and_reopens_project(
        self, client, tmp_path
    ) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        project = _create_project(client, [str(dir_a), str(dir_b)])
        project_id = project["project_id"]
        task_ids = project["created_task_ids"]

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
        ):
            await service.maybe_finalize(project_id)
        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["status"] == "failed"

        result = await service.retry_failed(project_id)
        assert result is not None
        assert len(result["retried_task_ids"]) == 2
        assert result["status"] == "running"
        assert result["finished_at"] is None
        # 聚合口径：每目录只取最新任务，total_tasks 仍是 2（重试任务替换旧任务）
        assert result["total_tasks"] == 2

        fresh = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert fresh["status"] == "running"
        running_tasks = [
            t for t in fresh["tasks"] if t["status"] == TaskStatus.READY.value
        ]
        assert len(running_tasks) == 2

    @pytest.mark.asyncio
    async def test_retry_failed_nothing_to_retry_keeps_state(
        self, client, tmp_path
    ) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        # 产出满足 artifact_patterns 的产物，使目录不再可重试
        (dir_a / "test_alpha.py").write_text("x", encoding="utf-8")
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, project["created_task_ids"][0])
            assert task is not None
            task.status = TaskStatus.COMPLETED.value
            task.result = "ok"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        with patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            new_callable=AsyncMock,
        ):
            await service.maybe_finalize(project_id)

        result = await service.retry_failed(project_id)
        assert result is not None
        assert result["status"] == "completed"
        assert result["retried_task_ids"] == []

    @pytest.mark.asyncio
    async def test_retry_missing_project_returns_none(self) -> None:
        service = BatchDirectoryService.get_instance()
        assert await service.retry_failed("does-not-exist") is None


class TestRetryTask:
    @pytest.mark.asyncio
    async def test_retry_task_creates_single_fresh_task(self, client, tmp_path) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        project = _create_project(client, [str(dir_a), str(dir_b)])
        project_id = project["project_id"]
        task_ids = project["created_task_ids"]

        # 仅 alpha 失败，beta 保持运行中
        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_ids[0])
            assert task is not None
            task.status = TaskStatus.FAILED.value
            task.error = "boom"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        result = await service.retry_task(project_id, task_ids[0])
        assert result is not None
        assert len(result["retried_task_ids"]) == 1
        assert result["status"] == "running"
        # latest-per-directory 口径下 beta 的任务仍计数
        assert result["total_tasks"] == 2

        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        # latest-per-directory：alpha 显示新任务，beta 保持原任务
        assert len(detail["tasks"]) == 2
        assert all(t["status"] == TaskStatus.READY.value for t in detail["tasks"])

    @pytest.mark.asyncio
    async def test_retry_task_rejects_successful_task(self, client, tmp_path) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        (dir_a / "test_alpha.py").write_text("x", encoding="utf-8")
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]
        task_id = project["created_task_ids"][0]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_id)
            assert task is not None
            task.status = TaskStatus.COMPLETED.value
            task.result = "ok"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        with pytest.raises(ValueError, match="Only failed or artifact-missing"):
            await service.retry_task(project_id, task_id)

    @pytest.mark.asyncio
    async def test_retry_task_rejects_stale_task(self, client, tmp_path) -> None:
        """After a directory was retried, its old task record is no longer
        the current task and must not be retryable again."""
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]
        old_task_id = project["created_task_ids"][0]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, old_task_id)
            assert task is not None
            task.status = TaskStatus.FAILED.value
            task.error = "boom"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        first = await service.retry_task(project_id, old_task_id)
        assert first is not None
        new_task_id = first["retried_task_ids"][0]

        with pytest.raises(ValueError, match="not the current task"):
            await service.retry_task(project_id, old_task_id)

        # 新任务尚未终态，不可重试
        with pytest.raises(ValueError, match="Only failed or artifact-missing"):
            await service.retry_task(project_id, new_task_id)

    @pytest.mark.asyncio
    async def test_retry_missing_project_returns_none(self) -> None:
        service = BatchDirectoryService.get_instance()
        assert await service.retry_task("does-not-exist", "t") is None


class TestRerunProject:
    @pytest.mark.asyncio
    async def test_rerun_project_requeues_all_directories(
        self, client, tmp_path
    ) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        project = _create_project(client, [str(dir_a), str(dir_b)])
        project_id = project["project_id"]

        async with get_session() as session:
            for task_id in project["created_task_ids"]:
                task = await session.get(KanbanTaskModel, task_id)
                assert task is not None
                task.status = TaskStatus.COMPLETED.value
                task.result = "ok"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        with patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            new_callable=AsyncMock,
        ):
            await service.maybe_finalize(project_id)
        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["status"] == "completed"

        result = await service.rerun_project(project_id)
        assert result is not None
        assert len(result["rerun_task_ids"]) == 2
        assert result["status"] == "running"
        assert result["finished_at"] is None
        assert result["total_tasks"] == 2

    @pytest.mark.asyncio
    async def test_rerun_rejects_running_project(self, client, tmp_path) -> None:
        """Rerunning a project whose tasks are still in flight would create
        duplicate tasks per directory; it must be rejected until terminal."""
        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]

        service = BatchDirectoryService.get_instance()
        with pytest.raises(ValueError, match="still running"):
            await service.rerun_project(project_id)

    @pytest.mark.asyncio
    async def test_rerun_missing_project_returns_none(self) -> None:
        service = BatchDirectoryService.get_instance()
        assert await service.rerun_project("does-not-exist") is None


class TestDeleteProtection:
    @pytest.mark.asyncio
    async def test_delete_rejects_project_with_active_tasks(
        self, client, tmp_path
    ) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, project["created_task_ids"][0])
            assert task is not None
            task.status = TaskStatus.RUNNING.value
            await session.commit()

        service = BatchDirectoryService.get_instance()
        with pytest.raises(ValueError, match="cancel it before deleting"):
            await service.delete_project(project_id)

        # 取消后任务全部终态，可以删除
        resp = client.post(f"/api/v1/batch-directories/{project_id}/cancel")
        assert resp.status_code == 200
        assert await service.delete_project(project_id) is True


class TestRetryThenComplete:
    @pytest.mark.asyncio
    async def test_project_reaches_completed_after_retry_succeeds(
        self, client, tmp_path
    ) -> None:
        """After retry, aggregation must key on the latest task per directory:
        once the fresh tasks succeed, the project reaches ``completed`` instead
        of being stuck forever with historical failures."""
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]
        old_task_id = project["created_task_ids"][0]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, old_task_id)
            assert task is not None
            task.status = TaskStatus.FAILED.value
            task.error = "boom"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        result = await service.retry_failed(project_id)
        assert result is not None
        assert len(result["retried_task_ids"]) == 1
        new_task_id = result["retried_task_ids"][0]

        # 重试任务成功且产物满足校验
        async with get_session() as session:
            task = await session.get(KanbanTaskModel, new_task_id)
            assert task is not None
            task.status = TaskStatus.COMPLETED.value
            task.result = "ok"
            await session.commit()
        (dir_a / "test_alpha.py").write_text("x", encoding="utf-8")

        with patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            await service.maybe_finalize(project_id)
            mock_notify.assert_awaited_once()
            assert mock_notify.await_args.kwargs["meta_data"]["status"] == "completed"

        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["status"] == "completed"
        assert detail["completed_tasks"] == 1
        assert detail["failed_tasks"] == 0
        assert detail["total_tasks"] == 1


class TestPauseResume:
    @pytest.mark.asyncio
    async def test_pause_freezes_queue_and_running_tasks(self, client, tmp_path) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        project = _create_project(client, [str(dir_a), str(dir_b)])
        project_id = project["project_id"]
        task_ids = project["created_task_ids"]

        # alpha 运行中，beta 排队等待
        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_ids[0])
            assert task is not None
            task.status = TaskStatus.RUNNING.value
            await session.commit()

        service = BatchDirectoryService.get_instance()
        result = await service.pause_project(project_id)
        assert result is not None
        assert result["status"] == "paused"
        assert len(result["paused_task_ids"]) == 2

        async with get_session() as session:
            for task_id in task_ids:
                task = await session.get(KanbanTaskModel, task_id)
                assert task is not None
                assert task.status == TaskStatus.BLOCKED.value
                assert task.block_kind == "human"
                assert task.blocked_reason == "batch_pause"

    @pytest.mark.asyncio
    async def test_pause_is_idempotent(self, client, tmp_path) -> None:
        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]

        service = BatchDirectoryService.get_instance()
        first = await service.pause_project(project_id)
        assert first is not None
        second = await service.pause_project(project_id)
        assert second is not None
        assert second["status"] == "paused"

    @pytest.mark.asyncio
    async def test_pause_terminal_project_rejected(self, client, tmp_path) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, project["created_task_ids"][0])
            assert task is not None
            task.status = TaskStatus.COMPLETED.value
            task.result = "ok"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        with patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            new_callable=AsyncMock,
        ):
            await service.maybe_finalize(project_id)

        with pytest.raises(ValueError, match="nothing to pause"):
            await service.pause_project(project_id)

    @pytest.mark.asyncio
    async def test_resume_unblocks_paused_tasks(self, client, tmp_path) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        project = _create_project(client, [str(dir_a), str(dir_b)])
        project_id = project["project_id"]
        task_ids = project["created_task_ids"]

        service = BatchDirectoryService.get_instance()
        await service.pause_project(project_id)

        result = await service.resume_project(project_id)
        assert result is not None
        assert result["status"] == "running"
        assert len(result["resumed_task_ids"]) == 2
        assert result["finished_at"] is None

        async with get_session() as session:
            for task_id in task_ids:
                task = await session.get(KanbanTaskModel, task_id)
                assert task is not None
                assert task.status == TaskStatus.READY.value
                assert task.block_kind is None

    @pytest.mark.asyncio
    async def test_resume_non_paused_rejected(self, client, tmp_path) -> None:
        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]

        service = BatchDirectoryService.get_instance()
        with pytest.raises(ValueError, match="not paused"):
            await service.resume_project(project_id)

    @pytest.mark.asyncio
    async def test_retry_and_rerun_rejected_while_paused(self, client, tmp_path) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, project["created_task_ids"][0])
            assert task is not None
            task.status = TaskStatus.FAILED.value
            task.error = "boom"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        await service.pause_project(project_id)

        with pytest.raises(ValueError, match="paused"):
            await service.retry_failed(project_id)
        with pytest.raises(ValueError, match="paused"):
            await service.rerun_project(project_id)


class TestApproveAllResults:
    @pytest.mark.asyncio
    async def test_approve_all_promotes_in_review_tasks(self, client, tmp_path) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        project = _create_project(client, [str(dir_a), str(dir_b)])
        project_id = project["project_id"]
        task_ids = project["created_task_ids"]

        # 一个待审批、一个已完成
        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_ids[0])
            assert task is not None
            task.status = TaskStatus.IN_REVIEW.value
            task.result = "ok"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        result = await service.approve_all_results(project_id)
        assert result is not None
        assert len(result["approved_task_ids"]) == 1
        assert result["approved_task_ids"][0] == task_ids[0]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_ids[0])
            assert task is not None
            assert task.status == TaskStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_approve_all_is_idempotent(self, client, tmp_path) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, project["created_task_ids"][0])
            assert task is not None
            task.status = TaskStatus.IN_REVIEW.value
            task.result = "ok"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        first = await service.approve_all_results(project_id)
        assert first is not None
        second = await service.approve_all_results(project_id)
        assert second is not None
        assert second["approved_task_ids"] == []

    @pytest.mark.asyncio
    async def test_approve_all_missing_project_returns_none(self) -> None:
        service = BatchDirectoryService.get_instance()
        assert await service.approve_all_results("does-not-exist") is None


async def asyncio_sleep_zero() -> None:
    """Yield control so scheduled asyncio task (created inside a running loop)
    actually runs. In pytest-asyncio async tests a running loop is available."""
    import asyncio

    await asyncio.sleep(0)
