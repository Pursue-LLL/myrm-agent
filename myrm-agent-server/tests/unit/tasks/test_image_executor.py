"""Tests for ImageTaskExecutor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.image import ImageGenerationError
from myrm_agent_harness.toolkits.llms.image.models import ImageGenerationConfig, ImageResult
from myrm_agent_harness.toolkits.llms.media_inputs import MediaInputError
from myrm_agent_harness.toolkits.tasks import Task, TaskStatus

from app.tasks.executors.image_executor import ImageTaskExecutor, image_task_result

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _task(**payload: object) -> Task:
    return Task(
        task_id="img-exec-1",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "a cat", **payload},
    )


def _result(*, persisted_ref: str | None = "media://media_cat", revised_prompt: str | None = None) -> ImageResult:
    return ImageResult(
        url="https://cdn.example/temporary.png",
        b64_json=None,
        revised_prompt=revised_prompt,
        model="gpt-image-2.6-sunburst",
        latency_ms=42.4,
        persisted_ref=persisted_ref,
        mime_type="image/png",
    )


def _patched_generator(result: ImageResult | Exception) -> tuple[MagicMock, MagicMock]:
    generator = MagicMock()
    if isinstance(result, Exception):
        generator.generate = AsyncMock(side_effect=result)
    else:
        generator.generate = AsyncMock(return_value=result)
    generator_cls = MagicMock(return_value=generator)
    return generator_cls, generator


@pytest.mark.asyncio
async def test_the_result_holds_the_stored_media_reference() -> None:
    config = ImageGenerationConfig(model="gpt-image-2.6-sunburst")
    resolver = MagicMock(return_value=config)
    task = _task(size="1536x1024", quality="high")
    generator_cls, generator = _patched_generator(_result(revised_prompt="a cute fluffy cat"))

    with patch("app.tasks.executors.image_executor.ImageGenerator", generator_cls):
        result = await ImageTaskExecutor(resolver).execute(task)

    resolver.assert_called_once_with(task)
    generator_cls.assert_called_once_with(config)
    generator.generate.assert_awaited_once_with("a cat", size="1536x1024", quality="high", reference_images=[])
    assert result == {
        "images": [{"url": "media://media_cat", "mime_type": "image/png"}],
        "prompt": "a cute fluffy cat",
        "model": "gpt-image-2.6-sunburst",
        "latency_ms": 42,
    }


@pytest.mark.asyncio
async def test_an_image_that_was_not_stored_fails_the_task() -> None:
    resolver = MagicMock(return_value=ImageGenerationConfig(model="gpt-image-2.6-sunburst"))
    generator_cls, _ = _patched_generator(_result(persisted_ref=None))

    with (
        patch("app.tasks.executors.image_executor.ImageGenerator", generator_cls),
        pytest.raises(ImageGenerationError, match="not stored"),
    ):
        await ImageTaskExecutor(resolver).execute(_task())


@pytest.mark.asyncio
async def test_references_go_through_the_single_resolver_with_the_workspace_roots() -> None:
    resolver = MagicMock(return_value=ImageGenerationConfig(model="gpt-image-2.6-sunburst"))
    generator_cls, generator = _patched_generator(_result())
    task = _task(reference_image_urls=["media://media_ref", "_uploaded/photo.png"], allowed_roots=["/work/chat-1"])

    with (
        patch("app.tasks.executors.image_executor.ImageGenerator", generator_cls),
        patch("app.tasks.executors.image_executor.resolve_media_inputs", AsyncMock(return_value=[_PNG, _PNG])) as resolve,
    ):
        await ImageTaskExecutor(resolver).execute(task)

    args, kwargs = resolve.await_args
    assert args[0] == ["media://media_ref", "_uploaded/photo.png"]
    assert args[1] == "image"
    assert [str(root) for root in args[2].allowed_roots] == ["/work/chat-1"]
    assert "media" in args[2].loaders
    assert kwargs == {"field_name": "reference_image_urls"}
    assert generator.generate.await_args.kwargs["reference_images"] == [_PNG, _PNG]


@pytest.mark.asyncio
async def test_a_bad_reference_fails_the_task_naming_the_field() -> None:
    resolver = MagicMock(return_value=ImageGenerationConfig(model="gpt-image-2.6-sunburst"))
    generator_cls, generator = _patched_generator(_result())

    with (
        patch("app.tasks.executors.image_executor.ImageGenerator", generator_cls),
        pytest.raises(MediaInputError, match="reference_image_urls"),
    ):
        await ImageTaskExecutor(resolver).execute(_task(reference_image_urls=["file:///etc/passwd"]))

    generator.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_payload_without_a_prompt_is_rejected() -> None:
    task = Task(task_id="img-exec-2", task_type="image_generate", user_id="u", status=TaskStatus.PENDING, payload={})

    with pytest.raises(ValueError, match="prompt"):
        await ImageTaskExecutor(MagicMock()).execute(task)


def test_image_task_result_is_the_shape_the_cards_read() -> None:
    assert image_task_result("media://media_x", "image/webp", prompt="p", model="m", latency_ms=9.6) == {
        "images": [{"url": "media://media_x", "mime_type": "image/webp"}],
        "prompt": "p",
        "model": "m",
        "latency_ms": 10,
    }


def test_the_executor_runs_image_tasks_only() -> None:
    executor = ImageTaskExecutor(MagicMock())

    assert executor.can_execute("image_generate")
    assert not executor.can_execute("video_generate")
