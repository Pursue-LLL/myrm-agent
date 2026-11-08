"""Vision Toolkits.

[INPUT]
- 图像/视频输入（回退模型配置）

[OUTPUT]
- VisionFallbackEngine: 视觉回退引擎（视频双槽位）
- create_vision_fallback_engine(): 工厂函数

[POS]
Vision capability layer — orchestrates fallback chains
for images and videos (including dual-slot video parity).
"""

from .fallback_engine import (
    VisionDescriptionError,
    VisionFallbackEngine,
    create_vision_fallback_engine,
    pick_video_fallback_model_cfgs,
    resolve_vision_fallback_llm_configs,
)
from .ocr_tier import OcrTierEngine
from .transcode import has_ffmpeg, transcode_video_h264
from .types import (
    VisionBackendKind,
    VisionResult,
)
from .video_analysis_engine import VideoAnalysisEngine

__all__ = [
    "OcrTierEngine",
    "VideoAnalysisEngine",
    "VisionBackendKind",
    "VisionDescriptionError",
    "VisionFallbackEngine",
    "VisionResult",
    "create_vision_fallback_engine",
    "has_ffmpeg",
    "pick_video_fallback_model_cfgs",
    "resolve_vision_fallback_llm_configs",
    "transcode_video_h264",
]
