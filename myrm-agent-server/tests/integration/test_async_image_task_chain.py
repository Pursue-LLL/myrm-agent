"""Integration test: async image enqueue -> worker executor chain."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.executors.image_executor import ImageTaskExecutor
from app.tasks.image_config_resolver import resolve_image_generation_config
from app.tasks.task_payload_crypto import seal_task_payload_secrets
from myrm_agent_harness.toolkits.llms.image.async_image_engine import AsyncImageGenerationTools
from myrm_agent_harness.toolkits.llms.image.models import ImageGenerationConfig
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore, TaskStatus


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


@pytest.mark.asyncio
async def test_async_image_enqueue_to_executor_uses_agent_config_snapshot(tmp_path: object) -> None:
    db_path = tmp_path / "tasks-integration.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    config = ImageGenerationConfig(
        model="flux-pro",
        api_key="sk-integration-test",
        fallback_models=["dall-e-3"],
    )
    async_engine = AsyncImageGenerationTools(config, store)

    raw = await async_engine.generate_image(
        "a red cube",
        size="1024x1024",
        user_id="user-int",
        agent_id="agent-int",
        chat_id="chat-int",
    )
    payload = json.loads(raw)
    task_id = payload["task_id"]

    task = await store.get_task(task_id)
    assert task is not None
    assert task.payload["model"] == "flux-pro"
    assert task.payload["api_key"] == "sk-integration-test"
    assert task.payload["chat_id"] == "chat-int"
    assert task.payload["agent_id"] == "agent-int"

    sealed_payload = seal_task_payload_secrets(dict(task.payload))
    await store.update_task(task_id, payload=sealed_payload)
    task = await store.get_task(task_id)
    assert task is not None
    assert "api_key" not in task.payload

    mock_result = MagicMock()
    mock_result.images = [
        MagicMock(url="https://cdn.example/int.png", width=1024, height=1024, mime_type="image/png"),
    ]
    mock_result.prompt = "a red cube"
    mock_result.model = "flux-pro"
    mock_result.provider = "openai"
    mock_result.latency_ms = 99

    with patch(
        "app.tasks.executors.image_executor.ImageGenerator",
    ) as generator_cls:
        generator = MagicMock()
        generator.generate = AsyncMock(return_value=mock_result)
        generator_cls.return_value = generator

        executor = ImageTaskExecutor(resolve_image_generation_config)
        result = await executor.execute(task)

    resolved = resolve_image_generation_config(task)
    generator_cls.assert_called_once()
    called_config = generator_cls.call_args.args[0]
    assert called_config.model == resolved.model == "flux-pro"
    assert called_config.api_key is not None
    assert called_config.api_key.get_secret_value() == "sk-integration-test"
    assert called_config.media_callback is not None

    assert result["model"] == "flux-pro"
    assert result["images"][0]["url"] == "https://cdn.example/int.png"

    await store.update_task(task_id, status=TaskStatus.SUCCEEDED, result=result)
    updated = await store.get_task(task_id)
    assert updated is not None
    assert updated.status == TaskStatus.SUCCEEDED
