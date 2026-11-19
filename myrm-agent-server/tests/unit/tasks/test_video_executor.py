"""Tests for VideoTaskExecutor."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.media_inputs import MediaInputError
from myrm_agent_harness.toolkits.tasks import Task, TaskStatus
from PIL import Image

from app.tasks.executors.video_executor import VideoTaskExecutor


def _task(**payload: object) -> Task:
    return Task(
        task_id="vid-exec-1",
        task_type="video_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "a dog running", **payload},
    )


def _patched_generator(to_dict: dict[str, object] | None = None) -> tuple[MagicMock, MagicMock]:
    video_result = MagicMock()
    video_result.to_dict.return_value = to_dict or {"video_urls": ["media://media_vid"], "count": 1}
    generator = MagicMock()
    generator.generate = AsyncMock(return_value=video_result)
    return MagicMock(return_value=generator), generator


def _oversized_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2500, 1500), (0, 255, 0)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_the_result_carries_the_stored_media_references_and_the_prompt() -> None:
    generator_cls, generator = _patched_generator()

    with patch("app.tasks.executors.video_executor.VideoGenerator", generator_cls):
        result = await VideoTaskExecutor(MagicMock()).execute(_task(duration_seconds=5, aspect_ratio="16:9"))

    assert result == {"video_urls": ["media://media_vid"], "count": 1, "prompt": "a dog running"}
    kwargs = generator.generate.await_args.kwargs
    assert kwargs["duration_seconds"] == 5
    assert kwargs["aspect_ratio"] == "16:9"
    assert kwargs["reference_images"] is None
    assert kwargs["reference_videos"] is None
    assert kwargs["extra_params"] is None


@pytest.mark.asyncio
async def test_resolved_reference_images_are_downsized_once() -> None:
    generator_cls, generator = _patched_generator()
    task = _task(reference_images=["media://media_big"])

    with (
        patch("app.tasks.executors.video_executor.VideoGenerator", generator_cls),
        patch("app.ai_agents.media_tools.input_policy.read_media_reference", AsyncMock(return_value=_oversized_jpeg())),
    ):
        await VideoTaskExecutor(MagicMock()).execute(task)

    passed = generator.generate.await_args.kwargs["reference_images"]
    assert passed is not None and len(passed) == 1
    with Image.open(io.BytesIO(passed[0])) as clamped:
        assert max(clamped.width, clamped.height) <= 2048


@pytest.mark.asyncio
async def test_references_use_the_workspace_roots_and_name_their_fields() -> None:
    generator_cls, generator = _patched_generator()
    task = _task(
        reference_images=["_uploaded/a.png"],
        reference_videos=["media://media_src"],
        allowed_roots=["/work/chat-1"],
    )
    resolved = AsyncMock(side_effect=[[b"img"], [b"vid"]])

    with (
        patch("app.tasks.executors.video_executor.VideoGenerator", generator_cls),
        patch("app.tasks.executors.video_executor.resolve_media_inputs", resolved),
    ):
        await VideoTaskExecutor(MagicMock()).execute(task)

    image_call, video_call = resolved.await_args_list
    assert image_call.args[:2] == (["_uploaded/a.png"], "image")
    assert video_call.args[:2] == (["media://media_src"], "video")
    assert image_call.kwargs == {"field_name": "reference_images"}
    assert video_call.kwargs == {"field_name": "reference_videos"}
    assert [str(root) for root in image_call.args[2].allowed_roots] == ["/work/chat-1"]
    kwargs = generator.generate.await_args.kwargs
    assert kwargs["reference_images"] == [b"img"]
    assert kwargs["reference_videos"] == [b"vid"]


@pytest.mark.asyncio
async def test_public_video_urls_reach_providers_that_fetch_them_themselves() -> None:
    generator_cls, generator = _patched_generator()
    task = _task(
        reference_videos=["https://cdn.example/a.mp4", "media://media_b"],
        extra_params={"mode": "extend"},
    )

    with (
        patch("app.tasks.executors.video_executor.VideoGenerator", generator_cls),
        patch("app.tasks.executors.video_executor.resolve_media_inputs", AsyncMock(return_value=[b"a", b"b"])),
    ):
        await VideoTaskExecutor(MagicMock()).execute(task)

    assert generator.generate.await_args.kwargs["extra_params"] == {
        "mode": "extend",
        "_video_source_urls": ["https://cdn.example/a.mp4"],
    }


@pytest.mark.asyncio
async def test_a_bad_reference_fails_the_task_naming_the_field() -> None:
    generator_cls, generator = _patched_generator()

    with (
        patch("app.tasks.executors.video_executor.VideoGenerator", generator_cls),
        pytest.raises(MediaInputError, match="reference_videos"),
    ):
        await VideoTaskExecutor(MagicMock()).execute(_task(reference_videos=["file:///etc/passwd"]))

    generator.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_payload_without_a_prompt_is_rejected() -> None:
    task = Task(task_id="vid-exec-2", task_type="video_generate", user_id="u", status=TaskStatus.PENDING, payload={})

    with pytest.raises(ValueError, match="prompt"):
        await VideoTaskExecutor(MagicMock()).execute(task)


def test_the_executor_runs_video_tasks_only() -> None:
    executor = VideoTaskExecutor(MagicMock())

    assert executor.can_execute("video_generate")
    assert not executor.can_execute("image_generate")
