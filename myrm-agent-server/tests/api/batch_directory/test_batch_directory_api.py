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

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.kanban.types import TaskStatus

from app.api.batch_directory.router import router as batch_directory_router
from app.api.kanban.router import router as kanban_router
from app.services.agent.outbound_notify.types import NotifyResult, NotifyTarget
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

    def test_create_project_forwards_advanced_settings_to_tasks(
        self, client, tmp_path
    ) -> None:
        """agent_id / model_override / max_runtime_seconds / require_approval are
        persisted on the project and forwarded to every created Kanban task.

        A silent drop of any of these would disable timeout protection, review
        gating or agent pinning for the whole batch, so the round trip is
        asserted end-to-end through the Kanban task detail API.
        """
        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        from myrm_agent_harness.backends.profiles.types import AgentProfile

        from app.database.connection import get_session
        from app.database.repositories.agent_repo import AgentRepository

        async def _register_agent() -> None:
            async with get_session() as session:
                await AgentRepository.create_profile(
                    session,
                    AgentProfile(
                        id="ag-42",
                        display_name="Advanced Batch Agent",
                        metadata={},
                    ),
                )
                await session.commit()

        asyncio.run(_register_agent())

        resp = client.post(
            "/api/v1/batch-directories",
            json={
                "name": "Advanced Batch",
                "prompt": "Analyze the codebase.",
                "directories": [str(dir_a)],
                "concurrency": 1,
                "agent_id": "ag-42",
                "model_override": "openai/gpt-test",
                "max_runtime_seconds": 3600,
                "require_approval": True,
            },
        )
        assert resp.status_code == 201, resp.text
        project = resp.json()
        assert project["agent_id"] == "ag-42"
        assert project["model_override"] == "openai/gpt-test"
        assert project["max_runtime_seconds"] == 3600
        assert project["require_approval"] is True

        detail_resp = client.get(f"/api/v1/batch-directories/{project['project_id']}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert len(detail["tasks"]) == 1
        task_id = detail["tasks"][0]["task_id"]

        task_resp = client.get(f"/api/v1/kanban/tasks/{task_id}")
        assert task_resp.status_code == 200
        task = task_resp.json()
        assert task["agent_id"] == "ag-42"
        assert task["model_override"] == "openai/gpt-test"
        assert task["max_runtime_seconds"] == 3600
        assert task["require_approval"] is True

        board_resp = client.get(f"/api/v1/kanban/boards/{project['board_id']}")
        assert board_resp.status_code == 200
        settings = board_resp.json()["settings"]
        assert settings["max_concurrent_tasks"] == 1

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
                kwargs["meta_data"]["action_url"] == f"/batch-directories/{project_id}"
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
            assert mock_notify.await_args.kwargs["meta_data"]["failed_directories"] == [
                str(dir_a),
                str(dir_b),
            ]
            message = mock_notify.await_args.kwargs["message"]
            assert "Failed directories:" in message
            assert str(dir_a) in message
            assert str(dir_b) in message
            assert "Duration:" in message

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

    @pytest.mark.asyncio
    async def test_retry_failed_does_not_overwrite_concurrent_cancel(
        self, client, tmp_path
    ) -> None:
        """A concurrent cancel that flips the project to ``cancelled`` while
        retry is fanning out must win — retry reopens the project with a
        conditional ``expected_status`` guard, so a concurrent cancel is never
        overwritten back to ``running`` (same guard as resume).

        The race window requires a non-terminal project: ``cancel_project``
        only flips non-terminal projects (``service.py`` guards on
        ``_PROJECT_TERMINAL_STATUSES``), so the project stays ``running``
        while a failed directory is retried and the user cancels concurrently.
        """
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel
        from app.services.batch_directory._run import (
            fan_out_batch_tasks as real_fan_out,
        )

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]
        task_ids = project["created_task_ids"]

        # 项目保持 running（非终态），仅将任务置 FAILED 模拟部分目录失败
        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_ids[0])
            assert task is not None
            task.status = TaskStatus.FAILED.value
            task.error = "boom"
            await session.commit()

        service = BatchDirectoryService.get_instance()

        async def cancel_after_fanout(kanban, **kwargs):
            created, errors = await real_fan_out(kanban, **kwargs)
            # 模拟并发取消：fan_out 完成后、_reopen_running 前项目被置 cancelled
            await service.cancel_project(project_id)
            return created, errors

        with patch(
            "app.services.batch_directory._retry.fan_out_batch_tasks",
            new=cancel_after_fanout,
        ):
            result = await service.retry_failed(project_id)

        assert result is not None
        assert result["status"] == "cancelled"


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
    async def test_pause_freezes_queue_and_running_tasks(
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
    async def test_retry_and_rerun_rejected_while_paused(
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
            task.status = TaskStatus.FAILED.value
            task.error = "boom"
            await session.commit()

        service = BatchDirectoryService.get_instance()
        await service.pause_project(project_id)

        with pytest.raises(ValueError, match="paused"):
            await service.retry_failed(project_id)
        with pytest.raises(ValueError, match="paused"):
            await service.rerun_project(project_id)

    @pytest.mark.asyncio
    async def test_pause_cancels_running_execution_before_block(
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

        # alpha 运行中（有活跃 agent 执行需要被取消）
        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_ids[0])
            assert task is not None
            task.status = TaskStatus.RUNNING.value
            await session.commit()

        service = BatchDirectoryService.get_instance()
        real_cancel = service.kanban.cancel_task_execution
        cancel_spy = AsyncMock(side_effect=lambda tid: real_cancel(tid))
        with patch.object(service.kanban, "cancel_task_execution", new=cancel_spy):
            result = await service.pause_project(project_id)
        assert result is not None
        assert result["status"] == "paused"
        assert len(result["paused_task_ids"]) == 2
        cancelled = {c.args[0] for c in cancel_spy.await_args_list}
        assert task_ids[0] in cancelled

    @pytest.mark.asyncio
    async def test_pause_then_cancel_archives_frozen_tasks(
        self, client, tmp_path
    ) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]
        task_id = project["created_task_ids"][0]

        service = BatchDirectoryService.get_instance()
        await service.pause_project(project_id)

        result = await service.cancel_project(project_id)
        assert result is not None
        assert result["status"] == "cancelled"
        assert task_id in result["cancelled_task_ids"]

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_id)
            assert task is not None
            assert task.status == TaskStatus.ARCHIVED.value

    @pytest.mark.asyncio
    async def test_resume_without_frozen_tasks_still_reopens(
        self, client, tmp_path
    ) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]
        task_id = project["created_task_ids"][0]

        service = BatchDirectoryService.get_instance()
        await service.pause_project(project_id)

        # 暂停期间任务已全部终态（例如审批在别处完成），无 batch_pause 冻结任务
        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_id)
            assert task is not None
            task.status = TaskStatus.COMPLETED.value
            task.result = "ok"
            await session.commit()

        result = await service.resume_project(project_id)
        assert result is not None
        assert result["status"] == "running"
        assert result["resumed_task_ids"] == []
        assert result["finished_at"] is None

    @pytest.mark.asyncio
    async def test_resume_keeps_paused_when_unblock_fails(
        self, client, tmp_path
    ) -> None:
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]

        service = BatchDirectoryService.get_instance()
        await service.pause_project(project_id)

        real_move = service.kanban.move_task

        async def fail_move(task_id: str, target, **kwargs):
            if target == TaskStatus.READY:
                raise RuntimeError("boom")
            return await real_move(task_id, target, **kwargs)

        with patch.object(service.kanban, "move_task", new=fail_move):
            result = await service.resume_project(project_id)
        assert result is not None
        assert result["status"] == "paused"
        assert result["resumed_task_ids"] == []

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, project["created_task_ids"][0])
            assert task is not None
            assert task.status == TaskStatus.BLOCKED.value

    @pytest.mark.asyncio
    async def test_pause_skips_task_that_finished_during_freeze(
        self, client, tmp_path
    ) -> None:
        """W1: a task that reaches a terminal state after the pause snapshot
        (while the freeze is in flight) must keep its result and be skipped —
        no cancel/move is issued against it, avoiding a redundant re-run."""
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
        real_get = service.kanban.get_task
        real_cancel = service.kanban.cancel_task_execution

        async def get_task_fresh(task_id: str):
            task = await real_get(task_id)
            if task_id == task_ids[0]:
                # 模拟 pause 快照后 alpha 立即完成：复查时已是终态
                task.status = TaskStatus.COMPLETED
                task.result = "done"
            return task

        cancel_spy = AsyncMock(side_effect=lambda tid: real_cancel(tid))
        with patch.object(service.kanban, "get_task", new=get_task_fresh), patch.object(
            service.kanban, "cancel_task_execution", new=cancel_spy
        ):
            result = await service.pause_project(project_id)

        assert result is not None
        assert result["status"] == "paused"
        # alpha 已终态：不冻结、不触发 cancel；beta 仍被冻结
        assert task_ids[0] not in result["paused_task_ids"]
        assert task_ids[1] in result["paused_task_ids"]
        assert not any(c.args[0] == task_ids[0] for c in cancel_spy.await_args_list)

        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_ids[0])
            assert task is not None
            # 冻结被跳过：alpha 未被置 BLOCKED，保持原运行状态
            assert task.status == TaskStatus.RUNNING.value
            task_b = await session.get(KanbanTaskModel, task_ids[1])
            assert task_b is not None
            assert task_b.status == TaskStatus.BLOCKED.value

    @pytest.mark.asyncio
    async def test_resume_does_not_overwrite_concurrent_cancel(
        self, client, tmp_path
    ) -> None:
        """W2: when a concurrent cancel flips the project to ``cancelled``
        while resume is unblocking, resume must not overwrite it back to
        ``running`` — cancel wins, the state machine stays consistent."""
        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]

        service = BatchDirectoryService.get_instance()
        await service.pause_project(project_id)

        real_move = service.kanban.move_task

        async def cancel_on_unblock(task_id: str, target, **kwargs):
            if target == TaskStatus.READY:
                # 模拟并发取消：项目置 cancelled 且冻结任务被归档
                await service.cancel_project(project_id)
                raise RuntimeError("boom")
            return await real_move(task_id, target, **kwargs)

        with patch.object(service.kanban, "move_task", new=cancel_on_unblock):
            result = await service.resume_project(project_id)

        assert result is not None
        assert result["status"] == "cancelled"
        assert result["resumed_task_ids"] == []


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


class TestChannelNotification:
    """Batch completion → executing agent's IM targets (best-effort channel push)."""

    @staticmethod
    def _target(channel: str = "feishu", recipient: str = "u-1") -> NotifyTarget:
        return NotifyTarget(channel=channel, recipient_id=recipient, label="ops")

    @pytest.mark.asyncio
    async def test_channel_push_delivers_summary_with_deep_link(self) -> None:
        from app.services.batch_directory import _helpers

        target = self._target()
        sender = MagicMock()
        sender.list_available_targets.return_value = [target]
        sender.send = AsyncMock(
            return_value=NotifyResult(success=True, channel="feishu", message_id="m1")
        )

        with patch.object(
            _helpers,
            "_load_agent_notify_targets",
            new=AsyncMock(return_value=({"channel": "feishu", "recipient_id": "u-1"},)),
        ), patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            return_value=(sender, None),
        ):
            await _helpers._send_channel_notification(
                agent_id="ag-1",
                project_name="Channel Test",
                status="completed",
                total=2,
                completed=2,
                failed=0,
                missing=[],
                project_id="proj-1",
            )

        sender.send.assert_awaited_once()
        body = sender.send.await_args.args[1]
        assert "Channel Test" in body
        assert "2/2 directories completed." in body
        assert "/batch-directories/proj-1" in body

    @pytest.mark.asyncio
    async def test_channel_push_includes_failure_and_missing_artifacts(self) -> None:
        from app.services.batch_directory import _helpers

        target = self._target()
        sender = MagicMock()
        sender.list_available_targets.return_value = [target]
        sender.send = AsyncMock(
            return_value=NotifyResult(success=True, channel="feishu", message_id="m2")
        )

        with patch.object(
            _helpers,
            "_load_agent_notify_targets",
            new=AsyncMock(return_value=({"channel": "feishu", "recipient_id": "u-1"},)),
        ), patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            return_value=(sender, None),
        ):
            await _helpers._send_channel_notification(
                agent_id="ag-1",
                project_name="Channel Test",
                status="failed",
                total=3,
                completed=1,
                failed=2,
                missing=["/tmp/alpha"],
                failed_directories=["/tmp/alpha", "/tmp/beta"],
                project_id="proj-2",
            )

        body = sender.send.await_args.args[1]
        assert "1 completed, 2 failed of 3 directories." in body
        assert "Failed directories:" in body
        assert "- /tmp/alpha" in body
        assert "- /tmp/beta" in body
        assert "1 directory missing required artifacts." in body

    @pytest.mark.asyncio
    async def test_channel_push_truncates_failed_directory_list(self) -> None:
        """Beyond 10 entries the list is truncated to keep the message short."""
        from app.services.batch_directory import _helpers

        target = self._target()
        sender = MagicMock()
        sender.list_available_targets.return_value = [target]
        sender.send = AsyncMock(
            return_value=NotifyResult(success=True, channel="feishu", message_id="m4")
        )
        failed_dirs = [f"/tmp/dir-{i:02d}" for i in range(12)]

        with patch.object(
            _helpers,
            "_load_agent_notify_targets",
            new=AsyncMock(return_value=({"channel": "feishu", "recipient_id": "u-1"},)),
        ), patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            return_value=(sender, None),
        ):
            await _helpers._send_channel_notification(
                agent_id="ag-1",
                project_name="Channel Test",
                status="failed",
                total=12,
                completed=0,
                failed=12,
                missing=[],
                failed_directories=failed_dirs,
                project_id="proj-5",
            )

        body = sender.send.await_args.args[1]
        assert body.count("- /tmp/dir-") == 10
        assert "... and 2 more" in body

    @pytest.mark.asyncio
    async def test_channel_push_uses_absolute_url_when_base_configured(self) -> None:
        """APP_BASE_URL turns the relative details path into a clickable URL."""
        from app.config.settings import settings
        from app.services.batch_directory import _helpers

        target = self._target()
        sender = MagicMock()
        sender.list_available_targets.return_value = [target]
        sender.send = AsyncMock(
            return_value=NotifyResult(success=True, channel="feishu", message_id="m5")
        )

        with patch.object(
            settings, "app_base_url", "https://myrm.example.com/"
        ), patch.object(
            _helpers,
            "_load_agent_notify_targets",
            new=AsyncMock(return_value=({"channel": "feishu", "recipient_id": "u-1"},)),
        ), patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            return_value=(sender, None),
        ):
            await _helpers._send_channel_notification(
                agent_id="ag-1",
                project_name="Channel Test",
                status="completed",
                total=1,
                completed=1,
                failed=0,
                missing=[],
                project_id="proj-6",
            )

        body = sender.send.await_args.args[1]
        assert "Details: https://myrm.example.com/batch-directories/proj-6" in body

    @pytest.mark.asyncio
    async def test_channel_push_skipped_without_targets_or_agent(self) -> None:
        from app.services.batch_directory import _helpers

        sender = MagicMock()
        with patch.object(
            _helpers, "_load_agent_notify_targets", new=AsyncMock(return_value=())
        ), patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            return_value=(sender, None),
        ) as mock_factory:
            await _helpers._send_channel_notification(
                agent_id="ag-1",
                project_name="Channel Test",
                status="completed",
                total=1,
                completed=1,
                failed=0,
                missing=[],
                project_id="proj-3",
            )
            mock_factory.assert_not_called()

        # 未绑定 agent 时连 targets 解析都跳过
        with patch.object(
            _helpers, "_load_agent_notify_targets", new=AsyncMock()
        ) as mock_load:
            await _helpers._send_channel_notification(
                agent_id=None,
                project_name="Channel Test",
                status="completed",
                total=1,
                completed=1,
                failed=0,
                missing=[],
                project_id="proj-3",
            )
            mock_load.assert_not_called()

    @pytest.mark.asyncio
    async def test_channel_push_failure_is_silent_and_keeps_notification(self) -> None:
        from app.services.batch_directory import _helpers

        target = self._target()
        sender = MagicMock()
        sender.list_available_targets.return_value = [target]
        sender.send = AsyncMock(
            return_value=NotifyResult(success=False, channel="feishu", error="http 500")
        )

        with patch.object(
            _helpers,
            "_load_agent_notify_targets",
            new=AsyncMock(return_value=({"channel": "feishu", "recipient_id": "u-1"},)),
        ), patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            return_value=(sender, None),
        ):
            # 投递失败不得抛异常
            await _helpers._send_channel_notification(
                agent_id="ag-1",
                project_name="Channel Test",
                status="failed",
                total=2,
                completed=1,
                failed=1,
                missing=[],
                project_id="proj-4",
            )
        sender.send.assert_awaited_once()

        # 发送抛异常同样静默
        sender.send = AsyncMock(side_effect=RuntimeError("boom"))
        with patch.object(
            _helpers,
            "_load_agent_notify_targets",
            new=AsyncMock(return_value=({"channel": "feishu", "recipient_id": "u-1"},)),
        ), patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            return_value=(sender, None),
        ):
            await _helpers._send_channel_notification(
                agent_id="ag-1",
                project_name="Channel Test",
                status="failed",
                total=2,
                completed=1,
                failed=1,
                missing=[],
                project_id="proj-4",
            )

    @pytest.mark.asyncio
    async def test_channel_push_sender_build_failure_is_silent(self) -> None:
        """Sender construction failure degrades to no push without raising."""
        from app.services.batch_directory import _helpers

        with patch.object(
            _helpers,
            "_load_agent_notify_targets",
            new=AsyncMock(return_value=({"channel": "feishu", "recipient_id": "u-1"},)),
        ), patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            side_effect=RuntimeError("no credential"),
        ):
            await _helpers._send_channel_notification(
                agent_id="ag-1",
                project_name="Channel Test",
                status="completed",
                total=1,
                completed=1,
                failed=0,
                missing=[],
                project_id="proj-7",
            )

    @pytest.mark.asyncio
    async def test_channel_push_sender_none_is_silent(self) -> None:
        """Sender build returning None degrades to no push without raising."""
        from app.services.batch_directory import _helpers

        with patch.object(
            _helpers,
            "_load_agent_notify_targets",
            new=AsyncMock(return_value=({"channel": "feishu", "recipient_id": "u-1"},)),
        ), patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            return_value=None,
        ):
            await _helpers._send_channel_notification(
                agent_id="ag-1",
                project_name="Channel Test",
                status="completed",
                total=1,
                completed=1,
                failed=0,
                missing=[],
                project_id="proj-8",
            )

    @pytest.mark.asyncio
    async def test_channel_push_sends_to_all_targets(self) -> None:
        """Every configured target receives the same summary body."""
        from app.services.batch_directory import _helpers

        sender = MagicMock()
        sender.list_available_targets.return_value = [
            self._target("feishu", "u-1"),
            self._target("dingtalk", "u-2"),
        ]
        sender.send = AsyncMock(
            return_value=NotifyResult(success=True, channel="feishu", message_id="m")
        )

        with patch.object(
            _helpers,
            "_load_agent_notify_targets",
            new=AsyncMock(
                return_value=(
                    {"channel": "feishu", "recipient_id": "u-1"},
                    {"channel": "dingtalk", "recipient_id": "u-2"},
                )
            ),
        ), patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            return_value=(sender, None),
        ):
            await _helpers._send_channel_notification(
                agent_id="ag-1",
                project_name="Channel Test",
                status="completed",
                total=1,
                completed=1,
                failed=0,
                missing=[],
                project_id="proj-9",
            )

        assert sender.send.await_count == 2
        bodies = {call.args[1] for call in sender.send.await_args_list}
        assert len(bodies) == 1

    @pytest.mark.asyncio
    async def test_channel_push_failure_includes_duration(self) -> None:
        """Failed batch body carries the failed list and the duration row."""
        from app.services.batch_directory import _helpers

        target = self._target()
        sender = MagicMock()
        sender.list_available_targets.return_value = [target]
        sender.send = AsyncMock(
            return_value=NotifyResult(success=True, channel="feishu", message_id="m")
        )

        with patch.object(
            _helpers,
            "_load_agent_notify_targets",
            new=AsyncMock(return_value=({"channel": "feishu", "recipient_id": "u-1"},)),
        ), patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            return_value=(sender, None),
        ):
            await _helpers._send_channel_notification(
                agent_id="ag-1",
                project_name="Channel Test",
                status="failed",
                total=3,
                completed=1,
                failed=2,
                missing=[],
                failed_directories=["/tmp/alpha", "/tmp/beta"],
                duration_seconds=510,
                project_id="proj-10",
            )

        body = sender.send.await_args.args[1]
        assert "2 failed of 3 directories." in body
        assert "Failed directories:" in body
        assert "- /tmp/alpha" in body
        assert "Duration: 8m 30s" in body

    @pytest.mark.asyncio
    async def test_maybe_finalize_invokes_channel_push(self, client, tmp_path) -> None:
        """End-to-end wiring: project.agent_id is read and channel push fires
        alongside the in-app notification on finalize."""
        from myrm_agent_harness.backends.profiles.types import AgentProfile

        from app.database.connection import get_session
        from app.database.repositories.agent_repo import AgentRepository

        # add_task 校验 agent 必须存在，且真实写入 notify_targets 走 resolver 读取路径
        async with get_session() as session:
            await AgentRepository.create_profile(
                session,
                AgentProfile(
                    id="batch-channel-agent",
                    display_name="Batch Agent",
                    metadata={
                        "notify_targets": [
                            {"channel": "feishu", "recipient_id": "u-1", "label": "ops"}
                        ]
                    },
                ),
            )
            await session.commit()

        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        resp = client.post(
            "/api/v1/batch-directories",
            json={
                "name": "Channel E2E",
                "prompt": "Analyze the codebase and report.",
                "directories": [str(dir_a), str(dir_b)],
                "concurrency": 2,
                "agent_id": "batch-channel-agent",
            },
        )
        assert resp.status_code == 201, resp.text
        project = resp.json()
        project_id = project["project_id"]

        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        async with get_session() as session:
            for task_id in project["created_task_ids"]:
                task = await session.get(KanbanTaskModel, task_id)
                assert task is not None
                task.status = TaskStatus.COMPLETED.value
                task.result = "ok"
            await session.commit()

        target = self._target()
        sender = MagicMock()
        sender.list_available_targets.return_value = [target]
        sender.send = AsyncMock(
            return_value=NotifyResult(success=True, channel="feishu", message_id="m3")
        )

        service = BatchDirectoryService.get_instance()
        with patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            return_value=(sender, None),
        ), patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            await service.maybe_finalize(project_id)

        sender.send.assert_awaited_once()
        body = sender.send.await_args.args[1]
        assert "Channel E2E" in body
        assert f"/batch-directories/{project_id}" in body
        assert "Duration:" in body
        mock_notify.assert_awaited_once()

        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["status"] == "completed"
        assert detail["agent_id"] == "batch-channel-agent"

    @pytest.mark.asyncio
    async def test_notify_disabled_skips_all_notifications(
        self, client, tmp_path
    ) -> None:
        """notify_enabled=False suppresses both in-app and channel notifications
        while the project still reaches its terminal state."""
        from myrm_agent_harness.backends.profiles.types import AgentProfile

        from app.database.connection import get_session
        from app.database.repositories.agent_repo import AgentRepository

        async with get_session() as session:
            await AgentRepository.create_profile(
                session,
                AgentProfile(
                    id="batch-silent-agent",
                    display_name="Silent Agent",
                    metadata={
                        "notify_targets": [
                            {"channel": "feishu", "recipient_id": "u-1", "label": "ops"}
                        ]
                    },
                ),
            )
            await session.commit()

        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        resp = client.post(
            "/api/v1/batch-directories",
            json={
                "name": "Silent E2E",
                "prompt": "Analyze the codebase and report.",
                "directories": [str(dir_a), str(dir_b)],
                "concurrency": 2,
                "agent_id": "batch-silent-agent",
                "notify_enabled": False,
            },
        )
        assert resp.status_code == 201, resp.text
        project = resp.json()
        project_id = project["project_id"]

        from app.database.models.kanban import KanbanTaskModel

        async with get_session() as session:
            for task_id in project["created_task_ids"]:
                task = await session.get(KanbanTaskModel, task_id)
                assert task is not None
                task.status = TaskStatus.COMPLETED.value
                task.result = "ok"
            await session.commit()

        target = self._target()
        sender = MagicMock()
        sender.list_available_targets.return_value = [target]
        sender.send = AsyncMock(
            return_value=NotifyResult(success=True, channel="feishu", message_id="m6")
        )

        service = BatchDirectoryService.get_instance()
        with patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            return_value=(sender, None),
        ), patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            await service.maybe_finalize(project_id)

        mock_notify.assert_not_awaited()
        sender.send.assert_not_awaited()

        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["status"] == "completed"


class TestDurationFormatting:
    """Duration rendering for completion notifications (shared both surfaces)."""

    def test_seconds_only(self) -> None:
        from app.services.batch_directory import _helpers

        assert _helpers._format_duration(42) == "42s"

    def test_minutes_with_seconds(self) -> None:
        from app.services.batch_directory import _helpers

        assert _helpers._format_duration(510) == "8m 30s"

    def test_whole_minutes(self) -> None:
        from app.services.batch_directory import _helpers

        assert _helpers._format_duration(600) == "10m"

    def test_hours_with_minutes(self) -> None:
        from app.services.batch_directory import _helpers

        assert _helpers._format_duration(3900) == "1h 5m"

    def test_whole_hours(self) -> None:
        from app.services.batch_directory import _helpers

        assert _helpers._format_duration(3600) == "1h"

    def test_summary_omits_duration_when_unknown(self) -> None:
        from app.services.batch_directory import _helpers

        _, message = _helpers._format_batch_summary(
            status="completed",
            project_name="P",
            total=2,
            completed=2,
            failed=0,
            missing=[],
        )
        assert "Duration" not in message

    def test_summary_includes_duration_when_known(self) -> None:
        from app.services.batch_directory import _helpers

        _, message = _helpers._format_batch_summary(
            status="completed",
            project_name="P",
            total=2,
            completed=2,
            failed=0,
            missing=[],
            duration_seconds=510,
        )
        assert "Duration: 8m 30s" in message


class TestEdgeCaseCoverage:
    """真实用户场景补测：危险路径/无效 board/目录去重/手动移动自愈等。

    Covers the remaining user-facing paths that the primary suite did not
    exercise directly: security rejection of dangerous directories, an
    invalid board reference, duplicate-directory dedup, the read-path
    self-heal when a task is moved to a terminal state via REST, and the
    paused guard on finalize.
    """

    def test_create_project_rejects_dangerous_directory(self, client, tmp_path) -> None:
        """System-sensitive directories (e.g. /etc) must be rejected with 400."""
        resp = client.post(
            "/api/v1/batch-directories",
            json={
                "name": "Evil",
                "prompt": "p",
                "directories": ["/etc"],
            },
        )
        assert resp.status_code == 400
        assert "Access denied" in resp.json()["detail"]

    def test_create_project_rejects_missing_board(self, client, tmp_path) -> None:
        """A board_id that does not exist must surface a clear 400."""
        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        resp = client.post(
            "/api/v1/batch-directories",
            json={
                "name": "Bad Board",
                "prompt": "p",
                "directories": [str(dir_a)],
                "board_id": "board-does-not-exist",
            },
        )
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    def test_create_project_deduplicates_directories(self, client, tmp_path) -> None:
        """Duplicate target directories are collapsed into one task."""
        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a), str(dir_a), str(dir_a)])
        assert project["total_tasks"] == 1
        assert len(project["created_task_ids"]) == 1
        assert project["directories"] == [str(dir_a)]

    @pytest.mark.asyncio
    async def test_read_path_self_heals_after_manual_terminal_move(
        self, client, tmp_path
    ) -> None:
        """REST-moved tasks (no dispatcher event) are finalized on the read path:
        get_project must trigger the terminal detection and fire notifications."""
        import asyncio

        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_b = tmp_path / "beta"
        dir_a.mkdir()
        dir_b.mkdir()
        project = _create_project(client, [str(dir_a), str(dir_b)])
        project_id = project["project_id"]
        task_ids = project["created_task_ids"]

        # 模拟用户手动移动任务到终态（不产生 dispatcher 事件）
        for task_id in task_ids:
            resp = client.post(
                f"/api/v1/kanban/tasks/{task_id}/move",
                json={"status": "completed", "result": "done", "force": True},
            )
            assert resp.status_code == 200, resp.text

        service = BatchDirectoryService.get_instance()
        with patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            detail = await service.get_project(project_id)
            assert detail is not None
            # 自愈调度是异步 fire-and-forget：轮询等待 finalize 完成
            import asyncio

            for _ in range(50):
                if mock_notify.await_count > 0:
                    break
                await asyncio.sleep(0.05)

        assert mock_notify.await_count == 1
        assert mock_notify.await_args.kwargs["meta_data"]["status"] == "completed"

        fresh = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert fresh["status"] == "completed"
        assert fresh["completed_tasks"] == 2

        # 任务状态确实已在任务表中持久化
        async with get_session() as session:
            for task_id in task_ids:
                task = await session.get(KanbanTaskModel, task_id)
                assert task is not None
                assert task.status == TaskStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_maybe_finalize_skips_when_paused(self, client, tmp_path) -> None:
        """A paused batch stays frozen: finalize is suppressed even if every
        task reached a terminal state (freeze must be stable until resume)."""
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        dir_a = tmp_path / "alpha"
        dir_a.mkdir()
        project = _create_project(client, [str(dir_a)])
        project_id = project["project_id"]
        task_id = project["created_task_ids"][0]

        service = BatchDirectoryService.get_instance()
        result = await service.pause_project(project_id)
        assert result is not None
        assert result["status"] == "paused"

        # 冻结后任务全被置终态（模拟极端并发：暂停后任务恰好全部完成）
        async with get_session() as session:
            task = await session.get(KanbanTaskModel, task_id)
            assert task is not None
            task.status = TaskStatus.COMPLETED.value
            task.result = "ok"
            await session.commit()

        with patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            new_callable=AsyncMock,
        ) as mock_notify:
            await service.maybe_finalize(project_id)
            mock_notify.assert_not_awaited()

        detail = client.get(f"/api/v1/batch-directories/{project_id}").json()
        assert detail["status"] == "paused"
        assert detail["finished_at"] is None

    @pytest.mark.asyncio
    async def test_channel_push_send_raise_is_silent(self) -> None:
        """sender.send() raising (e.g. gateway hiccup) must not break finalize."""
        from app.services.batch_directory import _helpers

        target = NotifyTarget(channel="feishu", recipient_id="u-1", label="ops")
        sender = MagicMock()
        sender.list_available_targets.return_value = [target]
        sender.send = AsyncMock(side_effect=RuntimeError("gateway down"))

        with patch.object(
            _helpers,
            "_load_agent_notify_targets",
            new=AsyncMock(return_value=({"channel": "feishu", "recipient_id": "u-1"},)),
        ), patch(
            "app.services.agent.outbound_notify.sender.create_notification_sender",
            return_value=(sender, None),
        ):
            await _helpers._send_channel_notification(
                agent_id="ag-1",
                project_name="Channel Test",
                status="completed",
                total=1,
                completed=1,
                failed=0,
                missing=[],
                project_id="proj-11",
            )

        sender.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_load_agent_notify_targets_resolver_error_degrades(self) -> None:
        """A resolver failure must degrade to no targets instead of raising."""
        from app.services.batch_directory import _helpers

        with patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            side_effect=RuntimeError("resolver down"),
        ):
            targets = await _helpers._load_agent_notify_targets("ag-missing")

        assert targets == ()

    def test_verify_artifact_patterns_missing_dir_returns_false(self) -> None:
        """A workspace that no longer exists reports artifacts as missing
        instead of raising."""
        from app.services.batch_directory import _helpers

        assert _helpers._verify_artifact_patterns("/no/such/dir", ["**/*.py"]) is False
