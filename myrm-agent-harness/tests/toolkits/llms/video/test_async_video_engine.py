"""Tests for the async video enqueue adapter and the generator's moderation failover rule.

[POS]
AsyncVideoGenerationTools enqueues one task per call and returns its id; ModerationBlockedError aborts failover.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from myrm_agent_harness.toolkits.llms.video.async_video_engine import AsyncVideoGenerationTools
from myrm_agent_harness.toolkits.llms.video.generator import VideoGenerator
from myrm_agent_harness.toolkits.llms.video.models import (
    ModerationBlockedError,
    ProviderCapabilities,
    VideoGenerationConfig,
)
from myrm_agent_harness.toolkits.llms.video.providers.base import VideoGenerationProvider
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore, TaskStatus

_CONFIG = {"provider": "gemini", "model": "veo-3.1-fast-generate-preview"}


@pytest.mark.asyncio
async def test_async_video_engine_enqueues_a_task_and_returns_its_id(tmp_path: Path) -> None:
    store = SQLiteTaskStore(db_path=str(tmp_path / "video-tasks.db"))
    await store.initialize()
    config = VideoGenerationConfig(**_CONFIG, api_key=SecretStr("sk-video-test"))
    engine = AsyncVideoGenerationTools(config, store)

    task_id = await engine.generate_video(
        "a sunset over the ocean",
        user_id="user-1",
        agent_id="agent-1",
        chat_id="chat-1",
        reference_images=["media://img1"],
    )

    assert task_id.startswith("vid-")
    task = await store.get_task(task_id)
    assert task is not None
    assert task.status == TaskStatus.PENDING
    assert task.task_type == "video_generate"
    assert task.payload["prompt"] == "a sunset over the ocean"
    assert task.payload["reference_images"] == ["media://img1"]
    assert task.payload["provider"] == "gemini"
    assert task.payload["model"] == "veo-3.1-fast-generate-preview"
    assert task.payload["api_key"] == "sk-video-test"
    assert task.payload["agent_id"] == "agent-1"
    assert task.payload["chat_id"] == "chat-1"


@pytest.mark.asyncio
async def test_the_allowed_roots_are_snapshotted_only_when_given(tmp_path: Path) -> None:
    store = SQLiteTaskStore(db_path=str(tmp_path / "video-tasks-roots.db"))
    await store.initialize()
    engine = AsyncVideoGenerationTools(VideoGenerationConfig(**_CONFIG), store)

    scoped = await store.get_task(await engine.generate_video("a", allowed_roots=("/work/chat-1",)))
    unscoped = await store.get_task(await engine.generate_video("b"))

    assert scoped is not None
    assert scoped.payload["allowed_roots"] == ["/work/chat-1"]
    assert unscoped is not None
    assert "allowed_roots" not in unscoped.payload


@pytest.mark.asyncio
async def test_the_payload_carries_no_force_flag(tmp_path: Path) -> None:
    store = SQLiteTaskStore(db_path=str(tmp_path / "video-tasks-force.db"))
    await store.initialize()
    engine = AsyncVideoGenerationTools(VideoGenerationConfig(**_CONFIG), store)

    task_id = await engine.generate_video("a mountain scene")

    task = await store.get_task(task_id)
    assert task is not None
    assert "force" not in task.payload


@pytest.mark.asyncio
async def test_async_video_engine_applies_payload_postprocessor(tmp_path: Path) -> None:
    store = SQLiteTaskStore(db_path=str(tmp_path / "video-tasks-post.db"))
    await store.initialize()
    config = VideoGenerationConfig(**_CONFIG, api_key=SecretStr("sk-video-test"))

    def _postprocess(payload: dict[str, object]) -> dict[str, object]:
        sealed = dict(payload)
        sealed.pop("api_key", None)
        sealed["api_key_enc"] = "ciphertext"
        return sealed

    engine = AsyncVideoGenerationTools(
        config,
        store,
        payload_postprocessor=_postprocess,
    )

    task_id = await engine.generate_video("a mountain scene")
    task = await store.get_task(task_id)
    assert task is not None
    assert "api_key" not in task.payload
    assert task.payload["api_key_enc"] == "ciphertext"


def test_provider_and_model_are_required() -> None:
    with pytest.raises(ValueError):
        VideoGenerationConfig()  # type: ignore[call-arg]


class _ModerationBlockedProvider(VideoGenerationProvider):
    @property
    def provider_id(self) -> str:
        return "mock-mod"

    @property
    def display_name(self) -> str:
        return "Mock Mod"

    @property
    def default_model(self) -> str:
        return "mod-1"

    @property
    def supported_models(self):  # type: ignore[no-untyped-def]
        return ()

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    async def generate(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ModerationBlockedError("Explicit moderation block: NSFW")


@pytest.mark.asyncio
async def test_generator_moderation_blocked_error_aborts_without_retry() -> None:
    registry = MagicMock()
    registry.get.return_value = _ModerationBlockedProvider()
    config = VideoGenerationConfig(provider="mock-mod", model="mod-1", max_retries=3)

    with pytest.raises(ModerationBlockedError, match="Explicit moderation block: NSFW"):
        await VideoGenerator(config, registry).generate("unsafe scene")
