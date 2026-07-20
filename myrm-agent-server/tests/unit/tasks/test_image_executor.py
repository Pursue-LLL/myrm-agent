"""Tests for ImageTaskExecutor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.image.models import ImageGenerationConfig
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

    mock_result = MagicMock()
    mock_result.images = [
        MagicMock(url="https://cdn.example/x.png", width=1024, height=1024, mime_type="image/png"),
    ]
    mock_result.prompt = "a cat"
    mock_result.model = "flux-pro"
    mock_result.provider = "openai"
    mock_result.latency_ms = 42

    with patch(
        "app.tasks.executors.image_executor.ImageGenerator",
    ) as generator_cls:
        generator = MagicMock()
        generator.generate = AsyncMock(return_value=mock_result)
        generator_cls.return_value = generator

        executor = ImageTaskExecutor(resolver)
        result = await executor.execute(task)

    resolver.assert_called_once_with(task)
    generator_cls.assert_called_once_with(config)
    assert result["model"] == "flux-pro"
    assert result["images"][0]["url"] == "https://cdn.example/x.png"
