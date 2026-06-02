"""Tests for sticker visual understanding service."""

from __future__ import annotations

import pytest

from app.channels.media.sticker_vision import (
    StickerVisionService,
    _build_sticker_prompt,
    describe_sticker_inbound,
)
from app.channels.types import InboundMessage


class _FakeEngine:
    """Fake VisionFallbackEngine for testing."""

    def __init__(self, response: str = "A cartoon cat waving"):
        self.response = response
        self.calls: list[tuple[str, str, str | None]] = []

    async def describe_image_b64(
        self,
        b64_data: str,
        mime_type: str = "image/jpeg",
        retry_count: int = 1,
        prompt: str | None = None,
    ) -> str:
        self.calls.append((b64_data, mime_type, prompt))
        return self.response


class _FakeDownloader:
    """Fake Telegram client for downloading sticker files."""

    def __init__(self, content: bytes = b"fake-webp-data"):
        self.content = content

    async def get_file(self, file_id: str) -> dict[str, object]:
        return {"file_path": f"stickers/file_{file_id}.webp"}

    async def download_file(self, file_path: str, *, timeout: float = 30.0) -> bytes:
        return self.content


class _FakeChannel:
    def __init__(self) -> None:
        self._client = _FakeDownloader()


def _make_sticker_msg(
    *,
    emoji: str = "😺",
    file_id: str = "sticker_file_123",
    file_unique_id: str = "unique_abc",
    set_name: str = "CatPack",
    is_animated: bool = False,
    is_video: bool = False,
) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user1",
        content=emoji,
        chat_id="chat1",
        media=(),
        metadata={
            "is_sticker": True,
            "sticker_file_id": file_id,
            "sticker_file_unique_id": file_unique_id,
            "sticker_emoji": emoji,
            "sticker_set_name": set_name,
            "sticker_is_animated": is_animated,
            "sticker_is_video": is_video,
        },
    )


@pytest.fixture
def engine() -> _FakeEngine:
    return _FakeEngine()


@pytest.fixture
def service(engine: _FakeEngine) -> StickerVisionService:
    return StickerVisionService(engine)  # type: ignore[arg-type]


class TestBuildStickerPrompt:
    def test_with_set_name(self) -> None:
        prompt = _build_sticker_prompt("CatPack")
        assert "CatPack" in prompt
        assert "sticker pack" in prompt

    def test_without_set_name(self) -> None:
        prompt = _build_sticker_prompt("")
        assert "sticker pack" not in prompt
        assert "Describe this sticker" in prompt


class TestStickerVisionService:
    @pytest.mark.asyncio
    async def test_describe_static_sticker(self, service: StickerVisionService, engine: _FakeEngine) -> None:
        downloader = _FakeDownloader()
        result = await service.describe(
            file_id="f1",
            file_unique_id="u1",
            downloader=downloader,  # type: ignore[arg-type]
            set_name="TestSet",
        )
        assert result == "A cartoon cat waving"
        assert len(engine.calls) == 1
        assert engine.calls[0][1] == "image/webp"

    @pytest.mark.asyncio
    async def test_skip_animated_sticker(self, service: StickerVisionService) -> None:
        result = await service.describe(
            file_id="f1",
            file_unique_id="u1",
            downloader=_FakeDownloader(),  # type: ignore[arg-type]
            is_animated=True,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_skip_video_sticker(self, service: StickerVisionService) -> None:
        result = await service.describe(
            file_id="f1",
            file_unique_id="u1",
            downloader=_FakeDownloader(),  # type: ignore[arg-type]
            is_video=True,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_skip_empty_file_unique_id(self, service: StickerVisionService) -> None:
        result = await service.describe(
            file_id="f1",
            file_unique_id="",
            downloader=_FakeDownloader(),  # type: ignore[arg-type]
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit(self, service: StickerVisionService, engine: _FakeEngine) -> None:
        downloader = _FakeDownloader()
        r1 = await service.describe("f1", "u1", downloader=downloader)  # type: ignore[arg-type]
        r2 = await service.describe("f1", "u1", downloader=downloader)  # type: ignore[arg-type]
        assert r1 == r2
        assert len(engine.calls) == 1  # only 1 API call

    @pytest.mark.asyncio
    async def test_cache_lru_eviction(self, engine: _FakeEngine) -> None:
        svc = StickerVisionService(engine, max_cache_size=2)  # type: ignore[arg-type]
        dl = _FakeDownloader()
        await svc.describe("f1", "u1", downloader=dl)  # type: ignore[arg-type]
        await svc.describe("f2", "u2", downloader=dl)  # type: ignore[arg-type]
        await svc.describe("f3", "u3", downloader=dl)  # type: ignore[arg-type]
        assert svc.cache_size == 2
        assert len(engine.calls) == 3

    @pytest.mark.asyncio
    async def test_vision_failure_returns_none(self) -> None:
        class _FailEngine(_FakeEngine):
            async def describe_image_b64(self, *a: object, **kw: object) -> str:
                raise RuntimeError("API down")

        svc = StickerVisionService(_FailEngine())  # type: ignore[arg-type]
        result = await svc.describe("f1", "u1", downloader=_FakeDownloader())  # type: ignore[arg-type]
        assert result is None

    @pytest.mark.asyncio
    async def test_prompt_includes_set_name(self, service: StickerVisionService, engine: _FakeEngine) -> None:
        await service.describe(
            "f1", "u1",
            downloader=_FakeDownloader(),  # type: ignore[arg-type]
            set_name="FunnyPepe",
        )
        prompt = engine.calls[0][2]
        assert prompt is not None
        assert "FunnyPepe" in prompt

    @pytest.mark.asyncio
    async def test_in_flight_dedup(self) -> None:
        """Concurrent requests for the same file_unique_id share one API call."""
        import asyncio

        class _SlowEngine(_FakeEngine):
            async def describe_image_b64(self, *a: object, **kw: object) -> str:
                await asyncio.sleep(0.05)
                return await super().describe_image_b64(*a, **kw)  # type: ignore[arg-type]

        engine = _SlowEngine()
        svc = StickerVisionService(engine)  # type: ignore[arg-type]
        dl = _FakeDownloader()

        results = await asyncio.gather(
            svc.describe("f1", "u1", downloader=dl),  # type: ignore[arg-type]
            svc.describe("f1", "u1", downloader=dl),  # type: ignore[arg-type]
            svc.describe("f1", "u1", downloader=dl),  # type: ignore[arg-type]
        )
        assert all(r == "A cartoon cat waving" for r in results)
        assert len(engine.calls) == 1  # only 1 API call despite 3 requests

    @pytest.mark.asyncio
    async def test_vision_analysis_failed_returns_none(self) -> None:
        """Vision returning failure prefix should not cache and returns None."""
        engine = _FakeEngine(response="[Vision Analysis Failed: timeout]")
        svc = StickerVisionService(engine)  # type: ignore[arg-type]
        result = await svc.describe("f1", "u1", downloader=_FakeDownloader())  # type: ignore[arg-type]
        assert result is None
        assert svc.cache_size == 0

    @pytest.mark.asyncio
    async def test_empty_description_returns_none(self) -> None:
        engine = _FakeEngine(response="")
        svc = StickerVisionService(engine)  # type: ignore[arg-type]
        result = await svc.describe("f1", "u1", downloader=_FakeDownloader())  # type: ignore[arg-type]
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_update_existing_key(self, engine: _FakeEngine) -> None:
        """Re-describing same file_unique_id with cache miss updates cache."""
        svc = StickerVisionService(engine, max_cache_size=10)  # type: ignore[arg-type]
        dl = _FakeDownloader()
        r1 = await svc.describe("f1", "u1", downloader=dl)  # type: ignore[arg-type]
        assert r1 == "A cartoon cat waving"
        assert svc.cache_size == 1

    @pytest.mark.asyncio
    async def test_empty_file_path_returns_none(self) -> None:
        """Downloader returning empty file_path triggers ValueError -> None."""

        class _EmptyPathDownloader(_FakeDownloader):
            async def get_file(self, file_id: str) -> dict[str, object]:
                return {"file_path": ""}

        svc = StickerVisionService(_FakeEngine())  # type: ignore[arg-type]
        result = await svc.describe("f1", "u1", downloader=_EmptyPathDownloader())  # type: ignore[arg-type]
        assert result is None

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self) -> None:
        """Vision call exceeding timeout returns None."""
        import asyncio

        class _TimeoutEngine(_FakeEngine):
            async def describe_image_b64(self, *a: object, **kw: object) -> str:
                await asyncio.sleep(20)
                return "should not reach"

        from app.channels.media import sticker_vision

        original = sticker_vision._DESCRIBE_TIMEOUT
        sticker_vision._DESCRIBE_TIMEOUT = 0.01
        try:
            svc = StickerVisionService(_TimeoutEngine())  # type: ignore[arg-type]
            result = await svc.describe("f1", "u1", downloader=_FakeDownloader())  # type: ignore[arg-type]
            assert result is None
        finally:
            sticker_vision._DESCRIBE_TIMEOUT = original


class TestDescribeStickerInbound:
    @pytest.mark.asyncio
    async def test_enriches_sticker_message(self, service: StickerVisionService) -> None:
        msg = _make_sticker_msg()
        channels: dict[str, _FakeChannel] = {"telegram": _FakeChannel()}

        result = await describe_sticker_inbound(msg, service, lambda name: channels.get(name))
        assert "[Sticker: A cartoon cat waving]" in result.content
        assert "😺" in result.content

    @pytest.mark.asyncio
    async def test_no_service_returns_original(self) -> None:
        msg = _make_sticker_msg()
        result = await describe_sticker_inbound(msg, None, lambda _: None)
        assert result is msg

    @pytest.mark.asyncio
    async def test_non_sticker_returns_original(self, service: StickerVisionService) -> None:
        msg = InboundMessage(
            channel="telegram",
            sender_id="user1",
            content="hello",
            chat_id="chat1",
            media=(),
            metadata={},
        )
        result = await describe_sticker_inbound(msg, service, lambda _: None)
        assert result is msg

    @pytest.mark.asyncio
    async def test_animated_sticker_returns_original(self, service: StickerVisionService) -> None:
        msg = _make_sticker_msg(is_animated=True)
        channels: dict[str, _FakeChannel] = {"telegram": _FakeChannel()}
        result = await describe_sticker_inbound(msg, service, lambda name: channels.get(name))
        assert result is msg

    @pytest.mark.asyncio
    async def test_video_sticker_returns_original(self, service: StickerVisionService) -> None:
        msg = _make_sticker_msg(is_video=True)
        channels: dict[str, _FakeChannel] = {"telegram": _FakeChannel()}
        result = await describe_sticker_inbound(msg, service, lambda name: channels.get(name))
        assert result is msg

    @pytest.mark.asyncio
    async def test_no_channel_returns_original(self, service: StickerVisionService) -> None:
        msg = _make_sticker_msg()
        result = await describe_sticker_inbound(msg, service, lambda _: None)
        assert result is msg
