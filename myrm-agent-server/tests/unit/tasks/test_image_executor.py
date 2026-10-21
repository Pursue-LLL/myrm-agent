"""Tests for ImageTaskExecutor."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.image.models import ImageGenerationConfig, ImageResult
from myrm_agent_harness.toolkits.tasks import Task, TaskStatus

from app.tasks.executors.image_executor import ImageTaskExecutor


@pytest.mark.asyncio
async def test_image_task_executor_uses_config_resolver() -> None:
    task = Task(
        task_id="img-exec-1",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "a cat", "count": 1},
    )
    config = ImageGenerationConfig(model="flux-pro")
    resolver = MagicMock(return_value=config)

    real_result = ImageResult(
        url="https://cdn.example/temporary.png",
        b64_json=None,
        revised_prompt="a cute fluffy cat",
        model="flux-pro",
        latency_ms=42.0,
        persisted_url="http://localhost:8080/api/artifacts/media/cat.png",
        mime_type="image/png",
    )

    with patch(
        "app.tasks.executors.image_executor.ImageGenerator",
    ) as generator_cls:
        generator = MagicMock()
        generator.generate = AsyncMock(return_value=real_result)
        generator_cls.return_value = generator

        executor = ImageTaskExecutor(resolver)
        result = await executor.execute(task)

    resolver.assert_called_once_with(task)
    generator_cls.assert_called_once_with(config)
    assert result["model"] == "flux-pro"
    assert result["images"][0]["url"] == "http://localhost:8080/api/artifacts/media/cat.png"
    assert result["images"][0]["mime_type"] == "image/png"
    assert result["prompt"] == "a cute fluffy cat"
    assert result["latency_ms"] == 42.0


@pytest.mark.asyncio
async def test_image_task_executor_fallback_when_not_persisted() -> None:
    task = Task(
        task_id="img-exec-2",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "a dog"},
    )
    config = ImageGenerationConfig(model="dall-e-3")
    resolver = MagicMock(return_value=config)

    raw_result = ImageResult(
        url="https://external-s3.example/dog.png",
        b64_json=None,
        revised_prompt=None,
        model="dall-e-3",
        latency_ms=105.0,
        persisted_url=None,
        mime_type="image/jpeg",
    )

    with patch(
        "app.tasks.executors.image_executor.ImageGenerator",
    ) as generator_cls:
        generator = MagicMock()
        generator.generate = AsyncMock(return_value=raw_result)
        generator_cls.return_value = generator

        executor = ImageTaskExecutor(resolver)
        result = await executor.execute(task)

    assert result["model"] == "dall-e-3"
    assert result["images"][0]["url"] == "https://external-s3.example/dog.png"
    assert result["images"][0]["mime_type"] == "image/jpeg"
    assert result["prompt"] == "a dog"


@pytest.mark.asyncio
async def test_image_task_executor_cancel() -> None:
    task = Task(
        task_id="img-exec-3",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.RUNNING,
        payload={"prompt": "a bird"},
        cancellation_event=asyncio.Event(),
    )
    resolver = MagicMock()
    executor = ImageTaskExecutor(resolver)

    assert not task.cancellation_event.is_set()
    cancelled = await executor.cancel(task)
    assert cancelled is True
    assert task.cancellation_event.is_set()
