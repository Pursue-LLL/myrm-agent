"""Fail-closed video persistence: the media callback decides whether a generation succeeded."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.llms.video.generator import VideoGenerator
from myrm_agent_harness.toolkits.llms.video.models import (
    ProviderCapabilities,
    VideoAsset,
    VideoGenerationConfig,
    VideoGenerationError,
)
from myrm_agent_harness.toolkits.llms.video.providers.base import ProviderOutput, VideoGenerationProvider

_MP4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 32


class _FakeProvider(VideoGenerationProvider):
    """Returns one MP4 asset per call and counts the calls."""

    def __init__(self, provider_id: str) -> None:
        self._provider_id = provider_id
        self.calls = 0

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def display_name(self) -> str:
        return self._provider_id

    @property
    def default_model(self) -> str:
        return "m"

    @property
    def supported_models(self):  # type: ignore[no-untyped-def]
        return ()

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    async def generate(self, *args, **kwargs) -> ProviderOutput:  # type: ignore[no-untyped-def]
        self.calls += 1
        return ProviderOutput(assets=[VideoAsset(data=_MP4, mime_type="video/mp4", filename="v.mp4", metadata={})])


def _generator(
    callback: AsyncMock | None, *, fallbacks: tuple[str, ...] = ()
) -> tuple[VideoGenerator, dict[str, _FakeProvider]]:
    providers = {name: _FakeProvider(name) for name in ("primary", *fallbacks)}
    registry = MagicMock()
    registry.get.side_effect = providers.get
    config = VideoGenerationConfig(
        provider="primary",
        model="m",
        max_retries=2,
        media_callback=callback,
        fallback_configs=[VideoGenerationConfig(provider=name, model="m") for name in fallbacks],
    )
    return VideoGenerator(config, registry), providers


@pytest.mark.asyncio
async def test_the_stored_reference_is_attached_to_the_result() -> None:
    callback = AsyncMock(return_value="media://vid1")
    generator, _ = _generator(callback)

    result = await generator.generate("a sunset")

    assert result.persisted_refs == ["media://vid1"]
    assert result.to_dict()["video_urls"] == ["media://vid1"]
    assert callback.await_args.args[:2] == (_MP4, "video/mp4")


@pytest.mark.asyncio
async def test_without_a_callback_the_result_has_no_reference() -> None:
    generator, _ = _generator(None)

    result = await generator.generate("a sunset")

    assert result.persisted_refs == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "callback",
    [AsyncMock(side_effect=OSError("storage unavailable")), AsyncMock(return_value="")],
    ids=["callback-raises", "empty-reference"],
)
async def test_a_video_that_cannot_be_stored_fails_the_generation(callback: AsyncMock) -> None:
    generator, _ = _generator(callback)

    with pytest.raises(VideoGenerationError, match="Failed to store the generated video"):
        await generator.generate("a sunset")

    assert generator.error_count == 1


@pytest.mark.asyncio
async def test_a_storage_failure_never_regenerates_or_falls_back() -> None:
    callback = AsyncMock(side_effect=OSError("storage unavailable"))
    generator, providers = _generator(callback, fallbacks=("fallback",))

    with pytest.raises(VideoGenerationError, match="Failed to store"):
        await generator.generate("a sunset")

    assert providers["primary"].calls == 1
    assert providers["fallback"].calls == 0
    assert callback.await_count == 1


@pytest.mark.asyncio
async def test_a_fallback_provider_result_is_stored_through_the_primary_callback() -> None:
    callback = AsyncMock(return_value="media://vid2")
    generator, providers = _generator(callback, fallbacks=("fallback",))
    providers["primary"].generate = AsyncMock(side_effect=VideoGenerationError("primary down"))  # type: ignore[method-assign]

    result = await generator.generate("a sunset")

    assert result.provider == "fallback"
    assert result.persisted_refs == ["media://vid2"]
    assert callback.await_count == 1
