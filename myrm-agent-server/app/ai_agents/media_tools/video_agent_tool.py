"""[INPUT]
- myrm_agent_harness.toolkits.llms.video.video_engine::VideoGenerationTools (POS: video generation engine)

[OUTPUT]
- create_video_generation_tool(): LangChain BaseTool adapter for video generation

[POS]
LangChain adapter for harness VideoGenerationTools (product layer).
"""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from myrm_agent_harness.toolkits.llms.video.video_engine import VideoGenerationTools


class VideoToolInput(BaseModel):
    action: Literal["generate", "status", "list"] = Field(
        default="generate",
        description='Use "generate", "status", or "list".',
    )
    prompt: str | None = Field(default=None, description="Text prompt (required for generate).")
    provider: str | None = Field(default=None, description="Override provider.")
    model: str | None = Field(default=None, description="Override model.")
    duration_seconds: int | None = Field(default=None, description="Clip duration in seconds.")
    aspect_ratio: str | None = Field(default=None, description='e.g. "16:9".')
    resolution: str | None = Field(default=None, description='e.g. "720p".')
    enable_audio: bool | None = Field(default=None, description="Enable audio track when supported.")
    reference_images: list[str] | None = Field(default=None, description="Reference image URLs/paths.")
    reference_videos: list[str] | None = Field(default=None, description="Reference video URLs/paths.")
    force: bool = Field(default=False, description="Force new generation even if a task is active.")


def create_video_generation_tool(engine: VideoGenerationTools) -> BaseTool:
    """Wrap a VideoGenerationTools engine as a LangChain tool named ``video_tool``."""

    @tool("video_tool", args_schema=VideoToolInput)
    async def video_tool(
        action: Literal["generate", "status", "list"] = "generate",
        prompt: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        duration_seconds: int | None = None,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        enable_audio: bool | None = None,
        reference_images: list[str] | None = None,
        reference_videos: list[str] | None = None,
        force: bool = False,
    ) -> str:
        """Generate, poll, or list video generation providers."""
        return await engine.execute(
            action,
            prompt=prompt,
            provider=provider,
            model=model,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            enable_audio=enable_audio,
            reference_images=reference_images,
            reference_videos=reference_videos,
            force=force,
        )

    video_tool.description = engine.tool_description
    return video_tool
