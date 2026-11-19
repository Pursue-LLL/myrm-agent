"""Video generation module — multi-provider video generation with failover.

Provides a unified interface for generating videos from text prompts or
reference images and videos (T2V, I2V and V2V modes) across multiple providers
(Google Veo, Qwen, MiniMax, xAI, fal, Volcengine). Generation runs as asynchronous tasks
with ordered failover and fail-closed persistence.

Quick start:
    from myrm_agent_harness.toolkits.llms.video import (
        VideoGenerationConfig,
        VideoGenerator,
        get_registry,
    )

    config = VideoGenerationConfig(provider="gemini", model="veo-3.1-fast-generate-preview")
    result = await VideoGenerator(config, get_registry()).generate("A sunset over the ocean")
"""

from .async_video_engine import AsyncVideoGenerationTools
from .generator import VideoGenerator
from .models import (
    FailoverAttempt,
    MediaCallback,
    MediaMeta,
    ModerationBlockedError,
    OverrideIgnored,
    ProviderCapabilities,
    VideoAsset,
    VideoGenerationConfig,
    VideoGenerationError,
    VideoResolution,
    VideoResult,
)
from .providers import ProviderRegistry, VideoGenerationProvider, get_registry
from .video_engine import VideoGenerationTools

__all__ = [
    "AsyncVideoGenerationTools",
    "FailoverAttempt",
    "MediaCallback",
    "MediaMeta",
    "ModerationBlockedError",
    "OverrideIgnored",
    "ProviderCapabilities",
    "ProviderRegistry",
    "VideoAsset",
    "VideoGenerationConfig",
    "VideoGenerationError",
    "VideoGenerationProvider",
    "VideoGenerationTools",
    "VideoGenerator",
    "VideoResolution",
    "VideoResult",
    "get_registry",
]
