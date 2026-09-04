"""Unit tests for chat_utils vision/video fallback routing (llms.vision integration)."""

from __future__ import annotations

import base64
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.core.utils.chat_utils import _process_human_content, _process_image_item, _process_video_item

_TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="


def _jpeg_data_url(width: int, height: int) -> str:
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


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
async def test_process_image_compresses_oversized_image() -> None:
    """Images over 4096px trigger channel compression to JPEG."""
    item = {
        "type": "image_url",
        "image_url": {"url": _jpeg_data_url(5000, 3000)},
    }
    result = await _process_image_item(
        item,
        meta={},
        model_cfg=_vision_model(),
        vision_fallback_model_cfg=SimpleNamespace(model="vl"),
    )
    assert result["type"] == "image_url"
    assert "image/jpeg" in result["image_url"]["url"]


@pytest.mark.asyncio
async def test_process_image_probe_failure_passthrough() -> None:
    """Corrupt small base64 image: probe fails, original item is kept."""
    corrupt_b64 = base64.b64encode(b"not an image at all").decode("ascii")
    item = {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{corrupt_b64}"},
    }
    result = await _process_image_item(
        item,
        meta={},
        model_cfg=_vision_model(),
        vision_fallback_model_cfg=SimpleNamespace(model="vl"),
    )
    assert result["type"] == "image_url"
    assert "image/png" in result["image_url"]["url"]


@pytest.mark.asyncio
async def test_process_image_compresses_rgba_png_with_background() -> None:
    """RGBA PNG over 4096px is flattened onto a white background as JPEG."""
    img = Image.new("RGBA", (5000, 3000), color=(255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    item = {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"},
    }
    result = await _process_image_item(
        item,
        meta={},
        model_cfg=_vision_model(),
        vision_fallback_model_cfg=SimpleNamespace(model="vl"),
    )
    assert result["type"] == "image_url"
    assert "image/jpeg" in result["image_url"]["url"]


@pytest.mark.asyncio
async def test_process_image_compresses_grayscale_jpeg() -> None:
    """L-mode JPEG over 4096px is converted to RGB and re-encoded as JPEG."""
    img = Image.new("L", (5000, 3000), color=128)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    item = {
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"},
    }
    result = await _process_image_item(
        item,
        meta={},
        model_cfg=_vision_model(),
        vision_fallback_model_cfg=SimpleNamespace(model="vl"),
    )
    assert result["type"] == "image_url"
    assert "image/jpeg" in result["image_url"]["url"]


@pytest.mark.asyncio
async def test_process_image_huge_bytes_compression_failure_keeps_original() -> None:
    """byte_size over the inline threshold forces a compression attempt; a
    decode failure keeps the original data URL untouched."""
    huge_b64 = base64.b64encode(b"\x00" * (6 * 1024 * 1024)).decode("ascii")
    item = {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{huge_b64}"},
    }
    result = await _process_image_item(
        item,
        meta={},
        model_cfg=_vision_model(),
        vision_fallback_model_cfg=SimpleNamespace(model="vl"),
    )
    assert result["type"] == "image_url"
    assert "image/png" in result["image_url"]["url"]


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
    cache_key = f"{img_hash}:chat_fallback"
    meta: dict[str, object] = {
        "extra_data": {"vision_cache": {cache_key: "[Image Analysis]:\ncached"}},
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
async def test_preprocess_inbound_multimodal_query_passthrough_string() -> None:
    from app.core.utils.chat_utils import preprocess_inbound_multimodal_query

    result = await preprocess_inbound_multimodal_query(
        "hello",
        model_cfg=_text_only_model(),
        vision_fallback_model_cfg=SimpleNamespace(model="vl"),
    )
    assert result == "hello"


@pytest.mark.asyncio
async def test_preprocess_inbound_multimodal_query_skips_without_fallback() -> None:
    from app.core.utils.chat_utils import preprocess_inbound_multimodal_query

    query = [
        {"type": "text", "text": "look"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_TINY_PNG_B64}"}},
    ]
    result = await preprocess_inbound_multimodal_query(
        query,
        model_cfg=_text_only_model(),
        vision_fallback_model_cfg=None,
    )
    assert result is query


@pytest.mark.asyncio
async def test_preprocess_inbound_multimodal_query_delegates_to_process_human_content() -> None:
    from app.core.utils.chat_utils import preprocess_inbound_multimodal_query

    query = [
        {"type": "text", "text": "look"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_TINY_PNG_B64}"}},
    ]
    processed = [{"type": "text", "text": "[Image Analysis]:\ndone"}]

    with patch(
        "app.core.utils.chat_utils._process_human_content",
        new_callable=AsyncMock,
        return_value=processed,
    ) as mock_process:
        result = await preprocess_inbound_multimodal_query(
            query,
            model_cfg=_text_only_model(),
            vision_fallback_model_cfg=SimpleNamespace(model="vl"),
            meta={"chat_id": "c1"},
        )

    assert result == processed
    mock_process.assert_awaited_once()
    call_kwargs = mock_process.await_args.kwargs
    assert call_kwargs["meta"] == {"chat_id": "c1"}
    assert call_kwargs["vision_fallback_model_cfg"].model == "vl"


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
    mock_engine.analyze_video_url.assert_awaited_once_with(
        "https://example.com/v.mp4",
        supports_video=False,
        native_video_required=False,
    )
    mock_bus.publish.assert_called()


@pytest.mark.asyncio
async def test_process_human_content_supplies_default_prompt_for_empty_text_with_media() -> None:
    query = [
        {"type": "text", "text": "   "},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_TINY_PNG_B64}"}},
    ]
    result = await _process_human_content(
        query,
        model_cfg=_vision_model(),
    )
    assert isinstance(result, list)
    text_item = next(item for item in result if isinstance(item, dict) and item.get("type") == "text")
    assert text_item["text"] == "请分析附带的媒体内容。"
