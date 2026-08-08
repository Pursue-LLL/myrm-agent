"""Unit tests for vision media routing SSOT."""

from __future__ import annotations

from app.core.types import ModelConfig
from app.core.vision.media_router import (
    pick_video_fallback_configs,
    resolve_image_route,
    resolve_video_route,
)


def test_resolve_image_route_native() -> None:
    route = resolve_image_route(supports_vision=True, has_fallback=False)
    assert route.cache_namespace == "native"
    assert route.backend_badge is None


def test_resolve_image_route_vlm_fallback() -> None:
    route = resolve_image_route(supports_vision=False, has_fallback=True)
    assert route.cache_namespace == "chat_fallback"
    assert route.backend_badge == "vlm"


def test_resolve_video_route_native() -> None:
    route = resolve_video_route(
        supports_video=True,
        has_video_fallback=False,
        has_vision_fallback=False,
    )
    assert route.use_native_video is True
    assert route.backend_badge is None


def test_resolve_video_route_frame_fallback() -> None:
    route = resolve_video_route(
        supports_video=False,
        has_video_fallback=False,
        has_vision_fallback=True,
    )
    assert route.use_native_video is False
    assert route.cache_namespace == "chat_fallback"
    assert route.backend_badge == "frame"


def test_resolve_video_route_native_video_required() -> None:
    route = resolve_video_route(
        supports_video=False,
        has_video_fallback=True,
        has_vision_fallback=False,
    )
    assert route.native_video_required is True
    assert route.backend_badge == "native_video"


def test_pick_video_fallback_configs_prefers_video_slot() -> None:
    video_cfg = ModelConfig(model="gemini-video", api_key="k")
    vision_cfg = ModelConfig(model="qwen-vl", api_key="k")
    picked = pick_video_fallback_configs([video_cfg], [vision_cfg])
    assert picked == [video_cfg]


def test_pick_video_fallback_configs_falls_back_to_vision() -> None:
    vision_cfg = ModelConfig(model="qwen-vl", api_key="k")
    picked = pick_video_fallback_configs(None, [vision_cfg])
    assert picked == [vision_cfg]
