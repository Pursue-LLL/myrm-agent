"""[INPUT]
- ProviderCapabilities (POS: capabilities metadata from video generator)
- Pydantic BaseModel and FieldInfo specifications

[OUTPUT]
- VideoToolInput: Static baseline Pydantic model for video generation
- DynamicVideoToolInput: Dynamically pruned Pydantic model with extra="allow"
- _build_dynamic_video_input_schema: Factory constructing the dynamic schema

[POS]
Schema definitions and dynamic schema diet builder for video generation tool.
Keeps System Prompt Prefix Cache stable while allowing runtime parameter passthrough.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic.fields import FieldInfo


class VideoToolInput(BaseModel):
    action: Literal["generate", "status", "list"] = Field(
        default="generate",
        description="Action to perform: 'generate' (submit async video creation task), 'status' (query progress of task_id), 'list' (discover supported video models and providers).",
    )
    prompt: str | None = Field(
        default=None,
        description="Detailed text prompt describing the video scene, motion, subject, and lighting (required for generate).",
    )
    provider: str | None = Field(
        default=None, description="Optional provider override (e.g. 'kling', 'luma', 'runway', 'minimax')."
    )
    model: str | None = Field(default=None, description="Optional model override.")
    duration_seconds: int | None = Field(default=None, description="Target clip duration in seconds (e.g. 5 or 10).")
    aspect_ratio: str | None = Field(default=None, description="Aspect ratio (e.g. '16:9', '9:16', '1:1').")
    resolution: str | None = Field(default=None, description="Video resolution: '720p', '1080p', or '4k'.")
    enable_audio: bool | None = Field(
        default=None, description="Whether to synthesize an audio/sound effects track when supported."
    )
    reference_images: list[str] | None = Field(
        default=None,
        description="Optional image URLs or local paths for image-to-video (I2V) generation.",
    )
    reference_videos: list[str] | None = Field(
        default=None,
        description="Optional video URLs or local paths for video-to-video (V2V) transformation.",
    )
    negative_prompt: str | None = Field(
        default=None,
        description="Negative prompt specifying elements to avoid (e.g. 'distorted faces, blurry, watermark, extra limbs').",
    )
    seed: int | None = Field(
        default=None,
        description="Random seed for reproducible video generation across multiple storyboard scenes.",
    )
    force: bool = Field(default=False, description="Force enqueue a new generation even if an existing session task is active.")
    task_id: str | None = Field(
        default=None,
        description="Task ID returned from a previous action='generate' call (required when action='status').",
    )


def _build_dynamic_video_input_schema(capabilities: object | None) -> type[BaseModel]:
    """Dynamically construct a trimmed VideoToolInput schema based on active provider capabilities.

    If a provider does NOT support audio, aspect_ratio, or reference_videos, those fields
    are omitted from the schema. This implements the Dynamic Schema Diet pattern from
    Hermes-Agent, preventing LLM parameter hallucinations (400 Bad Request).
    """
    from myrm_agent_harness.toolkits.llms.video.models import ProviderCapabilities

    if not isinstance(capabilities, ProviderCapabilities):
        return VideoToolInput

    supports_audio = bool(capabilities.supports_audio)
    supports_aspect_ratio = bool(capabilities.supports_aspect_ratio)
    max_input_videos = int(capabilities.max_input_videos or 0)
    max_duration_seconds = capabilities.max_duration_seconds

    fields: dict[str, tuple[object, FieldInfo]] = {
        "action": (
            Literal["generate", "status", "list"],
            FieldInfo(
                default="generate",
                description="Action to perform: 'generate' (submit async video creation task), 'status' (query progress of task_id), 'list' (discover supported video models and providers).",
            ),
        ),
        "prompt": (
            str | None,
            FieldInfo(
                default=None,
                description="Detailed text prompt describing the video scene, motion, subject, and lighting (required for generate).",
            ),
        ),
        "provider": (
            str | None,
            FieldInfo(default=None, description="Optional provider override (e.g. 'fal', 'kling', 'luma', 'runway', 'minimax')."),
        ),
        "model": (str | None, FieldInfo(default=None, description="Optional model override.")),
        "duration_seconds": (
            int | None,
            FieldInfo(
                default=None,
                description=(
                    f"Target clip duration in seconds (max {max_duration_seconds}s for current provider)."
                    if max_duration_seconds
                    else "Target clip duration in seconds (e.g. 5 or 10)."
                ),
            ),
        ),
    }

    if supports_aspect_ratio:
        fields["aspect_ratio"] = (
            str | None,
            FieldInfo(default=None, description="Aspect ratio (e.g. '16:9', '9:16', '1:1')."),
        )
    fields["resolution"] = (
        str | None,
        FieldInfo(default=None, description="Video resolution: '720p', '1080p', or '4k'."),
    )

    if supports_audio:
        fields["enable_audio"] = (
            bool | None,
            FieldInfo(default=None, description="Whether to synthesize an audio/sound effects track when supported."),
        )

    fields["reference_images"] = (
        list[str] | None,
        FieldInfo(
            default=None,
            description="Optional image URLs or local paths for image-to-video (I2V) generation.",
        ),
    )

    if max_input_videos > 0:
        fields["reference_videos"] = (
            list[str] | None,
            FieldInfo(
                default=None,
                description="Optional video URLs or local paths for video-to-video (V2V) transformation.",
            ),
        )

    fields["negative_prompt"] = (
        str | None,
        FieldInfo(
            default=None,
            description="Negative prompt specifying elements to avoid (e.g. 'distorted faces, blurry, watermark, extra limbs').",
        ),
    )
    fields["seed"] = (
        int | None,
        FieldInfo(default=None, description="Random seed for reproducible video generation across multiple storyboard scenes."),
    )
    fields["force"] = (
        bool,
        FieldInfo(default=False, description="Force enqueue a new generation even if an existing session task is active."),
    )
    fields["task_id"] = (
        str | None,
        FieldInfo(default=None, description="Task ID returned from a previous action='generate' call (required when action='status')."),
    )

    return create_model(
        "DynamicVideoToolInput",
        __config__=ConfigDict(extra="allow"),
        **fields,
    )  # type: ignore[call-overload]
