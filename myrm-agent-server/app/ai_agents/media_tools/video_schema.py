"""[INPUT]
- ProviderCapabilities (POS: capabilities metadata from video generation providers)
- Pydantic BaseModel and FieldInfo specifications

[OUTPUT]
- build_video_input_schema: Factory constructing the video tool input schema for a provider's capabilities

[POS]
Schema definition for the video generation tool. A provider that cannot do audio, aspect ratios or video input
does not get those parameters (a schema diet that prevents the model from hallucinating them); ``extra="allow"``
still lets a superset call through, and the generator reports what it ignored. The schema is fixed per provider,
so it keeps the system prompt prefix cache stable.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.toolkits.llms.video.models import ProviderCapabilities
from pydantic import BaseModel, ConfigDict, create_model
from pydantic.fields import FieldInfo

_REFERENCE_FORMS = "media:// references from earlier results, workspace file paths or http(s) URLs"


def build_video_input_schema(capabilities: ProviderCapabilities | None) -> type[BaseModel]:
    """Tool input model for ``video_tool``; ``capabilities`` of ``None`` keeps every parameter."""
    max_duration_seconds = capabilities.max_duration_seconds if capabilities else None
    fields: dict[str, tuple[object, FieldInfo]] = {
        "action": (
            Literal["generate", "status", "list"],
            FieldInfo(default="generate", description="Action to perform: 'generate', 'status' or 'list'."),
        ),
        "prompt": (
            str | None,
            FieldInfo(
                default=None,
                description="Detailed description of the video scene, motion, subject and lighting (required for generate).",
            ),
        ),
        "provider": (
            str | None,
            FieldInfo(default=None, description="Optional provider override; the ids are in the action='list' result."),
        ),
        "model": (
            str | None,
            FieldInfo(default=None, description="Optional model override; the ids are in the action='list' result."),
        ),
        "duration_seconds": (
            int | None,
            FieldInfo(
                default=None,
                description=(
                    f"Target clip duration in seconds (max {max_duration_seconds}s for the current provider)."
                    if max_duration_seconds
                    else "Target clip duration in seconds (e.g. 5 or 10)."
                ),
            ),
        ),
        "aspect_ratio": (
            str | None,
            FieldInfo(default=None, description="Aspect ratio (e.g. '16:9', '9:16', '1:1')."),
        ),
        "resolution": (
            str | None,
            FieldInfo(default=None, description="Video resolution: '720p', '1080p', or '4k'."),
        ),
        "enable_audio": (
            bool | None,
            FieldInfo(default=None, description="Whether to synthesize an audio track when supported."),
        ),
        "reference_images": (
            list[str] | None,
            FieldInfo(default=None, description=f"Reference images for image-to-video: {_REFERENCE_FORMS}."),
        ),
        "reference_videos": (
            list[str] | None,
            FieldInfo(default=None, description=f"Reference videos for video-to-video: {_REFERENCE_FORMS}."),
        ),
        "negative_prompt": (
            str | None,
            FieldInfo(default=None, description="Elements to avoid (e.g. 'distorted faces, blurry, watermark, extra limbs')."),
        ),
        "seed": (
            int | None,
            FieldInfo(default=None, description="Random seed for reproducible results across the scenes of a storyboard."),
        ),
        "task_id": (
            str | None,
            FieldInfo(default=None, description="Task ID from an earlier generate result (required when action='status')."),
        ),
    }

    if capabilities is not None:
        if not capabilities.supports_aspect_ratio:
            del fields["aspect_ratio"]
        if not capabilities.supports_audio:
            del fields["enable_audio"]
        if capabilities.max_input_videos <= 0:
            del fields["reference_videos"]

    # pydantic types a field definition as ``TypeForm``, which a runtime-built annotation cannot satisfy statically.
    model: type[BaseModel] = create_model(  # type: ignore[call-overload]
        "VideoToolInput",
        __config__=ConfigDict(extra="allow"),
        **fields,  # pyright: ignore[reportArgumentType]
    )
    return model
