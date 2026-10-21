"""Tests for VideoTaskExecutor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.tasks import Task, TaskStatus

from app.tasks.executors.video_executor import VideoTaskExecutor


@pytest.mark.asyncio
async def test_video_task_executor_clamps_resolved_images() -> None:
    import io

    from PIL import Image

    # Generate oversized image
    raw_img = Image.new("RGB", (2500, 1500), (0, 255, 0))
    buf = io.BytesIO()
    raw_img.save(buf, format="JPEG")
    oversized_bytes = buf.getvalue()

    task = Task(
        task_id="vid-exec-1",
        task_type="video_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={
            "prompt": "a dog running",
            "reference_images": ["https://example.com/dog.jpg"],
        },
    )
    mock_config = MagicMock()
    mock_resolver = MagicMock(return_value=mock_config)

    mock_video_result = MagicMock()
    mock_video_result.to_dict.return_value = {
        "video_url": "https://cdn.example/video.mp4",
        "duration_seconds": 5,
    }

    with (
        patch(
            "app.tasks.executors.video_executor._resolve_image_inputs",
            AsyncMock(return_value=[oversized_bytes]),
        ),
        patch(
            "app.tasks.executors.video_executor.VideoGenerator",
        ) as generator_cls,
    ):
        generator = MagicMock()
        generator.generate = AsyncMock(return_value=mock_video_result)
        generator_cls.return_value = generator

        executor = VideoTaskExecutor(mock_resolver)
        result = await executor.execute(task)

        assert result["video_url"] == "https://cdn.example/video.mp4"
        assert result["prompt"] == "a dog running"

        # Verify generator.generate received clamped images (max dimension <= 2048)
        assert generator.generate.await_count == 1
        call_kwargs = generator.generate.await_args.kwargs
        passed_images = call_kwargs.get("reference_images")
        assert passed_images is not None
        assert len(passed_images) == 1

        with Image.open(io.BytesIO(passed_images[0])) as clamped_img:
            assert max(clamped_img.width, clamped_img.height) <= 2048
