"""Integration: REST /tasks ↔ SQLite store + image payload snapshot (no mocks on store path)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.tasks.executors.image_executor import ImageTaskExecutor
from app.tasks.image_config_resolver import resolve_image_generation_config
from myrm_agent_harness.toolkits.llms.image.async_image_engine import AsyncImageGenerationTools
from myrm_agent_harness.toolkits.llms.image.models import ImageGenerationConfig
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore, TaskStatus


def _build_rest_app(store: SQLiteTaskStore):
    from fastapi import FastAPI

    from app.api.tasks.router import get_task_store, router as tasks_router

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
    async_engine = AsyncImageGenerationTools(config, store)
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
        assert body["payload"]["api_key"] == "sk-rest-integration"
        assert body["payload"]["agent_id"] == "agent-rest"
        assert body["payload"]["chat_id"] == "chat-rest"
        assert body["result"]["images"][0]["url"] == "https://cdn.example/rest.png"

        list_resp = await client.get("/api/v1/tasks", params={"task_type": "image_generate"})
        assert list_resp.status_code == 200
        listed = list_resp.json()["tasks"]
        assert any(row["task_id"] == task_id for row in listed)
