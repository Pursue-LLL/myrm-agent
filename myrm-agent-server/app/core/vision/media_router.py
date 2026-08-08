"""Vision media routing SSOT for chat preprocessing.

[INPUT]
app.core.types.business::ModelConfig (POS: Server 层大模型运行时配置)

[OUTPUT]
VisionMediaRoute: 单条媒体项的路由决策（native / fallback / cache / badge）
resolve_image_route / resolve_video_route / pick_video_fallback_configs

[POS]
Server 业务层视觉媒体路由 SSOT。将 Settings 图/视频降级槽与主模型能力合成为 chat 预处理决策，
不调用 LLM，不含 harness 引擎逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.types import ModelConfig


@dataclass(frozen=True)
class VisionMediaRoute:
    """Resolved routing decision for one media item."""

    use_native_video: bool
    native_video_required: bool
    cache_namespace: str
    backend_badge: str | None = None


def resolve_image_route(*, supports_vision: bool, has_fallback: bool) -> VisionMediaRoute:
    return VisionMediaRoute(
        use_native_video=False,
        native_video_required=False,
        cache_namespace="chat_fallback" if has_fallback else "native",
        backend_badge=None if supports_vision else ("vlm" if has_fallback else None),
    )


def resolve_video_route(
    *,
    supports_video: bool,
    has_video_fallback: bool,
    has_vision_fallback: bool,
) -> VisionMediaRoute:
    has_fallback = has_video_fallback or has_vision_fallback
    native_required = has_video_fallback and not supports_video
    return VisionMediaRoute(
        use_native_video=supports_video,
        native_video_required=native_required,
        cache_namespace="video_fallback" if has_video_fallback else "chat_fallback",
        backend_badge=None if supports_video else ("native_video" if has_video_fallback else "frame"),
    )


def pick_video_fallback_configs(
    video_cfgs: list["ModelConfig"] | None,
    vision_cfgs: list["ModelConfig"] | None,
) -> list["ModelConfig"]:
    from myrm_agent_harness.toolkits.llms.vision import pick_video_fallback_model_cfgs

    picked = pick_video_fallback_model_cfgs(video_cfgs, vision_cfgs)
    return list(picked)
