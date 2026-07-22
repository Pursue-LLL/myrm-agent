"""Integration: REST /tasks ↔ SQLite store + image payload snapshot (no mocks on store path)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.llms.image.async_image_engine import AsyncImageGenerationTools
from myrm_agent_harness.toolkits.llms.image.models import ImageGenerationConfig
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore, TaskStatus

from app.tasks.executors.image_executor import ImageTaskExecutor
from app.tasks.image_config_resolver import resolve_image_generation_config
from app.tasks.task_payload_crypto import API_KEY_ENC_FIELD, seal_task_payload_secrets


@pytest.fixture(autouse=True)
def _local_encryption() -> None:
    import app.services.config.encryption as enc_mod

    original = os.environ.get("DEPLOY_MODE")
    os.environ["DEPLOY_MODE"] = "local"
    enc_mod._encryption_service = None
    yield
    enc_mod._encryption_service = None
    if original is None:
        os.environ.pop("DEPLOY_MODE", None)
    else:
        os.environ["DEPLOY_MODE"] = original


def _build_rest_app(store: SQLiteTaskStore):
    from fastapi import FastAPI

    from app.api.tasks.router import get_task_store
    from app.api.tasks.router import router as tasks_router

    app = FastAPI()
    app.include_router(tasks_router, prefix="/api/v1/tasks")

    async def _override_store() -> SQLiteTaskStore:
        return store

    app.dependency_overrides[get_task_store] = _override_store
    return app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_get_image_task_reflects_payload_snapshot_and_executor_result(
    tmp_path: object,
) -> None:
    db_path = tmp_path / "tasks-rest.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    config = ImageGenerationConfig(
        model="flux-pro",
        api_key="sk-rest-integration",
        fallback_models=["dall-e-3"],
    )
    async_engine = AsyncImageGenerationTools(
        config,
        store,
        payload_postprocessor=seal_task_payload_secrets,
    )
    raw = await async_engine.generate_image(
        "a blue sphere",
        size="512x512",
        user_id="user-rest",
        agent_id="agent-rest",
        chat_id="chat-rest",
    )
    task_id = json.loads(raw)["task_id"]

    task = await store.get_task(task_id)
    assert task is not None
    assert "api_key" not in task.payload
    assert isinstance(task.payload.get(API_KEY_ENC_FIELD), str)

    mock_result = MagicMock()
    mock_result.images = [
        MagicMock(url="https://cdn.example/rest.png", width=512, height=512, mime_type="image/png"),
    ]
    mock_result.prompt = "a blue sphere"
    mock_result.model = "flux-pro"
    mock_result.provider = "openai"
    mock_result.latency_ms = 42

    with patch("app.tasks.executors.image_executor.ImageGenerator") as generator_cls:
        generator = MagicMock()
        generator.generate = AsyncMock(return_value=mock_result)
        generator_cls.return_value = generator

        executor = ImageTaskExecutor(resolve_image_generation_config)
        result = await executor.execute(task)

    await store.update_task(task_id, status=TaskStatus.SUCCEEDED, result=result)

    transport = ASGITransport(app=_build_rest_app(store))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        get_resp = await client.get(f"/api/v1/tasks/{task_id}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["task_id"] == task_id
        assert body["status"] == "succeeded"
        assert body["payload"]["model"] == "flux-pro"
        assert "api_key" not in body["payload"]
        assert isinstance(body["payload"].get(API_KEY_ENC_FIELD), str)
        assert body["payload"]["agent_id"] == "agent-rest"
        assert body["payload"]["chat_id"] == "chat-rest"
        assert body["result"]["images"][0]["url"] == "https://cdn.example/rest.png"

        list_resp = await client.get("/api/v1/tasks", params={"task_type": "image_generate"})
        assert list_resp.status_code == 200
        listed = list_resp.json()["tasks"]
        assert any(row["task_id"] == task_id for row in listed)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_list_tasks_supports_ids_and_detail(tmp_path: object) -> None:
    db_path = tmp_path / "tasks-rest-ids.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    config = ImageGenerationConfig(
        model="flux-pro",
        api_key="sk-rest-ids",
    )
    async_engine = AsyncImageGenerationTools(
        config,
        store,
        payload_postprocessor=seal_task_payload_secrets,
    )
    raw = await async_engine.generate_image("a yellow cube", user_id="user-rest")
    task_id = json.loads(raw)["task_id"]

    transport = ASGITransport(app=_build_rest_app(store))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        detail_resp = await client.get(
            "/api/v1/tasks",
            params={"ids": task_id, "detail": "true"},
        )
        assert detail_resp.status_code == 200
        detail_payload = detail_resp.json()
        assert detail_payload["total"] == 1
        task_row = detail_payload["tasks"][0]
        assert task_row["task_id"] == task_id
        assert task_row["task_type"] == "image_generate"
        assert "payload" in task_row
        assert "updated_at" in task_row

        missing_resp = await client.get(
            "/api/v1/tasks",
            params={"ids": "task-not-found"},
        )
        assert missing_resp.status_code == 200
        missing_payload = missing_resp.json()
        assert missing_payload["total"] == 0
        assert missing_payload["tasks"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_retry_uses_structured_errors_and_recovers_failed_task(tmp_path: object) -> None:
    db_path = tmp_path / "tasks-rest-retry.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    config = ImageGenerationConfig(
        model="flux-pro",
        api_key="sk-rest-retry",
    )
    async_engine = AsyncImageGenerationTools(
        config,
        store,
        payload_postprocessor=seal_task_payload_secrets,
    )
    raw = await async_engine.generate_image("a retry cube", user_id="user-rest-retry")
    task_id = json.loads(raw)["task_id"]

    transport = ASGITransport(app=_build_rest_app(store))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        missing_retry_resp = await client.post("/api/v1/tasks/task-does-not-exist/retry")
        assert missing_retry_resp.status_code == 404
        assert missing_retry_resp.json()["detail"] == {
            "code": "TASK_NOT_FOUND",
            "message": "Task not found",
            "recoverable": "permanent",
        }

        non_failed_retry_resp = await client.post(f"/api/v1/tasks/{task_id}/retry")
        assert non_failed_retry_resp.status_code == 400
        assert non_failed_retry_resp.json()["detail"] == {
            "code": "TASK_NOT_RETRYABLE",
            "message": "Only failed tasks can be retried",
            "recoverable": "permanent",
        }

        failed_at = datetime(2026, 1, 1, tzinfo=UTC)
        await store.update_task(
            task_id,
            status=TaskStatus.FAILED,
            result={"video_urls": ["https://cdn.example/stale.mp4"]},
            progress=0.83,
            progress_message="failed at 83%",
            started_at=failed_at,
            completed_at=failed_at,
            cancellation_reason="stale cancellation reason",
            worker_id="worker-stale",
            worker_heartbeat_at=failed_at,
            next_retry_at=failed_at,
        )

        with patch("app.api.tasks.router.task_event_bus.emit", new=AsyncMock()) as emit_mock:
            retry_resp = await client.post(f"/api/v1/tasks/{task_id}/retry")

        assert retry_resp.status_code == 200
        assert retry_resp.json() == {
            "message": "Task queued for retry",
            "task_id": task_id,
        }
        emit_mock.assert_awaited_once_with(
            task_id,
            TaskStatus.PENDING,
            {
                "task_type": "image_generate",
                "progress": 0.0,
            },
        )

        retried_task = await store.get_task(task_id)
        assert retried_task is not None
        assert retried_task.status == TaskStatus.PENDING
        assert retried_task.result is None
        assert retried_task.error is None
        assert retried_task.progress == 0.0
        assert retried_task.progress_message is None
        assert retried_task.started_at is None
        assert retried_task.completed_at is None
        assert retried_task.cancellation_reason is None
        assert retried_task.worker_id is None
        assert retried_task.worker_heartbeat_at is None
        assert retried_task.next_retry_at is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rest_cancel_uses_structured_errors_for_missing_and_terminal_task(tmp_path: object) -> None:
    db_path = tmp_path / "tasks-rest-cancel.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    config = ImageGenerationConfig(
        model="flux-pro",
        api_key="sk-rest-cancel",
    )
    async_engine = AsyncImageGenerationTools(
        config,
        store,
        payload_postprocessor=seal_task_payload_secrets,
    )
    raw = await async_engine.generate_image("a cancel cube", user_id="user-rest-cancel")
    task_id = json.loads(raw)["task_id"]
    await store.update_task(task_id, status=TaskStatus.SUCCEEDED)

    transport = ASGITransport(app=_build_rest_app(store))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        missing_cancel_resp = await client.post("/api/v1/tasks/task-does-not-exist/cancel")
        assert missing_cancel_resp.status_code == 404
        assert missing_cancel_resp.json()["detail"] == {
            "code": "TASK_NOT_FOUND",
            "message": "Task not found",
            "recoverable": "permanent",
        }

        terminal_cancel_resp = await client.post(f"/api/v1/tasks/{task_id}/cancel")
        assert terminal_cancel_resp.status_code == 400
        assert terminal_cancel_resp.json()["detail"] == {
            "code": "TASK_ALREADY_COMPLETED",
            "message": "Only active tasks can be cancelled",
            "recoverable": "permanent",
        }
