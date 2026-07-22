"""Integration test: async video enqueue -> worker executor chain."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.core.config.gateway import ToolGatewayConfig
from myrm_agent_harness.toolkits.llms.video import VideoGenerationConfig
from myrm_agent_harness.toolkits.llms.video.async_video_engine import AsyncVideoGenerationTools
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore, TaskStatus

from app.tasks.executors.video_executor import VideoTaskExecutor
from app.tasks.task_payload_crypto import API_KEY_ENC_FIELD, seal_task_payload_secrets
from app.tasks.video_config_resolver import resolve_video_generation_config


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
async def test_async_video_enqueue_to_executor_uses_agent_config_snapshot(tmp_path: object) -> None:
    db_path = tmp_path / "video-tasks-integration.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    config = VideoGenerationConfig(
        provider="openai",
        model="sora",
        api_key="sk-video-integration-test",
        timeout_seconds=180,
    )
    async_engine = AsyncVideoGenerationTools(
        config,
        store,
        payload_postprocessor=seal_task_payload_secrets,
    )

    raw = await async_engine.generate_video(
        "a red cube rotates in studio light",
        user_id="user-int",
        agent_id="agent-int",
        chat_id="chat-int",
    )
    payload = json.loads(raw)
    task_id = payload["task_id"]

    task = await store.get_task(task_id)
    assert task is not None
    assert task.payload["model"] == "sora"
    assert task.payload["provider"] == "openai"
    assert "api_key" not in task.payload
    assert isinstance(task.payload.get(API_KEY_ENC_FIELD), str)
    assert task.payload["chat_id"] == "chat-int"
    assert task.payload["agent_id"] == "agent-int"

    mock_result = MagicMock()
    mock_result.to_dict.return_value = {
        "video_urls": ["https://cdn.example/int-video.mp4"],
        "provider": "openai",
        "model": "sora",
        "count": 1,
        "latency_ms": 1880,
    }

    with patch(
        "app.tasks.executors.video_executor.VideoGenerator",
    ) as generator_cls:
        generator = MagicMock()
        generator.generate = AsyncMock(return_value=mock_result)
        generator_cls.return_value = generator

        executor = VideoTaskExecutor(resolve_video_generation_config)
        result = await executor.execute(task)

    resolved = resolve_video_generation_config(task)
    generator_cls.assert_called_once()
    called_config = generator_cls.call_args.args[0]
    assert called_config.model == resolved.model == "sora"
    assert called_config.provider == resolved.provider == "openai"
    assert called_config.api_key is not None
    assert called_config.api_key.get_secret_value() == "sk-video-integration-test"

    assert result["video_urls"][0] == "https://cdn.example/int-video.mp4"
    assert result["prompt"] == "a red cube rotates in studio light"

    await store.update_task(task_id, status=TaskStatus.SUCCEEDED, result=result)
    updated = await store.get_task(task_id)
    assert updated is not None
    assert updated.status == TaskStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_async_video_gateway_only_enqueue_persists_sealed_auth_token(
    tmp_path: object,
) -> None:
    db_path = tmp_path / "video-tasks-gateway.db"  # type: ignore[operator]
    store = SQLiteTaskStore(db_path=str(db_path))
    await store.initialize()

    config = VideoGenerationConfig(
        provider="openai",
        model="sora",
        gateway_config=ToolGatewayConfig(
            use_gateway=True,
            gateway_url="https://gateway.example/tool-relay",
            auth_token="vk-video-gateway",
        ),
    )
    async_engine = AsyncVideoGenerationTools(
        config,
        store,
        payload_postprocessor=seal_task_payload_secrets,
    )

    raw = await async_engine.generate_video("an airplane crossing clouds", user_id="user-gw")
    task_id = json.loads(raw)["task_id"]

    task = await store.get_task(task_id)
    assert task is not None
    gateway = task.payload.get("gateway_config")
    assert isinstance(gateway, dict)
    assert "auth_token" not in gateway
    assert isinstance(gateway.get("auth_token_enc"), str)

    resolved = resolve_video_generation_config(task)
    assert resolved.gateway_config is not None
    assert resolved.gateway_config.auth_token == "vk-video-gateway"
