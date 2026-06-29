"""Unit tests for chat_utils vision/video fallback routing (llms.vision integration)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.utils.chat_utils import _process_image_item, _process_video_item

_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="
)


def _text_only_model() -> SimpleNamespace:
    return SimpleNamespace(supports_vision=False, supports_video=False)


def _vision_model() -> SimpleNamespace:
    return SimpleNamespace(supports_vision=True, supports_video=True)


@pytest.mark.asyncio
async def test_process_image_passthrough_when_model_supports_vision() -> None:
    item = {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{_TINY_PNG_B64}"},
    }
    result = await _process_image_item(
        item,
        meta={},
        model_cfg=_vision_model(),
        vision_fallback_model_cfg=SimpleNamespace(model="vl"),
    )
    assert result["type"] == "image_url"


@pytest.mark.asyncio
async def test_process_image_uses_llms_vision_engine_and_sse() -> None:
    item = {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{_TINY_PNG_B64}"},
    }
    fallback_cfg = SimpleNamespace(model="MiniMax-VL", api_key="k", base_url="https://example.com")
    meta: dict[str, object] = {"chat_id": "chat-1", "message_id": "msg-1", "extra_data": {}}

    mock_engine = MagicMock()
    mock_engine.describe_image_b64 = AsyncMock(return_value="diagram with error text")

    mock_bus = MagicMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.llms.vision.fallback_engine.VisionFallbackEngine",
            return_value=mock_engine,
        ),
        patch(
            "app.services.event.app_event_bus.get_event_bus",
            return_value=mock_bus,
        ),
    ):
        result = await _process_image_item(
            item,
            meta=meta,
            model_cfg=_text_only_model(),
            vision_fallback_model_cfg=fallback_cfg,
        )

    assert result["type"] == "text"
    assert "[Image Analysis]" in str(result["text"])
    mock_engine.describe_image_b64.assert_awaited_once()
    mock_bus.publish.assert_called()
    extra = meta.get("extra_data")
    assert isinstance(extra, dict)
    cache = extra.get("vision_cache")
    assert isinstance(cache, dict)
    assert cache


@pytest.mark.asyncio
async def test_process_image_cache_hit_skips_engine() -> None:
    url = f"data:image/png;base64,{_TINY_PNG_B64}"
    import hashlib

    img_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
    meta: dict[str, object] = {
        "extra_data": {"vision_cache": {img_hash: "[Image Analysis]:\ncached"}},
    }
    item = {"type": "image_url", "image_url": {"url": url}}

    with patch(
        "myrm_agent_harness.toolkits.llms.vision.fallback_engine.VisionFallbackEngine",
    ) as mock_cls:
        result = await _process_image_item(
            item,
            meta=meta,
            model_cfg=_text_only_model(),
            vision_fallback_model_cfg=SimpleNamespace(model="vl"),
        )

    mock_cls.assert_not_called()
    assert result == {"type": "text", "text": "[Image Analysis]:\ncached"}


@pytest.mark.asyncio
async def test_process_video_emits_analyzing_and_uses_engine() -> None:
    item = {"type": "video_url", "video_url": {"url": "https://example.com/v.mp4"}}
    fallback_cfg = SimpleNamespace(model="MiniMax-VL", api_key="k", base_url="https://example.com")
    meta: dict[str, object] = {"chat_id": "chat-2", "message_id": "msg-2", "extra_data": {}}

    mock_engine = MagicMock()
    mock_engine.analyze_video_url = AsyncMock(return_value="person walking")

    mock_bus = MagicMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.llms.vision.video_analysis_engine.VideoAnalysisEngine",
            return_value=mock_engine,
        ),
        patch(
            "app.services.event.app_event_bus.get_event_bus",
            return_value=mock_bus,
        ),
    ):
        result = await _process_video_item(
            item,
            meta=meta,
            model_cfg=_text_only_model(),
            vision_fallback_model_cfg=fallback_cfg,
        )

    assert result["type"] == "text"
    assert "[Video Analysis]" in str(result["text"])
    mock_engine.analyze_video_url.assert_awaited_once_with("https://example.com/v.mp4")
    mock_bus.publish.assert_called()
